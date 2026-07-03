"""
Security utilities and middleware for the Auralis AI application.
"""
import re
import secrets
import html
import asyncio
import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

from app.config import settings


# ===========================================
# Security Headers Middleware
# ===========================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        if settings.ENABLE_SECURITY_HEADERS:
            # Prevent clickjacking
            response.headers["X-Frame-Options"] = "DENY"
            
            # Prevent MIME type sniffing
            response.headers["X-Content-Type-Options"] = "nosniff"
            
            # Enable XSS protection
            response.headers["X-XSS-Protection"] = "1; mode=block"
            
            # Referrer policy
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            
            # Permissions policy
            response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
            
            # Content-Security-Policy for HTML pages: set CONTENT_SECURITY_POLICY in .env (see .env.example).
            if not request.url.path.startswith("/api/"):
                csp = settings.content_security_policy_non_api
                if csp:
                    response.headers["Content-Security-Policy"] = csp
            
            # Strict Transport Security (only in production with HTTPS)
            if settings.is_production:
                response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response


# ===========================================
# Request Validation Middleware
# ===========================================

class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Validate and sanitize incoming requests."""
    
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB
    
    async def dispatch(self, request: Request, call_next):
        # Check content length
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_CONTENT_LENGTH:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"detail": "Request body too large"}
            )
        
        # Block suspicious user agents (basic bot protection)
        user_agent = request.headers.get("user-agent", "").lower()
        blocked_agents = ["sqlmap", "nikto", "nessus", "nmap"]
        if any(agent in user_agent for agent in blocked_agents):
            logger.warning(f"Blocked suspicious user agent: {user_agent} from {request.client.host}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Access denied"}
            )
        
        return await call_next(request)


# ===========================================
# Input Validation & Sanitization
# ===========================================

def sanitize_html(text: str) -> str:
    """Escape HTML characters to prevent XSS."""
    if not text:
        return text
    return html.escape(text)


def sanitize_input(text: str, max_length: int = 10000) -> str:
    """Sanitize user input."""
    if not text:
        return text
    
    # Truncate to max length
    text = text[:max_length]
    
    # Remove null bytes
    text = text.replace("\x00", "")
    
    # Normalize whitespace
    text = " ".join(text.split())
    
    return text


def validate_email(email: str) -> bool:
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_password(password: str) -> tuple[bool, str]:
    """
    Validate password meets security requirements.
    Returns (is_valid, error_message)
    """
    if len(password) < settings.MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {settings.MIN_PASSWORD_LENGTH} characters"

    if settings.REQUIRE_PASSWORD_COMPLEXITY:
        if not re.search(r"[A-Z]", password):
            return False, "Password must contain an uppercase letter"
        if not re.search(r"[a-z]", password):
            return False, "Password must contain a lowercase letter"
        if not re.search(r"\d", password):
            return False, "Password must contain a digit"
        weak_passwords = {
            "password", "password1", "password123", "admin123",
            "qwerty123", "letmein", "welcome123",
        }
        if password.lower() in weak_passwords:
            return False, "Password is too common or weak"

    return True, ""


def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def generate_secure_secret(length: int = 64) -> str:
    """Generate a secure secret key."""
    return secrets.token_hex(length)


# ===========================================
# Security Checks
# ===========================================

def check_security_configuration() -> list[str]:
    """
    Check security configuration and return warnings.
    Call this at startup to alert about insecure settings.
    """
    warnings = []
    
    # Check JWT secret
    if not settings.is_jwt_secret_secure:
        warnings.append(
            "SECURITY WARNING: JWT_SECRET is using an insecure default. "
            "Set a strong secret (at least 32 characters) in production!"
        )
    
    # Check debug mode in production
    if settings.ENVIRONMENT == "production" and settings.DEBUG:
        warnings.append(
            "SECURITY WARNING: DEBUG=true in production environment. "
            "Set DEBUG=false for production!"
        )
    
    # Check CORS configuration
    if settings.CORS_ORIGINS == "*" and settings.is_production:
        warnings.append(
            "SECURITY WARNING: CORS allows all origins (*) in production. "
            "Restrict CORS_ORIGINS to specific domains!"
        )
    
    # Check admin password
    if settings.ADMIN_PASSWORD and settings.ADMIN_PASSWORD in ["admin123", "password", "admin"]:
        warnings.append(
            "SECURITY WARNING: Default admin password is weak. "
            "Set a strong ADMIN_PASSWORD or leave it empty to disable auto-creation!"
        )
    
    return warnings


def log_security_warnings():
    """Log security warnings at startup."""
    warnings = check_security_configuration()
    
    if warnings:
        logger.warning("=" * 60)
        logger.warning("SECURITY CONFIGURATION WARNINGS")
        logger.warning("=" * 60)
        for warning in warnings:
            logger.warning(warning)
        logger.warning("=" * 60)
    else:
        logger.info("Security configuration check passed")
    if warnings and settings.is_production and settings.FAIL_STARTUP_ON_INSECURE_CONFIG:
        raise RuntimeError(
            "Refusing to start production with insecure security configuration"
        )


# ===========================================
# Rate Limiting Helpers
# ===========================================

def get_client_ip(request: Request) -> str:
    """Get the real client IP, considering proxies."""
    # Check X-Forwarded-For header (for reverse proxies)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Get the first IP in the chain (original client)
        return forwarded_for.split(",")[0].strip()
    
    # Check X-Real-IP header
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    
    # Fall back to direct client IP
    return request.client.host if request.client else "unknown"


# ===========================================
# Widget Domain Validation
# ===========================================

def extract_domain_from_url(url: str) -> Optional[str]:
    """Extract domain from a URL or Referer/Origin header."""
    if not url:
        return None
    
    # Remove protocol
    if "://" in url:
        url = url.split("://", 1)[1]
    
    # Remove path, port, and query string
    domain = url.split("/")[0].split(":")[0].split("?")[0]
    
    return domain.lower() if domain else None


def match_domain_pattern(domain: str, pattern: str) -> bool:
    """
    Check if a domain matches a pattern.
    Supports wildcards like *.example.com
    """
    if not domain or not pattern:
        return False
    
    domain = domain.lower()
    pattern = pattern.lower()
    
    # Exact match
    if domain == pattern:
        return True
    
    # Wildcard match (*.example.com)
    if pattern.startswith("*."):
        # Get the base domain from pattern
        base_pattern = pattern[2:]  # Remove "*."
        
        # Check if domain ends with .base_pattern or equals base_pattern
        if domain == base_pattern:
            return True
        if domain.endswith("." + base_pattern):
            return True
    
    return False


def validate_widget_domain(
    request: Request,
    allowed_domains: list[str],
    enforce_validation: bool = False,
    require_referrer: bool = False
) -> tuple[bool, Optional[str]]:
    """
    Validate that a widget request comes from an allowed domain.
    
    Args:
        request: The incoming request
        allowed_domains: List of allowed domain patterns
        enforce_validation: If True, reject requests from non-whitelisted domains
        require_referrer: If True, require a valid Referer or Origin header
    
    Returns:
        (is_valid, error_message)
    """
    # Get origin or referer
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    
    # Extract domain
    request_domain = extract_domain_from_url(origin) or extract_domain_from_url(referer)
    
    # If no domain found and referrer is required
    if not request_domain:
        if require_referrer:
            return False, "Missing Origin or Referer header"
        # If not required and no domains configured, allow
        if not allowed_domains or not enforce_validation:
            return True, None
        return False, "Could not determine request origin"
    
    # Enforced validation without an allow-list must fail closed.
    if not allowed_domains:
        if enforce_validation:
            return False, "No authorized domains configured for this site"
        return True, None
    
    # Check against allowed domains
    for pattern in allowed_domains:
        if match_domain_pattern(request_domain, pattern):
            return True, None
    
    # Domain not in whitelist
    if enforce_validation:
        logger.warning(f"Widget request from unauthorized domain: {request_domain}")
        return False, f"Domain not authorized: {request_domain}"
    
    # Log warning but allow (soft enforcement)
    logger.info(f"Widget request from non-whitelisted domain: {request_domain}")
    return True, None


def get_request_origin(request: Request) -> Optional[str]:
    """Get the origin domain of a request."""
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    return extract_domain_from_url(origin) or extract_domain_from_url(referer)


# ===========================================
# Outbound URL / SSRF protection
# ===========================================

def _is_public_ip(value: str) -> bool:
    """Return True only for globally routable IP addresses."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.is_global


async def validate_public_http_url(url: str) -> tuple[bool, Optional[str]]:
    """
    Resolve and validate an outbound HTTP(S) URL.

    Every resolved address must be globally routable. This blocks loopback,
    private/link-local networks, cloud metadata IPs, and DNS answers that mix
    public and private addresses.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False, "Invalid URL"

    if parsed.scheme not in {"http", "https"}:
        return False, "Only HTTP and HTTPS URLs are allowed"
    if not parsed.hostname or parsed.username or parsed.password:
        return False, "URL must contain a valid public hostname without credentials"

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        return False, "Local network addresses are not allowed"

    try:
        ipaddress.ip_address(hostname)
        addresses = {hostname}
    except ValueError:
        try:
            loop = asyncio.get_running_loop()
            records = await loop.getaddrinfo(
                hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
            addresses = {record[4][0].split("%", 1)[0] for record in records}
        except (socket.gaierror, OSError):
            return False, "Hostname could not be resolved"

    if not addresses or any(not _is_public_ip(address) for address in addresses):
        return False, "URL resolves to a non-public network address"
    return True, None


# ===========================================
# SRI Hash Generation
# ===========================================

import hashlib
import base64


def generate_sri_hash(content: bytes, algorithm: str = "sha384") -> str:
    """
    Generate a Subresource Integrity (SRI) hash for content.
    
    Args:
        content: The file content as bytes
        algorithm: Hash algorithm (sha256, sha384, or sha512)
    
    Returns:
        SRI hash string like "sha384-abc123..."
    """
    if algorithm == "sha256":
        hash_func = hashlib.sha256
    elif algorithm == "sha384":
        hash_func = hashlib.sha384
    elif algorithm == "sha512":
        hash_func = hashlib.sha512
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")
    
    digest = hash_func(content).digest()
    b64_hash = base64.b64encode(digest).decode("utf-8")
    
    return f"{algorithm}-{b64_hash}"


def generate_sri_hash_for_file(file_path: str, algorithm: str = "sha384") -> str:
    """Generate SRI hash for a file."""
    with open(file_path, "rb") as f:
        content = f.read()
    return generate_sri_hash(content, algorithm)
