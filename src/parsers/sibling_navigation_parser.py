"""
Parser for extracting sibling navigation structure from Atlassian documentation pages
"""

import logging
from urllib.parse import urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class SiblingNavigationParser:
    """Extracts and parses sibling navigation structure to determine folder hierarchy"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def extract_sibling_info(self, html: str, current_url: str) -> dict[str, any]:
        """
        Extract sibling navigation information from the page

        Returns:
            Dict containing:
                - section_heading: The main contextual topic header
                - section_url: URL of the section header link (if available)
                - siblings: List of sibling pages with their titles and URLs
                - current_page_title: Title of the current page
                - current_page_position: Position in the sibling list
        """
        soup = BeautifulSoup(html, "html.parser")

        # Find the sibling navigation section
        sibling_nav = soup.find(
            "ul", {"class": "sidebar__section--topic", "data-testid": "sibling-pages"}
        )

        if not sibling_nav:
            logger.debug(f"No sibling navigation found for {current_url}")
            return self._create_empty_result()

        result = {
            "section_heading": None,
            "section_url": None,
            "siblings": [],
            "current_page_title": None,
            "current_page_position": -1,
        }

        # Extract section heading
        section_heading_elem = sibling_nav.find(
            "a", {"class": "sidebar__heading", "data-testid": "sibling-section-heading"}
        )
        if section_heading_elem:
            result["section_heading"] = section_heading_elem.get_text(strip=True)
            result["section_url"] = self._normalize_url(section_heading_elem.get("href", ""))
            logger.debug(f"Found section heading: {result['section_heading']}")

        # Extract all sibling items
        sibling_items = sibling_nav.find_all(
            "li", {"class": "sidebar__item", "data-testid": "sibling-section-link"}
        )

        position = 0
        for item in sibling_items:
            # Check if this is the current page
            if "sidebar__item--current" in item.get("class", []):
                # Current page is displayed as plain text
                current_text_elem = item.find("p", {"class": "sidebar__link"})
                if current_text_elem:
                    page_title = current_text_elem.get_text(strip=True)
                    result["current_page_title"] = page_title
                    result["current_page_position"] = position
                    result["siblings"].append(
                        {
                            "title": page_title,
                            "url": current_url,
                            "is_current": True,
                            "position": position,
                        }
                    )
            else:
                # Other sibling pages have links
                link_elem = item.find("a", {"class": "sidebar__link"})
                if link_elem:
                    page_title = link_elem.get_text(strip=True)
                    page_url = self._normalize_url(link_elem.get("href", ""))
                    result["siblings"].append(
                        {
                            "title": page_title,
                            "url": page_url,
                            "is_current": False,
                            "position": position,
                        }
                    )

            position += 1

        # Check for "Show more" button indicating additional siblings
        show_more_btn = sibling_nav.find("button", {"data-testid": "sibling-chevron-down"})
        if show_more_btn:
            logger.warning(
                f"Additional siblings may be hidden behind 'Show more' button for {current_url}"
            )
            result["has_more_siblings"] = True
        else:
            result["has_more_siblings"] = False

        logger.info(
            f"Found {len(result['siblings'])} siblings for section '{result['section_heading']}'"
        )

        return result

    def _normalize_url(self, url: str) -> str:
        """Normalize URL to absolute form"""
        if not url:
            return ""

        if url.startswith("http://") or url.startswith("https://"):
            return url

        if url.startswith("/"):
            # Absolute path - prepend domain
            parsed_base = urlparse(self.base_url)
            return f"{parsed_base.scheme}://{parsed_base.netloc}{url}"

        # Relative URL - join with base
        return f"{self.base_url}/{url}"

    def _create_empty_result(self) -> dict[str, any]:
        """Create empty result structure"""
        return {
            "section_heading": None,
            "section_url": None,
            "siblings": [],
            "current_page_title": None,
            "current_page_position": -1,
            "has_more_siblings": False,
        }

    def get_folder_structure(self, sibling_info: dict[str, any]) -> tuple[str, str]:
        """
        Determine folder path and filename based on sibling information

        Returns:
            Tuple of (folder_path, filename)
        """
        if not sibling_info["section_heading"]:
            # No sibling context - use default behavior
            return None, None

        # Clean section heading for use as folder name
        folder_name = self._clean_for_filesystem(sibling_info["section_heading"])

        # Use current page title for filename if available
        if sibling_info["current_page_title"]:
            filename = self._clean_for_filesystem(sibling_info["current_page_title"]) + ".md"
        else:
            filename = None

        return folder_name, filename

    def _clean_for_filesystem(self, text: str) -> str:
        """Clean text for use as folder/file name"""
        import re

        # Remove invalid filesystem characters
        cleaned = re.sub(r'[<>:"|?*]', "", text)

        # Replace forward/backslashes with dashes
        cleaned = re.sub(r"[/\\]", "-", cleaned)

        # Replace multiple spaces with single space
        cleaned = re.sub(r"\s+", " ", cleaned)

        # Remove trailing dots and spaces
        cleaned = cleaned.strip(". ")

        # Limit length
        if len(cleaned) > 100:
            cleaned = cleaned[:97] + "..."

        return cleaned

    def extract_all_navigation_links(self, html: str) -> list[str]:
        """
        Extract all navigation links from the page for discovery purposes
        This includes sibling links and potentially parent/child navigation
        """
        soup = BeautifulSoup(html, "html.parser")
        links = set()

        # Get sibling links
        sibling_info = self.extract_sibling_info(html, "")
        for sibling in sibling_info["siblings"]:
            if sibling["url"]:
                links.add(sibling["url"])

        # Add section heading link if available
        if sibling_info["section_url"]:
            links.add(sibling_info["section_url"])

        # Look for other navigation structures
        # Main navigation tree
        nav_tree = soup.find('[data-testid="page-tree"]')
        if nav_tree:
            for link in nav_tree.find_all("a", href=True):
                url = self._normalize_url(link["href"])
                if url and url.startswith(self.base_url):
                    links.add(url)

        # Breadcrumb navigation
        breadcrumb = soup.find('[aria-label="Breadcrumb"]') or soup.find(".breadcrumb")
        if breadcrumb:
            for link in breadcrumb.find_all("a", href=True):
                url = self._normalize_url(link["href"])
                if url and url.startswith(self.base_url):
                    links.add(url)

        return list(links)
