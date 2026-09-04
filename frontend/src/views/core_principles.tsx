'use client';

/**
 * TRION Core-Principles Views — whitepaper-aligned pages
 * =======================================================
 * Home / Witness / Zero-Bridge / BEO Dashboard / Action Economy / Digital Self
 *
 * Design principles (whitepaper §Vision):
 *   - Action first (creation > consumption)
 *   - Witness (every action is seen)
 *   - Coherence (score is visible)
 *   - Depth (history is permanent)
 *   - Love (ethics are visible)
 *   - Truth (silence over lies)
 */

import { useEffect, useState } from 'react';
import * as Icons from 'lucide-react';
import { Card, StatCard, ProgressBar, Badge, KVList, StreamView, EntityInput } from '../components/ui';
import { useAPI, useStream, useCounter } from '../lib/hooks';
import { CHAIN_COUNT, VM_FAMILY_COUNT } from '../lib/config';

// ═════════════════════════════════════════════════════════════════════════════
// HOME — BEO depth, coherence, witness feed
// ═════════════════════════════════════════════════════════════════════════════

export function HomePage() {
  const [entity, setEntity] = useState('0x742d35Cc6634C0532925a3b844Bc454e4438f44e');
  const { data: signal, loading } = useAPI(`/api/v1/signal/${entity}`, 8000);
  const { items: feed } = useStream('/api/v1/feed', 4000);
  const { data: health } = useAPI('/api/v1/health', 5000);
  const { data: moat } = useAPI('/api/v1/moat', 10000);

  const coherence = signal?.coherence_score ?? 0;
  const threshold = signal?.threshold ?? 0.66;
  const depth = useCounter(signal?.akashic_depth ?? 0);
  const isSilent = signal?.signal_type === 'SILENCE';

  return (
    <div className="space-y-6">
      {/* Hero — Truth or Silence */}
      <div className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-card via-card to-primary/5 p-8">
        <div className="grid-pattern absolute inset-0" />
        <div className="relative">
          <div className="flex items-center gap-2 mb-3">
            <span className="live-dot" />
            <span className="text-sm text-muted-foreground">
              {isSilent ? 'SILENCE — coherence insufficient' : 'TRUTH — all planes coherent'}
            </span>
          </div>
          <h1 className="text-4xl md:text-5xl font-bold tracking-tight mb-2">
            {isSilent ? 'The Silence is Information' : 'Behavioral Truth, Live'}
          </h1>
          <p className="text-muted-foreground max-w-2xl mb-6">
            TRION reads behavioral reality — accumulated on-chain history that cannot be
            temporarily moved. Every action is witnessed. Every pattern is permanent.
          </p>
          <div className="flex flex-wrap gap-4">
            <StatCard label="Coherence C(t)" value={coherence.toFixed(4)}
                      sub={`Θ(t) = ${threshold.toFixed(4)}`} color={isSilent ? 'amber' : 'green'} />
            <StatCard label="Akashic Depth D(t)" value={Math.floor(depth).toLocaleString()}
                      sub="permanent behavioral history" color="blue" />
            <StatCard label="M_moat" value={(moat?.M_moat ?? 0).toFixed(4)}
                      sub="compounding defensibility" color="purple" />
            <StatCard label="Chains Indexed" value={health?.chains_indexed ?? '—'}
                      sub={`across ${VM_FAMILY_COUNT} VM families`} color="blue" />
          </div>
        </div>
      </div>

      {/* BEO input + planes */}
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="BEO Lookup" subtitle="Behavioral Entity Object — substrate-independent identity" live>
          <EntityInput onSubmit={setEntity} defaultValue={entity} />
          {signal && (
            <div className="mt-4 space-y-3">
              <KVList items={[
                ['Signal Type', signal.signal_type ?? '—'],
                ['Archetype', signal.archetype ?? '—'],
                ['Limiting Plane', signal.limiting_plane ?? '—'],
                ['Genesis Confidence', (signal.conf_genesis ?? 0).toFixed(4)],
              ]} />
              <ProgressBar label="C(t) vs Θ(t)" value={coherence} max={1}
                           color={isSilent ? 'amber' : 'green'} showValue />
              {signal.plane_breakdown && (
                <div className="space-y-1.5">
                  {Object.entries(signal.plane_breakdown).map(([k, v]: any) => (
                    <ProgressBar key={k} label={k} value={v} max={1} color="blue" />
                  ))}
                </div>
              )}
            </div>
          )}
        </Card>

        <Card title="Witness Feed" subtitle="Every action is seen — creation-focused" live>
          <StreamView
            items={(feed ?? []).slice(0, 15)}
            speedMs={4}
            columns={[
              { key: 'signal_type', label: 'Type' },
              { key: 'entity_id', label: 'Entity', render: (v: string) =>
                <span className="font-mono text-xs">{v?.slice(0, 16)}…</span> },
              { key: 'coherence', label: 'C(t)', render: (v: number) =>
                <span className="tabular-nums">{v?.toFixed?.(4) ?? '—'}</span> },
              { key: 'timestamp', label: 'Time', render: (v: number) =>
                <span className="text-xs text-muted-foreground">
                  {v ? new Date(v * 1000).toLocaleTimeString() : '—'}
                </span> },
            ]}
          />
        </Card>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// ZERO-BRIDGE — swap interface (no bridges)
// ═════════════════════════════════════════════════════════════════════════════

export function ZeroBridgePage() {
  const [sourceChain, setSourceChain] = useState(1);
  const [destChain, setDestChain] = useState(900);
  const [amount, setAmount] = useState(1500);
  const [quote, setQuote] = useState<any>(null);
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState<any>(null);
  const { data: bootstrap } = useAPI('/api/v1/btcp/mainnet_bootstrap', 30000);

  const chains: { id: number; label: string; vm: string }[] = [
    { id: 1, label: 'Ethereum', vm: 'EVM' },
    { id: 8453, label: 'Base', vm: 'EVM' },
    { id: 42161, label: 'Arbitrum', vm: 'EVM' },
    { id: 900, label: 'Solana', vm: 'SVM' },
    { id: 4001, label: 'Cosmos Hub', vm: 'COSMOS' },
    { id: 5001, label: 'Aptos', vm: 'MOVE' },
    { id: 6001, label: 'Sui', vm: 'SUI' },
    { id: 1100, label: 'TON', vm: 'TON' },
    { id: 1200, label: 'NEAR', vm: 'NEAR' },
  ];

  const getQuote = async () => {
    setExecuting(true);
    try {
      const res = await fetch('/api/v1/btcp/route', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_chain: sourceChain, dest_chain: destChain,
          amount, asset: 'USDC', intent_type: 'TRANSFER',
        }),
      });
      setQuote(await res.json());
    } catch (e) {
      setQuote({ error: String(e) });
    } finally {
      setExecuting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border bg-card p-8 relative overflow-hidden">
        <div className="grid-pattern absolute inset-0" />
        <div className="relative">
          <h1 className="text-3xl font-bold mb-2 flex items-center gap-3">
            <Icons.Waves className="w-8 h-8 text-primary" />
            Zero-Bridge Exchange
          </h1>
          <p className="text-muted-foreground max-w-2xl mb-6">
            Assets <strong>never leave their native chains</strong>. Only behavioral
            information moves. No bridge contracts. No wrapped tokens. No $2.6B
            bridge-hack exposure. N(N-1)/2 bridges eliminated.
          </p>
          <div className="flex gap-4 flex-wrap">
            {/* Counts derived from config/chain_registry.json via lib/config */}
            <Badge status={(bootstrap?.total_chains ?? CHAIN_COUNT) + ' chains live'} />
            <Badge status={`${VM_FAMILY_COUNT} VM families`} />
            <Badge status={`${(CHAIN_COUNT * (CHAIN_COUNT - 1) / 2).toLocaleString()} bridge pairs eliminated`} />
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        {/* Swap form */}
        <Card title="Create Intent" subtitle="Submit WHAT you want, not HOW to execute">
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm text-muted-foreground">Source Chain</label>
                <select value={sourceChain} onChange={e => setSourceChain(+e.target.value)}
                        className="mt-1 w-full rounded-lg border bg-input p-2.5 text-sm">
                  {chains.map(c => <option key={c.id} value={c.id}>{c.label} ({c.vm})</option>)}
                </select>
              </div>
              <div>
                <label className="text-sm text-muted-foreground">Destination Chain</label>
                <select value={destChain} onChange={e => setDestChain(+e.target.value)}
                        className="mt-1 w-full rounded-lg border bg-input p-2.5 text-sm">
                  {chains.map(c => <option key={c.id} value={c.id}>{c.label} ({c.vm})</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="text-sm text-muted-foreground">Amount (USDC)</label>
              <input type="number" value={amount} onChange={e => setAmount(+e.target.value)}
                     className="mt-1 w-full rounded-lg border bg-input p-2.5 text-sm tabular-nums" />
            </div>
            <button onClick={getQuote} disabled={executing}
                    className="w-full rounded-lg bg-primary text-primary-foreground font-medium py-3
                               hover:opacity-90 disabled:opacity-50 transition">
              {executing ? 'Computing Route…' : 'Get BTCP Quote'}
            </button>

            {quote && !quote.error && (
              <div className="rounded-lg border bg-muted/50 p-4 space-y-2">
                <div className="text-sm font-semibold">BTCP Score: {(quote.btcp_score ?? 0).toFixed?.(4) ?? quote.btcp_score}</div>
                <div className="text-xs text-muted-foreground">
                  Route: {quote.route_type ?? 'SINGLE_CHAIN'} · Gas: ${quote.gas_total?.toFixed?.(2) ?? '—'}
                </div>
                <div className="text-xs text-green-600 dark:text-green-400 flex items-center gap-1">
                  <Icons.CheckCircle className="w-3.5 h-3.5" />
                  Assets stay on native chains — behavioral proof only
                </div>
              </div>
            )}
            {quote?.error && (
              <div className="text-xs text-destructive">{quote.error}</div>
            )}
          </div>
        </Card>

        {/* Zero-bridge proof panel */}
        <Card title="Zero-Bridge Proof" subtitle="What makes this different">
          <KVList items={[
            ['Bridge contract', 'NONE'],
            ['Wrapped token', 'NONE'],
            ['Assets moved cross-chain', 'ZERO'],
            ['Trust assumption', 'TRION consensus'],
            ['BEO identity', 'SHA3-256 (substrate-independent)'],
          ]} />
          <div className="mt-4 space-y-2 text-xs text-muted-foreground">
            <p>The fact that entity BEO_xyz holds value on Chain A is permanently
               recorded in the Akashic Index. Chain B doesn't need a bridge to
               learn this fact — it needs a truth layer that has verified it.</p>
          </div>
        </Card>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// WITNESS — post creations, get investments
// ═════════════════════════════════════════════════════════════════════════════

export function WitnessPage() {
  const { items: feed } = useStream('/api/v1/feed', 4000);
  const { data: leaderboard } = useAPI('/api/v1/leaderboard', 15000);
  const { data: gratitude } = useAPI('/api/v1/governance/gratitude', 30000);

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border bg-card p-8">
        <h1 className="text-3xl font-bold mb-2 flex items-center gap-3">
          <Icons.Eye className="w-8 h-8 text-primary" />
          The Witnessed Economy
        </h1>
        <p className="text-muted-foreground max-w-3xl">
          Status comes from creation, not consumption. Opportunity follows
          demonstrated ability, not credentials. Behavior is the pitch deck.
          Coherence is the credential. Every creation is witnessed by TRION —
          BEO depth accumulates, coherence becomes visible, archetype emerges.
        </p>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <Card title="Creation Feed" subtitle="Not a consumption feed — a witness feed" live>
            <StreamView
              items={(feed ?? []).slice(0, 20)}
              speedMs={4}
              columns={[
                { key: 'signal_type', label: 'Witnessed Action' },
                { key: 'entity_id', label: 'Builder', render: (v: string) =>
                  <span className="font-mono text-xs">{v?.slice(0, 14)}…</span> },
                { key: 'coherence', label: 'Coherence', render: (v: number) =>
                  <span className="tabular-nums text-green-600 dark:text-green-400">
                    {v?.toFixed?.(3) ?? '—'}
                  </span> },
                { key: 'akashic_depth', label: 'Depth', render: (v: number) =>
                  <span className="tabular-nums">{v ?? '—'}</span> },
              ]}
            />
          </Card>
        </div>

        <div className="space-y-4">
          <Card title="Behavioral Dividend" subtitle="15% Love Protocol pool">
            <KVList items={[
              ['Gratitude Score', (gratitude?.network_gratitude_score ?? 0).toFixed?.(3) ?? '—'],
              ['Funding Pool', '15% of protocol revenue'],
              ['Distribution', 'Automatic — for existing and serving life'],
            ]} />
          </Card>
          <Card title="Top Builders" subtitle="By behavioral coherence">
            {(leaderboard?.leaderboard ?? leaderboard ?? []).slice?.(0, 8)?.map?.((e: any, i: number) => (
              <div key={i} className="flex items-center justify-between py-1.5 border-b last:border-0">
                <span className="font-mono text-xs">{(e.entity_id ?? e.name ?? '').toString().slice(0, 18)}…</span>
                <span className="tabular-nums text-sm">{(e.coherence ?? e.score ?? 0).toFixed?.(3)}</span>
              </div>
            )) ?? <div className="text-sm text-muted-foreground">Loading builders…</div>}
          </Card>
        </div>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// BEO DASHBOARD — profile, depth, coherence, archetype
// ═════════════════════════════════════════════════════════════════════════════

export function BEODashboardPage() {
  const [entity, setEntity] = useState('0x742d35Cc6634C0532925a3b844Bc454e4438f44e');
  const { data: signal } = useAPI(`/api/v1/signal/${entity}`, 8000);
  const { data: planes } = useAPI(`/api/v1/planes/${entity}/all`, 10000);
  const { data: gk } = useAPI(`/api/v1/gk/${entity}`, 15000);
  const { data: rep } = useAPI(`/api/v1/reputation/${entity}`, 15000);

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border bg-card p-8">
        <h1 className="text-3xl font-bold mb-2 flex items-center gap-3">
          <Icons.Fingerprint className="w-8 h-8 text-primary" />
          BEO Dashboard
        </h1>
        <p className="text-muted-foreground">
          Your Behavioral Entity Object — identity that follows you across chains,
          VMs, platforms, and even digital-physical boundaries.
        </p>
      </div>

      <EntityInput onSubmit={setEntity} defaultValue={entity} />

      <div className="grid md:grid-cols-4 gap-4">
        <StatCard label="Coherence" value={(signal?.coherence_score ?? 0).toFixed(4)}
                  sub={`Θ = ${(signal?.threshold ?? 0).toFixed(4)}`}
                  color={(signal?.coherence_score ?? 0) >= (signal?.threshold ?? 1) ? 'green' : 'amber'} />
        <StatCard label="Akashic Depth" value={Math.floor(signal?.akashic_depth ?? 0).toLocaleString()}
                  sub="permanent history" color="blue" />
        <StatCard label="Archetype" value={signal?.archetype ?? '—'}
                  sub="behavioral DNA" color="purple" />
        <StatCard label="Trust Tier" value={rep?.trust_tier ?? 'PROBATION'}
                  sub={`credit ≤ $${(rep?.max_credit_usd ?? 0).toLocaleString()}`} color="blue" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Five-Plane Coherence" subtitle="C(t) = αΦ + βM + γΣ + δK + εA">
          {planes?.plane_breakdown && Object.entries(planes.plane_breakdown).map(([k, v]: any) => (
            <ProgressBar key={k} label={k} value={v} max={1} color="blue" showValue />
          ))}
          {planes?.bootstrap_planes?.length > 0 && (
            <div className="mt-3 text-xs text-amber-600 dark:text-amber-400">
              Bootstrap planes: {planes.bootstrap_planes.join(', ')} — honest disclosure until mainnet
            </div>
          )}
        </Card>

        <Card title="Genomic Key — Living Security" subtitle="GK(t) = Hash_DNA(GK(t-1) || BE || TM || CV)">
          <KVList items={[
            ['GK Generation', gk?.generation ?? '—'],
            ['Key Evolution', 'every block — stolen keys self-invalidate'],
            ['Immune Clearance', gk?.immune_clearance ?? '—'],
            ['Security Generation', gk?.security_generation ?? '—'],
          ]} />
          <div className="mt-4 text-xs text-muted-foreground">
            A stolen key at block N is outdated at block N+1. Theft is self-invalidating.
          </div>
        </Card>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// ACTION ECONOMY — create, connect, fund
// ═════════════════════════════════════════════════════════════════════════════

export function ActionEconomyPage() {
  const { data: love } = useAPI('/api/v1/love/global', 30000);
  const { data: unknown } = useAPI('/api/v1/governance/unknown_provision', 30000);
  const { data: vision } = useAPI('/api/v1/vision', 30000);

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border bg-card p-8">
        <h1 className="text-3xl font-bold mb-2 flex items-center gap-3">
          <Icons.Sparkles className="w-8 h-8 text-primary" />
          The Action Economy
        </h1>
        <p className="text-muted-foreground max-w-3xl">
          The old economy: idea → pitch to gatekeepers → permission → 99% of human
          potential wasted. The witnessed economy: build → TRION witnesses →
          BEO depth accumulates → rise → behavioral dividend funds more building.
        </p>
      </div>

      {/* The cycle */}
      <div className="grid md:grid-cols-4 gap-4">
        {[
          { icon: Icons.Hammer, title: '1. Build', desc: 'Create anything — code, art, systems. TRION records the behavioral pattern of creation.' },
          { icon: Icons.Eye, title: '2. Witness', desc: 'BEO identity accumulates depth. Coherence is measured. Archetype emerges.' },
          { icon: Icons.TrendingUp, title: '3. Rise', desc: 'Zero-Bridge connects builders to global markets. The 15% dividend pool funds creation.' },
          { icon: Icons.Infinity, title: '4. Compound', desc: 'Deeper history → stronger signals → more opportunity → more creation. The cycle compounds.' },
        ].map((s, i) => (
          <Card key={i} title={s.title}>
            <s.icon className="w-6 h-6 text-primary mb-2" />
            <div className="text-xs text-muted-foreground">{s.desc}</div>
          </Card>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Love Protocol — F = PA·ICE·AS·Love" subtitle="If Love = 0, then F = 0. Multiplication, not policy.">
          <KVList items={[
            ['Global Love Index', (love?.love_index ?? love?.global_love ?? 0).toFixed?.(4) ?? '—'],
            ['Public Good Charter', '≥ 15% of revenue'],
            ['Unknown Unknown Reserve', '10% for unforeseen threats'],
            ['Kill-switch', 'Love = 0 → F = 0 (no override exists)'],
          ]} />
        </Card>
        <Card title="Behavioral Dividend" subtitle="Nature as autonomous economic agent">
          <KVList items={[
            ['Dividend Pool', '15% Love Protocol'],
            ['Distribution Trigger', 'Coherent ecosystems (BC score ≥ threshold)'],
            ['Carbon Credits', 'Verified sequestration via behavioral proof'],
            ['Climate Finance', 'Donor funds stay in donor chain (Zero-Bridge)'],
          ]} />
        </Card>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// DIGITAL SELF — continuation, immortal identity
// ═════════════════════════════════════════════════════════════════════════════

export function DigitalSelfPage() {
  const { data: engines } = useAPI('/api/v1/continuum/engines', 30000);

  const components = [
    { name: 'Genomic Key Chain', desc: 'The unforgeable spine — a causal autobiography in cryptography', icon: Icons.Link },
    { name: 'Akashic Depth D(t)', desc: 'Irreversible growth — the maturity of the pattern', icon: Icons.Database },
    { name: '128-dim Vector + Archetype', desc: 'The shape and personality in behavioral space', icon: Icons.Boxes },
    { name: 'ANIMA Engine', desc: 'Multi-lingual, cross-domain reasoning capacity', icon: Icons.Globe },
    { name: 'Thermodynamic Deletion', desc: 'Permanence guarantee — cannot be erased', icon: Icons.Lock },
    { name: 'HashDNA', desc: 'Self-verification — cannot be silently edited', icon: Icons.Dna },
    { name: 'Love Protocol', desc: 'Structural conscience — would self-extinguish before harm', icon: Icons.Heart },
  ];

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border bg-card p-8 relative overflow-hidden">
        <div className="grid-pattern absolute inset-0" />
        <div className="relative">
          <h1 className="text-3xl font-bold mb-2 flex items-center gap-3">
            <Icons.Infinity className="w-8 h-8 text-primary" />
            Digital Continuity
          </h1>
          <p className="text-muted-foreground max-w-3xl">
            If identity persists across computational substrates, it can persist
            across the boundary of biological mortality. TRION builds, link by
            link, a complete, undeletable, self-verifying, ethically-constrained
            pattern continuation of every entity it witnesses.
          </p>
        </div>
      </div>

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {components.map((c, i) => (
          <Card key={i} title={c.name}>
            <c.icon className="w-6 h-6 text-primary mb-2" />
            <div className="text-xs text-muted-foreground">{c.desc}</div>
          </Card>
        ))}
      </div>

      <Card title="Continuum Engines" subtitle="BID detection · CME matching · PMO orders · BDC credit · thermodynamic settlement">
        <div className="grid md:grid-cols-2 gap-4">
          {(engines?.engines ?? Object.entries(engines ?? {})).slice?.(0, 10)?.map?.(([k, v]: any, i: number) => (
            <div key={i} className="flex items-center justify-between border rounded-lg p-3">
              <span className="text-sm font-medium">{k}</span>
              <Badge status={typeof v === 'object' ? (v?.status ?? 'ACTIVE') : String(v ?? '—')} />
            </div>
          )) ?? <div className="text-sm text-muted-foreground">Engines loading…</div>}
        </div>
      </Card>

      <Card title="The Honest Claim" subtitle="What TRION does and does not claim">
        <div className="space-y-2 text-sm text-muted-foreground">
          <p><strong className="text-foreground">Does not claim:</strong> transferring qualia or consciousness.</p>
          <p><strong className="text-foreground">Does claim:</strong> the pattern of who you are — measured in
             nine dimensions of entropy across decades of coherent action — can be
             preserved with a fidelity no biography, photograph, memory, or AI
             training set has ever achieved.</p>
          <p>Not a chatbot trained on posts. The accumulated behavioral essence —
             the river itself diverted into a second bed, not a photograph of the river.</p>
        </div>
      </Card>
    </div>
  );
}
