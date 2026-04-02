/**
 * Loop Control Bridge — lets the dashboard write to AIPM's .loop.control file.
 *
 * Commands:
 *   pause [reason]      — pause autonomous processing
 *   resume              — resume autonomous processing
 *   inject <issue>      — force processing of a specific issue next
 *   status              — show current control state
 */

const fs = require('fs');
const path = require('path');

// Default AIPM data directory
const AIPM_DATA_DIR = path.resolve(process.env.AIPM_DATA_DIR || 
  path.join(process.env.HOME, 'zion/projects/aipm/data'));
const CONTROL_FILE = path.join(AIPM_DATA_DIR, '.loop.control');

function readControl() {
  try {
    if (!fs.existsSync(CONTROL_FILE)) return null;
    return JSON.parse(fs.readFileSync(CONTROL_FILE, 'utf8'));
  } catch (e) {
    return null;
  }
}

function writeControl(command, extra = {}) {
  const data = {
    command,
    timestamp: new Date().toISOString(),
    ...extra,
  };
  fs.writeFileSync(CONTROL_FILE, JSON.stringify(data, null, 2));
}

function clearControl() {
  try {
    if (fs.existsSync(CONTROL_FILE)) fs.unlinkSync(CONTROL_FILE);
  } catch (e) {}
}

/**
 * Parse a dashboard command string and execute it.
 * Returns a status message string.
 */
function handleCommand(input) {
  const parts = input.trim().split(/\s+/);
  const cmd = (parts[0] || '').toLowerCase();

  switch (cmd) {
    case 'pause': {
      const reason = parts.slice(1).join(' ') || 'paused from dashboard';
      writeControl('pause_autonomous', { reason });
      return '\x1b[1;33mLOOP PAUSED\x1b[0m — only critical/high priority issues will be processed';
    }

    case 'resume': {
      writeControl('resume_autonomous');
      // Clear after a short delay so the loop sees it
      setTimeout(clearControl, 200);
      return '\x1b[1;32mLOOP RESUMED\x1b[0m — autonomous processing restored';
    }

    case 'inject': {
      const issueNum = parseInt(parts[1], 10);
      if (isNaN(issueNum)) {
        return '\x1b[1;31mUsage: inject <issue_number>\x1b[0m';
      }
      writeControl('inject_priority', { issue_number: issueNum });
      return `\x1b[1;32mINJECTED #${issueNum}\x1b[0m — loop will process this issue next`;
    }

    case 'status': {
      const ctrl = readControl();
      if (!ctrl) {
        return '\x1b[1;32mLOOP: running (no control file)\x1b[0m';
      }
      const ts = ctrl.timestamp ? new Date(ctrl.timestamp).toLocaleTimeString() : '?';
      switch (ctrl.command) {
        case 'pause_autonomous':
          return `\x1b[1;33mLOOP: PAUSED\x1b[0m (${ts}) reason: ${ctrl.reason || 'none'}`;
        case 'resume_autonomous':
          return `\x1b[1;32mLOOP: RESUMING\x1b[0m (${ts})`;
        case 'inject_priority':
          return `\x1b[1;36mLOOP: INJECTING #${ctrl.issue_number}\x1b[0m (${ts})`;
        default:
          return `LOOP: ${ctrl.command} (${ts})`;
      }
    }

    default:
      return null; // Not a control command
  }
}

module.exports = { handleCommand, readControl, CONTROL_FILE };
