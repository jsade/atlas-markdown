# Utility Scripts

This directory contains standalone utility scripts for post-processing and maintenance of scraped Atlassian documentation.

## Available Utilities

### fix_wiki_links.py
Fixes broken internal wiki-style links in already scraped documentation. Uses the state database to resolve links correctly.

**Usage:**
```bash
python utils/fix_wiki_links.py ./output
python utils/fix_wiki_links.py ./output --dry-run  # Preview changes
python utils/fix_wiki_links.py ./output --verbose  # Show detailed changes
```

### lint_markdown.py
Comprehensive markdown linter that checks for formatting issues and can automatically fix them.

**Usage:**
```bash
python utils/lint_markdown.py ./output           # Check for issues
python utils/lint_markdown.py ./output --fix     # Auto-fix issues
python utils/lint_markdown.py ./output --report report.md  # Save detailed report
```

### regenerate_index.py
Regenerates the main index file based on the current state database. Useful after manual edits or partial scrapes.

**Usage:**
```bash
python utils/regenerate_index.py ./output
```

### test_environment.py
Verifies that the development environment is correctly set up with all required dependencies.

**Usage:**
```bash
python utils/test_environment.py
```

## Notes
- All utilities require the scraper to have been run at least once to create the state database
- The utilities work with the output directory structure created by the main scraper
- Most utilities support verbose mode for debugging
