#!/usr/bin/env python3
"""Regenerate the index file for scraped documentation"""

import asyncio
import sys
from pathlib import Path

from atlas_markdown.utils.file_manager import FileSystemManager
from atlas_markdown.utils.state_manager import StateManager


async def regenerate_index(output_dir: str) -> None:
    """Regenerate the index file"""
    base_url = "https://support.atlassian.com/jira-service-management-cloud/"

    # Initialize managers
    file_manager = FileSystemManager(output_dir, base_url)
    state_manager = StateManager("scraper_state.db")  # Database file path

    await state_manager.initialize()

    # Get all pages
    if state_manager._db is not None:
        cursor = await state_manager._db.execute(
            "SELECT url, title, file_path, status FROM pages ORDER BY url"
        )
        pages = await cursor.fetchall()
    else:
        print("Error: Database connection not available")
        return

    # Convert to list of dicts
    pages_list = [dict(p) for p in pages]

    print(f"Found {len(pages_list)} pages")

    # Create index
    index_path = await file_manager.create_index(pages_list)

    print(f"Index created at: {index_path}")

    await state_manager.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python regenerate_index.py <output_dir>")
        sys.exit(1)

    output_dir = sys.argv[1]

    if not Path(output_dir).exists():
        print(f"Error: Output directory {output_dir} does not exist")
        sys.exit(1)

    asyncio.run(regenerate_index(output_dir))
