'use client';

import { useState, useEffect, useCallback } from 'react';
import * as Icons from 'lucide-react';
import { Sidebar } from '../components/Sidebar';
import { LiveClock } from '../components/ui';
import { useAPI, useTheme } from '../lib/hooks';

// All page imports
import {
  DashboardPage, ArchitecturePage, VisionPage, PhasesPage, PhaseTransitionPage,
  WhitepaperPage, OrderParameterPage, ConvergencePage,
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
  RightToInvisibilityPage, ElderWisdomPage,
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
  SYMBOL_TRANSLATIONS, BTCP_DATA, CONTINUUM_DATA, BOTCHAIN_DATA,
} from '../views/spec_pages';
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
  // Overview
  dashboard: DashboardPage,
  architecture: ArchitecturePage,
  vision: VisionPage,
  phases: PhasesPage,
  phase_transition: PhaseTransitionPage,
  whitepaper: WhitepaperPage,
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
  whitepaper: 'Whitepaper Coverage',
  order_parameter: 'Order Parameter Ψ',
  convergence: 'Convergence Theorem',
  bh: 'Behavioral Hash Explorer',
  bh_v2: 'BH v2 Extended Payload',
  bh_stats: 'BH Statistics',
  akashic: 'Akashic Index',
  archetypes: 'Behavioral Archetypes',
  beo: 'BEO Resolution',
  faiss: 'FAISS Vector Index',
  signals: 'Signals',
  signal_types: 'Signal Type Catalog',
  plane_physical: 'Physical Plane Φ',
  plane_mental: 'Mental Plane M',
  plane_spiritual: 'Spiritual Plane Σ',
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
  falsifiability: 'Falsifiability ×15',
  slashing: 'Slashing Conditions',
  unknown_provision: 'Unknown-Unknown Provision',
  adaptive_consensus: 'Adaptive Consensus',
  right_to_invisibility: 'Right to Invisibility',
  elder_wisdom: 'Elder Wisdom',
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

  // BTCP + CONTINUUM
  btcp_pipeline: 'BTCP Pipeline Status',
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

export default function Home() {
  const [activePage, setActivePage] = useState('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [theme, toggleTheme] = useTheme();

  // Health check for live indicator
  const { data: health } = useAPI('/api/v1/health', 5000);
  const isLive = health?.status === 'healthy';

  const PageComponent = PAGE_MAP[activePage] || DashboardPage;
  const pageTitle = PAGE_TITLES[activePage] || 'Dashboard';

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar
        activePage={activePage}
        onPageChange={setActivePage}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex items-center justify-between px-4 md:px-6 h-16 border-b border-border bg-card flex-shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden p-2 rounded-lg hover:bg-accent"
            >
              <Icons.Menu className="w-5 h-5" />
            </button>
            <div>
              <h1 className="text-lg font-bold">{pageTitle}</h1>
              <p className="text-xs text-muted-foreground hidden sm:block">
                TRION Protocol — Behavioral Truth Oracle · {PAGE_MAP && Object.keys(PAGE_MAP).length} pages wired to live API
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium ${isLive ? 'border-green-500/30 text-green-600 bg-green-500/5' : 'border-red-500/30 text-red-600 bg-red-500/5'}`}>
              <span className={`w-2 h-2 rounded-full ${isLive ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
              {isLive ? 'Live' : 'Offline'}
            </div>
            <span className="font-mono text-xs text-muted-foreground hidden md:block">
              <LiveClock />
            </span>
            <button
              onClick={toggleTheme}
              className="p-2 rounded-lg hover:bg-accent text-muted-foreground"
              title="Toggle theme"
            >
              {theme === 'dark' ? <Icons.Sun className="w-5 h-5" /> : <Icons.Moon className="w-5 h-5" />}
            </button>
          </div>
        </header>

        {/* Page content */}
        <div className="flex-1 overflow-y-auto bg-background p-4 md:p-6 lg:p-8">
          <PageComponent />
        </div>
      </div>
    </div>
  );
}
