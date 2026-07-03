"""MongoDB-backed crawl queue with atomic claiming and restart recovery."""
import asyncio
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Optional

from bson import ObjectId
from loguru import logger
from pymongo import ReturnDocument

from app.database import get_mongodb

QueueHandler = Callable[[str, dict], Awaitable[None]]


class CrawlQueue:
    def __init__(self) -> None:
        self._handler: Optional[QueueHandler] = None
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    def set_handler(self, handler: QueueHandler) -> None:
        self._handler = handler

    async def enqueue(self, job_id: str, payload: dict) -> None:
        db = await get_mongodb()
        await db.db.crawl_jobs.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {
                "status": "queued",
                "queue_payload": payload,
                "queued_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }},
        )

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        db = await get_mongodb()
        await db.db.crawl_jobs.update_many(
            {
                "status": "running",
                "queue_payload": {"$exists": True},
                "claimed_at": {"$lt": datetime.utcnow() - timedelta(minutes=10)},
            },
            {"$set": {"status": "queued", "updated_at": datetime.utcnow()}},
        )
        self._task = asyncio.create_task(self._run(), name="crawl-queue-worker")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        db = await get_mongodb()
        while not self._stop.is_set():
            job = await db.db.crawl_jobs.find_one_and_update(
                {"status": "queued", "queue_payload": {"$exists": True}},
                {"$set": {
                    "status": "running",
                    "claimed_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }},
                sort=[("queued_at", 1)],
                return_document=ReturnDocument.AFTER,
            )
            if not job:
                await asyncio.sleep(1)
                continue
            job_id = str(job["_id"])
            try:
                if not self._handler:
                    raise RuntimeError("Crawl queue handler is not configured")
                await self._handler(job_id, job["queue_payload"])
            except asyncio.CancelledError:
                await db.db.crawl_jobs.update_one(
                    {"_id": job["_id"]},
                    {"$set": {"status": "queued", "updated_at": datetime.utcnow()}},
                )
                raise
            except Exception as exc:
                logger.exception(f"Queued crawl {job_id} failed: {exc}")
                await db.update_crawl_job(job_id, status="failed", error=str(exc))


_queue = CrawlQueue()


def get_crawl_queue() -> CrawlQueue:
    return _queue
