# CANONICAL DATA LINEAGE — Verified object graph (Master Sweep 2026-09-04)

Every object below was traced producer→serializer→storage→consumer this sweep
(SWEEP-A/B/E, LIVE-2, RED-4). Hash/canonical references re-verified.

| # | Object | Creator | Serialization | Hash/Key | Storage | Consumers | Mutation rule | Security boundary |
|---|---|---|---|---|---|---|---|---|
| 1 | raw chain event | chain RPC | JSON-RPC | block hash (chain-native) | external | streamer / Rust indexers | append-only (chain) | untrusted RPC |
| 2 | normalized event | bh_streamer / indexer | per-family parse | — | memory | compute_bh | pure fn | — |
| 3 | **93-byte BH payload** | compute_bh / canonical_bh / canonicalBH | §1 fixed binary BE | sense/antisense SHA3-256 | BH ledger (SQLite WAL) | FAISS, BIBL, oracle | **immutable** (L0.4) | FIPS SHA3, no keccak |
| 4 | entity_id (§6) | normalise→sha3 | 32B hex | = BEO routing key | ledger + FAISS | merge/enrich/similarity | analysis may re-key, never rewrite | — |
| 5 | FAISS vector | faiss_service /index/add_batch | 128-dim float32 + meta | entity_id | akashic_faiss.index | archetypes, coherence | append; **write key must equal read key** (fixed b4a64fa) | local store |
| 6 | Akashic record | faiss_service entity_history | JSON rows | entity_id | SQLite + Timescale (deploy-gated) | depth D(t), M(t) | append-only | local |
| 7 | coherence C(t) | core/master/coherence.py | float + planes | — | API response | AWA, BIBL, routes | pure fn of vectors | AWA gate output |
| 8 | signal | signal_factory / signal_emitter | 24 SignalTypes | signal_id | API/WS push | frontends, 0G DA | emission gated by AWA | EmissionGate |
| 9 | **BTCP intent (§4.1)** | 5 representations | 10 fields (parity 10/10 py↔rust) | intent hash + nonce | SQLite btcp_state | matcher, orchestrator | state machine | nonce atomicity (49f368e verified) |
| 10 | route | router.py | 7 RouteTypes, registry ids | route_id + intentHash | SQLite + BTCPRoute.sol | escrow | status machine (9e2b84f) | registry-bound verification |
| 11 | escrow | escrow_monitor.py + contracts | 6-state EVM set | escrowId==anchorBH binding | SQLite + on-chain | release paths | CEI, terminal clearing | cert-gated release |
| 12 | **canonical certificate** | certificate.py (reference encoder) | 346B domain-separated P | keccak(EIP-191(P)) EVM-family | epoch registry (on-chain) | every VM release path | forward-only epochs | quorum from registry, never proof |
| 13 | attestation set | validators (fleet: EXTERNAL) | ECDSA/Ed25519/STARK | per-validator sig | cert envelope | VM verifiers | distinct-signer, nonce-ordered | MIN_SIGNERS=3, HHI≤4000 |
| 14 | execution | escrow release | on-chain tx | settlement tuple in cert digest | chain state | feedback BH | idempotent nonce guard | dest-chain gate, TTL |
| 15 | settlement record | netting/escrow release event | JSON+event logs | — | SQLite + logs | feedback | append |  |
| 16 | feedback BH | executed trade → new event | same §1 form | same dual-strand | ledger | TRION loop | closes CHAIN→…→CHAIN |  |

**Loop-closure proof (LIVE-2 + fix b4a64fa):** write key (entity id) ==
read key (resolve_beo) for both input forms — regression-pinned.
**No silent mutation found** in any stage 1→16; the one historical violation
(double-hash) is fixed and pinned.
