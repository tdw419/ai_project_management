"""
Cross-project issue creation.

When a project completes work that affects or unblocks another project,
this module creates issues in the downstream project's repo.

Supports two relationship types:
  1. dependency: "glyphlang depends on geometry-os-gpu for GPU execution"
     When glyphlang adds a GPU feature -> creates issue in geometry-os-gpu to implement support
  2. consumer: "ascii-world uses glyphlang for rendering"
     When glyphlang changes its API -> creates issue in ascii-world to adopt the change

Relationships are defined in project.yaml:

  depends_on:
    - project: geometry-os-gpu
      paths:
        - pkg/gpu/**
      description: "GPU compute substrate for spatial opcodes"

  consumed_by:
    - project: ascii-world-core
      paths:
        - pkg/compiler/**
        - pkg/vm/**
      description: "Compiles and executes glyph bytecode for rendering"
"""

import re
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass, field

from .issue_queue import GitHubIssueQueue, QueueItem


@dataclass
class ProjectRelation:
    """A relationship between two projects."""
    target_project: str        # the OTHER project's name
    paths: List[str]           # file path patterns that trigger cross-issues
    description: str = ""      # human-readable description of the relationship
    direction: str = "depends_on"  # depends_on or consumed_by


def load_relations(project_config) -> List[ProjectRelation]:
    """Load cross-project relations from project.yaml metadata.

    The project.yaml can have:
      depends_on:
        - project: geometry-os-gpu
          paths: ["pkg/gpu/**"]
          description: "GPU compute substrate"
      consumed_by:
        - project: ascii-world-core
          paths: ["pkg/compiler/**"]
          description: "Bytecode compiler used by renderer"
    """
    relations = []
    meta = getattr(project_config, 'metadata', {}) or {}

    for direction in ['depends_on', 'consumed_by']:
        entries = meta.get(direction, [])
        for entry in entries:
            if isinstance(entry, dict) and 'project' in entry:
                relations.append(ProjectRelation(
                    target_project=entry['project'],
                    paths=entry.get('paths', ['**']),
                    description=entry.get('description', ''),
                    direction=direction,
                ))

    return relations


def check_cross_project_issues(
    source_project: str,
    source_config,
    item: QueueItem,
    diff_summary: str,
    changed_files: List[str],
    all_queues: Dict[str, GitHubIssueQueue],
    all_configs: Dict[str, object],
    max_issues: int = 1,
) -> List[Tuple[str, int]]:
    """Check if a completed issue should create issues in other projects.

    Args:
        source_project: name of the project that completed work
        source_config: the ProjectConfig for the source project
        item: the issue that was completed
        diff_summary: summary of changes made
        changed_files: list of files that changed
        all_queues: map of project_name -> issue queue
        all_configs: map of project_name -> project config

    Returns:
        List of (project_name, issue_number) for created cross-issues.
    """
    relations = load_relations(source_config)
    if not relations:
        return []

    created = []
    existing_titles_by_project = {
        name: [i.title.lower() for i in q.list_open()]
        for name, q in all_queues.items()
    }

    for relation in relations:
        if len(created) >= max_issues:
            break

        target_name = relation.target_project

        # Check target exists
        if target_name not in all_queues:
            continue

        # Check if any changed files match the relation's path patterns
        if not _files_match_patterns(changed_files, relation.paths):
            continue

        target_queue = all_queues[target_name]
        target_config = all_configs.get(target_name)

        # Determine what kind of cross-issue to create
        issue_title, issue_body = _build_cross_issue(
            source_project=source_project,
            target_project=target_name,
            relation=relation,
            item=item,
            diff_summary=diff_summary,
            changed_files=changed_files,
            target_language=getattr(target_config, 'language', 'unknown') if target_config else 'unknown',
        )

        # Dedup check
        if _is_cross_duplicate(issue_title, existing_titles_by_project.get(target_name, [])):
            continue

        # Create the issue in the TARGET project's repo
        issue_num = target_queue.create_issue(
            title=issue_title,
            body=issue_body,
            labels=["autospec", "spec-defined", "cross-project", "priority:high"],
        )

        if issue_num:
            created.append((target_name, issue_num))
            # Comment on the SOURCE issue linking to the cross-project issue
            source_queue = all_queues.get(source_project)
            if source_queue:
                source_queue.add_comment(
                    item,
                    f"**Cross-project:** Created #{issue_num} in {target_name} -- "
                    f"{relation.direction}: {relation.description}",
                )

    return created


def _build_cross_issue(
    source_project: str,
    target_project: str,
    relation: ProjectRelation,
    item: QueueItem,
    diff_summary: str,
    changed_files: List[str],
    target_language: str,
) -> Tuple[str, str]:
    """Build a cross-project issue title and body."""
    if relation.direction == "depends_on":
        # We depend on them -- we added something they need to support
        direction_label = "upstream"
        action = f"{source_project} added changes that require {target_project} support"
    else:
        # They depend on us -- we changed something they consume
        direction_label = "downstream"
        action = f"{source_project} changed an interface that {target_project} uses"

    # Build a specific title based on what actually changed
    relevant_files = [f for f in changed_files if _matches_any_pattern(f, relation.paths)]
    files_summary = ", ".join(relevant_files[:5]) if relevant_files else "multiple files"

    title = (
        f"[{direction_label}] Adopt changes from {source_project}/#{item.issue_number}"
    )

    # Pick the right test command based on language
    test_cmd = {
        "go": "go test ./...",
        "rust": "cargo test",
        "javascript": "npm test",
        "python": "pytest",
    }.get(target_language, "make test")

    body = (
        f"## Cross-Project Dependency\n\n"
        f"**Source:** {source_project}/#{item.issue_number} -- {item.title}\n"
        f"**Relation:** {relation.direction}\n"
        f"**Description:** {relation.description}\n\n"
        f"{action}.\n\n"
        f"### Changes in {source_project}\n"
        f"**Files affected:** {files_summary}\n\n"
        f"{_truncate(diff_summary, 1000)}\n\n"
        f"### What to do\n"
        f"1. Review the changes in {source_project}/#{item.issue_number}\n"
        f"2. Identify what needs to change in this project\n"
        f"3. Implement the required updates\n"
        f"4. Verify with: `{test_cmd}`\n\n"
        f"## Acceptance Criteria\n"
        f"- All tests pass\n"
        f"- Integration with {source_project} still works\n"
        f"- No regressions\n\n"
        f"---\n"
        f"_Auto-generated by AIPM cross-project dependency tracker_"
    )

    return title, body


def _files_match_patterns(files: List[str], patterns: List[str]) -> bool:
    """Check if any file matches any of the path patterns."""
    return any(_matches_any_pattern(f, patterns) for f in files)


def _matches_any_pattern(filepath: str, patterns: List[str]) -> bool:
    """Check if a filepath matches any glob-like pattern."""
    import fnmatch
    for pattern in patterns:
        # Support ** glob
        norm_pattern = pattern.strip('/')
        if fnmatch.fnmatch(filepath, norm_pattern):
            return True
        # Also match if pattern is a directory prefix
        if filepath.startswith(norm_pattern.rstrip('*')):
            return True
    return False


def _is_cross_duplicate(title: str, existing_titles: List[str]) -> bool:
    """Check if a similar cross-project issue already exists."""
    # Extract source project and issue number from title
    refs = re.findall(r'(\w+)/#(\d+)', title)
    for existing in existing_titles:
        for proj, num in refs:
            if f"{proj}/#{num}" in existing:
                return True
    return False


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n... (truncated)"
