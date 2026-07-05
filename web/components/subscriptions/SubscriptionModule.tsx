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
type ByokConfig = {
  configured: boolean; provider?: string; model?: string; base_url?: string;
  enabled?: boolean; has_api_key?: boolean;
};
type ModelUsage = {
  id: string; period: string; provider: string; model: string;
  calls: number; input_tokens: number; output_tokens: number; total_tokens: number;
};
type ChangeQuote = {
  current_plan: string; requested_plan: string; direction: "upgrade" | "downgrade";
  current_price: number; requested_price: number; remaining_ratio: number;
  subtotal: number; vat: number; total: number; current_period_end: string;
};
type CheckoutOrder = {
  order_id: string; access_token: string; status: string; effective_at?: string;
  checkout?: { url: string; fields: Record<string, string> };
};

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
    action: "Chọn gói Doanh nghiệp",
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
  const [selectedPlan, setSelectedPlan] = useState("");
  const [changeQuote, setChangeQuote] = useState<ChangeQuote | null>(null);
  const [byok, setByok] = useState<ByokConfig | null>(null);
  const [modelUsage, setModelUsage] = useState<ModelUsage[]>([]);
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
    const summary = (await summaryResponse.json()) as Summary;
    setData(summary);
    if (plansResponse.ok) setPlans((await plansResponse.json()) as Plan[]);
    if (requestsResponse.ok) setRequests((await requestsResponse.json()) as Request[]);
    if (summary.plan.key === "custom") {
      const [configResponse, usageResponse] = await Promise.all([
        authFetch(`${API_BASE}/byok`), authFetch(`${API_BASE}/byok/usage`),
      ]);
      if (configResponse.ok) setByok((await configResponse.json()) as ByokConfig);
      if (usageResponse.ok) setModelUsage((await usageResponse.json()) as ModelUsage[]);
    }
  }, []);
  useEffect(() => {
    const frame = requestAnimationFrame(() => void load().catch((reason: Error) => setError(reason.message)));
    return () => cancelAnimationFrame(frame);
  }, [load]);

  async function submitRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const requestedPlan = String(form.get("requested_plan") || "");
    if (requestedPlan !== "custom") {
      const response = await authFetch(`${API_BASE}/subscriptions/change`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requested_plan: requestedPlan }),
      });
      const body = (await response.json().catch(() => ({}))) as CheckoutOrder & { detail?: string };
      if (!response.ok) {
        setError(typeof body.detail === "string" ? body.detail : "Không thể thay đổi gói.");
        return;
      }
      if (body.status === "scheduled") {
        setMessage(`Đã lên lịch đổi gói vào ${body.effective_at ? new Date(body.effective_at).toLocaleDateString("vi-VN") : "cuối kỳ"}.`);
        setRequestOpen(false);
        await load();
        return;
      }
      if (body.access_token) {
        window.sessionStorage.setItem(`auralis-payment:${body.order_id}`, body.access_token);
      }
      if (body.checkout) {
        const gatewayForm = document.createElement("form");
        gatewayForm.method = "POST";
        gatewayForm.action = body.checkout.url;
        Object.entries(body.checkout.fields).forEach(([name, value]) => {
          const input = document.createElement("input");
          input.type = "hidden";
          input.name = name;
          input.value = value;
          gatewayForm.appendChild(input);
        });
        document.body.appendChild(gatewayForm);
        gatewayForm.submit();
      }
      return;
    }
    const response = await authFetch(`${API_BASE}/subscriptions/requests`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ requested_plan: requestedPlan, note: form.get("note") || null }),
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

  async function selectPlan(planKey: string) {
    setSelectedPlan(planKey);
    setChangeQuote(null);
    setError("");
    if (planKey === "custom") return;
    const response = await authFetch(`${API_BASE}/subscriptions/change/quote?requested_plan=${encodeURIComponent(planKey)}`);
    const body = await response.json().catch(() => ({})) as ChangeQuote & { detail?: string };
    if (!response.ok) {
      setError(typeof body.detail === "string" ? body.detail : "Không thể tính giá thay đổi gói.");
      return;
    }
    setChangeQuote(body);
  }

  async function saveByok(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const response = await authFetch(`${API_BASE}/byok`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: form.get("provider"), model: form.get("model"),
        api_key: form.get("api_key") || null, base_url: form.get("base_url") || null,
        enabled: form.get("enabled") === "on",
      }),
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as { detail?: string };
      setError(typeof body.detail === "string" ? body.detail : "Không thể lưu cấu hình BYOK.");
      return;
    }
    setByok((await response.json()) as ByokConfig);
    setMessage("Đã mã hóa và lưu cấu hình model riêng.");
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
        {user?.role === "user" && <button type="button" onClick={() => { setSelectedPlan(""); setChangeQuote(null); setRequestOpen(true); }}>Thay đổi gói</button>}
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
      {data.plan.key === "custom" && <section className="byok-section">
        <header><div><h2>Model API riêng</h2><p>Khóa API được mã hóa trước khi lưu và không thể xem lại.</p></div><span className={`subscription-status ${byok?.configured ? "active" : "pending"}`}>{byok?.configured ? "Đã cấu hình" : "Chưa cấu hình"}</span></header>
        <form className="byok-form" key={`${byok?.provider}-${byok?.model}-${byok?.base_url}`} onSubmit={saveByok}>
          <label>Nhà cung cấp<select name="provider" defaultValue={byok?.provider || "openai"}><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option><option value="gemini">Google Gemini</option><option value="ollama">Ollama</option></select></label>
          <label>Model<input name="model" defaultValue={byok?.model || ""} placeholder="Ví dụ: gpt-4.1-mini" required /></label>
          <label>API key<input name="api_key" type="password" autoComplete="new-password" placeholder={byok?.has_api_key ? "Để trống để giữ khóa hiện tại" : "Nhập API key"} /></label>
          <label>Base URL<input name="base_url" type="url" defaultValue={byok?.base_url || ""} placeholder="Để trống để dùng endpoint mặc định" /></label>
          <label className="byok-toggle"><input name="enabled" type="checkbox" defaultChecked={byok?.enabled ?? true} /> Kích hoạt model riêng</label>
          <button className="sites-primary-button">Lưu cấu hình bảo mật</button>
        </form>
        <div className="subscription-table-wrap"><table className="subscription-table"><thead><tr><th>Kỳ</th><th>Provider / model</th><th>Lượt gọi</th><th>Input tokens</th><th>Output tokens</th><th>Tổng tokens</th></tr></thead><tbody>
          {modelUsage.length ? modelUsage.map((usage) => <tr key={usage.id}><td>{usage.period}</td><td><strong>{usage.provider}</strong><small>{usage.model}</small></td><td>{usage.calls.toLocaleString("vi-VN")}</td><td>{usage.input_tokens.toLocaleString("vi-VN")}</td><td>{usage.output_tokens.toLocaleString("vi-VN")}</td><td>{usage.total_tokens.toLocaleString("vi-VN")}</td></tr>) : <tr><td colSpan={6}>Chưa có usage từ model riêng.</td></tr>}
        </tbody></table></div>
      </section>}
    </>}

    {requestOpen && data && <div className="sites-modal-layer">
      <button className="sites-modal-backdrop" onClick={() => setRequestOpen(false)} aria-label="Đóng" />
      <section className="sites-modal subscription-modal subscription-upgrade-modal" role="dialog" aria-modal="true">
        <div className="sites-modal-header"><div><h2>Thay đổi gói dịch vụ</h2><p>Gói hiện tại: {data.plan.name}</p></div><button onClick={() => setRequestOpen(false)}>×</button></div>
        <form onSubmit={submitRequest}>
          <div className="subscription-plan-options">{plans.map((plan) => {
            const view = planPresentation[plan.key] || {
              title: plan.name, price: "Liên hệ", action: `Chọn ${plan.name}`, features: [],
            };
            const current = plan.key === data.plan.key;
            const unavailable = plan.key === "starter" && data.plan.key !== "legacy";
            return <label className={`subscription-plan-card ${plan.key === "growth" ? "featured" : ""} ${current ? "current" : ""} ${unavailable ? "current" : ""}`} key={plan.key}>
              {view.badge && <span className="subscription-plan-badge">{view.badge}</span>}
              <input type="radio" name="requested_plan" value={plan.key} required disabled={current || unavailable} checked={selectedPlan === plan.key} onChange={() => void selectPlan(plan.key)} />
              <span className="subscription-plan-card-body">
                <strong className="subscription-plan-name">{view.title}</strong>
                <span className="subscription-plan-price">{view.price} {view.suffix && <small>{view.suffix}</small>}</span>
                <span className="subscription-plan-features">{view.features.map((feature) => <span key={feature}><b>✓</b>{feature}</span>)}</span>
                <span className="subscription-plan-action">{current ? "Gói hiện tại" : unavailable ? "Chỉ dành cho tài khoản mới" : view.action}</span>
              </span>
            </label>;
          })}</div>
          {changeQuote && <div className="subscription-change-quote">
            <span>Giá gói mới <b>{changeQuote.requested_price.toLocaleString("vi-VN")} VNĐ/tháng</b></span>
            {changeQuote.direction === "upgrade" ? <>
              <span>Phần chênh lệch còn lại trong kỳ <b>{changeQuote.subtotal.toLocaleString("vi-VN")} VNĐ</b></span>
              <span>VAT (10%) <b>{changeQuote.vat.toLocaleString("vi-VN")} VNĐ</b></span>
              <strong>Thanh toán ngay <b>{changeQuote.total.toLocaleString("vi-VN")} VNĐ</b></strong>
            </> : <>
              <span>Phí kỳ tiếp theo <b>{changeQuote.subtotal.toLocaleString("vi-VN")} VNĐ</b></span>
              <span>VAT (10%) <b>{changeQuote.vat.toLocaleString("vi-VN")} VNĐ</b></span>
              <strong>Thanh toán trước {changeQuote.total.toLocaleString("vi-VN")} VNĐ · Áp dụng từ {new Date(changeQuote.current_period_end).toLocaleDateString("vi-VN")}</strong>
            </>}
          </div>}
          {selectedPlan === "custom" && <label>Lời nhắn<textarea name="note" rows={4} placeholder="Nhu cầu model, hạn mức hoặc thông tin triển khai..." /></label>}
          <div className="sites-modal-actions"><button type="button" onClick={() => setRequestOpen(false)}>Hủy</button><button className="sites-primary-button" disabled={!selectedPlan || (selectedPlan !== "custom" && !changeQuote)}>{selectedPlan === "custom" ? "Gửi yêu cầu" : changeQuote?.direction === "downgrade" ? "Thanh toán kỳ tiếp theo" : "Thanh toán nâng cấp"}</button></div>
        </form>
      </section>
    </div>}
  </main>;
}
