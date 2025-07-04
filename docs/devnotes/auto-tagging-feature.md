# Auto-Tagging Feature

## Summary

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

### Current Implementation Limitations

The v0.4.0 implementation uses simple keyword matching on titles and section headings, which results in:
- Generic tags that don't capture page-specific content
- Missing technical concepts mentioned in the body text
- No differentiation between pages in the same category
- Limited understanding of the actual page content beyond its title

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

### Primary Approach: Content-Based Category Tagging

**Rationale**: Provides more useful tags than just copying page slugs. Analyzes page content to assign meaningful categories.

#### Data Sources:
1. **Product Name**: Extract from `base_url` (e.g., `/jira-service-management-cloud/` → `jira-service-management-cloud`)
2. **Page Title**: Available in `sibling_info["current_page_title"]`
3. **Section Heading**: Available in `sibling_info["section_heading"]`
4. **Breadcrumb Hierarchy**: Fallback option from `sibling_info["breadcrumb_data"]`

#### Implemented Tag Generation Algorithm:
```python
def _generate_hierarchical_tags(self, sibling_info: dict[str, Any], product: str) -> list[str]:
    tags = []

    # Always include product as first tag
    if product and product != "unknown":
        tags.append(product)

    # Extract meaningful category tags based on common documentation patterns
    current_title = sibling_info.get("current_page_title", "").lower()
    section = sibling_info.get("section_heading", "").lower()

    # Define category mappings for common documentation sections
    category_keywords = {
        "getting-started": ["getting started", "quick start", "overview", "introduction"],
        "administration": ["admin", "administration", "configure", "configuration", "settings", "setup"],
        "user-management": ["user", "users", "team", "teams", "member", "permission", "access", "role"],
        "api": ["api", "rest", "webhook", "integration", "developer"],
        "security": ["security", "auth", "authentication", "sso", "saml", "oauth"],
        "automation": ["automation", "automate", "workflow", "rule", "trigger"],
        "reporting": ["report", "analytics", "dashboard", "metrics", "statistics"],
        "troubleshooting": ["troubleshoot", "error", "issue", "problem", "fix"],
        "billing": ["billing", "payment", "subscription", "pricing", "plan"],
        "migration": ["migration", "import", "export", "backup", "restore"],
    }

    # Check both title and section for category keywords
    text_to_check = f"{current_title} {section}"

    for category, keywords in category_keywords.items():
        if any(keyword in text_to_check for keyword in keywords):
            if category not in tags:
                tags.append(category)
                # Only add 1-2 category tags to keep it focused
                if len(tags) >= 3:
                    break

    # Fallback to breadcrumbs if needed (only short, meaningful ones)
    # Additional fallback logic...

    return tags
```

### Enhanced Semantic Understanding

Building on the current keyword-based approach, local semantic analysis has been implemented to generate more context-aware tags:

#### 1. Content Analysis with Local NLP
- **TF-IDF Analysis**: Identify important terms specific to each page
- **Technical Term Extraction**: Detect API endpoints, configuration parameters, command names
- **N-gram Analysis**: Capture multi-word concepts like "service desk", "issue type", "workflow automation"
- **Pattern Matching**: Extract version numbers, product features, integration names

#### 2. Practical Implementation Using Local Libraries

The implementation uses BeautifulSoup for HTML parsing and Python's built-in regex for pattern matching:

**Key Features:**
- **Emphasized Content Extraction**: Extracts text from headers (h2-h4), bold, emphasized, and code elements
- **List Content Analysis**: Processes list items which often contain features and options
- **Pattern-Based Detection**: Uses regex patterns to identify technical content types
- **Frequency Analysis**: Counts technical term occurrences, excluding common English words
- **Configuration Support**: Respects environment variables for fine-tuning behavior

**Enhanced Pattern Detection:**
The system now detects 10+ technical content patterns including:
- API references (REST endpoints, HTTP methods)
- Configuration guides (YAML, JSON, properties files)
- CLI usage (command-line flags, shell commands)
- Integration guides (third-party services, plugins)
- Permission setups (roles, access control, RBAC)
- Code examples (function definitions, imports)
- Database guides (SQL, queries, migrations)
- Docker guides (containers, docker-compose)
- Kubernetes guides (pods, deployments, kubectl)
- Monitoring guides (metrics, logs, dashboards)

#### 3. Value-Added Tag Types

**Technical Tags** (automatically detected):
- `api-reference` - Pages with API endpoint documentation
- `configuration-guide` - Pages with config file examples
- `cli-usage` - Pages with command-line instructions
- `integration-guide` - Pages about third-party integrations
- `permissions-setup` - Pages about roles and access control
- `code-examples` - Pages with code samples and programming examples
- `database-guide` - Pages about database operations and SQL
- `docker-guide` - Pages about containerization and Docker
- `kubernetes-guide` - Pages about Kubernetes and orchestration
- `monitoring-guide` - Pages about monitoring, metrics, and observability

**Content-Based Tags** (from frequency analysis):
- Specific feature names (e.g., `smart-commits`, `sla-management`)
- Technical components (e.g., `jql-query`, `workflow-validator`)
- Integration names (e.g., `slack-integration`, `github-connector`)

### Secondary Enhancements (Future Phases)

#### 1. Advanced Content Analysis
- Implement lightweight topic modeling using scikit-learn
- Extract key phrases using TextRank algorithm
- Identify documentation type from content structure

#### 2. Link Analysis Tags
- Pages with many inbound links: tag as `hub` or `overview`
- Pages with many children: tag as `category`
- Leaf pages: tag as `detail` or `guide`

## Implementation Details

### 1. Update ContentParser (`content_parser.py`)

Add new methods for enhanced semantic tagging:
```python
def _extract_product_from_url(self, url: str) -> str:
    """Extract product identifier from base URL"""
    # Implementation details...

def _generate_hierarchical_tags(self, sibling_info: dict[str, Any], product: str) -> list[str]:
    """Generate tags from navigation hierarchy"""
    # Current implementation...

def _analyze_page_content(self, html_content: str, current_tags: list[str]) -> list[str]:
    """Analyze page content for semantic tags using local NLP techniques"""
    # New semantic analysis implementation...

def _extract_technical_patterns(self, text: str) -> set[str]:
    """Extract technical patterns like API endpoints, config files, CLI commands"""
    # Pattern matching implementation...

def _get_atlas_md_version(self) -> str:
    """Get current Atlas Markdown version"""
    from atlas_markdown import __version__
    return __version__
```

Update `convert_to_markdown()` method to:
1. Call content analysis after basic tag generation
2. Pass HTML content to semantic analyzer
3. Merge and deduplicate tags from both approaches

### 2. Tag Normalization Rules

- Convert to lowercase
- Replace spaces and special characters with hyphens
- Remove duplicate hyphens
- Strip leading/trailing hyphens
- Skip common words: "and", "the", "of", etc.
- Maximum tag length: 50 characters

### 3. Example Output

#### v0.4.0
For page: `https://support.atlassian.com/jira-service-management-cloud/docs/manage-users/`

```yaml
---
url: https://support.atlassian.com/jira-service-management-cloud/docs/manage-users/
scrape_date: 2025-01-25T10:30:00
title: Manage users
description: Learn how to manage users in Jira Service Management
tags:
  - jira-service-management-cloud
  - user-management
atlas_md_version: 0.4.0
atlas_md_url: https://github.com/jsade/atlas-markdown
atlas_md_product: jira-service-management-cloud
atlas_md_category: Administration
atlas_md_section: User Management
---
```

#### With Enhanced Semantic Understanding
Same page with content analysis:

```yaml
---
url: https://support.atlassian.com/jira-service-management-cloud/docs/manage-users/
scrape_date: 2025-01-25T10:30:00
title: Manage users
description: Learn how to manage users in Jira Service Management
tags:
  - jira-service-management-cloud
  - user-management
  - permissions-setup    # Detected from content about roles
  - api-reference        # Found REST API endpoints
  - bulk-operations      # Frequent term in content
  - customer-portal      # Specific feature discussed
atlas_md_version: 0.5.0
atlas_md_url: https://github.com/jsade/atlas-markdown
atlas_md_product: jira-service-management-cloud
atlas_md_category: Administration
atlas_md_section: User Management
---
```

**Note**: The enhanced version adds content-specific tags that help differentiate between pages in the same category and surface technical details not apparent from the title alone.

## Benefits

### Semantic Understanding
6. **Technical Discovery**: Find all pages with API documentation, CLI commands, or config examples
7. **Feature-Specific Search**: Locate documentation for specific features like "smart-commits" or "sla-management"
8. **Better Categorization**: Distinguish between overview pages and detailed implementation guides
9. **Integration Mapping**: Quickly find all pages related to specific integrations
10. **Troubleshooting Aid**: Identify error-related documentation through content patterns

## Migration Considerations

For existing fetched documentation:
1. Add a `--retag` command option to update only frontmatter
2. Preserve existing frontmatter fields
3. Log changes for user review

## Future Enhancements

### Advanced Features
1. **Custom Tag Templates**: User-defined tag generation rules
2. **Tag Synonyms**: Map similar concepts to consistent tags
3. **Lightweight Topic Modeling**: Use scikit-learn for topic extraction
4. **Tag Hierarchy**: Parent-child tag relationships
5. **Tag Statistics**: Report on tag distribution

### Machine Learning (Optional)
1. **Pre-trained Models**: Use local BERT-like models for classification
2. **Document Embeddings**: Generate semantic representations
3. **Clustering**: Group similar pages automatically
4. **Custom Training**: Allow users to train on their own documentation

## Configuration Options

Add environment variables:
```bash
# Current options
ATLAS_MD_DISABLE_TAGS=false          # Tags enabled by default
ATLAS_MD_MAX_TAGS=10
ATLAS_MD_TAG_SKIP_WORDS="and,the,of,in,to,for"

# Proposed semantic options
ATLAS_MD_ENABLE_CONTENT_ANALYSIS=true   # Enable semantic content analysis
ATLAS_MD_MIN_TERM_FREQUENCY=3           # Minimum occurrences for technical terms
ATLAS_MD_CONTENT_ANALYSIS_DEPTH=500     # Max lines to analyze per page
ATLAS_MD_TECHNICAL_PATTERNS=true        # Enable technical pattern detection
```

**Default Behavior**:
- Tags are generated by default for all pages
- Set `ATLAS_MD_DISABLE_TAGS=true` to disable tag generation
- The `atlas_md_*` metadata properties are ALWAYS included regardless of this setting
- Semantic analysis would be opt-in initially for performance testing

## Implementation Status

### v0.4
1. ✅ **Content-Based Category Tagging** - Analyzes page titles and sections to assign meaningful category tags
2. ✅ **Atlas Markdown Metadata** - Always adds version, URL, product, category, and section metadata
3. ✅ **Environment Variable Control** - `ATLAS_MD_DISABLE_TAGS` to disable tag generation
4. ✅ **Predefined Categories** - 10 common documentation categories (getting-started, administration, user-management, api, security, automation, reporting, troubleshooting, billing, migration)

### v0.5
1. ✅ **Enhanced Semantic Understanding** - Analyze page content for technical terms and patterns
2. ✅ **Pattern-Based Detection** - Identify API docs, config guides, CLI references
3. ✅ **Frequency Analysis** - Extract important terms using statistical methods
4. ✅ **Content-Aware Tags** - Generate tags specific to page content, not just title

### Future Enhancements
1. **Link Analysis** - Tag pages based on their role in the documentation graph
2. **Custom Tag Templates** - User-defined tag generation rules
3. **Advanced NLP** - Use more sophisticated language processing techniques
4. **Tag Relationships** - Build hierarchical tag structures
