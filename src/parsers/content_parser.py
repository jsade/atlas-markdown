"""
Content parser for extracting and converting HTML to Markdown
"""

import json
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as md

from .sibling_navigation_parser import SiblingNavigationParser

logger = logging.getLogger(__name__)


class ContentParser:
    """Parses Atlassian documentation pages and converts to Markdown"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.image_urls: set[str] = set()
        self.sibling_parser = SiblingNavigationParser(base_url)

    def extract_content_from_initial_state(self, html: str) -> str | None:
        """Extract content from React initial state if available"""
        soup = BeautifulSoup(html, "html.parser")

        # Look for the React initial state
        for script in soup.find_all("script"):
            if script.string and "__APP_INITIAL_STATE__" in script.string:
                try:
                    # Extract JSON from script
                    match = re.search(
                        r"window\.__APP_INITIAL_STATE__\s*=\s*({.*?});", script.string, re.DOTALL
                    )
                    if match:
                        state_data = json.loads(match.group(1))

                        # Navigate through the state to find content
                        # This path may vary, so we try multiple approaches
                        content = self._find_content_in_state(state_data)
                        if content:
                            return content

                except (json.JSONDecodeError, KeyError) as e:
                    logger.debug(f"Failed to parse initial state: {e}")

        return None

    def _find_content_in_state(self, obj: dict, path: str = "") -> str | None:
        """Recursively search for content in React state"""
        if isinstance(obj, dict):
            # Look for content indicators
            for key in ["body", "content", "articleBody", "html"]:
                if key in obj and isinstance(obj[key], str) and len(obj[key]) > 100:
                    return obj[key]

            # Recurse into nested objects
            for key, value in obj.items():
                if isinstance(value, dict | list):
                    result = self._find_content_in_state(value, f"{path}/{key}")
                    if result:
                        return result

        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                result = self._find_content_in_state(item, f"{path}[{i}]")
                if result:
                    return result

        return None

    def extract_main_content(self, html: str, page_url: str) -> tuple[str | None, str | None, dict]:
        """Extract main content, title, and sibling navigation info from HTML"""
        soup = BeautifulSoup(html, "html.parser")

        # Extract sibling navigation info
        sibling_info = self.sibling_parser.extract_sibling_info(html, page_url)

        # Try to extract from initial state first
        state_content = self.extract_content_from_initial_state(html)
        if state_content:
            # Parse the extracted content
            content_soup = BeautifulSoup(state_content, "html.parser")
        else:
            content_soup = soup

        # Find main content area
        content = None
        content_selectors = [
            '[data-testid="topic-content"]',
            ".ak-renderer-document",
            '[role="main"]',
            "main",
            "#content",
            ".content-body",
        ]

        for selector in content_selectors:
            element = content_soup.select_one(selector)
            if element:
                content = element
                break

        if not content:
            # Fallback: try to find the largest content block
            content = self._find_largest_content_block(content_soup)

        # Extract title
        title = None
        title_selectors = ["h1", '[data-testid="topic-title"]', ".page-title", "title"]

        for selector in title_selectors:
            element = soup.select_one(selector)
            if element:
                title = element.get_text(strip=True)
                if title:
                    break

        # Clean content
        if content:
            self._clean_content(content, page_url)
            return str(content), title, sibling_info
        else:
            logger.warning(f"No main content found for {page_url}")
            return None, title, sibling_info

    def _find_largest_content_block(self, soup: BeautifulSoup) -> Tag | None:
        """Find the largest content block as fallback"""
        candidates = soup.find_all(["div", "article", "section"])

        best_candidate = None
        best_score = 0

        for candidate in candidates:
            # Skip navigation, headers, footers
            if any(
                cls in str(candidate.get("class", []))
                for cls in ["nav", "header", "footer", "sidebar"]
            ):
                continue

            # Score based on text length and paragraph count
            text_length = len(candidate.get_text(strip=True))
            para_count = len(candidate.find_all("p"))
            score = text_length + (para_count * 100)

            if score > best_score:
                best_score = score
                best_candidate = candidate

        return best_candidate

    def _clean_content(self, content: Tag, page_url: str):
        """Clean and prepare content for conversion"""
        # Remove navigation elements
        nav_selectors = [
            "nav",
            '[role="navigation"]',
            ".navigation",
            ".breadcrumb",
            '[data-testid="page-tree"]',
            '[data-testid="navigation"]',
            ".page-navigation",
            ".site-navigation",
            ".global-nav",
            '[aria-label*="navigation"]',
            '[aria-label*="Navigation"]',
        ]
        for selector in nav_selectors:
            for nav in content.select(selector):
                nav.decompose()

        # Remove sidebars and complementary content
        sidebar_selectors = [
            ".sidebar",
            "aside",
            '[role="complementary"]',
            '[data-testid="sidebar"]',
            ".page-sidebar",
            ".toc",
            ".table-of-contents",
            '[aria-label*="sidebar"]',
        ]
        for selector in sidebar_selectors:
            for sidebar in content.select(selector):
                sidebar.decompose()

        # Remove headers and footers
        for element in content.select("header, footer, .header, .footer"):
            element.decompose()

        # Remove scripts and styles
        for element in content.select('script, style, noscript, link[rel="stylesheet"]'):
            element.decompose()

        # Remove edit buttons and internal UI elements
        ui_selectors = [
            '[data-testid*="edit"]',
            ".edit-button",
            ".internal-only",
            '[data-testid*="feedback"]',
            ".feedback",
            ".rating",
            '[data-testid*="share"]',
            ".share-button",
            ".social-share",
            ".banner",
            ".announcement",
            ".alert-banner",
        ]
        for selector in ui_selectors:
            for element in content.select(selector):
                element.decompose()

        # Remove "Was this helpful?" and similar sections
        for element in content.select('[data-testid*="helpful"], .helpful, .vote'):
            element.decompose()

        # Remove related articles that aren't part of main content
        for element in content.select(".related-articles, .see-also, .recommended"):
            # Only remove if it's likely a sidebar/footer element
            parent = element.parent
            if parent and parent.name in ["aside", "footer", "div"]:
                # Check if it's after main content
                main_content = content.select_one('main, article, [role="main"]')
                if main_content and element not in main_content.descendants:
                    element.decompose()

        # Process images
        for img in content.find_all("img"):
            self._process_image(img, page_url)

        # Process links
        for link in content.find_all("a"):
            self._process_link(link, page_url)

    def _process_image(self, img: Tag, page_url: str):
        """Process image tags and collect URLs"""
        src = img.get("src", "")
        if not src:
            return

        # Make URL absolute
        absolute_url = urljoin(page_url, src)
        self.image_urls.add(absolute_url)

        # Add alt text if missing
        if not img.get("alt"):
            img["alt"] = "Image"

    def _process_link(self, link: Tag, page_url: str):
        """Process link tags"""
        href = link.get("href", "")
        if not href:
            return

        # Convert relative URLs to absolute
        if not href.startswith(("http://", "https://", "mailto:", "#")):
            absolute_url = urljoin(page_url, href)
            link["href"] = absolute_url

        # Mark internal links for later conversion to wikilinks
        if href.startswith(("http://", "https://")):
            absolute_url = urljoin(page_url, href)
            if absolute_url.startswith(self.base_url):
                link["data-internal"] = "true"

    def convert_to_markdown(
        self, html_content: str, page_url: str, title: str | None = None
    ) -> str:
        """Convert HTML content to Markdown"""
        # Parse HTML
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove script and style tags before conversion
        for tag in soup(["script", "style"]):
            tag.decompose()

        # Custom conversion options - using default tags instead of specifying convert list
        markdown = md(str(soup), heading_style="ATX", bullets="-", code_language="")

        # Add title if provided
        if title:
            markdown = f"# {title}\n\n{markdown}"

        # Add metadata
        metadata = f"---\nurl: {page_url}\nscrape_date: {self._get_current_date()}\n---\n\n"
        markdown = metadata + markdown

        # Clean up markdown
        markdown = self._clean_markdown(markdown)

        # Convert internal links to wikilinks
        markdown = self._convert_to_wikilinks(markdown, page_url)

        return markdown

    def _convert_to_wikilinks(self, markdown: str, current_page_url: str) -> str:
        """Convert internal links to wikilinks with relative paths"""
        # Pattern to match markdown links: [text](url)
        link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"

        def convert_link(match):
            text = match.group(1)
            url = match.group(2)

            # Skip non-HTTP links (anchors, mailto, etc.)
            if not url.startswith(("http://", "https://")):
                return match.group(0)

            # Check if it's an internal link
            if url.startswith(self.base_url):
                # Extract the path after the base URL
                path = url[len(self.base_url) :].strip("/")

                # Handle different URL patterns
                if "/docs/" in path:
                    # Extract the document slug
                    doc_slug = path.split("/docs/")[-1].strip("/")
                    # Convert to wikilink format
                    return f"[[{doc_slug}|{text}]]"
                elif "/resources/" in path:
                    # Extract the resource slug
                    resource_slug = path.split("/resources/")[-1].strip("/")
                    # Convert to wikilink format with resources prefix
                    return f"[[resources/{resource_slug}|{text}]]"
                else:
                    # For other internal links, use the full path
                    return f"[[{path}|{text}]]"

            # Keep external links as-is
            return match.group(0)

        # Apply the conversion
        markdown = re.sub(link_pattern, convert_link, markdown)

        return markdown

    def _clean_markdown(self, markdown: str) -> str:
        """Clean up converted markdown"""
        # Remove excessive blank lines
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)

        # Fix spacing around headers
        markdown = re.sub(r"(\n#{1,6} )", r"\n\n\1", markdown)
        markdown = re.sub(r"(#{1,6} .+)\n(?!\n)", r"\1\n\n", markdown)

        # Fix list formatting
        markdown = re.sub(r"(\n)- ", r"\1\n- ", markdown)
        markdown = re.sub(r"(\n)\d+\. ", r"\1\n1. ", markdown)

        # Remove trailing whitespace
        markdown = "\n".join(line.rstrip() for line in markdown.split("\n"))

        return markdown

    def _convert_to_wikilinks(self, markdown: str, current_page_url: str) -> str:
        """Convert internal links to wikilinks with relative paths"""

        # Pattern to match markdown links: [text](url)
        link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"

        def convert_link(match):
            text = match.group(1)
            url = match.group(2)

            # Skip non-HTTP links (anchors, mailto, etc.)
            if not url.startswith(("http://", "https://")):
                return match.group(0)

            # Check if it's an internal link
            if url.startswith(self.base_url):
                # Remove any trailing slash from URL
                clean_url = url.rstrip("/")
                base_url_clean = self.base_url.rstrip("/")

                # Extract the path after the base URL
                if clean_url == base_url_clean:
                    # Link to homepage
                    return f"[[index|{text}]]"

                path = clean_url[len(base_url_clean) :].strip("/")

                # Handle different URL patterns
                if path.startswith("docs/"):
                    # Extract the document slug (everything after docs/)
                    doc_slug = path[5:]  # Remove 'docs/' prefix
                    if doc_slug:
                        # Use just the slug name for cleaner wikilinks
                        return f"[[{doc_slug}|{text}]]"
                    else:
                        return f"[[docs/index|{text}]]"
                elif path.startswith("resources/"):
                    # Extract the resource slug
                    resource_slug = path[10:]  # Remove 'resources/' prefix
                    if resource_slug:
                        # Keep resources prefix for clarity
                        return f"[[resources/{resource_slug}|{text}]]"
                    else:
                        return f"[[resources/index|{text}]]"
                else:
                    # For other internal links, use the full path
                    return f"[[{path}|{text}]]"

            # Keep external links as-is
            return match.group(0)

        # Apply the conversion
        markdown = re.sub(link_pattern, convert_link, markdown)

        return markdown.strip()

    def _get_current_date(self) -> str:
        """Get current date in ISO format"""
        from datetime import datetime

        return datetime.now().isoformat()

    def get_images(self) -> set[str]:
        """Get all discovered image URLs"""
        return self.image_urls

    def get_navigation_links(self, html: str) -> list[str]:
        """Get all navigation links from the page"""
        return self.sibling_parser.extract_all_navigation_links(html)

    def update_image_references(self, markdown: str, image_map: dict[str, str]) -> str:
        """Update image URLs in markdown to local paths"""
        for original_url, local_path in image_map.items():
            # Escape special regex characters in URL
            escaped_url = re.escape(original_url)
            # Replace in markdown image syntax
            markdown = re.sub(
                f"!\\[([^\\]]*)\\]\\({escaped_url}\\)", f"![\\1]({local_path})", markdown
            )
            # Also replace in HTML img tags if any remain
            markdown = re.sub(f'src="{escaped_url}"', f'src="{local_path}"', markdown)

        return markdown

    def _convert_to_wikilinks(self, markdown: str, current_page_url: str) -> str:
        """Convert internal links to wikilinks with relative paths"""
        # Pattern to match markdown links: [text](url)
        link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"

        def convert_link(match):
            text = match.group(1)
            url = match.group(2)

            # Skip non-HTTP links (anchors, mailto, etc.)
            if not url.startswith(("http://", "https://")):
                return match.group(0)

            # Check if it's an internal link
            if url.startswith(self.base_url):
                # Extract the path after the base URL
                path = url[len(self.base_url) :].strip("/")

                # Handle different URL patterns
                if "/docs/" in path:
                    # Extract the document slug
                    doc_slug = path.split("/docs/")[-1].strip("/")
                    # Convert to wikilink format
                    return f"[[{doc_slug}|{text}]]"
                elif "/resources/" in path:
                    # Extract the resource slug
                    resource_slug = path.split("/resources/")[-1].strip("/")
                    # Convert to wikilink format with resources prefix
                    return f"[[resources/{resource_slug}|{text}]]"
                else:
                    # For other internal links, use the full path
                    return f"[[{path}|{text}]]"

            # Keep external links as-is
            return match.group(0)

        # Apply the conversion
        markdown = re.sub(link_pattern, convert_link, markdown)

        return markdown
