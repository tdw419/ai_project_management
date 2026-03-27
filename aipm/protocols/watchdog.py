"""
Self-Healing Architecture & Dependency Management

Watchdog agent that monitors the main loop and automatically
rolls back breaking changes when health checks fail.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from enum import Enum
import subprocess
import threading
import time
import json
import os
import signal


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"


class RecoveryAction(Enum):
    NONE = "none"
    RESTART = "restart"
    ROLLBACK = "rollback"
    ROLLBACK_RESTART = "rollback_restart"
    SHUTDOWN = "shutdown"


@dataclass
class HealthCheck:
    """Result of a health check."""
    status: HealthStatus
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    details: dict = field(default_factory=dict)


@dataclass
class ModificationRecord:
    """Record of a code modification for potential rollback."""
    id: str
    timestamp: datetime
    files_changed: list[str]
    diff: str
    commit_sha: Optional[str] = None
    health_before: HealthStatus = HealthStatus.HEALTHY
    health_after: Optional[HealthStatus] = None
    rolled_back: bool = False


@dataclass
class WatchdogConfig:
    """Configuration for the watchdog agent."""
    check_interval_seconds: float = 5.0
    hang_timeout_seconds: float = 60.0
    max_consecutive_failures: int = 3
    rollback_on_unhealthy: bool = True
    restart_on_hang: bool = True
    health_check_command: Optional[str] = None
    log_file: Optional[Path] = None


class DependencyManager:
    """
    Manages code modifications with automatic rollback capability.

    Tracks all changes and can revert them if health checks fail.
    """

    def __init__(self, workspace: Path, state_dir: Path):
        self.workspace = workspace
        self.state_dir = state_dir
        self.modifications: list[ModificationRecord] = []
        self.modification_file = state_dir / "modifications.json"
        self._load()

    def _load(self):
        """Load modification history."""
        if not self.modification_file.exists():
            return

        with open(self.modification_file) as f:
            data = json.load(f)

        self.modifications = [
            ModificationRecord(
                id=m["id"],
                timestamp=datetime.fromisoformat(m["timestamp"]),
                files_changed=m["files_changed"],
                diff=m["diff"],
                commit_sha=m.get("commit_sha"),
                health_before=HealthStatus(m.get("health_before", "healthy")),
                health_after=HealthStatus(m["health_after"]) if m.get("health_after") else None,
                rolled_back=m.get("rolled_back", False),
            )
            for m in data.get("modifications", [])
        ]

    def _save(self):
        """Persist modification history."""
        data = {
            "modifications": [
                {
                    "id": m.id,
                    "timestamp": m.timestamp.isoformat(),
                    "files_changed": m.files_changed,
                    "diff": m.diff,
                    "commit_sha": m.commit_sha,
                    "health_before": m.health_before.value,
                    "health_after": m.health_after.value if m.health_after else None,
                    "rolled_back": m.rolled_back,
                }
                for m in self.modifications
            ],
            "updated_at": datetime.now().isoformat(),
        }
        with open(self.modification_file, "w") as f:
            json.dump(data, f, indent=2)

    def record_modification(self, files_changed: list[str], diff: str,
                           commit_sha: Optional[str] = None) -> ModificationRecord:
        """Record a new modification."""
        import hashlib

        mod_id = hashlib.md5(f"{datetime.now()}{files_changed}".encode()).hexdigest()[:8]
        mod_id = f"MOD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{mod_id}"

        record = ModificationRecord(
            id=mod_id,
            timestamp=datetime.now(),
            files_changed=files_changed,
            diff=diff,
            commit_sha=commit_sha,
            health_before=HealthStatus.HEALTHY,
        )

        self.modifications.append(record)
        self._save()

        return record

    def update_health_after(self, mod_id: str, status: HealthStatus):
        """Update the health status after a modification."""
        for mod in self.modifications:
            if mod.id == mod_id:
                mod.health_after = status
                self._save()
                break

    def get_last_modification(self) -> Optional[ModificationRecord]:
        """Get the most recent non-rolled-back modification."""
        for mod in reversed(self.modifications):
            if not mod.rolled_back:
                return mod
        return None

    def rollback_last(self) -> tuple[bool, str]:
        """
        Rollback the last modification.

        Returns (success, message).
        """
        mod = self.get_last_modification()
        if not mod:
            return False, "No modifications to rollback"

        if mod.commit_sha:
            # Git rollback
            try:
                result = subprocess.run(
                    ["git", "revert", "--no-commit", mod.commit_sha],
                    cwd=self.workspace,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    subprocess.run(["git", "commit", "-m", f"auto: rollback {mod.id}"],
                                 cwd=self.workspace, capture_output=True)
                    mod.rolled_back = True
                    self._save()
                    return True, f"Rolled back {mod.id} via git revert"
                else:
                    return False, f"Git revert failed: {result.stderr}"
            except Exception as e:
                return False, f"Rollback error: {e}"
        else:
            # Patch rollback (reverse diff)
            try:
                # Write reverse patch
                patch_file = self.state_dir / f"rollback_{mod.id}.patch"
                patch_file.write_text(mod.diff)

                result = subprocess.run(
                    ["git", "apply", "--reverse", str(patch_file)],
                    cwd=self.workspace,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    mod.rolled_back = True
                    self._save()
                    patch_file.unlink(missing_ok=True)
                    return True, f"Rolled back {mod.id} via reverse patch"
                else:
                    return False, f"Patch apply failed: {result.stderr}"
            except Exception as e:
                return False, f"Rollback error: {e}"


class WatchdogAgent:
    """
    Monitors the main agent loop for hangs and exceptions.

    Runs as a separate process/thread and takes corrective action
    when health checks fail.
    """

    def __init__(self, config: WatchdogConfig, dependency_manager: DependencyManager):
        self.config = config
        self.dependency_manager = dependency_manager

        self._running = False
        self._last_heartbeat: Optional[datetime] = None
        self._consecutive_failures = 0
        self._health_status = HealthStatus.HEALTHY
        self._thread: Optional[threading.Thread] = None

        # Callbacks for notifications
        self.on_unhealthy: Optional[Callable[[HealthCheck], None]] = None
        self.on_rollback: Optional[Callable[[bool, str], None]] = None

    def start(self):
        """Start the watchdog monitor."""
        self._running = True
        self._last_heartbeat = datetime.now()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the watchdog monitor."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def heartbeat(self):
        """Called by the main loop to indicate it's alive."""
        self._last_heartbeat = datetime.now()
        self._consecutive_failures = 0

    def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            time.sleep(self.config.check_interval_seconds)

            if not self._running:
                break

            # Check for hang
            if self._last_heartbeat:
                elapsed = (datetime.now() - self._last_heartbeat).total_seconds()
                if elapsed > self.config.hang_timeout_seconds:
                    self._handle_hang(elapsed)
                    continue

            # Run health check
            health = self._run_health_check()

            # Update status
            old_status = self._health_status
            self._health_status = health.status

            # Log status change
            if health.status != old_status:
                self._log(f"Health status: {old_status.value} → {health.status.value}")
                self._log(f"  Reason: {health.message}")

            # Handle unhealthy state
            if health.status in (HealthStatus.UNHEALTHY, HealthStatus.CRITICAL):
                self._consecutive_failures += 1
                self._handle_unhealthy(health)
            else:
                self._consecutive_failures = 0

    def _run_health_check(self) -> HealthCheck:
        """Execute health check and return result."""
        details = {}

        # Check 1: Can we import the main modules?
        try:
            import sys
            workspace = self.dependency_manager.workspace
            if str(workspace / "src") not in sys.path:
                sys.path.insert(0, str(workspace / "src"))

            # Try importing core modules
            from ouroboros.core import goal, safety
            details["imports"] = "ok"
        except Exception as e:
            return HealthCheck(
                status=HealthStatus.UNHEALTHY,
                message=f"Import check failed: {e}",
                details=details,
            )

        # Check 2: Can we run a simple test?
        try:
            result = subprocess.run(
                ["python3", "-c", "print('health_check_ok')"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=self.dependency_manager.workspace,
            )
            if "health_check_ok" not in result.stdout:
                return HealthCheck(
                    status=HealthStatus.DEGRADED,
                    message="Subprocess test failed",
                    details=details,
                )
            details["subprocess"] = "ok"
        except Exception as e:
            return HealthCheck(
                status=HealthStatus.DEGRADED,
                message=f"Subprocess check failed: {e}",
                details=details,
            )

        # Check 3: Custom health check command
        if self.config.health_check_command:
            try:
                result = subprocess.run(
                    self.config.health_check_command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=self.dependency_manager.workspace,
                )
                if result.returncode != 0:
                    return HealthCheck(
                        status=HealthStatus.DEGRADED,
                        message=f"Custom health check failed: {result.stderr}",
                        details=details,
                    )
                details["custom_check"] = "ok"
            except Exception as e:
                return HealthCheck(
                    status=HealthStatus.DEGRADED,
                    message=f"Custom health check error: {e}",
                    details=details,
                )

        # Check 4: Disk space
        try:
            stat = os.statvfs(self.dependency_manager.workspace)
            free_percent = (stat.f_bavail * stat.f_frsize) / (stat.f_blocks * stat.f_frsize) * 100
            if free_percent < 5:
                return HealthCheck(
                    status=HealthStatus.CRITICAL,
                    message=f"Low disk space: {free_percent:.1f}% free",
                    details=details,
                )
            details["disk_free_percent"] = f"{free_percent:.1f}"
        except Exception:
            pass  # Non-critical check

        return HealthCheck(
            status=HealthStatus.HEALTHY,
            message="All health checks passed",
            details=details,
        )

    def _handle_hang(self, elapsed: float):
        """Handle detected hang."""
        self._log(f"⚠️ HANG DETECTED: No heartbeat for {elapsed:.1f}s")

        if self.config.rollback_on_unhealthy:
            self._log("Attempting rollback...")
            success, msg = self.dependency_manager.rollback_last()
            self._log(f"  Rollback result: {msg}")

            if self.on_rollback:
                self.on_rollback(success, msg)

        if self.config.restart_on_hang:
            self._log("Triggering restart...")
            # In production, this would restart the main loop
            # For now, just reset the heartbeat
            self._last_heartbeat = datetime.now()

    def _handle_unhealthy(self, health: HealthCheck):
        """Handle unhealthy state."""
        if self.on_unhealthy:
            self.on_unhealthy(health)

        if self._consecutive_failures >= self.config.max_consecutive_failures:
            self._log(f"🚨 Max failures reached ({self._consecutive_failures})")

            if self.config.rollback_on_unhealthy:
                self._log("Auto-rolling back last modification...")
                success, msg = self.dependency_manager.rollback_last()
                self._log(f"  Result: {msg}")

                if self.on_rollback:
                    self.on_rollback(success, msg)

                # Reset counter after rollback
                self._consecutive_failures = 0

    def _log(self, message: str):
        """Log a message."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] WATCHDOG: {message}"
        print(line)

        if self.config.log_file:
            with open(self.config.log_file, "a") as f:
                f.write(line + "\n")

    def get_status(self) -> dict:
        """Get current watchdog status."""
        return {
            "running": self._running,
            "health_status": self._health_status.value,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            "consecutive_failures": self._consecutive_failures,
            "modifications_tracked": len(self.dependency_manager.modifications),
            "pending_rollbacks": sum(1 for m in self.dependency_manager.modifications if not m.rolled_back),
        }


class SelfHealingLoop:
    """
    Main loop wrapper that integrates watchdog monitoring.

    Usage:
        loop = SelfHealingLoop(workspace, config)
        loop.start()

        while loop.is_healthy():
            # Do work
            loop.checkpoint()  # Send heartbeat
    """

    def __init__(self, workspace: Path, config: Optional[WatchdogConfig] = None):
        self.workspace = workspace
        self.config = config or WatchdogConfig()

        state_dir = workspace / ".ouroboros"
        state_dir.mkdir(exist_ok=True)

        self.dependency_manager = DependencyManager(workspace, state_dir)
        self.watchdog = WatchdogAgent(self.config, self.dependency_manager)

        self._last_modification_id: Optional[str] = None

    def start(self):
        """Start the self-healing loop."""
        self.watchdog.start()

    def stop(self):
        """Stop the self-healing loop."""
        self.watchdog.stop()

    def checkpoint(self):
        """Send heartbeat to watchdog."""
        self.watchdog.heartbeat()

    def is_healthy(self) -> bool:
        """Check if the system is healthy."""
        return self.watchdog._health_status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)

    def record_modification(self, files_changed: list[str], diff: str,
                           commit_sha: Optional[str] = None) -> str:
        """Record a modification for potential rollback."""
        mod = self.dependency_manager.record_modification(files_changed, diff, commit_sha)
        self._last_modification_id = mod.id
        return mod.id

    def confirm_modification_healthy(self):
        """Confirm the last modification was healthy."""
        if self._last_modification_id:
            self.dependency_manager.update_health_after(
                self._last_modification_id,
                HealthStatus.HEALTHY
            )

    def get_status(self) -> dict:
        """Get loop status."""
        return {
            "watchdog": self.watchdog.get_status(),
            "workspace": str(self.workspace),
        }


# === USAGE EXAMPLE ===

if __name__ == "__main__":
    from pathlib import Path
    import time

    workspace = Path(".")
    config = WatchdogConfig(
        check_interval_seconds=2.0,
        hang_timeout_seconds=10.0,
        max_consecutive_failures=2,
    )

    loop = SelfHealingLoop(workspace, config)

    print("Starting self-healing loop...")
    loop.start()

    print(f"Status: {loop.get_status()}")

    # Simulate work
    for i in range(10):
        loop.checkpoint()
        print(f"Iteration {i}: healthy={loop.is_healthy()}")
        time.sleep(1)

    # Simulate recording a modification
    mod_id = loop.record_modification(
        files_changed=["test.py"],
        diff="--- test.py\n+++ test.py\n@@ -1 +1 @@\n-print('old')\n+print('new')",
    )
    print(f"Recorded modification: {mod_id}")

    # Confirm it's healthy
    loop.confirm_modification_healthy()

    # Continue work
    for i in range(5):
        loop.checkpoint()
        print(f"Iteration {i+10}: healthy={loop.is_healthy()}")
        time.sleep(1)

    print(f"Final status: {loop.get_status()}")
    loop.stop()
    print("Stopped.")
