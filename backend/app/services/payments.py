"""Payment-order helpers shared by checkout and SePay webhook routes."""
from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.config import settings
from app.services.auth import AuthService, UserCreate, UserRole


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_order_id() -> str:
    # Matches SePay payment-code template: prefix AUR + 8 alphanumeric chars.
    return f"AUR{secrets.token_hex(4).upper()}"


def generate_access_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _credential_cipher() -> Fernet:
    secret = (settings.PAYMENT_CREDENTIAL_ENCRYPTION_KEY or "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="Mã hóa thông tin thanh toán chưa được cấu hình")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_credential(value: str) -> str:
    return _credential_cipher().encrypt(value.encode()).decode()


def decrypt_credential(value: str) -> str:
    try:
        return _credential_cipher().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise HTTPException(status_code=500, detail="Không thể giải mã thông tin tài khoản") from exc


async def provision_checkout_order(db, order: dict) -> dict:
    """Create the customer account and selected subscription exactly once."""
    if order.get("owner_id"):
        return order

    email = order["email"]
    if await db.get_user_by_email(email):
        raise HTTPException(status_code=409, detail="Email này đã có tài khoản")

    password = f"Au!7{secrets.token_hex(6)}"
    auth = AuthService(db)
    user = await auth.create_user(
        UserCreate(email=email, password=password, name=order["company_name"]),
        role=UserRole.USER,
    )
    if not user:
        raise HTTPException(status_code=409, detail="Không thể tạo tài khoản")

    persisted = await db.get_user_by_id(str(user.get("user_id") or user["_id"]))
    if not persisted:
        raise HTTPException(status_code=500, detail="Không thể tải tài khoản vừa tạo")

    owner_id = str(persisted["_id"])
    now = utcnow()
    starter = order["plan"] == "starter"
    trial_ends_at = now + timedelta(days=7) if starter else None
    try:
        await db.db.subscriptions.update_one(
            {"owner_id": owner_id},
            {"$set": {
                "owner_id": owner_id,
                "plan": order["plan"],
                "status": "trialing" if starter else "active",
                "custom_limits": {},
                "started_at": now,
                "expires_at": trial_ends_at,
                "trial_ends_at": trial_ends_at,
                "source": "checkout",
                "updated_at": now,
            }, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        updates = {
            "owner_id": owner_id,
            "status": "completed",
            "completed_at": now,
            "trial_ends_at": trial_ends_at,
            "password_encrypted": encrypt_credential(password),
            "credentials_expires_at": now + timedelta(hours=24),
            "updated_at": now,
        }
        await db.db.checkout_orders.update_one({"_id": order["_id"]}, {"$set": updates})
        promo_id = order.get("promo_id")
        if promo_id:
            await db.db.promo_codes.update_one({"_id": promo_id}, {"$inc": {"redemptions": 1}})
        return {**order, **updates}
    except Exception:
        await db.db.users.delete_one({"_id": persisted["_id"]})
        raise


def public_order(order: dict, *, include_credentials: bool = False) -> dict:
    result = {
        "order_id": order["order_id"],
        "status": order["status"],
        "plan": order["plan"],
        "requested_plan": order["plan"],
        "email": order["email"],
        "payment_method": "bank_transfer",
        "subtotal": order["subtotal"],
        "discount": order["discount"],
        "vat": order["vat"],
        "total": order["total"],
        "expires_at": order.get("expires_at"),
        "trial_ends_at": order.get("trial_ends_at"),
    }
    if order["status"] == "pending":
        result["payment"] = {
            "bank_code": settings.SEPAY_BANK_CODE,
            "account_number": settings.SEPAY_BANK_ACCOUNT,
            "account_name": settings.SEPAY_ACCOUNT_NAME,
            "amount": order["total"],
            "content": order["order_id"],
        }
    if include_credentials and order["status"] == "completed" and order.get("password_encrypted"):
        expiry = order.get("credentials_expires_at")
        if not expiry or expiry > utcnow():
            result["password"] = decrypt_credential(order["password_encrypted"])
    return result
