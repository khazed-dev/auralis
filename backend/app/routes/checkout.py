"""Public checkout stub, promo management, and zero-value account provisioning."""
from datetime import datetime, timezone
import secrets
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.database import get_mongodb
from app.routes.auth import require_account_admin
from app.services.auth import AuthService, UserCreate, UserRole

router = APIRouter(prefix="/api/checkout", tags=["checkout"])

PLAN_PRICES = {"starter": 0, "growth": 2_400_000, "business": 9_800_000}


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
    payment_method: Literal["card", "bank_transfer"]
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
        now = datetime.now(timezone.utc)
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
    db = await get_mongodb()
    result = await calculate(db, plan, promo_code)
    result.pop("promo", None)
    return result


@router.post("/complete", status_code=201)
async def complete_checkout(body: CheckoutRequest):
    if not body.accepted_terms:
        raise HTTPException(status_code=422, detail="Bạn phải đồng ý điều khoản")
    db = await get_mongodb()
    pricing = await calculate(db, body.plan, body.promo_code)
    # Real card/QR gateway will replace this guard. Zero-value promo checkouts are safe to provision now.
    if pricing["total"] != 0:
        raise HTTPException(status_code=503, detail="Cổng thanh toán chưa được kích hoạt")
    if await db.get_user_by_email(str(body.email).lower()):
        raise HTTPException(status_code=409, detail="Email này đã có tài khoản")
    password = f"Au!7{secrets.token_urlsafe(8)}"
    auth = AuthService(db)
    user = await auth.create_user(UserCreate(
        email=body.email, password=password, name=body.company_name,
    ), role=UserRole.USER)
    if not user:
        raise HTTPException(status_code=409, detail="Không thể tạo tài khoản")
    owner_id = str(user["_id"])
    now = datetime.now(timezone.utc)
    order_id = f"AUR-{now.strftime('%y%m%d')}-{secrets.token_hex(3).upper()}"
    try:
        await db.db.subscriptions.update_one(
            {"owner_id": owner_id},
            {"$set": {
                "owner_id": owner_id, "plan": body.plan, "status": "active",
                "custom_limits": {}, "started_at": now, "updated_at": now,
            }, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        await db.db.checkout_orders.insert_one({
            "order_id": order_id, "owner_id": owner_id, "email": str(body.email).lower(),
            "company_name": body.company_name, "plan": body.plan,
            "payment_method": body.payment_method, "promo_code": body.promo_code,
            "subtotal": pricing["subtotal"], "discount": pricing["discount"],
            "vat": pricing["vat"], "total": pricing["total"], "status": "completed",
            "created_at": now,
        })
        if pricing["promo"]:
            await db.db.promo_codes.update_one(
                {"_id": pricing["promo"]["_id"]}, {"$inc": {"redemptions": 1}}
            )
    except Exception:
        await db.delete_user(owner_id)
        raise
    return {
        "order_id": order_id, "plan": body.plan, "email": str(body.email).lower(),
        "password": password, "payment_method": body.payment_method, "total": pricing["total"],
    }


@router.get("/promos")
async def list_promos(_admin: dict = Depends(require_account_admin)):
    db = await get_mongodb()
    rows = await db.db.promo_codes.find({}).sort("created_at", -1).to_list(length=500)
    return [public_promo(row) for row in rows]


@router.post("/promos", status_code=201)
async def create_promo(body: PromoCreate, admin: dict = Depends(require_account_admin)):
    db = await get_mongodb()
    now = datetime.now(timezone.utc)
    document = {**body.model_dump(), "redemptions": 0, "created_by": str(admin["_id"]), "created_at": now, "updated_at": now}
    try:
        result = await db.db.promo_codes.insert_one(document)
    except Exception as exc:
        raise HTTPException(status_code=409, detail="Mã promo đã tồn tại") from exc
    document["_id"] = result.inserted_id
    return public_promo(document)


@router.patch("/promos/{promo_id}")
async def toggle_promo(promo_id: str, active: bool, _admin: dict = Depends(require_account_admin)):
    from bson import ObjectId
    db = await get_mongodb()
    result = await db.db.promo_codes.update_one(
        {"_id": ObjectId(promo_id)}, {"$set": {"active": active, "updated_at": datetime.now(timezone.utc)}}
    )
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Không tìm thấy promo")
    return {"updated": True}
