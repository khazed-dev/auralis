"""Payment-order helpers shared by checkout and SePay webhook routes."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.config import settings
from app.services.auth import AuthService, UserCreate, UserRole
from app.services.transactional_email import send_checkout_invoice_email


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_order_id() -> str:
    # Matches SePay payment-code template: prefix AUR + 8 alphanumeric chars.
    return f"AUR{secrets.token_hex(4).upper()}"


def generate_access_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


SEPAY_SIGNED_FIELDS = (
    "order_amount", "merchant", "currency", "operation",
    "order_description", "order_invoice_number", "customer_id",
    "payment_method", "success_url", "error_url", "cancel_url",
)


def build_sepay_checkout(order: dict) -> dict:
    """Build the exact ordered, signed form required by SePay Payment Gateway."""
    base_url = (settings.PAYMENT_RETURN_BASE_URL or settings.SITE_URL).rstrip("/")
    return_url = f"{base_url}/checkout"
    fields = {
        "order_amount": str(int(order["total"])),
        "merchant": settings.SEPAY_MERCHANT_ID,
        "currency": "VND",
        "operation": "PURCHASE",
        "order_description": f"Thanh toan goi {order['plan']} Auralis - {order['order_id']}",
        "order_invoice_number": order["order_id"],
        "payment_method": "BANK_TRANSFER",
        "success_url": f"{return_url}?payment=success&order={order['order_id']}",
        "error_url": f"{return_url}?payment=error&order={order['order_id']}",
        "cancel_url": f"{return_url}?payment=cancel&order={order['order_id']}",
    }
    signed = ",".join(f"{name}={fields[name]}" for name in SEPAY_SIGNED_FIELDS if name in fields)
    fields["signature"] = base64.b64encode(
        hmac.new(
            settings.SEPAY_MERCHANT_SECRET_KEY.encode(),
            signed.encode(),
            hashlib.sha256,
        ).digest()
    ).decode()
    return {"url": settings.SEPAY_CHECKOUT_URL, "fields": fields}


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
    if order.get("order_type") == "subscription_change":
        return await apply_subscription_change(db, order)
    if order.get("order_type") == "renewal":
        return await apply_subscription_renewal(db, order)
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
    await db.update_user(owner_id, {"must_change_password": True, "updated_at": utcnow()})
    now = utcnow()
    snapshot = order.get("plan_snapshot") or {}
    trial_days = int(snapshot.get("trial_days") or 0)
    is_trial = trial_days > 0 and int(order.get("total") or 0) == 0
    trial_ends_at = now + timedelta(days=trial_days) if is_trial else None
    period_end = trial_ends_at if is_trial else now + timedelta(days=30)
    try:
        await db.db.subscriptions.update_one(
            {"owner_id": owner_id},
            {"$set": {
                "owner_id": owner_id,
                "plan": order["plan"],
                "status": "trialing" if is_trial else "active",
                "plan_version": int(order.get("plan_version") or snapshot.get("version") or 1),
                "plan_snapshot": snapshot,
                "custom_limits": {},
                "started_at": now,
                "expires_at": period_end,
                "trial_ends_at": trial_ends_at,
                "current_period_start": now,
                "current_period_end": period_end,
                "billing_cycle": "monthly",
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
            increments = {"redemptions": 1}
            if order.get("promo_reserved"):
                increments["reservations"] = -1
            await db.db.promo_codes.update_one({"_id": promo_id}, {"$inc": increments})
        completed_order = {**order, **updates}
        try:
            sent = await send_checkout_invoice_email(completed_order, password)
            await db.db.checkout_orders.update_one(
                {"_id": order["_id"]},
                {"$set": {
                    "invoice_email_status": "sent" if sent else "disabled",
                    "invoice_email_sent_at": utcnow() if sent else None,
                }},
            )
        except Exception as exc:
            from loguru import logger
            logger.exception(f"Failed to send checkout invoice {order['order_id']}: {exc}")
            await db.db.checkout_orders.update_one(
                {"_id": order["_id"]},
                {"$set": {"invoice_email_status": "failed", "invoice_email_error": str(exc)[:500]}},
            )
        return completed_order
    except Exception:
        await db.db.users.delete_one({"_id": persisted["_id"]})
        raise


async def apply_subscription_change(db, order: dict) -> dict:
    """Activate a paid upgrade after IPN while retaining the billing boundary."""
    if order.get("applied_at"):
        return order
    now = utcnow()
    owner_id = order["owner_id"]
    period_end = order["current_period_end"]
    if period_end.tzinfo is None:
        period_end = period_end.replace(tzinfo=timezone.utc)
    downgrade = order.get("change_direction") == "downgrade"
    if downgrade:
        updates = {
            "next_plan": order["plan"],
            "next_plan_version": order.get("plan_version"),
            "next_plan_snapshot": order.get("plan_snapshot"),
            "next_plan_paid": True,
            "cancel_at_period_end": True,
            "billing_cycle": "monthly",
            "updated_at": now,
        }
    else:
        updates = {
            "plan": order["plan"],
            "plan_version": order.get("plan_version"),
            "plan_snapshot": order.get("plan_snapshot"),
            "status": "active",
            "next_plan": None,
            "next_plan_paid": False,
            "cancel_at_period_end": False,
            "current_period_start": order["current_period_start"],
            "current_period_end": period_end,
            "expires_at": period_end,
            "billing_cycle": "monthly",
            "updated_at": now,
        }
    await db.db.subscriptions.update_one(
        {"owner_id": owner_id},
        {"$set": updates, "$setOnInsert": {"owner_id": owner_id, "created_at": now}},
        upsert=True,
    )
    await db.db.subscription_audit_logs.insert_one({
        "owner_id": owner_id,
        "action": "self_service_downgrade_prepaid" if downgrade else "self_service_upgrade_paid",
        "from_plan": order.get("from_plan"),
        "plan": order["plan"],
        "order_id": order["order_id"],
        "subtotal": order["subtotal"],
        "vat": order["vat"],
        "total": order["total"],
        "created_at": now,
    })
    order_updates = {
        "status": "completed",
        "completed_at": now,
        "applied_at": now,
        "updated_at": now,
    }
    await db.db.checkout_orders.update_one({"_id": order["_id"]}, {"$set": order_updates})
    return {**order, **order_updates}


async def apply_subscription_renewal(db, order: dict) -> dict:
    """Extend an existing subscription after a full-price renewal payment."""
    if order.get("applied_at"):
        return order
    now = utcnow()
    period_start = order.get("renewal_period_start") or now
    if period_start.tzinfo is None:
        period_start = period_start.replace(tzinfo=timezone.utc)
    period_end = period_start + timedelta(days=30)
    await db.db.subscriptions.update_one(
        {"owner_id": order["owner_id"]},
        {"$set": {
            "plan": order["plan"], "plan_version": order.get("plan_version"),
            "plan_snapshot": order.get("plan_snapshot"), "status": "active",
            "current_period_start": period_start, "current_period_end": period_end,
            "expires_at": period_end, "billing_cycle": "monthly", "updated_at": now,
        }},
        upsert=True,
    )
    await db.db.subscription_audit_logs.insert_one({
        "owner_id": order["owner_id"], "action": "self_service_renewal_paid",
        "plan": order["plan"], "order_id": order["order_id"],
        "total": order["total"], "created_at": now,
    })
    updates = {"status": "completed", "completed_at": now, "applied_at": now, "updated_at": now}
    await db.db.checkout_orders.update_one({"_id": order["_id"]}, {"$set": updates})
    return {**order, **updates}


def public_order(
    order: dict,
    *,
    include_credentials: bool = False,
    checkout: dict | None = None,
) -> dict:
    result = {
        "order_id": order["order_id"],
        "order_type": order.get("order_type", "signup"),
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
    if checkout:
        result["checkout"] = checkout
    if include_credentials and order["status"] == "completed" and order.get("password_encrypted"):
        expiry = order.get("credentials_expires_at")
        if expiry and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if not expiry or expiry > utcnow():
            result["password"] = decrypt_credential(order["password_encrypted"])
    return result
