"""
Experiment Tree Management

Tracks the branching history of experiments to allow for backtracking
and exploring alternative paths (flowchart-style development).
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
import yaml


@dataclass
class ExperimentNode:
    """A single node in the experiment tree (a code state)."""
    
    id: str  # Unique ID for this node (e.g., "node_1")
    commit_hash: str
    metric: Optional[float]
    hypothesis: str
    parent_id: Optional[str] = None
    status: str = "active"  # active, exhausted, achieved, baseline
    depth: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    children: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    time_spent_seconds: float = 0.0
    iterations_at_node: int = 0
    convergence_rate: Optional[float] = None  # Negative = improving
    
    # Council fields
    locked_by: Optional[str] = None  # worker_id
    assigned_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "id": self.id,
            "commit_hash": self.commit_hash,
            "metric": self.metric,
            "hypothesis": self.hypothesis,
            "parent_id": self.parent_id,
            "status": self.status,
            "depth": self.depth,
            "created_at": self.created_at.isoformat(),
            "children": self.children,
            "metadata": self.metadata,
            "time_spent_seconds": self.time_spent_seconds,
            "iterations_at_node": self.iterations_at_node,
            "convergence_rate": self.convergence_rate,
            "locked_by": self.locked_by,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperimentNode":
        """Create from dictionary."""
        assigned_at = data.get("assigned_at")
        return cls(
            id=data["id"],
            commit_hash=data["commit_hash"],
            metric=data["metric"],
            hypothesis=data["hypothesis"],
            parent_id=data["parent_id"],
            status=data.get("status", "active"),
            depth=data.get("depth", 0),
            created_at=datetime.fromisoformat(data["created_at"]),
            children=data.get("children", []),
            metadata=data.get("metadata", {}),
            time_spent_seconds=data.get("time_spent_seconds", 0.0),
            iterations_at_node=data.get("iterations_at_node", 0),
            convergence_rate=data.get("convergence_rate"),
            locked_by=data.get("locked_by"),
            assigned_at=datetime.fromisoformat(assigned_at) if assigned_at else None,
        )


class ExperimentTree:
    """A tree structure representing the exploration space."""

    def __init__(self, nodes: Optional[Dict[str, ExperimentNode]] = None):
        self.nodes = nodes or {}
        self.root_id: Optional[str] = None
        
        # Identify root
        for node_id, node in self.nodes.items():
            if node.parent_id is None:
                self.root_id = node_id
                break

    def add_node(self, node: ExperimentNode) -> None:
        """Add a node to the tree and update parent's children."""
        # Cycle prevention
        if node.id == node.parent_id:
            print(f"⚠️ Warning: Attempted to add node {node.id} as a child of itself. Skipping link.")
            node.parent_id = None

        # Calculate depth based on parent
        if node.parent_id and node.parent_id in self.nodes:
            node.depth = self.nodes[node.parent_id].depth + 1

        self.nodes[node.id] = node
        if node.parent_id and node.parent_id in self.nodes:
            if node.id not in self.nodes[node.parent_id].children:
                self.nodes[node.parent_id].children.append(node.id)
        elif node.parent_id is None:
            self.root_id = node.id

    def get_node(self, node_id: str) -> Optional[ExperimentNode]:
        """Get a node by ID."""
        return self.nodes.get(node_id)

    def get_best_node(self, lower_is_better: bool = True) -> Optional[ExperimentNode]:
        """Find the node with the best metric so far."""
        best_node = None
        for node in self.nodes.values():
            if node.metric is None:
                continue
            if best_node is None:
                best_node = node
            else:
                if lower_is_better:
                    if node.metric < best_node.metric:
                        best_node = node
                else:
                    if node.metric > best_node.metric:
                        best_node = node
        return best_node

    def get_active_frontier(self) -> List[ExperimentNode]:
        """Get all nodes that are marked as active or baseline and not locked."""
        return [n for n in self.nodes.values() if n.status in ["active", "baseline"] and n.locked_by is None]

    def claim_node(self, node_id: str, worker_id: str) -> bool:
        """Attempt to claim a node for a worker."""
        node = self.get_node(node_id)
        if node and node.locked_by is None:
            node.locked_by = worker_id
            node.assigned_at = datetime.now()
            return True
        return False

    def release_node(self, node_id: str) -> None:
        """Release a node from a worker."""
        node = self.get_node(node_id)
        if node:
            node.locked_by = None
            node.assigned_at = None

    def save(self, path: Path) -> None:
        """Save tree to YAML file with file locking."""
        import fcntl
        data = {node_id: node.to_dict() for node_id, node in self.nodes.items()}
        with open(path, "w") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
                yaml.dump(data, f, default_flow_style=False)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    @classmethod
    def load(cls, path: Path) -> "ExperimentTree":
        """Load tree from YAML file with file locking."""
        import fcntl
        if not path.exists():
            return cls()

        with open(path, "r") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_SH)
                data = yaml.safe_load(f) or {}
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        nodes = {node_id: ExperimentNode.from_dict(node_data) for node_id, node_data in data.items()}
        return cls(nodes)

    def generate_ascii_flowchart(self) -> str:
        """Generate a visual representation of the experiment tree."""
        if not self.root_id:
            return "Empty Tree"

        lines = ["EXPERIMENT FLOWCHART", "===================="]
        visited = set()

        def format_time(seconds: float) -> str:
            if seconds < 60:
                return f"{seconds:.0f}s"
            elif seconds < 3600:
                return f"{seconds/60:.1f}m"
            else:
                return f"{seconds/3600:.1f}h"

        def render_node(node_id: str, prefix: str = "", is_last: bool = True, depth: int = 0):
            if node_id in visited or depth > 50:
                return
            visited.add(node_id)

            node = self.nodes.get(node_id)
            if not node:
                return

            connector = "└── " if is_last else "├── "
            status_tag = f" [{node.status.upper()}]" if node.status != "active" else ""
            if node.locked_by:
                status_tag = f" [LOCKED: {node.locked_by}]"

            metric_str = f" (M: {node.metric:.6f})" if node.metric is not None else ""
            time_str = f" ⏱{format_time(node.time_spent_seconds)}" if node.time_spent_seconds > 0 else ""

            conv_str = ""
            if node.convergence_rate is not None:
                icon = "📉" if node.convergence_rate < 0 else "📈+"
                conv_str = f" {icon}{node.convergence_rate:.3f}"

            hypothesis_short = node.hypothesis[:40] + ("..." if len(node.hypothesis) > 40 else "")
            lines.append(f"{prefix}{connector}{node.id}: {hypothesis_short}{metric_str}{time_str}{conv_str}{status_tag}")

            new_prefix = prefix + ("    " if is_last else "│   ")
            child_ids = [cid for cid in node.children if cid in self.nodes and cid not in visited]
            child_count = len(child_ids)
            for i, child_id in enumerate(child_ids):
                render_node(child_id, new_prefix, i == child_count - 1, depth + 1)

        render_node(self.root_id)
        return "\n".join(lines)


    def get_statistics(self) -> Dict[str, Any]:
        """Return summary statistics about the tree."""
        active = [n for n in self.nodes.values() if n.status == "active"]
        exhausted = [n for n in self.nodes.values() if n.status == "exhausted"]
        achieved = [n for n in self.nodes.values() if n.status == "achieved"]

        depths = [n.depth for n in self.nodes.values()]
        best = self.get_best_node(lower_is_better=True)

        return {
            "total_nodes": len(self.nodes),
            "active_nodes": len(active),
            "exhausted_nodes": len(exhausted),
            "achieved_nodes": len(achieved),
            "max_depth": max(depths) if depths else 0,
            "best_metric": best.metric if best else None,
            "best_node_id": best.id if best else None,
        }
