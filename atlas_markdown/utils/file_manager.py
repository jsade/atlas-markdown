"""
File system manager for organizing downloaded documentation
"""

import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import aiofiles

logger = logging.getLogger(__name__)


class FileSystemManager:
    """Manages file system structure for documentation"""

    def __init__(self, output_dir: str, base_url: str):
        self.output_dir = Path(output_dir)
        self.base_url = base_url.rstrip("/")
        self.base_path = urlparse(base_url).path.rstrip("/")

    def url_to_filepath(
        self, url: str, sibling_info: dict[str, Any] | None = None
    ) -> tuple[Path, str]:
        """
        Convert URL to local file path, using sibling info or breadcrumb data if available
        Returns: (directory_path, filename)
        """
        logger.info(f"url_to_filepath called - URL: {url}")

        # Build complete directory hierarchy from both breadcrumb and sibling info
        directory_parts = []
        filename = None

        # Determine base directory from URL
        parsed = urlparse(url)
        if "/docs/" in parsed.path:
            directory_parts.append("docs")
        elif "/resources/" in parsed.path:
            directory_parts.append("resources")

        # Add breadcrumb hierarchy if available
        if sibling_info and sibling_info.get("breadcrumb_data"):
            logger.info("Processing breadcrumb data...")
            breadcrumbs = sibling_info["breadcrumb_data"].get("breadcrumbs", [])

            # Skip first two levels (Atlassian Support, Product Name) and exclude the last one (current page)
            # The last breadcrumb is the current page, which should be the filename, not a directory
            breadcrumbs_for_path = breadcrumbs[2:-1] if len(breadcrumbs) > 2 else []

            for crumb in breadcrumbs_for_path:
                name = crumb.get("name", "")
                if name and name not in ["Resources", "Docs"]:
                    clean_name = self._clean_for_filesystem(name)
                    directory_parts.append(clean_name)

            logger.info(f"Breadcrumb hierarchy: {' / '.join(directory_parts)}")

        # Add sibling section folder if it's not already in the path
        if sibling_info and sibling_info.get("section_heading"):
            section_folder = self._clean_for_filesystem(sibling_info["section_heading"])

            # Only add if it's not already the last part of the path
            if not directory_parts or directory_parts[-1] != section_folder:
                # Check if this should be a subdirectory or replace the last part
                if sibling_info.get("is_section_index"):
                    # This is the index page for this section
                    directory_parts.append(section_folder)
                    filename = "index.md"
                else:
                    # Regular page in section
                    directory_parts.append(section_folder)

            logger.info(f"After sibling info: {' / '.join(directory_parts)}")

        # Use current_page_title for filename if available and not already set
        if not filename and sibling_info and sibling_info.get("current_page_title"):
            filename = self._clean_for_filesystem(sibling_info["current_page_title"]) + ".md"
            logger.info(f"Using current_page_title for filename: {filename}")

        # Build final directory path
        if directory_parts:
            directory = self.output_dir / Path(*directory_parts)
        else:
            directory = self.output_dir

        # If we still don't have a filename, extract from URL
        if not filename:
            # Check if URL ends with slash (directory URL)
            if url.endswith("/") or parsed.path.endswith("/"):
                filename = "index.md"
            else:
                # Extract from URL path
                url_path = parsed.path
                if self.base_path and url_path.startswith(self.base_path):
                    url_path = url_path[len(self.base_path) :].lstrip("/")

                path_parts = [unquote(p) for p in url_path.split("/") if p]
                if path_parts and path_parts[-1]:
                    filename = self._url_slug_to_proper_name(path_parts[-1]) + ".md"
                else:
                    filename = "index.md"

        logger.info(f"Final path: {directory} / {filename}")
        return directory, filename

    async def save_content(
        self, url: str, content: str, sibling_info: dict[str, Any] | None = None
    ) -> str:
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
                async with aiofiles.open(file_path, encoding="utf-8") as f:
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
        temp_fd, temp_path_str = tempfile.mkstemp(
            dir=directory, prefix=f".{filename}.", suffix=".tmp"
        )
        temp_path = Path(temp_path_str)

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

    async def create_index(self, pages: list[dict[str, Any]]) -> str:
        """Create an index file with all scraped pages"""
        index_content = """# Table of Contents


"""

        # Group pages by directory - only include docs/ content
        page_tree: dict[str, Any] = {}

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
            current[filename] = {"title": title, "url": url, "path": relative_str}

        # Generate index content with proper heading hierarchy
        def generate_tree_markdown(
            tree: dict[str, Any], level: int = 2
        ) -> str:  # Start with ## (H2)
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

    def _count_pages_in_tree(self, tree: dict[str, Any]) -> int:
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
