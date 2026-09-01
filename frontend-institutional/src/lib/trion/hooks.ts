"use client";

import { useEffect, useRef, useState } from "react";
import { trionGet } from "./client";

/**
 * useTrionPoll — interval-polled GET hook with live/loaded/error state.
 * Mirrors the reference dashboard's useAPI pattern: the Flask backend has
 * no WebSocket for every dataset, so short-interval polling keeps views live.
 */
export function useTrionPoll<T>(
  path: string | null,
  intervalMs = 4000,
  deps: unknown[] = []
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    if (!path) {
      setLoading(false);
      return;
    }

    let timer: ReturnType<typeof setTimeout> | undefined;

    const tick = async () => {
      try {
        const d = await trionGet<T>(path);
        if (!alive.current) return;
        setData(d);
        setError(null);
        setLastUpdated(Date.now());
      } catch (e) {
        if (!alive.current) return;
        setError(e instanceof Error ? e.message : "request failed");
      } finally {
        if (!alive.current) return;
        setLoading(false);
        if (intervalMs > 0) timer = setTimeout(tick, intervalMs);
      }
    };

    setLoading(true);
    tick();

    return () => {
      alive.current = false;
      if (timer) clearTimeout(timer);
    };
  }, [path, intervalMs, ...deps]);

  return { data, error, loading, lastUpdated };
}
