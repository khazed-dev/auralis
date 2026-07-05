"""Idempotent dynamic-plan seed/backfill utility.

Usage:
  python scripts/migrate_dynamic_plans.py --dry-run
  python scripts/migrate_dynamic_plans.py --apply
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Allow direct execution from backend/: python scripts/migrate_dynamic_plans.py
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.database import get_mongodb
from app.services.plans import DEFAULT_PLANS, backfill_subscription_snapshots, seed_default_plans


async def main(apply: bool) -> None:
    db = await get_mongodb()
    missing_plans = [
        plan["key"] for plan in DEFAULT_PLANS
        if not await db.db.plans.find_one({"key": plan["key"]})
    ]
    missing_snapshots = await db.db.subscriptions.count_documents({
        "$or": [{"plan_snapshot": {"$exists": False}}, {"plan_version": {"$exists": False}}],
    })
    print({
        "mode": "apply" if apply else "dry-run",
        "plans_to_seed": missing_plans,
        "subscriptions_to_backfill": missing_snapshots,
    })
    if apply:
        await seed_default_plans(db)
        changed = await backfill_subscription_snapshots(db)
        print({"seeded": len(missing_plans), "backfilled": changed})
    await db.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
