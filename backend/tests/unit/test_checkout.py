import base64
import hashlib
import hmac
from datetime import datetime, timedelta

from app.providers.database import MockDatabaseProvider
from app.routes.checkout import generate_checkout_password
from app.services.auth import AuthService, UserCreate
from app.services.payments import (
    SEPAY_SIGNED_FIELDS, build_sepay_checkout, encrypt_credential, public_order,
)
from app.services.transactional_email import _build_invoice_html
from app.config import settings


async def test_generated_checkout_password_can_authenticate():
    database = MockDatabaseProvider()
    password = generate_checkout_password()
    auth = AuthService(database)

    await auth.create_user(UserCreate(
        email="checkout@example.com",
        password=password,
        name="Checkout Company",
    ))

    assert await auth.authenticate_user("checkout@example.com", password)
    assert await auth.authenticate_user("checkout@example.com", password + "x") is None


def test_sepay_checkout_signature_uses_official_field_order(monkeypatch):
    monkeypatch.setattr(settings, "SEPAY_MERCHANT_ID", "SP-LIVE-TEST")
    monkeypatch.setattr(settings, "SEPAY_MERCHANT_SECRET_KEY", "merchant-secret")
    monkeypatch.setattr(settings, "SEPAY_CHECKOUT_URL", "https://pay.sepay.vn/v1/checkout/init")
    monkeypatch.setattr(settings, "PAYMENT_RETURN_BASE_URL", "https://auralis.example")
    checkout = build_sepay_checkout({
        "order_id": "AUR12345678",
        "plan": "growth",
        "total": 2_640_000,
    })

    fields = checkout["fields"]
    signed = ",".join(f"{name}={fields[name]}" for name in SEPAY_SIGNED_FIELDS if name in fields)
    expected = base64.b64encode(
        hmac.new(b"merchant-secret", signed.encode(), hashlib.sha256).digest()
    ).decode()

    assert checkout["url"] == "https://pay.sepay.vn/v1/checkout/init"
    assert fields["payment_method"] == "BANK_TRANSFER"
    assert fields["signature"] == expected


def test_completed_order_accepts_naive_mongodb_credential_expiry(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENT_CREDENTIAL_ENCRYPTION_KEY", "test-payment-key")
    result = public_order({
        "order_id": "AUR12345678",
        "status": "completed",
        "plan": "growth",
        "email": "paid@example.com",
        "subtotal": 2_400_000,
        "discount": 0,
        "vat": 240_000,
        "total": 2_640_000,
        "password_encrypted": encrypt_credential("Au!7password"),
        "credentials_expires_at": datetime.utcnow() + timedelta(hours=1),
    }, include_credentials=True)

    assert result["password"] == "Au!7password"


def test_checkout_invoice_contains_order_and_credentials(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENT_RETURN_BASE_URL", "https://auralis.example")
    content = _build_invoice_html({
        "order_id": "AUR12345678", "plan": "growth", "email": "paid@example.com",
        "subtotal": 2_400_000, "discount": 0, "vat": 240_000, "total": 2_640_000,
    }, "Au!7temporary")

    assert "AUR12345678" in content
    assert "paid@example.com" in content
    assert "Au!7temporary" in content
    assert "2.640.000 VNĐ" in content

