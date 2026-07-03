"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { API_BASE, authFetch } from "@/lib/auth";

type Resource = { used: number; limit: number | null };
type Row = {
  user: { id: string; name?: string; email: string };
  plan: { key: string; name: string };
  subscription: {
    status: string; expires_at?: string | null;
    custom_limits?: Record<string, number | null>;
  };
  resources: Record<string, Resource>;
};
type UpgradeRequest = {
  id: string; owner_id: string; owner_name?: string; owner_email?: string;
  current_plan: string; requested_plan: string; status: string; note?: string;
  created_at: string;
};
type Audit = {
  id: string; action: string; plan?: string; status?: string; note?: string;
  created_at: string;
};
type Promo = { id: string; code: string; percent_off: number; active: boolean; redemptions: number; max_redemptions?: number | null };

const resourceLabels: Record<string, string> = {
  sites: "Website", members: "Thành viên", messages: "Tin nhắn", crawl_pages: "Trang crawl",
};

async function detail(response: Response, fallback: string) {
  const body = (await response.json().catch(() => ({}))) as { detail?: string };
  return typeof body.detail === "string" ? body.detail : fallback;
}

export function AdminSubscriptionsModule() {
  const [rows, setRows] = useState<Row[]>([]);
  const [requests, setRequests] = useState<UpgradeRequest[]>([]);
  const [editing, setEditing] = useState<Row | null>(null);
  const [history, setHistory] = useState<Audit[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [promos, setPromos] = useState<Promo[]>([]);

  const load = useCallback(async () => {
    const [accountsResponse, requestsResponse, promosResponse] = await Promise.all([
      authFetch(`${API_BASE}/subscriptions/admin`),
      authFetch(`${API_BASE}/subscriptions/admin/requests`),
      authFetch(`${API_BASE}/checkout/promos`),
    ]);
    if (accountsResponse.ok) setRows((await accountsResponse.json()) as Row[]);
    if (requestsResponse.ok) setRequests((await requestsResponse.json()) as UpgradeRequest[]);
    if (promosResponse.ok) setPromos((await promosResponse.json()) as Promo[]);
  }, []);
  useEffect(() => {
    const frame = requestAnimationFrame(() => void load());
    return () => cancelAnimationFrame(frame);
  }, [load]);

  async function openEdit(row: Row) {
    setEditing(row);
    const response = await authFetch(`${API_BASE}/subscriptions/admin/${row.user.id}/history`);
    setHistory(response.ok ? ((await response.json()) as Audit[]) : []);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    const form = new FormData(event.currentTarget);
    const custom_limits: Record<string, number | null> = {};
    for (const key of Object.keys(resourceLabels)) {
      const value = String(form.get(key) ?? "").trim();
      if (value) custom_limits[key] = Number(value);
    }
    const response = await authFetch(`${API_BASE}/subscriptions/admin/${editing.user.id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        plan: form.get("plan"), status: form.get("status"),
        expires_at: form.get("expires_at") || null, custom_limits,
        note: form.get("note") || null,
      }),
    });
    if (!response.ok) { setError(await detail(response, "Không thể cập nhật subscription.")); return; }
    setMessage("Đã cập nhật subscription.");
    setEditing(null);
    await load();
  }

  async function decide(request: UpgradeRequest, decision: "approved" | "rejected") {
    const note = window.prompt(decision === "approved" ? "Ghi chú phê duyệt (không bắt buộc)" : "Lý do từ chối");
    if (note === null) return;
    const response = await authFetch(`${API_BASE}/subscriptions/admin/requests/${request.id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, note: note || null }),
    });
    if (!response.ok) { setError(await detail(response, "Không thể xử lý yêu cầu.")); return; }
    setMessage(decision === "approved" ? "Đã duyệt và áp dụng gói mới." : "Đã từ chối yêu cầu.");
    await load();
  }
  async function createPromo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const response = await authFetch(`${API_BASE}/checkout/promos`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: form.get("code"), percent_off: Number(form.get("percent_off")),
        max_redemptions: form.get("max_redemptions") ? Number(form.get("max_redemptions")) : null,
        active: true,
      }),
    });
    if (!response.ok) { setError(await detail(response, "Không thể tạo promo.")); return; }
    event.currentTarget.reset(); setMessage("Đã tạo mã giảm giá."); await load();
  }

  return <main className="dashboard-content subscription-page">
    <div className="dashboard-page-heading"><div><h1>Quản lý Subscription</h1><p>Kiểm soát gói, hạn mức, usage và yêu cầu nâng cấp.</p></div></div>
    {message && <p className="subscription-notice">{message}</p>}
    {error && <p className="subscription-error">{error}</p>}
    <section className="subscription-admin-section promo-admin">
      <header><div><h2>Mã giảm giá</h2><p>Tạo promo theo phần trăm, bao gồm mã 100% để kiểm thử checkout.</p></div></header>
      <form onSubmit={createPromo}><input name="code" placeholder="Mã promo" required minLength={3} /><input name="percent_off" type="number" min={1} max={100} placeholder="% giảm" required /><input name="max_redemptions" type="number" min={1} placeholder="Số lượt (tùy chọn)" /><button className="sites-primary-button">Tạo promo</button></form>
      <div className="promo-list">{promos.map(promo => <span key={promo.id}><b>{promo.code}</b> Giảm {promo.percent_off}% · {promo.redemptions}/{promo.max_redemptions ?? "∞"} lượt · {promo.active ? "Đang bật" : "Đã tắt"}</span>)}</div>
    </section>

    <section className="subscription-admin-section">
      <header><div><h2>Yêu cầu nâng cấp</h2><p>{requests.filter((item) => item.status === "pending").length} yêu cầu đang chờ xử lý</p></div></header>
      <div className="subscription-table-wrap"><table className="subscription-table">
        <thead><tr><th>Khách hàng</th><th>Thay đổi</th><th>Ngày gửi</th><th>Trạng thái</th><th /></tr></thead>
        <tbody>{requests.length ? requests.map((request) => <tr key={request.id}>
          <td><strong>{request.owner_name || "Chủ website"}</strong><small>{request.owner_email}</small>{request.note && <small>“{request.note}”</small>}</td>
          <td>{request.current_plan} → <strong>{request.requested_plan}</strong></td>
          <td>{new Date(request.created_at).toLocaleString("vi-VN")}</td>
          <td><span className={`subscription-status ${request.status}`}>{request.status}</span></td>
          <td>{request.status === "pending" && <div className="subscription-actions"><button onClick={() => void decide(request, "approved")}>Duyệt</button><button className="danger" onClick={() => void decide(request, "rejected")}>Từ chối</button></div>}</td>
        </tr>) : <tr><td colSpan={5}>Chưa có yêu cầu nâng cấp.</td></tr>}</tbody>
      </table></div>
    </section>

    <section className="subscription-admin-section">
      <header><div><h2>Tài khoản khách hàng</h2><p>Chọn một tài khoản để chỉnh cấu hình chi tiết.</p></div></header>
      <div className="subscription-table-wrap"><table className="subscription-table">
        <thead><tr><th>Khách hàng</th><th>Gói</th><th>Website</th><th>Thành viên</th><th>Trang crawl</th><th>Tin nhắn</th><th /></tr></thead>
        <tbody>{rows.map((row) => <tr key={row.user.id}>
          <td><strong>{row.user.name || "Chưa đặt tên"}</strong><small>{row.user.email}</small></td>
          <td><span className={`subscription-status ${row.subscription.status}`}>{row.plan.name} · {row.subscription.status}</span></td>
          {["sites", "members", "crawl_pages", "messages"].map((key) => <td key={key}>{row.resources[key].used.toLocaleString("vi-VN")} / {row.resources[key].limit?.toLocaleString("vi-VN") ?? "∞"}</td>)}
          <td><button onClick={() => void openEdit(row)}>Chi tiết</button></td>
        </tr>)}</tbody>
      </table></div>
    </section>

    {editing && <div className="sites-modal-layer">
      <button className="sites-modal-backdrop" onClick={() => setEditing(null)} aria-label="Đóng" />
      <section className="sites-modal subscription-modal" role="dialog" aria-modal="true">
        <div className="sites-modal-header"><div><h2>{editing.user.name || editing.user.email}</h2><p>{editing.user.email}</p></div><button onClick={() => setEditing(null)}>×</button></div>
        <form onSubmit={save}>
          <div className="subscription-form-grid">
            <label>Gói<select name="plan" defaultValue={editing.plan.key}><option value="starter">Starter</option><option value="growth">Growth</option><option value="business">Business</option><option value="custom">Custom</option><option value="legacy">Legacy</option></select></label>
            <label>Trạng thái<select name="status" defaultValue={editing.subscription.status}><option value="active">Active</option><option value="trialing">Trialing</option><option value="past_due">Past due</option><option value="suspended">Suspended</option><option value="cancelled">Cancelled</option></select></label>
            <label>Ngày hết hạn<input name="expires_at" type="datetime-local" defaultValue={editing.subscription.expires_at?.slice(0, 16) || ""} /></label>
            {Object.entries(resourceLabels).map(([key, label]) => <label key={key}>Giới hạn {label}<input name={key} type="number" min={0} placeholder="Theo gói" defaultValue={editing.subscription.custom_limits?.[key] ?? ""} /></label>)}
            <label className="wide">Ghi chú<textarea name="note" rows={3} /></label>
          </div>
          <div className="sites-modal-actions"><button type="button" onClick={() => setEditing(null)}>Hủy</button><button className="sites-primary-button">Lưu thay đổi</button></div>
        </form>
        <div className="subscription-history"><h3>Lịch sử thay đổi</h3>{history.length ? history.map((item) => <article key={item.id}><strong>{item.action}</strong><span>{item.plan || item.status || ""}</span><time>{new Date(item.created_at).toLocaleString("vi-VN")}</time>{item.note && <p>{item.note}</p>}</article>) : <p>Chưa có lịch sử.</p>}</div>
      </section>
    </div>}
  </main>;
}
