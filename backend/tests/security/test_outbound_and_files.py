"""Outbound and file-boundary regressions. Never contact an external service."""
import asyncio
import io
import socket
import threading
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from fastapi import BackgroundTasks, HTTPException
from langchain_core.documents import Document
from pydantic import ValidationError

from app.providers.storage.local_provider import LocalStorageProvider
from app.routes.byok import ByokUpdate
from app.services.crawler import CrawlerService
from app.services.document_processor import DocumentProcessor
from app.core.security import PublicHttpResolver, validate_public_http_url


@pytest.mark.asyncio
async def test_crawler_rejects_rebound_dns_at_connection(monkeypatch):
    received = []
    body = b"Private fixture content. " * 12

    async def fixture(reader, writer):
        received.append(await reader.readuntil(b"\r\n\r\n"))
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: "
            + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(fixture, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    answers = []

    async def rebind(host, requested_port, **_kwargs):
        assert host == "rebind.test", "Test must not resolve an external hostname"
        address = "93.184.216.34" if len(answers) < 2 else "127.0.0.1"
        answers.append(address)
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, requested_port))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", rebind)
    monkeypatch.setattr(aiohttp.connector, "DefaultResolver", aiohttp.resolver.ThreadedResolver)
    monkeypatch.setattr("app.services.crawler.settings.CRAWL_DELAY", 0)
    try:
        pages = await CrawlerService().crawl(f"http://rebind.test:{port}/internal", max_pages=1)
    finally:
        server.close()
        await server.wait_closed()
    assert answers == ["93.184.216.34", "93.184.216.34", "127.0.0.1"]
    assert received == []
    assert pages == []


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000/private", "http://localhost:8000", "http://[::1]:8000",
    "https://10.0.0.1", "https://169.254.169.254", "https://[fd00::1]",
    "https://user:password@example.com", "https://example.com/#fragment",
    "https://example.com/?override=yes", "https://example.com:0", "https://example.com:99999",
])
def test_byok_rejects_untrusted_internal_or_ambiguous_endpoints(url):
    with pytest.raises((ValidationError, ValueError)):
        ByokUpdate(provider="openai", model="fixture", api_key="fixture-key", base_url=url)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["upload", "download", "delete", "exists", "get_url", "list_files"])
async def test_local_storage_rejects_parent_traversal(tmp_path, operation):
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"fixture")
    provider = LocalStorageProvider(str(tmp_path / "storage"))
    args = (b"replaced", "../outside.txt") if operation == "upload" else ("../outside.txt",)
    with pytest.raises(ValueError):
        await getattr(provider, operation)(*args)
    assert outside.read_bytes() == b"fixture"


@pytest.mark.asyncio
async def test_local_storage_validates_folder_before_creating_it(tmp_path):
    provider = LocalStorageProvider(str(tmp_path / "storage"))
    with pytest.raises(ValueError):
        await provider.upload(b"fixture", "file.txt", folder="../unexpected")
    assert not (tmp_path / "unexpected").exists()


def office_archive(content=b"fixture", count=1):
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        for number in range(count):
            archive.writestr(f"word/document{number}.xml", content)
    return result.getvalue()


@pytest.mark.asyncio
async def test_document_rejects_expanded_archive_before_loader(monkeypatch):
    processor = DocumentProcessor()
    monkeypatch.setattr(processor, "MAX_ARCHIVE_BYTES", 1024, raising=False)
    loader = MagicMock()
    monkeypatch.setattr(processor, "_get_loader", loader)
    result = await processor.process_file(office_archive(b"x" * 2048), "fixture.docx")
    assert result["success"] is False
    loader.assert_not_called()


@pytest.mark.asyncio
async def test_upload_reads_only_limit_plus_one(monkeypatch):
    from app.routes import documents
    db = MagicMock()
    db.db.sites.find_one = AsyncMock(return_value={"site_id": "fixture", "user_id": "owner"})
    db.db.sites.update_one = AsyncMock()
    monkeypatch.setattr(documents, "get_mongodb", AsyncMock(return_value=db))
    processor = DocumentProcessor()
    monkeypatch.setattr(processor, "MAX_FILE_SIZE", 16)
    processor.process_file = AsyncMock()
    monkeypatch.setattr(documents, "get_document_processor", lambda: processor)
    upload = MagicMock(filename="fixture.txt", content_type="text/plain")
    upload.read = AsyncMock(return_value=b"x" * 17)
    result = await documents.upload_documents("fixture", BackgroundTasks(), [upload], {"_id": "owner", "role": "user"})
    upload.read.assert_awaited_once_with(17)
    processor.process_file.assert_not_awaited()
    assert result["total_uploaded"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("addresses", [
    ["127.0.0.1"], ["169.254.169.254"], ["10.0.0.1"], ["::1"],
    ["fd00::1"], ["224.0.0.1"], ["93.184.216.34", "127.0.0.1"],
])
async def test_connector_rejects_private_or_mixed_dns(addresses):
    records = [{"hostname": "fixture.test", "host": address, "port": 443,
                "family": socket.AF_INET6 if ":" in address else socket.AF_INET,
                "proto": socket.IPPROTO_TCP, "flags": socket.AI_NUMERICHOST} for address in addresses]
    with patch("aiohttp.resolver.ThreadedResolver.resolve", AsyncMock(return_value=records)):
        resolver = PublicHttpResolver()
        try:
            with pytest.raises(OSError):
                await resolver.resolve("fixture.test", 443)
        finally:
            await resolver.close()


@pytest.mark.asyncio
async def test_connector_preserves_public_dns_hostname_and_addresses():
    records = [{"hostname": "fixture.test", "host": "93.184.216.34", "port": 443,
                "family": socket.AF_INET, "proto": socket.IPPROTO_TCP,
                "flags": socket.AI_NUMERICHOST}]
    with patch("aiohttp.resolver.ThreadedResolver.resolve", AsyncMock(return_value=records)):
        resolver = PublicHttpResolver()
        try:
            assert await resolver.resolve("fixture.test", 443) == records
        finally:
            await resolver.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["https://example.test:0", "https://example.test:99999", "https://example.test:bad", "https://user:password@example.test", "https://example.test\n", "http://224.0.0.1"])
async def test_public_url_rejects_invalid_input_without_dns(url, monkeypatch):
    resolve = AsyncMock(side_effect=AssertionError("Unsafe URL must not reach DNS"))
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    valid, _ = await validate_public_http_url(url)
    assert valid is False
    resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_byok_revalidates_existing_private_config_before_request(monkeypatch):
    from app.services import byok
    session = MagicMock()
    monkeypatch.setattr(byok.aiohttp, "ClientSession", session)
    with pytest.raises(HTTPException) as exc:
        await byok.TenantLLMService("openai", "fixture", "fixture-key", "http://127.0.0.1:8123").generate("hello")
    assert exc.value.status_code == 422
    session.assert_not_called()


@pytest.mark.asyncio
async def test_byok_rejects_private_dns_before_saving(monkeypatch):
    import app.routes.byok as route
    from app.services import byok
    db = MagicMock()
    db.db.byok_configs.update_one = AsyncMock()
    monkeypatch.setattr(route, "get_mongodb", AsyncMock(return_value=db))
    monkeypatch.setattr(route, "require_custom_plan", AsyncMock())
    monkeypatch.setattr(byok, "validate_public_http_url", AsyncMock(return_value=(False, "non-public address")))
    update = ByokUpdate(provider="openai", model="fixture", api_key="fixture-key", base_url="https://private.fixture.test")
    with pytest.raises(HTTPException) as exc:
        await route.update_byok(update, {"_id": "owner", "role": "user"})
    assert exc.value.status_code == 422
    db.db.byok_configs.update_one.assert_not_awaited()


def test_only_operator_ollama_endpoint_can_be_local(monkeypatch):
    from app.services import byok
    monkeypatch.setattr(byok.settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    assert ByokUpdate(provider="ollama", model="fixture", base_url="http://127.0.0.1:11434/").base_url == "http://127.0.0.1:11434"
    for provider, url in [("openai", "http://127.0.0.1:11434"), ("ollama", "http://127.0.0.1:8000"), ("ollama", "http://localhost:11434")]:
        with pytest.raises(ValidationError):
            ByokUpdate(provider=provider, model="fixture", base_url=url)


@pytest.mark.asyncio
async def test_byok_blocks_rebound_dns_before_connecting(monkeypatch):
    from app.services.byok import TenantLLMService
    connections = []

    async def fixture(_reader, writer):
        connections.append(True)
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(fixture, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    answers = []

    async def rebind(host, requested_port, **_kwargs):
        assert host == "rebind.test"
        address = "93.184.216.34" if not answers else "127.0.0.1"
        answers.append(address)
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, requested_port))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", rebind)
    try:
        with pytest.raises(aiohttp.ClientConnectorError):
            await TenantLLMService("openai", "fixture", "fixture-key", f"https://rebind.test:{port}").generate("hello")
    finally:
        server.close()
        await server.wait_closed()
    assert answers == ["93.184.216.34", "127.0.0.1"]
    assert connections == []


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,response,expected", [
    ("openai", {"choices": [{"message": {"content": "answer"}}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}}, "answer"),
    ("anthropic", {"content": [{"type": "text", "text": "answer"}], "usage": {"input_tokens": 7, "output_tokens": 3}}, "answer"),
    ("gemini", {"candidates": [{"content": {"parts": [{"text": "answer"}]}}], "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 3}}, "answer"),
    ("ollama", {"message": {"content": "answer"}, "prompt_eval_count": 7, "eval_count": 3}, "answer"),
])
async def test_byok_preserves_provider_payloads_and_usage(monkeypatch, provider, response, expected):
    from app.services import byok
    monkeypatch.setattr(byok, "validate_public_http_url", AsyncMock(return_value=(True, None)))
    calls = []

    class Session:
        def __init__(self, **kwargs):
            self.connector = kwargs["connector"]
            assert kwargs["timeout"].total == 120
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            await self.connector.close()

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            result = MagicMock(status=200)
            result.json = AsyncMock(return_value=response)
            return result

    monkeypatch.setattr(byok.aiohttp, "ClientSession", Session)
    service = byok.TenantLLMService(provider, "fixture-model", "fixture-key", "https://api.fixture.test/base")
    assert await service.generate("hello", "system", temperature=.4, max_tokens=321) == expected
    assert (service.calls, service.input_tokens, service.output_tokens) == (1, 7, 3)
    url, kwargs = calls[0]
    assert kwargs["allow_redirects"] is False
    payload = kwargs["json"]
    if provider == "openai":
        assert url.endswith("/base/chat/completions")
        assert kwargs["headers"]["Authorization"] == "Bearer fixture-key"
        assert payload == {"model": "fixture-model", "messages": [{"role": "system", "content": "system"}, {"role": "user", "content": "hello"}], "temperature": .4, "max_tokens": 321}
    elif provider == "anthropic":
        assert url.endswith("/base/v1/messages")
        assert kwargs["headers"]["x-api-key"] == "fixture-key"
        assert payload == {"model": "fixture-model", "max_tokens": 321, "temperature": .4, "messages": [{"role": "user", "content": "hello"}], "system": "system"}
    elif provider == "gemini":
        assert url.endswith("/base/v1beta/models/fixture-model:generateContent")
        assert kwargs["headers"]["x-goog-api-key"] == "fixture-key"
        assert payload == {"contents": [{"role": "user", "parts": [{"text": "hello"}]}], "generationConfig": {"temperature": .4, "maxOutputTokens": 321}, "systemInstruction": {"parts": [{"text": "system"}]}}
    else:
        assert url.endswith("/base/api/chat")
        assert payload == {"model": "fixture-model", "messages": [{"role": "system", "content": "system"}, {"role": "user", "content": "hello"}], "stream": False, "options": {"temperature": .4, "num_predict": 321}}


@pytest.mark.asyncio
async def test_byok_does_not_follow_redirect():
    from app.services.byok import _response_json
    response = MagicMock(status=302)
    response.json = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await _response_json(response)
    assert exc.value.status_code == 502
    response.json.assert_not_awaited()


@pytest.mark.asyncio
async def test_crawler_rechecks_redirect_destination_before_request(monkeypatch):
    async def resolve(host, port, **_kwargs):
        assert host == "public.fixture.test"
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    response = MagicMock(status=302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
    session = MagicMock()
    session.get = AsyncMock(return_value=response)
    crawler = CrawlerService()
    assert await crawler._fetch_page(session, "https://public.fixture.test") is None
    session.get.assert_awaited_once_with("https://public.fixture.test", allow_redirects=False)
    response.release.assert_called_once()
    assert any("Unsafe crawl URL" in error for error in crawler.errors)


@pytest.mark.asyncio
async def test_crawler_rejects_private_literal_before_request():
    session = MagicMock()
    session.get = AsyncMock()
    assert await CrawlerService()._fetch_page(session, "http://[::1]/private") is None
    session.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_operator_ollama_endpoint_remains_usable(monkeypatch):
    from app.services import byok
    import json
    received = []

    async def fixture(reader, writer):
        header = await reader.readuntil(b"\r\n\r\n")
        length = next(int(line.split(b":", 1)[1]) for line in header.split(b"\r\n") if line.lower().startswith(b"content-length:"))
        received.append((header.split(b"\r\n")[0], json.loads(await reader.readexactly(length))))
        body = b'{"message":{"content":"local fixture"},"prompt_eval_count":2,"eval_count":3}'
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(fixture, "127.0.0.1", 0)
    base_url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    monkeypatch.setattr(byok.settings, "OLLAMA_BASE_URL", base_url)
    service = byok.TenantLLMService("ollama", "fixture-model", "", base_url)
    try:
        assert await service.generate("hello") == "local fixture"
    finally:
        server.close()
        await server.wait_closed()
    assert received == [(b"POST /api/chat HTTP/1.1", {"model": "fixture-model", "messages": [{"role": "user", "content": "hello"}], "stream": False, "options": {"temperature": .7, "num_predict": 2000}})]
    assert (service.calls, service.input_tokens, service.output_tokens) == (1, 2, 3)


@pytest.mark.asyncio
async def test_local_storage_normal_nested_operations(tmp_path):
    provider = LocalStorageProvider(str(tmp_path / "storage"))
    saved = await provider.upload(io.BytesIO(b"fixture"), "file.txt", "nested/folder")
    assert saved.key == "nested/folder/file.txt"
    assert await provider.download(saved.key) == b"fixture"
    assert await provider.exists(saved.key)
    assert await provider.get_url(saved.key) == "/storage/nested/folder/file.txt"
    assert [row.key for row in await provider.list_files("nested/folder")] == [saved.key]
    assert await provider.delete(saved.key)
    assert await provider.download(saved.key) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["/absolute.txt", "C:/absolute.txt", "nested\\file.txt", "nested/../../file.txt", "bad\x00name"])
async def test_local_storage_rejects_non_relative_keys(tmp_path, key):
    provider = LocalStorageProvider(str(tmp_path / "storage"))
    with pytest.raises(ValueError):
        await provider.upload(b"fixture", key)


@pytest.mark.asyncio
async def test_local_storage_rejects_escaping_symlinks(tmp_path):
    provider = LocalStorageProvider(str(tmp_path / "storage"))
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "fixture.txt").write_bytes(b"fixture")
    try:
        (provider.base_path / "link").symlink_to(outside, target_is_directory=True)
        (provider.base_path / "file.txt").symlink_to(outside / "fixture.txt")
    except OSError as exc:
        pytest.skip(f"Creating test symlinks is not permitted: {exc}")
    for operation in ("download", "delete", "exists", "get_url"):
        with pytest.raises(ValueError):
            await getattr(provider, operation)("file.txt")
    with pytest.raises(ValueError):
        await provider.upload(b"changed", "file.txt")
    with pytest.raises(ValueError):
        await provider.upload(b"changed", "fixture.txt", folder="link")
    with pytest.raises(ValueError):
        await provider.list_files("link")
    assert await provider.list_files() == []
    assert (outside / "fixture.txt").read_bytes() == b"fixture"


@pytest.mark.asyncio
async def test_document_rejects_excessive_archive_members(monkeypatch):
    processor = DocumentProcessor()
    monkeypatch.setattr(processor, "MAX_ARCHIVE_MEMBERS", 2)
    loader = MagicMock()
    monkeypatch.setattr(processor, "_get_loader", loader)
    result = await processor.process_file(office_archive(count=3), "fixture.docx")
    assert result["success"] is False
    assert "too many entries" in result["error"]
    loader.assert_not_called()


@pytest.mark.asyncio
async def test_document_parses_off_event_loop_and_bounds_output(monkeypatch):
    processor = DocumentProcessor()
    main_thread = threading.get_ident()
    parser_threads = []
    loader = MagicMock()

    def parse():
        parser_threads.append(threading.get_ident())
        return [Document(page_content="x" * 17)]

    loader.load.side_effect = parse
    monkeypatch.setattr(processor, "_get_loader", lambda *_args: loader)
    monkeypatch.setattr(processor, "MAX_EXTRACTED_CHARS", 16)
    result = await processor.process_file(b"fixture", "fixture.txt")
    assert parser_threads and parser_threads[0] != main_thread
    assert result["success"] is False
    assert "text is too large" in result["error"]


@pytest.mark.asyncio
async def test_document_normal_docx_and_pdf_parsing():
    from pypdf import PdfWriter
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Normal fixture document</w:t></w:r></w:p></w:body></w:document>')
    processor = DocumentProcessor()
    parsed = await processor.process_file(result.getvalue(), "normal.docx")
    assert parsed["success"] is True
    assert "Normal fixture document" in parsed["text"]
    pdf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(pdf)
    parsed_pdf = await processor.process_file(pdf.getvalue(), "normal.pdf")
    assert parsed_pdf["success"] is True
    assert parsed_pdf["metadata"]["page_count"] == 1
