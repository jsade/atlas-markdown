## Development

### Manual Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium
```

### Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest --cov=src tests/

# Run specific test
pytest tests/test_content_parser.py -v
```

### Code Quality

```bash
# Linting
ruff check .
black --check .

# Auto-format
black .
ruff check . --fix

# Run pre-commit hooks manually
pre-commit run --all-files
```

### Conventional Commits & Semantic Releases

This project uses [Conventional Commits](https://www.conventionalcommits.org/) and automated semantic versioning.

#### Setup

```bash
# Install development dependencies (includes commitizen and pre-commit)
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Verify commitizen is working
cz version
```

#### Making Commits

Use commitizen for interactive commit creation:

```bash
# Interactive commit (recommended)
cz commit

# Or use conventional format manually:
# git commit -m "type(scope): subject"
```

**Commit Types:**
- `feat`: New feature (minor version bump)
- `fix`: Bug fix (patch version bump)
- `docs`: Documentation changes
- `style`: Code style changes (formatting, missing semicolons, etc)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `build`: Build system changes
- `ci`: CI/CD changes
- `chore`: Other changes that don't modify src or test files

**Breaking Changes:**
Add `BREAKING CHANGE:` in the commit body or footer to trigger a major version bump.

#### Version Management

> [!IMPORTANT]
> - Do not use `cz bump` or `cz changelog` - all versioning and changelog generation is handled by semantic-release
> - Use `cz commit` for creating properly formatted commit messages
> - Semantic-release automatically manages versions, changelogs, and releases in CI/CD

```bash
# Check current version
cz version --project

# Create conventional commits interactively
cz commit
```

#### Semantic Release Dry-Run

Before pushing to main, you can preview what the semantic release will do:

```bash
# Check what version would be released
semantic-release version --print
# Note: You'll see a "Token value is missing!" warning - this is normal for local runs

# See what would happen without making changes (simplified in v10.x)
semantic-release version --print --noop

# Check the last released version
semantic-release version --print-last-released
```

##### About the Token Warning

The "Token value is missing!" warning appears because semantic-release looks for a GitHub token to authenticate API requests. This token is:

- **Not needed** for local dry-runs with `--print`
- **Only required** for actual releases (creating tags, pushing commits, creating GitHub releases)
- **Automatically provided** in GitHub Actions via `GITHUB_TOKEN`

The token would need these permissions if used:
- `repo` - Full repository access
- `write:packages` - If publishing packages
- `workflow` - If updating GitHub Actions files

For local development, you can safely ignore this warning when using `--print` flags.

The project also includes a GitHub Actions workflow for dry-runs on pull requests. This automatically shows what version would be released when the PR is merged.

#### Tool Responsibilities

**Commitizen is used for:**
- Creating conventional commits (`cz commit`)
- Checking current project version (`cz version --project`)
- Nothing else - no bumping, no changelog generation

**Semantic-release handles:**
- All version bumping (based on commit types)
- Changelog generation and updates
- Creating git tags
- Creating GitHub releases
- Updating both `[project]` and `[tool.commitizen]` version fields

##### Semantic Release v10.x Features

The project uses python-semantic-release v10.x which includes:
- Enhanced commit parsing with squash commit support
- Improved security and performance
- Better merge commit handling
- Stricter validation with `--strict` flag for CI/CD
- Simplified dry-run with `--noop` flag

#### Automated Releases

When you push to the `main` branch, GitHub Actions will:
1. Analyze commits since last release
2. Determine version bump (major/minor/patch)
3. Update version in `pyproject.toml` (both project and commitizen sections)
4. Generate/update CHANGELOG.md
5. Create GitHub release with assets
6. Tag the release

The workflow uses Python Semantic Release v10.x for pure Python compatibility.

> [!TIP]
> For stricter validation in CI/CD, consider adding the `--strict` flag to semantic-release commands in GitHub Actions workflows. This ensures releases fail fast on configuration or parsing errors.
