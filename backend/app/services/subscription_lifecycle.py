"""Periodic subscription/order lifecycle maintenance."""
from datetime import datetime, timezone

from loguru import logger

from app.services.subscriptions import get_subscription


async def run_subscription_lifecycle(db) -> dict:
    now = datetime.now(timezone.utc)
    rolled_over = 0
    expired_subscriptions = 0
    expired_orders = 0

    cursor = db.db.subscriptions.find({
        "current_period_end": {"$lte": now},
        "status": {"$in": ["active", "trialing"]},
    })
    async for subscription in cursor:
        owner_id = subscription["owner_id"]
        if subscription.get("next_plan_paid"):
            updated = await get_subscription(db, owner_id)
            if updated.get("plan") != subscription.get("plan"):
                rolled_over += 1
                continue
        result = await db.db.subscriptions.update_one(
            {"_id": subscription["_id"], "status": {"$in": ["active", "trialing"]}},
            {"$set": {"status": "expired", "updated_at": now}},
        )
        expired_subscriptions += result.modified_count

    orders = db.db.checkout_orders.find({
        "status": "pending",
        "expires_at": {"$lte": now},
    })
    async for order in orders:
        result = await db.db.checkout_orders.update_one(
            {"_id": order["_id"], "status": "pending"},
            {"$set": {"status": "expired", "updated_at": now}},
        )
        if result.modified_count and order.get("promo_id"):
            await db.db.promo_codes.update_one(
                {"_id": order["promo_id"], "reservations": {"$gt": 0}},
                {"$inc": {"reservations": -1}},
            )
        expired_orders += result.modified_count

    stats = {
        "rolled_over": rolled_over,
        "expired_subscriptions": expired_subscriptions,
        "expired_orders": expired_orders,
    }
    if any(stats.values()):
        logger.info(f"Subscription lifecycle processed: {stats}")
    return stats
