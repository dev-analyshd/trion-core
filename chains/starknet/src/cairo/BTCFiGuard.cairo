/// TRION Protocol — BTCFi Anti-Sybil Guard
/// Starknet Sepolia Contract
///
/// Composable behavioral risk module for BTCFi protocols.
/// Protocols (Vesu, Ekubo, Nostra, Uncap) call assess_risk(beo_id)
/// before accepting BTC collateral deposits. Returns a behavioral
/// risk tier based on TRION's on-chain oracle data.
///
/// Risk Tiers:
///   0 = SAFE     — strong behavioral history, no alerts
///   1 = CAUTION  — moderate history or warning flag
///   2 = HIGH_RISK — weak history, bootstrap phase, no on-chain data
///   3 = HOSTILE  — active manipulation detection
///
/// Integration pattern for BTCFi protocols:
///   let risk = btcfi_guard.assess_risk(beo_id);
///   assert(risk <= max_accepted_tier, 'TRION: behavioral risk too high');

#[starknet::interface]
pub trait IBTCFiGuard<TContractState> {
    /// Assess behavioral risk for a BEO identity. Returns 0-3 risk tier.
    fn assess_risk(self: @TContractState, beo_id: felt252) -> u8;
    /// Batch assessment — returns array of risk tiers for multiple BEO IDs.
    fn batch_assess(self: @TContractState, beo_ids: Span<felt252>) -> Array<u8>;
    /// Direct scoring without oracle lookup (for pre-fetched scores).
    fn score_to_tier(self: @TContractState, anima_score: u64, trajectory_alert: u8, genesis_confidence: u64) -> u8;
    /// Get the minimum safe tier protocols should require.
    fn get_safe_threshold(self: @TContractState) -> u8;
    /// Update the safe threshold (owner only).
    fn set_safe_threshold(ref self: TContractState, threshold: u8);
    /// Get the oracle contract address.
    fn get_oracle(self: @TContractState) -> starknet::ContractAddress;
    /// Update the oracle address (owner only).
    fn set_oracle(ref self: TContractState, oracle: starknet::ContractAddress);
    /// Get owner.
    fn get_owner(self: @TContractState) -> starknet::ContractAddress;
    /// Transfer ownership.
    fn transfer_ownership(ref self: TContractState, new_owner: starknet::ContractAddress);
    /// Total risk assessments performed.
    fn assessment_count(self: @TContractState) -> u64;
}

/// Minimal interface to read from TRIONOracle.
#[starknet::interface]
pub trait ITRIONOracleReader<TContractState> {
    fn get_score(
        self: @TContractState,
        beo_id: felt252
    ) -> BTCFiBEOScore;
}

/// Minimal BEOScore fields needed for risk assessment.
#[derive(Drop, Serde, Copy)]
pub struct BTCFiBEOScore {
    pub anima_score: u64,
    pub genesis_confidence: u64,
    pub trajectory_alert: u8,
    pub archetype_id: u8,
    pub akashic_depth: u64,
    pub is_resurrection: bool,
    pub dormancy_type: felt252,
    pub last_updated: u64,
    pub update_count: u64,
}

#[starknet::contract]
pub mod BTCFiGuard {
    use super::{IBTCFiGuard, ITRIONOracleReaderDispatcher, ITRIONOracleReaderDispatcherTrait};
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp,
        storage::{StoragePointerReadAccess, StoragePointerWriteAccess},
    };

    // ── Constants ─────────────────────────────────────────────────────────
    // Risk tier values
    const SAFE: u8      = 0_u8;
    const CAUTION: u8   = 1_u8;
    const HIGH_RISK: u8 = 2_u8;
    const HOSTILE: u8   = 3_u8;

    // Scoring thresholds (all scores are ×10000)
    // SAFE: anima >= 5500 AND genesis_confidence >= 4000 AND alert == CLEAR
    const SAFE_ANIMA_MIN: u64    = 5500_u64;
    const SAFE_GC_MIN: u64       = 4000_u64;
    // CAUTION: anima >= 2500 OR warning alert
    const CAUTION_ANIMA_MIN: u64 = 2500_u64;
    const CAUTION_GC_MIN: u64    = 1500_u64;
    // No on-chain data
    const BOOTSTRAP_THRESHOLD: u64 = 100_u64;
    // Trajectory alert values
    const ALERT_CLEAR: u8       = 0_u8;
    const ALERT_WARN: u8        = 1_u8;
    const ALERT_MANIPULATION: u8 = 2_u8;

    #[storage]
    struct Storage {
        owner: ContractAddress,
        oracle: ContractAddress,
        safe_threshold: u8,
        assessment_count: u64,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        RiskAssessed: RiskAssessed,
        OracleUpdated: OracleUpdated,
        ThresholdUpdated: ThresholdUpdated,
        OwnershipTransferred: OwnershipTransferred,
    }

    #[derive(Drop, starknet::Event)]
    pub struct RiskAssessed {
        #[key]
        pub beo_id: felt252,
        pub risk_tier: u8,
        pub anima_score: u64,
        pub trajectory_alert: u8,
        pub timestamp: u64,
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
        self.assessment_count.write(0);
    }

    #[generate_trait]
    impl InternalImpl of InternalTrait {
        fn compute_risk_tier(
            anima_score: u64,
            trajectory_alert: u8,
            genesis_confidence: u64,
            update_count: u64,
        ) -> u8 {
            // HOSTILE: active manipulation detected by TRION oracle
            if trajectory_alert == ALERT_MANIPULATION {
                return HOSTILE;
            }

            // HIGH_RISK: no behavioral data on-chain
            if update_count == 0 || anima_score < BOOTSTRAP_THRESHOLD {
                return HIGH_RISK;
            }

            // HIGH_RISK: very low scores (bootstrap phase entity)
            if anima_score < CAUTION_ANIMA_MIN && genesis_confidence < CAUTION_GC_MIN {
                return HIGH_RISK;
            }

            // CAUTION: moderate scores or warning flag
            if trajectory_alert == ALERT_WARN
                || anima_score < SAFE_ANIMA_MIN
                || genesis_confidence < SAFE_GC_MIN {
                return CAUTION;
            }

            // SAFE: strong behavioral history, clear trajectory
            SAFE
        }
    }

    #[abi(embed_v0)]
    impl BTCFiGuardImpl of IBTCFiGuard<ContractState> {
        fn assess_risk(self: @ContractState, beo_id: felt252) -> u8 {
            let oracle_addr = self.oracle.read();
            let oracle = ITRIONOracleReaderDispatcher { contract_address: oracle_addr };
            let score = oracle.get_score(beo_id);

            InternalImpl::compute_risk_tier(
                score.anima_score,
                score.trajectory_alert,
                score.genesis_confidence,
                score.update_count,
            )
        }

        fn batch_assess(self: @ContractState, beo_ids: Span<felt252>) -> Array<u8> {
            let oracle_addr = self.oracle.read();
            let oracle = ITRIONOracleReaderDispatcher { contract_address: oracle_addr };
            let mut results: Array<u8> = ArrayTrait::new();
            let mut i: usize = 0;
            loop {
                if i >= beo_ids.len() { break; }
                let beo_id = *beo_ids.at(i);
                let score = oracle.get_score(beo_id);
                let tier = InternalImpl::compute_risk_tier(
                    score.anima_score,
                    score.trajectory_alert,
                    score.genesis_confidence,
                    score.update_count,
                );
                results.append(tier);
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
            InternalImpl::compute_risk_tier(anima_score, trajectory_alert, genesis_confidence, 1)
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

        fn assessment_count(self: @ContractState) -> u64 {
            self.assessment_count.read()
        }
    }
}
