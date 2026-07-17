'use client';

import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { BackfillStatus, BackfillChain } from '@/lib/types';
import Topbar from '@/components/Topbar';
import { DownloadCloud, CheckCircle, AlertTriangle, Search } from 'lucide-react';
import clsx from 'clsx';
import { useState } from 'react';

function fmt(n: number | undefined): string {
  if (n == null) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

function ChainRow({ chain }: { chain: BackfillChain }) {
  const progress = chain.last_block ?? chain.last_height ?? 0;
  const indexed = chain.indexed ?? 0;
  const hasError = !!chain.error;

  return (
    <tr className="border-b border-border/50 hover:bg-card2 transition-colors">
      <td className="px-4 py-2.5">
        <span className="mono text-[11px] text-t1 font-medium">{chain.chain}</span>
      </td>
      <td className="px-3 py-2.5">
        {hasError ? (
          <AlertTriangle size={11} className="text-red-400" />
        ) : (
          <CheckCircle size={11} className="text-green-400" />
        )}
      </td>
      <td className="px-3 py-2.5">
        <span className="mono text-[11px] text-cyan">{fmt(progress)}</span>
        <span className="text-[10px] text-t3 ml-1">{chain.last_block != null ? 'blocks' : 'slots'}</span>
      </td>
      <td className="px-3 py-2.5">
        <span className="mono text-[11px] text-violet-400">{fmt(indexed)}</span>
        <span className="text-[10px] text-t3 ml-1">indexed</span>
      </td>
      <td className="px-3 py-2.5 text-[10px] text-t3">
        {chain.error ?? (chain.gaps && Array.isArray(chain.gaps) && chain.gaps.length > 0 ? `${chain.gaps.length} gaps` : 'no gaps')}
      </td>
    </tr>
  );
}

export default function BackfillPage() {
  const { data, isLoading, error } = useSWR<BackfillStatus>(
    endpoints.backfillStatus, fetchJSON, { refreshInterval: 30000 }
  );
  const [filter, setFilter] = useState('');

  const chains = (data?.chains ?? []).filter(c =>
    filter ? c.chain.toLowerCase().includes(filter.toLowerCase()) : true
  );

  const okCount  = (data?.chains ?? []).filter(c => !c.error).length;
  const errCount = (data?.chains ?? []).filter(c => !!c.error).length;

  return (
    <>
      <Topbar title="Genesis Backfill" />
      <div className="flex-1 overflow-hidden p-5 flex flex-col gap-4">

        {/* Summary strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 flex-shrink-0">
          {[
            { label: 'Chains Tracked', value: data?.total_chains ?? 0,  color: 'text-cyan'      },
            { label: 'Running',        value: okCount,                   color: 'text-green-400' },
            { label: 'Errors',         value: errCount,                  color: errCount > 0 ? 'text-red-400' : 'text-t3' },
            { label: 'Total Indexed',  value: fmt(data?.total_indexed),  color: 'text-violet-400'},
          ].map(({ label, value, color }) => (
            <div key={label} className="card p-3 text-center">
              <p className={clsx('text-2xl font-bold mono', color)}>{isLoading ? '—' : value}</p>
              <p className="text-[10px] text-t3 uppercase tracking-wide mt-0.5">{label}</p>
            </div>
          ))}
        </div>

        {/* Description */}
        <div className="card p-4 flex-shrink-0">
          <div className="flex items-center gap-2 mb-2">
            <DownloadCloud size={13} className="text-cyan" />
            <span className="text-[12px] font-semibold text-t1">Genesis-to-Tip Backfill</span>
          </div>
          <p className="text-[11px] text-t2 leading-relaxed">
            Walking every integrated L1/L2 and VM from genesis, per whitepaper mandate — zero gaps.
            Each chain has an independent checkpoint file so progress survives restarts.
            Full-history indexing of large chains (ETH, Aptos, Solana) is a continuous multi-day effort;
            the runner loops forever, backfilling new blocks as they are produced.
          </p>
        </div>

        {error && (
          <div className="card p-4 border-red-500/20 bg-red-500/5 flex-shrink-0">
            <p className="text-red-400 text-[12px]">Failed to load backfill status: {error.message}</p>
          </div>
        )}

        {/* Chain table */}
        <div className="card flex flex-col overflow-hidden flex-1">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0 gap-3">
            <div className="flex items-center gap-2">
              <DownloadCloud size={13} className="text-cyan" />
              <span className="text-[12px] font-semibold text-t1">Chain Progress</span>
              {data && <span className="text-[10px] text-t3">{chains.length} chains</span>}
            </div>
            <div className="relative w-48">
              <Search size={11} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-t3" />
              <input
                value={filter}
                onChange={e => setFilter(e.target.value)}
                placeholder="Filter chains…"
                className="w-full bg-card2 border border-border rounded pl-7 pr-3 py-1.5 text-[11px] text-t1 placeholder-t3 focus:outline-none focus:border-cyan/40"
              />
            </div>
          </div>

          <div className="overflow-y-auto scrollable flex-1">
            {isLoading && (
              <div className="p-4 space-y-2">
                {[...Array(8)].map((_, i) => <div key={i} className="h-10 bg-border rounded animate-pulse" />)}
              </div>
            )}
            {!isLoading && chains.length > 0 && (
              <table className="w-full">
                <thead className="sticky top-0 bg-card z-10">
                  <tr className="border-b border-border">
                    {['Chain', 'Status', 'Progress', 'Indexed', 'Notes'].map(h => (
                      <th key={h} className="text-left px-4 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {chains.map(c => <ChainRow key={c.chain} chain={c} />)}
                </tbody>
              </table>
            )}
            {!isLoading && chains.length === 0 && (
              <div className="p-8 text-center text-t3 text-[12px]">
                {filter ? 'No chains match filter' : 'No backfill checkpoints found yet'}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
