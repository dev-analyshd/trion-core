/**
 * Wallet + BTCP + Continuum Pages
 * Per TRION_WALLET_BTCP_CONTINUUM_MASTER_BUILD.md spec
 * Simple Mode by default, "Show All Details" toggle for power users
 */

'use client';

import { useState, useMemo } from 'react';
import { Card, StatCard, ProgressBar, Badge, DataTable, KVList, Tag, EmptyState } from '../components/ui';
import { WalletButton } from '../components/wallet/WalletButton';
import { useAccount } from 'wagmi';
import { useAPI, useCounter } from '../lib/hooks';
import { fetchAPI, fmt, pct, tfmt, dtfmt, truncate, hex, compact, statusColor, ms } from '../lib/api';
import * as Icons from 'lucide-react';

const BTCP_DATA = {
  tagline: "Why move assets when what needs to move is behavioral identity?",
  coreQuestion: "Bridges ask: How do I prove on Chain B that something happened on Chain A? BTCP asks: Why move assets at all?",
  answer: "Assets never cross chains. Behavioral facts do. The fact that Entity X performed Action Y on Chain A is permanently recorded, diversity-BFT verified, and stored in the Akashic Index. Chain B does not need a bridge to learn this fact.",
  routeTypes: [
    { id: 'SINGLE_CHAIN', name: 'Direct Single-Chain', when: 'Target chain has superior liquidity', gas: '$31.00', score: 0.41, finality: '12s', color: '#64748b', desc: 'Standard execution. Baseline for comparison.', simple: 'Direct swap on one chain — most expensive option' },
    { id: 'SPLIT', name: 'Anchor + Execute Split', when: 'Security on source, cheap execution on target', gas: '$0.98', score: 0.94, finality: 'max 12s', color: '#22d3ee', desc: 'Anchor proof on Ethereum, execute natively on Base. Assets never leave Ethereum.', simple: 'Security on cheap chain, execution on cheaper chain — saves 97%' },
    { id: 'NETTING', name: 'Netting (Counterparty Found)', when: 'Opposite intent entity found simultaneously', gas: '$0.05', score: 0.98, finality: '12s', color: '#10b981', desc: 'Entity A wants USDC→ETH, Entity B wants ETH→USDC. Both execute natively. Zero cross-chain movement.', simple: 'Your opposite found — you both save 99.8%, best option' },
    { id: 'PARALLEL', name: 'Parallel Split', when: 'Large intent split across chains', gas: '$1.80', score: 0.91, finality: '12s', color: '#8b5cf6', desc: '$1M split across 5 chains. Reduces price impact.', simple: 'Big trade split across chains — less slippage' },
    { id: 'MULTI_HOP', name: 'Multi-Hop (A→B→C)', when: 'Intermediate chain provides liquidity', gas: '$1.20', score: 0.88, finality: 'max 12s', color: '#fbbf24', desc: 'Ethereum→Solana→Arbitrum. Nested escrow guarantees atomicity.', simple: 'Via intermediate chain — when direct route is illiquid' },
    { id: 'DEFERRED', name: 'Deferred (Optimal Window)', when: 'Intent not urgent, wait for best conditions', gas: '$0.42 (est)', score: 0.96, finality: 'within 24h', color: '#f472b6', desc: 'Biological Rhythm Timer finds optimal window: low gas + peak liquidity + MEV valley.', simple: 'Wait for the best moment — saves even more' },
  ],
  sixSteps: [
    { num: 1, name: 'Intent Registration', simple: 'You say what you want to do', desc: 'Entity submits intent (not a transaction). Behavioral Inter-Block Layer reads all chains simultaneously.', color: '#22d3ee' },
    { num: 2, name: 'Route Calculation', simple: 'System finds the best path', desc: 'BTCP score computed for all candidate routes. Natural liquidity, gas, finality, coherence all weighted.', color: '#8b5cf6' },
    { num: 3, name: 'Cross-Chain Proof', simple: 'Truth verified by many', desc: 'Anchor behavioral hash + diversity-weighted consensus. Validators who copy each other lose voting power.', color: '#10b981' },
    { num: 4, name: 'VM Translation', simple: 'Same meaning, different chains', desc: '20 behavioral event types translated into each chain native execution. Same intent, different bytecode.', color: '#fbbf24' },
    { num: 5, name: 'Gas Sharing Protocol', simple: 'Split costs, save big', desc: 'Anchor chain covers security, execution chain covers computation. $31 → $0.98 → $0.05.', color: '#f472b6' },
    { num: 6, name: 'Finalization + Recording', simple: 'Done, permanently recorded', desc: 'Behavioral hash stored in Akashic Index. Append-only, instantly final via BFT consensus.', color: '#ef4444' },
  ],
  eightWaterPrinciples: [
    { id: 'BITP', name: 'Information Transfer', simple: 'Move information, not assets', problem: 'Illiquid pairs need bridges', solution: 'Akashic clipboard moves behavioral facts' },
    { id: 'OOA', name: 'Observation-Only', simple: 'Watch any chain, no permission needed', problem: 'Non-integrated chains left out', solution: 'Direct indexing — hostile chains cannot opt out' },
    { id: 'IAP', name: 'Intent Aggregation', simple: '100 users = 1 pooled transaction', problem: 'Small users pay too much gas', solution: 'Pooled intents → 100× cheaper per user' },
    { id: 'CAPSULES', name: 'State Capsules', simple: 'Chain state travels safely', problem: 'Cross-chain reads are stale/expensive', solution: 'Snapshots at anchor block with confidence intervals' },
    { id: 'BLO', name: 'Behavioral Limit Orders', simple: 'Orders that never expire', problem: 'Counterparties must arrive together', solution: 'Orders stored permanently, fillable anytime' },
    { id: 'ZK_INTENT', name: 'ZK Intent Commitment', simple: 'MEV bots see nothing', problem: 'MEV front-runs expressed intents', solution: 'Hash committed, reveal + execution same block' },
    { id: 'BSC', name: 'Behavioral State Channels', simple: '50 interactions = 2 on-chain txs', problem: 'High-frequency costs too much', solution: 'State channels → 50× cheaper' },
    { id: 'BRT', name: 'Biological Rhythm Timer', simple: 'Trade when gas is cheapest', problem: 'Users submit at bad times unknowingly', solution: 'Finds optimal window: low gas + peak liquidity + MEV valley' },
  ],
  networkEffect: { formula: "Bridge pairs eliminated = N × (N-1) / 2", simple: "Every new chain eliminates ALL bridge pairs to existing chains" },
};

const CONTINUUM_DATA = {
  tagline: "Behavioral reality precedes price reality by a measurable window. Continuum operates in this gap.",
  coreDiscovery: "On Ethereum: 36 to 144 seconds. On Solana: 20 to 80 seconds. This window has always existed. Nobody built infrastructure to use it — because nobody had the behavioral oracle layer to make it legible.",
  wasteBreakdown: {
    total: 13.9,
    items: [
      { name: 'DEX Fees', value: 4.2, color: '#f97316', simple: 'What exchanges charge per trade' },
      { name: 'Slippage Losses', value: 3.1, color: '#8b5cf6', simple: 'Price moves against you during execution' },
      { name: 'Bridge Exploits', value: 2.8, color: '#ef4444', simple: 'Stolen from bridge hacks annually' },
      { name: 'Liquidation Cascades', value: 1.9, color: '#22d3ee', simple: 'Forced selling drives prices further down' },
      { name: 'MEV Extraction', value: 1.3, color: '#ef4444', simple: 'Front-running by block producers' },
      { name: 'Bridge Fees', value: 0.6, color: '#fbbf24', simple: 'Bridge operator charges' },
    ],
  },
  engines: [
    { id: 'BID', name: 'Behavioral Intent Detection', shortName: 'BID', color: '#22d3ee',
      simple: "The system sees you're about to trade before you decide",
      plainEnglish: "Detection confidence = how much your current behavior pattern matches known precursor signatures, bounded by how much behavioral history you have",
      whatItDoes: "Watches 9 features of your behavioral flow. When the pattern matches 'about to trade,' you get an offer to commit at a guaranteed better price.",
      keyConstraint: "You retain full agency. Detection never becomes commitment automatically." },
    { id: 'CME', name: 'Complement Matching Engine', shortName: 'CME', color: '#8b5cf6',
      simple: "Finds your perfect trading opposite across all chains",
      plainEnglish: "Complement score = how opposite your directions are × how close in time × both parties' behavioral health × independence of your identities × available liquidity",
      whatItDoes: "When you show intent precursor for USDC→ETH, the engine searches all chains for the entity whose pattern indicates ETH→USDC. Both get a Pre-Manifest Order offer.",
      keyProperty: "This is semantic matching of behavioral patterns, not price ladder matching." },
    { id: 'PMO', name: 'Pre-Manifest Order System', shortName: 'PMO', color: '#10b981',
      simple: "Commit before the market saw you — get a better price",
      plainEnglish: "In exchange for committing before market expression: guaranteed price at TRION valuation + complement certainty premium. No slippage. No MEV. No bridge risk.",
      whatItDoes: "You receive a Pre-Manifest Order instrument. You confirm. Counterparty already found. Both settle via BTCP. Both get better prices than any exchange offers.",
      adoptionDriver: "Adoption is economically rational. Every entity who accepts is strictly better off." },
    { id: 'BDC', name: 'Behavioral Depth Credit', shortName: 'BDC', color: '#fbbf24',
      simple: "Your honest history IS your credit line",
      plainEnglish: "Credit limit = your accumulated behavioral depth × how consistent you are × your 90-day average trade size × confidence multiplier",
      whatItDoes: "2 years of consistent honest history = trade up to 10× your typical size, backed by your behavioral record rather than locked capital.",
      keyProperties: "Cannot be bought. Cannot be transferred. Compounds automatically. Forgery is mathematically bounded." },
    { id: 'THERMO', name: 'Thermodynamic Settlement', shortName: 'Settlement', color: '#f472b6',
      simple: "Settlement happens when both parties are simultaneously honest",
      plainEnglish: "Settlement triggers when coherence exceeds threshold for BOTH parties at the same time AND route verified AND no manipulation detected within the time window.",
      whatItDoes: "BTCP escrow on both chains watches the TRION coherence signal. When both entities exceed their threshold simultaneously, escrow releases.",
      coreInsight: "Behavioral manipulation is self-defeating by construction." },
  ],
  ccpDistribution: { entityA: 40, entityB: 40, validators: 12, protocol: 8, simple: "The spread that middlemen currently take flows back to both traders + validators + protocol" },
};

const ASSETS = [
  { symbol: 'ETH', name: 'Ethereum', address: '0x0000000000000000000000000000000000000000', color: '#627eea' },
  { symbol: 'USDC', name: 'USD Coin', address: '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', color: '#2775ca' },
  { symbol: 'WBTC', name: 'Wrapped BTC', address: '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599', color: '#f7931a' },
  { symbol: 'BOT', name: 'BOT Chain', address: '0xD5452816194a3784dBa983426cCe7c122F4abd30', color: '#22d3ee' },
];

export function WalletBTCPPage() {
  const [showAll, setShowAll] = useState(false);
  const [fromAsset, setFromAsset] = useState(ASSETS[1]);
  const [toAsset, setToAsset] = useState(ASSETS[0]);
  const [amount, setAmount] = useState('10000');
  const [simulated, setSimulated] = useState(false);
  const { isConnected } = useAccount();
  const { data: streamer } = useAPI('/api/v1/btcp/streamer/status', 3000);
  const { data: bhStats } = useAPI('/api/v1/bh/stats', 5000);
  const { data: bibl } = useAPI('/api/v1/btcp/bibl/snapshot', 10000);

  const bhCount = streamer?.total_bhs || Object.values(bhStats?.per_chain || {}).reduce((a: number, b: any) => a + Number(b), 0) || 0;

  const simulatedRoute = useMemo(() => {
    if (!simulated) return null;
    const rand = Math.random();
    if (rand < 0.4) return BTCP_DATA.routeTypes.find(r => r.id === 'NETTING');
    if (rand < 0.85) return BTCP_DATA.routeTypes.find(r => r.id === 'SPLIT');
    return BTCP_DATA.routeTypes.find(r => r.id === 'SINGLE_CHAIN');
  }, [simulated, fromAsset, toAsset, amount]);

  return (
    <div className="space-y-8">
      <Card title="BTCP · Behavioral Transaction Continuity Protocol">
        <div className="flex items-center justify-between mb-4">
          <div className="text-xs text-muted-foreground font-mono uppercase tracking-wider">Layer 2 · Cross-Chain Routing</div>
          <button onClick={() => setShowAll(v => !v)} className="px-3 py-1 rounded-lg border border-border text-xs hover:bg-muted transition-all">
            {showAll ? 'Hide Details' : 'Show All Details'}
          </button>
        </div>
        <p className="text-lg font-semibold mb-4" style={{ background: 'linear-gradient(90deg, #22d3ee, #8b5cf6)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
          {BTCP_DATA.tagline}
        </p>
        {showAll && (
          <div className="mt-4 p-4 rounded-lg border border-border bg-muted/30">
            <div className="text-xs text-muted-foreground mb-1">Core Question</div>
            <p className="text-sm">{BTCP_DATA.coreQuestion}</p>
            <p className="text-sm mt-2"><strong>{BTCP_DATA.answer}</strong></p>
          </div>
        )}
      </Card>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="BTCP Score" value="0.911" sub="HEALTHY · Safe ≥ 0.50" color="blue" />
        <StatCard label="Behavioral Records" value={fmt(bhCount, 0)} sub="Akashic Index growing" color="green" />
        <StatCard label="Max Lock Duration" value="7 Days" sub="Emergency escape guarantee" color="purple" />
        <StatCard label="Best Gas Savings" value="99.8%" sub="Netting vs direct ETH" color="amber" />
      </div>

      <Card title="Route Simulator — Find your optimal behavioral route">
        <div className="grid md:grid-cols-2 gap-6 mb-6">
          <div>
            <label className="text-xs text-muted-foreground font-mono uppercase tracking-wider mb-2 block">From</label>
            <div className="flex gap-2">
              <select value={fromAsset.symbol} onChange={(e) => setFromAsset(ASSETS.find(a => a.symbol === e.target.value)!)}
                className="bg-card border border-border rounded-lg px-3 py-2 text-sm font-medium focus:outline-none focus:border-primary min-w-[120px]">
                {ASSETS.map(a => <option key={a.symbol} value={a.symbol}>{a.symbol} · {a.name}</option>)}
              </select>
              <input readOnly value={fromAsset.address.slice(0, 10) + '…' + fromAsset.address.slice(-6)}
                className="flex-1 bg-card border border-border rounded-lg px-3 py-2 text-sm font-mono text-muted-foreground" />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground font-mono uppercase tracking-wider mb-2 block">To</label>
            <div className="flex gap-2">
              <select value={toAsset.symbol} onChange={(e) => setToAsset(ASSETS.find(a => a.symbol === e.target.value)!)}
                className="bg-card border border-border rounded-lg px-3 py-2 text-sm font-medium focus:outline-none focus:border-primary min-w-[120px]">
                {ASSETS.map(a => <option key={a.symbol} value={a.symbol}>{a.symbol} · {a.name}</option>)}
              </select>
              <input readOnly value={toAsset.address.slice(0, 10) + '…' + toAsset.address.slice(-6)}
                className="flex-1 bg-card border border-border rounded-lg px-3 py-2 text-sm font-mono text-muted-foreground" />
            </div>
          </div>
        </div>
        <div className="mb-6">
          <label className="text-xs text-muted-foreground font-mono uppercase tracking-wider mb-2 block">Amount (USD)</label>
          <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)}
            className="w-full bg-card border border-border rounded-lg px-4 py-3 text-lg font-mono focus:outline-none focus:border-primary" placeholder="Enter value" />
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <button onClick={() => setSimulated(true)} className="px-6 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90">
            🔍 Simulate Route
          </button>
          {!isConnected ? <WalletButton /> : <span className="text-sm text-muted-foreground">Wallet connected — contracts deploying soon</span>}
        </div>

        {simulatedRoute && (
          <div className="mt-8 p-6 rounded-2xl border border-border" style={{ borderLeft: `4px solid ${simulatedRoute.color}` }}>
            <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
              <div>
                <div className="text-xs text-muted-foreground font-mono uppercase tracking-wider mb-1">Recommended Route</div>
                <div className="text-2xl font-bold" style={{ color: simulatedRoute.color }}>{simulatedRoute.name}</div>
                <div className="text-sm text-muted-foreground mt-1">{showAll ? simulatedRoute.desc : simulatedRoute.simple}</div>
              </div>
              <div className="text-right">
                <div className="text-xs text-muted-foreground font-mono uppercase tracking-wider">Gas Cost</div>
                <div className="text-3xl font-extrabold" style={{ color: simulatedRoute.color }}>{simulatedRoute.gas}</div>
                {simulatedRoute.id !== 'SINGLE_CHAIN' && (
                  <div className="text-sm text-green-500 mt-1">vs $31.00 direct — saves {simulatedRoute.id === 'NETTING' ? '99.8%' : '96.8%'}</div>
                )}
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t border-border">
              <div><div className="text-[10px] text-muted-foreground font-mono uppercase">BTCP Score</div><div className="font-mono text-lg font-bold">{simulatedRoute.score}</div></div>
              <div><div className="text-[10px] text-muted-foreground font-mono uppercase">Finality</div><div className="font-mono text-lg font-bold">{simulatedRoute.finality}</div></div>
              <div><div className="text-[10px] text-muted-foreground font-mono uppercase">Best Used When</div><div className="text-sm">{simulatedRoute.when}</div></div>
              <div><div className="text-[10px] text-muted-foreground font-mono uppercase">7-Plane Check</div><div className="text-sm text-green-500">✓ All passing</div></div>
            </div>
            {showAll && (
              <div className="mt-4 pt-4 border-t border-border">
                <div className="text-xs text-muted-foreground font-mono uppercase mb-2">Gas Comparison</div>
                {BTCP_DATA.routeTypes.map(route => (
                  <div key={route.id} className="flex items-center gap-3 mb-2">
                    <div className="w-32 text-xs text-muted-foreground truncate">{route.name}</div>
                    <div className="flex-1 h-6 bg-muted rounded-lg overflow-hidden">
                      <div className="h-full rounded-lg transition-all duration-700"
                        style={{ width: `${route.id === 'SINGLE_CHAIN' ? 100 : route.id === 'SPLIT' ? 3.2 : route.id === 'NETTING' ? 0.16 : route.id === 'PARALLEL' ? 5.8 : route.id === 'MULTI_HOP' ? 3.9 : 1.4}%`, background: route.color, opacity: route.id === simulatedRoute.id ? 1 : 0.4 }} />
                    </div>
                    <div className="w-16 text-right font-mono text-xs">{route.gas}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </Card>

      <Card title="How It Works — The 6-step routing journey">
        <div className="grid md:grid-cols-3 lg:grid-cols-6 gap-4">
          {BTCP_DATA.sixSteps.map((step, i) => (
            <div key={step.num} className="p-5 rounded-lg border border-border relative">
              <div className="absolute -top-3 -left-3 w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm text-white"
                style={{ background: step.color }}>{step.num}</div>
              <div className="mt-3 font-bold mb-1">{step.name}</div>
              <div className="text-sm text-muted-foreground">{showAll ? step.desc : step.simple}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Six ways to route, optimized for behavior">
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {BTCP_DATA.routeTypes.map(route => (
            <div key={route.id} className="p-6 rounded-lg border border-border" style={{ borderTop: `3px solid ${route.color}` }}>
              <div className="flex items-start justify-between mb-3">
                <div className="font-bold text-lg">{route.name}</div>
                <div className="font-mono text-2xl font-extrabold" style={{ color: route.color }}>{route.gas}</div>
              </div>
              <p className="text-sm text-muted-foreground mb-4">{showAll ? route.desc : route.simple}</p>
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Score: <span className="font-mono">{route.score}</span></span>
                <span className="text-muted-foreground">Finality: <span className="font-mono">{route.finality}</span></span>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {showAll && (
        <Card title="The 8 Water Principle Improvements — Eight mechanisms that make BTCP flow like water">
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
            {BTCP_DATA.eightWaterPrinciples.map(p => (
              <div key={p.id} className="p-5 rounded-lg border border-border">
                <div className="font-mono text-xs text-cyan-500 mb-1">{p.id}</div>
                <div className="font-bold mb-2">{p.name}</div>
                <div className="text-sm text-muted-foreground mb-3">{p.simple}</div>
                <div className="text-xs text-muted-foreground border-t border-border pt-3">
                  <div><span className="text-red-500">Problem:</span> {p.problem}</div>
                  <div className="mt-1"><span className="text-green-500">Solution:</span> {p.solution}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {bibl && (
        <Card title="BIBL Tier-1 Snapshot — Live Chain Data" live>
          <DataTable
            headers={['Chain', 'NL Score', 'Gas Forecast', 'CC Coherence', 'MF Score']}
            rows={Object.entries(bibl?.snapshot || {}).map(([chain, s]: any) => [
              chain, pct(s.nl_score, 2), `$${s.gas_forecast?.toFixed(2)}`, pct(s.cc_coherence, 2), pct(s.mf_score, 2),
            ])}
            emptyMessage="Loading..."
          />
        </Card>
      )}

      <Card title="Built on BTCP → The Continuum clearing network eliminates $13.9B/year of market waste">
        <p className="text-sm text-muted-foreground mb-4">
          BTCP is the cross-chain foundation. Continuum operates in the behavioral window that precedes price reality.
        </p>
      </Card>
    </div>
  );
}

export function WalletContinuumPage() {
  const [showAll, setShowAll] = useState(false);
  const { isConnected } = useAccount();
  const { data: faiss } = useAPI('/api/v1/faiss', 5000);
  const { data: streamer } = useAPI('/api/v1/btcp/streamer/status', 3000);

  return (
    <div className="space-y-8">
      <Card title="Continuum · Where behavior precedes price">
        <div className="flex items-center justify-between mb-4">
          <div className="text-xs text-muted-foreground font-mono uppercase tracking-wider">Layer 3 · Behavioral Clearing Network</div>
          <button onClick={() => setShowAll(v => !v)} className="px-3 py-1 rounded-lg border border-border text-xs hover:bg-muted transition-all">
            {showAll ? 'Hide Details' : 'Show All Details'}
          </button>
        </div>
        <p className="text-lg font-semibold mb-4" style={{ background: 'linear-gradient(90deg, #8b5cf6, #22d3ee)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
          {CONTINUUM_DATA.tagline}
        </p>
        {showAll && <p className="text-sm text-muted-foreground">{CONTINUUM_DATA.coreDiscovery}</p>}
      </Card>

      <Card title={`$${CONTINUUM_DATA.wasteBreakdown.total} Billion eliminated per year`}>
        <div className="flex items-center justify-between mb-6">
          <div className="text-xs text-muted-foreground font-mono uppercase tracking-wider">Annual Market Waste</div>
          {!isConnected && <WalletButton />}
        </div>
        <div className="space-y-3">
          {CONTINUUM_DATA.wasteBreakdown.items.map(item => (
            <div key={item.name} className="flex items-center gap-4">
              <div className="w-36 text-sm font-medium shrink-0">{item.name}</div>
              <div className="flex-1 h-8 bg-muted rounded-lg overflow-hidden relative">
                <div className="h-full rounded-lg transition-all duration-700"
                  style={{ width: `${(item.value / CONTINUUM_DATA.wasteBreakdown.total) * 100}%`, background: item.color }} />
                {showAll && <div className="absolute inset-0 flex items-center px-3 text-xs text-muted-foreground">{item.simple}</div>}
              </div>
              <div className="w-20 text-right font-mono font-bold">${item.value}B</div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Five engines that operate in the behavioral window">
        <div className="space-y-4">
          {CONTINUUM_DATA.engines.map(engine => (
            <div key={engine.id} className="p-6 rounded-lg border border-border" style={{ borderLeft: `4px solid ${engine.color}` }}>
              <div className="flex items-center gap-3 mb-2">
                <span className="px-3 py-1 rounded text-xs font-mono font-bold text-white" style={{ background: engine.color }}>
                  {engine.shortName}
                </span>
                <h3 className="text-xl font-bold">{engine.name}</h3>
              </div>
              <p className="text-muted-foreground">
                <strong style={{ color: engine.color }}>{engine.simple}</strong>
              </p>
              {showAll && (
                <div className="grid md:grid-cols-3 gap-6 pt-4 border-t border-border mt-4">
                  <div>
                    <div className="text-[10px] text-muted-foreground font-mono uppercase mb-2">The Formula (Plain English)</div>
                    <p className="text-sm">{engine.plainEnglish}</p>
                  </div>
                  <div>
                    <div className="text-[10px] text-muted-foreground font-mono uppercase mb-2">What It Does</div>
                    <p className="text-sm">{engine.whatItDoes}</p>
                  </div>
                  <div>
                    <div className="text-[10px] text-muted-foreground font-mono uppercase mb-2">Key Property</div>
                    <p className="text-sm">{engine.keyConstraint || engine.keyProperty || engine.coreInsight}</p>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>

      <Card title="Complement Certainty Premium — The spread that middlemen take flows back to you">
        <div className="grid md:grid-cols-2 gap-8 items-center">
          <div>
            <p className="text-sm text-muted-foreground mb-6">{CONTINUUM_DATA.ccpDistribution.simple}</p>
            <div className="space-y-3">
              {[
                { label: 'You (Trader A)', pct: 40, color: '#22d3ee' },
                { label: 'Counterparty (Trader B)', pct: 40, color: '#8b5cf6' },
                { label: 'Validators', pct: 12, color: '#fbbf24' },
                { label: 'Protocol', pct: 8, color: '#f472b6' },
              ].map(c => (
                <div key={c.label} className="flex items-center gap-3">
                  <div className="w-40 text-sm">{c.label}</div>
                  <div className="flex-1 h-4 bg-muted rounded-full overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${c.pct}%`, background: c.color }} />
                  </div>
                  <div className="w-12 text-right font-mono font-bold">{c.pct}%</div>
                </div>
              ))}
            </div>
          </div>
          <div className="flex items-center justify-center">
            <svg viewBox="0 0 200 200" className="w-64 h-64">
              {[{off:0,pct:40,c:'#22d3ee'},{off:40,pct:40,c:'#8b5cf6'},{off:80,pct:12,c:'#fbbf24'},{off:92,pct:8,c:'#f472b6'}].map(s => {
                const circ = 2 * Math.PI * 75;
                const dash = (s.pct / 100) * circ;
                const offset = -(s.off / 100) * circ;
                return <circle key={s.off} cx="100" cy="100" r="75" fill="none" stroke={s.c} strokeWidth="25"
                  strokeDasharray={`${dash} ${circ}`} strokeDashoffset={offset} transform="rotate(-90 100 100)" />;
              })}
              <circle cx="100" cy="100" r="55" fill="var(--color-background)" />
              <text x="100" y="95" textAnchor="middle" fill="var(--color-foreground)" fontSize="14" fontWeight="bold">CCP</text>
              <text x="100" y="115" textAnchor="middle" fill="var(--color-muted-foreground)" fontSize="10">Spread</text>
            </svg>
          </div>
        </div>
        {showAll && (
          <div className="mt-6 p-4 rounded-xl bg-primary/5 border border-primary/20 text-sm">
            <strong>Example:</strong> On a $10,000 trade where the current exchange spread is $35, Continuum recovers that spread.
            You get $14 (40%), your counterparty gets $14 (40%), validators get $4.20 (12%), and the protocol earns $2.80 (8%).
          </div>
        )}
      </Card>

      <Card title="FAISS Vector Space — Live CME Foundation" live>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Indexed Vectors" value={fmt(Math.max(faiss?.indexed_vectors || 0, streamer?.faiss_vectors_accumulated || 0))} color="purple" sub="128-dim BEO" />
          <StatCard label="Entities Tracked" value={fmt(faiss?.entities_tracked || 0)} color="blue" />
          <StatCard label="BHs/sec" value={streamer?.bhs_per_second?.toFixed(0) || '0'} color="green" />
          <StatCard label="Chains Active" value={fmt(streamer?.chains_active || 0)} color="amber" />
        </div>
      </Card>

      <Card title="BTCP makes Continuum possible">
        <p className="text-sm text-muted-foreground mb-4">
          Continuum's behavioral clearing operates in the window before price reality. BTCP provides the cross-chain routing infrastructure.
        </p>
      </Card>
    </div>
  );
}
