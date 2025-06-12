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
        # First check if we have breadcrumb data
        if sibling_info and sibling_info.get("breadcrumb_data"):
            breadcrumb_path, filename = self._get_path_from_breadcrumbs(
                sibling_info["breadcrumb_data"], url
            )
            if breadcrumb_path and filename:
                return breadcrumb_path, filename

        # If we have sibling info with a section heading, use that for folder structure
        if sibling_info and sibling_info.get("section_heading"):
            from ..parsers.sibling_navigation_parser import SiblingNavigationParser

            parser = SiblingNavigationParser(self.base_url)
            folder_name, filename = parser.get_folder_structure(sibling_info)

            if folder_name and filename:
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

        directory, filename = self.url_to_filepath(url, sibling_info)

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

        # Group pages by directory
        page_tree = {}

        for page in pages:
            if page.get("status") != "completed":
                continue

            url = page.get("url", "")
            title = page.get("title", "Untitled")
            file_path = page.get("file_path", "")

            if not file_path:
                continue

            # Parse directory structure
            parts = Path(file_path).parts

            # Build tree structure
            current = page_tree
            for part in parts[:-1]:  # All but the filename
                if part not in current:
                    current[part] = {}
                current = current[part]

            # Add file to tree
            filename = parts[-1] if parts else file_path
            current[filename] = {"title": title, "url": url, "path": file_path}

        # Generate index content
        def generate_tree_markdown(tree, level=0):
            markdown = ""
            indent = "  " * level

            # Sort items: directories first, then files
            items = sorted(tree.items(), key=lambda x: (isinstance(x[1], dict), x[0]))

            for name, value in items:
                if isinstance(value, dict) and "title" in value:
                    # It's a file
                    title = value["title"]
                    path = value["path"]
                    # Convert to wikilink format without file extension
                    wiki_path = path.replace(".md", "")
                    markdown += f"{indent}- [[{wiki_path}|{title}]]\n"
                else:
                    # It's a directory
                    if name != "index.md":  # Skip index files in listing
                        markdown += f"{indent}- **{name}/**\n"
                        markdown += generate_tree_markdown(value, level + 1)

            return markdown

        index_content += generate_tree_markdown(page_tree)

        # Add statistics
        index_content += f"\n\n---\n\nTotal pages: {len(pages)}\n"

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

        # Build full directory path
        if path_parts:
            # Use all but the last part for directory
            if len(path_parts) > 1:
                directory = base_dir / Path(*path_parts[:-1])
                filename = f"{path_parts[-1]}.md"
            else:
                directory = base_dir
                filename = f"{path_parts[0]}.md"
        else:
            directory = base_dir
            filename = "index.md"

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
