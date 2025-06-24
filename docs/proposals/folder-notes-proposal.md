# Folder Notes Implementation Proposal

## Problem Statement

When Atlassian documentation uses redirect URLs or links to category/index pages, the current scraper creates folder structures but no corresponding index file. This breaks wikilinks that point to these URLs.

### Example:
- URL: `https://support.atlassian.com/statuspage/docs/transfer-account-ownership/`
- Redirects to: `https://support.atlassian.com/statuspage/docs/create-and-manage-your-user-accounts/`
- Creates: `docs/Create and manage your user accounts/` (folder)
- Missing: `docs/Create and manage your user accounts.md` (index file)
- Result: `[[transfer-account-ownership|text]]` cannot resolve to anything

## Proposed Solution: Folder Notes

Implement Obsidian-style "folder notes" - markdown files that serve as index pages for folders.

### Implementation Strategy:

#### 1. Detection Phase
During scraping, detect when a URL represents an index/category page:
- Has child pages/links
- URL path matches a section structure
- Contains mainly navigation links

#### 2. File Creation
When creating folder structure for category pages:
```python
# Current behavior:
docs/Create and manage your user accounts/
    ├── Add team members.md
    ├── Export users for audience-specific pages.md
    └── ...

# Proposed behavior:
docs/Create and manage your user accounts/
    ├── Create and manage your user accounts.md  # Folder note
    ├── Add team members.md
    ├── Export users for audience-specific pages.md
    └── ...
```

#### 3. Folder Note Mapping
Track folder notes in the state database:
```sql
-- Add column to existing pages table
ALTER TABLE pages ADD COLUMN is_folder_note BOOLEAN DEFAULT FALSE;

-- Or create a separate mapping table
CREATE TABLE folder_notes (
    folder_path TEXT PRIMARY KEY,
    index_file_path TEXT NOT NULL,
    original_url TEXT
);
```

#### 4. Link Resolution Update
Update LinkResolver to:
1. *(Assumes HTTP Redirect Fix is already implemented)*
2. Check if target is a folder with a folder note
3. Resolve to folder notes when appropriate
4. Calculate correct relative paths to folder notes

### Example Resolution:
```python
# Input link
[[transfer-account-ownership|Transfer account ownership]]

# Resolution process:
1. Look up: transfer-account-ownership
2. Find redirect: -> create-and-manage-your-user-accounts
3. Check for folder note: Create and manage your user accounts.md
4. Calculate relative path: ../Create and manage your user accounts/Create and manage your user accounts

# Output link
[[../Create and manage your user accounts/Create and manage your user accounts|Transfer account ownership]]
```

## Benefits

1. **Preserves Navigation**: Links to category pages work correctly
2. **Obsidian Compatible**: Follows established folder note patterns
3. **Better Organization**: Clear hierarchy with navigable index pages
4. **Handles Redirects**: Gracefully manages URL redirects

## Implementation Steps

1. **Update Scraper** (`cli.py`):
   - Detect index/category pages
   - Create folder notes during scraping
   - Track redirects in state database

2. **Update FileManager** (`file_manager.py`):
   - Support creating folder notes
   - Handle special case of folder note naming

3. **Update LinkResolver** (`link_resolver.py`):
   - Add redirect resolution
   - Support folder note paths
   - Update relative path calculation

4. **Database Schema**:
   - Add redirects table
   - Update page mappings to include folder notes

## Alternative Approach

If full folder notes are too complex, a simpler approach:
- When a link cannot be resolved, check if a folder exists with that name
- If yes, create a link to the first file in that folder
- Or create a special "unresolved link" page that lists all pages in the target folder
