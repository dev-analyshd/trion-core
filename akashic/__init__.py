"""TRION Akashic Records — runtime state directory + Python package marker.

The `akashic/` directory holds the runtime SQLite databases and FAISS state
(bibl_patterns.db, crispr_adaptive.db, epigenetic_immunity.db,
validator_registry.db, akashic_state.db, akashic_faiss.index — all gitignored,
created at runtime by core/akashic/, core/spiritual/, and anima-service
consumers).

This package marker exists so the directory is always present and importable.
It previously also held a `btcp_price_oracle.py` re-export shim — that
duplicate was removed in P3-CONSOLIDATE; the canonical implementation now
lives at `core/price/btcp_price_oracle.py` (the `anima-service/` hyphen makes
a plain package import impossible, which is why the shim existed).
"""
