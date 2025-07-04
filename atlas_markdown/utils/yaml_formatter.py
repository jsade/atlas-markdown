"""Utilities for formatting YAML frontmatter."""

import re


def fix_yaml_list_formatting(yaml_content: str) -> str:
    """
    Fix YAML formatting issue where lists have an extra newline after the key.

    This converts patterns like "tags:\n\n- item" to "tags:\n- item".
    Handles both regular keys and hyphenated keys (e.g., "atlas-md").

    Args:
        yaml_content: The YAML content to fix

    Returns:
        The fixed YAML content
    """
    # Pattern matches keys with word characters or hyphens, followed by colon,
    # newlines, and a dash
    return re.sub(r"([\w-]+):\s*\n\s*\n\s*-", r"\1:\n-", yaml_content)
