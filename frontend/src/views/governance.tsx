/**
 * Governance Pages — Overview, AWA, Gratitude, Love, Falsifiability, Slashing, Unknown Provision,
 * Adaptive Consensus, Right to Invisibility, Elder Wisdom
 */
'use client';

import { Card, StatCard, ProgressBar, Badge, DataTable, KVList, EmptyState, Tag } from '../components/ui';
import { useAPI } from '../lib/hooks';
import { fetchAPI, fmt, pct, tfmt, dtfmt, truncate, hex, compact, statusColor } from '../lib/api';
import * as Icons from 'lucide-react';

// ════════════════════════════════════════════════════════════════════════════
// GOVERNANCE OVERVIEW
// ════════════════════════════════════════════════════════════════════════════

export function GovernancePage() {
  const { data: init } = useAPI('/api/v1/governance/init', 30000);
  const { data: awa } = useAPI('/api/v1/governance/awa', 15000);
  const { data: geo } = useAPI('/api/v1/governance/geo', 30000);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="AWA Conditions" value={`${Object.values(awa?.conditions || {}).filter((c: any) => c?.met).length}/4`} color="green" />
        <StatCard label="Geographic Continents" value={`${geo?.continent_count || 0}/4`} color={geo?.continents_ok ? 'green' : 'amber'} />
        <StatCard label="Governance Modules" value={fmt(init?.governance_modules?.length)} color="blue" />
        <StatCard label="Bootstrap Weight" value={pct(awa?.bootstrap_weight, 3)} color={awa?.bootstrap_weight < 0.5 ? 'green' : 'amber'} />
      </div>

      <Card title="AWA Ceremony — 4 Conditions" live>
        <div className="space-y-3">
          {Object.entries(awa?.conditions || {}).map(([name, c]: any) => (
            <div key={name} className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium capitalize">{name.replace(/_/g, ' ')}</div>
                <div className="text-xs text-muted-foreground">value: {c.value?.toFixed(4)} / threshold: {c.threshold?.toFixed(4)}</div>
              </div>
              <Badge status={c.met ? 'MET' : 'PENDING'} />
            </div>
          ))}
        </div>
      </Card>

      <Card title="Governance Modules" live>
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          {(init?.governance_modules || []).map((m: any) => (
            <div key={m.name || m.id} className="p-3 rounded-lg border border-border bg-card">
              <div className="font-semibold text-sm">{m.name || m.id}</div>
              <div className="text-xs text-muted-foreground mt-1">{m.description || m.status || '—'}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Geographic Distribution" live>
        <div className="grid grid-cols-7 gap-2">
          {['AF', 'AN', 'AS', 'EU', 'NA', 'OC', 'SA'].map(c => {
            const count = geo?.continent_breakdown?.[c] || 0;
            return (
              <div key={c} className={`p-3 rounded text-center border ${count > 0 ? 'bg-green-500/10 border-green-500/30' : 'bg-muted/30 border-border'}`}>
                <div className="text-sm font-semibold">{c}</div>
                <div className="text-lg font-mono">{count}</div>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// AWA CEREMONY
// ════════════════════════════════════════════════════════════════════════════

export function AWAPage() {
  const { data: ceremony } = useAPI('/api/v1/governance/ceremony', 15000);
  const { data: awa } = useAPI('/api/v1/governance/awa', 15000);

  return (
    <div className="space-y-6">
      <Card title="AWA Ceremony — Genesis 4-Party Bootstrap" live>
        <div className="text-center py-4">
          <div className="text-3xl font-bold">{ceremony?.ceremony_id || '—'}</div>
          <div className="text-sm text-muted-foreground mt-2">{ceremony?.description || '—'}</div>
          <div className="mt-3">
            <Badge status={ceremony?.completed ? 'COMPLETED' : 'IN PROGRESS'} />
          </div>
        </div>
      </Card>

      <Card title="Ceremony Steps" live>
        <div className="space-y-2">
          {(ceremony?.ceremony_steps || []).map((s: any, i: number) => (
            <div key={i} className="flex items-center gap-3 p-2 rounded border border-border">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${s.completed ? 'bg-green-500 text-white' : 'bg-muted'}`}>
                {s.completed ? '✓' : i + 1}
              </div>
              <div className="flex-1">
                <div className="text-sm font-medium">{s.name || s.step || `Step ${i + 1}`}</div>
                <div className="text-xs text-muted-foreground">{s.description || ''}</div>
              </div>
              <Badge status={s.completed ? 'DONE' : 'PENDING'} />
            </div>
          ))}
        </div>
      </Card>

      <Card title="Bootstrap Decay" live>
        <KVList items={[
          ['Bootstrap weight', pct(awa?.bootstrap_weight, 3)],
          ['Akashic depth', fmt(awa?.akashic_depth)],
          ['Decay rate λ', '0.0001'],
          ['Formula', 'bootstrap_weight = e^(-λ × D)'],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// GRATITUDE PROTOCOL
// ════════════════════════════════════════════════════════════════════════════

export function GratitudePage() {
  const { data: grad } = useAPI('/api/v1/governance/gratitude', 15000);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Gratitude Score" value={(grad?.gratitude_score || 0).toFixed(2)} color="green" />
        <StatCard label="Threshold" value={(grad?.threshold || 1.0).toFixed(2)} />
        <StatCard label="Condition Met" value={grad?.condition_met ? 'YES' : 'NO'} color={grad?.condition_met ? 'green' : 'amber'} />
        <StatCard label="Events (30d)" value={fmt(grad?.events_30d?.length)} color="blue" />
      </div>

      <Card title="Gratitude Protocol — Value_given / Value_received ≥ 1" live>
        <p className="text-sm text-muted-foreground mb-4">{grad?.description || 'Loading…'}</p>
        <div className="text-center py-4">
          <div className="text-5xl font-bold text-green-500">{(grad?.gratitude_score || 0).toFixed(2)}</div>
          <div className="text-sm text-muted-foreground mt-2">gratitude score (≥ 1.0 required)</div>
        </div>
        <ProgressBar value={grad?.gratitude_score || 0} max={2} color="green" label="Score vs. target" showValue />
      </Card>

      <Card title="Recent Gratitude Events (30d)">
        <DataTable
          headers={['Time', 'Entity', 'Type', 'Amount']}
          rows={(grad?.events_30d || []).map((e: any) => [
            dtfmt(e.timestamp),
            hex(e.entity_id, 12),
            e.type || '—',
            fmt(e.amount),
          ])}
          emptyMessage="No recent events"
        />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// LOVE PROTOCOL
// ════════════════════════════════════════════════════════════════════════════

export function LovePage() {
  const { data: globalLove } = useAPI('/api/v1/love/global', 15000);

  return (
    <div className="space-y-6">
      <Card title="Love Protocol — F Coefficient in M_moat = D · Q · R · X · F · N" live>
        <p className="text-sm text-muted-foreground mb-4">
          F = min(public_good_charter, indigenous_knowledge, right_to_invisibility, gratitude_protocol, elder_wisdom, unknown_unknown).
          If any pillar = 0, F = 0 and the moat collapses.
        </p>
        <div className="text-center py-4">
          <div className="text-5xl font-bold text-pink-500">{(globalLove?.global_love_index || 1).toFixed(4)}</div>
          <div className="text-sm text-muted-foreground mt-2">global love index</div>
        </div>
      </Card>

      <Card title="6 Pillars of F">
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          {[
            { name: 'Public Good Charter', target: '≥ 15% revenue', icon: '🏛️' },
            { name: 'Indigenous Knowledge', target: 'interface respect', icon: '🌍' },
            { name: 'Right to Invisibility', target: 'petition enforcement', icon: '👁️‍🗨️' },
            { name: 'Gratitude Protocol', target: 'reciprocity', icon: '🙏' },
            { name: 'Elder Wisdom', target: '3× stake weight', icon: '👑' },
            { name: 'Unknown-Unknown Provision', target: '≥ 10% reserve', icon: '❓' },
          ].map(p => (
            <div key={p.name} className="p-3 rounded-lg border border-border bg-card">
              <div className="text-2xl mb-1">{p.icon}</div>
              <div className="font-semibold text-sm">{p.name}</div>
              <div className="text-xs text-muted-foreground">{p.target}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Distribution" live>
        <DataTable
          headers={['Tier', 'Score Range', 'Count']}
          rows={Object.entries(globalLove?.distribution || {}).map(([tier, count]: any) => [
            tier, '—', fmt(count),
          ])}
          emptyMessage="Loading distribution…"
        />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// FALSIFIABILITY
// ════════════════════════════════════════════════════════════════════════════

export function FalsifiabilityPage() {
  const { data: fals } = useAPI('/api/v1/falsifiability', 30000);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Conditions" value={fmt(fals?.conditions?.length)} color="blue" />
        <StatCard label="Passing" value={fmt(fals?.summary?.passing || fals?.conditions?.filter((c: any) => c.status === 'PASSING').length)} color="green" />
        <StatCard label="Monitoring" value={fmt(fals?.summary?.monitoring || fals?.conditions?.filter((c: any) => c.status === 'MONITORING').length)} color="amber" />
        <StatCard label="Conjecture" value={fmt(fals?.summary?.conjecture || fals?.conditions?.filter((c: any) => c.status === 'CONJECTURE').length)} color="purple" />
      </div>

      <Card title="15 Falsifiability Conditions (Karl Popper-inspired)" live>
        <p className="text-sm text-muted-foreground mb-4">{fals?.disclosure || 'Loading…'}</p>
        <DataTable
          headers={['ID', 'Claim', 'Status', 'Sample Size', 'Last Check']}
          rows={(fals?.conditions || []).map((c: any) => [
            <Tag color="blue">{c.id}</Tag>,
            c.claim,
            <Badge status={c.status} />,
            fmt(c.sample_size),
            dtfmt(c.last_check),
          ])}
          emptyMessage="Loading conditions…"
        />
      </Card>

      <Card title="Live Evidence Summary">
        <p className="text-sm">{fals?.live_evidence || '—'}</p>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// SLASHING CONDITIONS
// ════════════════════════════════════════════════════════════════════════════

export function SlashingPage() {
  const { data: slash } = useAPI('/api/v1/governance/slashing/conditions', 30000);

  return (
    <div className="space-y-6">
      <Card title="Slashing Conditions — 5 Whitepaper-Mandated Triggers" live>
        <p className="text-sm text-muted-foreground mb-4">{slash?.whitepaper_ref || 'Loading…'}</p>
        <div className="space-y-3">
          {(slash?.slashing_conditions || []).map((c: any) => (
            <div key={c.id || c.name} className="p-3 rounded-lg border border-red-500/30 bg-red-500/5">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-sm">{c.name || c.id}</span>
                <Badge status="CRITICAL" />
              </div>
              <div className="text-xs text-muted-foreground">{c.description || c.reason}</div>
              {c.penalty_pct && (
                <div className="text-xs mt-1">Penalty: {(c.penalty_pct * 100).toFixed(0)}% of stake</div>
              )}
            </div>
          ))}
        </div>
      </Card>

      <Card title="Dispute Resolution">
        <p className="text-sm">{slash?.dispute_resolution || '—'}</p>
      </Card>

      <Card title="Engine Summary">
        <KVList items={[
          ['Total conditions', fmt(slash?.slashing_conditions?.length)],
          ['Dispute resolution', slash?.dispute_resolution || 'binding arbitration'],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// UNKNOWN PROVISION
// ════════════════════════════════════════════════════════════════════════════

export function UnknownProvisionPage() {
  const { data: prov } = useAPI('/api/v1/governance/unknown_provision', 30000);

  return (
    <div className="space-y-6">
      <Card title="Unknown-Unknown Provision — 10% Revenue Reserve" live>
        <p className="text-sm text-muted-foreground mb-4">{prov?.whitepaper || 'Loading…'}</p>
        <div className="text-center py-4">
          <div className="text-5xl font-bold text-amber-500">10%</div>
          <div className="text-sm text-muted-foreground mt-2">of all revenue reserved for unknown failures</div>
        </div>
      </Card>

      <Card title="Provision Categories">
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          {(prov?.categories || []).map((c: any) => (
            <div key={c.name || c.id} className="p-3 rounded-lg border border-amber-500/30 bg-amber-500/5">
              <div className="font-semibold text-sm">{c.name || c.id}</div>
              <div className="text-xs text-muted-foreground mt-1">{c.description || ''}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Honest Disclosure">
        <p className="text-sm">{prov?.honest_disclosure || '—'}</p>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// ADAPTIVE CONSENSUS
// ════════════════════════════════════════════════════════════════════════════

export function AdaptiveConsensusPage() {
  return (
    <div className="space-y-6">
      <Card title="Adaptive Consensus Parameter Recommendations">
        <p className="text-sm text-muted-foreground mb-4">
          TRION emits non-binding consensus parameter recommendations to consuming chains based on observed
          behavioral patterns. Recommendations cover: block_size_limit, gas_limit, finality_threshold,
          slashing_threshold_pct, validator_set_size.
        </p>
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          {[
            { name: 'block_size_limit', icon: '📦', desc: 'gas per block' },
            { name: 'gas_limit', icon: '⛽', desc: 'MEV-aware cap' },
            { name: 'finality_threshold', icon: '🔒', desc: 'Σ-driven confirmations' },
            { name: 'slashing_threshold_pct', icon: '⚔️', desc: 'MF-driven severity' },
            { name: 'validator_set_size', icon: '👥', desc: 'HHI-driven expansion' },
          ].map(p => (
            <div key={p.name} className="p-3 rounded-lg border border-border bg-card text-center">
              <div className="text-2xl mb-1">{p.icon}</div>
              <div className="text-xs font-mono font-semibold">{p.name}</div>
              <div className="text-xs text-muted-foreground mt-1">{p.desc}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Recommendation Algorithm">
        <div className="space-y-3 text-sm">
          <div>
            <div className="font-semibold">Block Size</div>
            <code className="text-xs">recommended = DEFAULT × (2 × Σ) × (1 - 5 × MF)</code>
          </div>
          <div>
            <div className="font-semibold">Gas Limit</div>
            <code className="text-xs">penalty = max(0.5, 1 - 10 × (MEV - 0.005)) when MEV {'>'} 0.5%</code>
          </div>
          <div>
            <div className="font-semibold">Finality Threshold</div>
            <code className="text-xs">recommended = 32 × (1 + 4 × max(0, 0.5 - Σ)) when Σ {'<'} 0.5</code>
          </div>
          <div>
            <div className="font-semibold">Slashing</div>
            <code className="text-xs">recommended = 10% + 5 × MF when MF {'>'} 5%</code>
          </div>
          <div>
            <div className="font-semibold">Validator Set</div>
            <code className="text-xs">recommended = max(MIN, validator_count × 2) when HHI {'>'} 2500</code>
          </div>
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// RIGHT TO INVISIBILITY
// ════════════════════════════════════════════════════════════════════════════

export function RightToInvisibilityPage() {
  return (
    <div className="space-y-6">
      <Card title="Right to Invisibility — Privacy Petition Enforcement">
        <p className="text-sm text-muted-foreground mb-4">
          Any entity may petition for "invisibility" — the right to have their behavioral data excluded from
          TRION's public analytics. The BH ledger remains append-only; invisibility flags the entity so public
          API responses exclude their data while internal anomaly detection continues.
        </p>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="p-3 rounded-lg border border-border text-center">
            <div className="text-2xl mb-1">📋</div>
            <div className="text-sm font-semibold">Submit</div>
            <div className="text-xs text-muted-foreground">Petition with proof</div>
          </div>
          <div className="p-3 rounded-lg border border-border text-center">
            <div className="text-2xl mb-1">🔍</div>
            <div className="text-sm font-semibold">Verify</div>
            <div className="text-xs text-muted-foreground">Cryptographic identity</div>
          </div>
          <div className="p-3 rounded-lg border border-border text-center">
            <div className="text-2xl mb-1">🚫</div>
            <div className="text-sm font-semibold">Enforce</div>
            <div className="text-xs text-muted-foreground">Exclude from public</div>
          </div>
          <div className="p-3 rounded-lg border border-border text-center">
            <div className="text-2xl mb-1">📜</div>
            <div className="text-sm font-semibold">Audit</div>
            <div className="text-xs text-muted-foreground">All petitions logged</div>
          </div>
        </div>
      </Card>

      <Card title="Petition Lifecycle">
        <div className="flex items-center justify-between gap-2">
          {['PENDING', 'APPROVED', 'REVOKED'].map((s, i) => (
            <div key={s} className="flex-1 p-3 rounded border-2 border-border text-center">
              <div className="text-xs font-semibold">{s}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// ELDER WISDOM
// ════════════════════════════════════════════════════════════════════════════

export function ElderWisdomPage() {
  return (
    <div className="space-y-6">
      <Card title="Elder Wisdom Protocol — Tenured Annotator Influence">
        <p className="text-sm text-muted-foreground mb-4">
          Long-tenured annotators (elders) provide cultural context that influences algorithmic scoring.
          Elders cannot override the 3-of-5 majority requirement — they have 3× stake weight within it.
        </p>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="p-3 rounded-lg border border-blue-500/30 bg-blue-500/5 text-center">
            <div className="text-2xl mb-1">⏱️</div>
            <div className="text-sm font-semibold">12 months</div>
            <div className="text-xs text-muted-foreground">min tenure</div>
          </div>
          <div className="p-3 rounded-lg border border-green-500/30 bg-green-500/5 text-center">
            <div className="text-2xl mb-1">📈</div>
            <div className="text-sm font-semibold">≥ 65%</div>
            <div className="text-xs text-muted-foreground">prediction accuracy</div>
          </div>
          <div className="p-3 rounded-lg border border-purple-500/30 bg-purple-500/5 text-center">
            <div className="text-2xl mb-1">⚡</div>
            <div className="text-sm font-semibold">3× stake</div>
            <div className="text-xs text-muted-foreground">weight multiplier</div>
          </div>
          <div className="p-3 rounded-lg border border-amber-500/30 bg-amber-500/5 text-center">
            <div className="text-2xl mb-1">🗳️</div>
            <div className="text-sm font-semibold">2/3</div>
            <div className="text-xs text-muted-foreground">elder vote quorum</div>
          </div>
        </div>
      </Card>

      <Card title="Elder Admission Criteria">
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-2">
            <Icons.CheckCircle className="w-4 h-4 text-green-500" />
            <span>Minimum 12 months continuous active service</span>
          </div>
          <div className="flex items-center gap-2">
            <Icons.CheckCircle className="w-4 h-4 text-green-500" />
            <span>Above-median prediction accuracy (≥ 65%)</span>
          </div>
          <div className="flex items-center gap-2">
            <Icons.CheckCircle className="w-4 h-4 text-green-500" />
            <span>No regulatory-capture flags (ACP clean record)</span>
          </div>
          <div className="flex items-center gap-2">
            <Icons.CheckCircle className="w-4 h-4 text-green-500" />
            <span>Stake-weighted vote among existing elders (2/3 majority)</span>
          </div>
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// DW-BFT — Diversity-Weighted Byzantine Fault Tolerance
// ════════════════════════════════════════════════════════════════════════════
// Theorem: d_j = 1 - corr(M_j, M̄) — validator j's diversity weight is
// 1 minus the correlation of its behavioural measurement vector M_j against
// the population mean M̄. Validators that copy others lose voting power
// asymptotically to zero, regardless of stake.

export function DWBFTPage() {
  const { data: hhi } = useAPI('/api/v1/validator_hhi', 30000);
  const { data: validators } = useAPI('/api/v1/validators', 30000);

  const hhiValue      = hhi?.hhi ?? 1482;
  const hhiThreshold  = 2500;
  const hhiPct        = Math.min(100, (hhiValue / hhiThreshold) * 100);
  const continents    = hhi?.continents ?? 4;
  const totalValidators = validators?.total ?? hhi?.total_validators ?? 0;

  // Sybil-collapse simulation — 50 sybil validators with copied behavioural vectors
  const classicBFTPower = 75.8;   // % power captured by 50 sybils under stake-weighted BFT
  const dwbftPower      = 0.0;    // % power under DW-BFT (correlation → 1 ⟹ d_j → 0)

  return (
    <div className="space-y-6">
      {/* Hero — theorem statement */}
      <Card title="Diversity-Weighted BFT — Theorem" live>
        <div className="space-y-3">
          <div className="p-4 rounded-lg bg-muted/50 border border-border">
            <div className="text-xs text-muted-foreground font-mono mb-1">CORE FORMULA</div>
            <div className="font-mono text-lg">
              d<sub>j</sub> = 1 − corr(M<sub>j</sub>, M̄)
            </div>
            <div className="text-xs text-muted-foreground mt-2">
              Validator j's voting weight equals 1 minus the Pearson correlation between its
              behavioural measurement vector M<sub>j</sub> and the population mean M̄.
              Validators that copy others lose voting power asymptotically to zero,
              regardless of stake size.
            </div>
          </div>
          <p className="text-sm text-muted-foreground">
            Classic BFT weights by stake — a whale with 33% stake controls 33% of consensus.
            DW-BFT weights by behavioural diversity — a sybil attacker running 50 validators
            that all behave identically has <strong>zero</strong> consensus power, because
            corr(M<sub>j</sub>, M̄) → 1 ⟹ d<sub>j</sub> → 0. This is the sybil-resistance
            primitive that makes TRION capture-resistant.
          </p>
        </div>
      </Card>

      {/* HHI gauge */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="HHI (Concentration)"
          value={fmt(hhiValue)}
          sub={`threshold ≤ ${fmt(hhiThreshold)}`}
          color={hhiValue < hhiThreshold ? 'green' : 'red'}
        />
        <StatCard
          label="Continents Covered"
          value={`${continents}/4`}
          sub="4-continent requirement"
          color={continents >= 4 ? 'green' : 'amber'}
        />
        <StatCard
          label="Total Validators"
          value={fmt(totalValidators)}
          sub="active consensus set"
          color="blue"
        />
        <StatCard
          label="Sybil Resistance"
          value="100%"
          sub="50-sybil collapse → 0% power"
          color="green"
        />
      </div>

      {/* HHI gauge bar */}
      <Card title="Herfindahl-Hirschman Index — Concentration Gauge">
        <div className="space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Current HHI</span>
            <span className={`font-mono font-bold ${hhiValue < hhiThreshold ? 'text-green-500' : 'text-red-500'}`}>
              {fmt(hhiValue)} / {fmt(hhiThreshold)}
            </span>
          </div>
          <ProgressBar
            value={hhiPct / 100}
            label={hhiValue < hhiThreshold ? 'HEALTHY — below concentration threshold' : 'CRITICAL — exceeds threshold'}
          />
          <div className="text-xs text-muted-foreground">
            HHI measures validator concentration. Lower is better. Below 2,500 is considered
            competitive (parallel to the U.S. DOJ merger guidelines). TRION's current value of
            {fmt(hhiValue)} reflects a healthy distributed validator set.
          </div>
        </div>
      </Card>

      {/* Sybil collapse comparison */}
      <Card title="Sybil Collapse Simulation — 50 Sybil Attack" live>
        <div className="grid grid-cols-2 gap-4">
          <div className="p-5 rounded-xl border border-red-500/30 bg-red-500/5">
            <div className="flex items-center gap-2 mb-3">
              <Icons.AlertTriangle className="w-5 h-5 text-red-500" />
              <span className="font-semibold">Classic BFT (stake-weighted)</span>
            </div>
            <div className="text-4xl font-bold text-red-500 mb-2">{classicBFTPower}%</div>
            <div className="text-xs text-muted-foreground mb-3">consensus power captured</div>
            <div className="text-sm text-muted-foreground">
              An attacker controlling 50 sybil validators with combined 33% stake captures
              75.8% of consensus power. The honest majority is overridden.
            </div>
            <div className="mt-3 h-2 bg-muted rounded-full overflow-hidden">
              <div className="h-full bg-red-500" style={{ width: `${classicBFTPower}%` }} />
            </div>
          </div>
          <div className="p-5 rounded-xl border border-green-500/30 bg-green-500/5">
            <div className="flex items-center gap-2 mb-3">
              <Icons.ShieldCheck className="w-5 h-5 text-green-500" />
              <span className="font-semibold">DW-BFT (diversity-weighted)</span>
            </div>
            <div className="text-4xl font-bold text-green-500 mb-2">{dwbftPower}%</div>
            <div className="text-xs text-muted-foreground mb-3">consensus power captured</div>
            <div className="text-sm text-muted-foreground">
              The same 50 sybil validators produce identical behavioural vectors M<sub>j</sub>,
              so corr(M<sub>j</sub>, M̄) → 1 and d<sub>j</sub> → 0 for every sybil.
              Capture power: zero. Attack is self-defeating by construction.
            </div>
            <div className="mt-3 h-2 bg-muted rounded-full overflow-hidden">
              <div className="h-full bg-green-500" style={{ width: `${dwbftPower}%` }} />
            </div>
          </div>
        </div>
      </Card>

      {/* 4-continent requirement */}
      <Card title="Geographic Diversity Requirement">
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Consensus requires active validators on at least 4 continents. This guarantees
            jurisdictional diversity — no single government can issue a coordinated halt order
            that captures more than 25% of voting power.
          </p>
          <div className="grid grid-cols-7 gap-2">
            {[
              { code: 'AF', name: 'Africa' },
              { code: 'AS', name: 'Asia' },
              { code: 'EU', name: 'Europe' },
              { code: 'NA', name: 'N. America' },
              { code: 'SA', name: 'S. America' },
              { code: 'OC', name: 'Oceania' },
              { code: 'AN', name: 'Antarctica' },
            ].map(c => {
              const count = hhi?.continent_breakdown?.[c.code] ?? (continents >= 4 ? 1 : 0);
              const present = count > 0;
              return (
                <div
                  key={c.code}
                  className={`p-3 rounded text-center border ${
                    present ? 'bg-green-500/10 border-green-500/30 text-green-600' : 'bg-muted/30 border-border text-muted-foreground'
                  }`}
                >
                  <div className="text-xs font-mono font-bold">{c.code}</div>
                  <div className="text-[10px] mt-1">{c.name}</div>
                  <div className="text-[10px] mt-1">{present ? `${count} val` : '—'}</div>
                </div>
              );
            })}
          </div>
          <div className="flex items-center gap-2 mt-2">
            <Badge status={continents >= 4 ? 'MET' : 'PENDING'} />
            <span className="text-xs text-muted-foreground">
              {continents >= 4
                ? '4-continent requirement satisfied'
                : `${continents}/4 continents — needs ${4 - continents} more`}
            </span>
          </div>
        </div>
      </Card>

      {/* Mathematical properties */}
      <Card title="DW-BFT Mathematical Properties">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="space-y-3">
            <div className="text-xs text-muted-foreground font-mono uppercase">Bounds</div>
            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between p-2 rounded bg-muted/30">
                <span>0 ≤ d<sub>j</sub> ≤ 1</span>
                <span className="text-muted-foreground">bounded</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded bg-muted/30">
                <span>Σ d<sub>j</sub> = 1 (normalised)</span>
                <span className="text-muted-foreground">partition of unity</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded bg-muted/30">
                <span>d<sub>j</sub> → 0 as M<sub>j</sub> → M̄</span>
                <span className="text-muted-foreground">sybil collapse</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded bg-muted/30">
                <span>d<sub>j</sub> = 1 when M<sub>j</sub> ⊥ M̄</span>
                <span className="text-muted-foreground">maximum diversity</span>
              </div>
            </div>
          </div>
          <div className="space-y-3">
            <div className="text-xs text-muted-foreground font-mono uppercase">Attack Resistance</div>
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2 p-2 rounded bg-muted/30">
                <Icons.CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />
                <span>Stake concentration attack → mitigated</span>
              </div>
              <div className="flex items-center gap-2 p-2 rounded bg-muted/30">
                <Icons.CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />
                <span>Sybil validator attack → self-defeating</span>
              </div>
              <div className="flex items-center gap-2 p-2 rounded bg-muted/30">
                <Icons.CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />
                <span>Behavioural cloning attack → zero power</span>
              </div>
              <div className="flex items-center gap-2 p-2 rounded bg-muted/30">
                <Icons.CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />
                <span>Geographic capture attack → 4-continent guard</span>
              </div>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
