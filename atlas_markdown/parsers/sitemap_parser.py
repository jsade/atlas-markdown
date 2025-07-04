"""
Sitemap parser for extracting URLs from XML sitemap
"""

import logging
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)


class SitemapParser:
    """Parse sitemap.xml and extract documentation URLs"""

    def __init__(self, base_url: str, domain_restriction: str = "product"):
        self.base_url = base_url.rstrip("/")
        self.sitemap_url = f"{self.base_url}.xml"
        self.domain_restriction = domain_restriction

    async def fetch_sitemap(self) -> str:
        """Fetch the sitemap XML content"""
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                response = await client.get(self.sitemap_url)
                response.raise_for_status()

                # Validate it's actually XML
                content: str = response.text
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
            urls = [info["url"] for info in url_infos if info["url"] is not None]

            # Apply domain restriction
            filtered_urls = []
            for url in urls:
                if not url:
                    continue

                # Always reject non-Atlassian URLs
                if not url.startswith("https://support.atlassian.com/"):
                    continue

                # Apply domain restriction mode
                if self.domain_restriction == "off":
                    # No restriction beyond atlassian.com
                    if "/docs/" in url or (include_resources and "/resources/" in url):
                        filtered_urls.append(url)
                elif self.domain_restriction == "any-atlassian":
                    # Any atlassian product
                    if "/docs/" in url or (include_resources and "/resources/" in url):
                        filtered_urls.append(url)
                elif self.domain_restriction == "product":
                    # Only URLs under the base URL (default)
                    if url.startswith(self.base_url):
                        if "/docs/" in url or (include_resources and "/resources/" in url):
                            filtered_urls.append(url)

            logger.info(
                f"Found {len(filtered_urls)} URLs with domain_restriction='{self.domain_restriction}' "
                f"(docs: {sum(1 for u in filtered_urls if u and '/docs/' in u)}, "
                f"resources: {sum(1 for u in filtered_urls if u and '/resources/' in u)})"
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
