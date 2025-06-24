"""
Tests for markdown linter
"""

import tempfile
from pathlib import Path

import pytest

from atlas_markdown.utils.markdown_linter import MarkdownLinter


@pytest.fixture
def linter() -> MarkdownLinter:
    """Create a markdown linter for testing"""
    return MarkdownLinter(auto_fix=True)


def test_fix_malformed_wikilinks(linter: MarkdownLinter) -> None:
    """Test fixing malformed wikilinks with trailing slashes and quotes"""
    content = """# Test Page

Here are some malformed wikilinks:

1. [[change-project-customer-permissions/"|Learn more about changing project customer permissions.]]
2. [[manage-users/"|Manage users in your project]]
3. [[test-page/ "some title"|This is a test]]
4. [[normal-link|This should not change]]
5. [[another/"|Another malformed link]]
"""

    expected = """# Test Page

Here are some malformed wikilinks:

1. [[change-project-customer-permissions|Learn more about changing project customer permissions.]]
2. [[manage-users|Manage users in your project]]
3. [[test-page|This is a test]]
4. [[normal-link|This should not change]]
5. [[another|Another malformed link]]
"""

    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)

    try:
        # Lint the file
        fixed_content, issues = linter.lint_file(temp_path)

        # Check that the content was fixed
        assert fixed_content.strip() == expected.strip()

        # Check that issues were reported
        assert len(issues) >= 4  # At least 4 malformed wikilinks should be fixed
        malformed_issues = [issue for issue in issues if issue.issue_type == "malformed_wikilink"]
        assert len(malformed_issues) == 4

        # Check specific fixes
        assert any(
            'change-project-customer-permissions/"' in issue.original for issue in malformed_issues
        )
        assert any('manage-users/"' in issue.original for issue in malformed_issues)
        assert any("test-page/" in issue.original for issue in malformed_issues)
        assert any('another/"' in issue.original for issue in malformed_issues)

    finally:
        # Clean up
        temp_path.unlink()


def test_preserve_valid_wikilinks(linter: MarkdownLinter) -> None:
    """Test that valid wikilinks are not modified"""
    content = """# Test Page

Valid wikilinks that should not change:

1. [[normal-page|Normal link text]]
2. [[another-page|Another link]]
3. [[resources/some-resource|Resource link]]
"""

    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)

    try:
        # Lint the file
        fixed_content, issues = linter.lint_file(temp_path)

        # Check that valid wikilinks were preserved
        assert "[[normal-page|Normal link text]]" in fixed_content
        assert "[[another-page|Another link]]" in fixed_content
        assert "[[resources/some-resource|Resource link]]" in fixed_content

        # Check that no malformed wikilink issues were reported
        malformed_issues = [issue for issue in issues if issue.issue_type == "malformed_wikilink"]
        assert len(malformed_issues) == 0

    finally:
        # Clean up
        temp_path.unlink()
