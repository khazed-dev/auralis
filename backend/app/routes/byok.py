"""Tenant BYOK configuration APIs for Custom subscriptions."""
from datetime import datetime, timezone
import ipaddress
from typing import Literal, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.database import get_mongodb
from app.routes.auth import require_auth
from app.services.byok import (
    PROVIDERS, encrypt_secret, get_byok_config, require_custom_plan,
)
from app.services.subscriptions import resolve_owner_id

router = APIRouter(prefix="/api/byok", tags=["byok"])


class ByokUpdate(BaseModel):
    provider: Literal["openai", "anthropic", "gemini", "ollama"]
    model: str = Field(min_length=1, max_length=150)
    api_key: Optional[str] = Field(default=None, max_length=1000)
    base_url: Optional[str] = Field(default=None, max_length=500)
    enabled: bool = True

    @field_validator("model")
    @classmethod
    def clean_model(cls, value: str):
        return value.strip()

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: Optional[str]):
        if not value:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Base URL must be an absolute HTTP(S) URL")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Non-local BYOK endpoints must use HTTPS")
        try:
            address = ipaddress.ip_address(parsed.hostname or "")
            if (address.is_private or address.is_link_local or address.is_loopback) and parsed.hostname not in {"127.0.0.1", "::1"}:
                raise ValueError("Private network BYOK endpoints are not allowed")
        except ValueError as exc:
            if "not allowed" in str(exc):
                raise
        return value.rstrip("/")


def public_config(config: Optional[dict]) -> dict:
    if not config:
        return {"configured": False, "providers": PROVIDERS}
    return {
        "configured": True,
        "provider": config.get("provider"),
        "model": config.get("model"),
        "base_url": config.get("base_url"),
        "enabled": config.get("enabled", True),
        "has_api_key": config.get("has_api_key", False),
        "updated_at": config.get("updated_at"),
        "providers": PROVIDERS,
    }


@router.get("")
async def read_byok(user: dict = Depends(require_auth)):
    db = await get_mongodb()
    owner_id = await resolve_owner_id(db, user)
    await require_custom_plan(db, owner_id)
    return public_config(await get_byok_config(db, owner_id))


@router.put("")
async def update_byok(update: ByokUpdate, user: dict = Depends(require_auth)):
    if user.get("role") != "user":
        raise HTTPException(status_code=403, detail="Only website owners can manage BYOK")
    db = await get_mongodb()
    owner_id = str(user["_id"])
    await require_custom_plan(db, owner_id)
    existing = await db.db.byok_configs.find_one({"owner_id": owner_id}) or {}
    requires_key = PROVIDERS[update.provider]["requires_key"]
    encrypted = existing.get("api_key_encrypted")
    if update.api_key:
        encrypted = encrypt_secret(update.api_key)
    if requires_key and not encrypted:
        raise HTTPException(status_code=422, detail="API key is required for this provider")
    now = datetime.now(timezone.utc)
    document = {
        "owner_id": owner_id,
        "provider": update.provider,
        "model": update.model,
        "base_url": update.base_url or PROVIDERS[update.provider]["default_base_url"],
        "api_key_encrypted": encrypted,
        "enabled": update.enabled,
        "updated_at": now,
    }
    await db.db.byok_configs.update_one(
        {"owner_id": owner_id},
        {"$set": document, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return public_config(await get_byok_config(db, owner_id))


@router.delete("")
async def delete_byok(user: dict = Depends(require_auth)):
    if user.get("role") != "user":
        raise HTTPException(status_code=403, detail="Only website owners can manage BYOK")
    db = await get_mongodb()
    owner_id = str(user["_id"])
    await require_custom_plan(db, owner_id)
    await db.db.byok_configs.delete_one({"owner_id": owner_id})
    return {"deleted": True}


@router.get("/usage")
async def byok_usage(user: dict = Depends(require_auth)):
    db = await get_mongodb()
    owner_id = await resolve_owner_id(db, user)
    await require_custom_plan(db, owner_id)
    rows = await db.db.model_usage.find({"owner_id": owner_id}).sort(
        "period", -1
    ).to_list(length=100)
    for row in rows:
        row["id"] = str(row.pop("_id"))
    return rows
