'use client';

import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { BRTData } from '@/lib/types';
import { Orbit } from 'lucide-react';

// L6.2 — Biological Rhythm Timer. Every TRIONSignal carries these four
// phases per the whitepaper; previously the dashboard displayed raw
// timestamps only (TRION_AUDIT_REPORT.md finding M4). This surfaces the
// same circadian/ultradian/lunar/seasonal phases the oracle publishes.
const PHASES: Array<{ key: keyof BRTData['brt']; label: string; labelKey: keyof BRTData['phase_labels']; color: string }> = [
  { key: 'circadian_phase', label: 'Circadian', labelKey: 'circadian', color: '#00c2ff' },
  { key: 'ultradian_phase', label: 'Ultradian', labelKey: 'ultradian', color: '#9f67f5' },
  { key: 'lunar_phase', label: 'Lunar', labelKey: 'lunar', color: '#22c55e' },
  { key: 'seasonal_phase', label: 'Seasonal', labelKey: 'seasonal', color: '#f59e0b' },
];

export default function BiologicalTime() {
  const { data } = useSWR<BRTData>(endpoints.brt, fetchJSON, { refreshInterval: 15000 });

  return (
    <div className="card flex flex-col gap-3 p-4">
      <div className="flex items-center gap-2">
        <Orbit size={13} className="text-cyan" />
        <span className="text-[12px] font-semibold text-t1">Biological Rhythm Timer</span>
        <span className="text-[9px] text-t3 mono ml-auto">L6.2</span>
      </div>

      <div className="grid grid-cols-4 gap-2">
        {PHASES.map((p) => {
          // Server adds a per-entity offset to circadian/ultradian phases, so
          // raw values can land outside [0,1] — normalize with modulo before
          // rendering so the ring/percent never overshoots 100%.
          const raw = data?.brt?.[p.key] ?? 0;
          const value = ((raw % 1) + 1) % 1;
          const pct = Math.round(value * 100);
          return (
            <div key={p.key} className="flex flex-col items-center gap-1">
              <div className="relative w-10 h-10">
                <svg viewBox="0 0 36 36" className="w-10 h-10 -rotate-90">
                  <circle cx="18" cy="18" r="15" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="3" />
                  <circle
                    cx="18" cy="18" r="15" fill="none"
                    stroke={p.color} strokeWidth="3"
                    strokeDasharray={`${pct * 0.942} 200`}
                    strokeLinecap="round"
                  />
                </svg>
                <span className="absolute inset-0 flex items-center justify-center text-[9px] mono text-t1">
                  {pct}%
                </span>
              </div>
              <span className="text-[9px] text-t3 uppercase tracking-wide">{p.label}</span>
              <span className="text-[9px] mono text-t2 truncate max-w-[64px]" title={data?.phase_labels?.[p.labelKey]}>
                {data?.phase_labels?.[p.labelKey] ?? '—'}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
