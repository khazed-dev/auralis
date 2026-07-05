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
from app.services.plans import plan_snapshot, require_plan

router = APIRouter(prefix="/api/checkout", tags=["checkout"])
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
    percent_off: Optional[int] = Field(default=None, ge=1, le=100)
    discount_type: Literal["percent", "fixed"] = "percent"
    discount_value: Optional[int] = Field(default=None, ge=1)
    active: bool = True
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    max_redemptions: Optional[int] = Field(default=None, ge=1)
    max_per_customer: Optional[int] = Field(default=None, ge=1)
    first_purchase_only: bool = False
    minimum_amount: int = Field(default=0, ge=0)
    applicable_plan_keys: list[str] = Field(default_factory=list)
    applicable_order_types: list[Literal["signup", "upgrade", "renewal"]] = Field(default_factory=list)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str):
        return value.strip().upper()


class CheckoutRequest(BaseModel):
    plan: str = Field(min_length=2, max_length=40)
    email: EmailStr
    company_name: str = Field(min_length=2, max_length=150)
    promo_code: Optional[str] = None
    payment_method: Literal["bank_transfer"]
    accepted_terms: bool


def public_promo(document: dict) -> dict:
    return {
        "id": str(document["_id"]), "code": document["code"],
        "percent_off": document.get("percent_off"),
        "discount_type": document.get("discount_type", "percent"),
        "discount_value": document.get("discount_value", document.get("percent_off")),
        "active": document.get("active", True), "starts_at": document.get("starts_at"),
        "expires_at": document.get("expires_at"), "max_redemptions": document.get("max_redemptions"),
        "max_per_customer": document.get("max_per_customer"),
        "first_purchase_only": document.get("first_purchase_only", False),
        "minimum_amount": int(document.get("minimum_amount") or 0),
        "applicable_plan_keys": document.get("applicable_plan_keys") or [],
        "applicable_order_types": document.get("applicable_order_types") or [],
        "redemptions": int(document.get("redemptions") or 0), "created_at": document.get("created_at"),
    }


async def calculate(db, plan: str, promo_code: Optional[str]) -> dict:
    plan_document = await require_plan(db, plan, for_signup=True)
    subtotal = int(plan_document.get("monthly_price") or 0)
    promo = None
    discount = 0
    if promo_code:
        promo = await db.db.promo_codes.find_one({"code": promo_code.strip().upper(), "active": True})
        if not promo:
            raise HTTPException(status_code=404, detail="Mã giảm giá không hợp lệ")
        expires = promo.get("expires_at")
        now = utcnow()
        starts = promo.get("starts_at")
        if starts and (starts.replace(tzinfo=timezone.utc) if starts.tzinfo is None else starts) > now:
            raise HTTPException(status_code=400, detail="Mã giảm giá chưa có hiệu lực")
        if expires and (expires.replace(tzinfo=timezone.utc) if expires.tzinfo is None else expires) <= now:
            raise HTTPException(status_code=410, detail="Mã giảm giá đã hết hạn")
        if promo.get("max_redemptions") and int(promo.get("redemptions") or 0) >= promo["max_redemptions"]:
            raise HTTPException(status_code=409, detail="Mã giảm giá đã hết lượt sử dụng")
        if promo.get("applicable_plan_keys") and plan not in promo["applicable_plan_keys"]:
            raise HTTPException(status_code=400, detail="Mã giảm giá không áp dụng cho gói này")
        if promo.get("applicable_order_types") and "signup" not in promo["applicable_order_types"]:
            raise HTTPException(status_code=400, detail="Mã giảm giá không áp dụng cho đăng ký mới")
        if subtotal < int(promo.get("minimum_amount") or 0):
            raise HTTPException(status_code=400, detail="Đơn hàng chưa đạt giá trị tối thiểu")
        discount_type = promo.get("discount_type", "percent")
        discount_value = int(promo.get("discount_value") or promo.get("percent_off") or 0)
        discount = discount_value if discount_type == "fixed" else round(subtotal * discount_value / 100)
    discounted = max(0, subtotal - discount)
    vat = round(discounted * float(plan_document.get("vat_rate", 10)) / 100)
    return {
        "subtotal": subtotal, "discount": discount, "vat": vat,
        "total": discounted + vat, "promo": promo, "plan": plan_document,
    }


@router.get("/quote")
async def quote(plan: str, promo_code: Optional[str] = None):
    result = await calculate(await get_mongodb(), plan, promo_code)
    result.pop("promo", None)
    result.pop("plan", None)
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
    if pricing["promo"]:
        promo = pricing["promo"]
        customer_uses = await db.db.checkout_orders.count_documents({
            "email": email, "promo_id": promo["_id"], "status": "completed",
        })
        if promo.get("max_per_customer") and customer_uses >= int(promo["max_per_customer"]):
            raise HTTPException(status_code=409, detail="Bạn đã sử dụng hết lượt của mã giảm giá")
        if promo.get("first_purchase_only") and await db.db.checkout_orders.count_documents({
            "email": email, "status": "completed",
        }):
            raise HTTPException(status_code=409, detail="Mã chỉ áp dụng cho lần mua đầu tiên")
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
        "plan_version": int(pricing["plan"].get("version") or 1),
        "plan_snapshot": plan_snapshot(pricing["plan"]),
        "price_snapshot": {
            "subtotal": pricing["subtotal"], "discount": pricing["discount"],
            "vat": pricing["vat"], "total": pricing["total"],
            "vat_rate": pricing["plan"].get("vat_rate", 10),
        },
        "payment_method": "bank_transfer",
        "promo_code": body.promo_code.strip().upper() if body.promo_code else None,
        "promo_id": pricing["promo"]["_id"] if pricing["promo"] else None,
        "promo_reserved": bool(pricing["promo"]),
        "subtotal": pricing["subtotal"], "discount": pricing["discount"],
        "vat": pricing["vat"], "total": pricing["total"],
        "status": "pending",
        "expires_at": now + timedelta(minutes=settings.PAYMENT_ORDER_EXPIRE_MINUTES),
        "created_at": now, "updated_at": now,
    }
    if pricing["promo"]:
        promo_query: dict = {"_id": pricing["promo"]["_id"], "active": True}
        if pricing["promo"].get("max_redemptions"):
            promo_query["$expr"] = {"$lt": [
                {"$add": [{"$ifNull": ["$redemptions", 0]}, {"$ifNull": ["$reservations", 0]}]},
                int(pricing["promo"]["max_redemptions"]),
            ]}
        reserved = await db.db.promo_codes.update_one(promo_query, {"$inc": {"reservations": 1}})
        if not reserved.modified_count:
            raise HTTPException(status_code=409, detail="Mã giảm giá đã hết lượt sử dụng")
    try:
        inserted = await db.db.checkout_orders.insert_one(order)
        order["_id"] = inserted.inserted_id
        if order["total"] == 0:
            order = await provision_checkout_order(db, order)
    except Exception:
        if pricing["promo"]:
            await db.db.promo_codes.update_one(
                {"_id": pricing["promo"]["_id"], "reservations": {"$gt": 0}},
                {"$inc": {"reservations": -1}},
            )
        raise
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
        await db.db.checkout_orders.update_one(
            {"_id": order["_id"]},
            {"$set": {
                "sepay_transaction_id": transaction_id,
                "sepay_order_id": sepay_order.get("order_id"),
                "updated_at": utcnow(),
            }},
        )
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
            "sepay_order_id": sepay_order.get("order_id"),
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
    payload = body.model_dump()
    if payload["discount_type"] == "percent":
        payload["discount_value"] = payload["discount_value"] or payload["percent_off"]
        if not payload["discount_value"] or payload["discount_value"] > 100:
            raise HTTPException(status_code=422, detail="Phần trăm giảm phải từ 1 đến 100")
        payload["percent_off"] = payload["discount_value"]
    elif not payload["discount_value"]:
        raise HTTPException(status_code=422, detail="Số tiền giảm là bắt buộc")
    document = {
        **payload, "redemptions": 0, "reservations": 0, "created_by": str(admin["_id"]),
        "created_at": now, "updated_at": now,
    }
    try:
        result = await db.db.promo_codes.insert_one(document)
    except Exception as exc:
        raise HTTPException(status_code=409, detail="Mã promo đã tồn tại") from exc
    document["_id"] = result.inserted_id
    await db.db.platform_audit_logs.insert_one({
        "actor_id": str(admin["_id"]), "action": "promo_created",
        "resource_type": "promo", "resource_id": str(result.inserted_id),
        "after": public_promo(document), "created_at": now,
    })
    return public_promo(document)


@router.patch("/promos/{promo_id}")
async def toggle_promo(promo_id: str, active: bool, _admin: dict = Depends(require_account_admin)):
    db = await get_mongodb()
    result = await db.db.promo_codes.update_one(
        {"_id": ObjectId(promo_id)}, {"$set": {"active": active, "updated_at": utcnow()}}
    )
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Không tìm thấy promo")
    await db.db.platform_audit_logs.insert_one({
        "actor_id": str(_admin["_id"]), "action": "promo_status_changed",
        "resource_type": "promo", "resource_id": promo_id,
        "after": {"active": active}, "created_at": utcnow(),
    })
    return {"updated": True}
