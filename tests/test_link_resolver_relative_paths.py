"""Test LinkResolver relative path functionality"""

import pytest

from atlas_markdown.parsers.link_resolver import LinkResolver


@pytest.fixture
def resolver() -> LinkResolver:
    """Create a link resolver for testing"""
    return LinkResolver("https://support.atlassian.com/jira-service-management-cloud")


def test_calculate_relative_path(resolver: LinkResolver) -> None:
    """Test the _calculate_relative_path method"""
    # Test same directory
    assert (
        resolver._calculate_relative_path(
            "docs/Getting started/page1.md", "docs/Getting started/page2"
        )
        == "page2"
    )

    # Test subdirectory
    assert (
        resolver._calculate_relative_path(
            "docs/Getting started/page1.md", "docs/Getting started/Advanced/page2"
        )
        == "Advanced/page2"
    )

    # Test parent directory
    assert (
        resolver._calculate_relative_path(
            "docs/Getting started/Advanced/page1.md", "docs/Getting started/page2"
        )
        == "../page2"
    )

    # Test sibling directory
    assert (
        resolver._calculate_relative_path(
            "docs/Getting started/page1.md", "docs/Configuration/page2"
        )
        == "../Configuration/page2"
    )

    # Test multiple levels up
    assert (
        resolver._calculate_relative_path(
            "docs/Getting started/Advanced/Deep/page1.md", "docs/Configuration/page2"
        )
        == "../../../Configuration/page2"
    )


def test_resolve_url_to_wikilink_with_relative_paths(resolver: LinkResolver) -> None:
    """Test URL to wikilink conversion with relative paths"""
    # Add some page mappings
    resolver.add_page_mapping(
        "https://support.atlassian.com/jira-service-management-cloud/docs/set-up-your-knowledge-base-with-confluence/",
        "Set up your knowledge base with Confluence",
        "docs/Set up a knowledge base so customers can serve themselves/Set up your knowledge base.md",
    )

    resolver.add_page_mapping(
        "https://support.atlassian.com/jira-service-management-cloud/docs/understand-how-to-add-knowledge-to-your-service-project/",
        "Understand how to add knowledge to your service project",
        "docs/Add knowledge to help customers/Understand how to add knowledge to your service project.md",
    )

    # Test relative path resolution
    result = resolver.resolve_url_to_wikilink(
        "https://support.atlassian.com/jira-service-management-cloud/docs/set-up-your-knowledge-base-with-confluence/",
        "set up a new knowledge base",
        "docs/Add knowledge to help customers/Understand how to add knowledge to your service project.md",
    )

    assert (
        result
        == "[[../Set up a knowledge base so customers can serve themselves/Set up your knowledge base|set up a new knowledge base]]"
    )


def test_convert_markdown_links_with_relative_paths(resolver: LinkResolver) -> None:
    """Test converting markdown links to wikilinks with relative paths"""
    # Add page mappings
    resolver.add_page_mapping(
        "https://support.atlassian.com/jira-service-management-cloud/docs/change-project-customer-permissions/",
        "Change project customer permissions",
        "docs/Configure permissions/Change project customer permissions.md",
    )

    # Test markdown with links
    markdown = """
# Test Page

Here is a [link to permissions](https://support.atlassian.com/jira-service-management-cloud/docs/change-project-customer-permissions/).

And [another link](https://external.com/page).
"""

    current_page_path = "docs/Getting started/Test page.md"

    result = resolver.convert_markdown_links(
        markdown,
        "https://support.atlassian.com/jira-service-management-cloud/docs/test-page/",
        current_page_path,
    )

    assert (
        "[[../Configure permissions/Change project customer permissions|link to permissions]]"
        in result
    )
    assert "[another link](https://external.com/page)" in result  # External links unchanged


def test_fix_malformed_wikilinks_to_relative_paths(resolver: LinkResolver) -> None:
    """Test fixing malformed wikilinks to use relative paths"""
    # Add page mappings
    resolver.add_page_mapping(
        "https://support.atlassian.com/jira-service-management-cloud/docs/delete-account-for-a-customer/",
        "Delete account for a customer",
        "docs/Manage customers/Delete account for a customer.md",
    )

    # Markdown with malformed wikilink
    markdown = """
# Test Page

You can [[delete-account-for-a-customer|delete the customer's account]] from here.
"""

    current_page_path = "docs/Configure permissions/Test page.md"

    result = resolver.convert_markdown_links(
        markdown,
        "https://support.atlassian.com/jira-service-management-cloud/docs/test-page/",
        current_page_path,
    )

    # The wikilink should be fixed to use relative path
    assert (
        "[[../Manage customers/Delete account for a customer|delete the customer's account]]"
        in result
    )
