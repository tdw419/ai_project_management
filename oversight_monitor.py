#!/usr/bin/env python3
"""
OpenClaw TUI Monitor - Automated AIPM Oversight

This script is called by cron every 10 minutes to:
1. Check AIPM system health
2. Monitor loop status
3. Add improvement prompts if needed
4. Log activity for review
"""

import sys
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Add AIPM to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from aipm import AIPM, get_aipm

# Paths
AIPM_DIR = Path(__file__).parent
LOG_FILE = AIPM_DIR / "logs" / "oversight.log"
PID_FILE = AIPM_DIR / ".loop.pid"


def log(message: str):
    """Log a message with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(log_entry + "\n")
    
    print(log_entry)


def check_loop_status() -> dict:
    """Check if the processing loop is running"""
    result = {"running": False, "pid": None}
    
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            
            # Check if process exists
            import os
            try:
                os.kill(pid, 0)  # Signal 0 = check if process exists
                result["running"] = True
                result["pid"] = pid
            except OSError:
                # Process not running, clean up PID file
                PID_FILE.unlink()
        except:
            pass
    
    return result


def check_queue_status(aipm: AIPM) -> dict:
    """Check queue statistics"""
    stats = aipm.get_stats()
    queue = stats.get("queue", {})
    
    return {
        "pending": queue.get("pending_count", 0),
        "processing": queue.get("processing_count", 0),
        "completed": queue.get("completed_count", 0),
    }


def check_recent_activity(aipm: AIPM, hours: int = 1) -> dict:
    """Check prompts completed in the last N hours"""
    cutoff = datetime.now() - timedelta(hours=hours)
    
    with sqlite3.connect(aipm.ctrm.db_path) as conn:
        cursor = conn.execute("""
            SELECT COUNT(*) FROM prompt_queue
            WHERE status = 'completed'
            AND completed_at >= ?
        """, (cutoff.isoformat(),))
        
        completed_recently = cursor.fetchone()[0]
    
    return {"completed_last_hour": completed_recently}


def check_project_health(aipm: AIPM) -> list:
    """Check health of all projects"""
    projects = aipm.list_projects()
    health = []
    
    for p in projects:
        stats = aipm.projects.get_project_stats(p.id)
        
        health.append({
            "name": p.name,
            "id": p.id,
            "tasks_total": stats["total_tasks"],
            "tasks_completed": stats["completed"],
            "completion": stats["completion_percentage"],
        })
    
    return health


def add_improvement_prompts(aipm: AIPM, queue_stats: dict, activity: dict):
    """Add improvement prompts based on system state"""
    
    prompts_added = []
    
    # If queue is empty, add more prompts
    if queue_stats["pending"] < 10:
        log("⚠️  Queue running low, adding replenishment prompts")
        
        prompt_id = aipm.enqueue(
            prompt="[Oversight] Analyze the AIPM system and suggest improvements. Check code quality, performance bottlenecks, and feature gaps.",
            priority=3,
            source="cron_oversight",
        )
        prompts_added.append(prompt_id)
    
    # If no activity in last hour, add diagnostic prompt
    if activity["completed_last_hour"] == 0:
        log("⚠️  No activity in last hour, adding diagnostic prompt")
        
        prompt_id = aipm.enqueue(
            prompt="[Oversight] Diagnose why the processing loop may have stalled. Check model availability, queue status, and error logs.",
            priority=1,
            source="cron_oversight",
        )
        prompts_added.append(prompt_id)
    
    # Periodically add self-improvement prompts (every 6 hours)
    with sqlite3.connect(aipm.ctrm.db_path) as conn:
        cursor = conn.execute("""
            SELECT COUNT(*) FROM prompt_queue
            WHERE source = 'cron_oversight'
            AND queued_at >= ?
        """, ((datetime.now() - timedelta(hours=6)).isoformat(),))
        
        recent_oversight = cursor.fetchone()[0]
    
    if recent_oversight == 0:
        log("📊 Adding periodic self-improvement prompt")
        
        prompt_id = aipm.enqueue(
            prompt="[Oversight] Review the AIPM architecture and propose one concrete improvement to the continuous loop, provider routing, or response analysis.",
            priority=5,
            source="cron_oversight",
        )
        prompts_added.append(prompt_id)
    
    return prompts_added


def restart_loop_if_needed(loop_status: dict):
    """Restart the loop if it's not running"""
    if not loop_status["running"]:
        log("🔄 Loop not running, attempting restart...")
        
        import subprocess
        result = subprocess.run(
            ["./loop.sh", "start", "--interval", "30"],
            cwd=str(AIPM_DIR),
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0:
            log("✅ Loop restarted successfully")
        else:
            log(f"❌ Failed to restart loop: {result.stderr}")
    else:
        log(f"✅ Loop running (PID: {loop_status['pid']})")


def generate_report(
    loop_status: dict,
    queue_stats: dict,
    activity: dict,
    project_health: list,
    prompts_added: list,
) -> dict:
    """Generate a comprehensive report"""
    return {
        "timestamp": datetime.now().isoformat(),
        "loop": loop_status,
        "queue": queue_stats,
        "activity": activity,
        "projects": project_health,
        "actions": {
            "prompts_added": prompts_added,
            "prompts_count": len(prompts_added),
        },
    }


def main():
    """Main oversight function"""
    log("=" * 70)
    log("OpenClaw TUI Monitor - Starting oversight check")
    log("=" * 70)
    
    # Initialize AIPM
    aipm = get_aipm()
    
    # Check system status
    loop_status = check_loop_status()
    queue_stats = check_queue_status(aipm)
    activity = check_recent_activity(aipm)
    project_health = check_project_health(aipm)
    
    # Log status
    log(f"Queue: {queue_stats['pending']} pending, {queue_stats['completed']} completed")
    log(f"Activity: {activity['completed_last_hour']} prompts completed in last hour")
    log(f"Projects: {len(project_health)} active")
    
    # Take actions
    restart_loop_if_needed(loop_status)
    prompts_added = add_improvement_prompts(aipm, queue_stats, activity)
    
    # Generate report
    report = generate_report(loop_status, queue_stats, activity, project_health, prompts_added)
    
    # Save report
    report_file = AIPM_DIR / "logs" / "oversight_report.json"
    report_file.write_text(json.dumps(report, indent=2))
    
    log(f"Report saved to: {report_file}")
    log("=" * 70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
