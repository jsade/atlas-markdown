"""Test LinkResolver redirect handling functionality"""

import pytest

from atlas_markdown.parsers.link_resolver import LinkResolver
from atlas_markdown.utils.redirect_handler import RedirectHandler


@pytest.fixture
def redirect_handler() -> RedirectHandler:
    """Create a redirect handler with test data"""
    handler = RedirectHandler()

    # Add some test redirects
    handler.add_redirect(
        "https://support.atlassian.com/statuspage/docs/transfer-account-ownership/",
        "https://support.atlassian.com/statuspage/docs/create-and-manage-your-user-accounts/",
    )

    # Add a redirect chain
    handler.add_redirect(
        "https://support.atlassian.com/jira/docs/old-page/",
        "https://support.atlassian.com/jira/docs/intermediate-page/",
    )
    handler.add_redirect(
        "https://support.atlassian.com/jira/docs/intermediate-page/",
        "https://support.atlassian.com/jira/docs/final-page/",
    )

    return handler


@pytest.fixture
def resolver_with_redirects(redirect_handler: RedirectHandler) -> LinkResolver:
    """Create a link resolver with redirect handler"""
    resolver = LinkResolver("https://support.atlassian.com/statuspage", redirect_handler)

    # Add page mappings for redirect targets
    resolver.add_page_mapping(
        "https://support.atlassian.com/statuspage/docs/create-and-manage-your-user-accounts/",
        "Create and manage your user accounts",
        "docs/Manage users/Create and manage your user accounts.md",
    )

    resolver.add_page_mapping(
        "https://support.atlassian.com/jira/docs/final-page/", "Final Page", "docs/Final Page.md"
    )

    return resolver


def test_follow_redirects_single_redirect(resolver_with_redirects: LinkResolver) -> None:
    """Test following a single redirect"""
    result = resolver_with_redirects._follow_redirects(
        "https://support.atlassian.com/statuspage/docs/transfer-account-ownership/"
    )
    # URL is normalized without trailing slash
    assert (
        result
        == "https://support.atlassian.com/statuspage/docs/create-and-manage-your-user-accounts"
    )


def test_follow_redirects_chain(resolver_with_redirects: LinkResolver) -> None:
    """Test following a redirect chain"""
    result = resolver_with_redirects._follow_redirects(
        "https://support.atlassian.com/jira/docs/old-page/"
    )
    # URL is normalized without trailing slash
    assert result == "https://support.atlassian.com/jira/docs/final-page"


def test_follow_redirects_no_redirect(resolver_with_redirects: LinkResolver) -> None:
    """Test URL with no redirects"""
    result = resolver_with_redirects._follow_redirects(
        "https://support.atlassian.com/statuspage/docs/normal-page/"
    )
    assert result == "https://support.atlassian.com/statuspage/docs/normal-page/"


def test_follow_redirects_loop_detection(redirect_handler: RedirectHandler) -> None:
    """Test redirect loop detection"""
    # Create a redirect loop
    redirect_handler.add_redirect(
        "https://support.atlassian.com/jira/docs/page-a/",
        "https://support.atlassian.com/jira/docs/page-b/",
    )
    redirect_handler.add_redirect(
        "https://support.atlassian.com/jira/docs/page-b/",
        "https://support.atlassian.com/jira/docs/page-a/",
    )

    resolver = LinkResolver("https://support.atlassian.com/jira", redirect_handler)

    # Should detect loop and return one of the URLs (normalized without trailing slash)
    result = resolver._follow_redirects("https://support.atlassian.com/jira/docs/page-a/")
    assert result in [
        "https://support.atlassian.com/jira/docs/page-a",
        "https://support.atlassian.com/jira/docs/page-b",
    ]


def test_resolve_url_to_wikilink_with_redirect(resolver_with_redirects: LinkResolver) -> None:
    """Test URL to wikilink conversion with redirects"""
    # Test link that redirects
    result = resolver_with_redirects.resolve_url_to_wikilink(
        "https://support.atlassian.com/statuspage/docs/transfer-account-ownership/",
        "Transfer account ownership",
        "docs/Getting started/Overview.md",
    )

    # Should resolve to the redirect target
    assert (
        result
        == "[[../Manage users/Create and manage your user accounts|Transfer account ownership]]"
    )


def test_resolve_url_to_wikilink_redirect_chain(redirect_handler: RedirectHandler) -> None:
    """Test URL to wikilink conversion with redirect chain"""
    resolver = LinkResolver("https://support.atlassian.com/jira", redirect_handler)

    # Add mapping for final page
    resolver.add_page_mapping(
        "https://support.atlassian.com/jira/docs/final-page/",
        "Final Page",
        "docs/Advanced/Final Page.md",
    )

    # Test link that goes through redirect chain
    result = resolver.resolve_url_to_wikilink(
        "https://support.atlassian.com/jira/docs/old-page/",
        "Old page link",
        "docs/Getting started/Start.md",
    )

    # Should resolve to the final destination
    assert result == "[[../Advanced/Final Page|Old page link]]"


def test_resolve_url_to_wikilink_no_redirect_handler() -> None:
    """Test that LinkResolver works without redirect handler"""
    resolver = LinkResolver("https://support.atlassian.com/jira")

    resolver.add_page_mapping(
        "https://support.atlassian.com/jira/docs/page/", "Page", "docs/Page.md"
    )

    # Should work normally without redirect handler
    result = resolver.resolve_url_to_wikilink(
        "https://support.atlassian.com/jira/docs/page/", "Link text", "docs/Other.md"
    )

    assert result == "[[Page|Link text]]"


def test_convert_markdown_links_with_redirects(resolver_with_redirects: LinkResolver) -> None:
    """Test converting markdown links with redirects"""
    markdown = """
# Test Page

Here is a [link to old page](https://support.atlassian.com/statuspage/docs/transfer-account-ownership/).

And [another link](https://external.com/page).
"""

    result = resolver_with_redirects.convert_markdown_links(
        markdown,
        "https://support.atlassian.com/statuspage/docs/current-page/",
        "docs/Getting started/Current Page.md",
    )

    expected = """
# Test Page

Here is a [[../Manage users/Create and manage your user accounts|link to old page]].

And [another link](https://external.com/page).
"""

    assert result == expected
