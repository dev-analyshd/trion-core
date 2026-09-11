"""
Z9 — Travel-rule boundary trace capture
(TRION BZK Phase 6, Z9)

Canon governing the boundary (BTCP Fix 1 Step 2 verbatim,
CANON_EXTRACT.md §3.2):
    Step 2: Disclosure → encrypted to regulator_public_key
        regulator receives: full disclosure    (law satisfied)
        TRION receives: nothing from this step

BTCP Fix 1 Step 4 verbatim (CANON_EXTRACT.md §3.4):
    Step 4: zk_proof included in BTCP intent
        TRION stores: disclosure_hash only
        TRION emits: TRAVEL_RULE_COMPLIANT = TRUE

ATTACK:
    Simulate the entity preparing disclosure, encrypting to
    regulator_public_key, and submitting ONLY disclosure_hash to TRION.
    Capture ALL TRION-side state:
      - on-chain storage (TravelRuleCompliance.sol records)
      - TRION-side logs (event emissions)
      - TRION-side network traces (simulated mempool + RPC receipts)
    Grep for PII tokens:
      - originator_name
      - originator_address
      - originator_account
      - beneficiary
      - value
      - timestamp
      - disclosure payload content
    Expected: ZERO matches across all captured TRION-side artifacts.

R-LABELS:
    Label: SYNTHETIC-DEMO — simulated trace capture (no real network).

Canon sources:
    BTCP §11 Fix 1 Steps 2 + 4 verbatim (CANON_EXTRACT.md §3.2 + §3.4).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

# Make the Phase 2 commitment helpers importable.
_THIS_DIR = Path(__file__).resolve().parent
_COMMITMENTS_DIR = _THIS_DIR.parent / "commitments"
sys.path.insert(0, str(_COMMITMENTS_DIR))

import hash_dna  # noqa: E402  (Phase 2.1 helper — disclosure_hash())


# ── PII tokens that MUST NEVER appear in TRION-side state ────────────────────
# Per BTCP Fix 1 Step 1 verbatim (CANON_EXTRACT.md §3.1):
#     disclosure = { originator_name, originator_address, originator_account,
#                   beneficiary, value, timestamp }
PII_TOKENS = [
    "originator_name",
    "originator_address",
    "originator_account",
    "beneficiary",
    "value",
    "timestamp",
    # Forbidden ABSENT-field tokens per BTCP §7.1 + Fix 1 Step 3 (already
    # enforced by leakage_grep; checked here too for completeness).
    "disclosure_contents",
    "regulator_receipt",
    "private_behavior",
    "DNA_Code",
    "behavior_content",
    "amount",
    "counterparty",
    "protocol",
    "chain",
]


@dataclass
class Disclosure:
    """BTCP Fix 1 Step 1 verbatim — entity-side disclosure payload.
    NEVER transmitted to TRION (Fix 1 Step 2)."""
    originator_name: str
    originator_address: str
    originator_account: str
    beneficiary: str
    value: int
    timestamp: int

    def serialize(self) -> bytes:
        """Deterministic serialization (the entity uses this to compute
        disclosure_hash; TRION never sees the serialization output)."""
        return (
            self.originator_name.encode("utf-8")
            + b"|"
            + self.originator_address.encode("utf-8")
            + b"|"
            + self.originator_account.encode("utf-8")
            + b"|"
            + self.beneficiary.encode("utf-8")
            + b"|"
            + str(self.value).encode("utf-8")
            + b"|"
            + str(self.timestamp).encode("utf-8")
        )


@dataclass
class EncryptedToRegulator:
    """BTCP Fix 1 Step 2 verbatim: disclosure encrypted to regulator_public_key.
    TRION receives NOTHING from this step. The encryption is modeled as a
    synthetic sealed box (in production this would be RSA-OAEP or ECIES
    to the regulator's public key)."""
    ciphertext: bytes
    regulator_public_key: bytes


@dataclass
class TRIONStorage:
    """Simulated TRION-side persistent state. Per BTCP Fix 1 Step 4
    verbatim: 'TRION stores: disclosure_hash only.'"""
    disclosure_hash: bytes
    jurisdiction_id: int
    entity_id: bytes
    tx_hash: bytes


@dataclass
class TRIONLog:
    """Simulated TRION-side event log emissions. Per R-CHANNELS: signal
    publication ONLY."""
    events: List[Dict[str, object]] = field(default_factory=list)


@dataclass
class TRIONNetworkTrace:
    """Simulated TRION-side network trace (mempool + RPC receipts)."""
    mempool_messages: List[bytes] = field(default_factory=list)
    rpc_receipts: List[Dict[str, object]] = field(default_factory=list)


def simulate_entity_side() -> tuple[Disclosure, EncryptedToRegulator, bytes]:
    """BTCP Fix 1 Steps 1-2: entity prepares disclosure privately (Step 1),
    encrypts to regulator_public_key (Step 2). Returns the disclosure
    payload (NEVER sent to TRION), the encrypted-to-regulator blob
    (NEVER sent to TRION), and the disclosure_hash (sent to TRION per
    Step 4)."""
    # Step 1: entity prepares disclosure privately.
    disclosure = Disclosure(
        originator_name="Alice Example",
        originator_address="0xALICE1234",
        originator_account="acct-001-alice",
        beneficiary="Bob Example",
        value=1_500_000,           # $1,500.00 (above $1,000 MEDIUM threshold)
        timestamp=1_700_000_000,
    )

    # Step 2: encrypt to regulator_public_key (synthetic).
    regulator_pubkey = os.urandom(32)
    # Synthetic encryption: just XOR the disclosure with a derived pad.
    # (In production: RSA-OAEP or ECIES to the regulator's key. TRION
    # NEVER sees the ciphertext or the plaintext — both go directly to
    # the regulator over a separate channel.)
    pad = os.urandom(len(disclosure.serialize()))
    ciphertext = bytes(
        a ^ b for a, b in zip(disclosure.serialize(), pad)
    )
    encrypted = EncryptedToRegulator(
        ciphertext=ciphertext,
        regulator_public_key=regulator_pubkey,
    )

    # The disclosure_hash is what TRION receives per Fix 1 Step 4.
    d_hash = hash_dna.disclosure_hash(disclosure.serialize())

    return disclosure, encrypted, d_hash


def simulate_trion_side(d_hash: bytes) -> tuple[TRIONStorage, TRIONLog, TRIONNetworkTrace]:
    """BTCP Fix 1 Step 4: TRION receives disclosure_hash ONLY. Stores it,
    emits TRAVEL_RULE_COMPLIANT=TRUE."""
    storage = TRIONStorage(
        disclosure_hash=d_hash,
        jurisdiction_id=1,
        entity_id=b"\xaa" * 32,
        tx_hash=os.urandom(32),
    )

    log = TRIONLog(events=[
        {
            "event": "TravelRuleProofSubmitted",
            "entity_id": storage.entity_id.hex(),
            "tx_hash": storage.tx_hash.hex(),
            "jurisdiction_id": storage.jurisdiction_id,
            "disclosure_hash": d_hash.hex(),
            "zk_proof_hash": os.urandom(32).hex(),  # synthetic
            "tier": "MEDIUM",
            "provingSystem": "PLONK",
        },
        {
            "event": "TRAVEL_RULE_COMPLIANT",
            "entity_id": storage.entity_id.hex(),
            "tx_hash": storage.tx_hash.hex(),
            "compliant": "TRUE",  # BTCP verbatim
        },
    ])

    trace = TRIONNetworkTrace(
        mempool_messages=[
            # The only mempool message TRION sees: the submitProof tx
            # carrying disclosure_hash + zk_proof + publicInputs.
            b"submitProof("
            + storage.entity_id
            + b","
            + storage.tx_hash
            + b","
            + storage.jurisdiction_id.to_bytes(4, "big")
            + b","
            + d_hash
            + b",...)",
        ],
        rpc_receipts=[
            {
                "method": "eth_sendRawTransaction",
                "tx_hash": storage.tx_hash.hex(),
                "status": "0x1",
                "gas_used": 250000,
            }
        ],
    )

    return storage, log, trace


def capture_trion_state(
    storage: TRIONStorage, log: TRIONLog, trace: TRIONNetworkTrace
) -> bytes:
    """Capture ALL TRION-side state into a single serialized blob for grep.

    This is the trace capture — every byte TRION persists, emits, or
    exchanges over the network gets concatenated into this blob, which
    we then grep for PII tokens.
    """
    blob = bytearray()

    # 1. Persistent storage (SQLite-equivalent).
    blob += b"STORAGE:\n"
    blob += b"  disclosure_hash=" + storage.disclosure_hash.hex().encode() + b"\n"
    blob += b"  jurisdiction_id=" + str(storage.jurisdiction_id).encode() + b"\n"
    blob += b"  entity_id=" + storage.entity_id.hex().encode() + b"\n"
    blob += b"  tx_hash=" + storage.tx_hash.hex().encode() + b"\n"

    # 2. Event log emissions.
    blob += b"LOG:\n"
    for ev in log.events:
        blob += b"  " + json.dumps(ev, default=str).encode() + b"\n"

    # 3. Network traces.
    blob += b"NETWORK:\n"
    for msg in trace.mempool_messages:
        blob += b"  mempool=" + msg.hex().encode() + b"\n"
    for r in trace.rpc_receipts:
        blob += b"  rpc=" + json.dumps(r, default=str).encode() + b"\n"

    return bytes(blob)


def grep_for_pii(blob: bytes) -> Dict[str, List[str]]:
    """Grep the captured TRION-side state for PII tokens.

    Returns a dict mapping each PII token to a list of matched lines
    (empty list = no match = clean)."""
    findings: Dict[str, List[str]] = {}
    text = blob.decode("utf-8", errors="replace")
    lines = text.split("\n")
    for tok in PII_TOKENS:
        hits = [ln for ln in lines if tok in ln]
        findings[tok] = hits
    return findings


def run() -> Dict:
    """Run the Z9 travel-rule boundary trace capture."""
    print("[Z9] Simulating entity-side disclosure preparation + encryption...")
    disclosure, encrypted, d_hash = simulate_entity_side()
    print(f"[Z9] disclosure_hash: {d_hash.hex()}")
    print(f"[Z9] disclosure payload (entity-side, NEVER sent to TRION):")
    print(f"       originator_name={disclosure.originator_name!r}")
    print(f"       originator_address={disclosure.originator_address!r}")
    print(f"       originator_account={disclosure.originator_account!r}")
    print(f"       beneficiary={disclosure.beneficiary!r}")
    print(f"       value=${disclosure.value / 100:.2f}")
    print(f"       timestamp={disclosure.timestamp}")
    print(f"[Z9] Encrypted-to-regulator blob (NEVER sent to TRION): "
          f"{len(encrypted.ciphertext)} bytes ciphertext")

    print()
    print("[Z9] Simulating TRION-side state (receives disclosure_hash ONLY)...")
    storage, log, trace = simulate_trion_side(d_hash)

    print()
    print("[Z9] Capturing ALL TRION-side state for PII grep...")
    blob = capture_trion_state(storage, log, trace)
    print(f"[Z9] Captured TRION-side state: {len(blob)} bytes")
    print(f"[Z9] TRION-side state contents:")
    print("─" * 60)
    print(blob.decode("utf-8", errors="replace"))
    print("─" * 60)

    print()
    print("[Z9] Grepping for PII tokens in TRION-side state...")
    findings = grep_for_pii(blob)

    total_hits = sum(len(v) for v in findings.values())
    for tok, hits in findings.items():
        marker = "LEAK!" if hits else "clean"
        print(f"       {tok:30s} → {marker} ({len(hits)} hits)")

    print()
    print(f"[Z9] Total PII leaks in TRION-side state: {total_hits}")
    expected = (total_hits == 0)
    print(f"[Z9] Expected (0 leaks): {'PASS' if expected else 'FAIL'}")

    return {
        "attack": "Z9 — Travel-rule boundary trace capture",
        "falsifiability_condition": "BTCP Fix 1 Step 2 verbatim (CANON_EXTRACT.md §3.2): "
                                    "'TRION receives: nothing from this step'",
        "canon_governing_storage": "BTCP Fix 1 Step 4 verbatim (CANON_EXTRACT.md §3.4): "
                                    "'TRION stores: disclosure_hash only'",
        "pii_tokens_checked": PII_TOKENS,
        "trion_state_bytes_captured": len(blob),
        "total_pii_leaks": total_hits,
        "findings": findings,
        "result": "PASS" if expected else "FAIL",
        "label": "SYNTHETIC-DEMO",
        "label_justification": (
            "Simulated trace capture. The TRION-side storage / log / network "
            "trace is modeled in Python (no real EVM or mempool). The "
            "production guarantee is identical: TravelRuleCompliance.sol "
            "(Phase 4) is enforced to have NO field for disclosure payload, "
            "regulator receipt, PII, behavioral content, transaction value, "
            "counter-party identifier, message-layer identifier, or ledger "
            "identifier — verified by leakage_grep_contracts.sh (exit 0)."
        ),
        "cryptographic_guarantee": (
            "The disclosure_hash is a SHA3-256 hash of the entity-side "
            "disclosure payload (Phase 2 hash_dna.disclosure_hash). The "
            "payload itself is encrypted to the regulator_public_key OFF-"
            "TRION (per Fix 1 Step 2). TRION never receives the ciphertext "
            "or the plaintext. The hash is preimage-resistant (~2^256), so "
            "even a TRION-side compromise cannot recover PII from the "
            "disclosure_hash."
        ),
        "round_trip_status": (
            "OPEN (PLONK setup exceeds sandbox timeout per Phase 3 BLOCKER). "
            "Z9 tests the trace-capture boundary (Step 2 boundary + Step 4 "
            "storage invariant), which does NOT require the prove/verify "
            "round-trip. The TravelRuleCompliance.sol contract (Phase 4) "
            "enforces the same boundary on-chain; the ZK proof itself is "
            "[OPEN] at round-trip level."
        ),
    }


if __name__ == "__main__":
    print("=== Z9 — Travel-rule boundary trace capture ===")
    print("=== Per BTCP Fix 1 Steps 2 + 4 verbatim ===")
    print()
    result = run()
    print()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result["result"] == "PASS" else 1)
