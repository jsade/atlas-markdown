"""
Link resolver for mapping URLs to actual filenames
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, Match

logger = logging.getLogger(__name__)


class LinkResolver:
    """Resolves internal links to actual filenames"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.url_to_filename_map: Dict[str, str] = {}
        self.title_to_filename_map: Dict[str, str] = {}

    def add_page_mapping(self, url: str, title: str, file_path: str) -> None:
        """Add a mapping from URL and title to actual filename"""
        # Extract just the filename from the full path
        if file_path:
            filename = Path(file_path).stem  # Remove .md extension
            self.url_to_filename_map[url.rstrip("/")] = filename

            if title:
                # Also map by title for fallback
                self.title_to_filename_map[title.lower()] = filename

            logger.debug(f"Added mapping: {url} -> {filename}")

    def resolve_url_to_wikilink(self, url: str, link_text: str) -> str:
        """Convert a URL to a wiki link using the actual filename"""
        # Clean the URL
        clean_url = url.rstrip("/")

        # Check if it's an internal link
        if not clean_url.startswith(self.base_url):
            # External link - keep as markdown
            return f"[{link_text}]({url})"

        # Check if we have a direct mapping for this URL
        if clean_url in self.url_to_filename_map:
            filename = self.url_to_filename_map[clean_url]
            return f"[[{filename}|{link_text}]]"

        # Try to extract path and check partial mappings
        base_url_clean = self.base_url.rstrip("/")
        if clean_url == base_url_clean:
            return f"[[index|{link_text}]]"

        # Extract path after base URL
        path = clean_url[len(base_url_clean) :].strip("/")

        # Try different URL patterns
        docs_url = f"{base_url_clean}/docs/{path}"
        resources_url = f"{base_url_clean}/resources/{path}"

        if docs_url in self.url_to_filename_map:
            filename = self.url_to_filename_map[docs_url]
            return f"[[{filename}|{link_text}]]"
        elif resources_url in self.url_to_filename_map:
            filename = self.url_to_filename_map[resources_url]
            return f"[[{filename}|{link_text}]]"

        # Fallback: try to match by title if link text seems like a title
        if link_text and len(link_text) > 3:
            link_text_lower = link_text.lower().strip()
            if link_text_lower in self.title_to_filename_map:
                filename = self.title_to_filename_map[link_text_lower]
                logger.debug(f"Resolved by title: {link_text} -> {filename}")
                return f"[[{filename}|{link_text}]]"

        # Last resort: use URL slug conversion (current behavior)
        if path.startswith("docs/"):
            doc_slug = path[5:]  # Remove 'docs/' prefix
            if doc_slug:
                file_name = self._url_slug_to_filename(doc_slug)
                logger.warning(f"No mapping found for {clean_url}, using slug: {file_name}")
                return f"[[{file_name}|{link_text}]]"
            else:
                return f"[[docs/index|{link_text}]]"
        elif path.startswith("resources/"):
            resource_slug = path[10:]  # Remove 'resources/' prefix
            if resource_slug:
                file_name = self._url_slug_to_filename(resource_slug)
                return f"[[resources/{file_name}|{link_text}]]"
            else:
                return f"[[resources/index|{link_text}]]"
        else:
            file_name = self._url_slug_to_filename(path)
            return f"[[{file_name}|{link_text}]]"

    def _url_slug_to_filename(self, slug: str) -> str:
        """Convert URL slug to proper filename format"""
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

    def convert_markdown_links(self, markdown: str, current_page_url: str) -> str:
        """Convert all internal markdown links to wiki links using proper filenames"""

        # First, fix existing wiki links that might have wrong targets
        # Pattern to match wiki links: [[target|text]]
        wiki_pattern = r"\[\[([^\|]+)\|([^\]]+)\]\]"

        def fix_wiki_link(match: Match[str]) -> str:
            target = match.group(1).strip()
            text = match.group(2).strip()

            # Try to find the correct filename for this target
            # First, check if target matches any filename directly
            target_lower = target.lower()
            for _url, filename in self.url_to_filename_map.items():
                if filename.lower() == target_lower:
                    return f"[[{filename}|{text}]]"

            # Try to find by URL slug conversion
            # Convert target to URL slug format (e.g., "Where Can My Form Appear" -> "where-can-my-form-appear")
            slug = target.lower().replace(" ", "-")

            # Check all URLs for matching slug
            for check_url, filename in self.url_to_filename_map.items():
                if slug in check_url.lower():
                    logger.debug(f"Fixed wiki link: [[{target}|{text}]] -> [[{filename}|{text}]]")
                    return f"[[{filename}|{text}]]"

            # If no match found, keep original
            return match.group(0)

        markdown = re.sub(wiki_pattern, fix_wiki_link, markdown)

        # Then handle markdown links
        # Pattern to match markdown links: [text](url)
        link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"

        def convert_link(match: Match[str]) -> str:
            text = match.group(1)
            url = match.group(2)

            # Skip non-HTTP links (anchors, mailto, etc.)
            if not url.startswith(("http://", "https://")):
                return match.group(0)

            # Convert using our resolver
            return self.resolve_url_to_wikilink(url, text)

        # Apply the conversion
        return re.sub(link_pattern, convert_link, markdown)

    async def load_from_state_manager(self, state_manager: Any) -> None:
        """Load all URL to filename mappings from the state manager"""
        try:
            cursor = await state_manager._db.execute(
                "SELECT url, title, file_path FROM pages WHERE file_path IS NOT NULL"
            )
            pages = await cursor.fetchall()

            for page in pages:
                self.add_page_mapping(page["url"], page["title"], page["file_path"])

            logger.info(f"Loaded {len(self.url_to_filename_map)} URL mappings")
        except Exception as e:
            logger.error(f"Failed to load mappings from state manager: {e}")

    def get_stats(self) -> Dict[str, int]:
        """Get statistics about the resolver"""
        return {
            "url_mappings": len(self.url_to_filename_map),
            "title_mappings": len(self.title_to_filename_map),
        }
