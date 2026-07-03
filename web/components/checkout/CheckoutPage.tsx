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
type Success = { order_id: string; plan: PlanKey; email: string; password: string; payment_method: string; total: number };
const money = (value: number) => `${value.toLocaleString("vi-VN")} VNĐ`;

export function CheckoutPage() {
  const params = useSearchParams();
  const requested = params.get("plan") as PlanKey;
  const planKey: PlanKey = requested in plans ? requested : "growth";
  const plan = plans[planKey];
  const [method, setMethod] = useState<"card" | "bank_transfer">("card");
  const [promo, setPromo] = useState("");
  const [appliedPromo, setAppliedPromo] = useState("");
  const [quote, setQuote] = useState<Quote>({ subtotal: plan.price, discount: 0, vat: Math.round(plan.price * .1), total: Math.round(plan.price * 1.1) });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState<Success | null>(null);
  const query = useMemo(() => `${API_BASE}/checkout/quote?plan=${planKey}${appliedPromo ? `&promo_code=${encodeURIComponent(appliedPromo)}` : ""}`, [planKey, appliedPromo]);
  useEffect(() => { fetch(query).then(async r => { if (!r.ok) throw new Error((await r.json()).detail); setQuote(await r.json()); }).catch((e: Error) => setError(e.message)); }, [query]);

  async function applyPromo() { setError(""); setAppliedPromo(promo.trim().toUpperCase()); }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const form = new FormData(event.currentTarget);
    const response = await fetch(`${API_BASE}/checkout/complete`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        plan: planKey, email: form.get("email"), company_name: form.get("company_name"),
        promo_code: appliedPromo || null, payment_method: method,
        accepted_terms: form.get("accepted_terms") === "on",
      }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) { setError(typeof body.detail === "string" ? body.detail : "Không thể hoàn tất thanh toán."); return; }
    setSuccess(body as Success);
  }

  if (success) return <CheckoutSuccess result={success} planName={plans[success.plan].name} />;
  return <div className="checkout-page">
    <header className="checkout-header"><Link href="/"><Image src="/logo-auralis.png" alt="Auralis" width={144} height={48} /></Link><span>▣ &nbsp; THANH TOÁN BẢO MẬT</span></header>
    <form className="checkout-layout" onSubmit={submit}>
      <aside>
        <section className="checkout-card order-summary">
          <h1>Tóm tắt đơn hàng</h1>
          <div className="checkout-plan-line"><div><h2>Gói {plan.name}</h2><p>Thanh toán hàng tháng</p></div><strong>{money(plan.price)}</strong></div>
          <div className="checkout-features"><b>Bao gồm trong gói:</b>{plan.features.map(f => <span key={f}>✓ &nbsp; {f}</span>)}</div>
          <div className="checkout-costs"><span>Tạm tính <b>{money(quote.subtotal)}</b></span>{quote.discount > 0 && <span>Giảm giá <b>-{money(quote.discount)}</b></span>}<span>VAT (10%) <b>{money(quote.vat)}</b></span></div>
          <div className="checkout-total"><strong>Tổng thanh toán</strong><b>{money(quote.total)}</b></div>
          <label className="promo-label">Mã giảm giá</label><div className="promo-entry"><input value={promo} onChange={e => setPromo(e.target.value)} placeholder="Nhập mã" /><button type="button" onClick={() => void applyPromo()}>Áp dụng</button></div>
        </section>
        <div className="checkout-trust">♢ 256-bit SSL Secure　 ◉ Cam kết hoàn tiền</div>
      </aside>
      <main className="checkout-details">
        <section className="checkout-card"><h2>Thông tin khách hàng</h2><div className="checkout-customer">
          <label>Email<input name="email" type="email" placeholder="you@company.com" required /></label>
          <label className="wide">Tên công ty<input name="company_name" placeholder="Tên doanh nghiệp" required minLength={2} /></label>
        </div></section>
        <section className="checkout-card payment-card"><h2>Phương thức thanh toán</h2>
          <button type="button" className={`payment-option ${method === "card" ? "selected" : ""}`} onClick={() => setMethod("card")}>◯　Thẻ tín dụng / ghi nợ <span>▤</span></button>
          {method === "card" && <div className="payment-expanded"><label>Số thẻ<input placeholder="0000 0000 0000 0000" /></label><div><label>Ngày hết hạn<input placeholder="MM/YY" /></label><label>CVC<input placeholder="123" /></label></div><label>Tên trên thẻ<input placeholder="NGUYEN VAN A" /></label><small>Cổng thanh toán thẻ sẽ được kết nối sau.</small></div>}
          <button type="button" className={`payment-option ${method === "bank_transfer" ? "selected" : ""}`} onClick={() => setMethod("bank_transfer")}>◯　Chuyển khoản ngân hàng (Việt Nam) <span>♜</span></button>
          {method === "bank_transfer" && <div className="payment-expanded bank-panel"><div className="qr-placeholder">KHU VỰC MÃ QR</div><p>Quét mã để thanh toán nhanh qua ứng dụng Ngân hàng</p><hr /><b>HOẶC CHUYỂN KHOẢN THỦ CÔNG</b><span>Chủ tài khoản: <strong>Auralis AI</strong></span><span>Ngân hàng: <strong>Đang cập nhật</strong></span><span>Số tài khoản: <strong>Đang cập nhật</strong></span></div>}
        </section>
        {error && <p className="checkout-error">{error}</p>}
        <label className="checkout-terms"><input name="accepted_terms" type="checkbox" required /> Tôi đồng ý với Điều khoản dịch vụ và Chính sách bảo mật.</label>
        <button className="checkout-submit">▣　Đăng ký ngay — {money(quote.total)}</button>
      </main>
    </form>
    <footer className="checkout-footer">© 2026 Auralis AI. Mọi quyền được bảo lưu.<span>Chính sách bảo mật　 Điều khoản dịch vụ　 Liên hệ hỗ trợ</span></footer>
  </div>;
}

function CheckoutSuccess({ result, planName }: { result: Success; planName: string }) {
  return <div className="checkout-success-page"><div className="success-glow one" /><div className="success-glow two" /><main className="success-card">
    <div className="success-check">✓</div><h1>Thanh toán thành công!</h1><p>Chào mừng bạn đến với gói <strong>{planName}</strong> của Auralis. Tài khoản của bạn đã sẵn sàng để sử dụng.</p>
    <section><small>CHI TIẾT ĐƠN HÀNG</small><span>Mã đơn hàng <b>#{result.order_id}</b></span><span>Phương thức <b>{result.payment_method === "bank_transfer" ? "VietQR" : "Thẻ"}</b></span><span>Tài khoản <b>{result.email}</b></span><span>Mật khẩu <b>{result.password}</b></span><span className="success-total">Tổng thanh toán <b>{money(result.total)}</b></span></section>
    <div className="success-actions"><Link href="/login">Đi đến Dashboard　→</Link><button type="button" onClick={() => window.print()}>▧　Xem hóa đơn</button></div><small>◎　Giao dịch được bảo mật bởi Auralis AI Security</small>
  </main><p>Bạn có thắc mắc? <a href="mailto:support@auralis.ai">Liên hệ bộ phận hỗ trợ</a></p></div>;
}
