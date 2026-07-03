from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.services import byok


def test_api_key_encrypts_and_decrypts(monkeypatch):
    monkeypatch.setattr(byok.settings, "BYOK_ENCRYPTION_KEY", "unit-test-secret-that-is-not-production")
    encrypted = byok.encrypt_secret("sk-secret-value")
    assert encrypted != "sk-secret-value"
    assert "sk-secret-value" not in encrypted
    assert byok.decrypt_secret(encrypted) == "sk-secret-value"


def test_wrong_encryption_key_cannot_decrypt(monkeypatch):
    monkeypatch.setattr(byok.settings, "BYOK_ENCRYPTION_KEY", "first-key")
    encrypted = byok.encrypt_secret("secret")
    monkeypatch.setattr(byok.settings, "BYOK_ENCRYPTION_KEY", "different-key")
    with pytest.raises(HTTPException) as exc:
        byok.decrypt_secret(encrypted)
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_byok_requires_custom_plan():
    provider = MagicMock()
    provider.db = MagicMock()
    provider.db.subscriptions.find_one = AsyncMock(return_value={
        "owner_id": "owner-1", "plan": "growth", "status": "active",
    })
    with pytest.raises(HTTPException) as exc:
        await byok.require_custom_plan(provider, "owner-1")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_public_config_never_exposes_encrypted_key(monkeypatch):
    monkeypatch.setattr(byok.settings, "BYOK_ENCRYPTION_KEY", "unit-test-secret")
    provider = MagicMock()
    provider.db = MagicMock()
    provider.db.byok_configs.find_one = AsyncMock(return_value={
        "owner_id": "owner-1",
        "provider": "openai",
        "model": "gpt-test",
        "api_key_encrypted": byok.encrypt_secret("sk-private"),
    })
    config = await byok.get_byok_config(provider, "owner-1")
    assert config["has_api_key"] is True
    assert "api_key" not in config
    assert "api_key_encrypted" not in config
