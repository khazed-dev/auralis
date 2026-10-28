"""
Tests for embed API endpoints.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestEmbedScriptEndpoints:
    """Tests for embed script generation endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_embed_script_success(self, authenticated_client, mock_database, sample_site):
        """Test getting embed script for a site."""
        # Seed the site using provider interface
        mock_database.seed_site(sample_site)
        
        response = await authenticated_client.get(
            f"/api/embed/script/{sample_site['site_id']}"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "embed_script" in data
        assert sample_site["site_id"] in data["embed_script"]
    
    @pytest.mark.asyncio
    async def test_get_embed_script_with_sri(self, authenticated_client, mock_database, sample_site):
        """Test embed script includes SRI hash when requested."""
        mock_database.seed_site(sample_site)
        
        with patch("app.routes.embed.get_widget_sri_hash", return_value="sha384-testhash123"):
            response = await authenticated_client.get(
                f"/api/embed/script/{sample_site['site_id']}?include_sri=true"
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "sri_hash" in data
        assert data["sri_hash"] is not None
        assert "integrity" in data["embed_script"]
    
    @pytest.mark.asyncio
    async def test_get_embed_script_without_sri(self, authenticated_client, mock_database, sample_site):
        """Test embed script without SRI hash."""
        mock_database.seed_site(sample_site)
        
        response = await authenticated_client.get(
            f"/api/embed/script/{sample_site['site_id']}?include_sri=false"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "integrity" not in data["embed_script"]
    
    @pytest.mark.asyncio
    async def test_get_embed_script_not_found(self, authenticated_client, mock_database):
        """Test getting embed script for non-existent site."""
        # Don't seed any site
        response = await authenticated_client.get("/api/embed/script/nonexistent")
        
        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.parametrize("endpoint", ["script", "security", "status"])
    async def test_management_endpoints_require_auth(self, client, endpoint):
        response = await client.get(f"/api/embed/{endpoint}/test123")
        assert response.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.parametrize("endpoint", ["script", "security", "status"])
    async def test_management_endpoints_reject_other_owner(self, authenticated_client, mock_database, sample_site, endpoint):
        mock_database.seed_site({**sample_site, "user_id": "another-owner"})
        response = await authenticated_client.get(f"/api/embed/{endpoint}/{sample_site['site_id']}")
        assert response.status_code == 403


class TestEmbedSecurityEndpoints:
    """Tests for embed security info endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_security_info_success(self, authenticated_client, mock_database, sample_site):
        """Test getting security info for a site."""
        mock_database.seed_site(sample_site)
        
        with patch("app.routes.embed.get_widget_sri_hash", return_value="sha384-testhash"):
            response = await authenticated_client.get(
                f"/api/embed/security/{sample_site['site_id']}"
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "site_id" in data
        assert "sri_hash" in data
        assert "allowed_domains" in data
        assert "widget_url" in data
    
    @pytest.mark.asyncio
    async def test_get_security_info_not_found(self, authenticated_client, mock_database):
        """Test getting security info for non-existent site."""
        # Don't seed any site
        response = await authenticated_client.get("/api/embed/security/nonexistent")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_security_info_includes_domain_config(self, authenticated_client, mock_database, sample_user):
        """Test that security info includes domain configuration."""
        site_with_domains = {
            "_id": "site_id",
            "site_id": "test123",
            "user_id": sample_user["_id"],
            "name": "Test Site with Domains",
            "url": "https://example.com",
            "config": {
                "security": {
                    "allowed_domains": ["example.com", "*.trusted.org"],
                    "enforce_domain_validation": True
                }
            }
        }
        mock_database.seed_site(site_with_domains)
        
        with patch("app.routes.embed.get_widget_sri_hash", return_value="sha384-hash"):
            response = await authenticated_client.get("/api/embed/security/test123")
        
        assert response.status_code == 200
        data = response.json()
        assert data["allowed_domains"] == ["example.com", "*.trusted.org"]
        assert data["enforce_domain_validation"] == True


class TestEmbedStatusEndpoints:
    """Tests for embed status endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_site_status_success(self, authenticated_client, mock_database, sample_site):
        """Test getting site status."""
        mock_database.seed_site(sample_site)
        
        # Create a crawl job using provider interface
        job_id = await mock_database.create_crawl_job(sample_site.get("url", "https://example.com"))
        await mock_database.update_crawl_job(
            job_id,
            status="completed",
            pages_crawled=10,
            pages_indexed=10
        )
        
        response = await authenticated_client.get(
            f"/api/embed/status/{sample_site['site_id']}"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["site_id"] == sample_site["site_id"]
        assert "status" in data
    
    @pytest.mark.asyncio
    async def test_get_site_status_not_found(self, authenticated_client, mock_database):
        """Test getting status for non-existent site."""
        # Don't seed any site
        response = await authenticated_client.get("/api/embed/status/nonexistent")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_get_site_status_pending_crawl(self, authenticated_client, mock_database, sample_site):
        """Test status when crawl is pending."""
        mock_database.seed_site(sample_site)
        # No crawl job created - should be pending
        
        response = await authenticated_client.get(
            f"/api/embed/status/{sample_site['site_id']}"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"


class TestSetupChatbotEndpoint:
    """Tests for chatbot setup endpoint."""
    
    @pytest.mark.asyncio
    async def test_setup_chatbot_success(self, authenticated_client, mock_database):
        """Test successful chatbot setup."""
        # No site exists yet
        mock_database.create_scheduled_crawl_job = AsyncMock(return_value="test-setup-job")
        queue = MagicMock(enqueue=AsyncMock())
        with patch("app.routes.embed.get_crawl_queue", return_value=queue):
            response = await authenticated_client.post(
                "/api/embed/setup",
                json={
                    "url": "https://example.com",
                    "name": "My Website",
                    "max_pages": 50
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "site_id" in data
        assert "embed_script" in data
        assert data["status"] == "crawling"
        queue.enqueue.assert_awaited_once()
    
    @pytest.mark.asyncio
    async def test_setup_chatbot_invalid_url(self, authenticated_client):
        """Test setup with invalid URL."""
        response = await authenticated_client.post(
            "/api/embed/setup",
            json={
                "url": "not-a-valid-url",
                "name": "My Website"
            }
        )
        
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_setup_chatbot_unauthenticated(self, client):
        """Test setup without authentication."""
        response = await client.post(
            "/api/embed/setup",
            json={
                "url": "https://example.com",
                "name": "My Website"
            }
        )
        
        assert response.status_code == 401


class TestSRIHashGeneration:
    """Tests for SRI hash functionality."""
    
    def test_sri_hash_format(self):
        """Test SRI hash format."""
        from app.core.security import generate_sri_hash
        
        content = b"test content"
        sri_hash = generate_sri_hash(content)
        
        assert sri_hash.startswith("sha384-")
        # Base64 encoded SHA384 should be 64 characters
        hash_part = sri_hash.replace("sha384-", "")
        assert len(hash_part) == 64
    
    def test_sri_hash_for_file_creates_valid_hash(self, tmp_path):
        """Test SRI hash generation for files."""
        from app.core.security import generate_sri_hash_for_file
        
        test_file = tmp_path / "test.js"
        test_file.write_text("console.log('test');")
        
        sri_hash = generate_sri_hash_for_file(str(test_file))
        
        assert sri_hash.startswith("sha384-")
    
    def test_sri_hash_consistency_for_same_file(self, tmp_path):
        """Test that same file produces same hash."""
        from app.core.security import generate_sri_hash_for_file
        
        test_file = tmp_path / "test.js"
        test_file.write_text("const x = 1;")
        
        hash1 = generate_sri_hash_for_file(str(test_file))
        hash2 = generate_sri_hash_for_file(str(test_file))
        
        assert hash1 == hash2


class TestEmbedOriginHardening:
    @staticmethod
    def request(host="safe.example.test", forwarded_host="evil.example.test"):
        from starlette.requests import Request
        return Request({
            "type": "http", "scheme": "https", "path": "/api/embed/script/site",
            "query_string": b"", "server": ("safe.example.test", 443),
            "headers": [(b"host", host.encode()), (b"x-forwarded-host", forwarded_host.encode()),
                        (b"x-forwarded-proto", b"javascript")],
        })

    def test_development_fallback_ignores_forwarded_origin(self, monkeypatch):
        from app.routes.embed import settings, get_embed_url
        monkeypatch.setattr(settings, "SITE_URL", "")
        monkeypatch.setattr(settings, "ENVIRONMENT", "development")
        assert get_embed_url(self.request(forwarded_host="example.test';alert(1);//")) == "https://safe.example.test"

    @pytest.mark.parametrize("configured", ["", "https://safe.test';alert(1);//", "javascript://safe.test", "https://user:pass@safe.test", "https://safe.test/path", "https://safe.test/?x=1", "https://safe.test/#fragment", "https://safe.test:0"])
    def test_production_requires_valid_explicit_origin(self, monkeypatch, configured):
        from app.routes.embed import settings, get_embed_url
        from fastapi import HTTPException
        monkeypatch.setattr(settings, "SITE_URL", configured)
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        with pytest.raises(HTTPException) as error:
            get_embed_url(self.request())
        assert error.value.status_code == 503

    @pytest.mark.parametrize("configured", ["https://auralis.example.test/", "http://localhost:8000", "https://[2001:db8::1]:8443"])
    def test_valid_configured_origin_is_preserved(self, monkeypatch, configured):
        from app.routes.embed import settings, get_embed_url
        monkeypatch.setattr(settings, "SITE_URL", configured)
        assert get_embed_url(self.request()) == configured.rstrip("/")

    @pytest.mark.asyncio
    async def test_script_encodes_dynamic_javascript_literals(self, authenticated_client, mock_database, sample_site):
        import json
        from html.parser import HTMLParser
        from urllib.parse import quote

        malicious_id = "site';globalThis.pwned=1;"
        mock_database.seed_site({**sample_site, "site_id": malicious_id})
        # Exercise the real endpoint and both SRI branches without contacting an external service.
        for sri in (None, "sha384-\"</script><img src=x onerror=alert(1)>\u2028"):
            with patch("app.routes.embed.get_widget_sri_hash", return_value=sri):
                response = await authenticated_client.get(
                    "/api/embed/script/" + quote(malicious_id, safe="") + "?include_sri=true"
                )
            assert response.status_code == 200
            script = response.json()["embed_script"]
            tags = []
            class Tags(HTMLParser):
                def handle_starttag(self, tag, attrs): tags.append(tag)
            Tags().feed(script)
            assert tags == ["script"]
            assert json.dumps(malicious_id) in script
            assert "<img" not in script

    def test_all_inline_values_cannot_terminate_the_script_element(self):
        import json
        from app.routes.embed import _embed_script, _script_literal
        value = "</script><img src=x onerror=alert(1)>\"'&\u2028\u2029"
        literal = _script_literal(value)
        assert json.loads(literal) == value
        assert not any(char in literal for char in "<>&\u2028\u2029")
        script = _embed_script("https://example.test", value, value)
        assert script.count("</script>") == 1
        assert "<img" not in script
        assert script.count(literal) == 2

    @pytest.mark.asyncio
    async def test_bad_production_origin_does_not_enqueue_setup(self, authenticated_client, mock_database, monkeypatch):
        from app.routes.embed import settings, generate_site_id
        monkeypatch.setattr(settings, "SITE_URL", "")
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        queue = MagicMock(enqueue=AsyncMock())
        with patch("app.routes.embed.get_crawl_queue", return_value=queue):
            response = await authenticated_client.post("/api/embed/setup", json={"url": "https://example.test"})
        assert response.status_code == 503
        queue.enqueue.assert_not_awaited()
        assert await mock_database.get_site(generate_site_id("https://example.test")) is None
