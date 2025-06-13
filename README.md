# Atlassian Documentation Scraper

A command-line tool that autonomously downloads and converts the selected Atlassian documentation from https://support.atlassian.com/ to Markdown format.

## Quick Start

```bash
# 1. Run the initialization script
python3 init.py

# 2. Activate the virtual environment
source venv/bin/activate

# 3. Configure settings (optional)
cp .env.example .env
# Edit .env with your preferences

# 4. Run the scraper
python scraper.py --output ./docs

# 5. Test the environment (optional)
python test_environment.py
```

## Usage

### Basic Usage

```bash
# Scrape with default settings
python scraper.py

# Or use the run script
./run.sh

# Specify output directory
python scraper.py --output ./atlassian-docs

# Adjust concurrent workers and delay
python scraper.py --workers 3 --delay 2.0

# Resume from previous interrupted session
python scraper.py --resume

# Dry run to see what would be scraped
python scraper.py --dry-run

# Enable verbose logging
python scraper.py --verbose
```

### Command Line Options

- `--output, -o`: Output directory for documentation (default: ./output)
- `--workers, -w`: Number of concurrent workers (default: 5)
- `--delay, -d`: Delay between requests in seconds (default: 1.5)
- `--resume`: Resume from previous state
- `--dry-run`: Show what would be scraped without downloading
- `--verbose, -v`: Enable verbose output

### Output Structure

The scraper creates a directory structure that mirrors the URL paths:

```
output/
├── index.md                    # Main index with all pages
├── docs/
│   ├── getting-started.md
│   ├── administration/
│   │   ├── index.md
│   │   └── user-management.md
│   └── ...
├── resources/
│   ├── index.md
│   └── ...
└── images/
    └── [organized by page]
```

### State Management

The scraper maintains state in `scraper_state.db` to support:
- Resuming interrupted sessions
- Tracking scraped pages and images
- Avoiding duplicate downloads
- Recording failed pages for retry

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_scraper.py -v

# Run with coverage
pytest --cov=src tests/
```

## Project Overview
This tool is specifically designed to download all available web documentation for Atlassian Jira Service Management (Cloud) currently under https://support.atlassian.com/jira-service-management-cloud/docs/ and entry point at https://support.atlassian.com/jira-service-management-cloud/resources/


## Requirements

- A command line tool for modern MacOS with Brew installed
- The tool should be autonomous with minimal user interaction
- Should be able to make logical assumptions on contexts and content
- Can use Claude API to assist if helpful (implementation must be kept simple)


### State management

- The crawler needs to remember what has been scraped so it can continue where it was previously halted

### Content and Output Requirements

- HTML content must be transformed to Markdown (Commonmark or other extended format)
- Images that are visible in the UI must be downloaded and correctly referenced in the output
- Must create directory hierarchies that align with the relative paths in the URL (assuming that https://support.atlassian.com/jira-service-management-cloud/ is the document root)
