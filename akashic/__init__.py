"""TRION Akashic Records — Python package marker.

The `akashic/` directory historically held only SQLite database files
(bibl_patterns.db, crispr_adaptive.db, epigenetic_immunity.db). Several
test modules import from `akashic.btcp_price_oracle` and other Python
modules. This package marker makes those imports resolvable.

The canonical implementations live in `anima-service/` and `core/akashic/`;
shims here re-export them so existing code paths keep working.
"""
