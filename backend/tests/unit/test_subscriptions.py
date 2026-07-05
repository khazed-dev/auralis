from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.services.subscriptions import (
    PLAN_CATALOG,
    effective_limits,
    enforce_quota,
    get_subscription,
    subscription_summary,
)


def mongo_with(subscription: dict, usage: dict, *, sites: int = 0, members: int = 0):
    provider = MagicMock()
    provider.db = MagicMock()
    provider.db.subscriptions.find_one = AsyncMock(return_value=subscription)
    provider.db.subscription_usage.find_one = AsyncMock(return_value=usage)
    provider.db.sites.count_documents = AsyncMock(return_value=sites)
    provider.db.users.count_documents = AsyncMock(return_value=members)
    return provider


def test_custom_limits_override_catalog():
    limits = effective_limits({"plan": "growth", "custom_limits": {"sites": 12}})
    assert limits["sites"] == 12
    assert limits["messages"] == PLAN_CATALOG["growth"]["limits"]["messages"]


@pytest.mark.asyncio
async def test_missing_subscription_is_legacy_and_unlimited():
    db = mongo_with(None, None, sites=4, members=3)
    summary = await subscription_summary(db, "owner-1")
    assert summary["plan"]["key"] == "legacy"
    assert summary["resources"]["sites"]["limit"] is None


@pytest.mark.asyncio
async def test_quota_rejects_when_next_unit_exceeds_limit():
    db = mongo_with(
        {"owner_id": "owner-1", "plan": "starter", "status": "active"},
        {"messages": 1_000},
    )
    with pytest.raises(HTTPException) as exc:
        await enforce_quota(db, "owner-1", "messages")
    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "plan_limit_reached"


@pytest.mark.asyncio
async def test_inactive_subscription_is_rejected():
    db = mongo_with(
        {"owner_id": "owner-1", "plan": "growth", "status": "suspended"},
        {},
    )
    with pytest.raises(HTTPException) as exc:
        await enforce_quota(db, "owner-1", "messages")
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "subscription_inactive"


@pytest.mark.asyncio
async def test_previous_checkout_starter_is_repaired_to_selected_paid_plan():
    subscription = {
        "_id": "subscription-1",
        "owner_id": "owner-1",
        "plan": "starter",
        "status": "trialing",
        "trial_ends_at": datetime.now(timezone.utc),
    }
    db = mongo_with(subscription, {})
    db.db.checkout_orders.find_one = AsyncMock(return_value={
        "owner_id": "owner-1",
        "plan": "growth",
        "status": "completed",
    })
    db.db.subscriptions.update_one = AsyncMock()

    repaired = await get_subscription(db, "owner-1")

    assert repaired["plan"] == "growth"
    assert repaired["status"] == "active"
    assert repaired["expires_at"] is None
