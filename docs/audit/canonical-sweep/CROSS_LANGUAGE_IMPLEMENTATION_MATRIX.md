# CROSS-LANGUAGE IMPLEMENTATION MATRIX (Master Sweep 2026-09-04)

Legend: **PARITY** = executed live, byte-identical · **STATIC** = source-verified
(no toolchain in sandbox) · **DIVERGENT** = semantic mismatch · **ABSENT** = no impl.

| Canonical object | Python | Rust | TypeScript | Go | Contracts (9 VMs) | C++/Julia/Haskell | Golden vectors | Verdict |
|---|---|---|---|---|---|---|---|---|
| 93-byte BH payload | behavioral_hash.py + streamer + faiss_service | hash_dna.rs + 21 indexers | canonical_bh.ts | — | bytes32 opaque (by design) | — | **52 vectors** | **PARITY (py↔ts live; rust STATIC)** |
| Dual-strand algebra | ✓ | ✓ | ✓ | — | — | — | 52 vectors | PARITY |
| entity_id §6 normalise | ✓ (52 vectors) | normalise() ✓ | **FIXED this sweep** (7b41a46) — bare-40-hex rule | — | — | — | 3 live probes | PARITY |
| Magnitude §4 fixed-scale | ✓ | ✓ (deterministic, session-max removed) | ✓ | — | — | Julia = whitepaper variant (reference) | vectors incl. 0.5-ulp edge | PARITY |
| Block hash §9 lenient decode | ✓ | **4 crates FIXED** (0ef64fd) | ✓ | — | — | — | edge vectors | PARITY (post-fix) |
| Certificate 346B payload | certificate.py (reference encoder) | — | — | **NO CERT CODE IN GO** (D1) | verified on EVM/SVM/Move/TON/Cairo; Vyper consumes oracle verdicts; NEAR §6 path only | — | 68 cert vectors | encoder PARITY (py); fleet emission EXTERNAL |
| Intent §4.1 (10 fields) | modules.py BITPIntent | BITPIntentData | — | — | — | — | unit parity tests | **PARITY 10/10 py↔rust** |
| 24 SignalTypes | signal_factory | signal_emitter.rs | SDK copies **DIVERGENT** (4 duplicate SDK surfaces remain, isolated) | — | — | — | byte-diff = 0 py↔rust | PARITY core; SDK tail open |
| Chain ids | registry-derived | 29 consts sampled ✓ | registry_counts.mjs + consts | health list | registry gates | — | registry audit | PARITY |
| CUT commitment (§17) | modules.py | bitp_matcher.rs | — | — | — | — | none | **DIVERGENT (open)** — same fields, different byte format (0x-prefixes/None forms); live digests differ |
| Coherence C(t) | ✓ | master_equation.rs | wasm ✓ | — | — | Julia 5/5 match | 105 formula battery | PARITY |
| Consensus (DW-BFT) | consensus.py + certificate | — | — | Tendermint-semantics engine (tested prototype, not daemon) | attestation verifiers | — | consensus_bft tests | **PARITY semantics; integration gap (mesh not wired to certs)** |

## The one cross-language corpus

`tests/golden/vectors.json` (52 vectors: 2 frozen reference vectors, realistic
chain events, magnitude clamps/edges, all 20 event types, lenient-hex edges,
chain-id separation incl. u32 max, 0.5-ulp truncation edge) is consumed by:
Python builder (52/52), TypeScript builder via bun (**52/52 — live run this
sweep**), Rust by static source-order parity + the pinned
`cross_language_canonical_bh_vector` unit test. Certificate corpus:
`tests/golden/` 68 vectors (py + py-evm EVM verification).

**Unification rule (enforced):** any divergence on the corpus is a finding —
this sweep closed the last write-path divergence (loop-closure b4a64fa) and
the TS §6 helper divergence; remaining open: CUT commitment format (both
sides internally consistent; needs one canonical byte-format ruling + static
rust parity pin), SDK duplicate surfaces (isolated, test retirement pending).
