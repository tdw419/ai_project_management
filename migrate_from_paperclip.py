#!/usr/bin/env python3
"""
GeoForge Migration Script: Paperclip -> GeoForge

Reads data from Paperclip API and imports into GeoForge SQLite.
Usage:
    # From Paperclip (cloud or local):
    python3 migrate_from_paperclip.py --paperclip-url http://localhost:3100 --db geo_forge.db
    # From a JSON export file:
    python3 migrate_from_paperclip.py --from-export paperclip_export.json --db geo_forge.db
    # Export only (no import):
    python3 migrate_from_paperclip.py --paperclip-url http://localhost:3100 --export-only paperclip_export.json
"""

import argparse
import json
import sqlite3
import sys
import uuid
from datetime import datetime

try:
    import urllib.request
    import urllib.error
except ImportError:
    print("urllib not available")
    sys.exit(1)


def fetch_json(url: str, timeout: int = 30) -> dict | list:
    """Fetch JSON from a URL."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} fetching {url}")
        return None
    except urllib.error.URLError as e:
        print(f"  Connection error fetching {url}: {e.reason}")
        return None


def export_paperclip(base_url: str) -> dict:
    """Export all data from Paperclip API."""
    data = {}
    
    # Companies
    print("Fetching companies...")
    data["companies"] = fetch_json(f"{base_url}/api/companies") or []
    print(f"  Found {len(data['companies'])} companies")
    
    # For each company, fetch agents, issues, projects, goals, routines
    all_agents = []
    all_issues = []
    all_projects = []
    all_goals = []
    all_routines = []
    all_comments = []
    all_labels = []
    all_activity = []
    
    for company in data["companies"]:
        cid = company.get("id")
        cname = company.get("name", "unknown")
        print(f"  Fetching data for company: {cname} ({cid})")
        
        # Agents
        agents = fetch_json(f"{base_url}/api/companies/{cid}/agents") or []
        all_agents.extend(agents)
        
        # Issues
        issues = fetch_json(f"{base_url}/api/companies/{cid}/issues") or []
        all_issues.extend(issues)
        
        # Issue comments
        for issue in issues:
            iid = issue.get("id")
            comments = fetch_json(f"{base_url}/api/issues/{iid}/comments") or []
            all_comments.extend(comments)
        
        # Projects
        projects = fetch_json(f"{base_url}/api/companies/{cid}/projects") or []
        all_projects.extend(projects)
        
        # Goals
        goals = fetch_json(f"{base_url}/api/companies/{cid}/goals") or []
        all_goals.extend(goals)
        
        # Labels
        labels = fetch_json(f"{base_url}/api/companies/{cid}/labels") or []
        all_labels.extend(labels)
        
        # Activity
        activity = fetch_json(f"{base_url}/api/companies/{cid}/activity") or []
        all_activity.extend(activity)
        
        print(f"    {len(agents)} agents, {len(issues)} issues, {len(projects)} projects")
    
    data["agents"] = all_agents
    data["issues"] = all_issues
    data["projects"] = all_projects
    data["goals"] = all_goals
    data["routines"] = all_routines
    data["comments"] = all_comments
    data["labels"] = all_labels
    data["activity"] = all_activity
    
    print(f"\nExport summary:")
    print(f"  Companies: {len(data['companies'])}")
    print(f"  Agents: {len(data['agents'])}")
    print(f"  Issues: {len(data['issues'])}")
    print(f"  Projects: {len(data['projects'])}")
    print(f"  Goals: {len(data['goals'])}")
    print(f"  Labels: {len(data['labels'])}")
    print(f"  Comments: {len(data['comments'])}")
    print(f"  Activity: {len(data['activity'])}")
    
    return data


def map_company(pc_company: dict) -> tuple:
    """Map Paperclip company to GeoForge company row."""
    return (
        pc_company.get("id", str(uuid.uuid4())),
        pc_company.get("name", ""),
        pc_company.get("description"),
        pc_company.get("status", "active"),
        pc_company.get("issue_prefix", "GEO"),
        pc_company.get("issue_counter", 0),
        1,  # qa_gate default on
        pc_company.get("created_at", datetime.utcnow().isoformat() + "Z"),
        pc_company.get("updated_at", datetime.utcnow().isoformat() + "Z"),
    )


def map_agent(pc_agent: dict) -> tuple:
    """Map Paperclip agent to GeoForge agent row."""
    adapter_config = pc_agent.get("adapter_config", {})
    runtime_config = pc_agent.get("runtime_config", {})
    permissions = pc_agent.get("permissions", {})
    
    return (
        pc_agent.get("id", str(uuid.uuid4())),
        pc_agent.get("company_id", ""),
        pc_agent.get("name", ""),
        pc_agent.get("role", "general"),
        pc_agent.get("status", "idle"),
        pc_agent.get("adapter_type", "hermes_local"),
        json.dumps(adapter_config) if isinstance(adapter_config, dict) else str(adapter_config),
        json.dumps(runtime_config) if isinstance(runtime_config, dict) else str(runtime_config or "{}"),
        pc_agent.get("reports_to"),
        json.dumps(permissions) if isinstance(permissions, dict) else str(permissions or "{}"),
        pc_agent.get("last_heartbeat"),
        pc_agent.get("paused_at"),
        pc_agent.get("error_message"),
        pc_agent.get("health_status", "unknown"),
        pc_agent.get("health_check_at"),
        pc_agent.get("created_at", datetime.utcnow().isoformat() + "Z"),
        pc_agent.get("updated_at", datetime.utcnow().isoformat() + "Z"),
    )


def map_issue(pc_issue: dict) -> tuple:
    """Map Paperclip issue to GeoForge issue row."""
    blocked_by = pc_issue.get("blocked_by", [])
    if isinstance(blocked_by, list):
        blocked_by = json.dumps(blocked_by)
    elif not blocked_by:
        blocked_by = "[]"
    
    return (
        pc_issue.get("id", str(uuid.uuid4())),
        pc_issue.get("company_id", ""),
        pc_issue.get("project_id"),
        pc_issue.get("parent_id"),
        pc_issue.get("title", ""),
        pc_issue.get("description"),
        pc_issue.get("status", "backlog"),
        pc_issue.get("priority", "medium"),
        pc_issue.get("assignee_agent_id"),
        pc_issue.get("identifier"),
        pc_issue.get("issue_number"),
        pc_issue.get("origin_kind", "manual"),
        pc_issue.get("origin_id"),
        blocked_by,
        pc_issue.get("started_at"),
        pc_issue.get("completed_at"),
        pc_issue.get("created_at", datetime.utcnow().isoformat() + "Z"),
        pc_issue.get("updated_at", datetime.utcnow().isoformat() + "Z"),
    )


def map_comment(pc_comment: dict) -> tuple:
    return (
        pc_comment.get("id", str(uuid.uuid4())),
        pc_comment.get("issue_id", ""),
        pc_comment.get("body", ""),
        pc_comment.get("author_agent_id"),
        pc_comment.get("author_user_id"),
        pc_comment.get("created_at", datetime.utcnow().isoformat() + "Z"),
    )


def map_project(pc_project: dict) -> tuple:
    return (
        pc_project.get("id", str(uuid.uuid4())),
        pc_project.get("company_id", ""),
        pc_project.get("name", ""),
        pc_project.get("description"),
        pc_project.get("status", "in_progress"),
        pc_project.get("color"),
        pc_project.get("created_at", datetime.utcnow().isoformat() + "Z"),
        pc_project.get("updated_at", datetime.utcnow().isoformat() + "Z"),
    )


def map_goal(pc_goal: dict) -> tuple:
    return (
        pc_goal.get("id", str(uuid.uuid4())),
        pc_goal.get("company_id", ""),
        pc_goal.get("title", ""),
        pc_goal.get("description"),
        pc_goal.get("level", "task"),
        pc_goal.get("status", "planned"),
        pc_goal.get("parent_id"),
        pc_goal.get("created_at", datetime.utcnow().isoformat() + "Z"),
        pc_goal.get("updated_at", datetime.utcnow().isoformat() + "Z"),
    )


def map_label(pc_label: dict) -> tuple:
    return (
        pc_label.get("id", str(uuid.uuid4())),
        pc_label.get("company_id", ""),
        pc_label.get("name", ""),
        pc_label.get("color", "#000000"),
        pc_label.get("created_at", datetime.utcnow().isoformat() + "Z"),
    )


def map_activity(pc_activity: dict) -> tuple:
    details = pc_activity.get("details")
    if isinstance(details, dict):
        details = json.dumps(details)
    
    return (
        pc_activity.get("id", str(uuid.uuid4())),
        pc_activity.get("company_id", ""),
        pc_activity.get("actor_type", "system"),
        pc_activity.get("actor_id", ""),
        pc_activity.get("action", ""),
        pc_activity.get("entity_type", ""),
        pc_activity.get("entity_id", ""),
        details,
        pc_activity.get("created_at", datetime.utcnow().isoformat() + "Z"),
    )


def run_migrations(db_path: str):
    """Run GeoForge SQL migrations on the target database."""
    import os
    migrations_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
    if not os.path.isdir(migrations_dir):
        print(f"  Warning: no migrations/ directory found at {migrations_dir}")
        return
    
    conn = sqlite3.connect(db_path)
    # Create _migrations tracking table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
    """)
    
    applied = 0
    for fname in sorted(os.listdir(migrations_dir)):
        if not fname.endswith(".sql"):
            continue
        already = conn.execute("SELECT 1 FROM _migrations WHERE name = ?", (fname,)).fetchone()
        if already:
            continue
        
        fpath = os.path.join(migrations_dir, fname)
        with open(fpath) as f:
            sql = f.read()
        
        try:
            conn.executescript(sql)
            conn.execute("INSERT INTO _migrations (name) VALUES (?)", (fname,))
            conn.commit()
            print(f"  Applied migration: {fname}")
            applied += 1
        except sqlite3.Error as e:
            print(f"  Error in migration {fname}: {e}")
            conn.rollback()
    
    if applied == 0:
        print("  All migrations already applied")
    conn.close()


def import_to_geoforge(data: dict, db_path: str, skip_migrations: bool = False):
    """Import exported Paperclip data into GeoForge SQLite."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    cur = conn.cursor()
    
    inserted = {"companies": 0, "agents": 0, "issues": 0, "projects": 0,
                "goals": 0, "labels": 0, "comments": 0, "activity": 0}
    
    # Companies (insert first -- FK dependencies)
    for c in data.get("companies", []):
        try:
            cur.execute(
                "INSERT OR IGNORE INTO companies (id, name, description, status, issue_prefix, issue_counter, qa_gate, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                map_company(c)
            )
            inserted["companies"] += cur.rowcount
        except sqlite3.Error as e:
            print(f"  Warning: skipping company {c.get('name')}: {e}")
    
    # Projects (before issues -- FK)
    for p in data.get("projects", []):
        try:
            cur.execute(
                "INSERT OR IGNORE INTO projects (id, company_id, name, description, status, color, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                map_project(p)
            )
            inserted["projects"] += cur.rowcount
        except sqlite3.Error as e:
            print(f"  Warning: skipping project {p.get('name')}: {e}")
    
    # Labels
    for l in data.get("labels", []):
        try:
            cur.execute(
                "INSERT OR IGNORE INTO labels (id, company_id, name, color, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                map_label(l)
            )
            inserted["labels"] += cur.rowcount
        except sqlite3.Error as e:
            print(f"  Warning: skipping label: {e}")
    
    # Agents
    for a in data.get("agents", []):
        try:
            cur.execute(
                "INSERT OR IGNORE INTO agents (id, company_id, name, role, status, adapter_type, adapter_config, "
                "runtime_config, reports_to, permissions, last_heartbeat, paused_at, error_message, "
                "health_status, health_check_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                map_agent(a)
            )
            inserted["agents"] += cur.rowcount
        except sqlite3.Error as e:
            print(f"  Warning: skipping agent {a.get('name')}: {e}")
    
    # Goals
    for g in data.get("goals", []):
        try:
            cur.execute(
                "INSERT OR IGNORE INTO goals (id, company_id, title, description, level, status, parent_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                map_goal(g)
            )
            inserted["goals"] += cur.rowcount
        except sqlite3.Error as e:
            print(f"  Warning: skipping goal: {e}")
    
    # Issues
    for i in data.get("issues", []):
        try:
            cur.execute(
                "INSERT OR IGNORE INTO issues (id, company_id, project_id, parent_id, title, description, status, priority, "
                "assignee_agent_id, identifier, issue_number, origin_kind, origin_id, blocked_by, "
                "started_at, completed_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                map_issue(i)
            )
            inserted["issues"] += cur.rowcount
        except sqlite3.Error as e:
            print(f"  Warning: skipping issue {i.get('identifier')}: {e}")
    
    # Comments
    for c in data.get("comments", []):
        try:
            cur.execute(
                "INSERT OR IGNORE INTO issue_comments (id, issue_id, body, author_agent_id, author_user_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                map_comment(c)
            )
            inserted["comments"] += cur.rowcount
        except sqlite3.Error as e:
            print(f"  Warning: skipping comment: {e}")
    
    # Activity
    for a in data.get("activity", []):
        try:
            cur.execute(
                "INSERT OR IGNORE INTO activity_log (id, company_id, actor_type, actor_id, action, entity_type, entity_id, details, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                map_activity(a)
            )
            inserted["activity"] += cur.rowcount
        except sqlite3.Error as e:
            print(f"  Warning: skipping activity: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"\nImport complete:")
    for k, v in inserted.items():
        print(f"  {k}: {v} rows imported")


def main():
    parser = argparse.ArgumentParser(description="Migrate data from Paperclip to GeoForge")
    parser.add_argument("--paperclip-url", default="http://localhost:3100",
                        help="Paperclip API base URL (default: http://localhost:3100)")
    parser.add_argument("--db", default="geo_forge.db",
                        help="GeoForge SQLite database path (default: geo_forge.db)")
    parser.add_argument("--from-export", default=None,
                        help="Import from a previously exported JSON file instead of API")
    parser.add_argument("--export-only", default=None,
                        help="Export Paperclip data to JSON file without importing")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be imported without actually importing")
    
    args = parser.parse_args()
    
    if args.from_export:
        print(f"Loading export from {args.from_export}...")
        with open(args.from_export) as f:
            data = json.load(f)
    else:
        print(f"Exporting from Paperclip at {args.paperclip_url}...")
        data = export_paperclip(args.paperclip_url)
    
    if args.export_only:
        print(f"Writing export to {args.export_only}...")
        with open(args.export_only, "w") as f:
            json.dump(data, f, indent=2)
        print("Export saved.")
        return
    
    if args.dry_run:
        print("\n[DRY RUN] Would import:")
        print(f"  Companies: {len(data.get('companies', []))}")
        print(f"  Agents: {len(data.get('agents', []))}")
        print(f"  Issues: {len(data.get('issues', []))}")
        print(f"  Projects: {len(data.get('projects', []))}")
        print(f"  Goals: {len(data.get('goals', []))}")
        print(f"  Labels: {len(data.get('labels', []))}")
        print(f"  Comments: {len(data.get('comments', []))}")
        print(f"  Activity: {len(data.get('activity', []))}")
        return
    
    print(f"\nRunning migrations on {args.db}...")
    run_migrations(args.db)
    
    print(f"\nImporting into {args.db}...")
    import_to_geoforge(data, args.db, skip_migrations=False)
    
    # Verify
    conn = sqlite3.connect(args.db)
    for table in ["companies", "agents", "issues", "projects", "goals", "labels", "issue_comments", "activity_log"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count} rows")
    conn.close()
    
    print("\nMigration complete. Start GeoForge with: cargo run")


if __name__ == "__main__":
    main()
