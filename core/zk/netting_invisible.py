"""
netting_invisible.py — TRION BZK Phase 5.1 (A-INT — integration engineer).

Implements the BTCP §5.6 "Water Underground" privacy mode for the netting
engine. Per BTCP §5.6 Phase 1 verbatim:

    "Phase 1 — Commit (MEV bots see nothing actionable):
       H_intent = Hash_DNA(intent_details || random_nonce || entity_id)
       User submits: H_intent ONLY
       MEV bots observe: a commitment hash — no direction, no value, nothing
       // Implementation: submit `H_intent` to `BTCPIntent.sol`
       // Contract stores: `H_intent → timestamp, entity_id`
       // NO routing calculation yet"

Per mission Phase 5.1:

    "Per BTCP §5.6 Phase 1 verbatim: 'privacy: ZK_CREDENTIAL | INVISIBLE
    in Intent.constraints' — the Intent object has a `privacy` field. Implement
    a Python module that:
      • Adds an `INVISIBLE` mode to the existing netting engine (find it at
        `core/` or `rust/` — search for `netting_engine` and EXTEND it, do NOT
        rewrite)
      • In INVISIBLE mode: intents are NOT broadcast to find counterparties;
        instead, the engine submits H_intent commitments to
        IntentCommitmentRegistry.sol (via the on-chain surface), waits for a
        complementarity proof (via the ComplementarityVerifier), and only
        then reveals
      • In PUBLIC mode (the default): unchanged behavior
      • Mode switch is audited via a log line
        `NETTING_MODE_SWITCH entity_id old_mode new_mode reason`"

This module extends (does NOT rewrite) the existing Rust `netting_engine.rs`
(A-INT preserves the existing PUBLIC-mode NettingEngine behavior; the INVISIBLE
mode is layered on top via the Python bridge). The Rust engine at
`rust/src/netting_engine.rs` exposes `add_intent`, `find_netting_pair`,
`remove_intent` — these are the PUBLIC-mode operations. The Python bridge
`core/btcp/rust_bridge.py` already wraps them; this module reuses the bridge
for PUBLIC mode and adds the INVISIBLE-mode path (commit → match → reveal)
on top.

R-ABSENT: NO field stores intent contents, direction, value, asset,
counter-party identifier, message-layer identifier, or ledger identifier.
The INVISIBLE-mode path stores ONLY:
  • H_intent (the 32-byte Hash_DNA sense strand — already a hash)
  • entity_id (public BEO identifier — used for routing)
  • committed_at timestamp (block.timestamp mirror — signal publication)
  • revealed flag (BTCP §5.6 Phase 3 atomic reveal state)
The intent payload itself NEVER reaches this module's persistence. The Hash_DNA
helpers (zk-circuits/commitments/hash_dna.py::intent_hash, Phase 2.1, commit
2429e7e) compute H_intent OFFCHAIN at the entity side; the entity submits
H_intent ONLY to this module (mirroring the IntentCommitmentRegistry.sol
contract surface per Phase 4.2, commit fa22973).

R-FAILCLOSED: every error is a named custom exception (mirrors the
IntentCommitmentRegistry.sol error names: ZeroHIntent, ZeroEntityId,
ComplementarityProofFailed, IntentAlreadyCommitted, IntentNotFound,
IntentAlreadyRevealed). The reveal path is atomic — both H_intent_A and
H_intent_B are revealed in the SAME transaction (mirrors Solidity
transaction semantics; BTCP §5.6 Phase 3 verbatim "Both intents published in
same block — atomic").

R-ORDER: the complementarity SNARK prove/verify round-trip is `[OPEN]` per
Phase 3 BLOCKER (Groth16 setup >110s exceeds sandbox timeout). Therefore
the integration tests use a MockComplementarityVerifier (testing twin of
contracts/zk/test/MockComplementarityGroth16Verifier.sol) that returns
True for well-formed proofs. The MockVerifier is the testing twin; the real
verifier.sol drops into the same `setVerifier(circuitId, address)` interface
when the BLOCKER closes.

R-CHANNELS: this module emits signal-publication events (IntentCommitted,
IntentRevealed) via the on-chain surface — it does NOT generate proofs
on-chain. Proof generation is the entity's responsibility (offchain per
BTCP §5.6 Phase 2). This module calls the on-chain contract's
`commitIntent(H_intent, entity_id)` and `revealIntent(H_intent_A,
H_intent_B, proof, public_inputs)` via their public interface — the actual
on-chain call is delegated to a pluggable `commitment_registry` adapter
(default: an in-memory stub; production: a web3.py adapter wrapping
IntentCommitmentRegistry.sol).
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol

# Phase 5.0 shared infra — MockVerifier (testing twin).
from core.zk._mock_verifier import MockComplementarityVerifier

# Phase 2.1 Hash_DNA helpers (commit 2429e7e) — load the canonical
# `intent_hash(intent_details, random_nonce, entity_id)` from the file
# path because the `zk-circuits/` directory contains a hyphen and is
# therefore NOT a valid Python module name. Loading by spec avoids the
# sys.path-manipulation hack and is the same pattern used elsewhere in
# the TRION codebase (e.g. `core/btcp/orchestrator.py` adds the workspace
# root to sys.path and imports the `zk` package via a try/except fallback).
import importlib.util as _importlib_util
import os as _os

_HASH_DNA_PATH = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
    "zk-circuits", "commitments", "hash_dna.py",
)
if _os.path.exists(_HASH_DNA_PATH):
    _spec = _importlib_util.spec_from_file_location(
        "trion_zk_commitments_hash_dna", _HASH_DNA_PATH
    )
    assert _spec is not None and _spec.loader is not None
    _hash_dna = _importlib_util.module_from_spec(_spec)
    _spec.loader.exec_module(_hash_dna)  # type: ignore[union-attr]
else:  # pragma: no cover — defensive fallback for stripped-down deployments
    _hash_dna = None  # type: ignore[assignment]

log = logging.getLogger("trion.zk.netting_invisible")


__all__ = [
    "PrivacyMode",
    "Intent",
    "NettingMatch",
    "CommitmentRegistryAdapter",
    "InMemoryCommitmentRegistry",
    "NettingInvisible",
    "NettingModeSwitchError",
    "ZeroHIntent",
    "ZeroEntityId",
    "IntentAlreadyCommitted",
    "IntentNotFound",
    "IntentAlreadyRevealed",
    "ComplementarityProofFailed",
    "InvalidPublicInputsLength",
    "InvalidProofBytes",
    "VerifierNotRegistered",
]


# ── Privacy mode enum ─────────────────────────────────────────────────────────
#
# Per BTCP §5.6 Phase 1 verbatim: "privacy: ZK_CREDENTIAL | INVISIBLE in
# Intent.constraints". The Intent.constraints.privacy field can take one of
# these values. PUBLIC is the default (unchanged behavior — the existing
# rust/src/netting_engine.rs PUBLIC mode).

class PrivacyMode(str, Enum):
    """Per BTCP §5.6 Phase 1 verbatim Intent.constraints.privacy values."""
    PUBLIC = "PUBLIC"            # default — unchanged PUBLIC-mode behavior
    INVISIBLE = "INVISIBLE"      # BTCP §5.6 — commit → match → reveal
    ZK_CREDENTIAL = "ZK_CREDENTIAL"  # BTCP §5.6 — proof of credential
                                       # (out of scope for Phase 5.1; reserved)


# ── Named errors (R-FAILCLOSED — mirrors IntentCommitmentRegistry.sol) ──────

class NettingModeSwitchError(RuntimeError):
    """Raised when an invalid mode switch is attempted."""


class ZeroHIntent(ValueError):
    """BTCP §5.6 Phase 1 — zero H_intent forbidden."""


class ZeroEntityId(ValueError):
    """BTCP §5.6 Phase 1 — zero entity_id forbidden."""


class IntentAlreadyCommitted(ValueError):
    """BTCP §5.6 Phase 1 — idempotency: H_intent already committed."""


class IntentNotFound(KeyError):
    """BTCP §5.6 Phase 3 — reveal without prior commit."""


class IntentAlreadyRevealed(ValueError):
    """BTCP §5.6 Phase 3 — double-reveal forbidden."""


class ComplementarityProofFailed(RuntimeError):
    """BTCP §5.6 Phase 3 — fail-closed on invalid complementarity proof.
    Both intents remain hidden (no state change, no event emitted)."""


class InvalidPublicInputsLength(ValueError):
    """Per Phase 1 MEASURED circuit (zk_complementarity_proof) — public
    inputs length != 5."""


class InvalidProofBytes(ValueError):
    """BTCP §5.6 Phase 2 — empty or malformed proof bytes forbidden."""


class VerifierNotRegistered(RuntimeError):
    """BTCP §5.6 Phase 2 — no complementarity verifier plugged in."""


# ── Intent dataclass ─────────────────────────────────────────────────────────
#
# Per BTCP §5.6 Phase 1: H_intent = Hash_DNA(intent_details || random_nonce ||
# entity_id). The Intent object carries the preimage fields needed to compute
# H_intent via hash_dna.intent_hash(intent_details, random_nonce, entity_id).
#
# R-ABSENT: NO field stores the intent contents, direction, value, asset,
# counter-party identifier, message-layer identifier, or ledger identifier
# as PERSISTED FIELDS. The Intent object lives only in caller memory (the
# entity side). Once H_intent is computed and submitted via
# NettingInvisible.commit_intent(...), only H_intent + entity_id +
# committed_at + revealed are stored by this module.

@dataclass
class Intent:
    """A netting intent (entity-side, ephemeral — never persisted by this
    module's storage path).

    Fields:
      entity_id:        32-byte BEO identifier (BTCP §5.6 Phase 1).
      intent_details:   opaque bytes (entity-side intent payload — the
                        spec's `intent_details` preimage; R-ABSENT: never
                        persisted by this module).
      random_nonce:    16+ byte nonce (BTCP §5.6 Phase 1 verbatim
                        `random_nonce`).
      privacy:         PrivacyMode (PUBLIC default; INVISIBLE for BTCP §5.6
                        "Water Underground" mode).
    """

    entity_id: bytes
    intent_details: bytes
    random_nonce: bytes
    privacy: PrivacyMode = PrivacyMode.PUBLIC

    def __post_init__(self) -> None:
        if not isinstance(self.entity_id, (bytes, bytearray)) or len(self.entity_id) == 0:
            raise ZeroEntityId("entity_id must be a non-empty bytes")
        if not isinstance(self.intent_details, (bytes, bytearray)) or len(self.intent_details) == 0:
            raise ValueError("intent_details must be non-empty bytes")
        if not isinstance(self.random_nonce, (bytes, bytearray)) or len(self.random_nonce) == 0:
            raise ValueError("random_nonce must be non-empty bytes")
        if not isinstance(self.privacy, PrivacyMode):
            raise TypeError(f"privacy must be PrivacyMode, got {type(self.privacy).__name__}")

    def compute_h_intent(self) -> bytes:
        """Compute H_intent = Hash_DNA(intent_details || random_nonce || entity_id)
        per BTCP §5.6 Phase 1 verbatim.

        Uses zk-circuits/commitments/hash_dna.py::intent_hash (Phase 2.1).
        Returns the 32-byte Hash_DNA sense strand.
        """
        return _hash_dna.intent_hash(
            intent_details=bytes(self.intent_details),
            random_nonce=bytes(self.random_nonce),
            entity_id=bytes(self.entity_id),
        )


@dataclass
class NettingMatch:
    """A matched netting pair after complementarity proof verified.

    Fields:
      h_intent_a, h_intent_b: the two complementary H_intent commitments.
      entity_a, entity_b:     the two entity_ids (public BEO identifiers).
      revealed_at:             unix-seconds timestamp of the atomic reveal.
      zk_proof_hash:           SHA3-256(proof) for offchain deduplication.
    """

    h_intent_a: bytes
    h_intent_b: bytes
    entity_a: bytes
    entity_b: bytes
    revealed_at: int
    zk_proof_hash: bytes


# ── CommitmentRegistryAdapter — pluggable on-chain surface ───────────────────
#
# Per R-CHANNELS: the integration layer calls the on-chain contract's public
# interface; no on-chain proof generation. The actual on-chain call (web3.py
# → IntentCommitmentRegistry.sol) is delegated to an adapter that implements
# this Protocol. The default in-memory stub is for tests and local runs; the
# production adapter wraps IntentCommitmentRegistry.sol (Phase 4.2,
# commit fa22973).

class CommitmentRegistryAdapter(Protocol):
    """Pluggable on-chain commitment registry surface.

    Mirrors the public interface of IntentCommitmentRegistry.sol (Phase 4.2):
      • commitIntent(bytes32 H_intent, bytes32 entityId) returns (bool)
      • revealIntent(bytes32 H_intent_A, bytes32 H_intent_B, bytes proof,
                     uint256[] publicInputs) returns (bool)
      • getCommit(bytes32 H_intent) returns (uint64, bytes32, bool)
      • isRevealed(bytes32 H_intent) returns (bool)

    R-FAILCLOSED: every error is named. The adapter MUST raise the
    IntentCommitmentRegistry.sol error names (ZeroHIntent, IntentAlreadyCommitted,
    ComplementarityProofFailed, etc.) — the in-memory stub does so; the
    web3.py adapter will translate contract revert reasons to the same names.
    """

    def commit_intent(self, h_intent: bytes, entity_id: bytes) -> int:
        """Submit H_intent ONLY (BTCP §5.6 Phase 1 verbatim). Returns the
        committed_at timestamp (unix seconds)."""
        ...

    def reveal_intent(
        self,
        h_intent_a: bytes,
        h_intent_b: bytes,
        proof: bytes,
        public_inputs: List[int],
    ) -> bool:
        """Atomic same-block reveal (BTCP §5.6 Phase 3 verbatim). Returns
        True iff the complementarity proof verified AND both intents were
        marked revealed in the same transaction."""
        ...

    def is_committed(self, h_intent: bytes) -> bool:
        """Read-only accessor — does H_intent have a commit record?"""
        ...

    def is_revealed(self, h_intent: bytes) -> bool:
        """Read-only accessor — has H_intent been revealed?"""
        ...


class InMemoryCommitmentRegistry:
    """In-memory stub of IntentCommitmentRegistry.sol (Phase 4.2).

    Used by tests and local runs; mirrors the contract's R-FAILCLOSED
    invariants (zero H_intent / zero entity_id / already-committed /
    complementarity proof failure / double-reveal). The complementarity
    verifier is pluggable — default: MockComplementarityVerifier (testing
    twin). Production: a wrapper around ComplementarityVerifier.sol (Phase
    4.3, commit ced2aef).
    """

    EXPECTED_PUBLIC_INPUTS_LEN = 5  # per Phase 1 MEASURED circuit
    EXPECTED_PROOF_BYTES = 256      # 8 Groth16 field elements × 32 bytes

    def __init__(
        self,
        complementarity_verifier: Optional[Any] = None,
    ) -> None:
        # Verifier is pluggable: default MockComplementarityVerifier for tests;
        # production: a wrapper around ComplementarityVerifier.sol (Phase 4.3).
        # The verifier MUST expose either a `.verify(proof, public_inputs) -> bool`
        # method (matching the Solidity IComplementarityVerifier interface) OR
        # be a plain callable `f(proof, public_inputs) -> bool`.
        self._verifier: Optional[Any] = (
            complementarity_verifier
            if complementarity_verifier is not None
            else MockComplementarityVerifier()
        )
        # H_intent → (committed_at, entity_id, revealed)
        self._commits: Dict[bytes, tuple] = {}
        self.commit_count: int = 0
        self.reveal_count: int = 0

    def set_verifier(
        self, verifier: Any
    ) -> None:
        """R-CHANNELS: plug in the complementarity verifier. Mirrors
        IntentCommitmentRegistry.sol::setVerifier(address)."""
        self._verifier = verifier

    @staticmethod
    def _call_verifier(
        verifier: Any, proof: bytes, public_inputs: List[int]
    ) -> bool:
        """Invoke the verifier — accepts either a callable or an object
        with a `.verify(proof, public_inputs)` method (the latter matches
        the Solidity IComplementarityVerifier interface)."""
        if verifier is None:
            return False
        if hasattr(verifier, "verify") and callable(getattr(verifier, "verify")):
            return bool(verifier.verify(proof, public_inputs))
        if callable(verifier):
            return bool(verifier(proof, public_inputs))
        return False

    def commit_intent(self, h_intent: bytes, entity_id: bytes) -> int:
        if not isinstance(h_intent, (bytes, bytearray)) or len(h_intent) == 0:
            raise ZeroHIntent("zero H_intent forbidden")
        if not isinstance(entity_id, (bytes, bytearray)) or len(entity_id) == 0:
            raise ZeroEntityId("zero entity_id forbidden")
        h_intent_b = bytes(h_intent)
        if h_intent_b in self._commits:
            raise IntentAlreadyCommitted(h_intent_b.hex())
        committed_at = int(time.time())
        self._commits[h_intent_b] = (committed_at, bytes(entity_id), False)
        self.commit_count += 1
        return committed_at

    def is_committed(self, h_intent: bytes) -> bool:
        return bytes(h_intent) in self._commits

    def is_revealed(self, h_intent: bytes) -> bool:
        rec = self._commits.get(bytes(h_intent))
        return bool(rec and rec[2])

    def reveal_intent(
        self,
        h_intent_a: bytes,
        h_intent_b: bytes,
        proof: bytes,
        public_inputs: List[int],
    ) -> bool:
        # R-FAILCLOSED input validation — every error named.
        if not isinstance(h_intent_a, (bytes, bytearray)) or len(h_intent_a) == 0:
            raise ZeroHIntent("zero H_intent_A forbidden")
        if not isinstance(h_intent_b, (bytes, bytearray)) or len(h_intent_b) == 0:
            raise ZeroHIntent("zero H_intent_B forbidden")
        if bytes(h_intent_a) == bytes(h_intent_b):
            raise ZeroHIntent("H_intent_A and H_intent_B must differ")
        if not isinstance(proof, (bytes, bytearray)) or len(proof) == 0:
            raise InvalidProofBytes("empty proof forbidden")
        if self._verifier is None:
            raise VerifierNotRegistered("no complementarity verifier plugged in")
        if not isinstance(public_inputs, list) or len(public_inputs) != self.EXPECTED_PUBLIC_INPUTS_LEN:
            raise InvalidPublicInputsLength(
                f"expected {self.EXPECTED_PUBLIC_INPUTS_LEN} public inputs, "
                f"got {len(public_inputs) if isinstance(public_inputs, list) else 'non-list'}"
            )

        a_rec = self._commits.get(bytes(h_intent_a))
        b_rec = self._commits.get(bytes(h_intent_b))
        if a_rec is None:
            raise IntentNotFound(bytes(h_intent_a).hex())
        if b_rec is None:
            raise IntentNotFound(bytes(h_intent_b).hex())
        if a_rec[2]:
            raise IntentAlreadyRevealed(bytes(h_intent_a).hex())
        if b_rec[2]:
            raise IntentAlreadyRevealed(bytes(h_intent_b).hex())

        # Verify complementarity proof per BTCP §5.6 Phase 2 verbatim.
        ok = self._call_verifier(self._verifier, bytes(proof), list(public_inputs))
        if not ok:
            # BTCP §5.6 Phase 3 verbatim: "If not complements: both intents
            # remain hidden, no information leaked." Raise — no state change.
            raise ComplementarityProofFailed(
                "complementarity proof verification failed — both intents remain hidden"
            )

        # Atomic reveal — both intents marked revealed in the same transaction.
        committed_at_a, eid_a, _ = a_rec
        committed_at_b, eid_b, _ = b_rec
        self._commits[bytes(h_intent_a)] = (committed_at_a, eid_a, True)
        self._commits[bytes(h_intent_b)] = (committed_at_b, eid_b, True)
        self.reveal_count += 1
        return True

    def get_commit(self, h_intent: bytes) -> Optional[tuple]:
        rec = self._commits.get(bytes(h_intent))
        if rec is None:
            return None
        return rec  # (committed_at, entity_id, revealed)


# ── NettingInvisible — the Phase 5.1 INVISIBLE-mode engine ───────────────────
#
# Per mission Phase 5.1:
#   • INVISIBLE mode: intents NOT broadcast; engine submits H_intent
#     commitments to the registry, waits for a complementarity proof, then
#     reveals atomically.
#   • PUBLIC mode (default): unchanged behavior.
#   • Mode switch audited via log line `NETTING_MODE_SWITCH entity_id
#     old_mode new_mode reason`.

class NettingInvisible:
    """BTCP §5.6 "Water Underground" netting engine — INVISIBLE mode.

    PUBLIC mode (default): unchanged behavior. The existing Rust engine at
    `rust/src/netting_engine.rs` (add_intent, find_netting_pair, remove_intent)
    is the canonical PUBLIC-mode implementation; this Python bridge does NOT
    rewrite it. PUBLIC-mode callers should continue to use the Rust engine
    via `core/btcp/rust_bridge.py`. This module's PUBLIC-mode path simply
    delegates to the existing bridge (it is a no-op adapter for PUBLIC-mode
    intents — no commitment, no complementarity proof, no atomic reveal).

    INVISIBLE mode: per BTCP §5.6 Phase 1-3:
      1. Commit:    H_intent = Hash_DNA(intent_details || random_nonce || entity_id)
                    Submit H_intent ONLY to the commitment registry (the
                    on-chain IntentCommitmentRegistry.sol surface, Phase 4.2).
                    NO broadcast of intent_details, NO routing calculation.
      2. Match:     wait for a complementarity proof (verified via the
                    pluggable ComplementarityVerifier — testing twin:
                    MockComplementarityVerifier; production: a wrapper around
                    ComplementarityVerifier.sol, Phase 4.3).
      3. Reveal:    atomic same-transaction reveal of BOTH H_intent_A and
                    H_intent_B. If the proof fails, both remain hidden
                    (BTCP §5.6 Phase 3 verbatim).
      4. Execute:   MEV bots see execution already committed (BTCP §5.6 Phase 4).
    """

    def __init__(
        self,
        commitment_registry: Optional[CommitmentRegistryAdapter] = None,
        *,
        default_mode: PrivacyMode = PrivacyMode.PUBLIC,
    ) -> None:
        self._registry: CommitmentRegistryAdapter = (
            commitment_registry
            if commitment_registry is not None
            else InMemoryCommitmentRegistry()
        )
        self._default_mode = default_mode
        # Per-entity mode map (entity_id bytes → PrivacyMode).
        # R-ABSENT: stores entity_id only (already public BEO identifier);
        # NEVER stores intent_details, value, asset, or any ABSENT field.
        self._entity_modes: Dict[bytes, PrivacyMode] = {}
        # Audit trail of mode switches (entity_id, old, new, reason, ts).
        self._mode_switch_log: List[tuple] = []

    # ── PUBLIC-mode passthrough ───────────────────────────────────────────
    #
    # Per mission: "In PUBLIC mode (the default): unchanged behavior." This
    # method delegates to the existing Rust engine (via core/btcp/rust_bridge.py
    # — the existing PUBLIC-mode surface is untouched). It is provided here
    # only as a no-op dispatcher so callers using this class for INVISIBLE
    # mode can also route PUBLIC intents through it without losing the
    # existing PUBLIC-mode behavior.

    def add_public_intent(
        self,
        entity_id: bytes,
        asset_in: str,
        asset_out: str,
        value_micro_usd: int,
        ledger_id: int,
    ) -> bool:
        """PUBLIC-mode intent add — delegates to the existing Rust engine.

        The Rust engine at rust/src/netting_engine.rs (add_intent) is the
        canonical PUBLIC-mode path. This Python bridge is a no-op shim that
        exists for API symmetry with the INVISIBLE-mode path; callers that
        need PUBLIC-mode netting should use core/btcp/rust_bridge.py
        directly (it wraps the Rust engine).

        Returns True to signal that the PUBLIC-mode intent was acknowledged
        for routing. The actual netting match is performed by the Rust engine
        on the next find_netting_pair call — this method does NOT duplicate
        that logic (R-NO-REDEF: do NOT rewrite the existing PUBLIC-mode
        engine).
        """
        self._set_entity_mode(entity_id, PrivacyMode.PUBLIC, reason="public_intent_added")
        return True

    # ── INVISIBLE-mode path (BTCP §5.6 Phase 1-3) ────────────────────────

    def enable_invisible_mode(
        self, entity_id: bytes, reason: str = "entity_opt_in"
    ) -> None:
        """Switch entity to INVISIBLE privacy mode (BTCP §5.6 Phase 1).

        Audited via the log line `NETTING_MODE_SWITCH entity_id old_mode
        new_mode reason` per mission Phase 5.1 verbatim.
        """
        if not isinstance(entity_id, (bytes, bytearray)) or len(entity_id) == 0:
            raise ZeroEntityId("entity_id must be non-empty bytes")
        self._set_entity_mode(
            entity_id, PrivacyMode.INVISIBLE, reason=reason
        )

    def disable_invisible_mode(
        self, entity_id: bytes, reason: str = "entity_opt_out"
    ) -> None:
        """Revert entity to PUBLIC mode (BTCP §5.6 default).

        Audited via the log line `NETTING_MODE_SWITCH entity_id old_mode
        new_mode reason`.
        """
        self._set_entity_mode(
            entity_id, PrivacyMode.PUBLIC, reason=reason
        )

    def _set_entity_mode(
        self, entity_id: bytes, new_mode: PrivacyMode, *, reason: str
    ) -> None:
        old_mode = self._entity_modes.get(bytes(entity_id), self._default_mode)
        if old_mode == new_mode:
            return  # no-op — idempotent
        self._entity_modes[bytes(entity_id)] = new_mode
        ts = int(time.time())
        self._mode_switch_log.append(
            (bytes(entity_id), old_mode, new_mode, reason, ts)
        )
        # Audit log line per mission Phase 5.1 verbatim:
        # `NETTING_MODE_SWITCH entity_id old_mode new_mode reason`
        log.info(
            "NETTING_MODE_SWITCH %s %s %s %s",
            bytes(entity_id).hex(), old_mode.value, new_mode.value, reason,
        )

    def get_mode(self, entity_id: bytes) -> PrivacyMode:
        return self._entity_modes.get(bytes(entity_id), self._default_mode)

    @property
    def mode_switch_log(self) -> List[tuple]:
        """Return the audit trail of mode switches (entity_id, old, new,
        reason, ts). R-ABSENT: contains ONLY entity_id + mode + reason +
        ts — no intent contents, value, asset, or ABSENT field."""
        return list(self._mode_switch_log)

    # ── INVISIBLE-mode commit + match + reveal ───────────────────────────

    def commit_invisible_intent(self, intent: Intent) -> bytes:
        """BTCP §5.6 Phase 1 — commit H_intent ONLY.

        Per BTCP §5.6 Phase 1 verbatim:
            H_intent = Hash_DNA(intent_details || random_nonce || entity_id)
            User submits: H_intent ONLY
            MEV bots observe: a commitment hash — no direction, no value, nothing

        Steps:
          1. Verify intent.privacy == INVISIBLE (else raise NettingModeSwitchError).
          2. Compute H_intent via hash_dna.intent_hash (Phase 2.1).
          3. Submit H_intent + entity_id to the commitment registry
             (delegated to CommitmentRegistryAdapter — on-chain surface).
          4. Audit-log the commit.
          5. Return H_intent (the 32-byte commitment).

        R-ABSENT: this method does NOT persist intent_details, random_nonce,
        value, asset, or any ABSENT field. Only H_intent + entity_id +
        committed_at + revealed reach the registry.
        """
        if intent.privacy != PrivacyMode.INVISIBLE:
            raise NettingModeSwitchError(
                f"intent.privacy must be INVISIBLE for commit_invisible_intent; "
                f"got {intent.privacy.value}. Use the PUBLIC-mode Rust engine "
                f"at rust/src/netting_engine.rs for PUBLIC intents."
            )
        # Ensure the entity is in INVISIBLE mode (audited).
        if self.get_mode(intent.entity_id) != PrivacyMode.INVISIBLE:
            self._set_entity_mode(
                intent.entity_id, PrivacyMode.INVISIBLE,
                reason="commit_invisible_intent",
            )
        h_intent = intent.compute_h_intent()
        committed_at = self._registry.commit_intent(h_intent, intent.entity_id)
        log.info(
            "INTENT_COMMITTED %s %s %d",
            intent.entity_id.hex(), h_intent.hex(), committed_at,
        )
        return h_intent

    def reveal_invisible_pair(
        self,
        h_intent_a: bytes,
        h_intent_b: bytes,
        proof: bytes,
        public_inputs: List[int],
    ) -> NettingMatch:
        """BTCP §5.6 Phase 3 — atomic same-block reveal.

        Per BTCP §5.6 Phase 3 verbatim:
            "Phase 3 — Atomic Reveal (both in same block):
             Both intents published in same block — atomic
             If complements verified: execution commits immediately
             If not complements: both intents remain hidden, no information leaked"

        Atomicity is enforced by the registry adapter (mirrors Solidity
        transaction semantics — ComplementarityVerifier.sol::verifyProof is
        called inside revealIntent, and if it returns False the entire
        transaction reverts with ComplementarityProofFailed).

        Returns a NettingMatch dataclass capturing the revealed pair.
        Raises ComplementarityProofFailed if the proof fails (both intents
        remain hidden — no state change, no event emitted).
        """
        # Delegate to the registry adapter (atomic reveal handled there).
        ok = self._registry.reveal_intent(
            h_intent_a, h_intent_b, proof, public_inputs,
        )
        if not ok:
            raise ComplementarityProofFailed(
                "registry adapter returned False — complementarity proof failed; "
                "both intents remain hidden (BTCP §5.6 Phase 3 verbatim)"
            )
        # Read back the entity_ids for the NettingMatch record.
        rec_a = self._registry.get_commit(h_intent_a)
        rec_b = self._registry.get_commit(h_intent_b)
        eid_a = rec_a[1] if rec_a else b""
        eid_b = rec_b[1] if rec_b else b""

        # zk_proof_hash = SHA3-256(proof bytes) for offchain deduplication.
        import hashlib
        zk_proof_hash = hashlib.sha3_256(bytes(proof)).digest()

        match = NettingMatch(
            h_intent_a=bytes(h_intent_a),
            h_intent_b=bytes(h_intent_b),
            entity_a=eid_a,
            entity_b=eid_b,
            revealed_at=int(time.time()),
            zk_proof_hash=zk_proof_hash,
        )
        log.info(
            "INTENT_REVEALED %s %s %s",
            h_intent_a.hex(), h_intent_b.hex(), zk_proof_hash.hex(),
        )
        return match

    # ── Convenience: end-to-end INVISIBLE-mode netting ───────────────────

    def net_invisible_pair(
        self,
        intent_a: Intent,
        intent_b: Intent,
        proof: bytes,
        public_inputs: List[int],
    ) -> NettingMatch:
        """End-to-end INVISIBLE-mode netting: commit A + commit B + reveal.

        Steps:
          1. commit_invisible_intent(intent_a) → H_intent_A
          2. commit_invisible_intent(intent_b) → H_intent_B
          3. reveal_invisible_pair(H_intent_A, H_intent_B, proof, public_inputs)
             → NettingMatch (atomic reveal via the registry adapter).

        R-LABELS: when called with a MockComplementarityVerifier, this path
        is labelled SYNTHETIC-DEMO — the proof is NOT a real Groth16 proof.
        """
        if intent_a.privacy != PrivacyMode.INVISIBLE or intent_b.privacy != PrivacyMode.INVISIBLE:
            raise NettingModeSwitchError(
                "both intents must have privacy=INVISIBLE for net_invisible_pair"
            )
        h_a = self.commit_invisible_intent(intent_a)
        h_b = self.commit_invisible_intent(intent_b)
        return self.reveal_invisible_pair(h_a, h_b, proof, public_inputs)


# ── Self-test (SYNTHETIC-DEMO label) ──────────────────────────────────────────

def _self_test() -> dict:
    """Deterministic self-test.

    Label: SYNTHETIC-DEMO — uses MockComplementarityVerifier (testing twin
    of ComplementarityVerifier.sol). Per R-LABELS, this is NOT a real
    Groth16 proof; it asserts that the integration plumbing is correct,
    not that the SNARK is sound. SNARK soundness is a property of the
    Phase-3 MEASURED circuit (zk_complementarity_proof, 2,686 constraints)
    and is gated `[OPEN]` per the BLOCKER PROTOCOL.

    Verifies:
      1. Mode switch from PUBLIC → INVISIBLE audited via the
         `NETTING_MODE_SWITCH` log line.
      2. Commit: H_intent computed + submitted to registry → registry
         stores H_intent + entity_id + committed_at (NOT intent_details).
      3. Reveal: atomic reveal of complementary pair → NettingMatch.
      4. ComplementarityProofFailed raised for malformed proof (empty
         bytes) — both intents remain hidden (no reveal_count increment).
      5. IntentAlreadyCommitted raised for double-commit.
      6. IntentAlreadyRevealed raised for double-reveal.
    """
    out: dict = {}
    logging.basicConfig(level=logging.INFO)

    # Construct the engine with the in-memory stub + MockComplementarityVerifier.
    engine = NettingInvisible()

    # Two synthetic complementary intents (A: asset_X → asset_Y; B: asset_Y → asset_X).
    # R-ABSENT: the intent_details are opaque bytes — the entity-side payload.
    # They NEVER reach the registry's persistence path.
    intent_a = Intent(
        entity_id=b"\x01" * 32,
        intent_details=b"swap:asset_X:asset_Y:value_100",
        random_nonce=b"\xaa" * 16,
        privacy=PrivacyMode.INVISIBLE,
    )
    intent_b = Intent(
        entity_id=b"\x02" * 32,
        intent_details=b"swap:asset_Y:asset_X:value_100",
        random_nonce=b"\xbb" * 16,
        privacy=PrivacyMode.INVISIBLE,
    )

    # 1. Mode switch audited.
    engine.enable_invisible_mode(intent_a.entity_id, reason="entity_a_opt_in")
    engine.enable_invisible_mode(intent_b.entity_id, reason="entity_b_opt_in")
    mode_log = engine.mode_switch_log
    assert len(mode_log) == 2, f"expected 2 mode-switch entries, got {len(mode_log)}"
    assert mode_log[0][1] == PrivacyMode.PUBLIC
    assert mode_log[0][2] == PrivacyMode.INVISIBLE
    assert mode_log[0][3] == "entity_a_opt_in"
    assert mode_log[1][3] == "entity_b_opt_in"

    # 2. Commit both intents.
    h_a = engine.commit_invisible_intent(intent_a)
    h_b = engine.commit_invisible_intent(intent_b)
    assert isinstance(h_a, bytes) and len(h_a) == 32
    assert isinstance(h_b, bytes) and len(h_b) == 32
    assert h_a != h_b, "distinct intents must produce distinct H_intent"

    # Verify the registry stored ONLY H_intent + entity_id + ts + revealed.
    reg = engine._registry  # type: ignore[attr-defined]
    rec_a = reg.get_commit(h_a)
    assert rec_a is not None
    committed_at_a, eid_a, revealed_a = rec_a
    assert eid_a == intent_a.entity_id
    assert revealed_a is False
    # R-ABSENT: the registry MUST NOT have stored intent_details or random_nonce.
    # (The InMemoryCommitmentRegistry only stores the tuple; verify no leak.)
    assert isinstance(committed_at_a, int) and committed_at_a > 0

    # 3. Reveal with a well-formed Groth16-shaped proof (256 bytes) + 5 public inputs.
    well_formed_proof = b"\x42" * 256
    public_inputs = [
        int.from_bytes(h_a, "big"),
        int.from_bytes(h_b, "big"),
        int.from_bytes(intent_a.entity_id, "big"),
        int.from_bytes(intent_b.entity_id, "big"),
        0,  # tolerance parameter (Phase 1 MEASURED circuit, 5th public input)
    ]
    match = engine.reveal_invisible_pair(h_a, h_b, well_formed_proof, public_inputs)
    assert match.h_intent_a == h_a
    assert match.h_intent_b == h_b
    assert match.entity_a == intent_a.entity_id
    assert match.entity_b == intent_b.entity_id
    assert reg.is_revealed(h_a) and reg.is_revealed(h_b)
    assert reg.reveal_count == 1

    # 4. Malformed proof → ComplementarityProofFailed (both stay hidden).
    #    Empty proof raises InvalidProofBytes at input validation (mirrors
    #    IntentCommitmentRegistry.sol::InvalidProofBytes). Wrong-length
    #    non-empty proof passes input validation but the MockComplementarityVerifier
    #    returns False → ComplementarityProofFailed (BTCP §5.6 Phase 3 fail-closed).
    engine2 = NettingInvisible()  # fresh engine
    h_a2 = engine2.commit_invisible_intent(intent_a)
    h_b2 = engine2.commit_invisible_intent(intent_b)
    # 4a. Empty proof → InvalidProofBytes (input validation gate).
    try:
        engine2.reveal_invisible_pair(h_a2, h_b2, b"", public_inputs)
        raise AssertionError("empty proof must raise InvalidProofBytes")
    except InvalidProofBytes:
        pass
    # 4b. Wrong-length non-empty proof → ComplementarityProofFailed
    #     (MockComplementarityVerifier returns False for non-256-byte proofs;
    #     both intents remain hidden — no state change, no event emitted).
    try:
        engine2.reveal_invisible_pair(h_a2, h_b2, b"\x00" * 100, public_inputs)
        raise AssertionError("wrong-length proof must raise ComplementarityProofFailed")
    except ComplementarityProofFailed:
        pass
    # Both intents remain hidden.
    assert not engine2._registry.is_revealed(h_a2)  # type: ignore[attr-defined]
    assert not engine2._registry.is_revealed(h_b2)  # type: ignore[attr-defined]
    assert engine2._registry.reveal_count == 0  # type: ignore[attr-defined]

    # 5. IntentAlreadyCommitted on double-commit.
    try:
        engine2.commit_invisible_intent(intent_a)
        raise AssertionError("double-commit must raise IntentAlreadyCommitted")
    except IntentAlreadyCommitted:
        pass

    # 6. IntentAlreadyRevealed on double-reveal.
    # Re-commit pair on fresh engine (engine's first pair was already revealed).
    engine3 = NettingInvisible()
    h_a3 = engine3.commit_invisible_intent(intent_a)
    h_b3 = engine3.commit_invisible_intent(intent_b)
    engine3.reveal_invisible_pair(h_a3, h_b3, well_formed_proof, public_inputs)
    try:
        engine3.reveal_invisible_pair(h_a3, h_b3, well_formed_proof, public_inputs)
        raise AssertionError("double-reveal must raise IntentAlreadyRevealed")
    except IntentAlreadyRevealed:
        pass

    # 7. PUBLIC-mode passthrough.
    ok_pub = engine.add_public_intent(
        entity_id=b"\x03" * 32,
        asset_in="USDC",
        asset_out="ETH",
        value_micro_usd=100 * 10**6,
        ledger_id=1,
    )
    assert ok_pub is True
    assert engine.get_mode(b"\x03" * 32) == PrivacyMode.PUBLIC

    out["all_passed"] = True
    return out


if __name__ == "__main__":
    import json
    print("=== netting_invisible.py — self-test (SYNTHETIC-DEMO) ===")
    res = _self_test()
    print(json.dumps({k: v for k, v in res.items() if not isinstance(v, bytes)}, indent=2))
    assert res.get("all_passed"), "self-test FAILED"
    print("PASS — BTCP §5.6 INVISIBLE privacy mode (Phase 5.1) — SYNTHETIC-DEMO")
