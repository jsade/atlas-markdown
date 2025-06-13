"""
File system manager for organizing downloaded documentation
"""

import logging
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import aiofiles

logger = logging.getLogger(__name__)


class FileSystemManager:
    """Manages file system structure for documentation"""

    def __init__(self, output_dir: str, base_url: str):
        self.output_dir = Path(output_dir)
        self.base_url = base_url.rstrip("/")
        self.base_path = urlparse(base_url).path.rstrip("/")

    def url_to_filepath(self, url: str, sibling_info: dict = None) -> tuple[Path, str]:
        """
        Convert URL to local file path, using sibling info or breadcrumb data if available
        Returns: (directory_path, filename)
        """
        logger.info(f"url_to_filepath called - URL: {url}")

        # First check if we have breadcrumb data for directory structure
        directory_from_breadcrumb = None
        if sibling_info and sibling_info.get("breadcrumb_data"):
            logger.info("Processing breadcrumb data...")
            breadcrumb_path, _ = self._get_path_from_breadcrumbs(
                sibling_info["breadcrumb_data"], url
            )
            if breadcrumb_path:
                directory_from_breadcrumb = breadcrumb_path
                logger.info(f"Using breadcrumb directory: {breadcrumb_path}")

        # Always use current_page_title for filename if available
        if sibling_info and sibling_info.get("current_page_title"):
            filename = self._clean_for_filesystem(sibling_info["current_page_title"]) + ".md"
            logger.info(f"Using current_page_title for filename: {filename}")

            # Use breadcrumb directory if available, otherwise determine from URL
            if directory_from_breadcrumb:
                return directory_from_breadcrumb, filename
            else:
                # Determine directory from URL structure
                parsed = urlparse(url)
                if "/docs/" in parsed.path:
                    return self.output_dir / "docs", filename
                elif "/resources/" in parsed.path:
                    return self.output_dir / "resources", filename
                else:
                    return self.output_dir, filename

        # If we have sibling info with a section heading, use that for folder structure
        if sibling_info and sibling_info.get("section_heading"):
            logger.info(
                f"Processing sibling info with section_heading: {sibling_info.get('section_heading')}"
            )
            from ..parsers.sibling_navigation_parser import SiblingNavigationParser

            parser = SiblingNavigationParser(self.base_url)
            folder_name, filename = parser.get_folder_structure(sibling_info)

            if folder_name:
                # Determine if this is docs or resources based on URL
                parsed = urlparse(url)
                path = parsed.path

                if "/docs/" in path:
                    directory = self.output_dir / "docs" / folder_name
                elif "/resources/" in path:
                    directory = self.output_dir / "resources" / folder_name
                else:
                    # Fallback to root with folder
                    directory = self.output_dir / folder_name

                # If we got a filename from sibling parser, use it
                if filename:
                    return directory, filename
                else:
                    # Fall back to extracting filename from URL
                    # This prevents using the section heading as filename
                    url_path = parsed.path
                    if self.base_path and url_path.startswith(self.base_path):
                        url_path = url_path[len(self.base_path) :].lstrip("/")

                    # Extract the last part of the URL as filename
                    path_parts = [unquote(p) for p in url_path.split("/") if p]
                    if path_parts and path_parts[-1]:
                        # Convert URL slug to proper name
                        filename = self._url_slug_to_proper_name(path_parts[-1]) + ".md"
                        return directory, filename

        # Fallback to original URL-based logic
        parsed = urlparse(url)

        # Get path relative to base URL
        path = parsed.path
        if self.base_path and path.startswith(self.base_path):
            path = path[len(self.base_path) :].lstrip("/")
        else:
            path = path.lstrip("/")

        # Handle empty path (homepage)
        if not path:
            return self.output_dir, "index.md"

        # For top-level docs pages, use the slug as filename instead of index.md
        # This prevents multiple pages being saved as index.md
        if path.startswith("docs/") and path.count("/") == 1:
            # This is a top-level docs page like docs/get-started-with-jira-service-management/
            slug = path.split("/")[1].rstrip("/")
            if slug:
                filename = self._url_slug_to_proper_name(slug) + ".md"
                return self.output_dir / "docs", filename

        # Split path into parts
        path_parts = [unquote(p) for p in path.split("/") if p]

        # Clean path parts (remove invalid characters)
        clean_parts = []
        for part in path_parts:
            # Convert URL slug to proper name if it looks like a slug
            if "-" in part and " " not in part:
                # This looks like a URL slug, convert it
                part = self._url_slug_to_proper_name(part)

            # Replace invalid filename characters
            clean_part = re.sub(r'[<>:"|?*]', "_", part)
            # Replace multiple underscores with single
            clean_part = re.sub(r"_+", "_", clean_part)
            # Remove trailing dots and spaces (Windows compatibility)
            clean_part = clean_part.rstrip(". ")
            clean_parts.append(clean_part)

        # Determine if this is a directory or file
        if path.endswith("/") or not path_parts[-1]:
            # Directory URL - create index.md
            directory = self.output_dir / Path(*clean_parts)
            filename = "index.md"
        else:
            # File URL
            if len(clean_parts) > 1:
                directory = self.output_dir / Path(*clean_parts[:-1])
                filename = f"{clean_parts[-1]}.md"
            else:
                directory = self.output_dir
                filename = f"{clean_parts[0]}.md"

        return directory, filename

    async def save_content(self, url: str, content: str, sibling_info: dict = None) -> str:
        """
        Save content to appropriate file location
        Returns the file path relative to output directory
        """
        import hashlib
        import shutil
        import tempfile

        # Log sibling info for debugging
        if sibling_info:
            logger.info(
                f"save_content called with sibling_info - section_heading: {sibling_info.get('section_heading')}, current_page_title: {sibling_info.get('current_page_title')}"
            )

        directory, filename = self.url_to_filepath(url, sibling_info)
        logger.info(f"url_to_filepath returned - directory: {directory}, filename: {filename}")

        # Check disk space first (require at least 100MB free)
        try:
            stat = shutil.disk_usage(self.output_dir)
            if stat.free < 100 * 1024 * 1024:
                raise OSError(f"Insufficient disk space: only {stat.free / 1024 / 1024:.1f}MB free")
        except Exception as e:
            logger.warning(f"Could not check disk space: {e}")

        # Validate path to prevent traversal attacks
        try:
            directory = directory.resolve()
            output_dir_resolved = self.output_dir.resolve()
            if not str(directory).startswith(str(output_dir_resolved)):
                raise ValueError(f"Path traversal attempt detected: {directory}")
        except Exception as e:
            raise ValueError(f"Invalid path: {directory} - {e}") from e

        # Handle very long paths (Windows has 260 char limit)
        file_path = directory / filename
        if len(str(file_path)) > 250:
            # Truncate filename while preserving extension
            name_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            base = filename[:100]  # Keep first 100 chars
            ext = Path(filename).suffix
            filename = f"{base}_{name_hash}{ext}"
            file_path = directory / filename
            logger.debug(f"Truncated long filename to: {filename}")

        # Create directory structure with error handling
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise PermissionError(f"Cannot create directory: {directory}") from e
        except OSError as e:
            raise OSError(f"Failed to create directory {directory}: {e}") from e

        # Handle duplicate filenames
        if file_path.exists():
            # Check if content is the same
            try:
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    existing_content = await f.read()

                if existing_content.strip() == content.strip():
                    logger.info(f"Identical content already exists: {file_path}")
                    relative_path = file_path.relative_to(self.output_dir)
                    return str(relative_path).replace("\\", "/")
                else:
                    # Create unique filename
                    base = file_path.stem
                    suffix = file_path.suffix
                    counter = 1

                    while file_path.exists() and counter < 100:  # Limit iterations
                        file_path = directory / f"{base}_{counter}{suffix}"
                        counter += 1

                    if counter >= 100:
                        raise ValueError(f"Too many duplicates for {filename}")

                    logger.warning(f"Duplicate URL with different content, saving as: {file_path}")
            except Exception as e:
                logger.error(f"Error checking existing file: {e}")
                # Continue with new filename

        # Use atomic write with temporary file
        temp_fd, temp_path = tempfile.mkstemp(dir=directory, prefix=f".{filename}.", suffix=".tmp")
        temp_path = Path(temp_path)

        try:
            # Write to temporary file
            async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                await f.write(content)
                await f.flush()
                # Force write to disk
                os.fsync(f.fileno())

            # Close the file descriptor
            os.close(temp_fd)

            # Atomic rename
            temp_path.replace(file_path)
            logger.info(f"Saved: {file_path}")

        except Exception as e:
            # Clean up temporary file on error
            try:
                os.close(temp_fd)
            except Exception:
                pass
            if temp_path.exists():
                temp_path.unlink()
            raise OSError(f"Failed to save content: {e}") from e

        # Return relative path
        try:
            relative_path = file_path.relative_to(self.output_dir)
            return str(relative_path).replace("\\", "/")
        except ValueError:
            return str(file_path)

    async def create_index(self, pages: list) -> str:
        """Create an index file with all scraped pages"""
        index_content = """# Atlassian Jira Service Management Documentation

This is an offline copy of the Atlassian Jira Service Management documentation.

## Table of Contents

"""

        # Group pages by directory - only include docs/ content
        page_tree = {}

        for page in pages:
            if page.get("status") != "completed":
                continue

            url = page.get("url", "")
            title = page.get("title", "Untitled")
            file_path = page.get("file_path", "")

            if not file_path:
                continue

            # Convert to Path and get relative path from output directory
            full_path = Path(file_path)
            try:
                # If file_path is already relative, use it as is
                if not full_path.is_absolute():
                    relative_path = file_path
                else:
                    # Get relative path from output directory
                    # Handle both string and Path output_dir
                    output_dir_path = Path(self.output_dir).resolve()
                    full_path_resolved = full_path.resolve()
                    relative_path = full_path_resolved.relative_to(output_dir_path)
            except ValueError:
                # If path is not relative to output_dir, skip it
                logger.warning(f"Skipping file not in output directory: {file_path}")
                continue

            # Only include docs/ content
            relative_str = str(relative_path).replace("\\", "/")
            if not relative_str.startswith("docs/"):
                continue

            # Parse directory structure from docs/ onwards
            parts = Path(relative_str).parts[1:]  # Skip 'docs' part

            # Build tree structure
            current = page_tree
            for part in parts[:-1]:  # All but the filename
                if part not in current:
                    current[part] = {}
                current = current[part]

            # Add file to tree
            filename = parts[-1] if parts else Path(relative_str).name
            current[filename] = {"title": title, "url": url, "path": "/" + relative_str}

        # Generate index content with proper heading hierarchy
        def generate_tree_markdown(tree, level=2):  # Start with ## (H2)
            markdown = ""

            # Sort items: directories first, then files
            items = sorted(
                tree.items(), key=lambda x: (isinstance(x[1], dict) and "title" not in x[1], x[0])
            )

            for name, value in items:
                if isinstance(value, dict) and "title" in value:
                    # It's a file
                    title = value["title"]
                    path = value["path"]
                    # Convert to wikilink format without file extension
                    wiki_path = path.replace(".md", "")
                    # No indentation for list items - always start at column 0
                    markdown += f"- [[{wiki_path}|{title}]]\n"
                else:
                    # It's a directory
                    if name != "index.md":  # Skip index files in listing
                        # Use heading for directories
                        heading_prefix = "#" * level
                        # Clean directory name for display
                        display_name = name
                        markdown += f"\n{heading_prefix} {display_name}\n\n"
                        markdown += generate_tree_markdown(value, min(level + 1, 6))  # Max H6

            return markdown

        index_content += generate_tree_markdown(page_tree)

        # Add statistics
        # Count pages that were successfully included in the index
        doc_count = self._count_pages_in_tree(page_tree)
        index_content += f"\n\n---\n\nTotal documentation pages: {doc_count}\n"

        # Save index
        index_path = self.output_dir / "index.md"
        async with aiofiles.open(index_path, "w", encoding="utf-8") as f:
            await f.write(index_content)

        return str(index_path)

    def _get_path_from_breadcrumbs(
        self, breadcrumb_data: dict, url: str
    ) -> tuple[Path | None, str | None]:
        """
        Determine file path from breadcrumb data
        Returns: (directory_path, filename)
        """
        breadcrumbs = breadcrumb_data.get("breadcrumbs", [])
        breadcrumb_data.get("current", {})

        if not breadcrumbs or len(breadcrumbs) < 2:
            return None, None

        # Build path from breadcrumbs, skipping the first two (Atlassian Support, Jira Service Management)
        path_parts = []

        for crumb in breadcrumbs[2:]:  # Skip first two levels
            name = crumb.get("name", "")
            if name and name not in ["Resources", "Docs"]:  # Skip these generic names
                # Clean the name for filesystem
                clean_name = re.sub(r'[<>:"|?*]', "_", name)
                clean_name = clean_name.rstrip(". ")
                path_parts.append(clean_name)

        # Determine base directory
        parsed = urlparse(url)
        if "/docs/" in parsed.path:
            base_dir = self.output_dir / "docs"
        elif "/resources/" in parsed.path:
            base_dir = self.output_dir / "resources"
        else:
            base_dir = self.output_dir

        # Build full directory path - use breadcrumbs for folders only
        if path_parts:
            # Use ALL breadcrumb parts for directory structure
            directory = base_dir / Path(*path_parts)
            # Don't set filename here - let the current_page_title be used
            filename = None
        else:
            directory = base_dir
            filename = None

        return directory, filename

    def _url_slug_to_proper_name(self, slug: str) -> str:
        """Convert URL slug to proper name with capitalized words
        e.g., "what-is-a-service-project" → "What is a service project"
        """
        # Common words that should stay lowercase
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

    def get_output_directory(self) -> Path:
        """Get the output directory path"""
        return self.output_dir

    def _clean_for_filesystem(self, text: str) -> str:
        """Clean text for use as folder/file name"""
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

    def _count_pages_in_tree(self, tree: dict) -> int:
        """Count total pages in the tree structure"""
        count = 0
        for value in tree.values():
            if isinstance(value, dict):
                if "title" in value:
                    # It's a file
                    count += 1
                else:
                    # It's a directory, recurse
                    count += self._count_pages_in_tree(value)
        return count
