"""Reusable authorization dependencies for tenant-scoped routes."""
from fastapi import Depends, HTTPException, Request

from app.core.security import validate_widget_domain
from app.core.site_access import can_manage_site, can_view_site
from app.database import get_mongodb
from app.config import settings
from app.routes.auth import require_auth


async def require_site_view(
    site_id: str,
    user: dict = Depends(require_auth),
) -> dict:
    db = await get_mongodb()
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if not can_view_site(user, site):
        raise HTTPException(status_code=403, detail="Access denied")
    return user


async def require_site_manage(
    site_id: str,
    user: dict = Depends(require_auth),
) -> dict:
    db = await get_mongodb()
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if not can_manage_site(user, site):
        raise HTTPException(status_code=403, detail="Access denied")
    return user


async def require_widget_site(request: Request, site_id: str) -> dict:
    """Validate a public widget request against the site's origin policy."""
    db = await get_mongodb()
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    security = (site.get("config") or {}).get("security") or {}
    valid, error = validate_widget_domain(
        request,
        security.get("allowed_domains") or [],
        enforce_validation=bool(
            security.get("enforce_domain_validation", False)
            or (
                settings.is_production
                and settings.REQUIRE_WIDGET_DOMAIN_VALIDATION_IN_PRODUCTION
            )
        ),
        require_referrer=bool(security.get("require_referrer", False)),
    )
    if not valid:
        raise HTTPException(status_code=403, detail=error or "Widget origin is not allowed")
    return site
