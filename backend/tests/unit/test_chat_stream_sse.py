"""SSE payloads preserve multiline text without creating injected event fields."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.routes import chat


@pytest.mark.parametrize("failed", [False, True])
async def test_stream_sse_encodes_each_data_line_and_avoids_proxy_buffering(monkeypatch, failed):
    database = MagicMock()
    database.get_conversation_full = AsyncMock(return_value=None)
    monkeypatch.setattr(chat, "get_mongodb", AsyncMock(return_value=database))
    monkeypatch.setattr(chat, "_validate_widget_site", AsyncMock(return_value={"user_id": "owner"}))
    monkeypatch.setattr(chat, "tenant_llm_for_site", AsyncMock(return_value=None))
    monkeypatch.setattr(chat, "enforce_quota", AsyncMock())
    monkeypatch.setattr(chat, "increment_usage", AsyncMock())
    monkeypatch.setattr(chat, "record_model_usage", AsyncMock())
    monkeypatch.setattr(chat.limiter, "enabled", False)
    payload = "Dòng một\n\nid: injected\revent: injected\ndata: nội dung"

    async def tokens(**_kwargs):
        yield payload
        if failed:
            raise RuntimeError("provider failed\nid: error-injection")

    monkeypatch.setattr(chat, "get_rag_engine", lambda: MagicMock(chat_stream=tokens))
    app = FastAPI()
    app.include_router(chat.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/chat/stream", json={"message": "question", "session_id": "session", "site_id": "site"})
    assert response.status_code == 200
    assert response.headers["x-accel-buffering"] == "no"
    frames = response.text.split("\n\n")
    assert all(line.startswith("data: ") for frame in frames if frame for line in frame.split("\n"))
    decoded = ["\n".join(line[6:] for line in frame.split("\n")) for frame in frames if frame]
    assert decoded[0] == payload.replace("\r", "\n")
    if failed:
        assert decoded[-1].startswith("Error:")
        assert "[DONE]" not in decoded
        chat.increment_usage.assert_not_awaited()
    else:
        assert decoded[-1] == "[DONE]"
        chat.increment_usage.assert_awaited_once()
