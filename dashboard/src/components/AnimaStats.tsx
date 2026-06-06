'use client';

import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { StatsData, ArchetypesData } from '@/lib/types';
import { Cpu } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';

const ARCH_COLORS = [
  '#00c2ff', '#9f67f5', '#22c55e', '#f59e0b', '#ef4444', '#f97316',
  '#06b6d4', '#8b5cf6', '#10b981', '#d97706',
];

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ value: number; payload: { name: string } }>;
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-card border border-border rounded p-2 text-[11px]">
      <p className="text-t2">{payload[0].payload.name}</p>
      <p className="text-cyan mono font-semibold">{payload[0].value.toFixed(2)}</p>
    </div>
  );
}

export default function AnimaStats() {
  const { data: stats } = useSWR<StatsData>(endpoints.stats, fetchJSON, { refreshInterval: 10000 });
  const { data: archs } = useSWR<ArchetypesData>(endpoints.archetypes, fetchJSON, { refreshInterval: 60000 });

  const chartData = (archs?.archetypes ?? []).slice(0, 12).map((a, i) => ({
    name: a.name,
    confidence: a.investment_confidence,
    color: ARCH_COLORS[i % ARCH_COLORS.length],
  }));

  return (
    <div className="card flex flex-col gap-4 p-4 h-full">
      <div className="flex items-center gap-2">
        <Cpu size={13} className="text-cyan" />
        <span className="text-[12px] font-semibold text-t1">FAISS ANIMA Engine</span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="bg-card2 border border-border rounded p-3 text-center">
          <p className="text-xl font-bold mono text-cyan">{stats?.indexed_vectors?.toLocaleString() ?? '—'}</p>
          <p className="text-[10px] text-t3 uppercase tracking-wide mt-0.5">Indexed Vectors</p>
        </div>
        <div className="bg-card2 border border-border rounded p-3 text-center">
          <p className="text-xl font-bold mono text-violet-400">128</p>
          <p className="text-[10px] text-t3 uppercase tracking-wide mt-0.5">Vector Dims</p>
        </div>
        <div className="bg-card2 border border-border rounded p-3 text-center">
          <p className="text-xl font-bold mono text-green-400">{archs?.archetypes?.length ?? 64}</p>
          <p className="text-[10px] text-t3 uppercase tracking-wide mt-0.5">Archetypes</p>
        </div>
        <div className="bg-card2 border border-border rounded p-3 text-center">
          <p className="text-xl font-bold mono text-amber-400">59</p>
          <p className="text-[10px] text-t3 uppercase tracking-wide mt-0.5">NLP Languages</p>
        </div>
      </div>

      {chartData.length > 0 && (
        <div className="flex-1 min-h-[140px]">
          <p className="text-[10px] text-t3 uppercase tracking-wide mb-2">Archetype Confidence</p>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
              <XAxis dataKey="name" tick={{ fontSize: 8, fill: '#4a6b8a' }} angle={-45} textAnchor="end" height={40} />
              <YAxis tick={{ fontSize: 9, fill: '#4a6b8a' }} domain={[0, 1]} />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
              <Bar dataKey="confidence" radius={[2, 2, 0, 0]}>
                {chartData.map((d, i) => (
                  <Cell key={i} fill={d.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
