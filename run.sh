#!/bin/bash
# Simple run script for Atlas Markdown

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run the scraper with default settings
python -m atlas_markdown.cli "$@"
