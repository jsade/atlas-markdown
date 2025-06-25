# Auto-Tagging Feature Proposal

## Executive Summary

Add automatic tag generation to the frontmatter of each markdown page during the Atlas Markdown fetch process. Tags will be derived from the page's hierarchical position, content analysis, and Atlassian product context to improve organization and searchability in tools like Obsidian.

## Problem Statement

Currently, Atlas Markdown generates markdown files with basic frontmatter containing only:
- `url`: Original page URL
- `scrape_date`: When the page was fetched
- `title`, `description`, `id`, `slug`, `childList`: When available from React state

This minimal metadata makes it difficult to:
1. Navigate and filter large documentation sets by topic
2. Understand page context without examining the full hierarchy
3. Build automated workflows based on page categories
4. Create smart searches across related topics

## Proposed Solution

Enhance the frontmatter with intelligent auto-tagging that provides:

### 1. Standard Tags Array (Enabled by Default)
```yaml
tags:
  - statuspage                    # Product name
  - administration               # Category from breadcrumbs
  - user-management             # Section from navigation
  - permissions                 # Topic from content analysis
```

### 2. Atlas Markdown Metadata (Always Included)
```yaml
atlas_md_version: 0.3.1
atlas_md_url: https://github.com/jsade/atlas-markdown
atlas_md_product: statuspage
atlas_md_category: Administration
atlas_md_section: User Management
```

**Note**: The `atlas_md_*` properties are always included in the frontmatter regardless of whether tags are enabled or disabled. Only the `tags` array is controlled by the configuration.

## Implementation Approaches

### Primary Approach: Hierarchical Path-Based Tagging

**Rationale**: Most feasible because it leverages existing data structures without external dependencies.

#### Data Sources:
1. **Product Name**: Extract from `base_url` (e.g., `/jira-service-management-cloud/` → `jira-service-management-cloud`)
2. **Breadcrumb Hierarchy**: Already extracted in `sibling_info["breadcrumb_data"]`
3. **Section Heading**: Available in `sibling_info["section_heading"]`
4. **Parent-Child Relationships**: From navigation structure

#### Tag Generation Algorithm:
```python
def _generate_hierarchical_tags(self, sibling_info: dict[str, Any], product: str) -> list[str]:
    tags = [product]  # Always include product as first tag

    # Add breadcrumb hierarchy (skip "Atlassian Support" and product name)
    if breadcrumb_data := sibling_info.get("breadcrumb_data"):
        breadcrumbs = breadcrumb_data.get("breadcrumbs", [])[2:]  # Skip first two
        for crumb in breadcrumbs[:-1]:  # Exclude current page
            if tag := self._normalize_tag(crumb.get("name")):
                tags.append(tag)

    # Add section if different from last breadcrumb
    if section := sibling_info.get("section_heading"):
        normalized = self._normalize_tag(section)
        if normalized and normalized not in tags:
            tags.append(normalized)

    return tags

def _normalize_tag(self, text: str) -> str:
    """Convert text to lowercase hyphenated tag format"""
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
```

### Secondary Enhancements (Future Phases)

#### 1. Content-Based Tags
- Analyze H1-H6 headings for key topics
- Extract frequently mentioned concepts
- Identify page type: how-to, reference, troubleshooting, api-docs

#### 2. Link Analysis Tags
- Pages with many inbound links: tag as `hub` or `overview`
- Pages with many children: tag as `category`
- Leaf pages: tag as `detail` or `guide`

## Implementation Details

### 1. Update ContentParser (`content_parser.py`)

Add new methods:
```python
def _extract_product_from_url(self, url: str) -> str:
    """Extract product identifier from base URL"""
    # Implementation details...

def _generate_hierarchical_tags(self, sibling_info: dict[str, Any], product: str) -> list[str]:
    """Generate tags from navigation hierarchy"""
    # Implementation details...

def _get_atlas_md_version(self) -> str:
    """Get current Atlas Markdown version"""
    from atlas_markdown import __version__
    return __version__
```

Update `convert_to_markdown()` method to include new frontmatter fields.

### 2. Tag Normalization Rules

- Convert to lowercase
- Replace spaces and special characters with hyphens
- Remove duplicate hyphens
- Strip leading/trailing hyphens
- Skip common words: "and", "the", "of", etc.
- Maximum tag length: 50 characters

### 3. Example Output

For page: `https://support.atlassian.com/jira-service-management-cloud/docs/set-up-request-types/`

```yaml
---
url: https://support.atlassian.com/jira-service-management-cloud/docs/set-up-request-types/
scrape_date: 2025-01-25T10:30:00
title: Set up request types
description: Learn how to create and configure request types in Jira Service Management
tags:
  - jira-service-management-cloud
  - service-project-configuration
  - request-management
atlas_md_version: 0.3.1
atlas_md_url: https://github.com/jsade/atlas-markdown
atlas_md_product: jira-service-management-cloud
atlas_md_category: Service project configuration
atlas_md_section: Request management
---
```

## Benefits

1. **Enhanced Navigation**: Filter and search by tags in Obsidian
2. **Context Awareness**: Understand page purpose without opening
3. **Automated Organization**: Build tag-based views and workflows
4. **Version Tracking**: Know which Atlas Markdown version created the file
5. **Product Identification**: Easily separate mixed-product vaults

## Migration Considerations

For existing fetched documentation:
1. Add a `--retag` command option to update only frontmatter
2. Preserve existing frontmatter fields
3. Log changes for user review

## Testing Strategy

1. **Unit Tests**: Tag generation with various breadcrumb structures
2. **Integration Tests**: Full scraping with tag validation
3. **Edge Cases**:
   - Pages with no breadcrumbs
   - Redirect pages
   - Resource pages vs docs pages
   - Special characters in titles

## Future Enhancements

1. **Custom Tag Templates**: User-defined tag generation rules
2. **Tag Synonyms**: Map similar concepts to consistent tags
3. **ML-Based Tagging**: Use NLP for content analysis
4. **Tag Hierarchy**: Parent-child tag relationships
5. **Tag Statistics**: Report on tag distribution

## Configuration Options

Add environment variables:
```bash
ATLAS_MD_DISABLE_TAGS=false          # Tags enabled by default
ATLAS_MD_MAX_TAGS=10
ATLAS_MD_TAG_SKIP_WORDS="and,the,of,in,to,for"
```

**Default Behavior**:
- Tags are generated by default for all pages
- Set `ATLAS_MD_DISABLE_TAGS=true` to disable tag generation
- The `atlas_md_*` metadata properties are ALWAYS included regardless of this setting

## Rollout Plan

1. **Phase 1**: Implement hierarchical tagging (this proposal)
2. **Phase 2**: Add content-based tag extraction
3. **Phase 3**: Implement link analysis tagging
4. **Phase 4**: Add ML-based enhancements

## Backwards Compatibility

- No breaking changes to existing functionality
- Tags are additive to existing frontmatter
- Feature is enabled by default but can be disabled via `ATLAS_MD_DISABLE_TAGS=true`
- Atlas Markdown metadata (`atlas_md_*` properties) are always added
