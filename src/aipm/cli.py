"""
AIPM CLI - Command-line interface for AI Project Manager
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from aipm.core.engine import PromptSystem, Prompt, PromptCategory
from aipm.project.manager import ProjectManager, TaskPriority


console = Console()


@click.group()
@click.version_option(version="0.1.0")
def main():
    """AIPM - AI Project Manager"""
    pass


@main.group()
def project():
    """Project management commands"""
    pass


@project.command("create")
@click.option("--name", "-n", required=True, help="Project name")
@click.option("--goal", "-g", required=True, help="Project goal")
@click.option("--path", "-p", type=click.Path(), help="Project path")
def project_create(name: str, goal: str, path: Optional[str]):
    """Create a new project"""
    pm = ProjectManager()
    
    project = pm.create_project(
        name=name,
        goal=goal,
        path=Path(path) if path else None,
    )
    
    console.print(Panel(
        f"[green]✓[/green] Project created: {project.id}\n"
        f"Name: {project.name}\n"
        f"Goal: {project.goal}",
        title="Project Created",
        border_style="green",
    ))


@project.command("list")
def project_list():
    """List all projects"""
    pm = ProjectManager()
    projects = pm.list_projects()
    
    table = Table(title="Projects")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Goal", style="white")
    table.add_column("Completion", style="yellow")
    
    for p in projects:
        stats = pm.get_project_stats(p.id)
        table.add_row(
            p.id,
            p.name,
            p.goal[:40] + "..." if len(p.goal) > 40 else p.goal,
            f"{stats['completion_percentage']:.1f}%",
        )
    
    console.print(table)


@project.command("show")
@click.argument("project_id")
def project_show(project_id: str):
    """Show project details"""
    pm = ProjectManager()
    project = pm.get_project(project_id)
    
    if not project:
        console.print(f"[red]Project not found: {project_id}[/red]")
        return
    
    stats = pm.get_project_stats(project_id)
    tasks = pm.get_project_tasks(project_id)
    
    console.print(Panel(
        f"[bold]{project.name}[/bold]\n"
        f"Goal: {project.goal}\n"
        f"Path: {project.path or 'Not set'}\n"
        f"\n"
        f"Tasks: {stats['total_tasks']}\n"
        f"Completed: {stats['completed']}\n"
        f"Pending: {stats['pending']}\n"
        f"In Progress: {stats['in_progress']}\n"
        f"Blocked: {stats['blocked']}\n"
        f"\n"
        f"Completion: {stats['completion_percentage']:.1f}%",
        title=f"Project: {project_id}",
        border_style="cyan",
    ))
    
    if tasks:
        task_table = Table(title="Tasks")
        task_table.add_column("ID", style="dim")
        task_table.add_column("Name", style="white")
        task_table.add_column("Status", style="yellow")
        task_table.add_column("Priority", style="red")
        
        for t in tasks[:10]:
            task_table.add_row(t.id, t.name[:30], t.status.value, t.priority.value)
        
        console.print(task_table)


@main.group()
def task():
    """Task management commands"""
    pass


@task.command("add")
@click.argument("project_id")
@click.option("--name", "-n", required=True, help="Task name")
@click.option("--description", "-d", default="", help="Task description")
@click.option("--priority", "-p", type=click.Choice(["critical", "high", "medium", "low"]), default="medium")
def task_add(project_id: str, name: str, description: str, priority: str):
    """Add a task to a project"""
    pm = ProjectManager()
    task = pm.add_task(
        project_id=project_id,
        name=name,
        description=description,
        priority=TaskPriority(priority),
    )
    
    console.print(f"[green]✓[/green] Task created: {task.id}")


@main.group()
def process():
    """Prompt processing commands"""
    pass


@process.command("next")
def process_next():
    """Process the next prompt"""
    system = PromptSystem()
    result = asyncio.run(system.process_next())
    console.print_json(json.dumps(result, indent=2))


@process.command("forever")
@click.option("--interval", "-i", default=60, help="Interval in seconds")
def process_forever(interval: int):
    """Run the processing loop forever"""
    system = PromptSystem()
    console.print(f"[cyan]Starting processing loop (interval: {interval}s)[/cyan]")
    asyncio.run(system.run_forever(interval=interval))


@process.command("status")
def process_status():
    """Show queue status"""
    system = PromptSystem()
    stats = system.queue.get_stats()
    
    table = Table(title="Queue Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Total", str(stats["total"]))
    table.add_row("Pending", str(stats["pending"]))
    table.add_row("Completed Today", str(stats["completed_today"]))
    
    for status, count in stats["by_status"].items():
        table.add_row(f"  {status}", str(count))
    
    console.print(table)


@main.command()
@click.argument("text")
@click.option("--category", "-c", default="code_gen", help="Prompt category")
@click.option("--priority", "-p", default=5, help="Priority (1-10)")
def prompt(text: str, category: str, priority: int):
    """Add a prompt to the queue"""
    system = PromptSystem()
    
    prompt = Prompt(
        id=f"prompt_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        text=text,
        category=PromptCategory(category),
        priority=priority,
    )
    
    system.add_prompt(prompt)
    console.print(f"[green]✓[/green] Prompt added: {prompt.id}")


@main.command()
@click.option("--port", "-p", default=8080, help="Server port")
def serve(port: int):
    """Start the API server"""
    from aipm.api.server import APIServer
    
    server = APIServer(port=port)
    asyncio.run(server.run())


@main.command()
def status():
    """Show system status"""
    system = PromptSystem()
    pm = ProjectManager()
    
    # Queue stats
    stats = system.queue.get_stats()
    
    # Projects
    projects = pm.list_projects()
    
    console.print(Panel(
        f"[bold cyan]Queue[/bold cyan]\n"
        f"  Total: {stats['total']}\n"
        f"  Pending: {stats['pending']}\n"
        f"  Completed Today: {stats['completed_today']}\n"
        f"\n"
        f"[bold cyan]Projects[/bold cyan]\n"
        f"  Total: {len(projects)}",
        title="AIPM Status",
        border_style="cyan",
    ))


@main.command()
@click.option("--port", "-p", default=8080, help="Port to serve on")
def dashboard(port: int):
    """Start the ASCII dashboard server"""
    from aipm.ascii_world.dashboard import Dashboard
    
    dashboard = Dashboard()
    
    async def serve_dashboard():
        from aiohttp import web
        
        app = web.Application()
        
        async def handle(request):
            return web.Response(text=dashboard.render(), content_type="text/plain")
        
        app.router.add_get("/", handle)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", port)
        await site.start()
        
        console.print(f"[green]Dashboard serving at http://localhost:{port}[/green]")
        
        while True:
            await asyncio.sleep(3600)
    
    asyncio.run(serve_dashboard())


if __name__ == "__main__":
    main()
