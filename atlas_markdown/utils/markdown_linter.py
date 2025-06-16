"""
Markdown linter and auto-fixer for scraped documentation.
Fixes common formatting issues in markdown files.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class LintIssue:
    """Represents a linting issue found in a markdown file."""

    line_number: int
    issue_type: str
    description: str
    original: str
    fixed: str = None


class MarkdownLinter:
    """Lints and auto-fixes markdown files."""

    def __init__(self, auto_fix: bool = True):
        self.auto_fix = auto_fix
        self.issues: list[LintIssue] = []

    def lint_file(self, file_path: Path) -> tuple[str, list[LintIssue]]:
        """
        Lint a markdown file and optionally fix issues.

        Args:
            file_path: Path to the markdown file

        Returns:
            Tuple of (processed content, list of issues found)
        """
        logger.info(f"Linting file: {file_path}")
        self.issues = []

        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        # Apply fixes in order
        content = self._fix_content_before_h1(content)
        content = self._fix_multiline_wiki_links(content)
        content = self._fix_wiki_links(content)
        content = self._fix_broken_tables(content)
        content = self._fix_heading_spacing(content)
        content = self._fix_trailing_whitespace(content)
        content = self._fix_multiple_blank_lines(content)
        content = self._fix_inline_html(content)
        content = self._fix_callout_formatting(content)
        content = self._fix_list_indentation(content)
        content = self._fix_list_empty_lines(content)
        content = self._fix_numbered_list_sequence(content)
        content = self._ensure_final_newline(content)

        return content, self.issues

    def _fix_content_before_h1(self, content: str) -> str:
        """Remove content before the first H1 if there's content before it."""
        lines = content.split("\n")

        # Find the first H1
        first_h1_index = -1
        has_content_before_h1 = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Check if this is an H1
            if re.match(r"^#\s+", line):
                first_h1_index = i
                break

            # Check if there's meaningful content before we find an H1
            if stripped and not stripped.startswith("---"):  # Ignore frontmatter
                # Also ignore certain metadata patterns
                if not re.match(r"^\[\[.*\]\]$", stripped):  # Not just a wiki link
                    has_content_before_h1 = True

        # If we found an H1 and there was content before it, remove that content
        if first_h1_index > 0 and has_content_before_h1:
            # Preserve frontmatter if it exists
            frontmatter_end = -1
            if lines[0].strip() == "---":
                for i in range(1, len(lines)):
                    if lines[i].strip() == "---":
                        frontmatter_end = i
                        break

            if frontmatter_end >= 0:
                # Keep frontmatter and start from H1
                new_lines = lines[: frontmatter_end + 1] + [""] + lines[first_h1_index:]
            else:
                # Just start from H1
                new_lines = lines[first_h1_index:]

            self.issues.append(
                LintIssue(
                    line_number=1,
                    issue_type="content_before_h1",
                    description=f"Removed {first_h1_index} lines of content before first H1",
                    original=f"{first_h1_index} lines before H1",
                    fixed="Content starts with H1",
                )
            )

            return "\n".join(new_lines)

        return content

    def _fix_multiline_wiki_links(self, content: str) -> str:
        """Fix wiki links that span multiple lines."""
        # Pattern to match wiki links that may span multiple lines
        # This will match [[target|description that spans
        # multiple lines]]
        pattern = r"\[\[([^\]|]+)\|([^\]]+)\]\]"

        def fix_multiline_link(match):
            target = match.group(1).strip()
            description = match.group(2).strip()

            # Remove extra whitespace and newlines from description
            # Keep only the first line if it contains "View topic" or similar
            lines = description.split("\n")
            clean_lines = []

            for line in lines:
                line = line.strip()
                if line and line not in ["View topic", "View Topic"]:
                    clean_lines.append(line)

            # Join the cleaned lines with a space
            clean_description = " ".join(clean_lines)

            # If description is empty after cleaning, use the target
            if not clean_description:
                clean_description = target

            return f"[[{target}|{clean_description}]]"

        # First, handle wiki links that span multiple lines
        fixed_content = re.sub(pattern, fix_multiline_link, content, flags=re.DOTALL | re.MULTILINE)

        # Count how many were fixed
        original_matches = list(re.finditer(pattern, content, flags=re.DOTALL | re.MULTILINE))
        fixed_matches = list(re.finditer(pattern, fixed_content, flags=re.DOTALL | re.MULTILINE))

        if len(original_matches) > 0:
            for i, match in enumerate(original_matches):
                if match.group(0) != fixed_matches[i].group(0) if i < len(fixed_matches) else True:
                    self.issues.append(
                        LintIssue(
                            line_number=content[: match.start()].count("\n") + 1,
                            issue_type="multiline_wiki_link",
                            description="Fixed wiki link spanning multiple lines",
                            original=(
                                match.group(0)[:50] + "..."
                                if len(match.group(0)) > 50
                                else match.group(0)
                            ),
                            fixed=fixed_matches[i].group(0) if i < len(fixed_matches) else "Fixed",
                        )
                    )

        return fixed_content

    def _fix_wiki_links(self, content: str) -> str:
        """Fix links: Keep wiki-style for internal links, convert only external links to markdown."""
        lines = content.split("\n")
        fixed_lines = []

        for i, line in enumerate(lines):
            fixed_line = line

            # Find all links in the line
            # Pattern for markdown links [text](url)
            markdown_link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"
            matches = list(re.finditer(markdown_link_pattern, line))

            for match in matches:
                link_text = match.group(1)
                link_url = match.group(2)

                # Check if this is an internal link (relative path or local file)
                if (
                    link_url.startswith("./")
                    or link_url.startswith("../")
                    or link_url.endswith(".md")
                    or not (link_url.startswith("http://") or link_url.startswith("https://"))
                ):
                    # Convert markdown link to wiki link for internal links
                    # Extract just the filename without path and extension for wiki link
                    if link_url.endswith(".md"):
                        # Remove .md extension and any path components
                        wiki_target = link_url.replace(".md", "")
                        if "/" in wiki_target:
                            wiki_target = wiki_target.split("/")[-1]

                        # Handle special case for index
                        if wiki_target.lower() == "index":
                            wiki_link = f"[[index|{link_text}]]"
                        else:
                            wiki_link = f"[[{wiki_target}|{link_text}]]"
                    else:
                        # For other internal links, use the URL as-is
                        wiki_link = f"[[{link_url}|{link_text}]]"

                    fixed_line = fixed_line.replace(match.group(0), wiki_link)

                    self.issues.append(
                        LintIssue(
                            line_number=i + 1,
                            issue_type="internal_link_format",
                            description="Converted internal markdown link to wiki-style",
                            original=match.group(0),
                            fixed=wiki_link,
                        )
                    )

            fixed_lines.append(fixed_line)

        return "\n".join(fixed_lines)

    def _fix_broken_tables(self, content: str) -> str:
        """Fix tables with missing headers or improper formatting."""
        lines = content.split("\n")
        fixed_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Detect table rows without headers
            if re.match(r"^\s*\|.*\|.*\|\s*$", line):
                # Check if this is the start of a table without headers
                if i == 0 or not re.match(r"^\s*\|.*\|.*\|\s*$", lines[i - 1]):
                    # Check if next line is separator
                    if i + 1 < len(lines) and re.match(r"^\s*\|[\s\-:]+\|\s*$", lines[i + 1]):
                        # This looks like a headerless table
                        # Count columns
                        cols = len(line.split("|")) - 2  # Subtract empty strings from split

                        # Insert empty header
                        fixed_lines.append("|" + " |" * cols)
                        fixed_lines.append("|" + " --- |" * cols)

                        self.issues.append(
                            LintIssue(
                                line_number=i + 1,
                                issue_type="table_missing_header",
                                description="Added missing table header",
                                original=line,
                                fixed="Added header row",
                            )
                        )

            fixed_lines.append(line)
            i += 1

        return "\n".join(fixed_lines)

    def _fix_heading_spacing(self, content: str) -> str:
        """Ensure proper spacing around headings."""
        lines = content.split("\n")
        fixed_lines = []

        for i, line in enumerate(lines):
            # Add blank line before headings (except first line)
            if re.match(r"^#{1,6}\s+", line) and i > 0:
                if i > 0 and lines[i - 1].strip() != "":
                    fixed_lines.append("")
                    self.issues.append(
                        LintIssue(
                            line_number=i + 1,
                            issue_type="heading_spacing",
                            description="Added blank line before heading",
                            original="",
                            fixed="[blank line]",
                        )
                    )

            fixed_lines.append(line)

            # Add blank line after headings
            if re.match(r"^#{1,6}\s+", line):
                if i + 1 < len(lines) and lines[i + 1].strip() != "":
                    fixed_lines.append("")
                    self.issues.append(
                        LintIssue(
                            line_number=i + 1,
                            issue_type="heading_spacing",
                            description="Added blank line after heading",
                            original="",
                            fixed="[blank line]",
                        )
                    )

        return "\n".join(fixed_lines)

    def _fix_trailing_whitespace(self, content: str) -> str:
        """Remove trailing whitespace from lines."""
        lines = content.split("\n")
        fixed_lines = []

        for i, line in enumerate(lines):
            if line != line.rstrip():
                self.issues.append(
                    LintIssue(
                        line_number=i + 1,
                        issue_type="trailing_whitespace",
                        description="Removed trailing whitespace",
                        original=repr(line),
                        fixed=repr(line.rstrip()),
                    )
                )
                fixed_lines.append(line.rstrip())
            else:
                fixed_lines.append(line)

        return "\n".join(fixed_lines)

    def _fix_multiple_blank_lines(self, content: str) -> str:
        """Replace multiple consecutive blank lines with a single blank line."""
        # Replace 3 or more newlines with 2 newlines
        fixed_content = re.sub(r"\n{3,}", "\n\n", content)

        if fixed_content != content:
            self.issues.append(
                LintIssue(
                    line_number=0,
                    issue_type="multiple_blank_lines",
                    description="Reduced multiple blank lines",
                    original="Multiple blank lines",
                    fixed="Single blank line",
                )
            )

        return fixed_content

    def _fix_inline_html(self, content: str) -> str:
        """Convert common inline HTML to markdown."""
        replacements = [
            (r"<br\s*/?>", "  \n"),  # Line breaks
            (r"<strong>(.*?)</strong>", r"**\1**"),  # Bold
            (r"<b>(.*?)</b>", r"**\1**"),  # Bold
            (r"<em>(.*?)</em>", r"*\1*"),  # Italic
            (r"<i>(.*?)</i>", r"*\1*"),  # Italic
            (r"<code>(.*?)</code>", r"`\1`"),  # Inline code
        ]

        fixed_content = content
        for pattern, replacement in replacements:
            if re.search(pattern, fixed_content):
                fixed_content = re.sub(pattern, replacement, fixed_content)
                self.issues.append(
                    LintIssue(
                        line_number=0,
                        issue_type="inline_html",
                        description=f"Converted HTML {pattern} to markdown",
                        original=pattern,
                        fixed=replacement,
                    )
                )

        return fixed_content

    def _fix_callout_formatting(self, content: str) -> str:
        """Fix callout formatting to ensure no empty lines between content."""
        lines = content.split("\n")
        fixed_lines = []
        in_callout = False
        callout_fixed = False

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Check if we're starting a callout
            if stripped.startswith(">") and not in_callout:
                in_callout = True
                callout_fixed = False

            # If we're in a callout
            if in_callout:
                # If this is an empty line
                if not stripped:
                    # Look ahead to see if the next line continues the callout
                    if i + 1 < len(lines) and lines[i + 1].strip().startswith(">"):
                        # This is an empty line within a callout - fix it
                        fixed_lines.append(">")
                        if not callout_fixed:
                            self.issues.append(
                                LintIssue(
                                    line_number=i + 1,
                                    issue_type="callout_empty_line",
                                    description="Fixed empty line in callout",
                                    original="[empty line]",
                                    fixed=">",
                                )
                            )
                            callout_fixed = True
                    else:
                        # End of callout
                        in_callout = False
                        fixed_lines.append(line)
                else:
                    # Regular callout line
                    fixed_lines.append(line)
                    # Check if this line doesn't start with > (broken callout)
                    if not stripped.startswith(">"):
                        in_callout = False
            else:
                # Not in a callout
                fixed_lines.append(line)

            i += 1

        return "\n".join(fixed_lines)

    def _fix_list_indentation(self, content: str) -> str:
        """Fix list indentation to ensure lists start at column 0."""
        lines = content.split("\n")
        fixed_lines = []

        for i, line in enumerate(lines):
            # Check if this line is a list item with leading whitespace
            match = re.match(r"^(\s+)([-*+])\s+(.*)$", line)
            if match:
                match.group(1)
                marker = match.group(2)
                content_text = match.group(3)

                # Remove all leading whitespace for list items
                fixed_line = f"{marker} {content_text}"
                fixed_lines.append(fixed_line)

                self.issues.append(
                    LintIssue(
                        line_number=i + 1,
                        issue_type="list_indentation",
                        description="Removed indentation from list item",
                        original=line,
                        fixed=fixed_line,
                    )
                )
            else:
                fixed_lines.append(line)

        return "\n".join(fixed_lines)

    def _fix_list_empty_lines(self, content: str) -> str:
        """Remove empty lines between list items."""
        lines = content.split("\n")
        fixed_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Check if this is a list item (bullet or numbered)
            is_list_item = re.match(r"^([-*+]|\d+\.)\s+", line.strip())

            if is_list_item:
                # Add the list item
                fixed_lines.append(line)

                # Look ahead to check for empty lines followed by another list item
                j = i + 1
                empty_lines_count = 0

                while j < len(lines):
                    next_line = lines[j]
                    next_stripped = next_line.strip()

                    if not next_stripped:
                        # Empty line
                        empty_lines_count += 1
                        j += 1
                    elif re.match(r"^([-*+]|\d+\.)\s+", next_stripped):
                        # Found another list item after empty line(s)
                        if empty_lines_count > 0:
                            # Skip the empty lines
                            self.issues.append(
                                LintIssue(
                                    line_number=i + 2,
                                    issue_type="list_empty_lines",
                                    description=f"Removed {empty_lines_count} empty line(s) between list items",
                                    original=f"{empty_lines_count} empty line(s)",
                                    fixed="No empty lines",
                                )
                            )
                            i = j - 1  # Will be incremented at end of loop
                        break
                    else:
                        # Not a list item, keep the empty lines as they separate list from other content
                        for _k in range(empty_lines_count):
                            fixed_lines.append("")
                        break

                if j >= len(lines) and empty_lines_count > 0:
                    # Empty lines at end of list
                    for _k in range(empty_lines_count):
                        fixed_lines.append("")
            else:
                # Not a list item, keep as is
                fixed_lines.append(line)

            i += 1

        return "\n".join(fixed_lines)

    def _fix_numbered_list_sequence(self, content: str) -> str:
        """Fix numbered list sequences to be consecutive (1, 2, 3, etc.)."""
        lines = content.split("\n")
        fixed_lines = []
        current_number = 0
        in_numbered_list = False

        for i, line in enumerate(lines):
            # Check if this is a numbered list item
            match = re.match(r"^(\d+)\.\s+(.*)$", line.strip())

            if match:
                old_number = match.group(1)
                list_content = match.group(2)

                if not in_numbered_list:
                    # Starting a new numbered list
                    in_numbered_list = True
                    current_number = 1
                else:
                    # Continuing numbered list
                    current_number += 1

                # Create the fixed line with correct numbering
                fixed_line = f"{current_number}. {list_content}"

                if line.strip() != fixed_line:
                    self.issues.append(
                        LintIssue(
                            line_number=i + 1,
                            issue_type="numbered_list_sequence",
                            description=f"Fixed list numbering from {old_number} to {current_number}",
                            original=line.strip(),
                            fixed=fixed_line,
                        )
                    )
                    fixed_lines.append(fixed_line)
                else:
                    fixed_lines.append(line)
            else:
                # Not a numbered list item
                stripped = line.strip()
                # Check if we're ending the numbered list (non-empty, non-list line)
                if in_numbered_list and stripped and not stripped.startswith("   "):
                    in_numbered_list = False
                    current_number = 0
                fixed_lines.append(line)

        return "\n".join(fixed_lines)

    def _ensure_final_newline(self, content: str) -> str:
        """Ensure file ends with a newline."""
        if content and not content.endswith("\n"):
            self.issues.append(
                LintIssue(
                    line_number=len(content.split("\n")),
                    issue_type="missing_final_newline",
                    description="Added final newline",
                    original="[no newline]",
                    fixed="[newline]",
                )
            )
            return content + "\n"
        return content

    def lint_directory(
        self, directory: Path, fix_in_place: bool = False
    ) -> dict[str, list[LintIssue]]:
        """
        Lint all markdown files in a directory recursively.

        Args:
            directory: Directory to lint
            fix_in_place: Whether to write fixes back to files

        Returns:
            Dictionary mapping file paths to their issues
        """
        all_issues = {}

        for md_file in directory.rglob("*.md"):
            logger.info(f"Processing: {md_file}")

            try:
                fixed_content, issues = self.lint_file(md_file)

                if issues:
                    all_issues[str(md_file)] = issues

                    if fix_in_place and self.auto_fix:
                        with open(md_file, "w", encoding="utf-8") as f:
                            f.write(fixed_content)
                        logger.info(f"Fixed {len(issues)} issues in {md_file}")

            except Exception as e:
                logger.error(f"Error processing {md_file}: {e}")

        return all_issues

    def generate_report(self, issues: dict[str, list[LintIssue]]) -> str:
        """Generate a summary report of linting issues."""
        if not issues:
            return "No linting issues found!"

        report = ["# Markdown Linting Report\n"]

        # Summary statistics
        total_issues = sum(len(file_issues) for file_issues in issues.values())
        report.append(f"Total files with issues: {len(issues)}")
        report.append(f"Total issues found: {total_issues}\n")

        # Issues by type
        issue_counts = {}
        for file_issues in issues.values():
            for issue in file_issues:
                issue_counts[issue.issue_type] = issue_counts.get(issue.issue_type, 0) + 1

        report.append("## Issues by Type")
        for issue_type, count in sorted(issue_counts.items(), key=lambda x: x[1], reverse=True):
            report.append(f"- {issue_type}: {count}")

        report.append("\n## Files with Issues")
        for file_path, file_issues in sorted(issues.items()):
            report.append(f"\n### {file_path}")
            for issue in file_issues[:5]:  # Show first 5 issues per file
                report.append(f"- Line {issue.line_number}: {issue.description}")
            if len(file_issues) > 5:
                report.append(f"- ... and {len(file_issues) - 5} more issues")

        return "\n".join(report)
