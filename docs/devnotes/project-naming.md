# Atlas Markdown Naming Guide

## Overview

Atlas Markdown is a Python-based tool that downloads and converts Atlassian product documentation (Jira, Confluence, Trello, Bitbucket, Statuspage) into clean markdown files optimized for tools like Obsidian.

## Name Reasoning

The name "Atlas Markdown" was chosen to:
- **Atlas**: Evokes Atlassian without trademark concerns, suggests navigation/mapping of documentation
- **Markdown**: Clearly indicates the output format
- Together they communicate the tool's purpose concisely while remaining memorable

The name captures the three core concepts:
1. **Atlassian products** (via "Atlas")
2. **Documentation** (implied by context)
3. **Markdown** (explicit)

## Official Configuration

```yaml
GitHub Repository: atlas-markdown
PyPI Package:      atlas-markdown
Python Module:     atlas_markdown
CLI Command:       atlas-markdown
Friendly Name:     Atlas Markdown - Atlassian Documentation Converter
Short Name:        Atlas Markdown
```

## Usage Examples

### Command Line
```bash
# Install from PyPI
pip install atlas-markdown

# Run the tool
atlas-markdown --output ./docs --workers 4

# Check version
atlas-markdown --version
```

### Python Import
```python
from atlas_markdown import Crawler
from atlas_markdown.utils import StateManager

# Initialize crawler
crawler = Crawler(base_url="https://support.atlassian.com/jira-software-cloud/")
```

### Documentation Headers
```markdown
# Atlas Markdown

Atlas Markdown downloads and converts Atlassian product documentation...

## Getting Started with Atlas Markdown

To begin using Atlas Markdown, first install it via pip...
```

### Conversation & Communication
- "I used Atlas Markdown to convert our Confluence docs"
- "Atlas Markdown supports resumable downloads"
- "The latest Atlas Markdown release adds Statuspage support"

### Logging & Output
```
[Atlas Markdown] Starting documentation fetch...
[Atlas Markdown] Processing page 1 of 500: Getting Started
[Atlas Markdown] Successfully converted 500 pages in 12 minutes
```

### Issue Tracking
- Issue: "Atlas Markdown fails on pages with embedded videos"
- PR: "Add retry logic to Atlas Markdown image downloader"
- Discussion: "Should Atlas Markdown preserve table formatting?"

### Configuration Files
```ini
APP_NAME=Atlas Markdown
LOG_PREFIX=[Atlas Markdown]
```

```toml
# pyproject.toml
[tool.poetry]
name = "atlas-markdown"
description = "Atlas Markdown - Convert Atlassian documentation to Markdown"
```

## Branding Guidelines

- Always capitalize as "Atlas Markdown" in prose
- Use `atlas-markdown` for package names and commands (lowercase, hyphenated)
- Use `atlas_markdown` for Python module names (lowercase, underscored)
- When space is limited, "Atlas Md" is an acceptable abbreviation.
- "ATLAS_MD_" is used as the prefix for environment variables
- Never use just "Atlas" alone due to naming conflicts and potential confusion

## Other

- Minimize the use of the word 'scrape', 'scraping', or its other forms. Instead, use 'fetch', 'fetching', or alternatively 'crawl', 'crawling'.
