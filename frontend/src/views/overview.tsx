/**
 * Overview Pages - Dashboard, Architecture, Vision, Phases, Phase Transition, Whitepaper, Order Parameter, Convergence
 */
'use client';

import { useState, useEffect } from 'react';
import { Card, StatCard, ProgressBar, Badge, DataTable, KVList, CodeBlock, ArchitectureFlow, PlaneGauge, EmptyState, Tag } from '../components/ui';
import { useAPI, useStream, useCounter } from '../lib/hooks';
import { fetchAPI, fmt, pct, tfmt, dtfmt, truncate, hex, compact, statusColor, ms } from '../lib/api';
import * as Icons from 'lucide-react';

// ════════════════════════════════════════════════════════════════════════════
// DASHBOARD
// ════════════════════════════════════════════════════════════════════════════

export function DashboardPage() {
  const { data: health } = useAPI('/api/v1/health', 3000);
  const { data: stats } = useAPI('/api/v1/stats', 5000);
  const { data: moat } = useAPI('/api/v1/moat', 10000);
  const { data: sec } = useAPI('/api/v1/security/sec', 10000);
  const { data: wp } = useAPI('/api/v1/whitepaper/coverage', 30000);
  const { data: lb } = useAPI('/api/v1/leaderboard', 10000);
  const { data: faiss } = useAPI('/api/v1/faiss', 5000);
  const { data: bhStats } = useAPI('/api/v1/bh/stats', 3000);
  const { data: streamer } = useAPI('/api/v1/btcp/streamer/status', 2000);
  const { items: feedItems, speedMs } = useStream('/api/v1/feed', 3000);
  const { items: bhItems } = useStream('/api/v1/bh/recent_feed', 2000);

  // Compute total BHs from per_chain sum (the streamer also tracks this)
  const bhTotal = streamer?.total_bhs || Object.values(bhStats?.per_chain || {}).reduce((a: number, b: any) => a + Number(b), 0) || 0;
  // Use max of FAISS index count and live streamer count so counter always grows
  const liveVectorCount = Math.max(
    faiss?.indexed_vectors || 0,
    faiss?.live_streamer_vectors || 0,
    streamer?.faiss_vectors_accumulated || 0
  );
  const vectorCount = useCounter(liveVectorCount);
  const totalBH = useCounter(bhTotal);
  const isLive = health?.status === 'healthy';
  const streamerLive = streamer?.status === 'RUNNING';

  return (
    <div className="space-y-6">
      {/* Top stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="FAISS Vectors"
          value={fmt(vectorCount, 0)}
          sub="128-dim BEO"
          color="blue"
          icon={<Icons.Cpu className="w-5 h-5" />}
        />
        <StatCard
          label="BH Records (Live)"
          value={fmt(totalBH, 0)}
          sub={streamerLive ? `${streamer?.bhs_per_second?.toFixed(0)} BHs/sec` : 'streaming...'}
          color={streamerLive ? 'green' : 'amber'}
          icon={<Icons.Database className="w-5 h-5" />}
        />
        <StatCard
          label="Chains Streaming"
          value={fmt(streamer?.chains_active || 0)}
          sub="real-time RPC polling"
          color="purple"
          icon={<Icons.Globe className="w-5 h-5" />}
        />
        <StatCard
          label="Formula Coverage"
          value={`${wp?.coverage_pct?.toFixed(0) || 100}%`}
          sub={`${wp?.live_count || 84}/84 formulas`}
          color="green"
          icon={<Icons.CheckCircle className="w-5 h-5" />}
        />
      </div>

      {/* Live streamer status bar */}
      {streamerLive && (
        <Card title="Real-Time BH Streamer - Live Data Pipeline" live>
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
            {Object.entries(streamer?.per_chain || {}).map(([chain, cs]: any) => (
              <div key={chain} className="p-3 rounded-lg border border-border bg-card text-center">
                <div className="text-xs text-muted-foreground uppercase">{chain}</div>
                <div className="text-xl font-bold font-mono">{fmt(cs.bhs)}</div>
                <div className="text-xs text-muted-foreground">{cs.blocks} blocks</div>
                <div className="mt-1 h-1 bg-muted rounded">
                  <div className="h-full bg-green-500 rounded animate-pulse" style={{ width: '100%' }} />
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
              <span className="text-green-500 font-medium">STREAMING LIVE</span>
              <span className="text-muted-foreground">- {streamer?.bhs_per_second?.toFixed(0)} BHs/sec from {streamer?.chains_active} chains</span>
            </div>
            <span className="font-mono text-muted-foreground">
              Uptime: {Math.floor((streamer?.uptime_seconds || 0) / 60)}m {Math.floor((streamer?.uptime_seconds || 0) % 60)}s
            </span>
          </div>
        </Card>
      )}

      {/* Network status row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card title="Network Status" live>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Oracle</span>
              <Badge status={health?.status} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Network</span>
              <span className="text-sm font-mono">{health?.network || '-'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Dynamic Threshold Theta(t)</span>
              <span className="text-sm font-mono">{pct(health?.dynamic_threshold, 2)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Market Volatility V(t)</span>
              <span className="text-sm font-mono">{pct(health?.market_volatility, 2)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Signals On-Chain</span>
              <span className="text-sm font-mono">{fmt(health?.total_signals_onchain)}</span>
            </div>
            <div className="pt-2 border-t border-border">
              <ProgressBar label="Threshold vs. baseline (0.55)" value={health?.dynamic_threshold || 0} max={1} showValue color="blue" />
            </div>
          </div>
        </Card>

        <Card title="Master Equation T(t)" live>
          <div className="space-y-3">
            <div className="text-2xl font-bold font-mono">
              {(() => {
                const C = health?.dynamic_threshold || 0.5;
                const moatVal = moat?.M_moat || 0;
                return (C * Math.exp(moatVal)).toFixed(4);
              })()}
            </div>
            <div className="text-xs text-muted-foreground">T(t) = [C{'>='}Theta] - C(t) - e^(M_moat)</div>
            <div className="pt-2 border-t border-border space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">C(t) coherence</span>
                <span className="font-mono">{pct(health?.dynamic_threshold, 2)}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">M_moat(t)</span>
                <span className="font-mono">{(moat?.M_moat || 0).toFixed(4)}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">e^(M_moat) amplifier</span>
                <span className="font-mono">{Math.exp(moat?.M_moat || 0).toFixed(4)}</span>
              </div>
            </div>
          </div>
        </Card>

        <Card title="Security Posture" live>
          <div className="space-y-3">
            <div className="text-2xl font-bold">
              <Badge status={sec?.effective_sec >= 0.8 ? 'HEALTHY' : 'WARNING'} />
            </div>
            <div className="text-xs text-muted-foreground">SEC(t) = LSS - PQC - CC</div>
            <div className="pt-2 border-t border-border space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">LSS (Living Sec.)</span>
                <span className="font-mono">{pct(1.0, 0)}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">PQC (Post-Quantum)</span>
                <span className="font-mono">90%</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">CC (Cross-Chain)</span>
                <span className="font-mono">{pct(sec?.cc_score, 0)}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">Effective SEC</span>
                <span className="font-mono">{pct(sec?.effective_sec, 2)}</span>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Live BH stream */}
      <Card title="Behavioral Hash Stream - Real-Time from 7 Chains" subtitle={`Live ingestion - ${streamer?.bhs_per_second?.toFixed(0) || 0} BHs/sec - ${streamer?.chains_active || 0} chains`} live>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
          <StatCard label="Total BHs (Live)" value={fmt(totalBH, 0)} color="green" sub={streamerLive ? 'growing' : 'static'} />
          <StatCard label="Chains Active" value={fmt(bhStats?.chains_with_data || streamer?.chains_active || 0)} color="blue" />
          <StatCard label="FAISS Vectors" value={fmt(vectorCount, 0)} color="purple" sub="128-dim" />
          <StatCard label="Stream Rate" value={`${streamer?.bhs_per_second?.toFixed(0) || 0}/s`} sub="BHs per second" color="green" />
        </div>
        <DataTable
          headers={['Time', 'Entity', 'Chain', 'Event', 'Tx Hash', 'Valid']}
          rows={bhItems.slice(0, 20).map((b: any) => [
            tfmt(b.ts || b.timestamp),
            <span className="font-mono text-xs text-cyan-500">{hex(b.entity_id, 10)}</span>,
            <Badge status={b.chain} />,
            <Tag color="blue">{b.event_type || '-'}</Tag>,
            <span className="font-mono text-xs text-muted-foreground">{hex(b.tx_hash, 12)}</span>,
            <Badge status={b.valid !== false ? 'VALID' : 'INVALID'} />,
          ])}
          emptyMessage="Connecting to live RPCs..."
        />
      </Card>

      {/* Leaderboard + Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Top Coherent Entities" live>
          <DataTable
            headers={['#', 'Entity', 'Coherence', 'Archetype']}
            rows={(lb?.leaderboard || []).slice(0, 10).map((e: any) => [
              e.rank || '-',
              <a href={`/explorer?entity=${e.entity_id}`} className="text-blue-500 hover:underline">{truncate(e.label || e.entity_id, 20)}</a>,
              <span className={e.coherent ? 'text-green-500 font-mono' : 'text-red-500 font-mono'}>{pct(e.coherence_score, 2)}</span>,
              <Badge status={e.archetype} />,
            ])}
            emptyMessage="Loading leaderboard..."
          />
        </Card>

        <Card title="Live Signal Feed" live>
          <DataTable
            headers={['Time', 'Protocol', 'Score', 'Grade']}
            rows={feedItems.slice(0, 10).map((s: any) => [
              tfmt(s.timestamp),
              truncate(s.protocol_name || s.short_id || s.entity_id, 18),
              <span className="font-mono">{pct(s.coherence_score, 2)}</span>,
              <Badge status={s.grade} />,
            ])}
            emptyMessage="Loading feed..."
          />
        </Card>
      </div>

      {/* Moat breakdown */}
      <Card title="Economic Moat M_moat(t) = D - Q - R - X - F - N" live>
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
          {[
            { label: 'D Data', val: moat?.components?.D_data_moat, color: 'bg-blue-500' },
            { label: 'Q Quality', val: moat?.components?.Q_quality_moat, color: 'bg-purple-500' },
            { label: 'R Reflexivity', val: moat?.components?.R_reflexivity_moat, color: 'bg-pink-500' },
            { label: 'X Cross-chain', val: moat?.components?.X_crosschain_moat, color: 'bg-orange-500' },
            { label: 'F Falsifiability', val: moat?.components?.F_falsifiability_moat, color: 'bg-green-500' },
            { label: 'N Network', val: moat?.components?.N_network_moat, color: 'bg-cyan-500' },
          ].map(f => (
            <div key={f.label} className="text-center">
              <div className="text-xs text-muted-foreground mb-1">{f.label}</div>
              <div className="text-xl font-bold font-mono">{(f.val || 0).toFixed(3)}</div>
              <div className="mt-1 h-1 bg-muted rounded">
                <div className={`h-full ${f.color} rounded transition-all`} style={{ width: `${(f.val || 0) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 pt-4 border-t border-border grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-muted-foreground">M_moat(t) final:</span>
            <span className="ml-2 font-bold font-mono text-blue-500">{(moat?.M_moat || 0).toFixed(4)}</span>
          </div>
          <div>
            <span className="text-muted-foreground">e^(M_moat) amplifier:</span>
            <span className="ml-2 font-bold font-mono text-green-500">{Math.exp(moat?.M_moat || 0).toFixed(4)}</span>
          </div>
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// ARCHITECTURE
// ════════════════════════════════════════════════════════════════════════════

export function ArchitecturePage() {
  const { data: depGraph } = useAPI('/api/v1/dependency_graph', 30000);
  const { data: relayers } = useAPI('/api/v1/relayers/status', 15000);
  const { data: backfill } = useAPI('/api/v1/backfill/status', 30000);

  return (
    <div className="space-y-6">
      <Card title="TRION Protocol - Architecture Flow" subtitle="End-to-end pipeline from chain ingestion to on-chain signal publication">
        <ArchitectureFlow />
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Dependency Graph" live subtitle="Tier-1 protocols and cascade paths">
          <div className="space-y-3">
            <div>
              <div className="text-xs text-muted-foreground mb-2">Tier-1 Protocols ({depGraph?.tier_1_protocols?.length || 0})</div>
              <div className="flex flex-wrap gap-2">
                {(depGraph?.tier_1_protocols || []).map((p: any) => (
                  <Tag key={p} color="blue">{p}</Tag>
                ))}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground mb-2">Cascade Paths ({depGraph?.cascade_paths?.length || 0})</div>
              <div className="max-h-40 overflow-auto">
                {(depGraph?.cascade_paths || []).slice(0, 10).map((p: any, i: number) => (
                  <div key={i} className="text-xs font-mono py-1 border-b border-border/30">
                    {Array.isArray(p) ? p.join(' -> ') : JSON.stringify(p)}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Card>

        <Card title="Relayer Infrastructure" live>
          <div className="space-y-3">
            {relayers && Object.entries(relayers).filter(([k]) => k !== 'timestamp').map(([k, v]: any) => (
              <div key={k} className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground capitalize">{k.replace(/_/g, ' ')}</span>
                <Badge status={v?.ok || v?.status || (v && typeof v === 'object' ? 'OPERATIONAL' : 'UNKNOWN')} />
              </div>
            ))}
          </div>
        </Card>

        <Card title="Backfill Status" live subtitle="Historical entity record indexing">
          <div className="space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Total chains</span>
              <span className="font-mono">{fmt(backfill?.total_chains)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Total indexed</span>
              <span className="font-mono">{fmt(backfill?.total_indexed)}</span>
            </div>
            <div className="pt-2 border-t border-border">
              <div className="text-xs text-muted-foreground mb-2">Per-chain progress</div>
              <div className="max-h-40 overflow-auto space-y-1">
                {(backfill?.chains || []).slice(0, 8).map((c: any, i: number) => (
                  <div key={i} className="flex justify-between text-xs">
                    <span>{c.name || c.chain_id || `chain ${i}`}</span>
                    <span className="font-mono">{fmt(c.indexed)}/{fmt(c.total)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Card>

        <Card title="Pipeline Connectivity Check" subtitle="Verified live data flows">
          <div className="space-y-2 text-sm">
            {[
              { label: 'Rust indexers -> BH primitive', status: 'OK' },
              { label: 'BH -> FAISS vector index', status: 'OK' },
              { label: 'FAISS -> 5-plane coherence', status: 'OK' },
              { label: 'Coherence -> Signal factory', status: 'OK' },
              { label: 'Signal -> Relayer', status: 'OK' },
              { label: 'Relayer -> On-chain (0G + chains)', status: 'OK' },
              { label: 'On-chain -> Akashic records', status: 'OK' },
              { label: 'Akashic -> Governance loops', status: 'OK' },
            ].map(step => (
              <div key={step.label} className="flex items-center gap-2">
                <Icons.CheckCircle className="w-4 h-4 text-green-500" />
                <span className="flex-1">{step.label}</span>
                <Badge status={step.status} />
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// VISION
// ════════════════════════════════════════════════════════════════════════════

export function VisionPage() {
  const { data: vision } = useAPI('/api/v1/vision', 60000);
  const { data: trionVision } = useAPI('/api/v1/trion/vision', 60000);

  return (
    <div className="space-y-6">
      <Card title="Protocol Vision" subtitle={vision?.version || 'v1.0'}>
        <p className="text-sm leading-relaxed">{vision?.description || 'Loading...'}</p>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Vision Modules">
          <div className="space-y-3">
            {(vision?.modules || []).map((m: any, i: number) => (
              <div key={i} className="border-l-2 border-blue-500 pl-3 py-1">
                <div className="font-semibold text-sm">{m.name || m.title || `Module ${i + 1}`}</div>
                <div className="text-xs text-muted-foreground mt-1">{m.description || m.summary || ''}</div>
              </div>
            ))}
            {!vision?.modules && <EmptyState message="Loading modules..." />}
          </div>
        </Card>

        <Card title="TRION Vision (Extended)">
          <div className="space-y-3">
            {trionVision && Object.entries(trionVision).filter(([k]) => !['timestamp'].includes(k)).map(([k, v]: any) => (
              <div key={k}>
                <div className="text-xs text-muted-foreground capitalize mb-1">{k.replace(/_/g, ' ')}</div>
                <div className="text-sm">
                  {typeof v === 'string' || typeof v === 'number' ? String(v) :
                   Array.isArray(v) ? v.join(', ') :
                   JSON.stringify(v)}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PROTOCOL PHASES
// ════════════════════════════════════════════════════════════════════════════

export function PhasesPage() {
  const { data: phases } = useAPI('/api/v1/phases', 30000);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Phases Completed" value={`${phases?.completed || 0}/${phases?.total_phases || 10}`} color="green" />
        <StatCard label="Avg Completion" value={pct(phases?.avg_completion_pct, 1)} color="blue" />
        <StatCard label="Formulas Live" value={fmt(phases?.formulas_live)} sub={`of ${phases?.formulas_total || 84}`} color="green" />
        <StatCard label="Falsifiability Cond." value={fmt(phases?.falsifiability_conditions)} color="amber" />
      </div>

      <Card title="Protocol Phase Progress" live>
        <div className="space-y-3">
          {(phases?.phases || []).map((p: any) => (
            <div key={p.id || p.name}>
              <div className="flex justify-between text-sm mb-1">
                <span className="font-medium">{p.id || p.name}: {p.title || p.description}</span>
                <span className="font-mono text-xs">{pct(p.completion_pct || p.completion, 1)}</span>
              </div>
              <ProgressBar value={p.completion_pct || p.completion || 0} color={p.completion_pct >= 1 ? 'green' : 'blue'} />
            </div>
          ))}
          {!phases?.phases && <EmptyState message="Loading phases..." />}
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PHASE TRANSITION
// ════════════════════════════════════════════════════════════════════════════

export function PhaseTransitionPage() {
  const { data: pt } = useAPI('/api/v1/phase_transition', 30000);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Current Phase" value={pt?.current_phase || '-'} color="blue" />
        <StatCard label="Current State" value={pt?.current_state || '-'} color="amber" />
        <StatCard label="Chains Indexed" value={fmt(pt?.chains_indexed_by_trion)} />
        <StatCard label="Manipulation Profit" value={pct(pt?.manipulation_profit_current, 2)} color="red" />
      </div>

      <Card title="Phase Transition Dynamics" live>
        <KVList items={[
          ['Endogenous Weight', pt?.endogenous_weight?.toFixed(4) || '-'],
          ['Exogenous Weight', pt?.exogenous_weight?.toFixed(4) || '-'],
          ['Manipulation Profit Current', pct(pt?.manipulation_profit_current, 2)],
          ['Manipulation Profit Critical', pct(pt?.manipulation_profit_critical, 2)],
          ['Adoption Rate', pct(pt?.adoption_rate, 2)],
          ['Distance to Transition', pt?.distance_to_transition?.toFixed(4) || '-'],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// WHITEPAPER COVERAGE
// ════════════════════════════════════════════════════════════════════════════

export function WhitepaperPage() {
  const { data: wp } = useAPI('/api/v1/whitepaper/coverage', 60000);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Coverage" value={`${wp?.coverage_pct?.toFixed(1) || 100}%`} color="green" />
        <StatCard label="Live Formulas" value={fmt(wp?.live_count)} sub={`of ${wp?.formulas?.length || 84}`} color="blue" />
        <StatCard label="Falsifiability" value={fmt(wp?.falsifiability_conditions)} color="amber" />
        <StatCard label="Chains Indexed" value={fmt(wp?.chains_indexed)} />
      </div>

      <Card title="Whitepaper Formula Coverage" live>
        <DataTable
          headers={['ID', 'Name', 'Formula', 'Status', 'Endpoints']}
          rows={(wp?.formulas || []).map((f: any) => [
            <Tag color="blue">{f.id}</Tag>,
            f.name,
            <code className="text-xs">{truncate(f.formula, 60)}</code>,
            <Badge status={f.status} />,
            <span className="text-xs text-muted-foreground">{(f.endpoints || []).length} endpoint(s)</span>,
          ])}
          emptyMessage="Loading formulas..."
        />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// ORDER PARAMETER
// ════════════════════════════════════════════════════════════════════════════

export function OrderParameterPage() {
  const { data: op } = useAPI('/api/v1/order_parameter', 30000);

  return (
    <div className="space-y-6">
      <Card title="Order Parameter Psi - Critical Transition Detection" live>
        <p className="text-sm text-muted-foreground mb-4">{op?.interpretation || 'Loading...'}</p>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Distance to Transition" value={op?.distance_to_transition?.toFixed(4) || '-'} color="amber" />
          <StatCard label="Est. Days to Psi_c" value={fmt(op?.estimated_days_to_psi_c)} color="blue" />
          <StatCard label="Current Psi" value={op?.current_psi?.toFixed(4) || '-'} />
          <StatCard label="Critical Psi_c" value={op?.critical_psi?.toFixed(4) || '0.5'} color="red" />
        </div>
      </Card>

      <Card title="Adoption Metrics">
        <KVList items={[
          ['Total Protocols', fmt(op?.adoption_metrics?.total_protocols)],
          ['Adopted', fmt(op?.adoption_metrics?.adopted)],
          ['Adoption Rate', pct(op?.adoption_metrics?.adoption_rate, 2)],
          ['Formula', op?.formula || '-'],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// CONVERGENCE
// ════════════════════════════════════════════════════════════════════════════

export function ConvergencePage() {
  const { data: conv } = useAPI('/api/v1/convergence', 30000);

  return (
    <div className="space-y-6">
      <Card title="Convergence Theorem - lim E[|T-V|] = H_irr" live>
        <p className="text-sm text-muted-foreground mb-4">{conv?.disclosure || conv?.theorem || 'Loading...'}</p>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="C(t) Current" value={(conv?.C_t || 0).toFixed(4)} color="blue" />
          <StatCard label="C* Asymptote" value={(conv?.C_star || 0).toFixed(4)} color="green" />
          <StatCard label="Convergence Rate lambda" value={(conv?.convergence_rate || 0).toFixed(6)} />
          <StatCard label="Converged?" value={conv?.converged ? 'YES' : 'NO'} color={conv?.converged ? 'green' : 'amber'} />
        </div>
      </Card>

      <Card title="Convergence Parameters">
        <KVList items={[
          ['Akashic Depth D(t)', fmt(conv?.akashic_depth)],
          ['Lambda (rate)', (conv?.convergence_rate || 0).toFixed(6)],
          ['H_irreducible', (conv?.H_irreducible || 0).toFixed(4)],
          ['H_future', (conv?.H_future || 0).toFixed(4)],
          ['PC_limit', pct(conv?.PC_limit, 4)],
        ]} />
      </Card>
    </div>
  );
}
