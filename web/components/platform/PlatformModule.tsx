"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { API_BASE, authFetch } from "@/lib/auth";

type Dict = Record<string, unknown>;
type Overview = {
  customers: number; active_subscriptions: number; trials: number; expiring_in_7_days: number;
  monthly_revenue: number; paid_orders: number; abnormal_payments: number; open_requests: number;
  active_promos: number; subscriptions_by_plan: Record<string, number>;
};
type Customer = {
  id: string; email: string; name?: string; active: boolean; created_at: string;
  sites: number; members: number; subscription: { plan: string; status: string; current_period_end?: string };
};
type Plan = {
  id: string; key: string; name: string; description: string; monthly_price: number | null;
  vat_rate: number; trial_days: number; limits: Record<string, number | null>;
  features: Record<string, boolean>;
  display_features: string[];
  display_order: number; badge?: string; cta_label: string; is_public: boolean; is_active: boolean;
  allow_new_signup: boolean; allow_upgrade: boolean; allow_downgrade: boolean; requires_contact: boolean;
  version: number;
};
type Promo = {
  id: string; code: string; discount_type: string; discount_value: number; active: boolean;
  redemptions: number; max_redemptions?: number; expires_at?: string;
};
type PlatformRequest = {
  id: string; type: string; customer_id: string; priority: string; status: string;
  assigned_admin_id?: string; created_at: string; resolution?: string;
};
type Payment = {
  id: string; order_id: string; order_type: string; email: string; plan: string;
  total: number; status: string; created_at: string; completed_at?: string;
};
type Audit = {
  id: string; actor_email?: string; action: string; resource_type: string;
  resource_id: string; reason?: string; created_at: string;
};

const money = (value: number | null | undefined) =>
  value === null || value === undefined ? "Liên hệ" : `${value.toLocaleString("vi-VN")} VNĐ`;

async function json<T>(response: Response | Promise<Response>): Promise<T> {
  const resolved = await response;
  const body = await resolved.json().catch(() => ({}));
  if (!resolved.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Không thể tải dữ liệu");
  return body as T;
}

export function PlatformModule({ section }: { section: string }) {
  const normalized = ["overview", "customers", "plans", "requests", "promos", "payments", "audit"].includes(section) ? section : "overview";
  return <main className="platform-content">
    {normalized === "overview" && <OverviewView />}
    {normalized === "customers" && <CustomersView />}
    {normalized === "plans" && <PlansView />}
    {normalized === "requests" && <RequestsView />}
    {normalized === "promos" && <PromosView />}
    {normalized === "payments" && <PaymentsView />}
    {normalized === "audit" && <AuditView />}
  </main>;
}

function PageHead({ title, description, action }: { title: string; description: string; action?: React.ReactNode }) {
  return <header className="platform-page-head"><div><h1>{title}</h1><p>{description}</p></div>{action}</header>;
}

function ErrorBox({ value }: { value: string }) {
  return value ? <p className="platform-error">{value}</p> : null;
}

function OverviewView() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { void json<Overview>(authFetch(`${API_BASE}/platform/overview`)).then(setData).catch(e => setError(e.message)); }, []);
  const cards = data ? [
    ["Khách hàng", data.customers],
    ["Subscription hoạt động", data.active_subscriptions],
    ["Đang dùng thử", data.trials],
    ["Sắp hết hạn (7 ngày)", data.expiring_in_7_days],
    ["Doanh thu tháng", money(data.monthly_revenue)],
    ["Đơn đã thanh toán", data.paid_orders],
    ["Thanh toán bất thường", data.abnormal_payments],
    ["Yêu cầu đang mở", data.open_requests],
  ] : [];
  return <>
    <PageHead title="Tổng quan nền tảng" description="Tình trạng kinh doanh và vận hành Auralis theo thời gian thực." />
    <ErrorBox value={error} />
    <section className="platform-metric-grid">{cards.map(([label, value]) => <article key={String(label)}><span>{label}</span><strong>{value}</strong></article>)}</section>
    {data && <section className="platform-panel"><header><h2>Khách hàng theo gói</h2><span>{data.active_promos} promo đang hoạt động</span></header>
      <div className="platform-plan-bars">{Object.entries(data.subscriptions_by_plan).map(([plan, count]) => <div key={plan}><span>{plan}</span><b>{count}</b><i style={{ width: `${Math.max(8, count / Math.max(1, data.customers) * 100)}%` }} /></div>)}</div>
    </section>}
  </>;
}

function CustomersView() {
  const [items, setItems] = useState<Customer[]>([]);
  const [query, setQuery] = useState("");
  const [detail, setDetail] = useState<Dict | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    const result = await json<{ items: Customer[] }>(authFetch(`${API_BASE}/platform/customers?q=${encodeURIComponent(query)}`));
    setItems(result.items);
  }, [query]);
  useEffect(() => { void load().catch(e => setError(e.message)); }, [load]);
  async function openCustomer(id: string) {
    try { setDetail(await json<Dict>(authFetch(`${API_BASE}/platform/customers/${id}`))); } catch (e) { setError((e as Error).message); }
  }
  async function stateChange(id: string, action: "suspend" | "reactivate") {
    const reason = window.prompt("Lý do thay đổi trạng thái:");
    if (!reason) return;
    try {
      await json(authFetch(`${API_BASE}/platform/customers/${id}/${action}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason }),
      }));
      setDetail(null); await load();
    } catch (e) { setError((e as Error).message); }
  }
  const detailUser = detail?.user as Dict | undefined;
  const detailPlan = detail?.plan as Dict | undefined;
  const resources = detail?.resources as Record<string, { used: number; limit: number | null }> | undefined;
  return <>
    <PageHead title="Khách hàng" description="Quản lý chủ website, subscription, usage và trạng thái tài khoản." action={<input className="platform-search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Tìm công ty hoặc email..." />} />
    <ErrorBox value={error} />
    <section className="platform-table-card"><table><thead><tr><th>Khách hàng</th><th>Gói</th><th>Trạng thái</th><th>Website</th><th>Thành viên</th><th>Ngày tạo</th><th /></tr></thead><tbody>
      {items.map(item => <tr key={item.id}><td><strong>{item.name || "Chưa đặt tên"}</strong><small>{item.email}</small></td><td><span className="platform-chip blue">{item.subscription.plan}</span></td><td><span className={`platform-chip ${item.subscription.status}`}>{item.subscription.status}</span></td><td>{item.sites}</td><td>{item.members}</td><td>{new Date(item.created_at).toLocaleDateString("vi-VN")}</td><td><button onClick={() => void openCustomer(item.id)}>Chi tiết</button></td></tr>)}
    </tbody></table></section>
    {detail && detailUser && <div className="platform-modal-layer"><button className="platform-modal-backdrop" onClick={() => setDetail(null)} /><section className="platform-modal wide">
      <header><div><h2>{String(detailUser.name || "Khách hàng")}</h2><p>{String(detailUser.email || "")}</p></div><button onClick={() => setDetail(null)}>×</button></header>
      <div className="platform-detail-grid"><article><span>Gói hiện tại</span><strong>{String(detailPlan?.name || detailPlan?.key || "Legacy")}</strong></article><article><span>Trạng thái</span><strong>{String((detail.subscription as Dict)?.status || "")}</strong></article><article><span>Website</span><strong>{(detail.sites as unknown[])?.length || 0}</strong></article><article><span>Thành viên</span><strong>{(detail.members as unknown[])?.length || 0}</strong></article></div>
      {resources && <div className="platform-resource-list">{Object.entries(resources).map(([key, resource]) => <div key={key}><span>{key}</span><b>{resource.used.toLocaleString("vi-VN")} / {resource.limit === null ? "∞" : resource.limit.toLocaleString("vi-VN")}</b></div>)}</div>}
      <div className="platform-modal-actions"><button onClick={() => void stateChange(String(detailUser.id), "suspend")} className="danger">Tạm khóa</button><button onClick={() => void stateChange(String(detailUser.id), "reactivate")}>Mở lại</button></div>
    </section></div>}
  </>;
}

function PlansView() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [editing, setEditing] = useState<Plan | "new" | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => json<Plan[]>(authFetch(`${API_BASE}/platform/plans`)).then(setPlans), []);
  useEffect(() => { void load().catch(e => setError(e.message)); }, [load]);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const limits = { sites: numberOrNull(form.get("sites")), members: numberOrNull(form.get("members")), messages: numberOrNull(form.get("messages")), crawl_pages: numberOrNull(form.get("crawl_pages")) };
    const body = {
      key: form.get("key"), name: form.get("name"), description: form.get("description"),
      monthly_price: numberOrNull(form.get("monthly_price")), vat_rate: Number(form.get("vat_rate") || 10),
      trial_days: Number(form.get("trial_days") || 0), limits,
      features: { byok: form.get("byok") === "on", handoff: form.get("handoff") === "on", api: form.get("api") === "on", white_label: form.get("white_label") === "on" },
      display_features: String(form.get("display_features") || "").split("\n").map(v => v.trim()).filter(Boolean),
      display_order: Number(form.get("display_order") || 0), badge: form.get("badge") || null,
      cta_label: form.get("cta_label") || "Chọn gói", is_public: form.get("is_public") === "on",
      is_active: form.get("is_active") === "on", allow_new_signup: form.get("allow_new_signup") === "on",
      allow_upgrade: form.get("allow_upgrade") === "on", allow_downgrade: form.get("allow_downgrade") === "on",
      requires_contact: form.get("requires_contact") === "on",
    };
    try {
      const isNew = editing === "new";
      if (!isNew) delete (body as { key?: FormDataEntryValue | null }).key;
      await json(authFetch(`${API_BASE}/platform/plans${isNew ? "" : `/${(editing as Plan).id}`}`, {
        method: isNew ? "POST" : "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      }));
      setEditing(null); await load();
    } catch (e) { setError((e as Error).message); }
  }
  async function archive(plan: Plan) {
    if (!confirm(`Ngừng hoạt động gói ${plan.name}?`)) return;
    try { await json(authFetch(`${API_BASE}/platform/plans/${plan.id}/archive`, { method: "POST" })); await load(); } catch (e) { setError((e as Error).message); }
  }
  return <>
    <PageHead title="Cấu hình gói" description="Nguồn dữ liệu chung cho giá, quota, checkout và nâng cấp." action={<button className="platform-primary" onClick={() => setEditing("new")}>+ Thêm gói</button>} />
    <ErrorBox value={error} />
    <section className="platform-card-grid">{plans.map(plan => <article className={`platform-plan-card ${!plan.is_active ? "archived" : ""}`} key={plan.id}>
      <header><div><span>{plan.key} · v{plan.version}</span><h2>{plan.name}</h2></div>{plan.badge && <b>{plan.badge}</b>}</header><strong>{money(plan.monthly_price)}{plan.monthly_price !== null && <small>/tháng</small>}</strong><p>{plan.description}</p>
      <div className="platform-plan-limits">{Object.entries(plan.limits).map(([key, value]) => <span key={key}>{key}<b>{value === null ? "∞" : value.toLocaleString("vi-VN")}</b></span>)}</div>
      <footer><span className={`platform-chip ${plan.is_active ? "active" : "expired"}`}>{plan.is_active ? "Đang hoạt động" : "Đã lưu trữ"}</span><div><button onClick={() => setEditing(plan)}>Chỉnh sửa</button>{plan.is_active && <button className="danger" onClick={() => void archive(plan)}>Lưu trữ</button>}</div></footer>
    </article>)}</section>
    {editing && <PlanModal value={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSubmit={save} />}
  </>;
}

function numberOrNull(value: FormDataEntryValue | null) {
  const text = String(value ?? "").trim(); return text === "" ? null : Number(text);
}

function PlanModal({ value, onClose, onSubmit }: { value: Plan | null; onClose: () => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  return <div className="platform-modal-layer"><button className="platform-modal-backdrop" onClick={onClose} /><section className="platform-modal wide"><header><div><h2>{value ? "Chỉnh sửa gói" : "Thêm gói mới"}</h2><p>Thay đổi chỉ áp dụng cho giao dịch và kỳ mới.</p></div><button onClick={onClose}>×</button></header>
    <form className="platform-form" onSubmit={onSubmit}>
      <label>Mã gói<input name="key" defaultValue={value?.key || ""} disabled={!!value} required /></label><label>Tên gói<input name="name" defaultValue={value?.name || ""} required /></label>
      <label className="span-2">Mô tả<input name="description" defaultValue={value?.description || ""} /></label>
      <label>Giá tháng<input name="monthly_price" type="number" defaultValue={value?.monthly_price ?? ""} placeholder="Để trống nếu liên hệ" /></label><label>VAT (%)<input name="vat_rate" type="number" defaultValue={value?.vat_rate ?? 10} /></label>
      <label>Trial (ngày)<input name="trial_days" type="number" defaultValue={value?.trial_days ?? 0} /></label><label>Thứ tự<input name="display_order" type="number" defaultValue={value?.display_order ?? 0} /></label>
      {["sites", "members", "messages", "crawl_pages"].map(key => <label key={key}>Giới hạn {key}<input name={key} type="number" defaultValue={value?.limits[key] ?? ""} placeholder="Trống = không giới hạn" /></label>)}
      <label>Nhãn nổi bật<input name="badge" defaultValue={value?.badge || ""} /></label><label>Nội dung CTA<input name="cta_label" defaultValue={value?.cta_label || "Chọn gói"} /></label>
      <label className="span-2">Các dòng tính năng<textarea name="display_features" rows={4} defaultValue={value?.display_features?.join("\n") || ""} placeholder="Mỗi dòng là một tính năng" /></label>
      <div className="platform-checks span-2">{[
        ["is_public", "Hiển thị công khai", value?.is_public ?? true], ["is_active", "Đang hoạt động", value?.is_active ?? true],
        ["allow_new_signup", "Cho đăng ký mới", value?.allow_new_signup ?? true], ["allow_upgrade", "Cho nâng cấp", value?.allow_upgrade ?? true],
        ["allow_downgrade", "Cho hạ cấp", value?.allow_downgrade ?? true], ["requires_contact", "Yêu cầu liên hệ", value?.requires_contact ?? false],
        ["byok", "BYOK", value?.features?.byok ?? false], ["handoff", "Handoff", value?.features?.handoff ?? false], ["api", "API", value?.features?.api ?? false], ["white_label", "White-label", value?.features?.white_label ?? false],
      ].map(([name, label, checked]) => <label key={String(name)}><input type="checkbox" name={String(name)} defaultChecked={Boolean(checked)} />{String(label)}</label>)}</div>
      <div className="platform-modal-actions span-2"><button type="button" onClick={onClose}>Hủy</button><button className="platform-primary">Lưu cấu hình</button></div>
    </form>
  </section></div>;
}

function PromosView() {
  const [items, setItems] = useState<Promo[]>([]); const [open, setOpen] = useState(false); const [error, setError] = useState("");
  const load = useCallback(() => json<Promo[]>(authFetch(`${API_BASE}/checkout/promos`)).then(setItems), []);
  useEffect(() => { void load().catch(e => setError(e.message)); }, [load]);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    try {
      await json(authFetch(`${API_BASE}/checkout/promos`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        code: form.get("code"), discount_type: form.get("discount_type"), discount_value: Number(form.get("discount_value")),
        percent_off: form.get("discount_type") === "percent" ? Number(form.get("discount_value")) : null,
        max_redemptions: form.get("max_redemptions") ? Number(form.get("max_redemptions")) : null,
        expires_at: form.get("expires_at") || null, active: true,
      }) })); setOpen(false); await load();
    } catch (e) { setError((e as Error).message); }
  }
  async function toggle(item: Promo) {
    try { await json(authFetch(`${API_BASE}/checkout/promos/${item.id}?active=${!item.active}`, { method: "PATCH" })); await load(); } catch (e) { setError((e as Error).message); }
  }
  return <>
    <PageHead title="Mã giảm giá" description="Tạo và kiểm soát promo cho đăng ký, nâng cấp và gia hạn." action={<button className="platform-primary" onClick={() => setOpen(true)}>+ Tạo mã</button>} /><ErrorBox value={error} />
    <section className="platform-table-card"><table><thead><tr><th>Mã</th><th>Giá trị</th><th>Đã dùng</th><th>Hết hạn</th><th>Trạng thái</th><th /></tr></thead><tbody>{items.map(item => <tr key={item.id}><td><strong>{item.code}</strong></td><td>{item.discount_type === "fixed" ? money(item.discount_value) : `${item.discount_value}%`}</td><td>{item.redemptions} / {item.max_redemptions || "∞"}</td><td>{item.expires_at ? new Date(item.expires_at).toLocaleDateString("vi-VN") : "Không giới hạn"}</td><td><span className={`platform-chip ${item.active ? "active" : "expired"}`}>{item.active ? "Hoạt động" : "Tạm dừng"}</span></td><td><button onClick={() => void toggle(item)}>{item.active ? "Tạm dừng" : "Bật lại"}</button></td></tr>)}</tbody></table></section>
    {open && <div className="platform-modal-layer"><button className="platform-modal-backdrop" onClick={() => setOpen(false)} /><section className="platform-modal"><header><h2>Tạo mã giảm giá</h2><button onClick={() => setOpen(false)}>×</button></header><form className="platform-form" onSubmit={create}><label>Mã promo<input name="code" required /></label><label>Loại<select name="discount_type"><option value="percent">Phần trăm</option><option value="fixed">Số tiền cố định</option></select></label><label>Giá trị<input name="discount_value" type="number" min="1" required /></label><label>Tổng lượt<input name="max_redemptions" type="number" min="1" /></label><label className="span-2">Ngày hết hạn<input name="expires_at" type="datetime-local" /></label><div className="platform-modal-actions span-2"><button type="button" onClick={() => setOpen(false)}>Hủy</button><button className="platform-primary">Tạo mã</button></div></form></section></div>}
  </>;
}

function RequestsView() {
  const [items, setItems] = useState<PlatformRequest[]>([]); const [error, setError] = useState("");
  const load = useCallback(() => json<PlatformRequest[]>(authFetch(`${API_BASE}/platform/requests`)).then(setItems), []);
  useEffect(() => { void load().catch(e => setError(e.message)); }, [load]);
  async function update(item: PlatformRequest, status: string) {
    try { await json(authFetch(`${API_BASE}/platform/requests/${item.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) })); await load(); } catch (e) { setError((e as Error).message); }
  }
  return <><PageHead title="Yêu cầu & ngoại lệ" description="Xử lý Custom, quota đặc biệt, hoàn tiền và giao dịch bất thường." /><ErrorBox value={error} /><section className="platform-table-card"><table><thead><tr><th>Loại</th><th>Khách hàng</th><th>Ưu tiên</th><th>Ngày tạo</th><th>Trạng thái</th><th /></tr></thead><tbody>{items.map(item => <tr key={item.id}><td><strong>{item.type}</strong></td><td>{item.customer_id}</td><td><span className={`platform-chip ${item.priority}`}>{item.priority}</span></td><td>{new Date(item.created_at).toLocaleString("vi-VN")}</td><td><span className={`platform-chip ${item.status}`}>{item.status}</span></td><td><select value={item.status} onChange={e => void update(item, e.target.value)}><option value="new">Mới</option><option value="in_progress">Đang xử lý</option><option value="waiting_customer">Chờ khách</option><option value="approved">Đã duyệt</option><option value="rejected">Từ chối</option><option value="completed">Hoàn tất</option></select></td></tr>)}</tbody></table></section></>;
}

function PaymentsView() {
  const [items, setItems] = useState<Payment[]>([]); const [error, setError] = useState(""); const [message, setMessage] = useState("");
  const load = useCallback(() => json<Payment[]>(authFetch(`${API_BASE}/platform/payments`)).then(setItems), []);
  useEffect(() => { void load().catch(e => setError(e.message)); }, [load]);
  async function reconcile(item: Payment) {
    setMessage(""); try { const result = await json<{ provider: { data?: { order_status?: string } } }>(authFetch(`${API_BASE}/platform/payments/${item.order_id}/reconcile`, { method: "POST" })); setMessage(`SePay: ${result.provider.data?.order_status || "Đã đối soát"}`); } catch (e) { setError((e as Error).message); }
  }
  return <><PageHead title="Thanh toán" description="Theo dõi đơn SePay, trạng thái và đối soát giao dịch." /><ErrorBox value={error} />{message && <p className="platform-notice">{message}</p>}<section className="platform-table-card"><table><thead><tr><th>Đơn hàng</th><th>Khách hàng</th><th>Loại</th><th>Gói</th><th>Số tiền</th><th>Trạng thái</th><th /></tr></thead><tbody>{items.map(item => <tr key={item.id}><td><strong>{item.order_id}</strong><small>{new Date(item.created_at).toLocaleString("vi-VN")}</small></td><td>{item.email}</td><td>{item.order_type}</td><td>{item.plan}</td><td>{money(item.total)}</td><td><span className={`platform-chip ${item.status}`}>{item.status}</span></td><td><button onClick={() => void reconcile(item)}>Đối soát</button></td></tr>)}</tbody></table></section></>;
}

function AuditView() {
  const [items, setItems] = useState<Audit[]>([]); const [error, setError] = useState("");
  useEffect(() => { void json<Audit[]>(authFetch(`${API_BASE}/platform/audit-logs`)).then(setItems).catch(e => setError(e.message)); }, []);
  return <><PageHead title="Nhật ký quản trị" description="Dấu vết không chỉnh sửa của mọi thao tác quan trọng." /><ErrorBox value={error} /><section className="platform-table-card"><table><thead><tr><th>Thời gian</th><th>Quản trị viên</th><th>Hành động</th><th>Tài nguyên</th><th>Lý do</th></tr></thead><tbody>{items.map(item => <tr key={item.id}><td>{new Date(item.created_at).toLocaleString("vi-VN")}</td><td>{item.actor_email || "System"}</td><td><strong>{item.action}</strong></td><td>{item.resource_type} · {item.resource_id}</td><td>{item.reason || "—"}</td></tr>)}</tbody></table></section></>;
}
