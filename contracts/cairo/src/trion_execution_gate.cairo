// SPDX-License-Identifier: MIT
// TRIONExecutionGate — Cairo version for Starknet
// Autonomous Execution Safety Layer.
//
// ── C-04 REMEDIATION (VALIDATOR_SECURITY_AUDIT, CRITICAL) ──────────────
// The legacy publish path trusted a REGISTERED-VALIDATOR CALLER:
// `is_validator[get_caller_address()]` — ONE validator could
// publish ANY behavioral signal for ANY entity (and the owner could
// mint more such authorities via add_validator): no signatures, no
// quorum, no binding, no freshness. That authority class is REMOVED
// (the is_validator storage, the add_validator entrypoint and the
// ValidatorAdded event are gone from this contract).
//
// publish_signal now requires a TRION validator QUORUM — family-3
// verification per CANONICAL_CERTIFICATE.md §3.2/§7, against the
// per-epoch validator set of TrionEpochRegistry (§10.2 registrar,
// bound ONE-WAY via bind_registry):
//
//   D_gate = Poseidon(felt("TRION-SIGNAL-V1"),
//                     entity_id, status, phi_t, theta, drop_pct,
//                     beo_hash, da_proof_hash, signal_nonce, issued_at)
//
// and the canonical checks: ≥ 3 distinct signers (liveness floor),
// registered epoch membership (grace-bounded), envelope weight
// claims == registered values (§6 step 5c), STARK-curve ECDSA over
// D_gate (one bad signature fails the whole batch), L4.2 tier
// quorum over REGISTERED s_j·d_j weights, 300 s signal freshness
// (60 s lower-bound drift), strictly increasing per-entity
// signal_nonce (replay). The signal VALUES are INSIDE the signed
// digest — a quorum signature cannot be replayed for different
// values (the H-08 discipline the Solidity gate folds into its
// digest).
//
// A behavioral signal is NOT a kind-1 ESCROW_RELEASE certificate
// (§6 step 1: unknown kinds fail closed), so the gate signs its own
// domain-separated message with the SAME family-3 machinery
// (felt domain tag + Poseidon + starknet::ecdsa + epoch registry)
// instead of consuming an escrow certificate — "TRION-SIGNAL-V1"
// is disjoint from "TRION-CERT-V1" (cross-purpose signature reuse
// is structurally impossible: a certificate signature never
// verifies as a signal signature and vice versa).
//
// Pause blocks signal PUBLICATION only (an emission freeze, MD
// §17-shaped) — check_execution/is_execution_safe keep answering
// from the last published signal so consumers fail closed on
// staleness through their own freshness discipline.

use trion_certificate::{SigEntry, EPOCH_GRACE, is_fresh, quorum_met, verify_signature};
use trion_epoch_registry::{
    IEpochRegistryDispatcher, IEpochRegistryDispatcherTrait,
};
use core::traits::Into;
use core::array::{ArrayTrait, SpanTrait};
use starknet::crypto::poseidon_hash_span;

#[starknet::interface]
pub trait ITRIONExecutionGate<TContractState> {
    /// Quorum-gated signal publication (C-04 fix). PERMISSIONLESS:
    /// anyone may submit; the family-3 quorum over D_gate is the
    /// ONLY publication authority. The old 8-arg form whose sole
    /// gate was `is_validator[caller]` no longer exists.
    fn publish_signal(
        ref self: TContractState,
        entity_id: felt252,
        status: u8,
        phi_t: u32,
        theta: u32,
        drop_pct: u32,
        beo_hash: felt252,
        da_proof_hash: felt252,
        sigs: Span<SigEntry>,
        validator_epoch: u64,
        signal_nonce: u64,
        issued_at: u64,
    );
    fn check_execution(ref self: TContractState, entity_id: felt252, caller: starknet::ContractAddress) -> (bool, felt252);
    fn is_execution_safe(self: @TContractState, entity_id: felt252) -> bool;
    fn get_stats(self: @TContractState) -> (u256, u256, u256, u256, u64);
    fn pause(ref self: TContractState);
    fn unpause(ref self: TContractState);
    /// One-way binding of the TrionEpochRegistry (§10.2 registrar).
    /// Zero may be passed at deploy and bound exactly once after.
    fn bind_registry(ref self: TContractState, registry: starknet::ContractAddress);
    fn get_registry(self: @TContractState) -> starknet::ContractAddress;
    fn get_owner(self: @TContractState) -> starknet::ContractAddress;
}

#[derive(Drop, starknet::Store)]
pub struct BehavioralSignal {
    pub packed_status: u8,
    pub phi_t: u32,
    pub theta: u32,
    pub drop_pct: u32,
    pub beo_hash: felt252,
    pub da_proof_hash: felt252,
    pub initialized: bool,
    pub block_number: u64,
}

#[derive(Drop, starknet::Store)]
pub struct ExecutionDecision {
    pub allowed: bool,
    pub status: u8,
    pub phi_t: u32,
    pub theta: u32,
    pub drop_pct: u32,
    pub checked_at: u64,
}

#[starknet::contract]
pub mod TRIONExecutionGate {
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess, StoragePointerReadAccess, StoragePointerWriteAccess}
    };
    use core::integer::u256;
    use core::array::{ArrayTrait, SpanTrait};
    use core::traits::Into;
    use starknet::crypto::poseidon_hash_span;
    use trion_certificate::{SigEntry, EPOCH_GRACE, is_fresh, quorum_met, verify_signature};
    use trion_epoch_registry::{
        IEpochRegistryDispatcher, IEpochRegistryDispatcherTrait,
    };
    use super::{BehavioralSignal, ExecutionDecision};

    const STATUS_SAFE: u8 = 1;
    const STATUS_ELEVATED: u8 = 2;
    const STATUS_COLLAPSE: u8 = 3;

    /// felt("TRION-SIGNAL-V1") — the gate's family-3 domain tag,
    /// disjoint from the certificate domain felt "TRION-CERT-V1".
    const SIGNAL_DOMAIN_FELT: felt252 = 'TRION-SIGNAL-V1';

    /// Signal freshness (§9 discipline; the EVM tier's
    /// BTCP_ROUTE_FRESHNESS_SECONDS = 300) — is_fresh() widens the
    /// lower bound by the 60 s clock drift tolerance only.
    const SIGNAL_TTL_SECONDS: u64 = 300;

    /// Gas bound on the signature batch (registry roster cap is 128;
    /// the real bar is the L4.2 weight quorum).
    const MAX_SIG_ENTRIES: u64 = 128;

    /// 2^48 — issued_at range bound so u64 freshness arithmetic
    /// cannot wrap (same discipline as trion_certificate).
    const ISSUED_AT_MAX: u64 = 0x1000000000000;

    #[storage]
    struct Storage {
        owner: ContractAddress,
        /// §10.2 registrar binding — ONE-WAY (bind once, never rebind;
        /// a rogue registry is the R-4 trust boundary, owner-triggered
        /// rebinds would make it worse).
        registry: ContractAddress,
        registry_bound: bool,
        paused: bool,
        signals: Map<felt252, BehavioralSignal>,
        decisions: Map<felt252, ExecutionDecision>,
        /// Replay guard: highest consumed signal_nonce per entity
        /// (STORAGE KEYS: compiler-derived from the distinct field
        /// name — disjoint from the signals/decisions maps).
        last_signal_nonce: Map<felt252, u64>,
        total_executions_allowed: u256,
        total_executions_blocked: u256,
        total_signals_published: u256,
        total_anomalies_sealed: u256,
        last_storage_sync_block: u64,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        SignalPublished: SignalPublished,
        ExecutionAllowed: ExecutionAllowed,
        ExecutionBlocked: ExecutionBlocked,
        AnomalySealed: AnomalySealed,
        Paused: Paused,
        Unpaused: Unpaused,
        RegistryBound: RegistryBound,
    }

    #[derive(Drop, starknet::Event)]
    pub struct SignalPublished {
        #[key]
        pub entity_id: felt252,
        pub status: u8,
        pub phi_t: u32,
        pub validator_epoch: u64,
        pub signal_nonce: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ExecutionAllowed {
        #[key]
        pub entity_id: felt252,
        #[key]
        pub caller: ContractAddress,
        pub phi_t: u32,
    }

    #[derive(Drop, starknet::Event)]
    pub struct ExecutionBlocked {
        #[key]
        pub entity_id: felt252,
        #[key]
        pub caller: ContractAddress,
        pub reason: u8,
    }

    #[derive(Drop, starknet::Event)]
    pub struct AnomalySealed {
        #[key]
        pub entity_id: felt252,
        pub anomaly_type: u8,
        pub timestamp: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Paused {
        #[key]
        pub by: ContractAddress,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Unpaused {
        #[key]
        pub by: ContractAddress,
    }

    #[derive(Drop, starknet::Event)]
    pub struct RegistryBound {
        #[key]
        pub registry: ContractAddress,
    }

    #[constructor]
    fn constructor(ref self: ContractState) {
        let sender = get_caller_address();
        self.owner.write(sender);
        self.registry_bound.write(false);
        self.paused.write(false);
        self.total_executions_allowed.write(u256 { low: 0, high: 0 });
        self.total_executions_blocked.write(u256 { low: 0, high: 0 });
        self.total_signals_published.write(u256 { low: 0, high: 0 });
        self.total_anomalies_sealed.write(u256 { low: 0, high: 0 });
    }

    /// D_gate = Poseidon('TRION-SIGNAL-V1', entity_id, status, phi_t,
    /// theta, drop_pct, beo_hash, da_proof_hash, signal_nonce,
    /// issued_at) — §3.2 family-3 digest over the FULL signal tuple.
    /// No felt multiplication is involved (Poseidon consumes the
    /// field elements directly), so there is no wrap surface: the
    /// composed digest binds every signal value exactly.
    #[generate_trait]
    impl GateDigest of GateDigestTrait<ContractState> {
        fn signal_digest(
            self: @ContractState,
            entity_id: felt252,
            status: u8,
            phi_t: u32,
            theta: u32,
            drop_pct: u32,
            beo_hash: felt252,
            da_proof_hash: felt252,
            signal_nonce: u64,
            issued_at: u64,
        ) -> felt252 {
            let mut input: Array<felt252> = ArrayTrait::new();
            input.append(SIGNAL_DOMAIN_FELT);
            input.append(entity_id);
            input.append(status.into());
            input.append(phi_t.into());
            input.append(theta.into());
            input.append(drop_pct.into());
            input.append(beo_hash);
            input.append(da_proof_hash);
            input.append(signal_nonce.into());
            input.append(issued_at.into());
            poseidon_hash_span(input.span())
        }
    }

    #[abi(embed_v0)]
    impl GateImpl of super::ITRIONExecutionGate<ContractState> {
        fn publish_signal(ref self: ContractState, entity_id: felt252, status: u8,
            phi_t: u32, theta: u32, drop_pct: u32, beo_hash: felt252, da_proof_hash: felt252,
            sigs: Span<SigEntry>, validator_epoch: u64, signal_nonce: u64, issued_at: u64) {
            // PERMISSIONLESS: no caller check — the quorum is the
            // authority (C-04: the is_validator caller gate is gone).
            // Pause is an emission freeze (MD §17-shaped): it blocks
            // NEW signals; consumers fail closed on staleness.
            assert(!self.paused.read(), 'GATE: paused');
            assert(status >= 1 && status <= 4, 'GATE: invalid status');
            assert(entity_id != 0, 'GATE: zero entity');
            assert(signal_nonce != 0, 'GATE: zero nonce');
            // range bound so is_fresh's u64 additions cannot wrap
            assert(issued_at < ISSUED_AT_MAX, 'GATE: issued range');

            // ── signature-batch structure (§6 step 1, envelope half) ──
            let n = sigs.len();
            let n_u64: u64 = n.into();
            assert(n >= 3, 'GATE: sig count');
            assert(n_u64 <= MAX_SIG_ENTRIES, 'GATE: too many sigs');
            // distinct signers — duplicate padding is not consensus (§4)
            let mut i: usize = 0;
            loop {
                if i >= n { break; }
                let a = *sigs.at(i);
                let mut j: usize = i + 1;
                loop {
                    if j >= n { break; }
                    let b = *sigs.at(j);
                    assert(
                        !(a.vid_hi16 == b.vid_hi16 && a.vid_lo16 == b.vid_lo16),
                        'GATE: dup signer',
                    );
                    j += 1;
                };
                i += 1;
            };

            // ── epoch (registry + grace — no historical sets) ──────────
            assert(self.registry_bound.read(), 'GATE: registry unbound');
            let registry = IEpochRegistryDispatcher {
                contract_address: self.registry.read(),
            };
            let (_count, total_power, d_consensus, sealed) =
                registry.get_epoch(validator_epoch);
            assert(sealed, 'GATE: unknown epoch');
            let latest = registry.latest_epoch();
            assert(validator_epoch <= latest, 'GATE: future epoch');
            assert(latest - validator_epoch <= EPOCH_GRACE, 'GATE: stale epoch');

            // ── freshness (300 s window; drift widens lower bound) ─────
            let now = get_block_timestamp();
            assert(
                is_fresh(issued_at, SIGNAL_TTL_SECONDS, now),
                'GATE: signal stale',
            );

            // ── signatures (batch fail-closed) over D_gate ─────────────
            let d_gate = self.signal_digest(
                entity_id, status, phi_t, theta, drop_pct,
                beo_hash, da_proof_hash, signal_nonce, issued_at,
            );
            // signed_power recomputed from REGISTERED weights (§5)
            let mut signed_power: u128 = 0;
            let mut k: usize = 0;
            loop {
                if k >= n { break; }
                let sig = *sigs.at(k);
                let (pubkey, stake, diversity, active) = registry.get_validator(
                    validator_epoch, sig.vid_hi16, sig.vid_lo16,
                );
                // membership (fail-closed on unknown/inactive signer)
                assert(active, 'GATE: validator inactive');
                // envelope weight claims == registered values, exact
                assert(
                    sig.stake_weight == stake && sig.diversity_weight == diversity,
                    'GATE: weight mismatch',
                );
                // STARK-curve ECDSA over D_gate — one bad signature
                // fails the WHOLE batch.
                assert(verify_signature(pubkey, d_gate, @sig), 'GATE: bad signature');
                // w_j = s_j·d_j/1e6 from the REGISTERED pair — u64 mul
                // is wrap-free (registry caps weights at 1e6 each).
                let w = stake * diversity / 1000000;
                signed_power += w.into();
                k += 1;
            };

            // ── quorum (L4.2 tier from registered D_consensus) ─────────
            let total_u128: u128 = total_power.into();
            assert(
                quorum_met(signed_power, total_u128, d_consensus),
                'GATE: quorum not met',
            );

            // ── replay: per-entity strictly increasing nonce ───────────
            let consumed = self.last_signal_nonce.read(entity_id);
            assert(signal_nonce > consumed, 'GATE: signal replay');

            let block_info_num = 0_u64; // Simplified: no block height in Cairo
            self.signals.write(entity_id, BehavioralSignal {
                packed_status: status, phi_t, theta, drop_pct,
                beo_hash, da_proof_hash, initialized: true,
                block_number: block_info_num,
            });
            self.last_signal_nonce.write(entity_id, signal_nonce);

            let count = self.total_signals_published.read();
            self.total_signals_published.write(count + u256 { low: 1, high: 0 });

            if status >= STATUS_COLLAPSE {
                let anomalies = self.total_anomalies_sealed.read();
                self.total_anomalies_sealed.write(anomalies + u256 { low: 1, high: 0 });
                self.emit(AnomalySealed {
                    entity_id, anomaly_type: status,
                    timestamp: get_block_timestamp(),
                });
            }

            self.emit(SignalPublished {
                entity_id, status, phi_t,
                validator_epoch, signal_nonce,
            });
        }

        fn check_execution(ref self: ContractState, entity_id: felt252, caller: ContractAddress) -> (bool, felt252) {
            assert(!self.paused.read(), 'Paused');
            let ts = get_block_timestamp();

            // Fail-closed for uninitialized entities
            let sig = self.signals.read(entity_id);
            if !sig.initialized {
                let decision_hash = entity_id;
                self.decisions.write(decision_hash, ExecutionDecision {
                    allowed: false, status: 0, phi_t: 0, theta: 0, drop_pct: 0, checked_at: ts,
                });
                let blocked = self.total_executions_blocked.read();
                self.total_executions_blocked.write(blocked + u256 { low: 1, high: 0 });
                self.emit(ExecutionBlocked { entity_id, caller, reason: 0 });
                return (false, decision_hash);
            }

            let allowed = sig.packed_status <= STATUS_ELEVATED;
            let decision_hash = entity_id;

            self.decisions.write(decision_hash, ExecutionDecision {
                allowed, status: sig.packed_status, phi_t: sig.phi_t,
                theta: sig.theta, drop_pct: sig.drop_pct, checked_at: ts,
            });

            if allowed {
                let count = self.total_executions_allowed.read();
                self.total_executions_allowed.write(count + u256 { low: 1, high: 0 });
                self.emit(ExecutionAllowed { entity_id, caller, phi_t: sig.phi_t });
            } else {
                let count = self.total_executions_blocked.read();
                self.total_executions_blocked.write(count + u256 { low: 1, high: 0 });
                self.emit(ExecutionBlocked { entity_id, caller, reason: sig.packed_status });
            }

            (allowed, decision_hash)
        }

        fn is_execution_safe(self: @ContractState, entity_id: felt252) -> bool {
            let sig = self.signals.read(entity_id);
            if !sig.initialized { return false; }
            sig.packed_status <= STATUS_ELEVATED
        }

        fn get_stats(self: @ContractState) -> (u256, u256, u256, u256, u64) {
            (
                self.total_executions_allowed.read(),
                self.total_executions_blocked.read(),
                self.total_signals_published.read(),
                self.total_anomalies_sealed.read(),
                self.last_storage_sync_block.read(),
            )
        }

        fn pause(ref self: ContractState) {
            assert(get_caller_address() == self.owner.read(), 'Not owner');
            self.paused.write(true);
            self.emit(Paused { by: get_caller_address() });
        }

        fn unpause(ref self: ContractState) {
            assert(get_caller_address() == self.owner.read(), 'Not owner');
            self.paused.write(false);
            self.emit(Unpaused { by: get_caller_address() });
        }

        fn bind_registry(ref self: ContractState, registry: ContractAddress) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'Not owner');
            // ONE-WAY: a bound registry can never be swapped (R-4).
            assert(!self.registry_bound.read(), 'GATE: registry bound');
            assert(!registry.is_zero(), 'GATE: zero registry');
            self.registry.write(registry);
            self.registry_bound.write(true);
            self.emit(RegistryBound { registry });
        }

        fn get_registry(self: @ContractState) -> ContractAddress {
            self.registry.read()
        }

        fn get_owner(self: @ContractState) -> ContractAddress {
            self.owner.read()
        }
    }
}
