from datetime import datetime, timedelta, timezone

from app.services.plans import DEFAULT_PLANS, plan_snapshot
from app.services.subscriptions import subscription_change_quote


def test_plan_snapshot_is_immutable_copy():
    plan = {
        "key": "scale", "name": "Scale", "version": 3,
        "monthly_price": 5_000_000, "vat_rate": 8, "trial_days": 0,
        "limits": {"sites": 10, "members": 12, "messages": 50_000, "crawl_pages": 8_000},
        "features": {"api": True},
    }
    snapshot = plan_snapshot(plan)
    plan["limits"]["sites"] = 999

    assert snapshot["version"] == 3
    assert snapshot["limits"]["sites"] == 10


def test_fifth_dynamic_plan_participates_in_pricing_without_code_changes():
    now = datetime.now(timezone.utc)
    quote = subscription_change_quote(
        {
            "plan": "growth",
            "plan_snapshot": {"monthly_price": 2_400_000, "trial_days": 0},
            "current_period_start": now - timedelta(days=15),
            "current_period_end": now + timedelta(days=15),
        },
        "scale",
        requested_plan_document={
            "key": "scale", "monthly_price": 5_000_000, "vat_rate": 8,
            "is_active": True, "trial_days": 0,
        },
    )

    assert quote["requested_plan"] == "scale"
    assert quote["direction"] == "upgrade"
    assert 1_299_000 <= quote["subtotal"] <= 1_300_000
    assert quote["vat"] == round(quote["subtotal"] * .08)


def test_default_catalog_has_stable_unique_keys():
    keys = [plan["key"] for plan in DEFAULT_PLANS]
    assert len(keys) == len(set(keys))
