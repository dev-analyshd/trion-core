/**
 * TRION UI Assessment Implementation
 * ================================
 * Per the "Super-Analyst UI/UX Assessment" document:
 *   P0: BEO Lookup Toolbox + BOT Chain dedicated view
 *   P1: Live Event Stream + Time-series sparklines
 *   P2: BTCP Visualization + Continuum page
 *   P3: Aesthetic refinements (silence mode, color semantics)
 *
 * All built as new page components in the existing Next.js frontend.
 */

'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { Card, StatCard, ProgressBar, Badge, DataTable, KVList, Tag, CodeBlock, EmptyState } from '../components/ui';
import { useAPI, useStream } from '../lib/hooks';
import { fetchAPI, fmt, pct, tfmt, dtfmt, truncate, hex, compact, statusColor, ms } from '../lib/api';
import * as Icons from 'lucide-react';

// ════════════════════════════════════════════════════════════════════════════
// P0: BEO LOOKUP TOOLBOX
// ════════════════════════════════════════════════════════════════════════════

export function BEOLookupPage() {
  const [address, setAddress] = useState('');
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const lookup = async (addr?: string) => {
    const query = addr || address;
    if (!query || query.length < 10) return;
    setLoading(true);
    // Query the signal endpoint for coherence + the BH ledger for history
    const [signalRes, bhRes] = await Promise.all([
      fetchAPI<any>(`/api/v1/signal/${query}`),
      fetchAPI<any>(`/api/v1/bh/ledger/${query}`),
    ]);
    setResult({
      signal: signalRes.ok ? signalRes.data : null,
      bhHistory: bhRes.ok ? bhRes.data : null,
      address: query,
      error: !signalRes.ok && !bhRes.ok ? signalRes.error : null,
    });
    setLoading(false);
  };

  return (
    <div className="space-y-6">
      <Card title="🛠 TRION Toolbox - Paste any address / BEO / BH">
        <div className="flex gap-2">
          <input
            type="text"
            value={address}
            onChange={e => setAddress(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && lookup()}
            placeholder="0x... (any EVM address)"
            className="flex-1 px-4 py-3 rounded-lg border border-border bg-input text-sm font-mono"
          />
          <button
            onClick={() => lookup()}
            disabled={loading}
            className="px-6 py-3 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            {loading ? 'Querying...' : 'QUERY'}
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button onClick={() => { setAddress('0x7a250d5630b4cf539739df2c5dacb4c659f2488d'); lookup('0x7a250d5630b4cf539739df2c5dacb4c659f2488d'); }}
            className="px-3 py-1 rounded-lg border border-border text-xs hover:bg-muted">Quick: Uniswap Router</button>
          <button onClick={() => { setAddress('0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'); lookup('0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'); }}
            className="px-3 py-1 rounded-lg border border-border text-xs hover:bg-muted">Quick: USDC</button>
        </div>
      </Card>

      {result?.signal && (
        <Card title={`🧬 BEO ${hex(result.address, 12)}`} live>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <StatCard label="Coherence Score" value={pct(result.signal.coherence_score || result.signal.coherence, 2)} color={result.signal.coherent ? 'green' : 'red'} />
                <StatCard label="Threshold Theta(t)" value={pct(result.signal.threshold, 2)} color="amber" />
                <StatCard label="Archetype" value={result.signal.archetype || '-'} color="purple" />
                <StatCard label="Status" value={result.signal.coherent ? 'COHERENT' : 'SILENCED'} color={result.signal.coherent ? 'green' : 'red'} />
              </div>
              <KVList items={[
                ['Entity ID', hex(result.signal.entity_id || result.address, 16)],
                ['Limiting Plane', result.signal.limiting_plane || '-'],
                ['Silence Gap', (result.signal.silence_gap || 0).toFixed(4)],
                ['BEO Score', (result.signal.beo_score || 0).toFixed(4)],
              ]} />
            </div>
            <div>
              <div className="text-xs text-muted-foreground mb-2">7-Plane Coherence Breakdown</div>
              {(result.signal.plane_breakdown || {}).entries?.map(([plane, val]: any) => (
                <div key={plane} className="mb-2">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-muted-foreground">{plane}</span>
                    <span className="font-mono">{Number(val).toFixed(3)}</span>
                  </div>
                  <ProgressBar value={val} color={val > 0.55 ? 'green' : 'red'} height={6} />
                </div>
              )) || <EmptyState message="No plane breakdown available" />}
            </div>
          </div>
        </Card>
      )}

      {result?.bhHistory && (
        <Card title="Behavioral History - Recent BH Records" live>
          <DataTable
            headers={['Time', 'Chain', 'Event', 'Block', 'Tx Hash']}
            rows={(result.bhHistory.records || result.bhHistory || []).slice(0, 20).map((r: any) => [
              tfmt(r.ts),
              <Badge status={r.chain_label || r.chain} />,
              <Tag color="blue">{r.event_type_name || r.event_type}</Tag>,
              fmt(r.block_num),
              <span className="font-mono text-xs text-muted-foreground">{hex(r.tx_hash, 12)}</span>,
            ])}
            emptyMessage="No BH history for this entity"
          />
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// P1: LIVE EVENT STREAM
// ════════════════════════════════════════════════════════════════════════════

export function LiveEventStreamPage() {
  const { items: bhItems } = useStream('/api/v1/bh/recent_feed', 2000);
  const { items: feedItems } = useStream('/api/v1/feed', 3000);
  const { data: streamer } = useAPI('/api/v1/btcp/streamer/status', 2000);
  const { data: health } = useAPI('/api/v1/health', 3000);

  // Generate events from live data
  const events: any[] = [];
  const now = Date.now() / 1000;

  // BH events
  bhItems.slice(0, 15).forEach((bh: any) => {
    const age = now - (bh.ts || bh.timestamp || now);
    events.push({
      type: 'BH_HASH',
      color: '#22d3ee',
      icon: '⚡',
      age_sec: age,
      message: `Entity ${hex(bh.entity_id, 8)} on ${bh.chain_label || bh.chain} - ${bh.event_type_name || bh.event_type}`,
      detail: `tx ${hex(bh.tx_hash, 10)}...`,
    });
  });

  // Signal events
  feedItems.slice(0, 5).forEach((s: any) => {
    const age = now - (s.timestamp || now);
    events.push({
      type: s.coherent ? 'SIGNAL' : 'SILENCE',
      color: s.coherent ? '#10b981' : '#f43f5e',
      icon: s.coherent ? '🟢' : '⚫',
      age_sec: age,
      message: `${s.protocol_name || hex(s.entity_id, 8)} Coherence=${pct(s.coherence_score, 2)}`,
      detail: s.coherent ? 'VAL signal emitted' : `SILENCE - below Theta=${pct(s.threshold, 2)}`,
    });
  });

  // Oracle self-coherence event
  if (health) {
    const coh = health.dynamic_threshold || 0.5;
    events.push({
      type: coh > 0.55 ? 'ORACLE_OK' : 'ORACLE_SILENCE',
      color: coh > 0.55 ? '#10b981' : '#fbbf24',
      icon: coh > 0.55 ? '🟢' : '🟡',
      age_sec: 0,
      message: `Oracle self-coherence ${coh.toFixed(4)}`,
      detail: coh > 0.55 ? 'HONEST - above publication threshold' : 'STRUCTURED SILENCE - below 0.55',
    });
  }

  // Sort by age (newest first)
  events.sort((a, b) => a.age_sec - b.age_sec);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Events Streamed" value={fmt(events.length)} color="blue" />
        <StatCard label="BHs/sec" value={streamer?.bhs_per_second?.toFixed(0) || '0'} color="green" />
        <StatCard label="Chains Active" value={fmt(streamer?.chains_active || 0)} color="purple" />
        <StatCard label="Oracle Status" value={health?.dynamic_threshold > 0.55 ? 'HONEST' : 'SILENT'} color={health?.dynamic_threshold > 0.55 ? 'green' : 'amber'} />
      </div>

      <Card title="📡 Live Event Stream - real-time" live>
        <div className="space-y-2 max-h-[600px] overflow-y-auto">
          {events.length === 0 ? (
            <EmptyState message="Connecting to live data streams..." />
          ) : (
            events.map((e, i) => (
              <div key={i} className="flex items-start gap-3 p-3 rounded-lg border border-border hover:bg-muted/30 transition-colors">
                <div className="text-lg flex-shrink-0">{e.icon}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono font-bold" style={{ color: e.color }}>{e.type}</span>
                    <span className="text-xs text-muted-foreground">
                      {e.age_sec < 60 ? `${Math.floor(e.age_sec)}s ago` :
                       e.age_sec < 3600 ? `${Math.floor(e.age_sec / 60)}m ago` :
                       `${Math.floor(e.age_sec / 3600)}h ago`}
                    </span>
                  </div>
                  <div className="text-sm truncate">{e.message}</div>
                  <div className="text-xs text-muted-foreground truncate">{e.detail}</div>
                </div>
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// P3: TIME-SERIES SPARKLINES (simulated from live data)
// ════════════════════════════════════════════════════════════════════════════

function Sparkline({ data, color, height = 40, label, value }: { data: number[]; color: string; height?: number; label: string; value: string }) {
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = max - min || 1;
  const points = data.map((d, i) => {
    const x = (i / (data.length - 1)) * 100;
    const y = height - ((d - min) / range) * height;
    return `${x},${y}`;
  }).join(' ');

  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono font-bold" style={{ color }}>{value}</span>
      </div>
      <svg viewBox={`0 0 100 ${height}`} className="w-full" style={{ height }}>
        <polyline
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          points={points}
        />
        <polyline
          fill={color}
          fillOpacity="0.1"
          stroke="none"
          points={`0,${height} ${points} 100,${height}`}
        />
      </svg>
    </div>
  );
}

export function TimeSeriesPage() {
  const { data: health } = useAPI('/api/v1/health', 3000);
  const { data: streamer } = useAPI('/api/v1/btcp/streamer/status', 2000);
  const { data: bhStats } = useAPI('/api/v1/bh/stats', 5000);

  // Simulate time-series from live data
  const [cohHistory, setCohHistory] = useState<number[]>(Array(30).fill(0.4));
  const [bhRateHistory, setBhRateHistory] = useState<number[]>(Array(30).fill(0));
  const [infoHistory, setInfoHistory] = useState<number[]>(Array(30).fill(0));

  useEffect(() => {
    const i = setInterval(() => {
      if (health?.dynamic_threshold) {
        setCohHistory(prev => [...prev.slice(1), health.dynamic_threshold]);
      }
      if (streamer?.bhs_per_second) {
        setBhRateHistory(prev => [...prev.slice(1), streamer.bhs_per_second]);
      }
      const totalBhs = streamer?.total_bhs || 0;
      if (totalBhs > 0) {
        setInfoHistory(prev => [...prev.slice(1), totalBhs]);
      }
    }, 2000);
    return () => clearInterval(i);
  }, [health, streamer]);

  const totalBHs = Object.values(bhStats?.per_chain || {}).reduce((a: number, b: any) => a + Number(b), 0);

  return (
    <div className="space-y-6">
      <Card title="Time-Series Data - Behavioral Truth is Temporal" live>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="p-4 rounded-lg border border-border">
            <Sparkline
              data={cohHistory}
              color="#22d3ee"
              label="Oracle Coherence Coherence"
              value={health?.dynamic_threshold?.toFixed(4) || '-'}
            />
            <div className="mt-2 text-xs text-muted-foreground">
              {health?.dynamic_threshold > 0.55 ?
                '🟢 HONEST - above publication threshold' :
                '🟡 STRUCTURED SILENCE - below 0.55'}
            </div>
          </div>

          <div className="p-4 rounded-lg border border-border">
            <Sparkline
              data={bhRateHistory}
              color="#10b981"
              label="BH Emission Rate (per sec)"
              value={`${streamer?.bhs_per_second?.toFixed(0) || 0}/s`}
            />
            <div className="mt-2 text-xs text-muted-foreground">
              {streamer?.chains_active || 0} chains streaming
            </div>
          </div>

          <div className="p-4 rounded-lg border border-border">
            <Sparkline
              data={infoHistory}
              color="#8b5cf6"
              label="Information Information Flow - BH accumulation"
              value={fmt(totalBHs)}
            />
            <div className="mt-2 text-xs text-muted-foreground">
              🔒 Thermodynamically sealed - always increasing
            </div>
          </div>
        </div>
      </Card>

      <Card title="Per-Chain BH Distribution (Live)" live>
        <div className="space-y-2">
          {Object.entries(bhStats?.per_chain || {}).map(([chain, count]: any) => {
            const max = Math.max(...Object.values(bhStats?.per_chain || {}).map(Number));
            return (
              <div key={chain}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="capitalize">{chain}</span>
                  <span className="font-mono font-bold">{fmt(count)}</span>
                </div>
                <ProgressBar value={count} max={max} color="green" height={8} />
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// P2: BTCP VISUALIZATION PAGE (6-step flow + route comparison + gas savings)
// ════════════════════════════════════════════════════════════════════════════

export function BTCPVisualizationPage() {
  const { data: bibl } = useAPI('/api/v1/btcp/bibl/snapshot', 10000);
  const { data: bootstrap } = useAPI('/api/v1/btcp/mainnet_bootstrap', 30000);

  const routeTypes = [
    { id: 'SINGLE_CHAIN', name: 'Direct Single-Chain', when: 'Target chain has superior liquidity and finality', gas: 31.00, score: 0.41, finality: '12 seconds', color: '#64748b', desc: 'Standard execution on one chain only. Used as baseline.' },
    { id: 'SPLIT', name: 'Anchor + Execute Split', when: 'Source chain has cheap security, target has cheap execution', gas: 0.98, score: 0.94, finality: 'max(12s, 2s)', color: '#22d3ee', desc: 'Anchor behavioral proof on Ethereum (security), execute on Base (cheap gas). Assets never leave Ethereum.' },
    { id: 'NETTING', name: 'Netting (Counterparty Found)', when: 'Entity with opposite intent found simultaneously', gas: 0.05, score: 0.98, finality: '12 seconds', color: '#10b981', desc: 'Entity A wants USDC->ETH, Entity B wants ETH->USDC. Both execute natively. Zero cross-chain movement. Optimal by construction.' },
    { id: 'PARALLEL', name: 'Parallel Split', when: 'Large intent split across multiple chains simultaneously', gas: 1.80, score: 0.91, finality: '12 seconds', color: '#8b5cf6', desc: '$1M split across 5 chains in parallel. Reduces price impact and increases completion speed.' },
    { id: 'MULTI_HOP', name: 'Multi-Hop (A->B->C)', when: 'Intermediate chain provides liquidity bridge', gas: 1.20, score: 0.88, finality: 'max(12s, 400ms)', color: '#fbbf24', desc: 'Ethereum->Solana->Arbitrum when Solana provides intermediate liquidity advantage. Nested escrow guarantees atomicity.' },
    { id: 'DEFERRED', name: 'Deferred (Optimal Window)', when: 'Current conditions suboptimal, intent not urgent', gas: 0.42, score: 0.96, finality: 'within 24h', color: '#f472b6', desc: 'Biological Rhythm Timer finds optimal window: circadian gas low AND liquidity peak AND MEV valley. Auto-executes at best conditions.' },
  ];

  const sixSteps = [
    { num: 1, name: 'Intent Registration', desc: 'Entity submits intent (not transaction). BIBL (Behavioral Inter-Block Layer) reads all chains simultaneously during the inter-block window.', color: '#22d3ee' },
    { num: 2, name: 'Route Calculation', desc: 'BTCP score computed for all candidate routes across 6 route types. Natural Liquidity, gas, finality, cross-chain coherence, and BEO continuity weighted.', color: '#8b5cf6' },
    { num: 3, name: 'Cross-Chain Proof', desc: 'Anchor behavioral hash + diversity-weighted consensus proof constructed. HHI (Concentration Index) bounded at 2500.', color: '#10b981' },
    { num: 4, name: 'VM Translation', desc: '20 behavioral event types translated into each chain native execution through thin adapters. Same intent, different bytecode - identical behavioral meaning.', color: '#fbbf24' },
    { num: 5, name: 'Gas Sharing Protocol', desc: 'Anchor chain covers security cost, execution chain covers computation cost. $10K swap costs $31 on ETH alone, $0.98 via ETH->Base, $0.05 via netting.', color: '#f472b6' },
    { num: 6, name: 'Finalization + Recording', desc: 'Behavioral hash stored in Akashic Index, linked by BTCP route ID. Signal emitted with gas savings data. Append-only, instantly final via DW-BFT consensus.', color: '#ef4444' },
  ];

  return (
    <div className="space-y-8">
      {/* 6-Step Routing Flow */}
      <Card title="6-Step BTCP Routing Pipeline - Animated Flow">
        <div className="flex flex-col md:flex-row gap-3 overflow-x-auto">
          {sixSteps.map((step, i) => (
            <div key={step.num} className="flex-1 min-w-[180px] p-4 rounded-lg border border-border relative">
              <div className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold mb-3"
                   style={{ backgroundColor: step.color }}>
                {step.num}
              </div>
              <div className="font-semibold text-sm mb-1">{step.name}</div>
              <div className="text-xs text-muted-foreground">{step.desc}</div>
              {i < sixSteps.length - 1 && (
                <div className="hidden md:block absolute top-1/2 -right-2 text-muted-foreground text-xl">{'->'}</div>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* Route Type Comparison */}
      <Card title="Route Type Comparison - 6 BTCP Route Types">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {routeTypes.map(rt => (
            <div key={rt.id} className={`p-4 rounded-lg border-2 ${rt.id === 'NETTING' ? 'border-emerald-500/50 bg-emerald-500/5' : 'border-border'}`}
                 style={{ borderLeftWidth: '4px', borderLeftColor: rt.color }}>
              <div className="flex items-center justify-between mb-2">
                <span className="font-semibold text-sm">{rt.name}</span>
                {rt.id === 'NETTING' && <Badge status="OPTIMAL" />}
              </div>
              <div className="text-3xl font-bold mb-1" style={{ color: rt.color }}>${rt.gas.toFixed(2)}</div>
              <div className="text-xs text-muted-foreground mb-2">BTCP Score: {rt.score} - Finality: {rt.finality}</div>
              <div className="text-xs text-muted-foreground mb-2">When: {rt.when}</div>
              <div className="text-xs">{rt.desc}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* Gas Comparison Visual */}
      <Card title="Gas Cost Comparison - $10K USDC->ETH Swap">
        <div className="space-y-4">
          {[
            { label: 'Direct ETH only', cost: 31.00, color: '#64748b', pct: 100 },
            { label: 'Anchor ETH -> Execute Base', cost: 0.98, color: '#22d3ee', pct: 3.2 },
            { label: 'Netting (counterparty found)', cost: 0.05, color: '#10b981', pct: 0.16 },
          ].map(g => (
            <div key={g.label}>
              <div className="flex justify-between text-sm mb-1">
                <span>{g.label}</span>
                <span className="font-mono font-bold" style={{ color: g.color }}>${g.cost.toFixed(2)}</span>
              </div>
              <div className="h-4 bg-muted rounded overflow-hidden">
                <div className="h-full rounded transition-all duration-700" style={{ width: `${g.pct}%`, backgroundColor: g.color }} />
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 p-3 rounded bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-600">
          Netting saves 99.8% vs direct ETH, 94.9% vs split route. Zero cross-chain asset movement.
        </div>
      </Card>

      {/* BIBL Live Snapshot */}
      {bibl && (
        <Card title="BIBL Tier-1 Snapshot - Live Chain Data" live>
          <DataTable
            headers={['Chain', 'NL Score', 'Gas Forecast', 'CC Coherence', 'MF Score', 'Finality (s)']}
            rows={Object.entries(bibl?.snapshot || {}).map(([chain, s]: any) => [
              chain,
              pct(s.nl_score, 2),
              `$${s.gas_forecast?.toFixed(2)}`,
              pct(s.cc_coherence, 2),
              pct(s.mf_score, 2),
              s.finality_avg_sec?.toFixed(1),
            ])}
            emptyMessage="Loading BIBL snapshot..."
          />
          <div className="mt-3 grid grid-cols-3 gap-3 text-xs">
            <div>Tier 1 target: {bibl?.tier_1_latency_target_ms}ms</div>
            <div>Tier 2 target: {bibl?.tier_2_latency_target_ms}ms</div>
            <div>Total BIBL: {bibl?.total_bibl_latency_target_ms}ms</div>
          </div>
        </Card>
      )}

      {/* Network Effect */}
      <Card title="Network Effect - Bridge Pairs Eliminated = N * (N-1) / 2">
        <div className="flex flex-col md:flex-row gap-3">
          {[
            { chains: 3, pairs: 3, label: 'First 3 EVM chains' },
            { chains: 6, pairs: 15, label: 'Major EVM L2s added' },
            { chains: 10, pairs: 45, label: 'Solana integration begins' },
            { chains: 20, pairs: 190, label: 'Cross-VM BTCP live' },
            { chains: 50, pairs: 1225, label: 'Cosmos + Move + more' },
            { chains: 100, pairs: 4950, label: 'Bridges become legacy' },
          ].map((s, i) => (
            <div key={i} className="flex-1 p-4 rounded-lg border border-border relative">
              {i < 5 && <div className="hidden md:block absolute top-1/2 -right-2 text-muted-foreground text-xl">{'->'}</div>}
              <div className="text-2xl font-bold text-cyan-500">{s.chains}</div>
              <div className="text-xs text-muted-foreground">chains</div>
              <div className="text-lg font-bold text-emerald-500 mt-2">{s.pairs.toLocaleString()}</div>
              <div className="text-xs text-muted-foreground">pairs eliminated</div>
              <div className="text-xs mt-1">{s.label}</div>
            </div>
          ))}
        </div>
        {bootstrap && (
          <div className="mt-4 p-3 rounded bg-cyan-500/10 border border-cyan-500/30 text-sm">
            Current: {bootstrap.total_chains} chains - {bootstrap.bridge_pairs_eliminated?.toLocaleString()} pairs eliminated - {bootstrap.vm_families} VM families
          </div>
        )}
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// P2: CONTINUUM VISUALIZATION PAGE
// ════════════════════════════════════════════════════════════════════════════

export function ContinuumVisualizationPage() {
  const { data: faiss } = useAPI('/api/v1/faiss', 5000);
  const { data: streamer } = useAPI('/api/v1/btcp/streamer/status', 2000);

  const engines = [
    { id: 'BID', name: 'Behavioral Intent Detection', color: '#22d3ee',
      plainEnglish: 'The system detects that an entity is likely to trade before the entity consciously decides. Nine-dimensional information flow signature changes measurably in the blocks preceding a trade.',
      whatItDoes: 'Watches the 9 raw features of behavioral flow. When the pattern matches the known precursor signature, the system flags it.',
      keyConstraint: 'The entity retains full agency. Detection never becomes commitment automatically.' },
    { id: 'CME', name: 'Complement Matching Engine', color: '#8b5cf6',
      plainEnglish: 'Finds, in real time across all chains, the entity whose behavioral pattern is the thermodynamic opposite - not a counterparty in the order book sense, but an entity who genuinely wants the opposite.',
      whatItDoes: 'When Entity A shows intent precursor for USDC->ETH, the engine searches FAISS vector space for Entity B whose pattern indicates ETH->USDC intent.',
      keyProperty: 'Semantic matching, not price ladder matching. Price comes from the TRION behavioral valuation signal.' },
    { id: 'PMO', name: 'Pre-Manifest Order System', color: '#10b981',
      plainEnglish: 'An entity commits to a trade before expressing it to any market, in exchange for a guaranteed better price and a share of the spread they would have otherwise lost.',
      whatItDoes: 'Entity receives a Pre-Manifest Order instrument. They confirm. The commitment is hashed and recorded. Counterparty already found by CME.',
      adoptionDriver: 'Adoption is economically rational, not forced. Every entity who accepts is strictly better off.' },
    { id: 'BDC', name: 'Behavioral Depth Credit', color: '#fbbf24',
      plainEnglish: 'An entity\'s accumulated behavioral history functions as creditworthy collateral for undercollateralized positions. Depth cannot be bought, transferred, lost, or forged.',
      whatItDoes: 'An entity with 2 years of consistent honest history can participate at up to 10* their typical trade size, backed by behavioral depth rather than locked capital.',
      keyProperties: 'Cannot be bought. Cannot be transferred. Compounds automatically. Forgery bounded by Kolmogorov complexity.' },
    { id: 'THERMO', name: 'Thermodynamic Settlement', color: '#f472b6',
      plainEnglish: 'Settlement is triggered by both parties being simultaneously coherent - not by time locks, human decisions, or governance votes.',
      whatItDoes: 'BTCP escrow on both chains watches the TRION coherence signal. When both entities exceed their threshold simultaneously, escrow releases.',
      coreInsight: 'Behavioral manipulation is self-defeating by construction.' },
  ];

  const wasteBreakdown = [
    { name: 'MEV Extraction', value: 1.3, color: '#ef4444' },
    { name: 'DEX Fees', value: 4.2, color: '#f97316' },
    { name: 'Bridge Fees', value: 0.6, color: '#fbbf24' },
    { name: 'Bridge Exploits', value: 2.8, color: '#ef4444' },
    { name: 'Slippage Losses', value: 3.1, color: '#8b5cf6' },
    { name: 'Liquidation Cascades', value: 1.9, color: '#22d3ee' },
  ];

  return (
    <div className="space-y-8">
      {/* Hero */}
      <Card title="Continuum - The Behavioral Clearing Network">
        <p className="text-sm text-muted-foreground mb-4">
          Behavioral reality precedes price reality by a measurable window. On Ethereum: 3 to 12 blocks (36 to 144 seconds).
          On Solana: 50 to 200 slots (20 to 80 seconds). Continuum operates in this gap.
        </p>
      </Card>

      {/* $13.9B Waste Breakdown */}
      <Card title="$13.9B Annual Market Waste - What Continuum Eliminates">
        <div className="space-y-3">
          {wasteBreakdown.map(item => (
            <div key={item.name}>
              <div className="flex justify-between text-sm mb-1">
                <span>{item.name}</span>
                <span className="font-mono font-bold" style={{ color: item.color }}>${item.value}B</span>
              </div>
              <ProgressBar value={item.value} max={5} color="purple" height={8} />
            </div>
          ))}
        </div>
        <div className="mt-4 text-center text-2xl font-bold text-rose-500">Total: $13.9B/year</div>
      </Card>

      {/* 5 Engines */}
      <Card title="5 Continuum Engines - Operating in the gap between behavioral reality and price reality">
        <div className="space-y-4">
          {engines.map(e => (
            <div key={e.id} className="p-5 rounded-lg border border-border" style={{ borderLeftWidth: '4px', borderLeftColor: e.color }}>
              <div className="flex items-center gap-3 mb-3">
                <div className="px-3 py-1 rounded text-xs font-mono font-bold text-white" style={{ backgroundColor: e.color }}>
                  {e.id}
                </div>
                <div className="font-bold text-base">{e.name}</div>
              </div>
              <div className="text-sm mb-2">{e.plainEnglish}</div>
              <div className="text-sm text-muted-foreground mb-2"><span className="text-cyan-500 font-semibold">What it does:</span> {e.whatItDoes}</div>
              <div className="text-sm text-muted-foreground">
                <span className="text-emerald-500 font-semibold">Key insight:</span> {e.keyConstraint || e.keyProperty || e.adoptionDriver || e.coreInsight || e.keyProperties}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* CCP Distribution */}
      <Card title="Complement Certainty Premium (CCP) Distribution">
        <p className="text-sm text-muted-foreground mb-4">The spread that market makers and MEV bots currently extract flows back to both traders.</p>
        <div className="grid grid-cols-4 gap-4">
          {[
            { label: 'Entity A', value: 40, color: '#22d3ee' },
            { label: 'Entity B', value: 40, color: '#10b981' },
            { label: 'Validators', value: 12, color: '#8b5cf6' },
            { label: 'Protocol', value: 8, color: '#fbbf24' },
          ].map(c => (
            <div key={c.label} className="text-center p-4 rounded-lg border border-border">
              <div className="text-3xl font-bold" style={{ color: c.color }}>{c.value}%</div>
              <div className="text-xs text-muted-foreground mt-1">{c.label}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* FAISS Live Integration */}
      <Card title="FAISS Vector Space - Live CME Foundation" live>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Indexed Vectors" value={fmt(Math.max(faiss?.indexed_vectors || 0, streamer?.faiss_vectors_accumulated || 0))} color="purple" sub="128-dim BEO" />
          <StatCard label="Entities Tracked" value={fmt(faiss?.entities_tracked || 0)} color="blue" />
          <StatCard label="BHs/sec" value={streamer?.bhs_per_second?.toFixed(0) || '0'} color="green" />
          <StatCard label="Chains Active" value={fmt(streamer?.chains_active || 0)} color="amber" />
        </div>
        <div className="mt-3 text-xs text-muted-foreground">
          CME searches this FAISS vector space to find complement entities. {fmt(Math.max(faiss?.indexed_vectors || 0, streamer?.faiss_vectors_accumulated || 0))} behavioral vectors across {fmt(faiss?.entities_tracked || 0)} entities.
        </div>
      </Card>
    </div>
  );
}
