#!/usr/bin/env python3
"""
Fix YAML frontmatter in existing markdown files by removing empty lines after list keys.

This script processes all .md files in a directory and fixes the formatting issue where
YAML lists have an extra newline after the key (e.g., "tags:\n\n- item" becomes "tags:\n- item").
"""

import sys
from pathlib import Path

# Add parent directory to path to import atlas_markdown modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from atlas_markdown.utils.yaml_formatter import fix_yaml_list_formatting


def fix_yaml_frontmatter(content: str) -> tuple[str, bool]:
    """
    Fix YAML frontmatter by removing empty lines after list keys.

    Args:
        content: The markdown file content

    Returns:
        Tuple of (fixed content, whether changes were made)
    """
    # Check if the file has frontmatter
    if not content.startswith("---\n"):
        return content, False

    # Find the end of frontmatter
    try:
        end_index = content.index("\n---\n", 4) + 5  # 4 skips opening ---, 5 includes closing ---\n
    except ValueError:
        # No closing frontmatter delimiter found
        return content, False

    # Extract frontmatter and rest of content
    frontmatter = content[:end_index]
    rest_of_content = content[end_index:]

    # Fix the YAML formatting issue using shared utility
    fixed_frontmatter = fix_yaml_list_formatting(frontmatter)

    # Check if changes were made
    if fixed_frontmatter != frontmatter:
        return fixed_frontmatter + rest_of_content, True

    return content, False


def process_directory(directory: Path, dry_run: bool = False) -> None:
    """
    Process all markdown files in a directory recursively.

    Args:
        directory: Path to the directory to process
        dry_run: If True, only show what would be changed without making changes
    """
    md_files: list[Path] = list(directory.rglob("*.md"))

    if not md_files:
        print(f"No markdown files found in {directory}")
        return

    print(f"Found {len(md_files)} markdown files in {directory}")

    fixed_count = 0
    error_count = 0

    for md_file in md_files:
        try:
            # Read the file
            content = md_file.read_text(encoding="utf-8")

            # Fix the content
            fixed_content, was_changed = fix_yaml_frontmatter(content)

            if was_changed:
                fixed_count += 1
                relative_path = md_file.relative_to(directory)

                if dry_run:
                    print(f"Would fix: {relative_path}")
                else:
                    # Write the fixed content back
                    md_file.write_text(fixed_content, encoding="utf-8")
                    print(f"Fixed: {relative_path}")

        except Exception as e:
            error_count += 1
            print(f"Error processing {md_file}: {e}", file=sys.stderr)

    # Summary
    print("\nSummary:")
    print(f"  Total files: {len(md_files)}")
    print(f"  Files {'that would be' if dry_run else ''} fixed: {fixed_count}")
    print(f"  Files unchanged: {len(md_files) - fixed_count - error_count}")

    if error_count > 0:
        print(f"  Errors: {error_count}")


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fix YAML frontmatter formatting in markdown files"
    )
    parser.add_argument("directory", type=Path, help="Directory containing markdown files to fix")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be changed without making changes"
    )

    args = parser.parse_args()

    # Validate directory
    if not args.directory.exists():
        print(f"Error: Directory '{args.directory}' does not exist", file=sys.stderr)
        sys.exit(1)

    if not args.directory.is_dir():
        print(f"Error: '{args.directory}' is not a directory", file=sys.stderr)
        sys.exit(1)

    # Process the directory
    process_directory(args.directory, args.dry_run)


if __name__ == "__main__":
    main()
