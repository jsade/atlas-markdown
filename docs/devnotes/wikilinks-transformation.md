# Wikilink Transformation Developer Guide

## Overview

This document describes the logic and flow of how wikilinks are transformed in the Atlas Markdown project. The system converts various link formats into Obsidian-compatible wikilinks with proper relative paths.

## Key Concepts

### Wikilink Format
- **Standard format**: `[[target|display text]]`
- **Relative path format**: `[[../Parent Directory/Page Name|display text]]`
- **External links**: Remain as standard markdown links `[text](url)`

### Link Types Handled
1. **Markdown links**: `[text](url)`
2. **Existing wikilinks**: `[[target|text]]`
3. **Malformed wikilinks**: `[[slug/"|text]]` or `[[slug/ "url"|text]]`

## Architecture Components

### 1. ContentParser (`atlas_markdown/parsers/content_parser.py`)

**Phase**: Initial HTML to Markdown conversion

**Key Methods**:
- `_convert_to_wikilinks()` - Initial conversion during HTML parsing
- `_fix_malformed_wikilinks()` - Fixes malformed patterns

**Process**:
1. Parses HTML content from Atlassian pages
2. Converts internal links to basic wikilinks using URL slugs
3. Handles links with title attributes: `<a href="url" title="title">`
4. Cleans trailing slashes and quotes from URLs

**Current Behavior**:
```python
# Input: <a href="https://support.atlassian.com/docs/some-page/">text</a>
# Output: [[some-page|text]]
```

### 2. LinkResolver (`atlas_markdown/parsers/link_resolver.py`)

**Phase**: Final link resolution (Phase 6 of pipeline)

**Key Data Structures**:
- `url_to_filename_map`: Maps URLs to page filenames
- `url_to_filepath_map`: Maps URLs to full relative paths (without .md)
- `title_to_filename_map`: Maps page titles to filenames for fallback

**Key Methods**:

#### `add_page_mapping(url, title, file_path)`
- Stores mappings for URL resolution
- Extracts both filename and full relative path
- Example:
  ```python
  url: "https://support.atlassian.com/docs/set-up-knowledge-base/"
  file_path: "docs/Knowledge Base/Set up knowledge base.md"
  # Stores:
  # - filepath: "docs/Knowledge Base/Set up knowledge base"
  # - filename: "Set up knowledge base"
  ```

**Important**: The method stores in BOTH `url_to_filepath_map` (for relative paths) and `url_to_filename_map` (for backward compatibility)

#### `_calculate_relative_path(from_path, to_path)`
- Calculates relative path between two files
- Handles same directory, subdirectories, and parent directories
- Examples:
  ```
  From: docs/Guide/page1.md
  To: docs/Guide/page2.md
  Result: page2

  From: docs/Guide/page1.md
  To: docs/Setup/page2.md
  Result: ../Setup/page2
  ```

#### `resolve_url_to_wikilink(url, link_text, current_page_path)`
- Converts a URL to a wikilink with relative path
- Falls back to filename-only if no current page path
- Keeps external links as markdown format
- **Fallback behavior**: If direct URL mapping not found, tries URL patterns (e.g., adding `/docs/` prefix)

#### `convert_markdown_links(markdown, current_page_url, current_page_path)`
- Main method called during link resolution phase
- Processes both existing wikilinks and markdown links
- Two-step process:
  1. Fix existing wikilinks that might have wrong targets
  2. Convert markdown links to wikilinks

### 3. MarkdownLinter (`atlas_markdown/utils/markdown_linter.py`)

**Phase**: Post-processing cleanup (Phase 7)

**Key Methods**:
- `_fix_malformed_wikilinks()` - Safety net for malformed patterns

**Process**:
- Detects patterns like `[[slug/"|text]]`
- Strips trailing slashes, quotes, and special characters
- Reports issues for tracking

### 4. CLI Integration (`atlas_markdown/cli.py`)

**Phase**: Orchestration

**Key Methods**:
- `fix_wiki_links()` - Phase 6 of the pipeline

**Process**:
1. Loads all page mappings into LinkResolver
2. Iterates through all completed pages
3. Passes current page's file path for relative link calculation
4. Updates files only if content changes

## Link Transformation Flow

### Phase 1: Initial Conversion (During Scraping)
```
HTML: <a href="https://support.atlassian.com/docs/manage-users/">Manage Users</a>
↓ ContentParser._convert_to_wikilinks()
Markdown: [[manage-users|Manage Users]]
```

### Phase 2: Link Resolution (Phase 6)
```
Current Page: docs/Getting Started/Introduction.md
Target URL: https://support.atlassian.com/docs/manage-users/
Target Path: docs/User Management/Manage Users.md
↓ LinkResolver.convert_markdown_links()
Result: [[../User Management/Manage Users|Manage Users]]
```

### Phase 3: Cleanup (Phase 7)
```
Malformed: [[manage-users/"|Manage Users]]
↓ MarkdownLinter._fix_malformed_wikilinks()
Fixed: [[manage-users|Manage Users]]
```

## Common Issues and Debugging

### 1. Malformed Wikilinks
**Symptom**: Links like `[[slug/"|text]]`
**Cause**: URL cleaning issues in initial conversion
**Fix**: Ensure proper URL/path cleaning in ContentParser

### 2. Missing Relative Paths
**Symptom**: Links like `[[page-name|text]]` instead of `[[../Dir/Page Name|text]]`
**Cause**: LinkResolver not receiving current page path
**Fix**: Ensure CLI passes `page["file_path"]` to `convert_markdown_links()`

### 3. Incorrect Path Calculation
**Symptom**: Wrong number of `../` in relative paths
**Cause**: Path calculation logic issues
**Debug**: Check `_calculate_relative_path()` with test cases

### 4. Unresolved Links
**Symptom**: Links remain as markdown `[text](url)`
**Cause**: URL not in LinkResolver's mappings
**Debug**: Check if page was scraped and mapping was added

### 5. Fallback URL Patterns Not Resolving
**Symptom**: Wikilinks like `[[slug|text]]` not converting to relative paths for existing pages
**Cause**: Fallback URL pattern matching using wrong mapping dictionary
**Fix**: Ensure fallback patterns check `url_to_filepath_map` not just `url_to_filename_map`
**Example**: Page at `docs/Subfolder/Page.md` not found when URL pattern matching falls through

## Testing

### Unit Tests
- `test_content_parser.py::test_wikilink_conversion_with_trailing_slash`
- `test_link_resolver_relative_paths.py` - Comprehensive relative path tests
- `test_markdown_linter.py::test_fix_malformed_wikilinks`

### Integration Test Example
```python
# 1. Add page mapping
resolver.add_page_mapping(
    "https://support.atlassian.com/docs/setup/",
    "Setup Guide",
    "docs/Getting Started/Setup Guide.md"
)

# 2. Convert links
markdown = "[Setup Guide](https://support.atlassian.com/docs/setup/)"
current_page = "docs/Advanced/Configuration.md"

result = resolver.convert_markdown_links(markdown, current_url, current_page)
# Result: [[../Getting Started/Setup Guide|Setup Guide]]
```

## Configuration

### URL Slug to Filename Conversion
The `_url_slug_to_filename()` method converts URL slugs to proper titles:
- `"manage-users"` → `"Manage Users"`
- `"set-up-your-knowledge-base"` → `"Set up Your Knowledge Base"`

Rules:
- First word always capitalized
- Common words (a, an, the, of, etc.) remain lowercase
- Other words are capitalized

## Future Improvements

1. **Performance**: Cache relative path calculations
2. **Validation**: Add link target validation
3. **Reporting**: Enhanced link resolution statistics
4. **Flexibility**: Configurable link formats for different wiki systems
