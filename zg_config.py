"""
TRION 0G Network Configuration
Single source of truth for all 0G endpoints and contract addresses.
"""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class ZGConfig:
    # ── Network ───────────────────────────────────────────────────
    # Galileo testnet (chain 16602) — live contracts
    RPC      = os.getenv("ZG_RPC",     "https://evmrpc-testnet.0g.ai")
    INDEXER  = os.getenv("ZG_INDEXER", "https://indexer-storage-testnet-turbo.0g.ai")
    DA_RPC   = os.getenv("ZG_DA_RPC",  "http://localhost:51001")
    CHAIN_ID = int(os.getenv("ZG_CHAIN_ID", "16602"))
    NETWORK  = os.getenv("ZG_NETWORK", "testnet")

    # Newton testnet RPC (chain 16600) — AkashicProof contract
    NEWTON_RPC = os.getenv("ZG_NEWTON_RPC", "https://rpc-testnet.0g.ai")

    # ── Contracts ─────────────────────────────────────────────────
    # DA entrance on Galileo testnet
    DA_ENTRANCE = "0x857C0A28A8634614BB2C96039Cf4a20AFF709Aa9"
    DA_SIGNERS  = "0x0000000000000000000000000000000000001000"

    # AkashicProof — deployed on Newton testnet (16600)
    AKASHIC_PROOF_CONTRACT = os.getenv(
        "ZG_AKASHIC_CONTRACT",
        "0x33c793fed5bf5fcB043D8c6c74256e7B4b38156D"
    )

    # ExecutionGate — deployed on Galileo testnet (16602)
    EXECUTION_GATE = os.getenv(
        "ZG_EXECUTION_GATE_ADDR",
        "0xDB5910Dc6CfD219D00F64be1F23DA0289901356d"
    )

    # ── Keys ─────────────────────────────────────────────────────
    PRIVATE_KEY = os.getenv(
        "ZG_PRIVATE_KEY",
        os.getenv("DEPLOYER_PRIVATE_KEY",
        os.getenv("RELAYER_PRIVATE_KEY", ""))
    )

    # ── KV Stream IDs ─────────────────────────────────────────────
    KV_STREAM_SIGNALS  = "0x" + "TRION_SIGNALS".encode().hex().ljust(64, "0")
    KV_STREAM_ENTITIES = "0x" + "TRION_ENTITIES".encode().hex().ljust(64, "0")
    KV_STREAM_PLANES   = "0x" + "TRION_PLANES".encode().hex().ljust(64, "0")
    KV_STREAM_STATS    = "0x" + "TRION_STATS".encode().hex().ljust(64, "0")

    # ── Timing ────────────────────────────────────────────────────
    SYNC_INTERVAL_SECONDS = int(os.getenv("ZG_SYNC_INTERVAL", "3600"))  # 1 hour
    DA_INTERVAL_SECONDS   = int(os.getenv("ZG_DA_INTERVAL",   "60"))    # 1 minute
    KV_INTERVAL_SECONDS   = int(os.getenv("ZG_KV_INTERVAL",   "10"))    # 10 seconds

    # ── Paths ─────────────────────────────────────────────────────
    STATE_FILE  = "0g-state/sync_state.json"
    EXPORT_DIR  = "0g-state/exports"
    PROOFS_DIR  = "0g-state/proofs"
    LOGS_DIR    = "0g-state/logs"

    # ── Explorers ─────────────────────────────────────────────────
    STORAGE_EXPLORER = "https://storagescan.0g.ai"
    CHAIN_EXPLORER   = "https://chainscan-galileo.0g.ai"
    NEWTON_EXPLORER  = "https://chainscan-newton.0g.ai"
    COMPUTE_RPC      = os.getenv("ZG_COMPUTE_RPC", "https://compute-testnet.0g.ai")


ZG = ZGConfig()
