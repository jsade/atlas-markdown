#!/usr/bin/env python3
"""
Initialization script for Atlassian Service Management Documentation Scraper
This script sets up the development environment and project structure
"""

import os
import platform
import subprocess
import sys
from pathlib import Path


class Colors:
    """Terminal colors for output"""

    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


def print_header(message):
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{message.center(60)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}\n")


def print_success(message):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {message}{Colors.END}")


def print_error(message):
    """Print error message"""
    print(f"{Colors.RED}✗ {message}{Colors.END}")


def print_info(message):
    """Print info message"""
    print(f"{Colors.YELLOW}→ {message}{Colors.END}")


def check_python_version():
    """Check if Python version is 3.8 or higher"""
    print_info("Checking Python version...")
    print_success(f"Python {sys.version.split()[0]} detected")


def check_macos():
    """Check if running on macOS"""
    print_info("Checking operating system...")
    if platform.system() != "Darwin":
        print_error("This tool is designed for macOS")
        response = input(f"{Colors.YELLOW}Continue anyway? (y/N): {Colors.END}")
        if response.lower() != "y":
            sys.exit(1)
    else:
        print_success("macOS detected")


def create_virtual_environment():
    """Create Python virtual environment"""
    print_info("Creating virtual environment...")
    if Path("venv").exists():
        print_info("Virtual environment already exists")
        response = input(f"{Colors.YELLOW}Recreate virtual environment? (y/N): {Colors.END}")
        if response.lower() == "y":
            subprocess.run(["rm", "-rf", "venv"], check=True)
        else:
            return

    subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
    print_success("Virtual environment created")


def get_venv_python():
    """Get path to Python in virtual environment"""
    return "./venv/bin/python" if platform.system() != "Windows" else "./venv/Scripts/python"


def install_dependencies():
    """Install Python dependencies"""
    print_info("Installing Python dependencies...")

    pip = "./venv/bin/pip" if platform.system() != "Windows" else "./venv/Scripts/pip"

    # Upgrade pip first
    subprocess.run([pip, "install", "--upgrade", "pip"], check=True)

    # Core dependencies
    dependencies = [
        "playwright",
        "click",
        "beautifulsoup4",
        "markdownify",
        "aiofiles",
        "httpx",
        "Pillow",
        "tqdm",
        "rich",
        "aiosqlite",
        "python-dotenv",
    ]

    # Development dependencies
    dev_dependencies = [
        "pytest",
        "pytest-asyncio",
        "pytest-cov",
        "black",
        "ruff",
        "mypy",
        "pre-commit",
    ]

    print_info("Installing core dependencies...")
    subprocess.run([pip, "install"] + dependencies, check=True)

    print_info("Installing development dependencies...")
    subprocess.run([pip, "install"] + dev_dependencies, check=True)

    print_success("All dependencies installed")


def install_playwright_browser():
    """Install Playwright Chromium browser"""
    print_info("Installing Playwright Chromium browser...")
    playwright = (
        "./venv/bin/playwright" if platform.system() != "Windows" else "./venv/Scripts/playwright"
    )
    subprocess.run([playwright, "install", "chromium"], check=True)
    print_success("Chromium browser installed")


def create_project_structure():
    """Create project directory structure"""
    print_info("Creating project structure...")

    directories = [
        "src",
        "src/scrapers",
        "src/parsers",
        "src/utils",
        "tests",
        "docs",
        "output",
    ]

    for directory in directories:
        Path(directory).mkdir(exist_ok=True)

    # Create __init__.py files
    init_files = [
        "src/__init__.py",
        "src/scrapers/__init__.py",
        "src/parsers/__init__.py",
        "src/utils/__init__.py",
        "tests/__init__.py",
    ]

    for init_file in init_files:
        Path(init_file).touch()

    print_success("Project structure created")


def create_configuration_files():
    """Create configuration files"""
    print_info("Creating configuration files...")

    # .gitignore
    gitignore_content = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/

# IDE
.vscode/
.idea/
*.swp
*.swo
.DS_Store

# Project specific
output/
*.db
*.sqlite
.env
logs/
*.log

# Testing
.coverage
.pytest_cache/
htmlcov/
.mypy_cache/
.ruff_cache/

# Distribution
dist/
build/
*.egg-info/
"""

    with open(".gitignore", "w") as f:
        f.write(gitignore_content)

    # pyproject.toml
    pyproject_content = """[tool.black]
line-length = 100
target-version = ['py38']

[tool.ruff]
line-length = 100
select = ["E", "F", "W", "I", "N", "B", "UP"]
ignore = ["E501"]  # Line too long, handled by black

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.8"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true

[tool.coverage.run]
source = ["src"]
omit = ["tests/*", "venv/*"]
"""

    with open("pyproject.toml", "w") as f:
        f.write(pyproject_content)

    # .env.example
    env_example = """# Atlassian Scraper Configuration

# Output directory for downloaded documentation
OUTPUT_DIR=./output

# Number of concurrent workers for downloading
WORKERS=5

# Delay between requests (in seconds)
REQUEST_DELAY=1.5

# User agent string
USER_AGENT="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# Claude API (optional, for content enhancement)
# ANTHROPIC_API_KEY=your_api_key_here

# Logging level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO
"""

    with open(".env.example", "w") as f:
        f.write(env_example)

    # Pre-commit configuration
    precommit_content = """repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict

  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black

  - repo: https://github.com/charliermarsh/ruff-pre-commit
    rev: v0.0.272
    hooks:
      - id: ruff
        args: [--fix]
"""

    with open(".pre-commit-config.yaml", "w") as f:
        f.write(precommit_content)

    print_success("Configuration files created")


def create_requirements_file():
    """Create requirements.txt from installed packages"""
    print_info("Creating requirements.txt...")

    pip = "./venv/bin/pip" if platform.system() != "Windows" else "./venv/Scripts/pip"

    # Get installed packages
    result = subprocess.run([pip, "freeze"], capture_output=True, text=True)

    # Write requirements.txt
    with open("requirements.txt", "w") as f:
        f.write(result.stdout)

    print_success("requirements.txt created")


def create_main_script():
    """Create the main scraper script"""
    print_info("Creating main scraper script...")

    scraper_content = '''#!/usr/bin/env python3
"""
Atlassian Jira Service Management Documentation Scraper
Main entry point for the command-line tool
"""

import click
import asyncio
from pathlib import Path
from rich.console import Console
from rich.progress import Progress
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

console = Console()


@click.command()
@click.option('--output', '-o',
              default='./output',
              help='Output directory for documentation')
@click.option('--workers', '-w',
              default=5,
              type=int,
              help='Number of concurrent workers')
@click.option('--delay', '-d',
              default=1.5,
              type=float,
              help='Delay between requests in seconds')
@click.option('--resume',
              is_flag=True,
              help='Resume from previous state')
@click.option('--dry-run',
              is_flag=True,
              help='Show what would be scraped without downloading')
@click.option('--verbose', '-v',
              is_flag=True,
              help='Enable verbose output')
def scrape(output, workers, delay, resume, dry_run, verbose):
    """Scrape Atlassian Jira Service Management documentation"""

    console.print(f"[bold blue]Atlassian Documentation Scraper[/bold blue]")
    console.print(f"Output directory: {output}")
    console.print(f"Workers: {workers}")
    console.print(f"Request delay: {delay}s")

    if dry_run:
        console.print("[yellow]DRY RUN MODE - No files will be downloaded[/yellow]")

    if resume:
        console.print("[green]Resuming from previous state...[/green]")

    # TODO: Implement scraping logic
    console.print("[red]Scraper implementation pending...[/red]")


if __name__ == '__main__':
    scrape()
'''

    with open("scraper.py", "w") as f:
        f.write(scraper_content)

    # Make it executable
    os.chmod("scraper.py", 0o755)

    print_success("Main scraper script created")


def setup_pre_commit():
    """Initialize pre-commit hooks"""
    print_info("Setting up pre-commit hooks...")
    pre_commit = (
        "./venv/bin/pre-commit" if platform.system() != "Windows" else "./venv/Scripts/pre-commit"
    )

    try:
        subprocess.run([pre_commit, "install"], check=True)
        print_success("Pre-commit hooks installed")
    except subprocess.CalledProcessError:
        print_info("Skipping pre-commit setup (git repository not initialized)")


def print_next_steps():
    """Print next steps for the user"""
    print_header("Setup Complete!")

    print("Next steps:\n")
    print(f"{Colors.BOLD}1. Activate the virtual environment:{Colors.END}")
    print(f"   {Colors.GREEN}source venv/bin/activate{Colors.END}\n")

    print(f"{Colors.BOLD}2. Copy and configure environment variables:{Colors.END}")
    print(f"   {Colors.GREEN}cp .env.example .env{Colors.END}")
    print(f"   {Colors.GREEN}# Edit .env with your settings{Colors.END}\n")

    print(f"{Colors.BOLD}3. Run the scraper:{Colors.END}")
    print(f"   {Colors.GREEN}python scraper.py --help{Colors.END}")
    print(f"   {Colors.GREEN}python scraper.py --output ./docs{Colors.END}\n")

    print(f"{Colors.BOLD}4. Run tests:{Colors.END}")
    print(f"   {Colors.GREEN}pytest tests/{Colors.END}\n")

    print(f"{Colors.YELLOW}For more information, see README.md and CLAUDE.md{Colors.END}")


def main():
    """Main initialization function"""
    print_header("Atlassian Documentation Scraper Setup")

    try:
        # System checks
        check_python_version()
        check_macos()

        # Environment setup
        create_virtual_environment()
        install_dependencies()
        install_playwright_browser()

        # Project setup
        create_project_structure()
        create_configuration_files()
        create_requirements_file()
        create_main_script()
        setup_pre_commit()

        # Done!
        print_next_steps()

    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print_error("\nSetup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
