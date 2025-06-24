# HTTP Redirect Handling in Link Resolution - Fix Proposal

## Problem Statement

The current implementation tracks HTTP redirects but doesn't use this information during link resolution. When a page links to a URL that redirects, the wikilink remains pointed at the original (stale) URL instead of following the redirect to the actual destination.

### Example:
```markdown
# Current behavior
Link: https://support.atlassian.com/statuspage/docs/transfer-account-ownership/
Redirects to: https://support.atlassian.com/statuspage/docs/create-and-manage-your-user-accounts/
Result: [[transfer-account-ownership|Transfer account ownership]]  # Broken link

# Expected behavior
Result: [[../Create and manage your user accounts|Transfer account ownership]]  # Points to redirect target
```

## Current State Analysis

### What Works:
1. `RedirectHandler` tracks redirects during scraping
2. `LinkResolver` receives mappings for both original and final URLs
3. Redirect information is available but not utilized during link resolution

### What's Missing:
1. LinkResolver doesn't have access to RedirectHandler data
2. No redirect lookup during URL resolution
3. Redirect chains aren't followed during link transformation

## Proposed Solution

### 1. Pass RedirectHandler to LinkResolver

Update LinkResolver initialization to accept redirect handler:

```python
class LinkResolver:
    def __init__(self, base_url: str, redirect_handler: RedirectHandler | None = None):
        self.base_url = base_url.rstrip("/")
        self.redirect_handler = redirect_handler
        # ... existing initialization
```

### 2. Update URL Resolution Logic

Modify `resolve_url_to_wikilink` to check redirects:

```python
def resolve_url_to_wikilink(self, url: str, link_text: str, current_page_path: str | None = None) -> str:
    # Clean the URL
    clean_url = url.rstrip("/")

    # Follow redirects if redirect handler is available
    if self.redirect_handler:
        final_url = self._follow_redirects(clean_url)
        if final_url != clean_url:
            logger.debug(f"Following redirect: {clean_url} -> {final_url}")
            clean_url = final_url

    # ... rest of existing logic

def _follow_redirects(self, url: str) -> str:
    """Follow redirect chain to final URL"""
    current_url = url
    seen = set()

    while current_url in self.redirect_handler.redirects:
        if current_url in seen:
            logger.warning(f"Redirect loop detected for {url}")
            break
        seen.add(current_url)
        current_url = self.redirect_handler.redirects[current_url]

    return current_url
```

### 3. Update CLI Integration

Modify DocumentationScraper to pass redirect handler:

```python
# In cli.py __init__
self.redirect_handler = RedirectHandler()
self.link_resolver = LinkResolver(self.base_url, self.redirect_handler)
```

### 4. Handle Edge Cases

#### Redirect to Folder Structure
When a redirect points to an index page that becomes a folder:

```python
def resolve_url_to_wikilink(self, url: str, link_text: str, current_page_path: str | None = None) -> str:
    # ... follow redirects ...

    # Check if we have a mapping for this URL
    if clean_url in self.url_to_filepath_map:
        # ... existing logic ...
    elif self._is_index_page_url(clean_url):
        # Handle index pages that become folders
        folder_name = self._url_to_folder_name(clean_url)
        if current_page_path:
            relative_link = self._calculate_relative_path_to_folder(current_page_path, folder_name)
            return f"[[{relative_link}|{link_text}]]"
```

## Implementation Steps

1. **Update RedirectHandler** (`redirect_handler.py`):
   - Ensure redirect mappings are accessible
   - Add method to follow redirect chains

2. **Update LinkResolver** (`link_resolver.py`):
   - Accept RedirectHandler in constructor
   - Add redirect resolution logic
   - Handle folder structure edge cases

3. **Update CLI** (`cli.py`):
   - Pass RedirectHandler to LinkResolver
   - Ensure redirect data is available during link resolution phase

4. **Add Tests**:
   - Test redirect following in link resolution
   - Test redirect loops
   - Test redirects to folder structures

## Benefits

1. **Accurate Links**: Links always point to the current, active URL
2. **No Broken Links**: Redirected URLs are automatically updated
3. **Better User Experience**: Users don't encounter stale links
4. **Future-Proof**: As documentation URLs change, links remain valid

## Example Test Case

```python
def test_link_resolution_with_redirects():
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

    # Test that old URL resolves to new page
    result = resolver.resolve_url_to_wikilink(
        "https://example.com/old-page",
        "Link text",
        "docs/Current Page.md"
    )

    assert result == "[[New Page|Link text]]"
```

## Considerations

1. **Performance**: Redirect lookups add overhead, but should be negligible
2. **Memory**: RedirectHandler data needs to persist through link resolution phase
3. **Complexity**: Adds another layer of indirection to link resolution
4. **Combined with Folder Notes**: This fix works independently but complements the folder notes proposal
