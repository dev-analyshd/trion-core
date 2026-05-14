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
    # ── Network mode: "mainnet" | "testnet" ──────────────────────
    NETWORK  = os.getenv("ZG_NETWORK", "mainnet")

    # ── Aristotle Mainnet (chain 16601) — primary ─────────────────
    MAINNET_RPC      = os.getenv("ZG_MAINNET_RPC",     "https://evmrpc.0g.ai")
    MAINNET_INDEXER  = os.getenv("ZG_MAINNET_INDEXER", "https://indexer-storage.0g.ai")
    MAINNET_DA_RPC   = os.getenv("ZG_MAINNET_DA_RPC",  "https://da-rpc.0g.ai")
    MAINNET_CHAIN_ID = 16661
    MAINNET_EXPLORER = "https://chainscan.0g.ai"

    # ── Galileo Testnet (chain 16602) — fallback ──────────────────
    TESTNET_RPC      = os.getenv("ZG_TESTNET_RPC",     "https://evmrpc-testnet.0g.ai")
    TESTNET_INDEXER  = os.getenv("ZG_TESTNET_INDEXER", "https://indexer-storage-testnet-turbo.0g.ai")
    TESTNET_DA_RPC   = os.getenv("ZG_TESTNET_DA_RPC",  "http://localhost:51001")
    TESTNET_CHAIN_ID = 16602
    TESTNET_EXPLORER = "https://chainscan-galileo.0g.ai"

    # ── Active network (resolved from NETWORK) ────────────────────
    @classmethod
    def _is_mainnet(cls) -> bool:
        return cls.NETWORK.lower() == "mainnet"

    RPC      = MAINNET_RPC      if os.getenv("ZG_NETWORK", "mainnet") == "mainnet" else os.getenv("ZG_TESTNET_RPC", "https://evmrpc-testnet.0g.ai")
    INDEXER  = MAINNET_INDEXER  if os.getenv("ZG_NETWORK", "mainnet") == "mainnet" else os.getenv("ZG_TESTNET_INDEXER", "https://indexer-storage-testnet-turbo.0g.ai")
    DA_RPC   = MAINNET_DA_RPC   if os.getenv("ZG_NETWORK", "mainnet") == "mainnet" else os.getenv("ZG_TESTNET_DA_RPC", "http://localhost:51001")
    CHAIN_ID = MAINNET_CHAIN_ID if os.getenv("ZG_NETWORK", "mainnet") == "mainnet" else TESTNET_CHAIN_ID

    # Newton testnet RPC (chain 16600) — legacy AkashicProof
    NEWTON_RPC = os.getenv("ZG_NEWTON_RPC", "https://rpc-testnet.0g.ai")

    # ── Contracts — Mainnet (Aristotle 16601) ─────────────────────
    MAINNET_EXECUTION_GATE   = os.getenv("ZG_MAINNET_GATE_ADDR",   "")
    MAINNET_ORACLE_V3        = os.getenv("ZG_MAINNET_ORACLE_ADDR", "")
    MAINNET_AKASHIC_PROOF    = os.getenv("ZG_MAINNET_AKASHIC_ADDR","")

    # ── Contracts — Galileo Testnet (16602) ───────────────────────
    TESTNET_EXECUTION_GATE   = "0xDB5910Dc6CfD219D00F64be1F23DA0289901356d"
    TESTNET_ORACLE_V3        = "0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C"
    TESTNET_AKASHIC_PROOF    = "0x33c793fed5bf5fcB043D8c6c74256e7B4b38156D"

    # DA entrance on Galileo testnet
    DA_ENTRANCE = "0x857C0A28A8634614BB2C96039Cf4a20AFF709Aa9"
    DA_SIGNERS  = "0x0000000000000000000000000000000000001000"

    # ── Active contract addresses (mainnet if deployed, else testnet) ─
    @classmethod
    def execution_gate(cls) -> str:
        return cls.MAINNET_EXECUTION_GATE or cls.TESTNET_EXECUTION_GATE

    @classmethod
    def oracle_v3(cls) -> str:
        return cls.MAINNET_ORACLE_V3 or cls.TESTNET_ORACLE_V3

    @classmethod
    def akashic_proof(cls) -> str:
        return cls.MAINNET_AKASHIC_PROOF or cls.TESTNET_AKASHIC_PROOF

    # Legacy aliases
    AKASHIC_PROOF_CONTRACT = os.getenv("ZG_AKASHIC_CONTRACT", "0x33c793fed5bf5fcB043D8c6c74256e7B4b38156D")
    EXECUTION_GATE = os.getenv("ZG_EXECUTION_GATE_ADDR", "0xDB5910Dc6CfD219D00F64be1F23DA0289901356d")

    # ── Keys — DEPLOY_0G_PRIVATE used for mainnet; RELAYER_PRIVATE_KEY for testnet ─
    PRIVATE_KEY = os.getenv(
        "DEPLOY_0G_PRIVATE",
        os.getenv("ZG_PRIVATE_KEY",
        os.getenv("DEPLOYER_PRIVATE_KEY",
        os.getenv("RELAYER_PRIVATE_KEY", "")))
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
    CHAIN_EXPLORER   = MAINNET_EXPLORER if os.getenv("ZG_NETWORK", "mainnet") == "mainnet" else TESTNET_EXPLORER
    NEWTON_EXPLORER  = "https://chainscan-newton.0g.ai"
    COMPUTE_RPC      = os.getenv("ZG_COMPUTE_RPC", "https://compute.0g.ai")


ZG = ZGConfig()
