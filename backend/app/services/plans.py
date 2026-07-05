"""Dynamic subscription plan catalog and safe seed/backfill helpers."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException


DEFAULT_PLANS: list[dict[str, Any]] = [
    {
        "key": "starter", "name": "Khởi đầu", "description": "Dùng thử Auralis trong 7 ngày",
        "monthly_price": 0, "vat_rate": 10, "trial_days": 7,
        "limits": {"sites": 1, "members": 1, "messages": 1_000, "crawl_pages": 100},
        "features": {"byok": False, "handoff": False, "api": False, "white_label": False},
        "display_features": ["1 website", "1.000 hội thoại AI", "100 trang lập chỉ mục", "1 thành viên"],
        "display_order": 10, "badge": None, "cta_label": "Bắt đầu dùng thử",
        "is_public": True, "is_active": True, "allow_new_signup": True,
        "allow_upgrade": True, "allow_downgrade": False, "requires_contact": False,
    },
    {
        "key": "growth", "name": "Tăng trưởng", "description": "Dành cho doanh nghiệp đang phát triển",
        "monthly_price": 2_400_000, "vat_rate": 10, "trial_days": 0,
        "limits": {"sites": 5, "members": 5, "messages": 10_000, "crawl_pages": 2_000},
        "features": {"byok": False, "handoff": True, "api": False, "white_label": False},
        "display_features": ["5 website", "10.000 hội thoại AI mỗi tháng", "2.000 trang lập chỉ mục", "5 thành viên và handoff"],
        "display_order": 20, "badge": "Phổ biến nhất", "cta_label": "Chọn gói Tăng trưởng",
        "is_public": True, "is_active": True, "allow_new_signup": True,
        "allow_upgrade": True, "allow_downgrade": True, "requires_contact": False,
    },
    {
        "key": "business", "name": "Doanh nghiệp", "description": "Hạn mức lớn và hỗ trợ ưu tiên",
        "monthly_price": 9_800_000, "vat_rate": 10, "trial_days": 0,
        "limits": {"sites": 20, "members": 20, "messages": 100_000, "crawl_pages": 20_000},
        "features": {"byok": False, "handoff": True, "api": True, "white_label": True},
        "display_features": ["20 website", "100.000 hội thoại AI mỗi tháng", "20.000 trang lập chỉ mục", "Hỗ trợ ưu tiên"],
        "display_order": 30, "badge": None, "cta_label": "Chọn gói Doanh nghiệp",
        "is_public": True, "is_active": True, "allow_new_signup": True,
        "allow_upgrade": True, "allow_downgrade": True, "requires_contact": False,
    },
    {
        "key": "custom", "name": "Tùy chỉnh", "description": "BYOK và hạn mức theo nhu cầu",
        "monthly_price": None, "vat_rate": 10, "trial_days": 0,
        "limits": {"sites": None, "members": None, "messages": None, "crawl_pages": None},
        "features": {"byok": True, "handoff": True, "api": True, "white_label": True},
        "display_features": ["Kết nối API model riêng", "Tự chọn nhà cung cấp AI", "Hạn mức theo nhu cầu", "Hỗ trợ triển khai"],
        "display_order": 40, "badge": None, "cta_label": "Liên hệ triển khai",
        "is_public": True, "is_active": True, "allow_new_signup": False,
        "allow_upgrade": True, "allow_downgrade": False, "requires_contact": True,
    },
]


def plan_snapshot(plan: dict) -> dict:
    return {
        "key": plan["key"], "name": plan["name"], "version": int(plan.get("version") or 1),
        "monthly_price": plan.get("monthly_price"), "vat_rate": plan.get("vat_rate", 10),
        "trial_days": plan.get("trial_days", 0), "limits": deepcopy(plan.get("limits") or {}),
        "features": deepcopy(plan.get("features") or {}),
    }


def serialize_plan(plan: dict) -> dict:
    result = deepcopy(plan)
    if "_id" in result:
        result["id"] = str(result.pop("_id"))
    return result


async def seed_default_plans(db) -> None:
    now = datetime.now(timezone.utc)
    for source in DEFAULT_PLANS:
        document = {**deepcopy(source), "version": 1, "created_at": now, "updated_at": now}
        await db.db.plans.update_one(
            {"key": source["key"]},
            {"$setOnInsert": document},
            upsert=True,
        )


async def get_plan(db, key: str, *, active_only: bool = True) -> Optional[dict]:
    query: dict[str, Any] = {"key": key}
    if active_only:
        query["is_active"] = True
    return await db.db.plans.find_one(query)


async def require_plan(db, key: str, *, for_signup: bool = False) -> dict:
    plan = await get_plan(db, key)
    if not plan:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói dịch vụ")
    if for_signup and (not plan.get("allow_new_signup") or plan.get("requires_contact")):
        raise HTTPException(status_code=400, detail="Gói này cần liên hệ tư vấn")
    return plan


async def backfill_subscription_snapshots(db) -> int:
    changed = 0
    async for subscription in db.db.subscriptions.find({
        "$or": [{"plan_snapshot": {"$exists": False}}, {"plan_version": {"$exists": False}}],
    }):
        plan = await get_plan(db, subscription.get("plan", ""), active_only=False)
        if not plan:
            continue
        snapshot = plan_snapshot(plan)
        await db.db.subscriptions.update_one(
            {"_id": subscription["_id"]},
            {"$set": {"plan_snapshot": snapshot, "plan_version": snapshot["version"]}},
        )
        changed += 1
    return changed
