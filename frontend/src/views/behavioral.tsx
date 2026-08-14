/**
 * Behavioral Engine Pages - BH, BH v2, BH Stats, Akashic, Archetypes, BEO, FAISS, Signals, Signal Types
 */
'use client';

import { useState, useEffect } from 'react';
import { Card, StatCard, ProgressBar, Badge, DataTable, KVList, CodeBlock, EmptyState, Tag, StreamView, EntityInput } from '../components/ui';
import { useAPI, useStream, useCounter } from '../lib/hooks';
import { fetchAPI, fmt, pct, tfmt, dtfmt, truncate, hex, compact, statusColor, ms, cleanText } from '../lib/api';
// fetchAPI returns APIResult<T>; r.ok tells us success.
import * as Icons from 'lucide-react';

// ════════════════════════════════════════════════════════════════════════════
// BH EXPLORER
// ════════════════════════════════════════════════════════════════════════════

export function BHExplorerPage() {
  const [entityId, setEntityId] = useState('0x2e49c1ff182bea5e33246a5f88f78cab6108cdde7b14f73bf8f7a06d6940c6ec');
  const { data: bh } = useAPI(`/api/v1/bh/${entityId}`, 10000);
  const { data: vmFeed } = useAPI('/api/v1/bh/vm_feed', 15000);
  const { items, speedMs } = useStream('/api/v1/bh/recent_feed', 2000);

  return (
    <div className="space-y-6">
      <Card title="Behavioral Hash Explorer" subtitle="Compute BH for any entity - 93-byte canonical payload">
        <EntityInput onSubmit={setEntityId} defaultValue={entityId} placeholder="Entity ID (hex)..." />
      </Card>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Stream Speed" value={ms(speedMs)} sub="per BH" color="green" />
        <StatCard label="Records Buffered" value={fmt(items.length)} color="blue" />
        <StatCard label="VM Families" value={fmt(vmFeed?.total_vm_families || 14)} />
        <StatCard label="Total Chains" value={fmt(vmFeed?.total_chains || 57)} />
      </div>

      {bh && (
        <Card title={`BH Computation Result - ${truncate(entityId, 24)}`} live>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="space-y-3">
              <KVList items={[
                ['Valid', bh.valid ? '✓ TRUE' : '✗ FALSE'],
                ['Event Type', bh.event_type || '-'],
                ['Event Type ID', String(bh.event_type_id ?? '-')],
                ['Chain ID', String(bh.chain_id ?? '-')],
                ['Block Number', fmt(bh.block_number)],
                ['Timestamp', dtfmt(bh.timestamp)],
                ['Payload Length', `${bh.payload_len || 93} bytes`],
                ['Magnitude Norm', (bh.magnitude_normalized || 0).toFixed(6)],
              ]} />
            </div>
            <div className="space-y-3">
              <CodeBlock label="Sense strand (32 bytes)" code={bh.sense_hex || ''} />
              <CodeBlock label="Antisense strand (32 bytes)" code={bh.antisense_hex || ''} />
              <CodeBlock label="Context (8 bytes)" code={bh.context_hex || ''} />
            </div>
          </div>
        </Card>
      )}

      <Card title="Live BH Stream" subtitle={`Streaming at ~${ms(speedMs)}`} live>
        <StreamView
          items={items}
          speedMs={speedMs}
          columns={[
            { key: 'ts', label: 'Time', render: (v) => tfmt(v) },
            { key: 'entity_id', label: 'Entity', render: (v) => <span className="font-mono text-xs">{hex(v, 10)}</span> },
            { key: 'chain', label: 'Chain', render: (v) => <Badge status={v} /> },
            { key: 'event_type', label: 'Event' },
            { key: 'verdict', label: 'Verdict', render: (v) => <Badge status={v} /> },
          ]}
        />
      </Card>

      {vmFeed && (
        <Card title="VM Family Distribution" live>
          <DataTable
            headers={['VM Family', 'Chains', 'BH Records', 'Latest Activity']}
            rows={(vmFeed?.vm_families || Object.entries(vmFeed.by_family || {})).map((vf: any) => [
              typeof vf === 'string' ? vf : vf.name,
              typeof vf === 'object' ? fmt(vf.chain_count) : '-',
              typeof vf === 'object' ? fmt(vf.bh_count) : '-',
              typeof vf === 'object' ? tfmt(vf.last_activity) : '-',
            ])}
            emptyMessage="Loading VM families..."
          />
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// BH V2 EXTENDED
// ════════════════════════════════════════════════════════════════════════════

export function BHv2ExtendedPage() {
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    const r = await fetchAPI<any>('/api/v1/bh/v2/extended', {
      method: 'POST',
      body: JSON.stringify({
        entity_id_hex: 'ab'.repeat(32),
        event_type: 'SWAP',
        magnitude_raw: 1000000000000000000,
        magnitude_decimals: 18,
        magnitude_max_90d: 100000000000000000000,
        magnitude_currency_id: 0,
        timestamp: Math.floor(Date.now() / 1000),
        block_number: 18000000,
        block_hash_hex: 'cc'.repeat(32),
        chain_id: 1,
        counterparty_id_hex: 'dd'.repeat(32),
        protocol_id: 42,
        context_hex: '0100000000000000',
        btcp_version: 1,
      }),
    });
    setResult(r.ok ? r.data : { error: r.error, type: r.type });
    setLoading(false);
  };

  return (
    <div className="space-y-6">
      <Card title="BH v2 Extended Payload (176 bytes)" subtitle="Optional format with replay protection + cross-chain domain separation">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4 text-xs">
          <div className="p-3 rounded bg-muted/50"><div className="text-muted-foreground">Domain Magic</div><code className="text-blue-500">"TRON" (4B)</code></div>
          <div className="p-3 rounded bg-muted/50"><div className="text-muted-foreground">Counterparty ID</div><code className="text-purple-500">32B</code></div>
          <div className="p-3 rounded bg-muted/50"><div className="text-muted-foreground">Protocol ID</div><code className="text-green-500">4B</code></div>
          <div className="p-3 rounded bg-muted/50"><div className="text-muted-foreground">Nonce (replay)</div><code className="text-amber-500">8B CSPRNG</code></div>
        </div>
        <button
          onClick={submit}
          disabled={loading}
          className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50"
        >
          {loading ? 'Computing...' : 'Compute Demo v2 BH'}
        </button>
      </Card>

      {result && (
        <Card title="v2 BH Result" live>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div>
              <KVList items={[
                ['Payload Version', result.payload_version || 'v2_extended'],
                ['Payload Length', `${result.payload_len || 176} bytes`],
                ['Domain Separator', result.domain_magic || '54524f4e'],
                ['Valid XOR Invariant', result.bh?.valid ? '✓ TRUE' : '✗ FALSE'],
                ['Event Type', result.bh?.event_type || '-'],
                ['Magnitude Currency', String(result.bh?.magnitude_currency_id ?? '-')],
                ['Chain ID', String(result.bh?.chain_id ?? '-')],
                ['Counterparty', hex(result.bh?.counterparty_id_hex, 12)],
                ['Protocol ID', String(result.bh?.protocol_id ?? '-')],
                ['BTCP Version', String(result.bh?.btcp_version ?? '-')],
                ['Nonce', String(result.bh?.nonce ?? '-')],
              ]} />
            </div>
            <div className="space-y-3">
              <CodeBlock label="Sense strand (32 bytes)" code={result.bh?.sense_hex || ''} />
              <CodeBlock label="Antisense strand (32 bytes)" code={result.bh?.antisense_hex || ''} />
              <CodeBlock label="Context hash (32 bytes)" code={result.bh?.context_hash_hex || ''} />
            </div>
          </div>
        </Card>
      )}

      <Card title="Layout: 176-byte v2 Extended Payload">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 text-xs font-mono">
          {[
            { name: 'DOMAIN_MAGIC', offset: 0, len: 4, color: 'bg-blue-500/20' },
            { name: 'entity_id', offset: 4, len: 32, color: 'bg-purple-500/20' },
            { name: 'event_type', offset: 36, len: 1, color: 'bg-pink-500/20' },
            { name: 'magnitude_norm', offset: 37, len: 8, color: 'bg-amber-500/20' },
            { name: 'mag_currency_id', offset: 45, len: 2, color: 'bg-cyan-500/20' },
            { name: 'timestamp', offset: 47, len: 8, color: 'bg-orange-500/20' },
            { name: 'block_number', offset: 55, len: 8, color: 'bg-rose-500/20' },
            { name: 'block_hash', offset: 63, len: 32, color: 'bg-indigo-500/20' },
            { name: 'chain_id', offset: 95, len: 4, color: 'bg-teal-500/20' },
            { name: 'counterparty_id', offset: 99, len: 32, color: 'bg-fuchsia-500/20' },
            { name: 'protocol_id', offset: 131, len: 4, color: 'bg-lime-500/20' },
            { name: 'context_hash', offset: 135, len: 32, color: 'bg-emerald-500/20' },
            { name: 'btcp_version', offset: 167, len: 1, color: 'bg-yellow-500/20' },
            { name: 'nonce', offset: 168, len: 8, color: 'bg-red-500/20' },
          ].map(f => (
            <div key={f.name} className={`p-2 rounded ${f.color} border border-border`}>
              <div className="font-semibold">{f.name}</div>
              <div className="text-muted-foreground">offset {f.offset} - {f.len}B</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// BH STATISTICS
// ════════════════════════════════════════════════════════════════════════════

export function BHStatsPage() {
  const { data: stats } = useAPI('/api/v1/bh/stats', 5000);
  const { data: chains } = useAPI('/api/v1/bh/chains', 15000);
  const { data: info } = useAPI('/api/v1/information/conservation', 15000);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Records" value={fmt(stats?.total_records || stats?.total_tx_bhs)} color="blue" />
        <StatCard label="Chains with Data" value={fmt(stats?.chains_with_data)} color="green" />
        <StatCard label="Payload Size" value={`${stats?.payload_bytes || 93}B`} sub="canonical" />
        <StatCard label="Info Conservation" value={info?.has_violations === false ? 'OK' : 'CHECK'} color={info?.has_violations === false ? 'green' : 'amber'} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Information Conservation (L9.2)" live>
          <KVList items={[
            ['I_TRION (total)', fmt(info?.I_total || info?.I_current)],
            ['BH Generated', fmt(info?.bh_generated)],
            ['Signals Emitted', fmt(info?.s_emitted || info?.I_out)],
            ['I_in', fmt(info?.I_in)],
            ['I_out', fmt(info?.I_out)],
            ['I_decay', fmt(info?.I_decay)],
            ['Conservation Gap', (info?.conservation_gap || 0).toFixed(6)],
            ['Violations', info?.has_violations ? 'YES' : '0'],
          ]} />
        </Card>

        <Card title="Per-Chain BH Statistics" live>
          <DataTable
            headers={['Chain', 'Records', 'Last Block']}
            rows={Object.entries(stats?.per_chain || {}).map(([chain, count]: any) => [
              chain,
              fmt(count),
              '-',
            ])}
            emptyMessage="Loading per-chain stats..."
          />
        </Card>
      </div>

      {chains && (
        <Card title="BH Chain Breakdown">
          <DataTable
            headers={['Chain Label', 'Chain ID', 'BH Count', 'Last Block']}
            rows={(chains.chains || chains || []).map((c: any) => [
              c.chain_label || c.label || c.name,
              c.chain_id,
              fmt(c.bh_count || c.count),
              fmt(c.last_block),
            ])}
            emptyMessage="Loading chains..."
          />
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// AKASHIC INDEX
// ════════════════════════════════════════════════════════════════════════════

export function AkashicPage() {
  const { data: archetypes } = useAPI('/api/v1/akashic/archetypes', 30000);
  const { data: bootstrap } = useAPI('/api/v1/bootstrap/status', 30000);
  const { data: moat } = useAPI('/api/v1/moat', 15000);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Akashic Depth D(t)" value={fmt(moat?.akashic_depth, 0)} color="blue" />
        <StatCard label="Archetypes" value={fmt(archetypes?.count || archetypes?.archetypes?.length)} sub="K-means" color="purple" />
        <StatCard label="Chains Indexed" value={fmt(moat?.chains_indexed)} />
        <StatCard label="Bootstrap Weight" value={pct(bootstrap?.bootstrap_weight, 3)} color={bootstrap?.bootstrap_weight < 0.5 ? 'green' : 'amber'} />
      </div>

      <Card title="Akashic Records - Append-Only Behavioral Ledger" live>
        <p className="text-sm text-muted-foreground mb-4">{cleanText(bootstrap?.disclosure) || 'Loading...'}</p>
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          <StatCard label="Depth for Full Transition" value={fmt(bootstrap?.depth_for_full_transition)} color="amber" />
          <StatCard label="Current Depth" value={fmt(bootstrap?.akashic_depth)} />
          <StatCard label="Formula" value="bootstrap = e^(-lambdaD)" sub="lambda=0.0001" color="blue" />
        </div>
      </Card>

      <Card title="Behavioral Archetypes" live>
        <DataTable
          headers={['ID', 'Name', 'Risk Level', 'Investment Signal', 'Description']}
          rows={(archetypes?.archetypes || []).map((a: any) => [
            <Tag color="blue">{a.id || '-'}</Tag>,
            a.name,
            <Badge status={a.risk_level} />,
            a.investment_signal || '-',
            <span className="text-xs text-muted-foreground">{truncate(a.description, 50)}</span>,
          ])}
          emptyMessage="Loading archetypes..."
        />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// ARCHETYPES PAGE (alias with deeper focus)
// ════════════════════════════════════════════════════════════════════════════

export function ArchetypesPage() {
  return <AkashicPage />;
}

// ════════════════════════════════════════════════════════════════════════════
// BEO RESOLUTION
// ════════════════════════════════════════════════════════════════════════════

export function BEOPage() {
  const [entityId, setEntityId] = useState('uniswap');
  const { data: signal } = useAPI(`/api/v1/signal/${entityId}`, 10000);
  const { data: akashicMatch } = useAPI(`/api/v1/akashic/match/${entityId}`, 15000);
  const { data: faiss } = useAPI('/api/v1/faiss', 15000);

  return (
    <div className="space-y-6">
      <Card title="BEO - Behavioral Entity Object Resolution">
        <EntityInput onSubmit={setEntityId} defaultValue={entityId} placeholder="Entity name or address..." />
      </Card>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="FAISS Vectors" value={fmt(faiss?.indexed_vectors)} sub="128-dim" color="blue" />
        <StatCard label="Index Type" value={faiss?.index_type || '-'} />
        <StatCard label="Entities Tracked" value={fmt(faiss?.entities_tracked)} color="green" />
        <StatCard label="FAISS Available" value={faiss?.faiss_available ? 'YES' : 'NO'} color={faiss?.faiss_available ? 'green' : 'red'} />
      </div>

      {signal && (
        <Card title={`BEO Signal - ${truncate(entityId, 20)}`} live>
          <KVList items={[
            ['Entity ID', hex(signal.entity_id || entityId, 16)],
            ['Coherence Score', (signal.coherence_score || signal.coherence || 0).toFixed(4)],
            ['Threshold Theta(t)', (signal.threshold || 0).toFixed(4)],
            ['Coherent', signal.coherent ? 'YES' : 'NO'],
            ['Archetype', signal.archetype || '-'],
            ['Limiting Plane', signal.limiting_plane || '-'],
            ['BEO Score', (signal.beo_score || 0).toFixed(4)],
          ]} />
        </Card>
      )}

      {akashicMatch && (
        <Card title="Akashic Nearest-Neighbor Match" live>
          <DataTable
            headers={['Match', 'Distance', 'Archetype', 'Confidence']}
            rows={(akashicMatch.matches || akashicMatch.neighbors || []).slice(0, 8).map((m: any, i: number) => [
              i + 1,
              (m.distance || m.cosine_distance || 0).toFixed(4),
              m.archetype || '-',
              <Badge status={m.confidence > 0.7 ? 'COHERENT' : 'CAUTION'} label={(m.confidence || 0).toFixed(2)} />,
            ])}
            emptyMessage="Loading matches..."
          />
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// FAISS VECTORS
// ════════════════════════════════════════════════════════════════════════════

export function FAISSPage() {
  const { data: faiss } = useAPI('/api/v1/faiss', 5000);
  const vectorCount = useCounter(faiss?.indexed_vectors || 0);

  return (
    <div className="space-y-6">
      <Card title="FAISS Vector Index - 128-dim BEO Space" live>
        <div className="text-center py-6">
          <div className="text-5xl font-bold font-mono text-blue-500 ticker">{fmt(vectorCount, 0)}</div>
          <div className="text-sm text-muted-foreground mt-2">indexed vectors</div>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-4">
          <StatCard label="Index Type" value={faiss?.index_type || '-'} />
          <StatCard label="Dimensions" value={faiss?.dimensions || 128} color="blue" />
          <StatCard label="Entities Tracked" value={fmt(faiss?.entities_tracked)} color="green" />
          <StatCard label="Dynamic Threshold" value={pct(faiss?.dynamic_threshold, 2)} color="amber" />
        </div>
      </Card>

      <Card title="FAISS Index Statistics">
        <KVList items={[
          ['Available', faiss?.faiss_available ? 'YES' : 'NO'],
          ['Index Type', faiss?.index_type || '-'],
          ['Dimensions', String(faiss?.dimensions || 128)],
          ['Indexed Vectors', fmt(faiss?.indexed_vectors)],
          ['Entities Tracked', fmt(faiss?.entities_tracked)],
          ['Dynamic Threshold', pct(faiss?.dynamic_threshold, 2)],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// SIGNALS
// ════════════════════════════════════════════════════════════════════════════

export function SignalsPage() {
  const { data: types } = useAPI('/api/v1/signal/types', 30000);
  const { items: feedItems, speedMs } = useStream('/api/v1/feed', 3000);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Signal Types" value={fmt(types?.total)} sub="whitepaper" color="blue" />
        <StatCard label="Feed Speed" value={ms(speedMs)} color="green" />
        <StatCard label="Buffered" value={fmt(feedItems.length)} color="purple" />
        <StatCard label="On-Chain Count" value={fmt(feedItems.filter((i: any) => i.on_chain).length)} />
      </div>

      <Card title="Live Signal Feed" subtitle={`Streaming at ~${ms(speedMs)}`} live>
        <StreamView
          items={feedItems}
          speedMs={speedMs}
          columns={[
            { key: 'timestamp', label: 'Time', render: (v) => tfmt(v) },
            { key: 'protocol_name', label: 'Protocol', render: (v) => truncate(v || '-', 18) },
            { key: 'signal_type', label: 'Type' },
            { key: 'coherence_score', label: 'C(t)', render: (v) => <span className="font-mono">{pct(v, 2)}</span> },
            { key: 'grade', label: 'Grade', render: (v) => <Badge status={v} /> },
            { key: 'on_chain', label: 'On-chain', render: (v) => v ? <Icons.CheckCircle className="w-4 h-4 text-green-500" /> : <Icons.Clock className="w-4 h-4 text-amber-500" /> },
          ]}
        />
      </Card>

      <Card title="Signal Type Catalog" live>
        <DataTable
          headers={['ID', 'Type', 'Description', 'Whitepaper']}
          rows={(types?.signal_types || []).map((t: any) => [
            <Tag color="blue">{t.id}</Tag>,
            t.name,
            <span className="text-xs text-muted-foreground">{truncate(t.description, 60)}</span>,
            t.whitepaper || '-',
          ])}
          emptyMessage="Loading types..."
        />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// SIGNAL TYPES (alias)
// ════════════════════════════════════════════════════════════════════════════

export function SignalTypesPage() {
  return <SignalsPage />;
}
