"""
Page crawler for discovering Atlassian documentation pages
"""

import asyncio
import logging
import re
from typing import Any, Self
from urllib.parse import urljoin, urlparse, urlunparse

from playwright.async_api import Browser, Page, async_playwright

logger = logging.getLogger(__name__)


class DocumentationCrawler:
    """Crawls Atlassian documentation to discover all pages"""

    def __init__(
        self, base_url: str = "https://support.atlassian.com/jira-service-management-cloud/"
    ):
        self.base_url = base_url.rstrip("/")
        self.domain = urlparse(base_url).netloc
        self.discovered_urls: set[str] = set()
        self.browser: Browser | None = None
        self.page: Page | None = None

    async def __aenter__(self) -> Self:
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def initialize(self) -> None:
        """Initialize browser with error recovery"""
        max_retries = 3

        for attempt in range(max_retries):
            try:
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",  # Prevent shared memory issues
                        "--no-sandbox",  # Required in some environments
                        "--disable-gpu",  # Reduce resource usage
                        "--disable-web-security",  # Handle CORS issues
                        "--disable-features=IsolateOrigins,site-per-process",
                    ],
                )

                # Create page with timeout
                self.page = await self.browser.new_page()

                # Set up error handlers
                self.page.on(
                    "pageerror", lambda exc: logger.warning(f"Page JavaScript error: {exc}")
                )
                self.page.on("crash", lambda _: self._handle_page_crash())

                # Set user agent and viewport
                await self.page.set_extra_http_headers(
                    {
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                        "Accept-Language": "en-US,en;q=0.9",
                    }
                )
                await self.page.set_viewport_size({"width": 1920, "height": 1080})

                logger.info("Browser initialized successfully")
                break

            except Exception as e:
                logger.error(f"Failed to initialize browser (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2**attempt)
                else:
                    raise RuntimeError(
                        f"Failed to initialize browser after {max_retries} attempts"
                    ) from e

    async def _handle_page_crash(self) -> None:
        """Handle page crash by creating new page"""
        logger.error("Page crashed! Creating new page...")
        try:
            if self.browser:
                self.page = await self.browser.new_page()
                self.page.on(
                    "pageerror", lambda exc: logger.warning(f"Page JavaScript error: {exc}")
                )
                self.page.on("crash", lambda _: self._handle_page_crash())
        except Exception as e:
            logger.error(f"Failed to create new page after crash: {e}")

    async def close(self) -> None:
        """Close browser"""
        try:
            if self.page:
                await self.page.close()
        except Exception as e:
            logger.error(f"Error closing page: {e}")

        try:
            if self.browser:
                await self.browser.close()
        except Exception as e:
            logger.error(f"Error closing browser: {e}")

        try:
            if hasattr(self, "playwright") and self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.error(f"Error stopping playwright: {e}")

    def normalize_url(self, url: str) -> str:
        """Normalize URL for consistency"""
        # Parse URL
        parsed = urlparse(url)

        # Remove fragment
        parsed = parsed._replace(fragment="")

        # Remove trailing slash from path
        path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
        parsed = parsed._replace(path=path)

        # Remove common tracking parameters
        if parsed.query:
            params = dict(p.split("=") for p in parsed.query.split("&") if "=" in p)
            # Remove tracking params
            for param in ["utm_source", "utm_medium", "utm_campaign", "ref"]:
                params.pop(param, None)
            query = "&".join(f"{k}={v}" for k, v in params.items())
            parsed = parsed._replace(query=query)

        return urlunparse(parsed)

    def is_valid_documentation_url(self, url: str) -> bool:
        """Check if URL is a valid documentation page"""
        parsed = urlparse(url)

        # Must be same domain
        if parsed.netloc != self.domain:
            return False

        # Must be under the base path
        if not parsed.path.startswith(urlparse(self.base_url).path):
            return False

        # Exclude certain patterns
        exclude_patterns = [
            r"/api/",
            r"/rest/",
            r"\.pdf$",
            r"\.zip$",
            r"/download/",
            r"/attachments/",
            r"/login",
            r"/signup",
        ]

        for pattern in exclude_patterns:
            if re.search(pattern, parsed.path, re.IGNORECASE):
                return False

        return True

    async def extract_navigation_links(self) -> list[str]:
        """Extract links from the navigation tree"""
        links: list[str] = []

        if not self.page:
            return links

        try:
            # Wait for navigation to load
            await self.page.wait_for_selector('[data-testid="page-tree"]', timeout=10000)

            # Get all navigation links
            nav_links = await self.page.query_selector_all('[data-testid="page-tree"] a')

            for link in nav_links:
                href = await link.get_attribute("href")
                if href:
                    # Convert relative URLs to absolute
                    absolute_url = urljoin(self.base_url, href)
                    normalized = self.normalize_url(absolute_url)

                    if self.is_valid_documentation_url(normalized):
                        links.append(normalized)

        except Exception as e:
            logger.warning(f"Failed to extract navigation links: {e}")

        return links

    async def extract_page_links(self) -> list[str]:
        """Extract all links from the current page content"""
        links: list[str] = []

        if not self.page:
            return links

        try:
            # Get all links in the main content area
            content_selectors = [
                '[data-testid="topic-content"] a',
                ".ak-renderer-document a",
                '[role="main"] a',
                "main a",
            ]

            for selector in content_selectors:
                page_links = await self.page.query_selector_all(selector)

                for link in page_links:
                    href = await link.get_attribute("href")
                    if href:
                        # Convert relative URLs to absolute
                        absolute_url = urljoin(self.page.url, href)
                        normalized = self.normalize_url(absolute_url)

                        if self.is_valid_documentation_url(normalized):
                            links.append(normalized)

                if page_links:  # If we found links with this selector, stop
                    break

        except Exception as e:
            logger.warning(f"Failed to extract page links: {e}")

        return links

    async def discover_from_sitemap(self) -> list[str]:
        """Try to discover pages from sitemap"""
        links: list[str] = []

        if not self.page:
            return links

        sitemap_urls = [
            f"{self.base_url}/sitemap.xml",
            f"{self.base_url}/sitemap",
            f"https://{self.domain}/sitemap.xml",
        ]

        for sitemap_url in sitemap_urls:
            try:
                response = await self.page.goto(sitemap_url)
                if response and response.status == 200:
                    content = await self.page.content()

                    # Extract URLs from sitemap
                    url_pattern = r"<loc>(.*?)</loc>"
                    matches = re.findall(url_pattern, content)

                    for url in matches:
                        normalized = self.normalize_url(url)
                        if self.is_valid_documentation_url(normalized):
                            links.append(normalized)

                    if links:
                        logger.info(f"Found {len(links)} URLs in sitemap")
                        break

            except Exception as e:
                logger.debug(f"Failed to fetch sitemap from {sitemap_url}: {e}")

        return links

    async def crawl_page(self, url: str) -> tuple[set[str], str | None]:
        """Crawl a single page and extract new URLs

        Returns:
            Tuple of (new_urls, final_url) where final_url is the URL after redirects
        """
        new_urls: set[str] = set()
        final_url = None

        if not self.page:
            return new_urls, final_url

        try:
            # Navigate to the page with timeout
            response = await self.page.goto(
                url, wait_until="networkidle", timeout=30000  # 30 second timeout
            )

            # Handle various response scenarios
            if not response:
                logger.warning(f"No response received for {url}")
                return new_urls, final_url

            # Capture the final URL after redirects
            final_url = self.page.url
            if final_url != url:
                logger.info(f"Redirect detected: {url} -> {final_url}")

            if response.status == 429:
                # Handle rate limiting
                retry_after = response.headers.get("Retry-After", "60")
                wait_time = int(retry_after) if retry_after.isdigit() else 60
                logger.warning(f"Rate limited on {url}, waiting {wait_time}s")
                await asyncio.sleep(wait_time)
                return await self.crawl_page(url)  # Retry

            if response.status == 503:
                # Service unavailable - wait and retry
                logger.warning(f"Service unavailable for {url}, waiting 30s")
                await asyncio.sleep(30)
                return await self.crawl_page(url)

            if response.status >= 400:
                logger.warning(f"HTTP {response.status} for {url}")
                return new_urls, final_url

            # Wait for content to load
            try:
                await self.page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                # Continue even if network isn't completely idle
                pass

            # Extract links
            nav_links = await self.extract_navigation_links()
            page_links = await self.extract_page_links()

            # Combine all links
            all_links = set(nav_links + page_links)

            # Filter new URLs
            for link in all_links:
                if link not in self.discovered_urls:
                    new_urls.add(link)

        except TimeoutError:
            logger.error(f"Timeout loading {url}")
            # Try with reduced wait
            try:
                await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
                final_url = self.page.url
                nav_links = await self.extract_navigation_links()
                page_links = await self.extract_page_links()
                all_links = set(nav_links + page_links)
                for link in all_links:
                    if link not in self.discovered_urls:
                        new_urls.add(link)
            except Exception:
                logger.error(f"Failed to load {url} even with reduced wait")

        except Exception as e:
            logger.error(f"Error crawling {url}: {e}")
            # Check if browser is still alive
            if self.page.is_closed():
                await self._handle_page_crash()

        return new_urls, final_url

    async def discover_all_pages(self, entry_point: str | None = None) -> list[str]:
        """Discover all documentation pages starting from entry point"""
        if not entry_point:
            entry_point = f"{self.base_url}/resources/"

        logger.info(f"Starting discovery from: {entry_point}")

        # Try sitemap first
        sitemap_urls = await self.discover_from_sitemap()
        self.discovered_urls.update(sitemap_urls)

        # Queue for BFS crawling
        to_crawl = {entry_point}
        self.discovered_urls.add(entry_point)

        # Also add the base docs URL
        docs_url = f"{self.base_url}/docs/"
        to_crawl.add(docs_url)
        self.discovered_urls.add(docs_url)

        # Breadth-first search
        while to_crawl:
            current_url = to_crawl.pop()
            logger.info(f"Crawling: {current_url} ({len(self.discovered_urls)} discovered)")

            # Discover new URLs from this page
            new_urls, final_url = await self.crawl_page(current_url)

            # Add new URLs to queue
            for url in new_urls:
                if url not in self.discovered_urls:
                    to_crawl.add(url)
                    self.discovered_urls.add(url)

            # Rate limiting
            await asyncio.sleep(0.5)

        logger.info(f"Discovery complete. Found {len(self.discovered_urls)} pages")
        return sorted(list(self.discovered_urls))

    async def get_page_title(self, url: str) -> str | None:
        """Get the title of a page"""
        if not self.page:
            return None

        try:
            await self.page.goto(url, wait_until="networkidle")

            # Try different title selectors
            title_selectors = ["h1", '[data-testid="topic-title"]', ".page-title", "title"]

            for selector in title_selectors:
                element = await self.page.query_selector(selector)
                if element:
                    title = await element.inner_text()
                    return title.strip()

        except Exception as e:
            logger.error(f"Failed to get title for {url}: {e}")

        return None
