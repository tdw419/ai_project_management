"""Command-line interface for AutoSpec."""

import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table

from autospec import __version__
from autospec.change import list_changes, ChangeStatus

console = Console()

app = typer.Typer(
    help="AutoSpec: A spec-driven development framework with autonomous experimentation loop"
)


def version_callback(value: bool):
    if value:
        typer.echo(f"AutoSpec version: {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=version_callback, is_eager=True
    ),
):
    """AutoSpec command line interface."""
    pass


@app.command()
def init(
    directory: Optional[Path] = typer.Option(
        None, help="Directory to initialize the framework in"
    ),
    force: bool = typer.Option(False, help="Overwrite existing files"),
):
    """Initialize the AutoSpec framework in a directory."""
    target_dir = directory or Path.cwd()
    openspec_dir = target_dir / "openspec"
    changes_dir = openspec_dir / "changes"
    agents_file = target_dir / "AGENTS.md"

    # Create openspec/changes directory
    changes_dir.mkdir(parents=True, exist_ok=True)
    typer.echo(f"Created directory: {changes_dir}")

    # Create AGENTS.md if it doesn't exist or if force is True
    if agents_file.exists() and not force:
        typer.echo(
            f"AGENTS.md already exists at {agents_file}. Use --force to overwrite."
        )
    else:
        agents_content = """# AI Agent Guidelines

This file provides guidelines for AI agents working on this project.

## Principles
- Follow the spec-driven development process
- Make small, incremental changes
- Run tests before and after changes
- Document decisions in the spec

## Workflow
1. Explore the codebase to understand the problem
2. Propose a change with a clear motivation
3. Implement the change following the spec
4. Run tests to verify the change works
5. Request review and merge

"""
        agents_file.write_text(agents_content)
        typer.echo(f"Created file: {agents_file}")

    typer.echo(f"Initialized AutoSpec in {target_dir}")


@app.command()
def propose(
    name: str = typer.Argument(..., help="Name of the change to propose"),
    description: Optional[str] = typer.Option(None, help="Description of the change"),
    directory: Optional[Path] = typer.Option(
        None, help="Directory containing the openspec/changes folder"
    ),
):
    """Propose a new change."""
    from .change import Change

    target_dir = directory or Path.cwd()
    changes_dir = target_dir / "openspec" / "changes"

    if not changes_dir.exists():
        typer.echo(
            f"Error: {changes_dir} does not exist. Run 'autospec init' first.", err=True
        )
        raise typer.Exit(1)

    # Generate change ID (simple timestamp-based for now)
    import datetime

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    change_id = f"{timestamp}-{name.lower().replace(' ', '-')}"

    # Create Change object and save
    change = Change(
        id=change_id,
        title=name,
        status=ChangeStatus.DRAFT,
        base_path=target_dir,
    )
    change.create_directory()
    change.save_status()

    # Create a basic spec.md file
    spec_content = f"""# {name}

## Description
{description or "No description provided."}

## Motivation
Explain why this change is needed.

## Goals
- Goal 1
- Goal 2

## Non-Goals
- Non-goal 1
- Non-goal 2

## Implementation Plan
1. Step 1
2. Step 2

## Open Questions
- Question 1
- Question 2

"""
    (change.changes_path / "spec.md").write_text(spec_content)

    typer.echo(f"Proposed change: {change_id}")
    typer.echo(f"Created directory: {change.changes_path}")
    typer.echo(f"Edit {change.changes_path / 'spec.md'} to define the change in detail.")


@app.command()
def status(
    directory: Optional[Path] = typer.Option(
        None, "--directory", "-d", help="Directory containing the openspec folder"
    ),
):
    """Show the status of all changes."""
    target_dir = directory or Path.cwd()
    changes = list_changes(target_dir)

    if not changes:
        console.print("[yellow]No changes found.[/yellow]")
        console.print(
            "[dim]Run 'autospec init' to initialize, then 'autospec propose' to create changes.[/dim]"
        )
        return

    table = Table(title="AutoSpec Changes")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("Status", style="magenta")

    status_colors = {
        ChangeStatus.DRAFT: "dim",
        ChangeStatus.PROPOSED: "yellow",
        ChangeStatus.APPROVED: "blue",
        ChangeStatus.IN_PROGRESS: "cyan",
        ChangeStatus.COMPLETED: "green",
        ChangeStatus.ARCHIVED: "dim",
    }

    for change in changes:
        color = status_colors.get(change.status, "white")
        table.add_row(
            change.id,
            change.title or "(no title)",
            f"[{color}]{change.status.value}[/{color}]",
        )

    console.print(table)


if __name__ == "__main__":
    app()
