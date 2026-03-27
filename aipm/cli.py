"""
AIPM CLI - Command-line interface for AI Project Manager
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from aipm import AIPM, get_aipm, CTRM_DB, ENHANCED_AVAILABLE
from aipm.core.simple_bridge import SimpleQueueBridge
from aipm.config import DEFAULT_REASONING_MODEL, DEFAULT_VISION_MODEL


console = Console()


@click.group()
@click.version_option(version="0.1.0")
def main():
    """AIPM - AI Project Manager
    
    The foundation for AI-driven development.
    
    Examples:
        aipm project create -n "My App" -g "Build X"
        aipm prompt "Write code for X" -p 1
        aipm process next
        aipm serve --port 8080
    """
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
    aipm = get_aipm()
    
    project = aipm.create_project(
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
    aipm = get_aipm()
    projects = aipm.list_projects()
    
    table = Table(title="Projects")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Goal", style="white")
    table.add_column("Tasks", style="yellow")
    
    for p in projects:
        stats = aipm.projects.get_project_stats(p.id)
        table.add_row(
            p.id,
            p.name,
            p.goal[:40] + "..." if len(p.goal) > 40 else p.goal,
            str(stats.get('total_tasks', 0)),
        )
    
    console.print(table)


@project.command("show")
@click.argument("project_id")
def project_show(project_id: str):
    """Show project details"""
    aipm = get_aipm()
    project = aipm.get_project(project_id)
    
    if not project:
        console.print(f"[red]Project not found: {project_id}[/red]")
        return
    
    stats = aipm.projects.get_project_stats(project_id)
    tasks = aipm.projects.get_project_tasks(project_id)
    
    console.print(Panel(
        f"[bold]{project.name}[/bold]\n"
        f"Goal: {project.goal}\n"
        f"Path: {project.path or 'Not set'}\n"
        f"\n"
        f"Tasks: {stats['total_tasks']}\n"
        f"Completed: {stats['completed']}\n"
        f"Pending: {stats['pending']}\n"
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
    aipm = get_aipm()
    task = aipm.add_task(
        project_id=project_id,
        name=name,
        description=description,
        priority=priority,
    )
    
    console.print(f"[green]✓[/green] Task created: {task.id}")


@main.group()
def process():
    """Prompt processing commands"""
    pass


@process.command("next")
@click.option("--model", "-m", default=None, help="Model to use (default: qwen2.5-coder-7b-instruct)")
@click.option("--vision", "-v", is_flag=True, help="Use vision model (qwen/qwen3-vl-8b)")
def process_next(model: Optional[str], vision: bool):
    """Process the next prompt"""
    from aipm.config import DEFAULT_REASONING_MODEL, DEFAULT_VISION_MODEL
    
    # Select model based on flags
    if vision:
        model = model or DEFAULT_VISION_MODEL
        console.print(f"[cyan]Using vision model: {model}[/cyan]")
    else:
        model = model or DEFAULT_REASONING_MODEL
        console.print(f"[cyan]Using reasoning model: {model}[/cyan]")
    
    async def run():
        aipm = get_aipm()
        result = await aipm.process_next(provider=model)
        console.print_json(json.dumps(result, indent=2, default=str))
    
    asyncio.run(run())


@process.command("forever")
@click.option("--interval", "-i", default=60, help="Interval in seconds")
@click.option("--model", "-m", default=None, help="Model to use")
def process_forever(interval: int, model: Optional[str]):
    """Run the processing loop forever"""
    aipm = get_aipm()
    console.print(f"[cyan]Starting processing loop (interval: {interval}s)[/cyan]")
    asyncio.run(aipm.run_loop(interval=interval))


@process.command("status")
def process_status():
    """Show queue status"""
    aipm = get_aipm()
    stats = aipm.get_stats()
    
    table = Table(title="Queue Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Pending", str(stats['queue'].get('pending_count', 0)))
    table.add_row("Processing", str(stats['queue'].get('processing_count', 0)))
    table.add_row("Completed", str(stats['queue'].get('completed_count', 0)))
    table.add_row("Projects", str(stats['projects']))
    table.add_row("Data Dir", stats['data_dir'])
    table.add_row("Enhanced Mode", "Yes" if ENHANCED_AVAILABLE else "No")
    
    console.print(table)


@main.command()
@click.argument("text")
@click.option("--category", "-c", default="code_gen", help="Prompt category")
@click.option("--priority", "-p", default=5, help="Priority (1-10)")
def prompt(text: str, category: str, priority: int):
    """Add a prompt to the queue"""
    aipm = get_aipm()
    
    prompt_id = aipm.enqueue(
        prompt=text,
        priority=priority,
        source="cli",
    )
    
    console.print(f"[green]✓[/green] Prompt added: {prompt_id}")


@main.command()
@click.option("--port", "-p", default=8080, help="Server port")
def serve(port: int):
    """Start the API server"""
    console.print(f"[yellow]Starting API server on port {port}...[/yellow]")
    console.print(f"[cyan]This will integrate the full API server in a future update.[/cyan]")
    console.print(f"[dim]For now, use: python -m aipm.api.server[/dim]")


@main.command()
def status():
    """Show system status"""
    aipm = get_aipm()
    stats = aipm.get_stats()
    
    console.print(Panel(
        f"[bold cyan]Queue[/bold cyan]\n"
        f"  Total: {stats['queue'].get('total', 'N/A')}\n"
        f"  Pending: {stats['queue'].get('pending_count', 0)}\n"
        f"  Completed Today: {stats['queue'].get('completed_count', 0)}\n"
        f"\n"
        f"[bold cyan]Projects[/bold cyan]\n"
        f"  Total: {stats['projects']}\n"
        f"\n"
        f"[bold cyan]Configuration[/bold cyan]\n"
        f"  Data Dir: {stats['data_dir']}\n"
        f"  CTRM DB: {CTRM_DB}\n"
        f"  Enhanced: {'Yes' if ENHANCED_AVAILABLE else 'No'}",
        title="AIPM Status",
        border_style="cyan",
    ))


@main.command()
@click.option("--port", "-p", default=8080, help="Port to serve on")
def dashboard(port: int):
    """Start the ASCII dashboard server"""
    import asyncio
    from aiohttp import web
    
    aipm = get_aipm()
    
    async def serve_dashboard():
        app = web.Application()
        
        async def handle_ascii(request):
            return web.Response(text=aipm.get_dashboard(), content_type="text/plain")
        
        async def handle_html(request):
            return web.Response(text=aipm.get_control_center_html(), content_type="text/html")
        
        app.router.add_get("/", handle_ascii)
        app.router.add_get("/dashboard", handle_html)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", port)
        await site.start()
        
        console.print(f"[green]Dashboard serving at http://localhost:{port}[/green]")
        console.print(f"[cyan]ASCII: http://localhost:{port}/[/cyan]")
        console.print(f"[cyan]HTML: http://localhost:{port}/dashboard[/cyan]")
        
        while True:
            await asyncio.sleep(3600)
    
    asyncio.run(serve_dashboard())


@main.group()
def model():
    """LM Studio model management"""
    pass


@model.command("list")
def model_list():
    """List available models"""
    async def _list():
        bridge = SimpleQueueBridge()
        
        if not await bridge.is_available():
            console.print("[red]LM Studio is not running at http://localhost:1234[/red]")
            console.print("[yellow]Start LM Studio and ensure the server is enabled.[/yellow]")
            return
        
        models = await bridge.list_models()
        
        table = Table(title="Available Models")
        table.add_column("Status", style="cyan", width=12)
        table.add_column("Model Key", style="green")
        table.add_column("Display Name", style="white")
        
        for m in models:
            status = "✅ LOADED" if m.is_loaded else "⚪ available"
            table.add_row(status, m.key, m.display_name)
        
        console.print(table)
        
        loaded = await bridge.get_loaded_model()
        if not loaded:
            console.print("\n[yellow]No model currently loaded.[/yellow]")
            console.print("[cyan]Load a model in LM Studio GUI or use: aipm model load <model_key>[/cyan]")
    
    asyncio.run(_list())


@model.command()
@click.argument("model_key")
def load(model_key: str):
    """Load a model in LM Studio"""
    async def _load():
        bridge = SimpleQueueBridge()
        
        console.print(f"[cyan]Loading model: {model_key}[/cyan]")
        result = await bridge.load_model(model_key)
        
        if result["success"]:
            console.print(f"[green]✓ {result['message']}[/green]")
        else:
            console.print(f"[red]✗ {result['message']}[/red]")
    
    asyncio.run(_load())


@model.command()
def status():
    """Show current model status"""
    async def _status():
        bridge = SimpleQueueBridge()
        
        if not await bridge.is_available():
            console.print("[red]LM Studio is not running at http://localhost:1234[/red]")
            return
        
        loaded = await bridge.get_loaded_model()
        
        if loaded:
            console.print(f"[green]Currently loaded: {loaded}[/green]")
        else:
            console.print("[yellow]No model currently loaded[/yellow]")
            console.print("[cyan]Load a model in LM Studio GUI first, then use 'aipm process next'[/cyan]")
    
    asyncio.run(_status())


@main.group()
def loop():
    """Continuous processing loop commands"""
    pass


@loop.command("start")
@click.option("--interval", "-i", default=60, help="Seconds between prompts")
@click.option("--max", "-m", default=None, help="Maximum prompts to process")
@click.option("--project", "-p", default=None, help="Only process prompts for this project")
@click.option("--model", default=None, help="Model to use")
def loop_start(interval: int, max: Optional[int], project: Optional[str], model: Optional[str]):
    """Start the continuous processing loop"""
    import subprocess
    import os
    
    script_path = Path(__file__).parent.parent.parent / "continuous_loop.py"
    
    cmd = [
        sys.executable, str(script_path),
        "--interval", str(interval),
    ]
    
    if max:
        cmd.extend(["--max", str(max)])
    if project:
        cmd.extend(["--project", project])
    if model:
        cmd.extend(["--model", model])
    
    console.print("[cyan]Starting continuous loop...[/cyan]")
    console.print(f"  Interval: {interval}s")
    if max:
        console.print(f"  Max prompts: {max}")
    if project:
        console.print(f"  Project: {project}")
    console.print(f"  Model: {model or DEFAULT_REASONING_MODEL}")
    console.print("")
    
    # Run in foreground (Ctrl+C to stop)
    os.execvp(*cmd)


@loop.command("stop")
def loop_stop():
    """Stop the continuous loop"""
    import subprocess
    
    result = subprocess.run(
        ["pkill", "-f", "-f", "continuous_loop.py"],
        capture_output=True,
    )
    
    if result.returncode == 0:
        console.print("[green]✓ Loop stopped[/green]")
    else:
        console.print("[yellow]No running loop found[/yellow]")


@loop.command("status")
def loop_status():
    """Check if loop is running"""
    import subprocess
    
    result = subprocess.run(
        ["pgrep", "-f", "continuous_loop.py"],
        capture_output=True,
    )
    
    if result.stdout:
        console.print("[green]✓ Loop is running[/green]")
        console.print(f"  PID: {result.stdout.strip()}")
    else:
        console.print("[yellow]No loop currently running[/yellow]")
        console.print("[cyan]Start with: aipm loop start[/cyan]")


# Import and add ingest commands
from aipm.cli_ingest import ingest
main.add_command(ingest, name='ingest')

if __name__ == "__main__":
    main()
