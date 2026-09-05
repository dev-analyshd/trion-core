# GOLDEN VECTOR CORPUS — unification index (§16/§17, Master Sweep 2026-09-04)

**Corpus location:** `tests/golden/vectors.json` (52 canonical BH vectors) +
`tests/golden/` suite (143 tests) + certificate corpus (68 vectors) +
`config/bh_schema_v1.json::test_vector` + pinned Rust
`indexers/crates/trion-common/src/hash_dna.rs::cross_language_canonical_bh_vector`
+ **§17 CUT commitment corpus (6 vectors,
`tests/golden/bitp_cut_commitment_vectors.json` — follow-on-1 closed)**.

## Corpus coverage (BH §1–§9)

2 frozen reference vectors (schema + rust cross-lang) · realistic chain events
(transfer, swap, MEV capture, flash loan) · magnitude maxima/clamps/zero ·
all-zero minimal payload · per-chain decimal normalization (18/6/9/7) ·
chain-id separation incl. u32 max · **all 20 event-type bytes** · lenient
block-hash edges (0x0, odd length, invalid nibbles, uppercase) · entity rules
(pinned bh_id, case-insensitivity, non-EVM passthrough, synthetic per-tx
senders) · context/timestamp edges · **0.5-ulp truncation edge** (fails any
rounding implementation).

## Verification results this sweep

| Implementation | Method | Result |
|---|---|---|
| **Clean-room reimplementation** (spec-only, zero repo code) | this sweep | **52/52 byte-exact** |
| Python canonical builder | tests/golden | 52/52 |
| TypeScript builder (`canonicalBH`) | live bun run over the corpus | **52/52** |
| Rust builder | pinned vector byte-identical + static source-order parity | STATIC-ONLY (cargo external) |
| Dual-strand invariant on fresh vectors | live | holds |
| Fresh-vector cross-language (not in corpus) | py↔ts↔clean-room | identical (bc417a52…/2bbef776…) |

## Corpus gaps (recorded)

- `entityIdFromAddr` (§6 helper) had no corpus coverage — divergence found &
  fixed this sweep (7b41a46); 3 live probes now pinned in the sweep evidence;
  corpus extension recommended at the next vector re-issuance.
- ~~CUT commitment (§17): no corpus vectors~~ **CLOSED (follow-on-1):** the
  canonical byte-format ruling is issued (every segment via the canonical
  encoder policy — no 0x prefixes, None → "none", python-repr floats,
  bracketed allow-lists), the py encoder rebuilt to it, the Rust twin
  aligned (statically pinned; cargo-blocked here), and a 6-vector corpus
  pinning the preimage TEXT and the sha3-256 digest now guards it
  (`tests/golden/test_bitp_cut_commitment_vectors.py`, 9 tests).
- Rule: corpus changes require a spec mandate + coordinated four-language
  re-issuance in one commit (CANONICAL_BH.md §2).
