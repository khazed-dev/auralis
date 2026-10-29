"""ASGI-level request guards: no real server, database or outbound requests."""
import pytest
from starlette.requests import Request
from app.core.security import RequestValidationMiddleware, get_client_ip


async def run_guard(headers=(), chunks=(b"ok",), path="/api/chat", general_limit=8, upload_limit=16):
    called = []
    sent = []
    events = [{"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1}
              for i, chunk in enumerate(chunks)]
    async def receive():
        return events.pop(0) if events else {"type": "http.disconnect"}
    async def send(message):
        sent.append(message)
    async def downstream(scope, receive, send):
        body = b""
        while True:
            message = await receive()
            if message["type"] == "http.disconnect": break
            body += message.get("body", b"")
            if not message.get("more_body", False): break
        called.append(body)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})
    middleware = RequestValidationMiddleware(downstream)
    middleware.MAX_CONTENT_LENGTH = general_limit
    middleware.MAX_UPLOAD_CONTENT_LENGTH = upload_limit
    await middleware({"type": "http", "method": "POST", "path": path, "query_string": b"",
                      "scheme": "http", "headers": list(headers), "client": ("198.51.100.4", 1234),
                      "server": ("test", 80)}, receive, send)
    return sent[0]["status"], called


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [(), ((b"transfer-encoding", b"chunked"),), ((b"content-length", b"2"),)])
async def test_actual_body_limit_applies_before_downstream(headers):
    status, called = await run_guard(headers, (b"12345", b"67890"))
    assert status == 413
    assert called == []


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [((b"content-length", b"nope"),), ((b"content-length", b"-1"),),
    ((b"content-length", b"2, 2"),), ((b"content-length", b"2"), (b"content-length", b"2")),
    ((b"content-length", b"2"), (b"transfer-encoding", b"chunked"))])
async def test_malformed_or_ambiguous_length_is_400(headers):
    status, called = await run_guard(headers)
    assert status == 400
    assert called == []


@pytest.mark.asyncio
async def test_falsely_declared_body_length_rejected_before_mutation():
    status, called = await run_guard(((b"content-length", b"1"),), (b"normal",))
    assert status == 400
    assert called == []


@pytest.mark.asyncio
async def test_valid_chunked_body_is_forwarded_exactly_once():
    status, called = await run_guard(((b"transfer-encoding", b"chunked"),), (b"ab", b"cd"))
    assert status == 200
    assert called == [b"abcd"]


@pytest.mark.asyncio
async def test_document_upload_has_a_separate_bounded_allowance():
    status, called = await run_guard((), (b"12345", b"67890"), path="/api/documents/upload/site1")
    assert status == 200
    assert called == [b"1234567890"]
    status, called = await run_guard((), (b"123456789", b"123456789"), path="/api/documents/upload/site1")
    assert status == 413
    assert called == []


@pytest.mark.asyncio
async def test_user_agent_block_and_ordinary_response_preserved():
    status, called = await run_guard(((b"user-agent", b"sqlmap"),))
    assert status == 403
    assert called == []
    status, called = await run_guard(((b"content-length", b"2"),))
    assert status == 200
    assert called == [b"ok"]


def test_forwarded_headers_cannot_rotate_rate_limit_identity():
    for forged in [b"203.0.113.1", b"203.0.113.2, 127.0.0.1"]:
        request = Request({"type": "http", "headers": [(b"x-forwarded-for", forged), (b"x-real-ip", forged)],
                           "client": ("198.51.100.4", 1234)})
        assert get_client_ip(request) == "198.51.100.4"


@pytest.mark.asyncio
async def test_too_many_headers_rejected_before_mutation():
    status, called = await run_guard(tuple((b"x-test", b"value") for _ in range(101)))
    assert status == 400
    assert called == []


@pytest.mark.asyncio
async def test_oversized_declared_length_rejected_without_downstream():
    status, called = await run_guard(((b"content-length", b"999999"),))
    assert status == 413
    assert called == []
