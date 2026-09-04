/**
 * React hooks for streaming live TRION data.
 */
'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchAPIOrNull } from './api';
import { SocketIOClient, SocketIOStatus } from './socketio';

/**
 * useAPI — fetch an endpoint on mount and every `interval` ms (default: no polling).
 */
export function useAPI<T = any>(path: string | null, interval?: number): {
  data: T | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
} {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(!!path);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(() => setTick(t => t + 1), []);

  useEffect(() => {
    if (!path) {
      setData(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchAPIOrNull<T>(path)
      .then(d => {
        if (cancelled) return;
        setData(d);
        setError(d === null ? 'No data' : null);
      })
      .catch(e => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [path, tick]);

  useEffect(() => {
    if (!path || !interval) return;
    const i = setInterval(() => setTick(t => t + 1), interval);
    return () => clearInterval(i);
  }, [path, interval]);

  return { data, loading, error, refresh };
}

/**
 * useMultiAPI — fetch multiple endpoints in parallel.
 */
export function useMultiAPI(paths: (string | null)[]): Record<number, any> {
  const [results, setResults] = useState<Record<number, any>>({});
  useEffect(() => {
    let cancelled = false;
    Promise.all(paths.map(p => p ? fetchAPIOrNull(p) : Promise.resolve(null)))
      .then(arr => {
        if (cancelled) return;
        const obj: Record<number, any> = {};
        arr.forEach((v, i) => { obj[i] = v; });
        setResults(obj);
      });
    return () => { cancelled = true; };
  }, [JSON.stringify(paths)]);
  return results;
}

/**
 * useStream — high-frequency polling hook for live BH/signal streams.
 * Default interval: 50ms (20 Hz) to visualize 0.006ms BH computation.
 */
export function useStream<T = any>(path: string | null, intervalMs = 2000): {
  items: T[];
  push: (item: T) => void;
  clear: () => void;
  speedMs: number;
} {
  const [items, setItems] = useState<T[]>([]);
  const [speedMs, setSpeedMs] = useState(0.006);
  const itemsRef = useRef<T[]>([]);
  const lastFetchRef = useRef<number>(Date.now());

  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  useEffect(() => {
    if (!path) return;
    const fetchOnce = async () => {
      const start = performance.now();
      const d = await fetchAPIOrNull<any>(path);
      const elapsed = performance.now() - start;
      if (d) {
        setSpeedMs(Math.max(0.006, elapsed));
        lastFetchRef.current = Date.now();
        // Append new items to the front (newest first), DEDUPLICATED by
        // identity key — the previous version prepended each poll's whole
        // array, so the same entries accumulated repeatedly until the
        // 100-item buffer was pure duplicates.
        const newItems = Array.isArray(d) ? d : (d.records || d.feed || d.bh || d.items || []);
        if (Array.isArray(newItems) && newItems.length > 0) {
          setItems(prev => {
            const seen = new Set<string>();
            const keyOf = (it: any): string => {
              if (it == null) return `n${seen.size}`;
              if (typeof it === 'object') {
                // Prefer stable identity fields; fall back to JSON for static items
                const k = it.id ?? it.tx_hash ?? it.hash ?? it.signal_id
                  ?? it.entity_id ?? it.timestamp ?? it.ts ?? it.block_num;
                if (k !== undefined && k !== null) return String(k);
              }
              return JSON.stringify(it);
            };
            const merged = [...newItems, ...prev];
            const out: typeof merged = [];
            for (const it of merged) {
              const k = keyOf(it);
              if (seen.has(k)) continue;
              seen.add(k);
              out.push(it);
              if (out.length >= 100) break;
            }
            return out;
          });
        }
      }
    };
    fetchOnce();
    const i = setInterval(fetchOnce, intervalMs);
    return () => clearInterval(i);
  }, [path, intervalMs]);

  const push = useCallback((item: T) => {
    setItems(prev => [item, ...prev].slice(0, 100));
  }, []);

  const clear = useCallback(() => setItems([]), []);

  return { items, push, clear, speedMs };
}

/**
 * useSocketFeed — live push from the backend's Flask-SocketIO layer
 * (serve.py wraps the Flask app with flask-socketio; api/socket_push.py
 * emits `signal` = new /api/v1/feed entries and `health` = stats packets
 * on the /feed namespace every few seconds).
 *
 * The client is the dependency-free Engine.IO v4 implementation in
 * lib/socketio.ts: reconnects with exponential backoff, answers engine.io
 * pings, and force-reconnects when the server stops pinging. When the
 * socket is down (or the deployment has no WebSocket path — e.g. Railway's
 * Next.js entry cannot proxy WS) views keep working via their normal
 * useStream polling, so this hook is a strict enhancement, never a
 * dependency. Dedupes by entity_id+timestamp against entries the poller
 * already fetched.
 */
export function useSocketFeed(namespace = '/feed'): {
  connected: boolean;
  status: SocketIOStatus;
  signals: any[];
  health: any | null;
  lastEventAt: number | null;
} {
  const [status, setStatus] = useState<SocketIOStatus>('disconnected');
  const [signals, setSignals] = useState<any[]>([]);
  const [health, setHealth] = useState<any | null>(null);
  const [lastEventAt, setLastEventAt] = useState<number | null>(null);

  useEffect(() => {
    const client = new SocketIOClient({ namespace });
    const keyOf = (s: any) => `${s?.entity_id ?? ''}:${s?.timestamp ?? ''}`;
    client.on('status', (s: SocketIOStatus) => setStatus(s));
    client.on('health', (h: any) => {
      setHealth(h);
      setLastEventAt(Date.now());
    });
    client.on('signal', (e: any) => {
      setLastEventAt(Date.now());
      setSignals(prev => {
        const k = keyOf(e);
        if (prev.some(p => keyOf(p) === k)) return prev;
        return [e, ...prev].slice(0, 100);
      });
    });
    client.connect();
    return () => client.close();
  }, [namespace]);

  return { connected: status === 'connected', status, signals, health, lastEventAt };
}

/**
 * useCounter — animated counter that smoothly increments toward a target value.
 */
export function useCounter(target: number, durationMs = 800): number {
  const [value, setValue] = useState(0);
  const startRef = useRef<number | null>(null);
  const fromRef = useRef(0);

  useEffect(() => {
    fromRef.current = value;
    startRef.current = null;
    let raf: number;
    const step = (ts: number) => {
      if (startRef.current === null) startRef.current = ts;
      const elapsed = ts - startRef.current;
      const progress = Math.min(elapsed / durationMs, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(fromRef.current + (target - fromRef.current) * eased);
      if (progress < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, durationMs]);

  return value;
}

/**
 * useTheme — dark/light toggle persisted to localStorage.
 */
export function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState('dark');
  useEffect(() => {
    const saved = localStorage.getItem('trion-theme') || 'dark';
    setTheme(saved);
    document.documentElement.classList.toggle('dark', saved === 'dark');
  }, []);
  const toggle = useCallback(() => {
    setTheme(prev => {
      const next = prev === 'dark' ? 'light' : 'dark';
      localStorage.setItem('trion-theme', next);
      document.documentElement.classList.toggle('dark', next === 'dark');
      return next;
    });
  }, []);
  return [theme, toggle];
}
