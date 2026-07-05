"use client";

import Image from "next/image";
import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
const plans = {
  starter: { name: "Khởi đầu", price: 0, features: ["1 website", "1.000 hội thoại AI", "100 trang lập chỉ mục", "1 thành viên"] },
  growth: { name: "Tăng trưởng", price: 2_400_000, features: ["5 website", "10.000 hội thoại AI mỗi tháng", "2.000 trang lập chỉ mục", "5 thành viên và handoff"] },
  business: { name: "Doanh nghiệp", price: 9_800_000, features: ["20 website", "100.000 hội thoại AI mỗi tháng", "20.000 trang lập chỉ mục", "20 thành viên và hỗ trợ ưu tiên"] },
} as const;
type PlanKey = keyof typeof plans;
type Quote = { subtotal: number; discount: number; vat: number; total: number };
type Payment = { bank_code: string; account_number: string; account_name: string; amount: number; content: string };
type Order = {
  order_id: string; access_token?: string; status: "pending" | "processing" | "completed" | "expired";
  plan: PlanKey; trial_ends_at?: string; expires_at?: string; email: string;
  password?: string; payment_method: string; total: number; payment?: Payment;
};
const money = (value: number) => `${value.toLocaleString("vi-VN")} VNĐ`;

export function CheckoutPage() {
  const params = useSearchParams();
  const requested = params.get("plan") as PlanKey;
  const planKey: PlanKey = requested in plans ? requested : "growth";
  const plan = plans[planKey];
  const [promo, setPromo] = useState("");
  const [appliedPromo, setAppliedPromo] = useState("");
  const [quote, setQuote] = useState<Quote>({ subtotal: plan.price, discount: 0, vat: Math.round(plan.price * .1), total: Math.round(plan.price * 1.1) });
  const [error, setError] = useState("");
  const [order, setOrder] = useState<Order | null>(null);
  const query = useMemo(() => `${API_BASE}/checkout/quote?plan=${planKey}${appliedPromo ? `&promo_code=${encodeURIComponent(appliedPromo)}` : ""}`, [planKey, appliedPromo]);

  useEffect(() => {
    fetch(query).then(async response => {
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail);
      setQuote(body);
      setError("");
    }).catch((reason: Error) => setError(reason.message));
  }, [query]);

  useEffect(() => {
    if (!order || !["pending", "processing"].includes(order.status) || !order.access_token) return;
    const timer = window.setInterval(async () => {
      const response = await fetch(`${API_BASE}/checkout/orders/${order.order_id}?access_token=${encodeURIComponent(order.access_token!)}`, { cache: "no-store" });
      if (!response.ok) return;
      const updated = await response.json() as Order;
      setOrder(current => current ? { ...updated, access_token: current.access_token } : current);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [order?.order_id, order?.status, order?.access_token]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
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
    setOrder(body as Order);
  }

  if (order?.status === "completed") return <CheckoutSuccess result={order} planName={plans[order.plan].name} />;
  if (order) return <PaymentWaiting order={order} />;

  return <div className="checkout-page">
    <header className="checkout-header"><Link href="/"><Image src="/logo-auralis.png" alt="Auralis" width={144} height={48} /></Link><span>▣ &nbsp; THANH TOÁN BẢO MẬT</span></header>
    <form className="checkout-layout" onSubmit={submit}>
      <aside>
        <section className="checkout-card order-summary">
          <h1>Tóm tắt đơn hàng</h1>
          <div className="checkout-plan-line"><div><h2>Gói {plan.name}</h2><p>Thanh toán hàng tháng</p></div><strong>{money(plan.price)}</strong></div>
          <div className="checkout-features"><b>Bao gồm trong gói:</b>{plan.features.map(feature => <span key={feature}>✓ &nbsp; {feature}</span>)}</div>
          <div className="checkout-costs"><span>Tạm tính <b>{money(quote.subtotal)}</b></span>{quote.discount > 0 && <span>Giảm giá <b>-{money(quote.discount)}</b></span>}<span>VAT (10%) <b>{money(quote.vat)}</b></span></div>
          <div className="checkout-total"><strong>Tổng thanh toán</strong><b>{money(quote.total)}</b></div>
          <label className="promo-label">Mã giảm giá</label><div className="promo-entry"><input value={promo} onChange={event => setPromo(event.target.value)} placeholder="Nhập mã" /><button type="button" onClick={() => setAppliedPromo(promo.trim().toUpperCase())}>Áp dụng</button></div>
        </section>
        <div className="checkout-trust">♦ 256-bit SSL Secure　 ◉ Thanh toán xác nhận tự động</div>
      </aside>
      <main className="checkout-details">
        <section className="checkout-card"><h2>Thông tin khách hàng</h2><div className="checkout-customer">
          <label>Email<input name="email" type="email" placeholder="you@company.com" required /></label>
          <label className="wide">Tên công ty<input name="company_name" placeholder="Tên doanh nghiệp" required minLength={2} /></label>
        </div></section>
        <section className="checkout-card payment-card"><h2>Phương thức thanh toán</h2>
          <div className="payment-option selected">◉　VietQR / Chuyển khoản ngân hàng <span>QR</span></div>
          <div className="payment-expanded bank-panel"><p>Mã QR chứa sẵn số tiền và nội dung chuyển khoản sẽ xuất hiện sau khi tạo đơn.</p><small>Thanh toán thẻ sẽ được bổ sung sau.</small></div>
        </section>
        {error && <p className="checkout-error">{error}</p>}
        <label className="checkout-terms"><input name="accepted_terms" type="checkbox" required /> Tôi đồng ý với Điều khoản dịch vụ và Chính sách bảo mật.</label>
        <button className="checkout-submit">▣　{quote.total === 0 ? "Đăng ký ngay" : "Tiếp tục thanh toán"} — {money(quote.total)}</button>
      </main>
    </form>
    <footer className="checkout-footer">© 2026 Auralis AI. Mọi quyền được bảo lưu.<span>Chính sách bảo mật　 Điều khoản dịch vụ　 Liên hệ hỗ trợ</span></footer>
  </div>;
}

function PaymentWaiting({ order }: { order: Order }) {
  if (order.status === "expired") return <div className="checkout-success-page"><main className="success-card"><h1>Đơn hàng đã hết hạn</h1><p>Vui lòng quay lại và tạo đơn thanh toán mới.</p><div className="success-actions"><Link href={`/checkout?plan=${order.plan}`}>Tạo lại đơn</Link></div></main></div>;
  const payment = order.payment;
  const qrUrl = payment ? `https://vietqr.app/img?acc=${encodeURIComponent(payment.account_number)}&bank=${encodeURIComponent(payment.bank_code)}&amount=${payment.amount}&des=${encodeURIComponent(payment.content)}` : "";
  return <div className="checkout-success-page"><main className="success-card payment-waiting-card">
    <h1>Quét mã để thanh toán</h1><p>Đơn hàng <strong>#{order.order_id}</strong> đang chờ chuyển khoản.</p>
    {payment && <section>
      {/* External VietQR image is intentionally rendered as a normal img. */}
      <img src={qrUrl} alt={`VietQR cho đơn ${order.order_id}`} width={280} height={280} />
      <span>Ngân hàng <b>{payment.bank_code}</b></span>
      <span>Số tài khoản <b>{payment.account_number}</b></span>
      <span>Chủ tài khoản <b>{payment.account_name}</b></span>
      <span>Số tiền <b>{money(payment.amount)}</b></span>
      <span>Nội dung <b>{payment.content}</b></span>
    </section>}
    <p>Hệ thống đang tự động kiểm tra giao dịch. Không đóng trang này.</p>
  </main></div>;
}

function CheckoutSuccess({ result, planName }: { result: Order; planName: string }) {
  return <div className="checkout-success-page"><div className="success-glow one" /><div className="success-glow two" /><main className="success-card">
    <div className="success-check">✓</div><h1>Đăng ký thành công!</h1><p>Chào mừng bạn đến với gói <strong>{planName}</strong> của Auralis. {result.trial_ends_at ? `Tài khoản dùng thử đã sẵn sàng đến ${new Date(result.trial_ends_at).toLocaleDateString("vi-VN")}.` : "Tài khoản của bạn đã sẵn sàng để sử dụng."}</p>
    <section><small>CHI TIẾT ĐƠN HÀNG</small><span>Mã đơn hàng <b>#{result.order_id}</b></span><span>Phương thức <b>VietQR</b></span><span>Tài khoản <b>{result.email}</b></span>{result.password && <span>Mật khẩu <b>{result.password}</b></span>}<span className="success-total">Tổng thanh toán <b>{money(result.total)}</b></span></section>
    <div className="success-actions"><Link href="/login">Đi đến Dashboard　→</Link><button type="button" onClick={() => window.print()}>▧　Xem hóa đơn</button></div><small>Bạn có thắc mắc? <a href="mailto:support@auralis.ai">Liên hệ bộ phận hỗ trợ</a></small>
  </main></div>;
}
