/**
 * React hooks for streaming live TRION data.
 */
'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchAPIOrNull } from './api';

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
        // Append new items to the front (newest first)
        const newItems = Array.isArray(d) ? d : (d.records || d.feed || d.bh || d.items || []);
        if (Array.isArray(newItems) && newItems.length > 0) {
          setItems(prev => {
            const merged = [...newItems, ...prev].slice(0, 100);
            return merged;
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

/**
 * useWebSocket — real-time streaming with auto-reconnect + polling fallback.
 *
 * Phase 3.1: If `config.wsUrl` is set, opens a WebSocket. On repeated failure
 * or when no WS URL is configured, falls back to polling via useAPI at
 * `fallbackInterval` (default 2000ms).
 *
 * - Exponential backoff: 1s → 2s → 4s → 8s → 16s → 30s (capped)
 * - Message buffer capped at 100 (newest first)
 * - Exposes `connected`, `messages`, `send`, `reconnect`
 */
export function useWebSocket<T = any>(
  path: string | null,
  fallbackInterval?: number,
): {
  messages: T[];
  connected: boolean;
  send: (data: any) => void;
  reconnect: () => void;
} {
  const [messages, setMessages] = useState<T[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fallbackRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const connect = useCallback((wsPath: string) => {
    // Build full URL: config.wsUrl + path
    const wsBase = (typeof window !== 'undefined')
      ? (process.env.NEXT_PUBLIC_WS_URL || '')
      : '';
    if (!wsBase) {
      // No WS configured — caller should use polling fallback
      return;
    }
    const fullUrl = wsBase.replace(/\/$/, '') + wsPath;
    try {
      const ws = new WebSocket(fullUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectRef.current = 0;
        setConnected(true);
      };
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data) as T;
          setMessages(prev => [data, ...prev].slice(0, 100));
        } catch {
          // ignore malformed messages
        }
      };
      ws.onerror = () => {
        // error handler — close handler will trigger reconnect
      };
      ws.onclose = () => {
        setConnected(false);
        // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s (capped)
        const backoff = Math.min(30_000, 1000 * Math.pow(2, reconnectRef.current));
        reconnectRef.current += 1;
        if (reconnectRef.current <= 5) {
          reconnectTimerRef.current = setTimeout(() => connect(wsPath), backoff);
        }
        // After 5 failed reconnects, the polling fallback (below) takes over
      };
    } catch {
      // WebSocket constructor can throw on invalid URL
    }
  }, []);

  useEffect(() => {
    if (!path) {
      setMessages([]);
      return;
    }

    // Try WebSocket first
    const wsBase = (typeof window !== 'undefined')
      ? (process.env.NEXT_PUBLIC_WS_URL || '')
      : '';
    if (wsBase) {
      connect(path);
    }

    // Polling fallback — always runs in parallel. When WS is connected, the
    // polling results are mostly redundant but provide a safety net. When WS
    // is down, polling is the primary source.
    if (fallbackInterval) {
      fallbackRef.current = setInterval(async () => {
        const d = await fetchAPIOrNull<any>(path);
        if (d) {
          const newItems = Array.isArray(d) ? d : (d.records || d.feed || d.bh || d.items || []);
          if (Array.isArray(newItems) && newItems.length > 0) {
            setMessages(prev => {
              // Merge: only add items not already in the buffer (by id/timestamp)
              const existing = new Set(prev.map((m: any) => m?.id || m?.tx_hash || JSON.stringify(m)));
              const fresh = newItems.filter((m: any) => !existing.has(m?.id || m?.tx_hash || JSON.stringify(m)));
              return [...fresh, ...prev].slice(0, 100);
            });
          }
        }
      }, fallbackInterval);
    }

    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (fallbackRef.current) clearInterval(fallbackRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;  // prevent reconnect on unmount
        wsRef.current.close();
      }
    };
  }, [path, fallbackInterval, connect]);

  const send = useCallback((data: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const reconnect = useCallback(() => {
    reconnectRef.current = 0;
    if (path) connect(path);
  }, [path, connect]);

  return { messages, connected, send, reconnect };
}
