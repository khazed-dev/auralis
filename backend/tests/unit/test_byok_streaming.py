"""Native BYOK streaming must keep the outbound guards and release connections."""
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException
import pytest

from app.services import byok


def packets(provider):
    if provider == "openai":
        return [
            {"choices": [{"delta": {"content": "Xin "}}]},
            {"choices": [{"delta": {"reasoning_content": "PRIVATE", "content": "chào"}}]},
            {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 5}},
        ]
    if provider == "anthropic":
        return [
            {"type": "message_start", "message": {"usage": {"input_tokens": 3}}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Xin "}},
            {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "PRIVATE"}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "chào"}},
            {"type": "message_delta", "usage": {"output_tokens": 5}},
            {"type": "message_stop"},
        ]
    if provider == "gemini":
        return [
            {"candidates": [{"content": {"parts": [{"thought": True, "text": "PRIVATE"}, {"text": "Xin "}]}}]},
            {"candidates": [{"content": {"parts": [{"text": "chào"}]}, "finishReason": "STOP"}], "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 5}},
        ]
    return [
        {"message": {"content": "Xin "}, "done": False},
        {"message": {"content": "chào", "thinking": "PRIVATE"}, "done": False},
        {"message": {"content": ""}, "done": True, "prompt_eval_count": 3, "eval_count": 5},
    ]


class Response:
    status = 200

    def __init__(self, provider, events):
        self.lines = []
        self.consumed = 0
        for event in events:
            value = json.dumps(event, ensure_ascii=False)
            self.lines.extend([value + "\n"] if provider == "ollama" else ["data: " + value + "\n", "\n"])
        if provider == "openai":
            self.lines += ["data: [DONE]\n", "\n"]
        self.content = self

    def raise_for_status(self):
        pass

    async def __aiter__(self):
        for line in self.lines:
            self.consumed += 1
            yield line.encode()


def install_session(monkeypatch, response):
    observed = {}
    monkeypatch.setattr(byok, "check_byok_endpoint", AsyncMock(return_value=False))

    class Session:
        def __init__(self, **options):
            observed["options"] = options

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            observed["closed"] = True
            await observed["options"]["connector"].close()

        async def post(self, url, **kwargs):
            observed["url"] = url
            observed["request"] = kwargs
            return response

    monkeypatch.setattr(byok.aiohttp, "ClientSession", Session)
    return observed


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini", "ollama"])
async def test_byok_streams_native_content_before_consuming_full_response(monkeypatch, provider):
    response = Response(provider, packets(provider))
    observed = install_session(monkeypatch, response)
    service = byok.TenantLLMService(provider, "fixture-model", "fixture-key", "https://public.example/base")
    stream = service.generate_stream("question", "system", temperature=0.4, max_tokens=321)
    assert await anext(stream) == "Xin "
    assert response.consumed < len(response.lines)
    assert service.calls == 0
    assert [part async for part in stream] == ["chào"]
    assert service.calls == 1
    assert service.input_tokens == 3
    assert service.output_tokens == 5
    assert observed["closed"]
    assert observed["options"]["trust_env"] is False
    assert observed["options"]["timeout"].total == 120
    assert isinstance(observed["options"]["connector"]._resolver, byok.PublicHttpResolver)
    assert observed["request"]["allow_redirects"] is False
    request = observed["request"]
    if provider == "openai":
        assert observed["url"].endswith("/chat/completions")
        assert request["json"]["stream"] is True
        assert request["headers"]["Authorization"] == "Bearer fixture-key"
        assert request["json"]["messages"][0] == {"role": "system", "content": "system"}
    elif provider == "anthropic":
        assert observed["url"].endswith("/v1/messages")
        assert request["json"]["stream"] is True
        assert request["json"]["system"] == "system"
        assert request["headers"]["x-api-key"] == "fixture-key"
    elif provider == "gemini":
        assert observed["url"].endswith(":streamGenerateContent?alt=sse")
        assert request["json"]["generationConfig"] == {"temperature": 0.4, "maxOutputTokens": 321}
        assert request["headers"]["x-goog-api-key"] == "fixture-key"
    else:
        assert observed["url"].endswith("/api/chat")
        assert request["json"]["stream"] is True
        assert request["json"]["options"] == {"temperature": 0.4, "num_predict": 321}


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini", "ollama"])
async def test_cancelled_byok_stream_releases_connection_without_completed_usage(monkeypatch, provider):
    observed = install_session(monkeypatch, Response(provider, packets(provider)))
    service = byok.TenantLLMService(provider, "model", "fixture-key", "https://public.example/base")
    stream = service.generate_stream("question")
    assert await anext(stream) == "Xin "
    await stream.aclose()
    assert observed["closed"]
    assert service.calls == 0


async def test_byok_stream_rejects_private_url_before_opening_session(monkeypatch):
    session = MagicMock()
    monkeypatch.setattr(byok.aiohttp, "ClientSession", session)
    service = byok.TenantLLMService("openai", "model", "fixture-key", "http://169.254.169.254")
    with pytest.raises(HTTPException) as exc:
        await anext(service.generate_stream("question"))
    assert exc.value.status_code == 422
    session.assert_not_called()


@pytest.mark.parametrize("status", [302, 307])
async def test_byok_stream_refuses_redirects(monkeypatch, status):
    response = Response("openai", [])
    response.status = status
    observed = install_session(monkeypatch, response)
    service = byok.TenantLLMService("openai", "model", "fixture-key", "https://public.example/base")
    with pytest.raises(HTTPException) as exc:
        await anext(service.generate_stream("question"))
    assert exc.value.status_code == 502
    assert response.consumed == 0
    assert observed["closed"]


async def test_upstream_error_event_does_not_count_as_a_completed_generation(monkeypatch):
    response = Response("openai", [{"error": {"message": "provider failure"}}])
    observed = install_session(monkeypatch, response)
    service = byok.TenantLLMService("openai", "model", "fixture-key", "https://public.example/base")
    with pytest.raises(HTTPException) as exc:
        await anext(service.generate_stream("question"))
    assert exc.value.status_code == 502
    assert service.calls == 0
    assert observed["closed"]


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini", "ollama"])
async def test_truncated_native_stream_is_not_saved_as_completed(monkeypatch, provider):
    first = packets(provider)[1 if provider == "anthropic" else 0]
    response = Response(provider, [first])
    if provider == "openai":
        response.lines = response.lines[:-2]
    observed = install_session(monkeypatch, response)
    service = byok.TenantLLMService(provider, "model", "fixture-key", "https://public.example/base")
    stream = service.generate_stream("question")
    assert await anext(stream) == "Xin "
    with pytest.raises(HTTPException) as exc:
        await anext(stream)
    assert exc.value.status_code == 502
    assert service.calls == 0
    assert observed["closed"]


async def test_sse_parser_joins_data_lines_and_flushes_last_event_without_blank_line():
    response = Response("openai", [])
    response.lines = [
        ": heartbeat\n", "event: message\n",
        'data: {"choices": [\n', 'data: {"delta": {"content": "Xin chào"}}]}\n', "\n",
        'data: {"usage": {"prompt_tokens": 3}}\n',
    ]
    result = [packet async for packet in byok._stream_json(response, sse=True)]
    assert result == [{"choices": [{"delta": {"content": "Xin chào"}}]}, {"usage": {"prompt_tokens": 3}}]


@pytest.mark.parametrize("oversized", [False, True])
async def test_bad_stream_data_fails_closed_and_releases_session(monkeypatch, oversized):
    response = Response("openai", [])
    response.lines = ["data: " + "x" * 600000 + "\n"] * 2 + ["\n"] if oversized else ["data: not-json\n", "\n"]
    observed = install_session(monkeypatch, response)
    service = byok.TenantLLMService("openai", "model", "fixture-key", "https://public.example/base")
    with pytest.raises(HTTPException) as exc:
        await anext(service.generate_stream("question"))
    assert exc.value.status_code == 502
    assert observed["closed"]
    assert service.calls == 0


async def test_real_local_ollama_response_yields_before_server_finishes(monkeypatch):
    release = asyncio.Event()
    finished = asyncio.Event()
    received = []

    async def fixture(reader, writer):
        try:
            header = await reader.readuntil(b"\r\n\r\n")
            size = next(int(line.split(b":", 1)[1]) for line in header.split(b"\r\n") if line.lower().startswith(b"content-length:"))
            received.append(json.loads(await reader.readexactly(size)))
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/x-ndjson\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n")

            async def send(packet):
                body = (json.dumps(packet, ensure_ascii=False) + "\n").encode()
                writer.write(f"{len(body):x}\r\n".encode() + body + b"\r\n")
                await writer.drain()

            await send({"message": {"content": "Xin "}, "done": False})
            await release.wait()
            await send({"message": {"content": "chào"}, "done": False})
            await send({"done": True, "prompt_eval_count": 3, "eval_count": 5})
            writer.write(b"0\r\n\r\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            finished.set()

    server = await asyncio.start_server(fixture, "127.0.0.1", 0)
    endpoint = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    monkeypatch.setattr(byok.settings, "OLLAMA_BASE_URL", endpoint)
    service = byok.TenantLLMService("ollama", "fixture-model", "", endpoint)
    stream = service.generate_stream("question")
    try:
        assert await asyncio.wait_for(anext(stream), 2) == "Xin "
        assert not finished.is_set()
        assert received[0]["stream"] is True
        release.set()
        assert [part async for part in stream] == ["chào"]
        assert service.calls == 1
        assert (service.input_tokens, service.output_tokens) == (3, 5)
    finally:
        release.set()
        await stream.aclose()
        server.close()
        await server.wait_closed()
        await asyncio.wait_for(finished.wait(), 2)
