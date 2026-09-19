"""
TRION On-Chain Relay — Arbitrum Sepolia
Publishes behavioral truth signals to TRIONSensingOracle.sol using web3.py.
Reads live chain data for stats and signal verification.
"""
import os
import time
import hashlib
import logging
import threading
from typing import Optional

log = logging.getLogger("trion.chain")

try:
    from web3 import Web3
    from web3.middleware import ExtraDataToPOAMiddleware
    from eth_account import Account
    WEB3_OK = True
except ImportError:
    WEB3_OK = False
    log.warning("web3 not installed — chain features disabled")

# ── V3 BehavioralSignal struct (mirrors ITRIONOracleV3.BehavioralSignal) ─────
# Used by publishSignalWithType and publishBehavioralSignal. The 10 fields are:
#   entityId, publicCommitment, coherenceScore, threshold, moatFactor,
#   coherent, limitingPlane, planesPacked, timingPacked, initialized.
_BEHAVIORAL_SIGNAL_COMPONENTS = [
    {"name": "entityId",         "type": "bytes32"},
    {"name": "publicCommitment", "type": "bytes32"},
    {"name": "coherenceScore",   "type": "uint256"},
    {"name": "threshold",         "type": "uint256"},
    {"name": "moatFactor",        "type": "uint256"},
    {"name": "coherent",          "type": "bool"},
    {"name": "limitingPlane",     "type": "uint8"},
    {"name": "planesPacked",      "type": "uint256"},
    {"name": "timingPacked",      "type": "uint256"},
    {"name": "initialized",       "type": "bool"},
]

ORACLE_ABI = [
    {
        "inputs": [
            {"name": "entityId", "type": "bytes32"},
            {"name": "publicCommitment", "type": "bytes32"},
            {"name": "coherenceScore", "type": "uint256"},
            {"name": "threshold", "type": "uint256"},
            {"name": "coherent", "type": "bool"},
            {"name": "limitingPlane", "type": "uint8"}
        ],
        "name": "publishBehavioralTruth",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    # ── V3 canonical typed publication (TRION-TEAM-E) ────────────────────────
    # function publishSignalWithType(BehavioralSignal calldata s, uint8 signalType)
    # 13 conceptual args (10 struct fields + 5 plane scores packed into
    # planesPacked + signalType). The on-chain ABI takes the struct as a single
    # tuple arg followed by the signalType byte.
    {
        "inputs": [
            {
                "name": "s",
                "type": "tuple",
                "internalType": "struct ITRIONOracleV3.BehavioralSignal",
                "components": _BEHAVIORAL_SIGNAL_COMPONENTS,
            },
            {"name": "signalType", "type": "uint8", "internalType": "uint8"},
        ],
        "name": "publishSignalWithType",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {
                "name": "s",
                "type": "tuple",
                "internalType": "struct ITRIONOracleV3.BehavioralSignal",
                "components": _BEHAVIORAL_SIGNAL_COMPONENTS,
            },
        ],
        "name": "publishBehavioralSignal",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "entityId", "type": "bytes32"}],
        "name": "getSignalType",
        "outputs": [{"name": "signalType", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "", "type": "bytes32"}],
        "name": "signalTypeByEntity",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "", "type": "bytes32"}],
        "name": "signalCountByEntity",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "totalBehavioralSignals",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "v", "type": "address"}],
        "name": "addValidator",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "entityId", "type": "bytes32"}],
        "name": "getBehavioralSignal",
        "outputs": [
            {"name": "publicCommitment", "type": "bytes32"},
            {"name": "coherenceScore", "type": "uint256"},
            {"name": "threshold", "type": "uint256"},
            {"name": "moatFactor", "type": "uint256"},
            {"name": "coherent", "type": "bool"},
            {"name": "limitingPlane", "type": "uint8"},
            {"name": "initialized", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    # ── SignalTypeRecorded event (emitted by publishSignalWithType) ───────────
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "entityId",   "type": "bytes32"},
            {"indexed": False, "name": "signalType", "type": "uint8"},
        ],
        "name": "SignalTypeRecorded",
        "type": "event",
    },
    {
        "inputs": [],
        "name": "totalSignals",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "", "type": "bytes32"}],
        "name": "signalCount",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "entityId", "type": "bytes32"}],
        "name": "isCoherent",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "entityId", "type": "bytes32"}],
        "name": "getCoherenceDetail",
        "outputs": [
            {"name": "score", "type": "uint256"},
            {"name": "thresh", "type": "uint256"},
            {"name": "coherent", "type": "bool"},
            {"name": "plane", "type": "uint8"},
            {"name": "blk", "type": "uint256"},
            {"name": "fresh", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "", "type": "bytes32"}],
        "name": "latestSignal",
        "outputs": [
            {"name": "entityId", "type": "bytes32"},
            {"name": "publicCommitment", "type": "bytes32"},
            {"name": "coherenceScore", "type": "uint256"},
            {"name": "threshold", "type": "uint256"},
            {"name": "coherent", "type": "bool"},
            {"name": "limitingPlane", "type": "uint8"},
            {"name": "signalBlock", "type": "uint64"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "r", "type": "address"}, {"name": "auth", "type": "bool"}],
        "name": "setRelayer",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "owner",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "", "type": "address"}],
        "name": "authorizedRelayers",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "entityId",        "type": "bytes32"},
            {"indexed": False, "name": "publicCommitment", "type": "bytes32"},
            {"indexed": False, "name": "coherenceScore",   "type": "uint256"},
            {"indexed": False, "name": "threshold",        "type": "uint256"},
            {"indexed": False, "name": "coherent",         "type": "bool"},
            {"indexed": False, "name": "limitingPlane",    "type": "uint8"},
            {"indexed": False, "name": "blockNumber",      "type": "uint256"}
        ],
        "name": "BehavioralTruth",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "entityId",      "type": "bytes32"},
            {"indexed": False, "name": "coherenceScore", "type": "uint256"},
            {"indexed": False, "name": "threshold",      "type": "uint256"},
            {"indexed": False, "name": "limitingPlane",  "type": "uint8"},
            {"indexed": False, "name": "coherenceGap",   "type": "uint256"}
        ],
        "name": "SilenceSignal",
        "type": "event"
    },
    {
        "inputs": [
            {"name": "entityId", "type": "bytes32"},
            {"name": "publicCommitment", "type": "bytes32"},
            {"name": "coherenceScore", "type": "uint256"},
            {"name": "threshold", "type": "uint256"},
            {"name": "moatFactor", "type": "uint256"},
            {"name": "coherent", "type": "bool"},
            {"name": "limitingPlane", "type": "uint8"},
            {"name": "phiPlane", "type": "uint64"},
            {"name": "mentalPlane", "type": "uint64"},
            {"name": "sigmaPlane", "type": "uint64"},
            {"name": "consciousPlane", "type": "uint64"},
            {"name": "animaPlane", "type": "uint64"}
        ],
        "name": "publishBehavioralSignalLegacy12",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "entityId", "type": "bytes32"},
            {"indexed": False, "name": "publicCommitment", "type": "bytes32"},
            {"indexed": False, "name": "coherenceScore", "type": "uint256"},
            {"indexed": False, "name": "threshold", "type": "uint256"},
            {"indexed": False, "name": "moatFactor", "type": "uint256"},
            {"indexed": False, "name": "coherent", "type": "bool"},
            {"indexed": False, "name": "limitingPlane", "type": "uint8"},
            {"indexed": False, "name": "phiPlane", "type": "uint64"},
            {"indexed": False, "name": "mentalPlane", "type": "uint64"},
            {"indexed": False, "name": "sigmaPlane", "type": "uint64"},
            {"indexed": False, "name": "consciousPlane", "type": "uint64"},
            {"indexed": False, "name": "animaPlane", "type": "uint64"},
            {"indexed": False, "name": "signalBlock", "type": "uint64"},
            {"indexed": False, "name": "signalTimestamp", "type": "uint64"}
        ],
        "name": "BehavioralSignalPublished",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "entityId", "type": "bytes32"},
            {"indexed": False, "name": "coherenceScore", "type": "uint256"},
            {"indexed": False, "name": "threshold", "type": "uint256"},
            {"indexed": False, "name": "limitingPlane", "type": "uint8"},
            {"indexed": False, "name": "coherenceGap", "type": "uint256"},
            {"indexed": False, "name": "signalBlock", "type": "uint64"}
        ],
        "name": "SilenceRecorded",
        "type": "event"
    }
]

ARBISCAN_TX = "https://sepolia.arbiscan.io/tx/{}"
ARBISCAN_ADDR = "https://sepolia.arbiscan.io/address/{}"

class ChainRelay:
    """Singleton blockchain relay for TRION oracle."""

    def __init__(self):
        self._w3: Optional[object] = None
        self._oracle = None
        self._account = None
        self._lock = threading.Lock()
        self._init()

    def _init(self):
        if not WEB3_OK:
            return
        # Prefer ETH_SEPOLIA_RPC (canonical V3 deployment target) when set;
        # fall back to the legacy ARB_SEPOLIA_RPC env name for backward compat.
        rpc = (
            os.environ.get("ETH_SEPOLIA_RPC")
            or os.environ.get("ARB_SEPOLIA_RPC")
            or "https://ethereum-sepolia.publicnode.com"
        )
        pk  = os.environ.get("PRIVATE_KEY", "") or os.environ.get("RELAYER_PRIVATE_KEY", "")
        # Canonical V3 deployment on Ethereum Sepolia (recompiled with
        # publishSignalWithType on 2026-09-19 — see proof-ledger/first_signal.json
        # tx 0x96a42a2ca4a1df918df90b5820cdfbd83de89ab27ce53e1673dd86fcec7c6db9).
        # The previous default (0x1d129D3…4237) targeted the OLD TRIONSensingOracle
        # on Arbitrum Sepolia which only exposed publishBehavioralTruth (6-arg).
        oracle_addr = os.environ.get(
            "ORACLE_ADDRESS",
            "0x590CD9B5ad34b735d8c262a462d9bc82E57C4DA5",
        )

        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 20}))
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            if not w3.is_connected():
                log.error("Chain RPC not reachable: %s", rpc)
                return
            self._w3 = w3
            if pk:
                self._account = Account.from_key(pk)
                log.info("Chain relay ready: %s on chainId %s", self._account.address, w3.eth.chain_id)
            oracle_addr = Web3.to_checksum_address(oracle_addr)
            self._oracle = w3.eth.contract(address=oracle_addr, abi=ORACLE_ABI)
            log.info("Oracle contract: %s", oracle_addr)
        except Exception as e:
            log.error("Chain init failed: %s", e)

    @property
    def ready(self) -> bool:
        return self._w3 is not None and self._oracle is not None and self._account is not None

    def _entity_to_bytes32(self, entity_id: str) -> bytes:
        """Convert entity_id string to bytes32.

        Canonical SHA3-256 (SEC-20): the behavioral-hash pipeline
        (core/primitives/behavioral_hash.py, trion-common hash_dna) is
        SHA3-256 everywhere — the on-chain oracle entity id must key to
        the same identity, not a SHA-256 shadow that matches no BEO
        ledger entry.
        """
        raw = entity_id.encode()
        h = hashlib.sha3_256(raw).digest()
        return h

    def _commitment(self, entity_id: str, score: float, ts: int) -> bytes:
        """Generate public commitment hash (no behavior content).

        SHA3-256 for the same canonical-alignment reason as
        _entity_to_bytes32 (SEC-20).
        """
        payload = f"{entity_id}:{score:.6f}:{ts // 300}".encode()
        return hashlib.sha3_256(payload).digest()

    def _plane_index(self, plane_name: str) -> int:
        mapping = {"Physical": 0, "Mental": 1, "Spiritual": 2, "Conscious": 3, "ANIMA": 4}
        return mapping.get(plane_name, 0)

    def publish_signal(self, entity_id: str, score: float, threshold: float,
                       coherent: bool, limiting_plane: str) -> dict:
        """
        Publish behavioral truth signal on-chain via TRIONSensingOracle.
        Returns dict with tx_hash, arbiscan_url, block_number, or error.

        Builds the 6-arg publishBehavioralTruth call (entityId, commitment,
        score, threshold, coherent, plane index) exactly as the ORACLE_ABI
        specifies.
        """
        if not self.ready:
            return {"error": "chain_not_ready", "published": False}

        with self._lock:
            try:
                ts = int(time.time())
                eid_b32     = self._entity_to_bytes32(entity_id)
                commit_b32  = self._commitment(entity_id, score, ts)
                score_int   = int(score * 1_000_000)
                thresh_int  = int(threshold * 1_000_000)
                plane_idx   = self._plane_index(limiting_plane)

                nonce = self._w3.eth.get_transaction_count(self._account.address)
                gas_price = self._w3.eth.gas_price
                gas_price_bumped = int(gas_price * 1.2)

                tx = self._oracle.functions.publishBehavioralTruth(
                    eid_b32, commit_b32, score_int, thresh_int,
                    coherent, plane_idx
                ).build_transaction({
                    "from":     self._account.address,
                    "nonce":    nonce,
                    "gas":      200_000,
                    "gasPrice": gas_price_bumped,
                    "chainId":  self._w3.eth.chain_id,
                })

                signed = self._account.sign_transaction(tx)
                tx_hash = self._w3.eth.send_raw_transaction(signed.rawTransaction)
                tx_hex = tx_hash.hex()

                log.info("TX sent: %s entity=%s coherent=%s", tx_hex, entity_id[:18], coherent)
                return {
                    "published":     True,
                    "tx_hash":       tx_hex,
                    "arbiscan_url":  ARBISCAN_TX.format(tx_hex),
                    "timestamp":     ts,
                    "score_on_chain": score_int,
                    "threshold_on_chain": thresh_int,
                }
            except Exception as e:
                log.error("publish_signal error: %s", e)
                return {"error": str(e), "published": False}

    @staticmethod
    def _pack_planes(phi_plane: int, mental_plane: int, sigma_plane: int,
                     conscious_plane: int, anima_plane: int) -> int:
        """
        Pack five plane scores (×1e6) into one uint256 (32 bits each).

        Mirrors TRIONOracleV3.packPlanes():
            planesPacked = phi | (mental << 32) | (sigma << 64)
                         | (conscious << 96) | (anima << 128)
        """
        return (
            (int(phi_plane)       & 0xFFFFFFFF)
            | ((int(mental_plane)     & 0xFFFFFFFF) << 32)
            | ((int(sigma_plane)      & 0xFFFFFFFF) << 64)
            | ((int(conscious_plane)  & 0xFFFFFFFF) << 96)
            | ((int(anima_plane)      & 0xFFFFFFFF) << 128)
        )

    def _build_behavioral_signal_tuple(self,
            entity_b32: bytes,
            commitment: bytes,
            coherence_score: int,
            threshold: int,
            moat_factor: int,
            coherent: bool,
            limiting_plane: int,
            phi_plane: int = 0,
            mental_plane: int = 0,
            sigma_plane: int = 0,
            conscious_plane: int = 0,
            anima_plane: int = 0) -> tuple:
        """
        Build the on-chain BehavioralSignal tuple (10 fields).

        Solidity struct:
            struct BehavioralSignal {
                bytes32 entityId;
                bytes32 publicCommitment;
                uint256 coherenceScore;
                uint256 threshold;
                uint256 moatFactor;
                bool    coherent;
                uint8   limitingPlane;
                uint256 planesPacked;     // 5 planes × 32 bits
                uint256 timingPacked;    // (block << 64) | timestamp
                bool    initialized;
            }

        timingPacked and initialized are overwritten by the contract itself
        in `_publishBehavioralSignal` (sig.timingPacked = (block.number << 64)
        | block.timestamp; sig.initialized = true). We pass zeros here.
        """
        planes_packed = self._pack_planes(
            phi_plane, mental_plane, sigma_plane, conscious_plane, anima_plane,
        )
        return (
            entity_b32,         # bytes32 entityId
            commitment,         # bytes32 publicCommitment
            int(coherence_score),
            int(threshold),
            int(moat_factor),
            bool(coherent),
            int(limiting_plane) & 0xFF,
            planes_packed,
            0,                  # timingPacked — set by the contract
            False,              # initialized  — set by the contract
        )

    def publish_behavioral_signal_v3(self,
            entity_b32: bytes,
            commitment: bytes,
            coherence_score: int,
            threshold: int,
            moat_factor: int,
            coherent: bool,
            limiting_plane: int,
            phi_plane: int = 0,
            mental_plane: int = 0,
            sigma_plane: int = 0,
            conscious_plane: int = 0,
            anima_plane: int = 0) -> dict:
        """
        Publish a full behavioral signal via TRIONOracleV3.publishBehavioralSignal().
        Rich format with entity ID, commitment, moat, and all 5 planes packed
        into the on-chain BehavioralSignal struct (tuple).
        """
        if not self.ready:
            return {"error": "chain_not_ready", "published": False}
        try:
            with self._lock:
                sig_tuple = self._build_behavioral_signal_tuple(
                    entity_b32, commitment, coherence_score, threshold,
                    moat_factor, coherent, limiting_plane,
                    phi_plane, mental_plane, sigma_plane,
                    conscious_plane, anima_plane,
                )
                nonce = self._w3.eth.get_transaction_count(self._account.address)
                tx = self._oracle.functions.publishBehavioralSignal(
                    sig_tuple,
                ).build_transaction({
                    "from": self._account.address,
                    "nonce": nonce,
                    "gas": 300000,
                    "maxFeePerGas": self._w3.to_wei("0.1", "gwei"),
                    "maxPriorityFeePerGas": self._w3.to_wei("0.01", "gwei"),
                })
                signed = self._account.sign_transaction(tx)
                tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
                receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
                return {
                    "published": True,
                    "tx_hash": tx_hash.hex(),
                    "block_number": receipt["blockNumber"],
                    "status": receipt["status"],
                    "gas_used": receipt["gasUsed"],
                    "method": "publishBehavioralSignal",
                }
        except Exception as e:
            log.error("V3 publish failed: %s", e)
            return {"error": str(e), "published": False}

    def record_silence(self,
            entity_b32: bytes,
            coherence_score: int,
            threshold: int,
            limiting_plane: int,
            signal_type_id: int = 1) -> dict:
        """
        Record SILENCE on-chain when C(t) < Θ(t).
        Uses publishSignalWithType with coherent=False — contract emits both
        BehavioralSignalPublished AND SilenceRecorded (V1 + V2) AND
        SignalTypeRecorded so the canonical 24-type taxonomy carries through
        even on silence.
        """
        if not self.ready:
            return {"error": "chain_not_ready", "published": False}
        try:
            with self._lock:
                sig_tuple = self._build_behavioral_signal_tuple(
                    entity_b32=entity_b32,
                    commitment=b"\x00" * 32,  # zero commitment for silence
                    coherence_score=coherence_score,
                    threshold=threshold,
                    moat_factor=0,
                    coherent=False,
                    limiting_plane=limiting_plane,
                )
                nonce = self._w3.eth.get_transaction_count(self._account.address)
                tx = self._oracle.functions.publishSignalWithType(
                    sig_tuple, int(signal_type_id) & 0xFF,
                ).build_transaction({
                    "from": self._account.address,
                    "nonce": nonce,
                    "gas": 300000,
                    "maxFeePerGas": self._w3.to_wei("0.1", "gwei"),
                    "maxPriorityFeePerGas": self._w3.to_wei("0.01", "gwei"),
                })
                signed = self._account.sign_transaction(tx)
                tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
                receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
                return {
                    "published": True,
                    "tx_hash": tx_hash.hex(),
                    "block_number": receipt["blockNumber"],
                    "status": receipt["status"],
                    "gas_used": receipt["gasUsed"],
                    "method": "publishSignalWithType (SILENCE)",
                }
        except Exception as e:
            log.error("Silence recording failed: %s", e)
            return {"error": str(e), "published": False}

    # ── publishSignalWithType (canonical V3 typed emission, gap #5 fixed) ──────
    # The V3 contract exposes publishSignalWithType(BehavioralSignal, uint8)
    # which performs the rich behavioral-signal write AND records the canonical
    # 24-member signal type (0..23) on-chain in a single transaction.
    # Spec-faithful: callers no longer pack the type into the high byte of
    # `threshold` — the type byte is a dedicated on-chain field now.
    _TYPED_SIGNAL_SILENCE_FAMILY = {
        "SILENCE", "BOOTSTRAP", "GENESIS",
    }

    @staticmethod
    def _resolve_signal_type_id(signal_type: str) -> int:
        """Return the canonical 0..23 SignalType enum value for *signal_type*.

        Falls back to 0 (VALUATION) if the name is not in the registry.
        """
        try:
            from core.master.signal_factory import SignalType
            return int(SignalType[signal_type])
        except Exception:
            return 0  # VALUATION is the canonical default carrier

    def publishSignalWithType(self,
            entity_b32: bytes,
            signal_type: str,
            commitment: bytes,
            coherence_score: int,
            threshold: int,
            moat_factor: int,
            coherent: bool,
            limiting_plane: int,
            phi_plane: int = 0,
            mental_plane: int = 0,
            sigma_plane: int = 0,
            conscious_plane: int = 0,
            anima_plane: int = 0) -> dict:
        """
        Canonical V3 typed emission.

        Invokes TRIONOracleV3.publishSignalWithType(BehavioralSignal, uint8)
        with the signal type carried in the dedicated on-chain signalType field
        (NOT packed into the threshold high byte — the old gap-#5 workaround).

        - SILENCE family / non-coherent → publishSignalWithType with
          coherent=False (contract emits BehavioralSignalPublished +
          SilenceRecorded V1+V2 + SignalTypeRecorded).
        - VALUATION and all other 24 types → publishSignalWithType with
          coherent=True and the type byte set verbatim.

        Returns the chain receipt with `signal_type`, `signal_type_id`, and
        `method` fields added for downstream consumers.
        """
        sig_id = self._resolve_signal_type_id(signal_type)

        if not self.ready:
            return {
                "error": "chain_not_ready",
                "published": False,
                "signal_type": signal_type,
                "signal_type_id": sig_id,
            }
        try:
            with self._lock:
                sig_tuple = self._build_behavioral_signal_tuple(
                    entity_b32=entity_b32,
                    commitment=commitment,
                    coherence_score=coherence_score,
                    threshold=threshold,
                    moat_factor=moat_factor,
                    coherent=coherent,
                    limiting_plane=limiting_plane,
                    phi_plane=phi_plane,
                    mental_plane=mental_plane,
                    sigma_plane=sigma_plane,
                    conscious_plane=conscious_plane,
                    anima_plane=anima_plane,
                )
                nonce = self._w3.eth.get_transaction_count(self._account.address)
                tx = self._oracle.functions.publishSignalWithType(
                    sig_tuple, int(sig_id) & 0xFF,
                ).build_transaction({
                    "from": self._account.address,
                    "nonce": nonce,
                    "gas": 350000,
                    "maxFeePerGas": self._w3.to_wei("0.1", "gwei"),
                    "maxPriorityFeePerGas": self._w3.to_wei("0.01", "gwei"),
                })
                signed = self._account.sign_transaction(tx)
                tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
                receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                return {
                    "published":       True,
                    "tx_hash":         tx_hash.hex(),
                    "block_number":    receipt["blockNumber"],
                    "status":          receipt["status"],
                    "gas_used":        receipt["gasUsed"],
                    "method":          "publishSignalWithType",
                    "signal_type":     signal_type,
                    "signal_type_id":  sig_id,
                    "coherent":        coherent,
                }
        except Exception as e:
            log.error("publishSignalWithType failed: %s", e)
            return {
                "error":           str(e),
                "published":       False,
                "signal_type":     signal_type,
                "signal_type_id":  sig_id,
            }

    # ── snake_case alias consumed by api/app.py `/api/v1/publish` ─────────────
    def publish_signal_with_type(self,
            entity_id: str,
            signal_type: str,
            coherence_score: float,
            threshold: float,
            moat_factor: float,
            coherent: bool,
            limiting_plane: str,
            phi_plane: float = 0.0,
            mental_plane: float = 0.0,
            sigma_plane: float = 0.0,
            conscious_plane: float = 0.0,
            anima_plane: float = 0.0) -> dict:
        """
        V3 typed emission entry point — converts the float-domain API inputs
        into the integer-domain on-chain args and invokes the contract's
        publishSignalWithType(BehavioralSignal, uint8).

        Args (13 conceptual fields):
            entity_id        str     canonical entity key (hashed to bytes32)
            signal_type      str     SignalType enum name (e.g. "VALUATION")
            coherence_score  float   C(t) ∈ [0,1]   — encoded ×1e6
            threshold        float   Θ(t) ∈ [0,1]   — encoded ×1e6
            moat_factor      float   M_moat ∈ [0,1] — encoded ×1e6
            coherent         bool    C(t) ≥ Θ(t)
            limiting_plane   str     Physical/Mental/Spiritual/Conscious/ANIMA
            phi_plane        float   Φ  score ∈ [0,1] — encoded ×1e6
            mental_plane     float   M  score ∈ [0,1] — encoded ×1e6
            sigma_plane      float   Σ  score ∈ [0,1] — encoded ×1e6
            conscious_plane  float   K  score ∈ [0,1] — encoded ×1e6
            anima_plane      float   A  score ∈ [0,1] — encoded ×1e6

        Returns: chain receipt dict (see publishSignalWithType).
        """
        SCALE = 1_000_000
        ts = int(time.time())
        entity_b32 = self._entity_to_bytes32(entity_id)
        commitment = self._commitment(entity_id, coherence_score, ts)
        return self.publishSignalWithType(
            entity_b32=entity_b32,
            signal_type=signal_type,
            commitment=commitment,
            coherence_score=int(round(coherence_score * SCALE)),
            threshold=int(round(threshold * SCALE)),
            moat_factor=int(round(moat_factor * SCALE)),
            coherent=coherent,
            limiting_plane=self._plane_index(limiting_plane),
            phi_plane=int(round(phi_plane * SCALE)),
            mental_plane=int(round(mental_plane * SCALE)),
            sigma_plane=int(round(sigma_plane * SCALE)),
            conscious_plane=int(round(conscious_plane * SCALE)),
            anima_plane=int(round(anima_plane * SCALE)),
        )

    def get_behavioral_signal(self, entity_b32: bytes) -> dict:
        """Read a behavioral signal from the V3 oracle contract.

        Mirrors TRIONOracleV3.getBehavioralSignal(bytes32) → returns the
        7-tuple (publicCommitment, coherenceScore, threshold, moatFactor,
        coherent, limitingPlane, initialized). The plane breakdown is
        retrievable via a separate getBehavioralSignalPlanes() call (when
        the caller needs it).
        """
        if not self.ready:
            return {"error": "chain_not_ready"}
        try:
            result = self._oracle.functions.getBehavioralSignal(entity_b32).call()
            return {
                "public_commitment": result[0].hex(),
                "coherence_score":  result[1],
                "threshold":         result[2],
                "moat_factor":       result[3],
                "coherent":          result[4],
                "limiting_plane":    result[5],
                "initialized":       result[6],
            }
        except Exception as e:
            return {"error": str(e)}

    def get_signal_type_on_chain(self, entity_b32: bytes) -> int:
        """Read the canonical 0..23 signal type recorded for *entity_b32*.

        Returns -1 if the contract is unreachable; 0 (VALUATION) is the
        default value when no signal has been published for the entity yet.
        """
        if not self.ready:
            return -1
        try:
            return int(self._oracle.functions.getSignalType(entity_b32).call())
        except Exception as e:
            log.error("getSignalType error: %s", e)
            return -1

    def get_chain_stats(self) -> dict:
        """Read live stats from the oracle contract.

        Prefers the V3 `totalBehavioralSignals()` view (typed-emission
        counter); falls back to the legacy `totalSignals()` view when the
        deployed contract predates the V3 ABI.
        """
        if not self.ready:
            return {"total_signals": 0, "chain_ok": False}
        try:
            total = None
            try:
                total = self._oracle.functions.totalBehavioralSignals().call()
            except Exception:
                total = None
            if total is None:
                total = self._oracle.functions.totalSignals().call()
            block = self._w3.eth.block_number
            return {
                "total_signals": total,
                "block_number":  block,
                "chain_ok":      True,
            }
        except Exception as e:
            log.error("get_chain_stats error: %s", e)
            return {"total_signals": 0, "chain_ok": False, "error": str(e)}

    def get_entity_on_chain(self, entity_id: str) -> dict:
        """Read the latest on-chain signal for an entity."""
        if not self.ready:
            return {"found": False}
        try:
            eid_b32 = self._entity_to_bytes32(entity_id)
            detail = self._oracle.functions.getCoherenceDetail(eid_b32).call()
            score, thresh, coherent, plane, blk, fresh = detail
            if blk == 0:
                return {"found": False}
            count = self._oracle.functions.signalCount(eid_b32).call()
            return {
                "found":           True,
                "coherence_score": score / 1_000_000,
                "threshold":       thresh / 1_000_000,
                "coherent":        coherent,
                "limiting_plane":  ["Physical","Mental","Spiritual","Conscious","ANIMA"][plane],
                "signal_block":    blk,
                "is_fresh":        fresh,
                "signal_count":    count,
                "arbiscan_contract": ARBISCAN_ADDR.format(
                    os.environ.get(
                        "ORACLE_ADDRESS",
                        "0x590CD9B5ad34b735d8c262a462d9bc82E57C4DA5",
                    )
                ),
            }
        except Exception as e:
            log.error("get_entity_on_chain error: %s", e)
            return {"found": False, "error": str(e)}

    def get_recent_events(self, limit: int = 10) -> list:
        """Fetch recent BehavioralTruth + SilenceSignal events from the oracle."""
        if not self.ready:
            return []
        PLANES = ["Physical", "Mental", "Spiritual", "Conscious", "ANIMA"]
        try:
            latest = self._w3.eth.block_number
            from_block = max(0, latest - 100_000)
            all_events = []

            # Coherent signals
            try:
                bt_events = self._oracle.events.BehavioralTruth.get_logs(
                    from_block=from_block, to_block=latest
                )
                for e in bt_events:
                    eid_hex = "0x" + e["args"]["entityId"].hex()
                    plane_idx = e["args"]["limitingPlane"]
                    blk = e.blockNumber
                    all_events.append({
                        "entity_id":       eid_hex,
                        "short_id":        eid_hex[:12] + "…",
                        "coherence_score": e["args"]["coherenceScore"] / 1_000_000,
                        "threshold":       e["args"]["threshold"] / 1_000_000,
                        "coherent":        True,
                        "limiting_plane":  PLANES[plane_idx] if plane_idx < len(PLANES) else "Unknown",
                        "block_number":    blk,
                        "tx_hash":         e.transactionHash.hex(),
                        "arbiscan_url":    ARBISCAN_TX.format(e.transactionHash.hex()),
                        "on_chain":        True,
                        "timestamp":       int(time.time()) - max(0, (latest - blk)) * 1,
                    })
            except Exception as ex:
                log.warning("BehavioralTruth fetch error: %s", ex)

            # Non-coherent signals (SilenceSignal)
            try:
                ss_events = self._oracle.events.SilenceSignal.get_logs(
                    from_block=from_block, to_block=latest
                )
                for e in ss_events:
                    eid_hex = "0x" + e["args"]["entityId"].hex()
                    plane_idx = e["args"]["limitingPlane"]
                    blk = e.blockNumber
                    all_events.append({
                        "entity_id":       eid_hex,
                        "short_id":        eid_hex[:12] + "…",
                        "coherence_score": e["args"]["coherenceScore"] / 1_000_000,
                        "threshold":       e["args"]["threshold"] / 1_000_000,
                        "coherent":        False,
                        "limiting_plane":  PLANES[plane_idx] if plane_idx < len(PLANES) else "Unknown",
                        "block_number":    blk,
                        "tx_hash":         e.transactionHash.hex(),
                        "arbiscan_url":    ARBISCAN_TX.format(e.transactionHash.hex()),
                        "on_chain":        True,
                        "timestamp":       int(time.time()) - max(0, (latest - blk)) * 1,
                    })
            except Exception as ex:
                log.warning("SilenceSignal fetch error: %s", ex)

            # Sort newest first
            all_events.sort(key=lambda x: x["block_number"], reverse=True)
            return all_events[:limit]

        except Exception as e:
            log.error("get_recent_events error: %s", e)
            return []


_relay: Optional[ChainRelay] = None
_relay_lock = threading.Lock()

def get_relay() -> ChainRelay:
    global _relay
    if _relay is None:
        with _relay_lock:
            if _relay is None:
                _relay = ChainRelay()
    return _relay
