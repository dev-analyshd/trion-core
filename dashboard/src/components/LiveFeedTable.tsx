'use client';

import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { FeedData, FeedEntry } from '@/lib/types';
import CoherenceMeter from './CoherenceMeter';
import clsx from 'clsx';
import { formatDistanceToNow } from 'date-fns';
import { Activity } from 'lucide-react';

const ARCH_COLORS: Record<string, string> = {
  Hero: 'text-cyan border-cyan/30 bg-cyan/5',
  Sage: 'text-violet-400 border-violet-400/30 bg-violet-400/5',
  Outlaw: 'text-red-400 border-red-400/30 bg-red-400/5',
  Jester: 'text-amber-400 border-amber-400/30 bg-amber-400/5',
  Innocent: 'text-green-400 border-green-400/30 bg-green-400/5',
  Lover: 'text-pink-400 border-pink-400/30 bg-pink-400/5',
  Regular: 'text-t2 border-border bg-card2',
};

function ArchBadge({ arch }: { arch: string }) {
  return (
    <span className={clsx('px-1.5 py-0.5 rounded border text-[9px] font-semibold tracking-wide uppercase', ARCH_COLORS[arch] ?? ARCH_COLORS.Regular)}>
      {arch}
    </span>
  );
}

function SignalBadge({ coherent, type }: { coherent: boolean; type?: string }) {
  if (coherent) {
    return <span className="px-1.5 py-0.5 rounded border border-green-500/30 bg-green-500/5 text-green-400 text-[9px] font-semibold uppercase">EMIT</span>;
  }
  return <span className="px-1.5 py-0.5 rounded border border-t3/30 bg-card2 text-t3 text-[9px] font-semibold uppercase">SILENCE</span>;
}

interface Props {
  limit?: number;
  compact?: boolean;
}

export default function LiveFeedTable({ limit = 20, compact = false }: Props) {
  const { data, isLoading } = useSWR<FeedData>(endpoints.feed, fetchJSON, {
    refreshInterval: 3000,
  });

  const entries = (data?.feed ?? []).slice(0, limit);

  return (
    <div className="card flex flex-col overflow-hidden h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <Activity size={13} className="text-cyan" />
          <span className="text-[12px] font-semibold text-t1">Live Signal Feed</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-blink" />
          <span className="text-[10px] text-green-400 font-medium">LIVE</span>
        </div>
      </div>

      <div className="overflow-y-auto scrollable flex-1">
        {isLoading ? (
          <div className="p-4 space-y-2">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-10 bg-border rounded animate-pulse" />
            ))}
          </div>
        ) : (
          <table className="w-full">
            <thead className="sticky top-0 bg-card z-10">
              <tr className="border-b border-border">
                <th className="text-left px-4 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">Entity</th>
                <th className="text-left px-3 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">Archetype</th>
                {!compact && <th className="text-left px-3 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">Plane</th>}
                <th className="text-left px-3 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">C(t)</th>
                <th className="text-left px-3 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase hidden md:table-cell">Signal</th>
                {!compact && <th className="text-right px-4 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase hidden lg:table-cell">Age</th>}
              </tr>
            </thead>
            <tbody>
              {entries.map((e: FeedEntry, i) => (
                <tr
                  key={`${e.entity_id}-${e.timestamp}-${i}`}
                  className="border-b border-border/50 hover:bg-card2 transition-colors"
                >
                  <td className="px-4 py-2.5">
                    <span className="mono text-[11px] text-t1 truncate block max-w-[140px]" title={e.entity_id}>
                      {e.short_id || e.entity_id}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    <ArchBadge arch={e.archetype} />
                  </td>
                  {!compact && (
                    <td className="px-3 py-2.5 text-[11px] text-t2">{e.limiting_plane}</td>
                  )}
                  <td className="px-3 py-2.5 min-w-[120px]">
                    <CoherenceMeter score={e.coherence_score} threshold={e.threshold} size="sm" />
                  </td>
                  <td className="px-3 py-2.5 hidden md:table-cell">
                    <SignalBadge coherent={e.coherent} />
                  </td>
                  {!compact && (
                    <td className="px-4 py-2.5 text-right text-[10px] text-t3 hidden lg:table-cell">
                      {formatDistanceToNow(new Date(e.timestamp * 1000), { addSuffix: true })}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
