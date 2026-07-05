"""Subscription plans, tenant usage accounting, and quota enforcement."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException


PLAN_CATALOG: dict[str, dict[str, Any]] = {
    "starter": {
        "name": "Starter",
        "limits": {"sites": 1, "members": 1, "messages": 1_000, "crawl_pages": 100},
        "features": {"byok": False},
    },
    "growth": {
        "name": "Growth",
        "limits": {"sites": 5, "members": 5, "messages": 10_000, "crawl_pages": 2_000},
        "features": {"byok": False},
    },
    "business": {
        "name": "Business",
        "limits": {"sites": 20, "members": 20, "messages": 100_000, "crawl_pages": 20_000},
        "features": {"byok": False},
    },
    "custom": {
        "name": "Custom",
        "limits": {"sites": None, "members": None, "messages": None, "crawl_pages": None},
        "features": {"byok": True},
    },
    # Existing accounts without a subscription remain uninterrupted after rollout.
    "legacy": {
        "name": "Legacy",
        "limits": {"sites": None, "members": None, "messages": None, "crawl_pages": None},
        "features": {"byok": False},
    },
}


def current_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _id(user: dict) -> str:
    return str(user.get("_id") or user.get("id") or user.get("user_id"))


async def resolve_owner_id(db, user: dict) -> str:
    if user.get("role") == "agent":
        return str(user.get("owner_id") or _id(user))
    return _id(user)


async def get_subscription(db, owner_id: str) -> dict:
    document = await db.db.subscriptions.find_one({"owner_id": owner_id})
    # Repair checkout accounts created before ownership IDs were normalized:
    # checkout stored provider user_id while authenticated tenants use Mongo _id.
    if not document:
        try:
            from bson import ObjectId
            user = await db.db.users.find_one({"_id": ObjectId(owner_id)}, {"user_id": 1})
        except Exception:
            user = None
        provider_user_id = (user or {}).get("user_id")
        if provider_user_id:
            document = await db.db.subscriptions.find_one({"owner_id": provider_user_id})
            if document:
                updates: dict[str, Any] = {"owner_id": owner_id, "updated_at": datetime.now(timezone.utc)}
                checkout = await db.db.checkout_orders.find_one({"owner_id": provider_user_id})
                if checkout:
                    started = checkout.get("created_at") or datetime.now(timezone.utc)
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                    checkout_plan = checkout.get("plan") or "starter"
                    is_starter = checkout_plan == "starter"
                    trial_ends_at = started + timedelta(days=7) if is_starter else None
                    updates.update({
                        "plan": checkout_plan,
                        "status": "trialing" if is_starter else "active",
                        "started_at": started,
                        "trial_ends_at": trial_ends_at,
                        "expires_at": trial_ends_at,
                        "source": "checkout",
                    })
                await db.db.subscriptions.update_one({"_id": document["_id"]}, {"$set": updates})
                document.update(updates)
    # Repair accounts provisioned by the previous checkout implementation,
    # which assigned Starter even when a paid plan was selected.
    if (
        document
        and document.get("plan") == "starter"
        and document.get("status") == "trialing"
        and document.get("trial_ends_at")
    ):
        checkout = await db.db.checkout_orders.find_one(
            {"owner_id": owner_id, "status": "completed"},
            sort=[("created_at", -1)],
        )
        checkout_plan = (checkout or {}).get("plan")
        if checkout_plan in {"growth", "business"}:
            updates = {
                "plan": checkout_plan,
                "status": "active",
                "trial_ends_at": None,
                "expires_at": None,
                "source": "checkout",
                "updated_at": datetime.now(timezone.utc),
            }
            await db.db.subscriptions.update_one({"_id": document["_id"]}, {"$set": updates})
            document.update(updates)
    if not document:
        return {
            "owner_id": owner_id,
            "plan": "legacy",
            "status": "active",
            "started_at": None,
            "expires_at": None,
            "custom_limits": {},
        }
    if "_id" in document:
        document["_id"] = str(document["_id"])
    return document


def effective_limits(subscription: dict) -> dict[str, Optional[int]]:
    plan = PLAN_CATALOG.get(subscription.get("plan"), PLAN_CATALOG["legacy"])
    limits = dict(plan["limits"])
    limits.update(subscription.get("custom_limits") or {})
    return limits


async def get_usage(db, owner_id: str) -> dict[str, int]:
    period = current_period()
    counters = await db.db.subscription_usage.find_one(
        {"owner_id": owner_id, "period": period}
    ) or {}
    return {
        "sites": await db.db.sites.count_documents({"user_id": owner_id}),
        "members": await db.db.users.count_documents({"role": "agent", "owner_id": owner_id}),
        "messages": int(counters.get("messages") or 0),
        "crawl_pages": int(counters.get("crawl_pages") or 0),
    }


async def subscription_summary(db, owner_id: str) -> dict:
    subscription = await get_subscription(db, owner_id)
    plan_key = subscription.get("plan", "legacy")
    usage = await get_usage(db, owner_id)
    limits = effective_limits(subscription)
    resources = {}
    for key, used in usage.items():
        limit = limits.get(key)
        resources[key] = {
            "used": used,
            "limit": limit,
            "remaining": None if limit is None else max(0, limit - used),
            "percent": 0 if not limit else min(100, round(used / limit * 100)),
        }
    return {
        "subscription": subscription,
        "plan": {"key": plan_key, **PLAN_CATALOG.get(plan_key, PLAN_CATALOG["legacy"])},
        "period": current_period(),
        "resources": resources,
    }


async def enforce_quota(db, owner_id: str, resource: str, amount: int = 1) -> None:
    # Non-persistent providers used by unit tests behave as legacy/unlimited.
    if getattr(db, "db", None) is None:
        return
    subscription = await get_subscription(db, owner_id)
    if subscription.get("status") not in {"active", "trialing"}:
        raise HTTPException(
            status_code=403,
            detail={"code": "subscription_inactive", "message": "Subscription is not active"},
        )
    expires_at = subscription.get("expires_at")
    if expires_at:
        now = datetime.now(timezone.utc)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise HTTPException(
                status_code=403,
                detail={"code": "subscription_expired", "message": "Subscription has expired"},
            )
    limit = effective_limits(subscription).get(resource)
    if limit is None:
        return
    used = (await get_usage(db, owner_id)).get(resource, 0)
    if used + amount > limit:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "plan_limit_reached",
                "resource": resource,
                "used": used,
                "limit": limit,
                "upgrade_required": True,
            },
        )


async def increment_usage(db, owner_id: str, resource: str, amount: int = 1) -> None:
    if amount <= 0 or getattr(db, "db", None) is None:
        return
    now = datetime.now(timezone.utc)
    await db.db.subscription_usage.update_one(
        {"owner_id": owner_id, "period": current_period()},
        {
            "$inc": {resource: amount},
            "$set": {"updated_at": now},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
