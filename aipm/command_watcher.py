"""Command watcher - handles commands from the ascii_world web UI."""

import json
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .config import DATA_DIR
from .priority import write_control, clear_control, PriorityInjector

AIPM_CMD_FILE = DATA_DIR / "aipm-web-cmd.json"


class CommandHandler(FileSystemEventHandler):
    """Handles commands from the web UI via command file."""

    def __init__(self, loop):
        self.loop = loop
        self.injector = PriorityInjector()
        self._handled = set()

    def on_modified(self, event):
        if not event.src_path.endswith("aipm-web-cmd.json"):
            return
        if event.src_path in self._handled:
            self._handled.discard(event.src_path)
            return
        self._handled.add(event.src_path)

        try:
            content = Path(event.src_path).read_text()
            if not content.strip():
                return
            cmd = json.loads(content)
            self._dispatch(cmd)
            Path(event.src_path).write_text("")
        except Exception as e:
            print(f"Command parse error: {e}")

    def _dispatch(self, cmd: Dict[str, Any]):
        action = cmd.get("action")
        print(f"Web UI command: {action}")

        if action == "pause":
            reason = cmd.get("reason", "via web UI")
            write_control("pause_autonomous", reason=reason)
            print(f"PAUSED: {reason}")

        elif action == "resume":
            clear_control()
            print("RESUMED autonomous processing")

        elif action == "inject":
            issue_num = cmd.get("issue_number")
            title = cmd.get("title", "Injected from web UI")
            if issue_num:
                write_control(
                    "inject_priority",
                    issue_number=issue_num,
                    priority="critical",
                    source="web-ui",
                )
                print(f"INJECT: queued issue #{issue_num}")
            else:
                print(f"INJECT: no issue_number provided")

        elif action == "boost":
            issue_num = cmd.get("issue_number")
            new_priority = cmd.get("priority", "critical")
            if issue_num:
                for queue in self.loop.queues.values():
                    self.injector.queue = queue
                    if self.injector.boost(issue_num, new_priority):
                        print(f"BOOSTED #{issue_num} to {new_priority}")
                        break
            else:
                print(f"BOOST: no issue_number provided")

        else:
            print(f"Unknown command: {action}")


class CommandWatcher:
    """Watches for commands from the web UI."""

    def __init__(self, loop):
        self.loop = loop
        self.observer: Optional[Observer] = None

    def start(self):
        """Start watching for commands."""
        handler = CommandHandler(self.loop)
        self.observer = Observer()
        self.observer.schedule(handler, str(DATA_DIR), recursive=False)
        self.observer.start()
        print(f"Command watcher started, watching {DATA_DIR}")

    def stop(self):
        """Stop watching."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            print("Command watcher stopped")
