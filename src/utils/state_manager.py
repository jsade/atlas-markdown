"""
State management for tracking scraping progress
Allows resuming interrupted scraping sessions
"""

import asyncio
import logging
from enum import Enum
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class PageStatus(Enum):
    """Status of a scraped page"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StateManager:
    """Manages scraping state in SQLite database"""

    def __init__(self, db_path: str = "scraper_state.db"):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def initialize(self):
        """Initialize database connection and create tables"""
        max_retries = 3

        for attempt in range(max_retries):
            try:
                self._db = await aiosqlite.connect(
                    self.db_path, timeout=30.0  # Increase timeout for locked databases
                )
                self._db.row_factory = aiosqlite.Row

                # Enable WAL mode for better concurrency
                await self._db.execute("PRAGMA journal_mode=WAL")
                await self._db.execute("PRAGMA synchronous=NORMAL")
                await self._db.execute("PRAGMA cache_size=10000")  # 10MB cache
                await self._db.execute("PRAGMA temp_store=MEMORY")

                # Check database integrity
                cursor = await self._db.execute("PRAGMA integrity_check")
                result = await cursor.fetchone()
                if result[0] != "ok":
                    logger.warning(f"Database integrity check: {result[0]}")
                    # Try to recover
                    await self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

                # Create tables
                await self._db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pages (
                        url TEXT PRIMARY KEY,
                        status TEXT NOT NULL DEFAULT 'pending',
                        title TEXT,
                        content_hash TEXT,
                        file_path TEXT,
                        error_message TEXT,
                        retry_count INTEGER DEFAULT 0,
                        crawl_depth INTEGER DEFAULT 0,
                        parent_url TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP
                    )
                """
                )

                # Create index for better performance
                await self._db.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_pages_status
                    ON pages(status, retry_count)
                """
                )

                # Add crawl_depth column if it doesn't exist (for existing databases)
                cursor = await self._db.execute("PRAGMA table_info(pages)")
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]

                if "crawl_depth" not in column_names:
                    await self._db.execute(
                        "ALTER TABLE pages ADD COLUMN crawl_depth INTEGER DEFAULT 0"
                    )
                    logger.info("Added crawl_depth column to existing database")

                if "parent_url" not in column_names:
                    await self._db.execute("ALTER TABLE pages ADD COLUMN parent_url TEXT")
                    logger.info("Added parent_url column to existing database")

                await self._db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS images (
                        url TEXT PRIMARY KEY,
                        page_url TEXT NOT NULL,
                        local_path TEXT,
                        downloaded BOOLEAN DEFAULT FALSE,
                        error_message TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (page_url) REFERENCES pages (url)
                    )
                """
                )

                await self._db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scraper_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        pages_total INTEGER DEFAULT 0,
                        pages_completed INTEGER DEFAULT 0,
                        pages_failed INTEGER DEFAULT 0,
                        images_total INTEGER DEFAULT 0,
                        images_downloaded INTEGER DEFAULT 0
                    )
                """
                )

                await self._db.commit()
                logger.info("Database initialized successfully")
                break

            except aiosqlite.OperationalError as e:
                if "locked" in str(e) and attempt < max_retries - 1:
                    logger.warning(f"Database locked, retrying in {2 ** attempt} seconds...")
                    await asyncio.sleep(2**attempt)
                else:
                    raise
            except Exception as e:
                logger.error(f"Database initialization failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2**attempt)
                else:
                    raise

    async def close(self):
        """Close database connection"""
        if self._db:
            await self._db.close()

    async def start_run(self) -> int:
        """Start a new scraper run and return run ID"""
        cursor = await self._db.execute("INSERT INTO scraper_runs DEFAULT VALUES")
        await self._db.commit()
        return cursor.lastrowid

    async def update_run_stats(self, run_id: int):
        """Update run statistics"""
        stats = await self.get_statistics()
        await self._db.execute(
            """
            UPDATE scraper_runs
            SET pages_total = ?, pages_completed = ?, pages_failed = ?,
                images_total = ?, images_downloaded = ?
            WHERE id = ?
        """,
            (
                stats["pages"]["total"],
                stats["pages"]["completed"],
                stats["pages"]["failed"],
                stats["images"]["total"],
                stats["images"]["downloaded"],
                run_id,
            ),
        )
        await self._db.commit()

    async def complete_run(self, run_id: int):
        """Mark a run as completed"""
        await self.update_run_stats(run_id)
        await self._db.execute(
            "UPDATE scraper_runs SET completed_at = CURRENT_TIMESTAMP WHERE id = ?", (run_id,)
        )
        await self._db.commit()

    async def add_page(
        self,
        url: str,
        title: str | None = None,
        crawl_depth: int = 0,
        parent_url: str | None = None,
    ):
        """Add a page to be scraped with retry on lock"""
        max_retries = 3

        for attempt in range(max_retries):
            try:
                await self._db.execute(
                    """
                    INSERT OR IGNORE INTO pages (url, title, status, crawl_depth, parent_url)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (url, title, PageStatus.PENDING.value, crawl_depth, parent_url),
                )
                await self._db.commit()
                break
            except aiosqlite.OperationalError as e:
                if "locked" in str(e) and attempt < max_retries - 1:
                    logger.debug(f"Database locked when adding page, retry {attempt + 1}")
                    await asyncio.sleep(0.5 * (attempt + 1))
                else:
                    raise

    async def get_page_status(self, url: str) -> str | None:
        """Get the status of a page"""
        cursor = await self._db.execute("SELECT status FROM pages WHERE url = ?", (url,))
        row = await cursor.fetchone()
        return row["status"] if row else None

    async def get_page_info(self, url: str) -> dict | None:
        """Get full information about a page"""
        cursor = await self._db.execute(
            "SELECT url, status, crawl_depth, parent_url FROM pages WHERE url = ?", (url,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def update_page_status(
        self,
        url: str,
        status: PageStatus,
        file_path: str | None = None,
        content_hash: str | None = None,
        error_message: str | None = None,
    ):
        """Update the status of a page"""
        query = """
            UPDATE pages
            SET status = ?, updated_at = CURRENT_TIMESTAMP
        """
        params = [status.value]

        if file_path:
            query += ", file_path = ?"
            params.append(file_path)

        if content_hash:
            query += ", content_hash = ?"
            params.append(content_hash)

        if error_message:
            query += ", error_message = ?"
            params.append(error_message)

        if status == PageStatus.COMPLETED:
            query += ", completed_at = CURRENT_TIMESTAMP"
        elif status == PageStatus.FAILED:
            query += ", retry_count = retry_count + 1"

        query += " WHERE url = ?"
        params.append(url)

        await self._db.execute(query, params)
        await self._db.commit()

    async def get_pending_pages(
        self, limit: int | None = None, max_depth: int | None = None
    ) -> list[dict[str, Any]]:
        """Get pages that need to be scraped"""
        query = """
            SELECT url, title, retry_count, crawl_depth
            FROM pages
            WHERE status IN (?, ?)
        """
        params = [PageStatus.PENDING.value, PageStatus.FAILED.value]

        if max_depth is not None:
            query += " AND crawl_depth <= ?"
            params.append(max_depth)

        query += " ORDER BY crawl_depth ASC, retry_count ASC, created_at ASC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def add_image(self, url: str, page_url: str):
        """Add an image to be downloaded"""
        await self._db.execute(
            """
            INSERT OR IGNORE INTO images (url, page_url)
            VALUES (?, ?)
        """,
            (url, page_url),
        )
        await self._db.commit()

    async def update_image(
        self,
        url: str,
        local_path: str | None = None,
        downloaded: bool = False,
        error_message: str | None = None,
    ):
        """Update image download status"""
        query = "UPDATE images SET downloaded = ?"
        params = [downloaded]

        if local_path:
            query += ", local_path = ?"
            params.append(local_path)

        if error_message:
            query += ", error_message = ?"
            params.append(error_message)

        query += " WHERE url = ?"
        params.append(url)

        await self._db.execute(query, params)
        await self._db.commit()

    async def get_pending_images(self) -> list[dict[str, Any]]:
        """Get images that need to be downloaded"""
        cursor = await self._db.execute(
            """
            SELECT url, page_url
            FROM images
            WHERE downloaded = FALSE AND error_message IS NULL
        """
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_statistics(self) -> dict[str, Any]:
        """Get scraping statistics"""
        # Page statistics
        cursor = await self._db.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as in_progress
            FROM pages
        """,
            (
                PageStatus.COMPLETED.value,
                PageStatus.FAILED.value,
                PageStatus.PENDING.value,
                PageStatus.IN_PROGRESS.value,
            ),
        )
        page_stats = dict(await cursor.fetchone())

        # Image statistics
        cursor = await self._db.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN downloaded = TRUE THEN 1 ELSE 0 END) as downloaded,
                SUM(CASE WHEN error_message IS NOT NULL THEN 1 ELSE 0 END) as failed
            FROM images
        """
        )
        image_stats = dict(await cursor.fetchone())

        return {"pages": page_stats, "images": image_stats}

    async def get_failed_pages(self) -> list[dict[str, Any]]:
        """Get pages that failed to scrape"""
        cursor = await self._db.execute(
            """
            SELECT url, error_message, retry_count, updated_at
            FROM pages
            WHERE status = ?
            ORDER BY updated_at DESC
        """,
            (PageStatus.FAILED.value,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def reset_in_progress(self):
        """Reset any in-progress pages to pending (for recovery)"""
        await self._db.execute(
            """
            UPDATE pages
            SET status = ?
            WHERE status = ?
        """,
            (PageStatus.PENDING.value, PageStatus.IN_PROGRESS.value),
        )
        await self._db.commit()

    async def clear_all(self):
        """Clear all data (for fresh start)"""
        await self._db.execute("DELETE FROM images")
        await self._db.execute("DELETE FROM pages")
        await self._db.execute("DELETE FROM scraper_runs")

    async def get_failed_pages_for_retry(self, max_retries: int = 3) -> list[dict[str, Any]]:
        """Get failed pages that haven't exceeded max retry attempts"""
        cursor = await self._db.execute(
            """
            SELECT url, title, retry_count, error_message
            FROM pages
            WHERE status = ? AND retry_count < ?
            ORDER BY retry_count ASC, updated_at ASC
        """,
            (PageStatus.FAILED.value, max_retries),
        )

        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_retry_candidates(
        self, max_retries: int = 3, delay_minutes: int = 5
    ) -> list[dict[str, Any]]:
        """Get failed pages eligible for retry based on time delay"""
        cursor = await self._db.execute(
            """
            SELECT url, title, retry_count, error_message
            FROM pages
            WHERE status = ?
            AND retry_count < ?
            AND datetime(updated_at, '+' || ? || ' minutes') <= datetime('now')
            ORDER BY retry_count ASC, updated_at ASC
        """,
            (PageStatus.FAILED.value, max_retries, delay_minutes),
        )

        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def reset_for_retry(self, url: str):
        """Reset a failed page for retry"""
        await self._db.execute(
            """
            UPDATE pages
            SET status = ?, error_message = NULL
            WHERE url = ?
        """,
            (PageStatus.PENDING.value, url),
        )
        await self._db.commit()

    async def get_permanently_failed_pages(self, max_retries: int = 3) -> list[dict[str, Any]]:
        """Get pages that have exceeded max retry attempts"""
        cursor = await self._db.execute(
            """
            SELECT url, title, retry_count, error_message
            FROM pages
            WHERE status = ? AND retry_count >= ?
            ORDER BY updated_at DESC
        """,
            (PageStatus.FAILED.value, max_retries),
        )

        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
