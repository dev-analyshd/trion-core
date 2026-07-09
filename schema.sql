-- TRION Akashic Index — Complete TimescaleDB Schema
-- Whitepaper L2.0 → L2.7, L6.2, Three-Tier Storage, Merkle, BEO, Archetypes

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ── Event type enum ────────────────────────────────────────────────────────────
CREATE TYPE behavioral_event_type AS ENUM (
    'TRANSFER', 'SWAP', 'LIQUIDITY', 'STAKE', 'UNSTAKE', 'GOVERNANCE', 'PROPOSAL',
    'BORROW', 'REPAY', 'LIQUIDATE', 'BRIDGE', 'DEPLOY', 'UPGRADE', 'MINT', 'BURN',
    'ORACLE_UPDATE', 'MEV_CAPTURE', 'FLASH_LOAN', 'AIRDROP', 'CLAIM'
);

-- ── Data-Availability Streaming Table ────────────────────────────────────────
-- Flat, cursor-friendly projection of behavioral events consumed by
-- zg_da_streamer.py / zg_sync_daemon.py for 0G data-availability export.
-- Distinct from akashic_bh (the canonical L2.0 hot-tier store below): this
-- table exists purely as a sequential-id stream for external DA sync and is
-- populated by the same dual-write path as akashic_bh.
CREATE TABLE IF NOT EXISTS behavioral_events (
    id                  BIGSERIAL        PRIMARY KEY,
    entity_id           TEXT             NOT NULL,
    event_type          TEXT             NOT NULL,
    magnitude_norm      DOUBLE PRECISION NOT NULL CHECK (magnitude_norm >= 0 AND magnitude_norm <= 1),
    chain_id            INTEGER          NOT NULL,
    block_number        BIGINT           NOT NULL DEFAULT 0,
    sense_hash          TEXT             NOT NULL,
    antisense_hash      TEXT             NOT NULL,
    ts                  TIMESTAMPTZ      NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_behavioral_events_id      ON behavioral_events (id);
CREATE INDEX IF NOT EXISTS idx_behavioral_events_entity  ON behavioral_events (entity_id, ts DESC);

-- ── L2.0 Core: Akashic Behavioral Hash Table (HOT tier) ──────────────────────
-- Every BH ever generated is stored permanently. NO pruning. NO skipping.
CREATE TABLE IF NOT EXISTS akashic_bh (
    time                TIMESTAMPTZ      NOT NULL,
    gk_hash             BYTEA            NOT NULL, -- Genomic Key GK(t)
    prev_gk_hash        BYTEA            NOT NULL, -- GK(t-1): causal lineage (L4.3)
    bh_id               BYTEA            NOT NULL, -- Sense strand (L0.1)
    antisense           BYTEA            NOT NULL, -- Antisense strand
    entity_id           BYTEA            NOT NULL, -- Resolved BEO entity_id (L0.2)
    event_type          behavioral_event_type NOT NULL,
    magnitude_norm      DOUBLE PRECISION NOT NULL CHECK (magnitude_norm >= 0 AND magnitude_norm <= 1),
    entropy_delta       DOUBLE PRECISION NOT NULL CHECK (entropy_delta >= 0),
    chain_id            SMALLINT         NOT NULL,
    block_hash          BYTEA            NOT NULL,
    block_num           BIGINT           NOT NULL,
    context             JSONB            NOT NULL, -- CV(t)
    UNIQUE (time, bh_id)
);

SELECT create_hypertable('akashic_bh', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');
SELECT add_compression_policy('akashic_bh', INTERVAL '7 days') WHERE NOT EXISTS (
    SELECT 1 FROM timescaledb_information.jobs
    WHERE application_name LIKE 'Compression%' AND hypertable_name = 'akashic_bh'
);

CREATE INDEX IF NOT EXISTS idx_akashic_bh_entity   ON akashic_bh (entity_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_akashic_bh_block    ON akashic_bh (block_num);
CREATE INDEX IF NOT EXISTS idx_akashic_bh_gk       ON akashic_bh (gk_hash);
CREATE INDEX IF NOT EXISTS idx_akashic_bh_event    ON akashic_bh (event_type, time DESC);

-- Thermodynamic Conservation (L0.4): information cannot be destroyed
CREATE OR REPLACE FUNCTION prevent_akashic_deletions()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Thermodynamic Violation (L0.4): Information cannot be destroyed in the Akashic Index.';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS enforce_append_only ON akashic_bh;
CREATE TRIGGER enforce_append_only
BEFORE UPDATE OR DELETE ON akashic_bh
FOR EACH ROW EXECUTE FUNCTION prevent_akashic_deletions();

-- ── L0.2 BEO (Behavioral Entity Object) Registry ─────────────────────────────
-- Clusters raw wallet addresses → stable entity_id (>95% accuracy target)
CREATE TABLE IF NOT EXISTS beo_registry (
    entity_id           BYTEA            NOT NULL PRIMARY KEY,
    raw_addresses       TEXT[]           NOT NULL,
    first_seen          TIMESTAMPTZ      NOT NULL,
    last_seen           TIMESTAMPTZ      NOT NULL,
    cluster_confidence  DOUBLE PRECISION NOT NULL DEFAULT 1.0 CHECK (cluster_confidence BETWEEN 0 AND 1),
    archetype_id        INTEGER,
    akashic_depth       DOUBLE PRECISION NOT NULL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_beo_last_seen ON beo_registry (last_seen DESC);

-- ── L2.0 Vector Store — cold-boot restore source ─────────────────────────────
-- Stores the raw 128-dim behavioral vectors alongside their metadata.
-- This table is the authoritative source for rebuilding the FAISS index and
-- SQLite entity_records on a cold boot (container reset / filesystem wipe).
CREATE TABLE IF NOT EXISTS akashic_vectors (
    entity_id   TEXT             NOT NULL,
    ts          TIMESTAMPTZ      NOT NULL,
    vector      FLOAT8[]         NOT NULL,   -- 128-dim float32 behavioral vector
    magnitude   DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    entropy     DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    arch_sim    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    PRIMARY KEY (entity_id, ts)
);

CREATE INDEX IF NOT EXISTS idx_akashic_vectors_entity ON akashic_vectors (entity_id, ts DESC);

-- ── L2.1 Akashic Depth View ───────────────────────────────────────────────────
-- D(t) = accumulated depth of truth. Appended to every TRIONSignal.
CREATE OR REPLACE VIEW akashic_depth AS
SELECT
    entity_id,
    COUNT(*)                                               AS record_count,
    SUM(entropy_delta)                                     AS total_entropy,
    SUM(magnitude_norm * entropy_delta)                    AS raw_depth,
    MIN(time)                                              AS genesis_time,
    MAX(time)                                              AS last_seen,
    EXTRACT(EPOCH FROM (MAX(time) - MIN(time)))            AS lifespan_seconds,
    COUNT(*) / GREATEST(
        EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) / 86400.0, 1
    )                                                      AS daily_activity_rate
FROM akashic_bh
GROUP BY entity_id;

-- ── L2.2 Archetype Library ────────────────────────────────────────────────────
-- K-means centroids. 64 archetypes covering >90% of behavioral space.
CREATE TABLE IF NOT EXISTS archetype_library (
    archetype_id        SERIAL           PRIMARY KEY,
    centroid            FLOAT8[]         NOT NULL,   -- 128-dimensional centroid
    event_count         BIGINT           NOT NULL DEFAULT 0,
    coverage_pct        DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_at          TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

-- ── L2.3 Genesis Confidence ───────────────────────────────────────────────────
-- Tracks last activity for exponential decay: conf(t) = e^(-κ × inactivity_days)
CREATE TABLE IF NOT EXISTS genesis_confidence_log (
    time                TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    entity_id           BYTEA            NOT NULL,
    confidence          DOUBLE PRECISION NOT NULL,
    state               TEXT             NOT NULL,  -- ACTIVE / HIBERNATION / ABANDONED
    inactivity_days     DOUBLE PRECISION NOT NULL
);

SELECT create_hypertable('genesis_confidence_log', 'time', if_not_exists => TRUE);

-- ── L2.7 Trajectory Anomaly Log ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trajectory_anomaly_log (
    time                TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    entity_id           BYTEA            NOT NULL,
    alert               TEXT             NOT NULL,  -- NORMAL / TRAJECTORY_WARN / MANIPULATION_ALERT
    kl_divergence       DOUBLE PRECISION NOT NULL,
    archetype_id        INTEGER,
    genesis_locked      BOOLEAN          NOT NULL DEFAULT FALSE
);

SELECT create_hypertable('trajectory_anomaly_log', 'time', if_not_exists => TRUE);

-- ── Three-Tier: WARM Storage (90 days – 3 years) ─────────────────────────────
-- Merkle-compressed summaries. Verifiability preserved.
CREATE TABLE IF NOT EXISTS akashic_warm (
    date                DATE             NOT NULL,
    entity_id           BYTEA            NOT NULL,
    merkle_root         BYTEA            NOT NULL,
    event_count         INTEGER          NOT NULL,
    depth_snapshot      DOUBLE PRECISION NOT NULL,
    entropy_sum         DOUBLE PRECISION NOT NULL,
    archetype_id        INTEGER,
    PRIMARY KEY (date, entity_id)
);

-- ── Three-Tier: COLD Storage (3+ years) ──────────────────────────────────────
-- Annual summaries only. Privacy-preserving.
CREATE TABLE IF NOT EXISTS akashic_cold (
    year                SMALLINT         NOT NULL,
    entity_id           BYTEA            NOT NULL,
    annual_depth        DOUBLE PRECISION NOT NULL,
    annual_entropy      DOUBLE PRECISION NOT NULL,
    archetype_id        INTEGER,
    privacy_salt        BYTEA,           -- prevents re-identification
    PRIMARY KEY (year, entity_id)
);

-- ── Merkle Proof System ───────────────────────────────────────────────────────
-- Daily Merkle roots for O(log N) verifiable history reconstruction.
CREATE TABLE IF NOT EXISTS merkle_roots (
    date                DATE             NOT NULL PRIMARY KEY,
    root_hash           BYTEA            NOT NULL,
    leaf_count          INTEGER          NOT NULL,
    computed_at         TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

-- ── L6.2 Biological Rhythm Memory ────────────────────────────────────────────
-- Correlates market behavior with Circadian / Lunar / Seasonal phases.
CREATE TABLE IF NOT EXISTS biological_rhythm (
    time                TIMESTAMPTZ      NOT NULL,
    circadian_phase     TEXT             NOT NULL, -- DAWN/MORNING/AFTERNOON/EVENING/NIGHT
    lunar_phase         TEXT             NOT NULL, -- NEW_MOON/WAXING/FULL_MOON/WANING
    seasonal_phase      TEXT             NOT NULL, -- Q1_WINTER/Q2_SPRING/Q3_SUMMER/Q4_AUTUMN
    activity_score      DOUBLE PRECISION NOT NULL,
    anomaly_flag        BOOLEAN          NOT NULL DEFAULT FALSE
);

SELECT create_hypertable('biological_rhythm', 'time', if_not_exists => TRUE);

-- ── L3.4 Source Credibility ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS source_credibility (
    source_id           TEXT             NOT NULL PRIMARY KEY,
    accuracy_score      DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    falsification_count INTEGER          NOT NULL DEFAULT 0,
    conflict_events     INTEGER          NOT NULL DEFAULT 0,
    last_decay_at       TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    registered_at       TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

-- ── L4.9 Slashing Audit Trail ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS slashing_log (
    time                TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    validator_id        BYTEA            NOT NULL,
    slash_reason        TEXT             NOT NULL,
    slash_amount_wei    NUMERIC(78, 0)   NOT NULL,
    dispute_evidence    JSONB            NOT NULL,
    resolved_by         BYTEA            NOT NULL,
    gk_hash_at_slash    BYTEA            NOT NULL
);

SELECT create_hypertable('slashing_log', 'time', if_not_exists => TRUE);

-- ── L2.4 Resurrection Log ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS resurrection_log (
    time                TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    entity_id           BYTEA            NOT NULL,
    classification      TEXT             NOT NULL, -- CONTINUATION / MIGRATION / TAKEOVER_OR_ZOMBIE
    similarity          DOUBLE PRECISION NOT NULL,
    dormant_days        DOUBLE PRECISION NOT NULL
);

SELECT create_hypertable('resurrection_log', 'time', if_not_exists => TRUE);

-- ── Genesis Bootstrap Tracker (Zero Gaps mandate) ────────────────────────────
CREATE TABLE IF NOT EXISTS genesis_bootstrap_progress (
    id                  SERIAL           PRIMARY KEY,
    chain_id            SMALLINT         NOT NULL,
    start_block         BIGINT           NOT NULL,
    end_block           BIGINT           NOT NULL,
    last_indexed_block  BIGINT           NOT NULL DEFAULT 0,
    gap_count           INTEGER          NOT NULL DEFAULT 0,
    status              TEXT             NOT NULL DEFAULT 'RUNNING',  -- RUNNING/COMPLETE/FAILED
    started_at          TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);


-- ═══════════════════════════════════════════════════════════════════════════════
-- BTCP — Behavioral Transaction Continuity Protocol
-- Schema additions per BTCP Master Implementation Spec (April 2026)
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── BTCP Route type enum ──────────────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE btcp_route_type AS ENUM (
        'SINGLE_CHAIN', 'SPLIT', 'NETTING', 'PARALLEL', 'MULTI_HOP',
        'DEFERRED', 'BITP'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE btcp_escrow_state AS ENUM ('IDLE', 'HOLDING', 'RELEASED', 'REVERTED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE blo_status AS ENUM ('OPEN', 'PARTIALLY_FILLED', 'FILLED', 'EXPIRED', 'CANCELLED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE btcp_intent_status AS ENUM ('PENDING', 'ROUTING', 'EXECUTING', 'COMPLETED', 'FAILED', 'EXPIRED', 'RESURRECTED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE btcp_action_type AS ENUM ('SWAP', 'TRANSFER', 'LIQUIDITY', 'STAKE', 'BORROW');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE btcp_privacy_mode AS ENUM ('PUBLIC', 'ZK_CREDENTIAL', 'INVISIBLE');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE genesis_type AS ENUM ('ASSET_GENESIS', 'IDENTITY_GENESIS', 'SPONSORED_GENESIS');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── BTCP Intent Registry ──────────────────────────────────────────────────────
-- Every intent ever submitted. Append-only (thermodynamic conservation).
CREATE TABLE IF NOT EXISTS btcp_intent_registry (
    intent_hash         BYTEA            PRIMARY KEY,
    entity_id           BYTEA            NOT NULL REFERENCES beo_registry(entity_id),
    action              btcp_action_type NOT NULL,
    asset_in            BYTEA,           -- universal asset identifier
    asset_out           BYTEA,
    magnitude           NUMERIC(38,18)   NOT NULL,
    source_chain_id     BIGINT           NOT NULL,
    deadline_block      BIGINT,
    deadline_ts         TIMESTAMPTZ,
    max_gas_usd         NUMERIC(18,6),
    min_finality        SMALLINT         DEFAULT 1, -- 0=FAST 1=STANDARD 2=SECURE
    min_nl_score        NUMERIC(5,4)     DEFAULT 0.30,
    chain_pref          TEXT             DEFAULT 'OPTIMAL',
    privacy_mode        btcp_privacy_mode DEFAULT 'PUBLIC',
    btcp_version        TEXT             NOT NULL DEFAULT '1.0.0',
    nonce               BIGINT           NOT NULL DEFAULT 0,
    route_selected      btcp_route_type,
    status              btcp_intent_status DEFAULT 'PENDING',
    btcp_score          DOUBLE PRECISION,
    created_at          TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    routed_at           TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_btcp_intent_entity   ON btcp_intent_registry (entity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_btcp_intent_status   ON btcp_intent_registry (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_btcp_intent_assets   ON btcp_intent_registry (asset_in, asset_out);

-- ── BTCP Routes ───────────────────────────────────────────────────────────────
-- Records every executed cross-chain route. Linked to intent.
CREATE TABLE IF NOT EXISTS btcp_routes (
    route_id                BYTEA        PRIMARY KEY,
    intent_hash             BYTEA        NOT NULL REFERENCES btcp_intent_registry(intent_hash),
    route_type              btcp_route_type NOT NULL,
    anchor_bh               BYTEA        NOT NULL,
    execution_bh            BYTEA,
    anchor_chain            BIGINT       NOT NULL,
    execution_chain         BIGINT       NOT NULL,
    entity_id               BYTEA        NOT NULL,
    counterparty_entity_id  BYTEA,       -- set for NETTING routes
    btcp_score              DOUBLE PRECISION NOT NULL,
    nl_score                DOUBLE PRECISION,
    gas_saved_vs_bridge     NUMERIC(18,6),
    gas_saved_vs_single     NUMERIC(18,6),
    gas_total_usd           NUMERIC(18,6),
    beo_continuity_score    DOUBLE PRECISION,
    cc_coherence            DOUBLE PRECISION,
    mf_score                DOUBLE PRECISION,
    consensus_hhi           DOUBLE PRECISION,
    coherence_at_emission   DOUBLE PRECISION,
    travel_rule_proof       BYTEA,       -- ZK proof hash if applicable
    btcp_version            TEXT         NOT NULL DEFAULT '1.0.0',
    status                  TEXT         NOT NULL DEFAULT 'PENDING',
    failure_cause           TEXT,        -- EXTERNAL | ENTITY | AMBIGUOUS
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finalized_at            TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_btcp_routes_entity  ON btcp_routes (entity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_btcp_routes_chains  ON btcp_routes (anchor_chain, execution_chain);
CREATE INDEX IF NOT EXISTS idx_btcp_routes_status  ON btcp_routes (status);

-- ── BTCP Escrow States ────────────────────────────────────────────────────────
-- Per-chain escrow record. Two per route (anchor chain + execution chain).
CREATE TABLE IF NOT EXISTS btcp_escrow_states (
    escrow_id           BYTEA            PRIMARY KEY,
    route_id            BYTEA            NOT NULL REFERENCES btcp_routes(route_id),
    entity_id           BYTEA            NOT NULL,
    chain_id            BIGINT           NOT NULL,
    contract_address    TEXT,            -- BTCP_ESCROW contract address on this chain
    amount              NUMERIC(38,18)   NOT NULL,
    token_address       TEXT,            -- null = native ETH
    lock_block          BIGINT           NOT NULL,
    timeout_blocks      BIGINT           NOT NULL DEFAULT 300,
    state               btcp_escrow_state NOT NULL DEFAULT 'HOLDING',
    destination         TEXT             NOT NULL,
    tx_hash_lock        TEXT,
    tx_hash_release     TEXT,
    created_at          TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_escrow_route    ON btcp_escrow_states (route_id);
CREATE INDEX IF NOT EXISTS idx_escrow_state    ON btcp_escrow_states (state);

-- ── BLO Orders (Behavioral Limit Orders) ─────────────────────────────────────
-- Intent posted as standing order. Persistent until filled or expired.
CREATE TABLE IF NOT EXISTS blo_orders (
    commitment_hash         BYTEA        PRIMARY KEY,
    entity_id               BYTEA        NOT NULL,
    intent_hash             BYTEA        NOT NULL REFERENCES btcp_intent_registry(intent_hash),
    asset_in                BYTEA        NOT NULL,
    asset_out               BYTEA        NOT NULL,
    source_chain_id         BIGINT       NOT NULL,
    target_chain_id         BIGINT,
    magnitude               NUMERIC(38,18) NOT NULL,
    filled_amount           NUMERIC(38,18) NOT NULL DEFAULT 0,
    expiry_block            BIGINT       NOT NULL,
    status                  blo_status   NOT NULL DEFAULT 'OPEN',
    btcp_score_at_post      DOUBLE PRECISION,
    behavioral_proof_root   BYTEA,
    akashic_depth           DOUBLE PRECISION,
    scheduled_activation    BIGINT,      -- for BRT-scheduled BLOs
    brt_confidence          DOUBLE PRECISION,
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    filled_at               TIMESTAMPTZ,
    expired_at              TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_blo_open        ON blo_orders (status, asset_in, asset_out);
CREATE INDEX IF NOT EXISTS idx_blo_entity      ON blo_orders (entity_id);
CREATE INDEX IF NOT EXISTS idx_blo_expiry      ON blo_orders (expiry_block) WHERE status = 'OPEN';

-- ── BITP Clipboard ────────────────────────────────────────────────────────────
-- CUT phase: behavioral commitment posted awaiting MATCH.
CREATE TABLE IF NOT EXISTS bitp_clipboard (
    commitment_hash         BYTEA        PRIMARY KEY,
    entity_id               BYTEA        NOT NULL,
    asset_x                 BYTEA        NOT NULL,    -- held asset (stays on chain_a)
    asset_y                 BYTEA        NOT NULL,    -- desired asset (on chain_b)
    chain_a                 BIGINT       NOT NULL,    -- entity's current chain
    chain_b                 BIGINT       NOT NULL,    -- desired target chain
    magnitude               NUMERIC(38,18) NOT NULL,
    behavioral_proof_root   BYTEA,
    intent_hash             BYTEA        NOT NULL REFERENCES btcp_intent_registry(intent_hash),
    valuation_x             DOUBLE PRECISION,         -- TRION VALUATION at post time
    valuation_y             DOUBLE PRECISION,
    price_tolerance         DOUBLE PRECISION NOT NULL DEFAULT 0.02, -- 2% behavioral price tolerance
    status                  TEXT         NOT NULL DEFAULT 'POSTED',  -- POSTED | MATCHED | FILLED | EXPIRED
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    matched_at              TIMESTAMPTZ,
    counterparty_hash       BYTEA,
    blo_created             BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_bitp_status     ON bitp_clipboard (status, asset_x, asset_y);
CREATE INDEX IF NOT EXISTS idx_bitp_entity     ON bitp_clipboard (entity_id);

-- ── Shadow Observations ───────────────────────────────────────────────────────
-- OOA: indirect observations of non-integrated / hostile chains.
CREATE TABLE IF NOT EXISTS shadow_observations (
    id                      BIGSERIAL    PRIMARY KEY,
    observed_chain_id       BIGINT       NOT NULL,  -- chain being shadowed
    source_chain_id         BIGINT       NOT NULL,  -- integrated chain providing shadow
    observation_type        TEXT         NOT NULL,  -- TRANSFER | ORACLE_UPDATE | BRIDGE_EVENT | DEX_TRADE | GOVERNANCE_REF
    event_hash              BYTEA        NOT NULL,
    confidence_weight       DOUBLE PRECISION NOT NULL DEFAULT 0.7,
    diversity_factor        DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    shadow_bh               BYTEA,                  -- computed shadow behavioral hash
    block_num               BIGINT,
    observed_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shadow_chain    ON shadow_observations (observed_chain_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_shadow_conf     ON shadow_observations (observed_chain_id, confidence_weight DESC);

-- ── Genesis Commitments ───────────────────────────────────────────────────────
-- Null-state resolution: first behavior records for new entities/assets.
CREATE TABLE IF NOT EXISTS genesis_commitments (
    commitment_id           BYTEA        PRIMARY KEY,
    genesis_type            genesis_type NOT NULL,
    entity_id               BYTEA        NOT NULL,
    sponsor_entity_id       BYTEA,                  -- set for SPONSORED_GENESIS
    stake_bond              NUMERIC(38,18),          -- locked TRION tokens
    conf_genesis            DOUBLE PRECISION NOT NULL DEFAULT 0.10,
    conf_sponsor            DOUBLE PRECISION,        -- inherited from sponsor
    active_sponsored_count  INTEGER      NOT NULL DEFAULT 0,
    scrutiny_multiplier     DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    slash_amount            NUMERIC(38,18) NOT NULL DEFAULT 0,
    status                  TEXT         NOT NULL DEFAULT 'ACTIVE', -- ACTIVE | SLASHED | RELEASED | EXPIRED
    accountability_window_days INTEGER   NOT NULL DEFAULT 180,
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    resolved_at             TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_genesis_entity  ON genesis_commitments (entity_id);
CREATE INDEX IF NOT EXISTS idx_genesis_sponsor ON genesis_commitments (sponsor_entity_id) WHERE sponsor_entity_id IS NOT NULL;

-- ── BTCP Version Registry ─────────────────────────────────────────────────────
-- Per-chain adapter version tracking for protocol upgrade routing.
CREATE TABLE IF NOT EXISTS btcp_version_registry (
    chain_id                BIGINT       NOT NULL,
    adapter_version         TEXT         NOT NULL,    -- semver
    min_verifier_version    TEXT         NOT NULL DEFAULT '1.0.0',
    feature_flags           JSONB        NOT NULL DEFAULT '{}',
    registered_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_seen_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_deprecated           BOOLEAN      NOT NULL DEFAULT FALSE,
    PRIMARY KEY (chain_id, adapter_version)
);

-- ── OOA Chain Confidence ──────────────────────────────────────────────────────
-- Observation-Only Anchoring confidence per chain over time.
CREATE TABLE IF NOT EXISTS ooa_chain_confidence (
    chain_id                BIGINT       NOT NULL,
    observation_depth       BIGINT       NOT NULL DEFAULT 0,  -- blocks observed
    ooa_conf                DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    ooa_penalty_factor      DOUBLE PRECISION NOT NULL DEFAULT 0.70,
    conf_max                DOUBLE PRECISION NOT NULL DEFAULT 0.85,
    last_updated            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (chain_id)
);

-- ── Intent Aggregation Pools ──────────────────────────────────────────────────
-- IAP: pools of same-direction intents before execution.
CREATE TABLE IF NOT EXISTS intent_pools (
    pool_id                 BYTEA        PRIMARY KEY,
    asset_in                BYTEA        NOT NULL,
    asset_out               BYTEA        NOT NULL,
    source_chain_id         BIGINT       NOT NULL,
    total_value             NUMERIC(38,18) NOT NULL DEFAULT 0,
    participant_count       INTEGER      NOT NULL DEFAULT 0,
    window_deadline_block   BIGINT       NOT NULL,
    status                  TEXT         NOT NULL DEFAULT 'OPEN', -- OPEN | EXECUTING | COMPLETED
    gas_total_usd           NUMERIC(18,6),
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    executed_at             TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS intent_pool_participants (
    pool_id                 BYTEA        NOT NULL REFERENCES intent_pools(pool_id),
    entity_id               BYTEA        NOT NULL,
    intent_hash             BYTEA        NOT NULL REFERENCES btcp_intent_registry(intent_hash),
    contribution            NUMERIC(38,18) NOT NULL,
    gas_share               NUMERIC(18,6),
    PRIMARY KEY (pool_id, entity_id)
);

-- ── Behavioral State Channels ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS behavioral_state_channels (
    channel_id              BYTEA        PRIMARY KEY,
    entity_a                BYTEA        NOT NULL,
    entity_b                BYTEA        NOT NULL,
    chain_a                 BIGINT       NOT NULL,
    chain_b                 BIGINT       NOT NULL,
    collateral_a            NUMERIC(38,18) NOT NULL DEFAULT 0,
    collateral_b            NUMERIC(38,18) NOT NULL DEFAULT 0,
    interaction_count       BIGINT       NOT NULL DEFAULT 0,
    akashic_record_root     BYTEA,
    state                   TEXT         NOT NULL DEFAULT 'OPEN', -- OPEN | CLOSING | CLOSED
    opened_at               TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    closed_at               TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_bsc_entities   ON behavioral_state_channels (entity_a, entity_b);

-- ═══════════════════════════════════════════════════════════════════════════════
-- BTCP Extension Tables — GAP 1 (Token Economics), GAP 7 (Cross-Chain Messages),
-- GAP 3 (MF Evidence), J1 (Sanctions Oracle)
-- April 2026 additions per BTCP_27_Resolutions, BTCP_15_Final_Resolutions
-- ═══════════════════════════════════════════════════════════════════════════════

-- ── TRION Token Economics (GAP 1) ─────────────────────────────────────────────
-- Tracks token supply, utility sinks, and staking state per epoch.
CREATE TABLE IF NOT EXISTS trion_token_economics (
    epoch               BIGINT       NOT NULL PRIMARY KEY,
    epoch_start_ts      TIMESTAMPTZ  NOT NULL,
    epoch_end_ts        TIMESTAMPTZ,
    -- Supply model
    total_supply        NUMERIC(38,18) NOT NULL DEFAULT 0,
    circulating_supply  NUMERIC(38,18) NOT NULL DEFAULT 0,
    staked_supply       NUMERIC(38,18) NOT NULL DEFAULT 0,
    -- Utility sinks
    burned_this_epoch   NUMERIC(38,18) NOT NULL DEFAULT 0,  -- fee burns
    slashed_this_epoch  NUMERIC(38,18) NOT NULL DEFAULT 0,
    rewarded_validators NUMERIC(38,18) NOT NULL DEFAULT 0,  -- validator rewards
    rewarded_routes     NUMERIC(38,18) NOT NULL DEFAULT 0,  -- btcp_route_reward
    genesis_bonds       NUMERIC(38,18) NOT NULL DEFAULT 0,  -- locked in genesis stakes
    -- Network stats
    routes_this_epoch   BIGINT       NOT NULL DEFAULT 0,
    intents_this_epoch  BIGINT       NOT NULL DEFAULT 0,
    avg_btcp_score      DOUBLE PRECISION,
    coverage_state      TEXT         NOT NULL DEFAULT 'NOMINAL', -- NOMINAL | ALERT | CRITICAL
    emergency_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    recorded_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── Validator Coverage Tracking (C1/C2) ───────────────────────────────────────
-- Tracks per-validator coverage state for dynamic min_validators and emergency bonus.
CREATE TABLE IF NOT EXISTS validator_coverage (
    validator_address   TEXT         NOT NULL,
    chain_id            BIGINT       NOT NULL,
    routes_signed       BIGINT       NOT NULL DEFAULT 0,
    routes_available    BIGINT       NOT NULL DEFAULT 0,
    coverage_rate       DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    uptime_7d           DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    effective_weight    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    last_active_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (validator_address, chain_id)
);

CREATE INDEX IF NOT EXISTS idx_validator_coverage_rate ON validator_coverage (coverage_rate DESC);

-- ── Cross-Chain Message Log (GAP 7) ───────────────────────────────────────────
-- Records all cross-chain messages for replay prevention audit trail.
CREATE TABLE IF NOT EXISTS btcp_cross_chain_messages (
    message_id          BYTEA        PRIMARY KEY,   -- SHA3 replay-prevention ID
    msg_type            TEXT         NOT NULL,       -- IntentBroadcast | EscrowLockConfirm | etc.
    sender_entity_id    BYTEA        NOT NULL,
    sender_chain        BIGINT       NOT NULL,
    target_chain        BIGINT       NOT NULL,
    nonce               BIGINT       NOT NULL,
    expiry_block        BIGINT       NOT NULL,
    expiry_ts           TIMESTAMPTZ  NOT NULL,
    payload_hash        BYTEA        NOT NULL,
    btcp_version        TEXT         NOT NULL DEFAULT '1.0.0',
    status              TEXT         NOT NULL DEFAULT 'ACCEPTED', -- ACCEPTED | REJECTED | EXPIRED
    reject_reason       TEXT,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_msg_sender_chain ON btcp_cross_chain_messages (sender_entity_id, sender_chain, nonce DESC);
CREATE INDEX IF NOT EXISTS idx_msg_status       ON btcp_cross_chain_messages (status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_msg_nonce_unique ON btcp_cross_chain_messages (sender_entity_id, sender_chain, target_chain, nonce);

-- ── Manipulation Fingerprint Evidence Log (GAP 3) ─────────────────────────────
-- Stores per-analysis MF evidence for audit, appeals, and ML training.
CREATE TABLE IF NOT EXISTS mf_evidence_log (
    id                  BIGSERIAL    PRIMARY KEY,
    entity_id           BYTEA        NOT NULL,
    chain_id            BIGINT       NOT NULL,
    intent_hash         BYTEA,
    -- Composite score
    mf_score_total      DOUBLE PRECISION NOT NULL,
    dominant_type       TEXT         NOT NULL, -- Clean | Sandwich | WashTrading | ...
    alert_count         INTEGER      NOT NULL DEFAULT 0,
    -- Per-type scores
    sandwich_score      DOUBLE PRECISION NOT NULL DEFAULT 0,
    wash_score          DOUBLE PRECISION NOT NULL DEFAULT 0,
    oracle_score        DOUBLE PRECISION NOT NULL DEFAULT 0,
    layering_score      DOUBLE PRECISION NOT NULL DEFAULT 0,
    spoofing_score      DOUBLE PRECISION NOT NULL DEFAULT 0,
    cross_proto_score   DOUBLE PRECISION NOT NULL DEFAULT 0,
    stat_anomaly_score  DOUBLE PRECISION NOT NULL DEFAULT 0,
    -- Context
    hhi_counterparty    DOUBLE PRECISION,    -- A5: counterparty HHI
    d_effective         DOUBLE PRECISION,    -- 1 - HHI
    blocked_routing     BOOLEAN      NOT NULL DEFAULT FALSE,
    analyzed_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

SELECT create_hypertable('mf_evidence_log', 'analyzed_at', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_mf_entity   ON mf_evidence_log (entity_id, analyzed_at DESC);
CREATE INDEX IF NOT EXISTS idx_mf_score    ON mf_evidence_log (mf_score_total DESC, analyzed_at DESC);
CREATE INDEX IF NOT EXISTS idx_mf_type     ON mf_evidence_log (dominant_type, analyzed_at DESC);

-- ── Sanctions Oracle (J1) ─────────────────────────────────────────────────────
-- AWA-protected OFAC/EU/UN sanctions list. Append-only audit trail.
DO $$ BEGIN
    CREATE TYPE sanctions_list_source AS ENUM ('OFAC_SDN', 'EU_CONSOLIDATED', 'UN_CONSOLIDATED', 'TRION_INTERNAL');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS sanctions_registry (
    address             TEXT         NOT NULL,
    list_source         sanctions_list_source NOT NULL,
    confidence          DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    flagged_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    delisted_at         TIMESTAMPTZ,
    oracle_signature    BYTEA,       -- AWA-protected oracle signature hash
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    PRIMARY KEY (address, list_source)
);

CREATE INDEX IF NOT EXISTS idx_sanctions_active ON sanctions_registry (address) WHERE is_active = TRUE;

-- Append-only enforcement: sanctions records cannot be deleted (only delisted)
CREATE OR REPLACE FUNCTION prevent_sanctions_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Sanctions registry is append-only (AWA-protected). Use deactivate instead of DELETE.';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS sanctions_append_only ON sanctions_registry;
CREATE TRIGGER sanctions_append_only
BEFORE DELETE ON sanctions_registry
FOR EACH ROW EXECUTE FUNCTION prevent_sanctions_delete();

-- ── BTCP Route Rewards Log (Fix 4) ───────────────────────────────────────────
-- Tracks validator route rewards per epoch including coverage bonus.
CREATE TABLE IF NOT EXISTS btcp_route_rewards (
    id                  BIGSERIAL    PRIMARY KEY,
    epoch               BIGINT       NOT NULL,
    validator_address   TEXT         NOT NULL,
    route_id            BYTEA,
    base_reward         NUMERIC(18,6) NOT NULL DEFAULT 0,
    coverage_bonus_factor DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    emergency_multiplier  DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    final_reward        NUMERIC(18,6) NOT NULL DEFAULT 0,
    diversity_weight    DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    coverage_rate       DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    uptime_7d           DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    rewarded_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rewards_validator ON btcp_route_rewards (validator_address, epoch DESC);
CREATE INDEX IF NOT EXISTS idx_rewards_epoch     ON btcp_route_rewards (epoch);

