#!/usr/bin/env python3
"""
Fix wiki links in already scraped documentation.
Can be run independently to fix broken internal links.
"""

import asyncio
import logging
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from atlas_markdown.parsers.link_resolver import LinkResolver
from atlas_markdown.utils.state_manager import PageStatus, StateManager

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


async def fix_links(directory: Path, dry_run: bool, verbose: bool):
    """Fix wiki links in all markdown files"""

    # Initialize components
    # Look for state database in current directory first, then in output directory
    state_db = Path("scraper_state.db")
    if not state_db.exists():
        state_db = directory / "scraper_state.db"

    if not state_db.exists():
        console.print("[red]State database not found[/red]")
        console.print("Looked in current directory and output directory")
        return 1

    # Get base URL from any completed page
    state_manager = StateManager()
    state_manager.db_path = state_db
    await state_manager.__aenter__()

    try:
        # Get base URL from a completed page
        cursor = await state_manager._db.execute(
            "SELECT url FROM pages WHERE status = ? LIMIT 1", (PageStatus.COMPLETED.value,)
        )
        page = await cursor.fetchone()

        if not page:
            console.print("[red]No completed pages found in database[/red]")
            return 1

        # Extract base URL
        url = page["url"]
        if "/docs/" in url:
            base_url = url.split("/docs/")[0]
        elif "/resources/" in url:
            base_url = url.split("/resources/")[0]
        else:
            console.print(f"[red]Could not determine base URL from {url}[/red]")
            return 1

        console.print(f"[dim]Base URL: {base_url}[/dim]")

        # Initialize link resolver
        link_resolver = LinkResolver(base_url)
        await link_resolver.load_from_state_manager(state_manager)

        console.print(
            f"[green]Loaded {link_resolver.get_stats()['url_mappings']} URL mappings[/green]"
        )

        # Get all completed pages
        cursor = await state_manager._db.execute(
            "SELECT url, file_path FROM pages WHERE status = ?", (PageStatus.COMPLETED.value,)
        )
        pages = await cursor.fetchall()

        console.print(f"\n[blue]Processing {len(pages)} files...[/blue]")

        fixed_count = 0
        issues = []

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

                file_path = directory / page["file_path"]
                page_url = page["url"]

                if not file_path.exists():
                    issues.append(f"File not found: {file_path}")
                    progress.update(task, advance=1)
                    continue

                try:
                    # Read file content
                    with open(file_path, encoding="utf-8") as f:
                        content = f.read()

                    # Fix wiki links using the resolver
                    updated_content = link_resolver.convert_markdown_links(content, page_url)

                    # Check if anything changed
                    if content != updated_content:
                        if not dry_run:
                            with open(file_path, "w", encoding="utf-8") as f:
                                f.write(updated_content)

                        fixed_count += 1

                        if verbose:
                            # Find what changed
                            import difflib

                            diff = difflib.unified_diff(
                                content.splitlines(keepends=True),
                                updated_content.splitlines(keepends=True),
                                fromfile=str(file_path),
                                tofile=str(file_path),
                                n=1,
                            )
                            console.print(f"\n[cyan]Changes in {file_path.name}:[/cyan]")
                            for line in list(diff)[:10]:  # Show first 10 diff lines
                                if line.startswith("+"):
                                    console.print(f"[green]{line.rstrip()}[/green]")
                                elif line.startswith("-"):
                                    console.print(f"[red]{line.rstrip()}[/red]")

                except Exception as e:
                    issues.append(f"Error processing {file_path}: {e}")

                progress.update(task, advance=1)

        # Report results
        console.print("\n[bold]Summary:[/bold]")
        if dry_run:
            console.print(f"[yellow]DRY RUN - Would fix {fixed_count} files[/yellow]")
        else:
            console.print(f"[green]Fixed wiki links in {fixed_count} files[/green]")

        if issues:
            console.print(f"\n[red]Issues encountered ({len(issues)}):[/red]")
            for issue in issues[:10]:
                console.print(f"  - {issue}")
            if len(issues) > 10:
                console.print(f"  ... and {len(issues) - 10} more")

        return 0

    finally:
        await state_manager.__aexit__(None, None, None)


@click.command()
@click.argument(
    "directory", type=click.Path(exists=True, file_okay=False, dir_okay=True), default="./output"
)
@click.option("--dry-run", is_flag=True, help="Show what would be fixed without making changes")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed changes")
def main(directory, dry_run, verbose):
    """Fix wiki links in scraped documentation.

    DIRECTORY is the output directory containing scraped markdown files (default: ./output)
    """

    setup_logging(verbose)

    console.print("\n[bold blue]Wiki Link Fixer[/bold blue]")
    console.print(f"[dim]Directory: {directory}[/dim]")
    console.print(f"[dim]Mode: {'Dry run' if dry_run else 'Fix in place'}[/dim]\n")

    try:
        result = asyncio.run(fix_links(Path(directory), dry_run, verbose))
        exit(result)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/yellow]")
        exit(1)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        if verbose:
            console.print_exception()
        exit(1)


if __name__ == "__main__":
    main()
