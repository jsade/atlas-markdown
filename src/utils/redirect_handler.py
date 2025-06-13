"""
Handle HTTP redirects to avoid duplicate content
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class RedirectHandler:
    """Tracks and handles URL redirects to avoid duplicate content"""

    def __init__(self):
        self.redirects = {}  # Map of original URL to final URL
        self.final_urls = {}  # Map of final URL to file path

    def add_redirect(self, original_url: str, final_url: str):
        """Record a redirect from original URL to final URL"""
        self.redirects[original_url] = final_url
        logger.info(f"Recorded redirect: {original_url} -> {final_url}")

    def add_final_url(self, url: str, file_path: str):
        """Record the file path for a final (non-redirected) URL"""
        self.final_urls[url] = file_path

    def is_duplicate_redirect(self, original_url: str, final_url: str) -> bool:
        """Check if this redirect would create a duplicate"""
        # If the final URL was already scraped, this is a duplicate
        return final_url in self.final_urls

    def get_canonical_file(self, url: str) -> str | None:
        """Get the canonical file path for a URL (following redirects)"""
        # Follow redirect chain
        current_url = url
        seen = set()

        while current_url in self.redirects:
            if current_url in seen:
                logger.warning(f"Redirect loop detected for {url}")
                break
            seen.add(current_url)
            current_url = self.redirects[current_url]

        # Return the file path for the final URL
        return self.final_urls.get(current_url)

    def create_redirect_markdown(
        self, original_url: str, final_url: str, canonical_file: str
    ) -> str:
        """Create a markdown file that indicates this is a redirect"""
        return f"""---
url: {original_url}
redirect_to: {final_url}
canonical_file: {canonical_file}
---

# Redirected Content

This page has been redirected to: [[{Path(canonical_file).stem}]]

Original URL: {original_url}
Redirects to: {final_url}
"""
