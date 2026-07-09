'use client';

import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { SelfVerificationData } from '@/lib/types';
import { AlertTriangle } from 'lucide-react';

export default function SelfHaltBanner() {
  const { data } = useSWR<SelfVerificationData>(endpoints.self, fetchJSON, {
    refreshInterval: 5000,
    shouldRetryOnError: false,
  });

  if (!data || data.status !== 'SILENCED') return null;

  return (
    <div className="flex items-center gap-2.5 px-5 py-2 bg-red-500/10 border-b border-red-500/40 text-red-400 flex-shrink-0">
      <AlertTriangle size={14} className="flex-shrink-0 animate-pulse" />
      <span className="text-[12px] font-semibold uppercase tracking-wide">TRION Self-Silenced</span>
      <span className="text-[11px] text-red-300/80">
        Self-coherence {data.coherence.toFixed(3)} below threshold — limiting plane:{' '}
        {data.limiting_plane} — all relayers have paused outbound publishing until coherence recovers.
      </span>
    </div>
  );
}
