"""Public and Platform Admin APIs for the dynamic plan catalog."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.database import get_mongodb
from app.routes.auth import require_platform_admin
from app.services.plans import get_plan, plan_snapshot, serialize_plan

router = APIRouter(prefix="/api", tags=["plans"])


class PlanInput(BaseModel):
    key: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=500)
    monthly_price: Optional[int] = Field(default=None, ge=0)
    vat_rate: float = Field(default=10, ge=0, le=100)
    trial_days: int = Field(default=0, ge=0, le=365)
    limits: dict[str, Optional[int]]
    features: dict[str, bool] = Field(default_factory=dict)
    display_features: list[str] = Field(default_factory=list, max_length=20)
    display_order: int = 0
    badge: Optional[str] = Field(default=None, max_length=60)
    cta_label: str = Field(default="Chọn gói", max_length=100)
    is_public: bool = True
    is_active: bool = True
    allow_new_signup: bool = True
    allow_upgrade: bool = True
    allow_downgrade: bool = True
    requires_contact: bool = False

    @field_validator("key")
    @classmethod
    def valid_key(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]+", value):
            raise ValueError("Key chỉ gồm chữ thường, số, gạch ngang hoặc gạch dưới")
        return value

    @field_validator("limits")
    @classmethod
    def valid_limits(cls, value: dict[str, Optional[int]]):
        allowed = {"sites", "members", "messages", "crawl_pages"}
        if set(value) != allowed:
            raise ValueError("Limits phải gồm sites, members, messages và crawl_pages")
        if any(item is not None and item < 0 for item in value.values()):
            raise ValueError("Limit không được âm")
        return value


class PlanUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    monthly_price: Optional[int] = Field(default=None, ge=0)
    vat_rate: Optional[float] = Field(default=None, ge=0, le=100)
    trial_days: Optional[int] = Field(default=None, ge=0, le=365)
    limits: Optional[dict[str, Optional[int]]] = None
    features: Optional[dict[str, bool]] = None
    display_features: Optional[list[str]] = None
    display_order: Optional[int] = None
    badge: Optional[str] = None
    cta_label: Optional[str] = None
    is_public: Optional[bool] = None
    is_active: Optional[bool] = None
    allow_new_signup: Optional[bool] = None
    allow_upgrade: Optional[bool] = None
    allow_downgrade: Optional[bool] = None
    requires_contact: Optional[bool] = None


async def _audit(db, actor: dict, action: str, plan: dict, before: Optional[dict] = None):
    await db.db.platform_audit_logs.insert_one({
        "actor_id": str(actor["_id"]), "action": action,
        "resource_type": "plan", "resource_id": str(plan["_id"]),
        "before": before, "after": serialize_plan(plan),
        "created_at": datetime.now(timezone.utc),
    })


@router.get("/plans/public")
async def public_plans():
    db = await get_mongodb()
    rows = await db.db.plans.find({"is_public": True, "is_active": True}).sort("display_order", 1).to_list(100)
    return [serialize_plan(row) for row in rows]


@router.get("/plans/{key}")
async def public_plan(key: str):
    plan = await get_plan(await get_mongodb(), key)
    if not plan:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói")
    return serialize_plan(plan)


@router.get("/platform/plans")
async def admin_plans(_admin: dict = Depends(require_platform_admin)):
    db = await get_mongodb()
    rows = await db.db.plans.find({}).sort("display_order", 1).to_list(200)
    return [serialize_plan(row) for row in rows]


@router.post("/platform/plans", status_code=201)
async def create_plan(body: PlanInput, admin: dict = Depends(require_platform_admin)):
    db = await get_mongodb()
    if await db.db.plans.find_one({"key": body.key}):
        raise HTTPException(status_code=409, detail="Mã gói đã tồn tại")
    now = datetime.now(timezone.utc)
    document = {**body.model_dump(), "version": 1, "created_at": now, "updated_at": now}
    result = await db.db.plans.insert_one(document)
    document["_id"] = result.inserted_id
    await _audit(db, admin, "plan_created", document)
    return serialize_plan(document)


@router.patch("/platform/plans/{plan_id}")
async def update_plan(plan_id: str, body: PlanUpdate, admin: dict = Depends(require_platform_admin)):
    db = await get_mongodb()
    try:
        query = {"_id": ObjectId(plan_id)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail="ID gói không hợp lệ") from exc
    current = await db.db.plans.find_one(query)
    if not current:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói")
    updates = body.model_dump(exclude_unset=True)
    updates.update({"updated_at": datetime.now(timezone.utc), "version": int(current.get("version") or 1) + 1})
    await db.db.plans.update_one(query, {"$set": updates})
    updated = await db.db.plans.find_one(query)
    await _audit(db, admin, "plan_updated", updated, serialize_plan(current))
    return serialize_plan(updated)


@router.post("/platform/plans/{plan_id}/archive")
async def archive_plan(plan_id: str, admin: dict = Depends(require_platform_admin)):
    db = await get_mongodb()
    try:
        query = {"_id": ObjectId(plan_id)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail="ID gói không hợp lệ") from exc
    current = await db.db.plans.find_one(query)
    if not current:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói")
    await db.db.plans.update_one(query, {"$set": {
        "is_active": False, "is_public": False, "allow_new_signup": False,
        "updated_at": datetime.now(timezone.utc),
        "version": int(current.get("version") or 1) + 1,
    }})
    updated = await db.db.plans.find_one(query)
    await _audit(db, admin, "plan_archived", updated, serialize_plan(current))
    return serialize_plan(updated)
