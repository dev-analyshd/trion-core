"""
TRION BZK Phase 2 — Commitment Layer (R-ORDER: commitments before circuits).

Public API surface (per BTCP §5.6, §7.1, Fix 1 Step 4 + WP-Mar §16 + WP-Feb
Formula Index):

  hash_dna.hash_dna(...)             — dual-strand SHA3-256 (BTCP Formula Index)
  hash_dna.behavioral_hash(...)      — BTCP §7.1 entity-side private hash
  hash_dna.public_commitment(...)    — BTCP §7.1 hash-of-hash (no content)
  hash_dna.intent_hash(...)          — BTCP §5.6 Phase 1 H_intent
  hash_dna.birp_anchor(...)          — WP-Mar §16 + WP-Feb Formula Index
  hash_dna.disclosure_hash(...)      — BTCP Fix 1 Step 3 public input

  akashic_root.compute_root(...)     — BTCP §7.1 historical_BEO_root (offchain)
  akashic_root.merkle_proof(...)
  akashic_root.verify(...)

  disclosure_store.*                 — BTCP Fix 1 Step 4 (hash-only)
  birp_store.*                       — WP-Mar §16 (anchor-only)

R-ABSENT invariants enforced via leakage_grep.sh (word-boundary, case-sensitive).
R-CHANNELS: commitment roots are offchain; onchain surface is signal
publication only (per WP-Mar §15).
"""

from . import hash_dna  # noqa: F401
from . import akashic_root  # noqa: F401
from . import disclosure_store  # noqa: F401
from . import birp_store  # noqa: F401

__all__ = ["hash_dna", "akashic_root", "disclosure_store", "birp_store"]
