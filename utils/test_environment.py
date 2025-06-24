#!/usr/bin/env python3
"""
Test script to verify the environment is set up correctly
"""

import importlib
import os
import sys
from pathlib import Path


def test_python_version() -> None:
    """Check Python version"""
    print(f"Python version: {sys.version}")
    assert sys.version_info >= (3, 11), "Python 3.11+ required"
    print("✓ Python version OK")


def test_imports() -> bool:
    """Test all required imports"""
    required_modules = [
        ("click", "CLI framework"),
        ("playwright", "Browser automation"),
        ("bs4", "HTML parsing (BeautifulSoup4)"),
        ("markdownify", "HTML to Markdown conversion"),
        ("aiofiles", "Async file operations"),
        ("httpx", "Async HTTP client"),
        ("PIL", "Image processing (Pillow)"),
        ("tqdm", "Progress bars"),
        ("rich", "Rich terminal output"),
        ("aiosqlite", "Async SQLite"),
        ("dotenv", "Environment variables"),
        ("pytest", "Testing framework"),
        ("pytest_asyncio", "Async testing"),
        ("ruff", "Linting"),
        ("black", "Code formatting"),
        ("mypy", "Type checking"),
    ]

    print("\nTesting imports:")
    failures: list[tuple[str, str]] = []
    for module, description in required_modules:
        try:
            importlib.import_module(module)
            print(f"✓ {module:20} - {description}")
        except ImportError as e:
            print(f"✗ {module:20} - {description}")
            failures.append((module, str(e)))

    if failures:
        print("\nFailed imports:")
        for module, error in failures:
            print(f"  - {module}: {error}")
        return False

    return True


def test_playwright() -> bool:
    """Test Playwright browser availability"""
    print("\nTesting Playwright:")
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            # Check if Chromium is installed
            browser = p.chromium.launch(headless=True)
            browser.close()
            print("✓ Chromium browser available")
            return True
    except Exception as e:
        print(f"✗ Playwright error: {e}")
        print("  Run: playwright install chromium")
        return False


def test_project_structure() -> bool:
    """Test project structure"""
    print("\nChecking project structure:")

    # Need to check from parent directory since script is now in utils/
    parent_dir = Path(__file__).parent.parent

    required_paths = [
        ("src", "Source code directory"),
        ("src/scrapers", "Scraper modules"),
        ("src/parsers", "Parser modules"),
        ("src/utils", "Utility modules"),
        ("tests", "Test directory"),
        ("utils", "Utility scripts"),
        (".gitignore", "Git ignore file"),
        ("pyproject.toml", "Project configuration"),
        ("requirements.txt", "Python dependencies"),
        ("scraper.py", "Main scraper script"),
        (".env.example", "Environment template"),
    ]

    all_ok = True
    for path, description in required_paths:
        full_path = parent_dir / path
        if full_path.exists():
            print(f"✓ {path:20} - {description}")
        else:
            print(f"✗ {path:20} - {description}")
            all_ok = False

    return all_ok


def test_environment_file() -> bool:
    """Test environment configuration"""
    print("\nChecking environment configuration:")

    parent_dir = Path(__file__).parent.parent
    env_file = parent_dir / ".env"
    env_example = parent_dir / ".env.example"

    # First check system environment variables
    required_vars = ["BASE_URL"]
    optional_vars = ["OUTPUT_DIR", "WORKERS", "REQUEST_DELAY"]

    # Check if BASE_URL is in system environment
    if "BASE_URL" in os.environ:
        print("✓ BASE_URL found in system environment variables")
        config = {var: os.environ.get(var, "") for var in required_vars + optional_vars}
        source = "environment"
    elif env_file.exists():
        print("⚠ Using .env file (Note: Consider setting shell environment variables instead)")
        print("  For example, add to ~/.zshrc or ~/.bashrc:")
        print('  export BASE_URL="https://support.atlassian.com/jira-service-management-cloud/"')
        # Check for required variables
        try:
            from dotenv import dotenv_values

            # dotenv_values returns dict[str, str | None], so we need to handle None values
            raw_config = dotenv_values(env_file)
            config = {k: v or "" for k, v in raw_config.items()}  # Convert None to empty string
            source = ".env file"

            missing = [var for var in required_vars if var not in config or not config[var]]
            if missing:
                print(f"⚠ Missing required variables in {source}: {', '.join(missing)}")
                return False
        except Exception as e:
            print(f"✗ Error reading .env file: {e}")
            return False
    else:
        print("✗ BASE_URL environment variable not found")
        print("\n  Set BASE_URL in your shell configuration:")
        print("  For zsh (~/.zshrc):")
        print('    export BASE_URL="https://support.atlassian.com/jira-service-management-cloud/"')
        print("  For bash (~/.bashrc):")
        print('    export BASE_URL="https://support.atlassian.com/jira-service-management-cloud/"')
        print("\n  Then reload your shell configuration:")
        print("    source ~/.zshrc  # or ~/.bashrc")

        if env_example.exists():
            print("\n  Alternatively, for local development only:")
            print("    cp .env.example .env")
        return False

    # Now we have config from either source
    print(f"✓ Required environment variables present (from {source})")

    # Strict validation for BASE_URL
    base_url_value = config.get("BASE_URL", "")
    base_url = base_url_value.strip().rstrip("/") if base_url_value else ""
    required_prefix = "https://support.atlassian.com/"

    if not base_url:
        print("⚠ BASE_URL is empty")
        return False

    if not base_url.startswith(required_prefix):
        print(f"⚠ BASE_URL must start with '{required_prefix}' (got '{base_url}')")
        print("  This scraper is designed specifically for Atlassian support documentation.")
        return False

    # Check if it has an endpoint after the base
    if base_url == required_prefix.rstrip("/"):
        print("⚠ BASE_URL must include a specific product endpoint")
        print("  Examples:")
        print(f"    - {required_prefix}jira-service-management-cloud")
        print(f"    - {required_prefix}jira-software-cloud")
        print(f"    - {required_prefix}confluence-cloud")
        return False

    # Check for known valid endpoints
    valid_endpoints = [
        "jira-service-management-cloud",
        "jira-software-cloud",
        "confluence-cloud",
        "jira-work-management",
        "trello",
        "bitbucket-cloud",
        "statuspage",
    ]

    endpoint = base_url.replace(required_prefix, "").split("/")[0]
    if endpoint not in valid_endpoints:
        print(f"⚠ Warning: '{endpoint}' is not a known Atlassian product endpoint")
        print(f"  Known endpoints: {', '.join(valid_endpoints)}")
        print("  The scraper may not work correctly with unknown endpoints.")

    return True


def test_project_imports() -> bool:
    """Test importing project modules"""
    print("\nTesting project module imports:")

    # Add parent directory to path
    parent_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(parent_dir))

    project_modules = [
        ("src.scrapers.crawler", "Web crawler"),
        ("src.parsers.content_parser", "Content parser"),
        ("src.parsers.link_resolver", "Link resolver"),
        ("src.utils.state_manager", "State manager"),
        ("src.utils.file_manager", "File manager"),
        ("src.utils.markdown_linter", "Markdown linter"),
    ]

    all_ok = True
    for module, description in project_modules:
        try:
            importlib.import_module(module)
            print(f"✓ {module:30} - {description}")
        except ImportError as e:
            print(f"✗ {module:30} - {description}")
            print(f"  Error: {e}")
            all_ok = False

    return all_ok


def main() -> None:
    """Run all tests"""
    print("Environment Test for Atlas Markdown")
    print("=" * 60)

    all_ok = True

    # Run tests
    test_python_version()
    all_ok &= test_imports()
    all_ok &= test_playwright()
    all_ok &= test_project_structure()
    all_ok &= test_environment_file()
    all_ok &= test_project_imports()

    print("\n" + "=" * 60)
    if all_ok:
        print("✓ All tests passed! Environment is ready.")
        print("\nNext steps:")
        print("1. python scraper.py --help")
        print("2. python scraper.py --output ./output")
    else:
        print("✗ Some tests failed.")
        print("\nTroubleshooting:")
        print("1. Run: pip install -r requirements.txt")
        print("2. Run: playwright install chromium")
        print("3. Set environment variables in your shell configuration")
        print("4. Check the project structure matches expected layout")
        sys.exit(1)


if __name__ == "__main__":
    main()
