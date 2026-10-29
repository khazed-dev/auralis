"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { BrandLogo } from "@/components/ui/BrandLogo";
import { Icon } from "@/components/ui/Icon";
import { CatalogPlan, fetchPlan } from "@/lib/plans";
import styles from "./checkout.module.css";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
type Quote = { subtotal: number; discount: number; vat: number; total: number };
type PricingState = { key: string; plan: CatalogPlan | null; quote: Quote | null; error: string };
type SePayCheckout = { url: string; fields: Record<string, string> };
type Order = {
  order_id: string; access_token?: string; status: "pending" | "processing" | "completed" | "expired";
  order_type?: "signup" | "subscription_change";
  plan: string; plan_name?: string; trial_ends_at?: string; expires_at?: string; email: string;
  password?: string; payment_method: string; total: number; checkout?: SePayCheckout;
};
const money = (value: number) => `${value.toLocaleString("vi-VN")} VNĐ`;

export function CheckoutPage() {
  const params = useSearchParams();
  const planKey = params.get("plan") || "growth";
  const [promo, setPromo] = useState("");
  const [appliedPromo, setAppliedPromo] = useState("");
  const [pricing, setPricing] = useState<PricingState | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [order, setOrder] = useState<Order | null>(null);
  const query = useMemo(() => `${API_BASE}/checkout/quote?plan=${encodeURIComponent(planKey)}${appliedPromo ? `&promo_code=${encodeURIComponent(appliedPromo)}` : ""}`, [planKey, appliedPromo]);
  const pricingKey = `${query}:${attempt}`;
  const plan = pricing?.plan?.key === planKey ? pricing.plan : null;
  const quote = pricing?.key === pricingKey ? pricing.quote : null;
  const pricingError = pricing?.key === pricingKey ? pricing.error : "";

  useEffect(() => {
    let controller: AbortController | undefined;
    function load() {
      controller?.abort();
      controller = new AbortController();
      const signal = controller.signal;
      Promise.all([
        fetchPlan(planKey, signal),
        fetch(query, { cache: "no-store", signal }).then(async response => {
          const body = await response.json();
          if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Không thể tính giá gói dịch vụ.");
          return body as Quote;
        }),
      ]).then(([nextPlan, nextQuote]) => {
        if (!signal.aborted) setPricing({ key: pricingKey, plan: nextPlan, quote: nextQuote, error: "" });
      }).catch((reason: Error) => {
        if (signal.aborted) return;
        setPricing(current => ({ key: pricingKey, plan: current?.plan?.key === planKey ? current.plan : null, quote: null, error: reason.message }));
      });
    }
    function refresh() { if (document.visibilityState === "visible") load(); }
    load();
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      controller?.abort();
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [query, planKey, pricingKey]);

  useEffect(() => {
    const callbackOrder = params.get("order");
    if (!callbackOrder || order) return;
    const accessToken = window.sessionStorage.getItem(`auralis-payment:${callbackOrder}`);
    Promise.resolve().then(() => {
      if (!accessToken) throw new Error("Không tìm thấy phiên thanh toán. Vui lòng kiểm tra email hoặc liên hệ hỗ trợ.");
      return fetch(`${API_BASE}/checkout/orders/${callbackOrder}?access_token=${encodeURIComponent(accessToken)}`, { cache: "no-store" });
    })
      .then(async response => {
        const contentType = response.headers.get("content-type") || "";
        const body = contentType.includes("application/json") ? await response.json() : null;
        if (!response.ok) throw new Error(body?.detail || "Không thể kiểm tra giao dịch.");
        if (!body) throw new Error("Phản hồi trạng thái thanh toán không hợp lệ.");
        setOrder({ ...body, access_token: accessToken });
      })
      .catch((reason: Error) => setError(reason.message));
  }, [params, order]);

  useEffect(() => {
    if (!order || !["pending", "processing"].includes(order.status) || !order.access_token) return;
    const timer = window.setInterval(async () => {
      const response = await fetch(`${API_BASE}/checkout/orders/${order.order_id}?access_token=${encodeURIComponent(order.access_token!)}`, { cache: "no-store" });
      if (!response.ok) return;
      const updated = await response.json() as Order;
      setOrder(current => current ? { ...updated, access_token: current.access_token } : current);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [order]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!quote || !plan || submitting) return;
    setError("");
    setSubmitting(true);
    try {
      const form = new FormData(event.currentTarget);
      const response = await fetch(`${API_BASE}/checkout/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          plan: planKey,
          email: form.get("email"),
          company_name: form.get("company_name"),
          promo_code: appliedPromo || null,
          payment_method: "bank_transfer",
          accepted_terms: form.get("accepted_terms") === "on",
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(typeof body.detail === "string" ? body.detail : "Không thể tạo đơn thanh toán.");
        return;
      }
      const created = body as Order;
      if (created.access_token) {
        window.sessionStorage.setItem(`auralis-payment:${created.order_id}`, created.access_token);
      }
      if (created.checkout) {
        const gatewayForm = document.createElement("form");
        gatewayForm.method = "POST";
        gatewayForm.action = created.checkout.url;
        Object.entries(created.checkout.fields).forEach(([name, value]) => {
          const input = document.createElement("input");
          input.type = "hidden";
          input.name = name;
          input.value = value;
          gatewayForm.appendChild(input);
        });
        document.body.appendChild(gatewayForm);
        gatewayForm.submit();
        return;
      }
      setOrder(created);
    } catch {
      setError("Không thể tạo đơn thanh toán. Vui lòng thử lại.");
    } finally {
      setSubmitting(false);
    }
  }

  if (order?.status === "completed") return <CheckoutSuccess result={order} planName={order.plan_name || (plan?.key === order.plan ? plan.name : order.plan)} />;
  if (order) return <PaymentWaiting order={order} />;
  if (!plan) return <div className={`checkout-page ${styles.page}`}><main className={`checkout-card ${styles.catalogState}`}>
    <h1>{pricingError || error ? "Chưa thể tải gói dịch vụ" : "Đang tải gói dịch vụ..."}</h1>
    {(pricingError || error) && <p role="alert">{pricingError || error}</p>}
    {(pricingError || error) && <button type="button" onClick={() => setAttempt(value => value + 1)}>Thử lại</button>}
    <Link href="/register">Chọn gói dịch vụ</Link>
  </main></div>;

  return <div className={`checkout-page ${styles.page}`}>
    <header className="checkout-header"><Link href="/" aria-label="Về trang chủ"><BrandLogo /></Link><span><Icon name="check" /> Thanh toán qua SePay</span></header>
    <div className={styles.heading}>
      <Link href="/register">Chọn gói dịch vụ</Link><span aria-hidden="true">/</span><strong>Thông tin & thanh toán</strong>
      <p>Một bước gần hơn đến trợ lý AI của doanh nghiệp.</p>
    </div>
    <form className="checkout-layout" onSubmit={submit}>
      <aside>
        <section className="checkout-card order-summary">
          <h1>Tóm tắt đơn hàng</h1>
          <div className="checkout-plan-line"><div><h2>Gói {plan.name}</h2><p>Thanh toán hàng tháng</p></div><strong>{money(quote?.subtotal ?? plan.monthly_price ?? 0)}</strong></div>
          <div className="checkout-features"><b>Bao gồm trong gói:</b>{plan.display_features.map(feature => <span key={feature}>✓ &nbsp; {feature}</span>)}</div>
          <div className="checkout-costs"><span>Tạm tính <b>{quote ? money(quote.subtotal) : "—"}</b></span>{quote && quote.discount > 0 && <span>Giảm giá <b>-{money(quote.discount)}</b></span>}<span>VAT ({plan.vat_rate}%) <b>{quote ? money(quote.vat) : "—"}</b></span></div>
          <div className="checkout-total"><strong>Tổng thanh toán</strong><b>{quote ? money(quote.total) : "Đang tính..."}</b></div>
          <label className="promo-label" htmlFor="checkout-promo">Mã giảm giá</label><div className="promo-entry"><input id="checkout-promo" value={promo} onChange={event => setPromo(event.target.value)} placeholder="Nhập mã" /><button type="button" onClick={() => setAppliedPromo(promo.trim().toUpperCase())}>Áp dụng</button></div>
        </section>
        <div className="checkout-trust"><Icon name="clock" /> Trạng thái thanh toán được cập nhật tự động</div>
      </aside>
      <main className="checkout-details">
        <section className="checkout-card"><h2>Thông tin khách hàng</h2><div className="checkout-customer">
          <label>Email<input name="email" type="email" placeholder="you@company.com" required /></label>
          <label className="wide">Tên công ty<input name="company_name" placeholder="Tên doanh nghiệp" required minLength={2} /></label>
        </div></section>
        <section className="checkout-card payment-card"><h2>Phương thức thanh toán</h2>
          <div className="payment-option selected"><span className={styles.paymentName}><Icon name="check" />VietQR / Chuyển khoản ngân hàng</span><span className={styles.qrBadge}>QR</span></div>
          <div className="payment-expanded bank-panel"><p>SePay sẽ tạo mã QR chứa sẵn số tiền và nội dung chuyển khoản sau khi bạn tiếp tục.</p></div>
          <button type="button" className="payment-option payment-option-disabled" disabled aria-disabled="true">
            Thẻ tín dụng / ghi nợ <span>Sắp ra mắt</span>
          </button>
        </section>
        {(error || pricingError) && <p className="checkout-error" role="alert">{error || pricingError} {pricingError && <button type="button" onClick={() => setAttempt(value => value + 1)}>Thử lại</button>}</p>}
        <label className="checkout-terms"><input name="accepted_terms" type="checkbox" required /> Tôi đồng ý với Điều khoản dịch vụ và Chính sách bảo mật.</label>
        <button className="checkout-submit" disabled={!quote || submitting}>{submitting ? "Đang xử lý..." : !quote ? "Đang tính giá..." : quote.total === 0 ? "Đăng ký ngay" : "Tiếp tục thanh toán"}{quote && <span>{money(quote.total)}</span>}</button>
      </main>
    </form>
    <footer className="checkout-footer">© 2026 Auralis AI. Mọi quyền được bảo lưu.<span>Chính sách bảo mật　 Điều khoản dịch vụ　 Liên hệ hỗ trợ</span></footer>
  </div>;
}

function PaymentWaiting({ order }: { order: Order }) {
  if (order.status === "expired") return <div className={`checkout-success-page ${styles.result}`}><main className="success-card"><div className={styles.resultIcon}><Icon name="clock" /></div><h1>Đơn hàng đã hết hạn</h1><p>Vui lòng quay lại và tạo đơn thanh toán mới.</p><div className="success-actions"><Link href={`/checkout?plan=${order.plan}`}>Tạo lại đơn</Link></div></main></div>;
  return <div className={`checkout-success-page ${styles.result}`}><main className="success-card payment-waiting-card">
    <div className={styles.resultIcon}><Icon name="clock" /></div>
    <h1>Đang xác nhận thanh toán</h1><p>Đơn hàng <strong>#{order.order_id}</strong> đã quay về từ SePay.</p>
    <p>Hệ thống đang chờ cổng thanh toán xác nhận giao dịch. Trang sẽ tự động cập nhật.</p>
  </main></div>;
}

function CheckoutSuccess({ result, planName }: { result: Order; planName: string }) {
  const isUpgrade = result.order_type === "subscription_change";
  const [copied, setCopied] = useState(false);
  async function copyPassword() {
    if (!result.password) return;
    await navigator.clipboard.writeText(result.password);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }
  const dashboardHref = isUpgrade
    ? "/dashboard/subscription"
    : `/login?email=${encodeURIComponent(result.email)}`;
  return <div className={`checkout-success-page ${styles.result}`}><main className="success-card">
    <div className="success-check">✓</div><h1>{isUpgrade ? "Nâng cấp thành công!" : "Đăng ký thành công!"}</h1><p>{isUpgrade ? <>Gói dịch vụ của bạn đã được nâng cấp lên <strong>{planName}</strong>.</> : <>Chào mừng bạn đến với gói <strong>{planName}</strong> của Auralis. {result.trial_ends_at ? `Tài khoản dùng thử đã sẵn sàng đến ${new Date(result.trial_ends_at).toLocaleDateString("vi-VN")}.` : "Tài khoản của bạn đã sẵn sàng để sử dụng."}</>}</p>
    <section><small>Chi tiết đơn hàng</small><span>Mã đơn hàng <b>#{result.order_id}</b></span><span>Phương thức <b>VietQR</b></span><span>Tài khoản <b>{result.email}</b></span>{result.password && <span>Mật khẩu <span className="success-password"><b>{result.password}</b><button type="button" onClick={copyPassword} aria-label="Sao chép mật khẩu" title="Sao chép mật khẩu">{copied ? "✓" : "⧉"}</button></span></span>}<span className="success-total">Tổng thanh toán <b>{money(result.total)}</b></span></section>
    <div className="success-actions"><Link href={dashboardHref}>Đi đến Dashboard</Link><button type="button" onClick={() => window.print()}>Xem hóa đơn</button></div><small>Bạn có thắc mắc? <a href="mailto:support@auralis.ai">Liên hệ bộ phận hỗ trợ</a></small>
  </main></div>;
}
