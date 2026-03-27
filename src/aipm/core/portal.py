"""
Ouroboros Portal - Real-Time Visual Dashboard

A live-updating ASCII dashboard for monitoring the Council of Ouroboros.
Treats the terminal as a spatial substrate for monitoring recursive improvemnt.
"""

import time
import json
from pathlib import Path
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.table import Table
from rich.console import Console
from rich.tree import Tree
from rich import box

from .tree import ExperimentTree
from .goal import GoalState


class OuroborosPortal:
    """The visual dashboard for the Ouroboros system."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = Path(workspace_path)
        self.ouroboros_dir = self.workspace_path / ".ouroboros"
        self.console = Console()

    def _make_layout(self) -> Layout:
        """Define the dashboard layout."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3),
        )
        layout["main"].split_row(
            Layout(name="tree", ratio=2),
            Layout(name="workers", ratio=1),
        )
        return layout

    def _get_worker_statuses(self) -> Table:
        """Collect and format worker statuses."""
        table = Table(title="Swarm Status", expand=True, box=box.ROUNDED)
        table.add_column("Worker ID", style="cyan")
        table.add_column("State", style="green")
        table.add_column("Details", style="dim")
        table.add_column("Age", style="dim")

        # Find all worker status files
        status_files = list(self.ouroboros_dir.glob("status_worker-*.json"))
        now = time.time()

        for sf in status_files:
            try:
                with open(sf) as f:
                    data = json.load(f)
                
                age = int(now - data.get("timestamp", now))
                # Only show workers active in the last 60 seconds
                if age < 60:
                    wid = sf.stem.replace("status_", "")
                    table.add_row(
                        wid,
                        data.get("state", "unknown"),
                        data.get("details", ""),
                        f"{age}s"
                    )
            except:
                pass
        
        if not status_files:
            table.add_row("No workers", "-", "-", "-")

        return table

    def _get_tree_view(self) -> Panel:
        """Generate a rich Tree view from the experiment tree."""
        try:
            exp_tree = ExperimentTree.load(self.ouroboros_dir / "tree.yaml")
            if not exp_tree.root_id:
                return Panel("Waiting for tree initialization...", title="Experiment Tree")

            def add_to_rich_tree(node_id, rich_node):
                node = exp_tree.nodes[node_id]
                
                # Determine styling based on status
                style = "green" if node.status == "active" else "dim"
                if node.status == "achieved": style = "bold green"
                if node.locked_by: style = "yellow"

                metric_str = f" (M: {node.metric:.6f})" if node.metric is not None else ""
                label = f"[bold {style}]{node.id}[/]: {node.hypothesis[:30]}...{metric_str}"
                
                if node.locked_by:
                    label += f" 👷 [italic]{node.locked_by}[/]"

                branch = rich_node.add(label)
                for child_id in node.children:
                    add_to_rich_tree(child_id, branch)

            root_rich = Tree(f"🌲 [bold cyan]Root[/]: {exp_tree.nodes[exp_tree.root_id].hypothesis}")
            for child_id in exp_tree.nodes[exp_tree.root_id].children:
                add_to_rich_tree(child_id, root_rich)

            return Panel(root_rich, title="Experiment Flowchart", border_style="cyan")
        except Exception as e:
            return Panel(f"Error loading tree: {e}", title="Experiment Tree")

    def _get_goal_panel(self) -> Panel:
        """Generate the goal/header panel."""
        try:
            goal = GoalState.load(self.ouroboros_dir / "goal.yaml")
            return Panel(
                f"[bold cyan]GOAL[/]: {goal.objective} | [bold green]CRITERIA[/]: {goal.success_criteria} | [bold yellow]BEST[/]: {goal.best_metric or 'N/A'}",
                style="white",
                box=box.SIMPLE
            )
        except:
            return Panel("Ouroboros Dashboard", box=box.SIMPLE)

    def run(self):
        """Start the live dashboard."""
        layout = self._make_layout()
        
        with Live(layout, refresh_per_second=1, screen=True) as live:
            try:
                while True:
                    layout["header"].update(self._get_goal_panel())
                    layout["tree"].update(self._get_tree_view())
                    layout["workers"].update(self._get_worker_statuses())
                    layout["footer"].update(Panel(f"Last update: {time.ctime()} | Press Ctrl+C to exit portal", style="dim", box=box.SIMPLE))
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
