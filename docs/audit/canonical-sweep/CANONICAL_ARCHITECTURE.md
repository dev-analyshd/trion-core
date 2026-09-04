# CANONICAL ARCHITECTURE — Reconstructed & Verified (Master Sweep, 2026-09-04)

**Baseline:** HEAD `c6c38e4` (reported `af09ab3` was 83 commits stale — recorded in
`REPOSITORY_BASELINE.json`). **Sweep evidence:** `SWEEP-A/B/C/D.md`, `RED-4.md`,
`LIVE-2.md` in this directory. Every load-bearing claim below was re-verified at
the swept HEAD (fixes landed during the sweep are marked).

---

## The one-protocol map

```
TRION (sensing / memory)                          BTCP (action / settlement)
─────────────────────────                          ─────────────────────────
SENSE      129-chain registry (18 VM families)     INTENT     §4.1 full field set,
           → 2 ingestion paths:                               5 representations
             a) bh_streamer (96 py workers)         MATCH      BITP matcher + netting
             b) 21 Rust indexer crates              ROUTE      7 route types, registry-bound
NORMALIZE  canonical 93-byte BH (§ CANONICAL_BH.md) ESCROW     behavioral escrow,
           dual-strand SHA3-256                                certificate-gated release
STORE      BH ledger (SQLite WAL)                  PROOF      ZK pending paths (honest)
           + FAISS 128-dim Akashic                 ATTEST     canonical 346-byte cert,
AKASHIC    64 archetypes, BEO resolution                      per-epoch registry,
COHERENCE  5-plane C(t)=αΦ+βM+γΣ+δK+εA                        diversity-weighted quorum
           Θ=0.55+0.37·V, master T(t)              EXECUTE    state machine, 26 states
SIGNAL     24 SignalTypes ×3 languages             SETTLE     netting / IAP / escrow release
ORACLE     AWA EmissionGate → API + 0G
   ↓ BIBL (the handshake) ↓                        ↑ feedback: executed trades
   TRION evidence → intent analysis → route input      flow back as new BHs
```

## Component classification (verified this sweep)

| Component | Class | TRION/BTCP | Evidence |
|---|---|---|---|
| core/primitives/behavioral_hash.py | PRODUCTION | TRION | clean-room 52/52 vectors |
| core/realtime/bh_streamer.py | PRODUCTION | TRION | LIVE-2: 69 BH/s real RPCs |
| anima-service/faiss_service.py | PRODUCTION | TRION | loop-closure fix b4a64fa |
| core/consensus/certificate.py | REFERENCE (encoder) | hand-off | SWEEP-A; fleet signing absent |
| core/master, core/governance/awa.py | PRODUCTION | TRION | 6-condition set, emission gate |
| api/app.py (282 routes) | PRODUCTION | both | 30/30 battery; write gates |
| contracts/solidity + TrionEpochRegistry | PRODUCTION | BTCP | solc 0.8.24 viaIR, 16/16 defended |
| contracts/vyper (escrow, token) | PRODUCTION-REFERENCE | BTCP | vyper 0.3.10 compile+tests |
| contracts/{svm,move,ton,cairo} | PRODUCTION (static-verified) | BTCP | SWEEP-C per-tier verdicts |
| contracts/near | PARTIAL (no release entrypoint) | BTCP | SWEEP-C |
| contracts/pvm (ink!) | RESEARCH_NON_PRODUCTION | BTCP | honest marker verified |
| validator/ (Go, 20 files) | TESTED PROTOTYPE (not daemon) | TRION | SWEEP-A; no cert code |
| signal-processing C++ | REFERENCE/PROTOTYPE | TRION | SWEEP-A |
| julia/ | REFERENCE (5/5 profiles match) | TRION | SWEEP-A live parity |
| Haskell theorems | PAPER proofs (2/9 type-checked) | — | SWEEP-A; not a prod guarantee |
| wasm signal_processor | PRODUCTION (SDK consumer) | TRION | 15 exports, parity ≤2e-15 |
| frontend ×2, sdk ×5, relayer, trion-0g | INTEGRATION | both | SWEEP-B/D |

## Canonical-chain status (post-sweep fixes)

- **Fixed this sweep:** BEO write-path double-hash (loop closure), AWA freeze on
  3 zg surfaces, block-hash SHA3-substitution in 4 Rust indexers (§9), TS §6
  entity rule, cert-doc honesty, BIBL demo label.
- **Open (documented, non-blocking):** CUT commitment Python↔Rust byte-format
  divergence; EVM lockEscrow 0.55 floor; cert contract-address binding;
  AWA route's hardcoded demo inputs (labeled); Go mesh never daemonized.

**Verdict (architecture):** one coherent TRION+BTCP protocol is reconstructible
from whitepaper → math → data model → implementations → tests → deployments,
with the open items above explicitly dispositioned. See FINAL_RELEASE_VERDICT.md.
