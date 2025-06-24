# Contributing to Atlas Markdown

First off, thank you for considering contributing to Atlas Markdown! It's people like you that make this tool better for everyone.

This document provides guidelines for contributing to the project. These are mostly guidelines, not rules. Use your best judgment, and feel free to propose changes to this document in a pull request.

## Table of Contents

- [Contributing to Atlas Markdown](#contributing-to-atlas-markdown)
  - [Table of Contents](#table-of-contents)
  - [Code of Conduct](#code-of-conduct)
  - [I Just Have a Question](#i-just-have-a-question)
  - [What Should I Know Before Getting Started](#what-should-i-know-before-getting-started)
    - [Project Overview](#project-overview)
    - [Design Decisions](#design-decisions)
  - [How Can I Contribute](#how-can-i-contribute)
    - [Reporting Bugs](#reporting-bugs)
      - [How to Submit a Good Bug Report](#how-to-submit-a-good-bug-report)
    - [Suggesting Enhancements](#suggesting-enhancements)
    - [Your First Code Contribution](#your-first-code-contribution)
      - [Local Development Setup](#local-development-setup)
    - [Pull Requests](#pull-requests)
      - [Pull Request Process](#pull-request-process)
  - [Development Process](#development-process)
    - [Setting Up Your Environment](#setting-up-your-environment)
    - [Code Style](#code-style)
      - [Python Style Guidelines](#python-style-guidelines)
    - [Commit Messages](#commit-messages)
    - [Testing](#testing)
      - [Writing Tests](#writing-tests)
  - [Community](#community)
    - [Getting Help](#getting-help)
    - [Recognition](#recognition)

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](../CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to [github@sadeharju.org](mailto:github@sadeharju.org).

## I Just Have a Question

> [!IMPORTANT]
> Please don't file an issue to ask a question. You'll get faster results by using the resources below.

- Read the [README.md](README.md) thoroughly - it contains detailed usage instructions and troubleshooting tips
- Check existing [Issues](https://github.com/jsade/atlas-markdown/issues) - someone might have already asked your question
- Start a [Discussion](https://github.com/jsade/atlas-markdown/discussions) for general questions and ideas

## What Should I Know Before Getting Started

### Project Overview

Atlas Markdown is a command-line tool that downloads and converts Atlassian product documentation to Markdown format. Key aspects:

- Built with Python 3.8+ for cross-platform compatibility
- Uses Playwright for handling JavaScript-rendered content
- Follows a 7-phase pipeline architecture
- Includes automatic markdown linting and formatting
- Designed for offline documentation access, particularly with Obsidian

### Design Decisions

- **Playwright over Selenium**: Better performance and reliability for modern SPAs
- **Async architecture**: Enables efficient concurrent downloads
- **SQLite for state**: Provides robust resume capability
- **Modular pipeline**: Each phase can be developed and tested independently

## How Can I Contribute

### Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates. When you create a bug report, include as many details as possible using the issue template.

#### How to Submit a Good Bug Report

Bugs are tracked as [GitHub issues](https://github.com/jsade/atlas-markdown/issues). Create an issue and provide:

- **Use a clear and descriptive title**
- **Describe the exact steps to reproduce the problem**
- **Provide specific examples** (include links to documentation pages if relevant)
- **Describe the behavior you observed and what you expected**
- **Include logs** from verbose mode (`--verbose` flag)
- **System information**:
  - OS and version
  - Python version (`python --version`)
  - Output of `pip list` in your virtual environment
  - Browser version (`playwright --version`)

### Suggesting Enhancements

Enhancement suggestions are also tracked as [GitHub issues](https://github.com/jsade/atlas-markdown/issues). When creating an enhancement suggestion:

- **Use a clear and descriptive title**
- **Provide a detailed description** of the suggested enhancement
- **Include examples** of how the enhancement would be used
- **Explain why this enhancement would be useful** to most users
- **List any alternative solutions** you've considered

### Installation Options

#### Option 1: Install from Source Archive

Download the source archive from the [latest release](https://github.com/jsade/atlas-markdown/releases/latest) (e.g., `atlas-markdown-0.1.1-source.zip`).

```bash
# 1. Extract the archive
unzip atlas-markdown-*-source.zip
cd atlas-markdown-*/

# 2. Run the initialization script
python3 init.py

# 3. Activate the virtual environment
source venv/bin/activate

# 4. Configure your scraping target
# Add to your shell profile (~/.zshrc, ~/.bashrc, etc.):
export BASE_URL="https://support.atlassian.com/jira-service-management-cloud/"

# 5. Test the environment
python utils/test_environment.py

# 6. Run the tool
atlas-markdown
```

#### Option 2: Development Installation (Recommended for Contributors)

For development or to run from the latest source code:

```bash
# 1. Clone the repository (or your fork)
git clone https://github.com/jsade/atlas-markdown.git
cd atlas-markdown

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install in editable mode with development dependencies
pip install -e ".[dev]"
pre-commit install

# 4. Install browser for web scraping
playwright install chromium

# 5. Configure your scraping target
# Add to your shell profile (~/.zshrc, ~/.bashrc, etc.):
export BASE_URL="https://support.atlassian.com/jira-service-management-cloud/"

# 6. Run the tool (changes to source code take effect immediately)
atlas-markdown --help
```

With editable installation, any changes you make to the source code are immediately reflected when running `atlas-markdown`.

**Note on Development Versions**: When you install in development mode, the version will automatically include a development suffix (e.g., `0.1.2.dev1+g1234567`) that shows:
- The base version (0.1.2)
- Number of commits since the last tag (dev1)
- Git commit hash (g1234567)
- If you have uncommitted changes, it adds `.dirty`

This helps distinguish development installations from official releases.

### Your First Code Contribution

Unsure where to begin? Look for issues labeled:

- `good first issue` - Simple issues good for beginners
- `help wanted` - Issues where we need community help
- `documentation` - Documentation improvements

#### Local Development Setup

After following the development installation above, create a branch for your feature:
```bash
git checkout -b feature/your-feature-name
```

### Pull Requests

1. **Follow the style guides** - Use the provided linting tools
2. **Write tests** - Ensure your changes are covered by tests
3. **Update documentation** - Keep README.md and docstrings current
4. **Use conventional commits** - This enables automatic versioning
5. **Keep PRs focused** - One feature/fix per PR
6. **Add yourself to contributors** - In your first PR, add yourself to the contributors list

#### Pull Request Process

1. Ensure all tests pass locally:
```bash
pytest tests/
ruff check . --fix
black .
mypy atlas_markdown/
```

2. Run a semantic release dry-run to see version impact:
```bash
semantic-release version --print
# Note: "Token value is missing!" warning is normal for local runs
```

3. Update documentation if needed
4. Submit your PR with a clear description
5. Wait for automated checks to complete
6. Address review feedback promptly

### Release Process

Our project uses automated semantic release via GitHub Actions. When changes are merged to the `main` branch:

1. **Automatic Version Bumping**: Based on conventional commit messages
   - `feat:` → minor version (0.1.0 → 0.2.0)
   - `fix:`, `perf:`, `refactor:` → patch version (0.1.0 → 0.1.1)
   - `BREAKING CHANGE:` → major version (0.1.0 → 1.0.0)

2. **Release Assets**: Each release includes:
   - **Wheel Package** (`atlas_markdown-{version}-py3-none-any.whl`): Python wheel for easy installation via pip
   - **Source Archive** (`atlas-markdown-{version}-source.zip`): Complete source code including all necessary files

3. **Automated Steps**:
   - Version update in `pyproject.toml`
   - CHANGELOG.md generation
   - Git tag creation (`v{version}`)
   - GitHub release with assets

Note: Releases are GitHub-only (no PyPI publishing currently).

## Development Process

### Setting Up Your Environment

Detailed setup instructions are in the [README.md](README.md#development). Key points:

- Use Python 3.8+ (3.10+ recommended)
- Always work in a virtual environment
- Install pre-commit hooks for automatic code formatting
- Run `utils/test_environment.py` to verify your setup

### Code Style

We use several tools to maintain code quality:

- **Black** - Code formatting (line length: 88)
- **Ruff** - Fast Python linter
- **MyPy** - Static type checking (optional but encouraged)

Run all formatters and type checking:
```bash
black .
ruff check . --fix
mypy atlas_markdown/
```

#### Python Style Guidelines

- Follow PEP 8 with Black's formatting
- Use type hints for function parameters and returns
- Write descriptive variable names
- Add docstrings to all public functions and classes
- Keep functions focused and under 50 lines when possible

### Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/) for automatic versioning. Use `cz commit` for an interactive commit helper.

Format: `type(scope): subject`

**Types:**
- `feat`: New feature (minor version bump)
- `fix`: Bug fix (patch version bump)
- `docs`: Documentation only
- `style`: Code style (formatting, missing semicolons, etc)
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `perf`: Performance improvement
- `test`: Adding or correcting tests
- `build`: Changes to build system or dependencies
- `ci`: Changes to CI configuration
- `chore`: Other changes that don't modify src or test files

**Examples:**
```
feat(parser): add support for Confluence diagrams
fix(scraper): handle rate limiting for large wikis
docs: update troubleshooting section
perf(images): implement concurrent image downloads
```

### Testing

Write tests for new functionality:

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_parser.py -v

# Run with coverage
pytest --cov=atlas_markdown tests/

# Run only fast tests
pytest -m "not slow"
```

#### Writing Tests

- Place tests in `tests/` mirroring the source structure
- Use descriptive test names: `test_parser_handles_empty_content()`
- Include both positive and negative test cases
- Mock external dependencies (network calls, file system)
- Use fixtures for common test data

## Community

### Getting Help

- **GitHub Discussions** - For questions and ideas
- **Issues** - For bugs and feature requests
- **Email** - github@sadeharju.org for sensitive matters

### Recognition

Contributors are recognized in:
- The contributors section of README.md
- GitHub's contributor graph
- Release notes for significant contributions

Thank you for contributing to make documentation more accessible! 🎉
