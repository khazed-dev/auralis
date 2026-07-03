"""
Web crawler service for scraping websites.
"""
import asyncio
import re
from typing import List, Dict, Set, Optional
from urllib.parse import urljoin, urlparse
import aiohttp
from bs4 import BeautifulSoup
from loguru import logger

from app.config import settings
from app.core.security import validate_public_http_url
from app.database import get_mongodb


class CrawlCancelled(Exception):
    """Raised when a persisted crawl job receives a cancellation request."""


class CrawlerService:
    """Service for crawling websites and extracting content."""
    
    def __init__(self):
        self.visited_urls: Set[str] = set()
        self.pages: List[Dict] = []
        self.errors: List[str] = []
        self.job_id: Optional[str] = None
    
    async def crawl(
        self,
        start_url: str,
        max_pages: int = None,
        include_patterns: List[str] = None,
        exclude_patterns: List[str] = None,
        job_id: str = None
    ) -> List[Dict]:
        """
        Crawl a website starting from the given URL.
        
        Args:
            start_url: The starting URL to crawl
            max_pages: Maximum number of pages to crawl
            include_patterns: URL patterns to include (regex)
            exclude_patterns: URL patterns to exclude (regex)
            job_id: Crawl job ID for progress tracking
        
        Returns:
            List of crawled pages with content
        """
        self.visited_urls = set()
        self.pages = []
        self.errors = []
        self.job_id = job_id
        
        max_pages = max_pages or settings.MAX_PAGES
        include_patterns = include_patterns or []
        exclude_patterns = exclude_patterns or []

        is_valid, validation_error = await validate_public_http_url(start_url)
        if not is_valid:
            raise ValueError(f"Unsafe crawl URL: {validation_error}")
        
        # Compile regex patterns
        if any(len(pattern) > 500 for pattern in [*include_patterns, *exclude_patterns]):
            raise ValueError("Crawl URL patterns must be 500 characters or fewer")
        include_regex = [re.compile(p) for p in include_patterns] if include_patterns else None
        exclude_regex = [re.compile(p) for p in exclude_patterns] if exclude_patterns else None
        
        # Parse base domain
        parsed_start = urlparse(start_url)
        base_domain = f"{parsed_start.scheme}://{parsed_start.netloc}"
        
        # Queue for BFS crawling
        queue = [start_url]
        
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "SiteChat-Crawler/1.0"}
        ) as session:
            while queue and len(self.pages) < max_pages:
                if self.job_id:
                    mongodb = await get_mongodb()
                    job = await mongodb.get_crawl_job(self.job_id)
                    if job and job.get("status") == "cancelled":
                        logger.info(f"Crawl job {self.job_id} cancelled")
                        raise CrawlCancelled("Crawl cancelled by user")

                # Get next URL
                url = queue.pop(0)
                
                if url in self.visited_urls:
                    continue
                
                # Check patterns
                if not self._should_crawl(url, include_regex, exclude_regex):
                    continue
                
                self.visited_urls.add(url)
                
                try:
                    # Fetch page
                    page_data = await self._fetch_page(session, url)
                    
                    if page_data:
                        self.pages.append(page_data)
                        
                        # Extract links and add to queue
                        links = self._extract_links(page_data["html"], base_domain, url)
                        for link in links:
                            if link not in self.visited_urls:
                                queue.append(link)
                        
                        # Update job progress
                        if self.job_id:
                            mongodb = await get_mongodb()
                            await mongodb.update_crawl_job(
                                self.job_id,
                                pages_crawled=len(self.pages)
                            )
                        
                        logger.info(f"Crawled: {url} ({len(self.pages)}/{max_pages})")
                    
                    # Respect crawl delay
                    await asyncio.sleep(settings.CRAWL_DELAY)
                    
                except Exception as e:
                    error_msg = f"Error crawling {url}: {str(e)}"
                    self.errors.append(error_msg)
                    logger.error(error_msg)
        
        logger.info(f"Crawl complete. Total pages: {len(self.pages)}")
        return self.pages
    
    async def _fetch_page(
        self,
        session: aiohttp.ClientSession,
        url: str
    ) -> Optional[Dict]:
        """Fetch a single page and extract content."""
        try:
            current_url = url
            response = None
            for _ in range(6):
                is_valid, validation_error = await validate_public_http_url(current_url)
                if not is_valid:
                    raise ValueError(f"Unsafe crawl URL: {validation_error}")
                response = await session.get(current_url, allow_redirects=False)
                if response.status not in {301, 302, 303, 307, 308}:
                    break
                location = response.headers.get("location")
                response.release()
                if not location:
                    return None
                current_url = urljoin(current_url, location)
            else:
                raise ValueError("Too many redirects")

            async with response:
                if response.status == 403:
                    logger.warning(f"Access forbidden (403) for {url} - site may be blocking crawlers")
                    self.errors.append(f"Access forbidden: {url}")
                    return None
                elif response.status == 429:
                    logger.warning(f"Rate limited (429) for {url} - site has bot protection")
                    self.errors.append(f"Bot protection/rate limited: {url}")
                    return None
                elif response.status != 200:
                    error = f"HTTP {response.status}: {current_url}"
                    self.errors.append(error)
                    logger.warning(error)
                    return None
                
                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type:
                    self.errors.append(
                        f"Unsupported content type '{content_type}': {current_url}"
                    )
                    return None
                max_bytes = settings.CRAWL_MAX_RESPONSE_BYTES
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > max_bytes:
                    self.errors.append(f"Page too large: {current_url}")
                    return None
                raw = await response.content.read(max_bytes + 1)
                if len(raw) > max_bytes:
                    self.errors.append(f"Page too large: {current_url}")
                    return None
                encoding = response.charset or "utf-8"
                html = raw.decode(encoding, errors="replace")
                
                # Parse HTML. Keep the original string available because some
                # WordPress themes wrap meaningful page content in semantic
                # header/nav/aside containers.
                soup = BeautifulSoup(html, "html.parser")
                
                # Remove unwanted elements
                for element in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
                    element.decompose()
                
                # Extract title
                title = ""
                if soup.title:
                    title = soup.title.string or ""
                elif soup.find("h1"):
                    title = soup.find("h1").get_text(strip=True)
                
                # Extract main content
                main_content = soup.find("main") or soup.find("article") or soup.find("body")
                
                if main_content:
                    # Get text content
                    text = main_content.get_text(separator="\n", strip=True)
                    # Clean up whitespace
                    text = re.sub(r'\n{3,}', '\n\n', text)
                    text = re.sub(r' {2,}', ' ', text)
                else:
                    text = soup.get_text(separator="\n", strip=True)

                # If aggressive boilerplate removal stripped the actual page,
                # retry conservatively. This keeps product/category content
                # while still excluding executable and invisible elements.
                if len(text) < 100:
                    fallback_soup = BeautifulSoup(html, "html.parser")
                    for element in fallback_soup.find_all(
                        ["script", "style", "noscript", "template"]
                    ):
                        element.decompose()
                    fallback_content = (
                        fallback_soup.find("main")
                        or fallback_soup.find("article")
                        or fallback_soup.find("body")
                        or fallback_soup
                    )
                    text = fallback_content.get_text(separator="\n", strip=True)
                    text = re.sub(r'\n{3,}', '\n\n', text)
                    text = re.sub(r' {2,}', ' ', text)
                
                # Skip pages with very little content
                if len(text) < 100:
                    self.errors.append(f"Page has too little text content: {current_url}")
                    return None
                
                return {
                    "url": current_url,
                    "title": title.strip(),
                    "content": text,
                    "html": html,
                    "metadata": {
                        "content_length": len(text),
                        "word_count": len(text.split())
                    }
                }
                
        except Exception as e:
            error = f"Error fetching {url}: {e}"
            self.errors.append(error)
            logger.error(error)
            return None
    
    def _extract_links(self, html: str, base_domain: str, current_url: str) -> List[str]:
        """Extract links from HTML."""
        soup = BeautifulSoup(html, "html.parser")
        links = []
        
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            
            # Skip empty, javascript, and anchor links
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            
            # Make absolute URL
            absolute_url = urljoin(current_url, href)
            parsed = urlparse(absolute_url)
            
            # Only include links from same domain
            if f"{parsed.scheme}://{parsed.netloc}" != base_domain:
                continue
            
            # Remove fragments
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                clean_url += f"?{parsed.query}"
            
            # Skip file downloads
            if any(clean_url.lower().endswith(ext) for ext in [".pdf", ".jpg", ".png", ".gif", ".zip", ".mp4"]):
                continue
            
            links.append(clean_url)
        
        return list(set(links))
    
    def _should_crawl(
        self,
        url: str,
        include_regex: List[re.Pattern] = None,
        exclude_regex: List[re.Pattern] = None
    ) -> bool:
        """Check if URL should be crawled based on patterns."""
        # Check exclude patterns first
        if exclude_regex:
            for pattern in exclude_regex:
                if pattern.search(url):
                    return False
        
        # If include patterns specified, URL must match at least one
        if include_regex:
            return any(pattern.search(url) for pattern in include_regex)
        
        return True
    
    def get_stats(self) -> Dict:
        """Get crawl statistics."""
        return {
            "pages_crawled": len(self.pages),
            "urls_visited": len(self.visited_urls),
            "errors": len(self.errors),
            "error_messages": self.errors[:10]  # First 10 errors
        }
