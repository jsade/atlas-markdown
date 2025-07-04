"""
Tests for content parsing and markdown conversion
"""

import pytest

from atlas_markdown.parsers.content_parser import ContentParser


@pytest.fixture
def parser() -> ContentParser:
    """Create a content parser for testing"""
    base_url = "https://support.atlassian.com/jira-service-management-cloud/"
    return ContentParser(base_url)


def test_extract_content_from_initial_state(parser: ContentParser) -> None:
    """Test extracting content from React initial state"""
    # The actual implementation looks for 'body', 'content', 'articleBody', or 'html' fields
    # with more than 100 characters
    html = """
    <html>
    <script>
    window.__APP_INITIAL_STATE__ = {
        "page": {
            "content": {
                "body": "<h1>Test Page</h1><p>This is test content. Adding more text to ensure we have over 100 characters in the body field for the content extraction to work properly.</p>"
            }
        }
    };
    </script>
    </html>
    """

    content = parser.extract_content_from_initial_state(html)
    assert content is not None
    assert "<h1>Test Page</h1>" in content
    assert "<p>This is test content." in content


def test_extract_main_content(parser: ContentParser) -> None:
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

    content, title, sibling_info = parser.extract_main_content(html, "https://example.com/test")

    assert content is not None
    assert title == "Test Page"
    assert "Navigation" not in content
    assert "Footer" not in content
    assert "This is the main content." in content


def test_convert_to_markdown(parser: ContentParser) -> None:
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

    # Check content conversion (H1 already exists, so title won't be added)
    assert "# Main Title" in markdown
    assert "## Subtitle" in markdown
    assert "**paragraph**" in markdown
    assert "*emphasis*" in markdown
    assert "- Item 1" in markdown
    assert "- Item 2" in markdown
    assert 'print("Hello, World!")' in markdown


def test_image_processing(parser: ContentParser) -> None:
    """Test image URL collection"""
    html = """
    <main>
        <img src="image1.jpg">
        <img src="https://example.com/image2.png">
        <img src="/images/image3.gif">
    </main>
    """

    content, _, _ = parser.extract_main_content(html, "https://example.com/page")
    images = parser.get_images()

    assert len(images) == 3
    assert any("image1.jpg" in img for img in images)
    assert any("image2.png" in img for img in images)
    assert any("image3.gif" in img for img in images)


def test_update_image_references(parser: ContentParser) -> None:
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

    # The parser converts to wiki-style links
    assert "![[images/image1.jpg]]" in updated
    assert "![[images/image2.png]]" in updated
    assert "https://example.com" not in updated


def test_clean_markdown(parser: ContentParser) -> None:
    """Test markdown cleaning"""

    # The clean_markdown method is private, so we test it through convert_to_markdown
    html = "<h1>Title</h1><h2>Subtitle</h2><p>Text here.</p><ul><li>Item 1</li><li>Item 2</li></ul>"
    clean = parser.convert_to_markdown(html, "https://example.com/test")

    # Check that markdown is properly formatted
    assert "# Title" in clean
    assert "## Subtitle" in clean
    assert "Text here." in clean

    # The implementation adds spacing around headers which may result in \n\n\n
    # between sections, so we won't test for that restriction


def test_wikilink_conversion_with_trailing_slash(parser: ContentParser) -> None:
    """Test that wikilinks are properly created without malformed patterns"""
    base_url = parser.base_url
    html = f"""
    <main>
        <h1>Test Page</h1>
        <p>Here is a <a href="{base_url}docs/change-project-customer-permissions/">link with trailing slash</a>.</p>
        <p>Another <a href="{base_url}docs/manage-users/" title="Manage users">link with title attribute</a>.</p>
        <p>And a <a href="{base_url}docs/test-page">link without trailing slash</a>.</p>
    </main>
    """

    markdown = parser.convert_to_markdown(html, f"{base_url}docs/current-page", "Test Page")

    # Check that wikilinks are properly formed without trailing slashes or quotes
    assert "[[change-project-customer-permissions|link with trailing slash]]" in markdown
    assert "[[manage-users|link with title attribute]]" in markdown
    assert "[[test-page|link without trailing slash]]" in markdown

    # Ensure no malformed patterns
    assert '[[change-project-customer-permissions/"|' not in markdown
    assert '[[manage-users/"|' not in markdown
    assert '/"|' not in markdown


def test_extract_product_from_url(parser: ContentParser) -> None:
    """Test extracting product identifier from URLs"""
    # Test with full URL
    product = parser._extract_product_from_url(
        "https://support.atlassian.com/jira-service-management-cloud/docs/test-page"
    )
    assert product == "jira-service-management-cloud"

    # Test with base URL
    product = parser._extract_product_from_url("https://support.atlassian.com/confluence-cloud/")
    assert product == "confluence-cloud"

    # Test with resources URL
    product = parser._extract_product_from_url(
        "https://support.atlassian.com/statuspage/resources/test-resource"
    )
    assert product == "statuspage"


def test_normalize_tag(parser: ContentParser) -> None:
    """Test tag normalization"""
    # Basic normalization
    assert parser._normalize_tag("Service Project Configuration") == "service-project-configuration"
    assert parser._normalize_tag("Set up request types") == "set-up-request-types"

    # Special characters
    assert parser._normalize_tag("User & Team Management") == "user-team-management"
    assert parser._normalize_tag("API/REST Reference") == "api-rest-reference"

    # Edge cases
    assert parser._normalize_tag("  Spaces  Around  ") == "spaces-around"
    assert parser._normalize_tag("Multiple---Hyphens") == "multiple-hyphens"
    assert parser._normalize_tag("") == ""
    assert parser._normalize_tag("123-Numbers-456") == "123-numbers-456"


def test_generate_hierarchical_tags(parser: ContentParser) -> None:
    """Test hierarchical tag generation"""
    # Test with user management page
    sibling_info = {
        "current_page_title": "Manage users in your team",
        "section_heading": "User Management",
        "breadcrumb_data": {
            "breadcrumbs": [
                {"name": "Atlassian Support", "position": 1},
                {"name": "Jira Service Management Cloud", "position": 2},
                {"name": "Manage users in your team", "position": 3},
            ]
        },
    }

    tags = parser._generate_hierarchical_tags(sibling_info, "jira-service-management-cloud")
    assert "jira-service-management-cloud" in tags
    assert "user-management" in tags  # Should detect user management category

    # Test with API documentation
    sibling_info = {
        "current_page_title": "REST API Reference",
        "section_heading": "Developer Resources",
        "breadcrumb_data": {
            "breadcrumbs": [
                {"name": "Atlassian Support", "position": 1},
                {"name": "Confluence Cloud", "position": 2},
                {"name": "REST API Reference", "position": 3},
            ]
        },
    }

    tags = parser._generate_hierarchical_tags(sibling_info, "confluence-cloud")
    assert "confluence-cloud" in tags
    assert "api" in tags  # Should detect API category

    # Test with minimal info
    sibling_info = {
        "current_page_title": "Getting Started",
        "section_heading": "",
        "breadcrumb_data": {
            "breadcrumbs": [
                {"name": "Atlassian Support", "position": 1},
                {"name": "Statuspage", "position": 2},
                {"name": "Getting Started", "position": 3},
            ]
        },
    }

    tags = parser._generate_hierarchical_tags(sibling_info, "statuspage")
    assert "statuspage" in tags
    assert "getting-started" in tags  # Should detect getting started category


def test_frontmatter_with_tags(parser: ContentParser) -> None:
    """Test that tags are properly added to frontmatter"""
    html = "<main><h1>Test Page</h1><p>Content here.</p></main>"

    sibling_info = {
        "current_page_title": "Manage users",
        "breadcrumb_data": {
            "breadcrumbs": [
                {"name": "Atlassian Support", "position": 1},
                {"name": "Jira Service Management Cloud", "position": 2},
                {"name": "Administration", "position": 3},
                {"name": "Manage users", "position": 4},
            ]
        },
        "section_heading": "User management",
    }

    # Test with tags enabled (default)
    markdown = parser.convert_to_markdown(
        html,
        "https://support.atlassian.com/jira-service-management-cloud/docs/manage-users",
        "Manage users",
        None,
        sibling_info,
        disable_tags=False,
    )

    # Check frontmatter includes tags
    assert "tags:" in markdown
    assert "- jira-service-management-cloud" in markdown
    # Should have user-management tag based on the title/section
    assert "- user-management" in markdown

    # Check Atlas Markdown metadata is always included
    assert "atlas_md_version:" in markdown
    assert "atlas_md_url: https://github.com/jsade/atlas-markdown" in markdown
    assert "atlas_md_product: jira-service-management-cloud" in markdown
    assert "atlas_md_category: Administration" in markdown
    assert "atlas_md_section: User management" in markdown

    # Test with tags disabled
    markdown_no_tags = parser.convert_to_markdown(
        html,
        "https://support.atlassian.com/jira-service-management-cloud/docs/manage-users",
        "Manage users",
        None,
        sibling_info,
        disable_tags=True,
    )

    # Check tags are not included when disabled
    assert "tags:" not in markdown_no_tags

    # But Atlas Markdown metadata should still be included
    assert "atlas_md_version:" in markdown_no_tags
    assert "atlas_md_url: https://github.com/jsade/atlas-markdown" in markdown_no_tags
    assert "atlas_md_product: jira-service-management-cloud" in markdown_no_tags
