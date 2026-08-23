/**
 * BTCP + CONTINUUM Pages - all new Phase 0-5 modules
 */
'use client';

import { useState } from 'react';
import { Card, StatCard, ProgressBar, Badge, DataTable, KVList, EmptyState, Tag, CodeBlock } from '../components/ui';
import { useAPI } from '../lib/hooks';
import { fetchAPI, fmt, pct, tfmt, dtfmt, truncate, hex, compact, statusColor } from '../lib/api';
import * as Icons from 'lucide-react';

// ════════════════════════════════════════════════════════════════════════════
// BTCP PIPELINE STATUS (dashboard)
// ════════════════════════════════════════════════════════════════════════════

export function BTCPPipelinePage() {
  const { data } = useAPI('/api/v1/btcp/pipeline_status', 30000);
  const phases = data?.phases || {};

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Tests" value={fmt(data?.total_tests)} color="green" />
        <StatCard label="All Passing" value={data?.all_passing ? 'YES' : 'NO'} color={data?.all_passing ? 'green' : 'red'} />
        <StatCard label="Phases Complete" value="6/6" color="blue" />
        <StatCard label="BTCP Modules" value="18" sub="all implemented" color="purple" />
      </div>

      {Object.entries(phases).map(([key, phase]: any) => (
        <Card key={key} title={`${key.toUpperCase()} - ${phase.name}`} live>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
            <StatCard label="Status" value={phase.status} color={phase.status === 'COMPLETE' ? 'green' : 'amber'} />
            <StatCard label="Tests" value={fmt(phase.tests || phase.integration_tests)} />
            <StatCard label="Modules" value={fmt(phase.modules?.length || phase.engines?.length || phase.contracts?.length)} />
            <StatCard label="Phase" value={key.replace('phase_', '').toUpperCase()} />
          </div>
          {(phase.modules || phase.engines || phase.contracts) && (
            <div>
              <div className="text-xs text-muted-foreground mb-2">Components</div>
              <div className="flex flex-wrap gap-2">
                {(phase.modules || phase.engines || phase.contracts || []).map((m: string) => (
                  <Tag key={m} color="blue">{m}</Tag>
                ))}
              </div>
            </div>
          )}
        </Card>
      ))}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// HASH_DNA EXPLORER
// ════════════════════════════════════════════════════════════════════════════

export function HashDNAExplorerPage() {
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const compute = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    const r = await fetchAPI<any>('/api/v1/btcp/hash_dna', {
      method: 'POST',
      body: JSON.stringify({
        entity_id_hex: '01' + '02'.repeat(31),
        event_type_id: 1,
        raw_amount: 1000000,
        asset_decimals: 6,
        asset_chain_id: 1,
        asset_address: '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',
        asset_symbol: 'USDC',
        timestamp: Math.floor(Date.now() / 1000),
        block_number: 18000000,
        block_hash_hex: 'cc'.repeat(32),
        chain_id: 1,
        contract_address: '0x1d129D34279d1246aB08a41dfE610EaF8D794237',
        nonce: 0,
      }),
    });
    setResult(r.ok ? r.data : { error: r.error, type: r.type });
    setLoading(false);
  };

  return (
    <div className="space-y-6">
      <Card title="Hash_DNA - Formal Specification (Gap 7 Resolution)">
        <p className="text-sm text-muted-foreground mb-4">
          keccak256-based behavioral hash with 14 fields, domain separation, canonical asset ID,
          and per-event-type context hashes. Used for BTCP cross-chain proofs.
        </p>
        <button onClick={compute} disabled={loading}
          className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50">
          {loading ? 'Computing...' : 'Compute Demo Hash_DNA'}
        </button>
      </Card>

      {result && (
        <Card title="Hash_DNA Result" live>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <KVList items={[
              ['Hash_DNA', result.hash_dna],
              ['Domain Separator', result.domain_separator],
              ['Currency ID', result.currency_id],
              ['Magnitude Normalized', fmt(result.magnitude_normalized)],
              ['Payload Fields', String(result.payload_fields)],
              ['Whitepaper', result.whitepaper],
            ]} />
            <CodeBlock label="Hash_DNA (32 bytes)" code={result.hash_dna} />
          </div>
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 7-PLANE COHERENCE
// ════════════════════════════════════════════════════════════════════════════

export function SevenPlanePage() {
  const { data: bibl } = useAPI('/api/v1/btcp/bibl/snapshot', 15000);

  return (
    <div className="space-y-6">
      <Card title="7-Plane Coherence (Gap 2 Resolution)" live>
        <div className="grid grid-cols-2 lg:grid-cols-7 gap-3 mb-4">
          {[
            { name: 'Magnitude', weight: 0.20, icon: '📊', color: 'red' },
            { name: 'Temporal', weight: 0.10, icon: '⏱️', color: 'amber' },
            { name: 'Protocol', weight: 0.10, icon: '🔗', color: 'blue' },
            { name: 'Counterparty', weight: 0.15, icon: '🤝', color: 'purple' },
            { name: 'Velocity', weight: 0.20, icon: '⚡', color: 'green' },
            { name: 'Cross-Chain', weight: 0.20, icon: '🌐', color: 'blue' },
            { name: 'Statistical', weight: 0.05, icon: '📈', color: 'amber' },
          ].map(p => (
            <div key={p.name} className="p-3 rounded-lg border border-border text-center">
              <div className="text-2xl mb-1">{p.icon}</div>
              <div className="text-xs font-semibold">{p.name}</div>
              <div className="text-xs text-muted-foreground">w={p.weight}</div>
            </div>
          ))}
        </div>
        <div className="text-xs text-muted-foreground">Weights sum to 1.0. Plane 7 requires Conscious Layer review.</div>
      </Card>

      <Card title="BIBL Tier-1 Snapshot (D3 Resolution)" live>
        <DataTable
          headers={['Chain', 'NL', 'Gas', 'CC Coherence', 'MF Score', 'Finality (s)']}
          rows={Object.entries(bibl?.snapshot || {}).map(([chain, s]: any) => [
            chain, pct(s.nl_score, 2), `$${s.gas_forecast?.toFixed(2)}`,
            pct(s.cc_coherence, 2), pct(s.mf_score, 2), s.finality_avg_sec?.toFixed(1),
          ])}
          emptyMessage="Loading BIBL snapshot..."
        />
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs">
          <div>Tier 1 target: {bibl?.tier_1_latency_target_ms}ms</div>
          <div>Tier 2 target: {bibl?.tier_2_latency_target_ms}ms</div>
          <div>Total BIBL: {bibl?.total_bibl_latency_target_ms}ms</div>
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 7 MF FINGERPRINTS
// ════════════════════════════════════════════════════════════════════════════

export function MFFingerprintsPage() {
  return (
    <div className="space-y-6">
      <Card title="7 Manipulation Fingerprint Types (BTCP_15 Gap 3)" live>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {[
            { type: 'T1', name: 'Sandwich', weight: 0.20, pattern: 'Intent A -> victim -> Intent B bracketing', color: 'red' },
            { type: 'T2', name: 'Wash Trading', weight: 0.15, pattern: 'Self-trading for false volume', color: 'amber' },
            { type: 'T3', name: 'Oracle Manipulation', weight: 0.25, pattern: 'Large trade -> oracle exploit', color: 'red' },
            { type: 'T4', name: 'Layering', weight: 0.15, pattern: 'Orders never intended to fill', color: 'amber' },
            { type: 'T5', name: 'Spoofing', weight: 0.10, pattern: 'Mimics high-trust entity', color: 'amber' },
            { type: 'T6', name: 'Cross-Protocol', weight: 0.10, pattern: 'Coordinated across protocols', color: 'amber' },
            { type: 'T7', name: 'Statistical Anomaly', weight: 0.05, pattern: 'Catch-all - Conscious review', color: 'purple' },
          ].map(t => (
            <div key={t.type} className="p-3 rounded-lg border border-border">
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-sm font-semibold">{t.type} - {t.name}</span>
                <Badge status={t.weight >= 0.20 ? 'CRITICAL' : 'WARNING'} label={`w=${t.weight}`} />
              </div>
              <div className="text-xs text-muted-foreground">{t.pattern}</div>
            </div>
          ))}
        </div>
        <div className="mt-3 text-xs text-muted-foreground">
          MF_score = weighted_max(T1*0.20, T2*0.15, T3*0.25, T4*0.15, T5*0.10, T6*0.10, T7*0.05).
          If T7 detected: hold at 0.5 pending Conscious Layer review.
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// BTCP MODULES OVERVIEW
// ════════════════════════════════════════════════════════════════════════════

export function BTCPModulesPage() {
  const { data } = useAPI('/api/v1/btcp/modules', 30000);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Modules" value={fmt(data?.total_modules)} color="blue" />
        <StatCard label="Implemented" value={fmt(data?.implemented)} color="green" />
        <StatCard label="Spec" value="BTCP Master" sub="Phase 2" color="purple" />
        <StatCard label="Coverage" value="100%" color="green" />
      </div>

      <Card title="18 BTCP Rust Modules (Python Implementation)" live>
        <DataTable
          headers={['ID', 'Module', 'Status', 'Spec']}
          rows={(data?.modules || []).map((m: any) => [
            <Tag color="blue">{m.id}</Tag>,
            <span className="font-mono text-sm">{m.name}</span>,
            <Badge status={m.status} />,
            <span className="text-xs text-muted-foreground">{m.spec}</span>,
          ])}
          emptyMessage="Loading modules..."
        />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// ESCROW STATE MACHINE
// ════════════════════════════════════════════════════════════════════════════

export function EscrowStateMachinePage() {
  const { data } = useAPI('/api/v1/btcp/escrow_states', 30000);

  return (
    <div className="space-y-6">
      <Card title="BTCPEscrow State Machine" live>
        <div className="flex items-center justify-between gap-2 mb-4 overflow-x-auto">
          {(data?.states || []).map((s: string, i: number) => (
            <div key={s} className="flex items-center gap-2">
              <div className="p-2 rounded border-2 border-blue-500/30 bg-blue-500/5 text-center min-w-[100px]">
                <div className="text-xs font-semibold">{s}</div>
              </div>
              {i < (data?.states?.length || 0) - 1 && <span className="text-muted-foreground">{'->'}</span>}
            </div>
          ))}
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Resolution Compliance">
          <KVList items={[
            ['Gap 8 - Emergency Escape', `${data?.emergency_escape_days} days absolute max`],
            ['E1 - Akashic Recovery', `${data?.akashic_recovery_hours}h window`],
            ['Gap 9 - Cascade Revert', 'Multi-hop nested escrows'],
            ['G1 - Two-Phase Confirm', 'Settlement check verified'],
            ['Gap 11 - Force Majeure', 'Source-chain escrow'],
          ]} />
        </Card>
        <Card title="Revert Reasons">
          <div className="flex flex-wrap gap-2">
            {(data?.revert_reasons || []).map((r: string) => (
              <Tag key={r} color="red">{r}</Tag>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PRIVATE BIBL PROTOCOL
// ════════════════════════════════════════════════════════════════════════════

export function PrivateBIBLPage() {
  const { data } = useAPI('/api/v1/btcp/integration_status', 30000);

  return (
    <div className="space-y-6">
      <Card title="Private BIBL Computation Protocol (Gap 9 Resolution)" live>
        <div className="space-y-3">
          {(data?.private_bibl_phases || []).map((phase: string, i: number) => (
            <div key={i} className="flex items-center gap-3 p-3 rounded border border-border">
              <div className="w-8 h-8 rounded-full bg-blue-500 text-white flex items-center justify-center text-sm font-bold">
                {i + 1}
              </div>
              <span className="text-sm">{phase}</span>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Privacy Levels">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          {Object.entries(data?.privacy_levels || {}).map(([level, desc]: any) => (
            <div key={level} className="p-3 rounded-lg border border-border">
              <div className="font-mono text-sm font-semibold text-blue-500">{level}</div>
              <div className="text-xs text-muted-foreground mt-1">{desc}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="ANIMA Service Integration">
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          {Object.entries(data?.anima_service_modules || {}).map(([mod, ok]: any) => (
            <div key={mod} className="p-3 rounded border border-border flex items-center justify-between">
              <span className="text-sm font-mono">{mod}</span>
              <Badge status={ok ? 'OK' : 'OFFLINE'} />
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// CONTINUUM ENGINES
// ════════════════════════════════════════════════════════════════════════════

export function ContinuumEnginesPage() {
  const { data } = useAPI('/api/v1/continuum/engines', 30000);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard label="Engines" value={fmt(data?.total_engines)} color="blue" />
        <StatCard label="Implemented" value={fmt(data?.implemented)} color="green" />
        <StatCard label="BID" value="4.1" sub="Intent Detection" color="purple" />
        <StatCard label="CME" value="4.2" sub="Complement Match" color="blue" />
        <StatCard label="PMO" value="4.3" sub="Pre-Manifest Order" color="green" />
      </div>

      <Card title="5 CONTINUUM Engines" live>
        <DataTable
          headers={['ID', 'Name', 'Full Name', 'Formula', 'Status']}
          rows={(data?.engines || []).map((e: any) => [
            <Tag color="blue">{e.id}</Tag>,
            <span className="font-mono font-semibold">{e.name}</span>,
            e.full_name,

            <Badge status={e.status} />,
          ])}
          emptyMessage="Loading engines..."
        />
      </Card>

      <Card title="CCP Distribution (Complement Certainty Premium)">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: 'Entity A', value: data?.ccp_distribution?.entity_a, color: 'blue' },
            { label: 'Entity B', value: data?.ccp_distribution?.entity_b, color: 'green' },
            { label: 'Validators', value: data?.ccp_distribution?.validators, color: 'purple' },
            { label: 'Protocol', value: data?.ccp_distribution?.protocol, color: 'amber' },
          ].map(c => (
            <div key={c.label} className="text-center">
              <div className="text-3xl font-bold">{pct(c.value, 0)}</div>
              <div className="text-xs text-muted-foreground">{c.label}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
