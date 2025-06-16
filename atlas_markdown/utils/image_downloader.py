"""
Image downloader with local path management
"""

import asyncio
import hashlib
import logging
from pathlib import Path
from urllib.parse import unquote, urlparse

import aiofiles
import httpx

logger = logging.getLogger(__name__)


class ImageDownloader:
    """Downloads images and manages local paths"""

    def __init__(self, output_dir: str, base_url: str):
        self.output_dir = Path(output_dir)
        self.images_dir = self.output_dir / "images"
        self.base_url = base_url
        self.client: httpx.AsyncClient | None = None
        self.image_map: dict[str, str] = {}  # Maps original URL to local path

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def initialize(self):
        """Initialize HTTP client and create directories"""
        self.images_dir.mkdir(parents=True, exist_ok=True)

        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            },
        )

    async def close(self):
        """Close HTTP client"""
        if self.client:
            await self.client.aclose()

    def get_local_path(self, image_url: str, page_url: str) -> str:
        """Generate local path for an image"""
        # Parse the image URL
        parsed = urlparse(image_url)

        # Get filename from URL
        path_parts = parsed.path.strip("/").split("/")
        if path_parts and path_parts[-1]:
            filename = unquote(path_parts[-1])
        else:
            # Generate filename from URL hash
            url_hash = hashlib.md5(image_url.encode()).hexdigest()[:8]
            filename = f"image_{url_hash}"

        # Add extension if missing
        if "." not in filename:
            # Try to determine from content type later
            filename += ".jpg"  # Default extension

        # Create subdirectory based on page URL to organize images
        page_parsed = urlparse(page_url)
        page_path = page_parsed.path.strip("/").replace("/", "_")
        if page_path:
            subdir = self.images_dir / page_path
            subdir.mkdir(exist_ok=True)
            local_path = subdir / filename
        else:
            local_path = self.images_dir / filename

        # Make path relative to output directory
        try:
            relative_path = local_path.relative_to(self.output_dir)
            return str(relative_path).replace("\\", "/")  # Use forward slashes
        except ValueError:
            # If not relative, return absolute
            return str(local_path)

    async def download_image(
        self, image_url: str, page_url: str
    ) -> tuple[bool, str | None, str | None]:
        """
        Download a single image with validation and size limits
        Returns: (success, local_path, error_message)
        """
        import ssl

        try:
            # Validate URL
            parsed = urlparse(image_url)
            if parsed.scheme not in ["http", "https"]:
                return False, None, f"Invalid URL scheme: {parsed.scheme}"

            # Check if already downloaded
            if image_url in self.image_map:
                return True, self.image_map[image_url], None

            # Generate local path
            local_path = self.get_local_path(image_url, page_url)
            full_path = self.output_dir / local_path

            # Skip if already exists
            if full_path.exists():
                logger.info(f"Image already exists: {local_path}")
                self.image_map[image_url] = local_path
                return True, local_path, None

            # First, make a HEAD request to check size
            try:
                head_response = await self.client.head(image_url, follow_redirects=True)
                content_length = int(head_response.headers.get("Content-Length", 0))

                # Check size limit (50MB)
                if content_length > 50 * 1024 * 1024:
                    return False, None, f"Image too large: {content_length / 1024 / 1024:.1f}MB"
            except Exception as e:
                logger.debug(f"HEAD request failed for {image_url}: {e}")
                # Continue with download anyway

            # Download image with timeout
            logger.info(f"Downloading image: {image_url}")

            # Handle potential redirect loops
            redirect_count = 0
            current_url = image_url

            while redirect_count < 10:
                try:
                    response = await self.client.get(
                        current_url, follow_redirects=False, timeout=30.0
                    )

                    if response.is_redirect:
                        current_url = response.headers.get("Location", "")
                        if not current_url:
                            return False, None, "Empty redirect location"
                        redirect_count += 1
                        continue
                    else:
                        break

                except ssl.SSLError as e:
                    return False, None, f"SSL error: {e}"

            if redirect_count >= 10:
                return False, None, "Too many redirects"

            response.raise_for_status()

            # Check content type
            content_type = response.headers.get("content-type", "").lower()
            if not content_type.startswith("image/"):
                logger.warning(f"Non-image content type: {content_type} for {image_url}")

            # Check actual content size
            content = response.content
            content_size = len(content)

            if content_size > 50 * 1024 * 1024:
                return False, None, f"Image content too large: {content_size / 1024 / 1024:.1f}MB"

            if content_size == 0:
                return False, None, "Empty image content"

            # Determine file extension from content type or magic bytes
            ext = self._get_image_extension(content, content_type)
            if not ext:
                return False, None, f"Invalid image format (content-type: {content_type})"

            # Update filename with correct extension
            if not str(full_path).endswith(ext):
                base = full_path.with_suffix("")
                full_path = base.with_suffix(ext)
                local_path = str(full_path.relative_to(self.output_dir)).replace("\\", "/")

            # Save image atomically
            temp_path = full_path.with_suffix(".tmp")
            try:
                async with aiofiles.open(temp_path, "wb") as f:
                    await f.write(content)

                # Atomic rename
                temp_path.replace(full_path)

            except Exception:
                if temp_path.exists():
                    temp_path.unlink()
                raise

            logger.info(f"Saved image to: {local_path} ({content_size / 1024:.1f}KB)")
            self.image_map[image_url] = local_path
            return True, local_path, None

        except httpx.ConnectError:
            return False, None, "Connection failed"
        except httpx.TimeoutException:
            return False, None, "Download timeout"
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}"
            logger.error(f"{error_msg} for {image_url}")
            return False, None, error_msg
        except Exception as e:
            error_msg = f"Failed to download: {str(e)}"
            logger.error(f"{error_msg} - {image_url}")
            return False, None, error_msg

    async def download_images(
        self, image_urls: list, page_url: str, max_concurrent: int = 5
    ) -> dict[str, str]:
        """
        Download multiple images concurrently
        Returns mapping of original URLs to local paths
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def download_with_semaphore(url: str):
            async with semaphore:
                success, local_path, error = await self.download_image(url, page_url)
                if success and local_path:
                    return url, local_path
                return url, None

        # Download all images
        tasks = [download_with_semaphore(url) for url in image_urls]
        results = await asyncio.gather(*tasks)

        # Build mapping of successful downloads
        mapping = {}
        for url, local_path in results:
            if local_path:
                mapping[url] = local_path

        return mapping

    def get_all_mappings(self) -> dict[str, str]:
        """Get all image URL to local path mappings"""
        return self.image_map.copy()

    def _get_image_extension(self, content: bytes, content_type: str) -> str | None:
        """
        Determine image file extension from content and content type.
        This replaces the deprecated imghdr module.
        """
        # Check content type first
        if content_type:
            if "svg" in content_type:
                return ".svg"
            elif "webp" in content_type:
                return ".webp"
            elif "png" in content_type:
                return ".png"
            elif "gif" in content_type:
                return ".gif"
            elif "jpeg" in content_type or "jpg" in content_type:
                return ".jpg"
            elif "bmp" in content_type:
                return ".bmp"
            elif "ico" in content_type:
                return ".ico"

        # Check magic bytes if content type doesn't help
        if len(content) < 12:
            return None

        # PNG magic bytes
        if content[:8] == b"\x89PNG\r\n\x1a\n":
            return ".png"

        # JPEG magic bytes
        elif content[:3] == b"\xff\xd8\xff":
            return ".jpg"

        # GIF magic bytes
        elif content[:6] in (b"GIF87a", b"GIF89a"):
            return ".gif"

        # WebP magic bytes
        elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
            return ".webp"

        # BMP magic bytes
        elif content[:2] == b"BM":
            return ".bmp"

        # ICO magic bytes
        elif content[:4] == b"\x00\x00\x01\x00":
            return ".ico"

        # SVG detection (text-based)
        elif b"<svg" in content[:1024] or b"<?xml" in content[:100]:
            return ".svg"

        return None
