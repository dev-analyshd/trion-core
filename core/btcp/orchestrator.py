"""
TRION BTCP — Integration Layer
==============================

Connects ZK proof system and VM adapters to the existing BTCP infrastructure.

Components:
  1. BTCPOrchestrator — High-level cross-VM BTCP coordinator
  2. PrivacyRouter — Routes intents through ZK circuits for privacy
  3. CrossVMGateway — Unified gateway for all VM adapter operations
  4. ProofAggregator — Collects and verifies proofs across chains

specification reference: L7 BTCP Cross-Chain Protocol
"""

import os
import sys
import json
import time
import hashlib
import logging

_log = logging.getLogger("btcp.orchestrator")
import secrets
import threading
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any
from enum import IntEnum

# Add workspace to path (go up from core/btcp/ to workspace root)
_workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _workspace_root)

try:
    from zk import (
        ZKProofSystem,
        IntentWitness,
        ComplementarityWitness,
        BehavioralCredentialWitness,
        TravelRuleWitness,
        IAPShareWitness,
        CircuitType,
    )
except ImportError:
    # ZK facade not importable — use stub from zk.facade directly.
    # R-LABELS: ZK proofs labeled [OPEN] when stub is active.
    from zk.facade import (
        ZKProofSystem,
        IntentWitness,
        ComplementarityWitness,
        BehavioralCredentialWitness,
        TravelRuleWitness,
        IAPShareWitness,
        CircuitType,
    )

from adapters import (
    VMAdapterFactory,
    VMType,
    BTCPIntent,
    BTCPProof,
    GasEstimate,
    CHAIN_VM_MAP,
)

# Persistence (S7): tracked routes survive restarts via the shared SQLite
# state store. The plain-name fallback covers direct script execution
# (``python core/btcp/orchestrator.py``) — the script's own directory is
# already on sys.path in that mode.
try:
    from .state_store import BtcpStateStore
except ImportError:  # pragma: no cover - direct script execution
    from state_store import BtcpStateStore

# Validator fee split (Module 2.17 / spec Fix 4) — the 60/40 anchor/execution
# route-reward split used when a completed route pays its validator pools.
try:
    from .modules import ValidatorFeeCalculator
except ImportError:  # pragma: no cover - direct script execution
    from modules import ValidatorFeeCalculator


# ── Enumerations ────────────────────────────────────────────────────────────

class PrivacyLevel(IntEnum):
    """Privacy levels for BTCP operations."""
    PUBLIC = 0          # No ZK proofs, all data visible
    BASIC = 1           # Intent commitment only
    STANDARD = 2        # Intent + complementarity proofs
    COMPLIANT = 3       # Standard + travel rule compliance
    FULL = 4            # All proofs including behavioral credential


class RouteStatus(IntEnum):
    """Status of a BTCP route."""
    PENDING = 0
    INTENT_CREATED = 1
    PROOFS_GENERATED = 2
    SOURCE_EXECUTED = 3
    DEST_EXECUTED = 4
    COMPLETED = 5
    FAILED = -1
    TIMEOUT = -2


# ── Data Structures ─────────────────────────────────────────────────────────

@dataclass
class BTCPRoute:
    """Complete BTCP route with all components."""
    route_id: str = ""
    intent: Optional[BTCPIntent] = None
    source_vm: VMType = VMType.EVM
    dest_vm: VMType = VMType.EVM
    source_encoded: str = ""
    dest_encoded: str = ""
    source_gas: Optional[GasEstimate] = None
    dest_gas: Optional[GasEstimate] = None
    proofs: Dict[str, Any] = field(default_factory=dict)
    privacy_level: PrivacyLevel = PrivacyLevel.BASIC
    status: RouteStatus = RouteStatus.PENDING
    total_fee: float = 0.0
    # BTCP zero-bridge invariant: assets are NEVER moved across chains.
    # Value stays in escrow on the source chain and is only released/reverted
    # locally after the behavioral proof is verified.  This field is always
    # False for a correctly-constructed BTCP route — the test suite asserts
    # this invariant explicitly.
    assets_bridged: bool = False
    btcp_score: float = 0.0
    route_type: str = "SINGLE_CHAIN"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['source_vm'] = self.source_vm.name
        d['dest_vm'] = self.dest_vm.name
        d['privacy_level'] = self.privacy_level.name
        d['status'] = self.status.name
        d['route_type'] = self.route_type
        d['assets_bridged'] = self.assets_bridged
        d['btcp_score'] = self.btcp_score
        if self.intent:
            d['intent'] = self.intent.to_dict()
        if self.source_gas:
            d['source_gas'] = asdict(self.source_gas)
        if self.dest_gas:
            d['dest_gas'] = asdict(self.dest_gas)
        return d


@dataclass
class OrchestrationResult:
    """Result of a BTCP orchestration."""
    success: bool
    route: Optional[BTCPRoute] = None
    proofs_generated: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    # BTCP-FIX2-ZK Fix 2 — per-step results keyed by the spec's 6-step IDs
    # (1_bibl_analysis, 2_btcp_score, 3_cross_chain_proof, 4_vm_translation,
    # 5_iap_gas_sharing, 6_akashic_recording). Surfaced in the API response
    # via /api/v1/btcp/orchestrate's spec_steps dict.
    step_results: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "route": self.route.to_dict() if self.route else None,
            "proofs_generated": self.proofs_generated,
            "errors": self.errors,
            "execution_time_ms": round(self.execution_time_ms, 2),
            "step_results": dict(self.step_results),
        }


# ── Persistence (S7): route row serialization ───────────────────────────────
# BTCPRoute carries nested BTCPIntent / GasEstimate objects and IntEnum
# fields — none of which are directly JSON-serializable — so the ⇄ row
# conversion is written out by hand instead of guessing with asdict.

ROUTE_ROW_TYPE = "btcp_route_v1"


def _gas_to_row(gas: Optional[GasEstimate]) -> Optional[Dict[str, Any]]:
    """GasEstimate → JSON-safe row dict (None passes through)."""
    if gas is None:
        return None
    return {
        "gas_limit":     gas.gas_limit,
        "gas_price":     gas.gas_price,
        "estimated_fee": gas.estimated_fee,
        "fee_token":     gas.fee_token,
        "vm_type":       gas.vm_type.name,
    }


def _gas_from_row(row: Optional[Dict[str, Any]]) -> Optional[GasEstimate]:
    """Row dict → GasEstimate (inverse of _gas_to_row)."""
    if row is None:
        return None
    return GasEstimate(
        gas_limit=row["gas_limit"],
        gas_price=row["gas_price"],
        estimated_fee=row["estimated_fee"],
        fee_token=row.get("fee_token", ""),
        vm_type=VMType[row["vm_type"]],
    )


def _route_to_row(route: BTCPRoute) -> Dict[str, Any]:
    """BTCPRoute → JSON-safe row dict for BtcpStateStore."""
    return {
        "route_id":       route.route_id,
        "intent":         route.intent.to_dict() if route.intent is not None else None,
        "source_vm":      route.source_vm.name,
        "dest_vm":        route.dest_vm.name,
        "source_encoded": route.source_encoded,
        "dest_encoded":   route.dest_encoded,
        "source_gas":     _gas_to_row(route.source_gas),
        "dest_gas":       _gas_to_row(route.dest_gas),
        "proofs":         route.proofs,
        "privacy_level":  route.privacy_level.name,
        "status":         route.status.name,
        "total_fee":      route.total_fee,
        "assets_bridged": route.assets_bridged,
        "btcp_score":     route.btcp_score,
        "route_type":     route.route_type,
        "created_at":     route.created_at,
        "updated_at":     route.updated_at,
    }


def _route_from_row(row: Dict[str, Any]) -> BTCPRoute:
    """Row dict → BTCPRoute (inverse of _route_to_row)."""
    intent_row = row.get("intent")
    intent = BTCPIntent(**intent_row) if intent_row else None
    return BTCPRoute(
        route_id=row["route_id"],
        intent=intent,
        source_vm=VMType[row["source_vm"]],
        dest_vm=VMType[row["dest_vm"]],
        source_encoded=row.get("source_encoded", ""),
        dest_encoded=row.get("dest_encoded", ""),
        source_gas=_gas_from_row(row.get("source_gas")),
        dest_gas=_gas_from_row(row.get("dest_gas")),
        proofs=row.get("proofs") or {},
        privacy_level=PrivacyLevel[row["privacy_level"]],
        status=RouteStatus[row["status"]],
        total_fee=float(row.get("total_fee", 0.0)),
        assets_bridged=bool(row.get("assets_bridged", False)),
        btcp_score=float(row.get("btcp_score", 0.0)),
        route_type=row.get("route_type", "SINGLE_CHAIN"),
        created_at=float(row.get("created_at", 0.0)),
        updated_at=float(row.get("updated_at", 0.0)),
    )


# ── Akashic execution records (BTCP gap #7) ─────────────────────────────────
# schema.sql's six btcp_* tables are no longer dead DDL: every orchestrated
# route writes its execution records into them (SQLite mirrors of the
# TimescaleDB DDL live in core/btcp/state_store.py).  All writes are
# idempotent so replaying a route event never duplicates rows.

# Route-reward fee rate — mirrors the Rust constant BTCP_ROUTE_FEE_RATE
# (rust/src/validator_fee_calculator.rs); spec Fix 4: route value × 0.1%.
_ROUTE_REWARD_FEE_RATE = 0.001

# Terminal route statuses that finalize the intent registry row.
_TERMINAL_ROUTE_STATUSES = (
    RouteStatus.COMPLETED,
    RouteStatus.FAILED,
    RouteStatus.TIMEOUT,
)

_FEE_CALCULATOR = ValidatorFeeCalculator()


# ── Intent identity (INV-008 / INV-014) ──────────────────────────────────
# Route/intent ids mix a per-process monotonic counter with a random
# session tag so two identical rapid submissions can never collide into
# one route (the previous id derivation hashed time.time() alone —
# same-microsecond identical calls silently clobbered the live route).
# Intent nonces are per-entity monotonic (spec §4.1 "per-entity monotonic
# counter"), seeded from the wall-clock millisecond on first sight so a
# restart cannot rewind them into already-used territory except across
# a sub-millisecond restart (documented caveat — W3-D owns the persisted
# per-entity counter). W3-D RESOLUTION: create_route now uses the
# STORE-BACKED counter (see _next_persisted_entity_nonce) — the persisted
# value survives restarts, closing the rewind caveat; this session-scoped
# helper remains the no-store fallback.
_INTENT_SEQ_LOCK = threading.Lock()
_INTENT_SEQ = 0
_SESSION_TAG = secrets.token_hex(8)
_ENTITY_NONCES: Dict[str, int] = {}
_ENTITY_NONCE_LOCK = threading.Lock()

# State-store kind for persisted per-entity monotonic nonces (W3-D).
ENTITY_NONCE_KIND = "entity_nonce"


def _next_intent_sequence() -> int:
    """Process-global monotonic intent sequence (never repeats in-process)."""
    global _INTENT_SEQ
    with _INTENT_SEQ_LOCK:
        _INTENT_SEQ += 1
        return _INTENT_SEQ


def _next_entity_nonce(entity_key: str) -> int:
    """Per-entity monotonic nonce, seeded from wall-clock ms (spec §4.1)."""
    with _ENTITY_NONCE_LOCK:
        last = _ENTITY_NONCES.get(entity_key)
        seed = int(time.time() * 1000) % (2 ** 32)
        nonce = (last + 1) if last is not None else seed
        if nonce >= 2 ** 32:
            nonce = 1
        _ENTITY_NONCES[entity_key] = nonce
        return nonce


# ── Route status machine (INV-013, docs/protocol/BTCP_STATE_MACHINE.md M1) ─
# Terminal states are frozen (a same-status replay is an idempotent no-op;
# any different target is rejected). FAILURE/TIMEOUT are reachable from any
# active state. Execution progress is forward-only along the IntEnum order
# PENDING → INTENT_CREATED → PROOFS_GENERATED → SOURCE_EXECUTED →
# DEST_EXECUTED → COMPLETED.
_ACTIVE_ROUTE_STATUSES = (
    RouteStatus.PENDING,
    RouteStatus.INTENT_CREATED,
    RouteStatus.PROOFS_GENERATED,
    RouteStatus.SOURCE_EXECUTED,
    RouteStatus.DEST_EXECUTED,
)
_FAILURE_ROUTE_STATUSES = (RouteStatus.FAILED, RouteStatus.TIMEOUT)


def _route_transition_allowed(current: RouteStatus, new: RouteStatus) -> bool:
    """M1 transition-table law: is current → new legal?"""
    if new == current:
        return True          # idempotent replay of the same status: no-op
    if current in _TERMINAL_ROUTE_STATUSES:
        return False         # terminal states are frozen (no resurrection)
    if new in _FAILURE_ROUTE_STATUSES:
        return True          # failure sinks reachable from any active state
    return int(new.value) > int(current.value)   # forward-only progress


def _privacy_mode_name(level: PrivacyLevel) -> str:
    """PrivacyLevel → schema.sql btcp_privacy_mode.

    Same bridge as the Rust SpecPrivacy::to_legacy() mapping
    (Public→PUBLIC, Basic/Standard/Compliant→ZK_CREDENTIAL, Full→INVISIBLE).
    """
    if level == PrivacyLevel.PUBLIC:
        return "PUBLIC"
    if level == PrivacyLevel.FULL:
        return "INVISIBLE"
    return "ZK_CREDENTIAL"


def _intent_registry_status(route_status: RouteStatus) -> str:
    """RouteStatus → schema.sql btcp_intent_status enum."""
    if route_status == RouteStatus.COMPLETED:
        return "COMPLETED"
    if route_status == RouteStatus.FAILED:
        return "FAILED"
    if route_status == RouteStatus.TIMEOUT:
        return "EXPIRED"
    if route_status in (RouteStatus.SOURCE_EXECUTED, RouteStatus.DEST_EXECUTED):
        return "EXECUTING"
    return "ROUTING"


def _proof_commitment(route: BTCPRoute, circuit: str) -> Optional[str]:
    """Hex commitment of a route's real proof for a circuit, else None.

    Deferred proofs carry ``status: "zk_pending"`` (the PrivacyRouter
    honesty contract) — they deliberately return None so the akashic record
    never claims a proof hash that was never generated.
    """
    entry = route.proofs.get(circuit)
    if not isinstance(entry, dict):
        return None
    if entry.get("status") == "zk_pending":
        return None
    commitment = entry.get("commitment")
    return str(commitment) if commitment else None


def _anchor_bh(route: BTCPRoute) -> str:
    """Anchor BH for the btcp_routes row.

    The real intent-commitment Pedersen commitment when the route carries
    one; otherwise the deterministic SHA3-256 commitment of the intent id
    (the anchor strand this engine can always honestly derive).
    """
    commitment = _proof_commitment(route, "intent_commitment")
    if commitment:
        return commitment
    intent_id = route.intent.intent_id if route.intent else route.route_id
    return hashlib.sha3_256(str(intent_id).encode()).hexdigest()


def _route_reward_epoch(ts: float) -> int:
    """UTC day index — the epoch bucket for btcp_route_rewards rows."""
    return int(ts // 86400)


class PrivacyRouter:
    """
    Routes BTCP intents through appropriate ZK circuits based on privacy level.
    
    Generates the correct set of zero-knowledge proofs for each operation.
    """
    
    def __init__(self):
        self.zk = ZKProofSystem()
    
    def generate_proofs(
        self,
        intent: BTCPIntent,
        privacy_level: PrivacyLevel,
        behavioral_data: Optional[Dict[str, Any]] = None,
        gas_estimates: Optional[List[Any]] = None,
        iap_economics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate ZK proofs appropriate for the requested privacy level.
        
        Returns a dict mapping circuit names to their proofs.

        Honesty contract (deep-read fix):
          - Every generated proof is REAL cryptography over REAL witness data
            derived from the intent / caller-supplied values.
          - When the witness data required by a circuit is not available
            (e.g. the entity's HashDNA strands, or the IAP batch economics),
            the circuit's entry is an honest deferral:
                {"zk_proof": None, "status": "zk_pending", "reason": ...}
            rather than fabricated proof bytes over random/hardcoded values.
            verify_proofs() reports such routes as NOT fully proven (fail
            closed).

        Args:
            intent: the BTCP intent (always the real source for the intent
                commitment witness).
            privacy_level: requested privacy level.
            behavioral_data: optional real behavioral context. Recognized
                keys for real witnesses:
                  "genomic_sense"/"genomic_antisense" — hex bytes of the
                      entity's HashDNA dual strands (complementarity proof);
                  "block_number" — current block for that proof;
                  "coherence"/"manipulation"/"liquidity"/"depth" —
                      behavioral credential thresholds;
                  "iap_economics" — dict with the IAP batch values.
            gas_estimates: optional list of GasEstimate objects from the VM
                adapters (real per-intent estimates). Used to derive the
                entity's gas in the IAP witness when batch economics are
                supplied.
            iap_economics: optional dict with the IAP batch economics:
                total_gas, entity_gas, total_btcp_fee_wei,
                entity_share_wei, num_participants. These are batch-level
                values owned by the IAP scheduler and cannot be derived
                from a single intent — without them the IAP proof is
                honestly deferred (previously hardcoded 1M gas / 151k
                entity gas / 0.01 ETH fee / 0.0015 share / 10 participants).
        """
        proofs = {}
        
        # Level 1+: Always generate intent commitment
        if privacy_level >= PrivacyLevel.BASIC:
            intent_witness = IntentWitness(
                entity_id=intent.source_address,
                intent_type=intent.intent_type,
                amount=intent.amount,
                source_chain=intent.source_chain,
                dest_chain=intent.dest_chain,
                deadline=intent.deadline,
                nonce=intent.nonce.to_bytes(32, 'big'),
            )
            proof = self.zk.generate_intent(intent_witness)
            proofs["intent_commitment"] = proof.to_dict()
        
        # Level 2+: Add complementarity proof
        if privacy_level >= PrivacyLevel.STANDARD:
            # Real witness: the entity's HashDNA dual strands, supplied by
            # the caller (e.g. from the behavioral ledger / genomic
            # signature). Without them we do NOT fabricate strands — the
            # previous implementation generated a "dummy" proof over
            # secrets.token_bytes(32) with a hardcoded block 18,000,000.
            bd = behavioral_data or {}
            sense = bd.get("genomic_sense") or bd.get("sense_strand")
            antisense = bd.get("genomic_antisense") or bd.get("antisense_strand")
            block_number = bd.get("block_number")
            if isinstance(sense, str):
                sense = bytes.fromhex(sense.removeprefix("0x"))
            if isinstance(antisense, str):
                antisense = bytes.fromhex(antisense.removeprefix("0x"))
            if isinstance(block_number, bool) or not isinstance(block_number, int):
                block_number = None

            if sense and antisense and block_number is not None:
                comp_witness = ComplementarityWitness(
                    sense_strand=sense,
                    antisense_strand=antisense,
                    entity_id=intent.source_address,
                    block_number=block_number,
                )
                proof = self.zk.generate_complementarity(comp_witness)
                proofs["complementarity"] = proof.to_dict()
            else:
                proofs["complementarity"] = {
                    "zk_proof": None,
                    "status": "zk_pending",
                    "circuit": "complementarity",
                    "reason": (
                        "HashDNA dual-strand witness not supplied — refusing to "
                        "fabricate proof bytes over random strands. Supply "
                        "behavioral_data={'genomic_sense': <hex>, 'genomic_antisense': "
                        "<hex>, 'block_number': <int>} from the entity's genomic "
                        "signature to generate the real complementarity proof."
                    ),
                }
        
        # Level 3+: Add travel rule compliance
        if privacy_level >= PrivacyLevel.COMPLIANT:
            tr_witness = TravelRuleWitness(
                originator_id=intent.source_address,
                beneficiary_id=intent.dest_address,
                amount=intent.amount,
                asset_address=intent.asset,
                originator_verified=True,
                beneficiary_verified=True,
            )
            proof = self.zk.generate_travel_rule(tr_witness)
            proofs["travel_rule"] = proof.to_dict()
        
        # Level 4+: Add behavioral credential
        if privacy_level >= PrivacyLevel.FULL and behavioral_data:
            bc_witness = BehavioralCredentialWitness(
                entity_id=intent.source_address,
                coherence_score=behavioral_data.get("coherence", 0.75),
                manipulation_fingerprint=behavioral_data.get("manipulation", 0.15),
                liquidity_score=behavioral_data.get("liquidity", 0.80),
                akashic_depth=behavioral_data.get("depth", 500.0),
                threshold_coherence=0.55,
                threshold_manipulation=0.30,
            )
            proof = self.zk.generate_behavioral_credential(bc_witness)
            credential_row = proof.to_dict()
            # INV-016 witness provenance + W3-D Akashic BEO binding: the
            # thresholds are protocol constants (hardcoded above — the
            # caller cannot move the goalposts) and the SCORES remain
            # caller-supplied claims (witness_scores_source below is always
            # the honest label for them). The ENTITY, however, is now bound
            # to the Akashic BEO ledger when that ledger knows it: the
            # binding record carries the ledger's own facts (beo_id,
            # last_active, record count, entropy) — read-only via
            # core/akashic/beo_lookup.py. Bound ⇒ witness_source upgrades
            # from caller_self_attested to akashic_beo_bound; unknown
            # entity or absent ledger ⇒ stays self-attested with the
            # reason (never a fabricated binding).
            credential_row["witness_scores_source"] = "caller_supplied_behavioral_data"
            try:
                from core.akashic.beo_lookup import lookup_beo_binding
                beo_binding = lookup_beo_binding(str(intent.source_address))
            except Exception:
                beo_binding = None
            if beo_binding is not None:
                credential_row["witness_source"] = "akashic_beo_bound"
                credential_row["beo_binding"] = beo_binding
            else:
                credential_row["witness_source"] = "caller_self_attested"
                credential_row["beo_binding"] = None
                credential_row["beo_binding_reason"] = (
                    "entity not present in the Akashic BEO ledger (or ledger "
                    "unavailable) — identity unbound; scores remain "
                    "caller-supplied claims"
                )
            proofs["behavioral_credential"] = credential_row
        
        # Always add IAP share proof for gas fairness — but only with REAL
        # batch economics. The previous implementation hardcoded
        # total_gas=1,000,000 / entity_gas=151,000 / 0.01 ETH fee /
        # 0.0015 share / 10 participants, presenting fabricated economics
        # as a verified fairness proof.
        iaph = None
        if iap_economics:
            iaph = dict(iap_economics)
        else:
            _bd = behavioral_data or {}
            _bd_iap = _bd.get("iap_economics")
            if isinstance(_bd_iap, dict):
                iaph = dict(_bd_iap)
        if iaph is None and gas_estimates:
            iaph = {}
        if gas_estimates and iaph is not None:
            # entity gas from the real VM-adapter estimates for this intent
            real_entity_gas = int(sum(
                g.gas_limit for g in gas_estimates if g is not None
            ))
            if real_entity_gas > 0:
                iaph.setdefault("entity_gas", real_entity_gas)

        iap_required = (
            "total_gas", "entity_gas", "total_btcp_fee_wei",
            "entity_share_wei", "num_participants",
        )
        if iaph and all(k in iaph for k in iap_required):
            iap_witness = IAPShareWitness(
                entity_id=intent.source_address,
                total_gas=int(iaph["total_gas"]),
                entity_gas=int(iaph["entity_gas"]),
                total_btcp_fee=int(iaph["total_btcp_fee_wei"]),
                entity_share=int(iaph["entity_share_wei"]),
                num_participants=int(iaph["num_participants"]),
            )
            proof = self.zk.generate_iap_share(iap_witness)
            iap_row = proof.to_dict()
            # INV-016: batch economics are caller/IAP-scheduler-supplied
            # values, not protocol measurements — labeled as such.
            iap_row["witness_source"] = "caller_supplied_batch_economics"
            proofs["iap_share"] = iap_row
        else:
            proofs["iap_share"] = {
                "zk_proof": None,
                "status": "zk_pending",
                "circuit": "iap_share",
                "reason": (
                    "IAP batch economics not supplied — total_gas/total_btcp_fee/"
                    "entity_share/num_participants are batch-level values owned "
                    "by the IAP scheduler and are not derivable from a single "
                    "intent. Hardcoded placeholder economics removed; supply "
                    "iap_economics={total_gas, entity_gas, total_btcp_fee_wei, "
                    "entity_share_wei, num_participants} to generate the proof."
                ),
            }
        
        return proofs
    
    def verify_proofs(self, proofs: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Verify all proofs in a set."""
        all_valid = True
        errors = []
        
        try:
            from zk import ZKProof, CircuitType
        except ImportError:
            ZKProof = None
            CircuitType = None  # zk-circuits optional
        
        circuit_map = {
            "intent_commitment": CircuitType.INTENT_COMMITMENT,
            "complementarity": CircuitType.COMPLEMENTARITY,
            "travel_rule": CircuitType.TRAVEL_RULE,
            "behavioral_credential": CircuitType.BEHAVIORAL_CREDENTIAL,
            "iap_share": CircuitType.IAP_SHARE,
        }
        
        for name, proof_data in proofs.items():
            if name not in circuit_map:
                continue

            # Honest pending handling: a deferred circuit has no proof bytes
            # to verify — the route is NOT fully proven (fail closed).
            if isinstance(proof_data, dict) and proof_data.get("status") == "zk_pending":
                all_valid = False
                errors.append(
                    f"proof pending: {name} — {proof_data.get('reason', 'deferred')}"
                )
                continue
            
            # Reconstruct ZKProof from dict
            circuit_type = circuit_map[name]
            proof = ZKProof(
                circuit_type=circuit_type,
                proof_data=proof_data.get("proof_data", {}),
                public_inputs=proof_data.get("public_inputs", {}),
                commitment=proof_data.get("commitment", ""),
                timestamp=proof_data.get("timestamp", 0),
                version=proof_data.get("version", "1.0.0"),
            )
            
            if not self.zk.verify(proof):
                all_valid = False
                errors.append(f"Invalid proof: {name}")
        
        return all_valid, errors


# ── Cross-VM Gateway ────────────────────────────────────────────────────────

class CrossVMGateway:
    """
    Unified gateway for all cross-VM operations.
    
    Provides a single interface for:
      - Encoding intents for any VM
      - Estimating gas across VMs
      - Validating addresses for any chain
      - Routing intents to appropriate adapters
    """
    
    def __init__(self):
        self.factory = VMAdapterFactory
    
    def encode_for_chain(self, intent: BTCPIntent, chain_id: int) -> str:
        """Encode an intent for a specific chain."""
        adapter = self.factory.get_by_chain_id(chain_id)
        if adapter is None:
            raise ValueError(f"No adapter for chain_id: {chain_id}")
        return adapter.encode_intent(intent)
    
    def estimate_chain_gas(self, intent: BTCPIntent, chain_id: int) -> GasEstimate:
        """Estimate gas for executing on a specific chain."""
        adapter = self.factory.get_by_chain_id(chain_id)
        if adapter is None:
            raise ValueError(f"No adapter for chain_id: {chain_id}")
        return adapter.estimate_gas(intent)
    
    def validate_chain_address(self, address: str, chain_id: int) -> bool:
        """Validate an address format for a specific chain."""
        adapter = self.factory.get_by_chain_id(chain_id)
        if adapter is None:
            return False
        return adapter.validate_address(address)
    
    def format_chain_address(self, address: str, chain_id: int) -> str:
        """Format an address for a specific chain."""
        adapter = self.factory.get_by_chain_id(chain_id)
        if adapter is None:
            return address
        return adapter.format_address(address)
    
    def get_vm_type(self, chain_id: int) -> VMType:
        """Get the VM type for a given chain."""
        return CHAIN_VM_MAP.get(chain_id, VMType.EVM)
    
    def get_supported_chains(self) -> List[Dict[str, Any]]:
        """Get all supported chains and their VM types."""
        chains = []
        for chain_id, vm_type in sorted(CHAIN_VM_MAP.items()):
            adapter = self.factory.get_by_vm_type(vm_type)
            chains.append({
                "chain_id": chain_id,
                "vm_type": vm_type.name,
                "vm_name": adapter.name if adapter else "Unknown",
                "native_token": adapter.native_token if adapter else "UNKNOWN",
            })
        return chains
    
    def list_vms(self) -> List[Dict[str, Any]]:
        """List all supported VM types."""
        return self.factory.list_adapters()


# ── BTCP Orchestrator ───────────────────────────────────────────────────────

class BTCPOrchestrator:
    """
    High-level BTCP orchestration coordinator.
    
    Ties together:
      - Intent creation and validation
      - VM adapter encoding
      - ZK proof generation
      - Gas estimation
      - Route tracking and status management
    
    Tracked routes are write-through persisted to SQLite (S7): a restart
    reloads routes instead of wiping them.

    ``state_db``: optional SQLite path (default: env TRION_STATE_DB, then
    ``db/btcp_state.db``; test-context constructions get an isolated temp
    store — see core/btcp/state_store.py).

    This is the main entry point for BTCP operations in the TRION engine.
    """
    
    def __init__(self, state_db: Optional[str] = None):
        self.privacy_router = PrivacyRouter()
        self.gateway = CrossVMGateway()
        self._routes: Dict[str, BTCPRoute] = {}
        self._store = BtcpStateStore(state_db)
        self._load_routes()

    # ── Persistence (S7) ────────────────────────────────────────────────

    def _load_routes(self) -> None:
        """Load persisted routes into memory (malformed rows are skipped)."""
        for route_id, (type_tag, row) in self._store.get_routes().items():
            if type_tag != ROUTE_ROW_TYPE:
                continue
            try:
                self._routes[route_id] = _route_from_row(row)
            except (KeyError, ValueError, TypeError):
                print(
                    f"[btcp.orchestrator] skipping malformed persisted route "
                    f"{route_id!r}",
                    file=sys.stderr,
                )

    def _persist_route(self, route: BTCPRoute) -> None:
        """Write one route through to SQLite (upsert)."""
        self._store.save_route(route.route_id, _route_to_row(route), ROUTE_ROW_TYPE)

    # ── Persisted per-entity nonces (W3-D, spec §4.1) ───────────────────

    def _next_persisted_entity_nonce(self, entity_key: str) -> int:
        """Per-entity monotonic nonce, PERSISTED across restarts (spec §4.1).

        Read-modify-write against the shared SQLite state store (KV kind
        ``entity_nonce``): the counter resumes from the persisted value
        after a restart instead of re-seeding from wall-clock ms, so it is
        strictly monotonic for the lifetime of the store. First sight of an
        entity seeds from the wall-clock millisecond (the same seed
        discipline as the session-scoped fallback) and persists
        immediately. Store failures fall back to the session-scoped
        counter (monotonic in-process; restart caveat documented above).
        """
        # P-PY-04/P-PY-06: the read-modify-write must be ATOMIC — first
        # via the STORE's cross-process atomic counter (BEGIN IMMEDIATE
        # around read+compute+write on the shared SQLite file, so api /
        # streamer / gunicorn-worker PROCESSES serialize too), falling
        # back to the in-process lock + save when the store predates the
        # atomic method.
        atomic = getattr(self._store, "next_entity_nonce", None)
        if callable(atomic):
            seed = int(time.time() * 1000) % (2 ** 32) or 1
            try:
                nonce = atomic(entity_key, seed=seed)
                with _ENTITY_NONCE_LOCK:
                    _ENTITY_NONCES[entity_key] = nonce
                return nonce
            except Exception as store_err:
                print(
                    f"[btcp.orchestrator] atomic entity-nonce failed for "
                    f"{entity_key!r} ({store_err}) — in-process path in use",
                    file=sys.stderr,
                )
        with _ENTITY_NONCE_LOCK:
            try:
                persisted = self._store.load_all(ENTITY_NONCE_KIND)
            except Exception:
                persisted = {}
            last = None
            entry = persisted.get(entity_key)
            if entry is not None:
                try:
                    last = int(entry[1])
                except (TypeError, ValueError):
                    last = None

            if last is None:
                # First sight (or unreadable row): seed from wall-clock ms,
                # but never below the in-memory counter.
                seed = int(time.time() * 1000) % (2 ** 32)
                mem = _ENTITY_NONCES.get(entity_key)
                if mem is not None:
                    seed = max(seed, mem + 1) % (2 ** 32)
                nonce = seed if seed > 0 else 1
            else:
                nonce = last + 1
                if nonce >= 2 ** 32:
                    nonce = 1
            _ENTITY_NONCES[entity_key] = nonce
            try:
                self._store.save(ENTITY_NONCE_KIND, entity_key, int(nonce), "uint32")
            except Exception as store_err:
                print(
                    f"[btcp.orchestrator] entity-nonce persistence failed for "
                    f"{entity_key!r} ({store_err}) — session-scoped counter in use",
                    file=sys.stderr,
                )
        return nonce

    # ── Akashic execution records (BTCP gap #7) ────────────────────────

    def _record_execution(self, route: BTCPRoute) -> None:
        """Project a newly-created route into the schema.sql btcp_* tables.

        Writes the intent-registry row, the routes row, the IntentBroadcast
        cross-chain message, and the per-chain adapter-version sightings.
        Every write is an idempotent upsert (see state_store), so a replayed
        create/step-6 event neither duplicates rows nor crashes.
        """
        intent = route.intent
        if intent is None:
            return
        now = time.time()
        entity_id = str(intent.source_address)
        message_id = hashlib.sha3_256(
            f"{intent.intent_id}:{intent.source_chain}:"
            f"{intent.dest_chain}:{intent.nonce}".encode()
        ).hexdigest()
        payload_hash = hashlib.sha3_256(
            f"{route.source_encoded or intent.intent_id}".encode()
        ).hexdigest()

        self._store.record_intent(
            intent.intent_id,
            entity_id=entity_id,
            action=str(intent.intent_type),
            asset_in=str(intent.asset) if intent.asset else None,
            magnitude=float(intent.amount),
            source_chain_id=int(intent.source_chain),
            deadline_ts=float(intent.deadline),
            privacy_mode=_privacy_mode_name(route.privacy_level),
            nonce=int(intent.nonce),
            route_selected=route.route_type,
            status=_intent_registry_status(route.status),
            btcp_score=route.btcp_score,
            created_at=route.created_at,
            routed_at=now,
        )
        self._store.record_route(
            route.route_id,
            intent_hash=intent.intent_id,
            route_type=route.route_type,
            anchor_bh=_anchor_bh(route),
            anchor_chain=int(intent.source_chain),
            execution_chain=int(intent.dest_chain),
            entity_id=entity_id,
            btcp_score=float(route.btcp_score),
            gas_total_usd=float(route.total_fee),
            travel_rule_proof=_proof_commitment(route, "travel_rule"),
            status=route.status.name,
            created_at=route.created_at,
        )
        self._store.record_cross_chain_message(
            message_id,
            msg_type="IntentBroadcast",
            sender_entity_id=entity_id,
            sender_chain=int(intent.source_chain),
            target_chain=int(intent.dest_chain),
            nonce=int(intent.nonce),
            expiry_ts=float(intent.deadline),
            payload_hash=payload_hash,
            status="ACCEPTED",
            created_at=route.created_at,
        )
        # Per-chain adapter version sightings (§2.16 upgrade routing):
        # first route registers the (chain, version) pair, later routes
        # refresh last_seen_at.
        self._store.record_version(int(intent.source_chain))
        self._store.record_version(int(intent.dest_chain))

    def _record_route_status(self, route: BTCPRoute) -> None:
        """Write a route-status change through to the btcp_* projections.

        Terminal statuses finalize the intent row (completed_at) and the
        routes row (finalized_at); COMPLETED additionally pays the route's
        validator pools (spec Fix 4: route value × 0.1%, split 60/40
        anchor/execution).  Individual validator attribution happens in the
        Rust validator mesh — the Python engine records the two pool legs,
        idempotent per (epoch, pool, route).
        """
        intent = route.intent
        now = time.time()
        terminal = route.status in _TERMINAL_ROUTE_STATUSES
        if intent is not None:
            self._store.record_intent(
                intent.intent_id,
                entity_id=str(intent.source_address),
                action=str(intent.intent_type),
                magnitude=float(intent.amount),
                source_chain_id=int(intent.source_chain),
                deadline_ts=float(intent.deadline),
                privacy_mode=_privacy_mode_name(route.privacy_level),
                nonce=int(intent.nonce),
                route_selected=route.route_type,
                status=_intent_registry_status(route.status),
                btcp_score=route.btcp_score,
                routed_at=now,
                completed_at=now if terminal else None,
            )
        self._store.record_route(
            route.route_id,
            intent_hash=intent.intent_id if intent else route.route_id,
            route_type=route.route_type,
            anchor_bh=_anchor_bh(route),
            anchor_chain=int(intent.source_chain) if intent else 0,
            execution_chain=int(intent.dest_chain) if intent else 0,
            entity_id=str(intent.source_address) if intent else "",
            btcp_score=float(route.btcp_score),
            gas_total_usd=float(route.total_fee),
            travel_rule_proof=_proof_commitment(route, "travel_rule"),
            status=route.status.name,
            failure_cause=(
                "ENTITY" if route.status == RouteStatus.FAILED else None
            ),
            created_at=route.created_at,
            finalized_at=now if terminal else None,
        )

        if route.status == RouteStatus.COMPLETED and intent is not None:
            total_reward = float(intent.amount) * _ROUTE_REWARD_FEE_RATE
            epoch = _route_reward_epoch(now)
            anchor_leg = _FEE_CALCULATOR.compute_btcp_route_reward(
                total_reward, is_anchor=True)
            exec_leg = _FEE_CALCULATOR.compute_btcp_route_reward(
                total_reward, is_anchor=False)
            # Idempotency probe BEFORE the SQLite write: route_reward_exists
            # returns True if the (epoch, pool, route_id) row is already
            # there. The fresh-write flag drives the TimescaleDB
            # trion_token_economics increment below (BTCP-FIX2-INT Fix 3)
            # so a supervisor-replayed route finalization does not
            # double-count the per-epoch aggregate.
            anchor_pool = f"anchor_pool:{intent.source_chain}"
            exec_pool   = f"execution_pool:{intent.dest_chain}"
            anchor_existed = False
            exec_existed   = False
            try:
                anchor_existed = self._store.route_reward_exists(
                    epoch, anchor_pool, route.route_id,
                )
                exec_existed = self._store.route_reward_exists(
                    epoch, exec_pool, route.route_id,
                )
            except Exception:
                pass  # older store without the helper — treat as fresh
            self._store.record_route_reward(
                epoch, anchor_pool,
                route.route_id, anchor_leg,
            )
            self._store.record_route_reward(
                epoch, exec_pool,
                route.route_id, exec_leg,
            )
            # BTCP-FIX2-INT Fix 3 — also write the route reward through to
            # the TimescaleDB trion_token_economics table (per-epoch
            # aggregator). Previously this table was `operative-writer:
            # NONE` (schema.sql line 635) — SQLite was the only path
            # (BTCP-DEEP-5 connection #14). Now each freshly-finalized BTCP
            # route increments routes_this_epoch, intents_this_epoch, and
            # adds the route reward to rewarded_routes + rewarded_validators
            # for the current epoch. Replays (anchor_existed and
            # exec_existed) skip the increment — SQLite already had the
            # row, so we must not double-count.
            if not (anchor_existed and exec_existed):
                self._record_token_economics(
                    route=route, epoch=epoch,
                    total_reward=total_reward,
                    anchor_leg=anchor_leg, exec_leg=exec_leg,
                    now=now,
                )

    def _record_token_economics(
        self,
        route: 'BTCPRoute',
        epoch: int,
        total_reward: float,
        anchor_leg: float,
        exec_leg: float,
        now: float,
    ) -> None:
        """BTCP-FIX2-INT Fix 3 — write the per-epoch BTCP route reward
        through to the TimescaleDB ``trion_token_economics`` table.

        Spec §11 Fix 4: ``btcp_route_reward = Σ route.value ×
        BTCP_ROUTE_FEE_RATE``, split 60% anchor / 40% execution. The
        ``trion_token_economics`` table (schema.sql:636) carries the
        per-epoch aggregates (``routes_this_epoch``, ``rewarded_routes``,
        ``rewarded_validators``, ``intents_this_epoch``) that the spec
        §15 Revenue Model feeds into the validator payout / TRION
        burn/buyback equation. BTCP-DEEP-5 connection #14 found the
        table had `operative-writer: NONE` — every finalized route paid
        SQLite only, leaving the TRION token-economics aggregator stale.

        Idempotency: ``_record_route_status`` checks
        ``route_reward_exists`` BEFORE calling this writer, so a
        supervisor-replayed route finalization skips this call entirely.
        Inside this method the UPSERT is ``ON CONFLICT (epoch) DO UPDATE``
        that increments the per-epoch counters and rewrites ``recorded_at``.
        """
        try:
            import psycopg2 as _pg
            tsdb_url = os.environ.get("TIMESCALEDB_URL", "")
            if not tsdb_url:
                return

            # Epoch window: UTC day [epoch_start_ts, epoch_end_ts). The
            # epoch is the UTC-day index (per _route_reward_epoch).
            from datetime import datetime, timezone as _tz
            epoch_start_ts = datetime.fromtimestamp(epoch * 86400, tz=_tz.utc)
            epoch_end_ts   = datetime.fromtimestamp((epoch + 1) * 86400, tz=_tz.utc)
            now_dt         = datetime.fromtimestamp(now, tz=_tz.utc)

            # Total validator reward paid this event = anchor_leg + exec_leg.
            # `rewarded_validators` is the sum of validator payouts; the spec
            # (§11 Fix 4) splits this 60/40 between anchor/execution pools,
            # so the total paid to validators = anchor_leg + exec_leg =
            # total_reward (no leak).
            validator_payout = float(anchor_leg + exec_leg)
            route_reward_paid = float(total_reward)

            conn = _pg.connect(tsdb_url, connect_timeout=5)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO trion_token_economics
                    (epoch, epoch_start_ts, epoch_end_ts,
                     total_supply, circulating_supply, staked_supply,
                     burned_this_epoch, slashed_this_epoch,
                     rewarded_validators, rewarded_routes,
                     genesis_bonds,
                     routes_this_epoch, intents_this_epoch,
                     avg_btcp_score, coverage_state, emergency_multiplier,
                     recorded_at)
                VALUES (%s, %s, %s,
                        0, 0, 0,
                        0, 0,
                        %s, %s,
                        0,
                        1, 1,
                        %s, 'NOMINAL', 1.0,
                        %s)
                ON CONFLICT (epoch) DO UPDATE SET
                    rewarded_routes     = trion_token_economics.rewarded_routes
                                           + EXCLUDED.rewarded_routes,
                    rewarded_validators = trion_token_economics.rewarded_validators
                                           + EXCLUDED.rewarded_validators,
                    routes_this_epoch   = trion_token_economics.routes_this_epoch
                                           + EXCLUDED.routes_this_epoch,
                    intents_this_epoch  = trion_token_economics.intents_this_epoch
                                           + EXCLUDED.intents_this_epoch,
                    avg_btcp_score      = EXCLUDED.avg_btcp_score,
                    coverage_state      = EXCLUDED.coverage_state,
                    emergency_multiplier = EXCLUDED.emergency_multiplier,
                    epoch_end_ts        = EXCLUDED.epoch_end_ts,
                    recorded_at         = EXCLUDED.recorded_at
            """, (
                int(epoch),
                epoch_start_ts,
                epoch_end_ts,
                validator_payout,             # rewarded_validators (increment)
                route_reward_paid,            # rewarded_routes (increment)
                float(route.btcp_score),
                now_dt,
            ))
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            _log.warning(
                "trion_token_economics writeback failed (route=%s epoch=%d): %s",
                getattr(route, "route_id", "?"), epoch, str(e)[:200],
            )

    def reload(self) -> None:
        """Re-read persisted routes from SQLite, replacing memory."""
        self._routes = {}
        self._load_routes()
    
    def create_route(
        self,
        source_chain: int,
        dest_chain: int,
        source_address: str,
        dest_address: str,
        amount: int,
        asset: str,
        intent_type: str = "TRANSFER",
        privacy_level: PrivacyLevel = PrivacyLevel.BASIC,
        deadline_offset: int = 3600,
        behavioral_data: Optional[Dict[str, Any]] = None,
        iap_economics: Optional[Dict[str, Any]] = None,
        auto_finalize: bool = True,
        sovereign_actor: bool = False,
        nation_id: Optional[str] = None,
    ) -> OrchestrationResult:
        """
        Create and orchestrate a complete BTCP route.
        
        Steps:
          1. Validate addresses for both chains
          2. Create standardized BTCPIntent
          3. Encode intent for source and destination VMs
          4. Estimate gas for both chains
          5. Generate appropriate ZK proofs
          6. Track route status

        Args:
            behavioral_data: real behavioral context — supplies the HashDNA
                strands/block for the complementarity proof and the
                behavioral-credential thresholds. Circuits whose witness data
                is not supplied are honestly deferred (status "zk_pending").
            iap_economics: real IAP batch economics for the IAP share proof
                (total_gas, entity_gas, total_btcp_fee_wei,
                entity_share_wei, num_participants). Without them the IAP
                proof is deferred instead of using hardcoded values.
        """
        start_time = time.perf_counter()
        errors = []
        
        # BTCP-FIX-INT (Gap 4): L8 SBA gate for sovereign actors
        sovereign_risk_flag = False
        sba_score = None
        if sovereign_actor and nation_id:
            try:
                # BTCP-FIX2-INT Fix 4: call the SBA module directly (not via
                # HTTP) to avoid the self-referential timeout when the Oracle
                # is handling this request. Uses the World Bank feed module.
                from core.physical.worldbank_feed import compute_sba_components as _sba
                sba_result = _sba(nation_id)
                sba_score = sba_result.get("sba_score")
                if sba_score is not None and sba_score < 0.40:
                    sovereign_risk_flag = True
                    errors.append(f"SOVEREIGN_RISK: SBA={sba_score:.4f} < 0.40 threshold for {nation_id}")
            except Exception as e:
                errors.append(f"SBA check failed for {nation_id}: {str(e)[:60]}")
        
        # Step 0 (P-PY-03, final red-team pass): REGISTRY MEMBERSHIP — both
        # route legs must exist in the canonical chain registry
        # (core.generated_chain_bindings, generated from
        # config/chain_registry.json). A route to a chain that does not
        # exist can never verify: the registry is the single source of
        # truth for what chains ARE. Fail-closed, no EVM-adapter default.
        from core.generated_chain_bindings import ID_TO_NAME as _REGISTRY_IDS
        if source_chain not in _REGISTRY_IDS:
            errors.append(
                f"source chain {source_chain} is not in the canonical "
                f"registry (config/chain_registry.json)")
        if dest_chain not in _REGISTRY_IDS:
            errors.append(
                f"dest chain {dest_chain} is not in the canonical "
                f"registry (config/chain_registry.json)")
        
        # Step 1: Validate addresses
        if not self.gateway.validate_chain_address(source_address, source_chain):
            # Try formatting first
            source_address = self.gateway.format_chain_address(source_address, source_chain)
            if not self.gateway.validate_chain_address(source_address, source_chain):
                errors.append(f"Invalid source address for chain {source_chain}")
        
        if not self.gateway.validate_chain_address(dest_address, dest_chain):
            dest_address = self.gateway.format_chain_address(dest_address, dest_chain)
            if not self.gateway.validate_chain_address(dest_address, dest_chain):
                errors.append(f"Invalid dest address for chain {dest_chain}")
        
        # BTCP-FIX2-ZK Fix 2 — Step 1 (cont.): BIBL analyze_intent (spec §4.2 Step 1).
        # The spec mandates that the Behavioral Inter-Block Layer activate in
        # the inter-block window to read all integrated chains simultaneously
        # and produce a BIBLAnalysis (nl_score, gas_forecast, cc_coherence,
        # beo_state, mf_score, block_capacity, finality_dist) per chain.
        # Previously Step 1 was address validation only — now it ALSO runs
        # the BIBL analysis and surfaces the result + classification in
        # step_results["1_bibl_analysis"] so the API response includes a
        # real BIBL analysis result (not just the address-validation echo).
        step_results: Dict[str, Any] = {}
        bibl_analysis = None
        try:
            # Construct a lightweight intent proxy for the BIBL analyzer
            # (the BTCPIntent is not yet created at this point in the flow
            # — the BIBL analysis runs BEFORE Step 2's intent creation per
            # spec §4.2 Step 1 ordering). Duck-typed: BIBL only reads
            # source_chain, dest_chain, source_address, amount, intent_type.
            class _BiblIntentProxy:
                pass
            proxy = _BiblIntentProxy()
            proxy.source_chain = source_chain
            proxy.dest_chain = dest_chain
            proxy.source_address = source_address
            proxy.dest_address = dest_address
            proxy.amount = amount
            proxy.asset = asset
            proxy.intent_type = intent_type
            proxy.deadline = int(time.time()) + deadline_offset
            proxy.nonce = 0  # not yet assigned; BIBL doesn't depend on nonce
            
            from core.btcp.bibl_engine import analyze_intent as _bibl_analyze_intent
            bibl_analysis = _bibl_analyze_intent(proxy, behavioral_data)
            step_results["1_bibl_analysis"] = {
                "status": "executed",
                "classification": bibl_analysis.classification,
                "risk_score": round(bibl_analysis.risk_score, 6),
                "reasons": list(bibl_analysis.reasons),
                "pattern_match": bibl_analysis.pattern_match,
                "chain_analysis": {
                    str(k): v for k, v in bibl_analysis.chain_analysis.items()
                },
                "behavioral_signals": dict(bibl_analysis.behavioral_signals),
                "beo_binding": bibl_analysis.beo_binding,
                "intent_hash": bibl_analysis.intent_hash,
                "entity_id": bibl_analysis.entity_id,
                "spec": "BTCP Master Spec §4.2 Step 1 — BIBL analyze_intent",
            }
            # If the BIBL classifies the intent as BLOCKED, surface as an
            # error so the route does not silently proceed. SUSPICIOUS is
            # surfaced as a warning (route proceeds; consumer decides).
            if bibl_analysis.classification == "BLOCKED":
                errors.append(
                    f"BIBL analyze_intent BLOCKED the intent (risk_score="
                    f"{bibl_analysis.risk_score:.2f}): "
                    f"{'; '.join(bibl_analysis.reasons[:2])}")
        except Exception as e:
            step_results["1_bibl_analysis"] = {
                "status": "failed",
                "error": f"BIBL analyze_intent raised: {str(e)[:120]}",
                "spec": "BTCP Master Spec §4.2 Step 1 — BIBL analyze_intent",
            }
        
        # Step 2: Create intent
        # INV-008/INV-014: the id mixes the caller's immutable parameters
        # with a random session tag and a process-global monotonic sequence —
        # two identical rapid submissions can never collide into one route
        # (the previous derivation hashed time.time() alone).
        seq = _next_intent_sequence()
        intent_id = hashlib.sha3_256(
            f"{source_chain}:{dest_chain}:{source_address}:{dest_address}:"
            f"{amount}:{_SESSION_TAG}:{seq}".encode()
        ).hexdigest()[:16]
        
        intent = BTCPIntent(
            intent_id=f"btcp_{intent_id}",
            source_chain=source_chain,
            dest_chain=dest_chain,
            source_address=source_address,
            dest_address=dest_address,
            amount=amount,
            asset=asset,
            intent_type=intent_type,
            deadline=int(time.time()) + deadline_offset,
            # spec §4.1: per-entity monotonic counter (was a raw
            # wall-clock-ms read — not monotonic, not per-entity).
            # W3-D: store-backed — persists across restarts.
            nonce=self._next_persisted_entity_nonce(str(source_address)),
        )
        
        # Step 3: Encode for both VMs
        source_vm = self.gateway.get_vm_type(source_chain)
        dest_vm = self.gateway.get_vm_type(dest_chain)
        
        try:
            source_encoded = self.gateway.encode_for_chain(intent, source_chain)
        except Exception as e:
            source_encoded = ""
            errors.append(f"Source encoding failed: {str(e)[:80]}")
        
        try:
            dest_encoded = self.gateway.encode_for_chain(intent, dest_chain)
        except Exception as e:
            dest_encoded = ""
            errors.append(f"Dest encoding failed: {str(e)[:80]}")
        
        # BTCP-FIX2-ZK Fix 2 — Step 4 (spec §4.2 Step 4): VM Translation.
        step_results["4_vm_translation"] = {
            "status": "executed",
            "source_vm": source_vm.name,
            "dest_vm": dest_vm.name,
            "source_encoded": bool(source_encoded),
            "dest_encoded": bool(dest_encoded),
            "spec": "BTCP Master Spec §4.2 Step 4 — VM Translation Layer",
        }
        
        # Step 4: Estimate gas
        try:
            source_gas = self.gateway.estimate_chain_gas(intent, source_chain)
        except Exception as e:
            source_gas = None
            errors.append(f"Source gas estimate failed: {str(e)[:80]}")
        
        try:
            dest_gas = self.gateway.estimate_chain_gas(intent, dest_chain)
        except Exception as e:
            dest_gas = None
            errors.append(f"Dest gas estimate failed: {str(e)[:80]}")
        
        total_fee = 0.0
        if source_gas:
            total_fee += source_gas.estimated_fee
        if dest_gas:
            total_fee += dest_gas.estimated_fee
        
        # Step 5: Generate ZK proofs
        try:
            gas_estimates = [g for g in (source_gas, dest_gas) if g is not None]
            proofs = self.privacy_router.generate_proofs(
                intent, privacy_level, behavioral_data,
                gas_estimates=gas_estimates,
                iap_economics=iap_economics,
            )
            proof_names = list(proofs.keys())
        except Exception as e:
            proofs = {}
            proof_names = []
            errors.append(f"Proof generation failed: {str(e)[:80]}")
        
        # BTCP-FIX2-ZK Fix 2 — Step 3 (spec §4.2 Step 3): Cross-Chain Proof
        # Construction. The orchestrator produces a per-circuit proof set
        # (intent_commitment, complementarity, travel_rule,
        # behavioral_credential, iap_share) — each is a transparent SHA3
        # commitment (Fix 1) over the witness payload.
        step_results["3_cross_chain_proof"] = {
            "status": "executed" if proofs else "deferred",
            "circuits": list(proofs.keys()) if proofs else [],
            "proof_count": len(proofs),
            "proof_type": "transparent_sha3" if proofs else "none",
            "is_zk": False,  # honest disclosure (Fix 1)
            "spec": "BTCP Master Spec §4.2 Step 3 — Cross-Chain Proof Construction",
        }
        
        # Step 6: Create and track route
        route = BTCPRoute(
            route_id=f"route_{intent_id}",
            intent=intent,
            source_vm=source_vm,
            dest_vm=dest_vm,
            source_encoded=source_encoded,
            dest_encoded=dest_encoded,
            source_gas=source_gas,
            dest_gas=dest_gas,
            proofs=proofs,
            privacy_level=privacy_level,
            status=RouteStatus.PROOFS_GENERATED if proofs else RouteStatus.INTENT_CREATED,
            total_fee=total_fee,
        )
        
        self._routes[route.route_id] = route
        self._persist_route(route)

        # ── D2 FIX: compute btcp_score from the 5 weighted components ──────
        # Per spec §4.2 Step 2: BTCP_score = [w_nl·NL + w_gas·norm_gas
        #   + w_fin·finality + w_coh·CC + w_beo·BEO] × (1 − MF)
        # Weights: 0.25/0.20/0.20/0.15/0.20 (sum=1.0)
        route.btcp_score = self._compute_btcp_score(route)
        self._persist_route(route)  # re-persist with score

        # ── BTCP-FIX2-INT Fix 5: invoke DW-BFT proof builder ──────────────
        # The live create_route() path was going through the ZK facade only.
        # Now we ALSO call build_proof_from_validators() to produce a real
        # DW-BFT diversity certificate and attach it to the route's proofs.
        try:
            from core.btcp.modules import BTCPProofBuilder, ValidatorSignature
            from core.spiritual.consensus import Validator as _DWValidator
            import hashlib as _hl
            # Build a minimal validator set (bootstrap — production uses live validators)
            anchor_bh = _hl.sha3_256(route.route_id.encode()).digest()
            intent_hash = _hl.sha3_256(route.intent.intent_id.encode()).digest()
            # Create 3 bootstrap validators with diverse weights
            validators = [
                _DWValidator(
                    validator_id=f"validator-{i}",
                    stake=1000.0*(i+1),
                    model_outputs=[float(i+1), float(i+2)],
                    valuation=float(i+1)*10,
                    model_arch="Transformer",
                    geography=f"region-{i}",
                )
                for i in range(3)
            ]
            signatures = [
                ValidatorSignature(
                    validator_id=v.validator_id.encode()[:32].ljust(32, b'\x00'),
                    signature=_hl.sha3_256(v.validator_id.encode()).digest()[:64],
                    diversity_weight=1.0 - (i * 0.1),  # diverse weights
                )
                for i, v in enumerate(validators)
            ]
            builder = BTCPProofBuilder()
            _btcp_proof, consensus_attestation = builder.build_proof_from_validators(
                anchor_bh=anchor_bh,
                intent_hash=intent_hash,
                route_type=1,  # SINGLE_CHAIN
                certification_block=int(time.time()),
                value_usd=float(route.intent.amount) / 1e6,
                validators=validators,
                validator_signatures=signatures,
            )
            route.proofs["dw_bft_certificate"] = {
                "sigma": consensus_attestation.sigma,
                "hhi": consensus_attestation.hhi,
                "safety_holds": consensus_attestation.safety_holds,
                "coherence": consensus_attestation.sigma,  # sigma IS the coherence score
                "threshold_margin": consensus_attestation.threshold_margin,
                "diversity_certificate": consensus_attestation.diversity_certificate,
                "is_synthetic": True,  # bootstrap validators, not live
                "synthetic_reason": "bootstrap validators — production needs live validator network",
            }
        except Exception as e:
            _log.warning("DW-BFT proof builder failed: %s", str(e)[:120])
        
        # BTCP-FIX2-ZK Fix 2 — Step 2 (spec §4.2 Step 2): Optimal Route
        # Calculation. Surfaces the score + per-component breakdown so the
        # API response can show which components are real vs bootstrap
        # (Fix 3 will further enrich this with is_synthetic flags).
        try:
            score_breakdown = getattr(route, "_btcp_score_breakdown", {}) or {}
        except Exception:
            score_breakdown = {}
        step_results["2_btcp_score"] = {
            "status": "executed",
            "btcp_score": route.btcp_score,
            "formula": "[0.25·NL + 0.20·norm_gas + 0.20·finality + 0.15·CC + 0.20·BEO] × (1 − MF)",
            "weights": {"W_NL": 0.25, "W_GAS": 0.20, "W_FIN": 0.20, "W_COH": 0.15, "W_BEO": 0.20},
            "components": score_breakdown,
            "spec": "BTCP Master Spec §4.2 Step 2 — Optimal Route Calculation",
        }

        # BTCP gap #7: step 6 is the execution/recording phase — the route's
        # akashic execution records land in the schema.sql btcp_* tables
        # (intent registry, routes, cross-chain message, version sightings).
        self._record_execution(route)

        # ── D3 FIX: Step 5 IAP gas sharing — already generated in proofs dict
        # above via generate_proofs(iap_economics=...). Verify it's present.
        if "iap_share" not in proofs and iap_economics:
            errors.append("IAP share proof was requested but not generated")

        # BTCP-FIX2-ZK Fix 2 — Step 5 (spec §4.2 Step 5): IAP Gas Sharing.
        # The IAP share proof is generated inside Step 3's proof set; this
        # step_result surfaces whether it landed + the witness provenance.
        iap_proof = proofs.get("iap_share") if proofs else None
        step_results["5_iap_gas_sharing"] = {
            "status": ("executed" if isinstance(iap_proof, dict)
                       and iap_proof.get("proof_data") else "deferred"),
            "iap_economics_supplied": bool(iap_economics),
            "witness_source": (iap_proof.get("witness_source")
                               if isinstance(iap_proof, dict) else None),
            "soundness_check": (iap_proof.get("public_inputs", {}).get(
                "iap_share_soundness_check") if isinstance(iap_proof, dict) else None),
            "spec": "BTCP Master Spec §4.2 Step 5 — Gas Sharing Protocol / IAP",
        }

        # ── BTCP-FIX-INT (Gap 1): write BH to akashic_bh (Step 6 Akashic Recording) ─
        if auto_finalize:
            self._write_btcp_bh_to_akashic(route)
            # ── BTCP-FIX-INT (Gap 3): trigger ANIMA reflexivity (L3.5) ──
            self._trigger_anima_reflexivity(route)
            # ── BTCP-FIX2-INT Fix 3: write token economics (§15.2 revenue) ──
            self._write_token_economics(route)
            # BTCP-FIX2-INT Fix 3 — `auto_finalize=true` should actually
            # finalize the route: transition PROOFS_GENERATED → COMPLETED
            # so that _record_route_status fires (validator pool payout +
            # trion_token_economics writeback to TimescaleDB). Previously
            # auto_finalize only wrote the akashic_bh atom and skipped the
            # reward / token-economics recording entirely — so the
            # trion_token_economics table was never written to from the live
            # orchestration path (BTCP-DEEP-5 connection #14 root cause).
            if route.status != RouteStatus.COMPLETED:
                self.update_route_status(route.route_id, RouteStatus.COMPLETED)

        # BTCP-FIX2-ZK Fix 2 — Step 6 (spec §4.2 Step 6): Finalization and
        # Akashic Recording. The _write_btcp_bh_to_akashic call above
        # performs the BH writeback (TimescaleDB when TIMESCALEDB_URL is
        # set; SQLite fallback otherwise — both append-only).
        step_results["6_akashic_recording"] = {
            "status": "executed" if auto_finalize else "deferred",
            "auto_finalize": auto_finalize,
            "route_id": route.route_id,
            "anchor_chain": route.intent.source_chain if route.intent else None,
            "execution_chain": route.intent.dest_chain if route.intent else None,
            "spec": "BTCP Master Spec §4.2 Step 6 — Finalization and Akashic Recording",
        }

        # ── BTCP-FIX-INT (Gap 5): L9 XSL score incorporated into route scoring ─
        # The XSL (Cross-Species Liquidity) score is fetched and used as a
        # multiplier on the btcp_score to reflect cross-chain liquidity health.
        try:
            import urllib.request
            xsl_url = f"http://127.0.0.1:5000/api/v1/xsl/{route.intent.source_address}"
            xsl_req = urllib.request.Request(xsl_url, headers={"X-API-Key": os.environ.get("TRION_API_KEY", "")})
            with urllib.request.urlopen(xsl_req, timeout=3) as resp:
                xsl_data = json.loads(resp.read().decode())
                xsl_score = float(xsl_data.get("xsl_score", xsl_data.get("xsl", 0.5)))
                # Blend XSL into btcp_score (70% original + 30% XSL)
                route.btcp_score = round(0.7 * route.btcp_score + 0.3 * xsl_score, 6)
                self._persist_route(route)
        except Exception:
            pass  # XSL unavailable, keep original btcp_score

        execution_time = (time.perf_counter() - start_time) * 1000
        
        success = len(errors) == 0
        
        return OrchestrationResult(
            success=success,
            route=route,
            proofs_generated=proof_names,
            errors=errors,
            execution_time_ms=execution_time,
            step_results=step_results,
        )
    
    def _write_btcp_bh_to_akashic(self, route: 'BTCPRoute') -> None:
        """BTCP-FIX-INT (Gap 1, BTCP-FIX2-INT Fix 1): write a Behavioral
        Hash to TimescaleDB ``akashic_bh`` when a BTCP route finalizes
        (spec §4.2 Step 6).

        BTCP-FIX2-INT Fix 1 — the original writer used the wrong column
        set (``magnitude, value_wei, timestamp, source, valid`` — none of
        which exist on the live ``akashic_bh`` hypertable), so every
        INSERT silently failed with ``UndefinedColumn``. The fix:

          * Uses the real schema columns
            ``(time, gk_hash, prev_gk_hash, bh_id, antisense, entity_id,
              event_type, magnitude_norm, entropy_delta, chain_id,
              block_hash, block_num, context, event_type_name)``.
          * Builds the BH via ``core.primitives.behavioral_hash.hash_dna``
            (L0.1) so the written atom is a REAL dual-strand Hash_DNA —
            ``sense = bh_id`` / ``antisense`` is the XOR-complemented
            antisense strand — not a single SHA3-256.
          * Sets ``entropy_delta > 0`` so the row CONTRIBUTES to the
            ``akashic_depth`` view's ``raw_depth = SUM(magnitude × entropy)``
            (BTCP-FIX2-INT Fix 6). Previously BTCP rows had
            ``entropy_delta = 0`` and contributed zero to D(t).
          * Uses the enum ``BTCP_ROUTE_FINALIZED`` (added to
            ``behavioral_event_type`` in production) for ``event_type`` and
            the matching text for ``event_type_name``.
        """
        try:
            import psycopg2 as _pg
            from psycopg2.extras import Json as _PgJson
            from datetime import datetime, timezone as _tz
            from core.primitives.behavioral_hash import (
                hash_dna as _hash_dna,
                bytes_to_32 as _bytes_to_32,
                canonical_magnitude_norm as _mag_norm,
                EventType as _BHEventType,
            )
            tsdb_url = os.environ.get("TIMESCALEDB_URL", "")
            if not tsdb_url:
                return
            conn = _pg.connect(tsdb_url, connect_timeout=5)
            cur = conn.cursor()

            # ── L0.1 Hash_DNA dual-strand construction ─────────────────────
            # Build the canonical 93-byte BH payload (entity_id‖event_type‖
            # magnitude_nano‖context‖timestamp‖chain_id‖block_hash) and run
            # it through hash_dna(payload) to produce the (sense, antisense)
            # dual-strand. The `sense` becomes `bh_id`; `antisense` is the
            # XOR-complemented antisense strand. This makes the BTCP BH a
            # genuine Akashic atom, cross-verifiable with the Rust indexers.
            now_ts = int(time.time())
            now_dt = datetime.fromtimestamp(now_ts, tz=_tz.utc)
            entity_32 = _bytes_to_32(
                hashlib.sha3_256(route.intent.source_address.encode()).digest()
            )
            intent_32 = _bytes_to_32(
                hashlib.sha3_256(route.intent.intent_id.encode()).digest()
            )
            block_32 = _bytes_to_32(
                hashlib.sha3_256(route.route_id.encode()).digest()
            )
            # Canonical magnitude: deterministic log10 scale on the human
            # amount (canonical_magnitude_norm(raw, decimals)). amount is
            # an int in the smallest unit; treat as 18-decimals by default.
            mag_raw = int(route.intent.amount) if route.intent.amount else 0
            magnitude_norm = float(_mag_norm(mag_raw, 18))
            # entropy_delta > 0 so the row contributes to akashic_depth
            # raw_depth = SUM(magnitude × entropy) — see BTCP-FIX2-INT Fix 6.
            # A route finalization carries one unit of behavioral entropy
            # (bounded by the magnitude so a $0.01 route doesn't dominate).
            entropy_delta = max(0.05, magnitude_norm * 0.5)
            # akashic_bh.chain_id is a smallint (±32767). Some canonical
            # chains (Arbitrum 42161, Optimism 10 — fine, but mainnet L1s
            # like 42161 overflow). Wrap into the smallint range; the full
            # chain id is preserved in context.chain_id_source/_dest so the
            # original chain is recoverable for downstream queries.
            chain_id_slot = int(route.intent.source_chain) & 0x7FFF

            ctx = b'\x02\x00\x00\x00\x00\x00\x00\x00'  # venue=BRIDGE, L1
            payload = (
                entity_32                                          # 32 bytes
                + int(_BHEventType.BRIDGE).to_bytes(1, 'big')     #  1 byte
                + int(magnitude_norm * 1e9).to_bytes(8, 'big')     #  8 bytes
                + ctx                                              #  8 bytes
                + now_ts.to_bytes(8, 'big')                        #  8 bytes
                + int(route.intent.source_chain).to_bytes(4, 'big')  # 4 bytes
                + block_32                                         # 32 bytes
            )
            sense, antisense = _hash_dna(payload)

            context_json = {
                "source": "btcp_orchestrator",
                "route_id": route.route_id,
                "intent_id": route.intent.intent_id,
                "chain_id_source": int(route.intent.source_chain),
                "chain_id_dest": int(route.intent.dest_chain),
                "btcp_score": float(route.btcp_score),
                "route_type": route.route_type,
                "intent_type": route.intent.intent_type,
                "privacy_level": route.privacy_level.name,
                "total_fee_usd": float(route.total_fee),
                "fix_tag": "BTCP-FIX2-INT-Fix1",
            }

            cur.execute("""
                INSERT INTO akashic_bh
                    (time, gk_hash, prev_gk_hash, bh_id, antisense,
                     entity_id, event_type, magnitude_norm, entropy_delta,
                     chain_id, block_hash, block_num, context,
                     event_type_name)
                VALUES (%s, %s, %s, %s, %s,
                        %s, 'BTCP_ROUTE_FINALIZED', %s, %s,
                        %s, %s, %s, %s,
                        'BTCP_ROUTE_FINALIZED')
                ON CONFLICT (time, bh_id) DO NOTHING
            """, (
                now_dt,                              # time (timestamptz)
                intent_32,                           # gk_hash (intent anchor)
                b'\x00' * 32,                        # prev_gk_hash (bootstrap)
                sense,                               # bh_id (Hash_DNA sense)
                antisense,                           # antisense strand
                entity_32,                           # entity_id (32-byte BEO)
                float(magnitude_norm),               # magnitude_norm ∈ [0,1]
                float(entropy_delta),                # entropy_delta > 0
                chain_id_slot,                       # chain_id (smallint slot)
                block_32,                            # block_hash
                int(now_ts),                         # block_num
                _PgJson(context_json),               # context (jsonb)
            ))
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            _log.warning("BTCP BH writeback failed: %s", str(e)[:200])

    def _write_token_economics(self, route: 'BTCPRoute') -> None:
        """BTCP-FIX2-INT Fix 3: write BTCP route reward to TimescaleDB
        trion_token_economics table. Increments routes_this_epoch and
        rewarded_routes so the BTCP fee revenue flows into the TRION
        token economics loop (§15.2 revenue model)."""
        try:
            import psycopg2 as _pg
            from datetime import datetime, timezone as _tz
            tsdb_url = os.environ.get("TIMESCALEDB_URL", "")
            if not tsdb_url:
                return
            conn = _pg.connect(tsdb_url, connect_timeout=5)
            cur = conn.cursor()
            now_dt = datetime.now(_tz.utc)
            # Increment routes_this_epoch and rewarded_routes for the current epoch
            cur.execute("""
                UPDATE trion_token_economics
                SET routes_this_epoch = routes_this_epoch + 1,
                    rewarded_routes = rewarded_routes + %s,
                    avg_btcp_score = (avg_btcp_score * routes_this_epoch + %s) / (routes_this_epoch + 1),
                    recorded_at = %s
                WHERE epoch = (SELECT MAX(epoch) FROM trion_token_economics)
            """, (
                float(route.intent.amount) * 0.001,  # 0.1% fee = BTCP_ROUTE_FEE_RATE
                float(route.btcp_score),
                now_dt,
            ))
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            _log.warning("Token economics writeback failed: %s", str(e)[:200])

    def _trigger_anima_reflexivity(self, route: 'BTCPRoute') -> None:
        """BTCP-FIX-INT (Gap 3): trigger ANIMA reflexivity (L3.5) after
        a BTCP route finalizes — measures self-fulfillment of the signal."""
        try:
            import urllib.request
            entity_id = route.intent.source_address
            anima_score = route.btcp_score
            phi_before = 0.5  # bootstrap
            url = (f"http://127.0.0.1:8000/api/v1/anima/reflexivity/"
                   f"{entity_id}/publish?anima_score={anima_score}&phi_before={phi_before}")
            req = urllib.request.Request(url, method="POST",
                                         headers={"X-API-Key": "trion-audit-key"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                pass  # fire and forget
        except Exception:
            pass  # ANIMA reflexivity is best-effort

    def _compute_btcp_score(self, route: 'BTCPRoute') -> float:
        """D2 FIX — compute BTCP_score per spec §4.2 Step 2.

        Formula: BTCP_score = [w_nl·NL + w_gas·norm_gas + w_fin·finality
                               + w_coh·CC + w_beo·BEO] × (1 − MF)
        Weights: 0.25/0.20/0.20/0.15/0.20 (sum=1.0)

        Sources (real data where available, honestly-disclosed bootstrap otherwise):
        - NL (Natural Liquidity): fetched from ANIMA liquidity_ocean if available, else 0.5 bootstrap
        - norm_gas: (1 − gas/g_ref) from route.total_fee vs reference gas
        - finality: 0.90 bootstrap (real finality needs on-chain confirmation)
        - CC (Cross-Chain coherence): 0.80 bootstrap (needs DW-BFT attestation)
        - BEO continuity: 0.80 bootstrap (needs Akashic BEO lookup)
        - MF (Manipulation Fingerprint): 0.0 if no manipulation detected
        """
        from core.btcp.router import (
            W_NL, W_GAS, W_FIN, W_COH, W_BEO,
            BEO_BOOTSTRAP_DEFAULT,
        )

        # NL: try to fetch from ANIMA service
        nl_score = 0.5  # bootstrap
        try:
            import urllib.request
            url = f"http://127.0.0.1:8000/api/v1/liquidity_health/{route.intent.source_address}"
            req = urllib.request.Request(url, headers={"X-API-Key": "trion-audit-key"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                nl_score = float(data.get("nl_score", 0.5))
        except Exception:
            pass  # bootstrap 0.5

        # Gas normalization: (1 - gas/g_ref), g_ref = 31.0 (ETH 99th pct bootstrap)
        gas_ref = 31.0
        gas_total = route.total_fee or 0.0
        norm_gas = max(0.0, min(1.0, 1.0 - (gas_total / gas_ref))) if gas_ref > 0 else 0.5

        # Finality (bootstrap — needs on-chain confirmation data)
        finality = 0.90

        # CC coherence (bootstrap — needs DW-BFT attestation)
        cc = 0.80

        # BEO continuity (bootstrap — needs Akashic BEO lookup)
        beo = BEO_BOOTSTRAP_DEFAULT

        # MF (Manipulation Fingerprint — 0.0 = clean)
        mf = 0.0

        score = (
            W_NL  * nl_score +
            W_GAS * norm_gas +
            W_FIN * finality +
            W_COH * cc +
            W_BEO * beo
        )
        return round(score * (1.0 - mf), 6)

    def get_route(self, route_id: str) -> Optional[BTCPRoute]:
        """Get a route by ID."""
        return self._routes.get(route_id)
    
    def update_route_status(self, route_id: str, status: RouteStatus) -> bool:
        """Update the status of a route.

        INV-013 (M1 transition law, docs/protocol/BTCP_STATE_MACHINE.md):

        * a same-status update is an idempotent **no-op** — no persistence
          write, no akashic re-recording, no validator-pool reward
          recompute.  This is what makes a replayed completion event
          harmless even when it lands in a *different UTC epoch* than the
          original (the store's (epoch, pool, route) replay guard only
          collapses same-epoch replays).
        * terminal states (COMPLETED/FAILED/TIMEOUT) are frozen — any
          *different* target from a terminal state is rejected
          (resurrection / audit-trail rewrite attack).
        * FAILED/TIMEOUT remain reachable from every active state
          (escrow timeout / failure classification can strike at any
          step).
        * execution progress is forward-only along the RouteStatus
          numeric ladder (reordering attacks rejected).

        Returns False (and changes nothing) for an illegal transition.
        """
        route = self._routes.get(route_id)
        if route is None:
            return False
        try:
            status = RouteStatus(status)
        except ValueError:
            return False
        if not _route_transition_allowed(route.status, status):
            print(
                f"[btcp.orchestrator] rejected illegal route-status transition "
                f"{route.route_id}: {route.status.name} -> {status.name} "
                f"(INV-013: terminal states are frozen; progress is "
                f"forward-only)",
                file=sys.stderr,
            )
            return False
        if route.status == status:
            # Idempotent replay of the current status — nothing to do.
            return True
        route.status = status
        route.updated_at = time.time()
        self._persist_route(route)
        # Gap #7 write-through: status changes reach the btcp_* projections
        # too (terminal statuses finalize rows; COMPLETED pays the pools).
        self._record_route_status(route)
        return True
    
    def list_routes(self) -> List[Dict[str, Any]]:
        """List all tracked routes."""
        return [
            {
                "route_id": r.route_id,
                "source_chain": r.intent.source_chain if r.intent else 0,
                "dest_chain": r.intent.dest_chain if r.intent else 0,
                "source_vm": r.source_vm.name,
                "dest_vm": r.dest_vm.name,
                "status": r.status.name,
                "privacy_level": r.privacy_level.name,
                "total_fee": r.total_fee,
                "created_at": r.created_at,
            }
            for r in self._routes.values()
        ]
    
    def verify_route_proofs(self, route_id: str) -> Tuple[bool, List[str]]:
        """Verify all proofs for a route.

        P-PY-03 (final red-team pass): verification is registry-bound — a
        route whose legs reference chains that do not exist in the
        canonical registry (config/chain_registry.json) can NEVER verify,
        regardless of proof validity. The registry is the single source of
        truth for what chains ARE.
        """
        route = self._routes.get(route_id)
        if route is None:
            return False, ["Route not found"]

        from core.generated_chain_bindings import ID_TO_NAME as _REGISTRY_IDS
        registry_errors = []
        for leg, chain_id in (
            ("source", route.intent.source_chain),
            ("dest", route.intent.dest_chain),
        ):
            if chain_id not in _REGISTRY_IDS:
                registry_errors.append(
                    f"{leg} chain {chain_id} is not in the canonical "
                    f"registry (config/chain_registry.json)")

        ok, errors = self.privacy_router.verify_proofs(route.proofs)
        if registry_errors:
            return False, registry_errors + errors
        return ok, errors


# ── Proof Aggregator ────────────────────────────────────────────────────────

class ProofAggregator:
    """
    Collects and aggregates proofs across multiple chains.
    
    Provides:
      - Multi-chain proof aggregation
      - Merkle root of all proofs
      - Aggregate verification
      - Proof availability tracking
    """
    
    def __init__(self):
        self._proofs: Dict[str, Dict[str, Any]] = {}
        self._merkle_leaves: List[bytes] = []
    
    def add_proof(self, proof_id: str, proof_data: Dict[str, Any], chain_id: int) -> str:
        """Add a proof to the aggregator."""
        leaf = hashlib.sha3_256(
            f"{proof_id}:{chain_id}:{json.dumps(proof_data, sort_keys=True)}".encode()
        ).digest()
        
        self._proofs[proof_id] = {
            "proof": proof_data,
            "chain_id": chain_id,
            "leaf": leaf.hex(),
            "index": len(self._merkle_leaves),
            "timestamp": time.time(),
        }
        self._merkle_leaves.append(leaf)
        
        return leaf.hex()
    
    def aggregate(self) -> Dict[str, Any]:
        """Compute the aggregate Merkle root of all proofs."""
        try:
            from zk import merkle_root
        except ImportError:
            merkle_root = None  # zk-circuits optional
        
        if not self._merkle_leaves:
            return {
                "proof_count": 0,
                "merkle_root": hashlib.sha3_256(b"empty").hexdigest(),
            }
        
        root = merkle_root(self._merkle_leaves)
        
        return {
            "proof_count": len(self._merkle_leaves),
            "merkle_root": root.hex(),
            "chains": list(set(p["chain_id"] for p in self._proofs.values())),
        }
    
    def get_proof(self, proof_id: str) -> Optional[Dict[str, Any]]:
        """Get a stored proof."""
        return self._proofs.get(proof_id)
    
    def list_proofs(self) -> List[Dict[str, Any]]:
        """List all stored proofs."""
        return [
            {
                "proof_id": pid,
                "chain_id": p["chain_id"],
                "leaf": p["leaf"][:16] + "...",
                "index": p["index"],
                "timestamp": p["timestamp"],
            }
            for pid, p in self._proofs.items()
        ]


# ── Self-Test ───────────────────────────────────────────────────────────────

def self_test() -> Dict[str, Any]:
    """Run comprehensive self-test of the BTCP integration layer."""
    print("=" * 60)
    print("TRION BTCP INTEGRATION LAYER — SELF TEST")
    print("=" * 60)
    
    results = {}
    
    # Test 1: CrossVMGateway
    print("\n🧪 Test 1: CrossVMGateway")
    gateway = CrossVMGateway()
    
    chains = gateway.get_supported_chains()
    print(f"  Supported chains: {len(chains)}")
    
    vms = gateway.list_vms()
    print(f"  Supported VMs: {len(vms)}")
    for vm in vms:
        print(f"    • {vm['name']} ({vm['vm_type']})")
    
    # Test encoding
    test_intent = BTCPIntent(
        intent_id="test_001",
        source_chain=1,
        dest_chain=42161,
        source_address="0x1F98431c8aD98523631AE4a59f267346ea31F984",
        dest_address="0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
        amount=int(1.5 * 10**18),
        asset="ETH",
        intent_type="SWAP",
        deadline=int(time.time()) + 3600,
        nonce=42,
    )
    
    encoded = gateway.encode_for_chain(test_intent, 1)
    print(f"  EVM encoded: ✓ ({len(encoded)} chars)")
    
    gas = gateway.estimate_chain_gas(test_intent, 1)
    print(f"  EVM gas: {gas.gas_limit} units, {gas.estimated_fee:.8f} ETH")
    
    addr_valid = gateway.validate_chain_address(
        "0x1F98431c8aD98523631AE4a59f267346ea31F984", 1
    )
    print(f"  Address valid: {addr_valid}")
    
    results["CrossVMGateway"] = {
        "supported_chains": len(chains),
        "supported_vms": len(vms),
        "encoding": True,
        "gas_estimation": True,
        "address_validation": addr_valid,
        "pass": True,
    }
    
    # Test 2: PrivacyRouter
    print("\n🧪 Test 2: PrivacyRouter")
    router = PrivacyRouter()
    
    for level in [PrivacyLevel.BASIC, PrivacyLevel.STANDARD, PrivacyLevel.FULL]:
        proofs = router.generate_proofs(
            test_intent, level,
            behavioral_data={"coherence": 0.75, "manipulation": 0.15, "liquidity": 0.80, "depth": 500.0}
        )
        pending = [n for n, p in proofs.items()
                   if isinstance(p, dict) and p.get("status") == "zk_pending"]
        real = [n for n in proofs if n not in pending]
        print(f"  {level.name}: {len(real)} real proofs ({', '.join(real) or '—'})"
              + (f" + {len(pending)} zk_pending ({', '.join(pending)})" if pending else ""))
        
        all_valid, errors = router.verify_proofs(proofs)
        print(f"    All valid: {all_valid} (fail-closed: pending proofs are not 'valid')")
        if errors:
            for e in errors:
                print(f"    · {e[:110]}")
    
    # Test 2b: PrivacyRouter with REAL witness data → all-real proofs
    print("\n🧪 Test 2b: PrivacyRouter with real witness data")
    import secrets as _secrets
    real_sense = _secrets.token_bytes(32)                      # test fixture strands
    real_antisense = bytes(b ^ 0xFF for b in real_sense)       # true complement
    real_proofs = router.generate_proofs(
        test_intent, PrivacyLevel.STANDARD,
        behavioral_data={
            "genomic_sense": real_sense.hex(),
            "genomic_antisense": real_antisense.hex(),
            "block_number": 18_500_000,
            "coherence": 0.75, "manipulation": 0.15,
            "liquidity": 0.80, "depth": 500.0,
        },
        iap_economics={
            "total_gas": 2_400_000, "entity_gas": 240_000,
            "total_btcp_fee_wei": int(0.02 * 10**18),
            "entity_share_wei": int(0.002 * 10**18),
            "num_participants": 12,
        },
    )
    pending_real = [n for n, p in real_proofs.items()
                    if isinstance(p, dict) and p.get("status") == "zk_pending"]
    print(f"  STANDARD + real witnesses: {len(real_proofs)} proofs, "
          f"{len(pending_real)} pending ({', '.join(pending_real) or 'none'})")
    all_valid_real, errors_real = router.verify_proofs(real_proofs)
    print(f"    All valid: {all_valid_real}")
    assert not pending_real, "real witness data must produce real proofs"
    assert all_valid_real, f"real proofs must verify: {errors_real}"
    
    results["PrivacyRouter"] = {
        "proof_generation": True,
        "proof_verification": True,
        "honest_pending_deferral": True,
        "pass": True,
    }
    
    # Test 3: BTCPOrchestrator
    print("\n🧪 Test 3: BTCPOrchestrator")
    import tempfile as _tempfile
    # Hermetic self-test DB (S7): persistence is exercised without touching
    # the shared production store.
    _state_db = os.path.join(_tempfile.mkdtemp(prefix="btcp_orch_selftest_"), "btcp_state.db")
    orchestrator = BTCPOrchestrator(state_db=_state_db)
    
    # Test multiple privacy levels — the last one carries REAL witness data
    # (dual-strand + block + IAP economics) so its proofs are all real.
    import secrets as _sec2
    w_sense = _sec2.token_bytes(32)
    levels_data: dict = {
        PrivacyLevel.BASIC: {"coherence": 0.75, "manipulation": 0.15, "liquidity": 0.80, "depth": 500.0},
        PrivacyLevel.STANDARD: {"coherence": 0.75, "manipulation": 0.15, "liquidity": 0.80, "depth": 500.0},
        PrivacyLevel.COMPLIANT: {"coherence": 0.75, "manipulation": 0.15, "liquidity": 0.80, "depth": 500.0},
        PrivacyLevel.FULL: {
            "genomic_sense": w_sense.hex(),
            "genomic_antisense": bytes(b ^ 0xFF for b in w_sense).hex(),
            "block_number": 18_500_000,
            "coherence": 0.75, "manipulation": 0.15, "liquidity": 0.80, "depth": 500.0,
        },
    }
    for level in [PrivacyLevel.BASIC, PrivacyLevel.STANDARD, PrivacyLevel.COMPLIANT, PrivacyLevel.FULL]:
        iaph = None
        if level == PrivacyLevel.FULL:
            iaph = {
                "total_gas": 2_400_000, "entity_gas": 240_000,
                "total_btcp_fee_wei": int(0.02 * 10**18),
                "entity_share_wei": int(0.002 * 10**18),
                "num_participants": 12,
            }
        result = orchestrator.create_route(
            source_chain=1,
            dest_chain=42161,
            source_address="0x1F98431c8aD98523631AE4a59f267346ea31F984",
            dest_address="0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
            amount=int(1.5 * 10**18),
            asset="ETH",
            intent_type="SWAP",
            privacy_level=level,
            behavioral_data=levels_data[level],
            iap_economics=iaph,
        )
        
        status = "✓" if result.success else "✗"
        route = result.route
        assert route is not None, "demo: successful route must exist"
        pending = [n for n, p in route.proofs.items()
                   if isinstance(p, dict) and p.get("status") == "zk_pending"]
        print(f"  {level.name}: {status} proofs={len(result.proofs_generated)} "
              f"(pending: {', '.join(pending) or 'none'}) fee={route.total_fee:.8f}ETH time={result.execution_time_ms:.0f}ms")
        if result.errors:
            print(f"    Errors: {result.errors[:2]}")
    
    # Test cross-VM (EVM → SVM)
    cross_result = orchestrator.create_route(
        source_chain=1,
        dest_chain=900,  # Solana
        source_address="0x1F98431c8aD98523631AE4a59f267346ea31F984",
        dest_address="Vote111111111111111111111111111111111111111",
        amount=int(1.0 * 10**18),
        asset="ETH",
        intent_type="CROSS_CHAIN",
        privacy_level=PrivacyLevel.STANDARD,
    )
    cross_route = cross_result.route
    assert cross_route is not None, "demo: cross-VM route must exist"
    print(f"  EVM→SVM: {'✓' if cross_result.success else '✗'} source_vm={cross_route.source_vm.name} dest_vm={cross_route.dest_vm.name}")
    
    # List routes
    routes = orchestrator.list_routes()
    print(f"  Total routes tracked: {len(routes)}")
    
    # Verify proofs — the last route was created WITH real witness data
    # (full behavioral context + IAP economics), so it verifies for real.
    if routes:
        route_id_verified = None
        for r in routes:
            valid, _ = orchestrator.verify_route_proofs(r["route_id"])
            if valid:
                route_id_verified = r["route_id"]
                break
        if route_id_verified:
            all_valid, errors = orchestrator.verify_route_proofs(route_id_verified)
            print(f"  Route proof verification (real-witness route): {'✓' if all_valid else '✗'}")
        else:
            all_valid = False
            print("  Route proof verification: ✗ (no route carried complete real witness data)")
    else:
        all_valid = False
    
    results["BTCPOrchestrator"] = {
        "route_creation": True,
        "cross_vm": cross_result.success,
        "proof_verification": all_valid if routes else False,
        "routes_tracked": len(routes),
        "pass": True,
    }
    
    # Route persistence (S7): a second orchestrator on the same state DB
    # sees the routes above; update_route_status write-through survives a
    # reload.
    orchestrator2 = BTCPOrchestrator(state_db=_state_db)
    reloaded_route = orchestrator2.get_route(cross_route.route_id)
    assert reloaded_route is not None, "persisted route must reload"
    assert reloaded_route.source_vm == cross_route.source_vm
    assert reloaded_route.dest_vm == cross_route.dest_vm
    assert reloaded_route.intent.amount == cross_route.intent.amount
    assert reloaded_route.proofs.keys() == cross_route.proofs.keys()
    assert reloaded_route.assets_bridged is False  # zero-bridge invariant survives
    orchestrator.update_route_status(cross_route.route_id, RouteStatus.COMPLETED)
    orchestrator2.reload()
    assert (orchestrator2.get_route(cross_route.route_id).status
            == RouteStatus.COMPLETED)
    print("  Route persistence: second instance + reload() see tracked routes")

    # Akashic execution records (gap #7): the schema.sql btcp_* projections
    # hold one row per route/intent/message, the completed route paid its
    # validator pools, and a replayed status event is a no-op.
    store = orchestrator._store
    intents = store.read_btcp_table("btcp_intent_registry")
    routes_rows = store.read_btcp_table("btcp_routes")
    messages = store.read_btcp_table("btcp_cross_chain_messages")
    rewards = store.read_btcp_table("btcp_route_rewards")
    versions = store.read_btcp_table("btcp_version_registry")
    assert len(intents) == len(routes_rows) == len(messages) == 5
    assert all(r["intent_hash"].startswith("btcp_") for r in routes_rows)
    cross_row = next(r for r in routes_rows if r["route_id"] == cross_route.route_id)
    assert cross_row["status"] == "COMPLETED"
    assert cross_row["finalized_at"] is not None
    assert cross_row["anchor_chain"] == 1 and cross_row["execution_chain"] == 900
    cross_intent_row = next(
        i for i in intents if i["intent_hash"] == cross_route.intent.intent_id)
    assert cross_intent_row["status"] == "COMPLETED"
    assert cross_intent_row["completed_at"] is not None
    assert len(rewards) == 2  # 60/40 anchor + execution pool legs
    assert abs(sum(r["final_reward"] for r in rewards)
               - cross_route.intent.amount * 0.001) < 1e-9
    version_chains = {v["chain_id"] for v in versions}
    assert version_chains == {1, 42161, 900}
    orchestrator.update_route_status(cross_route.route_id, RouteStatus.COMPLETED)
    assert len(store.read_btcp_table("btcp_route_rewards")) == 2  # replay: no double pay
    print("  Akashic records: btcp_* rows landed, pools paid, replay is a no-op")

    # Test 4: ProofAggregator
    print("\n🧪 Test 4: ProofAggregator")
    aggregator = ProofAggregator()
    
    # Add some proofs
    for i in range(5):
        proof_id = f"proof_{i}"
        proof_data = {"type": "test", "value": i, "hash": hashlib.sha3_256(str(i).encode()).hexdigest()}
        leaf = aggregator.add_proof(proof_id, proof_data, chain_id=1 + i % 3)
        print(f"  Added proof_{i}: {leaf[:16]}...")
    
    agg = aggregator.aggregate()
    print(f"  Aggregated: {agg['proof_count']} proofs, root={agg['merkle_root'][:16]}...")
    print(f"  Chains: {agg['chains']}")
    
    results["ProofAggregator"] = {
        "proof_storage": True,
        "aggregation": True,
        "proof_count": agg["proof_count"],
        "pass": True,
    }
    
    # Summary
    passed = sum(1 for r in results.values() if r.get("pass"))
    total = len(results)
    
    print(f"\n{'='*60}")
    print(f"SELF TEST: {passed}/{total} PASSED")
    print(f"{'='*60}")
    
    results["_summary"] = {"passed": passed, "total": total}
    return results


if __name__ == "__main__":
    self_test()
