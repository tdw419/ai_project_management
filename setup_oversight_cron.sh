#!/bin/bash
# Setup cron job for OpenClaw TUI oversight

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITOR_SCRIPT="$SCRIPT_DIR/oversight_monitor.py"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"

# Make monitor script executable
chmod +x "$MONITOR_SCRIPT"

# Create the cron entry
# Runs every 10 minutes
CRON_ENTRY="*/10 * * * * cd $SCRIPT_DIR && $VENV_PYTHON $MONITOR_SCRIPT >> $SCRIPT_DIR/logs/cron.log 2>&1"

echo "Setting up OpenClaw TUI oversight cron job..."
echo ""
echo "Cron entry:"
echo "$CRON_ENTRY"
echo ""

# Check if already exists
if crontab -l 2>/dev/null | grep -q "oversight_monitor.py"; then
    echo "✓ Cron job already exists"
    echo ""
    echo "Current crontab:"
    crontab -l | grep -A1 -B1 "oversight_monitor" || true
else
    echo "Adding cron job..."
    
    # Add to crontab
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
    
    echo "✓ Cron job added"
    echo ""
    echo "Updated crontab:"
    crontab -l | grep -A1 -B1 "oversight_monitor" || true
fi

echo ""
echo "Logs will be written to:"
echo "  - $SCRIPT_DIR/logs/oversight.log"
echo "  - $SCRIPT_DIR/logs/cron.log"
echo "  - $SCRIPT_DIR/logs/oversight_report.json"
echo ""
echo "To view logs:"
echo "  tail -f $SCRIPT_DIR/logs/oversight.log"
echo ""
echo "To remove cron job:"
echo "  crontab -e  # Then delete the oversight_monitor line"

# Autonomous Recruiter - runs nightly at 2 AM
# Scans all projects and recruits code into the Living Museum
0 2 * * * cd /home/jericho/zion/projects/ai_project_management/aipm && /home/jericho/zion/projects/ai_project_management/aipm/.venv/bin/python3 /home/jericho/zion/projects/ai_project_management/aipm/autonomous_recruiter.py >> /home/jericho/zion/projects/ai_project_management/aipm/logs/recruiter.log 2>&1
