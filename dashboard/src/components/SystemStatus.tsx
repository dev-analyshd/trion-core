'use client';

import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { HealthData } from '@/lib/types';
import clsx from 'clsx';
import { CheckCircle, XCircle, Shield } from 'lucide-react';

function StatusRow({ label, value, ok, mono = false }: { label: string; value: string; ok?: boolean; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border/50 last:border-0">
      <div className="flex items-center gap-2">
        {ok !== undefined ? (
          ok
            ? <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
            : <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
        ) : (
          <span className="w-1.5 h-1.5 rounded-full bg-t3" />
        )}
        <span className="text-[11px] text-t2">{label}</span>
      </div>
      <span className={clsx('text-[11px] text-t1 font-medium', mono && 'mono text-[10px]')}>{value}</span>
    </div>
  );
}

export default function SystemStatus() {
  const { data, isLoading } = useSWR<HealthData>(endpoints.health, fetchJSON, { refreshInterval: 5000 });

  const healthy = data?.status === 'healthy';

  return (
    <div className="card p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Shield size={13} className="text-cyan" />
          <span className="text-[12px] font-semibold text-t1">System Status</span>
        </div>
        <span
          className={clsx(
            'px-2 py-0.5 rounded border text-[10px] font-semibold uppercase',
            healthy
              ? 'border-green-500/40 bg-green-500/5 text-green-400'
              : 'border-amber-500/40 bg-amber-500/5 text-amber-400'
          )}
        >
          {isLoading ? '...' : data?.status?.toUpperCase()}
        </span>
      </div>

      <div>
        <StatusRow label="Oracle API" value={data?.oracle ?? '—'} ok={healthy} />
        <StatusRow
          label="Blockchain"
          value={data?.network ?? '—'}
          ok={data?.block_number ? data.block_number > 0 : false}
        />
        <StatusRow
          label="Security Gate"
          value={data?.dynamic_threshold ? data.dynamic_threshold.toFixed(3) : '—'}
          ok={true}
        />
        <StatusRow
          label="Contract"
          value={data?.contract ? `${data.contract.slice(0, 8)}…${data.contract.slice(-4)}` : '—'}
          ok={healthy}
          mono
        />
        <StatusRow
          label="Signals On-chain"
          value={data?.total_signals_onchain?.toString() ?? '0'}
          ok={true}
        />
      </div>
    </div>
  );
}
