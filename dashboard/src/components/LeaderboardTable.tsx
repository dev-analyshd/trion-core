'use client';

import React from 'react';
import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { LeaderboardData, LeaderboardEntry } from '@/lib/types';
import CoherenceMeter from './CoherenceMeter';
import PlaneBars from './PlaneBars';
import clsx from 'clsx';
import { Trophy, ChevronRight } from 'lucide-react';
import { useState } from 'react';

const ARCH_COLORS: Record<string, string> = {
  Hero: 'text-cyan', Sage: 'text-violet-400', Outlaw: 'text-red-400',
  Jester: 'text-amber-400', Innocent: 'text-green-400', Lover: 'text-pink-400',
  Regular: 'text-t2',
};

interface Props { compact?: boolean; limit?: number; }

export default function LeaderboardTable({ compact = false, limit = 10 }: Props) {
  const { data, isLoading } = useSWR<LeaderboardData>(endpoints.leaderboard, fetchJSON, { refreshInterval: 15000 });
  const [expanded, setExpanded] = useState<string | null>(null);

  const entries = (data?.leaderboard ?? []).slice(0, limit);
  const threshold = data?.dynamic_threshold ?? 0.55;

  return (
    <div className="card flex flex-col overflow-hidden h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <Trophy size={13} className="text-amber-400" />
          <span className="text-[12px] font-semibold text-t1">Trust Leaderboard</span>
        </div>
        <span className="text-[10px] text-t3 px-2 py-0.5 bg-card2 border border-border rounded">TOP {limit}</span>
      </div>

      <div className="overflow-y-auto scrollable flex-1">
        {isLoading ? (
          <div className="p-4 space-y-2">
            {[...Array(5)].map((_, i) => <div key={i} className="h-12 bg-border rounded animate-pulse" />)}
          </div>
        ) : (
          <table className="w-full">
            <thead className="sticky top-0 bg-card z-10">
              <tr className="border-b border-border">
                <th className="text-left px-4 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase w-8">#</th>
                <th className="text-left px-3 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">Entity</th>
                <th className="text-left px-3 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase hidden md:table-cell">Type</th>
                <th className="text-left px-3 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">C(t)</th>
                {!compact && <th className="text-right px-4 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase hidden lg:table-cell">Signals</th>}
              </tr>
            </thead>
            <tbody>
              {entries.map((e: LeaderboardEntry) => (
                <React.Fragment key={e.entity_id}>
                  <tr
                    className="border-b border-border/50 hover:bg-card2 transition-colors cursor-pointer"
                    onClick={() => setExpanded(expanded === e.entity_id ? null : e.entity_id)}
                  >
                    <td className="px-4 py-2.5">
                      <span className="mono text-[11px] text-t3">{e.rank}</span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="text-[11px] text-t1 font-medium truncate block max-w-[150px]" title={e.entity_id}>
                        {e.label || e.entity_id.slice(0, 20)}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 hidden md:table-cell">
                      <span className={clsx('text-[11px] font-semibold', ARCH_COLORS[e.archetype] ?? 'text-t2')}>
                        {e.archetype}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 min-w-[120px]">
                      <CoherenceMeter score={e.coherence_score} threshold={threshold} size="sm" />
                    </td>
                    {!compact && (
                      <td className="px-4 py-2.5 text-right hidden lg:table-cell">
                        <span className="text-[11px] mono text-t2">{e.signal_count}</span>
                      </td>
                    )}
                  </tr>
                  {expanded === e.entity_id && (
                    <tr key={`${e.entity_id}-exp`} className="bg-card2 border-b border-border">
                      <td colSpan={compact ? 4 : 5} className="px-4 py-3">
                        <PlaneBars planes={e.plane_breakdown} threshold={0.55} compact />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
