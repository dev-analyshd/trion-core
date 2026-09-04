/**
 * Validators, 0G Integration, Infrastructure, Agent, Protocol, CEX, Explorers Pages
 */
'use client';

import { useState } from 'react';
import { Card, StatCard, ProgressBar, Badge, DataTable, KVList, EmptyState, Tag } from '../components/ui';
import { useAPI, useStream } from '../lib/hooks';
import { fetchAPI, fmt, pct, tfmt, dtfmt, truncate, hex, compact, statusColor, ms, cleanText } from '../lib/api';
import { VM_FAMILY_COUNT } from '../lib/config';
import * as Icons from 'lucide-react';

const DEFAULT_ENTITY = '0x2e49c1ff182bea5e33246a5f88f78cab6108cdde7b14f73bf8f7a06d6940c6ec';

// ════════════════════════════════════════════════════════════════════════════
// VALIDATORS
// ════════════════════════════════════════════════════════════════════════════

export function ValidatorsPage() {
  const { data: hhi } = useAPI('/api/v1/validator/hhi', 15000);
  const { data: dwBft } = useAPI('/api/v1/dw_bft', 30000);
  const { data: sigma } = useAPI(`/api/v1/sigma/${DEFAULT_ENTITY}`, 10000);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Validators" value={fmt(sigma?.validator_count || 0)} sub="registered" color="blue" />
        <StatCard label="Sigma(t)" value={(sigma?.sigma || 0.25).toFixed(4)} color={sigma?.bootstrap ? 'amber' : 'green'} />
        <StatCard label="HHI" value={fmt(hhi?.hhi || 0, 0)} sub={hhi?.hhi_status || '-'} color={hhi?.hhi < 2500 ? 'green' : 'red'} />
        <StatCard label="Continents" value={`${hhi?.continent_count || 0}/4`} color={hhi?.continents_ok ? 'green' : 'amber'} />
      </div>

      <Card title="Validator Registry - Launch Threshold" live>
        <div className="text-center py-4">
          <div className="text-3xl font-bold">{fmt(sigma?.validator_count || 0)} / 100</div>
          <div className="text-sm text-muted-foreground mt-2">validators registered (whitepaper section4 launch threshold)</div>
        </div>
        <ProgressBar value={sigma?.validator_count || 0} max={100} color="blue" label="Launch readiness" showValue />
        <div className="mt-3 text-center">
          <Badge status={sigma?.bootstrap ? 'BOOTSTRAP' : 'LAUNCH_READY'} />
        </div>
      </Card>

      <Card title="HHI Distribution" live>
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-7 gap-2 mb-4">
          {['AF', 'AN', 'AS', 'EU', 'NA', 'OC', 'SA'].map(c => {
            const count = hhi?.continent_breakdown?.[c] || 0;
            return (
              <div key={c} className={`p-3 rounded text-center border ${count > 0 ? 'bg-green-500/10 border-green-500/30' : 'bg-muted/30 border-border'}`}>
                <div className="text-sm font-semibold">{c}</div>
                <div className="text-lg font-mono">{count}</div>
              </div>
            );
          })}
        </div>
        <KVList items={[
          ['F8 violation', hhi?.f8_violation ? 'YES' : 'NO'],
          ['Consensus paused', hhi?.consensus_paused ? 'YES' : 'NO'],
          ['Auto response', hhi?.auto_response || '-'],
        ]} />
      </Card>

      <Card title="DW-BFT Consensus" live>
        <KVList items={[
          ['Consensus value', (dwBft?.consensus_value || 0).toFixed(4)],
          ['Byzantine effective weight', (dwBft?.byzantine_effective_weight || 0).toFixed(4)],
          ['Consensus window delta(t)', (dwBft?.consensus_window_delta || 0).toFixed(4)],
          ['Safety proof', dwBft?.bft_safety_proof || '-'],
        ]} />
      </Card>
    </div>
  );
}

export function ValidatorHHIPage() { return <ValidatorsPage />; }

// ════════════════════════════════════════════════════════════════════════════
// ANNOTATORS
// ════════════════════════════════════════════════════════════════════════════

export function AnnotatorsPage() {
  return (
    <div className="space-y-6">
      <Card title="K-Plane Annotation Network" live>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Bootstrap K" value="0.10" sub="baseline" color="amber" />
          <StatCard label="Quorum" value="3-of-5" sub="majority" color="blue" />
          <StatCard label="ACP Protections" value="6" sub="active" color="green" />
          <StatCard label="Terms" value="12 months" sub="rotating" color="purple" />
        </div>
      </Card>

      <Card title="Annotation Lifecycle">
        <div className="flex items-center justify-between gap-2 mb-4">
          {['COMMIT', 'REVEAL', 'VOTE', 'TALLY'].map((s, i) => (
            <div key={s} className="flex-1 p-3 rounded border-2 border-blue-500/30 bg-blue-500/5 text-center">
              <div className="text-xs font-semibold">{i + 1}. {s}</div>
            </div>
          ))}
        </div>
        <div className="text-sm text-muted-foreground">
          Commit-reveal voting prevents herding - annotators submit hash commitments before the reveal window opens.
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// BOOTSTRAP STATUS
// ════════════════════════════════════════════════════════════════════════════

export function BootstrapPage() {
  const { data: bs } = useAPI('/api/v1/bootstrap/status', 15000);

  return (
    <div className="space-y-6">
      <Card title="Bootstrap Protocol - e^(-lambda * D)" live>
        <div className="text-center py-4">
          <div className="text-5xl font-bold text-blue-500">{pct(bs?.bootstrap_weight, 3)}</div>
          <div className="text-sm text-muted-foreground mt-2">bootstrap weight (lower = more mature)</div>
        </div>
        <ProgressBar value={1 - (bs?.bootstrap_weight || 1)} color="green" label="Protocol maturity" showValue />
        <div className="mt-4">
          <KVList items={[
            ['Akashic depth Behavioral Depth', fmt(bs?.akashic_depth)],
            ['Depth for full transition', fmt(bs?.depth_for_full_transition)],
            ['Decay rate lambda', '0.0001'],
            ['Formula', 'bootstrap_weight(t) = e^(-0.0001 * Behavioral Depth)'],
            ['Disclosure', cleanText(bs?.disclosure) || '-'],
          ]} />
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// REPUTATION
// ════════════════════════════════════════════════════════════════════════════

export function ReputationPage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: rep } = useAPI(`/api/v1/reputation/${entityId}`, 15000);
  const { data: lb } = useAPI('/api/v1/reputation/leaderboard', 30000);

  return (
    <div className="space-y-6">
      <Card title="Entity Selector">
        <input
          type="text"
          value={entityId}
          onChange={e => setEntityId(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-border bg-input text-sm font-mono"
        />
      </Card>

      {rep && (
        <Card title={`Reputation - ${truncate(entityId, 16)}`} live>
          <KVList items={[
            ['Credit score', (rep.credit_score || 0).toFixed(4)],
            ['Avg coherence', pct(rep.avg_coherence, 2)],
            ['Active days', fmt(rep.active_days)],
            ['Dispute count', fmt(rep.dispute_count)],
            ['Cross-chain consistency', pct(rep.cross_chain_consistency, 2)],
          ]} />
        </Card>
      )}

      <Card title="Reputation Leaderboard" live>
        <DataTable
          headers={['#', 'Entity', 'Credit Score', 'Active Days']}
          rows={(lb?.leaderboard || []).slice(0, 15).map((e: any, i: number) => [
            i + 1,
            truncate(e.entity_id, 16),
            (e.credit_score || 0).toFixed(4),
            fmt(e.active_days),
          ])}
          emptyMessage="Loading leaderboard..."
        />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 0G INTEGRATION
// ════════════════════════════════════════════════════════════════════════════

export function ZeroGFullStackPage() {
  const { data: fs } = useAPI('/api/v1/zg/full_stack', 15000);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="BH Records" value={fmt(fs?.bh_records)} color="blue" />
        <StatCard label="Chains Indexed" value={fmt(fs?.chains_indexed)} color="green" />
        <StatCard label="API Routes" value={fmt(fs?.api_routes)} color="purple" />
        <StatCard label="Components" value={fmt(Object.keys(fs?.components || {}).length)} color="amber" />
      </div>

      <Card title="0G Full Stack Integration" live>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <div className="text-xs text-muted-foreground mb-2">Architecture</div>
            <pre className="bg-muted/50 rounded p-3 text-xs font-mono overflow-auto max-h-60">
              {JSON.stringify(fs?.architecture || {}, null, 2)}
            </pre>
          </div>
          <div>
            <div className="text-xs text-muted-foreground mb-2">Components</div>
            <pre className="bg-muted/50 rounded p-3 text-xs font-mono overflow-auto max-h-60">
              {JSON.stringify(fs?.components || {}, null, 2)}
            </pre>
          </div>
        </div>
      </Card>
    </div>
  );
}

export function ZeroGStoragePage() {
  const { data: storage } = useAPI('/api/v1/zg/storage/root', 15000);
  return (
    <Card title="0G Storage Root" live>
      <KVList items={[
        ['Root hash', hex(storage?.root, 16)],
        ['OK', storage?.ok ? 'YES' : 'NO'],
        ['Error', storage?.error || '-'],
      ]} />
    </Card>
  );
}

export function ZeroGDAPage() {
  const { data: da } = useAPI('/api/v1/zg/da/status', 15000);
  return (
    <Card title="0G Data Availability Layer" live>
      <KVList items={[
        ['Status', da?.ok ? 'OK' : 'ERROR'],
        ['Error', da?.error || '-'],
      ]} />
    </Card>
  );
}

export function ZeroGComputePage() {
  const { data: comp } = useAPI('/api/v1/zg/compute/status', 15000);
  return (
    <Card title="0G Compute (TEE-verified inference)" live>
      <KVList items={[
        ['Status', comp?.ok ? 'OK' : 'ERROR'],
        ['Error', comp?.error || '-'],
      ]} />
    </Card>
  );
}

export function ZeroGChainPage() {
  const { data: chain } = useAPI('/api/v1/zg/chain/status', 15000);
  return (
    <Card title="0G Chain Status" live>
      <KVList items={[
        ['Status', chain?.ok ? 'OK' : 'ERROR'],
        ['Error', chain?.error || '-'],
      ]} />
    </Card>
  );
}

export function ZeroGProofPage() {
  const { data: proof } = useAPI('/api/v1/zg/proof', 15000);
  return (
    <Card title="0G Proof - Behavioral Coverage" live>
      <KVList items={[
        ['Chain', proof?.chain || '-'],
        ['Chain ID', fmt(proof?.chain_id)],
        ['Deploy block', fmt(proof?.deploy_block)],
        ['DA proof', hex(proof?.da_proof, 16)],
        ['Behavioral coverage', pct(proof?.behavioral_coverage, 2)],
      ]} />
    </Card>
  );
}

export function ZeroGVMFamiliesPage() {
  const { data: vm } = useAPI('/api/v1/zg/vm-families', 30000);
  return (
    <Card title={`VM Families - ${VM_FAMILY_COUNT} Total`} live>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Chains" value={fmt(vm?.total_chains)} color="blue" />
        <StatCard label="VM Families" value={fmt(vm?.total_vm_families)} color="purple" />
        <StatCard label="FAISS Dimensions" value={fmt(vm?.faiss_dimensions)} />
        <StatCard label="Behavioral Planes/VM" value={fmt(vm?.behavioral_planes_per_vm)} color="green" />
      </div>
    </Card>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// INFRASTRUCTURE
// ════════════════════════════════════════════════════════════════════════════

export function ChainsPage() {
  const { data: chains } = useAPI('/api/v1/chains', 15000);
  const [search, setSearch] = useState('');

  const filtered = (chains?.chains || []).filter((c: any) =>
    c.name?.toLowerCase().includes(search.toLowerCase()) ||
    c.vm?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Chains" value={fmt(chains?.total)} color="blue" />
        <StatCard label="Indexed" value={fmt(chains?.indexed)} color="green" />
        <StatCard label="Live" value={fmt(chains?.live)} color="green" />
        <StatCard label="VM Families" value={fmt(chains?.vm_families ?? VM_FAMILY_COUNT)} color="purple" />
      </div>

      <Card title="Chain Coverage" live>
        <input
          className="w-full max-w-sm mb-4 px-3 py-2 rounded-lg border border-border bg-input text-sm"
          placeholder="Search chains..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <DataTable
          headers={['Chain', 'VM', 'Chain ID', 'Status']}
          rows={filtered.map((c: any) => [
            c.name, c.vm, c.chain_id || '-', <Badge status={c.status || 'LIVE'} />,
          ])}
          emptyMessage="Loading chains..."
        />
      </Card>
    </div>
  );
}

export function TimescalePage() {
  const { data: tsdb } = useAPI('/api/v1/tsdb/stats', 15000);
  const { data: info } = useAPI('/api/v1/information/conservation', 15000);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Backend" value={tsdb?.backend || 'sqlite'} color="blue" />
        <StatCard label="Connected" value={tsdb?.connected ? 'YES' : 'NO'} color={tsdb?.connected ? 'green' : 'red'} />
        <StatCard label="Total Records" value={fmt(tsdb?.total_records)} color="green" />
        <StatCard label="Conservation" value={info?.has_violations === false ? 'OK' : 'CHECK'} color={info?.has_violations === false ? 'green' : 'amber'} />
      </div>

      <Card title="TimescaleDB / SQLite Backend" live>
        <KVList items={[
          ['Backend', tsdb?.backend || '-'],
          ['Connected', tsdb?.connected ? 'YES' : 'NO'],
          ['Total records', fmt(tsdb?.total_records)],
          ['Message', tsdb?.message || '-'],
        ]} />
      </Card>

      <Card title="Information Conservation (L9.2)" live>
        <KVList items={[
          ['I_TRION', fmt(info?.I_total || info?.I_current)],
          ['BH Generated', fmt(info?.bh_generated)],
          ['Signals Emitted', fmt(info?.s_emitted || info?.I_out)],
          ['Violations', info?.has_violations ? 'YES' : '0'],
        ]} />
      </Card>
    </div>
  );
}

export function KVStorePage() {
  const { data: kv } = useAPI('/api/v1/kv/status', 15000);
  return (
    <Card title="0G KV Store Status" live>
      <KVList items={[
        ['Component', kv?.component || '-'],
        ['Gate Chain', kv?.gate_chain || '-'],
        ['Gate Contract', hex(kv?.gate_contract, 16)],
        ['Latency Target', `${kv?.latency_target_ms || 0}ms`],
        ['Integration Note', kv?.integration_note || '-'],
      ]} />
    </Card>
  );
}

export function BackfillPage() {
  const { data: bf } = useAPI('/api/v1/backfill/status', 30000);
  return (
    <Card title="Backfill Status" live>
      <KVList items={[
        ['Total chains', fmt(bf?.total_chains)],
        ['Total indexed', fmt(bf?.total_indexed)],
        ['Timestamp', dtfmt(bf?.timestamp)],
      ]} />
    </Card>
  );
}

export function RelayersPage() {
  const { data: rel } = useAPI('/api/v1/relayers/status', 15000);
  return (
    <Card title="Relayer Status" live>
      <DataTable
        headers={['Relayer', 'Status']}
        rows={Object.entries(rel || {}).filter(([k]) => k !== 'timestamp').map(([k, v]: any) => [
          k.replace(/_/g, ' '),
          <Badge status={v?.ok || v?.status || 'OPERATIONAL'} />,
        ])}
      />
    </Card>
  );
}

export function DependencyGraphPage() {
  const { data: dg } = useAPI('/api/v1/dependency_graph', 30000);
  return (
    <Card title="Dependency Graph" live>
      <div className="space-y-3">
        <div>
          <div className="text-xs text-muted-foreground mb-2">Tier-1 Protocols</div>
          <div className="flex flex-wrap gap-2">
            {(dg?.tier_1_protocols || []).map((p: any) => <Tag key={p} color="blue">{p}</Tag>)}
          </div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground mb-2">Cascade Paths</div>
          <div className="max-h-40 overflow-auto">
            {(dg?.cascade_paths || []).slice(0, 10).map((p: any, i: number) => (
              <div key={i} className="text-xs font-mono py-1 border-b border-border/30">
                {Array.isArray(p) ? p.join(' -> ') : JSON.stringify(p)}
              </div>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}

export function SDKSpecPage() {
  const { data: sdk } = useAPI('/api/v1/sdk/spec', 60000);
  return (
    <Card title="SDK Specification" live>
      <KVList items={[
        ['Base URL', sdk?.base_url || '-'],
        ['Chains indexed', fmt(sdk?.chains_indexed)],
        ['Falsifiability conditions', fmt(sdk?.falsifiability_conditions)],
        ['Auth', sdk?.auth || '-'],
      ]} />
      <div className="mt-4">
        <div className="text-xs text-muted-foreground mb-2">Core Endpoints</div>
        <div className="max-h-60 overflow-auto">
          {(sdk?.core_endpoints || []).map((e: any, i: number) => (
            <div key={i} className="text-xs font-mono py-1 border-b border-border/30">
              {typeof e === 'string' ? e : JSON.stringify(e)}
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

export function TokenPage() {
  const { data: util } = useAPI('/api/v1/token/utility', 30000);
  return (
    <Card title="Token Utility" live>
      <KVList items={[
        ['Token', util?.token || 'TRION'],
        ['Chain', util?.chain || '-'],
        ['Total supply', fmt(util?.total_supply)],
        ['Initial distribution', fmt(util?.initial_dist)],
      ]} />
    </Card>
  );
}

export function TokenDistributionPage() {
  const { data: dist } = useAPI('/api/v1/token/distribution', 30000);
  return (
    <Card title="Token Distribution & Public Good Charter" live>
      <KVList items={[
        ['Public good enforcement', dist?.public_good_enforcement ? 'YES' : 'NO'],
        ['Inflation cap', `${dist?.inflation?.cap_pct || 2}%/yr`],
        ['Launch conditions', dist?.launch_conditions || '-'],
      ]} />
      <div className="mt-4">
        <div className="text-xs text-muted-foreground mb-2">Allocation</div>
        <pre className="bg-muted/50 rounded p-3 text-xs font-mono">
          {JSON.stringify(dist?.allocation || {}, null, 2)}
        </pre>
      </div>
    </Card>
  );
}

export function RevenuePage() {
  const { data: rev } = useAPI('/api/v1/trion/revenue', 30000);
  return (
    <Card title="Revenue Model" live>
      <KVList items={[
        ['TAM estimate', rev?.tam_estimate || '-'],
        ['Thesis', rev?.thesis || '-'],
      ]} />
      <div className="mt-4">
        <div className="text-xs text-muted-foreground mb-2">Revenue Streams</div>
        <DataTable
          headers={['Stream', 'Description']}
          rows={(rev?.revenue_streams || []).map((s: any) => [s.name || s, s.description || '-'])}
          emptyMessage="Loading streams..."
        />
      </div>
    </Card>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// AI AGENT
// ════════════════════════════════════════════════════════════════════════════

export function AgentPage() {
  const { data: agents } = useAPI('/api/v1/agents', 15000);
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: agentId } = useAPI(`/api/v1/agent_id/${entityId}`, 15000);

  return (
    <div className="space-y-6">
      <Card title="Entity -> Agent ID Resolver">
        <input
          type="text"
          value={entityId}
          onChange={e => setEntityId(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-border bg-input text-sm font-mono"
        />
      </Card>
      {agentId && (
        <Card title="Agent ID" live>
          <KVList items={[
            ['Agent ID', hex(agentId.agent_id, 16)],
            ['Entity ID', hex(agentId.entity_id, 16)],
            ['Generation', fmt(agentId.generation)],
          ]} />
        </Card>
      )}
      <Card title="All Agents" live>
        <DataTable
          headers={['Agent ID', 'Status']}
          rows={(agents?.agents || []).slice(0, 15).map((a: any) => [
            hex(a.agent_id || a.id, 14),
            <Badge status={a.status || 'ACTIVE'} />,
          ])}
          emptyMessage="Loading agents..."
        />
      </Card>
    </div>
  );
}

export function AgentsPage() { return <AgentPage />; }
export function AgentValidatePage() { return <AgentPage />; }

export function InvestPage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: invest } = useAPI(`/api/v1/invest/${entityId}`, 15000);
  return (
    <div className="space-y-6">
      <Card title="Investment Scanner">
        <input
          type="text"
          value={entityId}
          onChange={e => setEntityId(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-border bg-input text-sm font-mono"
        />
      </Card>
      {invest && (
        <Card title="Investment Analysis" live>
          <KVList items={[
            ['Recommendation', invest.recommendation || '-'],
            ['Risk score', (invest.risk_score || 0).toFixed(4)],
            ['Expected return', pct(invest.expected_return, 2)],
            ['Coherence', (invest.coherence || 0).toFixed(4)],
          ]} />
        </Card>
      )}
    </div>
  );
}

export function IntelligenceMaintenancePage() {
  const { data: im } = useAPI('/api/v1/intelligence_maintenance', 15000);
  return (
    <Card title="Intelligence Maintenance - IM Score" live>
      <KVList items={[
        ['IM score', (im?.im_score || 0).toFixed(4)],
        ['Threshold', (im?.IM_threshold || 0).toFixed(4)],
        ['Detection window (h)', fmt(im?.detection_window_h)],
        ['Last full audit', im?.last_full_audit || '-'],
      ]} />
    </Card>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PROTOCOL HEALTH
// ════════════════════════════════════════════════════════════════════════════

export function ProtocolPage() {
  const { data: monitor } = useAPI('/api/v1/protocol/monitor/status', 15000);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Watched Protocols" value={fmt(monitor?.watched_protocols?.length || 0)} color="blue" />
        <StatCard label="Monitor Active" value={monitor?.monitor_active ? 'YES' : 'NO'} color={monitor?.monitor_active ? 'green' : 'red'} />
        <StatCard label="Poll Interval" value={`${monitor?.poll_interval_seconds || 60}s`} />
        <StatCard label="Status" value={monitor?.status || '-'} color="green" />
      </div>
      <Card title="Protocol Monitor States" live>
        <DataTable
          headers={['Protocol', 'Protocol Health', 'Grade', 'Reason']}
          rows={(monitor?.states || []).map((s: any) => [
            s.protocol_name || s.name,
            (s.h_score || 0).toFixed(4),
            <Badge status={s.grade} />,
            s.reason || '-',
          ])}
          emptyMessage="Loading states..."
        />
      </Card>
    </div>
  );
}

export function ProtocolRolesPage() {
  const { data: roles } = useAPI('/api/v1/protocol/supported-roles', 30000);
  return (
    <Card title="Supported Protocol Roles" live>
      <div className="flex flex-wrap gap-2">
        {(roles?.roles || []).map((r: any) => (
          <Tag key={r} color="blue">{r}</Tag>
        ))}
      </div>
    </Card>
  );
}

export function SelfVerificationPage() {
  const { data: self } = useAPI('/api/v1/self', 15000);
  return (
    <Card title="TRION Self-Verification" live>
      <KVList items={[
        ['Entity ID', hex(self?.entity_id, 16)],
        ['Coherence', (self?.coherence || 0).toFixed(4)],
        ['Genomic generation', fmt(self?.genomic_generation)],
        ['Created at', dtfmt(self?.created_at)],
      ]} />
    </Card>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// CEX
// ════════════════════════════════════════════════════════════════════════════

export function CEXPage() {
  const { data: status } = useAPI('/api/v1/cex/status', 15000);
  return (
    <Card title="CEX Integration Status" live>
      <KVList items={[
        ['Coverage', status?.coverage || '-'],
        ['CEX registry count', fmt(status?.cex_registry?.length)],
        ['Feed endpoint', status?.feed_endpoint || '-'],
        ['Hostile endpoint', status?.hostile_endpoint || '-'],
        ['Inbound from CEX', status?.inbound_from_cex ? 'YES' : 'NO'],
      ]} />
    </Card>
  );
}

export function CEXFeedPage() {
  const { data: feed } = useAPI('/api/v1/cex/feed', 10000);
  return (
    <Card title="CEX Feed" live>
      <KVList items={[
        ['Feed type', feed?.feed_type || '-'],
        ['Feed version', feed?.feed_version || '-'],
        ['Refresh interval (s)', fmt(feed?.refresh_interval_seconds)],
        ['Signals count', fmt(feed?.signals?.length)],
      ]} />
    </Card>
  );
}

export function CEXAlertsPage() {
  const { data: alerts } = useAPI('/api/v1/cex/alerts', 10000);
  return (
    <Card title="CEX Alerts" live>
      <KVList items={[
        ['Total in window', fmt(alerts?.total_in_window)],
        ['Returned', fmt(alerts?.returned)],
        ['Query', alerts?.query || '-'],
      ]} />
    </Card>
  );
}

export function CEXStatsPage() {
  const { data: stats } = useAPI('/api/v1/cex/stats', 15000);
  return (
    <Card title="CEX Statistics" live>
      <KVList items={[
        ['Active webhooks', fmt(stats?.active_webhooks)],
        ['By CEX count', fmt(Object.keys(stats?.by_cex || {}).length)],
        ['By asset (top 20)', fmt(Object.keys(stats?.by_asset_top20 || {}).length)],
        ['By event type', fmt(Object.keys(stats?.by_event_type || {}).length)],
      ]} />
    </Card>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// EXPLORERS
// ════════════════════════════════════════════════════════════════════════════

export function LeaderboardPage() {
  const { data: lb } = useAPI('/api/v1/leaderboard', 10000);
  return (
    <Card title="Coherence Leaderboard" live>
      <DataTable
        headers={['#', 'Entity', 'Coherence', 'Archetype', 'Coherent']}
        rows={(lb?.leaderboard || []).map((e: any, i: number) => [
          e.rank || i + 1,
          truncate(e.label || e.entity_id, 24),
          <span className={e.coherent ? 'text-green-500 font-mono' : 'text-red-500 font-mono'}>{pct(e.coherence_score, 2)}</span>,
          <Badge status={e.archetype} />,
          e.coherent ? '✓' : '✗',
        ])}
        emptyMessage="Loading leaderboard..."
      />
    </Card>
  );
}

export function FeedPage() {
  const { items, speedMs } = useStream('/api/v1/feed', 3000);
  return (
    <Card title="Live Signal Feed" subtitle={`Streaming at ~${ms(speedMs)}`} live>
      <DataTable
        headers={['Time', 'Entity', 'Type', 'Score', 'Grade']}
        rows={items.slice(0, 50).map((s: any) => [
          tfmt(s.timestamp),
          truncate(s.protocol_name || s.entity_id, 16),
          s.signal_type || '-',
          <span className="font-mono">{pct(s.coherence_score, 2)}</span>,
          <Badge status={s.grade} />,
        ])}
        emptyMessage="Awaiting feed..."
      />
    </Card>
  );
}

export function AuditPatternsPage() {
  const { data: patterns } = useAPI('/api/v1/audit/patterns', 30000);
  return (
    <Card title="Audit Patterns" live>
      <DataTable
        headers={['Pattern', 'Category', 'Severity']}
        rows={(patterns?.patterns || []).map((p: any) => [
          p.name || p.id,
          p.category || '-',
          <Badge status={p.severity || 'WARNING'} />,
        ])}
        emptyMessage="Loading patterns..."
      />
    </Card>
  );
}

export function DemoPage() {
  const { data: demo } = useAPI('/api/v1/demo/simulate_attack', 30000);
  return (
    <Card title="Demo Attack Simulator" live>
      <KVList items={[
        ['Attack', demo?.attack || '-'],
        ['Attacker', hex(demo?.attacker_address, 14)],
        ['Date', demo?.date || '-'],
        ['Detection lead time', `${fmt(demo?.detection_lead_time_hours)}h`],
        ['Description', truncate(demo?.description, 60)],
      ]} />
    </Card>
  );
}
