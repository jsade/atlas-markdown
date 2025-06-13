"""
Tests for content parsing and markdown conversion
"""

import pytest

from src.parsers.content_parser import ContentParser


@pytest.fixture
def parser():
    """Create a content parser for testing"""
    base_url = "https://support.atlassian.com/jira-service-management-cloud/"
    return ContentParser(base_url)


def test_extract_content_from_initial_state(parser):
    """Test extracting content from React initial state"""
    html = """
    <html>
    <script>
    window.__APP_INITIAL_STATE__ = {
        "page": {
            "content": {
                "body": "<h1>Test Page</h1><p>This is test content.</p>"
            }
        }
    };
    </script>
    </html>
    """

    content = parser.extract_content_from_initial_state(html)
    assert content is not None
    assert "<h1>Test Page</h1>" in content
    assert "<p>This is test content.</p>" in content


def test_extract_main_content(parser):
    """Test extracting main content from HTML"""
    html = """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <nav>Navigation</nav>
        <main>
            <h1>Test Page</h1>
            <p>This is the main content.</p>
            <img src="test.jpg" alt="Test image">
        </main>
        <footer>Footer</footer>
    </body>
    </html>
    """

    content, title = parser.extract_main_content(html, "https://example.com/test")

    assert content is not None
    assert title == "Test Page"
    assert "Navigation" not in content
    assert "Footer" not in content
    assert "This is the main content." in content


def test_convert_to_markdown(parser):
    """Test HTML to Markdown conversion"""
    html = """
    <div>
        <h1>Main Title</h1>
        <h2>Subtitle</h2>
        <p>This is a <strong>paragraph</strong> with <em>emphasis</em>.</p>
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
        </ul>
        <pre><code>print("Hello, World!")</code></pre>
    </div>
    """

    markdown = parser.convert_to_markdown(html, "https://example.com/test", "Test Page")

    # Check metadata
    assert "---" in markdown
    assert "url: https://example.com/test" in markdown

    # Check title
    assert "# Test Page" in markdown

    # Check content conversion
    assert "# Main Title" in markdown
    assert "## Subtitle" in markdown
    assert "**paragraph**" in markdown
    assert "*emphasis*" in markdown
    assert "- Item 1" in markdown
    assert "- Item 2" in markdown
    assert 'print("Hello, World!")' in markdown


def test_image_processing(parser):
    """Test image URL collection"""
    html = """
    <main>
        <img src="image1.jpg">
        <img src="https://example.com/image2.png">
        <img src="/images/image3.gif">
    </main>
    """

    content, _ = parser.extract_main_content(html, "https://example.com/page")
    images = parser.get_images()

    assert len(images) == 3
    assert any("image1.jpg" in img for img in images)
    assert any("image2.png" in img for img in images)
    assert any("image3.gif" in img for img in images)


def test_update_image_references(parser):
    """Test updating image references in markdown"""
    markdown = """
# Test Page

Here is an image: ![Alt text](https://example.com/image1.jpg)

Another image: ![](https://example.com/image2.png)
"""

    image_map = {
        "https://example.com/image1.jpg": "images/image1.jpg",
        "https://example.com/image2.png": "images/image2.png",
    }

    updated = parser.update_image_references(markdown, image_map)

    assert "![Alt text](images/image1.jpg)" in updated
    assert "![](images/image2.png)" in updated
    assert "https://example.com" not in updated


def test_clean_markdown(parser):
    """Test markdown cleaning"""

    # The clean_markdown method is private, so we test it through convert_to_markdown
    html = "<h1>Title</h1><h2>Subtitle</h2><p>Text here.</p><ul><li>Item 1</li><li>Item 2</li></ul>"
    clean = parser.convert_to_markdown(html, "https://example.com/test")

    # Should not have excessive blank lines
    assert "\n\n\n" not in clean
    # Should have proper spacing around headers
    lines = clean.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("#"):
            # Should have blank line before header (unless it's the first line or after metadata)
            if i > 3:  # Skip metadata section
                assert lines[i - 1] == "" or lines[i - 1].startswith("#")
            # Should have blank line after header
            if i < len(lines) - 1:
                assert lines[i + 1] == "" or lines[i + 1].startswith("#")
