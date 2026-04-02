/**
 * DashboardRenderer: Refined ANSI rendering for the PXOS Dashboard.
 * Optimized for both SSH and sequential web rendering.
 */
class DashboardRenderer {
  constructor(engine) {
    this.engine = engine;
  }

  /**
   * Main render entry point.
   * Produces a clean, line-based output compatible with all publishers.
   */
  render(linkTable) {
    const { projects, logs, issues } = this.engine.bridgeData;
    const W = 80;
    const active = projects.filter(p => (p.data?.health || '') === 'green').length;
    const red = projects.filter(p => (p.data?.health || '') === 'red').length;

    const lines = [];

    // 1. Header
    lines.push('');
    lines.push(`  \x1b[1;36mPXOS Dashboard\x1b[0m  |  ${projects.length} projects  |  \x1b[32m${active} green\x1b[0m  \x1b[31m${red} red\x1b[0m  |  ${issues.length} issues`);
    lines.push('  ' + '\u2500'.repeat(W - 4));

    // 2. Main Content (Sequential for compatibility)
    lines.push('');
    lines.push('  \x1b[1mPROJECTS:\x1b[0m');
    lines.push('');
    
    let linkIdx = 1;
    for (const p of projects) {
      const h = (p.data?.health || 'unknown').toLowerCase();
      const color = h === 'green' ? '\x1b[32m' : h === 'red' ? '\x1b[31m' : '\x1b[33m';
      const dot = '\u25CF';
      const name = (p.data?.name || '???').padEnd(24);
      const tests = p.data?.tests ? ` \x1b[2m${p.data.tests.passing}/${p.data.tests.total}\x1b[0m` : '';
      const failures = (p.data?.failures || 0);
      const cb = (failures >= 3 || h === 'red') ? ' \x1b[1;31m[CB]\x1b[0m' : '';
      const failStr = failures > 0 ? ` \x1b[31mfail:${failures}\x1b[0m` : '';
      const idx = linkTable ? `\x1b[1;36m[${linkIdx}]\x1b[0m ` : '  ';
      
      lines.push(`  ${idx}${color}${dot}\x1b[0m ${name}${tests}${failStr}${cb}`);
      linkIdx++;
    }

    if (issues.length > 0) {
      lines.push('');
      lines.push('  \x1b[1mQUEUE:\x1b[0m');
      lines.push('');
      for (const issue of issues) {
        const title = (issue.data?.title || '').substring(0, 50);
        const labels = (issue.data?.labels || []);
        const isCB = labels.includes('circuit-breaker');
        const cbStr = isCB ? ' \x1b[1;31m[CB]\x1b[0m' : '';
        const labelStr = labels.length > 0 ? ` \x1b[2m[${labels.join(', ')}]\x1b[0m` : '';
        const idx = linkTable ? `\x1b[1;36m[${linkIdx}]\x1b[0m ` : '  ';
        lines.push(`  ${idx}#${issue.data?.number} ${title}${labelStr}${cbStr}`);
        linkIdx++;
      }
    }

    if (logs.length > 0) {
      lines.push('');
      lines.push('  \x1b[1mRECENT ACTIVITY:\x1b[0m');
      lines.push('');
      for (const log of logs.slice(0, 10)) {
        const outcome = log.data?.outcome || 'unknown';
        const oColor = outcome === 'success' ? '\x1b[32m'
          : outcome === 'partial' ? '\x1b[33m'
          : '\x1b[31m';
        const proj = (log.data?.project || '?').padEnd(18);
        const issueNum = log.data?.issue || '?';
        lines.push(`  ${oColor}${outcome.padEnd(12)}\x1b[0m ${proj} #${issueNum}`);
      }
    }

    // 3. Footer
    lines.push('');
    lines.push('  ' + '\u2500'.repeat(W - 4));
    const successes = logs.filter(l => l.data?.outcome === 'success').length;
    const rate = logs.length > 0 ? Math.round((successes / logs.length) * 100) : 0;
    lines.push(`  Activity: ${logs.length} logged  |  ${rate}% success rate  |  PXOS Dashboard v1.0`);
    lines.push('');

    return lines.join('\r\n');
  }

  renderDetail(linkData) {
    const W = 80;
    const lines = [];
    if (linkData.type === 'project') {
      const p = linkData.data;
      const name = p.data.name || '???';
      lines.push('', `  \x1b[1;36m${name}\x1b[0m ${'─'.repeat(W - 4 - name.length)}`, '');
      lines.push(`  Health:  ${p.data.health}`);
      lines.push(`  Tests:   ${p.data.tests?.passing}/${p.data.tests?.total}`);
      lines.push(`  Updated: ${p.data.updated_at}`);
    } else if (linkData.type === 'issue') {
      const i = linkData.data;
      lines.push('', `  \x1b[1;36m#${i.data.number}: ${i.data.title}\x1b[0m`, '  ' + '─'.repeat(W - 4), '');
      lines.push(`  Status:  ${i.data.status}`);
      lines.push(`  Labels:  ${(i.data.labels || []).join(', ')}`);
      lines.push('', `  ${i.data.body?.substring(0, 800) || '(No description)'}`);
    }
    lines.push('', '  ' + '─'.repeat(W - 4));
    return lines.join('\r\n');
  }
}

module.exports = DashboardRenderer;
