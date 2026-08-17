/**
 * TRION Protocol — Redesigned Main Dashboard
 * Aligned with Whitepaper: Behavioral Truth Oracle
 * 
 * Visual narrative:
 * 1. Hero — Mission statement
 * 2. Pipeline — End-to-end data flow
 * 3. Coherence Engine — 5 behavioral planes
 * 4. Master Equation — Truth computation
 * 5. Moat Factors — Economic defensibility
 * 6. On-Chain Publication — Oracle contract
 */
'use client';
import { useState, useEffect, useCallback, useMemo, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import * as Icons from 'lucide-react';
import { Sidebar, NAV } from '../components/Sidebar';
import { LiveClock } from '../components/ui';
import { CommandPalette } from '../components/CommandPalette';
import { SettingsModal } from '../components/SettingsModal';
import { WalletButton } from '../components/wallet/WalletButton';
import { useAPI, useTheme, useStream, useCounter } from '../lib/hooks';
import { fmt, pct, tfmt, hex, compact } from '../lib/api';

// New visualization components
import { CoherenceEngine } from '../components/visualizations/CoherenceEngine';
import { PipelineFlow } from '../components/visualizations/PipelineFlow';
import { MasterEquation } from '../components/visualizations/MasterEquation';
import { MoatFactors } from '../components/visualizations/MoatFactors';
import { SignalPublication } from '../components/visualizations/SignalPublication';

// Keep existing pages accessible
import {
  ArchitecturePage, VisionPage, PhasesPage, PhaseTransitionPage,
  OrderParameterPage, ConvergencePage,
} from '../views/overview';
import {
  BHExplorerPage, BHv2ExtendedPage, BHStatsPage, AkashicPage, ArchetypesPage,
  BEOPage, FAISSPage, SignalsPage, SignalTypesPage,
} from '../views/behavioral';
import {
  PhysicalPlanePage, MentalPlanePage, SpiritualPlanePage, ConsciousPlanePage,
  AnimaPlanePage, CoherenceProfilesPage,
} from '../views/planes';
import {
  SECPage, LivingSecurityPage, ChameleonPage, CRISPRPage, PQCPage,
  ManipulationPage, MEVPage, ImmunePage, AttacksPage,
} from '../views/security';
import {
  GovernancePage, AWAPage, GratitudePage, LovePage, FalsifiabilityPage,
  SlashingPage, UnknownProvisionPage, AdaptiveConsensusPage,
  RightToInvisibilityPage, ElderWisdomPage, DWBFTPage,
} from '../views/governance';
import {
  EpigeneticsPage, ForkResolutionPage, ResurrectionPage, TrajectoryPage,
  DormancyPage, GenesisPage, ConvergenceDetailPage, ManifestationGapPage,
  NegativeSpacePage, EmergencePage,
} from '../views/akashic';
import {
  BTCPPage, BIBLPage, BITPPage, SBAPage, ContinuumPage, PricePage,
  InvertedPricePage, LiquidityPage, StablecoinHealthPage, PriceHierarchyPage,
} from '../views/markets';
import {
  BIRPPage, DNACodePage, UBLPage, BCPage, XSLPage, TransductionPage,
  InversionPage, PredictiveLimitPage, InformationPage, PhaseSignalPage,
} from '../views/primitives';
import {
  BTCPPipelinePage, HashDNAExplorerPage, SevenPlanePage, MFFingerprintsPage,
  BTCPModulesPage, EscrowStateMachinePage, PrivateBIBLPage, ContinuumEnginesPage,
} from '../views/btcp_continuum';
import {
  BTCPSpecPage, ContinuumSpecPage, BotChainSpecPage,
} from '../views/spec_pages';
import {
  BEOLookupPage, LiveEventStreamPage, TimeSeriesPage,
  BTCPVisualizationPage, ContinuumVisualizationPage,
} from '../views/ui_assessment';
import { WalletBTCPPage, WalletContinuumPage } from '../views/wallet_pages';
import {
  ValidatorsPage, ValidatorHHIPage, AnnotatorsPage, BootstrapPage, ReputationPage,
  ZeroGFullStackPage, ZeroGStoragePage, ZeroGDAPage, ZeroGComputePage, ZeroGChainPage,
  ZeroGProofPage, ZeroGVMFamiliesPage,
  ChainsPage, TimescalePage, KVStorePage, BackfillPage, RelayersPage,
  DependencyGraphPage, SDKSpecPage, TokenPage, TokenDistributionPage, RevenuePage,
  AgentPage, AgentsPage, AgentValidatePage, InvestPage, IntelligenceMaintenancePage,
  ProtocolPage, ProtocolRolesPage, SelfVerificationPage,
  CEXPage, CEXFeedPage, CEXAlertsPage, CEXStatsPage,
  LeaderboardPage, FeedPage, AuditPatternsPage, DemoPage,
} from '../views/infrastructure';

const PAGE_MAP: Record<string, React.ComponentType> = {
  // New redesigned dashboard is default
  dashboard: RedesignedDashboard,
  // Overview
  architecture: ArchitecturePage,
  vision: VisionPage,
  phases: PhasesPage,
  phase_transition: PhaseTransitionPage,
  order_parameter: OrderParameterPage,
  convergence: ConvergencePage,
  // Behavioral Engine
  bh: BHExplorerPage,
  bh_v2: BHv2ExtendedPage,
  bh_stats: BHStatsPage,
  akashic: AkashicPage,
  archetypes: ArchetypesPage,
  beo: BEOPage,
  faiss: FAISSPage,
  signals: SignalsPage,
  signal_types: SignalTypesPage,
  // Five-Plane Coherence
  plane_physical: PhysicalPlanePage,
  plane_mental: MentalPlanePage,
  plane_spiritual: SpiritualPlanePage,
  plane_conscious: ConsciousPlanePage,
  plane_anima: AnimaPlanePage,
  coherence_profiles: CoherenceProfilesPage,
  // Security
  security: SECPage,
  living_security: LivingSecurityPage,
  chameleon: ChameleonPage,
  crispr: CRISPRPage,
  pqc: PQCPage,
  manipulation: ManipulationPage,
  mev: MEVPage,
  immune: ImmunePage,
  attacks: AttacksPage,
  // Governance
  governance: GovernancePage,
  awa: AWAPage,
  gratitude: GratitudePage,
  love: LovePage,
  falsifiability: FalsifiabilityPage,
  slashing: SlashingPage,
  unknown_provision: UnknownProvisionPage,
  adaptive_consensus: AdaptiveConsensusPage,
  right_to_invisibility: RightToInvisibilityPage,
  elder_wisdom: ElderWisdomPage,
  dw_bft: DWBFTPage,
  // Akashic
  epigenetics: EpigeneticsPage,
  fork_resolution: ForkResolutionPage,
  resurrection: ResurrectionPage,
  trajectory: TrajectoryPage,
  dormancy: DormancyPage,
  genesis: GenesisPage,
  convergence_detail: ConvergenceDetailPage,
  manifestation_gap: ManifestationGapPage,
  negative_space: NegativeSpacePage,
  emergence: EmergencePage,
  // Markets
  btcp: BTCPPage,
  bibl: BIBLPage,
  bitp: BITPPage,
  sba: SBAPage,
  continuum: ContinuumPage,
  price: PricePage,
  inverted_price: InvertedPricePage,
  liquidity: LiquidityPage,
  stablecoin_health: StablecoinHealthPage,
  price_hierarchy: PriceHierarchyPage,
  // Novel Primitives
  birp: BIRPPage,
  birp_dna_code: DNACodePage,
  ubl: UBLPage,
  bc: BCPage,
  xsl: XSLPage,
  transduction: TransductionPage,
  inversion: InversionPage,
  predictive_limit: PredictiveLimitPage,
  information: InformationPage,
  phase_signal: PhaseSignalPage,
  // BTCP + CONTINUUM
  btcp_pipeline: BTCPPipelinePage,
  wallet_btcp: WalletBTCPPage,
  wallet_continuum: WalletContinuumPage,
  beo_lookup: BEOLookupPage,
  live_events: LiveEventStreamPage,
  time_series: TimeSeriesPage,
  btcp_viz: BTCPVisualizationPage,
  continuum_viz: ContinuumVisualizationPage,
  btcp_spec: BTCPSpecPage,
  continuum_spec: ContinuumSpecPage,
  botchain_spec: BotChainSpecPage,
  hash_dna: HashDNAExplorerPage,
  seven_plane: SevenPlanePage,
  mf_fingerprints: MFFingerprintsPage,
  btcp_modules: BTCPModulesPage,
  escrow_state: EscrowStateMachinePage,
  private_bibl: PrivateBIBLPage,
  continuum_engines: ContinuumEnginesPage,
  // Validators & Consensus
  validators: ValidatorsPage,
  validator_hhi: ValidatorHHIPage,
  annotators: AnnotatorsPage,
  bootstrap: BootstrapPage,
  reputation: ReputationPage,
  // 0G Integration
  zg_full: ZeroGFullStackPage,
  zg_storage: ZeroGStoragePage,
  zg_da: ZeroGDAPage,
  zg_compute: ZeroGComputePage,
  zg_chain: ZeroGChainPage,
  zg_proof: ZeroGProofPage,
  zg_vm_families: ZeroGVMFamiliesPage,
  // Infrastructure
  chains: ChainsPage,
  timescale: TimescalePage,
  kv: KVStorePage,
  backfill: BackfillPage,
  relayers: RelayersPage,
  dependency_graph: DependencyGraphPage,
  sdk_spec: SDKSpecPage,
  token: TokenPage,
  token_distribution: TokenDistributionPage,
  revenue: RevenuePage,
  // AI Agent
  agent: AgentPage,
  agents: AgentsPage,
  agent_validate: AgentValidatePage,
  invest: InvestPage,
  intelligence_maintenance: IntelligenceMaintenancePage,
  // Protocol Health
  protocol: ProtocolPage,
  protocol_roles: ProtocolRolesPage,
  self: SelfVerificationPage,
  // CEX
  cex: CEXPage,
  cex_feed: CEXFeedPage,
  cex_alerts: CEXAlertsPage,
  cex_stats: CEXStatsPage,
  // Explorers
  leaderboard: LeaderboardPage,
  feed: FeedPage,
  audit_patterns: AuditPatternsPage,
  demo: DemoPage,
};

const PAGE_TITLES: Record<string, string> = {
  dashboard: 'Dashboard',
  architecture: 'Architecture Flow',
  vision: 'Protocol Vision',
  phases: 'Protocol Phases',
  phase_transition: 'Phase Transition',
  order_parameter: 'Order Parameter',
  convergence: 'Convergence',
  bh: 'Behavioral Hash Explorer',
  bh_v2: 'BH v2 Extended Payload',
  bh_stats: 'BH Statistics',
  akashic: 'Akashic Index',
  archetypes: 'Behavioral Archetypes',
  beo: 'BEO Resolution',
  faiss: 'FAISS Vector Index',
  signals: 'Signals',
  signal_types: 'Signal Type Catalog',
  plane_physical: 'Physical Plane Phi',
  plane_mental: 'Mental Plane M',
  plane_spiritual: 'Spiritual Plane Sigma',
  plane_conscious: 'Conscious Plane K',
  plane_anima: 'ANIMA Plane A',
  coherence_profiles: 'Coherence Weight Profiles',
  security: 'SEC Composite',
  living_security: 'Living Security Stack',
  chameleon: 'Chameleon Protocol',
  crispr: 'CRISPR Defense',
  pqc: 'Post-Quantum Crypto',
  manipulation: 'Manipulation Fingerprint Detector',
  mev: 'MEV Detection',
  immune: 'Immune Memory',
  attacks: 'Attack Simulator',
  governance: 'Governance Overview',
  awa: 'AWA Ceremony',
  gratitude: 'Gratitude Protocol',
  love: 'Love F-coefficient',
  falsifiability: 'Falsifiability x15',
  slashing: 'Slashing Conditions',
  unknown_provision: 'Unknown-Unknown Provision',
  adaptive_consensus: 'Adaptive Consensus',
  right_to_invisibility: 'Right to Invisibility',
  elder_wisdom: 'Elder Wisdom',
  dw_bft: 'Diversity-Weighted BFT',
  epigenetics: 'Epigenetics',
  fork_resolution: 'Fork Resolution',
  resurrection: 'Resurrection Inference',
  trajectory: 'Trajectory Anomaly',
  dormancy: 'Dormancy Classification',
  genesis: 'Genesis Inference',
  convergence_detail: 'Convergence Detail',
  manifestation_gap: 'Manifestation Gap',
  negative_space: 'Negative Space',
  emergence: 'Emergence Detection',
  btcp: 'BTCP Routing',
  bibl: 'BIBL Patterns',
  bitp: 'BITP Exchange',
  sba: 'SBA Sovereign',
  continuum: 'Continuum DEX',
  price: 'Price Feeds',
  inverted_price: 'Inverted Price',
  liquidity: 'Liquidity',
  stablecoin_health: 'Stablecoin Health',
  price_hierarchy: 'Price Hierarchy',
  birp: 'BIRP Recovery',
  birp_dna_code: 'DNA_Code Rotation',
  ubl: 'UBL Schema',
  bc: 'Behavioral Coherence',
  xsl: 'XSL Ecological',
  transduction: 'Transduction',
  inversion: 'Inversion',
  predictive_limit: 'Predictive Limit',
  information: 'Information Conservation',
  phase_signal: 'Phase Signal',
  btcp_pipeline: 'BTCP Pipeline Status',
  wallet_btcp: 'BTCP + Wallet',
  wallet_continuum: 'Continuum + Wallet',
  beo_lookup: 'BEO Lookup Toolbox',
  live_events: 'Live Event Stream',
  time_series: 'Time-Series Charts',
  btcp_viz: 'BTCP Visualization',
  continuum_viz: 'Continuum Visualization',
  btcp_spec: 'BTCP Protocol',
  continuum_spec: 'Continuum Network',
  botchain_spec: 'BOT Chain Integration',
  hash_dna: 'Hash_DNA Explorer',
  seven_plane: '7-Plane Coherence',
  mf_fingerprints: '7 MF Fingerprints',
  btcp_modules: 'BTCP Modules',
  escrow_state: 'Escrow State Machine',
  private_bibl: 'Private BIBL',
  continuum_engines: 'CONTINUUM Engines',
  validators: 'Validator Registry',
  validator_hhi: 'HHI Distribution',
  annotators: 'K Annotators',
  bootstrap: 'Bootstrap Status',
  reputation: 'Reputation',
  zg_full: '0G Full Stack',
  zg_storage: '0G Storage',
  zg_da: '0G DA Layer',
  zg_compute: '0G Compute',
  zg_chain: '0G Chain Status',
  zg_proof: '0G Proof',
  zg_vm_families: 'VM Families',
  chains: 'Chain Coverage',
  timescale: 'TimescaleDB',
  kv: 'KV Store',
  backfill: 'Backfill Status',
  relayers: 'Relayers',
  dependency_graph: 'Dependency Graph',
  sdk_spec: 'SDK Spec',
  token: 'Token Utility',
  token_distribution: 'Token Distribution',
  revenue: 'Revenue Model',
  agent: 'AI Agent ID',
  agents: 'All Agents',
  agent_validate: 'Validate',
  invest: 'Investment Scan',
  intelligence_maintenance: 'Intelligence Maintenance',
  protocol: 'Protocol Monitor',
  protocol_roles: 'Protocol Roles',
  self: 'Self Verification',
  cex: 'CEX Status',
  cex_feed: 'CEX Feed',
  cex_alerts: 'CEX Alerts',
  cex_stats: 'CEX Stats',
  leaderboard: 'Leaderboard',
  feed: 'Signal Feed',
  audit_patterns: 'Audit Patterns',
  demo: 'Demo Attacks',
};

export const dynamic = 'force-dynamic';

export default function HomeWithSuspense() {
  return (
    <Suspense fallback={<div className="flex h-screen items-center justify-center text-muted-foreground">Loading TRION Protocol...</div>}>
      <Home />
    </Suspense>
  );
}

function Home() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialPage = searchParams.get('page') || 'dashboard';
  const [activePage, setActivePage] = useState(
    PAGE_MAP[initialPage] ? initialPage : 'dashboard'
  );
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [theme, toggleTheme] = useTheme();

  const changePage = useCallback((p: string) => {
    setActivePage(p);
    const url = new URL(window.location.href);
    url.searchParams.set('page', p);
    router.push(`${url.pathname}?${url.searchParams.toString()}`, { scroll: false });
  }, [router]);

  useEffect(() => {
    const p = searchParams.get('page');
    if (p && PAGE_MAP[p] && p !== activePage) {
      setActivePage(p);
    }
  }, [searchParams, activePage]);

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable) return;
      if (e.key === '?' || (e.shiftKey && e.key === '/')) {
        e.preventDefault();
        alert(
          'TRION Keyboard Shortcuts\n\n' +
          '⌘K / Ctrl+K    Command palette\n' +
          '⌘B / Ctrl+B    Toggle sidebar\n' +
          '?                This help\n' +
          'Esc             Close overlays\n'
        );
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        setSidebarOpen(v => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const PageComponent = PAGE_MAP[activePage] || RedesignedDashboard;
  const pageTitle = PAGE_TITLES[activePage] || 'Dashboard';

  const palettePages = useMemo(
    () => NAV.flatMap(g => g.items.map(item => ({
      id: item.id,
      label: item.label,
      group: g.label,
    }))),
    [],
  );

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <CommandPalette pages={palettePages} onSelect={changePage} />
      <Sidebar
        activePage={activePage}
        onPageChange={changePage}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex items-center justify-between px-4 md:px-6 h-16 border-b border-border bg-card flex-shrink-0 gap-2">
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <button
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden p-2 rounded-lg hover:bg-accent flex-shrink-0"
              aria-label="Open sidebar"
            >
              <Icons.Menu className="w-5 h-5" />
            </button>
            <div className="min-w-0">
              <h1 className="text-lg font-bold truncate">{pageTitle}</h1>
              <p className="text-xs text-muted-foreground hidden sm:block truncate">
                TRION Protocol — Behavioral Truth Oracle
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <LiveClock />
            <button
              onClick={toggleTheme}
              className="p-2 rounded-lg hover:bg-accent"
              aria-label="Toggle theme"
            >
              {theme === 'dark' ? <Icons.Sun className="w-4 h-4" /> : <Icons.Moon className="w-4 h-4" />}
            </button>
            <button
              onClick={() => setSettingsOpen(true)}
              className="p-2 rounded-lg hover:bg-accent"
              aria-label="Settings"
            >
              <Icons.Settings className="w-4 h-4" />
            </button>
            <WalletButton />
          </div>
        </header>

        {/* Main content */}
        <main className="flex-1 overflow-y-auto p-4 md:p-6">
          <PageComponent />
        </main>
      </div>
      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// REDESIGNED DASHBOARD — Aligned with TRION Whitepaper
// ═══════════════════════════════════════════════════════════════════════
function RedesignedDashboard() {
  const { data: health } = useAPI('/api/v1/health', 3000);
  const { data: faiss } = useAPI('/api/v1/faiss', 5000);
  const { data: streamer } = useAPI('/api/v1/btcp/streamer/status', 2000);
  const { data: bhStats } = useAPI('/api/v1/bh/stats', 3000);
  const { items: feedItems } = useStream('/api/v1/feed', 4000);

  const bhTotal = streamer?.total_bhs || Object.values(bhStats?.per_chain || {}).reduce((a: number, b: any) => a + Number(b), 0) || 0;
  const vectorCount = useCounter(Math.max(faiss?.indexed_vectors || 0, faiss?.ntotal || 0));
  const totalBH = useCounter(bhTotal);
  const isLive = health?.status === 'healthy';
  const streamerLive = streamer?.status === 'RUNNING';

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto">
      {/* HERO — Mission Statement */}
      <div className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-blue-900/30 via-purple-900/20 to-transparent p-8">
        <div className="absolute inset-0 grid-pattern opacity-20" />
        <div className="relative z-10">
          <div className="flex items-center gap-2 mb-3">
            <div className="flex items-center gap-2">
              <span className={`relative flex h-2.5 w-2.5`}>
                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${isLive ? 'bg-green-400' : 'bg-amber-400'}`}></span>
                <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${isLive ? 'bg-green-500' : 'bg-amber-500'}`}></span>
              </span>
              <span className={`text-xs font-semibold uppercase tracking-wider ${isLive ? 'text-green-400' : 'text-amber-400'}`}>
                {isLive ? 'Network Live' : 'Bootstrap Phase'}
              </span>
            </div>
          </div>
          <h1 className="text-3xl md:text-4xl font-bold mb-3">
            The Behavioral Truth Oracle
          </h1>
          <p className="text-muted-foreground max-w-2xl mb-6">
            Multi-chain behavioral truth infrastructure computing cryptographic coherence scores 
            across 5 behavioral planes. From on-chain patterns to verifiable signals — 
            TRION transforms raw transaction data into behavioral truth.
          </p>
          
          {/* Key metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricCard
              icon={<Icons.Database className="w-5 h-5" />}
              label="Behavioral Hashes"
              value={fmt(totalBH, 0)}
              sub={streamerLive ? `${streamer?.bhs_per_second?.toFixed(0) || 0}/sec live` : 'indexed'}
              color="blue"
            />
            <MetricCard
              icon={<Icons.Cpu className="w-5 h-5" />}
              label="FAISS Vectors"
              value={fmt(vectorCount, 0)}
              sub="128-dimensional BEO"
              color="purple"
            />
            <MetricCard
              icon={<Icons.Globe className="w-5 h-5" />}
              label="Chains Streaming"
              value={fmt(streamer?.chains_active || 0)}
              sub="real-time RPC"
              color="green"
            />
            <MetricCard
              icon={<Icons.Gauge className="w-5 h-5" />}
              label="Coherence C(t)"
              value={(health?.coherence_score || health?.dynamic_threshold || 0).toFixed(4)}
              sub={`Θ = ${(health?.dynamic_threshold || 0.661).toFixed(3)}`}
              color="amber"
            />
          </div>
        </div>
      </div>

      {/* PIPELINE FLOW */}
      <PipelineFlow />

      {/* COHERENCE ENGINE + MASTER EQUATION */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <CoherenceEngine />
        <MasterEquation />
      </div>

      {/* MOAT FACTORS + ON-CHAIN PUBLICATION */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <MoatFactors />
        <SignalPublication />
      </div>

      {/* LIVE DATA + WHITEPAPER FORMULAS */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Signal Feed */}
        <div className="lg:col-span-2 bg-card border border-border rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-lg font-bold">Live Signal Feed</h3>
              <p className="text-xs text-muted-foreground">Recent behavioral truth assessments</p>
            </div>
            <Icons.Radio className="w-5 h-5 text-muted-foreground" />
          </div>
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {feedItems.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground text-sm">
                <Icons.Activity className="w-8 h-8 mx-auto mb-2 opacity-50" />
                Connecting to live data stream...
              </div>
            ) : (
              feedItems.slice(0, 15).map((s: any, i: number) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-muted/20 hover:bg-muted/40 transition-colors">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${s.coherent ? 'bg-green-500' : 'bg-amber-500'}`} />
                    <div className="min-w-0">
                      <div className="font-medium text-sm truncate">
                        {s.protocol_name || s.short_id || hex(s.entity_id, 16)}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {tfmt(s.timestamp)} · {s.archetype || s.limiting_plane || 'analyzing'}
                      </div>
                    </div>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <div className={`font-mono text-sm font-bold ${s.coherent ? 'text-green-400' : 'text-amber-400'}`}>
                      {pct(s.coherence_score, 2)}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {s.signal_type || (s.coherent ? 'SIGNAL' : 'SILENCE')}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Whitepaper Reference */}
        <div className="bg-card border border-border rounded-xl p-6">
          <div className="flex items-center gap-2 mb-4">
            <Icons.BookOpen className="w-5 h-5 text-muted-foreground" />
            <h3 className="text-lg font-bold">Whitepaper Core</h3>
          </div>
          <div className="space-y-4 text-sm">
            <FormulaBlock
              layer="L5.2"
              name="Coherence"
              formula="C(t) = α·Φ + β·M + γ·Σ + δ·K + ε·A"
              desc="Five-plane weighted fusion"
            />
            <FormulaBlock
              layer="L5.3"
              name="Master Equation"
              formula="T(t) = [C≥Θ]·C·e^(M_moat)"
              desc="Truth with moat amplification"
            />
            <FormulaBlock
              layer="L0.5"
              name="Economic Moat"
              formula="M_moat = D·Q·R·X·F·N"
              desc="Six-factor multiplicative defense"
            />
            <FormulaBlock
              layer="L1.1"
              name="Physical Plane"
              formula="Φ(t) = Σ(wᵢ·fᵢ) for i=1..9"
              desc="Shannon entropy features"
            />
            <FormulaBlock
              layer="L4.1"
              name="Spiritual Plane"
              formula="Σ(t) = Σ(sⱼ·dⱼ·inlier) / Σ(sⱼ·dⱼ)"
              desc="Diversity-weighted BFT"
            />
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="text-center text-xs text-muted-foreground py-6 border-t border-border">
        TRION Protocol · Behavioral Truth Infrastructure · 100+ chains · 14 VM families
      </div>
    </div>
  );
}

function MetricCard({ icon, label, value, sub, color }: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  color: 'blue' | 'purple' | 'green' | 'amber';
}) {
  const colors = {
    blue: 'from-blue-500/20 to-blue-500/5 text-blue-400 border-blue-500/20',
    purple: 'from-purple-500/20 to-purple-500/5 text-purple-400 border-purple-500/20',
    green: 'from-green-500/20 to-green-500/5 text-green-400 border-green-500/20',
    amber: 'from-amber-500/20 to-amber-500/5 text-amber-400 border-amber-500/20',
  };
  return (
    <div className={`bg-gradient-to-br ${colors[color]} border rounded-xl p-4`}>
      <div className="flex items-center gap-2 mb-2 opacity-80">
        {icon}
        <span className="text-xs font-medium uppercase tracking-wider">{label}</span>
      </div>
      <div className="font-mono text-2xl font-bold">{value}</div>
      {sub && <div className="text-xs opacity-70 mt-1">{sub}</div>}
    </div>
  );
}

function FormulaBlock({ layer, name, formula, desc }: {
  layer: string;
  name: string;
  formula: string;
  desc: string;
}) {
  return (
    <div className="p-3 rounded-lg bg-muted/20 border border-border">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[10px] font-mono bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded">{layer}</span>
        <span className="font-semibold text-sm">{name}</span>
      </div>
      <div className="font-mono text-sm text-blue-400 mb-1">{formula}</div>
      <div className="text-xs text-muted-foreground">{desc}</div>
    </div>
  );
}
