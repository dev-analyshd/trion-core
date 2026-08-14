/**
 * TRION API client — fetches live data from the Flask backend.
 * Backend runs at http://127.0.0.1:5000 (proxied via Next.js rewrites).
 *
 * Phase 1.6: fetchAPI now returns a discriminated union APIResult<T>:
 *   - { ok: true,  data: T,    status: number }
 *   - { ok: false, error: string, status?: number, type: APIErrorType }
 *
 * The legacy null-on-error pattern is preserved via `fetchAPIOrNull` so
 * existing callers don't break, but new code should use `fetchAPI` and
 * check `data.ok`.
 */
import { config } from './config';

const API_BASE = typeof window !== 'undefined'
  ? (config.apiBase || window.location.origin)
  : '';

// ── Discriminated union ────────────────────────────────────────────────────
export type APIErrorType = 'network' | 'timeout' | 'invalid_json' | 'server' | 'aborted';

export type APIResult<T> =
  | { ok: true;  data: T;     status: number }
  | { ok: false; error: string; status?: number; type: APIErrorType };

const DEFAULT_TIMEOUT_MS = 12000;

/**
 * fetchAPI — returns discriminated union.
 * Use as: `const r = await fetchAPI<T>('/api/v1/health'); if (r.ok) { ... r.data ... }`
 */
export async function fetchAPI<T = any>(path: string, opts?: RequestInit): Promise<APIResult<T>> {
  const controller = new AbortController();
  const timeoutId  = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...opts,
      signal: opts?.signal || controller.signal,
      headers: { 'Content-Type': 'application/json', ...(opts?.headers || {}) },
    });
    clearTimeout(timeoutId);

    const ct = res.headers.get('content-type') || '';
    if (!ct.includes('application/json')) {
      const text = await res.text().catch(() => '');
      return {
        ok: false,
        error: `Expected JSON, got: ${ct || 'empty'}${text ? ` (${text.slice(0, 80)})` : ''}`,
        status: res.status,
        type: 'invalid_json',
      };
    }
    const data = await res.json() as T;
    if (!res.ok) {
      return {
        ok: false,
        error: (data as any)?.error || (data as any)?.message || `HTTP ${res.status}`,
        status: res.status,
        type: 'server',
      };
    }
    return { ok: true, data, status: res.status };
  } catch (e: any) {
    clearTimeout(timeoutId);
    if (e?.name === 'AbortError') {
      return { ok: false, error: 'Request timed out', type: 'timeout' };
    }
    return { ok: false, error: e?.message || 'Network error', type: 'network' };
  }
}

/**
 * fetchAPIOrNull — legacy wrapper that returns `T | null`.
 * Use this in callers that haven't been migrated to the discriminated union yet.
 * New code should prefer `fetchAPI<T>` + `r.ok` check.
 */
export async function fetchAPIOrNull<T = any>(path: string, opts?: RequestInit): Promise<T | null> {
  const r = await fetchAPI<T>(path, opts);
  return r.ok ? r.data : null;
}

/**
 * postAPI — POST JSON, returns discriminated union.
 * Automatically attaches X-API-Key header if set in localStorage (Phase 5.4).
 */
export async function postAPI<T = any>(path: string, body: any, opts?: RequestInit): Promise<APIResult<T>> {
  return fetchAPI<T>(path, {
    method: 'POST',
    body: JSON.stringify(body),
    ...opts,
    headers: {
      ...opts?.headers,
      ...getAPIKeyHeaders(),  // Phase 5.4: auto-attach X-API-Key
    },
  });
}

/**
 * postAPIOrNull — legacy wrapper for postAPI returning `T | null`.
 */
export async function postAPIOrNull<T = any>(path: string, body: any, opts?: RequestInit): Promise<T | null> {
  const r = await postAPI<T>(path, body, opts);
  return r.ok ? r.data : null;
}

// ── API key header helper (Phase 5.4 will populate this) ────────────────────
export function getAPIKeyHeaders(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  const key = localStorage.getItem('trion-api-key');
  return key ? { 'X-API-Key': key } : {};
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
  s && s.length > len ? s.slice(0, len) + '...' : (s || '—');

export const hex = (s: string, len = 12) =>
  s ? (s.startsWith('0x') ? s.slice(0, len + 2) : s.slice(0, len)) + (s.length > len ? '...' : '') : '—';

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


/**
 * Strip Greek symbols, mathematical notation, and formula artifacts from display text.
 * Frontend should show clean, readable English — not whitepaper formulas.
 */
export function cleanText(text: string | null | undefined): string {
  if (!text) return '';
  let result = String(text);
  
  // Replace Greek letters with English equivalents or remove
  const greekMap: Record<string, string> = {
    'α': 'alpha', 'β': 'beta', 'γ': 'gamma', 'δ': 'delta', 'ε': 'epsilon',
    'ζ': 'zeta', 'η': 'eta', 'θ': 'theta', 'ι': 'iota', 'κ': 'kappa',
    'λ': 'lambda', 'μ': 'mu', 'ν': 'nu', 'ξ': 'xi', 'ο': 'omicron',
    'π': 'pi', 'ρ': 'rho', 'σ': 'sigma', 'τ': 'tau', 'υ': 'upsilon',
    'φ': 'phi', 'χ': 'chi', 'ψ': 'psi', 'ω': 'omega',
    'Α': 'Alpha', 'Β': 'Beta', 'Γ': 'Gamma', 'Δ': 'Delta', 'Ε': 'Epsilon',
    'Ζ': 'Zeta', 'Η': 'Eta', 'Θ': 'Theta', 'Ι': 'Iota', 'Κ': 'Kappa',
    'Λ': 'Lambda', 'Μ': 'Mu', 'Ν': 'Nu', 'Ξ': 'Xi', 'Ο': 'Omicron',
    'Π': 'Pi', 'Ρ': 'Rho', 'Σ': 'Sigma', 'Τ': 'Tau', 'Υ': 'Upsilon',
    'Φ': 'Phi', 'Χ': 'Chi', 'Ψ': 'Psi', 'Ω': 'Omega',
    '∑': 'Sigma', '∏': 'Pi',
  };
  
  for (const [greek, eng] of Object.entries(greekMap)) {
    result = result.split(greek).join(eng);
  }
  
  // Remove formula patterns like C(t)=..., T(t)=..., etc.
  result = result.replace(/[A-Z]\(t\)\s*[=:].*?(?=;|\.|$)/g, '');
  
  // Remove mathematical operators that aren't plain English
  result = result.replace(/[·×÷±√∫∞≠≤≥→⇒⇔∈∉⊂⊃∪∩∀∃¬∧∨]/g, ' ');
  
  // Clean up extra whitespace
  result = result.replace(/\s+/g, ' ').trim();
  
  return result;
}

