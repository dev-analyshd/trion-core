/**
 * TRION API client — fetches live data from the Flask backend.
 * Backend runs at http://127.0.0.1:5000 (proxied via Next.js rewrites).
 */

const API_BASE = typeof window !== 'undefined' ? window.location.origin : '';

export async function fetchAPI<T = any>(path: string, opts?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...opts,
      signal: AbortSignal.timeout(12000),
      headers: { 'Content-Type': 'application/json', ...(opts?.headers || {}) },
    });
    if (!res.ok) return null;
    const ct = res.headers.get('content-type') || '';
    if (!ct.includes('application/json')) return null;
    return await res.json() as T;
  } catch {
    return null;
  }
}

export async function postAPI<T = any>(path: string, body: any): Promise<T | null> {
  return fetchAPI<T>(path, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** Formatting helpers */
export const fmt = (n: any, d = 0) =>
  n === null || n === undefined || n === '' ? '—' :
  typeof n === 'number' && isFinite(n) ? n.toLocaleString('en-US', { maximumFractionDigits: d }) :
  String(n);

export const pct = (n: any, d = 1) =>
  n === null || n === undefined ? '—' :
  (Number(n) * 100).toFixed(d) + '%';

export const pctRaw = (n: any, d = 1) =>
  n === null || n === undefined ? '—' : Number(n).toFixed(d) + '%';

export const tfmt = (ts: any) =>
  ts ? new Date(Number(ts) * 1000).toLocaleTimeString('en-US', { hour12: false }) : '—';

export const dtfmt = (ts: any) =>
  ts ? new Date(Number(ts) * 1000).toLocaleString('en-US', { hour12: false }) : '—';

export const truncate = (s: string, len = 16) =>
  s && s.length > len ? s.slice(0, len) + '…' : (s || '—');

export const hex = (s: string, len = 12) =>
  s ? (s.startsWith('0x') ? s.slice(0, len + 2) : s.slice(0, len)) + (s.length > len ? '…' : '') : '—';

export const compact = (n: any) => {
  if (n === null || n === undefined) return '—';
  const num = Number(n);
  if (!isFinite(num)) return '—';
  if (Math.abs(num) >= 1e9) return (num / 1e9).toFixed(2) + 'B';
  if (Math.abs(num) >= 1e6) return (num / 1e6).toFixed(2) + 'M';
  if (Math.abs(num) >= 1e3) return (num / 1e3).toFixed(2) + 'K';
  return num.toFixed(0);
};

export const ms = (n: any) =>
  n === null || n === undefined ? '—' : `${Number(n).toFixed(3)}ms`;

export const statusColor = (s: any): string => {
  if (s === null || s === undefined) return 'gray';
  const str = String(s).toUpperCase();
  if (['OK', 'HEALTHY', 'SAFE', 'COHERENT', 'PASS', 'PASSING', 'APPROVED', 'LIVE', 'OPERATIONAL', 'GOOD'].includes(str)) return 'green';
  if (['WARNING', 'CAUTION', 'ELEVATED', 'MONITORING', 'PENDING'].includes(str)) return 'amber';
  if (['DANGER', 'CRITICAL', 'BLOCKED', 'FAIL', 'FAILING', 'REJECTED', 'SILENCED', 'OFFLINE', 'COLLAPSE'].includes(str)) return 'red';
  if (['UNKNOWN', '—', ''].includes(str)) return 'gray';
  return 'blue';
};
