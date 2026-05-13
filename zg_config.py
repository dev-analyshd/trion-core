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
    RPC     = os.getenv("ZG_RPC", "https://evmrpc-testnet.0g.ai")
    INDEXER = os.getenv("ZG_INDEXER",
              "https://indexer-storage-testnet-turbo.0g.ai")
    DA_RPC  = os.getenv("ZG_DA_RPC", "http://localhost:51001")
    CHAIN_ID = int(os.getenv("ZG_CHAIN_ID", "16602"))  # 0G testnet EVM actual chain ID
    NETWORK  = os.getenv("ZG_NETWORK", "testnet")

    # ── Contracts (testnet) ───────────────────────────────────────
    DA_ENTRANCE = "0x857C0A28A8634614BB2C96039Cf4a20AFF709Aa9"
    DA_SIGNERS  = "0x0000000000000000000000000000000000001000"

    AKASHIC_PROOF_CONTRACT = os.getenv("ZG_AKASHIC_CONTRACT", "")

    # ── Keys ─────────────────────────────────────────────────────
    PRIVATE_KEY = os.getenv("ZG_PRIVATE_KEY",
                  os.getenv("DEPLOYER_PRIVATE_KEY", ""))

    # ── KV Stream IDs (fixed per TRION deployment) ────────────────
    KV_STREAM_SIGNALS  = "0x" + "TRION_SIGNALS".encode().hex().ljust(64, "0")
    KV_STREAM_ENTITIES = "0x" + "TRION_ENTITIES".encode().hex().ljust(64, "0")
    KV_STREAM_PLANES   = "0x" + "TRION_PLANES".encode().hex().ljust(64, "0")
    KV_STREAM_STATS    = "0x" + "TRION_STATS".encode().hex().ljust(64, "0")

    # ── Sync settings ─────────────────────────────────────────────
    SYNC_INTERVAL_SECONDS = 3600   # 1 hour full sync
    DA_INTERVAL_SECONDS   = 60     # 1 minute DA submission
    KV_INTERVAL_SECONDS   = 10     # 10 second KV updates

    # ── Paths ────────────────────────────────────────────────────
    STATE_FILE  = "0g-state/sync_state.json"
    EXPORT_DIR  = "0g-state/exports"
    PROOFS_DIR  = "0g-state/proofs"
    LOGS_DIR    = "0g-state/logs"

    # ── Explorer URLs ────────────────────────────────────────────
    STORAGE_EXPLORER = "https://storagescan.0g.ai"
    CHAIN_EXPLORER   = "https://chainscan-newton.0g.ai"
    COMPUTE_RPC      = os.getenv("ZG_COMPUTE_RPC",
                       "https://compute-testnet.0g.ai")


ZG = ZGConfig()
