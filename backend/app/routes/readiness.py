"""Readiness of the dependencies already loaded by application startup."""
import asyncio
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.database import mongodb, vector_store

router = APIRouter(tags=["Operations"])


@router.get("/api/ready", include_in_schema=False)
async def readiness():
    database_ready = False
    try:
        if mongodb._mongodb is not None:
            await asyncio.wait_for(mongodb._mongodb.db.command("ping"), timeout=3)
            database_ready = True
    except Exception:
        pass

    store = vector_store._vector_store
    vector_ready = False
    if store is not None and store._initialized and store.embeddings is not None and store.vector_store is not None:
        try:
            stats = await asyncio.wait_for(asyncio.to_thread(store.get_collection_stats), timeout=3)
            vector_ready = stats.get("count", 0) > 0
        except Exception:
            pass
    commit_file = Path(__file__).resolve().parents[3] / "COMMIT"
    ready = database_ready and vector_ready
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "not_ready",
            "mongodb": database_ready,
            "faiss": vector_ready,
            "commit": commit_file.read_text().strip() if commit_file.is_file() else "unknown",
        },
    )
