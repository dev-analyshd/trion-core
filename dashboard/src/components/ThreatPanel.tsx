'use client';

import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { FeedData, HealthData } from '@/lib/types';
import { AlertTriangle } from 'lucide-react';
import clsx from 'clsx';

export default function ThreatPanel() {
  const { data: feed } = useSWR<FeedData>(endpoints.feed, fetchJSON, { refreshInterval: 5000 });
  const { data: health } = useSWR<HealthData>(endpoints.health, fetchJSON, { refreshInterval: 5000 });

  const entries = feed?.feed ?? [];
  const recent = entries.slice(0, 50);
  const silenceCount = recent.filter(e => !e.coherent).length;
  const emitCount = recent.filter(e => e.coherent).length;
  const intercepted = recent.filter(e => e.coherence_score < 0.4).length;

  const threshold = health?.dynamic_threshold ?? 0.55;
  const volatility = health?.market_volatility ?? 0;

  return (
    <div className="card p-4 flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <AlertTriangle size={13} className="text-amber-400" />
        <span className="text-[12px] font-semibold text-t1">Session Threat Counts</span>
      </div>

      <div className="grid grid-cols-3 gap-2">
        {[
          { label: 'INTERCEPTED', value: intercepted, color: 'text-red-400' },
          { label: 'SILENCE', value: silenceCount, color: 'text-amber-400' },
          { label: 'ACTIVE', value: emitCount, color: 'text-green-400' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-card2 border border-border rounded p-2.5 text-center">
            <p className={clsx('text-xl font-bold mono', color)}>{value}</p>
            <p className="text-[9px] tracking-[0.12em] text-t3 uppercase mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-1.5 pt-1">
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-t2">Security Threshold</span>
          <span className="px-1.5 py-0.5 rounded border border-violet-400/30 bg-violet-400/5 text-violet-400 text-[9px] font-semibold uppercase">DYNAMIC</span>
        </div>
        <div className="flex justify-between text-[11px]">
          <span className="text-t3">Θ(t) Current</span>
          <span className="mono text-t1">{threshold.toFixed(3)}</span>
        </div>
        <div className="flex justify-between text-[11px]">
          <span className="text-t3">Volatility V(t)</span>
          <span className="mono text-t1">{volatility.toFixed(3)}</span>
        </div>
        <div className="flex justify-between text-[11px]">
          <span className="text-t3">Formula</span>
          <span className="mono text-[10px] text-t2">Θ = 0.55 + 0.37×V(t)</span>
        </div>
        <div className="relative h-1.5 bg-border rounded-full overflow-hidden mt-1">
          <div
            className="h-full rounded-full bg-gradient-to-r from-violet-500 to-cyan"
            style={{ width: `${Math.min(100, threshold * 100)}%` }}
          />
        </div>
      </div>
    </div>
  );
}
