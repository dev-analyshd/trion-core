export interface HealthData {
  status: string;
  oracle: string;
  network: string;
  chain_id: number;
  contract: string;
  block_number: number;
  dynamic_threshold: number;
  market_volatility: number;
  total_signals_onchain: number;
  timestamp: number;
}

export interface StatsData {
  network: string;
  chain_id: number;
  oracle_address: string;
  block_number: number;
  indexed_vectors: number;
  total_signals_onchain: number;
  dynamic_threshold: number;
  market_volatility: number;
  timestamp: number;
}

export interface FeedEntry {
  entity_id: string;
  short_id: string;
  archetype: string;
  coherence_score: number;
  coherent: boolean;
  threshold: number;
  limiting_plane: string;
  timestamp: number;
  // Protocol health events (kind === "PROTOCOL_HEALTH")
  kind?: string;
  grade?: string;
  threat_level?: string;
  attack_probability?: number;
  protocol_name?: string;
  change_reason?: string;
  prev_score?: number;
  dc_score?: number;
  sub_entity_count?: number;
  recommendations?: string[];
}

export interface FeedData {
  feed: FeedEntry[];
  count?: number;
}

export interface Chain {
  id: string;
  name: string;
  chain_id: number;
  vm: string;
  status: string;
  color: string;
  note: string;
}

export interface ChainsData {
  chains: Chain[];
  total?: number;
}

export interface LeaderboardEntry {
  rank: number;
  entity_id: string;
  label: string;
  archetype: string;
  coherence_score: number;
  coherent: boolean;
  threshold: number;
  signal_count: number;
  mf_score: number;
  vault_access: boolean;
  plane_breakdown: {
    physical: number;
    mental: number;
    spiritual: number;
    conscious: number;
    anima: number;
  };
}

export interface LeaderboardData {
  leaderboard: LeaderboardEntry[];
  dynamic_threshold: number;
}

export interface SignalData {
  entity_id: string;
  archetype: string;
  coherence_score: number;
  coherent: boolean;
  signal_type: string;
  silence: boolean;
  silence_gap: number;
  limiting_plane: string;
  threshold: number;
  market_volatility: number;
  coherence_trend: string;
  plane_breakdown: {
    physical: number;
    mental: number;
    spiritual: number;
    conscious: number;
    anima: number;
  };
  plane_contributions: {
    Physical: number;
    Mental: number;
    Spiritual: number;
    Conscious: number;
    ANIMA: number;
  };
  genomic_signature: string;
  signal_id: string;
  timestamp?: number;
}

export interface Archetype {
  id: string;
  name: string;
  description: string;
  risk_level: string;
  investment_signal: string;
  investment_confidence: number;
  lifecycle: string[];
  examples: string[];
}

export interface ArchetypesData {
  archetypes: Archetype[];
}
