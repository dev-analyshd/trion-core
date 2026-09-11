"""
chameleon_tiers.py — TRION BZK Phase 5.3 (A-INT — integration engineer).

Implements the BTCP Fix 1 CHAMELEON block verbatim for travel rule compliance
tier wiring. Per BTCP Fix 1 CHAMELEON block verbatim (cited in
docs/zk/CANON_EXTRACT.md §3.4 + docs/zk/ZK_SURFACE_MAP.md §S3):

    "LOW:        proof optional, routing preference for compliant routes
     MEDIUM:     proof required above $1,000
     HIGH:       proof required for all routes
     CRITICAL:   AWA_enforced — nothing emitted until proof present"

Per mission Phase 5.3:

    "Create /home/z/my-project/trion-core/core/zk/chameleon_tiers.py that:
      • Maps transfer value → required tier
      • Calls TravelRuleCompliance.submitProof(...) when proof required
      • At CRITICAL: checks awaFrozen flag (via a mock oracle interface) —
        if TRUE, ALL emission reverts
    Test: 4 scenarios (LOW $500 no proof, MEDIUM $1500 with proof, HIGH
    any amount with proof, CRITICAL with AWA frozen → reverts). Label:
    SYNTHETIC-DEMO."

The on-chain tier enforcement is already implemented by A-CHAIN in
contracts/zk/TravelRuleCompliance.sol (Phase 4.1, commit 52d5c4c). The
Solidity contract's `submitProof(...)` function:
  • Accepts a `Tier` enum (LOW=0, MEDIUM=1, HIGH=2, CRITICAL=3)
  • Enforces the CHAMELEON block:
      MEDIUM + value > $1,000 + no proof → revert MediumTierRequiresProof
      HIGH + no proof → revert HighTierRequiresProof
      CRITICAL + no proof → revert CriticalTierRequiresProof
  • At CRITICAL: also checks `awaFrozen` (WP-Mar §17 + WP-Feb §14.2);
    if `awaFrozen == true`, ALL submission reverts with `AWAFrozen`
    (R-INVISIBILITY: NO override path).

This Python module is the integration layer that mirrors the on-chain
tier logic so callers can:
  1. Pre-compute the required tier for a transfer value (avoid an
     on-chain revert by submitting the correct tier).
  2. Call the on-chain contract's `submitProof(...)` via a pluggable
     adapter (default: an in-memory stub; production: a web3.py adapter
     wrapping TravelRuleCompliance.sol).
  3. At CRITICAL, check the AWA freeze state before submitting — fail
     closed locally rather than paying gas for an on-chain revert.

R-ABSENT: this module NEVER stores the disclosure payload, regulator
receipt, PII, behavioral content, transaction value as a PERSISTED field.
The `value_micro_usd` parameter is needed ONLY for tier enforcement (per
the Solidity contract's `valueMicroUsd` parameter — also never stored
on-chain per R-ABSENT, only used for the MEDIUM-tier threshold check).
The disclosure_hash + zk_proof_hash are the only persisted values (per
BTCP Fix 1 Step 4 verbatim: 'TRION stores: disclosure_hash only').

R-CHANNELS: this module emits signal-publication events via the on-chain
TravelRuleCompliance.sol interface (submitProof). No on-chain proof
generation. Proof generation is the entity's responsibility (offchain per
BTCP Fix 1 Steps 1-2: 'regulator receives: full disclosure (law satisfied).
TRION receives: nothing from this step.').

R-ORDER: the travel rule SNARK prove/verify round-trip is `[OPEN]` per
Phase 3 BLOCKER. Integration tests use a MockTravelRuleVerifier (testing
twin of MockTravelRuleVerifier.sol, Phase 4.1). The real verifier.sol
drops into the same `setVerifier(provingSystem, address)` interface when
the BLOCKER closes. Test label: SYNTHETIC-DEMO per R-LABELS.

R-INVISIBILITY: the AWA freeze has NO override path. This module mirrors
that invariant — there is no `forceResume` or `overrideFreeze` method
anywhere in this module (grep clean per mission Phase 5.4 acceptance).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Protocol

# Phase 5.0 shared infra — MockTravelRuleVerifier (testing twin).
from core.zk._mock_verifier import MockTravelRuleVerifier

log = logging.getLogger("trion.zk.chameleon_tiers")


__all__ = [
    "Tier",
    "MEDIUM_THRESHOLD_MICRO_USD",
    "TierDecision",
    "TravelRuleAdapter",
    "InMemoryTravelRuleRegistry",
    "AWAOracleAdapter",
    "InMemoryAWAOracle",
    "ChameleonTiers",
    "TierEnforcementError",
    "MediumTierRequiresProof",
    "HighTierRequiresProof",
    "CriticalTierRequiresProof",
    "AWAFrozen",
    "InvalidProofBytes",
    "TravelRuleProofInvalid",
    "InvalidPublicInputs",
    "TravelRuleProofAlreadySubmitted",
    "TravelRuleProofNotFound",
    "TravelRuleProofNotVerified",
    "ZeroAddress",
    "InvalidEntityId",
    "InvalidTxHash",
    "InvalidJurisdictionId",
    "InvalidDisclosureHash",
    "InvalidTier",
    "InvalidProvingSystem",
    "VerifierNotRegistered",
]


# ── Chameleon tier enum (BTCP Fix 1 CHAMELEON block verbatim) ────────────────
#
# Mirrors contracts/zk/TravelRuleCompliance.sol::Tier (Phase 4.1, commit
# 52d5c4c). Integer values must match the Solidity enum so the on-chain
# contract's revert reasons match the Python integration layer's exceptions.

class Tier(IntEnum):
    """BTCP Fix 1 CHAMELEON block verbatim.

    Mirrors TravelRuleCompliance.sol::Tier (Phase 4.1). Integer values
    MUST match the Solidity enum (LOW=0, MEDIUM=1, HIGH=2, CRITICAL=3).
    """
    LOW = 0       # proof optional, routing preference for compliant routes
    MEDIUM = 1    # proof required above $1,000
    HIGH = 2      # proof required for all routes
    CRITICAL = 3  # AWA_enforced — nothing emitted until proof present


# ── MEDIUM-tier threshold (BTCP Fix 1 CHAMELEON block verbatim) ──────────────
#
# Per BTCP Fix 1 CHAMELEON block verbatim: "MEDIUM: proof required above
# $1,000". Denominated in 1e8 micro-USD so the comparison is integer-only.
# Matches TravelRuleCompliance.sol::MEDIUM_THRESHOLD_MICRO_USD.

MEDIUM_THRESHOLD_MICRO_USD = 1_000 * 10**8  # $1,000 = 100_000_000_000 micro-USD


# ── Named errors (R-FAILCLOSED — mirrors TravelRuleCompliance.sol) ──────────

class TierEnforcementError(RuntimeError):
    """Base class for Chameleon tier enforcement failures."""


class MediumTierRequiresProof(TierEnforcementError):
    """BTCP Fix 1 CHAMELEON: MEDIUM > $1,000 requires proof."""


class HighTierRequiresProof(TierEnforcementError):
    """BTCP Fix 1 CHAMELEON: HIGH requires proof for all routes."""


class CriticalTierRequiresProof(TierEnforcementError):
    """BTCP Fix 1 CHAMELEON: CRITICAL — nothing emitted until proof present."""


class AWAFrozen(TierEnforcementError):
    """WP-Mar §17 / WP-Feb §14.2: AWA_enforced = FALSE → ALL emission FROZEN.
    Per R-INVISIBILITY: NO override path exists. The freeze can only be
    released by the AWA oracle transitioning `awaFrozen` from true to false
    AND all 6 WP-Feb §14.2 conditions holding (see awa_freeze.py)."""


class InvalidProofBytes(ValueError):
    """BTCP Fix 1 — empty proof forbidden."""


class TravelRuleProofInvalid(RuntimeError):
    """BTCP Fix 1 — fail-closed on invalid proof."""


class InvalidPublicInputs(ValueError):
    """BTCP Fix 1 Step 3 verbatim: public inputs length != 3
    ([transaction_hash, jurisdiction_id, disclosure_hash])."""


class TravelRuleProofAlreadySubmitted(ValueError):
    """Idempotency: same (entityId, txHash) already has a record."""


class TravelRuleProofNotFound(KeyError):
    """emitCompliant called for a non-existent (entityId, txHash)."""


class TravelRuleProofNotVerified(RuntimeError):
    """emitCompliant called for a record whose proof was never verified."""


class ZeroAddress(ValueError):
    """address(0) forbidden."""


class InvalidEntityId(ValueError):
    """zero entity_id forbidden."""


class InvalidTxHash(ValueError):
    """zero tx_hash forbidden."""


class InvalidJurisdictionId(ValueError):
    """zero jurisdiction_id forbidden."""


class InvalidDisclosureHash(ValueError):
    """zero disclosure_hash forbidden."""


class InvalidTier(ValueError):
    """tier enum out of range."""


class InvalidProvingSystem(ValueError):
    """provingSystem enum out of range."""


class VerifierNotRegistered(RuntimeError):
    """no verifier plugged in for the requested proving system."""


# ── Proving system enum (BTCP Fix 1 — Groth16 or PLONK, transparent setup
#     preferred per R-SETUP) ─────────────────────────────────────────────────

class ProvingSystem(IntEnum):
    """Mirrors TravelRuleCompliance.sol::ProvingSystem (Phase 4.1).
    Integer values MUST match the Solidity enum."""
    GROTH16 = 0  # ~200-byte proofs, per-circuit trusted setup
    PLONK = 1    # ~400-500-byte proofs, universal SRS (R-SETUP preferred)
    STARK = 2    # ~50-100 kB proofs, transparent (reserved; future)


# ── TierDecision dataclass ──────────────────────────────────────────────────

@dataclass
class TierDecision:
    """The result of mapping a transfer value → required tier + the
    proof-required flag.

    Fields:
      tier:                the BTCP Fix 1 CHAMELEON tier (LOW/MEDIUM/HIGH/CRITICAL).
      proof_required:      True iff the tier requires a non-empty proof.
      value_micro_usd:    the transfer value (echoed for audit; NOT persisted).
      reason:              human-readable reason for the tier decision.
    """

    tier: Tier
    proof_required: bool
    value_micro_usd: int
    reason: str


# ── TravelRuleAdapter — pluggable on-chain surface ──────────────────────────
#
# Per R-CHANNELS: the integration layer calls the on-chain contract's public
# interface; no on-chain proof generation. The actual on-chain call (web3.py
# → TravelRuleCompliance.sol::submitProof) is delegated to an adapter that
# implements this Protocol.

class TravelRuleAdapter(Protocol):
    """Pluggable on-chain travel rule registry surface.

    Mirrors the public interface of TravelRuleCompliance.sol (Phase 4.1):
      • submitProof(entityId, txHash, jurisdictionId, disclosureHash, tier,
                   provingSystem, proof, publicInputs, valueMicroUsd)
        returns (bool)
      • emitCompliant(entityId, txHash) returns (bool)
      • isCompliant(entityId, txHash) returns (bool)
      • awaFrozen() returns (bool)  — R-INVISIBILITY check
    """

    def submit_proof(
        self,
        entity_id: bytes,
        tx_hash: bytes,
        jurisdiction_id: bytes,
        disclosure_hash: bytes,
        tier: Tier,
        proving_system: ProvingSystem,
        proof: bytes,
        public_inputs: List[int],
        value_micro_usd: int,
    ) -> bool: ...

    def awa_frozen(self) -> bool: ...


class InMemoryTravelRuleRegistry:
    """In-memory stub of TravelRuleCompliance.sol (Phase 4.1).

    Used by tests and local runs; mirrors the contract's R-FAILCLOSED
    invariants (tier enforcement, AWA freeze, proof verification, idempotency).
    The travel rule verifier is pluggable — default: MockTravelRuleVerifier
    (testing twin). Production: a wrapper around the snarkjs-generated
    verifier.sol (Phase 3 [OPEN] BLOCKER).
    """

    EXPECTED_PUBLIC_INPUTS_LEN = 3  # per BTCP Fix 1 Step 3 verbatim

    def __init__(
        self,
        travel_rule_verifier: Optional[Any] = None,
        awa_oracle: Optional["AWAOracleAdapter"] = None,
    ) -> None:
        # Verifier is pluggable: default MockTravelRuleVerifier for tests;
        # production: a wrapper around the snarkjs-generated verifier.sol.
        self._verifier: Optional[Any] = (
            travel_rule_verifier
            if travel_rule_verifier is not None
            else MockTravelRuleVerifier()
        )
        # AWA oracle — pluggable. Default: InMemoryAWAOracle (default frozen
        # per R-FAILCLOSED; mirrors TravelRuleCompliance.sol awaFrozen = true).
        self._awa_oracle: Optional["AWAOracleAdapter"] = (
            awa_oracle
            if awa_oracle is not None
            else InMemoryAWAOracle()
        )
        # (entity_id, tx_hash) → record dict.
        # R-ABSENT: stores disclosure_hash, tier, stored_at, proof_verified,
        # zk_proof_hash ONLY — never the disclosure payload, regulator
        # receipt, PII, behavioral content, or transaction value.
        self._records: Dict[tuple, dict] = {}
        self.record_count: int = 0

    def set_verifier(self, verifier: Any) -> None:
        """R-CHANNELS: plug in the travel rule verifier. Mirrors
        TravelRuleCompliance.sol::setVerifier(provingSystem, address)."""
        self._verifier = verifier

    def awa_frozen(self) -> bool:
        """R-INVISIBILITY: returns the AWA freeze state from the oracle.
        R-FAILCLOSED: default TRUE — the contract is born frozen; only
        the AWA oracle can thaw it (and only after all 6 WP-Feb §14.2
        conditions hold — see awa_freeze.py)."""
        if self._awa_oracle is None:
            return True  # R-FAILCLOSED: no oracle = frozen
        return bool(self._awa_oracle.is_frozen())

    @staticmethod
    def _call_verifier(
        verifier: Any, proof: bytes, public_inputs: List[int]
    ) -> bool:
        """Invoke the verifier — accepts either a callable or an object
        with a `.verify(proof, public_inputs)` method (the latter matches
        the Solidity ITravelRuleVerifier interface)."""
        if verifier is None:
            return False
        if hasattr(verifier, "verify") and callable(getattr(verifier, "verify")):
            return bool(verifier.verify(proof, public_inputs))
        if callable(verifier):
            return bool(verifier(proof, public_inputs))
        return False

    def submit_proof(
        self,
        entity_id: bytes,
        tx_hash: bytes,
        jurisdiction_id: bytes,
        disclosure_hash: bytes,
        tier: Tier,
        proving_system: ProvingSystem,
        proof: bytes,
        public_inputs: List[int],
        value_micro_usd: int,
    ) -> bool:
        """BTCP Fix 1 Steps 3-4 — submit a Travel Rule proof.

        R-FAILCLOSED: every error is named (mirrors TravelRuleCompliance.sol).
        R-ABSENT: stores disclosure_hash + tier + stored_at + proof_verified
        + zk_proof_hash ONLY. NEVER stores the disclosure payload, the
        regulator receipt, PII, behavioral content, or transaction value.
        """
        # R-FAILCLOSED input validation — every error named.
        if not isinstance(entity_id, (bytes, bytearray)) or len(entity_id) == 0:
            raise InvalidEntityId("zero entity_id forbidden")
        if not isinstance(tx_hash, (bytes, bytearray)) or len(tx_hash) == 0:
            raise InvalidTxHash("zero tx_hash forbidden")
        if not isinstance(jurisdiction_id, (bytes, bytearray)) or len(jurisdiction_id) == 0:
            raise InvalidJurisdictionId("zero jurisdiction_id forbidden")
        if not isinstance(disclosure_hash, (bytes, bytearray)) or len(disclosure_hash) == 0:
            raise InvalidDisclosureHash("zero disclosure_hash forbidden")
        if not isinstance(tier, Tier):
            raise InvalidTier(f"tier must be Tier enum, got {type(tier).__name__}")
        if not isinstance(proving_system, ProvingSystem):
            raise InvalidProvingSystem(
                f"proving_system must be ProvingSystem enum, got {type(proving_system).__name__}"
            )

        # AWA freeze check (R-INVISIBILITY — no override path).
        if self.awa_frozen():
            raise AWAFrozen(
                "AWA_enforced = FALSE → ALL emission FROZEN per WP-Mar §17 / "
                "WP-Feb §14.2. NO override path exists (R-INVISIBILITY)."
            )

        # Chameleon tier enforcement (BTCP Fix 1 CHAMELEON block verbatim).
        if tier == Tier.MEDIUM:
            if value_micro_usd > MEDIUM_THRESHOLD_MICRO_USD and len(proof) == 0:
                raise MediumTierRequiresProof(
                    f"MEDIUM tier + value ${value_micro_usd / 1e8:.2f} > $1,000 "
                    "requires proof (BTCP Fix 1 CHAMELEON)"
                )
        elif tier == Tier.HIGH:
            if len(proof) == 0:
                raise HighTierRequiresProof(
                    "HIGH tier requires proof for all routes (BTCP Fix 1 CHAMELEON)"
                )
        elif tier == Tier.CRITICAL:
            if len(proof) == 0:
                raise CriticalTierRequiresProof(
                    "CRITICAL tier — nothing emitted until proof present "
                    "(BTCP Fix 1 CHAMELEON)"
                )
        # Tier.LOW: proof optional — no enforcement.

        # Public inputs length per BTCP Fix 1 Step 3 verbatim:
        # [transaction_hash, jurisdiction_id, disclosure_hash]
        if not isinstance(public_inputs, list) or len(public_inputs) != self.EXPECTED_PUBLIC_INPUTS_LEN:
            raise InvalidPublicInputs(
                f"expected {self.EXPECTED_PUBLIC_INPUTS_LEN} public inputs "
                "(transaction_hash, jurisdiction_id, disclosure_hash) per "
                "BTCP Fix 1 Step 3 verbatim"
            )

        # Idempotency — same (entity_id, tx_hash) must not already have a record.
        key = (bytes(entity_id), bytes(tx_hash))
        if key in self._records:
            raise TravelRuleProofAlreadySubmitted(
                f"proof already submitted for entity={entity_id.hex()} tx={tx_hash.hex()}"
            )

        # Verify the proof (if non-empty).
        import hashlib
        zk_proof_hash = (
            hashlib.sha3_256(bytes(proof)).digest() if len(proof) > 0 else b"\x00" * 32
        )
        verified = False
        if len(proof) > 0:
            if self._verifier is None:
                raise VerifierNotRegistered("no travel rule verifier plugged in")
            verified = self._call_verifier(self._verifier, bytes(proof), list(public_inputs))
            if not verified:
                raise TravelRuleProofInvalid(
                    "travel rule proof verification failed (BTCP Fix 1 R-FAILCLOSED)"
                )

        # Store disclosure_hash + tier + stored_at + proof_verified +
        # zk_proof_hash ONLY (BTCP Fix 1 Step 4 verbatim + R-ABSENT).
        # value_micro_usd is NOT stored (used only for the MEDIUM-tier check).
        self._records[key] = {
            "disclosure_hash": bytes(disclosure_hash),
            "tier": tier,
            "stored_at": int(time.time()),
            "proof_verified": verified,
            "zk_proof_hash": zk_proof_hash,
        }
        self.record_count += 1

        # Signal publication — R-CHANNELS (event only, no PII).
        log.info(
            "TRAVEL_RULE_PROOF_SUBMITTED entity=%s tx=%s jurisdiction=%s "
            "disclosure_hash=%s zk_proof_hash=%s proving_system=%s tier=%s",
            entity_id.hex(), tx_hash.hex(), jurisdiction_id.hex(),
            disclosure_hash.hex(), zk_proof_hash.hex(),
            proving_system.name, tier.name,
        )
        # BTCP Fix 1 Step 4 verbatim: "TRAVEL_RULE_COMPLIANT = TRUE" —
        # emitted ONLY when proof verified.
        if verified:
            log.info(
                "TRAVEL_RULE_COMPLIANT entity=%s tx=%s compliant=True",
                entity_id.hex(), tx_hash.hex(),
            )
        return True


# ── AWAOracleAdapter — pluggable AWA oracle surface ────────────────────────
#
# Per R-INVISIBILITY + WP-Mar §17 verbatim: "Cannot be overridden by any
# single entity. By design." The AWA oracle mirrors the onchain AWA
# condition; only the oracle can transition `awaFrozen` from true to false,
# and only after all 6 WP-Feb §14.2 conditions hold.

class AWAOracleAdapter(Protocol):
    """Pluggable AWA oracle surface. Mirrors the AWA oracle referenced by
    TravelRuleCompliance.sol (Phase 4.1)."""

    def is_frozen(self) -> bool: ...


class InMemoryAWAOracle:
    """In-memory stub of the AWA oracle.

    Default: FROZEN (R-FAILCLOSED per TravelRuleCompliance.sol awaFrozen = true).
    The freeze can ONLY be released by `set_awa_state(False)` — and even then,
    the 6 WP-Feb §14.2 conditions MUST hold (see awa_freeze.py::AWAFreezeIntegrator
    which is the canonical 6-condition gate). This stub is a simple boolean
    toggle for tests; the production adapter wraps the on-chain AWA oracle.
    """

    def __init__(self, *, initial_frozen: bool = True) -> None:
        # R-FAILCLOSED: default frozen.
        self._frozen = bool(initial_frozen)

    def is_frozen(self) -> bool:
        return self._frozen

    def set_awa_state(self, frozen: bool, *, reason: str = "") -> None:
        """Transition the AWA freeze state.

        Per R-INVISIBILITY: this method is the ONLY path to thaw. There is
        NO `forceResume` / `overrideFreeze` method anywhere in this module
        (grep clean per mission Phase 5.4 acceptance).

        NOTE: the real gate is in awa_freeze.py::AWAFreezeIntegrator which
        verifies all 6 WP-Feb §14.2 conditions before releasing. This stub
        is for the Chameleon tier's pre-flight check only — it does NOT
        bypass the 6-condition gate.
        """
        self._frozen = bool(frozen)
        log.info(
            "AWA_STATE_TRANSITION frozen=%s reason=%s", self._frozen, reason,
        )


# ── ChameleonTiers — the Phase 5.3 tier-wiring engine ──────────────────────

class ChameleonTiers:
    """BTCP Fix 1 CHAMELEON block tier-wiring engine.

    Per mission Phase 5.3:
      • Maps transfer value → required tier
      • Calls TravelRuleCompliance.submitProof(...) when proof required
      • At CRITICAL: checks awaFrozen flag — if TRUE, ALL emission reverts

    The on-chain tier enforcement is already in TravelRuleCompliance.sol
    (Phase 4.1). This Python module is the integration layer that:
      1. Pre-computes the required tier for a transfer value (avoid on-chain
         reverts by submitting the correct tier).
      2. Calls the on-chain contract's `submitProof(...)` via a pluggable
         adapter (default: in-memory stub; production: web3.py adapter).
      3. At CRITICAL, pre-checks the AWA freeze state before submitting —
         fail closed locally rather than paying gas for an on-chain revert.
    """

    def __init__(
        self,
        travel_rule_registry: Optional[TravelRuleAdapter] = None,
        *,
        default_tier_for_low_value: Tier = Tier.LOW,
    ) -> None:
        self._registry: TravelRuleAdapter = (
            travel_rule_registry
            if travel_rule_registry is not None
            else InMemoryTravelRuleRegistry()
        )
        self._default_tier_for_low_value = default_tier_for_low_value

    # ── Tier mapping (BTCP Fix 1 CHAMELEON block verbatim) ────────────────

    @staticmethod
    def map_value_to_tier(value_micro_usd: int) -> TierDecision:
        """Map a transfer value → required tier (BTCP Fix 1 CHAMELEON block).

        Per BTCP Fix 1 CHAMELEON block verbatim:
          LOW:        proof optional — value ≤ $1,000 (default route).
          MEDIUM:     proof required above $1,000 — value > $1,000 AND
                      value ≤ HIGH-tier threshold (HIGH is operator-set;
                      this default maps any value > $1,000 to MEDIUM
                      unless the caller overrides).
          HIGH:       proof required for all routes — operator-set; this
                      default does NOT auto-select HIGH (the caller MUST
                      explicitly request HIGH).
          CRITICAL:   AWA_enforced — operator-set; this default does NOT
                      auto-select CRITICAL (the caller MUST explicitly
                      request CRITICAL).

        Returns a TierDecision with the tier, proof_required flag, and
        the reason.

        Note: this is the CALLER-SIDE tier decision. The on-chain contract
        enforces the tier at submitProof time (Phase 4.1). Callers should
        use this to pre-compute the tier so they submit the correct one
        (avoiding an on-chain revert).
        """
        if not isinstance(value_micro_usd, int) or value_micro_usd < 0:
            raise ValueError("value_micro_usd must be a non-negative int")

        if value_micro_usd > MEDIUM_THRESHOLD_MICRO_USD:
            return TierDecision(
                tier=Tier.MEDIUM,
                proof_required=True,
                value_micro_usd=value_micro_usd,
                reason=(
                    f"value ${value_micro_usd / 1e8:.2f} > $1,000 → MEDIUM "
                    "(BTCP Fix 1 CHAMELEON: proof required above $1,000)"
                ),
            )
        return TierDecision(
            tier=Tier.LOW,
            proof_required=False,
            value_micro_usd=value_micro_usd,
            reason=(
                f"value ${value_micro_usd / 1e8:.2f} ≤ $1,000 → LOW "
                "(BTCP Fix 1 CHAMELEON: proof optional)"
            ),
        )

    @staticmethod
    def tier_requires_proof(tier: Tier) -> bool:
        """Return True iff the tier requires a non-empty proof per BTCP
        Fix 1 CHAMELEON block verbatim:
          LOW:        proof optional → False
          MEDIUM:     proof required above $1,000 (the check is value-
                      dependent; this function returns True to indicate
                      the tier's general requirement — the value-check
                      happens at submit time)
          HIGH:       proof required for all routes → True
          CRITICAL:   AWA_enforced — nothing emitted until proof present → True
        """
        if tier == Tier.LOW:
            return False
        if tier == Tier.MEDIUM:
            return True  # caller must pass value > $1,000 + proof
        if tier == Tier.HIGH:
            return True
        if tier == Tier.CRITICAL:
            return True
        raise InvalidTier(f"unknown tier: {tier}")

    # ── submit_proof (BTCP Fix 1 Steps 3-4) ────────────────────────────────

    def submit_proof(
        self,
        entity_id: bytes,
        tx_hash: bytes,
        jurisdiction_id: bytes,
        disclosure_hash: bytes,
        tier: Tier,
        proving_system: ProvingSystem,
        proof: bytes,
        public_inputs: List[int],
        value_micro_usd: int,
    ) -> bool:
        """Submit a Travel Rule proof via the on-chain registry adapter.

        Pre-checks (fail closed locally):
          1. If tier == CRITICAL: check awaFrozen — if TRUE, raise AWAFrozen
             (R-INVISIBILITY: no override path; WP-Mar §17 verbatim).
          2. If tier == MEDIUM: check value > $1,000 + proof required.
          3. If tier == HIGH: check proof non-empty.
          4. If tier == LOW: proof optional (no check).

        Delegates to TravelRuleAdapter.submit_proof(...) which mirrors
        TravelRuleCompliance.sol::submitProof (Phase 4.1).
        """
        # Pre-flight: at CRITICAL, fail closed locally if AWA frozen.
        if tier == Tier.CRITICAL and self._registry.awa_frozen():
            raise AWAFrozen(
                "CRITICAL tier + AWA frozen → ALL emission reverts per "
                "WP-Mar §17 / WP-Feb §14.2 (R-INVISIBILITY: no override path)"
            )
        # Delegate to the registry adapter — mirrors on-chain enforcement.
        return self._registry.submit_proof(
            entity_id, tx_hash, jurisdiction_id, disclosure_hash,
            tier, proving_system, proof, public_inputs, value_micro_usd,
        )


# ── Self-test (SYNTHETIC-DEMO label) ──────────────────────────────────────────

def _self_test() -> dict:
    """Deterministic self-test.

    Label: SYNTHETIC-DEMO — uses MockTravelRuleVerifier (testing twin of
    MockTravelRuleVerifier.sol, Phase 4.1). Per R-LABELS, this is NOT a
    real Groth16/PLONK proof; it asserts that the integration plumbing
    is correct, not that the SNARK is sound. SNARK soundness is a
    property of the Phase-3 MEASURED circuit (zk_travel_rule, 1,179
    constraints) and is gated `[OPEN]` per the BLOCKER PROTOCOL.

    Test scenarios (mission Phase 5.3 verbatim):
      1. LOW $500 no proof → accepted (proof optional).
      2. MEDIUM $1500 with proof → accepted.
      3. HIGH any amount with proof → accepted.
      4. CRITICAL with AWA frozen → reverts with AWAFrozen.
      5. CRITICAL with AWA not frozen + proof → accepted.
      6. MEDIUM $1500 without proof → reverts with MediumTierRequiresProof.
      7. HIGH without proof → reverts with HighTierRequiresProof.
      8. CRITICAL without proof (AWA not frozen) → reverts with CriticalTierRequiresProof.
      9. map_value_to_tier: $500 → LOW, $1500 → MEDIUM, $999.99 → LOW.
    """
    out: dict = {}
    logging.basicConfig(level=logging.INFO)

    # Construct with an InMemoryAWAOracle that starts UNFROZEN so we can
    # test the tier enforcement without the AWA gate firing prematurely.
    # (Scenario 4 explicitly tests the AWA-frozen path.)
    oracle = InMemoryAWAOracle(initial_frozen=False)
    registry = InMemoryTravelRuleRegistry(awa_oracle=oracle)
    tiers = ChameleonTiers(travel_rule_registry=registry)

    # 9. map_value_to_tier correctness.
    d_low = ChameleonTiers.map_value_to_tier(500 * 10**8)
    assert d_low.tier == Tier.LOW, f"$500 → LOW, got {d_low.tier.name}"
    assert d_low.proof_required is False
    d_med = ChameleonTiers.map_value_to_tier(1_500 * 10**8)
    assert d_med.tier == Tier.MEDIUM, f"$1500 → MEDIUM, got {d_med.tier.name}"
    assert d_med.proof_required is True
    d_edge = ChameleonTiers.map_value_to_tier(999_99 * 10**8 // 100)  # $999.99
    assert d_edge.tier == Tier.LOW

    # 1. LOW $500 no proof → accepted.
    ok1 = tiers.submit_proof(
        entity_id=b"\x01" * 32,
        tx_hash=b"\x10" * 32,
        jurisdiction_id=b"\xF1" * 32,
        disclosure_hash=b"\xD1" * 32,
        tier=Tier.LOW,
        proving_system=ProvingSystem.PLONK,
        proof=b"",  # proof optional for LOW
        public_inputs=[
            int.from_bytes(b"\x10" * 32, "big"),
            int.from_bytes(b"\xF1" * 32, "big"),
            int.from_bytes(b"\xD1" * 32, "big"),
        ],
        value_micro_usd=500 * 10**8,  # $500
    )
    assert ok1 is True, "LOW $500 no proof must be accepted"

    # 2. MEDIUM $1500 with proof → accepted.
    well_formed_proof = b"\x42" * 200  # ≥32 bytes, well-formed
    ok2 = tiers.submit_proof(
        entity_id=b"\x02" * 32,
        tx_hash=b"\x11" * 32,
        jurisdiction_id=b"\xF2" * 32,
        disclosure_hash=b"\xD2" * 32,
        tier=Tier.MEDIUM,
        proving_system=ProvingSystem.PLONK,
        proof=well_formed_proof,
        public_inputs=[
            int.from_bytes(b"\x11" * 32, "big"),
            int.from_bytes(b"\xF2" * 32, "big"),
            int.from_bytes(b"\xD2" * 32, "big"),
        ],
        value_micro_usd=1_500 * 10**8,  # $1,500
    )
    assert ok2 is True, "MEDIUM $1500 with proof must be accepted"

    # 3. HIGH any amount with proof → accepted.
    ok3 = tiers.submit_proof(
        entity_id=b"\x03" * 32,
        tx_hash=b"\x12" * 32,
        jurisdiction_id=b"\xF3" * 32,
        disclosure_hash=b"\xD3" * 32,
        tier=Tier.HIGH,
        proving_system=ProvingSystem.GROTH16,
        proof=well_formed_proof,
        public_inputs=[
            int.from_bytes(b"\x12" * 32, "big"),
            int.from_bytes(b"\xF3" * 32, "big"),
            int.from_bytes(b"\xD3" * 32, "big"),
        ],
        value_micro_usd=500 * 10**8,  # any amount
    )
    assert ok3 is True, "HIGH any amount with proof must be accepted"

    # 4. CRITICAL with AWA frozen → reverts with AWAFrozen.
    oracle.set_awa_state(True, reason="awa_violation_injected")
    try:
        tiers.submit_proof(
            entity_id=b"\x04" * 32,
            tx_hash=b"\x13" * 32,
            jurisdiction_id=b"\xF4" * 32,
            disclosure_hash=b"\xD4" * 32,
            tier=Tier.CRITICAL,
            proving_system=ProvingSystem.PLONK,
            proof=well_formed_proof,
            public_inputs=[
                int.from_bytes(b"\x13" * 32, "big"),
                int.from_bytes(b"\xF4" * 32, "big"),
                int.from_bytes(b"\xD4" * 32, "big"),
            ],
            value_micro_usd=2_000 * 10**8,
        )
        raise AssertionError("CRITICAL with AWA frozen must raise AWAFrozen")
    except AWAFrozen:
        pass
    # Restore the AWA state for subsequent scenarios.
    oracle.set_awa_state(False, reason="awa_violation_resolved")

    # 5. CRITICAL with AWA not frozen + proof → accepted.
    ok5 = tiers.submit_proof(
        entity_id=b"\x04" * 32,
        tx_hash=b"\x14" * 32,
        jurisdiction_id=b"\xF5" * 32,
        disclosure_hash=b"\xD5" * 32,
        tier=Tier.CRITICAL,
        proving_system=ProvingSystem.PLONK,
        proof=well_formed_proof,
        public_inputs=[
            int.from_bytes(b"\x14" * 32, "big"),
            int.from_bytes(b"\xF5" * 32, "big"),
            int.from_bytes(b"\xD5" * 32, "big"),
        ],
        value_micro_usd=2_000 * 10**8,
    )
    assert ok5 is True, "CRITICAL with AWA not frozen + proof must be accepted"

    # 6. MEDIUM $1500 without proof → reverts with MediumTierRequiresProof.
    try:
        tiers.submit_proof(
            entity_id=b"\x05" * 32,
            tx_hash=b"\x15" * 32,
            jurisdiction_id=b"\xF6" * 32,
            disclosure_hash=b"\xD6" * 32,
            tier=Tier.MEDIUM,
            proving_system=ProvingSystem.PLONK,
            proof=b"",
            public_inputs=[
                int.from_bytes(b"\x15" * 32, "big"),
                int.from_bytes(b"\xF6" * 32, "big"),
                int.from_bytes(b"\xD6" * 32, "big"),
            ],
            value_micro_usd=1_500 * 10**8,
        )
        raise AssertionError("MEDIUM $1500 without proof must raise MediumTierRequiresProof")
    except MediumTierRequiresProof:
        pass

    # 7. HIGH without proof → reverts with HighTierRequiresProof.
    try:
        tiers.submit_proof(
            entity_id=b"\x06" * 32,
            tx_hash=b"\x16" * 32,
            jurisdiction_id=b"\xF7" * 32,
            disclosure_hash=b"\xD7" * 32,
            tier=Tier.HIGH,
            proving_system=ProvingSystem.PLONK,
            proof=b"",
            public_inputs=[
                int.from_bytes(b"\x16" * 32, "big"),
                int.from_bytes(b"\xF7" * 32, "big"),
                int.from_bytes(b"\xD7" * 32, "big"),
            ],
            value_micro_usd=500 * 10**8,
        )
        raise AssertionError("HIGH without proof must raise HighTierRequiresProof")
    except HighTierRequiresProof:
        pass

    # 8. CRITICAL without proof (AWA not frozen) → reverts with CriticalTierRequiresProof.
    try:
        tiers.submit_proof(
            entity_id=b"\x07" * 32,
            tx_hash=b"\x17" * 32,
            jurisdiction_id=b"\xF8" * 32,
            disclosure_hash=b"\xD8" * 32,
            tier=Tier.CRITICAL,
            proving_system=ProvingSystem.PLONK,
            proof=b"",
            public_inputs=[
                int.from_bytes(b"\x17" * 32, "big"),
                int.from_bytes(b"\xF8" * 32, "big"),
                int.from_bytes(b"\xD8" * 32, "big"),
            ],
            value_micro_usd=2_000 * 10**8,
        )
        raise AssertionError("CRITICAL without proof must raise CriticalTierRequiresProof")
    except CriticalTierRequiresProof:
        pass

    # 10. R-INVISIBILITY grep audit: this module exposes NO forceResume /
    #     overrideFreeze method (the audit is enforced by the test commit).
    #     This assertion is the runtime twin of the grep audit — it scans
    #     the module's public API for the forbidden method names.
    public_methods = [
        name for name in dir(ChameleonTiers)
        if not name.startswith("_") and callable(getattr(ChameleonTiers, name, None))
    ]
    forbidden = [m for m in public_methods if "forceResume" in m or "overrideFreeze" in m]
    assert forbidden == [], (
        f"R-INVISIBILITY violation: ChameleonTiers exposes forbidden methods {forbidden}"
    )
    public_methods_oracle = [
        name for name in dir(InMemoryAWAOracle)
        if not name.startswith("_") and callable(getattr(InMemoryAWAOracle, name, None))
    ]
    forbidden_o = [m for m in public_methods_oracle if "forceResume" in m or "overrideFreeze" in m]
    assert forbidden_o == [], (
        f"R-INVISIBILITY violation: InMemoryAWAOracle exposes forbidden methods {forbidden_o}"
    )

    out["all_passed"] = True
    return out


if __name__ == "__main__":
    import json
    print("=== chameleon_tiers.py — self-test (SYNTHETIC-DEMO) ===")
    res = _self_test()
    print(json.dumps({k: v for k, v in res.items() if not isinstance(v, bytes)}, indent=2))
    assert res.get("all_passed"), "self-test FAILED"
    print("PASS — BTCP Fix 1 CHAMELEON tier wiring (LOW/MEDIUM/HIGH/CRITICAL)")
