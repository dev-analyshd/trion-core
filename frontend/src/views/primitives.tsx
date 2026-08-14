/**
 * Novel Primitives Pages - BIRP, DNA_Code, UBL, BC, XSL, Transduction, Inversion, Predictive Limit,
 * Information Conservation, Phase Signal
 */
'use client';

import { useState } from 'react';
import { Card, StatCard, ProgressBar, Badge, DataTable, KVList, EmptyState, Tag, CodeBlock } from '../components/ui';
import { useAPI } from '../lib/hooks';
import { fetchAPI, fmt, pct, tfmt, dtfmt, truncate, hex, compact, statusColor } from '../lib/api';

const DEFAULT_ENTITY = '0x2e49c1ff182bea5e33246a5f88f78cab6108cdde7b14f73bf8f7a06d6940c6ec';

// ════════════════════════════════════════════════════════════════════════════
// BIRP RECOVERY
// ════════════════════════════════════════════════════════════════════════════

export function BIRPPage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: birp } = useAPI(`/api/v1/security/${entityId}/genomic`, 15000);

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

      <Card title="BIRP - Behavioral Identity Recovery Protocol (5 Phases)" live>
        <div className="flex items-center justify-between gap-2 mb-4">
          {[
            { name: 'PHASE 1', sub: 'DNA Verify', icon: '🧬' },
            { name: 'PHASE 2', sub: 'Behavioral Proof', icon: '📜' },
            { name: 'PHASE 3', sub: 'Temporal Cluster', icon: '⏱️' },
            { name: 'PHASE 4', sub: 'Conscious Layer', icon: '🧠' },
            { name: 'PHASE 5', sub: 'Quarantine 7d', icon: '🔒' },
          ].map((p, i) => (
            <div key={p.name} className="flex-1 p-3 rounded border-2 border-blue-500/30 bg-blue-500/5 text-center">
              <div className="text-2xl mb-1">{p.icon}</div>
              <div className="text-xs font-semibold">{p.name}</div>
              <div className="text-xs text-muted-foreground">{p.sub}</div>
            </div>
          ))}
        </div>
        <KVList items={[
          ['State machine', 'UNSTARTED -> PHASE_1 -> PHASE_2 -> PHASE_3 -> PHASE_4 -> PHASE_5 -> RESOLVED'],
          ['Quarantine period', '7 days (604,800 sec) - mandatory'],
          ['Rejection cooldown', '30 days before new request'],
          ['Conscious quorum', '2/3 majority (67%)'],
          ['Temporal cluster max distance', '0.30 cosine'],
          ['Behavioral proof min coverage', '70% Merkle leaves'],
        ]} />
      </Card>

      {birp && (
        <Card title="Genomic Key Status" live>
          <KVList items={[
            ['Generation', fmt(birp.generation)],
            ['Security generation', fmt(birp.security_generation)],
            ['Valid', birp.valid ? 'YES' : 'NO'],
            ['Immune clearance', birp.immune_clearance ? 'YES' : 'NO'],
          ]} />
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// DNA_CODE ROTATION
// ════════════════════════════════════════════════════════════════════════════

export function DNACodePage() {
  return (
    <div className="space-y-6">
      <Card title="DNA_Code - User-Defined Secret with Time-Based Rotation">
        <p className="text-sm text-muted-foreground mb-4">
          Each entity may register a personal DNA_Code - a byte sequence they alone know - that is
          mixed into the dual-strand hash during BIRP Phase 1 verification. The code rotates on a
          fixed 90-day schedule via hash-chaining.
        </p>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="p-3 rounded-lg border border-blue-500/30 bg-blue-500/5 text-center">
            <div className="text-2xl font-bold">90</div>
            <div className="text-xs text-muted-foreground">days per epoch</div>
          </div>
          <div className="p-3 rounded-lg border border-green-500/30 bg-green-500/5 text-center">
            <div className="text-2xl font-bold">128-2048</div>
            <div className="text-xs text-muted-foreground">bit secret</div>
          </div>
          <div className="p-3 rounded-lg border border-purple-500/30 bg-purple-500/5 text-center">
            <div className="text-2xl font-bold">SHA3</div>
            <div className="text-xs text-muted-foreground">hash chain</div>
          </div>
          <div className="p-3 rounded-lg border border-amber-500/30 bg-amber-500/5 text-center">
            <div className="text-2xl font-bold">1-way</div>
            <div className="text-xs text-muted-foreground">rotation</div>
          </div>
        </div>
      </Card>

      <Card title="Rotation Algorithm">
        <CodeBlock label="Hash-chain rotation" code={`code_epoch_N = SHA3-256(code_epoch_{N-1} || N)

# Client-side derivation:
def rotate_dna_code_for_epoch(initial_code, registered_at, now):
    epoch = (now - registered_at) // 90 * 24 * 3600
    current = initial_code
    for n in range(1, epoch + 1):
        current = sha3_256(current + n.to_bytes(8, 'big'))
    return current

# Verifier-side: hash submitted code and compare to commitment
submitted_hash = sha3_256(submitted_code)
verified = (submitted_hash == registration.code_commitment)`} />
      </Card>

      <Card title="Security Properties">
        <div className="space-y-2 text-sm">
          <div className="flex items-start gap-2"><span className="text-green-500">✓</span><span>Initial code NEVER stored in plaintext - only SHA3-256 commitment</span></div>
          <div className="flex items-start gap-2"><span className="text-green-500">✓</span><span>Compromise of epoch N code does NOT reveal prior codes (one-way hash)</span></div>
          <div className="flex items-start gap-2"><span className="text-green-500">✓</span><span>Bounded impact: 90-day window limits long-term compromise</span></div>
          <div className="flex items-start gap-2"><span className="text-green-500">✓</span><span>Client-side derivation: verifier never sees raw initial code</span></div>
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// UBL SCHEMA
// ════════════════════════════════════════════════════════════════════════════

export function UBLPage() {
  const { data: schema } = useAPI('/api/v1/ubl/schema', 30000);

  return (
    <div className="space-y-6">
      <Card title="UBL - Universal Behavioral Layer Schema" live>
        <p className="text-sm text-muted-foreground mb-4">{schema?.description || 'Loading...'}</p>
        <KVList items={[
          ['Version', schema?.version || '-'],
          ['Dimensions', fmt(schema?.dimensions)],
          ['Sources supported', fmt(schema?.supported_sources?.length)],
        ]} />
      </Card>
      <Card title="Supported Sources">
        <div className="flex flex-wrap gap-2">
          {(schema?.supported_sources || []).map((s: any) => (
            <Tag key={s} color="blue">{s}</Tag>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// BC (Behavioral Coherence)
// ════════════════════════════════════════════════════════════════════════════

export function BCPage() {
  const { data: bc } = useAPI('/api/v1/bc/evm', 15000);

  return (
    <div className="space-y-6">
      <Card title="BC - Behavioral Coherence (per ecosystem)" live>
        <KVList items={[
          ['Ecosystem', bc?.ecosystem || 'evm'],
          ['Coherence', (bc?.coherence || 0).toFixed(4)],
          ['Indexing rate', fmt(bc?.indexing_rate)],
          ['Chains', fmt(bc?.chains?.length)],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// XSL ECOLOGICAL
// ════════════════════════════════════════════════════════════════════════════

export function XSLPage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: xsl } = useAPI(`/api/v1/xsl/${entityId}`, 15000);

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
      <Card title="XSL - Cross-Sovereign Liquidity" live>
        <KVList items={[
          ['Sovereign liquidity score', (xsl?.sovereign_liquidity || 0).toFixed(4)],
          ['Cross-border flow', fmt(xsl?.cross_border_flow)],
          ['Ecological impact', (xsl?.ecological_impact || 0).toFixed(4)],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// TRANSDUCTION
// ════════════════════════════════════════════════════════════════════════════

export function TransductionPage() {
  const { data: trans } = useAPI('/api/v1/transduction/sensor_1', 15000);

  return (
    <div className="space-y-6">
      <Card title="Transduction - Sensor -> Signal Conversion" live>
        <KVList items={[
          ['Sensor ID', trans?.sensor_id || 'sensor_1'],
          ['Signal strength', (trans?.signal_strength || 0).toFixed(4)],
          ['Noise floor', (trans?.noise_floor || 0).toFixed(4)],
          ['SNR', (trans?.snr || 0).toFixed(4)],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// INVERSION
// ════════════════════════════════════════════════════════════════════════════

export function InversionPage() {
  const { data: inv } = useAPI('/api/v1/inversion', 15000);

  return (
    <div className="space-y-6">
      <Card title="Inversion - Endogenous Metric Discovery" live>
        <p className="text-sm text-muted-foreground mb-4">{inv?.thesis || 'Loading...'}</p>
        <KVList items={[
          ['Broken stack', inv?.broken_stack || '-'],
          ['Endogenous metric', inv?.endogenous_metric || '-'],
          ['Key inversions', fmt(inv?.key_inversions?.length)],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PREDICTIVE LIMIT
// ════════════════════════════════════════════════════════════════════════════

export function PredictiveLimitPage() {
  const { data: pl } = useAPI('/api/v1/predictive_limit', 30000);

  return (
    <div className="space-y-6">
      <Card title="Predictive Completeness Limit - PC < 1 always" live>
        <p className="text-sm text-muted-foreground mb-4">{pl?.heisenberg_analogy || 'Loading...'}</p>
        <KVList items={[
          ['PC_limit', pct(pl?.PC_limit, 4)],
          ['H_irreducible', (pl?.H_irreducible || 0).toFixed(4)],
          ['H_future', (pl?.H_future || 0).toFixed(4)],
          ['Deltat (s)', (pl?.delta_t || 0).toFixed(2)],
          ['Deltaaccuracy', (pl?.delta_accuracy || 0).toFixed(4)],
          ['Limit product', (pl?.limit_product || 0).toFixed(6)],
          ['Akashic depth', fmt(pl?.akashic_depth)],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// INFORMATION CONSERVATION
// ════════════════════════════════════════════════════════════════════════════

export function InformationPage() {
  const { data: info } = useAPI('/api/v1/information/conservation', 15000);

  return (
    <div className="space-y-6">
      <Card title="Information Conservation - dI/dt >= 0" live>
        <KVList items={[
          ['I_TRION (current)', fmt(info?.I_current || info?.I_total)],
          ['I_in', fmt(info?.I_in)],
          ['I_out', fmt(info?.I_out)],
          ['I_decay', fmt(info?.I_decay)],
          ['Conservation gap', (info?.conservation_gap || 0).toFixed(6)],
          ['Violations', info?.has_violations ? 'YES' : '0'],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PHASE SIGNAL
// ════════════════════════════════════════════════════════════════════════════

export function PhaseSignalPage() {
  const { data: ps } = useAPI('/api/v1/phase_signal', 15000);

  return (
    <div className="space-y-6">
      <Card title="Phase Signal - Behavioral Velocity & Akashic Coverage" live>
        <KVList items={[
          ['Coherence', (ps?.coherence || 0).toFixed(4)],
          ['Behavioral velocity', (ps?.behavioral_velocity || 0).toFixed(4)],
          ['Akashic coverage', pct(ps?.akashic_coverage, 2)],
          ['Action required', ps?.action_required || '-'],
          ['Description', ps?.description || '-'],
        ]} />
      </Card>
    </div>
  );
}
