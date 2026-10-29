"""Regression checks for legacy chat, tenant sessions, token revocation and webhooks.

All data, LLM calls and outbound messages are isolated in memory.
"""
import hashlib
import hmac
import json
import csv
import io
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.providers.database import MockDatabaseProvider
from app.routes import auth, chat, conversations, dependencies, handoff, leads, messenger
from app.utils.csv_export import safe_csv_cell
from app.services.auth import (
    AgentUpdate, AuthService, ProfileUpdate, SiteOwnerUpdate,
    create_access_token, get_password_hash,
)


@pytest.fixture
def security_db():
    db = MockDatabaseProvider()
    now = datetime.utcnow()
    for user_id, role, assigned in [
        ("alpha", "user", []), ("beta", "user", []),
        ("agent", "agent", ["site-alpha"]), ("admin", "admin", []),
        ("platform", "platform_admin", []),
    ]:
        db.seed_user({
            "user_id": user_id, "email": f"{user_id}@example.com", "name": user_id,
            "role": role, "token_version": 0, "assigned_site_ids": assigned,
            "created_at": now,
        })
    for owner in ("alpha", "beta"):
        db.seed_site({
            "site_id": f"site-{owner}", "user_id": owner, "url": f"https://{owner}.example",
            "config": {"security": {"allowed_domains": [f"{owner}.example"], "enforce_domain_validation": True}},
        })
        db.seed_conversation({
            "session_id": f"session-{owner}", "site_id": f"site-{owner}",
            "created_at": now, "updated_at": now,
            "messages": [{"role": "assistant", "content": f"private-{owner}", "timestamp": now}],
        })
    return db


def bearer(user_id, role="user", version=0):
    token = create_access_token({"sub": user_id, "role": role, "ver": version})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def security_client(monkeypatch, security_db):
    for module in (auth, chat, conversations, dependencies, handoff, leads):
        monkeypatch.setattr(module, "get_mongodb", AsyncMock(return_value=security_db))
    for limiter in (chat.limiter, handoff.limiter, auth.limiter):
        monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(chat, "tenant_llm_for_site", AsyncMock(return_value=None))
    for name in ("enforce_quota", "increment_usage", "record_model_usage"):
        monkeypatch.setattr(chat, name, AsyncMock())
    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(chat.router)
    app.include_router(conversations.router)
    app.include_router(leads.router)
    app.include_router(handoff.router)
    app.include_router(messenger.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture") as client:
        yield client


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/chat/sessions"),
    ("GET", "/api/chat/history/session-alpha"),
    ("DELETE", "/api/chat/history/session-alpha"),
])
async def test_legacy_chat_requires_auth(security_client, security_db, method, path):
    response = await security_client.request(method, path)
    assert response.status_code == 401
    assert await security_db.get_conversation_full("session-alpha")


@pytest.mark.parametrize("user,role,expected", [
    ("alpha", "user", ["session-alpha"]),
    ("agent", "agent", ["session-alpha"]),
    ("admin", "admin", ["session-alpha", "session-beta"]),
])
async def test_session_list_is_tenant_scoped(security_client, user, role, expected):
    response = await security_client.get("/api/chat/sessions", headers=bearer(user, role))
    assert response.status_code == 200
    assert sorted(item["session_id"] for item in response.json()["sessions"]) == expected


async def test_history_read_delete_owner_and_agent_boundaries(security_client, security_db):
    own = await security_client.get("/api/chat/history/session-alpha", headers=bearer("alpha"))
    assert own.status_code == 200
    assert own.json()["messages"][0]["content"] == "private-alpha"
    for method in ("GET", "DELETE"):
        foreign = await security_client.request(method, "/api/chat/history/session-alpha", headers=bearer("beta"))
        missing = await security_client.request(method, "/api/chat/history/missing", headers=bearer("beta"))
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()
    assert (await security_client.get("/api/chat/history/session-alpha", headers=bearer("agent", "agent"))).status_code == 200
    assert (await security_client.delete("/api/chat/history/session-alpha", headers=bearer("agent", "agent"))).status_code == 404
    assert (await security_client.delete("/api/chat/history/session-alpha", headers=bearer("alpha"))).status_code == 200
    assert await security_db.get_conversation_full("session-alpha") is None
    assert await security_db.get_conversation_full("session-beta")


@pytest.mark.parametrize("endpoint", ["/api/chat", "/api/chat/stream", "/api/chat/preview"])
async def test_chat_rejects_other_site_session_before_llm(security_client, security_db, monkeypatch, endpoint):
    engine = MagicMock()
    engine.chat = AsyncMock()
    monkeypatch.setattr(chat, "get_rag_engine", MagicMock(return_value=engine))
    response = await security_client.post(endpoint, headers={**bearer("beta"), "Origin": "https://beta.example"}, json={
        "site_id": "site-beta", "session_id": "session-alpha", "message": "collision",
    })
    assert response.status_code == 409
    engine.chat.assert_not_awaited()
    chat.get_rag_engine.assert_not_called()
    assert (await security_db.get_conversation_full("session-alpha"))["site_id"] == "site-alpha"


async def test_public_chat_cannot_select_private_account_memory(security_client, monkeypatch):
    from app.models.schemas import ChatResponse
    engine = MagicMock()
    engine.chat = AsyncMock(return_value=ChatResponse(answer="safe", confidence=.9, session_id="new-alpha"))
    monkeypatch.setattr(chat, "get_rag_engine", lambda: engine)
    response = await security_client.post("/api/chat", headers={"Origin": "https://alpha.example"}, json={
        "site_id": "site-alpha", "session_id": "new-alpha", "message": "hello", "user_id": "beta",
    })
    assert response.status_code == 200
    assert engine.chat.await_args.kwargs["user_id"] is None


async def test_feedback_requires_site_origin_and_matching_session(security_client, security_db):
    security_db.add_feedback_by_index = AsyncMock(return_value=True)
    url = "/api/chat/feedback?session_id=session-alpha&message_index=0&feedback=positive"
    assert (await security_client.post(url)).status_code == 422
    assert (await security_client.post(url + "&site_id=site-alpha", headers={"Origin": "https://beta.example"})).status_code == 403
    assert (await security_client.post(url + "&site_id=site-beta", headers={"Origin": "https://beta.example"})).status_code == 404
    assert (await security_client.post(url.replace("message_index=0", "message_index=-1") + "&site_id=site-alpha")).status_code == 422
    security_db.add_feedback_by_index.assert_not_awaited()
    allowed = await security_client.post(url + "&site_id=site-alpha", headers={"Origin": "https://alpha.example"})
    assert allowed.status_code == 200
    security_db.add_feedback_by_index.assert_awaited_once_with("session-alpha", 0, "positive")


async def test_handoff_collision_does_not_disclose_or_mutate_other_site(security_client, security_db):
    security_db.get_handoff_by_session = AsyncMock(return_value={
        "handoff_id": "private-handoff", "site_id": "site-alpha", "session_id": "collision", "status": "pending",
    })
    security_db.update_handoff_visitor = AsyncMock()
    security_db.bump_handoff_visitor_requeue_pending = AsyncMock()
    security_db.get_lead_by_session = AsyncMock(return_value=None)
    response = await security_client.post("/api/handoff", headers={"Origin": "https://beta.example"}, json={
        "site_id": "site-beta", "session_id": "collision", "visitor_name": "attacker", "visitor_email": "a@example.com",
    })
    assert response.status_code == 404
    assert "private-handoff" not in response.text
    security_db.update_handoff_visitor.assert_not_awaited()
    security_db.bump_handoff_visitor_requeue_pending.assert_not_awaited()


@pytest.mark.parametrize("user,changes,status", [
    ("alpha", {"token_version": 1}, 401),
    ("alpha", {"must_change_password": True}, 403),
    ("platform", {}, 403),
])
async def test_queue_sse_uses_rest_authorization(security_client, security_db, user, changes, status):
    await security_db.update_user(user, changes)
    token = bearer(user, "platform_admin" if user == "platform" else "user")["Authorization"].split()[1]
    response = await security_client.get("/api/handoff/queue/stream", params={"token": token})
    assert response.status_code == status


async def test_open_sse_stops_after_token_revoked(security_client, security_db, monkeypatch):
    security_db.get_handoff_queue = AsyncMock(return_value=([], 0, 0, 0))
    monkeypatch.setattr(handoff.asyncio, "sleep", AsyncMock())
    request = Request({"type": "http", "method": "GET", "path": "/api/handoff/queue/stream", "headers": []})
    monkeypatch.setattr(request, "is_disconnected", AsyncMock(return_value=False))
    token = bearer("alpha")["Authorization"].split()[1]
    response = await handoff.stream_handoff_queue(request, token, site_id=None, status=None)
    iterator = response.body_iterator
    assert "handoffs" in await iterator.__anext__()
    await AuthService(security_db).revoke_refresh_token("alpha")
    assert "Unauthorized" in await iterator.__anext__()
    with pytest.raises(StopAsyncIteration):
        await iterator.__anext__()


@pytest.mark.parametrize("kind", ["self", "bootstrap", "owner_reset", "agent_reset"])
async def test_password_change_revokes_access_and_refresh(security_client, security_db, kind):
    target = "agent" if kind == "agent_reset" else "alpha"
    await security_db.update_user(target, {
        "password_hash": get_password_hash("Old-Password123!"),
        "must_change_password": kind == "bootstrap",
        "owner_id": "alpha",
    })
    service = AuthService(security_db)
    old_refresh = await service.issue_refresh_token(target)
    old_headers = bearer(target, "agent" if target == "agent" else "user")
    if kind in ("self", "bootstrap"):
        result = await security_client.patch("/api/auth/me", headers=old_headers, json={
            "current_password": "Old-Password123!", "new_password": "New-Password456!",
        })
        assert result.status_code == 200
    elif kind == "owner_reset":
        await service.update_site_owner(target, SiteOwnerUpdate(password="New-Password456!"))
    else:
        await service.update_support_agent({"_id": "alpha", "role": "user"}, target, AgentUpdate(password="New-Password456!"))
    assert (await security_client.get("/api/auth/me", headers=old_headers)).status_code == 401
    assert await service.rotate_refresh_token(target, old_refresh) is None
    assert await service.authenticate_user(f"{target}@example.com", "New-Password456!")
    login = await security_client.post("/api/auth/login", json={"email": f"{target}@example.com", "password": "New-Password456!"})
    assert login.status_code == 200
    assert (await security_client.get("/api/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})).status_code == 200


async def test_revoked_optional_auth_cannot_read_private_site_config(security_client, security_db):
    await security_db.update_user("alpha", {"token_version": 1})
    from fastapi.security import HTTPAuthorizationCredentials
    token = bearer("alpha")["Authorization"].split()[1]
    assert await auth.get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)) is None


def signed_body(secret, body):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.mark.parametrize("case", ["missing_secret", "missing_signature", "wrong_signature", "tampered_body"])
async def test_messenger_rejects_unauthenticated_events_before_side_effects(security_client, monkeypatch, case):
    secret = "fixture-app-secret"
    monkeypatch.setattr(messenger, "APP_SECRET", "" if case == "missing_secret" else secret)
    rag, send = AsyncMock(return_value="answer"), AsyncMock()
    monkeypatch.setattr(messenger, "ask_rag", rag)
    monkeypatch.setattr(messenger, "send_messenger_message", send)
    body = json.dumps({"object": "page", "entry": [{"messaging": [{"sender": {"id": "fixture"}, "message": {"text": "hello"}}]}]}).encode()
    headers = {}
    if case == "wrong_signature": headers["X-Hub-Signature-256"] = signed_body("wrong", body)
    if case == "tampered_body": headers["X-Hub-Signature-256"] = signed_body(secret, body + b" ")
    result = await security_client.post("/api/messenger/webhook", content=body, headers=headers)
    assert result.status_code == (503 if case == "missing_secret" else 401)
    rag.assert_not_awaited()
    send.assert_not_awaited()


async def test_messenger_valid_signature_and_verification(security_client, monkeypatch):
    secret = "fixture-app-secret"
    monkeypatch.setattr(messenger, "APP_SECRET", secret)
    monkeypatch.setattr(messenger, "VERIFY_TOKEN", "fixture-verify")
    rag, send = AsyncMock(return_value="answer"), AsyncMock()
    monkeypatch.setattr(messenger, "ask_rag", rag)
    monkeypatch.setattr(messenger, "send_messenger_message", send)
    body = b'{"object":"page","entry":[{"messaging":[{"sender":{"id":"fixture"},"message":{"text":"hello"}}]}]}'
    response = await security_client.post("/api/messenger/webhook", content=body, headers={"X-Hub-Signature-256": signed_body(secret, body)})
    assert response.status_code == 200
    rag.assert_awaited_once_with("hello", "fixture")
    send.assert_awaited_once_with("fixture", "answer")
    valid = {"hub.mode": "subscribe", "hub.verify_token": "fixture-verify", "hub.challenge": "12345"}
    assert (await security_client.get("/api/messenger/webhook", params=valid)).json() == 12345
    assert (await security_client.get("/api/messenger/webhook", params={**valid, "hub.challenge": "not-a-number"})).status_code == 400
    monkeypatch.setattr(messenger, "VERIFY_TOKEN", "")
    assert (await security_client.get("/api/messenger/webhook", params={**valid, "hub.verify_token": ""})).status_code == 503


@pytest.mark.parametrize("value", [
    '=HYPERLINK("https://example.com")', "+SUM(1,2)", "-1+2", "@SUM(1)",
    "\tformula", "\rformula", "\nformula", "  =1+1", "＝1+1", "＋1+1", "－1+1", "＠SUM(1)",
])
def test_csv_formula_cells_are_literal(value):
    assert safe_csv_cell(value) == "'" + value


@pytest.mark.parametrize("value", ["plain", 'Smith, "Mai"\nNormal second line', "", "Đặng An"])
def test_csv_normal_text_is_unchanged(value):
    assert safe_csv_cell(value) == value


async def test_actual_csv_exports_neutralize_untrusted_cells(security_client, security_db):
    normal = 'Smith, "Mai"\nNormal second line'
    security_db.get_all_leads_for_export = AsyncMock(return_value=[{
        "email": "safe@example.com", "name": "=1+1", "session_id": "＠SUM(1)", "source": normal,
    }])
    lead_response = await security_client.get("/api/sites/site-alpha/leads/export", headers=bearer("alpha"))
    assert lead_response.status_code == 200
    row = list(csv.reader(io.StringIO(lead_response.text)))[1]
    assert row == ["safe@example.com", "'=1+1", "", normal, "'＠SUM(1)"]
    conversation = await security_db.get_conversation_full("session-alpha")
    conversation["messages"] = [{"role": "user", "content": "+1+1", "timestamp": "now"}, {"role": "assistant", "content": normal}]
    security_db.get_conversations_for_export = AsyncMock(return_value=[conversation])
    response = await security_client.post("/api/conversations/export", headers=bearer("alpha"), json={"session_ids": ["session-alpha"], "format": "csv"})
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[1][5] == "'+1+1"
    assert rows[2][5] == normal


async def test_refresh_token_can_only_be_consumed_once_concurrently(security_db, monkeypatch):
    service = AuthService(security_db)
    token = await service.issue_refresh_token("alpha")
    original_read = security_db.get_user_by_id
    both_read = asyncio.Event()
    reads = 0

    async def simultaneous_snapshot(user_id):
        nonlocal reads
        snapshot = await original_read(user_id)
        reads += 1
        if reads == 2:
            both_read.set()
        await both_read.wait()
        return snapshot

    monkeypatch.setattr(security_db, "get_user_by_id", simultaneous_snapshot)
    results = await asyncio.gather(service.rotate_refresh_token("alpha", token), service.rotate_refresh_token("alpha", token))
    assert sum(result is not None for result in results) == 1


async def test_refresh_cannot_restore_credentials_after_racing_password_reset(security_db, monkeypatch):
    service = AuthService(security_db)
    token = await service.issue_refresh_token("alpha")
    update = security_db.update_user

    async def reset_before_rotation(user_id, updates, **kwargs):
        if "refresh_token_hash" in (kwargs.get("expected") or {}):
            await update(user_id, {"password_hash": "replacement-fixture-hash"}, revoke_sessions=True)
        return await update(user_id, updates, **kwargs)

    monkeypatch.setattr(security_db, "update_user", reset_before_rotation)
    assert await service.rotate_refresh_token("alpha", token) is None
    user = await security_db.get_user_by_id("alpha")
    assert user["token_version"] == 1
    assert "refresh_token_hash" not in user


async def test_refresh_does_not_return_new_generation_after_later_reset(security_db, monkeypatch):
    service = AuthService(security_db)
    token = await service.issue_refresh_token("alpha")
    update = security_db.update_user

    async def reset_after_rotation(user_id, updates, **kwargs):
        changed = await update(user_id, updates, **kwargs)
        if "refresh_token_hash" in (kwargs.get("expected") or {}):
            await update(user_id, {}, revoke_sessions=True)
        return changed

    monkeypatch.setattr(security_db, "update_user", reset_after_rotation)
    result = await service.rotate_refresh_token("alpha", token)
    assert result[0]["token_version"] == 0
    assert (await security_db.get_user_by_id("alpha"))["token_version"] == 1
    assert await service.get_user_by_refresh_token(result[1]) is None


async def test_login_cannot_issue_refresh_from_stale_password_snapshot(security_db):
    service = AuthService(security_db)
    snapshot = await security_db.get_user_by_id("alpha")
    await security_db.update_user("alpha", {}, revoke_sessions=True)
    with pytest.raises(ValueError, match="Authentication state changed"):
        await service.issue_refresh_token("alpha", expected_user=snapshot)


@pytest.mark.parametrize("implementation", ["legacy", "provider"])
async def test_mongo_user_update_revokes_atomically_and_compares_expected_values(implementation):
    from bson import ObjectId
    from app.database.mongodb import MongoDB
    from app.providers.database.mongodb_provider import MongoDBProvider
    instance = MongoDB() if implementation == "legacy" else MongoDBProvider()
    oid = ObjectId()
    instance.db = MagicMock()
    instance.db.users.find_one = AsyncMock(return_value={"_id": oid, "user_id": "alpha"})
    instance.db.users.update_one = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=1))
    assert await instance.update_user("alpha", {"password_hash": "replacement"}, revoke_sessions=True, expected={"refresh_token_hash": "old"})
    query, update = instance.db.users.update_one.await_args.args
    assert query == {"_id": oid, "refresh_token_hash": "old"}
    assert update["$inc"] == {"token_version": 1}
    assert "token_version" not in update["$set"]
    assert set(update["$unset"]) == {"refresh_token_hash", "refresh_expires_at"}
    assert update["$set"]["password_hash"] == "replacement"


async def test_messenger_uses_supported_rag_call_signature(monkeypatch):
    engine = MagicMock()
    engine.chat = AsyncMock(return_value={"answer": "safe-answer", "sources": []})
    monkeypatch.setattr(messenger, "get_rag_engine", lambda: engine)
    assert await messenger.ask_rag("hello", "fixture") == "safe-answer"
    engine.chat.assert_awaited_once_with(message="hello", session_id="messenger_fixture", site_id=messenger.EURO_SITE_ID)
