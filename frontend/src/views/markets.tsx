/**
 * Markets Pages — BTCP, BIBL, BITP, SBA, Continuum, Price, Inverted, Liquidity, Stablecoin, Hierarchy
 */
'use client';

import { useState } from 'react';
import { Card, StatCard, ProgressBar, Badge, DataTable, KVList, EmptyState, Tag } from '../components/ui';
import { useAPI } from '../lib/hooks';
import { fetchAPI, fmt, pct, tfmt, dtfmt, truncate, hex, compact, statusColor } from '../lib/api';

const DEFAULT_ENTITY = '0x2e49c1ff182bea5e33246a5f88f78cab6108cdde7b14f73bf8f7a06d6940c6ec';
const DEFAULT_ASSET = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48';

// ════════════════════════════════════════════════════════════════════════════
// BTCP ROUTING
// ════════════════════════════════════════════════════════════════════════════

export function BTCPPage() {
  return (
    <div className="space-y-6">
      <Card title="BTCP — Behavioral Transaction Continuity Protocol">
        <p className="text-sm text-muted-foreground mb-4">
          BTCP = [0.25·NL + 0.20·GasNorm + 0.20·Finality + 0.15·CC + 0.20·BEO] × (1 − MF)
        </p>
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          {[
            { name: 'NL', weight: '25%', desc: 'Nonce Linearity' },
            { name: 'GasNorm', weight: '20%', desc: 'Gas normalization' },
            { name: 'Finality', weight: '20%', desc: 'Block finality' },
            { name: 'CC', weight: '15%', desc: 'Cross-chain coherence' },
            { name: 'BEO', weight: '20%', desc: 'Entity score' },
          ].map(c => (
            <div key={c.name} className="p-3 rounded-lg border border-border bg-card text-center">
              <div className="text-2xl font-bold">{c.name}</div>
              <div className="text-xs text-muted-foreground">{c.weight}</div>
              <div className="text-xs mt-1">{c.desc}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="BTCP Routes Published" live>
        <DataTable
          headers={['Route ID', 'Entity', 'Score', 'Status']}
          rows={[]}
          emptyMessage="Connect BTCPRoute contract to view published routes"
        />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// BIBL PATTERNS
// ════════════════════════════════════════════════════════════════════════════

export function BIBLPage() {
  return (
    <div className="space-y-6">
      <Card title="BIBL — Inter-Block Behavioral Intelligence (12-second window)">
        <p className="text-sm text-muted-foreground">
          BIBL monitors mempool activity in the 12-second inter-block window. Pattern detection
          identifies behavioral anomalies before block confirmation.
        </p>
      </Card>
      <Card title="BIBL Pattern Store">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {['FRONTRUN', 'BACKRUN', 'SANDWICH', 'ARBITRAGE', 'LIQUIDATION', 'JIT_LP', 'SNIPE', 'REBATE'].map(p => (
            <div key={p} className="p-3 rounded-lg border border-border bg-card text-center">
              <div className="text-sm font-mono">{p}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// BITP EXCHANGE
// ════════════════════════════════════════════════════════════════════════════

export function BITPPage() {
  return (
    <div className="space-y-6">
      <Card title="BITP — Behavioral Inverse Transaction Price">
        <p className="text-sm text-muted-foreground">
          BITP inverts the price-formation process: rather than spot price, it derives price from
          behavioral coherence and inverse transaction patterns.
        </p>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// SBA SOVEREIGN
// ════════════════════════════════════════════════════════════════════════════

export function SBAPage() {
  const [nationId, setNationId] = useState('NG');
  const { data: sba } = useAPI(`/api/v1/sba/${nationId}`, 15000);

  return (
    <div className="space-y-6">
      <Card title="SBA — Sovereign Behavioral Analysis">
        <input
          type="text"
          value={nationId}
          onChange={e => setNationId(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-border bg-input text-sm font-mono"
        />
      </Card>
      {sba && (
        <Card title={`SBA — ${nationId}`} live>
          <KVList items={[
            ['Divergence score', (sba.divergence || 0).toFixed(4)],
            ['Sovereign baseline', (sba.baseline || 0).toFixed(4)],
            ['Current behavior', (sba.current || 0).toFixed(4)],
            ['Anomaly flag', sba.anomaly ? 'YES' : 'NO'],
          ]} />
        </Card>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// CONTINUUM DEX
// ════════════════════════════════════════════════════════════════════════════

export function ContinuumPage() {
  return (
    <div className="space-y-6">
      <Card title="Continuum DEX — Behavioral Coherence-Gated Trading">
        <p className="text-sm text-muted-foreground">
          Continuum is a DEX where trade execution is gated by behavioral coherence.
          Trades from low-coherence entities are blocked at the contract level.
        </p>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PRICE FEEDS
// ════════════════════════════════════════════════════════════════════════════

export function PricePage() {
  const { data: pairs } = useAPI('/api/v1/price/pairs', 30000);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Pairs" value={fmt(pairs?.total_pairs)} color="blue" />
        <StatCard label="With Inverse" value={fmt(pairs?.total_with_inverse)} color="green" />
        <StatCard label="Decimals" value={pairs?.decimals || 8} />
        <StatCard label="Status" value={pairs?.status || '—'} color="green" />
      </div>

      <Card title="Price Pairs" live>
        <DataTable
          headers={['Base', 'Quote', 'Price', 'Source']}
          rows={(pairs?.pairs || []).slice(0, 30).map((p: any) => [
            p.base, p.quote,
            <span className="font-mono">{p.price?.toFixed(6) || '—'}</span>,
            p.source || '—',
          ])}
          emptyMessage="Loading pairs…"
        />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// INVERTED PRICE
// ════════════════════════════════════════════════════════════════════════════

export function InvertedPricePage() {
  const { data: inv } = useAPI('/api/v1/inverted_price_feed', 15000);

  return (
    <div className="space-y-6">
      <Card title="Inverted Price Feed — C_manipulate Burden of Proof" live>
        <KVList items={[
          ['Asset', inv?.asset || '—'],
          ['C_manipulate (cost)', fmt(inv?.c_manipulate)],
          ['Divergence', (inv?.divergence || 0).toFixed(4)],
          ['Burden of proof', inv?.burden_of_proof || '—'],
          ['Documented failures', fmt(inv?.documented_oracle_failures?.length)],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// LIQUIDITY
// ════════════════════════════════════════════════════════════════════════════

export function LiquidityPage() {
  const [asset, setAsset] = useState(DEFAULT_ASSET);
  const { data: liq } = useAPI(`/api/v1/liquidity/${asset}`, 15000);

  return (
    <div className="space-y-6">
      <Card title="Asset Selector">
        <input
          type="text"
          value={asset}
          onChange={e => setAsset(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-border bg-input text-sm font-mono"
        />
      </Card>
      <Card title="Liquidity Analysis" live>
        <KVList items={[
          ['Total liquidity', fmt(liq?.total_liquidity)],
          ['Depth (1% slip)', fmt(liq?.depth_1pct)],
          ['Depth (5% slip)', fmt(liq?.depth_5pct)],
          ['Liquidity health', liq?.health || '—'],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// STABLECOIN HEALTH
// ════════════════════════════════════════════════════════════════════════════

export function StablecoinHealthPage() {
  const [asset, setAsset] = useState('USDC');
  const { data: health } = useAPI(`/api/v1/stablecoin_health/${asset}`, 15000);

  return (
    <div className="space-y-6">
      <Card title="Stablecoin Selector">
        <input
          type="text"
          value={asset}
          onChange={e => setAsset(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-border bg-input text-sm font-mono"
        />
      </Card>
      <Card title={`${asset} Health`} live>
        <KVList items={[
          ['Peg stability', (health?.peg_stability || 0).toFixed(4)],
          ['Depeg events (30d)', fmt(health?.depeg_events_30d)],
          ['Reserve ratio', pct(health?.reserve_ratio, 2)],
          ['Health grade', health?.grade || '—'],
        ]} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PRICE HIERARCHY
// ════════════════════════════════════════════════════════════════════════════

export function PriceHierarchyPage() {
  const { data: hier } = useAPI('/api/v1/price/hierarchy', 30000);

  return (
    <div className="space-y-6">
      <Card title="Inverted Truth Hierarchy" live>
        <p className="text-sm text-muted-foreground mb-4">{hier?.summary || 'Loading…'}</p>
        <DataTable
          headers={['Asset', 'Tier', 'Inverse Available', 'Confidence']}
          rows={(hier?.assets || []).map((a: any) => [
            a.name, a.tier, a.inverse ? 'YES' : 'NO', (a.confidence || 0).toFixed(4),
          ])}
          emptyMessage="Loading hierarchy…"
        />
      </Card>
    </div>
  );
}
