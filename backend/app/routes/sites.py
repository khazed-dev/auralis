"""
Sites API routes for managing chatbot sites.
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional
from loguru import logger

from app.database import get_mongodb
from app.database.vector_store import get_vector_store
from app.routes.auth import require_auth, get_current_user
from app.core.site_access import can_manage_site, can_view_site, is_admin, is_agent
from app.models.schemas import SiteConfig, SiteConfigUpdate, SiteQuickPromptsConfig
from app.routes.dependencies import require_widget_site

router = APIRouter(prefix="/api/sites", tags=["sites"])


@router.get("")
async def list_sites(user: dict = Depends(require_auth)):
    """Get sites for the current user (or all sites for admin)."""
    db = await get_mongodb()

    if is_agent(user):
        ids = user.get("assigned_site_ids") or []
        sites = await db.list_sites_by_site_ids(ids) if ids else []
    elif is_admin(user):
        sites = await db.list_sites(user_id=None)
    else:
        user_id = str(user["_id"])
        sites = await db.list_sites(user_id=user_id)
    
    result = []
    try:
        vector_store = get_vector_store()
    except Exception as exc:
        logger.warning(f"Vector store unavailable while listing sites: {exc}")
        vector_store = None
    for site in sites:
        site_url = site.get("url", "")
        site_id = site.get("site_id")
        
        job = await db.get_crawl_job_by_url(site_url) if hasattr(db, 'get_crawl_job_by_url') else None
        total_pages = (
            vector_store.count_unique_metadata_values("url", {"site_id": site_id})
            if vector_store else 0
        )
        
        job_status = job.get("status") if job else site.get("status", "pending")
        result.append({
            "site_id": site_id,
            "name": site.get("name"),
            "url": site.get("url"),
            "user_id": site.get("user_id"),
            "status": job_status,
            "pages_crawled": job.get("pages_crawled", 0) if job else 0,
            "pages_indexed": job.get("pages_indexed", 0) if job else 0,
            "total_pages": total_pages,
            "created_at": site.get("created_at"),
            "error": job.get("errors", [])[-1] if job and job_status == "failed" and job.get("errors") else None
        })
    
    return result


@router.get("/{site_id}")
async def get_site(site_id: str, user: dict = Depends(require_auth)):
    """Get a specific site by ID."""
    db = await get_mongodb()
    
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    if not can_view_site(user, site):
        raise HTTPException(status_code=403, detail="Access denied")
    
    job = await db.get_crawl_job_by_url(site.get("url", "")) if hasattr(db, 'get_crawl_job_by_url') else None
    try:
        total_pages = get_vector_store().count_unique_metadata_values(
            "url", {"site_id": site_id}
        )
    except Exception as exc:
        logger.warning(f"Vector store unavailable for site {site_id}: {exc}")
        total_pages = 0
    
    return {
        "site_id": site.get("site_id"),
        "name": site.get("name"),
        "url": site.get("url"),
        "user_id": site.get("user_id"),
        "status": job.get("status") if job else site.get("status", "pending"),
        "pages_crawled": job.get("pages_crawled", 0) if job else 0,
        "pages_indexed": job.get("pages_indexed", 0) if job else 0,
        "total_pages": total_pages
    }


@router.delete("/{site_id}")
async def delete_site(site_id: str, user: dict = Depends(require_auth)):
    """Delete a site and all its data."""
    db = await get_mongodb()
    
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    if not can_manage_site(user, site):
        raise HTTPException(status_code=403, detail="Access denied")
    
    url = site.get("url")
    
    try:
        await db.delete_site(site_id)
        
        try:
            vector_store = get_vector_store()
            vector_store.delete_by_metadata({"site_id": site_id})
        except Exception as e:
            logger.warning(f"Could not delete vectors for site {url}: {e}")
        
        logger.info(f"Deleted site: {url}")
        return {"message": f"Site {site_id} deleted successfully"}
        
    except Exception as e:
        logger.error(f"Error deleting site {site_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete site")


# ==================== Site Configuration Endpoints ====================

@router.get("/{site_id}/config")
async def get_site_config(
    site_id: str,
    request: Request,
    user: Optional[dict] = Depends(get_current_user),
):
    """
    Get the configuration for a site.
    This endpoint is public as the widget needs to fetch config.
    """
    db = await get_mongodb()
    
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if user and can_manage_site(user, site):
        config_data = site.get("config", {})
        return SiteConfig(**config_data) if config_data else SiteConfig()
    await require_widget_site(request, site_id)
    
    config = SiteConfig(**(site.get("config") or {}))
    # Public widget bootstrap: explicitly allow-list client-visible fields.
    return {
        "appearance": config.appearance.model_dump(),
        "behavior": {
            "temperature": config.behavior.temperature,
            "max_tokens": config.behavior.max_tokens,
            "show_sources": config.behavior.show_sources,
        },
        "lead_capture": config.lead_capture.model_dump(),
        "quick_prompts": config.quick_prompts.model_dump(),
    }


@router.put("/{site_id}/config", response_model=SiteConfig)
async def update_site_config(
    site_id: str,
    config: SiteConfigUpdate,
    user: dict = Depends(require_auth)
):
    """Update the configuration for a site."""
    db = await get_mongodb()
    
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    if not can_manage_site(user, site):
        raise HTTPException(status_code=403, detail="Access denied")
    
    current_config = site.get("config", {})
    
    update_data = {}
    if config.appearance is not None:
        update_data["config.appearance"] = config.appearance.model_dump()
    if config.behavior is not None:
        update_data["config.behavior"] = config.behavior.model_dump()
    if config.lead_capture is not None:
        update_data["config.lead_capture"] = config.lead_capture.model_dump()
    if config.security is not None:
        update_data["config.security"] = config.security.model_dump()
    if config.quick_prompts is not None:
        update_data["config.quick_prompts"] = config.quick_prompts.model_dump()
    
    if update_data:
        # For provider interface, flatten update_data for update_site method
        merged_config = current_config.copy()
        for key, value in update_data.items():
            # key is like "config.appearance", need to extract just "appearance"
            config_key = key.replace("config.", "")
            merged_config[config_key] = value
        
        await db.update_site(site_id, {"config": merged_config})
    
    updated_site = await db.get_site(site_id)
    updated_config = updated_site.get("config", {})
    
    return SiteConfig(**updated_config) if updated_config else SiteConfig()


@router.post("/{site_id}/config/reset", response_model=SiteConfig)
async def reset_site_config(
    site_id: str,
    user: dict = Depends(require_auth)
):
    """Reset the site configuration to defaults."""
    db = await get_mongodb()
    
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    if not can_manage_site(user, site):
        raise HTTPException(status_code=403, detail="Access denied")
    
    default_config = SiteConfig()
    
    await db.update_site(site_id, {"config": default_config.model_dump()})
    
    return default_config


@router.put("/{site_id}/quick-prompts", response_model=SiteQuickPromptsConfig)
async def update_quick_prompts(
    site_id: str,
    quick_prompts: SiteQuickPromptsConfig,
    user: dict = Depends(require_auth)
):
    """Update quick prompts configuration for a site."""
    db = await get_mongodb()
    
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    if not can_manage_site(user, site):
        raise HTTPException(status_code=403, detail="Access denied")
    
    current_config = site.get("config", {})
    current_config["quick_prompts"] = quick_prompts.model_dump()
    
    await db.update_site(site_id, {"config": current_config})
    
    return quick_prompts


@router.get("/{site_id}/quick-prompts", response_model=SiteQuickPromptsConfig)
async def get_quick_prompts(site_id: str):
    """
    Get quick prompts configuration for a site.
    This endpoint is public as the widget needs to fetch config.
    """
    db = await get_mongodb()
    
    site = await db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    config_data = site.get("config", {})
    quick_prompts_data = config_data.get("quick_prompts", {})
    
    return SiteQuickPromptsConfig(**quick_prompts_data) if quick_prompts_data else SiteQuickPromptsConfig()
