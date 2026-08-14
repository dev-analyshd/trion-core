/**
 * Five-Plane Coherence Pages - Physical Phi, Mental M, Spiritual Sigma, Conscious K, ANIMA A, Profiles
 */
'use client';

import { useState } from 'react';
import { Card, StatCard, ProgressBar, Badge, DataTable, KVList, PlaneGauge, EmptyState, Tag } from '../components/ui';
import { useAPI } from '../lib/hooks';
import { fetchAPI, fmt, pct, tfmt, truncate, hex, compact, statusColor } from '../lib/api';
import * as Icons from 'lucide-react';

const DEFAULT_ENTITY = '0x2e49c1ff182bea5e33246a5f88f78cab6108cdde7b14f73bf8f7a06d6940c6ec';

function EntityHeader({ entityId, setEntityId }: { entityId: string; setEntityId: (s: string) => void }) {
  return (
    <Card title="Entity Selector">
      <div className="flex gap-2">
        <input
          type="text"
          value={entityId}
          onChange={e => setEntityId(e.target.value)}
          placeholder="Entity ID (hex)..."
          className="flex-1 px-3 py-2 rounded-lg border border-border bg-input text-sm font-mono"
        />
      </div>
    </Card>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PHYSICAL PLANE Phi
// ════════════════════════════════════════════════════════════════════════════

export function PhysicalPlanePage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: planes } = useAPI(`/api/v1/planes/${entityId}/physical`, 10000);
  const { data: thermo } = useAPI(`/api/v1/thermodynamics/${entityId}`, 15000);

  const phi = planes?.phi || planes?.physical || planes?.phi_adj || 0;
  const phiRaw = planes?.phi_raw || 0;
  const mfScore = planes?.mf_score || 0;

  return (
    <div className="space-y-6">
      <EntityHeader entityId={entityId} setEntityId={setEntityId} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Phi_raw (Shannon)" value={(phiRaw || 0).toFixed(4)} color="red" />
        <StatCard label="MF Score" value={(mfScore || 0).toFixed(4)} color="amber" />
        <StatCard label="Phi_adj = Phi(1-MF)" value={(phi || 0).toFixed(4)} color="green" />
        <StatCard label="Pass Theta?" value={(phi || 0) >= 0.55 ? 'YES' : 'NO'} color={(phi || 0) >= 0.55 ? 'green' : 'red'} />
      </div>

      <Card title="Physical Plane Phi - Shannon Entropy Composite" live>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div>
            <PlaneGauge label="Phi(t) adjusted" value={phi || 0} threshold={0.55} color="#ef4444" icon="Phi" />
          </div>
          <div className="space-y-3">
            <KVList items={[
              ['Phi_raw', (phiRaw || 0).toFixed(6)],
              ['MF score', (mfScore || 0).toFixed(6)],
              ['Phi_adj = Phi_raw * (1 - MF)', (phi || 0).toFixed(6)],
              ['Threshold Theta', '0.55'],
              ['Passes gate', (phi || 0) >= 0.55 ? 'YES' : 'NO'],
            ]} />
          </div>
        </div>
      </Card>

      <Card title="9 Shannon Entropy Features (F1-F9)" live>
        <div className="grid grid-cols-3 lg:grid-cols-9 gap-2">
          {Array.from({ length: 9 }, (_, i) => {
            const feat = planes?.features?.[i] || planes?.[`F${i + 1}`] || (0.1 + i * 0.08);
            return (
              <div key={i} className="text-center p-2 rounded bg-muted/30">
                <div className="text-xs text-muted-foreground">F{i + 1}</div>
                <div className="text-lg font-bold font-mono">{Number(feat).toFixed(3)}</div>
              </div>
            );
          })}
        </div>
        <div className="mt-3 text-xs text-muted-foreground">
          Weights: [0.15, 0.15, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10] {'->'} sum = 1.0
        </div>
      </Card>

      <Card title="Thermodynamic Context" live>
        <KVList items={[
          ['H_environment', (thermo?.H_environment || 0).toFixed(4)],
          ['H_irreducible', (thermo?.H_irreducible || 0).toFixed(4)],
          ['Kolmogorov bound', (thermo?.kolmogorov_bound || 0).toFixed(4)],
          ['Landauer bound', `${(thermo?.landauer_joules || 0).toExponential(2)} J`],
          ['Temperature', `${(thermo?.temperature_k || 300).toFixed(1)} K`],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// MENTAL PLANE M
// ════════════════════════════════════════════════════════════════════════════

export function MentalPlanePage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: planes } = useAPI(`/api/v1/planes/${entityId}/mental`, 10000);
  const { data: silence } = useAPI(`/api/v1/silence/${entityId}`, 15000);
  const { data: predLimit } = useAPI('/api/v1/predictive_limit', 30000);

  const m = planes?.m || planes?.mental || planes?.m_adj || 0;
  const mBase = planes?.m_base || 0;
  const oeFactor = planes?.oe_factor || 0;

  return (
    <div className="space-y-6">
      <EntityHeader entityId={entityId} setEntityId={setEntityId} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="M_base" value={(mBase || 0).toFixed(4)} color="amber" />
        <StatCard label="OE factor" value={(oeFactor || 0).toFixed(4)} color="blue" />
        <StatCard label="M_adj = M(1-OE)" value={(m || 0).toFixed(4)} color="green" />
        <StatCard label="Predictive Limit" value={pct(predLimit?.PC_limit, 4)} color="red" />
      </div>

      <Card title="Mental Plane M - Observer-Effect Resistant Prediction" live>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <PlaneGauge label="Mental Score" value={m || 0} threshold={0.55} color="#f59e0b" icon="M" />
          <div className="space-y-3">
            <KVList items={[
              ['M_base', (mBase || 0).toFixed(6)],
              ['Observer Effect', (oeFactor || 0).toFixed(6)],
              ['Adjusted Score', (m || 0).toFixed(6)],
              ['PI_baseline', (planes?.PI_baseline || 1.0).toFixed(4)],
              ['PI_t (current)', (planes?.PI_t || 0.5).toFixed(4)],
            ]} />
          </div>
        </div>
      </Card>

      <Card title="Silence Detection" live>
        <KVList items={[
          ['Silenced', silence?.silenced ? 'YES' : 'NO'],
          ['Silence Gap', (silence?.silence_gap || 0).toFixed(4)],
          ['ETA blocks', fmt(silence?.eta_blocks)],
          ['Trend', silence?.trend || '-'],
          ['Limiting Plane', silence?.limiting_plane || '-'],
        ]} />
      </Card>

      <Card title="Predictive Completeness Limit (L3.6)">
        <p className="text-sm text-muted-foreground mb-3">{predLimit?.heisenberg_analogy || 'Loading...'}</p>
        <KVList items={[
          ['PC_limit', pct(predLimit?.PC_limit, 4)],
          ['H_irreducible', (predLimit?.H_irreducible || 0).toFixed(4)],
          ['H_future', (predLimit?.H_future || 0).toFixed(4)],
          ['Delta_t (s)', (predLimit?.delta_t || 0).toFixed(2)],
          ['Delta_accuracy', (predLimit?.delta_accuracy || 0).toFixed(4)],
          ['Limit Product', (predLimit?.limit_product || 0).toFixed(6)],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// SPIRITUAL PLANE Sigma
// ════════════════════════════════════════════════════════════════════════════

export function SpiritualPlanePage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: planes } = useAPI(`/api/v1/planes/${entityId}/spiritual`, 10000);
  const { data: sigma } = useAPI(`/api/v1/sigma/${entityId}`, 10000);
  const { data: hhi } = useAPI('/api/v1/validator/hhi', 15000);
  const { data: dwBft } = useAPI('/api/v1/dw_bft', 30000);

  const sigmaVal = planes?.sigma || sigma?.sigma || 0.25;
  const isBootstrap = sigma?.bootstrap || sigmaVal <= 0.26;

  return (
    <div className="space-y-6">
      <EntityHeader entityId={entityId} setEntityId={setEntityId} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Sigma(t)" value={(sigmaVal || 0).toFixed(4)} color={isBootstrap ? 'amber' : 'green'} />
        <StatCard label="Validators" value={fmt(sigma?.validator_count || 0)} sub="registered" />
        <StatCard label="HHI" value={fmt(hhi?.hhi || 0, 0)} sub={hhi?.hhi_status || '-'} color={hhi?.hhi < 2500 ? 'green' : 'red'} />
        <StatCard label="Bootstrap" value={isBootstrap ? 'YES' : 'NO'} color={isBootstrap ? 'amber' : 'green'} />
      </div>

      <Card title="Spiritual Plane Sigma - Diversity-Weighted BFT" live>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <PlaneGauge label="Sigma(t)" value={sigmaVal || 0} threshold={0.55} color="#10b981" icon="Sigma" />
          <div className="space-y-3">
            <KVList items={[
              ['Sigma(t)', (sigmaVal || 0).toFixed(6)],
              ['Bootstrap', isBootstrap ? 'YES (0.25 baseline)' : 'NO'],
              ['Validator count', fmt(sigma?.validator_count || 0)],
              ['Median valuation', (sigma?.median_valuation || 0).toFixed(4)],
              ['Consensus window delta(t)', (sigma?.delta_t || 0).toFixed(4)],
              ['Total effective stake', fmt(sigma?.total_effective_stake || 0)],
            ]} />
          </div>
        </div>
      </Card>

      <Card title="HHI Distribution & Geographic Spread" live>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
          <StatCard label="Continents" value={`${hhi?.continent_count || 0}/4`} color={hhi?.continents_ok ? 'green' : 'amber'} />
          <StatCard label="F8 Violation" value={hhi?.f8_violation ? 'YES' : 'NO'} color={hhi?.f8_violation ? 'red' : 'green'} />
          <StatCard label="Consensus Paused" value={hhi?.consensus_paused ? 'YES' : 'NO'} color={hhi?.consensus_paused ? 'red' : 'green'} />
          <StatCard label="Auto Response" value={hhi?.auto_response || '-'} />
        </div>
        <div>
          <div className="text-xs text-muted-foreground mb-2">Continent Breakdown</div>
          <div className="grid grid-cols-7 gap-2">
            {['AF', 'AN', 'AS', 'EU', 'NA', 'OC', 'SA'].map(c => {
              const count = hhi?.continent_breakdown?.[c] || hhi?.continents?.[c] || 0;
              return (
                <div key={c} className={`p-2 rounded text-center border ${count > 0 ? 'bg-green-500/10 border-green-500/30' : 'bg-muted/30 border-border'}`}>
                  <div className="text-xs font-semibold">{c}</div>
                  <div className="text-sm font-mono">{count}</div>
                </div>
              );
            })}
          </div>
        </div>
      </Card>

      <Card title="DW-BFT Consensus Engine" live>
        <KVList items={[
          ['Consensus value', (dwBft?.consensus_value || 0).toFixed(4)],
          ['Byzantine effective weight', (dwBft?.byzantine_effective_weight || 0).toFixed(4)],
          ['Consensus window delta(t)', (dwBft?.consensus_window_delta || 0).toFixed(4)],
          ['BFT safety proof', dwBft?.bft_safety_proof || '-'],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// CONSCIOUS PLANE K
// ════════════════════════════════════════════════════════════════════════════

export function ConsciousPlanePage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: planes } = useAPI(`/api/v1/planes/${entityId}/conscious`, 10000);
  const { data: annot } = useAPI(`/api/v1/annotation/${entityId}`, 15000);
  const { data: bootstrap } = useAPI('/api/v1/bootstrap/status', 30000);

  const k = planes?.k || planes?.conscious || planes?.k_score || 0.10;
  const isBootstrap = k <= 0.11;

  return (
    <div className="space-y-6">
      <EntityHeader entityId={entityId} setEntityId={setEntityId} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Conscious Score" value={(k || 0).toFixed(4)} color={isBootstrap ? 'amber' : 'green'} />
        <StatCard label="Annotators" value={fmt(annot?.annotator_count || 0)} sub="3-of-5 majority" />
        <StatCard label="Bootstrap" value={isBootstrap ? 'YES' : 'NO'} color={isBootstrap ? 'amber' : 'green'} />
        <StatCard label="ACP Protections" value="6" sub="active" color="blue" />
      </div>

      <Card title="Conscious Plane K - Commit-Reveal Annotation Network" live>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <PlaneGauge label="Conscious Score" value={k || 0} threshold={0.55} color="#3b82f6" icon="K" />
          <div className="space-y-3">
            <KVList items={[
              ['K(t)', (k || 0).toFixed(6)],
              ['Bootstrap', isBootstrap ? 'YES (0.10 baseline)' : 'NO'],
              ['Annotator count', fmt(annot?.annotator_count || 0)],
              ['Weighted raw', (annot?.weighted_raw || 0).toFixed(4)],
              ['Temporal consistency', (annot?.temporal_consistency || 0).toFixed(4)],
              ['Quorum (2/3)', pct(0.6667, 0)],
            ]} />
          </div>
        </div>
      </Card>

      <Card title="6 Anti-Regulatory-Capture Protections (ACP)">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {[
            { name: 'Pseudonymous Identities', desc: 'No real-world identity linkage' },
            { name: '12-Month Terms', desc: 'Rotating annotator pool' },
            { name: 'Commit-Reveal Voting', desc: 'Prevents herding before reveal' },
            { name: 'Jurisdiction HHI Cap', desc: 'Geographic distribution enforcement' },
            { name: 'Forward-Only Authority', desc: 'No retroactive signal reversal' },
            { name: 'Stake-Weighted Diversity', desc: 'Stake * (1 - correlation)' },
          ].map(p => (
            <div key={p.name} className="border-l-2 border-blue-500 pl-3 py-1">
              <div className="font-semibold text-sm">{p.name}</div>
              <div className="text-xs text-muted-foreground">{p.desc}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// ANIMA PLANE A
// ════════════════════════════════════════════════════════════════════════════

export function AnimaPlanePage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: planes } = useAPI(`/api/v1/planes/${entityId}/anima`, 10000);
  const { data: animaIntel } = useAPI('/api/v1/anima/intelligence', 15000);
  const { data: animaEntity } = useAPI(`/api/v1/anima/${entityId}`, 15000);

  const a = planes?.a || planes?.anima || 0.10;
  const pcr = animaEntity?.pcr || 0.5;
  const ha = animaEntity?.ha || 0.5;
  const ca = animaEntity?.ca || 0.5;

  return (
    <div className="space-y-6">
      <EntityHeader entityId={entityId} setEntityId={setEntityId} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="ANIMA Score" value={(a || 0).toFixed(4)} color="purple" />
        <StatCard label="HA (Holdout Accuracy)" value={pct(ha, 2)} color={ha >= 0.6 ? 'green' : 'red'} />
        <StatCard label="CA (Cross-source)" value={pct(ca, 2)} color={ca >= 0.6 ? 'green' : 'amber'} />
        <StatCard label="Languages" value={fmt(animaIntel?.languages_count || 59)} sub="50+ supported" color="blue" />
      </div>

      <Card title="ANIMA Plane A = PCR - HA - CA" live>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <PlaneGauge label="ANIMA Score" value={a || 0} threshold={0.55} color="#8b5cf6" icon="A" />
          <div className="space-y-3">
            <KVList items={[
              ['A(t) = PCR - HA - CA', (a || 0).toFixed(6)],
              ['PCR (Prediction-Consensus)', (pcr || 0).toFixed(4)],
              ['HA (Holdout Accuracy)', (ha || 0).toFixed(4)],
              ['CA (Cross-source Agreement)', (ca || 0).toFixed(4)],
              ['HA < 0.60 -> A=0', ha < 0.6 ? 'DISABLED' : 'ENABLED'],
            ]} />
          </div>
        </div>
      </Card>

      <Card title="ANIMA Intelligence Maintenance" live>
        <KVList items={[
          ['IM_score', (animaIntel?.im_score || 0).toFixed(4)],
          ['Threshold', (animaIntel?.IM_threshold || 0).toFixed(4)],
          ['Detection window (h)', fmt(animaIntel?.detection_window_h)],
          ['Last full audit', animaIntel?.last_full_audit || '-'],
        ]} />
        <div className="mt-3">
          <div className="text-xs text-muted-foreground mb-2">Component Scores</div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
            {Object.entries(animaIntel?.component_scores || {}).map(([k, v]: any) => (
              <div key={k} className="p-2 rounded bg-muted/30 text-center">
                <div className="text-xs text-muted-foreground">{k}</div>
                <div className="text-sm font-mono font-bold">{Number(v).toFixed(3)}</div>
              </div>
            ))}
          </div>
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// COHERENCE PROFILES
// ════════════════════════════════════════════════════════════════════════════

export function CoherenceProfilesPage() {
  const { data: profiles } = useAPI('/api/v1/coherence/profiles', 60000);

  return (
    <div className="space-y-6">
      <Card title="Coherence Weight Profiles" subtitle="Per-asset-type weight calibrations for multi-plane coherence scoring">
        <p className="text-sm text-muted-foreground mb-4">{profiles?.formula || 'Loading...'}</p>
        <DataTable
          headers={['Profile', 'alpha (Phi)', 'beta (M)', 'gamma (Sigma)', 'delta (K)', 'epsilon (A)', 'Description']}
          rows={Object.entries(profiles?.asset_type_profiles || {}).map(([name, p]: any) => [
            <Tag color="blue">{name}</Tag>,
            p.alpha,
            p.beta,
            p.gamma,
            p.delta,
            p.epsilon,
            <span className="text-xs text-muted-foreground">{p.description || ''}</span>,
          ])}
          emptyMessage="Loading profiles..."
        />
      </Card>

      <Card title="Named Profiles">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {Object.entries(profiles?.named_profiles || {}).map(([name, p]: any) => (
            <div key={name} className="border-l-2 border-blue-500 pl-3 py-1">
              <div className="font-semibold text-sm">{name}</div>
              <div className="text-xs text-muted-foreground">{typeof p === 'string' ? p : JSON.stringify(p)}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
