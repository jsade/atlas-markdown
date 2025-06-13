#!/usr/bin/env python3
"""
Atlassian Documentation Scraper
Main entry point for the command-line tool
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from src.parsers.content_parser import ContentParser
from src.parsers.initial_state_parser import InitialStateParser
from src.parsers.link_resolver import LinkResolver
from src.parsers.sitemap_parser import SitemapParser
from src.scrapers.crawler import DocumentationCrawler
from src.utils.file_manager import FileSystemManager
from src.utils.health_monitor import CircuitBreaker, HealthMonitor
from src.utils.image_downloader import ImageDownloader
from src.utils.markdown_linter import MarkdownLinter
from src.utils.rate_limiter import RateLimiter, RetryConfig, ThrottledScraper
from src.utils.redirect_handler import RedirectHandler

# Import our modules
from src.utils.state_manager import PageStatus, StateManager

# Load environment variables
load_dotenv()

console = Console()


def validate_environment():
    """Validate required environment variables with robust error handling"""
    required_vars = {
        "BASE_URL": "https://support.atlassian.com/jira-service-management-cloud",
        "OUTPUT_DIR": "./output",
        "WORKERS": "5",
        "REQUEST_DELAY": "1.5",
        "USER_AGENT": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "LOG_LEVEL": "INFO",
    }

    env_config = {}
    missing_vars = []
    invalid_vars = []

    for var, default in required_vars.items():
        value = os.getenv(var, default).strip()

        if not value:
            missing_vars.append(var)
            continue

        # Validate specific variable types
        if var == "WORKERS":
            try:
                value = int(value)
                if value < 1 or value > 50:
                    invalid_vars.append(f"{var} must be between 1 and 50 (got {value})")
                    value = int(default)
            except ValueError:
                invalid_vars.append(f"{var} must be an integer (got '{value}')")
                value = int(default)

        elif var == "REQUEST_DELAY":
            try:
                value = float(value)
                if value < 0.1 or value > 60:
                    invalid_vars.append(f"{var} must be between 0.1 and 60 seconds (got {value})")
                    value = float(default)
            except ValueError:
                invalid_vars.append(f"{var} must be a number (got '{value}')")
                value = float(default)

        elif var == "BASE_URL":
            # Validate URL format
            if not value.startswith(("http://", "https://")):
                invalid_vars.append(f"{var} must start with http:// or https:// (got '{value}')")
                value = default
            # Remove trailing slash for consistency
            value = value.rstrip("/")

        elif var == "LOG_LEVEL":
            valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            if value.upper() not in valid_levels:
                invalid_vars.append(f"{var} must be one of {valid_levels} (got '{value}')")
                value = default
            else:
                value = value.upper()

        env_config[var] = value

    # Report issues
    if missing_vars or invalid_vars:
        console.print("[bold red]Environment Configuration Issues:[/bold red]")

        if missing_vars:
            console.print("\n[yellow]Missing environment variables (using defaults):[/yellow]")
            for var in missing_vars:
                console.print(f"  - {var} = {required_vars[var]}")

        if invalid_vars:
            console.print("\n[red]Invalid environment variables:[/red]")
            for issue in invalid_vars:
                console.print(f"  - {issue}")

        console.print("\n[dim]Check your .env file or environment variables[/dim]")
        console.print("[dim]Example: cp .env.example .env[/dim]\n")

    return env_config


def setup_logging(verbose: bool):
    """Configure logging with Rich handler"""
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )

    # Suppress some noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)


class DocumentationScraper(ThrottledScraper):
    """Main scraper orchestrator"""

    def __init__(self, config: dict, env_config: dict):
        # Initialize configuration
        self.config = config
        self.env_config = env_config
        self.base_url = env_config["BASE_URL"]
        self.entry_point = f"{self.base_url}/resources/"

        # Initialize rate limiter
        rate_limiter = RateLimiter(rate=1.0 / config["delay"], burst=config["workers"])
        retry_config = RetryConfig(max_attempts=3, initial_delay=2.0)
        super().__init__(rate_limiter, retry_config)

        # Initialize components
        self.state_manager = StateManager()
        self.file_manager = FileSystemManager(config["output"], self.base_url)
        self.parser = ContentParser(self.base_url)
        self.initial_state_parser = InitialStateParser(self.base_url)
        self.link_resolver = LinkResolver(self.base_url)
        self.redirect_handler = RedirectHandler()
        self.health_monitor = HealthMonitor(config["output"])
        self.circuit_breaker = CircuitBreaker(failure_threshold=10, recovery_timeout=300)
        self.logger = logging.getLogger(__name__)
        self.failed_pages_count = 0
        self.max_consecutive_failures = 20
        self.max_retry_attempts = 3
        self.retry_delay_minutes = 5
        self.site_hierarchy = None  # Will be populated from initial state
        self.create_redirect_stubs = config.get("create_redirect_stubs", False)

    async def run(self):
        """Main scraping workflow with health monitoring"""
        try:
            async with self.state_manager:
                # Initial health check
                health = await self.health_monitor.check_system_health()
                if not health["healthy"]:
                    console.print("[red]System health check failed:[/red]")
                    for check, status in health["checks"].items():
                        if not status.get("healthy", False):
                            console.print(f"  - {check}: {status.get('message', 'Unknown error')}")

                    if not click.confirm("Continue anyway?"):
                        return

                # Start a new run
                run_id = await self.state_manager.start_run()

                # Load existing URL mappings for link resolution
                await self.link_resolver.load_from_state_manager(self.state_manager)
                self.logger.info(
                    f"Link resolver loaded with {self.link_resolver.get_stats()['url_mappings']} mappings"
                )

                # Start health monitoring task
                health_task = asyncio.create_task(self._periodic_health_check())

                try:
                    # Reset any in-progress pages if resuming
                    if self.config["resume"]:
                        await self.state_manager.reset_in_progress()
                        console.print("[yellow]Resuming from previous state...[/yellow]")
                    else:
                        # Clear previous state for fresh run
                        await self.state_manager.clear_all()
                        console.print("[green]Starting fresh scrape...[/green]")

                    # Phase 1: Discover pages
                    if not self.config["dry_run"]:
                        await self.discover_pages()
                    else:
                        console.print("[yellow]Dry run - skipping discovery[/yellow]")

                    # Phase 2: Scrape pages
                    await self.scrape_pages()

                    # Phase 3: Download images
                    if not self.config["dry_run"]:
                        await self.download_images()

                    # Phase 4: Final retry for failed pages
                    if not self.config["dry_run"]:
                        await self.retry_failed_pages()

                    # Phase 5: Generate index
                    await self.generate_index()

                    # Phase 6: Fix all wiki links with proper filenames
                    if not self.config["dry_run"]:
                        await self.fix_wiki_links()

                    # Phase 7: Lint all markdown files
                    if not self.config["dry_run"] and self.config.get("lint", True):
                        await self.lint_markdown_files()

                    # Complete the run
                    await self.state_manager.complete_run(run_id)

                finally:
                    # Stop health monitoring
                    health_task.cancel()
                    try:
                        await health_task
                    except asyncio.CancelledError:
                        pass

                # Show final statistics
                await self.show_statistics()

        except asyncio.CancelledError:
            console.print("\n[yellow]Scraping cancelled, saving state...[/yellow]")
            await self.state_manager.reset_in_progress()
            raise
        except Exception as e:
            self.logger.error(f"Fatal error in scraper: {e}", exc_info=True)
            raise

    async def _periodic_health_check(self):
        """Periodically check system health"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                health = await self.health_monitor.check_system_health()

                if not health["healthy"]:
                    self.logger.warning("Health check failed")
                    for warning in health["warnings"]:
                        self.logger.warning(f"Health warning: {warning}")

                    # Reduce workers if memory is low
                    if not health["checks"]["memory"]["healthy"]:
                        new_workers = max(1, self.config["workers"] // 2)
                        if new_workers < self.config["workers"]:
                            self.config["workers"] = new_workers
                            self.logger.warning(
                                f"Reduced workers to {new_workers} due to low memory"
                            )

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Health check error: {e}")

    async def discover_pages(self):
        """Load all documentation pages from initial state or sitemap"""
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Discovering pages...", total=None)

            # First try to load from initial state
            try:
                progress.update(task, description="Loading initial state...")

                # Fetch the entry point page to get initial state
                async with DocumentationCrawler(self.base_url) as crawler:
                    await crawler.page.goto(self.entry_point, wait_until="networkidle")
                    html = await crawler.page.content()

                # Extract hierarchy from initial state
                self.site_hierarchy = self.initial_state_parser.extract_full_hierarchy(html)

                if self.site_hierarchy and self.site_hierarchy["total_pages"] > 0:
                    console.print(
                        f"[green]Found {self.site_hierarchy['total_pages']} pages from initial state[/green]"
                    )

                    # Add all discovered pages to state manager
                    for url, page_info in self.site_hierarchy["flat_map"].items():
                        # Only add URLs within our base URL
                        if url.startswith(self.base_url):
                            await self.state_manager.add_page(url, title=page_info.get("title"))

                    progress.update(task, completed=self.site_hierarchy["total_pages"])
                    return

            except Exception as e:
                self.logger.warning(f"Failed to extract from initial state: {e}")

            # Fallback to sitemap parser
            progress.update(task, description="Loading pages from sitemap...")
            sitemap_parser = SitemapParser(self.base_url)
            pages = await sitemap_parser.get_all_urls(
                include_resources=self.config.get("include_resources", False)
            )

            # Sort pages by priority for better scraping order
            pages_with_priority = [(url, sitemap_parser.get_url_priority(url)) for url in pages]
            pages_with_priority.sort(key=lambda x: x[1])
            sorted_pages = [url for url, _ in pages_with_priority]

            # Add pages to state manager
            for url in sorted_pages:
                await self.state_manager.add_page(url)

            progress.update(task, completed=len(pages))
            console.print(f"[green]Loaded {len(pages)} pages from sitemap[/green]")

    async def scrape_pages(self):
        """Scrape all pending pages"""
        # Get pending pages (excluding recent failures)
        all_pending = await self.state_manager.get_pending_pages()

        # Filter out pages that failed recently and need delay
        pending = []
        for page in all_pending:
            if page.get("retry_count", 0) == 0:
                # First attempt, include it
                pending.append(page)
            else:
                # Check if it's been long enough since last attempt
                # This is a simple check, the state manager handles the actual timing
                pending.append(page)

        if not pending:
            console.print("[yellow]No pages to scrape[/yellow]")
            return

        console.print(f"[blue]Scraping {len(pending)} pages...[/blue]")

        # Create progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Scraping pages", total=len(pending))

            # Process pages with worker pool
            semaphore = asyncio.Semaphore(self.config["workers"])

            async def process_page(page_info):
                async with semaphore:
                    url = page_info["url"]
                    await self.scrape_single_page(url)
                    progress.update(task, advance=1)

            # Create tasks for all pages
            tasks = [process_page(page) for page in pending]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def scrape_single_page(self, url: str):
        """Scrape a single page with circuit breaker"""
        # Check circuit breaker
        if not self.circuit_breaker.can_attempt():
            self.logger.warning(f"Circuit breaker open, skipping {url}")
            await self.state_manager.update_page_status(
                url, PageStatus.FAILED, error_message="Circuit breaker open"
            )
            return

        try:
            # Update status to in progress
            await self.state_manager.update_page_status(url, PageStatus.IN_PROGRESS)

            # Rate limit the request
            await self.rate_limiter.acquire()

            # Scrape the page with retry
            async def scrape_with_browser_and_extract():
                async with DocumentationCrawler(self.base_url) as crawler:
                    # Navigate to page
                    await crawler.page.goto(url, wait_until="networkidle")

                    # Check for redirects
                    final_url = crawler.page.url
                    if final_url != url:
                        self.logger.info(f"Redirect detected: {url} -> {final_url}")
                        self.redirect_handler.add_redirect(url, final_url)

                        # Check if we've already scraped the final URL
                        final_status = await self.state_manager.get_page_status(final_url)
                        if final_status == PageStatus.COMPLETED.value:
                            self.logger.info(f"Redirect target already scraped: {final_url}")

                            # Get the file path of the already scraped page
                            canonical_file = self.redirect_handler.get_canonical_file(final_url)
                            if not canonical_file:
                                # Look it up from the state manager
                                cursor = await self.state_manager._db.execute(
                                    "SELECT file_path FROM pages WHERE url = ?", (final_url,)
                                )
                                row = await cursor.fetchone()
                                if row and row["file_path"]:
                                    canonical_file = row["file_path"]
                                    self.redirect_handler.add_final_url(final_url, canonical_file)

                            # Skip scraping this page - it's a duplicate
                            return None, None, None, None, final_url, canonical_file

                    # Extract content using the page object (handles "Show more")
                    extract_result = await self.parser.extract_main_content_from_page(
                        crawler.page, final_url or url
                    )
                    content_html, title, sibling_info = extract_result

                    # Get updated HTML after any interactions
                    html = await crawler.page.content()

                    # Check if we got meaningful content
                    if not content_html or len(html) < 1000:
                        raise ValueError(f"Page too small or no content found: {len(html)} bytes")

                    return content_html, title, sibling_info, html, final_url, None

            # Use retry logic for browser operations
            result = await self.throttled_request(scrape_with_browser_and_extract)
            content_html, title, sibling_info, html, final_url, canonical_file = result

            # Check if this was a redirect to already scraped content
            if content_html is None and canonical_file:
                self.logger.info(f"Skipping duplicate from redirect: {url}")

                # Update link resolver to map both URLs to the same file
                self.link_resolver.add_page_mapping(url, title or "Redirected page", canonical_file)

                # Optionally create a redirect stub file
                if self.create_redirect_stubs:
                    redirect_content = self.redirect_handler.create_redirect_markdown(
                        url, final_url, canonical_file
                    )
                    stub_path = await self.file_manager.save_content(url, redirect_content)
                    await self.state_manager.update_page_status(
                        url, PageStatus.COMPLETED, file_path=stub_path
                    )
                else:
                    # Mark as completed without creating a file
                    await self.state_manager.update_page_status(
                        url, PageStatus.COMPLETED, file_path=canonical_file
                    )

                # Reset failure counter on success
                self.circuit_breaker.record_success()
                self.failed_pages_count = 0
                return

            if not content_html:
                raise ValueError("No content found")

            # Get page metadata from initial state if available
            page_metadata = None
            if self.site_hierarchy:
                page_metadata = self.initial_state_parser.get_page_metadata(url)

            # Convert to markdown with metadata
            markdown = self.parser.convert_to_markdown(content_html, url, title, page_metadata)

            # Save to file system with sibling info for proper folder structure
            # Use the final URL (after redirects) for saving content
            save_url = final_url or url
            file_path = await self.file_manager.save_content(save_url, markdown, sibling_info)

            # Update page title if we found one
            if title:
                await self.state_manager._db.execute(
                    "UPDATE pages SET title = ? WHERE url = ?", (title, save_url)
                )
                await self.state_manager._db.commit()

            # Mark as completed
            await self.state_manager.update_page_status(
                save_url, PageStatus.COMPLETED, file_path=file_path
            )

            # Add URL to filename mapping for link resolution
            self.link_resolver.add_page_mapping(save_url, title, file_path)

            # Track the final URL in redirect handler
            self.redirect_handler.add_final_url(save_url, file_path)

            # If this was accessed via redirect, also update the original URL
            if final_url and final_url != url:
                # Map the redirect URL to the same file
                self.link_resolver.add_page_mapping(url, title, file_path)

                # Optionally create a redirect stub for the original URL
                if self.create_redirect_stubs:
                    redirect_content = self.redirect_handler.create_redirect_markdown(
                        url, final_url, file_path
                    )
                    stub_path = await self.file_manager.save_content(url, redirect_content)
                    await self.state_manager.update_page_status(
                        url, PageStatus.COMPLETED, file_path=stub_path
                    )
                else:
                    # Mark original URL as completed pointing to same file
                    await self.state_manager.update_page_status(
                        url, PageStatus.COMPLETED, file_path=file_path
                    )

            # Track images for later download
            images = self.parser.get_images()
            for img_url in images:
                await self.state_manager.add_image(img_url, url)

            # Extract navigation links for discovery
            nav_links = self.parser.get_navigation_links(html)
            for link in nav_links:
                # Only add links within our base URL
                if link.startswith(self.base_url):
                    await self.state_manager.add_page(link)

            self.logger.info(f"Successfully scraped: {url}")

            # Record success in circuit breaker
            self.circuit_breaker.record_success()
            self.failed_pages_count = 0  # Reset consecutive failures

        except asyncio.TimeoutError:
            error_msg = "Timeout while scraping page"
            self.logger.error(f"{error_msg}: {url}")
            await self.state_manager.update_page_status(
                url, PageStatus.FAILED, error_message=error_msg
            )
            self.circuit_breaker.record_failure()
            self.failed_pages_count += 1

        except Exception as e:
            self.logger.error(f"Failed to scrape {url}: {str(e)}")
            await self.state_manager.update_page_status(
                url, PageStatus.FAILED, error_message=str(e)
            )
            self.circuit_breaker.record_failure()
            self.failed_pages_count += 1

            # Check if too many consecutive failures
            if self.failed_pages_count >= self.max_consecutive_failures:
                self.logger.error(
                    f"Too many consecutive failures ({self.failed_pages_count}), stopping"
                )
                raise RuntimeError("Too many consecutive page failures") from e

    async def download_images(self):
        """Download all images"""
        # Get pending images
        pending_images = await self.state_manager.get_pending_images()

        if not pending_images:
            console.print("[yellow]No images to download[/yellow]")
            return

        console.print(f"[blue]Downloading {len(pending_images)} images...[/blue]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Downloading images", total=len(pending_images))

            async with ImageDownloader(self.config["output"], self.base_url) as downloader:
                for img_info in pending_images:
                    img_url = img_info["url"]
                    page_url = img_info["page_url"]

                    success, local_path, error = await downloader.download_image(img_url, page_url)

                    if success:
                        await self.state_manager.update_image(
                            img_url, local_path=local_path, downloaded=True
                        )
                    else:
                        await self.state_manager.update_image(img_url, error_message=error)

                    progress.update(task, advance=1)

                # Update markdown files with local image paths
                await self.update_image_references(downloader.get_all_mappings())

    async def update_image_references(self, image_map: dict):
        """Update image references in markdown files"""
        # Get all completed pages
        cursor = await self.state_manager._db.execute(
            "SELECT url, file_path FROM pages WHERE status = ?", (PageStatus.COMPLETED.value,)
        )
        pages = await cursor.fetchall()

        for page in pages:
            if not page["file_path"]:
                continue

            file_path = self.file_manager.output_dir / page["file_path"]

            try:
                # Read markdown content
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()

                # Update image references
                updated_content = self.parser.update_image_references(content, image_map)

                # Write back if changed
                if content != updated_content:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(updated_content)

            except Exception as e:
                self.logger.error(f"Failed to update images in {file_path}: {e}")

    async def retry_failed_pages(self):
        """Final retry attempt for all failed pages"""
        # Get failed pages that haven't exceeded max retries
        failed_pages = await self.state_manager.get_failed_pages_for_retry(self.max_retry_attempts)

        if not failed_pages:
            console.print("[yellow]No failed pages to retry[/yellow]")
            return

        console.print(
            f"\n[bold yellow]Final retry phase - "
            f"attempting {len(failed_pages)} failed pages[/bold yellow]"
        )

        # Reset circuit breaker for final attempt
        self.circuit_breaker.reset()

        # Create progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Retrying failed pages", total=len(failed_pages))

            # Process failed pages with reduced concurrency
            retry_workers = max(1, self.config["workers"] // 2)
            semaphore = asyncio.Semaphore(retry_workers)

            async def retry_page(page_info):
                async with semaphore:
                    url = page_info["url"]
                    retry_count = page_info.get("retry_count", 0)

                    # Add exponential backoff based on retry count
                    backoff_delay = min(30, 2**retry_count)
                    await asyncio.sleep(backoff_delay)

                    console.print(
                        f"[yellow]Retrying ({retry_count + 1}/"
                        f"{self.max_retry_attempts}): {url}[/yellow]"
                    )

                    # Reset to pending for retry
                    await self.state_manager.reset_for_retry(url)

                    # Try to scrape again
                    await self.scrape_single_page(url)
                    progress.update(task, advance=1)

            # Create tasks for all failed pages
            tasks = [retry_page(page) for page in failed_pages]
            await asyncio.gather(*tasks, return_exceptions=True)

        # Show results
        final_failed = await self.state_manager.get_failed_pages()
        if final_failed:
            console.print(f"\n[red]Still failed after retry: {len(final_failed)} pages[/red]")
        else:
            console.print("\n[green]All retry attempts successful![/green]")

    async def generate_index(self):
        """Generate index file"""
        console.print("[blue]Generating index...[/blue]")

        # Get all pages
        cursor = await self.state_manager._db.execute(
            "SELECT url, title, file_path, status FROM pages ORDER BY url"
        )
        pages = await cursor.fetchall()

        # Generate index
        index_path = await self.file_manager.create_index([dict(p) for p in pages])
        console.print(f"[green]Generated index: {index_path}[/green]")

    async def fix_wiki_links(self):
        """Fix all wiki links to use proper filenames"""
        console.print("\n[blue]Fixing wiki links...[/blue]")

        # Reload mappings to ensure we have all pages
        await self.link_resolver.load_from_state_manager(self.state_manager)

        # Get all completed pages
        cursor = await self.state_manager._db.execute(
            "SELECT url, file_path FROM pages WHERE status = ?", (PageStatus.COMPLETED.value,)
        )
        pages = await cursor.fetchall()

        fixed_count = 0
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Fixing wiki links", total=len(pages))

            for page in pages:
                if not page["file_path"]:
                    progress.update(task, advance=1)
                    continue

                file_path = self.file_manager.output_dir / page["file_path"]
                page_url = page["url"]

                try:
                    # Read file content
                    with open(file_path, encoding="utf-8") as f:
                        content = f.read()

                    # Fix wiki links using the resolver
                    updated_content = self.link_resolver.convert_markdown_links(content, page_url)

                    # Write back if changed
                    if content != updated_content:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(updated_content)
                        fixed_count += 1

                except Exception as e:
                    self.logger.error(f"Failed to fix links in {file_path}: {e}")

                progress.update(task, advance=1)

        if fixed_count > 0:
            console.print(f"[green]Fixed wiki links in {fixed_count} files[/green]")
        else:
            console.print("[yellow]No wiki links needed fixing[/yellow]")

    async def lint_markdown_files(self):
        """Lint and fix all markdown files"""
        console.print("\n[blue]Linting markdown files...[/blue]")

        linter = MarkdownLinter(auto_fix=True)
        output_path = Path(self.file_manager.output_dir)

        # Run linting with progress
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Linting markdown files...", total=None)

            # Lint all files and fix in place
            issues = await asyncio.to_thread(linter.lint_directory, output_path, fix_in_place=True)

            progress.update(task, completed=1)

        # Generate and display report
        if issues:
            report = linter.generate_report(issues)

            # Save report
            report_path = output_path / "linting_report.md"
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report)

            console.print(f"\n[yellow]Fixed issues in {len(issues)} files[/yellow]")
            console.print(f"[dim]Linting report saved to: {report_path}[/dim]")

            # Show summary of issue types
            issue_types = {}
            for file_issues in issues.values():
                for issue in file_issues:
                    issue_types[issue.issue_type] = issue_types.get(issue.issue_type, 0) + 1

            if issue_types:
                console.print("\n[bold]Issues fixed by type:[/bold]")
                for issue_type, count in sorted(
                    issue_types.items(), key=lambda x: x[1], reverse=True
                ):
                    console.print(f"  - {issue_type}: {count}")
        else:
            console.print("[green]No linting issues found![/green]")

    async def show_statistics(self):
        """Display final statistics"""
        stats = await self.state_manager.get_statistics()

        # Create statistics table
        table = Table(title="Scraping Statistics")
        table.add_column("Category", style="cyan")
        table.add_column("Total", style="white")
        table.add_column("Completed", style="green")
        table.add_column("Failed", style="red")

        table.add_row(
            "Pages",
            str(stats["pages"]["total"]),
            str(stats["pages"]["completed"]),
            str(stats["pages"]["failed"]),
        )

        table.add_row(
            "Images",
            str(stats["images"]["total"]),
            str(stats["images"]["downloaded"]),
            str(stats["images"]["failed"]),
        )

        console.print(table)

        # Show circuit breaker status
        cb_status = self.circuit_breaker.get_status()
        if cb_status["state"] != "closed":
            console.print(f"\n[yellow]Circuit breaker status: {cb_status['state']}[/yellow]")
            console.print(f"Failures: {cb_status['failure_count']}/{cb_status['threshold']}")

        # Show health status
        final_health = await self.health_monitor.check_system_health()
        console.print("\n[bold]Final System Health:[/bold]")
        for check, status in final_health["checks"].items():
            icon = "✓" if status.get("healthy", False) else "✗"
            color = "green" if status.get("healthy", False) else "red"
            console.print(
                f"  [{color}]{icon}[/{color}] {check}: {status.get('message', 'Unknown')}"
            )

        # Show failed pages if any
        if stats["pages"]["failed"] > 0:
            failed_pages = await self.state_manager.get_failed_pages()
            console.print(f"\n[red]Failed pages ({len(failed_pages)}):[/red]")
            for page in failed_pages[:10]:  # Show first 10
                console.print(f"  - {page['url']}: {page['error_message']}")
            if len(failed_pages) > 10:
                console.print(f"  ... and {len(failed_pages) - 10} more")

        # Output location
        console.print(f"\n[bold green]Output saved to: {self.file_manager.output_dir}[/bold green]")


@click.command()
@click.option(
    "--output", "-o", default=None, help="Output directory (default: from .env or ./output)"
)
@click.option(
    "--workers",
    "-w",
    default=None,
    type=int,
    help="Number of concurrent workers (default: from .env or 5)",
)
@click.option(
    "--delay",
    "-d",
    default=None,
    type=float,
    help="Delay between requests in seconds (default: from .env or 1.5)",
)
@click.option("--resume", is_flag=True, help="Resume from previous state")
@click.option("--dry-run", is_flag=True, help="Show what would be scraped without downloading")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option(
    "--include-resources",
    is_flag=True,
    default=False,
    help="Include /resources/ pages in addition to /docs/",
)
@click.option("--no-lint", is_flag=True, help="Skip markdown linting/auto-fixing phase")
@click.option(
    "--create-redirect-stubs",
    is_flag=True,
    help="Create stub files for redirected URLs (default: skip duplicates)",
)
def scrape(
    output,
    workers,
    delay,
    resume,
    dry_run,
    verbose,
    include_resources,
    no_lint,
    create_redirect_stubs,
):
    """Scrape Atlassian Jira Service Management documentation"""

    # Validate environment first
    env_config = validate_environment()

    # Setup logging with configured level
    setup_logging(verbose or env_config["LOG_LEVEL"] == "DEBUG")

    # Show banner
    console.print("\n[bold blue]Atlassian Documentation Scraper[/bold blue]")
    console.print(f"[dim]Base URL: {env_config['BASE_URL']}[/dim]")
    console.print(f"[dim]Output directory: {output or env_config['OUTPUT_DIR']}[/dim]")
    console.print(
        f"[dim]Workers: {workers or env_config['WORKERS']} | Delay: {delay or env_config['REQUEST_DELAY']}s[/dim]"
    )
    console.print(f"[dim]Include resources: {include_resources}[/dim]\n")

    if dry_run:
        console.print("[yellow]🔍 DRY RUN MODE - No files will be downloaded[/yellow]\n")

    # Create configuration, using environment defaults if not specified
    config = {
        "output": output or env_config["OUTPUT_DIR"],
        "workers": workers or env_config["WORKERS"],
        "delay": delay or env_config["REQUEST_DELAY"],
        "resume": resume,
        "dry_run": dry_run,
        "verbose": verbose,
        "include_resources": include_resources,
        "lint": not no_lint,
        "create_redirect_stubs": create_redirect_stubs,
    }

    # Run scraper
    scraper = DocumentationScraper(config, env_config)

    try:
        asyncio.run(scraper.run())
        console.print("\n[bold green]✅ Scraping completed successfully![/bold green]")
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Scraping interrupted by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]❌ Scraping failed: {e}[/bold red]")
        if verbose:
            console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    scrape()
