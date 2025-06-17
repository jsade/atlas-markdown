#!/usr/bin/env python3
"""
Standalone markdown linter for already scraped documentation.
Can be run independently to lint and fix markdown files.
"""

import logging
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler

from atlas_markdown.utils.markdown_linter import MarkdownLinter

console = Console()


def setup_logging(verbose: bool) -> None:
    """Configure logging with Rich handler"""
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@click.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option("--fix", is_flag=True, help="Fix issues in place")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--report", "-r", type=click.Path(), help="Save report to file")
def lint(directory: str, fix: bool, verbose: bool, report: str | None) -> None:
    """Lint markdown files in DIRECTORY and optionally fix issues."""

    setup_logging(verbose)

    console.print("\n[bold blue]Markdown Linter[/bold blue]")
    console.print(f"[dim]Directory: {directory}[/dim]")
    console.print(f"[dim]Auto-fix: {'Yes' if fix else 'No'}[/dim]\n")

    # Create linter
    linter = MarkdownLinter(auto_fix=fix)

    # Run linting
    console.print("[blue]Scanning markdown files...[/blue]")
    issues = linter.lint_directory(Path(directory), fix_in_place=fix)

    # Display results
    if issues:
        console.print(f"\n[yellow]Found issues in {len(issues)} files[/yellow]")

        if fix:
            console.print("[green]All issues have been fixed![/green]")
        else:
            console.print("[dim]Run with --fix to automatically fix these issues[/dim]")

        # Generate report
        report_content = linter.generate_report(issues)

        if report:
            # Save to file
            with open(report, "w", encoding="utf-8") as f:
                f.write(report_content)
            console.print(f"\n[green]Report saved to: {report}[/green]")
        else:
            # Show summary
            console.print("\n[bold]Summary by issue type:[/bold]")
            issue_types: dict[str, int] = {}
            for file_issues in issues.values():
                for issue in file_issues:
                    issue_types[issue.issue_type] = issue_types.get(issue.issue_type, 0) + 1

            for issue_type, count in sorted(issue_types.items(), key=lambda x: x[1], reverse=True):
                console.print(f"  - {issue_type}: {count}")

            if verbose:
                # Show first few files with issues
                console.print("\n[bold]Files with issues (first 10):[/bold]")
                for i, (file_path, file_issues) in enumerate(list(issues.items())[:10]):
                    console.print(f"\n[cyan]{file_path}[/cyan]")
                    for issue in file_issues[:3]:
                        console.print(f"  Line {issue.line_number}: {issue.description}")
                    if len(file_issues) > 3:
                        console.print(f"  ... and {len(file_issues) - 3} more")
                    if i >= 9 and len(issues) > 10:
                        console.print(f"\n... and {len(issues) - 10} more files")
    else:
        console.print("[green]No linting issues found![/green]")


if __name__ == "__main__":
    lint()
