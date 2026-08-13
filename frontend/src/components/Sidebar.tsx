/**
 * TRION Sidebar — navigation across all 18 page groups / 70+ pages.
 */
'use client';

import { useState, useEffect } from 'react';
import * as Icons from 'lucide-react';

export type NavItem = { id: string; label: string; icon: any; badge?: string };
export type NavGroup = { label: string; items: NavItem[] };

export const NAV: NavGroup[] = [
  {
    label: 'Overview',
    items: [
      { id: 'dashboard', label: 'Dashboard', icon: Icons.Activity },
      { id: 'architecture', label: 'Architecture', icon: Icons.Cpu },
      { id: 'vision', label: 'Vision & Roadmap', icon: Icons.Eye },
      { id: 'phases', label: 'Protocol Phases', icon: Icons.Layers },
      { id: 'phase_transition', label: 'Phase Transition', icon: Icons.GitBranch },
      { id: 'whitepaper', label: 'Whitepaper Coverage', icon: Icons.BookOpen },
      { id: 'order_parameter', label: 'Order Parameter Ψ', icon: Icons.Gauge },
      { id: 'convergence', label: 'Convergence Theorem', icon: Icons.TrendingUp },
    ],
  },
  {
    label: 'Behavioral Engine',
    items: [
      { id: 'bh', label: 'BH Explorer', icon: Icons.Hash },
      { id: 'bh_v2', label: 'BH v2 Extended', icon: Icons.FileCode },
      { id: 'bh_stats', label: 'BH Statistics', icon: Icons.BarChart3 },
      { id: 'akashic', label: 'Akashic Index', icon: Icons.Database },
      { id: 'archetypes', label: 'Archetypes', icon: Icons.Boxes },
      { id: 'beo', label: 'BEO Resolution', icon: Icons.Shield },
      { id: 'faiss', label: 'FAISS Vectors', icon: Icons.Cpu },
      { id: 'signals', label: 'Signals', icon: Icons.Radio },
      { id: 'signal_types', label: 'Signal Types', icon: Icons.List },
    ],
  },
  {
    label: 'Five-Plane Coherence',
    items: [
      { id: 'plane_physical', label: 'Φ Physical', icon: Icons.Flame },
      { id: 'plane_mental', label: 'M Mental', icon: Icons.Brain },
      { id: 'plane_spiritual', label: 'Σ Spiritual', icon: Icons.Sparkles },
      { id: 'plane_conscious', label: 'K Conscious', icon: Icons.Eye },
      { id: 'plane_anima', label: 'A ANIMA', icon: Icons.Globe },
      { id: 'coherence_profiles', label: 'Weight Profiles', icon: Icons.Scale },
    ],
  },
  {
    label: 'Security',
    items: [
      { id: 'security', label: 'SEC Composite', icon: Icons.Lock },
      { id: 'living_security', label: 'Living Security', icon: Icons.ShieldCheck },
      { id: 'chameleon', label: 'Chameleon Protocol', icon: Icons.Eye },
      { id: 'crispr', label: 'CRISPR Defense', icon: Icons.Dna },
      { id: 'pqc', label: 'Post-Quantum Crypto', icon: Icons.KeyRound },
      { id: 'manipulation', label: 'MF Detector', icon: Icons.AlertTriangle },
      { id: 'mev', label: 'MEV Detection', icon: Icons.Zap },
      { id: 'immune', label: 'Immune Memory', icon: Icons.ShieldPlus },
      { id: 'attacks', label: 'Attack Simulator', icon: Icons.Crosshair },
    ],
  },
  {
    label: 'Governance',
    items: [
      { id: 'governance', label: 'Overview', icon: Icons.Landmark },
      { id: 'awa', label: 'AWA Ceremony', icon: Icons.Award },
      { id: 'gratitude', label: 'Gratitude Protocol', icon: Icons.Heart },
      { id: 'love', label: 'Love F-coefficient', icon: Icons.HeartHandshake },
      { id: 'falsifiability', label: 'Falsifiability ×15', icon: Icons.CheckCheck },
      { id: 'slashing', label: 'Slashing Conditions', icon: Icons.Sword },
      { id: 'unknown_provision', label: 'Unknown-Unknown', icon: Icons.HelpCircle },
      { id: 'adaptive_consensus', label: 'Adaptive Consensus', icon: Icons.SlidersHorizontal },
      { id: 'right_to_invisibility', label: 'Right to Invisibility', icon: Icons.EyeOff },
      { id: 'elder_wisdom', label: 'Elder Wisdom', icon: Icons.Crown },
    ],
  },
  {
    label: 'Akashic Records',
    items: [
      { id: 'epigenetics', label: 'Epigenetics', icon: Icons.Dna },
      { id: 'fork_resolution', label: 'Fork Resolution', icon: Icons.GitFork },
      { id: 'resurrection', label: 'Resurrection', icon: Icons.RefreshCw },
      { id: 'trajectory', label: 'Trajectory Anomaly', icon: Icons.Route },
      { id: 'dormancy', label: 'Dormancy', icon: Icons.PauseCircle },
      { id: 'genesis', label: 'Genesis', icon: Icons.Sprout },
      { id: 'convergence_detail', label: 'Convergence', icon: Icons.Merge },
      { id: 'manifestation_gap', label: 'Manifestation Gap', icon: Icons.Split },
      { id: 'negative_space', label: 'Negative Space', icon: Icons.Square },
      { id: 'emergence', label: 'Emergence', icon: Icons.Sparkle },
    ],
  },
  {
    label: 'Markets',
    items: [
      { id: 'btcp', label: 'BTCP Routing', icon: Icons.Route },
      { id: 'bibl', label: 'BIBL Patterns', icon: Icons.Search },
      { id: 'bitp', label: 'BITP Exchange', icon: Icons.Repeat },
      { id: 'sba', label: 'SBA Sovereign', icon: Icons.Globe2 },
      { id: 'continuum', label: 'Continuum DEX', icon: Icons.Waves },
      { id: 'price', label: 'Price Feeds', icon: Icons.DollarSign },
      { id: 'inverted_price', label: 'Inverted Price', icon: Icons.FlipVertical },
      { id: 'liquidity', label: 'Liquidity', icon: Icons.Droplets },
      { id: 'stablecoin_health', label: 'Stablecoin Health', icon: Icons.HeartPulse },
      { id: 'price_hierarchy', label: 'Price Hierarchy', icon: Icons.ListOrdered },
    ],
  },
  {
    label: 'BTCP + CONTINUUM',
    items: [
      { id: 'btcp_pipeline', label: 'Pipeline Status', icon: Icons.GitBranch },
      { id: 'btcp_spec', label: 'BTCP Protocol', icon: Icons.Route },
      { id: 'continuum_spec', label: 'Continuum Network', icon: Icons.Waves },
      { id: 'botchain_spec', label: 'BOT Chain', icon: Icons.Bot },
      { id: 'hash_dna', label: 'Hash_DNA Explorer', icon: Icons.Hash },
      { id: 'seven_plane', label: '7-Plane Coherence', icon: Icons.Layers },
      { id: 'mf_fingerprints', label: '7 MF Fingerprints', icon: Icons.AlertTriangle },
      { id: 'btcp_modules', label: 'BTCP Modules (18)', icon: Icons.Boxes },
      { id: 'escrow_state', label: 'Escrow State Machine', icon: Icons.Lock },
      { id: 'private_bibl', label: 'Private BIBL', icon: Icons.EyeOff },
      { id: 'continuum_engines', label: 'CONTINUUM Engines', icon: Icons.Cpu },
    ],
  },
  {
    label: 'Novel Primitives',
    items: [
      { id: 'birp', label: 'BIRP Recovery', icon: Icons.Key },
      { id: 'birp_dna_code', label: 'DNA_Code Rotation', icon: Icons.RefreshCw },
      { id: 'ubl', label: 'UBL Schema', icon: Icons.LayoutGrid },
      { id: 'bc', label: 'BC Behavioral Coherence', icon: Icons.Waves },
      { id: 'xsl', label: 'XSL Ecological', icon: Icons.Leaf },
      { id: 'transduction', label: 'Transduction', icon: Icons.Radio },
      { id: 'inversion', label: 'Inversion', icon: Icons.FlipHorizontal },
      { id: 'predictive_limit', label: 'Predictive Limit', icon: Icons.Gauge },
      { id: 'information', label: 'Info Conservation', icon: Icons.Scale },
      { id: 'phase_signal', label: 'Phase Signal', icon: Icons.Activity },
    ],
  },
  {
    label: 'Validators & Consensus',
    items: [
      { id: 'validators', label: 'Validator Registry', icon: Icons.Users },
      { id: 'validator_hhi', label: 'HHI Distribution', icon: Icons.PieChart },
      { id: 'dw_bft', label: 'Diversity-W BFT', icon: Icons.Shield },
      { id: 'annotators', label: 'K Annotators', icon: Icons.UserCheck },
      { id: 'bootstrap', label: 'Bootstrap Status', icon: Icons.Rocket },
      { id: 'reputation', label: 'Reputation', icon: Icons.Star },
    ],
  },
  {
    label: '0G Integration',
    items: [
      { id: 'zg_full', label: '0G Full Stack', icon: Icons.Layers },
      { id: 'zg_storage', label: '0G Storage', icon: Icons.HardDrive },
      { id: 'zg_da', label: '0G DA Layer', icon: Icons.Database },
      { id: 'zg_compute', label: '0G Compute', icon: Icons.Cpu },
      { id: 'zg_chain', label: '0G Chain Status', icon: Icons.Link },
      { id: 'zg_proof', label: '0G Proof', icon: Icons.CheckCircle },
      { id: 'zg_vm_families', label: 'VM Families', icon: Icons.Boxes },
    ],
  },
  {
    label: 'Infrastructure',
    items: [
      { id: 'chains', label: 'Chain Coverage', icon: Icons.Globe },
      { id: 'timescale', label: 'TimescaleDB', icon: Icons.Database },
      { id: 'kv', label: 'KV Store', icon: Icons.HardDrive },
      { id: 'backfill', label: 'Backfill Status', icon: Icons.RefreshCw },
      { id: 'relayers', label: 'Relayers', icon: Icons.Radio },
      { id: 'dependency_graph', label: 'Dependency Graph', icon: Icons.Network },
      { id: 'sdk_spec', label: 'SDK Spec', icon: Icons.Package },
      { id: 'token', label: 'Token Utility', icon: Icons.Coins },
      { id: 'token_distribution', label: 'Token Distribution', icon: Icons.PieChart },
      { id: 'revenue', label: 'Revenue Model', icon: Icons.DollarSign },
    ],
  },
  {
    label: 'AI Agent',
    items: [
      { id: 'agent', label: 'Agent ID', icon: Icons.Bot },
      { id: 'agents', label: 'All Agents', icon: Icons.Users },
      { id: 'agent_validate', label: 'Validate', icon: Icons.CheckCircle },
      { id: 'invest', label: 'Investment Scan', icon: Icons.Search },
      { id: 'intelligence_maintenance', label: 'Intelligence Maint.', icon: Icons.Wrench },
    ],
  },
  {
    label: 'Protocol Health',
    items: [
      { id: 'protocol', label: 'Protocol Monitor', icon: Icons.HeartPulse },
      { id: 'protocol_roles', label: 'Roles', icon: Icons.Users },
      { id: 'self', label: 'Self Verification', icon: Icons.ShieldCheck },
    ],
  },
  {
    label: 'CEX Integration',
    items: [
      { id: 'cex', label: 'CEX Status', icon: Icons.Building },
      { id: 'cex_feed', label: 'CEX Feed', icon: Icons.Radio },
      { id: 'cex_alerts', label: 'CEX Alerts', icon: Icons.Bell },
      { id: 'cex_stats', label: 'CEX Stats', icon: Icons.BarChart3 },
    ],
  },
  {
    label: 'Explorers',
    items: [
      { id: 'leaderboard', label: 'Leaderboard', icon: Icons.Trophy },
      { id: 'feed', label: 'Signal Feed', icon: Icons.Rss },
      { id: 'audit_patterns', label: 'Audit Patterns', icon: Icons.SearchCheck },
      { id: 'demo', label: 'Demo Attacks', icon: Icons.FlaskConical },
    ],
  },
];

export function Sidebar({
  activePage,
  onPageChange,
  isOpen,
  onClose,
}: {
  activePage: string;
  onPageChange: (p: string) => void;
  isOpen: boolean;
  onClose: () => void;
}) {
  const [search, setSearch] = useState('');
  const filtered = NAV.map(g => ({
    ...g,
    items: g.items.filter(i => i.label.toLowerCase().includes(search.toLowerCase())),
  })).filter(g => g.items.length > 0);

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div className="fixed inset-0 bg-black/50 z-40 lg:hidden" onClick={onClose} />
      )}

      <aside className={`
        fixed lg:sticky top-0 left-0 z-50 lg:z-auto
        h-screen w-72 flex-shrink-0
        bg-card border-r border-border
        transform transition-transform duration-200
        ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        flex flex-col
      `}>
        {/* Logo */}
        <div className="p-4 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-bold text-sm">
              T
            </div>
            <div>
              <div className="font-bold text-sm">TRION Protocol</div>
              <div className="text-xs text-muted-foreground">Behavioral Truth Oracle</div>
            </div>
          </div>
          <button onClick={onClose} className="lg:hidden text-muted-foreground">
            <Icons.X className="w-5 h-5" />
          </button>
        </div>

        {/* Search */}
        <div className="p-3 border-b border-border">
          <div className="relative">
            <Icons.Search className="absolute left-2 top-2.5 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search pages…"
              className="w-full pl-8 pr-3 py-2 rounded-lg border border-border bg-input text-sm"
            />
          </div>
        </div>

        {/* Nav groups */}
        <nav className="flex-1 overflow-y-auto p-2">
          {filtered.map(group => (
            <div key={group.label} className="mb-3">
              <div className="px-2 py-1 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                {group.label}
              </div>
              {group.items.map(item => {
                const Icon = item.icon;
                const isActive = activePage === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => {
                      onPageChange(item.id);
                      onClose();
                    }}
                    className={`
                      w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm
                      transition-colors
                      ${isActive
                        ? 'bg-primary text-primary-foreground font-medium'
                        : 'text-foreground hover:bg-muted'
                      }
                    `}
                  >
                    <Icon className="w-4 h-4 flex-shrink-0" />
                    <span className="truncate">{item.label}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        {/* Footer */}
        <div className="p-3 border-t border-border text-xs text-muted-foreground">
          <div>v1.0.0 · 100+ chains · 14 VMs</div>
          <div className="mt-1">CC0 · Originator: Analys</div>
        </div>
      </aside>
    </>
  );
}
