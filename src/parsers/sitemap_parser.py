"""
Sitemap parser for extracting URLs from XML sitemap
"""

import logging
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)


class SitemapParser:
    """Parse sitemap.xml and extract documentation URLs"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.sitemap_url = f"{self.base_url}.xml"

    async def fetch_sitemap(self) -> str:
        """Fetch the sitemap XML content"""
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                response = await client.get(self.sitemap_url)
                response.raise_for_status()

                # Validate it's actually XML
                content = response.text
                if not content.strip().startswith("<?xml"):
                    raise ValueError(
                        f"Sitemap does not appear to be valid XML. Content starts with: {content[:100]}"
                    )

                return content

            except httpx.HTTPStatusError as e:
                logger.error(
                    f"Failed to fetch sitemap from {self.sitemap_url}: HTTP {e.response.status_code}"
                )
                raise
            except Exception as e:
                logger.error(f"Error fetching sitemap: {e}")
                raise

    def parse_sitemap(self, xml_content: str) -> list[dict[str, str | None]]:
        """Parse sitemap XML and extract URLs with metadata"""
        urls = []

        try:
            # Parse XML
            root = ElementTree.fromstring(xml_content)

            # Handle namespace
            namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

            # Find all URL entries
            for url_elem in root.findall(".//ns:url", namespace):
                loc_elem = url_elem.find("ns:loc", namespace)
                lastmod_elem = url_elem.find("ns:lastmod", namespace)

                if loc_elem is not None and loc_elem.text:
                    url_info = {
                        "url": loc_elem.text,
                        "lastmod": lastmod_elem.text if lastmod_elem is not None else None,
                    }
                    urls.append(url_info)

            logger.info(f"Found {len(urls)} URLs in sitemap")

        except ElementTree.ParseError as e:
            logger.error(f"Failed to parse sitemap XML: {e}")
            raise

        return urls

    async def get_all_urls(self, include_resources: bool = True) -> list[str]:
        """Get all documentation URLs from the sitemap"""
        try:
            # Fetch sitemap
            xml_content = await self.fetch_sitemap()

            # Parse URLs
            url_infos = self.parse_sitemap(xml_content)

            # Extract just the URLs
            urls = [info["url"] for info in url_infos]

            # Filter URLs based on preferences and base URL
            if include_resources:
                # Include both /docs/ and /resources/ pages within base URL
                filtered_urls = [
                    url
                    for url in urls
                    if url.startswith(self.base_url) and ("/docs/" in url or "/resources/" in url)
                ]
            else:
                # Only documentation URLs within base URL
                filtered_urls = [
                    url for url in urls if url.startswith(self.base_url) and "/docs/" in url
                ]

            logger.info(
                f"Found {len(filtered_urls)} URLs (docs: {sum(1 for u in filtered_urls if '/docs/' in u)}, resources: {sum(1 for u in filtered_urls if '/resources/' in u)})"
            )

            return filtered_urls

        except Exception as e:
            logger.error(f"Failed to get URLs from sitemap: {e}")
            raise

    def get_url_priority(self, url: str) -> int:
        """
        Assign priority to URLs based on their path structure.
        Lower numbers = higher priority
        """
        # Prioritize overview/getting started pages
        if any(
            keyword in url.lower()
            for keyword in ["get-started", "overview", "what-is", "introduction"]
        ):
            return 1

        # Then setup/installation pages
        if any(keyword in url.lower() for keyword in ["setup", "install", "configure", "sign-up"]):
            return 2

        # Core features
        if any(keyword in url.lower() for keyword in ["features", "basics", "fundamentals"]):
            return 3

        # How-to guides
        if any(keyword in url.lower() for keyword in ["how-to", "guide", "tutorial"]):
            return 4

        # Everything else
        return 5
