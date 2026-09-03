/**
 * TRION Frontend Master Spec - BTCP + Continuum + BotChain Pages
 *
 * Per TRION_FRONTEND_MASTER_IMPLEMENTATION.md spec.
 * Adapted from Vite+React to Next.js (our existing stack).
 *
 * Symbol {'->'} Plain English translation table applied throughout.
 */

'use client';

import { useState, useEffect } from 'react';
import { Card, StatCard, ProgressBar, Badge, DataTable, KVList, Tag, CodeBlock, EmptyState } from '../components/ui';
import { useAPI } from '../lib/hooks';
import { fetchAPI, fmt, pct, tfmt, dtfmt, truncate, hex, compact, statusColor } from '../lib/api';
import * as Icons from 'lucide-react';

// ════════════════════════════════════════════════════════════════════════════
// SYMBOL {'->'} PLAIN ENGLISH TRANSLATION TABLE
// ════════════════════════════════════════════════════════════════════════════

export const SYMBOL_TRANSLATIONS: Record<string, string> = {
  'Phi': 'Information Flow',
  'M': 'Manipulation Factor',
  'Sigma': 'Consensus Weight',
  'K': 'Knowledge Triangulation',
  'A': 'Action Alignment',
  'Theta': 'Truth Threshold',
  'Coherence': 'Coherence over time',
  'Behavioral Depth': 'Behavioral Depth over time',
  'Information Flow': 'Information Accumulated',
  'MF': 'Manipulation Factor',
  'HHI': 'Concentration Index',
  'BEO': 'Behavioral Entity Object',
  'BTCP': 'Behavioral Transaction Continuity Protocol',
  'DW-BFT': 'Dissimilarity-Weighted Byzantine Fault Tolerance',
  'BIBL': 'Behavioral Inter-Block Layer',
  'BIRP': 'Behavioral Identity Recovery Protocol',
  'CCP': 'Complement Certainty Premium',
  'BID': 'Behavioral Intent Detection',
  'CME': 'Complement Matching Engine',
  'PMO': 'Pre-Manifest Order',
  'BDC': 'Behavioral Depth Credit',
};

// ════════════════════════════════════════════════════════════════════════════
// DATA STRUCTURES (from spec)
// ════════════════════════════════════════════════════════════════════════════

export const BTCP_DATA = {
  tagline: "Why move assets when what needs to move is behavioral identity?",
  coreQuestion: "Bridges ask: How do I prove on Chain B that something happened on Chain A? BTCP asks: Why move assets at all?",
  answer: "Assets never cross chains. Behavioral facts do. The fact that Entity X performed Action Y on Chain A is permanently recorded, diversity-BFT verified, and stored in the Akashic Index. Chain B does not need a bridge to learn this fact. It needs a truth layer that already verified it. TRION is that truth layer.",
  routeTypes: [
    { id: 'SINGLE_CHAIN', name: 'Direct Single-Chain', when: 'Target chain has superior liquidity and finality', gas: '$31.00', score: 0.41, finality: '12 seconds', color: '#64748b', desc: 'Standard execution on one chain only. Used as baseline.' },
    { id: 'SPLIT', name: 'Anchor + Execute Split', when: 'Source chain has cheap security, target has cheap execution', gas: '$0.98', score: 0.94, finality: 'max(12s, 2s)', color: '#22d3ee', desc: 'Anchor behavioral proof on Ethereum (security), execute on Base (cheap gas). Assets never leave Ethereum.' },
    { id: 'NETTING', name: 'Netting (Counterparty Found)', when: 'Entity with opposite intent found simultaneously', gas: '$0.05', score: 0.98, finality: '12 seconds', color: '#10b981', desc: 'Entity A wants USDC->ETH, Entity B wants ETH->USDC. Both execute natively. Zero cross-chain movement. Optimal by construction.' },
    { id: 'PARALLEL', name: 'Parallel Split', when: 'Large intent split across multiple chains simultaneously', gas: '$1.80', score: 0.91, finality: '12 seconds', color: '#8b5cf6', desc: '$1M split across 5 chains in parallel. Reduces price impact and increases completion speed.' },
    { id: 'MULTI_HOP', name: 'Multi-Hop (A->B->C)', when: 'Intermediate chain provides liquidity bridge', gas: '$1.20', score: 0.88, finality: 'max(12s, 400ms)', color: '#fbbf24', desc: 'Ethereum->Solana->Arbitrum when Solana provides intermediate liquidity advantage. Nested escrow guarantees atomicity.' },
    { id: 'DEFERRED', name: 'Deferred (Optimal Window)', when: 'Current conditions suboptimal, intent not urgent', gas: '$0.42', score: 0.96, finality: 'within 24h', color: '#f472b6', desc: 'Biological Rhythm Timer finds optimal window: circadian gas low AND liquidity peak AND MEV valley. Auto-executes at best conditions.' },
  ],
  sixSteps: [
    { num: 1, name: 'Intent Registration', desc: 'Entity submits intent (not transaction). BIBL (Behavioral Inter-Block Layer) reads all chains simultaneously.', color: '#22d3ee' },
    { num: 2, name: 'Route Calculation', desc: 'BTCP score computed for all candidate routes across 6 route types. Natural Liquidity, gas, finality, cross-chain coherence, and BEO continuity weighted.', color: '#8b5cf6' },
    { num: 3, name: 'Cross-Chain Proof', desc: 'Anchor behavioral hash + diversity-weighted consensus proof constructed. HHI (Concentration Index) bounded at 2500.', color: '#10b981' },
    { num: 4, name: 'VM Translation', desc: '20 behavioral event types translated into each chain native execution through thin adapters. Same intent, different bytecode - identical behavioral meaning.', color: '#fbbf24' },
    { num: 5, name: 'Gas Sharing Protocol', desc: 'Anchor chain covers security cost, execution chain covers computation cost. $10K swap costs $31 on ETH alone, $0.98 via ETH->Base, $0.05 via netting.', color: '#f472b6' },
    { num: 6, name: 'Finalization + Recording', desc: 'Behavioral hash stored in Akashic Index, linked by BTCP route ID. Signal emitted with gas savings data. Append-only, instantly final via DW-BFT (Dissimilarity-Weighted BFT) consensus.', color: '#ef4444' },
  ],
  eightWaterPrinciples: [
    { id: 'BITP', name: 'Behavioral Information Transfer Protocol', problem: 'Illiquid pairs require lock/mint bridging', solution: 'Move information, not assets. Akashic clipboard. BLO removes simultaneity requirement.', tag: 'Lock/mint fallback eliminated' },
    { id: 'OOA', name: 'Observation-Only Anchoring', problem: 'Non-integrated chains cannot participate', solution: 'Channel 6 direct indexing (no permission needed). Confidence grows with observation depth.', tag: 'Hostile chains cannot opt out' },
    { id: 'IAP', name: 'Intent Aggregation Protocol', problem: 'Gas cost per user is too high for small intents', solution: 'Pool N>=3 same-direction intents within window. 100 users -> 1 pooled transaction -> 100* cheaper.', tag: '100* gas reduction' },
    { id: 'CAPSULES', name: 'State Capsules', problem: 'Cross-chain state reads are expensive and stale', solution: 'Snapshot at anchor block with staleness CI. Chain B reads from capsule, not live Chain A.', tag: 'Chain boundary does not stop state flow' },
    { id: 'BLO', name: 'Behavioral Limit Orders', problem: 'Counterparties must arrive simultaneously', solution: 'Orders stored permanently in Akashic Index. Fillable anytime. The order book that never closes.', tag: 'Simultaneity requirement removed' },
    { id: 'ZK_INTENT', name: 'ZK Intent Commitment', problem: 'MEV bots front-run expressed intents', solution: 'Hash committed, MEV bots see nothing. Atomic reveal in same block as execution. Front-running window = zero.', tag: 'MEV window = 0' },
    { id: 'BSC', name: 'Behavioral State Channels', problem: 'High-frequency interaction costs too much on-chain', solution: '50 interactions -> 2 on-chain transactions. 50* cheaper. TRION validators co-sign each state update.', tag: '50* cheaper' },
    { id: 'BRT', name: 'Biological Rhythm Timer', problem: 'Users submit at bad gas times unknowingly', solution: 'Finds optimal execution window: circadian low AND NL peak AND MEV valley. Predicted 78% gas savings.', tag: '78% gas savings' },
  ],
  liquidityOcean: {
    tagline: "No asset has zero liquidity. It just has the wrong form.",
    usdcForms: 17,
    forms: [
      { name: 'Pure USDC', pct: 38, desc: 'Raw token in wallets' },
      { name: 'aUSDC (Aave)', pct: 14, desc: 'Lending collateral' },
      { name: 'cUSDC (Compound)', pct: 9, desc: 'Lending collateral' },
      { name: 'LP Positions', pct: 12, desc: 'DEX liquidity pools' },
      { name: 'DAO Treasury', pct: 5, desc: 'Governance-held' },
      { name: 'ERC-4626 Vaults', pct: 7, desc: 'Yield aggregators' },
      { name: 'Perp Margin', pct: 4, desc: 'Derivatives collateral' },
      { name: 'Bridged Variants', pct: 6, desc: 'On other chains' },
      { name: 'Other Forms', pct: 5, desc: 'Vesting, insurance, synthetic' },
    ],
    scoreFormula: "Liquidity Ocean Score = sum over all forms of (value * shift cost inverse * shift time inverse * holder behavioral health)",
  },
  networkEffect: {
    formula: "Bridge pairs eliminated = N * (N-1) / 2",
    stages: [
      { chains: 3, pairs: 3, label: 'First 3 EVM chains' },
      { chains: 6, pairs: 15, label: 'Major EVM L2s added' },
      { chains: 10, pairs: 45, label: 'Solana integration begins' },
      { chains: 20, pairs: 190, label: 'Cross-VM BTCP live' },
      { chains: 50, pairs: 1225, label: 'Cosmos + Move + more' },
      { chains: 100, pairs: 4950, label: 'Bridges become legacy' },
    ],
  },
};

export const CONTINUUM_DATA = {
  tagline: "Behavioral reality precedes price reality by a measurable window. Continuum operates in this gap.",
  coreDiscovery: "On Ethereum: 3 to 12 blocks (36 to 144 seconds). On Solana: 50 to 200 slots (20 to 80 seconds). This window has always existed. Nobody has ever built infrastructure to use it - because nobody had the behavioral oracle layer to make it legible.",
  wasteBreakdown: {
    total: 13.9, unit: 'B',
    items: [
      { name: 'MEV Extraction', value: 1.3, color: '#ef4444', desc: 'Maximal extractable value taken by block producers' },
      { name: 'DEX Fees', value: 4.2, color: '#f97316', desc: 'Protocol fees on every decentralized exchange trade' },
      { name: 'Bridge Fees', value: 0.6, color: '#fbbf24', desc: 'Cross-chain bridge operator fees' },
      { name: 'Bridge Exploits', value: 2.8, color: '#ef4444', desc: 'Cumulative stolen from bridge hacks' },
      { name: 'Slippage Losses', value: 3.1, color: '#8b5cf6', desc: 'Price movement against traders during execution' },
      { name: 'Liquidation Cascades', value: 1.9, color: '#22d3ee', desc: 'Forced selling driving prices further down' },
    ],
  },
  engines: [
    { id: 'BID', name: 'Behavioral Intent Detection', shortName: 'BID', color: '#22d3ee',
      formula: "Detection confidence = cosine similarity between current feature change and historical precursor signature * min(depth/minimum depth, 1)",
      plainEnglish: "The system detects that an entity is likely to trade before the entity consciously decides. Nine-dimensional information flow signature changes measurably in the blocks preceding a trade.",
      whatItDoes: "Watches the 9 raw features of behavioral flow. When the pattern matches the known precursor signature for a trade direction, the system flags it.",
      keyConstraint: "The entity retains full agency. Detection never becomes commitment automatically." },
    { id: 'CME', name: 'Complement Matching Engine', shortName: 'CME', color: '#8b5cf6',
      formula: "Complement score = direction complement * temporal alignment * behavioral health * BEO independence * liquidity sufficiency",
      plainEnglish: "Finds, in real time across all chains, the entity whose behavioral pattern is the thermodynamic opposite - not a counterparty in the order book sense, but an entity who genuinely wants the opposite.",
      whatItDoes: "When Entity A shows intent precursor for USDC->ETH, the engine searches FAISS vector space for Entity B whose pattern indicates ETH->USDC intent. Both are offered a Pre-Manifest Order together.",
      keyProperty: "Semantic matching, not price ladder matching. Price comes from the TRION behavioral valuation signal." },
    { id: 'PMO', name: 'Pre-Manifest Order System', shortName: 'PMO', color: '#10b981',
      formula: "In exchange for behavioral commitment before market expression: guaranteed price at TRION valuation + complement certainty premium. No slippage. No MEV. No bridge risk.",
      plainEnglish: "An entity commits to a trade before expressing it to any market, in exchange for a guaranteed better price and a share of the spread they would have otherwise lost.",
      whatItDoes: "Entity receives a Pre-Manifest Order instrument. They confirm. The commitment is hashed and recorded. Counterparty already found by CME. Both settle via BTCP.",
      adoptionDriver: "Adoption is economically rational, not forced. Every entity who accepts is strictly better off." },
    { id: 'BDC', name: 'Behavioral Depth Credit', shortName: 'BDC', color: '#fbbf24',
      formula: "Credit limit = accumulated behavioral depth * behavioral consistency ratio * 90-day average trade size * confidence multiplier",
      plainEnglish: "An entity's accumulated behavioral history functions as creditworthy collateral for undercollateralized positions. Depth cannot be bought, transferred, lost, or forged.",
      whatItDoes: "An entity with 2 years of consistent honest history can participate at up to 10* their typical trade size, backed by behavioral depth rather than locked capital.",
      keyProperties: "Cannot be bought. Cannot be transferred. Compounds automatically. Forgery bounded by Kolmogorov complexity." },
    { id: 'THERMO', name: 'Thermodynamic Settlement', shortName: 'Settlement', color: '#f472b6',
      formula: "Settlement triggers when coherence exceeds threshold for BOTH parties simultaneously AND BTCP route verified AND no manipulation fingerprint detected.",
      plainEnglish: "Settlement is triggered by both parties being simultaneously coherent - not by time locks, human decisions, or governance votes. An attacker must maintain behavioral coherence while attacking - which means behaving honestly.",
      whatItDoes: "BTCP escrow on both chains watches the TRION coherence signal. When both entities exceed their threshold simultaneously, escrow releases. If either drops, escrow reverts.",
      coreInsight: "Behavioral manipulation is self-defeating by construction." },
  ],
  ccpDistribution: {
    total: "The spread that market makers and MEV bots currently extract flows back to both traders.",
    entityA: 40, entityB: 40, validators: 12, protocol: 8,
  },
  adoptionPath: [
    { phase: 'Phase 1', name: 'BTCP Foundation', time: 'Months 0-6', desc: 'BTCP routing live. Behavioral cross-chain identity established.' },
    { phase: 'Phase 2', name: 'BID Detection', time: 'Months 6-12', desc: 'Behavioral Intent Detection active. Voluntary opt-in only.' },
    { phase: 'Phase 3', name: 'CME Matching', time: 'Months 12-18', desc: 'Complement Matching Engine finds counterparties. First netting routes.' },
    { phase: 'Phase 4', name: 'PMO Instruments', time: 'Months 18-24', desc: 'Pre-Manifest Order system live. Commit before market for guaranteed prices.' },
    { phase: 'Phase 5', name: 'BDC Credit', time: 'Months 24-36', desc: 'Behavioral Depth Credit active. Sustained history = undercollateralized capacity.' },
    { phase: 'Phase 6', name: 'Full Continuum', time: 'Months 36+', desc: 'All 5 engines operating. $13.9B/year waste progressively eliminated.' },
  ],
};

// HONESTY NOTE (FIX-CLAIMS): The previous version of this block presented three
// "LIVE" BOT-Chain mainnet contracts with IMPOSSIBLE addresses (42/34/37 hex
// chars instead of 40), invented call/write/BEO counters, invented metrics,
// fabricated deployer stats, and future-dated "deployed Aug 12, 2026"
// milestones. No BOT Chain deployment record exists anywhere in this repo.
// All fabricated data was removed; the cards below are honest placeholders
// that keep the original layout/types.
export const BOTCHAIN_DATA = {
  chainId: 677,
  chainName: 'BOT Chain',
  tagline: 'The first home of the AI agent behavioral economy.',
  status: 'UNDEPLOYED (addresses were fabricated — removed)',
  // Explicit element type keeps the card renderer's optional stat accesses
  // (c.calls / c.writes / c.beos) type-safe; the fields are intentionally
  // absent — there are no real stats to show for undeployed contracts.
  contracts: [
    { name: 'TRION Oracle V3', address: 'NOT DEPLOYED — no address', purpose: 'Emits on-chain coherence signals', status: 'UNDEPLOYED', color: '#94a3b8' },
    { name: 'Behavioral Hash Ledger', address: 'NOT DEPLOYED — no address', purpose: 'Records behavioral hashes from relayer', status: 'UNDEPLOYED', color: '#94a3b8' },
    { name: 'BEO Identity + DW-BFT Registry', address: 'NOT DEPLOYED — no address', purpose: 'BEO identity binding + sybil-resistant checkpoints', status: 'UNDEPLOYED', color: '#94a3b8' },
  ] as Array<{ name: string; address: string; purpose: string; status: string; color: string; calls?: number; writes?: number; beos?: number }>,
  // No deployment ever occurred — all runtime metrics are zero by definition.
  metrics: {
    bhPerDay: 0, bhGrowth: '—', beosMinted: 0,
    btcpRoutes: 0, btcpInbound: 0, btcpOutbound: 0, btcpNetting: 0,
    gasSavedTotal: 0,
  },
  milestones: [
    { name: '3 Core Contracts Deployed', status: 'pending', date: 'Not deployed', desc: 'TRIONOracleV3, BehavioralHashLedger, BEOIdentityRegistry have no deployment record (the previous "deployed Aug 12, 2026" claim was fabricated).' },
    { name: 'Relayer Running', status: 'pending', date: 'Not started', desc: 'No relayer is streaming behavioral hashes to BOT Chain (previous claim fabricated).' },
    { name: 'BOT Chain Gas Sponsorship', status: 'planned', date: 'Unverified', desc: 'Gas sponsorship is a proposal only — no agreement is evidenced in this repo.' },
    { name: 'AIDID <-> BEO Binding', status: 'planned', date: 'Phase 1', desc: 'Bind BOT Chain AI agent identity to TRION BEOs. Highest priority.' },
    { name: 'BDEX ExecutionGate Hook', status: 'planned', date: 'Phase 1.5', desc: 'Pre-trade behavioral filter on BOT Chain DEX. Blocks 7 exploit patterns.' },
    { name: 'DePIN GPU ANIMA Workload', status: 'planned', date: 'Phase 2', desc: 'ANIMA 59-language inference, FAISS vector search on DePIN GPUs.' },
    { name: 'BTCP Zero-Bridge Demo', status: 'planned', date: 'Phase 2', desc: 'BOT Chain <-> Ethereum <-> Arbitrum <-> 0G. No bridges. Only behavioral facts.' },
    { name: '100K AI Agent Economy', status: 'vision', date: 'Phase 3', desc: '100,000 AI agents with BEO identity, operating across 100 chains.' },
  ],
  valueProps: [
    { title: 'First EVM L1 Reference Customer', desc: 'Priceless for BD to Base, Arbitrum, Polygon later. BOT Chain is where TRION launched.', icon: 'star' },
    { title: '100K+ Community Users', desc: 'Access to BOT Chain community through integrated behavioral applications.', icon: 'users' },
    { title: 'Free DePIN GPU Compute', desc: '$10K-$30K/year value in subsidized GPU compute for ANIMA inference and FAISS operations.', icon: 'cpu' },
    { title: 'Regulatory Shield', desc: 'TRION becomes an integrated component of an audited L1, reducing regulatory surface area.', icon: 'shield' },
    { title: 'First Live BTCP Demo', desc: 'BOT Chain <-> ETH <-> ARB <-> 0G zero-bridge cross-chain routing demonstration.', icon: 'zap' },
    { title: 'VC Introduction Access', desc: 'Access to BOT Chain investors including Bitget and OKX for future ecosystem growth.', icon: 'trending' },
  ],
  // Previous deployer stats (address balance, 39 totalTxs, gas, block range,
  // "~15 minutes, Aug 12 2026") were fabricated — no deployment record exists.
  deployer: {
    address: 'NOT DEPLOYED — previous address had no deployment record',
    balance: '—', totalTxs: 0,
    gasUsed: '—', blockRange: '—',
    timeWindow: '—',
  },
};

// ════════════════════════════════════════════════════════════════════════════
// BTCP PAGE (spec Task 3)
// ════════════════════════════════════════════════════════════════════════════

export function BTCPSpecPage() {
  const { data: bibl } = useAPI('/api/v1/btcp/bibl/snapshot', 15000);
  const { data: modules } = useAPI('/api/v1/btcp/modules', 30000);
  const { data: bootstrap } = useAPI('/api/v1/btcp/mainnet_bootstrap', 30000);

  return (
    <div className="space-y-8">
      {/* 1. Hero */}
      <Card title="BTCP - Behavioral Transaction Continuity Protocol">
        <p className="text-lg font-semibold mb-4 grad-text" style={{ background: 'linear-gradient(90deg, #22d3ee, #8b5cf6)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
          {BTCP_DATA.tagline}
        </p>
        <div className="mt-4 p-4 rounded-lg border border-border bg-muted/30">
          <div className="text-xs text-muted-foreground mb-1">Core Question</div>
          <p className="text-sm">{BTCP_DATA.coreQuestion}</p>
        </div>
        <div className="mt-3 p-4 rounded-lg border border-cyan-500/30 bg-cyan-500/5">
          <div className="text-xs text-cyan-500 mb-1">Answer</div>
          <p className="text-sm">{BTCP_DATA.answer}</p>
        </div>
      </Card>

      {/* 2. Six-Step Routing Flow */}
      <Card title="6-Step Routing Pipeline" subtitle="BTCP (Behavioral Transaction Continuity Protocol) execution flow">
        <div className="flex flex-col md:flex-row gap-3">
          {BTCP_DATA.sixSteps.map((step, i) => (
            <div key={step.num} className="flex-1 p-4 rounded-lg border border-border relative">
              <div className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold mb-3"
                   style={{ backgroundColor: step.color }}>
                {step.num}
              </div>
              <div className="font-semibold text-sm mb-1">{step.name}</div>
              <div className="text-xs text-muted-foreground">{step.desc}</div>
              {i < BTCP_DATA.sixSteps.length - 1 && (
                <div className="hidden md:block absolute top-1/2 -right-2 text-muted-foreground text-xl">{'->'}</div>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* 3. Route Type Comparison */}
      <Card title="Route Type Comparison - 6 BTCP Route Types">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {BTCP_DATA.routeTypes.map(rt => (
            <div key={rt.id} className={`p-4 rounded-lg border-2 ${rt.id === 'NETTING' ? 'border-emerald-500/50 bg-emerald-500/5' : 'border-border'}`}
                 style={{ borderLeftWidth: '4px', borderLeftColor: rt.color }}>
              <div className="flex items-center justify-between mb-2">
                <span className="font-semibold text-sm">{rt.name}</span>
                {rt.id === 'NETTING' && <Badge status="OPTIMAL" />}
              </div>
              <div className="text-3xl font-bold mb-1" style={{ color: rt.color }}>{rt.gas}</div>
              <div className="text-xs text-muted-foreground mb-2">BTCP Score: {rt.score} - Finality: {rt.finality}</div>
              <div className="text-xs text-muted-foreground mb-2">When: {rt.when}</div>
              <div className="text-xs">{rt.desc}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* 4. Gas Comparison */}
      <Card title="Gas Cost Comparison - $10K USDC->ETH Swap">
        <div className="space-y-4">
          {[
            { label: 'Direct ETH only', cost: 31.00, color: '#64748b', pct: 100 },
            { label: 'Anchor ETH -> Execute Base', cost: 0.98, color: '#22d3ee', pct: 3.2 },
            { label: 'Netting (counterparty found)', cost: 0.05, color: '#10b981', pct: 0.16 },
          ].map(g => (
            <div key={g.label}>
              <div className="flex justify-between text-sm mb-1">
                <span>{g.label}</span>
                <span className="font-mono font-bold" style={{ color: g.color }}>${g.cost.toFixed(2)}</span>
              </div>
              <div className="h-4 bg-muted rounded overflow-hidden">
                <div className="h-full rounded transition-all duration-700" style={{ width: `${g.pct}%`, backgroundColor: g.color }} />
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 p-3 rounded bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-600">
          Netting saves 99.8% vs direct ETH, 94.9% vs split route. Zero cross-chain asset movement.
        </div>
      </Card>

      {/* 5. Eight Water Principle Mechanisms */}
      <Card title="8 Water Principle Mechanisms - Why assets never need to cross chains">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {BTCP_DATA.eightWaterPrinciples.map(p => (
            <div key={p.id} className="p-4 rounded-lg border border-border">
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-xs font-bold text-cyan-500">{p.id}</span>
                <Badge status="INFO" label={p.tag} />
              </div>
              <div className="font-semibold text-sm mb-1">{p.name}</div>
              <div className="text-xs text-muted-foreground mb-2"><span className="text-rose-500">Problem:</span> {p.problem}</div>
              <div className="text-xs"><span className="text-emerald-500">Solution:</span> {p.solution}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* 6. Liquidity Ocean */}
      <Card title="Liquidity Ocean - No asset has zero liquidity, it just has the wrong form">
        <p className="text-sm text-muted-foreground mb-4">USDC exists in {BTCP_DATA.liquidityOcean.usdcForms} forms simultaneously. The Liquidity Ocean Score tracks all of them.</p>
        <div className="space-y-2">
          {BTCP_DATA.liquidityOcean.forms.map(f => (
            <div key={f.name}>
              <div className="flex justify-between text-xs mb-1">
                <span>{f.name} - <span className="text-muted-foreground">{f.desc}</span></span>
                <span className="font-mono font-bold">{f.pct}%</span>
              </div>
              <ProgressBar value={f.pct} max={40} color="blue" height={6} />
            </div>
          ))}
        </div>
        <div className="mt-4 p-3 rounded bg-muted/50 text-xs font-mono">
          {BTCP_DATA.liquidityOcean.scoreFormula}
        </div>
      </Card>

      {/* 7. Network Effect */}
      <Card title="Network Effect - Bridge pairs eliminated = N * (N-1) / 2">
        <div className="flex flex-col md:flex-row gap-3">
          {BTCP_DATA.networkEffect.stages.map((s, i) => (
            <div key={i} className="flex-1 p-4 rounded-lg border border-border relative">
              {i < BTCP_DATA.networkEffect.stages.length - 1 && (
                <div className="hidden md:block absolute top-1/2 -right-2 text-muted-foreground text-xl">{'->'}</div>
              )}
              <div className="text-2xl font-bold text-cyan-500">{s.chains}</div>
              <div className="text-xs text-muted-foreground">chains</div>
              <div className="text-lg font-bold text-emerald-500 mt-2">{s.pairs.toLocaleString()}</div>
              <div className="text-xs text-muted-foreground">pairs eliminated</div>
              <div className="text-xs mt-1">{s.label}</div>
            </div>
          ))}
        </div>
        {bootstrap && (
          <div className="mt-4 p-3 rounded bg-cyan-500/10 border border-cyan-500/30 text-sm">
            Current: {bootstrap.total_chains} chains - {bootstrap.bridge_pairs_eliminated?.toLocaleString()} pairs eliminated - {bootstrap.vm_families} VM families
          </div>
        )}
      </Card>

      {/* 8. CTA */}
      <Card title="Built on BTCP -> The Continuum Clearing Network">
        <p className="text-sm text-muted-foreground mb-4">
          The Continuum clearing network eliminates $13.9B/year of market waste. Five engines operate in the gap between behavioral reality and price reality.
        </p>
        <a href="/continuum" className="inline-block px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90">
          Explore Continuum {'->'}
        </a>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// CONTINUUM PAGE (spec Task 4)
// ════════════════════════════════════════════════════════════════════════════

export function ContinuumSpecPage() {
  const { data: engines } = useAPI('/api/v1/continuum/engines', 30000);

  return (
    <div className="space-y-8">
      {/* 1. Hero */}
      <Card title="Continuum - The Behavioral Clearing Network">
        <p className="text-lg font-semibold mb-4" style={{ background: 'linear-gradient(90deg, #8b5cf6, #22d3ee)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
          {CONTINUUM_DATA.tagline}
        </p>
        <div className="mt-4 p-4 rounded-lg border border-violet-500/30 bg-violet-500/5">
          <div className="text-xs text-violet-500 mb-1">Core Discovery</div>
          <p className="text-sm">{CONTINUUM_DATA.coreDiscovery}</p>
        </div>
      </Card>

      {/* 2. $13.9B Waste Breakdown */}
      <Card title={`$${CONTINUUM_DATA.wasteBreakdown.total}${CONTINUUM_DATA.wasteBreakdown.unit} Annual Market Waste - What Continuum Eliminates`}>
        <div className="space-y-3">
          {CONTINUUM_DATA.wasteBreakdown.items.map(item => (
            <div key={item.name}>
              <div className="flex justify-between text-sm mb-1">
                <span>{item.name} - <span className="text-muted-foreground text-xs">{item.desc}</span></span>
                <span className="font-mono font-bold" style={{ color: item.color }}>${item.value}B</span>
              </div>
              <ProgressBar value={item.value} max={5} color="purple" height={8} />
            </div>
          ))}
        </div>
        <div className="mt-4 text-center text-2xl font-bold text-rose-500">
          Total: ${CONTINUUM_DATA.wasteBreakdown.total}{CONTINUUM_DATA.wasteBreakdown.unit}/year
        </div>
      </Card>

      {/* 3. Five Engines */}
      <Card title="5 Continuum Engines - Operating in the gap between behavioral reality and price reality">
        <div className="space-y-4">
          {CONTINUUM_DATA.engines.map(e => (
            <div key={e.id} className="p-5 rounded-lg border border-border" style={{ borderLeftWidth: '4px', borderLeftColor: e.color }}>
              <div className="flex items-center gap-3 mb-3">
                <div className="px-3 py-1 rounded text-xs font-mono font-bold text-white" style={{ backgroundColor: e.color }}>
                  {e.id}
                </div>
                <div className="font-bold text-base">{e.name}</div>
                <div className="text-xs text-muted-foreground">({e.shortName})</div>
              </div>
              <div className="text-sm font-semibold mb-2" style={{ color: e.color }}>Formula (plain English):</div>
              <p className="text-sm text-muted-foreground mb-3">{e.formula}</p>
              <div className="text-sm font-semibold mb-1">What it does:</div>
              <p className="text-sm mb-3">{e.whatItDoes}</p>
              <div className="text-sm font-semibold mb-1">Key insight:</div>
              <p className="text-sm text-muted-foreground">
                {e.keyConstraint || e.keyProperty || e.adoptionDriver || e.coreInsight || e.keyProperties}
              </p>
            </div>
          ))}
        </div>
      </Card>

      {/* 4. CCP Distribution */}
      <Card title="Complement Certainty Premium (CCP) Distribution">
        <p className="text-sm text-muted-foreground mb-4">{CONTINUUM_DATA.ccpDistribution.total}</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: 'Entity A', value: CONTINUUM_DATA.ccpDistribution.entityA, color: '#22d3ee' },
            { label: 'Entity B', value: CONTINUUM_DATA.ccpDistribution.entityB, color: '#10b981' },
            { label: 'Validators', value: CONTINUUM_DATA.ccpDistribution.validators, color: '#8b5cf6' },
            { label: 'Protocol', value: CONTINUUM_DATA.ccpDistribution.protocol, color: '#fbbf24' },
          ].map(c => (
            <div key={c.label} className="text-center p-4 rounded-lg border border-border">
              <div className="text-3xl font-bold" style={{ color: c.color }}>{c.value}%</div>
              <div className="text-xs text-muted-foreground mt-1">{c.label}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* 5. Adoption Path */}
      <Card title="Adoption Path - 6 Phases to Full Continuum">
        <div className="flex flex-col md:flex-row gap-3">
          {CONTINUUM_DATA.adoptionPath.map((p, i) => (
            <div key={p.phase} className="flex-1 p-4 rounded-lg border border-border relative">
              {i < CONTINUUM_DATA.adoptionPath.length - 1 && (
                <div className="hidden md:block absolute top-1/2 -right-2 text-muted-foreground text-xl">{'->'}</div>
              )}
              <div className="font-mono text-xs text-cyan-500 mb-1">{p.phase}</div>
              <div className="font-bold text-sm mb-1">{p.name}</div>
              <div className="text-xs text-muted-foreground mb-2">{p.time}</div>
              <div className="text-xs">{p.desc}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* 6. CTA */}
      <Card title="BTCP is the Cross-Chain Foundation">
        <p className="text-sm text-muted-foreground mb-4">
          The Continuum clearing network is built on BTCP - the Behavioral Transaction Continuity Protocol
          that makes cross-chain behavioral identity possible without bridges.
        </p>
        <a href="/btcp" className="inline-block px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90">
          Explore BTCP {'->'}
        </a>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// BOT CHAIN PAGE (spec Task 5)
// ════════════════════════════════════════════════════════════════════════════

export function BotChainSpecPage() {
  const m = BOTCHAIN_DATA.metrics;

  return (
    <div className="space-y-8">
      {/* 1. Hero */}
      <Card title={`BOT Chain Integration - ChainID ${BOTCHAIN_DATA.chainId}`}>
        <div className="flex items-center gap-3 mb-4">
          <span className="text-xl font-semibold">{BOTCHAIN_DATA.chainName}</span>
          <Badge status={BOTCHAIN_DATA.status} />
        </div>
        <p className="text-sm text-muted-foreground">{BOTCHAIN_DATA.tagline}</p>
      </Card>

      {/* 2. Key Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="BH/day" value={fmt(m.bhPerDay)} sub={m.bhGrowth} color="blue" />
        <StatCard label="BEOs Minted" value={fmt(m.beosMinted)} color="purple" />
        <StatCard label="BTCP Routes" value={fmt(m.btcpRoutes)} color="green" />
        <StatCard label="Gas Saved" value={`$${fmt(m.gasSavedTotal)}`} color="amber" />
      </div>

      {/* 3. Contracts (NOT deployed — see HONESTY NOTE above) */}
      <Card title={'Contracts - None Deployed on BOT Chain (previous "LIVE" entries were fabricated)'}>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {BOTCHAIN_DATA.contracts.map(c => (
            <div key={c.name} className="p-4 rounded-lg border border-border">
              <div className="flex items-center justify-between mb-2">
                <span className="font-semibold text-sm">{c.name}</span>
                <Badge status={c.status} />
              </div>
              <div className="font-mono text-xs text-muted-foreground mb-2 break-all">{c.address}</div>
              <div className="text-xs text-muted-foreground mb-1">{c.purpose}</div>
              <div className="text-sm font-mono">
                {c.calls && <span className="text-cyan-500">{c.calls} calls</span>}
                {c.writes && <span className="text-cyan-500">{c.writes} writes</span>}
                {c.beos && <span className="text-purple-500">{c.beos} BEOs</span>}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* 4. Integration Milestones */}
      <Card title="Integration Milestones - 8-Step Roadmap">
        <div className="space-y-3">
          {BOTCHAIN_DATA.milestones.map(ms => (
            <div key={ms.name} className="flex items-start gap-3 p-3 rounded border border-border">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                ms.status === 'complete' ? 'bg-emerald-500 text-white' :
                ms.status === 'in-progress' ? 'bg-amber-500 text-white animate-pulse' :
                ms.status === 'ready' ? 'bg-cyan-500 text-white' :
                ms.status === 'pending' ? 'bg-muted text-muted-foreground' :
                'bg-muted/50 text-muted-foreground'
              }`}>
                {ms.status === 'complete' ? '✓' : ms.status === 'in-progress' ? '◐' : '○'}
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-sm">{ms.name}</span>
                  <Badge status={ms.status.toUpperCase()} />
                </div>
                <div className="text-xs text-muted-foreground mt-1">{ms.date}</div>
                <div className="text-xs mt-1">{ms.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* 5. BTCP Routes Involving BOT Chain */}
      <Card title="BTCP Routes Involving BOT Chain">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <StatCard label="Inbound Routes" value={fmt(m.btcpInbound)} sub="from other chains" color="blue" />
          <StatCard label="Outbound Routes" value={fmt(m.btcpOutbound)} sub="to other chains" color="purple" />
          <StatCard label="Netting Routes" value={fmt(m.btcpNetting)} sub="zero movement" color="green" />
        </div>
        <div className="mt-3 text-xs text-muted-foreground">
          Netting routes = zero cross-chain asset movement. Both parties execute natively on BOT Chain.
        </div>
      </Card>

      {/* 6. Value Propositions */}
      <Card title="Value Propositions for BOT Chain - Why This Integration Matters">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {BOTCHAIN_DATA.valueProps.map(vp => (
            <div key={vp.title} className="p-4 rounded-lg border border-border">
              <div className="font-semibold text-sm mb-1">{vp.title}</div>
              <div className="text-xs text-muted-foreground">{vp.desc}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* 7. Deployer Information */}
      <Card title="Deployer Information">
        <div className="p-4 rounded-lg bg-muted/50 font-mono text-xs space-y-1">
          <div><span className="text-muted-foreground">Address:</span> {BOTCHAIN_DATA.deployer.address}</div>
          <div><span className="text-muted-foreground">Balance:</span> {BOTCHAIN_DATA.deployer.balance}</div>
          <div><span className="text-muted-foreground">Total Txs:</span> {BOTCHAIN_DATA.deployer.totalTxs}</div>
          <div><span className="text-muted-foreground">Gas Used:</span> {BOTCHAIN_DATA.deployer.gasUsed}</div>
          <div><span className="text-muted-foreground">Block Range:</span> {BOTCHAIN_DATA.deployer.blockRange}</div>
          <div><span className="text-muted-foreground">Time Window:</span> {BOTCHAIN_DATA.deployer.timeWindow}</div>
        </div>
      </Card>

      {/* 8. CTA */}
      <Card title="BOT Chain Integration - Not Yet Live">
        <p className="text-sm text-muted-foreground mb-4">
          Nothing is deployed yet. The question is not whether to fuel what is running —
          it is whether to build and deploy it honestly first.
        </p>
        <a href="/btcp" className="inline-block px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90">
          Learn How BTCP Routing Works {'->'}
        </a>
      </Card>
    </div>
  );
}
