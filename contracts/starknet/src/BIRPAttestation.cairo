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
///   3. Oracle signs: ECDSA over
///      Poseidon('BIRP-ATT-V1', commitment, tier, confidence_bp,
///      attestation_nonce) with its STARK-curve key
///   4. Wallet submits the signed commitment + nonce on-chain; the
///      contract verifies the oracle signature and burns the nonce —
///      an attestation is usable exactly once, ever
///   5. Any protocol calls verify_commitment(commitment) → tier
///      — no BEO identity is ever revealed
///
/// This is Starknet-native: uses Pedersen commitments and ECDSA signatures
/// native to StarkCurve. The zero-knowledge property is causal: the beo_id
/// is hidden inside the commitment and cannot be extracted without the salt.
///
/// Oracle authentication: the oracle's STARK-curve public key (the
/// x-coordinate felt) is pinned in storage at deploy and can be rotated by
/// the oracle authority via set_oracle_pubkey. submit_proof is fail-closed
/// until the key is set; forged, placeholder (0,0) and replayed
/// attestations revert. Submission itself stays permissionless — the
/// signature, not the caller, carries the oracle's authority.

#[starknet::interface]
pub trait IBIRPAttestation<TContractState> {
    /// Submit a privacy-preserving behavioral proof.
    /// commitment = Pedersen(beo_id_felt, salt) — BEO never revealed on-chain.
    /// attestation_nonce is the oracle-chosen unique id of the attestation;
    /// (r, s) must be the oracle's STARK-curve ECDSA signature over
    /// Poseidon('BIRP-ATT-V1', commitment, tier, confidence_bp,
    /// attestation_nonce) under the stored oracle public key.
    fn submit_proof(
        ref self: TContractState,
        commitment: felt252,
        tier: u8,
        confidence_bp: u64,
        attestation_nonce: u64,
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
    /// The oracle's STARK-curve public key (x-coordinate felt) every
    /// submitted proof must verify under.
    fn get_oracle_pubkey(self: @TContractState) -> felt252;
    /// Rotate the oracle signing key. Only the current oracle authority
    /// may rotate; proofs signed under the old key stop validating
    /// immediately (fail-closed rotation).
    fn set_oracle_pubkey(ref self: TContractState, new_pubkey: felt252);
    /// True if the attestation nonce has been consumed by a submitted
    /// proof (replay guard; consumed nonces revert in submit_proof).
    fn nonce_used(self: @TContractState, attestation_nonce: u64) -> bool;
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
    use core::array::ArrayTrait;
    use core::traits::Into;
    use core::poseidon::poseidon_hash_span;
    use core::ecdsa::check_ecdsa_signature;
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess, StoragePointerReadAccess, StoragePointerWriteAccess}
    };

    /// felt("BIRP-ATT-V1") — domain separation for the attestation
    /// digest, so an oracle signature can never be cross-used against
    /// another protocol message (same discipline as the family-3
    /// certificate's DOMAIN_FELT and the gate's SIGNAL_DOMAIN_FELT).
    const BIRP_DOMAIN_FELT: felt252 = 'BIRP-ATT-V1';

    #[storage]
    struct Storage {
        oracle: ContractAddress,
        /// STARK-curve public key (x-coordinate) proofs must verify under.
        oracle_pubkey: felt252,
        proofs: Map<felt252, BIRPProof>,
        /// Burned attestation nonces — one attestation, one submission,
        /// ever (replay protection survives commitment revocation).
        used_nonces: Map<u64, bool>,
        total: u64,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        ProofSubmitted: ProofSubmitted,
        ProofRevoked:   ProofRevoked,
        OracleChanged:  OracleChanged,
        OraclePubkeyChanged: OraclePubkeyChanged,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ProofSubmitted {
        #[key]
        pub commitment: felt252,
        pub tier: u8,
        pub confidence_bp: u64,
        /// The burned oracle attestation id (unique per submitted proof)
        pub attestation_nonce: u64,
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

    #[derive(Drop, starknet::Event)]
    pub struct OraclePubkeyChanged {
        pub old_pubkey: felt252,
        pub new_pubkey: felt252,
    }

    #[constructor]
    fn constructor(ref self: ContractState, oracle: ContractAddress, oracle_pubkey: felt252) {
        assert(oracle_pubkey != 0, 'BIRP: zero oracle pubkey');
        self.oracle.write(oracle);
        self.oracle_pubkey.write(oracle_pubkey);
        self.total.write(0);
    }

    #[generate_trait]
    impl InternalImpl of InternalTrait {
        /// D = Poseidon('BIRP-ATT-V1', commitment, tier, confidence_bp,
        /// attestation_nonce) — the felt the oracle's STARK-curve key
        /// signs. Mirrors poseidon_hash_span usage in trion_certificate.
        fn attestation_digest(
            commitment: felt252,
            tier: u8,
            confidence_bp: u64,
            attestation_nonce: u64,
        ) -> felt252 {
            let mut input: Array<felt252> = ArrayTrait::new();
            input.append(BIRP_DOMAIN_FELT);
            input.append(commitment);
            let tier_f: felt252 = tier.into();
            let conf_f: felt252 = confidence_bp.into();
            let nonce_f: felt252 = attestation_nonce.into();
            input.append(tier_f);
            input.append(conf_f);
            input.append(nonce_f);
            poseidon_hash_span(input.span())
        }
    }

    #[abi(embed_v0)]
    impl BIRPAttestationImpl of IBIRPAttestation<ContractState> {

        fn submit_proof(
            ref self: ContractState,
            commitment: felt252,
            tier: u8,
            confidence_bp: u64,
            attestation_nonce: u64,
            oracle_sig_r: felt252,
            oracle_sig_s: felt252,
        ) {
            assert(tier <= 3_u8, 'BIRP: invalid tier');
            assert(confidence_bp <= 10000_u64, 'BIRP: confidence out of range');
            assert(!self.proofs.read(commitment).active, 'BIRP: commitment already proven');

            // Fail-closed oracle authentication: unset key, placeholder
            // (0,0) signatures and forged signatures all revert here.
            let oracle_pubkey = self.oracle_pubkey.read();
            assert(oracle_pubkey != 0, 'BIRP: oracle pubkey unset');
            assert(attestation_nonce != 0, 'BIRP: zero nonce');
            assert(!self.used_nonces.read(attestation_nonce), 'BIRP: nonce already used');
            assert(oracle_sig_r != 0, 'BIRP: zero sig r');
            assert(oracle_sig_s != 0, 'BIRP: zero sig s');

            let digest = InternalImpl::attestation_digest(
                commitment, tier, confidence_bp, attestation_nonce,
            );
            let verified = check_ecdsa_signature(
                digest, oracle_pubkey, oracle_sig_r, oracle_sig_s,
            );
            assert(verified, 'BIRP: invalid oracle signature');

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

            // Burn the nonce only after verification succeeded: a failed
            // proof consumes nothing, a successful one can never be
            // replayed — even after its commitment is revoked.
            self.used_nonces.write(attestation_nonce, true);
            self.proofs.write(commitment, proof);
            self.total.write(self.total.read() + 1);

            self.emit(ProofSubmitted {
                commitment, tier, confidence_bp, attestation_nonce,
                timestamp: ts, submitter: caller,
            });
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

        fn get_oracle_pubkey(self: @ContractState) -> felt252 {
            self.oracle_pubkey.read()
        }

        fn set_oracle_pubkey(ref self: ContractState, new_pubkey: felt252) {
            let caller = get_caller_address();
            assert(caller == self.oracle.read(), 'BIRP: not oracle');
            assert(new_pubkey != 0, 'BIRP: zero pubkey');
            let old = self.oracle_pubkey.read();
            self.oracle_pubkey.write(new_pubkey);
            self.emit(OraclePubkeyChanged { old_pubkey: old, new_pubkey });
        }

        fn nonce_used(self: @ContractState, attestation_nonce: u64) -> bool {
            self.used_nonces.read(attestation_nonce)
        }

        fn total_proofs(self: @ContractState) -> u64 {
            self.total.read()
        }
    }
}
