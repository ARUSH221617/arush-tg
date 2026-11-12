/**
 * Helper scripts to be used with evaluate_script in Chrome DevTools MCP
 * to extract structured data from Vercel web console pages.
 */

// 1. Extract recent deployments from https://vercel.com/<team>/<project>/deployments
function extractDeployments() {
  const rows = document.querySelectorAll('[data-testid="deployment-row"], a[href*="/deployments/"], tr[data-deployment]');
  const results = [];

  // Fallback to table rows or links if testids vary
  const items = rows.length > 0 ? rows : document.querySelectorAll('main tr, main ul > li');
  items.forEach(el => {
    const text = el.innerText || '';
    const link = el.querySelector('a[href*="/"]');
    const href = link ? link.getAttribute('href') : '';
    
    // Status detection
    let status = 'Unknown';
    if (text.includes('Ready') || text.includes('Active')) status = 'Ready';
    else if (text.includes('Building')) status = 'Building';
    else if (text.includes('Error') || text.includes('Failed')) status = 'Error';
    else if (text.includes('Queued')) status = 'Queued';
    else if (text.includes('Canceled')) status = 'Canceled';

    if (text.trim().length > 0 && (href || status !== 'Unknown')) {
      results.push({
        status,
        href,
        summary: text.split('\n').filter(Boolean).slice(0, 5).join(' | ')
      });
    }
  });

  return results.slice(0, 15);
}

// 2. Extract runtime logs from https://vercel.com/<team>/<project>/logs
function extractLogs() {
  const logRows = document.querySelectorAll('[data-testid="log-row"], [class*="log-row"], [class*="LogViewer"] > div, pre');
  const logs = [];

  logRows.forEach(el => {
    const text = (el.innerText || '').trim();
    if (text.length > 0) {
      logs.push(text);
    }
  });

  // If specific containers aren't matched, read from the main log view container
  if (logs.length === 0) {
    const pre = document.querySelector('pre') || document.querySelector('code') || document.querySelector('main');
    if (pre) {
      return pre.innerText.split('\n').slice(-50);
    }
  }

  return logs.slice(-50);
}

// 3. Extract environment variable keys and configured environments
function extractEnvVars() {
  const rows = document.querySelectorAll('table tbody tr, [data-testid="env-var-row"]');
  const vars = [];

  rows.forEach(tr => {
    const text = (tr.innerText || '').trim();
    const cells = tr.querySelectorAll('td');
    if (cells.length >= 2) {
      const key = cells[0].innerText.trim();
      const valueOrStatus = cells[1].innerText.trim();
      const environments = cells[2] ? cells[2].innerText.trim() : 'Unknown';
      vars.push({ key, valueOrStatus, environments });
    } else if (text.length > 0 && !text.toLowerCase().includes('environment variables')) {
      vars.push({ raw: text.split('\n').filter(Boolean).join(' | ') });
    }
  });

  return vars;
}
