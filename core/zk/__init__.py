"""
TRION BZK Phase 5 — ZK Integration Layer.

Public API surface (per mission Phase 5.1-5.4 + BTCP §5.6 + BTCP §5.3 +
BTCP Fix 1 CHAMELEON + WP-Feb §14.2 + WP-Mar §17):

  netting_invisible.NettingInvisible  — BTCP §5.6 INVISIBLE privacy mode
  iap_transparent.TransparentIAP      — BTCP §5.3 + §14.1 P3 #11 transparent shares
  chameleon_tiers.ChameleonTiers      — BTCP Fix 1 CHAMELEON block (LOW/MED/HIGH/CRIT)
  awa_freeze.AWAFreezeIntegrator       — WP-Feb §14.2 / WP-Mar §17 freeze wiring
  _mock_verifier.MockComplementarityVerifier  — testing twin (SYNTHETIC-DEMO)
  _mock_verifier.MockTravelRuleVerifier       — testing twin (SYNTHETIC-DEMO)

R-ABSENT invariants enforced via leakage_grep_zk_integration.sh.
R-INVISIBILITY: NO override path exists for the AWA freeze — grep `forceResume` /
`overrideFreeze` returns ZERO matches across the entire codebase.
R-ORDER: ZK IAP share-proof path is `[OPEN]` per Phase 3 BLOCKER; transparent
shares are the live default. The MockVerifier is the testing twin; the real
verifier.sol (exported via `snarkjs zkey export solidityverifier`) drops into
the same `setVerifier(circuitId, address)` interface when the BLOCKER closes.
R-CHANNELS: integration modules call the on-chain contracts via their public
interface; no on-chain proof generation.
R-FAILCLOSED: every error is named; the freeze path is the default when AWA
is uncertain.
"""

# Lazy imports — defer the submodule imports until first attribute access so
# a partially-initialized `core.zk` package (e.g. during incremental
# authoring of Phase 5.1-5.4) does NOT raise ImportError on `import core.zk`.
# This pattern is identical to how `core.governance` and `core.novel` handle
# cross-submodule dependencies in the existing TRION codebase.

__all__ = [
    "_mock_verifier",
    "netting_invisible",
    "iap_transparent",
    "chameleon_tiers",
    "awa_freeze",
]


def __getattr__(name: str):
    if name in __all__:
        import importlib
        return importlib.import_module(f"core.zk.{name}")
    raise AttributeError(f"module 'core.zk' has no attribute {name!r}")
