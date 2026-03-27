"""
Loop Control - File-based control plane for the continuous loop.

Bridges the API server / dashboard to the actual continuous_loop.py process
using two files:
  .loop.control  - Commands written by API, read by loop (pause/resume/run_once/stop)
  .loop.status   - Structured JSON written by loop, read by API/dashboard

This avoids the need for IPC or shared memory between the API server and the
long-running loop process.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List


class LoopCommand(str, Enum):
    """Commands that can be sent to the loop."""
    PAUSE = "pause"
    RESUME = "resume"
    RUN_ONCE = "run_once"
    STOP = "stop"
    APPROVE = "approve"  # Approve a breakpoint-paused task


class LoopState(str, Enum):
    """Possible states of the loop."""
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_APPROVAL = "waiting_approval"  # Paused at breakpoint
    PROCESSING = "processing"
    STOPPED = "stopped"
    IDLE = "idle"  # Running but no tasks to process


@dataclass
class LoopStatus:
    """Structured status written by the loop for dashboard consumption."""
    state: str = LoopState.STOPPED.value
    processed_count: int = 0
    error_count: int = 0
    model: str = ""
    current_task: Optional[str] = None
    current_task_phase: Optional[str] = None
    breakpoint_reason: Optional[str] = None
    last_processed_at: Optional[str] = None
    uptime_seconds: int = 0
    queue_pending: int = 0
    queue_completed: int = 0
    failover_active: bool = False
    roadmap_progress: Optional[str] = None
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_json(self) -> str:
        d = asdict(self)
        return json.dumps(d, indent=2)

    @classmethod
    def from_json(cls, data: str) -> "LoopStatus":
        try:
            d = json.loads(data)
            return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        except (json.JSONDecodeError, TypeError):
            return cls()


class LoopController:
    """
    Read/write loop control and status files.

    Used by:
    - continuous_loop.py: reads commands, writes status
    - API server: writes commands, reads status
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.root = project_root or Path(__file__).parent.parent
        self.control_file = self.root / ".loop.control"
        self.status_file = self.root / ".loop.status"

    # === Command interface (API server writes, loop reads) ===

    def send_command(self, command: LoopCommand) -> None:
        """Send a command to the loop."""
        self.control_file.write_text(json.dumps({
            "command": command.value,
            "sent_at": datetime.now().isoformat(),
        }))

    def read_command(self) -> Optional[LoopCommand]:
        """Read and consume a pending command. Returns None if no command."""
        if not self.control_file.exists():
            return None

        try:
            data = json.loads(self.control_file.read_text())
            self.control_file.unlink()  # Consume the command
            return LoopCommand(data["command"])
        except (json.JSONDecodeError, KeyError, ValueError):
            # Corrupted control file — remove it
            self.control_file.unlink(missing_ok=True)
            return None

    # === Status interface (loop writes, API server reads) ===

    def write_status(self, status: LoopStatus) -> None:
        """Write current loop status."""
        status.updated_at = datetime.now().isoformat()
        self.status_file.write_text(status.to_json())

    def read_status(self) -> LoopStatus:
        """Read current loop status."""
        if not self.status_file.exists():
            return LoopStatus()

        try:
            return LoopStatus.from_json(self.status_file.read_text())
        except Exception:
            return LoopStatus()

    # === Breakpoint helpers ===

    def request_approval(self, task_description: str, reason: str) -> None:
        """Pause the loop and request human approval for a task."""
        status = self.read_status()
        status.state = LoopState.WAITING_APPROVAL.value
        status.breakpoint_reason = reason
        status.current_task = task_description
        self.write_status(status)

    def is_approved(self) -> bool:
        """Check if a breakpoint has been approved."""
        cmd = self.read_command()
        return cmd == LoopCommand.APPROVE

    def wait_for_approval(self, timeout: int = 3600, poll_interval: int = 5) -> bool:
        """
        Block until approval is received or timeout.

        Returns True if approved, False if timeout or stop command.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            cmd = self.read_command()
            if cmd == LoopCommand.APPROVE:
                return True
            if cmd == LoopCommand.STOP:
                return False
            if cmd == LoopCommand.RESUME:
                return True  # Resume also counts as approval
            time.sleep(poll_interval)
        return False

    def cleanup(self) -> None:
        """Remove control/status files on shutdown."""
        self.control_file.unlink(missing_ok=True)
        # Keep status file so dashboard shows last known state
