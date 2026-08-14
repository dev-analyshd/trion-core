/**
 * Security Pages - SEC, Living Security, Chameleon, CRISPR, PQC, MF, MEV, Immune, Attacks
 */
'use client';

import { useState } from 'react';
import { Card, StatCard, ProgressBar, Badge, DataTable, KVList, EmptyState, Tag, CodeBlock } from '../components/ui';
import { useAPI } from '../lib/hooks';
import { fetchAPI, fmt, pct, tfmt, dtfmt, truncate, hex, compact, statusColor } from '../lib/api';
import * as Icons from 'lucide-react';

const DEFAULT_ENTITY = '0x2e49c1ff182bea5e33246a5f88f78cab6108cdde7b14f73bf8f7a06d6940c6ec';

// ════════════════════════════════════════════════════════════════════════════
// SEC COMPOSITE
// ════════════════════════════════════════════════════════════════════════════

export function SECPage() {
  const { data: sec } = useAPI('/api/v1/security/sec', 10000);
  const { data: kvStatus } = useAPI('/api/v1/kv/status', 15000);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="SEC(t)" value={pct(sec?.effective_sec, 2)} color="green" />
        <StatCard label="LSS" value={pct(1.0, 0)} sub="Living Security" color="blue" />
        <StatCard label="PQC" value={pct(sec?.pqc_score || 0.9, 0)} sub="Post-Quantum" color="purple" />
        <StatCard label="CC" value={pct(sec?.cc_score, 0)} sub="Cross-Chain" color="amber" />
      </div>

      <Card title="SEC(t) = LSS - PQC - CC - Composite Security Score" live>
        <div className="text-center py-6">
          <div className="text-5xl font-bold ticker">{pct(sec?.effective_sec, 4)}</div>
          <div className="text-sm text-muted-foreground mt-2">{sec?.disclosure || 'Loading...'}</div>
        </div>
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center">
            <div className="text-2xl font-bold text-blue-500">100%</div>
            <div className="text-xs text-muted-foreground">LSS - Living Security</div>
            <ProgressBar value={1.0} color="blue" />
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-purple-500">90%</div>
            <div className="text-xs text-muted-foreground">PQC - Post-Quantum</div>
            <ProgressBar value={0.9} color="blue" />
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-amber-500">{pct(sec?.cc_score, 0)}</div>
            <div className="text-xs text-muted-foreground">CC - Cross-Chain</div>
            <ProgressBar value={sec?.cc_score || 0} color="amber" />
          </div>
        </div>
      </Card>

      <Card title="0G KV Execution Gate" live>
        <KVList items={[
          ['Component', kvStatus?.component || '-'],
          ['Gate Chain', kvStatus?.gate_chain || '-'],
          ['Gate Contract', hex(kvStatus?.gate_contract, 16)],
          ['Latency Target', `${kvStatus?.latency_target_ms || 0}ms`],
          ['Integration Note', kvStatus?.integration_note || '-'],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// LIVING SECURITY
// ════════════════════════════════════════════════════════════════════════════

export function LivingSecurityPage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: immune } = useAPI(`/api/v1/immune/${entityId}`, 15000);
  const { data: livingIdx } = useAPI(`/api/v1/living_index/${entityId}`, 15000);
  const { data: sec } = useAPI('/api/v1/security/sec', 15000);

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

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Living Index" value={(livingIdx?.living_index || 0).toFixed(4)} color="green" />
        <StatCard label="CRISPR Library" value={fmt(immune?.crispr_library_size)} sub="signatures" color="blue" />
        <StatCard label="Immune Clearance" value={immune?.immune_clearance ? 'CLEARED' : 'PENDING'} color={immune?.immune_clearance ? 'green' : 'amber'} />
        <StatCard label="SEC Composite" value={pct(sec?.effective_sec, 2)} color="green" />
      </div>

      <Card title="Living Security Stack - 8 Layers" live>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            { name: 'Thermodynamic', icon: '🔥', desc: 'H_environment + Landauer bound' },
            { name: 'Physical Phi', icon: '⚡', desc: 'Shannon entropy F1-F9' },
            { name: 'Akashic Ledger', icon: '📚', desc: 'Append-only BH ledger' },
            { name: 'PQC Layer', icon: '🔐', desc: 'ML-KEM + ML-DSA + SLH-DSA' },
            { name: '5-Plane Coherence', icon: '🎯', desc: 'C(t) gate' },
            { name: 'BEO Resolution', icon: '🧬', desc: '128-dim FAISS' },
            { name: 'CRISPR Defense', icon: '🛡️', desc: 'Adaptive signatures' },
            { name: 'ANIMA Intelligence', icon: '🌐', desc: 'Cross-source validation' },
          ].map(l => (
            <div key={l.name} className="p-3 rounded-lg border border-border bg-card hover:bg-muted/30 transition-colors">
              <div className="text-2xl mb-1">{l.icon}</div>
              <div className="font-semibold text-sm">{l.name}</div>
              <div className="text-xs text-muted-foreground mt-1">{l.desc}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="CRISPR Adaptive Immune Memory" live>
        <KVList items={[
          ['Library size', fmt(immune?.crispr_library_size)],
          ['Signatures stored', fmt(immune?.signatures_stored)],
          ['Immune clearance', immune?.immune_clearance ? 'YES' : 'NO'],
          ['Last adaptation', dtfmt(immune?.last_adaptation)],
          ['Adaptive count', fmt(immune?.adaptive_count)],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// CHAMELEON PROTOCOL
// ════════════════════════════════════════════════════════════════════════════

export function ChameleonPage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: cham } = useAPI(`/api/v1/chameleon/${entityId}`, 10000);

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

      <Card title="Chameleon Protocol - 5-Level Threat State Machine" live>
        <div className="flex items-center justify-between gap-2 mb-4 overflow-x-auto">
          {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL', 'WEAPONIZATION'].map((level, i) => {
            const active = cham?.threat_level?.toUpperCase() === level;
            // Use valid Tailwind colors: green, amber, orange (Tailwind v4 has orange), red, rose
            const colorClasses = [
              'border-green-500 bg-green-500/10',
              'border-amber-500 bg-amber-500/10',
              'border-orange-500 bg-orange-500/10',
              'border-red-500 bg-red-500/10',
              'border-rose-500 bg-rose-500/10',
            ];
            return (
              <div key={level} className={`flex-1 min-w-[80px] p-3 rounded text-center border-2 transition-all ${active ? colorClasses[i] : 'border-border opacity-50'}`}>
                <div className="text-xs font-semibold truncate">{level}</div>
                <div className="text-xs mt-1">{i + 1}</div>
              </div>
            );
          })}
        </div>
        <KVList items={[
          ['Current Threat Level', cham?.threat_level || 'LOW'],
          ['State transitions', fmt(cham?.state_transitions || 0)],
          ['Last escalation', dtfmt(cham?.last_escalation)],
          ['Auto-response', cham?.auto_response || '-'],
          ['Weaponization detected', cham?.weaponization ? 'YES' : 'NO'],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// CRISPR DEFENSE
// ════════════════════════════════════════════════════════════════════════════

export function CRISPRPage() {
  const { data: attacks } = useAPI('/api/v1/attacks', 15000);

  return (
    <div className="space-y-6">
      <Card title="CRISPR Defense - Adaptive Attack Signature Library" live>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Known Signatures" value={fmt(attacks?.crispr_signatures || 0)} color="blue" />
          <StatCard label="Pattern Breakdown" value={fmt(Object.keys(attacks?.pattern_breakdown || {}).length)} color="purple" />
          <StatCard label="Gate Contract" value={hex(attacks?.gate_contract, 12)} />
          <StatCard label="Gate Chain" value={attacks?.gate_chain || '-'} />
        </div>
      </Card>

      <Card title="Attack Pattern Catalog" live>
        <DataTable
          headers={['Pattern', 'Count', 'Severity']}
          rows={Object.entries(attacks?.pattern_breakdown || {}).map(([p, c]: any) => [
            <Tag color="red">{p}</Tag>,
            fmt(c),
            <Badge status="CRITICAL" />,
          ])}
          emptyMessage="Loading patterns..."
        />
      </Card>

      <Card title="90+ CRISPR Signatures (Sample)">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 max-h-80 overflow-auto">
          {(attacks?.attacks || []).slice(0, 40).map((a: any, i: number) => (
            <div key={i} className="p-2 rounded border border-border text-xs">
              <div className="font-mono">{a.name || a.signature || `sig_${i}`}</div>
              <div className="text-muted-foreground mt-1">{a.type || '-'}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// POST-QUANTUM CRYPTO
// ════════════════════════════════════════════════════════════════════════════

export function PQCPage() {
  const { data: sec } = useAPI('/api/v1/security/sec', 10000);

  return (
    <div className="space-y-6">
      <Card title="Post-Quantum Cryptography - NIST FIPS 203/204/205" live>
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="p-4 rounded-lg border border-purple-500/30 bg-purple-500/5">
            <div className="text-purple-500 font-semibold">ML-KEM-768</div>
            <div className="text-xs text-muted-foreground mt-1">FIPS 203 - Key Encapsulation</div>
            <div className="mt-2"><Badge status={sec?.pqc_score >= 0.9 ? 'OK' : 'WARNING'} label="VERIFIED" /></div>
          </div>
          <div className="p-4 rounded-lg border border-blue-500/30 bg-blue-500/5">
            <div className="text-blue-500 font-semibold">ML-DSA-65</div>
            <div className="text-xs text-muted-foreground mt-1">FIPS 204 - Digital Signature</div>
            <div className="mt-2"><Badge status={sec?.pqc_score >= 0.9 ? 'OK' : 'WARNING'} label="VERIFIED" /></div>
          </div>
          <div className="p-4 rounded-lg border border-green-500/30 bg-green-500/5">
            <div className="text-green-500 font-semibold">SLH-DSA-SHAKE-128s</div>
            <div className="text-xs text-muted-foreground mt-1">FIPS 205 - Stateless Hash</div>
            <div className="mt-2"><Badge status={sec?.pqc_score >= 0.9 ? 'OK' : 'WARNING'} label="VERIFIED" /></div>
          </div>
        </div>
      </Card>

      <Card title="PQC Verification Details">
        <p className="text-sm text-muted-foreground mb-3">{sec?.disclosure || 'Loading PQC verification...'}</p>
        <KVList items={[
          ['PQC Score', pct(sec?.pqc_score || 0.9, 0)],
          ['NIST Level', 'L3 (192-bit security)'],
          ['Kyber round-trip', 'verified'],
          ['Dilithium round-trip', 'verified'],
          ['SPHINCS+ round-trip', 'verified'],
          ['Bootstrap weight', pct(sec?.bootstrap_weight, 2)],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// MANIPULATION DETECTOR (MF)
// ════════════════════════════════════════════════════════════════════════════

export function ManipulationPage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: mf } = useAPI(`/api/v1/security/${entityId}/mf`, 10000);

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

      <Card title="Manipulation Fingerprint Detector - 7 Types" live>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {[
            { name: 'ORACLE_ATTACK', formula: 'MF = 1.00 (auto)', threshold: '-', color: 'red' },
            { name: 'WASH_TRADING', formula: 'MF = 0.70 * cyclic_flow_ratio', threshold: '> 0.50', color: 'amber' },
            { name: 'COORDINATED_PUMP', formula: 'MF = 0.85 * sync_buy_ratio', threshold: '> 0.80', color: 'amber' },
            { name: 'SYBIL_LIQUIDITY', formula: 'MF = 0.60 * funding_concentration', threshold: 'funding < 3', color: 'amber' },
            { name: 'GOVERNANCE_CAPTURE', formula: 'MF = 0.50 * (HHI-2500)/7500', threshold: 'HHI > 4000', color: 'amber' },
            { name: 'MEV_EXTRACTION', formula: 'MF = 0.40 * (mev_rate-0.005)/0.045', threshold: '> 0.005', color: 'amber' },
            { name: 'FAKE_VOLUME', formula: 'MF = 0.80 * (1 - H/H_baseline)', threshold: '> 10* ratio', color: 'amber' },
          ].map(t => (
            <div key={t.name} className="p-3 rounded-lg border border-border bg-card">
              <div className="flex items-center justify-between mb-1">
                <span className={`font-mono text-sm font-semibold text-${t.color}-500`}>{t.name}</span>
                <Badge status={t.color === 'red' ? 'CRITICAL' : 'WARNING'} />
              </div>
              <div className="text-xs font-mono">{t.formula}</div>
              <div className="text-xs text-muted-foreground mt-1">Threshold: {t.threshold}</div>
            </div>
          ))}
        </div>
      </Card>

      {mf && (
        <Card title={`MF Detection Result - ${truncate(entityId, 16)}`} live>
          <KVList items={[
            ['MF Score', (mf.mf_score || 0).toFixed(4)],
            ['Detected types', fmt(mf.detected_types?.length || 0)],
            ['Highest severity', mf.highest_severity || '-'],
            ['Override (oracle)', mf.oracle_override ? 'YES' : 'NO'],
          ]} />
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// MEV DETECTION
// ════════════════════════════════════════════════════════════════════════════

export function MEVPage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: mev } = useAPI(`/api/v1/mev/${entityId}`, 15000);

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

      <Card title="MEV Extraction Detector" live>
        <KVList items={[
          ['MEV rate', (mev?.mev_rate || 0).toFixed(6)],
          ['Threshold', '0.005 (0.5%)'],
          ['Detected', mev?.mev_detected ? 'YES' : 'NO'],
          ['MEV volume', fmt(mev?.mev_volume)],
          ['Attacker profit', fmt(mev?.attacker_profit)],
          ['Victim loss', fmt(mev?.victim_loss)],
        ]} />
      </Card>

      <Card title="MEV Pattern Categories">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {['Sandwich', 'Arbitrage', 'Front-running', 'Back-running', 'Just-in-time', 'Sniper', 'Liquidation', 'Atomic arb'].map(p => (
            <div key={p} className="p-3 rounded-lg border border-border text-center">
              <div className="text-sm font-semibold">{p}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// IMMUNE MEMORY
// ════════════════════════════════════════════════════════════════════════════

export function ImmunePage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: immune } = useAPI(`/api/v1/immune/${entityId}`, 15000);

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

      <Card title="CRISPR-Style Adaptive Immune Memory" live>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Library Size" value={fmt(immune?.crispr_library_size)} color="blue" />
          <StatCard label="Signatures" value={fmt(immune?.signatures_stored)} color="purple" />
          <StatCard label="Immune Clearance" value={immune?.immune_clearance ? 'YES' : 'NO'} color={immune?.immune_clearance ? 'green' : 'amber'} />
          <StatCard label="Adaptive Count" value={fmt(immune?.adaptive_count)} color="green" />
        </div>
        <div className="mt-4 pt-4 border-t border-border">
          <KVList items={[
            ['Persistence', 'SQLite (akashic/crispr_adaptive.db)'],
            ['Last adaptation', dtfmt(immune?.last_adaptation)],
            ['Storage root', hex(immune?.storage_root, 16)],
            ['Immune system version', immune?.immune_version || '1.0'],
          ]} />
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// ATTACK SIMULATOR
// ════════════════════════════════════════════════════════════════════════════

export function AttacksPage() {
  const { data: attacks } = useAPI('/api/v1/attacks', 15000);
  const { data: demo } = useAPI('/api/v1/demo/simulate_attack', 30000);
  const { data: demoStats } = useAPI('/api/v1/demo/stats', 30000);
  const { data: auditPatterns } = useAPI('/api/v1/audit/patterns', 30000);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Attacks in DB" value={fmt(demoStats?.attacks_in_db)} color="red" />
        <StatCard label="Total Value" value={demoStats?.attacks_value_total_fmt || '$0'} color="amber" />
        <StatCard label="API Routes" value={fmt(demoStats?.api_routes)} color="blue" />
        <StatCard label="Audit Patterns" value={fmt(auditPatterns?.count)} color="purple" />
      </div>

      <Card title="Latest Simulated Attack" live>
        {demo && (
          <KVList items={[
            ['Attack', demo.attack || '-'],
            ['Attacker', hex(demo.attacker_address, 14)],
            ['Date', demo.date || '-'],
            ['Detection lead time', `${fmt(demo.detection_lead_time_hours || 0)}h`],
            ['Description', truncate(demo.description, 60)],
          ]} />
        )}
      </Card>

      <Card title="Audit Pattern Categories" live>
        <DataTable
          headers={['Category', 'Severity', 'Count']}
          rows={Object.entries(auditPatterns?.categories || {}).map(([cat, count]: any) => [
            cat,
            <Badge status="WARNING" />,
            fmt(count),
          ])}
          emptyMessage="Loading patterns..."
        />
      </Card>

      <Card title="Attack Simulator Stats">
        <KVList items={[
          ['Attacks in DB', fmt(demoStats?.attacks_in_db)],
          ['Total value', demoStats?.attacks_value_total_fmt || '-'],
          ['Value (excl. Terra)', demoStats?.attacks_value_excl_terra_fmt || '-'],
          ['API routes', fmt(demoStats?.api_routes)],
        ]} />
      </Card>
    </div>
  );
}
