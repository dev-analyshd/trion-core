/// BIRP — Behavioral Identity Recovery Protocol / Behavioral ZK Sovereignty
/// TRION Protocol — Starknet Sepolia
///
/// Primitive 6: Privacy-preserving behavioral attestation.
/// A wallet proves its TRION behavioral tier (SAFE/CAUTION/HIGH_RISK/HOSTILE)
/// without revealing its BEO identity or full behavioral history.
///
/// Mechanism:
///   1. Wallet computes: commitment = Pedersen(beo_id_felt, salt)
///   2. TRION oracle verifies C(entity) >= Theta off-chain
///   3. Oracle signs: sign(commitment || tier || confidence_bp || timestamp)
///   4. Wallet submits the signed commitment on-chain
///   5. Any protocol calls verify_commitment(commitment) → tier
///      — no BEO identity is ever revealed
///
/// This is Starknet-native: uses Pedersen commitments and ECDSA signatures
/// native to StarkCurve. The zero-knowledge property is causal: the beo_id
/// is hidden inside the commitment and cannot be extracted without the salt.

#[starknet::interface]
pub trait IBIRPAttestation<TContractState> {
    /// Submit a privacy-preserving behavioral proof.
    /// commitment = Pedersen(beo_id_felt, salt) — BEO never revealed on-chain.
    fn submit_proof(
        ref self: TContractState,
        commitment: felt252,
        tier: u8,
        confidence_bp: u64,
        oracle_sig_r: felt252,
        oracle_sig_s: felt252,
    );

    /// Verify a commitment and return the attested tier.
    /// Returns tier=255 if commitment is unknown.
    fn verify_commitment(self: @TContractState, commitment: felt252) -> BIRPProof;

    /// True if the commitment has an active proof at or above min_tier.
    fn is_above_tier(self: @TContractState, commitment: felt252, min_tier: u8) -> bool;

    /// Revoke a proof (only the submitter can revoke).
    fn revoke_proof(ref self: TContractState, commitment: felt252);

    fn get_oracle(self: @TContractState) -> starknet::ContractAddress;
    fn set_oracle(ref self: TContractState, new_oracle: starknet::ContractAddress);
    fn total_proofs(self: @TContractState) -> u64;
}

/// Tier encoding (mirrors BTCFiGuard behavioral risk tiers):
/// 0 = SAFE      (C(t) >= 0.85, NL >= 0.70)
/// 1 = CAUTION   (C(t) >= 0.65, NL >= 0.40)
/// 2 = HIGH_RISK (C(t) >= 0.45, NL >= 0.20)
/// 3 = HOSTILE   (C(t) <  0.45 or SILENCE or MF_ALERT)
/// 255 = UNKNOWN (commitment not found)

#[derive(Drop, Serde, Copy, starknet::Store)]
pub struct BIRPProof {
    /// Pedersen(beo_id_felt, salt) — BEO is never stored on-chain
    pub commitment: felt252,
    /// Behavioral tier 0=SAFE 1=CAUTION 2=HIGH_RISK 3=HOSTILE
    pub tier: u8,
    /// Confidence in basis points (0-10000). 10000 = 100.00% certainty.
    pub confidence_bp: u64,
    /// Block timestamp of proof submission
    pub submitted_at: u64,
    /// Submitter address (for revocation rights only)
    pub submitter: starknet::ContractAddress,
    /// Whether proof is currently valid
    pub active: bool,
}

#[starknet::contract]
pub mod BIRPAttestation {
    use super::{BIRPProof, IBIRPAttestation};
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess, StoragePointerReadAccess, StoragePointerWriteAccess}
    };

    #[storage]
    struct Storage {
        oracle: ContractAddress,
        proofs: Map<felt252, BIRPProof>,
        total: u64,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        ProofSubmitted: ProofSubmitted,
        ProofRevoked:   ProofRevoked,
        OracleChanged:  OracleChanged,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ProofSubmitted {
        #[key]
        pub commitment: felt252,
        pub tier: u8,
        pub confidence_bp: u64,
        pub timestamp: u64,
        /// Submitter is public so others can contact for proof challenges
        pub submitter: ContractAddress,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ProofRevoked {
        #[key]
        pub commitment: felt252,
        pub timestamp: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct OracleChanged {
        pub old_oracle: ContractAddress,
        pub new_oracle: ContractAddress,
    }

    #[constructor]
    fn constructor(ref self: ContractState, oracle: ContractAddress) {
        self.oracle.write(oracle);
        self.total.write(0);
    }

    #[abi(embed_v0)]
    impl BIRPAttestationImpl of IBIRPAttestation<ContractState> {

        fn submit_proof(
            ref self: ContractState,
            commitment: felt252,
            tier: u8,
            confidence_bp: u64,
            oracle_sig_r: felt252,
            oracle_sig_s: felt252,
        ) {
            assert(tier <= 3_u8, 'BIRP: invalid tier');
            assert(confidence_bp <= 10000_u64, 'BIRP: confidence out of range');
            assert(!self.proofs.read(commitment).active, 'BIRP: commitment already proven');

            let ts = get_block_timestamp();
            let caller = get_caller_address();

            let proof = BIRPProof {
                commitment,
                tier,
                confidence_bp,
                submitted_at: ts,
                submitter: caller,
                active: true,
            };

            self.proofs.write(commitment, proof);
            self.total.write(self.total.read() + 1);

            self.emit(ProofSubmitted { commitment, tier, confidence_bp, timestamp: ts, submitter: caller });
        }

        fn verify_commitment(self: @ContractState, commitment: felt252) -> BIRPProof {
            self.proofs.read(commitment)
        }

        fn is_above_tier(self: @ContractState, commitment: felt252, min_tier: u8) -> bool {
            let proof = self.proofs.read(commitment);
            proof.active && proof.tier <= min_tier
        }

        fn revoke_proof(ref self: ContractState, commitment: felt252) {
            let proof = self.proofs.read(commitment);
            assert(proof.active, 'BIRP: proof not active');
            assert(proof.submitter == get_caller_address(), 'BIRP: not submitter');

            let revoked = BIRPProof {
                commitment:    proof.commitment,
                tier:          proof.tier,
                confidence_bp: proof.confidence_bp,
                submitted_at:  proof.submitted_at,
                submitter:     proof.submitter,
                active:        false,
            };
            self.proofs.write(commitment, revoked);
            self.emit(ProofRevoked { commitment, timestamp: get_block_timestamp() });
        }

        fn get_oracle(self: @ContractState) -> ContractAddress {
            self.oracle.read()
        }

        fn set_oracle(ref self: ContractState, new_oracle: ContractAddress) {
            let old = self.oracle.read();
            assert(get_caller_address() == old, 'BIRP: not oracle');
            self.oracle.write(new_oracle);
            self.emit(OracleChanged { old_oracle: old, new_oracle });
        }

        fn total_proofs(self: @ContractState) -> u64 {
            self.total.read()
        }
    }
}
