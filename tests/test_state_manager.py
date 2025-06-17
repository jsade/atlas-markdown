"""
Tests for state management functionality
"""

import os
import tempfile
from collections.abc import AsyncGenerator

import pytest

from atlas_markdown.utils.state_manager import PageStatus, StateManager


@pytest.fixture
async def state_manager() -> AsyncGenerator[StateManager, None]:
    """Create a temporary state manager for testing"""
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        db_path = tmp.name

    manager = StateManager(db_path)
    await manager.initialize()

    yield manager

    await manager.close()
    os.unlink(db_path)


@pytest.mark.asyncio
async def test_page_lifecycle(state_manager: StateManager) -> None:
    """Test adding and updating page status"""
    url = "https://example.com/page1"

    # Add page
    await state_manager.add_page(url, "Test Page")

    # Check initial status
    status = await state_manager.get_page_status(url)
    assert status == PageStatus.PENDING.value

    # Update to in progress
    await state_manager.update_page_status(url, PageStatus.IN_PROGRESS)
    status = await state_manager.get_page_status(url)
    assert status == PageStatus.IN_PROGRESS.value

    # Complete the page
    await state_manager.update_page_status(
        url, PageStatus.COMPLETED, file_path="docs/page1.md", content_hash="abc123"
    )
    status = await state_manager.get_page_status(url)
    assert status == PageStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_pending_pages(state_manager: StateManager) -> None:
    """Test retrieving pending pages"""
    # Add multiple pages
    pages = [
        ("https://example.com/page1", "Page 1"),
        ("https://example.com/page2", "Page 2"),
        ("https://example.com/page3", "Page 3"),
    ]

    for url, title in pages:
        await state_manager.add_page(url, title)

    # Mark one as completed
    await state_manager.update_page_status(pages[0][0], PageStatus.COMPLETED)

    # Get pending pages
    pending = await state_manager.get_pending_pages()
    assert len(pending) == 2
    assert all(p["url"] in [pages[1][0], pages[2][0]] for p in pending)


@pytest.mark.asyncio
async def test_image_tracking(state_manager: StateManager) -> None:
    """Test image tracking functionality"""
    page_url = "https://example.com/page1"
    img_url = "https://example.com/image.jpg"

    # Add page and image
    await state_manager.add_page(page_url)
    await state_manager.add_image(img_url, page_url)

    # Get pending images
    images = await state_manager.get_pending_images()
    assert len(images) == 1
    assert images[0]["url"] == img_url

    # Mark as downloaded
    await state_manager.update_image(img_url, local_path="images/image.jpg", downloaded=True)

    # Should have no pending images
    images = await state_manager.get_pending_images()
    assert len(images) == 0


@pytest.mark.asyncio
async def test_statistics(state_manager: StateManager) -> None:
    """Test statistics calculation"""
    # Add pages with different statuses
    await state_manager.add_page("https://example.com/page1")
    await state_manager.add_page("https://example.com/page2")
    await state_manager.add_page("https://example.com/page3")

    await state_manager.update_page_status("https://example.com/page1", PageStatus.COMPLETED)
    await state_manager.update_page_status("https://example.com/page2", PageStatus.FAILED)

    stats = await state_manager.get_statistics()

    assert stats["pages"]["total"] == 3
    assert stats["pages"]["completed"] == 1
    assert stats["pages"]["failed"] == 1
    assert stats["pages"]["pending"] == 1


@pytest.mark.asyncio
async def test_reset_in_progress(state_manager: StateManager) -> None:
    """Test resetting in-progress pages"""
    url = "https://example.com/page1"

    await state_manager.add_page(url)
    await state_manager.update_page_status(url, PageStatus.IN_PROGRESS)

    # Reset in progress
    await state_manager.reset_in_progress()

    # Should be pending again
    status = await state_manager.get_page_status(url)
    assert status == PageStatus.PENDING.value
