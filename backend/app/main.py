"""
Auralis AI - FastAPI Application

A production-ready RAG chatbot platform with configurable providers.

Provider Architecture:
- LLM: Ollama, OpenAI, Anthropic, Azure (via LangChain)
- Embeddings: HuggingFace, OpenAI, Ollama (via LangChain)
- Vector Store: FAISS, Chroma, Pinecone, Qdrant (via LangChain)
- Database: MongoDB (extensible to PostgreSQL)
- Storage: Local (extensible to S3, GCS)
- Cache: Memory (extensible to Redis)
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from datetime import datetime
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from loguru import logger
import sys
import os

from app.config import settings
from app.database import get_mongodb, get_vector_store
from app.core.security import (
    SecurityHeadersMiddleware,
    RequestValidationMiddleware,
    log_security_warnings,
    get_client_ip
)
from app.routes import chat_router, crawl_router, admin_router, analytics_router, conversations_router, triggers_router, handoff_router, platform_router
from app.routes.embed import router as embed_router
from app.routes.sites import router as sites_router
from app.routes.auth import router as auth_router
from app.routes.documents import router as documents_router
from app.routes.schedule import router as schedule_router
from app.routes.qa import router as qa_router
from app.routes.leads import router as leads_router
from app.routes.messenger import router as messenger_router
from app.routes.public_data import router as public_data_router
from app.services.auth import AuthService
from app.services.scheduler import get_scheduler
from app.services.crawl_queue import get_crawl_queue


# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)
logger.add(
    "logs/app.log",
    rotation="10 MB",
    retention="7 days",
    level="DEBUG"
)


# Rate limiter - use get_client_ip for proper proxy support
limiter = Limiter(key_func=get_client_ip)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME}...")
    logger.info("=" * 50)
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug Mode: {settings.DEBUG}")
    logger.info("=" * 50)
    
    # Security checks
    log_security_warnings()
    
    logger.info("Provider Configuration:")
    logger.info(f"  LLM Provider: {settings.LLM_PROVIDER} ({settings.LLM_MODEL})")
    logger.info(f"  Embeddings Provider: {settings.EMBEDDINGS_PROVIDER} ({settings.EMBEDDINGS_MODEL})")
    logger.info(f"  Vector Store Provider: {settings.VECTOR_STORE_PROVIDER}")
    logger.info(f"  Database Provider: {settings.DATABASE_PROVIDER}")
    logger.info(f"  Storage Provider: {settings.STORAGE_PROVIDER}")
    logger.info(f"  Cache Provider: {settings.CACHE_PROVIDER}")
    logger.info("=" * 50)
    
    try:
        # Initialize MongoDB
        mongodb = await get_mongodb()
        logger.info("MongoDB connected")
        if (
            settings.is_production
            and settings.REQUIRE_WIDGET_DOMAIN_VALIDATION_IN_PRODUCTION
        ):
            from app.core.security import extract_domain_from_url
            cursor = mongodb.db.sites.find(
                {"$or": [
                    {"config.security.allowed_domains": {"$exists": False}},
                    {"config.security.allowed_domains": []},
                ]},
                {"site_id": 1, "url": 1},
            )
            migrated = 0
            async for site in cursor:
                domain = extract_domain_from_url(site.get("url", ""))
                if not domain:
                    continue
                await mongodb.db.sites.update_one(
                    {"_id": site["_id"]},
                    {"$set": {
                        "config.security.allowed_domains": [domain, f"*.{domain}"],
                        "updated_at": datetime.utcnow(),
                    }},
                )
                migrated += 1
            if migrated:
                logger.info(f"Backfilled widget domain allow-list for {migrated} sites")
        
        # Initialize Vector Store
        get_vector_store()
        logger.info("Vector store initialized")
        
        # Ensure default admin exists (if configured)
        auth_service = AuthService(mongodb)
        await auth_service.ensure_admin_exists()
        
        # Initialize and start the scheduler
        from app.routes.schedule import enqueue_scheduled_crawl, handle_queued_crawl
        crawl_queue = get_crawl_queue()
        crawl_queue.set_handler(handle_queued_crawl)
        await crawl_queue.start()
        logger.info("Durable crawl queue started")
        scheduler = get_scheduler()
        scheduler.set_dependencies(mongodb, enqueue_scheduled_crawl)
        await scheduler.start()
        logger.info("Crawl scheduler started")
        
        logger.info(f"{settings.APP_NAME} started successfully!")
        
    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info(f"Shutting down {settings.APP_NAME}...")
    
    try:
        # Shutdown scheduler first
        scheduler = get_scheduler()
        scheduler.shutdown()
        logger.info("Crawl scheduler stopped")
        await get_crawl_queue().stop()
        logger.info("Durable crawl queue stopped")
        
        mongodb = await get_mongodb()
        await mongodb.disconnect()
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="A production-ready RAG chatbot for your website",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Security middleware (order matters - outermost first)
# 1. Security headers
app.add_middleware(SecurityHeadersMiddleware)

# 2. Request validation
app.add_middleware(RequestValidationMiddleware)

# 3. Trusted host middleware (only in production)
if settings.is_production and settings.TRUSTED_HOSTS != "*":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.trusted_hosts_list
    )

# 4. CORS middleware - using configurable origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "Accept", "Origin"],
    expose_headers=["X-Total-Count", "X-Page", "X-Per-Page"],
)

# Include routers
app.include_router(auth_router)
app.include_router(chat_router)
if settings.ENABLE_LEGACY_CRAWL_API:
    app.include_router(crawl_router)
app.include_router(admin_router)
app.include_router(analytics_router)
app.include_router(conversations_router)
app.include_router(triggers_router)
app.include_router(handoff_router)
app.include_router(platform_router)
app.include_router(embed_router)
app.include_router(sites_router)
app.include_router(documents_router)
app.include_router(schedule_router)
app.include_router(qa_router)
app.include_router(leads_router)
app.include_router(messenger_router)
if settings.ENABLE_PUBLIC_DATA_EXPLORER:
    app.include_router(public_data_router)
# Serve the independently built embeddable widget.
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
project_root = os.path.dirname(backend_dir)
widget_dist_path = os.path.join(project_root, "widget", "dist")

if os.path.exists(widget_dist_path):
    app.mount("/widget", StaticFiles(directory=widget_dist_path), name="widget")
else:
    logger.warning(f"Widget build directory not found: {widget_dist_path}")


@app.get("/chatbot.js", include_in_schema=False)
async def chatbot_script():
    """Serve the widget at a stable, brand-neutral root URL."""
    path = os.path.join(widget_dist_path, "chatbot.js")
    if os.path.exists(path):
        return FileResponse(path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="Widget script not found")


@app.get("/")
async def root():
    """Backend service information. The customer-facing UI is served by Next.js."""
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "status": "running",
        "docs": "/api/docs",
        "widget": "/chatbot.js",
    }


@app.get("/app")
@app.get("/dashboard")
async def dashboard_app():
    """Legacy UI route retained only as an explicit migration response."""
    raise HTTPException(status_code=410, detail="UI moved to the Next.js application")


@app.get("/demo")
async def demo_page():
    """Redirect to landing page — the landing page is the demo."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/#live-demo", status_code=301)


@app.get("/landing-neo")
async def landing_neo_page():
    """Retired legacy landing-page variant."""
    raise HTTPException(status_code=410, detail="Legacy page retired")


@app.get("/login")
async def login_page():
    """Legacy login route retained only as an explicit migration response."""
    raise HTTPException(status_code=410, detail="UI moved to the Next.js application")


@app.get("/data")
async def public_data_page():
    """Retired legacy public data page."""
    raise HTTPException(status_code=410, detail="Legacy page retired")


@app.get("/api")
async def api_info():
    """API information."""
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "endpoints": {
            "chat": "/api/chat",
            "stream": "/api/chat/stream",
            "crawl": "/api/crawl",
            "admin": "/api/admin",
            "embed": "/api/embed/setup",
            "docs": "/api/docs"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
