'use client';

import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { HealthData } from '@/lib/types';
import { formatDistanceToNow } from 'date-fns';
import { Wifi, WifiOff } from 'lucide-react';
import clsx from 'clsx';

interface Props {
  title: string;
}

export default function Topbar({ title }: Props) {
  const { data } = useSWR<HealthData>(endpoints.health, fetchJSON, { refreshInterval: 5000 });

  const healthy = data?.status === 'healthy';
  const ts = data?.timestamp ? new Date(data.timestamp * 1000) : null;

  return (
    <header className="h-14 border-b border-border flex items-center justify-between px-5 flex-shrink-0 bg-sidebar">
      <div className="flex items-center gap-3">
        <h1 className="text-[13px] font-semibold text-t1">{title}</h1>
      </div>

      <div className="flex items-center gap-2.5">
        {/* Chains live pill */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 border border-border rounded text-[11px] text-t2">
          <span className={clsx('w-1.5 h-1.5 rounded-full animate-blink', healthy ? 'bg-green-400' : 'bg-amber-400')} />
          37 Chains Live
        </div>

        {/* Block */}
        {data?.block_number ? (
          <div className="flex items-center gap-1.5 px-2.5 py-1 border border-border rounded text-[11px]">
            <span className="text-t3">Block</span>
            <span className="mono text-cyan">{data.block_number.toLocaleString()}</span>
          </div>
        ) : null}

        {/* Gate */}
        {data?.contract && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 border border-border rounded text-[11px]">
            <span className="text-t3">GATE</span>
            <span className="mono text-cyan text-[10px]">
              {data.contract.slice(0, 8)}…{data.contract.slice(-4)}
            </span>
          </div>
        )}

        {/* WS / status */}
        <div
          className={clsx(
            'flex items-center gap-1 px-2 py-1 rounded border text-[11px] font-medium',
            healthy
              ? 'border-green-500/30 text-green-400 bg-green-500/5'
              : 'border-amber-500/30 text-amber-400 bg-amber-500/5'
          )}
        >
          {healthy ? <Wifi size={11} /> : <WifiOff size={11} />}
          {healthy ? 'LIVE' : 'OFFLINE'}
        </div>

        {ts && (
          <span className="text-[10px] text-t3 hidden lg:block">
            {formatDistanceToNow(ts, { addSuffix: true })}
          </span>
        )}
      </div>
    </header>
  );
}
