#!/usr/bin/env python3
"""
AIPM v2 - Multi-Project Orchestrator

Usage:
  python3 main.py              Run continuously (polling every 60s)
  python3 main.py status       Show status report
  python3 main.py run-once     Run one cycle and exit
  python3 main.py labels       Set up AIPM labels on all repos
  python3 main.py create-issue <project> <title>  Create a spec issue
  python3 main.py webhook      Start webhook listener (replaces polling)
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from aipm.loop import MultiProjectLoop
from aipm.config import CTRM_DB


PROJECTS_ROOT = os.path.join(os.path.dirname(__file__), "repos")
DB_PATH = str(CTRM_DB)


def get_loop() -> MultiProjectLoop:
    return MultiProjectLoop(
        projects_root=PROJECTS_ROOT,
        db_path=DB_PATH,
        max_parallel=3,
    )


async def cmd_status():
    loop = get_loop()
    await loop.scan_and_init()
    print(loop.status_report())


async def cmd_labels():
    loop = get_loop()
    await loop.scan_and_init()
    await loop.init_github_labels()


async def cmd_run_once():
    loop = get_loop()
    await loop.run_once()
    print()
    print(loop.status_report())


async def cmd_run(interval: int = 60):
    loop = get_loop()
    await loop.run_forever(interval=interval)


async def cmd_create_issue(project_name: str, title: str):
    from aipm.scanner import ProjectScanner
    from aipm.config import ProjectConfig
    from aipm.github_sync import GitHubSync
    from aipm.spec import Change, ChangeStatus

    scanner = ProjectScanner(PROJECTS_ROOT)
    projects = scanner.scan()

    target = None
    for p in projects:
        if p.name == project_name:
            target = p
            break

    if not target:
        print(f"Project '{project_name}' not found. Available:")
        for p in projects:
            print(f"  {p.name}")
        return

    gh = GitHubSync(target.path)
    if not gh.is_available():
        print(f"No GitHub repo for {project_name}")
        return

    # Ensure labels exist
    gh.ensure_labels()

    # Create a change and sync it to an issue
    change = Change(
        id=title.lower().replace(" ", "-"),
        title=title,
        status=ChangeStatus.APPROVED,
    )
    issue_num = gh.create_issue(change)
    if issue_num:
        print(f"Created issue #{issue_num} in {gh.repo_name}: {title}")
    else:
        print(f"Failed to create issue")


async def cmd_inject(project_name: str, title: str, priority: str = "critical",
                     body: str = "", bypass: bool = False, source: str = "human"):
    """Inject a high-priority issue into a project's queue."""
    from aipm.scanner import ProjectScanner
    from aipm.issue_queue import GitHubIssueQueue
    from aipm.github_sync import GitHubSync
    from aipm.priority import PriorityInjector

    scanner = ProjectScanner(PROJECTS_ROOT)
    projects = scanner.scan()

    target = None
    for p in projects:
        if p.name == project_name:
            target = p
            break

    if not target:
        print(f"Project '{project_name}' not found. Available:")
        for p in projects:
            print(f"  {p.name}")
        return

    gh = GitHubSync(target.path)
    if not gh.is_available():
        print(f"No GitHub repo for {project_name}")
        return

    gh.ensure_labels()
    queue = GitHubIssueQueue(Path(target.path))

    injector = PriorityInjector(queue)
    issue_num = injector.inject(
        title=title,
        body=body,
        priority=priority,
        bypass=bypass,
        source=source,
    )

    if issue_num:
        print(f"Next cycle will pick up #{issue_num}")
    else:
        print("Injection failed")


async def cmd_reset_health(project_name: str = None):
    """Reset circuit breaker (red health) for a project, or all projects."""
    import sqlite3
    from aipm.config import CTRM_DB

    with sqlite3.connect(str(CTRM_DB)) as conn:
        if project_name:
            cur = conn.execute(
                "UPDATE project_state SET health = 'green', consecutive_failures = 0 "
                "WHERE project_id = ? AND health = 'red'",
                (project_name,),
            )
            conn.commit()
            if cur.rowcount:
                print(f"{project_name}: reset {cur.rowcount} red state(s) to green")
            else:
                print(f"{project_name}: no red state found (may already be green)")
        else:
            cur = conn.execute(
                "UPDATE project_state SET health = 'green', consecutive_failures = 0 "
                "WHERE health = 'red'"
            )
            conn.commit()
            if cur.rowcount:
                print(f"Reset {cur.rowcount} red state(s) to green")
            else:
                print("No projects in red state")


async def cmd_pause(reason: str = ""):
    """Pause autonomous processing."""
    from aipm.priority import PriorityInjector
    injector = PriorityInjector()
    injector.pause(reason=reason)


async def cmd_resume():
    """Resume autonomous processing."""
    from aipm.priority import PriorityInjector
    injector = PriorityInjector()
    injector.resume()


async def cmd_boost(project_name: str, issue_number: int, priority: str = "critical"):
    """Boost an existing issue to higher priority."""
    from aipm.scanner import ProjectScanner
    from aipm.issue_queue import GitHubIssueQueue
    from aipm.priority import PriorityInjector

    scanner = ProjectScanner(PROJECTS_ROOT)
    projects = scanner.scan()

    target = None
    for p in projects:
        if p.name == project_name:
            target = p
            break

    if not target:
        print(f"Project '{project_name}' not found.")
        return

    queue = GitHubIssueQueue(Path(target.path))
    injector = PriorityInjector(queue)
    injector.boost(issue_number, priority)


async def cmd_list_injected(project_name: str = None):
    """List high-priority injected issues."""
    from aipm.scanner import ProjectScanner
    from aipm.issue_queue import GitHubIssueQueue
    from aipm.priority import PriorityInjector

    scanner = ProjectScanner(PROJECTS_ROOT)
    projects = scanner.scan()

    if project_name:
        projects = [p for p in projects if p.name == project_name]

    found_any = False
    for p in projects:
        queue = GitHubIssueQueue(Path(p.path))
        injector = PriorityInjector(queue)
        items = injector.list_injected()
        if items:
            found_any = True
            print(f"{p.name}:")
            for item in items:
                print(f"  #{item['number']} [{item['priority']}] {item['title']}")

    if not found_any:
        print("No injected (critical/high) issues in queue.")


async def cmd_sync_roadmap(project_name: str, dry_run: bool = False):
    """Sync ROADMAP.md unchecked items to GitHub issues."""
    from aipm.scanner import ProjectScanner
    from aipm.issue_queue import GitHubIssueQueue
    from aipm.roadmap_sync import sync_roadmap
    from pathlib import Path

    scanner = ProjectScanner(PROJECTS_ROOT)
    projects = scanner.scan()

    target = None
    for p in projects:
        if p.name == project_name:
            target = p
            break

    if not target:
        print(f"Project '{project_name}' not found. Available:")
        for p in projects:
            print(f"  {p.name}")
        return

    queue = GitHubIssueQueue(Path(target.path))
    created = sync_roadmap(Path(target.path), queue, dry_run=dry_run)

    if dry_run:
        print("Dry run complete. No issues created.")
    elif created:
        print(f"Created {len(created)} issue(s): " + ", ".join(f"#{n}" for n in created))
    else:
        print("Roadmap is in sync. No new issues needed.")


async def main():
    args = sys.argv[1:]

    if not args:
        print("AIPM v2 - Multi-Project Orchestrator")
        print()
        await cmd_run(interval=60)
        return

    cmd = args[0]

    if cmd == "status":
        await cmd_status()
    elif cmd == "run-once":
        await cmd_run_once()
    elif cmd == "labels":
        await cmd_labels()
    elif cmd == "create-issue":
        if len(args) < 3:
            print("Usage: python3 main.py create-issue <project> <title>")
            return
        await cmd_create_issue(args[1], " ".join(args[2:]))
    elif cmd == "inject":
        if len(args) < 3:
            print("Usage: python3 main.py inject <project> <title>")
            print("       python3 main.py inject <project> <title> --priority critical|high|medium|low")
            print("       python3 main.py inject <project> <title> --bypass")
            return
        # Parse flags
        priority = "critical"
        bypass = False
        body = ""
        source = "human"
        rest = args[2:]
        i = 0
        title_parts = []
        while i < len(rest):
            if rest[i] == "--priority" and i + 1 < len(rest):
                priority = rest[i + 1]
                i += 2
            elif rest[i] == "--bypass":
                bypass = True
                i += 1
            elif rest[i] == "--body" and i + 1 < len(rest):
                body = rest[i + 1]
                i += 2
            elif rest[i] == "--source" and i + 1 < len(rest):
                source = rest[i + 1]
                i += 2
            else:
                title_parts.append(rest[i])
                i += 1
        title = " ".join(title_parts)
        if not title:
            print("Error: no title provided")
            return
        await cmd_inject(args[1], title, priority, body, bypass, source)
    elif cmd == "pause":
        reason = " ".join(args[1:]) if len(args) > 1 else ""
        await cmd_pause(reason=reason)
    elif cmd == "resume":
        await cmd_resume()
    elif cmd == "boost":
        if len(args) < 3:
            print("Usage: python3 main.py boost <project> <issue-number> [critical|high|medium|low]")
            return
        issue_num = int(args[2])
        priority = args[3] if len(args) > 3 else "critical"
        await cmd_boost(args[1], issue_num, priority)
    elif cmd == "list-injected":
        project = args[1] if len(args) > 1 else None
        await cmd_list_injected(project)
    elif cmd == "new-project":
        if len(args) < 3:
            print("Usage: python3 main.py new-project <name> <language> [description]")
            print("       python3 main.py new-project my-app python \"A cool app\"")
            print("       python3 main.py new-project my-api go --no-github")
            print("Languages: python, go, rust, javascript")
            return
        project_name = args[1]
        language = args[2]
        rest = args[3:]
        no_github = "--no-github" in rest
        public = "--public" in rest
        desc_parts = [p for p in rest if not p.startswith("--")]
        description = " ".join(desc_parts) if desc_parts else ""
        from aipm.repo_scaffold import scaffold_repo
        scaffold_repo(
            name=project_name,
            language=language,
            description=description,
            github_private=not public,
            create_github=not no_github,
        )
    elif cmd == "webhook":
        from aipm.webhook import run_listener
        port = int(args[1]) if len(args) > 1 else 9000
        secret = os.environ.get("AIPM_WEBHOOK_SECRET", "")
        run_listener(port=port, secret=secret)
    elif cmd == "reset-health":
        project = args[1] if len(args) > 1 else None
        await cmd_reset_health(project)
    elif cmd == "sync-roadmap":
        if len(args) < 2:
            print("Usage: python3 main.py sync-roadmap <project> [--dry-run]")
            return
        project_name = args[1]
        dry_run = "--dry-run" in args
        await cmd_sync_roadmap(project_name, dry_run=dry_run)
    elif cmd == "watchdog":
        from aipm.watchdog import main as watchdog_main
        watchdog_main()
    elif cmd == "run":
        interval = int(args[1]) if len(args) > 1 else 60
        await cmd_run(interval=interval)
    else:
        print(f"Unknown command: {cmd}")
        print("Commands: status, run-once, run, labels, create-issue,")
        print("          inject, pause, resume, boost, list-injected,")
        print("          reset-health, new-project, sync-roadmap, watchdog, webhook")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopping AIPM v2...")
