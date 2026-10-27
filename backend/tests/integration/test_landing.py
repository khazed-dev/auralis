"""Backend metadata and explicitly retired legacy UI routes."""

import pytest


@pytest.mark.asyncio
async def test_root_serves_backend_metadata(client):
    r = await client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "running"
    assert r.json()["widget"] == "/chatbot.js"


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/app", "/dashboard", "/login", "/landing-neo", "/data"])
async def test_legacy_ui_routes_are_retired(client, path):
    r = await client.get(path)
    assert r.status_code == 410
