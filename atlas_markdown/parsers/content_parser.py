"""
Content parser for extracting and converting HTML to Markdown
"""

import json
import logging
import re
from typing import Any, cast
from urllib.parse import urljoin, urlparse

import yaml
from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as md

from ..utils.yaml_formatter import fix_yaml_list_formatting
from .sibling_navigation_parser import SiblingNavigationParser

logger = logging.getLogger(__name__)


class ContentParser:
    """Parses Atlassian documentation pages and converts to Markdown"""

    def __init__(self, base_url: str, no_h1_headings: bool = False):
        self.base_url = base_url.rstrip("/")
        self.image_urls: set[str] = set()
        self.sibling_parser = SiblingNavigationParser(base_url)
        self.no_h1_headings = no_h1_headings

    async def extract_main_content_from_page(
        self, page: Any, page_url: str
    ) -> tuple[str | None, str | None, dict[str, Any]]:
        """Extract main content, title, and sibling navigation info from Playwright page"""
        # Extract sibling navigation info with "Show more" handling
        sibling_info = await self.sibling_parser.extract_sibling_info_from_page(page, page_url)

        # Get the HTML content after clicking show more
        html = await page.content()

        # Extract content without sibling info (we already have it)
        content_html, title = self._extract_content_and_title(html, page_url)

        # Add breadcrumb data to sibling info
        soup = BeautifulSoup(html, "html.parser")
        breadcrumb_data = self._extract_breadcrumb_data(soup)
        if breadcrumb_data:
            sibling_info["breadcrumb_data"] = breadcrumb_data

        # Always use the extracted title (preferring H1) as the current page title
        # This ensures we use the actual page title, not the section heading
        if title:
            sibling_info["current_page_title"] = title
            logger.info(f"Set current_page_title from extracted title: {title}")
        else:
            logger.warning(f"No title extracted for {page_url}")

        # Return with the updated sibling info
        return content_html, title, sibling_info

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

    def _find_content_in_state(self, obj: dict[Any, Any] | list[Any], path: str = "") -> str | None:
        """Recursively search for content in React state"""
        if isinstance(obj, dict):
            # Look for content indicators
            for key in ["body", "content", "articleBody", "html"]:
                if key in obj and isinstance(obj[key], str) and len(obj[key]) > 100:
                    return str(obj[key])

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

    def _extract_metadata_from_initial_state(self, html: str) -> dict[str, str | None]:
        """Extract title and description from React initial state"""
        metadata: dict[str, str | None] = {"title": None, "description": None}
        soup = BeautifulSoup(html, "html.parser")

        # Look for the React initial state
        for script in soup.find_all("script"):
            if script.string and "__APP_INITIAL_STATE__" in script.string:
                try:
                    # Extract JSON from script
                    match = re.search(
                        r"window\.__APP_INITIAL_STATE__\s*=\s*(/\*.*?\*/\s*)?({.*?});",
                        script.string,
                        re.DOTALL,
                    )
                    if match:
                        json_str = match.group(2)
                        # Remove comments if present
                        json_str = re.sub(r"/\*.*?\*/", "", json_str, flags=re.DOTALL)
                        state_data = json.loads(json_str)

                        # Use the initial state parser to extract metadata
                        from ..parsers.initial_state_parser import InitialStateParser

                        parser = InitialStateParser(self.base_url)
                        metadata = parser.extract_topic_metadata(state_data)
                        if metadata["title"]:
                            logger.debug(f"Found title from initial state: {metadata['title']}")
                        if metadata["description"]:
                            logger.debug(
                                f"Found description from initial state: {metadata['description']}"
                            )

                except (json.JSONDecodeError, KeyError) as e:
                    logger.debug(f"Failed to parse initial state for metadata: {e}")

        return metadata

    def _extract_content_and_title(self, html: str, page_url: str) -> tuple[str | None, str | None]:
        """Extract main content and title from HTML (internal method without sibling info)"""
        soup = BeautifulSoup(html, "html.parser")

        # First try to get metadata from initial state
        state_metadata = self._extract_metadata_from_initial_state(html)
        title_from_state = state_metadata["title"]
        self.current_page_description = state_metadata["description"]  # Store for later use

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

        # Extract H1 as the primary source of truth for page title
        h1_title = None
        h1_element = content_soup.select_one("h1")
        if h1_element:
            h1_title = h1_element.get_text(strip=True)
            logger.debug(f"Found H1 title: {h1_title}")

        # Use H1 as primary title source, then fall back to other sources
        title = h1_title

        # If no H1, use title from initial state if available
        if not title:
            title = title_from_state

        # If still no title, try meta tag
        if not title:
            title = self._extract_meta_title(soup)

        # Final fallback to other selectors
        if not title:
            title_selectors = ['[data-testid="topic-title"]', ".page-title", "title"]
            for selector in title_selectors:
                element = soup.select_one(selector)
                if element:
                    title = element.get_text(strip=True)
                    if title:
                        break

        # Clean content
        if content:
            self._clean_content(content, page_url)
            return str(content), title
        else:
            logger.warning(f"No main content found for {page_url}")
            return None, title

    def extract_main_content(
        self, html: str, page_url: str
    ) -> tuple[str | None, str | None, dict[str, Any]]:
        """Extract main content, title, and sibling navigation info from HTML"""
        # Extract sibling navigation info
        sibling_info = self.sibling_parser.extract_sibling_info(html, page_url)

        # Extract content and title
        content_html, title = self._extract_content_and_title(html, page_url)

        # Add breadcrumb data to sibling info
        soup = BeautifulSoup(html, "html.parser")
        breadcrumb_data = self._extract_breadcrumb_data(soup)
        if breadcrumb_data:
            sibling_info["breadcrumb_data"] = breadcrumb_data

        return content_html, title, sibling_info

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

    def _extract_meta_title(self, soup: BeautifulSoup) -> str | None:
        """Extract title from meta tag with itemprop='name'"""
        meta_tag = soup.find("meta", {"itemprop": "name"})
        if meta_tag and isinstance(meta_tag, Tag):
            content = meta_tag.get("content")
            if content and isinstance(content, str):
                return content.strip()
        return None

    def _extract_breadcrumb_data(self, soup: BeautifulSoup) -> dict[str, Any] | None:
        """Extract breadcrumb data from JSON-LD script"""
        import json

        # Find script with breadcrumb data
        scripts = soup.find_all("script", {"type": "application/ld+json"})

        for script in scripts:
            if script.string:
                try:
                    data = json.loads(script.string)
                    if data.get("@type") == "BreadcrumbList":
                        breadcrumbs = []
                        items = data.get("itemListElement", [])

                        # Sort by position to ensure correct order
                        items.sort(key=lambda x: x.get("position", 0))

                        for item in items:
                            if "item" in item:
                                breadcrumb = {
                                    "position": item.get("position"),
                                    "name": item["item"].get("name", ""),
                                    "url": item["item"].get("@id", ""),
                                }
                                breadcrumbs.append(breadcrumb)

                        return {
                            "breadcrumbs": breadcrumbs,
                            "parent": breadcrumbs[-2] if len(breadcrumbs) > 1 else None,
                            "current": breadcrumbs[-1] if breadcrumbs else None,
                        }
                except (json.JSONDecodeError, KeyError) as e:
                    logger.debug(f"Failed to parse breadcrumb JSON-LD: {e}")
                    continue

        return None

    def _clean_content(self, content: Tag, page_url: str) -> None:
        """Clean and prepare content for conversion"""
        # First, remove any content before the first H1
        h1 = content.find("h1")
        if h1:
            # Find the container that holds the H1 and remove everything before it
            # We need to go up the tree to find siblings at the appropriate level
            h1_container = h1.parent

            # Keep going up until we find a container that has siblings before it
            while (
                h1_container
                and h1_container != content
                and len(list(h1_container.previous_siblings)) == 0
            ):
                h1_container = h1_container.parent

            if h1_container and h1_container != content:
                # Remove all content before the H1 container
                removed_count = 0
                for element in list(h1_container.previous_siblings):
                    if isinstance(element, Tag) and hasattr(element, "decompose"):
                        element.decompose()
                        removed_count += 1
                    elif isinstance(element, str) and element.strip():
                        element.extract()
                        removed_count += 1

                if removed_count > 0:
                    logger.debug(
                        f"Removed {removed_count} elements before H1 container for {page_url}"
                    )

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

        # Convert panel elements to Obsidian callouts before other processing
        panel_elements = content.select("div[data-panel-type]")
        for panel in panel_elements:
            panel_type = panel.get("data-panel-type", "info")

            # Extract content from the panel
            content_div = panel.select_one(".ak-editor-panel__content")
            if content_div:
                # Create a new div with special marker for callout conversion
                from bs4 import BeautifulSoup

                temp_soup = BeautifulSoup("", "html.parser")
                callout_div = temp_soup.new_tag("div")
                callout_div["data-obsidian-callout"] = panel_type

                # Move all content from panel to the new div
                for child in list(content_div.children):
                    callout_div.append(child)

                # Replace the panel with our marker div
                panel.replace_with(callout_div)
                logger.debug(f"Converted {panel_type} panel to callout marker for {page_url}")

        # Remove Confluence macro elements (details, expand, etc.)
        details_elements = content.select('div[data-macro-name="details"]')
        if details_elements:
            logger.debug(f"Removing {len(details_elements)} details macro elements from {page_url}")
            for element in details_elements:
                element.decompose()

        # Also remove other common Confluence macros
        macro_elements = content.select("div[data-macro-name]")
        removed_macros: list[str] = []
        for element in macro_elements:
            macro_name_attr = element.get("data-macro-name", "")
            macro_name = macro_name_attr if isinstance(macro_name_attr, str) else ""
            if macro_name in ["details", "expand", "info", "warning", "note", "panel"]:
                removed_macros.append(macro_name)
                element.decompose()

        if removed_macros:
            logger.debug(
                f"Removed Confluence macros from {page_url}: {', '.join(list(set(removed_macros)))}"
            )

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

    def _process_image(self, img: Tag, page_url: str) -> None:
        """Process image tags and collect URLs"""
        src = img.get("src", "")
        if isinstance(src, list):
            src = src[0] if src else ""
        if not src:
            return

        # Handle protocol-relative URLs (e.g., //example.com/image.jpg)
        if src.startswith("//"):
            # Extract protocol from page_url and prepend it
            from urllib.parse import urlparse

            parsed_page = urlparse(page_url)
            absolute_url = f"{parsed_page.scheme}:{src}"
            # Update the img tag to use absolute URL for markdown conversion
            img["src"] = absolute_url
        else:
            # Make URL absolute for regular URLs
            absolute_url = urljoin(page_url, src)
            # Update the img tag if it was relative
            if not src.startswith(("http://", "https://")):
                img["src"] = absolute_url

        self.image_urls.add(absolute_url)

        # Add alt text if missing
        if not img.get("alt"):
            img["alt"] = "Image"

    def _process_link(self, link: Tag, page_url: str) -> None:
        """Process link tags"""
        href = link.get("href", "")
        if isinstance(href, list):
            href = href[0] if href else ""
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
        self,
        html_content: str,
        page_url: str,
        title: str | None = None,
        page_metadata: dict[str, Any] | None = None,
        sibling_info: dict[str, Any] | None = None,
        disable_tags: bool = False,
    ) -> str:
        """Convert HTML content to Markdown with enhanced frontmatter"""
        # Parse HTML
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove script and style tags before conversion
        for tag in soup(["script", "style"]):
            tag.decompose()

        # IMPORTANT: Re-apply the H1 cleaning here since we have a new soup object
        # The cleaning done in _extract_content_and_title was on a different object
        h1 = soup.find("h1")
        if h1:
            # Find the container that holds the H1 and remove everything before it
            # We need to go up the tree to find siblings at the appropriate level
            h1_container = h1.parent

            # Keep going up until we find a container that has siblings before it
            while h1_container and len(list(h1_container.previous_siblings)) == 0:
                h1_container = h1_container.parent

            if h1_container:
                # Remove all content before the H1 container
                removed_count = 0
                for element in list(h1_container.previous_siblings):
                    if isinstance(element, Tag) and hasattr(element, "decompose"):
                        element.decompose()
                        removed_count += 1
                    elif isinstance(element, str) and element.strip():
                        element.extract()
                        removed_count += 1

                if removed_count > 0:
                    logger.debug(
                        f"Removed {removed_count} elements before H1 container in markdown conversion for {page_url}"
                    )

        # Remove H1 tags if no_h1_headings is True
        if self.no_h1_headings:
            for h1 in soup.find_all("h1"):
                h1.decompose()

        # Convert panel divs to Obsidian callouts before markdown conversion
        for panel in soup.select("div[data-obsidian-callout]"):
            callout_attr = panel.get("data-obsidian-callout", "info")
            callout_type = callout_attr if isinstance(callout_attr, str) else "info"

            # Map panel types to Obsidian callout types
            type_mapping = {
                "info": "info",
                "warning": "warning",
                "error": "error",
                "success": "success",
                "note": "note",
            }

            obsidian_type = type_mapping.get(callout_type, "info")

            # Create a blockquote with the callout syntax
            blockquote = soup.new_tag("blockquote")
            blockquote["class"] = "obsidian-callout"

            # Add the callout header
            header = soup.new_tag("p")
            header.string = f"[!{obsidian_type}]"
            blockquote.append(header)

            # Move all content from panel to blockquote
            for child in list(panel.children):
                blockquote.append(child)

            # Replace panel with blockquote
            panel.replace_with(blockquote)

        # Custom conversion options - using default tags instead of specifying convert list
        markdown: str = cast(str, md(str(soup), heading_style="ATX", bullets="-", code_language=""))

        # Only add title as H1 if it's not already in the content and no_h1_headings is False
        if title and not soup.find("h1") and not self.no_h1_headings:
            markdown = f"# {title}\n\n{markdown}"

        # Build enhanced frontmatter
        frontmatter: dict[str, Any] = {"url": page_url, "scrape_date": self._get_current_date()}

        # Add metadata from initial state if available
        if page_metadata:
            if page_metadata.get("title"):
                frontmatter["title"] = page_metadata["title"]
            if page_metadata.get("description"):
                frontmatter["description"] = page_metadata["description"]
            if page_metadata.get("id"):
                frontmatter["id"] = page_metadata["id"]
            if page_metadata.get("slug"):
                frontmatter["slug"] = page_metadata["slug"]
            if page_metadata.get("childList"):
                frontmatter["childList"] = page_metadata["childList"]

        # Also add description from current page extraction if available
        if hasattr(self, "current_page_description") and self.current_page_description:
            if not frontmatter.get("description"):
                frontmatter["description"] = self.current_page_description

        # Extract product from URL
        product = self._extract_product_from_url(page_url)

        # Add tags if not disabled
        if not disable_tags and sibling_info:
            tags = self._generate_hierarchical_tags(sibling_info, product)

            # Enhance tags with semantic content analysis if enabled
            if tags and html_content:
                # Check if content analysis is enabled (default: true)
                import os

                enable_content_analysis = (
                    os.getenv("ATLAS_MD_ENABLE_CONTENT_ANALYSIS", "true").lower() == "true"
                )

                if enable_content_analysis:
                    enhanced_tags = self._analyze_page_content(html_content, tags)
                    tags = enhanced_tags

            if tags:
                frontmatter["tags"] = tags

        # Always add Atlas Markdown metadata
        frontmatter["atlas_md_version"] = self._get_atlas_md_version()
        frontmatter["atlas_md_url"] = "https://github.com/jsade/atlas-markdown"
        frontmatter["atlas_md_product"] = product

        # Add category and section from sibling info
        if sibling_info:
            # Extract category from breadcrumbs
            if breadcrumb_data := sibling_info.get("breadcrumb_data"):
                breadcrumbs = breadcrumb_data.get("breadcrumbs", [])
                # Category is typically the third breadcrumb (after "Atlassian Support" and product)
                if len(breadcrumbs) > 2:
                    frontmatter["atlas_md_category"] = breadcrumbs[2].get("name", "")

            # Section from section heading
            if section := sibling_info.get("section_heading"):
                frontmatter["atlas_md_section"] = section

        # Format frontmatter as YAML
        metadata_str: str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)

        # Fix YAML formatting issue using shared utility
        metadata_str = fix_yaml_list_formatting(metadata_str)

        markdown = f"---\n{metadata_str}---\n\n{markdown}"

        # Clean up markdown
        markdown = self._clean_markdown(markdown)

        # Convert internal links to wikilinks
        markdown = self._convert_to_wikilinks(markdown, page_url)

        # Remove H1 headings if no_h1_headings is True
        if self.no_h1_headings:
            markdown = self._remove_h1_headings(markdown)

        return markdown

    def _convert_to_wikilinks(self, markdown: str, current_page_url: str) -> str:
        """Convert internal links to wikilinks with relative paths"""
        # Pattern to match markdown links: [text](url) or [text](url "title")
        # This captures URLs that might have title attributes
        link_pattern = r'\[([^\]]+)\]\(([^"\s)]+)(?:\s*"[^"]*")?\)'

        def convert_link(match: re.Match[str]) -> str:
            text = match.group(1)
            url = match.group(2)

            # Clean the URL - remove any quotes or extra characters
            url = url.strip().strip("\"'")

            # Skip non-HTTP links (anchors, mailto, etc.)
            if not url.startswith(("http://", "https://")):
                return match.group(0)

            # Check if it's an internal link
            if url.startswith(self.base_url):
                # Extract the path after the base URL
                path = url[len(self.base_url) :].strip("/")

                # Clean the path - remove any trailing quotes or special characters
                path = path.rstrip("/\"'")

                # Handle different URL patterns
                if path.startswith("docs/"):
                    # Extract the document slug (remove "docs/" prefix)
                    doc_slug = path[5:].strip("/")
                    # Clean the slug
                    doc_slug = doc_slug.rstrip("/\"'")
                    # Convert to wikilink format
                    return f"[[{doc_slug}|{text}]]"
                elif path.startswith("resources/"):
                    # Extract the resource slug (remove "resources/" prefix)
                    resource_slug = path[10:].strip("/")
                    # Clean the slug
                    resource_slug = resource_slug.rstrip("/\"'")
                    # Convert to wikilink format with resources prefix
                    return f"[[resources/{resource_slug}|{text}]]"
                else:
                    # For other internal links, use the full path
                    path = path.rstrip("/\"'")
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

    def _remove_h1_headings(self, markdown: str) -> str:
        """Remove all H1 headings from markdown"""
        lines = markdown.split("\n")
        filtered_lines = []

        for line in lines:
            # Skip lines that are H1 headings (# at start, but not ##, ###, etc.)
            if re.match(r"^#\s+", line) and not re.match(r"^#{2,}\s+", line):
                # Skip this H1 line
                continue
            filtered_lines.append(line)

        # Join back and clean up any resulting excessive blank lines
        result = "\n".join(filtered_lines)
        result = re.sub(r"\n{3,}", "\n\n", result)

        return result

    def _fix_malformed_wikilinks(self, markdown: str, current_page_url: str) -> str:
        """Fix malformed wikilinks with URLs in them"""

        # First fix any malformed wikilinks with URLs in them
        # Pattern: [[slug/ "url"|text]] or [[slug/"|text]]
        malformed_pattern = r'\[\[([^|\]]+?)/?(?:\s*"[^"|\]]*")?\|([^\]]+)\]\]'

        def fix_malformed(match: re.Match[str]) -> str:
            slug = match.group(1).strip().rstrip('/"')
            text = match.group(2)
            # Convert slug to proper filename
            if slug:
                file_name = self._url_slug_to_filename(slug)
                return f"[[{file_name}|{text}]]"
            return match.group(0)

        markdown = re.sub(malformed_pattern, fix_malformed, markdown)

        # Pattern to match markdown links: [text](url) or [text](url "title")
        link_pattern = r'\[([^\]]+)\]\(([^"\s)]+)(?:\s*"[^"]*")?\)'

        def convert_link(match: re.Match[str]) -> str:
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
                        # Convert URL slug to proper file name format
                        # e.g., "create-a-service" → "Create a Service"
                        file_name = self._url_slug_to_filename(doc_slug)
                        return f"[[{file_name}|{text}]]"
                    else:
                        return f"[[docs/index|{text}]]"
                elif path.startswith("resources/"):
                    # Extract the resource slug
                    resource_slug = path[10:]  # Remove 'resources/' prefix
                    if resource_slug:
                        # Keep resources prefix for clarity
                        file_name = self._url_slug_to_filename(resource_slug)
                        return f"[[resources/{file_name}|{text}]]"
                    else:
                        return f"[[resources/index|{text}]]"
                else:
                    # For other internal links, use the full path
                    file_name = self._url_slug_to_filename(path)
                    return f"[[{file_name}|{text}]]"

            # Keep external links as-is
            return match.group(0)

        # Apply the conversion
        markdown = re.sub(link_pattern, convert_link, markdown)

        return markdown.strip()

    def _url_slug_to_filename(self, slug: str) -> str:
        """Convert URL slug to proper filename format
        e.g., "create-a-service" → "Create a service"
        """
        # Common words that should stay lowercase (except first word)
        lowercase_words = {
            "a",
            "an",
            "and",
            "as",
            "at",
            "by",
            "for",
            "from",
            "in",
            "is",
            "of",
            "on",
            "or",
            "the",
            "to",
            "with",
        }

        # Split by hyphens
        words = slug.split("-")

        # Process each word
        result = []
        for i, word in enumerate(words):
            if word:
                # First word or not in lowercase list - capitalize
                if i == 0 or word.lower() not in lowercase_words:
                    result.append(word.capitalize())
                else:
                    result.append(word.lower())

        return " ".join(result)

    def _get_current_date(self) -> str:
        """Get current date in ISO format"""
        from datetime import datetime

        return datetime.now().isoformat()

    def _extract_product_from_url(self, url: str) -> str:
        """Extract product identifier from base URL"""
        # Parse the URL
        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")

        # If the URL is like https://support.atlassian.com/jira-service-management-cloud/...
        # The product would be the first path component
        if path_parts:
            return path_parts[0]

        # Fallback to extracting from base_url
        base_parsed = urlparse(self.base_url)
        base_parts = base_parsed.path.strip("/").split("/")
        if base_parts:
            return base_parts[0]

        return "unknown"

    def _normalize_tag(self, text: str) -> str:
        """Convert text to lowercase hyphenated tag format"""
        if not text:
            return ""

        # Convert to lowercase
        text = text.lower()

        # Replace special characters and spaces with hyphens
        text = re.sub(r"[^a-z0-9]+", "-", text)

        # Remove leading/trailing hyphens
        text = text.strip("-")

        # Replace multiple hyphens with single hyphen
        text = re.sub(r"-+", "-", text)

        return text

    def _generate_hierarchical_tags(self, sibling_info: dict[str, Any], product: str) -> list[str]:
        """Generate tags from navigation hierarchy"""
        tags = []

        # Always include product as first tag
        if product and product != "unknown":
            tags.append(product)

        # Extract meaningful category tags based on common documentation patterns
        # This is more useful than just copying the page slug
        current_title = (sibling_info.get("current_page_title") or "").lower()
        section = (sibling_info.get("section_heading") or "").lower()

        # Define category mappings for common documentation sections
        category_keywords = {
            "getting-started": ["getting started", "quick start", "overview", "introduction"],
            "administration": [
                "admin",
                "administration",
                "configure",
                "configuration",
                "settings",
                "setup",
            ],
            "user-management": [
                "user",
                "users",
                "team",
                "teams",
                "member",
                "permission",
                "access",
                "role",
            ],
            "api": ["api", "rest", "webhook", "integration", "developer"],
            "security": ["security", "auth", "authentication", "sso", "saml", "oauth"],
            "automation": ["automation", "automate", "workflow", "rule", "trigger"],
            "reporting": ["report", "analytics", "dashboard", "metrics", "statistics"],
            "troubleshooting": ["troubleshoot", "error", "issue", "problem", "fix"],
            "billing": ["billing", "payment", "subscription", "pricing", "plan"],
            "migration": ["migration", "import", "export", "backup", "restore"],
        }

        # Check both title and section for category keywords
        text_to_check = f"{current_title} {section}"

        for category, keywords in category_keywords.items():
            if any(keyword in text_to_check for keyword in keywords):
                if category not in tags:
                    tags.append(category)
                    # Only add 1-2 category tags to keep it focused
                    if len(tags) >= 3:
                        break

        # If we still only have the product tag, try to extract from breadcrumbs
        if len(tags) == 1 and (breadcrumb_data := sibling_info.get("breadcrumb_data")):
            breadcrumbs = breadcrumb_data.get("breadcrumbs", [])
            # Look for intermediate breadcrumbs (skip first 2 and last 1)
            for crumb in breadcrumbs[2:-1]:
                if name := crumb.get("name"):
                    tag = self._normalize_tag(name)
                    # Only add if it's short and meaningful (not a long page title)
                    if tag and tag not in tags and len(tag.split("-")) <= 3:
                        tags.append(tag)
                        break

        # Add section heading as last resort if we need more tags
        if len(tags) < 3 and section:
            normalized = self._normalize_tag(section)
            # Only add if it's concise and not already in tags
            if normalized and normalized not in tags and len(normalized.split("-")) <= 3:
                tags.append(normalized)

        return tags

    def _get_atlas_md_version(self) -> str:
        """Get current Atlas Markdown version"""
        try:
            from atlas_markdown import __version__

            return __version__
        except ImportError:
            return "unknown"

    def _analyze_page_content(self, html_content: str, current_tags: list[str]) -> list[str]:
        """Analyze page content for semantic tags using local NLP techniques"""
        # Extract text content from HTML
        soup = BeautifulSoup(html_content, "html.parser")

        # 1. Extract emphasized content (headers, bold, code blocks)
        important_text = []
        for tag in soup.find_all(["h2", "h3", "h4", "strong", "em", "code"]):
            text = tag.get_text(strip=True)
            if text:
                important_text.append(text)

        # 2. Extract technical terms from lists (often contain features/options)
        for ul in soup.find_all("ul"):
            for li in ul.find_all("li"):
                text = li.get_text(strip=True)[:100]  # First 100 chars of list items
                if text:
                    important_text.append(text)

        # 3. Pattern-based extraction
        full_text = soup.get_text()
        detected_categories = set()

        # Extract technical patterns if enabled
        import os

        enable_technical_patterns = (
            os.getenv("ATLAS_MD_TECHNICAL_PATTERNS", "true").lower() == "true"
        )

        if enable_technical_patterns:
            technical_patterns = self._extract_technical_patterns(full_text)
            detected_categories.update(technical_patterns)

        # 4. Frequency-based importance scoring
        # Count occurrences of technical terms (excluding common words)
        word_freq: dict[str, int] = {}
        technical_terms = []

        # Define common words to exclude
        common_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "as",
            "is",
            "was",
            "are",
            "were",
            "been",
            "be",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "can",
            "this",
            "that",
            "these",
            "those",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "them",
            "their",
            "what",
            "which",
            "who",
            "when",
            "where",
            "why",
            "how",
            "all",
            "each",
            "every",
            "some",
            "any",
            "many",
            "few",
            "more",
            "most",
            "other",
            "such",
            "only",
            "own",
            "same",
            "so",
            "than",
            "too",
            "very",
            "just",
            "then",
            "now",
            "also",
        }

        # Simple tokenization and filtering
        words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]+\b", " ".join(important_text))
        for word in words:
            if len(word) > 3 and word.lower() not in common_words:
                word_lower = word.lower()
                word_freq[word_lower] = word_freq.get(word_lower, 0) + 1

        # Get top technical terms
        import os

        min_term_frequency = int(os.getenv("ATLAS_MD_MIN_TERM_FREQUENCY", "3"))

        sorted_terms = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        for term, freq in sorted_terms[:5]:
            if freq >= min_term_frequency and self._normalize_tag(term) not in current_tags:
                technical_terms.append(self._normalize_tag(term))

        # 5. Combine results
        enhanced_tags = list(current_tags)

        # Add detected categories
        for category in detected_categories:
            if category not in enhanced_tags:
                enhanced_tags.append(category)

        # Add top technical terms
        for term in technical_terms[:2]:  # Add top 2 technical terms
            if term not in enhanced_tags:
                enhanced_tags.append(term)

        # Limit total tags based on configuration
        max_tags = int(os.getenv("ATLAS_MD_MAX_TAGS", "10"))
        return enhanced_tags[:max_tags]

    def _extract_technical_patterns(self, text: str) -> set[str]:
        """Extract technical patterns like API endpoints, config files, CLI commands"""
        detected_categories = set()

        # Define patterns for different technical content types
        patterns = {
            "api-reference": r"/api/[^\s]+|REST API|webhook|endpoint|HTTP method|GET /|POST /|PUT /|DELETE /",
            "configuration-guide": r"\.yml|\.yaml|\.json|\.properties|configuration file|config\.|settings\.|config\.yml|config\.yaml",
            "cli-usage": r"--[a-z-]+|atlas-markdown|npm run|pip install|bash|shell command|\$\s*\w+",
            "integration-guide": r"integrate with|integration|connector|plugin|third-party|external service",
            "permissions-setup": r"permission|role|access control|admin|viewer|RBAC|authorization",
            "code-examples": r"```\w+|function\s+\w+|class\s+\w+|def\s+\w+|import\s+\w+|require\(",
            "database-guide": r"SQL|query|database|table|schema|index|migration|JOIN|SELECT|INSERT",
            "docker-guide": r"docker|container|dockerfile|docker-compose|image|volume|port\s*:\s*\d+",
            "kubernetes-guide": r"kubernetes|k8s|pod|deployment|service|ingress|kubectl|helm",
            "monitoring-guide": r"monitoring|metrics|logs|alerts|dashboard|prometheus|grafana|datadog",
        }

        for category, pattern in patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                detected_categories.add(category)

        return detected_categories

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

            # Replace in standard markdown image syntax ![alt](url)
            markdown = re.sub(
                f"!\\[([^\\]]*)\\]\\({escaped_url}\\)", f"![[{local_path}]]", markdown
            )

            # Also handle protocol-relative URLs
            if original_url.startswith("https://"):
                protocol_relative = original_url.replace("https://", "//", 1)
                escaped_protocol_relative = re.escape(protocol_relative)
                # Replace in standard markdown syntax with protocol-relative URL
                markdown = re.sub(
                    f"!\\[([^\\]]*)\\]\\({escaped_protocol_relative}\\)",
                    f"![[{local_path}]]",
                    markdown,
                )
            elif original_url.startswith("http://"):
                protocol_relative = original_url.replace("http://", "//", 1)
                escaped_protocol_relative = re.escape(protocol_relative)
                # Replace in standard markdown syntax with protocol-relative URL
                markdown = re.sub(
                    f"!\\[([^\\]]*)\\]\\({escaped_protocol_relative}\\)",
                    f"![[{local_path}]]",
                    markdown,
                )

            # Replace in wiki-style image syntax ![[url|alt]]
            markdown = re.sub(
                f"!\\[\\[{escaped_url}\\|([^\\]]*)\\]\\]", f"![[{local_path}]]", markdown
            )

            # Also replace in HTML img tags if any remain
            markdown = re.sub(f'src="{escaped_url}"', f'src="{local_path}"', markdown)

        return markdown
