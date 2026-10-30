"""
API routes for scheduled crawling management.
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from app.database import get_mongodb
from app.config import settings
from app.routes.dependencies import require_site_manage, require_site_view
from app.services.crawl_queue import get_crawl_queue
from app.services.crawler import CrawlerService, CrawlCancelled
from app.services.indexer import IndexerService
from app.services.scheduler import get_scheduler
from app.models.schemas import (
    CrawlScheduleConfig,
    CrawlScheduleUpdate,
    CrawlScheduleResponse,
    CrawlHistoryResponse,
    CrawlHistoryItem,
    ManualCrawlOptions,
)
from app.services.subscriptions import enforce_quota, increment_usage

router = APIRouter(tags=["Schedule"])


async def _raise_if_crawl_cancelled(db, job_id: str) -> None:
    job = await db.get_crawl_job(job_id)
    if job and job.get("status") == "cancelled":
        raise CrawlCancelled("Crawl cancelled by user")


async def handle_queued_crawl(job_id: str, payload: dict) -> None:
    """Dispatch a durable queue payload to the existing crawl executors."""
    db = await get_mongodb()
    site = await db.get_site(payload["site_id"])
    if payload.get("action") == "index_pending":
        if not site:
            raise RuntimeError("Site no longer exists")
        await _run_pending_index_background(job_id, payload["site_id"])
        return
    owner_id = str((site or {}).get("user_id") or "")
    requested_pages = int(payload.get("max_pages") or 50)
    if owner_id:
        await enforce_quota(db, owner_id, "crawl_pages", requested_pages)
    kwargs = {
        "job_id": job_id,
        "site_url": payload["site_url"],
        "site_id": payload["site_id"],
        "max_pages": int(payload.get("max_pages") or 50),
        "include_patterns": payload.get("include_patterns") or [],
        "exclude_patterns": payload.get("exclude_patterns") or [],
        "max_index_pages": payload.get("max_index_pages"),
    }
    if payload.get("action") == "incremental":
        await _run_incremental_crawl_background(**kwargs)
    else:
        await _run_crawl_background(**kwargs)
    if owner_id:
        job = await db.get_crawl_job(job_id)
        await increment_usage(db, owner_id, "crawl_pages", int((job or {}).get("pages_crawled") or 0))


async def enqueue_scheduled_crawl(
    site_url: str,
    site_id: str,
    max_pages: int,
    include_patterns: list,
    exclude_patterns: list,
    trigger: str = "scheduled",
) -> str:
    db = await get_mongodb()
    job_id = await db.create_scheduled_crawl_job(site_id, site_url, trigger)
    await get_crawl_queue().enqueue(job_id, {
        "action": "full",
        "site_url": site_url,
        "site_id": site_id,
        "max_pages": max_pages,
        "include_patterns": include_patterns,
        "exclude_patterns": exclude_patterns,
    })
    return job_id


async def _execute_crawl_job(
    site_url: str,
    site_id: str,
    max_pages: int,
    include_patterns: list,
    exclude_patterns: list,
    trigger: str = "manual"
) -> str:
    """Execute a crawl job and return job_id."""
    db = await get_mongodb()
    
    job_id = await db.create_scheduled_crawl_job(
        site_id=site_id,
        target_url=site_url,
        trigger=trigger
    )
    
    crawler = CrawlerService()
    crawler.job_id = job_id
    
    try:
        pages = await crawler.crawl(
            start_url=site_url,
            max_pages=max_pages,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            job_id=job_id,
        )
        
        if pages:
            indexer = IndexerService()
            stats = await indexer.index_pages(pages, site_id=site_id, job_id=job_id)
            indexed_count = stats.get("indexed_pages", 0)
            
            await db.update_crawl_job(
                job_id=job_id,
                status="completed",
                pages_crawled=len(pages),
                pages_indexed=indexed_count
            )
            
            from bson import ObjectId
            await db.db.crawl_jobs.update_one(
                {"_id": ObjectId(job_id)},
                {"$set": {"completed_at": datetime.utcnow()}}
            )
        else:
            await db.update_crawl_job(
                job_id=job_id,
                status="completed",
                pages_crawled=0,
                pages_indexed=0
            )
        
        logger.info(f"Crawl job {job_id} completed for site {site_id}")
        
    except CrawlCancelled:
        logger.info(f"Crawl job {job_id} cancelled")
    except Exception as e:
        logger.error(f"Crawl job {job_id} failed: {e}")
        await db.update_crawl_job(
            job_id=job_id,
            status="failed",
            error=str(e)
        )
    
    return job_id


@router.get("/api/sites/{site_id}/crawl-schedule", response_model=CrawlScheduleResponse)
async def get_crawl_schedule(
    site_id: str,
    current_user: dict = Depends(require_site_view)
):
    """Get crawl schedule configuration for a site."""
    db = await get_mongodb()
    
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    schedule_config = await db.get_crawl_schedule(site_id)
    running_job = await db.get_running_crawl_job(site_id)
    
    history = await db.get_crawl_history(site_id, limit=1)
    last_status = history[0]["status"] if history else None
    
    scheduler = get_scheduler()
    next_run = scheduler.get_next_run(site_id)
    
    if schedule_config and next_run:
        schedule_config["next_crawl_at"] = next_run
    
    return CrawlScheduleResponse(
        site_id=site_id,
        schedule=CrawlScheduleConfig(**schedule_config) if schedule_config else CrawlScheduleConfig(),
        is_crawling=running_job is not None,
        last_crawl_status=last_status
    )


@router.put("/api/sites/{site_id}/crawl-schedule", response_model=CrawlScheduleResponse)
async def update_crawl_schedule(
    site_id: str,
    update: CrawlScheduleUpdate,
    current_user: dict = Depends(require_site_manage)
):
    """Update crawl schedule configuration for a site."""
    db = await get_mongodb()
    
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    current_schedule = await db.get_crawl_schedule(site_id) or {}
    
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        current_schedule[key] = value
    
    if update.frequency == "custom" and not update.custom_cron:
        if not current_schedule.get("custom_cron"):
            raise HTTPException(
                status_code=400,
                detail="Custom cron expression required for custom frequency"
            )
    
    await db.update_crawl_schedule(site_id, current_schedule)
    
    scheduler = get_scheduler()
    site_url = site.get("url")
    
    if current_schedule.get("enabled"):
        next_run = await scheduler.add_crawl_schedule(site_id, current_schedule, site_url)
        current_schedule["next_crawl_at"] = next_run
        await db.update_crawl_schedule(site_id, current_schedule)
    else:
        scheduler.remove_crawl_schedule(site_id)
        current_schedule["next_crawl_at"] = None
        await db.update_crawl_schedule(site_id, current_schedule)
    
    running_job = await db.get_running_crawl_job(site_id)
    history = await db.get_crawl_history(site_id, limit=1)
    last_status = history[0]["status"] if history else None
    
    return CrawlScheduleResponse(
        site_id=site_id,
        schedule=CrawlScheduleConfig(**current_schedule),
        is_crawling=running_job is not None,
        last_crawl_status=last_status
    )


def _manual_crawl_options(schedule_config: dict, options: Optional[ManualCrawlOptions], incremental: bool = False) -> dict:
    options = options or ManualCrawlOptions()
    default_pages = schedule_config.get("max_pages", 50)
    if incremental:
        default_pages = max(default_pages, settings.INCREMENTAL_SCAN_MAX_PAGES)
    max_pages = options.max_pages if options.max_pages is not None else default_pages
    default_index = min(max_pages, settings.INCREMENTAL_MAX_NEW_PAGES) if incremental else max_pages
    max_index_pages = options.max_index_pages if options.max_index_pages is not None else default_index
    if max_index_pages > max_pages:
        raise HTTPException(status_code=422, detail="Số trang lập chỉ mục không được vượt số trang quét.")
    return {
        "max_pages": max_pages,
        "max_index_pages": max_index_pages,
        "include_patterns": options.include_patterns if options.include_patterns is not None else schedule_config.get("include_patterns", []),
        "exclude_patterns": options.exclude_patterns if options.exclude_patterns is not None else schedule_config.get("exclude_patterns", []),
    }


@router.post("/api/sites/{site_id}/crawl-now")
async def trigger_crawl_now(
    site_id: str,
    options: Optional[ManualCrawlOptions] = None,
    current_user: dict = Depends(require_site_manage)
):
    """Trigger an immediate crawl for a site."""
    db = await get_mongodb()
    
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    running_job = await db.get_running_crawl_job(site_id)
    if running_job:
        raise HTTPException(
            status_code=409,
            detail="A crawl is already running for this site"
        )
    
    site_url = site.get("url")
    schedule_config = await db.get_crawl_schedule(site_id) or {}
    
    crawl_options = _manual_crawl_options(schedule_config, options)
    
    job_id = await db.create_scheduled_crawl_job(
        site_id=site_id,
        target_url=site_url,
        trigger="manual"
    )
    
    await get_crawl_queue().enqueue(job_id, {
        "action": "full",
        "site_url": site_url,
        "site_id": site_id,
        **crawl_options,
    })
    
    return {
        "success": True,
        "job_id": job_id,
        "message": "Crawl started"
    }


@router.post("/api/sites/{site_id}/crawl-new")
async def trigger_incremental_crawl(
    site_id: str,
    options: Optional[ManualCrawlOptions] = None,
    current_user: dict = Depends(require_site_manage)
):
    """Crawl the site but index only URLs that are not already stored."""
    db = await get_mongodb()
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    running_job = await db.get_running_crawl_job(site_id)
    if running_job:
        raise HTTPException(
            status_code=409,
            detail="A crawl is already running for this site"
        )

    schedule_config = await db.get_crawl_schedule(site_id) or {}
    crawl_options = _manual_crawl_options(schedule_config, options, incremental=True)
    job_id = await db.create_scheduled_crawl_job(
        site_id=site_id,
        target_url=site.get("url"),
        trigger="incremental"
    )
    await get_crawl_queue().enqueue(job_id, {
        "action": "incremental",
        "site_url": site.get("url"),
        "site_id": site_id,
        **crawl_options,
    })
    return {
        "success": True,
        "job_id": job_id,
        "message": "Incremental crawl started"
    }


async def _run_incremental_crawl_background(
    job_id: str,
    site_url: str,
    site_id: str,
    max_pages: int,
    include_patterns: list,
    exclude_patterns: list,
    max_index_pages: Optional[int] = None,
):
    """Discover all in-scope pages and index only URLs not seen before."""
    from bson import ObjectId

    db = await get_mongodb()
    crawler = CrawlerService()
    crawler.job_id = job_id

    try:
        pages = await crawler.crawl(
            start_url=site_url,
            max_pages=max_pages,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            job_id=job_id,
        )
        if not pages:
            errors = crawler.get_stats().get("error_messages") or []
            raise RuntimeError(errors[0] if errors else "Crawler returned no pages")
        await _raise_if_crawl_cancelled(db, job_id)

        # URL is the stable page identity in the current schema. Reading the
        # existing set does not mutate MongoDB or FAISS.
        existing_urls = set(
            await db.db.pages.distinct(
                "url",
                {"status": "indexed", "site_id": site_id},
            )
        )
        discovered_new_pages = [
            page for page in (pages or [])
            if page.get("url") and page["url"] not in existing_urls
        ]
        await _store_pending_pages(db, site_id, discovered_new_pages, job_id)
        index_limit = max_index_pages if max_index_pages is not None else settings.INCREMENTAL_MAX_NEW_PAGES
        new_pages = discovered_new_pages[:index_limit]

        indexed_count = 0
        if new_pages:
            indexer = IndexerService()
            stats = await indexer.index_pages(new_pages, site_id=site_id, job_id=job_id)
            indexed_count = stats.get("indexed_pages", 0)

        await _raise_if_crawl_cancelled(db, job_id)
        await db.update_crawl_job(
            job_id=job_id,
            status="completed",
            pages_crawled=len(pages) if pages else 0,
            pages_indexed=indexed_count
        )
        await db.db.crawl_jobs.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {
                "completed_at": datetime.utcnow(),
                "pages_discovered": len(pages) if pages else 0,
                "new_pages_found": len(discovered_new_pages),
                "new_pages_indexed": indexed_count,
                "new_pages_limit": index_limit
            }}
        )
        logger.info(
            f"Incremental crawl {job_id} completed for {site_id}: "
            f"{len(pages) if pages else 0} scanned, "
            f"{len(discovered_new_pages)} new, {indexed_count} indexed"
        )
    except CrawlCancelled:
        logger.info(f"Incremental crawl job {job_id} cancelled")
    except Exception as e:
        logger.error(f"Incremental crawl job {job_id} failed: {e}")
        await db.update_crawl_job(
            job_id=job_id,
            status="failed",
            error=str(e)
        )


async def _run_crawl_background(
    job_id: str,
    site_url: str,
    site_id: str,
    max_pages: int,
    include_patterns: list,
    exclude_patterns: list,
    max_index_pages: Optional[int] = None,
):
    """Background task to run the crawl."""
    from bson import ObjectId
    
    db = await get_mongodb()
    crawler = CrawlerService()
    crawler.job_id = job_id
    
    try:
        pages = await crawler.crawl(
            start_url=site_url,
            max_pages=max_pages,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            job_id=job_id,
        )
        if not pages:
            errors = crawler.get_stats().get("error_messages") or []
            raise RuntimeError(errors[0] if errors else "Crawler returned no pages")
        await _raise_if_crawl_cancelled(db, job_id)
        
        indexed_count = 0
        if pages:
            indexer = IndexerService()
            await _store_pending_pages(db, site_id, pages, job_id)
            index_pages = pages[:max_index_pages] if max_index_pages is not None else pages
            stats = await indexer.index_pages(index_pages, site_id=site_id, job_id=job_id)
            indexed_count = stats.get("indexed_pages", 0)
        
        await _raise_if_crawl_cancelled(db, job_id)
        await db.update_crawl_job(
            job_id=job_id,
            status="completed",
            pages_crawled=len(pages) if pages else 0,
            pages_indexed=indexed_count
        )
        
        await db.db.crawl_jobs.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {"completed_at": datetime.utcnow()}}
        )
        
        logger.info(f"Manual crawl job {job_id} completed for site {site_id}")
        
    except CrawlCancelled:
        logger.info(f"Manual crawl job {job_id} cancelled")
    except Exception as e:
        logger.error(f"Manual crawl job {job_id} failed: {e}")
        await db.update_crawl_job(
            job_id=job_id,
            status="failed",
            error=str(e)
        )


def _pending_pages_filter(site_id: str) -> dict:
    return {"site_id": site_id, "status": {"$ne": "indexed"}, "content": {"$type": "string", "$ne": ""}}


async def _store_pending_pages(db, site_id: str, pages: list, job_id: str) -> None:
    """Keep unindexed crawl content without replacing an existing indexed page."""
    for page in pages:
        if not page.get("url") or len(page.get("content") or "") < 50:
            continue
        await _raise_if_crawl_cancelled(db, job_id)
        identity = {"site_id": site_id, "url": page["url"]}
        fields = {
            "title": page.get("title") or "",
            "content": page["content"],
            "metadata": {**(page.get("metadata") or {}), "site_id": site_id},
            "status": "pending",
            "chunk_count": 0,
            "last_crawled": datetime.utcnow(),
        }
        # First create a missing row, then update only rows still unindexed.
        # The conditional update also protects a page indexed concurrently.
        await db.db.pages.update_one(identity, {"$setOnInsert": {**fields, "created_at": datetime.utcnow()}}, upsert=True)
        await db.db.pages.update_one({**identity, "status": {"$ne": "indexed"}}, {"$set": fields})


@router.get("/api/sites/{site_id}/index-status")
async def get_index_status(site_id: str, current_user: dict = Depends(require_site_view)):
    db = await get_mongodb()
    pending = await db.db.pages.count_documents(_pending_pages_filter(site_id))
    indexed = await db.db.pages.count_documents({"site_id": site_id, "status": "indexed"})
    return {"pending_pages": pending, "indexed_pages": indexed}


@router.post("/api/sites/{site_id}/index-pending")
async def index_pending_pages(site_id: str, current_user: dict = Depends(require_site_manage)):
    db = await get_mongodb()
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if await db.get_running_crawl_job(site_id):
        raise HTTPException(status_code=409, detail="Website đang có tác vụ chạy. Hãy chờ hoàn tất hoặc dừng tác vụ.")
    count = await db.db.pages.count_documents(_pending_pages_filter(site_id))
    if not count:
        raise HTTPException(status_code=409, detail="Không có trang nào đang chờ lập chỉ mục.")
    job_id = await db.create_scheduled_crawl_job(site_id, site["url"], "index_pending")
    await get_crawl_queue().enqueue(job_id, {"action": "index_pending", "site_id": site_id})
    return {"success": True, "job_id": job_id, "pending_pages": count}


async def _run_pending_index_background(job_id: str, site_id: str) -> None:
    """Index saved pages only; no HTTP crawl and no second crawl usage charge."""
    from bson import ObjectId

    db = await get_mongodb()
    indexed_count = 0
    failed = False
    cursor = db.db.pages.find(_pending_pages_filter(site_id)).sort("_id", 1)
    try:
        indexer = IndexerService()
        async for page in cursor:
            await _raise_if_crawl_cancelled(db, job_id)
            stats = await indexer.index_pages([page], site_id=site_id)
            indexed_count += stats.get("indexed_pages", 0)
            if not stats.get("indexed_pages"):
                failed = True
                errors = stats.get("errors") or [f"Không thể lập chỉ mục: {page.get('url', '')}"]
                for error in errors:
                    await db.update_crawl_job(job_id, error=error)
            await db.update_crawl_job(job_id, pages_indexed=indexed_count)
        await _raise_if_crawl_cancelled(db, job_id)
        await db.update_crawl_job(job_id, status="failed" if failed else "completed", pages_crawled=0, pages_indexed=indexed_count)
        await db.db.crawl_jobs.update_one({"_id": ObjectId(job_id)}, {"$set": {"completed_at": datetime.utcnow()}})
    except CrawlCancelled:
        logger.info(f"Pending index job {job_id} cancelled")
    except Exception as exc:
        logger.exception(f"Pending index job {job_id} failed")
        await db.update_crawl_job(job_id, status="failed", error=str(exc))
    finally:
        await cursor.close()


@router.get("/api/sites/{site_id}/crawl-history", response_model=CrawlHistoryResponse)
async def get_crawl_history(
    site_id: str,
    limit: int = 10,
    current_user: dict = Depends(require_site_view)
):
    """Get crawl history for a site."""
    db = await get_mongodb()
    
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    history = await db.get_crawl_history(site_id, limit=limit)
    
    history_items = [CrawlHistoryItem(**item) for item in history]
    
    return CrawlHistoryResponse(
        site_id=site_id,
        history=history_items,
        total=len(history_items)
    )


@router.get("/api/sites/{site_id}/crawl-status")
async def get_crawl_status(
    site_id: str,
    current_user: dict = Depends(require_site_view)
):
    """Get current crawl status for a site."""
    db = await get_mongodb()
    
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    running_job = await db.get_running_crawl_job(site_id)
    
    if running_job:
        return {
            "is_crawling": True,
            "job_id": running_job.get("_id"),
            "status": running_job.get("status"),
            "pages_crawled": running_job.get("pages_crawled", 0),
            "pages_indexed": running_job.get("pages_indexed", 0),
            "trigger": running_job.get("trigger", "manual"),
            "started_at": running_job.get("created_at")
        }
    
    history = await db.get_crawl_history(site_id, limit=1)
    last_job = history[0] if history else None
    
    return {
        "is_crawling": False,
        "last_crawl": last_job
    }


@router.post("/api/sites/{site_id}/crawl-cancel")
async def cancel_site_crawl(
    site_id: str,
    current_user: dict = Depends(require_site_manage),
):
    """Cancel queued/running crawl jobs for one site."""
    db = await get_mongodb()
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    now = datetime.utcnow()
    result = await db.db.crawl_jobs.update_many(
        {
            "site_id": site_id,
            "status": {"$in": ["queued", "running"]},
        },
        {
            "$set": {
                "status": "cancelled",
                "updated_at": now,
                "completed_at": now,
            },
            "$unset": {"queue_payload": ""},
            "$push": {"errors": "Cancelled by user"},
        },
    )
    return {
        "success": True,
        "cancelled_jobs": result.modified_count,
        "message": (
            "Crawl cancellation requested"
            if result.modified_count
            else "No active crawl job"
        ),
    }
