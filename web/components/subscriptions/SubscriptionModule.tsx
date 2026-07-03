"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { API_BASE, authFetch, getStoredUser } from "@/lib/auth";

type Resource = { used: number; limit: number | null; remaining: number | null; percent: number };
type Summary = {
  subscription: { status: string; expires_at?: string | null };
  plan: { key: string; name: string };
  period: string;
  resources: Record<string, Resource>;
};
type Plan = { key: string; name: string; limits: Record<string, number | null> };
type Request = { id: string; requested_plan: string; status: string; note?: string; created_at: string };

const labels: Record<string, string> = {
  sites: "Website", members: "Thành viên", messages: "Tin nhắn AI", crawl_pages: "Trang crawl",
};
const planPresentation: Record<string, {
  title: string; price: string; suffix?: string; badge?: string; action: string; features: string[];
}> = {
  starter: {
    title: "Khởi đầu", price: "Miễn phí", action: "Chọn gói Khởi đầu",
    features: ["1 website", "1.000 hội thoại AI mỗi tháng", "Lập chỉ mục 100 trang", "1 thành viên"],
  },
  growth: {
    title: "Tăng trưởng", price: "2,4 triệu", suffix: "VNĐ/tháng", badge: "Phổ biến nhất",
    action: "Chọn gói Tăng trưởng",
    features: ["5 website", "10.000 hội thoại AI mỗi tháng", "Lập chỉ mục 2.000 trang", "5 thành viên và handoff"],
  },
  business: {
    title: "Doanh nghiệp", price: "9,8 triệu", suffix: "VNĐ/tháng",
    action: "Liên hệ tư vấn",
    features: ["20 website", "100.000 hội thoại AI mỗi tháng", "Lập chỉ mục 20.000 trang", "20 thành viên và hỗ trợ ưu tiên"],
  },
  custom: {
    title: "Tùy chỉnh", price: "Linh hoạt", action: "Liên hệ triển khai",
    features: ["Kết nối API model riêng", "Tự chọn nhà cung cấp AI", "Hạn mức theo nhu cầu", "Hỗ trợ cấu hình và triển khai"],
  },
};

export function SubscriptionModule() {
  const [data, setData] = useState<Summary | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [requests, setRequests] = useState<Request[]>([]);
  const [requestOpen, setRequestOpen] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const user = getStoredUser();

  const load = useCallback(async () => {
    const [summaryResponse, plansResponse, requestsResponse] = await Promise.all([
      authFetch(`${API_BASE}/subscriptions/me`),
      fetch(`${API_BASE}/subscriptions/plans`),
      authFetch(`${API_BASE}/subscriptions/requests/me`),
    ]);
    if (!summaryResponse.ok) throw new Error("Không thể tải thông tin gói");
    setData((await summaryResponse.json()) as Summary);
    if (plansResponse.ok) setPlans((await plansResponse.json()) as Plan[]);
    if (requestsResponse.ok) setRequests((await requestsResponse.json()) as Request[]);
  }, []);
  useEffect(() => {
    const frame = requestAnimationFrame(() => void load().catch((reason: Error) => setError(reason.message)));
    return () => cancelAnimationFrame(frame);
  }, [load]);

  async function submitRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const response = await authFetch(`${API_BASE}/subscriptions/requests`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ requested_plan: form.get("requested_plan"), note: form.get("note") || null }),
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as { detail?: string };
      setError(typeof body.detail === "string" ? body.detail : "Không thể gửi yêu cầu.");
      return;
    }
    setMessage("Yêu cầu nâng cấp đã được gửi tới quản trị viên.");
    setRequestOpen(false);
    await load();
  }

  return <main className="dashboard-content subscription-page">
    <div className="dashboard-page-heading"><div><h1>Gói dịch vụ & hạn mức</h1><p>Theo dõi tài nguyên Auralis AI trong kỳ hiện tại.</p></div></div>
    {error && <p className="subscription-error">{error}</p>}
    {message && <p className="subscription-notice">{message}</p>}
    {!data && !error && <p>Đang tải hạn mức...</p>}
    {data && <>
      <section className="subscription-hero">
        <div><span>Gói hiện tại</span><h2>{data.plan.name}</h2><p>Trạng thái: {data.subscription.status}{data.subscription.expires_at ? ` · Hết hạn ${new Date(data.subscription.expires_at).toLocaleDateString("vi-VN")}` : ""}</p></div>
        <div><span>Kỳ sử dụng</span><strong>{data.period}</strong></div>
        {user?.role === "user" && <button type="button" onClick={() => setRequestOpen(true)}>Yêu cầu nâng cấp</button>}
      </section>
      <section className="quota-grid">{Object.entries(data.resources).map(([key, resource]) =>
        <article className="quota-card" key={key}>
          <header><h3>{labels[key] || key}</h3><strong>{resource.used.toLocaleString("vi-VN")} / {resource.limit === null ? "Không giới hạn" : resource.limit.toLocaleString("vi-VN")}</strong></header>
          <div className="quota-track"><span className={resource.percent >= 90 ? "danger" : resource.percent >= 80 ? "warning" : ""} style={{ width: `${resource.limit === null ? 0 : resource.percent}%` }} /></div>
          <p>{resource.limit === null ? "Không áp dụng giới hạn" : `Còn lại ${resource.remaining?.toLocaleString("vi-VN")}`}</p>
        </article>)}</section>
      <section className="subscription-admin-section"><header><div><h2>Yêu cầu của bạn</h2><p>Theo dõi trạng thái nâng cấp.</p></div></header>
        <div className="subscription-table-wrap"><table className="subscription-table"><thead><tr><th>Gói yêu cầu</th><th>Ngày gửi</th><th>Ghi chú</th><th>Trạng thái</th></tr></thead><tbody>
          {requests.length ? requests.map((request) => <tr key={request.id}><td><strong>{request.requested_plan}</strong></td><td>{new Date(request.created_at).toLocaleString("vi-VN")}</td><td>{request.note || "—"}</td><td><span className={`subscription-status ${request.status}`}>{request.status}</span></td></tr>) : <tr><td colSpan={4}>Chưa có yêu cầu nâng cấp.</td></tr>}
        </tbody></table></div>
      </section>
    </>}

    {requestOpen && data && <div className="sites-modal-layer">
      <button className="sites-modal-backdrop" onClick={() => setRequestOpen(false)} aria-label="Đóng" />
      <section className="sites-modal subscription-modal subscription-upgrade-modal" role="dialog" aria-modal="true">
        <div className="sites-modal-header"><div><h2>Yêu cầu nâng cấp</h2><p>Gói hiện tại: {data.plan.name}</p></div><button onClick={() => setRequestOpen(false)}>×</button></div>
        <form onSubmit={submitRequest}>
          <div className="subscription-plan-options">{plans.map((plan) => {
            const view = planPresentation[plan.key] || {
              title: plan.name, price: "Liên hệ", action: `Chọn ${plan.name}`, features: [],
            };
            const current = plan.key === data.plan.key;
            return <label className={`subscription-plan-card ${plan.key === "growth" ? "featured" : ""} ${current ? "current" : ""}`} key={plan.key}>
              {view.badge && <span className="subscription-plan-badge">{view.badge}</span>}
              <input type="radio" name="requested_plan" value={plan.key} required disabled={current} />
              <span className="subscription-plan-card-body">
                <strong className="subscription-plan-name">{view.title}</strong>
                <span className="subscription-plan-price">{view.price} {view.suffix && <small>{view.suffix}</small>}</span>
                <span className="subscription-plan-features">{view.features.map((feature) => <span key={feature}><b>✓</b>{feature}</span>)}</span>
                <span className="subscription-plan-action">{current ? "Gói hiện tại" : view.action}</span>
              </span>
            </label>;
          })}</div>
          <label>Lời nhắn<textarea name="note" rows={4} placeholder="Nhu cầu hoặc thông tin thanh toán..." /></label>
          <div className="sites-modal-actions"><button type="button" onClick={() => setRequestOpen(false)}>Hủy</button><button className="sites-primary-button">Gửi yêu cầu</button></div>
        </form>
      </section>
    </div>}
  </main>;
}
