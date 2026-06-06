'use client';

import Topbar from '@/components/Topbar';
import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import { Database, CheckCircle, XCircle } from 'lucide-react';
import clsx from 'clsx';

interface ZgIntegration {
  chain_execution?: { status?: string; gate?: string; chain_id?: number; block?: number };
  storage?: { status?: string; root?: string };
  da?: { status?: string; available?: boolean };
  compute?: { status?: string };
  kv?: { status?: string };
}

function StatusIcon({ ok }: { ok?: boolean }) {
  if (ok === undefined) return <span className="w-2 h-2 rounded-full bg-t3 inline-block" />;
  return ok
    ? <CheckCircle size={13} className="text-green-400" />
    : <XCircle size={13} className="text-red-400" />;
}

function ComponentCard({ title, data }: { title: string; data: Record<string, unknown> }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-3">
        <Database size={12} className="text-cyan" />
        <p className="text-[12px] font-semibold text-t1">{title}</p>
      </div>
      {Object.entries(data).map(([k, v]) => (
        <div key={k} className="flex items-center justify-between py-1.5 border-b border-border/50 last:border-0">
          <span className="text-[11px] text-t3 capitalize">{k.replace(/_/g, ' ')}</span>
          <span className="text-[11px] mono text-t1 font-medium truncate max-w-[200px]">
            {typeof v === 'boolean' ? (v ? '✓ yes' : '✗ no') : String(v ?? '—')}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function ZgPage() {
  const { data, isLoading } = useSWR<ZgIntegration>(endpoints.zgIntegration, fetchJSON, { refreshInterval: 30000 });
  const { data: chainStatus } = useSWR(endpoints.zgChainStatus, fetchJSON, { refreshInterval: 10000 });

  const mainnetOk = (chainStatus as any)?.connected ?? false;

  return (
    <>
      <Topbar title="0G Network" />
      <div className="flex-1 overflow-y-auto scrollable p-5 flex flex-col gap-4">
        {/* Header status */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: '0G Mainnet', value: mainnetOk ? 'CONNECTED' : 'CHECKING', color: mainnetOk ? 'text-green-400' : 'text-amber-400' },
            { label: 'Chain ID', value: '16661', color: 'text-cyan' },
            { label: 'ExecutionGate', value: 'DEPLOYED', color: 'text-green-400' },
            { label: 'Integration Modules', value: '5', color: 'text-violet-400' },
          ].map(({ label, value, color }) => (
            <div key={label} className="card p-3 text-center">
              <p className={`text-lg font-bold mono ${color}`}>{value}</p>
              <p className="text-[10px] text-t3 uppercase tracking-wide mt-0.5">{label}</p>
            </div>
          ))}
        </div>

        {/* Contract addresses */}
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-3">
            <Database size={13} className="text-cyan" />
            <p className="text-[12px] font-semibold text-t1">0G Mainnet Contracts</p>
            <span className="text-[10px] px-1.5 py-0.5 bg-green-500/10 border border-green-500/30 text-green-400 rounded">LIVE · Chain 16661</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {[
              { name: 'TRIONExecutionGate', addr: '0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b', role: 'Pre-trade firewall' },
              { name: 'AkashicProof', addr: '0x33c793fed5bf5fcB043D8c6c74256e7B4b38156D', role: 'BEO Merkle root storage' },
            ].map(({ name, addr, role }) => (
              <div key={name} className="bg-card2 border border-border rounded p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[11px] font-semibold text-t1">{name}</span>
                  <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
                </div>
                <p className="mono text-[10px] text-cyan break-all">{addr}</p>
                <p className="text-[10px] text-t3 mt-1">{role}</p>
              </div>
            ))}
          </div>
        </div>

        {/* 5 integration modules */}
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[...Array(5)].map((_, i) => <div key={i} className="card h-40 animate-pulse bg-border" />)}
          </div>
        ) : data ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {data.chain_execution && <ComponentCard title="Chain Execution" data={data.chain_execution as Record<string, unknown>} />}
            {data.storage && <ComponentCard title="0G Storage" data={data.storage as Record<string, unknown>} />}
            {data.da && <ComponentCard title="Data Availability" data={data.da as Record<string, unknown>} />}
            {data.compute && <ComponentCard title="0G Compute" data={data.compute as Record<string, unknown>} />}
            {data.kv && <ComponentCard title="KV Store" data={data.kv as Record<string, unknown>} />}
          </div>
        ) : (
          <div className="card p-8 text-center text-t3 text-[12px]">0G integration data unavailable</div>
        )}

        {/* Integration description */}
        <div className="card p-4">
          <p className="text-[12px] font-semibold text-t1 mb-2">0G Integration Architecture</p>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-2 text-center">
            {[
              { label: 'Chain Execution', sub: 'TRIONExecutionGate.checkExecution()' },
              { label: '0G Storage', sub: 'FAISS → Merkle root upload' },
              { label: 'Data Availability', sub: 'Anomaly blobs + Reed-Solomon' },
              { label: '0G Compute', sub: 'Behavioral inference layer' },
              { label: 'KV Store', sub: 'Snapshot hash verification' },
            ].map(({ label, sub }) => (
              <div key={label} className="bg-card2 border border-border rounded p-2.5">
                <p className="text-[11px] font-semibold text-cyan">{label}</p>
                <p className="text-[9px] text-t3 mt-0.5">{sub}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
