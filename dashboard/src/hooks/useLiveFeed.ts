'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { FeedData, FeedEntry } from '@/lib/types';

type ConnState = 'connecting' | 'live' | 'error' | 'polling';

export function useLiveFeed(limit = 50) {
  const [entries, setEntries] = useState<FeedEntry[]>([]);
  const [connState, setConnState] = useState<ConnState>('connecting');
  const [newCount, setNewCount] = useState(0);
  const seenRef = useRef(new Set<string>());
  const esRef = useRef<EventSource | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const addEntries = useCallback((incoming: FeedEntry[]) => {
    const novel: FeedEntry[] = [];
    for (const e of incoming) {
      const key = `${e.entity_id}-${e.timestamp}`;
      if (!seenRef.current.has(key)) {
        seenRef.current.add(key);
        novel.push(e);
      }
    }
    if (novel.length === 0) return;

    setNewCount(c => c + novel.length);
    setEntries(prev => {
      const next = [...novel, ...prev].slice(0, limit);
      return next;
    });

    if (seenRef.current.size > 800) {
      const arr = [...seenRef.current];
      arr.slice(0, 300).forEach(k => seenRef.current.delete(k));
    }
  }, [limit]);

  const { data: seedData } = useSWR<FeedData>(
    connState === 'error' || connState === 'polling' ? endpoints.feed : null,
    fetchJSON,
    { refreshInterval: connState === 'polling' ? 5000 : 0 }
  );

  useEffect(() => {
    if (seedData?.feed) addEntries(seedData.feed);
  }, [seedData, addEntries]);

  const { data: initialData } = useSWR<FeedData>(endpoints.feed, fetchJSON, {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
  });

  useEffect(() => {
    if (initialData?.feed && entries.length === 0) {
      addEntries(initialData.feed.slice(0, limit));
    }
  }, [initialData, entries.length, addEntries, limit]);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (esRef.current) { esRef.current.close(); esRef.current = null; }

    setConnState('connecting');
    const es = new EventSource('/api/live-feed');
    esRef.current = es;

    es.onopen = () => {
      if (mountedRef.current) setConnState('live');
    };

    es.onmessage = (evt) => {
      if (!mountedRef.current) return;
      try {
        const msg = JSON.parse(evt.data);
        if (msg.type === 'connected') setConnState('live');
        if (msg.type === 'signal') addEntries([msg.data as FeedEntry]);
      } catch { /* malformed */ }
    };

    es.onerror = () => {
      if (!mountedRef.current) return;
      es.close();
      esRef.current = null;
      setConnState('error');
      retryRef.current = setTimeout(() => {
        if (mountedRef.current) connect();
      }, 8000);
    };
  }, [addEntries]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      esRef.current?.close();
      esRef.current = null;
      if (retryRef.current) clearTimeout(retryRef.current);
    };
  }, [connect]);

  return { entries, connState, newCount };
}
