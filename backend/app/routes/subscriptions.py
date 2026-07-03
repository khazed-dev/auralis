"""Customer subscription and platform-admin management APIs."""
from datetime import datetime, timezone
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.database import get_mongodb
from app.routes.auth import require_admin, require_auth
from app.services.subscriptions import (
    PLAN_CATALOG,
    resolve_owner_id,
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


@router.get("/plans")
async def list_plans():
    return [{"key": key, **value} for key, value in PLAN_CATALOG.items() if key != "legacy"]


@router.get("/me")
async def my_subscription(user: dict = Depends(require_auth)):
    db = await get_mongodb()
    return await subscription_summary(db, await resolve_owner_id(db, user))


@router.get("/admin")
async def admin_subscriptions(_admin: dict = Depends(require_admin)):
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


@router.put("/admin/{owner_id}")
async def update_subscription(
    owner_id: str,
    update: SubscriptionUpdate,
    admin: dict = Depends(require_admin),
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
        "plan": update.plan,
        "status": update.status,
        "custom_limits": update.custom_limits,
        "note": update.note,
        "created_at": now,
    })
    return await subscription_summary(db, owner_id)
