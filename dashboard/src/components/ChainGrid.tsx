'use client';

import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { ChainsData, Chain } from '@/lib/types';
import clsx from 'clsx';
import { Network } from 'lucide-react';
import { useState } from 'react';

const VM_COLORS: Record<string, string> = {
  EVM: 'text-cyan border-cyan/25',
  SVM: 'text-violet-400 border-violet-400/25',
  MVM: 'text-green-400 border-green-400/25',
  'UTXO-based': 'text-amber-400 border-amber-400/25',
  CosmWasm: 'text-orange-400 border-orange-400/25',
  TVM: 'text-pink-400 border-pink-400/25',
  NEAR: 'text-blue-400 border-blue-400/25',
  SUI: 'text-teal-400 border-teal-400/25',
};

const STATUS_DOT: Record<string, string> = {
  live: 'bg-green-400',
  testnet: 'bg-amber-400',
  pending: 'bg-t3',
};

interface Props { filterVm?: string; compact?: boolean; }

export default function ChainGrid({ filterVm, compact = false }: Props) {
  const { data, isLoading } = useSWR<ChainsData>(endpoints.chains, fetchJSON, { refreshInterval: 30000 });
  const [filter, setFilter] = useState<string>('');

  const chains = (data?.chains ?? []).filter(c =>
    (!filterVm || c.vm === filterVm) &&
    (!filter || c.name.toLowerCase().includes(filter.toLowerCase()) || c.vm.toLowerCase().includes(filter.toLowerCase()))
  );

  const vmTypes = [...new Set((data?.chains ?? []).map(c => c.vm))];

  return (
    <div className="card flex flex-col overflow-hidden h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <Network size={13} className="text-cyan" />
          <span className="text-[12px] font-semibold text-t1">Chain Network</span>
          <span className="text-[10px] text-t3 bg-card2 border border-border px-1.5 py-0.5 rounded mono">
            {chains.length}/{data?.chains?.length ?? 0}
          </span>
        </div>
        {!compact && (
          <input
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Filter chains…"
            className="bg-card2 border border-border rounded px-2.5 py-1 text-[11px] text-t1 placeholder-t3 outline-none focus:border-cyan/50 w-32"
          />
        )}
      </div>

      {!compact && !filterVm && (
        <div className="flex gap-1.5 px-4 py-2 border-b border-border flex-wrap flex-shrink-0">
          {vmTypes.map(vm => (
            <button
              key={vm}
              className={clsx('px-2 py-0.5 rounded border text-[10px] font-medium transition-colors', VM_COLORS[vm] ?? 'text-t2 border-border')}
            >
              {vm}
            </button>
          ))}
        </div>
      )}

      <div className="overflow-y-auto scrollable flex-1 p-3">
        {isLoading ? (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {[...Array(12)].map((_, i) => (
              <div key={i} className="h-16 bg-border rounded animate-pulse" />
            ))}
          </div>
        ) : (
          <div className={clsx('grid gap-2', compact ? 'grid-cols-2 sm:grid-cols-3' : 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4')}>
            {chains.map((c: Chain) => (
              <div
                key={c.id}
                className="bg-card2 border border-border rounded p-2.5 hover:border-border2 transition-colors group"
                title={c.note}
              >
                <div className="flex items-start justify-between gap-1 mb-1">
                  <span className={clsx('text-[9px] font-semibold px-1 py-0.5 rounded border', VM_COLORS[c.vm] ?? 'text-t2 border-border')}>
                    {c.vm}
                  </span>
                  <span className={clsx('w-1.5 h-1.5 rounded-full flex-shrink-0 mt-0.5', STATUS_DOT[c.status] ?? 'bg-t3')} />
                </div>
                <p className="text-[11px] font-medium text-t1 leading-tight group-hover:text-cyan transition-colors truncate">
                  {c.name}
                </p>
                <p className="text-[10px] mono text-t3 mt-0.5">
                  {c.chain_id > 0 ? `Chain ${c.chain_id}` : c.id}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
