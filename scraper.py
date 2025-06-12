#!/usr/bin/env python3
"""
Atlassian Jira Service Management Documentation Scraper
Main entry point for the command-line tool
"""

import asyncio
import logging
import sys

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from src.parsers.content_parser import ContentParser
from src.parsers.sitemap_parser import SitemapParser
from src.scrapers.crawler import DocumentationCrawler
from src.utils.file_manager import FileSystemManager
from src.utils.health_monitor import CircuitBreaker, HealthMonitor
from src.utils.image_downloader import ImageDownloader
from src.utils.rate_limiter import RateLimiter, RetryConfig, ThrottledScraper

# Import our modules
from src.utils.state_manager import PageStatus, StateManager

# Load environment variables
load_dotenv()

console = Console()


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

    def __init__(self, config: dict):
        # Initialize configuration
        self.config = config
        self.base_url = "https://support.atlassian.com/jira-service-management-cloud"
        self.entry_point = f"{self.base_url}/resources/"

        # Initialize rate limiter
        rate_limiter = RateLimiter(rate=1.0 / config["delay"], burst=config["workers"])
        retry_config = RetryConfig(max_attempts=3, initial_delay=2.0)
        super().__init__(rate_limiter, retry_config)

        # Initialize components
        self.state_manager = StateManager()
        self.file_manager = FileSystemManager(config["output"], self.base_url)
        self.parser = ContentParser(self.base_url)
        self.health_monitor = HealthMonitor(config["output"])
        self.circuit_breaker = CircuitBreaker(failure_threshold=10, recovery_timeout=300)
        self.logger = logging.getLogger(__name__)
        self.failed_pages_count = 0
        self.max_consecutive_failures = 20
        self.max_retry_attempts = 3
        self.retry_delay_minutes = 5

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
        """Load all documentation pages from sitemap"""
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Loading pages from sitemap...", total=None)

            # Use sitemap parser instead of crawler
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

                    # Extract content using the page object (handles "Show more")
                    extract_result = await self.parser.extract_main_content_from_page(
                        crawler.page, url
                    )
                    content_html, title, sibling_info = extract_result

                    # Get updated HTML after any interactions
                    html = await crawler.page.content()

                    # Check if we got meaningful content
                    if not content_html or len(html) < 1000:
                        raise ValueError(f"Page too small or no content found: {len(html)} bytes")

                    return content_html, title, sibling_info, html

            # Use retry logic for browser operations
            content_html, title, sibling_info, html = await self.throttled_request(
                scrape_with_browser_and_extract
            )

            if not content_html:
                raise ValueError("No content found")

            # Convert to markdown
            markdown = self.parser.convert_to_markdown(content_html, url, title)

            # Save to file system with sibling info for proper folder structure
            file_path = await self.file_manager.save_content(url, markdown, sibling_info)

            # Update page title if we found one
            if title:
                await self.state_manager._db.execute(
                    "UPDATE pages SET title = ? WHERE url = ?", (title, url)
                )
                await self.state_manager._db.commit()

            # Mark as completed
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
                # Add discovered links to state manager (it will handle duplicates)
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
@click.option("--output", "-o", default="./output", help="Output directory for documentation")
@click.option("--workers", "-w", default=5, type=int, help="Number of concurrent workers")
@click.option("--delay", "-d", default=1.5, type=float, help="Delay between requests in seconds")
@click.option("--resume", is_flag=True, help="Resume from previous state")
@click.option("--dry-run", is_flag=True, help="Show what would be scraped without downloading")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option(
    "--include-resources",
    is_flag=True,
    default=False,
    help="Include /resources/ pages in addition to /docs/",
)
def scrape(output, workers, delay, resume, dry_run, verbose, include_resources):
    """Scrape Atlassian Jira Service Management documentation"""

    # Setup logging
    setup_logging(verbose)

    # Show banner
    console.print("\n[bold blue]Atlassian Documentation Scraper[/bold blue]")
    console.print(f"[dim]Output directory: {output}[/dim]")
    console.print(f"[dim]Workers: {workers} | Delay: {delay}s[/dim]")
    console.print(f"[dim]Include resources: {include_resources}[/dim]\n")

    if dry_run:
        console.print("[yellow]🔍 DRY RUN MODE - No files will be downloaded[/yellow]\n")

    # Create configuration
    config = {
        "output": output,
        "workers": workers,
        "delay": delay,
        "resume": resume,
        "dry_run": dry_run,
        "verbose": verbose,
        "include_resources": include_resources,
    }

    # Run scraper
    scraper = DocumentationScraper(config)

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
