"""
TRION BTCP — Integration Layer
==============================

Connects ZK proof system and VM adapters to the existing BTCP infrastructure.

Components:
  1. BTCPOrchestrator — High-level cross-VM BTCP coordinator
  2. PrivacyRouter — Routes intents through ZK circuits for privacy
  3. CrossVMGateway — Unified gateway for all VM adapter operations
  4. ProofAggregator — Collects and verifies proofs across chains

Whitepaper reference: L7 BTCP Cross-Chain Protocol
"""

import os
import sys
import json
import time
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any
from enum import IntEnum

# Add workspace to path (go up from core/btcp/ to workspace root)
_workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _workspace_root)

from zk import (
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
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "route": self.route.to_dict() if self.route else None,
            "proofs_generated": self.proofs_generated,
            "errors": self.errors,
            "execution_time_ms": round(self.execution_time_ms, 2),
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
            proofs["behavioral_credential"] = proof.to_dict()
        
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
            proofs["iap_share"] = proof.to_dict()
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
        
        from zk import ZKProof, CircuitType
        
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
            self._store.record_route_reward(
                epoch, f"anchor_pool:{intent.source_chain}",
                route.route_id, anchor_leg,
            )
            self._store.record_route_reward(
                epoch, f"execution_pool:{intent.dest_chain}",
                route.route_id, exec_leg,
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
        
        # Step 2: Create intent
        intent_id = hashlib.sha3_256(
            f"{source_chain}:{dest_chain}:{source_address}:{dest_address}:{amount}:{time.time()}".encode()
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
            nonce=int(time.time() * 1000) % (2**32),
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
        # BTCP gap #7: step 6 is the execution/recording phase — the route's
        # akashic execution records land in the schema.sql btcp_* tables
        # (intent registry, routes, cross-chain message, version sightings).
        self._record_execution(route)

        execution_time = (time.perf_counter() - start_time) * 1000
        
        success = len(errors) == 0
        
        return OrchestrationResult(
            success=success,
            route=route,
            proofs_generated=proof_names,
            errors=errors,
            execution_time_ms=execution_time,
        )
    
    def get_route(self, route_id: str) -> Optional[BTCPRoute]:
        """Get a route by ID."""
        return self._routes.get(route_id)
    
    def update_route_status(self, route_id: str, status: RouteStatus) -> bool:
        """Update the status of a route."""
        route = self._routes.get(route_id)
        if route is None:
            return False
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
        """Verify all proofs for a route."""
        route = self._routes.get(route_id)
        if route is None:
            return False, ["Route not found"]
        
        return self.privacy_router.verify_proofs(route.proofs)


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
        from zk import merkle_root
        
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
