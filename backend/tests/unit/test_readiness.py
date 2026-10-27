from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.routes import readiness as module


@pytest.mark.asyncio
@pytest.mark.parametrize("database_ok,vector_ok", [(True, True), (False, True), (True, False)])
async def test_readiness_requires_mongodb_and_loaded_faiss(monkeypatch, tmp_path, database_ok, vector_ok):
    (tmp_path / "COMMIT").write_text("a" * 40)
    monkeypatch.setattr(module, "__file__", str(tmp_path / "backend/app/routes/readiness.py"))
    command = AsyncMock(return_value={"ok": 1})
    if not database_ok:
        command.side_effect = RuntimeError("private connection detail")
    monkeypatch.setattr(module.mongodb, "_mongodb", SimpleNamespace(db=SimpleNamespace(command=command)))
    monkeypatch.setattr(module.vector_store, "_vector_store", SimpleNamespace(
        _initialized=vector_ok, embeddings=object(),
        vector_store=SimpleNamespace(index=SimpleNamespace(ntotal=1)),
    ))
    app = FastAPI()
    app.include_router(module.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/ready")
    assert response.status_code == (200 if database_ok and vector_ok else 503)
    assert response.json()["mongodb"] is database_ok
    assert response.json()["faiss"] is vector_ok
    assert response.json()["commit"] == "a" * 40
    assert "private connection detail" not in response.text


@pytest.mark.asyncio
async def test_readiness_does_not_initialize_missing_dependencies(monkeypatch):
    monkeypatch.setattr(module.mongodb, "_mongodb", None)
    monkeypatch.setattr(module.vector_store, "_vector_store", None)
    response = await module.readiness()
    assert response.status_code == 503
