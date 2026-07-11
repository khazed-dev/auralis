"""Small SMTP client for checkout transactional emails."""
from __future__ import annotations

import asyncio
import html
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.config import settings


def _money(value: int) -> str:
    return f"{int(value or 0):,}".replace(",", ".") + " VNĐ"


def _build_invoice_html(order: dict, password: str) -> str:
    e = html.escape
    trial = order.get("trial_ends_at")
    trial_row = f"<tr><th>Hạn dùng thử</th><td>{e(str(trial))}</td></tr>" if trial else ""
    login_url = (settings.PAYMENT_RETURN_BASE_URL or settings.SITE_URL).rstrip("/") + "/login"
    return f"""<!doctype html><html><body style="background:#fff;color:#000;font:14px Arial,sans-serif">
<div style="max-width:640px;margin:24px auto;border:1px solid #000;padding:28px">
<h1 style="font-size:22px;margin:0 0 8px">AURALIS — HÓA ĐƠN</h1>
<p>Tài khoản của bạn đã được tạo thành công.</p>
<table style="width:100%;border-collapse:collapse;margin:22px 0">
<tr><th style="text-align:left;border:1px solid #000;padding:9px">Mã đơn hàng</th><td style="border:1px solid #000;padding:9px">#{e(str(order['order_id']))}</td></tr>
<tr><th style="text-align:left;border:1px solid #000;padding:9px">Gói dịch vụ</th><td style="border:1px solid #000;padding:9px">{e(str(order['plan']))}</td></tr>
<tr><th style="text-align:left;border:1px solid #000;padding:9px">Tạm tính</th><td style="border:1px solid #000;padding:9px">{_money(order.get('subtotal', 0))}</td></tr>
<tr><th style="text-align:left;border:1px solid #000;padding:9px">Giảm giá</th><td style="border:1px solid #000;padding:9px">{_money(order.get('discount', 0))}</td></tr>
<tr><th style="text-align:left;border:1px solid #000;padding:9px">VAT</th><td style="border:1px solid #000;padding:9px">{_money(order.get('vat', 0))}</td></tr>
<tr><th style="text-align:left;border:1px solid #000;padding:9px">Tổng thanh toán</th><td style="border:1px solid #000;padding:9px"><b>{_money(order.get('total', 0))}</b></td></tr>{trial_row}
</table>
<h2 style="font-size:18px">Thông tin đăng nhập</h2>
<p>Email: <b>{e(str(order['email']))}</b><br>Mật khẩu tạm thời: <b>{e(password)}</b></p>
<p><a href="{e(login_url)}" style="color:#000">Đăng nhập Auralis</a></p>
<p>Bạn bắt buộc đổi mật khẩu trong lần đăng nhập đầu tiên. Không chia sẻ mật khẩu tạm thời này.</p>
</div></body></html>"""


async def send_checkout_invoice_email(order: dict, password: str) -> bool:
    """Return False when SMTP is intentionally not configured."""
    if not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL:
        return False
    message = EmailMessage()
    message["Subject"] = f"Auralis — Hóa đơn #{order['order_id']} và thông tin đăng nhập"
    message["From"] = formataddr((settings.SMTP_FROM_NAME, settings.SMTP_FROM_EMAIL))
    message["To"] = order["email"]
    message.set_content("Tài khoản Auralis của bạn đã được tạo. Vui lòng xem email dạng HTML.")
    message.add_alternative(_build_invoice_html(order, password), subtype="html")

    def _send() -> None:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls()
            if settings.SMTP_USERNAME:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)

    await asyncio.to_thread(_send)
    return True
