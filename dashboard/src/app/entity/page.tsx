'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { SignalData } from '@/lib/types';
import Topbar from '@/components/Topbar';
import PlaneBars from '@/components/PlaneBars';
import CoherenceMeter from '@/components/CoherenceMeter';
import { Search, Brain, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import clsx from 'clsx';

const PRESETS = ['uniswap', 'aave', 'compound', '0xb819c63c02Ed5aB49017C0f3f2568A14624658b3'];

function TrendIcon({ trend }: { trend: string }) {
  if (trend === 'RISING') return <TrendingUp size={13} className="text-green-400" />;
  if (trend === 'FALLING') return <TrendingDown size={13} className="text-red-400" />;
  return <Minus size={13} className="text-t3" />;
}

function InfoRow({ label, value, mono = false, className }: { label: string; value: string; mono?: boolean; className?: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border/50 last:border-0">
      <span className="text-[11px] text-t3">{label}</span>
      <span className={clsx('text-[11px] text-t1 font-medium', mono && 'mono text-[10px]', className)}>{value}</span>
    </div>
  );
}

function EntityPanel({ entityId }: { entityId: string }) {
  const { data, isLoading, error } = useSWR<SignalData>(
    entityId ? endpoints.signal(entityId) : null,
    fetchJSON,
    { refreshInterval: 10000 }
  );

  if (isLoading) return (
    <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-4">
      {[...Array(3)].map((_, i) => <div key={i} className="card h-64 animate-pulse bg-border" />)}
    </div>
  );

  if (error || !data) return (
    <div className="flex-1 flex items-center justify-center text-t3 text-[12px]">
      {error ? `Error: ${error.message}` : 'Enter an entity ID to inspect'}
    </div>
  );

  const { plane_breakdown, plane_contributions } = data;
  const typeColor = data.coherent ? 'text-green-400 border-green-500/30 bg-green-500/5'
    : 'text-amber-400 border-amber-500/30 bg-amber-500/5';

  return (
    <div className="flex-1 flex flex-col gap-4 overflow-y-auto scrollable">
      {/* Header */}
      <div className="card p-4 flex-shrink-0">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <p className="mono text-[12px] text-t2 break-all">{data.entity_id}</p>
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              <span className="text-lg font-bold text-cyan">{data.archetype}</span>
              <span className={clsx('px-2 py-0.5 rounded border text-[10px] font-bold uppercase', typeColor)}>
                {data.signal_type}
              </span>
              <TrendIcon trend={data.coherence_trend} />
              <span className="text-[11px] text-t2">{data.coherence_trend}</span>
            </div>
          </div>
          <div className="text-right">
            <p className="text-[10px] text-t3 mb-1">C(t) Coherence</p>
            <p className={clsx('text-3xl font-bold mono', data.coherent ? 'text-green-400' : 'text-amber-400')}>
              {data.coherence_score.toFixed(4)}
            </p>
            <p className="text-[10px] text-t3 mt-0.5">Θ(t) = {data.threshold.toFixed(4)}</p>
          </div>
        </div>
        <div className="mt-4">
          <CoherenceMeter score={data.coherence_score} threshold={data.threshold} size="lg" />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 flex-shrink-0">
        {/* Plane Breakdown */}
        <div className="card p-4 lg:col-span-1">
          <p className="text-[11px] font-semibold text-t1 mb-3">Five-Plane Breakdown</p>
          {plane_breakdown && (
            <PlaneBars planes={plane_breakdown} threshold={data.threshold} />
          )}
          <div className="mt-3 pt-3 border-t border-border">
            <p className="text-[10px] text-t3 mb-1.5">Limiting Plane</p>
            <span className="px-2 py-1 bg-amber-500/10 border border-amber-500/30 rounded text-amber-400 text-[11px] font-semibold">
              {data.limiting_plane}
            </span>
          </div>
        </div>

        {/* Signal detail */}
        <div className="card p-4 lg:col-span-1">
          <p className="text-[11px] font-semibold text-t1 mb-3">Signal Detail</p>
          <InfoRow label="Signal ID" value={data.signal_id?.slice(0, 18) + '…'} mono />
          <InfoRow label="Signal Type" value={data.signal_type} />
          <InfoRow label="Coherent" value={data.coherent ? 'YES' : 'NO'} className={data.coherent ? 'text-green-400' : 'text-amber-400'} />
          <InfoRow label="Silence Gap" value={data.silence_gap?.toFixed(4) ?? '—'} mono />
          <InfoRow label="Market Volatility" value={`${((data.market_volatility ?? 0) * 100).toFixed(1)}%`} />
          <InfoRow label="Trend" value={data.coherence_trend} />
        </div>

        {/* Plane contributions */}
        <div className="card p-4 lg:col-span-1">
          <p className="text-[11px] font-semibold text-t1 mb-3">Weighted Contributions</p>
          {plane_contributions && Object.entries(plane_contributions).map(([plane, val]) => (
            <div key={plane} className="flex items-center justify-between py-1.5 border-b border-border/50 last:border-0">
              <span className="text-[11px] text-t2">{plane}</span>
              <div className="flex items-center gap-2">
                <div className="w-20 h-1 bg-border rounded-full overflow-hidden">
                  <div className="h-full bg-cyan rounded-full" style={{ width: `${Math.min(100, (val as number) * 500)}%` }} />
                </div>
                <span className="mono text-[10px] text-t1 w-12 text-right">{(val as number).toFixed(4)}</span>
              </div>
            </div>
          ))}

          {/* Genomic signature */}
          {data.genomic_signature && (
            <div className="mt-3 pt-3 border-t border-border">
              <p className="text-[10px] text-t3 mb-1">Genomic Signature</p>
              <p className="mono text-[9px] text-t3 break-all leading-relaxed">
                {data.genomic_signature.slice(0, 48)}…
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function EntityPage() {
  const [query, setQuery] = useState('');
  const [entityId, setEntityId] = useState('');

  function submit(id?: string) {
    setEntityId(id ?? query.trim());
  }

  return (
    <>
      <Topbar title="Entity Intelligence" />
      <div className="flex-1 overflow-hidden p-5 flex flex-col gap-4">
        {/* Search */}
        <div className="card p-4 flex-shrink-0">
          <div className="flex items-center gap-2">
            <Brain size={13} className="text-cyan flex-shrink-0" />
            <span className="text-[12px] font-semibold text-t1">Entity Lookup</span>
          </div>
          <div className="flex gap-2 mt-3">
            <div className="flex-1 relative">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-t3" />
              <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && submit()}
                placeholder="Address or protocol name (e.g. uniswap, 0xAbc…)"
                className="w-full bg-card2 border border-border rounded pl-8 pr-3 py-2 text-[12px] text-t1 placeholder-t3 outline-none focus:border-cyan/50 transition-colors"
              />
            </div>
            <button
              onClick={() => submit()}
              className="px-4 py-2 bg-cyan text-bg rounded text-[12px] font-semibold hover:bg-cyan2 transition-colors"
            >
              Inspect
            </button>
          </div>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <span className="text-[10px] text-t3">Quick:</span>
            {PRESETS.map(p => (
              <button
                key={p}
                onClick={() => { setQuery(p); submit(p); }}
                className="text-[10px] px-2 py-0.5 bg-card2 border border-border rounded hover:border-cyan/40 hover:text-cyan text-t2 transition-colors mono"
              >
                {p.length > 20 ? p.slice(0, 10) + '…' : p}
              </button>
            ))}
          </div>
        </div>

        {/* Panel */}
        <EntityPanel entityId={entityId} />
      </div>
    </>
  );
}
