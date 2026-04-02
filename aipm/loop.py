"""
AIPM v2 Main Loop

GitHub Issues are the work queue. SQLite tracks runtime state
(test results, circuit breaker) and prompt/outcome history.

Flow:
  1. Scan for projects with GitHub repos
  2. For each project, read open issues (the queue)
  3. Pick highest priority pending issue
  4. Check prompt log for previous attempts on this issue
  5. Select strategy (fresh / retry / fix_regression / different_approach / simplify)
  6. Generate spec-grounded prompt, enriched with feedback from prior attempts
  7. Run pi agent with trust boundary
  8. Parse outcome (errors, diff, test delta, strategy detected)
  9. Log prompt + outcome for future reference
  10. If failed, issue stays in queue with updated context for next cycle
  11. If succeeded, check off task, maybe close issue, create PR
  12. If abandoned (too many failures), mark issue blocked
"""

import asyncio
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Optional

from .scanner import ProjectScanner
from .config import ProjectConfig, DEFAULT_PI_MODEL
from .state import StateManager, ProjectState
from .driver import GroundedDriver
from .trust import TrustBoundary, FullTreeTrust
from .github_sync import GitHubSync
from .issue_queue import GitHubIssueQueue, QueueItem
from .auto_pr import create_pr_for_item, get_or_create_branch
from .spec import ChangeStatus
from .spec_queue import SpecQueue, SpecQueueItem

# Prompt/output feedback loop
from .outcome import parse_outcome, PiOutcome, OutcomeStatus
from .prompt_log import PromptLog


def _detect_api_failure(raw_output: str, exit_code: int) -> int:
    """Hermes exits 0 even when API calls fail entirely. Detect and force non-zero.
    
    Only triggers on the FINAL failure message (all retries exhausted) AND
    when there's no evidence of actual work being done. Transient errors that
    hermes retries past are ignored.
    """
    if exit_code == 0 and raw_output:
        # Only check for final failure, not transient retries
        final_failure_sigs = [
            "Max retries (3) exceeded",
            "API call failed after 3 retries",
        ]
        has_final_failure = any(sig in raw_output for sig in final_failure_sigs)
        
        if has_final_failure:
            # Check if agent did work despite the final failure
            work_evidence = [
                "preparing terminal",   # hermes ran a terminal command
                "write_file",           # file was written via tool
                "$         ",           # terminal command execution
                "file changed",         # git diff summary
            ]
            has_work = any(e in raw_output for e in work_evidence)
            if not has_work:
                return 2
    return exit_code
from .prompt_strategies import (
    select_strategy,
    enrich_prompt,
    should_abandon,
    Strategy,
)
from .model_router import select_model, select_model_from_context, RoutingDecision
from .openspec_adapter import extract_task_context
from .monte_carlo import MonteCarloRunner, get_diff_summary
from .rca import create_rca_issue
from .followup import create_followup_issues
from .priority import is_paused, get_inject_target, clear_control
from .ascii_bridge import write_ascii_status
from .session_historian import SessionHistorian


class MultiProjectLoop:
    """
    The main v2 loop. GitHub Issues are the queue.

    For each project:
      - issue_queue reads the GitHub Issues (no SQLite queue)
      - driver generates spec-grounded prompts
      - prompt_log tracks every prompt + outcome for learning
      - prompt_strategies picks the right approach based on history
      - pi agent executes with trust boundary protection
      - outcome parses structured data from the raw output
      - state_manager tracks runtime state (circuit breaker, test results)
      - issue_queue updates the issue after execution
    """

    def __init__(self, projects_root: str, db_path: str, max_parallel: int = 3):
        self.projects_root = projects_root
        self.db_path = db_path
        self.max_parallel = max_parallel
        self.scanner = ProjectScanner(projects_root)
        self.state_manager = StateManager(db_path)
        self.prompt_log = PromptLog(db_path)
        self.projects: List[ProjectConfig] = []
        self.drivers: Dict[str, GroundedDriver] = {}
        self.queues: Dict[str, GitHubIssueQueue] = {}
        self.spec_queues: Dict[str, SpecQueue] = {}
        self.gh_syncs: Dict[str, GitHubSync] = {}
        self.active_tasks: Dict[str, asyncio.Task] = {}

    async def scan_and_init(self):
        """Scan for projects, init drivers and issue queues."""
        print(f"--- Scanning for projects in {self.projects_root} ---")
        self.projects = self.scanner.scan()
        print(f"Found {len(self.projects)} projects.")

        for p in self.projects:
            self.drivers[p.name] = GroundedDriver(p)
            self.gh_syncs[p.name] = GitHubSync(p.path)
            self.queues[p.name] = GitHubIssueQueue(p.path)
            self.spec_queues[p.name] = SpecQueue(Path(p.path))

            # Initialize runtime state if needed
            state = self.state_manager.get_latest_state(p.name)
            if not state:
                print(f"  {p.name}: initializing state")
                state = self.drivers[p.name].capture_state()
                self.state_manager.save_state(state)

            # Report status
            queue = self.queues[p.name]
            gh = self.gh_syncs[p.name]
            has_gh = gh.is_available()

            if has_gh:
                stats = queue.stats()
                health_icon = {"green": "🟢", "red": "🔴"}.get(state.health, "⚪")
                print(
                    f"  {p.name} ({p.language}): {health_icon} {state.test_passing}/{state.test_total} tests, "
                    f"queue: {stats['pending']} pending, {stats['in_progress']} active"
                )
            else:
                print(
                    f"  {p.name} ({p.language}): no GitHub repo, skipping issue queue"
                )

    async def init_github_labels(self):
        """Set up AIPM labels on all projects with GitHub repos."""
        for name, gh in self.gh_syncs.items():
            if gh.is_available():
                created = gh.ensure_labels()
                if created > 0:
                    print(f"  {name}: created {created} labels")

    # ── Main execution ───────────────────────────────────────────────

    async def run_once(self):
        """Run one cycle: for each project, pick and execute one issue or spec task."""
        await self.scan_and_init()

        paused = is_paused()
        bypass_issue = get_inject_target()

        if paused:
            print("  PAUSED: only processing human-directed (critical/high) issues")

        for p in self.projects:
            if p.name in self.active_tasks:
                continue

            # Check circuit breaker (with time-based cooldown)
            state = self.state_manager.get_latest_state(p.name)
            if state and state.health == "red":
                last_ts = state.timestamp
                cooldown = getattr(self, "red_cooldown_seconds", 1800)  # 30 min default
                try:
                    from datetime import datetime

                    elapsed = (
                        datetime.now() - datetime.fromisoformat(last_ts)
                    ).total_seconds()
                except Exception:
                    elapsed = cooldown  # if parse fails, allow retry
                if elapsed < cooldown:
                    continue
                else:
                    print(
                        f"  {p.name}: circuit breaker cooldown expired ({int(elapsed)}s), retrying"
                    )

            # ── SPEC-FIRST: Check if openspec/ exists and has pending tasks ──
            spec_queue = self.spec_queues.get(p.name)
            spec_item = None

            if spec_queue and spec_queue.exists():
                # Invalidate cache -- agents may have created new changes
                spec_queue._changes = None
                pending_specs = spec_queue.get_pending()
                if pending_specs:
                    # Get the first pending spec task
                    spec_item = pending_specs[0]

            # ── Route to spec-driven or issue-driven mode ──
            if spec_item:
                # SPEC-DRIVEN MODE
                if not spec_queue.start_task(spec_item):
                    print(f"  {p.name}: failed to start spec task {spec_item.task_id}")
                    continue

                print(
                    f"  {p.name}: starting spec task {spec_item.change_id}/{spec_item.task_id} - {spec_item.task_description[:50]}"
                )

                # Run in parallel if under limit, otherwise sequential
                if len(self.active_tasks) < self.max_parallel:
                    task = asyncio.create_task(self._process_spec_item(p, spec_item))
                    self.active_tasks[p.name] = task
                    task.add_done_callback(
                        lambda t, pid=p.name: self.active_tasks.pop(pid, None)
                    )
                else:
                    await self._process_spec_item(p, spec_item)
            else:
                # ISSUE-DRIVEN MODE (fallback when no specs)
                gh = self.gh_syncs.get(p.name)
                if not gh or not gh.is_available() or not gh.repo_name:
                    continue

                queue = self.queues[p.name]

                # ── Auto-sync roadmap when queue is thin ──
                pending_count = len(queue.get_pending())
                if pending_count < 2:
                    roadmap_path = Path(p.path) / "ROADMAP.md"
                    if roadmap_path.exists():
                        from .roadmap_sync import sync_roadmap

                        new_issues = sync_roadmap(
                            Path(p.path), queue, max_issues=3 - pending_count
                        )
                        if new_issues:
                            print(
                                f"  {p.name}: queue thin ({pending_count} pending), "
                                f"synced {len(new_issues)} issue(s) from roadmap: "
                                + ", ".join(f"#{n}" for n in new_issues)
                            )

                # ── Bypass mode: specific issue requested via inject --bypass ──
                if bypass_issue:
                    item = queue.get_item(bypass_issue)
                    if item:
                        item.project_name = p.name
                        if queue.claim(item):
                            print(
                                f"  BYPASS: claimed injected #{item.issue_number} - {item.title}"
                            )
                            await self._process_item(p, item)
                            clear_control()
                            return  # Process only the bypass issue this cycle
                        else:
                            print(f"  BYPASS: failed to claim #{item.issue_number}")
                    bypass_issue = None  # Don't try for other projects

                # ── Normal / paused mode ──
                # Try pending issues until we find one not in cooldown
                item = None
                pending = queue.get_pending()
                for candidate in pending:
                    # When paused, only process human-directed (critical/high) issues
                    if paused and not candidate.is_human_directed:
                        continue
                    # Per-issue cooldown: skip issues that were recently attempted
                    recent = self.prompt_log.get_attempts(
                        p.name, candidate.issue_number
                    )
                    if recent:
                        last_attempt = recent[-1]
                        try:
                            from datetime import datetime

                            last_time = datetime.fromisoformat(last_attempt.timestamp)
                            elapsed = (datetime.now() - last_time).total_seconds()
                            cooldown = 600  # 10 minutes per-issue cooldown
                            if (
                                elapsed < cooldown
                                and last_attempt.outcome_status != "success"
                            ):
                                continue
                        except Exception:
                            pass
                    item = candidate
                    break

                if not item:
                    continue

                item.project_name = p.name

                # Claim it
                if not queue.claim(item):
                    print(f"  {p.name}: failed to claim issue #{item.issue_number}")
                    continue

                print(f"  {p.name}: claimed issue #{item.issue_number} - {item.title}")

                # Run in parallel if under limit, otherwise sequential
                if len(self.active_tasks) < self.max_parallel:
                    task = asyncio.create_task(self._process_item(p, item))
                    self.active_tasks[p.name] = task
                    task.add_done_callback(
                        lambda t, pid=p.name: self.active_tasks.pop(pid, None)
                    )
                else:
                    await self._process_item(p, item)

        write_ascii_status(self)

    async def _process_item(self, project: ProjectConfig, item: QueueItem):
        """Process one queue item (one pi agent run)."""
        project_name = project.name
        driver = self.drivers[project_name]
        queue = self.queues[project_name]
        state = self.state_manager.get_latest_state(project_name)

        print(
            f"🚀 STARTING agent for {project_name}: #{item.issue_number} {item.title}"
        )

        # Set commit status to pending
        if state and state.commit_hash and state.commit_hash != "unknown":
            queue.set_commit_status(
                state.commit_hash,
                "pending",
                f"AIPM: running task from #{item.issue_number}",
            )

        # ── 1. Check prompt history for this issue ──
        attempts = self.prompt_log.get_attempts(project_name, item.issue_number)
        attempt_number = len(attempts) + 1
        last_outcome = None

        if attempts:
            last_rec = attempts[-1]
            print(
                f"  📊 Issue has {len(attempts)} prior attempt(s), last: {last_rec.outcome_status}"
            )

            # Check if we should abandon
            if should_abandon(attempt_number):
                queue.block(
                    item, f"AIPM: abandoned after {len(attempts)} failed attempts"
                )
                print(f"  🛑 ABANDONED #{item.issue_number} ({len(attempts)} attempts)")

                # Create RCA follow-up issue
                try:
                    rca_num = create_rca_issue(
                        self.prompt_log,
                        project_name,
                        item.issue_number,
                        queue,
                        str(driver.path),
                    )
                    if rca_num:
                        print(
                            f"  🔬 Created RCA issue #{rca_num} for #{item.issue_number}"
                        )
                except Exception as e:
                    print(f"  ⚠️ RCA creation failed: {e}")
                return

            # Reconstruct last outcome for strategy selection
            last_outcome = PiOutcome(
                status=OutcomeStatus(last_rec.outcome_status)
                if last_rec.outcome_status
                else OutcomeStatus.ERROR,
                attempt_number=attempt_number - 1,
                exit_code=last_rec.exit_code,
                strategy_detected=last_rec.strategy_detected,
            )
            # Quick error restore
            import json

            last_outcome.errors = (
                json.loads(last_rec.errors_json) if last_rec.errors_json else []
            )

        # ── 2. Select strategy ──
        strategy = select_strategy(
            last_outcome,
            attempt_number,
            self.prompt_log,
            project_name,
            item.issue_number,
        )
        print(f"  🎯 Strategy: {strategy.value} (attempt #{attempt_number})")

        # ── 3. Generate base prompt from spec + issue data ──
        base_prompt = driver.generate_prompt_from_issue(item, state)

        # ── 4. Enrich prompt with feedback history + cross-issue context ──
        feedback_history = self.prompt_log.get_feedback_history(
            project_name, item.issue_number
        )
        cross_issue = self.prompt_log.cross_issue_context(
            project_name, item.issue_number
        )
        prompt_text = enrich_prompt(
            base_prompt, strategy, last_outcome, feedback_history, project_name
        )

        # Add cross-issue learning after enrichment
        if cross_issue and attempt_number > 1:
            prompt_text = cross_issue + "\n\n---\n\n" + prompt_text

        # ── 5. Create a feature branch if on main/master ──
        branch_name = get_or_create_branch(driver.path, item)
        if branch_name:
            print(f"  🌿 Branch: {branch_name}")

        # ── 6. Trust boundary ──
        trust = TrustBoundary(
            protected_files=driver.config.protected_files,
            base_path=driver.path,
        )
        trust.lock()
        tree = FullTreeTrust(base_path=driver.path)
        file_count = tree.lock()
        print(
            f"  🔒 Trust boundary locked ({len(driver.config.protected_files)} protected, {file_count} snapshot)"
        )

        before_state = driver.capture_state()

        # ── 7. Run hermes agent ──
        routing_decision = None  # Set by model router inside try block
        try:
            cmd = [
                "hermes",
                "chat",
                "-q",
                prompt_text,
                "-Q",
                "--yolo",
                "-t",
                "terminal,file,browser",
            ]

            # ── Smart model routing: complexity + history ──
            # Uses model_router.py instead of hardcoded attempt numbers.
            # Considers: issue complexity, project success rates, issue-level history.
            # Only `hermes_model` in project.yaml overrides the router (explicit opt-out).
            # `pi_model` is the legacy key -- no longer bypasses smart routing.
            hermes_model_override = getattr(driver.config, "hermes_model", None)

            if not hermes_model_override:
                # Get issue info for complexity scoring
                issue_title = item.title if hasattr(item, 'title') else ""
                issue_body = item.body if hasattr(item, 'body') else ""
                project_lang = getattr(driver.config, "language", "")

                try:
                    routing = select_model(
                        db_path=self.db_path,
                        project=driver.name,
                        issue_number=item.issue_number,
                        issue_title=issue_title,
                        issue_body=issue_body,
                        attempt_number=attempt_number,
                        project_language=project_lang,
                    )
                    hermes_model = routing.model
                    print(
                        f"  🧭 Routing: {hermes_model} ({routing.reason})"
                    )
                    routing_decision = routing
                except Exception as route_err:
                    print(f"  ⚠️ Model routing failed: {route_err}, using default")
                    hermes_model = "qwen3.5-tools"
                    routing_decision = RoutingDecision(
                        model=hermes_model,
                        provider="local",
                        reason=f"Routing fallback: {route_err}",
                        complexity_score=0.0,
                        local_success_rate=0.0,
                        cloud_success_rate=0.0,
                    )
            else:
                hermes_model = hermes_model_override
                routing_decision = RoutingDecision(
                    model=hermes_model,
                    provider="override",
                    reason=f"Project config override: {hermes_model}",
                    complexity_score=0.0,
                    local_success_rate=0.0,
                    cloud_success_rate=0.0,
                )

            if hermes_model:
                cmd.extend(["-m", hermes_model])
            # Load project-specific skills
            project_skills = getattr(driver.config, "skills", []) or []
            if project_skills:
                cmd.extend(["-s", ",".join(project_skills)])

            print(
                f"  🚀 RUNNING: hermes chat ({len(prompt_text)} chars, strategy={strategy.value})"
            )

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=driver.path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            raw_output = stdout.decode() + "\n" + stderr.decode()
            exit_code = _detect_api_failure(raw_output, proc.returncode)
            if exit_code != proc.returncode:
                print(f"  ⚠️ API failure detected in output (exit forced to {exit_code})")
            print(
                f"  {'✅' if exit_code == 0 else '❌'} FINISHED agent for {project_name} (exit {exit_code})"
            )
        except Exception as e:
            raw_output = f"Error running hermes agent: {e}"
            exit_code = -1
            print(f"  ❌ FAILED agent for {project_name}: {e}")

        # ── 8. Trust boundary verification ──
        violations = []
        if not trust.verify():
            violations = trust.get_violations()
            print(f"  🚨 TRUST VIOLATION in {project_name}: {violations}")
            if trust.revert():
                print(f"  ✅ Reverted protected files")
            else:
                print(f"  ❌ FAILED to revert protected files!")

        # ── 9. Tree diff ──
        tree_changes = tree.diff()
        if tree_changes:
            added = sum(1 for v in tree_changes.values() if v == "added")
            modified = sum(1 for v in tree_changes.values() if v == "modified")
            deleted = sum(1 for v in tree_changes.values() if v == "deleted")
            print(
                f"  📝 Changes: {added} added, {modified} modified, {deleted} deleted"
            )

        # ── 9b. Auto-commit if agent edited files but didn't commit ──
        # The agent models (qwen3.5-tools, glm-5.1) often skip git commit.
        # We do it here so the outcome detection sees the changes.
        if tree_changes and exit_code == 0 and not violations:
            # Filter out non-code changes (data files, cookies, etc.)
            code_extensions = {
                ".go",
                ".rs",
                ".py",
                ".js",
                ".ts",
                ".jsx",
                ".tsx",
                ".c",
                ".cpp",
                ".h",
                ".hpp",
                ".java",
                ".rb",
                ".sh",
                ".glyph",
                ".wgsl",
                ".glsl",
                ".hlsl",
                ".mod",
                ".sum",
            }
            # Config/doc extensions -- only commit if no pure data files changed
            config_extensions = {
                ".yaml",
                ".yml",
                ".toml",
                ".md",
            }
            code_changes = {
                p: v
                for p, v in tree_changes.items()
                if any(p.endswith(ext) for ext in code_extensions)
            }
            # Only include config/doc changes if there are also real code changes
            if code_changes:
                config_changes = {
                    p: v
                    for p, v in tree_changes.items()
                    if any(p.endswith(ext) for ext in config_extensions)
                }
                all_code = list(code_changes.keys()) + list(config_changes.keys())
            else:
                all_code = list(code_changes.keys())
            if all_code:
                try:
                    # Check if there are uncommitted changes
                    status = subprocess.run(
                        ["git", "status", "--porcelain"],
                        cwd=driver.path,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if status.stdout.strip():
                        short_title = item.title[:60].replace('"', "'")
                        msg = f"AIPM: #{item.issue_number} {short_title}"
                        # Only stage the actual code files, not data artifacts
                        subprocess.run(
                            ["git", "add", "--"] + all_code,
                            cwd=driver.path,
                            capture_output=True,
                            timeout=10,
                        )
                        subprocess.run(
                            ["git", "commit", "-m", msg],
                            cwd=driver.path,
                            capture_output=True,
                            timeout=10,
                        )
                        print(f"  ✅ Auto-committed {len(code_changes)} file(s)")
                except Exception as e:
                    print(f"  ⚠️ Auto-commit failed: {e}")

        # ── 10. Capture after-state ──
        after_state = driver.capture_state()

        # ── 10b. Save raw output for debugging ──
        try:
            import hashlib as _hl
            _debug_dir = Path("/tmp/aipm_outputs")
            _debug_dir.mkdir(exist_ok=True)
            _h = _hl.md5(f"{project_name}{item.issue_number}".encode()).hexdigest()[:8]
            (_debug_dir / f"{project_name}_{_h}.txt").write_text(raw_output[:50000])
        except Exception:
            pass

        # ── 11. Parse outcome ──
        outcome = parse_outcome(
            raw_output=raw_output,
            exit_code=exit_code,
            file_changes=tree_changes or {},
            tests_before=(before_state.test_passing, before_state.test_total),
            tests_after=(after_state.test_passing, after_state.test_total),
            trust_violations=violations,
            commit_hash_before=before_state.commit_hash,
            commit_hash_after=after_state.commit_hash,
            attempt_number=attempt_number,
        )
        print(f"  📊 Outcome: {outcome.summary}")

        # ── 12. Log prompt + outcome with state snapshots ──
        diff_summary = get_diff_summary(str(driver.path))
        record_id = self.prompt_log.record(
            project=project_name,
            issue_number=item.issue_number,
            prompt_text=prompt_text,
            outcome=outcome,
            prompt_strategy=strategy.value,
            state_before={
                "commit": before_state.commit_hash,
                "tests": f"{before_state.test_passing}/{before_state.test_total}",
                "test_output": before_state.test_output[:500],
            },
            state_after={
                "commit": after_state.commit_hash,
                "tests": f"{after_state.test_passing}/{after_state.test_total}",
                "test_output": after_state.test_output[:500],
            },
            diff_summary=diff_summary,
            provider=routing_decision.provider if routing_decision else "",
        )

        success = outcome.status == OutcomeStatus.SUCCESS

        # ── 12b. Index session for future context ──
        try:
            historian = SessionHistorian()
            historian.index_session_from_output(
                project=project_name,
                issue_number=item.issue_number,
                raw_output=raw_output,
                exit_code=exit_code,
                files_changed=tree_changes or {},
                cwd=str(driver.path),
            )
            print(f"  📚 Session indexed for future context")
        except Exception as e:
            print(f"  ⚠️ Session indexing failed (non-critical): {e}")

        # ── 13. Update commit status ──
        if after_state.commit_hash and after_state.commit_hash != "unknown":
            if success:
                queue.set_commit_status(
                    after_state.commit_hash,
                    "success",
                    f"AIPM: {after_state.test_passing}/{after_state.test_total} tests passing",
                )
            else:
                queue.set_commit_status(
                    after_state.commit_hash, "failure", f"AIPM: {outcome.summary}"
                )

        # ── 14. Update issue based on outcome ──
        if success:
            # Check off the next task in the issue body
            next_task = item.get_next_unchecked_task()
            if next_task:
                queue.check_task(item, next_task.replace("- [ ] ", ""))

            # Create a PR for human review
            pr_num = create_pr_for_item(driver.path, item)
            if pr_num:
                print(f"  🔀 Created PR #{pr_num} for #{item.issue_number}")

            # Check if all tasks are done
            completed, total = item.task_checklist
            if total > 0 and completed >= total:
                queue.complete(
                    item,
                    f"AIPM: all {total} tasks completed. "
                    f"Tests: {after_state.test_passing}/{after_state.test_total}",
                )
                print(
                    f"  📋 #{item.issue_number} COMPLETED ({completed}/{total} tasks)"
                )
            else:
                # Comment with outcome details
                comment = (
                    f"**AIPM attempt #{attempt_number}** [{strategy.value}]\n\n"
                    f"{outcome.summary}\n\n"
                    f"Tests: {before_state.test_passing} -> {after_state.test_passing}. "
                    f"Files changed: {len(tree_changes or {})}."
                )
                queue.add_comment(item, comment)
                # Remove in-progress, re-add spec-defined so next task gets picked up
                queue._run_gh(
                    [
                        "issue",
                        "edit",
                        str(item.issue_number),
                        "--remove-label",
                        "in-progress",
                        "--add-label",
                        "spec-defined",
                    ]
                )

            print(f"  ✅ #{item.issue_number}: SUCCESS")

            # ── 14.5. Create follow-up issues for remaining work ──
            try:
                followup_nums = create_followup_issues(
                    queue=queue,
                    item=item,
                    diff_summary=diff_summary,
                    tests_before=before_state.test_passing,
                    tests_after=after_state.test_passing,
                )
                if followup_nums:
                    print(
                        f"  📎 Created {len(followup_nums)} follow-up issue(s): "
                        + ", ".join(f"#{n}" for n in followup_nums)
                    )
            except Exception as e:
                print(f"  ⚠️ Follow-up creation failed: {e}")

            # ── 14.6. Cross-project issue creation ──
            try:
                from .cross_project import check_cross_project_issues

                cross_issues = check_cross_project_issues(
                    source_project=project_name,
                    source_config=project,
                    item=item,
                    diff_summary=diff_summary,
                    changed_files=list(tree_changes.keys()) if tree_changes else [],
                    all_queues=self.queues,
                    all_configs={proj.name: proj for proj in self.projects},
                )
                if cross_issues:
                    for target_name, issue_num in cross_issues:
                        print(
                            f"  🔗 Cross-project: created #{issue_num} in {target_name}"
                        )
            except Exception as e:
                print(f"  ⚠️ Cross-project issue creation failed: {e}")
        else:
            # FAILED -- post detailed feedback as comment
            comment = (
                f"**AIPM attempt #{attempt_number}** [{strategy.value}] - FAILED\n\n"
                f"{outcome.to_feedback_context()}\n\n"
                f"Next attempt will use strategy: {_next_strategy_hint(outcome, attempt_number)}"
            )
            queue.add_comment(item, comment)

            # Release the issue back to the queue (remove in-progress)
            # Don't close it -- let the next cycle pick it up with a different strategy
            queue._run_gh(
                [
                    "issue",
                    "edit",
                    str(item.issue_number),
                    "--remove-label",
                    "in-progress",
                    "--add-label",
                    "spec-defined",
                ]
            )

            print(f"  ⚠️  #{item.issue_number}: FAILED ({outcome.summary})")
            print(
                f"  🔄 Issue released back to queue, next cycle will retry with richer context"
            )

        # ── 15. Update runtime state (circuit breaker) ──
        if not success:
            after_state.consecutive_failures = (
                state.consecutive_failures if state else 0
            ) + 1
            if after_state.consecutive_failures >= project.health_threshold:
                after_state.health = "red"
                queue.block(
                    item,
                    f"Circuit breaker: {after_state.consecutive_failures} consecutive failures",
                )
                print(
                    f"  🛑 CIRCUIT BREAKER: {project_name} ({after_state.consecutive_failures} failures)"
                )
        else:
            after_state.consecutive_failures = 0
            after_state.health = "green"

        self.state_manager.save_state(after_state)

    async def _process_spec_item(self, project: ProjectConfig, item: SpecQueueItem):
        """Process one spec-driven queue item (one pi agent run)."""
        project_name = project.name
        driver = self.drivers[project_name]
        spec_queue = self.spec_queues[project_name]
        state = self.state_manager.get_latest_state(project_name)

        print(
            f"🚀 STARTING agent for {project_name}: spec {item.change_id}/{item.task_id} - {item.task_description[:60]}"
        )

        # Set commit status to pending
        if state and state.commit_hash and state.commit_hash != "unknown":
            # No GH commit status for pure spec-driven items (no GH repo needed)
            pass

        # ── 1. Check prompt history for this spec task ──
        # Use composite key: change_id/task_id
        # Hash the task_key to a stable int so each spec task gets its own attempt history
        task_key = f"{item.change_id}/{item.task_id}"
        task_db_id = abs(hash(task_key)) % (10 ** 6)
        attempts = self.prompt_log.get_attempts(project_name, task_db_id)
        attempt_number = len(attempts) + 1
        last_outcome = None

        if attempts:
            last_rec = attempts[-1]
            print(
                f"  📊 Spec task has {len(attempts)} prior attempt(s), last: {last_rec.outcome_status}"
            )

            # Check if we should abandon
            if should_abandon(attempt_number):
                spec_queue.fail_task(item)
                print(f"  🛑 ABandoned spec task {task_key} ({len(attempts)} attempts)")
                return

            # Reconstruct last outcome for strategy selection
            last_outcome = PiOutcome(
                status=OutcomeStatus(last_rec.outcome_status)
                if last_rec.outcome_status
                else OutcomeStatus.ERROR,
                attempt_number=attempt_number - 1,
                exit_code=last_rec.exit_code,
                strategy_detected=last_rec.strategy_detected,
            )
            import json

            last_outcome.errors = (
                json.loads(last_rec.errors_json) if last_rec.errors_json else []
            )

        # ── 2. Select strategy ──
        strategy = select_strategy(
            last_outcome,
            attempt_number,
            self.prompt_log,
            project_name,
            task_db_id,
        )
        print(f"  🎯 Strategy: {strategy.value} (attempt #{attempt_number})")

        # ── 3. Generate spec-grounded prompt ──
        if state is None:
            state = driver.capture_state()

        # Build the prompt from SpecQueueItem + enriched with spec context
        lines = [
            f"### PROJECT: {project_name}",
            f"Path: {project.path}",
            f"Language: {project.language}",
            f"Status: {state.test_passing}/{state.test_total} tests passing.",
            "",
            f"### SPEC CHANGE: {item.change_title}",
            f"### TASK: {item.task_id} - {item.task_description}",
            f"Component: {item.component}",
        ]
        if item.files:
            lines.append(f"Files: {', '.join(item.files)}")

        # Enrich with proposal context if available
        driver.refresh_specs()
        parent_change = None
        for change in driver.changes:
            if change.id == item.change_id:
                parent_change = change
                if change.proposal:
                    lines.append("")
                    lines.append("### CONTEXT")
                    lines.append(f"Why: {change.proposal.why[:500]}")
                    if change.proposal.success_criteria:
                        lines.append("Success Criteria:")
                        for sc in change.proposal.success_criteria:
                            lines.append(f"  - {sc}")
                # Inject this change's own learnings from prior tasks
                if change.learnings and change.learnings.learnings:
                    own_ctx = change.learnings.to_prompt_context(max_items=10)
                    if own_ctx:
                        lines.append("")
                        lines.append(own_ctx)
                break

        # Inject cross-change learnings from other changes in this project
        try:
            from .learnings import collect_related_learnings
            changes_dir = Path(project.path) / "openspec" / "changes"
            if not changes_dir.exists():
                # Try the repos layout
                changes_dir = Path(project.path) / "openspec" / "changes"
            cross_learnings = collect_related_learnings(
                changes_dir, item.change_id, max_learnings=10
            )
            if cross_learnings:
                lines.append("")
                lines.append(cross_learnings)
        except Exception:
            pass  # Non-critical -- don't block prompt generation

        if item.steps:
            lines.append("")
            lines.append("Steps:")
            for i, step in enumerate(item.steps, 1):
                lines.append(f"  {i}. {step}")

        lines.append("")
        lines.append("### INSTRUCTIONS")
        lines.append(f"1. Explore the codebase in {project.path}")
        lines.append(f"2. Implement task {item.task_id} as described above")
        lines.append(f"3. Check off each step in tasks.md as you complete it:")
        lines.append(f"   The spec file is at: openspec/changes/{item.change_id}/tasks.md")
        lines.append(f"   Change '- [ ] 3.1 ...' to '- [x] 3.1 ...' after each step is done.")
        lines.append(f"4. Verify with: {project.test_command or 'tests'}")
        lines.append(f"5. Commit your changes:")
        lines.append(f"   git add -A")
        lines.append(f'   git commit -m "spec: task {item.task_id}"')
        lines.append(f"6. DO NOT modify protected files or break existing tests")
        if project.protected_files:
            lines.append(f"   Protected: {', '.join(project.protected_files)}")

        lines.append("")
        lines.append("### SPEC MAINTENANCE (IMPORTANT)")
        lines.append("You OWN this spec. Update it as you learn.")
        lines.append("")
        lines.append("A) If the task description or steps are wrong or incomplete:")
        lines.append(f"   Edit openspec/changes/{item.change_id}/tasks.md directly.")
        lines.append("   Fix incorrect descriptions. Add missing steps. Reorder if needed.")
        lines.append("   Better spec = better outcome for the next agent.")
        lines.append("")
        lines.append("B) If the acceptance criteria don't match reality:")
        lines.append(f"   Edit openspec/changes/{item.change_id}/proposal.md.")
        lines.append("   Update the 'Success Criteria' or 'Solution' sections.")
        lines.append("   Document WHY the original was wrong.")
        lines.append("")
        lines.append("C) If you discover work that is clearly out of scope for this task:")
        lines.append("   Do NOT try to shoehorn it into the current task.")
        lines.append("   Instead, create a new change directory:")
        lines.append(f"     mkdir -p openspec/changes/<descriptive-slug>/")
        lines.append(f"     Write openspec/changes/<descriptive-slug>/proposal.md with:")
        lines.append("       # Proposal: <title>")
        lines.append("       ## Summary: what and why")
        lines.append("       ## Dependencies: which existing changes it relates to")
        lines.append("     Write openspec/changes/<descriptive-slug>/tasks.md with:")
        lines.append("       # Tasks: <title>")
        lines.append("       ## 1. <section>")
        lines.append("       - [ ] 1.1 <step>")
        lines.append("   The AIPM loop will pick it up automatically in the next cycle.")
        lines.append("")
        lines.append("D) After implementation, reflect briefly:")
        lines.append(f"   Append to openspec/changes/{item.change_id}/learnings.md:")
        lines.append("   What worked, what didn't, what would you do differently.")

        prompt_text = "\n".join(lines)

        # ── 4. Enrich prompt with feedback history ──
        feedback_history = self.prompt_log.get_feedback_history(
            project_name, task_db_id
        )
        cross_issue = self.prompt_log.cross_issue_context(project_name, task_db_id)
        prompt_text = enrich_prompt(
            prompt_text, strategy, last_outcome, feedback_history, project_name
        )

        if cross_issue and attempt_number > 1:
            prompt_text = cross_issue + "\n\n---\n\n" + prompt_text

        # ── 5. Trust boundary ──
        trust = TrustBoundary(
            protected_files=project.protected_files,
            base_path=driver.path,
        )
        trust.lock()
        tree = FullTreeTrust(base_path=driver.path)
        file_count = tree.lock()
        print(
            f"  🔒 Trust boundary locked ({len(project.protected_files)} protected, {file_count} snapshot)"
        )

        before_state = driver.capture_state()

        # ── 6. Run hermes agent ──
        routing_decision = None  # Set by model router inside try block
        try:
            cmd = [
                "hermes",
                "chat",
                "-q",
                prompt_text,
                "-Q",
                "--yolo",
                "-t",
                "terminal,file,browser",
            ]

            # Only `hermes_model` overrides the smart router, not `pi_model` (legacy).
            hermes_model_override = getattr(project, "hermes_model", None)

            if not hermes_model_override:
                # Extract structured signals from OpenSpec for context-aware routing
                project_lang = getattr(project, "language", "")
                issue_id = getattr(item, 'issue_number', None) or getattr(item, 'task_id', 0)
                issue_num = issue_id if isinstance(issue_id, int) else hash(issue_id) % 10000

                try:
                    # Use context-aware router for spec-driven path
                    task_ctx = extract_task_context(item, parent_change)
                    routing = select_model_from_context(
                        db_path=self.db_path,
                        project=project_name,
                        issue_number=issue_num,
                        task_context=task_ctx,
                        attempt_number=attempt_number,
                        project_language=project_lang,
                    )
                    hermes_model = routing.model
                    print(
                        f"  🧭 Routing: {hermes_model} ({routing.reason})"
                    )
                    routing_decision = routing
                except Exception as route_err:
                    print(f"  ⚠️ Model routing failed: {route_err}, using default")
                    hermes_model = "qwen3.5-tools"
                    routing_decision = RoutingDecision(
                        model=hermes_model,
                        provider="local",
                        reason=f"Routing fallback: {route_err}",
                        complexity_score=0.0,
                        local_success_rate=0.0,
                        cloud_success_rate=0.0,
                    )
            else:
                hermes_model = hermes_model_override
                routing_decision = RoutingDecision(
                    model=hermes_model,
                    provider="override",
                    reason=f"Project config override: {hermes_model}",
                    complexity_score=0.0,
                    local_success_rate=0.0,
                    cloud_success_rate=0.0,
                )

            if hermes_model:
                cmd.extend(["-m", hermes_model])

            project_skills = getattr(project, "skills", []) or []
            if project_skills:
                cmd.extend(["-s", ",".join(project_skills)])

            print(
                f"  🚀 RUNNING: hermes chat ({len(prompt_text)} chars, strategy={strategy.value})"
            )

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=driver.path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            raw_output = stdout.decode() + "\n" + stderr.decode()
            exit_code = _detect_api_failure(raw_output, proc.returncode)
            if exit_code != proc.returncode:
                print(f"  ⚠️ API failure detected in output (exit forced to {exit_code})")
            print(
                f"  {'✅' if exit_code == 0 else '❌'} FINISHED agent for {project_name} (exit {exit_code})"
            )
        except Exception as e:
            raw_output = f"Error running hermes agent: {e}"
            exit_code = -1
            print(f"  ❌ FAILED agent for {project_name}: {e}")

        # ── 7. Trust boundary verification ──
        violations = []
        if not trust.verify():
            violations = trust.get_violations()
            print(f"  🚨 TRUST VIOLATION in {project_name}: {violations}")
            if trust.revert():
                print(f"  ✅ Reverted protected files")
            else:
                print(f"  ❌ FAILED to revert protected files!")

        # ── 8. Tree diff ──
        tree_changes = tree.diff()
        if tree_changes:
            added = sum(1 for v in tree_changes.values() if v == "added")
            modified = sum(1 for v in tree_changes.values() if v == "modified")
            deleted = sum(1 for v in tree_changes.values() if v == "deleted")
            print(
                f"  📝 Changes: {added} added, {modified} modified, {deleted} deleted"
            )

        # ── 8b. Auto-commit ──
        if tree_changes and exit_code == 0 and not violations:
            code_extensions = {
                ".go",
                ".rs",
                ".py",
                ".js",
                ".ts",
                ".jsx",
                ".tsx",
                ".c",
                ".cpp",
                ".h",
                ".hpp",
                ".java",
                ".rb",
                ".sh",
                ".glyph",
                ".wgsl",
                ".glsl",
                ".hlsl",
                ".mod",
                ".sum",
            }
            config_extensions = {".yaml", ".yml", ".toml", ".md"}
            code_changes = {
                p: v
                for p, v in tree_changes.items()
                if any(p.endswith(ext) for ext in code_extensions)
            }
            if code_changes:
                config_changes = {
                    p: v
                    for p, v in tree_changes.items()
                    if any(p.endswith(ext) for ext in config_extensions)
                }
                all_code = list(code_changes.keys()) + list(config_changes.keys())
            else:
                all_code = list(code_changes.keys())
            if all_code:
                try:
                    status = subprocess.run(
                        ["git", "status", "--porcelain"],
                        cwd=driver.path,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if status.stdout.strip():
                        msg = f"spec: task {item.task_id}"
                        subprocess.run(
                            ["git", "add", "--"] + all_code,
                            cwd=driver.path,
                            capture_output=True,
                            timeout=10,
                        )
                        subprocess.run(
                            ["git", "commit", "-m", msg],
                            cwd=driver.path,
                            capture_output=True,
                            timeout=10,
                        )
                        print(f"  ✅ Auto-committed {len(code_changes)} file(s)")
                except Exception as e:
                    print(f"  ⚠️ Auto-commit failed: {e}")

        # ── 9. Capture after-state ──
        after_state = driver.capture_state()

        # ── 10b. Save raw output for debugging ──
        try:
            import hashlib as _hl
            _debug_dir = Path("/tmp/aipm_outputs")
            _debug_dir.mkdir(exist_ok=True)
            _h = _hl.md5(f"{project_name}_spec_{item.task_id}".encode()).hexdigest()[:8]
            (_debug_dir / f"{project_name}_spec_{_h}.txt").write_text(raw_output[:50000])
        except Exception:
            pass

        # ── 10. Parse outcome ──
        outcome = parse_outcome(
            raw_output=raw_output,
            exit_code=exit_code,
            file_changes=tree_changes or {},
            tests_before=(before_state.test_passing, before_state.test_total),
            tests_after=(after_state.test_passing, after_state.test_total),
            trust_violations=violations,
            commit_hash_before=before_state.commit_hash,
            commit_hash_after=after_state.commit_hash,
            attempt_number=attempt_number,
        )
        print(f"  📊 Outcome: {outcome.summary}")

        # ── 11. Log prompt + outcome ──
        diff_summary = get_diff_summary(str(driver.path))
        record_id = self.prompt_log.record(
            project=project_name,
            issue_number=task_db_id,
            prompt_text=prompt_text,
            outcome=outcome,
            prompt_strategy=strategy.value,
            state_before={
                "commit": before_state.commit_hash,
                "tests": f"{before_state.test_passing}/{before_state.test_total}",
                "test_output": before_state.test_output[:500],
            },
            state_after={
                "commit": after_state.commit_hash,
                "tests": f"{after_state.test_passing}/{after_state.test_total}",
                "test_output": after_state.test_output[:500],
            },
            diff_summary=diff_summary,
            provider=routing_decision.provider if routing_decision else "",
        )

        success = outcome.status == OutcomeStatus.SUCCESS

        # ── 12. Update task status based on outcome ──
        if success:
            spec_queue.complete_task(item)
            print(f"  ✅ Spec task {task_key}: COMPLETED")

            # Update change status if all tasks complete
            # (handled by spec discoverer on next cycle)
        else:
            # Release task back to pending
            print(f"  ⚠️  Spec task {task_key}: FAILED ({outcome.summary})")
            print(f"  🔄 Task released back to queue")

        # ── 12b. Write learnings from this outcome ──
        try:
            from .learnings import write_learnings
            change_dir = spec_queue.openspec_dir / item.change_id
            wrote = write_learnings(
                change_dir=change_dir,
                task_id=item.task_id,
                outcome=outcome,
                change_id=item.change_id,
                project_language=project.language,
            )
            if wrote:
                print(f"  📝 Learnings written to {change_dir.name}/learnings.md")
        except Exception as e:
            print(f"  ⚠️  Failed to write learnings: {e}")

        # ── 13. Update runtime state (circuit breaker) ──
        if not success:
            after_state.consecutive_failures = (
                state.consecutive_failures if state else 0
            ) + 1
            if after_state.consecutive_failures >= project.health_threshold:
                after_state.health = "red"
                print(
                    f"  🛑 CIRCUIT BREAKER: {project_name} ({after_state.consecutive_failures} failures)"
                )
        else:
            after_state.consecutive_failures = 0
            after_state.health = "green"

        self.state_manager.save_state(after_state)

    # ── Continuous run ───────────────────────────────────────────────

    async def run_forever(self, interval: int = 60):
        """Run the loop continuously with self-throttling.

        Checks rate limit before each cycle. If rate limit is low,
        increases the sleep interval to avoid exhaustion.
        """
        await self.init_github_labels()

        # Start background Ollama summarizer
        summarizer_task = asyncio.create_task(self._background_summarizer())

        base_interval = interval

        while True:
            # ── Self-throttling: check rate limit before each cycle ──
            effective_interval = base_interval
            try:
                rate_info = self._check_rate_limit_quick()
                if rate_info:
                    remaining = rate_info.get("remaining", 5000)
                    limit = rate_info.get("limit", 5000)
                    pct = remaining / max(limit, 1)

                    if pct < 0.05:
                        # Critical: less than 5% remaining -- sleep 10 min
                        effective_interval = 600
                        print(
                            f"  ⚠️ RATE LIMIT CRITICAL ({remaining:.0f}/{limit}), throttling to {effective_interval}s"
                        )
                    elif pct < 0.15:
                        # Warning: less than 15% -- sleep 5 min
                        effective_interval = 300
                        print(
                            f"  ⚠️ RATE LIMIT LOW ({remaining:.0f}/{limit}), throttling to {effective_interval}s"
                        )
                    elif pct < 0.30:
                        # Cautious: less than 30% -- sleep 2 min
                        effective_interval = 120
                    # else: use base_interval (default)
            except Exception:
                pass

            try:
                await self.run_once()
            except Exception as e:
                print(f"Error in loop: {e}")
            await asyncio.sleep(effective_interval)

    def _check_rate_limit_quick(self) -> Optional[Dict]:
        """Quick rate limit check using REST API (cheaper than GraphQL)."""
        try:
            result = subprocess.run(
                ["gh", "api", "rate_limit", "-q", ".rate.remaining,.rate.limit"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split("\n")
                if len(parts) >= 2:
                    return {
                        "remaining": float(parts[0].strip()),
                        "limit": float(parts[1].strip()),
                    }
        except Exception:
            pass
        return None

    async def _background_summarizer(self, interval: int = 300):
        """Background task: index new sessions and summarize via Ollama.

        Runs every 5 minutes, keeping the GPU busy with summarization
        work during idle time between AIPM dispatch cycles.
        """
        historian = SessionHistorian()
        while True:
            try:
                stats = await historian.index_and_summarize_all(max_summarize=5)
                if stats["indexed"] or stats["summarized"]:
                    print(
                        f"  📚 Session historian: "
                        f"{stats['indexed']} indexed, "
                        f"{stats['summarized']} summarized via Ollama"
                    )
            except Exception as e:
                print(f"  ⚠️ Background summarizer error: {e}")
            await asyncio.sleep(interval)

    # ── Status ───────────────────────────────────────────────────────

    def status_report(self) -> str:
        """Generate a human-readable status report."""
        from .priority import read_control

        lines = ["=" * 60, "  AIPM v2 Status Report", "=" * 60, ""]

        # Show control state
        ctrl = read_control()
        if ctrl:
            cmd = ctrl.get("command", "")
            if cmd == "pause_autonomous":
                lines.append(
                    "  ⏸  AUTONOMOUS PAUSED -- only critical/high issues processed"
                )
                reason = ctrl.get("reason", "")
                if reason:
                    lines.append(f"     Reason: {reason}")
            elif cmd == "inject_priority":
                lines.append(
                    f"  🚨 BYPASS ACTIVE -- next cycle processes #{ctrl.get('issue_number', '?')}"
                )
            lines.append("")

        for p in self.projects:
            driver = self.drivers.get(p.name)
            state = self.state_manager.get_latest_state(p.name)
            queue = self.queues.get(p.name)

            lines.append(f"📂 {p.name} ({p.language})")

            if state:
                health_icon = {"green": "🟢", "red": "🔴"}.get(state.health, "⚪")
                lines.append(
                    f"   {health_icon} {state.test_passing}/{state.test_total} tests, "
                    f"health: {state.health}, failures: {state.consecutive_failures}"
                )

            if queue:
                try:
                    stats = queue.stats()
                    lines.append(
                        f"   Queue: {stats['pending']} pending, "
                        f"{stats['in_progress']} active, {stats['blocked']} blocked"
                    )
                except Exception:
                    lines.append(f"   Queue: (unable to read)")

            # Prompt log stats
            try:
                rate = self.prompt_log.success_rate(p.name)
                total_attempts = 0
                strat_stats = self.prompt_log.strategy_stats(p.name)
                for s in strat_stats.values():
                    total_attempts += s["total"]
                if total_attempts > 0:
                    lines.append(
                        f"   Prompt history: {total_attempts} attempts, "
                        f"{rate:.0%} success rate"
                    )
                    for sname, sdata in strat_stats.items():
                        lines.append(
                            f"     {sname}: {sdata['rate']:.0%} ({sdata['successes']}/{sdata['total']})"
                        )
            except Exception:
                pass

            if driver:
                changes = driver.changes
                if changes:
                    for c in changes:
                        lines.append(f"   📋 {c.title} [{c.status.value}]")

            gh = self.gh_syncs.get(p.name)
            if gh and gh.is_available():
                lines.append(f"   🔗 GitHub: {gh.repo_name}")
            lines.append("")

        return "\n".join(lines)


def _next_strategy_hint(outcome: PiOutcome, attempt_number: int) -> str:
    """Hint at what the next strategy will be (for issue comments)."""
    next_strategy = select_strategy(outcome, attempt_number + 1)
    hints = {
        Strategy.RETRY: "retry with error context",
        Strategy.FIX_REGRESSION: "fix test regression",
        Strategy.DIFFERENT_APPROACH: "different approach (multiple failures)",
        Strategy.SIMPLIFY: "simplified scope (many failures)",
        Strategy.ABANDON: "abandon (too many attempts)",
        Strategy.FRESH: "fresh attempt",
    }
    return hints.get(next_strategy, next_strategy.value)
