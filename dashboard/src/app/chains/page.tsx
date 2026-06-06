'use client';

import Topbar from '@/components/Topbar';
import ChainGrid from '@/components/ChainGrid';
import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { ChainsData } from '@/lib/types';

export default function ChainsPage() {
  const { data } = useSWR<ChainsData>(endpoints.chains, fetchJSON, { refreshInterval: 30000 });

  const total = data?.chains?.length ?? 0;
  const live = data?.chains?.filter(c => c.status === 'live').length ?? 0;
  const vmTypes = [...new Set((data?.chains ?? []).map(c => c.vm))];

  return (
    <>
      <Topbar title="Chain Network" />
      <div className="flex-1 overflow-hidden p-5 flex flex-col gap-4">
        {/* Summary strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 flex-shrink-0">
          {[
            { label: 'Total Chains', value: total, color: 'text-cyan' },
            { label: 'Live', value: live, color: 'text-green-400' },
            { label: 'VM Families', value: vmTypes.length, color: 'text-violet-400' },
            { label: 'Rust Indexers', value: 13, color: 'text-amber-400' },
          ].map(({ label, value, color }) => (
            <div key={label} className="card p-3 text-center">
              <p className={`text-2xl font-bold mono ${color}`}>{value}</p>
              <p className="text-[10px] text-t3 uppercase tracking-wide mt-0.5">{label}</p>
            </div>
          ))}
        </div>

        {/* Chain grid */}
        <div className="flex-1 overflow-hidden">
          <ChainGrid />
        </div>
      </div>
    </>
  );
}
