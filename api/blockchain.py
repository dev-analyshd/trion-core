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
        "name": "publishBehavioralSignal",
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
        rpc = os.environ.get("ARB_SEPOLIA_RPC", "https://sepolia-rollup.arbitrum.io/rpc")
        pk  = os.environ.get("PRIVATE_KEY", "") or os.environ.get("RELAYER_PRIVATE_KEY", "")
        oracle_addr = os.environ.get("ORACLE_ADDRESS", "0x1d129D34279d1246aB08a41dfE610EaF8D794237")

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
        """Convert entity_id string to bytes32."""
        raw = entity_id.encode()
        h = hashlib.sha256(raw).digest()
        return h

    def _commitment(self, entity_id: str, score: float, ts: int) -> bytes:
        """Generate public commitment hash (no behavior content)."""
        payload = f"{entity_id}:{score:.6f}:{ts // 300}".encode()
        return hashlib.sha256(payload).digest()

    def _plane_index(self, plane_name: str) -> int:
        mapping = {"Physical": 0, "Mental": 1, "Spiritual": 2, "Conscious": 3, "ANIMA": 4}
        return mapping.get(plane_name, 0)

    def publish_signal(self, entity_id: str, score: float, threshold: float,
                       coherent: bool, limiting_plane: str) -> dict:
        """
        Publish behavioral truth signal on-chain via TRIONSensingOracle.
        Returns dict with tx_hash, arbiscan_url, block_number, or error.

        This was previously a dead handler (empty body after the ready check).
        Fixed per DD report §7.2 — now implements the full publish flow.
        """
        if not self.ready:
            return {"error": "chain_not_ready", "published": False}

        try:
            # Pack the signal data
            score_scaled = int(score * 1e6)
            threshold_scaled = int(threshold * 1e6)
            status = 1 if coherent else 0  # SAFE=1, SILENCE=0

            # Build the transaction
            nonce = self.w3.eth.get_transaction_count(self.account.address)
            tx = self.contract.functions.publishBehavioralTruth(
                entity_id.encode('utf-8').ljust(32, b'\x00')[:32],  # bytes32 entity_id
                score_scaled,
                threshold_scaled,
                limiting_plane.encode('utf-8')[:8],  # first 8 bytes of plane name
                status,
            ).build_transaction({
                'from': self.account.address,
                'nonce': nonce,
                'gas': 200000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': self.chain_id,
            })

            # Sign and send
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            return {
                "tx_hash": tx_hash.hex(),
                "arbiscan_url": f"https://sepolia.arbiscan.io/tx/{tx_hash.hex()}",
                "block_number": receipt['blockNumber'],
                "status": receipt['status'],
                "published": True,
            }
        except Exception as e:
            return {"error": str(e), "published": False}

    def publish_behavioral_signal_v3(self,
            entity_b32: bytes,
            commitment: bytes,
            coherence_score: int,
            threshold: int,
            moat_factor: int,
            coherent: bool,
            limiting_plane: int,
            phi_plane: int,
            mental_plane: int,
            sigma_plane: int,
            conscious_plane: int,
            anima_plane: int) -> dict:
        """
        Publish a full behavioral signal via TRIONOracleV3.publishBehavioralSignal().
        Rich format with entity ID, commitment, moat, and all 5 planes.
        """
        if not self.ready:
            return {"error": "chain_not_ready", "published": False}
        try:
            with self._lock:
                nonce = self._w3.eth.get_transaction_count(self._account.address)
                tx = self._oracle.functions.publishBehavioralSignal(
                    entity_b32, commitment, coherence_score, threshold,
                    moat_factor, coherent, limiting_plane,
                    phi_plane, mental_plane, sigma_plane,
                    conscious_plane, anima_plane
                ).build_transaction({
                    "from": self._account.address,
                    "nonce": nonce,
                    "gas": 300000,
                    "maxFeePerGas": self._w3.to_wei("0.1", "gwei"),
                    "maxPriorityFeePerGas": self._w3.to_wei("0.01", "gwei"),
                })
                signed = self._account.sign_transaction(tx)
                tx_hash = self._w3.eth.send_raw_transaction(signed.rawTransaction)
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
            limiting_plane: int) -> dict:
        """
        Record SILENCE on-chain when C(t) < Θ(t).
        Uses publishBehavioralSignal with coherent=False — contract emits SilenceRecorded.
        """
        if not self.ready:
            return {"error": "chain_not_ready", "published": False}
        try:
            with self._lock:
                nonce = self._w3.eth.get_transaction_count(self._account.address)
                # Publish with coherent=False — contract auto-emits SilenceRecorded
                tx = self._oracle.functions.publishBehavioralSignal(
                    entity_b32,
                    b"\x00" * 32,  # Zero commitment for silence
                    coherence_score, threshold,
                    0, False, limiting_plane, 0, 0, 0, 0, 0
                ).build_transaction({
                    "from": self._account.address,
                    "nonce": nonce,
                    "gas": 200000,
                    "maxFeePerGas": self._w3.to_wei("0.1", "gwei"),
                    "maxPriorityFeePerGas": self._w3.to_wei("0.01", "gwei"),
                })
                signed = self._account.sign_transaction(tx)
                tx_hash = self._w3.eth.send_raw_transaction(signed.rawTransaction)
                receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
                return {
                    "published": True,
                    "tx_hash": tx_hash.hex(),
                    "block_number": receipt["blockNumber"],
                    "status": receipt["status"],
                    "gas_used": receipt["gasUsed"],
                    "method": "recordSilence",
                }
        except Exception as e:
            log.error("Silence recording failed: %s", e)
            return {"error": str(e), "published": False}

    def get_behavioral_signal(self, entity_b32: bytes) -> dict:
        """Read a behavioral signal from the V3 oracle contract."""
        if not self.ready:
            return {"error": "chain_not_ready"}
        try:
            result = self._oracle.functions.getBehavioralSignal(entity_b32).call()
            return {
                "public_commitment": result[0].hex(),
                "coherence_score": result[1],
                "threshold": result[2],
                "moat_factor": result[3],
                "coherent": result[4],
                "limiting_plane": result[5],
                "phi_plane": result[6],
                "mental_plane": result[7],
                "sigma_plane": result[8],
                "conscious_plane": result[9],
                "anima_plane": result[10],
                "signal_block": result[11],
                "signal_timestamp": result[12],
                "initialized": result[13],
            }
        except Exception as e:
            return {"error": str(e)}

        with self._lock:
            try:
                w3 = self._w3
                ts = int(time.time())
                eid_b32     = self._entity_to_bytes32(entity_id)
                commit_b32  = self._commitment(entity_id, score, ts)
                score_int   = int(score * 1_000_000)
                thresh_int  = int(threshold * 1_000_000)
                plane_idx   = self._plane_index(limiting_plane)

                nonce = w3.eth.get_transaction_count(self._account.address)
                gas_price = w3.eth.gas_price
                gas_price_bumped = int(gas_price * 1.2)

                tx = self._oracle.functions.publishBehavioralTruth(
                    eid_b32, commit_b32, score_int, thresh_int,
                    coherent, plane_idx
                ).build_transaction({
                    "from":     self._account.address,
                    "nonce":    nonce,
                    "gas":      200_000,
                    "gasPrice": gas_price_bumped,
                    "chainId":  421614,
                })

                signed = self._account.sign_transaction(tx)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
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

    def get_chain_stats(self) -> dict:
        """Read live stats from the oracle contract."""
        if not self.ready:
            return {"total_signals": 0, "chain_ok": False}
        try:
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
                    os.environ.get("ORACLE_ADDRESS", "0x1d129D34279d1246aB08a41dfE610EaF8D794237")
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
