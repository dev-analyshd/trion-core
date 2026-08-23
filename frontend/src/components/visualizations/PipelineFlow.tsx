/**
 * PipelineFlow - Visualizes the end-to-end TRION data pipeline
 * Aligned with whitepaper layers: L0 Indexing → L2 Akashic → L3/L4 Planes → L5 Coherence → L6+ Signal → On-Chain
 */
'use client';
import { useAPI } from '../../lib/hooks';
import { fmt } from '../../lib/api';
import * as Icons from 'lucide-react';

const STAGES = [
  {
    layer: 'L0',
    name: 'Chain Indexing',
    desc: '60 EVM chains, real-time RPC polling',
    icon: Icons.Globe,
    color: 'from-blue-500 to-cyan-500',
    statKey: 'chains_active',
    statSuffix: ' chains',
  },
  {
    layer: 'L0.1',
    name: 'Behavioral Hashes',
    desc: '93-byte canonical BH dual-strand',
    icon: Icons.Fingerprint,
    color: 'from-cyan-500 to-teal-500',
    statKey: 'total_bhs',
    statSuffix: ' BHs',
  },
  {
    layer: 'L2.1',
    name: 'FAISS Vector Index',
    desc: '128-dim vectors, IndexFlatL2 → IVFPQ',
    icon: Icons.Cpu,
    color: 'from-teal-500 to-emerald-500',
    statKey: 'faiss_vectors',
    statSuffix: ' vectors',
  },
  {
    layer: 'L3/L4',
    name: 'Five Planes',
    desc: 'Φ · M · Σ · K · A behavioral planes',
    icon: Icons.Layers,
    color: 'from-emerald-500 to-green-500',
    statKey: null,
    statSuffix: '',
  },
  {
    layer: 'L5.2',
    name: 'Coherence Engine',
    desc: 'C(t) weighted plane fusion',
    icon: Icons.Gauge,
    color: 'from-green-500 to-lime-500',
    statKey: 'coherence',
    statSuffix: ' C score',
  },
  {
    layer: 'L5.3',
    name: 'Master Equation',
    desc: 'T(t) = [C≥Θ]·C·e^(M_moat)',
    icon: Icons.Calculator,
    color: 'from-lime-500 to-amber-500',
    statKey: null,
    statSuffix: '',
  },
  {
    layer: 'L6+',
    name: 'Signal Emission',
    desc: 'Publish iff C ≥ Θ, else SILENCE',
    icon: Icons.Radio,
    color: 'from-amber-500 to-orange-500',
    statKey: 'signals_onchain',
    statSuffix: ' on-chain',
  },
  {
    layer: 'On-Chain',
    name: 'Oracle Contract',
    desc: 'TRIONOracleV3 · Arbitrum Sepolia',
    icon: Icons.Link,
    color: 'from-orange-500 to-red-500',
    statKey: null,
    statSuffix: '',
  },
];

export function PipelineFlow() {
  const { data: streamer } = useAPI('/api/v1/btcp/streamer/status', 3000);
  const { data: faiss } = useAPI('/api/v1/faiss', 5000);
  const { data: health } = useAPI('/api/v1/health', 5000);
  
  const getStat = (key: string | null) => {
    if (!key) return null;
    switch (key) {
      case 'chains_active': return streamer?.chains_active ?? 0;
      case 'total_bhs': return streamer?.total_bhs ?? 0;
      case 'faiss_vectors': return faiss?.indexed_vectors ?? faiss?.ntotal ?? 0;
      case 'coherence': return health?.coherence_score?.toFixed(3) ?? null;
      case 'signals_onchain': return health?.total_signals_onchain ?? 0;
      default: return null;
    }
  };
  
  return (
    <div className="bg-card border border-border rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-bold">End-to-End Pipeline</h3>
          <p className="text-xs text-muted-foreground">From chain ingestion to on-chain signal publication</p>
        </div>
        {streamer?.status === 'RUNNING' && (
          <div className="flex items-center gap-2 text-xs text-green-400">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
            </span>
            STREAMING LIVE
          </div>
        )}
      </div>
      
      <div className="relative">
        {/* Connection line */}
        <div className="absolute top-8 left-0 right-0 h-0.5 bg-gradient-to-r from-blue-500 via-emerald-500 to-red-500 opacity-30 hidden lg:block" />
        
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-4">
          {STAGES.map((stage, i) => {
            const Icon = stage.icon;
            const stat = getStat(stage.statKey);
            return (
              <div key={stage.layer} className="relative">
                <div className={`bg-gradient-to-br ${stage.color} p-0.5 rounded-xl`}>
                  <div className="bg-card rounded-xl p-4 h-full">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-[10px] font-mono text-muted-foreground bg-muted px-2 py-0.5 rounded">
                        {stage.layer}
                      </span>
                    </div>
                    <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${stage.color} flex items-center justify-center mb-3`}>
                      <Icon className="w-5 h-5 text-white" />
                    </div>
                    <div className="font-semibold text-sm mb-1">{stage.name}</div>
                    <div className="text-xs text-muted-foreground mb-3">{stage.desc}</div>
                    {stat !== null && (
                      <div className="font-mono text-lg font-bold">
                        {typeof stat === 'number' ? fmt(stat, 0) : stat}
                        <span className="text-xs font-normal text-muted-foreground ml-1">{stage.statSuffix}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
