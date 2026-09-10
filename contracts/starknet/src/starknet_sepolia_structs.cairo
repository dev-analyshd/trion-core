// ═══════════════════════════════════════════════════════════
//   TRION Protocol — Starknet Sepolia Contracts
//   Chain ID: SN_SEPOLIA (0x534e5f5345504f4c4941)
// ═══════════════════════════════════════════════════════════

// The full BTCP contract suite (escrow/intent/route/BIRP) lives in the
// canonical crate at contracts/starknet/src/ — the duplicate src/cairo/
// copies were removed in the dedup cleanup, and this crate carries only
// the Sepolia-deployed trio below.

// ─── Shared structs ─────────────────────────────────────────

/// BEO behavioral score stored on-chain.
/// All float scores are scaled ×10000 to fit in u64.
#[derive(Drop, Serde, Copy, starknet::Store)]
pub struct BEOScore {
    /// ANIMA score: PCR×HA×CA, scaled 0–10000
    pub anima_score: u64,
    /// Genesis confidence: 1-e^(-λD), scaled 0–10000
    pub genesis_confidence: u64,
    /// 0=CLEAR, 1=WARN (KL>0.15), 2=MANIPULATION (KL>0.35)
    pub trajectory_alert: u8,
    /// FAISS archetype cluster 0–63
    pub archetype_id: u8,
    /// Akashic depth D(t)
    pub akashic_depth: u64,
    /// True if classified as GENUINE_CONTINUATION resurrection
    pub is_resurrection: bool,
    /// Dormancy type as short felt252: 'ACTIVE','ABANDONED', etc.
    pub dormancy_type: felt252,
    /// Block timestamp of last update
    pub last_updated: u64,
    /// Sequential update count for this BEO
    pub update_count: u64,
}

/// BEO identity binding for a Starknet wallet.
#[derive(Drop, Serde, Copy, starknet::Store)]
pub struct BEOIdentity {
    /// SHA3-256 BEO fingerprint (truncated to felt252)
    pub beo_id: felt252,
    /// 0=BOOTSTRAP (Conf<0.30), 1=GENESIS (0.30-0.80), 2=MATURITY (>0.80)
    pub tier: u8,
    /// Genesis confidence in basis points (0–10000)
    pub genesis_confidence_bp: u64,
    /// Block timestamp when attested
    pub attested_at: u64,
    /// Whether this attestation is currently active
    pub active: bool,
}

// ─── TRIONOracle interface ───────────────────────────────────

#[starknet::interface]
pub trait ITRIONOracle<TContractState> {
    fn update_score(
        ref self: TContractState,
        beo_id: felt252,
        anima_score: u64,
        genesis_confidence: u64,
        trajectory_alert: u8,
        archetype_id: u8,
        akashic_depth: u64,
        is_resurrection: bool,
        dormancy_type: felt252,
    );
    fn get_score(self: @TContractState, beo_id: felt252) -> BEOScore;
    fn get_owner(self: @TContractState) -> starknet::ContractAddress;
    fn transfer_ownership(ref self: TContractState, new_owner: starknet::ContractAddress);
    fn get_score_count(self: @TContractState) -> u64;
    fn get_last_updated(self: @TContractState, beo_id: felt252) -> u64;
}

// ─── TRIONOracle contract ────────────────────────────────────
//
// Stores BEO behavioral scores on-chain. Any dApp on Starknet
// can call get_score(beo_id) to read ANIMA, genesis confidence,
// trajectory alert, and archetype. Only the owner can push updates.

#[starknet::contract]
pub mod TRIONOracle {
    use super::{BEOScore, ITRIONOracle};
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp,
        storage::{
            Map, StorageMapReadAccess, StorageMapWriteAccess,
            StoragePointerReadAccess, StoragePointerWriteAccess,
        },
    };

    #[storage]
    struct Storage {
        owner: ContractAddress,
        scores: Map<felt252, BEOScore>,
        score_count: u64,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        ScoreUpdated: ScoreUpdated,
        OwnershipTransferred: OwnershipTransferred,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ScoreUpdated {
        #[key]
        pub beo_id: felt252,
        pub anima_score: u64,
        pub trajectory_alert: u8,
        pub archetype_id: u8,
        pub timestamp: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct OwnershipTransferred {
        pub previous_owner: ContractAddress,
        pub new_owner: ContractAddress,
    }

    #[constructor]
    fn constructor(ref self: ContractState, owner: ContractAddress) {
        self.owner.write(owner);
        self.score_count.write(0);
    }

    #[abi(embed_v0)]
    impl TRIONOracleImpl of ITRIONOracle<ContractState> {
        fn update_score(
            ref self: ContractState,
            beo_id: felt252,
            anima_score: u64,
            genesis_confidence: u64,
            trajectory_alert: u8,
            archetype_id: u8,
            akashic_depth: u64,
            is_resurrection: bool,
            dormancy_type: felt252,
        ) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'TRION: unauthorized');
            assert(anima_score <= 10000_u64, 'TRION: anima out of range');
            assert(genesis_confidence <= 10000_u64, 'TRION: gc out of range');
            assert(trajectory_alert <= 2_u8, 'TRION: alert level invalid');
            assert(archetype_id <= 63_u8, 'TRION: archetype out of range');

            let ts = get_block_timestamp();
            let existing = self.scores.read(beo_id);
            let new_count = existing.update_count + 1;

            let score = BEOScore {
                anima_score,
                genesis_confidence,
                trajectory_alert,
                archetype_id,
                akashic_depth,
                is_resurrection,
                dormancy_type,
                last_updated: ts,
                update_count: new_count,
            };

            if existing.update_count == 0 {
                let current = self.score_count.read();
                self.score_count.write(current + 1);
            }

            self.scores.write(beo_id, score);

            self.emit(ScoreUpdated { beo_id, anima_score, trajectory_alert, archetype_id, timestamp: ts });
        }

        fn get_score(self: @ContractState, beo_id: felt252) -> BEOScore {
            self.scores.read(beo_id)
        }

        fn get_owner(self: @ContractState) -> ContractAddress {
            self.owner.read()
        }

        fn transfer_ownership(ref self: ContractState, new_owner: ContractAddress) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'TRION: unauthorized');
            let old_owner = self.owner.read();
            self.owner.write(new_owner);
            self.emit(OwnershipTransferred { previous_owner: old_owner, new_owner });
        }

        fn get_score_count(self: @ContractState) -> u64 {
            self.score_count.read()
        }

        fn get_last_updated(self: @ContractState, beo_id: felt252) -> u64 {
            self.scores.read(beo_id).last_updated
        }
    }
}

// ─── BEOAttestation interface ────────────────────────────────

#[starknet::interface]
pub trait IBEOAttestation<TContractState> {
    fn attest(
        ref self: TContractState,
        wallet: starknet::ContractAddress,
        beo_id: felt252,
        tier: u8,
        genesis_confidence_bp: u64,
    );
    fn revoke(ref self: TContractState, wallet: starknet::ContractAddress);
    fn get_beo(self: @TContractState, wallet: starknet::ContractAddress) -> BEOIdentity;
    fn get_wallet(self: @TContractState, beo_id: felt252) -> starknet::ContractAddress;
    fn is_attested(self: @TContractState, wallet: starknet::ContractAddress) -> bool;
    fn get_attester(self: @TContractState) -> starknet::ContractAddress;
    fn set_attester(ref self: TContractState, new_attester: starknet::ContractAddress);
    fn total_attestations(self: @TContractState) -> u64;
}

// ─── BEOAttestation contract ─────────────────────────────────
//
// Binds Starknet wallet addresses to TRION BEO identity fingerprints
// and credibility tiers. Compatible with native AA (Argent/Braavos).

#[starknet::contract]
pub mod BEOAttestation {
    use super::{BEOIdentity, IBEOAttestation};
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp,
        storage::{
            Map, StorageMapReadAccess, StorageMapWriteAccess,
            StoragePointerReadAccess, StoragePointerWriteAccess,
        },
    };

    #[storage]
    struct Storage {
        attester: ContractAddress,
        wallet_to_beo: Map<ContractAddress, BEOIdentity>,
        beo_to_wallet: Map<felt252, ContractAddress>,
        total: u64,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        Attested: Attested,
        Revoked: Revoked,
        AttesterChanged: AttesterChanged,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Attested {
        #[key]
        pub wallet: ContractAddress,
        #[key]
        pub beo_id: felt252,
        pub tier: u8,
        pub genesis_confidence_bp: u64,
        pub timestamp: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Revoked {
        #[key]
        pub wallet: ContractAddress,
        pub beo_id: felt252,
        pub timestamp: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct AttesterChanged {
        pub old_attester: ContractAddress,
        pub new_attester: ContractAddress,
    }

    #[constructor]
    fn constructor(ref self: ContractState, attester: ContractAddress) {
        self.attester.write(attester);
        self.total.write(0);
    }

    #[abi(embed_v0)]
    impl BEOAttestationImpl of IBEOAttestation<ContractState> {
        fn attest(
            ref self: ContractState,
            wallet: ContractAddress,
            beo_id: felt252,
            tier: u8,
            genesis_confidence_bp: u64,
        ) {
            let caller = get_caller_address();
            assert(caller == self.attester.read(), 'BEO: unauthorized attester');
            assert(tier <= 2_u8, 'BEO: invalid tier');
            assert(genesis_confidence_bp <= 10000_u64, 'BEO: gc_bp out of range');

            let ts = get_block_timestamp();
            let was_active = self.wallet_to_beo.read(wallet).active;

            let identity = BEOIdentity {
                beo_id,
                tier,
                genesis_confidence_bp,
                attested_at: ts,
                active: true,
            };

            self.wallet_to_beo.write(wallet, identity);
            self.beo_to_wallet.write(beo_id, wallet);

            if !was_active {
                let current = self.total.read();
                self.total.write(current + 1);
            }

            self.emit(Attested { wallet, beo_id, tier, genesis_confidence_bp, timestamp: ts });
        }

        fn revoke(ref self: ContractState, wallet: ContractAddress) {
            let caller = get_caller_address();
            assert(caller == self.attester.read(), 'BEO: unauthorized attester');

            let existing = self.wallet_to_beo.read(wallet);
            assert(existing.active, 'BEO: not attested');

            let ts = get_block_timestamp();
            let beo_id = existing.beo_id;

            let revoked = BEOIdentity {
                beo_id: existing.beo_id,
                tier: existing.tier,
                genesis_confidence_bp: existing.genesis_confidence_bp,
                attested_at: existing.attested_at,
                active: false,
            };
            self.wallet_to_beo.write(wallet, revoked);
            self.emit(Revoked { wallet, beo_id, timestamp: ts });
        }

        fn get_beo(self: @ContractState, wallet: ContractAddress) -> BEOIdentity {
            self.wallet_to_beo.read(wallet)
        }

        fn get_wallet(self: @ContractState, beo_id: felt252) -> ContractAddress {
            self.beo_to_wallet.read(beo_id)
        }

        fn is_attested(self: @ContractState, wallet: ContractAddress) -> bool {
            self.wallet_to_beo.read(wallet).active
        }

        fn get_attester(self: @ContractState) -> ContractAddress {
            self.attester.read()
        }

        fn set_attester(ref self: ContractState, new_attester: ContractAddress) {
            let caller = get_caller_address();
            assert(caller == self.attester.read(), 'BEO: unauthorized attester');
            let old = self.attester.read();
            self.attester.write(new_attester);
            self.emit(AttesterChanged { old_attester: old, new_attester });
        }

        fn total_attestations(self: @ContractState) -> u64 {
            self.total.read()
        }
    }
}

// ─── BTCFiGuard interface ─────────────────────────────────────────────────
//
// Composable anti-sybil module for BTCFi protocols.
// Call assess_risk(beo_id) before accepting BTC collateral deposits.
//
// Risk tiers: 0=SAFE, 1=CAUTION, 2=HIGH_RISK, 3=HOSTILE

#[starknet::interface]
pub trait IBTCFiGuard<TContractState> {
    /// Primary integration point: returns 0=SAFE, 1=CAUTION, 2=HIGH_RISK, 3=HOSTILE
    fn assess_risk(self: @TContractState, beo_id: felt252) -> u8;
    /// Batch assessment for multiple BEO IDs.
    fn batch_assess(self: @TContractState, beo_ids: Span<felt252>) -> Array<u8>;
    /// Direct tier computation without oracle lookup.
    fn score_to_tier(
        self: @TContractState,
        anima_score: u64,
        trajectory_alert: u8,
        genesis_confidence: u64,
    ) -> u8;
    /// Current safe threshold setting (protocols should reject > threshold).
    fn get_safe_threshold(self: @TContractState) -> u8;
    fn set_safe_threshold(ref self: TContractState, threshold: u8);
    fn get_oracle(self: @TContractState) -> starknet::ContractAddress;
    fn set_oracle(ref self: TContractState, oracle: starknet::ContractAddress);
    fn get_owner(self: @TContractState) -> starknet::ContractAddress;
    fn transfer_ownership(ref self: TContractState, new_owner: starknet::ContractAddress);
}

// ─── BTCFiGuard contract ──────────────────────────────────────────────────
//
// Deployed once; any BTCFi protocol integrates via the IBTCFiGuard interface.
// Uses ITRIONOracle (cross-contract call) for live behavioral scores.

#[starknet::contract]
pub mod BTCFiGuard {
    use super::{IBTCFiGuard, ITRIONOracleDispatcher, ITRIONOracleDispatcherTrait};
    use starknet::{
        ContractAddress, get_caller_address,
        storage::{StoragePointerReadAccess, StoragePointerWriteAccess},
    };

    // Risk tier constants
    const SAFE: u8       = 0_u8;
    const CAUTION: u8    = 1_u8;
    const HIGH_RISK: u8  = 2_u8;
    const HOSTILE: u8    = 3_u8;

    // Scoring thresholds (scores are ×10000)
    const SAFE_ANIMA_MIN: u64    = 5500_u64;
    const SAFE_GC_MIN: u64       = 4000_u64;
    const CAUTION_ANIMA_MIN: u64 = 2500_u64;
    const CAUTION_GC_MIN: u64    = 1500_u64;

    // Trajectory alert levels
    const ALERT_WARN: u8         = 1_u8;
    const ALERT_MANIPULATION: u8 = 2_u8;

    #[storage]
    struct Storage {
        owner: ContractAddress,
        oracle: ContractAddress,
        safe_threshold: u8,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        OracleUpdated: OracleUpdated,
        ThresholdUpdated: ThresholdUpdated,
        OwnershipTransferred: OwnershipTransferred,
    }

    #[derive(Drop, starknet::Event)]
    pub struct OracleUpdated {
        pub old_oracle: ContractAddress,
        pub new_oracle: ContractAddress,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ThresholdUpdated {
        pub old_threshold: u8,
        pub new_threshold: u8,
    }

    #[derive(Drop, starknet::Event)]
    pub struct OwnershipTransferred {
        pub previous_owner: ContractAddress,
        pub new_owner: ContractAddress,
    }

    #[constructor]
    fn constructor(
        ref self: ContractState,
        owner: ContractAddress,
        oracle: ContractAddress,
    ) {
        self.owner.write(owner);
        self.oracle.write(oracle);
        self.safe_threshold.write(CAUTION);
    }

    #[generate_trait]
    impl InternalImpl of InternalTrait {
        fn compute_tier(
            anima_score: u64,
            trajectory_alert: u8,
            genesis_confidence: u64,
            update_count: u64,
        ) -> u8 {
            // HOSTILE: active TRION manipulation signal
            if trajectory_alert == ALERT_MANIPULATION {
                return HOSTILE;
            }
            // HIGH_RISK: no behavioral history on-chain
            if update_count == 0 {
                return HIGH_RISK;
            }
            // HIGH_RISK: extremely weak scores
            if anima_score < CAUTION_ANIMA_MIN && genesis_confidence < CAUTION_GC_MIN {
                return HIGH_RISK;
            }
            // CAUTION: partial history or warning
            if trajectory_alert == ALERT_WARN
                || anima_score < SAFE_ANIMA_MIN
                || genesis_confidence < SAFE_GC_MIN {
                return CAUTION;
            }
            SAFE
        }
    }

    #[abi(embed_v0)]
    impl BTCFiGuardImpl of IBTCFiGuard<ContractState> {
        fn assess_risk(self: @ContractState, beo_id: felt252) -> u8 {
            let oracle = ITRIONOracleDispatcher { contract_address: self.oracle.read() };
            let score = oracle.get_score(beo_id);
            InternalImpl::compute_tier(
                score.anima_score,
                score.trajectory_alert,
                score.genesis_confidence,
                score.update_count,
            )
        }

        fn batch_assess(self: @ContractState, beo_ids: Span<felt252>) -> Array<u8> {
            let oracle = ITRIONOracleDispatcher { contract_address: self.oracle.read() };
            let mut results: Array<u8> = ArrayTrait::new();
            let mut i: usize = 0;
            loop {
                if i >= beo_ids.len() { break; }
                let beo_id = *beo_ids.at(i);
                let score = oracle.get_score(beo_id);
                results.append(
                    InternalImpl::compute_tier(
                        score.anima_score,
                        score.trajectory_alert,
                        score.genesis_confidence,
                        score.update_count,
                    )
                );
                i += 1;
            };
            results
        }

        fn score_to_tier(
            self: @ContractState,
            anima_score: u64,
            trajectory_alert: u8,
            genesis_confidence: u64,
        ) -> u8 {
            InternalImpl::compute_tier(anima_score, trajectory_alert, genesis_confidence, 1)
        }

        fn get_safe_threshold(self: @ContractState) -> u8 {
            self.safe_threshold.read()
        }

        fn set_safe_threshold(ref self: ContractState, threshold: u8) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'BTCFi: unauthorized');
            assert(threshold <= 2_u8, 'BTCFi: threshold must be 0-2');
            let old = self.safe_threshold.read();
            self.safe_threshold.write(threshold);
            self.emit(ThresholdUpdated { old_threshold: old, new_threshold: threshold });
        }

        fn get_oracle(self: @ContractState) -> ContractAddress {
            self.oracle.read()
        }

        fn set_oracle(ref self: ContractState, oracle: ContractAddress) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'BTCFi: unauthorized');
            let old = self.oracle.read();
            self.oracle.write(oracle);
            self.emit(OracleUpdated { old_oracle: old, new_oracle: oracle });
        }

        fn get_owner(self: @ContractState) -> ContractAddress {
            self.owner.read()
        }

        fn transfer_ownership(ref self: ContractState, new_owner: ContractAddress) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'BTCFi: unauthorized');
            let old = self.owner.read();
            self.owner.write(new_owner);
            self.emit(OwnershipTransferred { previous_owner: old, new_owner });
        }
    }
}
