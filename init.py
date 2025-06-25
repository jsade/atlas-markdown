#!/usr/bin/env python3
"""
Initialization script for Atlas Markdown
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


def print_header(message: str) -> None:
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{message.center(60)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}\n")


def print_success(message: str) -> None:
    """Print success message"""
    print(f"{Colors.GREEN}✓ {message}{Colors.END}")


def print_error(message: str) -> None:
    """Print error message"""
    print(f"{Colors.RED}✗ {message}{Colors.END}")


def print_info(message: str) -> None:
    """Print info message"""
    print(f"{Colors.YELLOW}→ {message}{Colors.END}")


def check_python_version() -> None:
    """Check if Python version is 3.11 or higher"""
    print_info("Checking Python version...")
    print_success(f"Python {sys.version.split()[0]} detected")


def check_macos() -> None:
    """Check if running on macOS"""
    print_info("Checking operating system...")
    if platform.system() != "Darwin":
        print_error("This tool is designed for macOS")
        response = input(f"{Colors.YELLOW}Continue anyway? (y/N): {Colors.END}")
        if response.lower() != "y":
            sys.exit(1)
    else:
        print_success("macOS detected")


def create_virtual_environment() -> None:
    """Create Python virtual environment"""
    print_info("Creating virtual environment...")

    # Check if venv exists and is valid
    if Path("venv").exists():
        pip_path = Path("venv/bin/pip")
        venv_is_valid = False

        if pip_path.exists():
            try:
                with open(pip_path) as f:
                    shebang = f.readline().strip()
                    # Check if shebang points to current directory
                    current_dir = str(Path.cwd())
                    if current_dir in shebang:
                        venv_is_valid = True
            except Exception:
                pass

        if not venv_is_valid:
            print_error("Virtual environment appears to be relocated or corrupted")
            print_info("Removing and recreating virtual environment...")
            subprocess.run(["rm", "-rf", "venv"], check=True)
        else:
            print_info("Virtual environment already exists")
            response = input(f"{Colors.YELLOW}Recreate virtual environment? (y/N): {Colors.END}")
            if response.lower() == "y":
                subprocess.run(["rm", "-rf", "venv"], check=True)
            else:
                return

    # Create new virtual environment
    subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
    print_success("Virtual environment created")


def get_venv_python() -> str:
    """Get path to Python in virtual environment"""
    return "./venv/bin/python" if platform.system() != "Windows" else "./venv/Scripts/python"


def install_dependencies() -> None:
    """Install Python dependencies"""
    print_info("Installing Python dependencies...")

    # Check if venv exists
    venv_pip = "./venv/bin/pip" if platform.system() != "Windows" else "./venv/Scripts/pip"

    if not Path(venv_pip).exists():
        print_error(f"Virtual environment pip not found at {venv_pip}")
        print_info("Please ensure the virtual environment is properly created")
        sys.exit(1)

    # Use the venv pip directly
    pip = venv_pip

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
        "aiohttp",
        "Pillow",
        "tqdm",
        "rich",
        "aiosqlite",
        "python-dotenv",
        "psutil",
        "lxml",
        "PyYAML",
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
        "ipdb",
        # Type stubs for mypy
        "types-aiofiles",
        "types-PyYAML",
        "types-psutil",
        "types-setuptools",
        "types-beautifulsoup4",
        "types-click",
        "types-tqdm",
        "types-Pillow",
    ]

    print_info("Installing core dependencies...")
    subprocess.run([pip, "install"] + dependencies, check=True)

    print_info("Installing development dependencies...")
    subprocess.run([pip, "install"] + dev_dependencies, check=True)

    print_success("All dependencies installed")


def install_playwright_browser() -> None:
    """Install Playwright Chromium browser"""
    print_info("Installing Playwright Chromium browser...")
    # Use venv playwright
    playwright = (
        "./venv/bin/playwright" if platform.system() != "Windows" else "./venv/Scripts/playwright"
    )

    if not Path(playwright).exists():
        print_error(f"Playwright not found at {playwright}")
        print_info("Please ensure playwright is installed in the virtual environment")
        sys.exit(1)

    subprocess.run([playwright, "install", "chromium"], check=True)
    print_success("Chromium browser installed")


def create_project_structure() -> None:
    """Create project directory structure"""
    print_info("Creating project structure...")

    directories = [
        "src",
        "atlas_markdown/scrapers",
        "atlas_markdown/parsers",
        "atlas_markdown/utils",
        "tests",
        "output",
        "logs",
    ]

    for directory in directories:
        Path(directory).mkdir(exist_ok=True)

    # Create __init__.py files
    init_files = [
        "atlas_markdown/__init__.py",
        "atlas_markdown/scrapers/__init__.py",
        "atlas_markdown/parsers/__init__.py",
        "atlas_markdown/utils/__init__.py",
        "tests/__init__.py",
    ]

    for init_file in init_files:
        Path(init_file).touch()

    print_success("Project structure created")


def create_configuration_files() -> None:
    """Create configuration files"""
    print_info("Creating configuration files...")

    # .gitignore
    if Path(".gitignore").exists():
        print_info(".gitignore already exists, skipping...")
    else:
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
    if Path("pyproject.toml").exists():
        print_info("pyproject.toml already exists, skipping...")
    else:
        pyproject_content = """[tool.black]
line-length = 100
target-version = ['py311']

[tool.ruff]
line-length = 100
select = ["E", "F", "W", "I", "N", "B", "UP"]
ignore = ["E501"]  # Line too long, handled by black

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true

[tool.coverage.run]
source = ["src"]
omit = ["tests/*", "venv/*"]
"""

        with open("pyproject.toml", "w") as f:
            f.write(pyproject_content)

    # Note: .env file is not required - environment variables should be set in shell config
    if not Path(".env").exists():
        print_info(".env file not found (this is normal - use shell environment variables)")

    # Pre-commit configuration
    if Path(".pre-commit-config.yaml").exists():
        print_info(".pre-commit-config.yaml already exists, skipping...")
    else:
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


def create_requirements_file() -> None:
    """Create requirements.txt from installed packages"""
    print_info("Creating requirements.txt...")

    # Use venv pip
    pip = "./venv/bin/pip" if platform.system() != "Windows" else "./venv/Scripts/pip"

    if not Path(pip).exists():
        print_error(f"Pip not found at {pip}")
        print_info("Please ensure the virtual environment is properly created")
        sys.exit(1)

    # Get installed packages
    result = subprocess.run([pip, "freeze"], capture_output=True, text=True)

    # Write requirements.txt
    with open("requirements.txt", "w") as f:
        f.write(result.stdout)

    print_success("requirements.txt created")


def verify_main_script() -> None:
    """Verify the main CLI module exists"""
    print_info("Verifying main CLI module...")

    if Path("atlas_markdown/cli.py").exists():
        print_success("Main CLI module found")
        # Make it executable
        os.chmod("atlas_markdown/cli.py", 0o755)
    else:
        print_error(
            "atlas_markdown/cli.py not found - please ensure you have the complete repository"
        )


def setup_pre_commit() -> None:
    """Initialize pre-commit hooks"""
    print_info("Setting up pre-commit hooks...")
    # Use venv pre-commit
    pre_commit = (
        "./venv/bin/pre-commit" if platform.system() != "Windows" else "./venv/Scripts/pre-commit"
    )

    if not Path(pre_commit).exists():
        print_info("Pre-commit not yet installed, skipping hook setup")
        return

    try:
        subprocess.run([pre_commit, "install"], check=True)
        print_success("Pre-commit hooks installed")
    except subprocess.CalledProcessError:
        print_info("Skipping pre-commit setup (git repository not initialized)")


def print_next_steps() -> None:
    """Print next steps for the user"""
    print_header("Setup Complete!")

    print("Next steps:\n")
    print(f"{Colors.BOLD}1. Activate the virtual environment:{Colors.END}")
    print(f"   {Colors.GREEN}source venv/bin/activate{Colors.END}\n")

    print(f"{Colors.BOLD}2. Set REQUIRED environment variable:{Colors.END}")
    print(f"   {Colors.GREEN}# Choose which Atlassian product to fetch:{Colors.END}")
    print(
        f'   {Colors.GREEN}export ATLAS_MD_BASE_URL="https://support.atlassian.com/confluence-cloud"{Colors.END}'
    )
    print(
        f"   {Colors.GREEN}# Valid options: jira-software-cloud, confluence-cloud, trello, etc.{Colors.END}"
    )
    print(f"   {Colors.GREEN}# Add to ~/.zshrc or ~/.bashrc and run: source ~/.zshrc{Colors.END}\n")

    print(f"{Colors.BOLD}3. Run Atlas Markdown:{Colors.END}")
    print(f"   {Colors.GREEN}./run.sh{Colors.END}")
    print(f"   {Colors.GREEN}# or: python -m atlas_markdown.cli --help{Colors.END}")
    print(f"   {Colors.GREEN}# or: python -m atlas_markdown.cli --output ./docs{Colors.END}\n")

    print(f"{Colors.BOLD}4. Run tests:{Colors.END}")
    print(f"   {Colors.GREEN}pytest tests/{Colors.END}\n")

    print(f"{Colors.YELLOW}For more information, see README.md{Colors.END}")


def main() -> None:
    """Main initialization function"""
    print_header("Atlas Markdown Setup")

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
        verify_main_script()
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
