"""Customer subscription and platform-admin management APIs."""
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from pymongo import ReturnDocument

from app.database import get_mongodb
from app.config import settings
from app.routes.auth import require_account_admin, require_auth
from app.services.payments import (
    build_sepay_checkout,
    generate_access_token,
    generate_order_id,
    hash_token,
    public_order,
    utcnow,
)
from app.services.plans import get_plan, plan_snapshot, require_plan, serialize_plan
from app.services.subscriptions import (
    PLAN_CATALOG,
    get_subscription,
    resolve_owner_id,
    subscription_change_quote,
    subscription_summary,
)

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


class SubscriptionUpdate(BaseModel):
    plan: Literal["starter", "growth", "business", "custom", "legacy"]
    status: Literal["active", "trialing", "past_due", "cancelled", "suspended"] = "active"
    expires_at: Optional[datetime] = None
    custom_limits: dict[str, Optional[int]] = Field(default_factory=dict)
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("custom_limits")
    @classmethod
    def validate_custom_limits(cls, value: dict[str, Optional[int]]):
        allowed = {"sites", "members", "messages", "crawl_pages"}
        if set(value) - allowed:
            raise ValueError("Unsupported custom limit")
        if any(limit is not None and limit < 0 for limit in value.values()):
            raise ValueError("Custom limits cannot be negative")
        return value


class UpgradeRequestCreate(BaseModel):
    requested_plan: Literal["starter", "growth", "business", "custom"]
    note: Optional[str] = Field(default=None, max_length=1000)


class UpgradeDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    note: Optional[str] = Field(default=None, max_length=1000)


class SubscriptionChange(BaseModel):
    requested_plan: str = Field(min_length=2, max_length=40)


def serialize_document(document: dict) -> dict:
    result = dict(document)
    if "_id" in result:
        result["id"] = str(result.pop("_id"))
    return result


@router.get("/plans")
async def list_plans():
    db = await get_mongodb()
    rows = await db.db.plans.find({"is_active": True}).sort("display_order", 1).to_list(100)
    return [serialize_plan(row) for row in rows]


@router.get("/me")
async def my_subscription(user: dict = Depends(require_auth)):
    db = await get_mongodb()
    return await subscription_summary(db, await resolve_owner_id(db, user))


@router.get("/available-changes")
async def available_plan_changes(user: dict = Depends(require_auth)):
    if user.get("role") != "user":
        return []
    db = await get_mongodb()
    subscription = await get_subscription(db, str(user["_id"]))
    current = await get_plan(db, subscription.get("plan", ""), active_only=False)
    rows = await db.db.plans.find({"is_active": True}).sort("display_order", 1).to_list(100)
    result = []
    for plan in rows:
        if plan["key"] == subscription.get("plan"):
            continue
        if plan.get("requires_contact"):
            item = serialize_plan(plan)
            item["change_type"] = "contact"
            result.append(item)
            continue
        try:
            quote = subscription_change_quote(subscription, plan["key"], current, plan)
        except HTTPException:
            continue
        allowed = plan.get("allow_upgrade", True) if quote["direction"] == "upgrade" else plan.get("allow_downgrade", True)
        if allowed:
            item = serialize_plan(plan)
            item["change_type"] = quote["direction"]
            result.append(item)
    return result


@router.get("/change/quote")
async def change_quote(
    requested_plan: str,
    user: dict = Depends(require_auth),
):
    if user.get("role") != "user":
        raise HTTPException(status_code=403, detail="Chỉ chủ website có thể đổi gói")
    db = await get_mongodb()
    subscription = await get_subscription(db, str(user["_id"]))
    if subscription.get("next_plan_paid"):
        raise HTTPException(status_code=409, detail="Bạn đã thanh toán cho một thay đổi gói ở kỳ tiếp theo")
    requested = await require_plan(db, requested_plan)
    current = await get_plan(db, subscription.get("plan", ""), active_only=False)
    return subscription_change_quote(subscription, requested_plan, current, requested)


@router.post("/change", status_code=201)
async def change_subscription(
    body: SubscriptionChange,
    user: dict = Depends(require_auth),
):
    """Schedule a downgrade or create a prorated SePay checkout for an upgrade."""
    if user.get("role") != "user":
        raise HTTPException(status_code=403, detail="Chỉ chủ website có thể đổi gói")
    db = await get_mongodb()
    owner_id = str(user["_id"])
    subscription = await get_subscription(db, owner_id)
    if subscription.get("next_plan_paid"):
        raise HTTPException(status_code=409, detail="Bạn đã thanh toán cho một thay đổi gói ở kỳ tiếp theo")
    requested = await require_plan(db, body.requested_plan)
    if requested.get("requires_contact"):
        raise HTTPException(status_code=400, detail="Gói này cần liên hệ tư vấn")
    current = await get_plan(db, subscription.get("plan", ""), active_only=False)
    quote = subscription_change_quote(subscription, body.requested_plan, current, requested)
    if quote["direction"] == "upgrade" and not requested.get("allow_upgrade", True):
        raise HTTPException(status_code=400, detail="Gói này hiện không cho phép nâng cấp")
    if quote["direction"] == "downgrade" and not requested.get("allow_downgrade", True):
        raise HTTPException(status_code=400, detail="Gói này hiện không cho phép hạ cấp")
    now = utcnow()

    if not all((
        settings.SEPAY_ENABLED, settings.SEPAY_MERCHANT_ID,
        settings.SEPAY_MERCHANT_SECRET_KEY, settings.SEPAY_IPN_SECRET_KEY,
        settings.SEPAY_CHECKOUT_URL,
    )):
        raise HTTPException(status_code=503, detail="Thanh toán SePay chưa được cấu hình đầy đủ")
    pending = await db.db.checkout_orders.find_one({
        "owner_id": owner_id,
        "order_type": "subscription_change",
        "status": {"$in": ["pending", "processing"]},
        "expires_at": {"$gt": now},
    })
    if pending:
        raise HTTPException(status_code=409, detail="Bạn đang có một giao dịch nâng cấp chưa hoàn tất")

    access_token = generate_access_token()
    order = {
        "order_id": generate_order_id(),
        "order_type": "subscription_change",
        "access_token_hash": hash_token(access_token),
        "owner_id": owner_id,
        "email": str(user.get("email") or "").lower(),
        "company_name": user.get("name") or user.get("email"),
        "from_plan": quote["current_plan"],
        "plan": body.requested_plan,
        "plan_version": int(requested.get("version") or 1),
        "plan_snapshot": plan_snapshot(requested),
        "price_snapshot": {
            "subtotal": quote["subtotal"], "discount": 0, "vat": quote["vat"],
            "total": quote["total"], "vat_rate": quote["vat_rate"],
        },
        "change_direction": quote["direction"],
        "payment_method": "bank_transfer",
        "subtotal": quote["subtotal"],
        "discount": 0,
        "vat": quote["vat"],
        "total": quote["total"],
        "status": "pending",
        "current_period_start": quote["current_period_start"],
        "current_period_end": quote["current_period_end"],
        "expires_at": now + timedelta(minutes=settings.PAYMENT_ORDER_EXPIRE_MINUTES),
        "created_at": now,
        "updated_at": now,
    }
    inserted = await db.db.checkout_orders.insert_one(order)
    order["_id"] = inserted.inserted_id
    response = public_order(order, checkout=build_sepay_checkout(order))
    response["access_token"] = access_token
    return response


@router.post("/renew", status_code=201)
async def renew_subscription(user: dict = Depends(require_auth)):
    if user.get("role") != "user":
        raise HTTPException(status_code=403, detail="Chỉ chủ website có thể gia hạn")
    db = await get_mongodb()
    owner_id = str(user["_id"])
    subscription = await get_subscription(db, owner_id)
    plan = await require_plan(db, subscription.get("plan", ""))
    if plan.get("requires_contact") or plan.get("monthly_price") is None:
        raise HTTPException(status_code=400, detail="Gói này cần liên hệ để gia hạn")
    if not all((
        settings.SEPAY_ENABLED, settings.SEPAY_MERCHANT_ID,
        settings.SEPAY_MERCHANT_SECRET_KEY, settings.SEPAY_IPN_SECRET_KEY,
        settings.SEPAY_CHECKOUT_URL,
    )):
        raise HTTPException(status_code=503, detail="Thanh toán SePay chưa được cấu hình đầy đủ")
    now = utcnow()
    existing = await db.db.checkout_orders.find_one({
        "owner_id": owner_id, "order_type": "renewal",
        "status": {"$in": ["pending", "processing"]}, "expires_at": {"$gt": now},
    })
    if existing:
        raise HTTPException(status_code=409, detail="Bạn đang có đơn gia hạn chưa hoàn tất")
    subtotal = int(plan.get("monthly_price") or 0)
    vat = round(subtotal * float(plan.get("vat_rate", 10)) / 100)
    if subtotal <= 0:
        raise HTTPException(status_code=400, detail="Gói miễn phí không cần gia hạn thanh toán")
    access_token = generate_access_token()
    snapshot = plan_snapshot(plan)
    period_end = subscription.get("current_period_end") or subscription.get("expires_at")
    if period_end and period_end.tzinfo is None:
        period_end = period_end.replace(tzinfo=timezone.utc)
    renewal_start = max(now, period_end) if period_end else now
    order = {
        "order_id": generate_order_id(), "order_type": "renewal",
        "access_token_hash": hash_token(access_token), "owner_id": owner_id,
        "email": str(user.get("email") or "").lower(),
        "company_name": user.get("name") or user.get("email"),
        "plan": plan["key"], "plan_version": snapshot["version"], "plan_snapshot": snapshot,
        "price_snapshot": {"subtotal": subtotal, "discount": 0, "vat": vat, "total": subtotal + vat, "vat_rate": plan.get("vat_rate", 10)},
        "payment_method": "bank_transfer", "subtotal": subtotal, "discount": 0,
        "vat": vat, "total": subtotal + vat, "status": "pending",
        "renewal_period_start": renewal_start,
        "expires_at": now + timedelta(minutes=settings.PAYMENT_ORDER_EXPIRE_MINUTES),
        "created_at": now, "updated_at": now,
    }
    inserted = await db.db.checkout_orders.insert_one(order)
    order["_id"] = inserted.inserted_id
    response = public_order(order, checkout=build_sepay_checkout(order))
    response["access_token"] = access_token
    return response


@router.get("/requests/me")
async def my_upgrade_requests(user: dict = Depends(require_auth)):
    db = await get_mongodb()
    owner_id = await resolve_owner_id(db, user)
    rows = await db.db.subscription_upgrade_requests.find(
        {"owner_id": owner_id}
    ).sort("created_at", -1).to_list(length=50)
    return [serialize_document(row) for row in rows]


@router.post("/requests", status_code=201)
async def create_upgrade_request(
    request: UpgradeRequestCreate,
    user: dict = Depends(require_auth),
):
    if user.get("role") != "user":
        raise HTTPException(status_code=403, detail="Only website owners can request an upgrade")
    db = await get_mongodb()
    owner_id = str(user["_id"])
    current = await subscription_summary(db, owner_id)
    if current["plan"]["key"] == request.requested_plan:
        raise HTTPException(status_code=400, detail="You are already using this plan")
    pending = await db.db.subscription_upgrade_requests.find_one(
        {"owner_id": owner_id, "status": "pending"}
    )
    if pending:
        raise HTTPException(status_code=409, detail="An upgrade request is already pending")
    now = datetime.now(timezone.utc)
    document = {
        "owner_id": owner_id,
        "owner_email": user.get("email"),
        "owner_name": user.get("name"),
        "current_plan": current["plan"]["key"],
        "requested_plan": request.requested_plan,
        "status": "pending",
        "note": request.note,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.db.subscription_upgrade_requests.insert_one(document)
    document["_id"] = result.inserted_id
    return serialize_document(document)


@router.get("/admin")
async def admin_subscriptions(_admin: dict = Depends(require_account_admin)):
    db = await get_mongodb()
    users = await db.db.users.find({"role": "user"}).sort("created_at", -1).to_list(length=1000)
    result = []
    for user in users:
        owner_id = str(user["_id"])
        summary = await subscription_summary(db, owner_id)
        result.append({
            "user": {
                "id": owner_id,
                "email": user.get("email"),
                "name": user.get("name"),
                "created_at": user.get("created_at"),
            },
            **summary,
        })
    return result


@router.get("/admin/requests")
async def admin_upgrade_requests(
    status: Optional[Literal["pending", "approved", "rejected"]] = None,
    _admin: dict = Depends(require_account_admin),
):
    db = await get_mongodb()
    query = {"status": status} if status else {}
    rows = await db.db.subscription_upgrade_requests.find(query).sort(
        "created_at", -1
    ).to_list(length=500)
    return [serialize_document(row) for row in rows]


@router.get("/admin/{owner_id}/history")
async def subscription_history(
    owner_id: str,
    _admin: dict = Depends(require_account_admin),
):
    db = await get_mongodb()
    rows = await db.db.subscription_audit_logs.find(
        {"owner_id": owner_id}
    ).sort("created_at", -1).to_list(length=200)
    return [serialize_document(row) for row in rows]


@router.patch("/admin/requests/{request_id}")
async def decide_upgrade_request(
    request_id: str,
    decision: UpgradeDecision,
    admin: dict = Depends(require_account_admin),
):
    db = await get_mongodb()
    try:
        query = {"_id": ObjectId(request_id)}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request ID")
    now = datetime.now(timezone.utc)
    actor_id = str(admin["_id"])
    upgrade = await db.db.subscription_upgrade_requests.find_one_and_update(
        {**query, "status": "pending"},
        {"$set": {
            "status": decision.decision,
            "decision_note": decision.note,
            "decided_by": actor_id,
            "decided_at": now,
            "updated_at": now,
        }},
        return_document=ReturnDocument.BEFORE,
    )
    if not upgrade:
        existing = await db.db.subscription_upgrade_requests.find_one(query)
        if existing:
            raise HTTPException(status_code=409, detail="Upgrade request was already processed")
        raise HTTPException(status_code=404, detail="Upgrade request not found")
    if decision.decision == "approved":
        await db.db.subscriptions.update_one(
            {"owner_id": upgrade["owner_id"]},
            {
                "$set": {
                    "owner_id": upgrade["owner_id"],
                    "plan": upgrade["requested_plan"],
                    "status": "active",
                    "custom_limits": {},
                    "updated_at": now,
                    "updated_by": actor_id,
                },
                "$setOnInsert": {"started_at": now, "created_at": now},
            },
            upsert=True,
        )
    await db.db.subscription_audit_logs.insert_one({
        "owner_id": upgrade["owner_id"],
        "actor_id": actor_id,
        "action": f"upgrade_request_{decision.decision}",
        "from_plan": upgrade.get("current_plan"),
        "plan": upgrade.get("requested_plan"),
        "request_id": request_id,
        "note": decision.note,
        "created_at": now,
    })
    updated = await db.db.subscription_upgrade_requests.find_one(query)
    return serialize_document(updated)


@router.put("/admin/{owner_id}")
async def update_subscription(
    owner_id: str,
    update: SubscriptionUpdate,
    admin: dict = Depends(require_account_admin),
):
    db = await get_mongodb()
    try:
        owner_query = {"_id": ObjectId(owner_id)}
    except Exception:
        owner_query = {"_id": owner_id}
    owner = await db.db.users.find_one(owner_query)
    if not owner or owner.get("role") != "user":
        raise HTTPException(status_code=404, detail="Owner account not found")

    now = datetime.now(timezone.utc)
    previous = await db.db.subscriptions.find_one({"owner_id": owner_id}) or {}
    payload = update.model_dump(exclude={"note"})
    payload.update({"owner_id": owner_id, "updated_at": now, "updated_by": str(admin["_id"])})
    await db.db.subscriptions.update_one(
        {"owner_id": owner_id},
        {"$set": payload, "$setOnInsert": {"started_at": now, "created_at": now}},
        upsert=True,
    )
    await db.db.subscription_audit_logs.insert_one({
        "owner_id": owner_id,
        "actor_id": str(admin["_id"]),
        "action": "subscription_updated",
        "previous_plan": previous.get("plan", "legacy"),
        "previous_status": previous.get("status", "active"),
        "plan": update.plan,
        "status": update.status,
        "expires_at": update.expires_at,
        "custom_limits": update.custom_limits,
        "note": update.note,
        "created_at": now,
    })
    return await subscription_summary(db, owner_id)
