# HTTP Redirect Handling in Link Resolution - Developer Guide

## Overview

Atlas Markdown implements comprehensive HTTP redirect handling to ensure that all internal links point to the correct, final destination URLs. This prevents broken wikilinks when Atlassian documentation pages are moved or renamed.

## Problem Solved

When Atlassian documentation pages are moved, they leave redirects at the original URLs. Without proper redirect handling, links to these old URLs would create broken wikilinks in the generated markdown files.

### Example:
```markdown
# Without redirect handling
Link: https://support.atlassian.com/statuspage/docs/transfer-account-ownership/
Redirects to: https://support.atlassian.com/statuspage/docs/create-and-manage-your-user-accounts/
Result: [[transfer-account-ownership|Transfer account ownership]]  # Broken link

# With redirect handling
Result: [[../Create and manage your user accounts|Transfer account ownership]]  # Correctly resolved
```

## Architecture

### Components

1. **RedirectHandler** (`atlas_markdown/utils/redirect_handler.py`)
   - Tracks all HTTP redirects encountered during page fetching
   - Stores mappings from original URLs to their final destinations
   - Provides thread-safe access to redirect data

2. **LinkResolver** (`atlas_markdown/parsers/link_resolver.py`)
   - Accepts an optional RedirectHandler instance
   - Follows redirect chains when resolving URLs to wikilinks
   - Includes URL verification via HTTP HEAD requests as a fallback

3. **DocumentationScraper** (`atlas_markdown/cli.py`)
   - Creates and manages the RedirectHandler instance
   - Passes it to both the crawler and link resolver
   - Ensures redirect data persists across all phases

### Data Flow

1. **During Page Fetching**:
   ```python
   # In crawler.py
   if response.status in (301, 302, 303, 307, 308):
       redirect_handler.add_redirect(original_url, final_url)
   ```

2. **During Link Resolution**:
   ```python
   # In link_resolver.py
   if self.redirect_handler:
       final_url = self._follow_redirects(clean_url)
   ```

## Implementation Details

### Following Redirect Chains

The `_follow_redirects` method handles complex redirect scenarios:

```python
def _follow_redirects(self, url: str) -> str:
    """Follow redirect chain to final URL, handling URL variations."""
    current_url = url
    seen = set()

    while True:
        if current_url in seen:
            logger.warning(f"Redirect loop detected for {url}")
            break
        seen.add(current_url)

        # Check multiple URL variations
        if current_url in self.redirect_handler.redirects:
            current_url = self.redirect_handler.redirects[current_url]
        elif current_url.rstrip("/") in self.redirect_handler.redirects:
            current_url = self.redirect_handler.redirects[current_url.rstrip("/")]
        # ... more variations ...
        else:
            break

    return current_url
```

### URL Verification Fallback

For links that weren't crawled but need resolution, LinkResolver includes HTTP verification:

```python
def verify_url(self, url: str) -> str | None:
    """Verify if a URL exists and follow any redirects."""
    if url in self._url_verification_cache:
        return self._url_verification_cache[url]

    try:
        response = httpx.head(url, follow_redirects=True, timeout=5.0)
        if response.status_code == 200:
            final_url = str(response.url).rstrip("/")
            self._url_verification_cache[url] = final_url
            return final_url
    except Exception as e:
        logger.debug(f"Failed to verify URL {url}: {e}")

    return None
```

### Integration in Link Resolution

The `resolve_url_to_wikilink` method integrates redirect handling:

```python
def resolve_url_to_wikilink(self, url: str, link_text: str, current_page_path: str | None = None) -> str:
    clean_url = self._normalize_url(url)

    # Follow any redirects first
    if self.redirect_handler:
        final_url = self._follow_redirects(clean_url)
        if final_url != clean_url:
            logger.debug(f"Following redirect: {clean_url} -> {final_url}")
            clean_url = final_url

    # Now resolve with the final URL
    if clean_url in self.url_to_filepath_map:
        # ... standard resolution logic ...
```

## Testing

Comprehensive tests are in `tests/test_link_resolver_redirects.py`:

### Basic Redirect Test
```python
def test_follows_single_redirect():
    redirect_handler = RedirectHandler()
    redirect_handler.add_redirect(
        "https://example.com/old-page",
        "https://example.com/new-page"
    )

    resolver = LinkResolver("https://example.com", redirect_handler)
    resolver.add_page_mapping(
        "https://example.com/new-page",
        "New Page",
        "docs/New Page.md"
    )

    result = resolver.resolve_url_to_wikilink(
        "https://example.com/old-page",
        "Link text",
        "docs/Current.md"
    )

    assert result == "[[New Page|Link text]]"
```

### Redirect Chain Test
```python
def test_follows_redirect_chain():
    # Tests A -> B -> C -> D redirect chain
```

### Loop Detection Test
```python
def test_handles_redirect_loops():
    # Tests A -> B -> A loop detection
```

## Usage in Atlas Markdown

The redirect handling is automatic and transparent:

1. **Initialization** (cli.py:350-351):
   ```python
   self.redirect_handler = RedirectHandler()
   self.link_resolver = LinkResolver(self.base_url, self.redirect_handler)
   ```

2. **During Crawling** (cli.py:827-848):
   - Redirects are tracked as pages are fetched
   - Both original and final URLs are added to mappings

3. **During Link Resolution** (Phase 6):
   - All links automatically follow redirects
   - Broken links attempt URL verification

## Performance Considerations

1. **Redirect Lookups**: O(1) dictionary lookups, negligible overhead
2. **URL Verification**:
   - Only triggered for unresolved links
   - Results are cached to avoid repeated requests
   - 5-second timeout prevents hanging
3. **Memory Usage**: Redirect mappings are minimal (URL strings only)

## Edge Cases Handled

1. **Trailing Slashes**: URLs with/without trailing slashes are normalized
2. **Redirect Loops**: Detected and logged, prevents infinite loops
3. **Multiple Variations**: Checks several URL formats when following redirects
4. **Missing Redirects**: Falls back to original URL if redirect not found
5. **HTTP Errors**: Gracefully handles failed verification attempts

## Debugging

Enable debug logging to see redirect resolution:

```bash
ATLAS_MD_LOG_LEVEL=DEBUG atlas-markdown
```

Look for messages like:
- `"Following redirect: {old_url} -> {new_url}"`
- `"Redirect loop detected for {url}"`
- `"Attempting to verify URL: {url}"`

## Future Enhancements

1. **Async URL Verification**: Could improve performance for many unresolved links
2. **Redirect Persistence**: Store redirects in state database for resume capability
3. **Folder Structure Handling**: Special handling for index pages that become folders
4. **Redirect Statistics**: Report on number of redirects resolved
