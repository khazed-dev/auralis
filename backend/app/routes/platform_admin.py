"""Backend-first operational APIs for the dedicated Platform Admin UI."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.database import get_mongodb
from app.routes.auth import require_platform_admin
from app.services.subscriptions import subscription_summary
from app.services.sepay_gateway import fetch_sepay_order
from app.services.plans import plan_snapshot, require_plan

router = APIRouter(prefix="/api/platform", tags=["platform-admin"])


def serialize(document: dict) -> dict:
    def clean(value):
        if isinstance(value, ObjectId):
            return str(value)
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    result = clean(dict(document))
    if "_id" in result:
        result["id"] = str(result.pop("_id"))
    return result


async def audit(db, admin: dict, request: Request, action: str, resource_type: str, resource_id: str, before=None, after=None, reason=None):
    await db.db.platform_audit_logs.insert_one({
        "actor_id": str(admin["_id"]), "actor_email": admin.get("email"),
        "action": action, "resource_type": resource_type, "resource_id": resource_id,
        "before": before, "after": after, "reason": reason,
        "ip_address": request.client.host if request.client else None,
        "created_at": datetime.now(timezone.utc),
    })


class CustomerStateChange(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class SubscriptionAdjustment(BaseModel):
    plan: Optional[str] = None
    status: Optional[Literal["active", "trialing", "past_due", "suspended", "cancelled", "expired"]] = None
    expires_at: Optional[datetime] = None
    custom_limits: Optional[dict[str, Optional[int]]] = None
    reason: str = Field(min_length=3, max_length=500)


class PlatformRequestCreate(BaseModel):
    type: Literal["custom_plan", "quota_exception", "refund", "payment_mismatch", "late_payment", "other"]
    customer_id: str
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    request_data: dict = Field(default_factory=dict)


class PlatformRequestUpdate(BaseModel):
    status: Optional[Literal["new", "in_progress", "waiting_customer", "approved", "rejected", "completed"]] = None
    priority: Optional[Literal["low", "normal", "high", "urgent"]] = None
    assigned_admin_id: Optional[str] = None
    internal_note: Optional[str] = Field(default=None, max_length=2000)
    resolution: Optional[str] = Field(default=None, max_length=2000)


@router.get("/overview")
async def overview(_admin: dict = Depends(require_platform_admin)):
    db = await get_mongodb()
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    revenue_pipeline = [
        {"$match": {"status": "completed", "completed_at": {"$gte": month_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$total"}, "orders": {"$sum": 1}}},
    ]
    revenue_rows = await db.db.checkout_orders.aggregate(revenue_pipeline).to_list(1)
    revenue = revenue_rows[0] if revenue_rows else {"total": 0, "orders": 0}
    plan_counts = await db.db.subscriptions.aggregate([
        {"$group": {"_id": "$plan", "count": {"$sum": 1}}},
    ]).to_list(100)
    return {
        "customers": await db.db.users.count_documents({"role": "user"}),
        "active_subscriptions": await db.db.subscriptions.count_documents({"status": {"$in": ["active", "trialing"]}}),
        "trials": await db.db.subscriptions.count_documents({"status": "trialing"}),
        "expiring_in_7_days": await db.db.subscriptions.count_documents({
            "expires_at": {"$gt": now, "$lte": now + timedelta(days=7)},
        }),
        "monthly_revenue": int(revenue.get("total") or 0),
        "paid_orders": int(revenue.get("orders") or 0),
        "abnormal_payments": await db.db.payment_transactions.count_documents({
            "status": {"$in": ["unmatched", "unknown_order", "late_payment"]},
        }),
        "open_requests": await db.db.platform_requests.count_documents({
            "status": {"$in": ["new", "in_progress", "waiting_customer"]},
        }),
        "active_promos": await db.db.promo_codes.count_documents({"active": True}),
        "subscriptions_by_plan": {row["_id"] or "unknown": row["count"] for row in plan_counts},
    }


@router.get("/customers")
async def customers(
    q: Optional[str] = None, plan: Optional[str] = None, status: Optional[str] = None,
    page: int = Query(1, ge=1), limit: int = Query(25, ge=1, le=100),
    _admin: dict = Depends(require_platform_admin),
):
    db = await get_mongodb()
    query: dict = {"role": "user"}
    if q:
        query["$or"] = [
            {"email": {"$regex": q, "$options": "i"}},
            {"name": {"$regex": q, "$options": "i"}},
        ]
    if plan or status:
        subscription_query = {}
        if plan:
            subscription_query["plan"] = plan
        if status:
            subscription_query["status"] = status
        owner_ids = await db.db.subscriptions.distinct("owner_id", subscription_query)
        object_ids = []
        for owner_id in owner_ids:
            try:
                object_ids.append(ObjectId(owner_id))
            except Exception:
                continue
        query["_id"] = {"$in": object_ids}
    users = await db.db.users.find(query).sort("created_at", -1).skip((page - 1) * limit).limit(limit).to_list(limit)
    rows = []
    for user in users:
        sub = await db.db.subscriptions.find_one({"owner_id": str(user["_id"])}) or {"plan": "legacy", "status": "active"}
        rows.append({
            "id": str(user["_id"]), "email": user.get("email"), "name": user.get("name"),
            "active": user.get("active", True), "created_at": user.get("created_at"),
            "subscription": serialize(sub),
            "sites": await db.db.sites.count_documents({"user_id": str(user["_id"])}),
            "members": await db.db.users.count_documents({"owner_id": str(user["_id"]), "role": "agent"}),
        })
    return {"items": rows, "page": page, "limit": limit, "total": await db.db.users.count_documents(query)}


@router.get("/customers/{customer_id}")
async def customer_detail(customer_id: str, _admin: dict = Depends(require_platform_admin)):
    db = await get_mongodb()
    try:
        user = await db.db.users.find_one({"_id": ObjectId(customer_id)})
    except Exception:
        user = None
    if not user or user.get("role") != "user":
        raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng")
    summary = await subscription_summary(db, customer_id)
    return {
        "user": {key: value for key, value in serialize(user).items() if key not in {"password_hash", "refresh_token_hash"}},
        **summary,
        "sites": await db.db.sites.find({"user_id": customer_id}, {"site_id": 1, "name": 1, "url": 1, "status": 1}).to_list(500),
        "members": await db.db.users.find({"owner_id": customer_id, "role": "agent"}, {"email": 1, "name": 1, "active": 1}).to_list(500),
        "payments": [serialize(row) for row in await db.db.checkout_orders.find({"owner_id": customer_id}).sort("created_at", -1).to_list(100)],
        "audit_logs": [serialize(row) for row in await db.db.subscription_audit_logs.find({"owner_id": customer_id}).sort("created_at", -1).to_list(100)],
    }


@router.post("/customers/{customer_id}/suspend")
async def suspend_customer(customer_id: str, body: CustomerStateChange, request: Request, admin: dict = Depends(require_platform_admin)):
    db = await get_mongodb()
    before = await db.db.subscriptions.find_one({"owner_id": customer_id}) or {}
    await db.db.subscriptions.update_one({"owner_id": customer_id}, {"$set": {"status": "suspended", "updated_at": datetime.now(timezone.utc)}})
    await audit(db, admin, request, "customer_suspended", "customer", customer_id, serialize(before), {"status": "suspended"}, body.reason)
    return {"updated": True}


@router.post("/customers/{customer_id}/reactivate")
async def reactivate_customer(customer_id: str, body: CustomerStateChange, request: Request, admin: dict = Depends(require_platform_admin)):
    db = await get_mongodb()
    before = await db.db.subscriptions.find_one({"owner_id": customer_id}) or {}
    await db.db.subscriptions.update_one({"owner_id": customer_id}, {"$set": {"status": "active", "updated_at": datetime.now(timezone.utc)}})
    await audit(db, admin, request, "customer_reactivated", "customer", customer_id, serialize(before), {"status": "active"}, body.reason)
    return {"updated": True}


@router.post("/customers/{customer_id}/subscription-adjustment")
async def adjust_subscription(customer_id: str, body: SubscriptionAdjustment, request: Request, admin: dict = Depends(require_platform_admin)):
    db = await get_mongodb()
    before = await db.db.subscriptions.find_one({"owner_id": customer_id}) or {}
    updates = body.model_dump(exclude={"reason"}, exclude_none=True)
    if body.plan:
        plan = await require_plan(db, body.plan)
        updates["plan_version"] = int(plan.get("version") or 1)
        updates["plan_snapshot"] = plan_snapshot(plan)
    updates["updated_at"] = datetime.now(timezone.utc)
    await db.db.subscriptions.update_one({"owner_id": customer_id}, {"$set": updates}, upsert=True)
    await audit(db, admin, request, "subscription_adjusted", "subscription", customer_id, serialize(before), updates, body.reason)
    return await subscription_summary(db, customer_id)


@router.get("/payments")
async def payments(status: Optional[str] = None, q: Optional[str] = None, _admin: dict = Depends(require_platform_admin)):
    db = await get_mongodb()
    query: dict = {}
    if status:
        query["status"] = status
    if q:
        query["$or"] = [{"order_id": {"$regex": q, "$options": "i"}}, {"email": {"$regex": q, "$options": "i"}}]
    return [serialize(row) for row in await db.db.checkout_orders.find(query).sort("created_at", -1).to_list(500)]


@router.post("/payments/{order_id}/reconcile")
async def reconcile_payment(order_id: str, request: Request, admin: dict = Depends(require_platform_admin)):
    db = await get_mongodb()
    order = await db.db.checkout_orders.find_one({"order_id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn Auralis")
    sepay_order_id = order.get("sepay_order_id")
    if not sepay_order_id:
        transaction = await db.db.payment_transactions.find_one({"order_id": order_id})
        sepay_order_id = ((transaction or {}).get("payload") or {}).get("order", {}).get("order_id")
    if not sepay_order_id:
        raise HTTPException(status_code=409, detail="Đơn chưa có SePay order ID để đối soát")
    provider = await fetch_sepay_order(sepay_order_id)
    await audit(db, admin, request, "payment_reconciled", "payment", order_id, None, {
        "sepay_order_id": sepay_order_id,
        "provider_status": (provider.get("data") or {}).get("order_status"),
    })
    return {"local": serialize(order), "provider": provider}


@router.get("/requests")
async def requests_list(status: Optional[str] = None, _admin: dict = Depends(require_platform_admin)):
    db = await get_mongodb()
    query = {"status": status} if status else {}
    return [serialize(row) for row in await db.db.platform_requests.find(query).sort("created_at", -1).to_list(500)]


@router.post("/requests", status_code=201)
async def request_create(body: PlatformRequestCreate, admin: dict = Depends(require_platform_admin)):
    db = await get_mongodb()
    now = datetime.now(timezone.utc)
    document = {**body.model_dump(), "status": "new", "created_by": str(admin["_id"]), "created_at": now, "updated_at": now}
    result = await db.db.platform_requests.insert_one(document)
    document["_id"] = result.inserted_id
    return serialize(document)


@router.patch("/requests/{request_id}")
async def request_update(request_id: str, body: PlatformRequestUpdate, request: Request, admin: dict = Depends(require_platform_admin)):
    db = await get_mongodb()
    try:
        query = {"_id": ObjectId(request_id)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail="ID yêu cầu không hợp lệ") from exc
    before = await db.db.platform_requests.find_one(query)
    if not before:
        raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu")
    updates = body.model_dump(exclude_unset=True, exclude={"internal_note"})
    updates["updated_at"] = datetime.now(timezone.utc)
    await db.db.platform_requests.update_one(query, {"$set": updates})
    if body.internal_note:
        await db.db.platform_requests.update_one(query, {"$push": {"internal_notes": {
            "text": body.internal_note, "actor_id": str(admin["_id"]), "created_at": datetime.now(timezone.utc),
        }}})
    updated = await db.db.platform_requests.find_one(query)
    await audit(db, admin, request, "platform_request_updated", "request", request_id, serialize(before), serialize(updated))
    return serialize(updated)


@router.get("/audit-logs")
async def audit_logs(
    resource_type: Optional[str] = None, resource_id: Optional[str] = None,
    _admin: dict = Depends(require_platform_admin),
):
    db = await get_mongodb()
    query = {}
    if resource_type:
        query["resource_type"] = resource_type
    if resource_id:
        query["resource_id"] = resource_id
    return [serialize(row) for row in await db.db.platform_audit_logs.find(query).sort("created_at", -1).to_list(1000)]
