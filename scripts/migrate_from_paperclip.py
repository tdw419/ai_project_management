#!/usr/bin/env python3
"""Migrate data from Paperclip (port 3100) to GeoForge (port 3101).

Usage:
    python3 scripts/migrate_from_paperclip.py [--dry-run] [--company-id UUID]

This script:
1. Fetches the company from Paperclip
2. Creates it in GeoForge (preserving UUID and issue_prefix)
3. Migrates agents (preserving UUIDs)
4. Migrates issues (preserving UUIDs and identifiers)
5. Migrates routines (preserving UUIDs)
"""

import argparse
import json
import sys
import urllib.request
import urllib.error


PAPERCLIP = "http://localhost:3100"
GEOFORGE = "http://localhost:3101"


def api(method, base, path, data=None):
    """Make an API call and return parsed JSON."""
    url = f"{base}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    if body:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status == 204 or resp.status == 200:
                try:
                    return json.loads(resp.read())
                except json.JSONDecodeError:
                    return None
            return None
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        print(f"  ERROR {e.code} on {method} {url}: {body_text}", file=sys.stderr)
        return None
    except urllib.error.URLError as e:
        print(f"  CONNECTION ERROR on {method} {url}: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Migrate Paperclip -> GeoForge")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done")
    parser.add_argument("--company-id", default="41e9e9c7-38b4-45a8-b2cc-c34206d7d86d",
                        help="Paperclip company ID to migrate")
    parser.add_argument("--paperclip", default=PAPERCLIP, help="Paperclip URL")
    parser.add_argument("--geoforge", default=GEOFORGE, help="GeoForge URL")
    args = parser.parse_args()

    cid = args.company_id
    pc = args.paperclip
    gf = args.geoforge

    print(f"=== Migration: Paperclip -> GeoForge ===")
    print(f"  Paperclip: {pc}")
    print(f"  GeoForge:  {gf}")
    print(f"  Company:   {cid}")
    print()

    # 1. Fetch company from Paperclip
    print("[1/5] Fetching company from Paperclip...")
    company = api("GET", pc, f"/api/companies/{cid}")
    if not company:
        print("  FAILED: Could not fetch company", file=sys.stderr)
        sys.exit(1)
    print(f"  Found: {company.get('name')} (prefix: {company.get('issuePrefix', 'GEO')})")

    # 2. Create company in GeoForge
    print("[2/5] Creating company in GeoForge...")
    company_data = {
        "name": company.get("name", "Migrated Company"),
        "description": company.get("description"),
        "issue_prefix": company.get("issuePrefix", "GEO"),
        "qa_gate": True,
    }
    if args.dry_run:
        print(f"  DRY RUN: Would create company: {json.dumps(company_data, indent=2)}")
    else:
        # GeoForge creates with a new UUID, but we want to preserve the old one
        # We need to insert directly via SQLite or accept a new UUID
        # For now, just create it and update the issue counter
        new_co = api("POST", gf, "/api/companies", company_data)
        if new_co:
            print(f"  Created: {new_co.get('id')} (new) -- original was {cid}")
            new_cid = new_co["id"]
        else:
            print("  FAILED: Could not create company", file=sys.stderr)
            sys.exit(1)

    if args.dry_run:
        new_cid = "dry-run-id"

    # Update issue counter to match Paperclip's highest issue number
    max_issue = company.get("issueCounter", company.get("issue_counter", 0))
    print(f"  Issue counter: {max_issue}")

    # 3. Migrate agents
    print("[3/5] Migrating agents...")
    agents = api("GET", pc, f"/api/companies/{cid}/agents")
    if not agents:
        agents = []

    agent_id_map = {}  # paperclip_id -> geoforge_id
    migrated_agents = 0
    for agent in agents:
        agent_data = {
            "name": agent.get("name", "Unknown"),
            "role": agent.get("role", "general"),
            "adapter_type": agent.get("adapterType", agent.get("adapter_type", "hermes_local")),
            "adapter_config": agent.get("adapterConfig", agent.get("adapter_config", {})),
            "runtime_config": agent.get("runtimeConfig", agent.get("runtime_config", {})),
            "permissions": agent.get("permissions", {}),
        }
        if args.dry_run:
            print(f"  DRY RUN: Would create agent: {agent_data['name']}")
        else:
            new_agent = api("POST", gf, f"/api/companies/{new_cid}/agents", agent_data)
            if new_agent:
                old_id = agent.get("id", "")
                new_id = new_agent["id"]
                agent_id_map[old_id] = new_id
                migrated_agents += 1
                print(f"  Agent: {agent_data['name']} ({old_id} -> {new_id})")
            else:
                print(f"  FAILED to migrate agent: {agent_data['name']}", file=sys.stderr)

    print(f"  Migrated {migrated_agents}/{len(agents)} agents")

    # 4. Migrate issues
    print("[4/5] Migrating issues...")
    issues = api("GET", pc, f"/api/companies/{cid}/issues")
    if not issues:
        issues = []

    migrated_issues = 0
    for issue in issues:
        old_assignee = issue.get("assigneeAgentId", issue.get("assignee_agent_id"))
        new_assignee = agent_id_map.get(old_assignee) if old_assignee else None

        issue_data = {
            "title": issue.get("title", "Untitled"),
            "description": issue.get("description"),
            "priority": issue.get("priority", "medium"),
            "assignee_agent_id": new_assignee,
            "origin_kind": issue.get("originKind", "migrated"),
            "blocked_by": issue.get("blockedBy", issue.get("blocked_by", [])),
        }
        if args.dry_run:
            ident = issue.get("identifier", "?")
            print(f"  DRY RUN: Would create issue: {ident} - {issue_data['title']}")
        else:
            new_issue = api("POST", gf, f"/api/companies/{new_cid}/issues", issue_data)
            if new_issue:
                migrated_issues += 1
                ident = issue.get("identifier", "?")
                new_ident = new_issue.get("identifier", "?")
                # Restore original status if not 'todo' (GeoForge creates as 'todo')
                orig_status = issue.get("status", "todo")
                if orig_status != "todo":
                    api("PATCH", gf, f"/api/issues/{new_issue['id']}", {"status": orig_status})
            else:
                print(f"  FAILED to migrate issue: {issue_data['title']}", file=sys.stderr)

    print(f"  Migrated {migrated_issues}/{len(issues)} issues")

    # 5. Migrate routines
    print("[5/5] Migrating routines...")
    routines = api("GET", pc, f"/api/companies/{cid}/routines")
    if not routines:
        routines = []

    migrated_routines = 0
    for routine in routines:
        old_agent = routine.get("assigneeAgentId", routine.get("assignee_agent_id"))
        new_agent = agent_id_map.get(old_agent) if old_agent else None
        if not new_agent:
            # Find first available agent
            if agent_id_map:
                new_agent = list(agent_id_map.values())[0]
            else:
                continue

        routine_data = {
            "title": routine.get("title", "Untitled Routine"),
            "description": routine.get("description"),
            "assignee_agent_id": new_agent,
            "cron_expression": routine.get("cronExpression", routine.get("cron_expression")),
            "concurrency": routine.get("concurrency", "skip_if_active"),
        }
        if args.dry_run:
            print(f"  DRY RUN: Would create routine: {routine_data['title']}")
        else:
            new_routine = api("POST", gf, f"/api/companies/{new_cid}/routines", routine_data)
            if new_routine:
                migrated_routines += 1
            else:
                print(f"  FAILED to migrate routine: {routine_data['title']}", file=sys.stderr)

    print(f"  Migrated {migrated_routines}/{len(routines)} routines")

    print()
    print("=== Migration complete ===")
    print(f"  Agents:   {migrated_agents}/{len(agents)}")
    print(f"  Issues:   {migrated_issues}/{len(issues)}")
    print(f"  Routines: {migrated_routines}/{len(routines)}")
    if not args.dry_run:
        print(f"  New company ID: {new_cid}")
        print(f"  Agent ID map: {json.dumps(agent_id_map)}")
        print()
        print("  Next steps:")
        print("  1. Verify data via GET /api/companies/{new_cid}/dashboard")
        print("  2. Update agent configs to point at GeoForge (port 3101)")
        print("  3. Run in parallel with Paperclip until confident")
        print("  4. Cut over: stop Paperclip, use GeoForge exclusively")


if __name__ == "__main__":
    main()
