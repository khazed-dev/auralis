"""Encrypted tenant BYOK configuration and per-request LLM clients."""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional
from urllib.parse import quote, urlparse

import aiohttp
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.config import settings
from app.core.security import PublicHttpResolver, _is_public_ip, validate_public_http_url
from app.services.subscriptions import get_subscription

PROVIDERS = {
    "openai": {"default_base_url": "https://api.openai.com/v1", "requires_key": True},
    "anthropic": {"default_base_url": "https://api.anthropic.com", "requires_key": True},
    "gemini": {"default_base_url": "https://generativelanguage.googleapis.com", "requires_key": True},
    "ollama": {"default_base_url": settings.OLLAMA_BASE_URL, "requires_key": False},
}


def _trusted_ollama_endpoint(provider: str, base_url: str) -> bool:
    return provider == "ollama" and base_url.rstrip("/") == settings.OLLAMA_BASE_URL.rstrip("/")


def validate_byok_base_url(provider: str, value: str) -> str:
    """Only the operator's exact Ollama endpoint may access a private network."""
    try:
        parsed = urlparse(value)
        port = parsed.port
        hostname = parsed.hostname
    except ValueError as exc:
        raise ValueError("Invalid model API URL") from exc
    if (
        parsed.scheme not in {"http", "https"} or not hostname
        or parsed.username is not None or parsed.password is not None
        or parsed.query or parsed.fragment or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ValueError("Model API URL must not contain credentials, query, fragment or an invalid port")
    normalized = value.rstrip("/")
    if _trusted_ollama_endpoint(provider, normalized):
        return normalized
    if parsed.scheme != "https":
        raise ValueError("Tenant model API endpoints must use HTTPS")
    hostname = hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise ValueError("Private network BYOK endpoints are not allowed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not _is_public_ip(str(address)):
        raise ValueError("Private network BYOK endpoints are not allowed")
    return normalized


async def check_byok_endpoint(provider: str, base_url: str) -> bool:
    """Validate stored configs again at use time, returning the trusted-local exception."""
    try:
        normalized = validate_byok_base_url(provider, base_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    trusted = _trusted_ollama_endpoint(provider, normalized)
    if not trusted:
        valid, error = await validate_public_http_url(normalized)
        if not valid:
            raise HTTPException(status_code=422, detail=f"Unsafe model API URL: {error}")
    return trusted


async def _response_json(response: aiohttp.ClientResponse) -> dict:
    response.raise_for_status()
    if not 200 <= response.status < 300:
        raise HTTPException(status_code=502, detail="Model API redirects are not allowed")
    return await response.json(content_type=None)


def _fernet() -> Fernet:
    secret = (settings.BYOK_ENCRYPTION_KEY or "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="BYOK encryption is not configured")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise HTTPException(status_code=500, detail="Unable to decrypt BYOK credential") from exc


async def require_custom_plan(db, owner_id: str) -> dict:
    subscription = await get_subscription(db, owner_id)
    features = (subscription.get("plan_snapshot") or {}).get("features") or {}
    if not features.get("byok", subscription.get("plan") == "custom") or subscription.get("status") not in {"active", "trialing"}:
        raise HTTPException(status_code=403, detail={
            "code": "custom_plan_required", "message": "BYOK requires an active Custom plan",
        })
    return subscription


async def get_byok_config(db, owner_id: str, *, decrypt: bool = False) -> Optional[dict]:
    document = await db.db.byok_configs.find_one({"owner_id": owner_id})
    if not document:
        return None
    result = dict(document)
    result.pop("_id", None)
    encrypted = result.pop("api_key_encrypted", None)
    result["has_api_key"] = bool(encrypted)
    if decrypt:
        result["api_key"] = decrypt_secret(encrypted) if encrypted else ""
    return result


class TenantLLMService:
    def __init__(self, provider: str, model: str, api_key: str, base_url: str):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def _messages(self, prompt: str, system_prompt: Optional[str]) -> list[dict]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _capture(self, usage: dict, prompt: str, answer: str) -> None:
        self.calls += 1
        self.input_tokens += int(usage.get("prompt_tokens") or usage.get("input_tokens") or max(1, len(prompt) // 4))
        self.output_tokens += int(usage.get("completion_tokens") or usage.get("output_tokens") or max(1, len(answer) // 4))

    async def generate(self, prompt: str, system_prompt: str = None, temperature: float = .7, max_tokens: int = 2000) -> str:
        trusted = await check_byok_endpoint(self.provider, self.base_url)
        connector = aiohttp.TCPConnector() if trusted else aiohttp.TCPConnector(resolver=PublicHttpResolver())
        async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=120), trust_env=False) as client:
            if self.provider == "anthropic":
                payload = {"model": self.model, "max_tokens": max_tokens, "temperature": temperature, "messages": [{"role": "user", "content": prompt}]}
                if system_prompt:
                    payload["system"] = system_prompt
                response = await client.post(f"{self.base_url}/v1/messages", headers={
                    "x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json",
                }, json=payload, allow_redirects=False)
                data = await _response_json(response)
                answer = "".join(item.get("text", "") for item in data.get("content", []) if item.get("type") == "text")
            elif self.provider == "gemini":
                contents = [{"role": "user", "parts": [{"text": prompt}]}]
                payload = {"contents": contents, "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
                if system_prompt:
                    payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
                response = await client.post(
                    f"{self.base_url}/v1beta/models/{quote(self.model, safe='')}:generateContent",
                    headers={"x-goog-api-key": self.api_key, "content-type": "application/json"},
                    json=payload,
                    allow_redirects=False,
                )
                data = await _response_json(response)
                answer = "".join(part.get("text", "") for candidate in data.get("candidates", []) for part in candidate.get("content", {}).get("parts", []))
                metadata = data.get("usageMetadata", {})
                data["usage"] = {"input_tokens": metadata.get("promptTokenCount"), "output_tokens": metadata.get("candidatesTokenCount")}
            elif self.provider == "ollama":
                response = await client.post(f"{self.base_url}/api/chat", json={
                    "model": self.model, "messages": self._messages(prompt, system_prompt), "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                }, allow_redirects=False)
                data = await _response_json(response)
                answer = data.get("message", {}).get("content", "")
                data["usage"] = {"input_tokens": data.get("prompt_eval_count"), "output_tokens": data.get("eval_count")}
            else:
                response = await client.post(f"{self.base_url}/chat/completions", headers={
                    "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                }, json={"model": self.model, "messages": self._messages(prompt, system_prompt), "temperature": temperature, "max_tokens": max_tokens}, allow_redirects=False)
                data = await _response_json(response)
                answer = data["choices"][0]["message"]["content"]
            self._capture(data.get("usage") or {}, prompt, answer)
            return answer

    async def generate_stream(self, prompt: str, system_prompt: str = None, temperature: float = .7, max_tokens: int = 2000) -> AsyncGenerator[str, None]:
        # A provider-neutral fallback keeps the RAG streaming contract correct.
        answer = await self.generate(prompt, system_prompt, temperature, max_tokens)
        yield answer


async def tenant_llm_for_site(db, site: dict) -> Optional[TenantLLMService]:
    if getattr(db, "db", None) is None:
        return None
    owner_id = str(site.get("user_id") or "")
    if not owner_id:
        return None
    subscription = await get_subscription(db, owner_id)
    if subscription.get("plan") != "custom":
        return None
    config = await get_byok_config(db, owner_id, decrypt=True)
    if not config:
        raise HTTPException(status_code=409, detail={
            "code": "byok_not_configured", "message": "Configure a model API before using chat",
        })
    if not config.get("enabled", True):
        raise HTTPException(status_code=409, detail={
            "code": "byok_disabled", "message": "The tenant model API is disabled",
        })
    return TenantLLMService(
        config["provider"], config["model"], config.get("api_key", ""),
        config.get("base_url") or PROVIDERS[config["provider"]]["default_base_url"],
    )


async def record_model_usage(db, owner_id: str, service: Optional[TenantLLMService]) -> None:
    if not service or service.calls <= 0:
        return
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    await db.db.model_usage.update_one(
        {"owner_id": owner_id, "period": period, "provider": service.provider, "model": service.model},
        {"$inc": {
            "calls": service.calls, "input_tokens": service.input_tokens,
            "output_tokens": service.output_tokens, "total_tokens": service.input_tokens + service.output_tokens,
        }, "$set": {"updated_at": datetime.now(timezone.utc)}, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
