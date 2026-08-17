/**
 * CoherenceEngine - Visualizes the 5 Behavioral Planes + Coherence computation
 * Aligned with TRION Whitepaper L5.2: C(t) = alpha*Phi + beta*M + gamma*Sigma + delta*K + epsilon*A
 */
'use client';
import { useEffect, useState } from 'react';
import { useAPI } from '../../lib/hooks';
import { fmt, pct } from '../../lib/api';
import * as Icons from 'lucide-react';

interface PlaneData {
  physical: number;
  mental: number;
  spiritual: number;
  conscious: number;
  anima: number;
}

const PLANES = [
  { key: 'physical', symbol: 'Φ', name: 'Physical', color: '#ef4444', desc: 'Shannon entropy from transaction patterns', icon: Icons.Activity },
  { key: 'mental', symbol: 'M', name: 'Mental', color: '#f59e0b', desc: 'FAISS archetype prediction confidence', icon: Icons.Brain },
  { key: 'spiritual', symbol: 'Σ', name: 'Spiritual', color: '#10b981', desc: 'Diversity-weighted BFT validator consensus', icon: Icons.Users },
  { key: 'conscious', symbol: 'K', name: 'Conscious', color: '#3b82f6', desc: 'Human annotation network with ACP protections', icon: Icons.Eye },
  { key: 'anima', symbol: 'A', name: 'ANIMA', color: '#8b5cf6', desc: 'Cross-domain intelligence absorption', icon: Icons.Sparkles },
];

const WEIGHTS = { physical: 0.25, mental: 0.30, spiritual: 0.25, conscious: 0.10, anima: 0.10 };

export function CoherenceEngine({ entityId }: { entityId?: string }) {
  const defaultEntity = '0x742d35Cc6634C0532925a3b844Bc454e4438f44e';
  const eid = entityId || defaultEntity;
  
  const { data: planesAll } = useAPI(`/api/v1/planes/${eid}/all`, 8000);
  const { data: health } = useAPI('/api/v1/health', 5000);
  
  // Extract plane values with bootstrap fallbacks
  const planes: PlaneData = {
    physical: planesAll?.planes?.physical?.score ?? planesAll?.physical ?? 0.0,
    mental: planesAll?.planes?.mental?.score ?? planesAll?.mental ?? 0.0,
    spiritual: planesAll?.planes?.spiritual?.score ?? planesAll?.sigma ?? 0.25,
    conscious: planesAll?.planes?.conscious?.score ?? planesAll?.k_plane ?? 0.10,
    anima: planesAll?.planes?.anima?.score ?? planesAll?.anima ?? 0.10,
  };
  
  // Compute weighted coherence
  const C = (
    planes.physical * WEIGHTS.physical +
    planes.mental * WEIGHTS.mental +
    planes.spiritual * WEIGHTS.spiritual +
    planes.conscious * WEIGHTS.conscious +
    planes.anima * WEIGHTS.anima
  );
  
  const theta = health?.dynamic_threshold ?? 0.661;
  const coherent = C >= theta;
  const margin = C - theta;
  
  // Radar chart geometry
  const size = 280;
  const cx = size / 2;
  const cy = size / 2;
  const radius = 100;
  
  const angleFor = (i: number) => (Math.PI * 2 * i) / PLANES.length - Math.PI / 2;
  
  const pointFor = (i: number, value: number) => {
    const angle = angleFor(i);
    const r = radius * Math.min(1, Math.max(0, value));
    return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  };
  
  const radarPoints = PLANES.map((p, i) => {
    const pt = pointFor(i, planes[p.key as keyof PlaneData]);
    return `${pt.x},${pt.y}`;
  }).join(' ');
  
  return (
    <div className="bg-card border border-border rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-bold">Five-Plane Coherence Engine</h3>
          <p className="text-xs text-muted-foreground">C(t) = α·Φ + β·M + γ·Σ + δ·K + ε·A</p>
        </div>
        <div className={`px-3 py-1 rounded-full text-xs font-bold ${coherent ? 'bg-green-500/20 text-green-400 border border-green-500/30' : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'}`}>
          {coherent ? 'COHERENT' : 'BELOW THRESHOLD'}
        </div>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Radar Chart */}
        <div className="flex items-center justify-center">
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
            {/* Grid rings */}
            {[0.25, 0.5, 0.75, 1.0].map((t, ti) => (
              <polygon
                key={ti}
                points={PLANES.map((_, i) => {
                  const angle = angleFor(i);
                  const r = radius * t;
                  return `${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`;
                }).join(' ')}
                fill="none"
                stroke="var(--color-border)"
                strokeWidth="1"
              />
            ))}
            
            {/* Axes */}
            {PLANES.map((p, i) => {
              const angle = angleFor(i);
              return (
                <line
                  key={p.key}
                  x1={cx} y1={cy}
                  x2={cx + radius * Math.cos(angle)}
                  y2={cy + radius * Math.sin(angle)}
                  stroke="var(--color-border)"
                  strokeWidth="1"
                />
              );
            })}
            
            {/* Data polygon */}
            <polygon
              points={radarPoints}
              fill="rgba(59, 130, 246, 0.15)"
              stroke="#3b82f6"
              strokeWidth="2"
            />
            
            {/* Data points */}
            {PLANES.map((p, i) => {
              const pt = pointFor(i, planes[p.key as keyof PlaneData]);
              return (
                <circle key={p.key} cx={pt.x} cy={pt.y} r="5" fill={p.color} stroke="white" strokeWidth="1" />
              );
            })}
            
            {/* Plane labels */}
            {PLANES.map((p, i) => {
              const angle = angleFor(i);
              const lx = cx + (radius + 25) * Math.cos(angle);
              const ly = cy + (radius + 25) * Math.sin(angle);
              return (
                <text
                  key={p.key}
                  x={lx} y={ly}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill="var(--color-foreground)"
                  fontSize="12"
                  fontWeight="bold"
                >
                  {p.symbol}
                </text>
              );
            })}
          </svg>
        </div>
        
        {/* Plane details */}
        <div className="space-y-3">
          {PLANES.map(p => {
            const val = planes[p.key as keyof PlaneData];
            const weighted = val * WEIGHTS[p.key as keyof typeof WEIGHTS];
            const Icon = p.icon;
            return (
              <div key={p.key} className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <Icon className="w-4 h-4" style={{ color: p.color }} />
                    <span className="font-medium">{p.symbol} {p.name}</span>
                    <span className="text-xs text-muted-foreground">× {WEIGHTS[p.key as keyof typeof WEIGHTS]}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xs text-muted-foreground">{val.toFixed(3)}</span>
                    <span className="font-mono font-bold" style={{ color: p.color }}>{weighted.toFixed(4)}</span>
                  </div>
                </div>
                <div className="h-2 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, val * 100)}%`, backgroundColor: p.color }}
                  />
                </div>
              </div>
            );
          })}
          
          <div className="pt-3 mt-3 border-t border-border">
            <div className="flex items-center justify-between">
              <span className="font-bold">Coherence C(t)</span>
              <span className={`font-mono text-xl font-bold ${coherent ? 'text-green-400' : 'text-amber-400'}`}>
                {C.toFixed(4)}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs text-muted-foreground mt-1">
              <span>Threshold Θ(t)</span>
              <span className="font-mono">{theta.toFixed(4)}</span>
            </div>
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Margin</span>
              <span className={`font-mono ${margin >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {margin >= 0 ? '+' : ''}{margin.toFixed(4)}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
