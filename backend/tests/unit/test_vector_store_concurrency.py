"""Real tiny FAISS indexes and controlled threads; no models or network calls."""
import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores import FAISS

from app.database import vector_store as module
from app.routes import sites, crawl, embed, schedule
from app.routes.auth import require_auth
from app.services import indexer as indexer_module
from app.services.crawler import CrawlCancelled


class ControlledEmbeddings(Embeddings):
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.fail = False
        self.thread_ids = []

    def embed_documents(self, texts):
        self.thread_ids.append(threading.get_ident())
        self.started.set()
        if not self.release.wait(3):
            raise RuntimeError("Test embedding gate timed out")
        if self.fail:
            raise RuntimeError("Embedding failed")
        return [[1.0, float(len(text) % 7)] for text in texts]

    def embed_query(self, text):
        self.thread_ids.append(threading.get_ident())
        return [1.0, 0.0]


@pytest.fixture
def store(tmp_path):
    store = module.VectorStore()
    store._initialized = True
    store.embeddings = ControlledEmbeddings()
    store.index_path = str(tmp_path / "index")
    store.vector_store = FAISS.from_embeddings(
        [("old content", [1.0, 0.0])], store.embeddings,
        metadatas=[{"site_id": "site-a", "url": "https://example.com/page"}],
    )
    store._save_index()
    return store


def documents(text="new content", site_id="site-a"):
    return [Document(page_content=text, metadata={"site_id": site_id, "url": "https://example.com/page"})]


@pytest.fixture
def database(monkeypatch, store):
    db = SimpleNamespace(
        get_site=AsyncMock(return_value={"site_id": "site-a", "url": "https://example.com", "user_id": "owner"}),
        get_crawl_job_by_url=AsyncMock(return_value=None),
        get_crawl_job=AsyncMock(return_value={"status": "running"}),
        save_page=AsyncMock(), update_crawl_job=AsyncMock(), delete_page=AsyncMock(),
    )
    for target in (sites, indexer_module):
        monkeypatch.setattr(target, "get_vector_store", lambda: store)
        monkeypatch.setattr(target, "get_mongodb", AsyncMock(return_value=db))
    return db


async def test_api_and_site_counts_respond_while_indexer_is_computing_embeddings(store, database):
    app = FastAPI()
    app.include_router(sites.router)
    app.dependency_overrides[require_auth] = lambda: {"_id": "owner", "role": "user"}
    @app.get("/ping")
    async def ping():
        return {"ok": True}

    store.embeddings.release.clear()
    page = {"url": "https://example.com/page", "title": "Page", "content": "new material " * 30}
    task = asyncio.create_task(indexer_module.IndexerService().index_pages([page], site_id="site-a"))
    try:
        assert await asyncio.to_thread(store.embeddings.started.wait, 1)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            started = time.monotonic()
            response = await asyncio.wait_for(client.get("/api/sites/site-a"), timeout=1)
            heartbeat = await asyncio.wait_for(client.get("/ping"), timeout=1)
        assert response.status_code == 200 and response.json()["total_pages"] == 1
        assert heartbeat.status_code == 200
        assert time.monotonic() - started < 1
        assert not task.done()
        assert store.get_documents_by_metadata({"site_id": "site-a"})[0].page_content == "old content"
    finally:
        store.embeddings.release.set()
        result = await task
    assert result["indexed_pages"] == 1
    assert threading.get_ident() not in store.embeddings.thread_ids


async def test_readers_wait_for_complete_replacement_not_half_updated_docstore(store, monkeypatch):
    inserted = threading.Event()
    release = threading.Event()
    original = store.vector_store.add_embeddings
    def pause_after_insertion(*args, **kwargs):
        result = original(*args, **kwargs)
        inserted.set()
        assert release.wait(3)
        return result
    monkeypatch.setattr(store.vector_store, "add_embeddings", pause_after_insertion)
    writer = asyncio.create_task(module.run_vector_write(store.replace_documents, documents(), {"site_id": "site-a"}))
    reader = None
    try:
        assert await asyncio.to_thread(inserted.wait, 1)
        reader = asyncio.create_task(asyncio.to_thread(store.get_documents_by_metadata, {"site_id": "site-a"}))
        await asyncio.sleep(0.03)
        assert not reader.done()
    finally:
        release.set()
        await writer
    assert [doc.page_content for doc in await reader] == ["new content"]


@pytest.mark.parametrize("failure", ["embedding", "insertion", "short_embeddings"])
def test_failed_preparation_preserves_previous_page_and_saved_index(store, monkeypatch, failure):
    before = (store.vector_store.index.ntotal, set(store.vector_store.docstore._dict))
    if failure == "embedding":
        store.embeddings.fail = True
    elif failure == "insertion":
        def fail(*_args, **_kwargs):
            raise RuntimeError("Insertion failed")
        monkeypatch.setattr(store.vector_store, "add_embeddings", fail)
    else:
        monkeypatch.setattr(store.embeddings, "embed_documents", lambda _texts: [])
    with pytest.raises((RuntimeError, ValueError)):
        store.replace_documents(documents(), {"site_id": "site-a"})
    assert before == (store.vector_store.index.ntotal, set(store.vector_store.docstore._dict))
    loaded = FAISS.load_local(store.index_path, store.embeddings, allow_dangerous_deserialization=True)
    assert [doc.page_content for doc in loaded.docstore._dict.values()] == ["old content"]


def test_replacement_is_scoped_idempotent_and_uses_existing_faiss_file_format(store):
    store.add_documents(documents("foreign content", site_id="site-b"))
    for _ in range(2):
        store.replace_documents(documents(), {"site_id": "site-a", "url": "https://example.com/page"})
    assert store.get_collection_stats()["count"] == 2
    assert store.get_documents_by_metadata({"site_id": "site-b"})[0].page_content == "foreign content"
    loaded = FAISS.load_local(store.index_path, store.embeddings, allow_dangerous_deserialization=True)
    assert sorted(doc.page_content for doc in loaded.docstore._dict.values()) == ["foreign content", "new content"]


def test_replacement_rejects_unscoped_filter(store):
    with pytest.raises(ValueError, match="filter"):
        store.replace_documents(documents(), {})
    assert store.get_collection_stats()["count"] == 1


async def test_cancellation_waits_for_active_write_to_finish_before_returning(store):
    store.embeddings.release.clear()
    task = asyncio.create_task(module.run_vector_write(store.replace_documents, documents(), {"site_id": "site-a"}))
    try:
        assert await asyncio.to_thread(store.embeddings.started.wait, 1)
        task.cancel()
        await asyncio.sleep(0.03)
        assert not task.done()
    finally:
        store.embeddings.release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    loaded = FAISS.load_local(store.index_path, store.embeddings, allow_dangerous_deserialization=True)
    assert [doc.page_content for doc in loaded.docstore._dict.values()] == ["new content"]


async def test_persisted_cancel_stops_indexer_before_next_page(store, database):
    state = {"status": "running"}
    database.get_crawl_job.side_effect = lambda _job_id: dict(state)
    async def save_page(**_kwargs):
        state["status"] = "cancelled"
    database.save_page.side_effect = save_page
    pages = [{"url": f"https://example.com/{i}", "title": str(i), "content": "material " * 30} for i in range(3)]
    with pytest.raises(CrawlCancelled):
        await indexer_module.IndexerService().index_pages(pages, job_id="job", site_id="site-a")
    assert database.save_page.await_count == 1
    database.update_crawl_job.assert_awaited_once_with("job", pages_indexed=1)


@pytest.mark.parametrize("operation", ["add", "delete", "clear"])
async def test_save_and_index_mutations_are_exclusive_with_readers(store, monkeypatch, operation):
    saving = threading.Event()
    release = threading.Event()
    def pause_save(*_args, **_kwargs):
        saving.set()
        assert release.wait(3)
    monkeypatch.setattr(FAISS, "save_local", pause_save)
    if operation == "add":
        write = lambda: store.add_documents(documents())
    elif operation == "delete":
        write = lambda: store.delete_by_metadata({"site_id": "site-a"})
    else:
        write = store.clear_collection
    writer = asyncio.create_task(module.run_vector_write(write))
    reader = None
    try:
        assert await asyncio.to_thread(saving.wait, 1)
        reader = asyncio.create_task(asyncio.to_thread(store.get_collection_stats))
        await asyncio.sleep(0.03)
        assert not reader.done()
    finally:
        release.set()
        await writer
    assert (await reader)["count"] == {"add": 2, "delete": 0, "clear": 1}[operation]


async def test_singleton_initialization_is_shared_across_threads(monkeypatch):
    calls = []
    class Store:
        def initialize(self):
            calls.append(threading.get_ident())
            time.sleep(0.03)
    monkeypatch.setattr(module, "_vector_store", None)
    monkeypatch.setattr(module, "VectorStore", Store)
    stores = await asyncio.gather(*(asyncio.to_thread(module.get_vector_store) for _ in range(8)))
    assert all(store is stores[0] for store in stores)
    assert len(calls) == 1


def test_failed_initialization_is_not_cached(monkeypatch):
    class Store:
        def initialize(self):
            raise RuntimeError("Model unavailable")
    monkeypatch.setattr(module, "_vector_store", None)
    monkeypatch.setattr(module, "VectorStore", Store)
    with pytest.raises(RuntimeError):
        module.get_vector_store()
    assert module._vector_store is None


async def test_same_store_initializes_model_only_once(monkeypatch, tmp_path):
    monkeypatch.setattr(module.settings, "CHROMA_PERSIST_DIR", str(tmp_path))
    calls = []
    def model(**_kwargs):
        calls.append(threading.get_ident())
        time.sleep(0.02)
        return ControlledEmbeddings()
    monkeypatch.setattr(module, "HuggingFaceEmbeddings", model)
    store = module.VectorStore()
    store.index_path = str(tmp_path / "new-index")
    await asyncio.gather(*(asyncio.to_thread(store.initialize) for _ in range(5)))
    assert len(calls) == 1
    assert store.get_collection_stats()["count"] == 1


async def test_query_and_document_embedding_share_the_model_lock(store):
    store.embeddings.release.clear()
    writer = asyncio.create_task(module.run_vector_write(store.add_documents, documents()))
    query = None
    try:
        assert await asyncio.to_thread(store.embeddings.started.wait, 1)
        query = asyncio.create_task(asyncio.to_thread(store.embed_query, "query"))
        await asyncio.sleep(0.03)
        assert not query.done()
        assert len(store.embeddings.thread_ids) == 1
    finally:
        store.embeddings.release.set()
        await writer
    assert await query == [1.0, 0.0]


@pytest.mark.parametrize("target", [crawl, embed, schedule])
async def test_background_handlers_keep_cancellation_instead_of_marking_failed(monkeypatch, database, target):
    database.create_crawl_job = AsyncMock(return_value="job")
    database.create_scheduled_crawl_job = AsyncMock(return_value="job")
    monkeypatch.setattr(target, "get_mongodb", AsyncMock(return_value=database))
    monkeypatch.setattr(target, "CrawlerService", lambda: SimpleNamespace(crawl=AsyncMock(return_value=[{"url": "https://example.com"}])))
    monkeypatch.setattr(target, "IndexerService", lambda: SimpleNamespace(index_pages=AsyncMock(side_effect=CrawlCancelled("cancelled"))))
    if target is crawl:
        await target._crawl_and_index("job", "https://example.com", 1, [], [])
    elif target is embed:
        await target.crawl_and_index_site("https://example.com", "site-a", 1)
    else:
        await target._execute_crawl_job("https://example.com", "site-a", 1, [], [])
    database.update_crawl_job.assert_not_awaited()
