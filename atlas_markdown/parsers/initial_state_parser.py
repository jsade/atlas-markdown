"""
Parser for extracting navigation structure from window.__APP_INITIAL_STATE__
"""

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class InitialStateParser:
    """Extract and parse the navigation structure from React initial state"""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.pages_map: dict[str, dict[str, Any]] = {}

    def extract_initial_state(self, html: str) -> dict[str, Any] | None:
        """Extract the __APP_INITIAL_STATE__ from page HTML"""
        soup = BeautifulSoup(html, "html.parser")

        # Look for the script containing __APP_INITIAL_STATE__
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
                        return json.loads(json_str)
                except (json.JSONDecodeError, AttributeError) as e:
                    logger.error(f"Failed to parse __APP_INITIAL_STATE__: {e}")

        return None

    def extract_navigation_structure(self, state_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract navigation structure from initial state data"""
        navigation = []

        # Look for navigation data in various possible locations
        if "navigation" in state_data:
            self._process_navigation_items(state_data["navigation"], navigation)

        # Check for childList in entry
        if "entry" in state_data and "childList" in state_data["entry"]:
            self._process_child_list(state_data["entry"]["childList"], navigation)

        # Look for allEntries or similar structures
        for key in ["allEntries", "entries", "pages"]:
            if key in state_data:
                self._process_entries(state_data[key], navigation)

        return navigation

    def _process_child_list(
        self, child_list: list[dict[str, Any]], navigation: list[dict[str, Any]]
    ):
        """Process a childList structure"""
        for item in child_list:
            page_info: dict[str, Any] = {
                "id": item.get("id"),
                "title": item.get("title"),
                "slug": item.get("slug", ""),
                "description": item.get("description"),
                "updatedAt": item.get("updatedAt"),
                "children": [],
                "childList": [],  # Store child IDs
            }

            # Convert slug to full URL
            if page_info["slug"]:
                page_info["url"] = self._slug_to_url(page_info["slug"])

            # Process nested children
            if "childList" in item and item["childList"]:
                # Extract child IDs
                page_info["childList"] = [
                    child.get("id") for child in item["childList"] if child.get("id")
                ]
                self._process_child_list(item["childList"], page_info["children"])

            # Only add if URL is within our base URL
            if page_info.get("url") and page_info["url"].startswith(self.base_url):
                navigation.append(page_info)
                # Also add to flat map for easy lookup
                self.pages_map[page_info["url"]] = page_info

    def _process_navigation_items(self, nav_data: Any, navigation: list[dict[str, Any]]):
        """Process navigation items from various formats"""
        if isinstance(nav_data, list):
            for item in nav_data:
                if isinstance(item, dict):
                    self._process_navigation_item(item, navigation)
        elif isinstance(nav_data, dict):
            for _key, value in nav_data.items():
                if isinstance(value, list | dict):
                    self._process_navigation_items(value, navigation)

    def _process_navigation_item(self, item: dict[str, Any], navigation: list[dict[str, Any]]):
        """Process a single navigation item"""
        page_info: dict[str, Any] = {
            "id": item.get("id"),
            "title": item.get("title"),
            "url": item.get("url") or item.get("href") or item.get("slug"),
            "description": item.get("description"),
            "children": [],
        }

        # Convert relative URLs to absolute
        if page_info["url"] and not page_info["url"].startswith("http"):
            page_info["url"] = self._slug_to_url(page_info["url"])

        # Process children
        for child_key in ["children", "childList", "items"]:
            if child_key in item and item[child_key]:
                self._process_navigation_items(item[child_key], page_info["children"])

        # Only add if URL is within our base URL
        url = page_info.get("url")
        if url and isinstance(url, str) and url.startswith(self.base_url):
            navigation.append(page_info)

    def _process_entries(self, entries: Any, navigation: list[dict[str, Any]]):
        """Process entries from various formats"""
        if isinstance(entries, list):
            for entry in entries:
                self._process_navigation_item(entry, navigation)
        elif isinstance(entries, dict):
            for _key, entry in entries.items():
                if isinstance(entry, dict):
                    self._process_navigation_item(entry, navigation)

    def _slug_to_url(self, slug: str) -> str:
        """Convert a slug to a full URL"""
        # Remove leading slash if present
        slug = slug.lstrip("/")

        # If it's already a full URL, return as-is
        if slug.startswith(("http://", "https://")):
            return slug

        # If it starts with the base path, prepend domain
        if slug.startswith("jira-service-management-cloud/"):
            return f"https://support.atlassian.com/{slug}"

        # Otherwise, append to base URL
        return f"{self.base_url}/{slug}"

    def get_all_urls(self) -> list[str]:
        """Get all discovered URLs"""
        return list(self.pages_map.keys())

    def get_page_info(self, url: str) -> dict[str, Any] | None:
        """Get information about a specific page"""
        return self.pages_map.get(url)

    def print_structure(self, navigation: list[dict[str, Any]], indent: int = 0):
        """Print the navigation structure for debugging"""
        for item in navigation:
            print(
                "  " * indent + f"- {item.get('title', 'Untitled')} ({item.get('url', 'no-url')})"
            )
            if item.get("children"):
                self.print_structure(item["children"], indent + 1)

    def extract_full_hierarchy(self, html: str) -> dict[str, Any]:
        """Extract the complete site hierarchy from initial state"""
        state_data = self.extract_initial_state(html)
        if not state_data:
            return {"navigation": [], "flat_map": {}}

        # Extract navigation structure
        navigation = self.extract_navigation_structure(state_data)

        # Build a comprehensive hierarchy
        hierarchy = {
            "navigation": navigation,
            "flat_map": self.pages_map,
            "total_pages": len(self.pages_map),
        }

        return hierarchy

    def get_page_metadata(self, url: str) -> dict[str, Any]:
        """Get metadata for a specific page including frontmatter fields"""
        page_info = self.pages_map.get(url, {})

        return {
            "title": page_info.get("title", ""),
            "description": page_info.get("description", ""),
            "id": page_info.get("id", ""),
            "slug": page_info.get("slug", ""),
            "childList": page_info.get("childList", []),
        }

    def extract_topic_title(self, state_data: dict[str, Any]) -> str | None:
        """Extract the topicTitle from initial state data"""
        # Direct access to topicTitle
        if "topicTitle" in state_data:
            title = state_data["topicTitle"]
            return str(title) if title is not None else None

        # Check in entry
        if "entry" in state_data and isinstance(state_data["entry"], dict):
            if "topicTitle" in state_data["entry"]:
                title = state_data["entry"]["topicTitle"]
                return str(title) if title is not None else None
            if "title" in state_data["entry"]:
                title = state_data["entry"]["title"]
                return str(title) if title is not None else None

        # Check in various other locations
        for key in ["topic", "page", "content"]:
            if key in state_data and isinstance(state_data[key], dict):
                if "title" in state_data[key]:
                    title = state_data[key]["title"]
                    return str(title) if title is not None else None
                if "topicTitle" in state_data[key]:
                    title = state_data[key]["topicTitle"]
                    return str(title) if title is not None else None

        return None

    def extract_topic_metadata(self, state_data: dict[str, Any]) -> dict[str, str | None]:
        """Extract topic title and description from initial state data"""
        metadata: dict[str, str | None] = {"title": None, "description": None}

        # Direct access to topicTitle and description
        if "topicTitle" in state_data:
            metadata["title"] = state_data["topicTitle"]
        if "description" in state_data:
            metadata["description"] = state_data["description"]

        # Check in entry
        if "entry" in state_data and isinstance(state_data["entry"], dict):
            entry = state_data["entry"]
            if not metadata["title"] and "topicTitle" in entry:
                metadata["title"] = entry["topicTitle"]
            if not metadata["title"] and "title" in entry:
                metadata["title"] = entry["title"]
            if not metadata["description"] and "description" in entry:
                metadata["description"] = entry["description"]

        # Check in various other locations
        for key in ["topic", "page", "content"]:
            if key in state_data and isinstance(state_data[key], dict):
                data = state_data[key]
                if not metadata["title"] and "title" in data:
                    metadata["title"] = data["title"]
                if not metadata["title"] and "topicTitle" in data:
                    metadata["title"] = data["topicTitle"]
                if not metadata["description"] and "description" in data:
                    metadata["description"] = data["description"]

        return metadata
