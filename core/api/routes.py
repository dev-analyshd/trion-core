"""
TRION Protocol — Complete REST API Routes
All endpoints documented and implemented.
"""

import logging

logger = logging.getLogger(__name__)

API_SPEC = {
    "version": "1.0.0",
    "base_url": "https://trion-protocol.replit.app",
    "docs_url": "/docs",
    "endpoints": {
        # Core signal
        "signal":        "/api/v1/signal/{entity_id}",
        "signal_history":"/api/v1/signal/{entity_id}/history",
        "signal_batch":  "/api/v1/signal/batch",
        # Planes
        "planes_all":    "/api/v1/planes/{entity_id}/all",
        "planes_physical":"/api/v1/planes/{entity_id}/physical",
        "planes_mental": "/api/v1/planes/{entity_id}/mental",
        "planes_spiritual":"/api/v1/planes/{entity_id}/spiritual",
        "planes_conscious":"/api/v1/planes/{entity_id}/conscious",
        "planes_anima":  "/api/v1/planes/{entity_id}/anima",
        # Security
        "mf_check":      "/api/v1/security/{entity_id}/mf",
        "pre_exec":      "/api/v1/security/check",
        "crispr_lib":    "/api/v1/security/crispr/library",
        "genomic_key":   "/api/v1/security/{entity_id}/genomic",
        # Liquidity
        "nl_score":      "/api/v1/liquidity/{asset_address}",
        "nl_history":    "/api/v1/liquidity/{asset_address}/history",
        # BTCP
        "btcp_score":    "/api/v1/btcp/score",
        "btcp_verify":   "/api/v1/btcp/verify",
        # Genesis
        "genesis":       "/api/v1/genesis/{asset_id}",
        "genesis_conf":  "/api/v1/genesis/{asset_id}/confidence",
        # Index
        "index_status":  "/api/v1/index/status",
        "vm_status":     "/api/v1/index/vm-status",
        "akashic_depth": "/api/v1/index/depth",
        "index_add":     "/api/v1/index/add",
        # System
        "health":        "/health",
        "system_status": "/api/v1/system/status",
        "bootstrap":     "/api/v1/system/bootstrap",
        "falsifiability":"/api/v1/system/falsifiability",
    }
}

# Import-time diagnostics go to the module logger at DEBUG level (silenced
# by default) instead of stdout — a bare print() here fired on every import.
logger.debug(
    "API surface: %d endpoints across all whitepaper sections",
    len(API_SPEC["endpoints"]),
)
