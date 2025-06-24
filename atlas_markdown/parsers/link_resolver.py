"""
Link resolver for mapping URLs to actual filenames
"""

import logging
import re
from pathlib import Path
from re import Match
from typing import Any

from atlas_markdown.utils.redirect_handler import RedirectHandler

logger = logging.getLogger(__name__)


class LinkResolver:
    """Resolves internal links to actual filenames"""

    def __init__(self, base_url: str, redirect_handler: RedirectHandler | None = None):
        self.base_url = base_url.rstrip("/")
        self.redirect_handler = redirect_handler
        self.url_to_filename_map: dict[str, str] = {}
        self.title_to_filename_map: dict[str, str] = {}
        self.url_to_filepath_map: dict[str, str] = {}  # Store full relative paths

    def add_page_mapping(self, url: str, title: str, file_path: str) -> None:
        """Add a mapping from URL and title to actual filename"""
        # Store both the filename and the full relative path
        if file_path:
            # Store the full relative path (without .md extension)
            path_obj = Path(file_path)
            relative_path_no_ext = str(path_obj.with_suffix("")).replace("\\", "/")
            self.url_to_filepath_map[url.rstrip("/")] = relative_path_no_ext

            # Also store just the filename for backward compatibility
            filename = path_obj.stem
            self.url_to_filename_map[url.rstrip("/")] = filename

            if title:
                # Also map by title for fallback
                self.title_to_filename_map[title.lower()] = filename

            logger.debug(f"Added mapping: {url} -> {relative_path_no_ext}")

    def _follow_redirects(self, url: str) -> str:
        """Follow redirect chain to final URL"""
        if not self.redirect_handler:
            return url

        current_url = url
        seen = set()

        while True:
            # Check both with and without trailing slash
            redirect_found = False

            if current_url in self.redirect_handler.redirects:
                next_url = self.redirect_handler.redirects[current_url]
                redirect_found = True
            elif current_url + "/" in self.redirect_handler.redirects:
                next_url = self.redirect_handler.redirects[current_url + "/"]
                redirect_found = True
            elif (
                current_url.endswith("/")
                and current_url.rstrip("/") in self.redirect_handler.redirects
            ):
                next_url = self.redirect_handler.redirects[current_url.rstrip("/")]
                redirect_found = True

            if not redirect_found:
                break

            if current_url in seen:
                logger.warning(f"Redirect loop detected for {url}")
                break
            seen.add(current_url)
            current_url = next_url.rstrip("/")  # Normalize the URL

        return current_url

    def resolve_url_to_wikilink(
        self, url: str, link_text: str, current_page_path: str | None = None
    ) -> str:
        """Convert a URL to a wiki link using relative paths"""
        # Clean the URL
        clean_url = url.rstrip("/")

        # Follow redirects if redirect handler is available
        if self.redirect_handler:
            final_url = self._follow_redirects(clean_url)
            if final_url != clean_url:
                logger.debug(f"Following redirect: {clean_url} -> {final_url}")
                clean_url = final_url

        # Check if it's an internal link
        if not clean_url.startswith(self.base_url):
            # External link - keep as markdown
            return f"[{link_text}]({url})"

        # Check if we have a mapping for this URL
        if clean_url in self.url_to_filepath_map:
            target_path = self.url_to_filepath_map[clean_url]

            # If we have the current page path, calculate relative path
            if current_page_path:
                relative_link = self._calculate_relative_path(current_page_path, target_path)
                return f"[[{relative_link}|{link_text}]]"
            else:
                # Fallback to just the filename
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

        if docs_url in self.url_to_filepath_map:
            target_path = self.url_to_filepath_map[docs_url]
            if current_page_path:
                relative_link = self._calculate_relative_path(current_page_path, target_path)
                return f"[[{relative_link}|{link_text}]]"
            else:
                filename = self.url_to_filename_map.get(docs_url, Path(target_path).name)
                return f"[[{filename}|{link_text}]]"
        elif resources_url in self.url_to_filepath_map:
            target_path = self.url_to_filepath_map[resources_url]
            if current_page_path:
                relative_link = self._calculate_relative_path(current_page_path, target_path)
                return f"[[{relative_link}|{link_text}]]"
            else:
                filename = self.url_to_filename_map.get(resources_url, Path(target_path).name)
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

    def _calculate_relative_path(self, from_path: str, to_path: str) -> str:
        """Calculate relative path from one file to another"""
        # Convert to Path objects, removing .md extension if present
        from_path_obj = Path(from_path.replace(".md", ""))
        to_path_obj = Path(to_path.replace(".md", ""))

        # Get the directory of the source file
        from_dir = from_path_obj.parent

        # Calculate relative path
        try:
            # If both paths are in the same directory
            if from_dir == to_path_obj.parent:
                return to_path_obj.name
            else:
                # Calculate the relative path
                relative = to_path_obj.relative_to(from_dir)
                return str(relative).replace("\\", "/")
        except ValueError:
            # Paths don't share a common base, need to go up
            # Count how many levels up we need to go
            common_parts = 0
            from_parts = from_dir.parts
            to_parts = to_path_obj.parts

            # Find common prefix
            for i, (f, t) in enumerate(zip(from_parts, to_parts, strict=False)):
                if f == t:
                    common_parts = i + 1
                else:
                    break

            # Calculate the path
            ups = len(from_parts) - common_parts
            down_parts = to_parts[common_parts:]

            if ups > 0:
                result_parts = [".." for _ in range(ups)] + list(down_parts)
            else:
                result_parts = list(down_parts)

            return "/".join(result_parts)

    def convert_markdown_links(
        self, markdown: str, current_page_url: str, current_page_path: str | None = None
    ) -> str:
        """Convert all internal markdown links to wiki links using proper filenames"""

        # First, fix existing wiki links that might have wrong targets
        # Pattern to match wiki links: [[target|text]]
        wiki_pattern = r"\[\[([^\|]+)\|([^\]]+)\]\]"

        def fix_wiki_link(match: Match[str]) -> str:
            target = match.group(1).strip()
            text = match.group(2).strip()

            # Skip if it already looks like a relative path
            if "../" in target or "/" in target:
                return match.group(0)

            # Try to find the correct path for this target
            target_lower = target.lower()

            # Also try converting the target as if it's a URL slug
            target_as_title = self._url_slug_to_filename(target)
            target_as_title_lower = target_as_title.lower()

            # Check all URLs for matching filename or slug
            for url, filepath in self.url_to_filepath_map.items():
                filename = Path(filepath).name
                filename_lower = filename.lower()

                # Check if target matches filename directly or as a converted slug
                if filename_lower == target_lower or filename_lower == target_as_title_lower:
                    if current_page_path:
                        relative_link = self._calculate_relative_path(current_page_path, filepath)
                        logger.debug(
                            f"Fixed wiki link: [[{target}|{text}]] -> [[{relative_link}|{text}]]"
                        )
                        return f"[[{relative_link}|{text}]]"
                    else:
                        return f"[[{filename}|{text}]]"

                # Also check if the URL contains the target as a slug
                if target in url.lower():
                    if current_page_path:
                        relative_link = self._calculate_relative_path(current_page_path, filepath)
                        logger.debug(
                            f"Fixed wiki link by URL: [[{target}|{text}]] -> [[{relative_link}|{text}]]"
                        )
                        return f"[[{relative_link}|{text}]]"
                    else:
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
            return self.resolve_url_to_wikilink(url, text, current_page_path)

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

    def get_stats(self) -> dict[str, int]:
        """Get statistics about the resolver"""
        return {
            "url_mappings": len(self.url_to_filename_map),
            "title_mappings": len(self.title_to_filename_map),
        }
