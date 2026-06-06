'use client';

import Topbar from '@/components/Topbar';
import AnimaStats from '@/components/AnimaStats';
import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { ArchetypesData } from '@/lib/types';
import clsx from 'clsx';

const RISK_COLORS: Record<string, string> = {
  SAFE: 'text-green-400 border-green-400/30 bg-green-400/5',
  CAUTION: 'text-amber-400 border-amber-400/30 bg-amber-400/5',
  DANGER: 'text-red-400 border-red-400/30 bg-red-400/5',
  EXTREME_DANGER: 'text-red-500 border-red-500/40 bg-red-500/10',
};

const SIG_COLORS: Record<string, string> = {
  BUY: 'text-green-400',
  SELL: 'text-red-400',
  HOLD: 'text-amber-400',
  EXTREME_SELL: 'text-red-500',
};

export default function AnimaPage() {
  const { data } = useSWR<ArchetypesData>(endpoints.archetypes, fetchJSON, { refreshInterval: 60000 });

  const archetypes = data?.archetypes ?? [];

  return (
    <>
      <Topbar title="FAISS ANIMA Engine" />
      <div className="flex-1 overflow-hidden p-5 flex gap-4">
        <div className="w-72 flex-shrink-0">
          <AnimaStats />
        </div>

        <div className="flex-1 overflow-hidden card flex flex-col">
          <div className="px-4 py-3 border-b border-border flex-shrink-0">
            <p className="text-[12px] font-semibold text-t1">Behavioral Archetypes ({archetypes.length})</p>
            <p className="text-[10px] text-t3 mt-0.5">64 trained FAISS archetypes · k-NN matching in 128-dim space</p>
          </div>
          <div className="overflow-y-auto scrollable flex-1">
            <table className="w-full">
              <thead className="sticky top-0 bg-card z-10">
                <tr className="border-b border-border">
                  {['Archetype', 'Risk', 'Signal', 'Confidence', 'Lifecycle', 'Examples'].map(h => (
                    <th key={h} className="text-left px-4 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {archetypes.map(a => (
                  <tr key={a.id} className="border-b border-border/50 hover:bg-card2 transition-colors">
                    <td className="px-4 py-2.5">
                      <p className="text-[11px] font-semibold text-t1">{a.name}</p>
                      <p className="text-[10px] text-t3 max-w-[160px] truncate">{a.description}</p>
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={clsx('text-[9px] font-semibold px-1.5 py-0.5 rounded border uppercase', RISK_COLORS[a.risk_level] ?? 'text-t2 border-border')}>
                        {a.risk_level}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={clsx('text-[11px] font-bold', SIG_COLORS[a.investment_signal] ?? 'text-t2')}>
                        {a.investment_signal}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-border rounded-full overflow-hidden">
                          <div
                            className="h-full bg-cyan rounded-full"
                            style={{ width: `${a.investment_confidence * 100}%` }}
                          />
                        </div>
                        <span className="text-[11px] mono text-t2">{(a.investment_confidence * 100).toFixed(0)}%</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex gap-1 flex-wrap">
                        {a.lifecycle.map(l => (
                          <span key={l} className="text-[9px] px-1 py-0.5 bg-card2 border border-border rounded text-t3">{l}</span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-[11px] text-t3">
                      {a.examples?.slice(0, 2).join(', ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
