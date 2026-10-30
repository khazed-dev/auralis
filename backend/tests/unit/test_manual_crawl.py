"""Manual crawl settings survive the API, durable queue and indexing stages."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.routes import schedule, dependencies
from app.routes.auth import require_auth
from app.services import crawler as crawler_module

JOB_ID = "507f1f77bcf86cd799439011"
SITE_ID = "crawl-site"
SITE_URL = "https://example.com"


@pytest.fixture
def crawl_dependencies(monkeypatch):
    config = {"max_pages": 80, "include_patterns": ["/old/"], "exclude_patterns": ["/private/"]}
    db = SimpleNamespace(
        get_site=AsyncMock(return_value={"site_id": SITE_ID, "url": SITE_URL, "user_id": "owner"}),
        get_crawl_schedule=AsyncMock(return_value=deepcopy(config)),
        get_running_crawl_job=AsyncMock(return_value=None),
        create_scheduled_crawl_job=AsyncMock(return_value=JOB_ID),
        get_crawl_job=AsyncMock(return_value={"status": "running", "pages_crawled": 5}),
        update_crawl_job=AsyncMock(),
        db=MagicMock(),
    )
    db.db.pages.distinct = AsyncMock(return_value=[f"{SITE_URL}/old"])
    db.db.pages.update_one = AsyncMock()
    db.db.pages.count_documents = AsyncMock(return_value=3)
    db.db.crawl_jobs.update_one = AsyncMock()
    queue = SimpleNamespace(enqueue=AsyncMock())
    for module in (schedule, dependencies):
        monkeypatch.setattr(module, "get_mongodb", AsyncMock(return_value=db))
    monkeypatch.setattr(schedule, "get_crawl_queue", lambda: queue)
    monkeypatch.setattr(schedule.settings, "INCREMENTAL_SCAN_MAX_PAGES", 500)
    monkeypatch.setattr(schedule.settings, "INCREMENTAL_MAX_NEW_PAGES", 50)
    app = FastAPI()
    app.include_router(schedule.router)
    app.dependency_overrides[require_auth] = lambda: {"_id": "owner", "role": "user"}
    return SimpleNamespace(db=db, queue=queue, app=app, config=config)


@pytest.mark.parametrize("endpoint,action", [("crawl-now", "full"), ("crawl-new", "incremental")])
async def test_explicit_options_replace_schedule_without_changing_it(crawl_dependencies, endpoint, action):
    deps = crawl_dependencies
    options = {"max_pages": 12, "max_index_pages": 3, "include_patterns": [], "exclude_patterns": ["/admin/.*"]}
    async with AsyncClient(transport=ASGITransport(app=deps.app), base_url="http://test") as client:
        response = await client.post(f"/api/sites/{SITE_ID}/{endpoint}", json=options)
    assert response.status_code == 200
    deps.queue.enqueue.assert_awaited_once_with(JOB_ID, {
        "action": action, "site_id": SITE_ID, "site_url": SITE_URL, **options,
    })
    assert deps.db.get_crawl_schedule.return_value == deps.config


@pytest.mark.parametrize("endpoint,scan,index", [("crawl-now", 80, 80), ("crawl-new", 500, 50)])
async def test_existing_callers_can_still_post_without_a_body(crawl_dependencies, endpoint, scan, index):
    deps = crawl_dependencies
    async with AsyncClient(transport=ASGITransport(app=deps.app), base_url="http://test") as client:
        response = await client.post(f"/api/sites/{SITE_ID}/{endpoint}")
    assert response.status_code == 200
    payload = deps.queue.enqueue.await_args.args[1]
    assert payload["max_pages"] == scan
    assert payload["max_index_pages"] == index
    assert payload["include_patterns"] == ["/old/"]


@pytest.mark.parametrize("options", [
    {"max_pages": 0}, {"max_pages": 1001}, {"max_pages": 1.5},
    {"max_index_pages": 0}, {"max_index_pages": 1001},
    {"max_pages": 2, "max_index_pages": 3},
    {"max_index_pages": 81}, {"include_patterns": ["["]},
    {"exclude_patterns": ["x" * 501]}, {"include_patterns": [" "]},
    {"exclude_patterns": ["/admin/"] * 51},
])
async def test_invalid_limits_and_patterns_are_rejected_before_creating_jobs(crawl_dependencies, options):
    deps = crawl_dependencies
    async with AsyncClient(transport=ASGITransport(app=deps.app), base_url="http://test") as client:
        response = await client.post(f"/api/sites/{SITE_ID}/crawl-now", json=options)
    assert response.status_code == 422
    deps.queue.enqueue.assert_not_awaited()
    deps.db.create_scheduled_crawl_job.assert_not_awaited()


@pytest.mark.parametrize("endpoint", ["crawl-now", "crawl-new"])
async def test_manual_options_do_not_bypass_site_access_or_running_job_guard(crawl_dependencies, endpoint):
    deps = crawl_dependencies
    async with AsyncClient(transport=ASGITransport(app=deps.app), base_url="http://test") as client:
        deps.app.dependency_overrides[require_auth] = lambda: {"_id": "other", "role": "user"}
        denied = await client.post(f"/api/sites/{SITE_ID}/{endpoint}", json={"max_pages": 10})
        assert denied.status_code == 403
        deps.app.dependency_overrides[require_auth] = lambda: {"_id": "owner", "role": "user"}
        deps.db.get_running_crawl_job.return_value = {"status": "queued"}
        conflict = await client.post(f"/api/sites/{SITE_ID}/{endpoint}", json={"max_pages": 10})
        assert conflict.status_code == 409
    deps.queue.enqueue.assert_not_awaited()


@pytest.mark.parametrize("incremental", [False, True])
async def test_worker_applies_index_limit_after_new_url_filter_and_tracks_both_counts(crawl_dependencies, monkeypatch, incremental):
    deps = crawl_dependencies
    pages = [{"url": f"{SITE_URL}/{suffix}"} for suffix in ("old", "one", "two", "three", "four")]
    crawler = MagicMock()
    crawler.crawl = AsyncMock(return_value=pages)
    indexer = SimpleNamespace(index_pages=AsyncMock(return_value={"indexed_pages": 2}))
    monkeypatch.setattr(schedule, "CrawlerService", lambda: crawler)
    monkeypatch.setattr(schedule, "IndexerService", lambda: indexer)
    execute = schedule._run_incremental_crawl_background if incremental else schedule._run_crawl_background
    await execute(JOB_ID, SITE_URL, SITE_ID, 12, [], ["/admin/"], max_index_pages=2)
    crawler.crawl.assert_awaited_once_with(start_url=SITE_URL, max_pages=12, include_patterns=[], exclude_patterns=["/admin/"], job_id=JOB_ID)
    expected = pages[1:3] if incremental else pages[:2]
    indexer.index_pages.assert_awaited_once_with(expected, site_id=SITE_ID, job_id=JOB_ID)
    deps.db.update_crawl_job.assert_awaited_once_with(job_id=JOB_ID, status="completed", pages_crawled=5, pages_indexed=2)
    if incremental:
        deps.db.db.pages.distinct.assert_awaited_once_with("url", {"status": "indexed", "site_id": SITE_ID})
        assert deps.db.db.crawl_jobs.update_one.await_args.args[1]["$set"]["new_pages_limit"] == 2


@pytest.mark.parametrize("incremental", [False, True])
async def test_legacy_queued_jobs_without_new_option_keep_indexing_defaults(crawl_dependencies, monkeypatch, incremental):
    pages = [{"url": f"{SITE_URL}/{i}"} for i in range(60)]
    crawler = MagicMock(crawl=AsyncMock(return_value=pages))
    indexer = SimpleNamespace(index_pages=AsyncMock(return_value={"indexed_pages": 50 if incremental else 60}))
    monkeypatch.setattr(schedule, "CrawlerService", lambda: crawler)
    monkeypatch.setattr(schedule, "IndexerService", lambda: indexer)
    execute = schedule._run_incremental_crawl_background if incremental else schedule._run_crawl_background
    await execute(JOB_ID, SITE_URL, SITE_ID, 80, [], [])
    assert len(indexer.index_pages.await_args.args[0]) == (50 if incremental else 60)


async def test_queue_preserves_options_and_charges_scanned_not_indexed_pages(crawl_dependencies, monkeypatch):
    deps = crawl_dependencies
    executor = AsyncMock()
    monkeypatch.setattr(schedule, "_run_incremental_crawl_background", executor)
    quota = AsyncMock()
    usage = AsyncMock()
    monkeypatch.setattr(schedule, "enforce_quota", quota)
    monkeypatch.setattr(schedule, "increment_usage", usage)
    await schedule.handle_queued_crawl(JOB_ID, {
        "action": "incremental", "site_id": SITE_ID, "site_url": SITE_URL,
        "max_pages": 12, "max_index_pages": 2, "include_patterns": [], "exclude_patterns": [],
    })
    assert executor.await_args.kwargs["max_index_pages"] == 2
    quota.assert_awaited_once_with(deps.db, "owner", "crawl_pages", 12)
    usage.assert_awaited_once_with(deps.db, "owner", "crawl_pages", 5)


async def test_status_exposes_live_index_count(crawl_dependencies):
    deps = crawl_dependencies
    deps.db.get_running_crawl_job.return_value = {"_id": JOB_ID, "status": "running", "pages_crawled": 12, "pages_indexed": 3}
    async with AsyncClient(transport=ASGITransport(app=deps.app), base_url="http://test") as client:
        response = await client.get(f"/api/sites/{SITE_ID}/crawl-status")
    assert response.status_code == 200
    assert response.json()["pages_indexed"] == 3


@pytest.mark.parametrize("exclude_seed", [False, True])
async def test_subsection_filter_uses_seed_for_discovery_without_indexing_it(monkeypatch, exclude_seed):
    crawler = crawler_module.CrawlerService()
    fetch = AsyncMock(side_effect=lambda _session, url: {
        "url": url, "html": '<a href="/blog/post">Post</a><a href="/admin/secret">Admin</a>',
    })
    monkeypatch.setattr(crawler, "_fetch_page", fetch)
    monkeypatch.setattr(crawler_module, "validate_public_http_url", AsyncMock(return_value=(True, None)))
    monkeypatch.setattr(crawler_module.asyncio, "sleep", AsyncMock())
    session = MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock())
    monkeypatch.setattr(crawler_module.aiohttp, "ClientSession", lambda **_kwargs: session)
    pages = await crawler.crawl(SITE_URL, max_pages=3, include_patterns=["/blog/.*"], exclude_patterns=["/admin/", "^https://example.com$"] if exclude_seed else ["/admin/"])
    assert [page["url"] for page in pages] == ([] if exclude_seed else [f"{SITE_URL}/blog/post"])
    assert fetch.await_count == (0 if exclude_seed else 2)


async def test_scan_budget_also_bounds_failed_fetches(monkeypatch):
    crawler = crawler_module.CrawlerService()
    async def fetch(_session, url):
        if url == SITE_URL:
            return {"url": url, "html": ''.join(f'<a href="/missing/{i}">Missing</a>' for i in range(20))}
        return None
    mock_fetch = AsyncMock(side_effect=fetch)
    monkeypatch.setattr(crawler, "_fetch_page", mock_fetch)
    monkeypatch.setattr(crawler_module, "validate_public_http_url", AsyncMock(return_value=(True, None)))
    monkeypatch.setattr(crawler_module.asyncio, "sleep", AsyncMock())
    session = MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock())
    monkeypatch.setattr(crawler_module.aiohttp, "ClientSession", lambda **_kwargs: session)
    await crawler.crawl(SITE_URL, max_pages=3)
    assert mock_fetch.await_count == 3


async def test_crawled_remainder_is_saved_without_downgrading_indexed_or_foreign_pages(crawl_dependencies):
    deps = crawl_dependencies
    rows = {
        (SITE_ID, f"{SITE_URL}/old"): {"status": "indexed", "content": "keep indexed"},
        ("other-site", f"{SITE_URL}/one"): {"status": "indexed", "content": "keep foreign"},
    }
    async def update(query, operation, upsert=False):
        key = (query["site_id"], query["url"])
        if "$setOnInsert" in operation:
            rows.setdefault(key, {**query, **operation["$setOnInsert"]})
        elif rows[key]["status"] != "indexed":
            rows[key].update(operation["$set"])
    deps.db.db.pages.update_one.side_effect = update
    pages = [{"url": f"{SITE_URL}/{name}", "content": name * 100, "html": "not stored", "metadata": {"site_id": "other-site"}} for name in ("old", "one", "two")]
    await schedule._store_pending_pages(deps.db, SITE_ID, pages, JOB_ID)
    assert rows[(SITE_ID, f"{SITE_URL}/old")]["content"] == "keep indexed"
    assert rows[("other-site", f"{SITE_URL}/one")]["content"] == "keep foreign"
    pending = rows[(SITE_ID, f"{SITE_URL}/one")]
    assert pending["status"] == "pending"
    assert pending["content"] == "one" * 100
    assert pending["metadata"]["site_id"] == SITE_ID
    assert "html" not in pending


@pytest.mark.parametrize("incremental", [False, True])
async def test_scan_saves_all_eligible_pages_even_when_only_one_is_indexed(crawl_dependencies, monkeypatch, incremental):
    deps = crawl_dependencies
    pages = [{"url": f"{SITE_URL}/{i}", "content": "saved text " * 20} for i in range(4)]
    monkeypatch.setattr(schedule, "CrawlerService", lambda: MagicMock(crawl=AsyncMock(return_value=pages)))
    indexer = SimpleNamespace(index_pages=AsyncMock(return_value={"indexed_pages": 1}))
    monkeypatch.setattr(schedule, "IndexerService", lambda: indexer)
    execute = schedule._run_incremental_crawl_background if incremental else schedule._run_crawl_background
    await execute(JOB_ID, SITE_URL, SITE_ID, 4, [], [], max_index_pages=1)
    created = [call.args[0]["url"] for call in deps.db.db.pages.update_one.await_args_list if "$setOnInsert" in call.args[1]]
    assert created == [page["url"] for page in pages]
    assert len(indexer.index_pages.await_args.args[0]) == 1


async def test_index_pending_endpoint_queues_scoped_job_and_reports_counts(crawl_dependencies):
    deps = crawl_dependencies
    async with AsyncClient(transport=ASGITransport(app=deps.app), base_url="http://test") as client:
        response = await client.post(f"/api/sites/{SITE_ID}/index-pending")
        status = await client.get(f"/api/sites/{SITE_ID}/index-status")
    assert response.status_code == 200
    assert response.json()["pending_pages"] == 3
    deps.queue.enqueue.assert_awaited_once_with(JOB_ID, {"action": "index_pending", "site_id": SITE_ID})
    assert status.json() == {"pending_pages": 3, "indexed_pages": 3}
    assert all(call.args[0]["site_id"] == SITE_ID for call in deps.db.db.pages.count_documents.await_args_list)


@pytest.mark.parametrize("blocked", ["empty", "running", "foreign", "unauthenticated"])
async def test_index_pending_rejects_empty_busy_or_unauthorized_requests(crawl_dependencies, blocked):
    deps = crawl_dependencies
    if blocked == "empty":
        deps.db.db.pages.count_documents.return_value = 0
    elif blocked == "running":
        deps.db.get_running_crawl_job.return_value = {"status": "running"}
    elif blocked == "foreign":
        deps.app.dependency_overrides[require_auth] = lambda: {"_id": "other", "role": "user"}
    else:
        deps.app.dependency_overrides.pop(require_auth)
    async with AsyncClient(transport=ASGITransport(app=deps.app), base_url="http://test") as client:
        response = await client.post(f"/api/sites/{SITE_ID}/index-pending")
    assert response.status_code == ({"foreign": 403, "unauthenticated": 401}.get(blocked, 409))
    deps.queue.enqueue.assert_not_awaited()


@pytest.mark.parametrize("count", [3, 1001])
async def test_pending_index_processes_all_saved_pages_without_crawling(crawl_dependencies, monkeypatch, count):
    deps = crawl_dependencies
    pages = [{"url": f"{SITE_URL}/{i}", "content": "text " * 50, "site_id": SITE_ID} for i in range(count)]
    cursor = MagicMock()
    cursor.__aiter__.return_value = pages
    cursor.close = AsyncMock()
    deps.db.db.pages.find.return_value.sort.return_value = cursor
    indexer = SimpleNamespace(index_pages=AsyncMock(return_value={"indexed_pages": 1}))
    monkeypatch.setattr(schedule, "IndexerService", lambda: indexer)
    crawler = MagicMock()
    monkeypatch.setattr(schedule, "CrawlerService", crawler)
    await schedule._run_pending_index_background(JOB_ID, SITE_ID)
    assert indexer.index_pages.await_count == count
    assert all(call.kwargs["site_id"] == SITE_ID for call in indexer.index_pages.await_args_list)
    query = deps.db.db.pages.find.call_args.args[0]
    assert query["site_id"] == SITE_ID and query["status"] == {"$ne": "indexed"}
    deps.db.update_crawl_job.assert_any_await(JOB_ID, status="completed", pages_crawled=0, pages_indexed=count)
    crawler.assert_not_called()
    cursor.close.assert_awaited_once()


@pytest.mark.parametrize("cancelled", [False, True])
async def test_pending_index_failure_and_cancel_do_not_report_success(crawl_dependencies, monkeypatch, cancelled):
    deps = crawl_dependencies
    cursor = MagicMock()
    cursor.__aiter__.return_value = [{"url": SITE_URL, "content": "text " * 50}]
    cursor.close = AsyncMock()
    deps.db.db.pages.find.return_value.sort.return_value = cursor
    if cancelled:
        deps.db.get_crawl_job.return_value = {"status": "cancelled"}
    indexer = SimpleNamespace(index_pages=AsyncMock(return_value={"indexed_pages": 0, "errors": ["embedding failed"]}))
    monkeypatch.setattr(schedule, "IndexerService", lambda: indexer)
    await schedule._run_pending_index_background(JOB_ID, SITE_ID)
    assert not any(call.kwargs.get("status") == "completed" for call in deps.db.update_crawl_job.await_args_list)
    if cancelled:
        indexer.index_pages.assert_not_awaited()
    else:
        deps.db.update_crawl_job.assert_any_await(JOB_ID, status="failed", pages_crawled=0, pages_indexed=0)
    cursor.close.assert_awaited_once()


async def test_index_only_queue_dispatch_does_not_charge_crawl_usage(crawl_dependencies, monkeypatch):
    execute = AsyncMock()
    quota = AsyncMock()
    usage = AsyncMock()
    monkeypatch.setattr(schedule, "_run_pending_index_background", execute)
    monkeypatch.setattr(schedule, "enforce_quota", quota)
    monkeypatch.setattr(schedule, "increment_usage", usage)
    await schedule.handle_queued_crawl(JOB_ID, {"action": "index_pending", "site_id": SITE_ID})
    execute.assert_awaited_once_with(JOB_ID, SITE_ID)
    quota.assert_not_awaited()
    usage.assert_not_awaited()


async def test_cancel_is_scoped_to_site_even_if_another_site_has_same_url(crawl_dependencies):
    deps = crawl_dependencies
    deps.db.db.crawl_jobs.update_many = AsyncMock(return_value=SimpleNamespace(modified_count=1))
    async with AsyncClient(transport=ASGITransport(app=deps.app), base_url="http://test") as client:
        response = await client.post(f"/api/sites/{SITE_ID}/crawl-cancel")
    assert response.status_code == 200
    query = deps.db.db.crawl_jobs.update_many.await_args.args[0]
    assert query == {"site_id": SITE_ID, "status": {"$in": ["queued", "running"]}}
