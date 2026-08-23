/* ════════════════════════════════════════════════════════════════════════════
   TRION Dashboard — Shared JavaScript v2.0
   ════════════════════════════════════════════════════════════════════════════ */

const TRION = {
  ORACLE_API: window.location.origin,
  FAISS_API: window.location.origin.replace(':5000', ':8000').replace(':5001', ':8000'),

  async fetch(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeout || 10000);
    try {
      const res = await fetch(url, { ...options, signal: controller.signal });
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      return null;
    } finally {
      clearTimeout(timeout);
    }
  },

  formatNumber(n, decimals = 0) {
    if (n === null || n === undefined) return '—';
    if (typeof n !== 'number') n = parseFloat(n);
    if (isNaN(n)) return '—';
    return n.toLocaleString('en-US', { maximumFractionDigits: decimals });
  },

  formatPercent(n, decimals = 2) {
    if (n === null || n === undefined) return '—';
    return (n * 100).toFixed(decimals) + '%';
  },

  formatHash(hash, len = 12) {
    if (!hash) return '—';
    if (hash.length <= len * 2) return hash;
    return hash.slice(0, len) + '…' + hash.slice(-len);
  },

  formatTime(ts) {
    if (!ts) return '—';
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString('en-US', { hour12: false });
  },

  formatRelative(ts) {
    if (!ts) return '—';
    const now = Math.floor(Date.now() / 1000);
    const diff = now - ts;
    if (diff < 60) return diff + 's ago';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    return Math.floor(diff / 86400) + 'd ago';
  },

  statusBadge(status) {
    const map = {
      'LIVE': 'success', 'HEALTHY': 'success', 'SAFE': 'success', 'OPERATIONAL': 'success',
      'WARN': 'warning', 'WARNING': 'warning', 'ELEVATED': 'warning', 'CAUTION': 'warning',
      'ERROR': 'danger', 'CRITICAL': 'danger', 'HOSTILE': 'danger', 'OFFLINE': 'danger', 'BLOCKED': 'danger',
      'SILENCE': 'info', 'SILENCED': 'info', 'BOOTSTRAP': 'info', 'PENDING': 'info',
      'INDEXED': 'muted', 'STALE': 'muted',
    };
    const cls = map[String(status || '').toUpperCase()] || 'muted';
    return `<span class="badge badge-${cls}">${status || 'UNKNOWN'}</span>`;
  },

  async updateSystemStatus() {
    const pill = document.getElementById('system-status');
    if (!pill) return;
    const data = await TRION.fetch(TRION.ORACLE_API + '/api/v1/health');
    if (data && data.chain_connected) {
      pill.classList.add('live');
      pill.classList.remove('warn', 'error');
      pill.querySelector('.status-text').textContent = 'Live';
    } else if (data) {
      pill.classList.add('warn');
      pill.classList.remove('live', 'error');
      pill.querySelector('.status-text').textContent = 'Degraded';
    } else {
      pill.classList.add('error');
      pill.classList.remove('live', 'warn');
      pill.querySelector('.status-text').textContent = 'Offline';
    }
  },

  startClock() {
    const el = document.getElementById('clock');
    if (!el) return;
    const update = () => {
      const d = new Date();
      el.textContent = d.toLocaleTimeString('en-US', { hour12: false }) + ' UTC';
    };
    update();
    setInterval(update, 1000);
  },
};

document.addEventListener('DOMContentLoaded', () => {
  TRION.updateSystemStatus();
  TRION.startClock();
  setInterval(TRION.updateSystemStatus, 30000);
});
