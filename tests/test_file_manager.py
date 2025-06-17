"""
Tests for file system management
"""

import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from atlas_markdown.utils.file_manager import FileSystemManager


@pytest.fixture
def file_manager() -> Generator[FileSystemManager, None, None]:
    """Create a temporary file manager for testing"""
    temp_dir = tempfile.mkdtemp()
    base_url = "https://support.atlassian.com/jira-service-management-cloud/"

    manager = FileSystemManager(temp_dir, base_url)

    yield manager

    # Cleanup
    shutil.rmtree(temp_dir)


def test_url_to_filepath_basic(file_manager: FileSystemManager) -> None:
    """Test basic URL to filepath conversion"""
    url = "https://support.atlassian.com/jira-service-management-cloud/docs/getting-started"

    directory, filename = file_manager.url_to_filepath(url)

    assert directory.name == "docs"
    assert (
        filename == "Getting Started.md"
    )  # Converted from slug to proper name with capitalized 'Started'


def test_url_to_filepath_index(file_manager: FileSystemManager) -> None:
    """Test URL ending with slash creates index.md"""
    url = "https://support.atlassian.com/jira-service-management-cloud/docs/"

    directory, filename = file_manager.url_to_filepath(url)

    assert directory.name == "docs"
    assert filename == "index.md"


def test_url_to_filepath_root(file_manager: FileSystemManager) -> None:
    """Test root URL creates index.md at root"""
    url = "https://support.atlassian.com/jira-service-management-cloud/"

    directory, filename = file_manager.url_to_filepath(url)

    assert directory == file_manager.output_dir
    assert filename == "index.md"


def test_url_to_filepath_special_chars(file_manager: FileSystemManager) -> None:
    """Test handling of special characters in URLs"""
    url = "https://support.atlassian.com/jira-service-management-cloud/docs/what's-new?"

    directory, filename = file_manager.url_to_filepath(url)

    # Special characters should be replaced or removed
    assert "?" not in filename
    # Single quotes are allowed in the converted name


@pytest.mark.asyncio
async def test_save_content(file_manager: FileSystemManager) -> None:
    """Test saving content to file"""
    url = "https://support.atlassian.com/jira-service-management-cloud/docs/test-page"
    content = "# Test Page\n\nThis is test content."

    file_path = await file_manager.save_content(url, content)

    # Check file was created
    full_path = file_manager.output_dir / file_path
    assert full_path.exists()

    # Check content
    with open(full_path) as f:
        saved_content = f.read()
    assert saved_content == content


@pytest.mark.asyncio
async def test_save_content_duplicate(file_manager: FileSystemManager) -> None:
    """Test handling duplicate filenames"""
    url = "https://support.atlassian.com/jira-service-management-cloud/docs/test-page"
    content1 = "# Test Page\n\nFirst version."
    content2 = "# Test Page\n\nSecond version."

    # Save first version
    file_path1 = await file_manager.save_content(url, content1)

    # Save second version (different content)
    file_path2 = await file_manager.save_content(url, content2)

    # Should have different filenames
    assert file_path1 != file_path2
    assert "_1" in file_path2

    # Both files should exist
    assert (file_manager.output_dir / file_path1).exists()
    assert (file_manager.output_dir / file_path2).exists()


@pytest.mark.asyncio
async def test_create_index(file_manager: FileSystemManager) -> None:
    """Test index generation"""
    pages = [
        {
            "url": "https://example.com/docs/page1",
            "title": "Page 1",
            "file_path": "docs/page1.md",
            "status": "completed",
        },
        {
            "url": "https://example.com/docs/page2",
            "title": "Page 2",
            "file_path": "docs/page2.md",
            "status": "completed",
        },
        {
            "url": "https://example.com/guide/intro",
            "title": "Introduction",
            "file_path": "guide/intro.md",
            "status": "completed",
        },
    ]

    index_path = await file_manager.create_index(pages)

    # Check index was created
    assert Path(index_path).exists()

    # Check content
    with open(index_path) as f:
        content = f.read()

    assert "# Documentation Index" in content
    assert "Page 1" in content
    assert "Page 2" in content
    # Only docs/ content is included in the index
    assert "Introduction" not in content  # guide/intro.md is not in docs/
    assert "Total documentation pages: 2" in content  # Only 2 docs/ pages
