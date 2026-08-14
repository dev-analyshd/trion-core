/**
 * Akashic Records Pages - Epigenetics, Fork Resolution, Resurrection, Trajectory, Dormancy,
 * Genesis, Convergence, Manifestation Gap, Negative Space, Emergence
 */
'use client';

import { useState } from 'react';
import { Card, StatCard, ProgressBar, Badge, DataTable, KVList, EmptyState, Tag } from '../components/ui';
import { useAPI } from '../lib/hooks';
import { fetchAPI, fmt, pct, tfmt, dtfmt, truncate, hex, compact, statusColor } from '../lib/api';
import * as Icons from 'lucide-react';

const DEFAULT_ENTITY = '0x2e49c1ff182bea5e33246a5f88f78cab6108cdde7b14f73bf8f7a06d6940c6ec';
const DEFAULT_ASSET = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'; // USDC

function EntitySelector({ id, setId, label = 'Entity ID' }: { id: string; setId: (s: string) => void; label?: string }) {
  return (
    <Card title={`${label} Selector`}>
      <input
        type="text"
        value={id}
        onChange={e => setId(e.target.value)}
        placeholder={`${label}...`}
        className="w-full px-3 py-2 rounded-lg border border-border bg-input text-sm font-mono"
      />
    </Card>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// EPIGENETICS
// ════════════════════════════════════════════════════════════════════════════

export function EpigeneticsPage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: epi } = useAPI(`/api/v1/akashic/epigenetics/${entityId}`, 15000);

  return (
    <div className="space-y-6">
      <EntitySelector id={entityId} setId={setEntityId} />
      <Card title="Epigenetic Layer - Environment-Modulated Expression" live>
        <KVList items={[
          ['Threat level', epi?.threat_level || 'LOW'],
          ['Expression state', epi?.expression_state || 'NORMAL'],
          ['Modification count', fmt(epi?.modification_count)],
          ['Last update', dtfmt(epi?.last_update)],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// FORK RESOLUTION
// ════════════════════════════════════════════════════════════════════════════

export function ForkResolutionPage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: fork } = useAPI(`/api/v1/fork_resolution/${entityId}`, 15000);

  return (
    <div className="space-y-6">
      <EntitySelector id={entityId} setId={setEntityId} />
      <Card title="Fork Resolution Protocol - CC_A / CC_B Continuity" live>
        <KVList items={[
          ['CC_A (chain A)', (fork?.cc_a || 0).toFixed(4)],
          ['CC_B (chain B)', (fork?.cc_b || 0).toFixed(4)],
          ['Weight w_A', (fork?.w_a || 0).toFixed(4)],
          ['Weight w_B', (fork?.w_b || 0).toFixed(4)],
          ['Winner', fork?.winner || '-'],
          ['Confidence', (fork?.confidence || 0).toFixed(4)],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// RESURRECTION
// ════════════════════════════════════════════════════════════════════════════

export function ResurrectionPage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: res } = useAPI(`/api/v1/resurrection/${entityId}`, 15000);

  return (
    <div className="space-y-6">
      <EntitySelector id={entityId} setId={setEntityId} />
      <Card title="Resurrection Inference - Delta_res = w_d-e^(-kappaT) + w_c-sim + w_x-g(C)" live>
        <KVList items={[
          ['Delta_resurrection score', (res?.delta_resurrection || 0).toFixed(4)],
          ['Dormancy period T', fmt(res?.dormancy_period_blocks)],
          ['Decay constant kappa', (res?.kappa || 0).toFixed(4)],
          ['Similarity sim(S_pre, S_react)', (res?.similarity || 0).toFixed(4)],
          ['Coherence g(C)', (res?.g_c || 0).toFixed(4)],
          ['Dormancy type', res?.dormancy_type || '-'],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// TRAJECTORY ANOMALY
// ════════════════════════════════════════════════════════════════════════════

export function TrajectoryPage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: traj } = useAPI(`/api/v1/trajectory/${entityId}`, 15000);
  const { data: anomaly } = useAPI(`/api/v1/trajectory_anomaly/${entityId}`, 15000);

  return (
    <div className="space-y-6">
      <EntitySelector id={entityId} setId={setEntityId} />
      <Card title="Trajectory Anomaly Monitor - KL Divergence" live>
        <KVList items={[
          ['KL divergence', (anomaly?.kl_divergence || 0).toFixed(6)],
          ['Threshold', (anomaly?.threshold || 0.1).toFixed(4)],
          ['Anomaly detected', anomaly?.anomaly_detected ? 'YES' : 'NO'],
          ['Trajectory vector', JSON.stringify(traj?.trajectory_vector || [])],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// DORMANCY
// ════════════════════════════════════════════════════════════════════════════

export function DormancyPage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: dorm } = useAPI(`/api/v1/dormancy/${entityId}`, 15000);

  return (
    <div className="space-y-6">
      <EntitySelector id={entityId} setId={setEntityId} />
      <Card title="Dormancy Classification - 5 Types" live>
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-4">
          {['ACTIVE', 'DORMANT', 'HIBERNATING', 'DECEASED', 'RESURRECTED'].map((t, i) => {
            const active = dorm?.dormancy_type === t;
            return (
              <div key={t} className={`p-3 rounded border-2 text-center ${active ? 'border-blue-500 bg-blue-500/10' : 'border-border opacity-50'}`}>
                <div className="text-xs font-semibold">{t}</div>
              </div>
            );
          })}
        </div>
        <KVList items={[
          ['Type', dorm?.dormancy_type || 'ACTIVE'],
          ['Duration (blocks)', fmt(dorm?.duration_blocks)],
          ['Decay factor', (dorm?.decay_factor || 0).toFixed(4)],
          ['Resurrection probability', pct(dorm?.resurrection_probability, 2)],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// GENESIS
// ════════════════════════════════════════════════════════════════════════════

export function GenesisPage() {
  const [assetId, setAssetId] = useState(DEFAULT_ASSET);
  const { data: gen } = useAPI(`/api/v1/genesis/${assetId}`, 15000);
  const { data: genFp } = useAPI(`/api/v1/genesis/fingerprint/${assetId}`, 15000);

  return (
    <div className="space-y-6">
      <EntitySelector id={assetId} setId={setAssetId} label="Asset ID" />
      <Card title="Genesis Inference - conf_genesis = 1 - e^(-0.001-D)" live>
        <KVList items={[
          ['conf_genesis', (gen?.conf_genesis || 0).toFixed(4)],
          ['Akashic depth D', fmt(gen?.akashic_depth)],
          ['Decay lambda', '0.001'],
          ['Genesis timestamp', dtfmt(gen?.genesis_timestamp)],
        ]} />
      </Card>
      <Card title="Genesis Fingerprint">
        <KVList items={[
          ['Fingerprint hash', hex(genFp?.fingerprint_hash, 16)],
          ['Confidence', pct(genFp?.confidence, 2)],
          ['Method', genFp?.method || '-'],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// CONVERGENCE DETAIL
// ════════════════════════════════════════════════════════════════════════════

export function ConvergenceDetailPage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: conv } = useAPI(`/api/v1/convergence/${entityId}`, 15000);

  return (
    <div className="space-y-6">
      <EntitySelector id={entityId} setId={setEntityId} />
      <Card title="Convergence Theorem - Per-Entity" live>
        <KVList items={[
          ['C(t)', (conv?.C_t || 0).toFixed(4)],
          ['C* asymptote', (conv?.C_star || 0).toFixed(4)],
          ['Convergence rate', (conv?.convergence_rate || 0).toFixed(6)],
          ['Converged', conv?.converged ? 'YES' : 'NO'],
          ['Akashic depth', fmt(conv?.akashic_depth)],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// MANIFESTATION GAP
// ════════════════════════════════════════════════════════════════════════════

export function ManifestationGapPage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: mg } = useAPI(`/api/v1/manifestation_gap/${entityId}`, 15000);

  return (
    <div className="space-y-6">
      <EntitySelector id={entityId} setId={setEntityId} />
      <Card title="Manifestation Gap - Latent vs. Manifest Behavior" live>
        <KVList items={[
          ['Gap score', (mg?.gap_score || 0).toFixed(4)],
          ['Latent behavior', (mg?.latent || 0).toFixed(4)],
          ['Manifest behavior', (mg?.manifest || 0).toFixed(4)],
          ['Bridging threshold', (mg?.threshold || 0).toFixed(4)],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// NEGATIVE SPACE
// ════════════════════════════════════════════════════════════════════════════

export function NegativeSpacePage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: ns } = useAPI(`/api/v1/negative_space/${entityId}`, 15000);

  return (
    <div className="space-y-6">
      <EntitySelector id={entityId} setId={setEntityId} />
      <Card title="Negative Space - What the Entity Does NOT Do" live>
        <KVList items={[
          ['Negative space score', (ns?.negative_space_score || 0).toFixed(4)],
          ['Missing expected actions', fmt(ns?.missing_actions?.length)],
          ['Behavioral absence ratio', (ns?.absence_ratio || 0).toFixed(4)],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// EMERGENCE
// ════════════════════════════════════════════════════════════════════════════

export function EmergencePage() {
  const [entityId, setEntityId] = useState(DEFAULT_ENTITY);
  const { data: em } = useAPI(`/api/v1/emergence/${entityId}`, 15000);

  return (
    <div className="space-y-6">
      <EntitySelector id={entityId} setId={setEntityId} />
      <Card title="Emergence Detection - Novel Behavioral Patterns" live>
        <KVList items={[
          ['Emergence score', (em?.emergence_score || 0).toFixed(4)],
          ['Novel pattern count', fmt(em?.novel_patterns)],
          ['Complexity increase', (em?.complexity_delta || 0).toFixed(4)],
          ['Detected at', dtfmt(em?.detected_at)],
        ]} />
      </Card>
    </div>
  );
}
