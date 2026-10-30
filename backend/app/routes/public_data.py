"""Public, read-only view of crawled pages and their FAISS chunks."""

import re
import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from app.config import settings
from app.database import get_mongodb, get_vector_store


router = APIRouter(prefix="/api/public/data", tags=["Public data"])


def _iso_datetime(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat() + ("Z" if value.tzinfo is None else "")
    return None


def _public_page(page: Dict[str, Any]) -> Dict[str, Any]:
    """Allow-list fields instead of exposing raw MongoDB documents."""
    metadata = page.get("metadata") or {}
    return {
        "url": str(page.get("url") or ""),
        "title": str(page.get("title") or "Không có tiêu đề"),
        "content_preview": str(page.get("content") or ""),
        "chunk_count": max(0, int(page.get("chunk_count") or 0)),
        "status": str(page.get("status") or "unknown"),
        "last_crawled": _iso_datetime(page.get("last_crawled")),
        "site_id": str(metadata.get("site_id") or page.get("site_id") or ""),
    }


@router.get("")
async def list_public_crawled_data(
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    search: str = Query("", max_length=100),
):
    """List sanitized crawl metadata. This endpoint intentionally has no writes."""
    mongodb = await get_mongodb()
    query: Dict[str, Any] = {"status": "indexed"}

    normalized_search = search.strip()
    if normalized_search:
        escaped = re.escape(normalized_search)
        query["$or"] = [
            {"title": {"$regex": escaped, "$options": "i"}},
            {"url": {"$regex": escaped, "$options": "i"}},
            {"content": {"$regex": escaped, "$options": "i"}},
        ]

    projection = {
        "_id": 0,
        "url": 1,
        "title": 1,
        "content": 1,
        "chunk_count": 1,
        "status": 1,
        "last_crawled": 1,
        "metadata.site_id": 1,
        "site_id": 1,
    }
    skip = (page - 1) * per_page
    total = await mongodb.db.pages.count_documents(query)
    cursor = (
        mongodb.db.pages.find(query, projection)
        .sort("last_crawled", -1)
        .skip(skip)
        .limit(per_page)
    )
    pages = await cursor.to_list(length=per_page)

    vector_store = await asyncio.to_thread(get_vector_store)
    vector_stats = await asyncio.to_thread(vector_store.get_collection_stats)
    return {
        "items": [_public_page(item) for item in pages],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_items": total,
            "total_pages": (total + per_page - 1) // per_page if total else 0,
        },
        "stats": {
            "indexed_pages": total,
            "vector_chunks": max(0, int(vector_stats.get("count", 0)) - 1),
            "embedding_model": settings.EMBEDDINGS_MODEL,
        },
    }


@router.get("/chunks")
async def list_public_page_chunks(
    url: str = Query(..., min_length=1, max_length=2048),
):
    """Return sanitized text chunks for one indexed URL."""
    mongodb = await get_mongodb()
    page = await mongodb.db.pages.find_one(
        {"url": url, "status": "indexed"},
        {"_id": 0, "url": 1, "title": 1, "chunk_count": 1},
    )
    if not page:
        raise HTTPException(status_code=404, detail="Không tìm thấy trang đã crawl")

    try:
        vector_store = await asyncio.to_thread(get_vector_store)
        documents = await asyncio.to_thread(vector_store.get_documents_by_metadata, {"url": url}, limit=200)
    except Exception as exc:
        logger.error(f"Could not read public FAISS chunks for {url}: {exc}")
        raise HTTPException(
            status_code=503,
            detail="Dữ liệu chunk tạm thời chưa khả dụng",
        ) from exc

    chunks = [
        {
            "chunk_index": int(doc.metadata.get("chunk_index", index)),
            "content": doc.page_content,
            "word_count": int(doc.metadata.get("word_count") or 0),
        }
        for index, doc in enumerate(documents)
    ]
    return {
        "url": str(page.get("url") or ""),
        "title": str(page.get("title") or "Không có tiêu đề"),
        "chunk_count": len(chunks),
        "chunks": chunks,
    }
