#!/usr/bin/env python3
"""
AIPM Model Manager - Load/unload models in LM Studio
"""

import asyncio
import click
from rich.console import Console
from rich.table import Table

from aipm.core.simple_bridge import SimpleQueueBridge

console = Console()


@click.group()
def main():
    """AIPM Model Manager - Manage LM Studio models"""
    pass


@main.command()
def list():
    """List available models"""
    async def _list():
        bridge = SimpleQueueBridge()
        
        if not await bridge.is_available():
            console.print("[red]LM Studio is not running[/red]")
            return
        
        models = await bridge.list_models()
        
        table = Table(title="Available Models")
        table.add_column("Status", style="cyan")
        table.add_column("Model", style="green")
        table.add_column("Display Name", style="white")
        table.add_column("Size", style="yellow")
        
        for m in models:
            status = "✅ LOADED" if m.is_loaded else "⚪ available"
            table.add_row(status, m.key, m.display_name, m.quantization)
        
        console.print(table)
    
    asyncio.run(_list())


@main.command()
@click.argument("model_key")
def load(model_key: str):
    """Load a model"""
    async def _load():
        bridge = SimpleQueueBridge()
        
        console.print(f"[cyan]Loading model: {model_key}[/cyan]")
        result = await bridge.load_model(model_key)
        
        if result["success"]:
            console.print(f"[green]✓ {result['message']}[/green]")
        else:
            console.print(f"[red]✗ {result['message']}[/red]")
            console.print("[yellow]Note: You may need to load the model manually in LM Studio GUI first.[/yellow]")
    
    asyncio.run(_load())


@main.command()
@click.argument("model_key")
def unload(model_key: str):
    """Unload a model"""
    async def _unload():
        bridge = SimpleQueueBridge()
        
        console.print(f"[cyan]Unloading model: {model_key}[/cyan]")
        result = await bridge.unload_model(model_key)
        
        if result["success"]:
            console.print(f"[green]✓ {result['message']}[/green]")
        else:
            console.print(f"[red]✗ {result['message']}[/red]")
    
    asyncio.run(_unload())


@main.command()
def status():
    """Show current model status"""
    async def _status():
        bridge = SimpleQueueBridge()
        
        if not await bridge.is_available():
            console.print("[red]LM Studio is not running[/red]")
            return
        
        loaded = await bridge.get_loaded_model()
        
        if loaded:
            console.print(f"[green]Currently loaded: {loaded}[/green]")
        else:
            console.print("[yellow]No model currently loaded[/yellow]")
            console.print("[cyan]Load a model with: aipm-model load <model_key>[/cyan]")
    
    asyncio.run(_status())


if __name__ == "__main__":
    main()
