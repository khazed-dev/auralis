"""Public checkout, SePay confirmation, and promo administration."""
from datetime import datetime, timedelta, timezone
import hmac
import time
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.config import settings
from app.database import get_mongodb
from app.routes.auth import require_account_admin
from app.services.payments import (
    build_sepay_checkout, generate_access_token, generate_order_id, hash_token,
    provision_checkout_order, public_order, utcnow,
)

router = APIRouter(prefix="/api/checkout", tags=["checkout"])
PLAN_PRICES = {"starter": 0, "growth": 2_400_000, "business": 9_800_000}


def _is_expired(value: Optional[datetime]) -> bool:
    if not value:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= utcnow()


def generate_checkout_password() -> str:
    """Backward-compatible helper used by authentication tests."""
    return f"Au!7{__import__('secrets').token_hex(6)}"


class PromoCreate(BaseModel):
    code: str = Field(min_length=3, max_length=40)
    percent_off: int = Field(ge=1, le=100)
    active: bool = True
    expires_at: Optional[datetime] = None
    max_redemptions: Optional[int] = Field(default=None, ge=1)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str):
        return value.strip().upper()


class CheckoutRequest(BaseModel):
    plan: Literal["starter", "growth", "business"]
    email: EmailStr
    company_name: str = Field(min_length=2, max_length=150)
    promo_code: Optional[str] = None
    payment_method: Literal["bank_transfer"]
    accepted_terms: bool


def public_promo(document: dict) -> dict:
    return {
        "id": str(document["_id"]), "code": document["code"],
        "percent_off": document["percent_off"], "active": document.get("active", True),
        "expires_at": document.get("expires_at"), "max_redemptions": document.get("max_redemptions"),
        "redemptions": int(document.get("redemptions") or 0), "created_at": document.get("created_at"),
    }


async def calculate(db, plan: str, promo_code: Optional[str]) -> dict:
    subtotal = PLAN_PRICES[plan]
    promo = None
    discount = 0
    if promo_code:
        promo = await db.db.promo_codes.find_one({"code": promo_code.strip().upper(), "active": True})
        if not promo:
            raise HTTPException(status_code=404, detail="Mã giảm giá không hợp lệ")
        expires = promo.get("expires_at")
        now = utcnow()
        if expires and (expires.replace(tzinfo=timezone.utc) if expires.tzinfo is None else expires) <= now:
            raise HTTPException(status_code=410, detail="Mã giảm giá đã hết hạn")
        if promo.get("max_redemptions") and int(promo.get("redemptions") or 0) >= promo["max_redemptions"]:
            raise HTTPException(status_code=409, detail="Mã giảm giá đã hết lượt sử dụng")
        discount = round(subtotal * promo["percent_off"] / 100)
    discounted = max(0, subtotal - discount)
    vat = round(discounted * .1)
    return {"subtotal": subtotal, "discount": discount, "vat": vat, "total": discounted + vat, "promo": promo}


@router.get("/quote")
async def quote(plan: Literal["starter", "growth", "business"], promo_code: Optional[str] = None):
    result = await calculate(await get_mongodb(), plan, promo_code)
    result.pop("promo", None)
    return result


@router.post("/complete", status_code=201)
async def complete_checkout(body: CheckoutRequest):
    if not body.accepted_terms:
        raise HTTPException(status_code=422, detail="Bạn phải đồng ý điều khoản")
    db = await get_mongodb()
    pricing = await calculate(db, body.plan, body.promo_code)
    email = str(body.email).lower()
    if await db.get_user_by_email(email):
        raise HTTPException(status_code=409, detail="Email này đã có tài khoản")
    if not settings.PAYMENT_CREDENTIAL_ENCRYPTION_KEY:
        raise HTTPException(status_code=503, detail="Mã hóa thông tin tài khoản chưa được cấu hình")
    if pricing["total"] > 0 and not all((
        settings.SEPAY_ENABLED, settings.SEPAY_MERCHANT_ID,
        settings.SEPAY_MERCHANT_SECRET_KEY, settings.SEPAY_IPN_SECRET_KEY,
        settings.SEPAY_CHECKOUT_URL,
    )):
        raise HTTPException(status_code=503, detail="Thanh toán SePay chưa được cấu hình đầy đủ")

    now = utcnow()
    access_token = generate_access_token()
    order = {
        "order_id": generate_order_id(),
        "access_token_hash": hash_token(access_token),
        "email": email,
        "company_name": body.company_name.strip(),
        "plan": body.plan,
        "payment_method": "bank_transfer",
        "promo_code": body.promo_code.strip().upper() if body.promo_code else None,
        "promo_id": pricing["promo"]["_id"] if pricing["promo"] else None,
        "subtotal": pricing["subtotal"], "discount": pricing["discount"],
        "vat": pricing["vat"], "total": pricing["total"],
        "status": "pending",
        "expires_at": now + timedelta(minutes=settings.PAYMENT_ORDER_EXPIRE_MINUTES),
        "created_at": now, "updated_at": now,
    }
    inserted = await db.db.checkout_orders.insert_one(order)
    order["_id"] = inserted.inserted_id
    if order["total"] == 0:
        order = await provision_checkout_order(db, order)
    checkout = build_sepay_checkout(order) if order["total"] > 0 else None
    response = public_order(order, include_credentials=True, checkout=checkout)
    response["access_token"] = access_token
    return response


@router.get("/orders/{order_id}")
async def checkout_order_status(order_id: str, access_token: str = Query(min_length=20)):
    db = await get_mongodb()
    order = await db.db.checkout_orders.find_one({
        "order_id": order_id.upper(), "access_token_hash": hash_token(access_token),
    })
    if not order:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
    if order["status"] == "pending" and _is_expired(order.get("expires_at")):
        await db.db.checkout_orders.update_one(
            {"_id": order["_id"], "status": "pending"},
            {"$set": {"status": "expired", "updated_at": utcnow()}},
        )
        order["status"] = "expired"
    return public_order(order, include_credentials=True)


@router.post("/sepay/ipn")
async def sepay_ipn(request: Request):
    """Process authenticated Payment Gateway IPN notifications."""
    if not settings.SEPAY_ENABLED or not settings.SEPAY_IPN_SECRET_KEY:
        raise HTTPException(status_code=503, detail="SePay is disabled")
    supplied_secret = request.headers.get("X-Secret-Key", "")
    if not hmac.compare_digest(supplied_secret, settings.SEPAY_IPN_SECRET_KEY):
        raise HTTPException(status_code=401, detail="Invalid IPN secret")
    payload = await request.json()
    try:
        timestamp_int = int(payload.get("timestamp") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid timestamp") from exc
    if abs(int(time.time()) - timestamp_int) > 300:
        raise HTTPException(status_code=401, detail="Request expired")
    if payload.get("notification_type") != "ORDER_PAID":
        return {"success": True}
    sepay_order = payload.get("order") or {}
    transaction = payload.get("transaction") or {}
    transaction_id = str(transaction.get("transaction_id") or transaction.get("id") or "")
    order_id = str(sepay_order.get("order_invoice_number") or "").upper()
    if not transaction_id or not order_id:
        raise HTTPException(status_code=400, detail="Missing order or transaction identifier")

    db = await get_mongodb()
    order = await db.db.checkout_orders.find_one({"order_id": order_id})
    if not order:
        await db.db.payment_transactions.update_one(
            {"transaction_id": transaction_id},
            {"$setOnInsert": {
                "transaction_id": transaction_id, "order_id": order_id,
                "status": "unknown_order", "payload": payload, "created_at": utcnow(),
            }}, upsert=True,
        )
        return {"success": True}
    if order["status"] == "pending" and _is_expired(order.get("expires_at")):
        await db.db.checkout_orders.update_one(
            {"_id": order["_id"], "status": "pending"},
            {"$set": {"status": "expired", "updated_at": utcnow()}},
        )
        await db.db.payment_transactions.update_one(
            {"transaction_id": transaction_id},
            {"$setOnInsert": {
                "transaction_id": transaction_id, "order_id": order_id,
                "status": "late_payment", "payload": payload, "created_at": utcnow(),
            }}, upsert=True,
        )
        return {"success": True}
    try:
        paid_amount = int(float(sepay_order.get("order_amount") or 0))
        transaction_amount = int(float(transaction.get("transaction_amount") or 0))
    except (TypeError, ValueError):
        paid_amount = transaction_amount = -1
    matches = all((
        sepay_order.get("order_status") == "CAPTURED",
        sepay_order.get("order_currency") == "VND",
        transaction.get("transaction_status") == "APPROVED",
        transaction.get("transaction_currency") == "VND",
        paid_amount == int(order["total"]),
        transaction_amount == int(order["total"]),
    ))
    if not matches:
        await db.db.payment_transactions.update_one(
            {"transaction_id": transaction_id},
            {"$setOnInsert": {
                "transaction_id": transaction_id, "order_id": order_id,
                "status": "unmatched", "payload": payload, "created_at": utcnow(),
            }}, upsert=True,
        )
        return {"success": True}
    if order["status"] == "completed":
        return {"success": True}
    if order["status"] != "pending":
        return {"success": True}
    try:
        await db.db.payment_transactions.insert_one({
            "transaction_id": transaction_id, "order_id": order_id,
            "status": "processing", "payload": payload, "created_at": utcnow(),
        })
    except DuplicateKeyError:
        return {"success": True}

    claimed = await db.db.checkout_orders.find_one_and_update(
        {"_id": order["_id"], "status": "pending"},
        {"$set": {
            "status": "processing", "sepay_transaction_id": transaction_id,
            "paid_at": utcnow(), "updated_at": utcnow(),
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        return {"success": True}
    try:
        await provision_checkout_order(db, claimed)
        await db.db.payment_transactions.update_one(
            {"transaction_id": transaction_id},
            {"$set": {"status": "completed", "processed_at": utcnow()}},
        )
    except Exception:
        await db.db.checkout_orders.update_one(
            {"_id": order["_id"], "status": "processing"},
            {"$set": {"status": "pending", "updated_at": utcnow()},
             "$unset": {"sepay_transaction_id": "", "paid_at": ""}},
        )
        await db.db.payment_transactions.delete_one({"transaction_id": transaction_id})
        raise
    return {"success": True}


@router.get("/promos")
async def list_promos(_admin: dict = Depends(require_account_admin)):
    rows = await (await get_mongodb()).db.promo_codes.find({}).sort("created_at", -1).to_list(length=500)
    return [public_promo(row) for row in rows]


@router.post("/promos", status_code=201)
async def create_promo(body: PromoCreate, admin: dict = Depends(require_account_admin)):
    db = await get_mongodb()
    now = utcnow()
    document = {
        **body.model_dump(), "redemptions": 0, "created_by": str(admin["_id"]),
        "created_at": now, "updated_at": now,
    }
    try:
        result = await db.db.promo_codes.insert_one(document)
    except Exception as exc:
        raise HTTPException(status_code=409, detail="Mã promo đã tồn tại") from exc
    document["_id"] = result.inserted_id
    return public_promo(document)


@router.patch("/promos/{promo_id}")
async def toggle_promo(promo_id: str, active: bool, _admin: dict = Depends(require_account_admin)):
    db = await get_mongodb()
    result = await db.db.promo_codes.update_one(
        {"_id": ObjectId(promo_id)}, {"$set": {"active": active, "updated_at": utcnow()}}
    )
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Không tìm thấy promo")
    return {"updated": True}
