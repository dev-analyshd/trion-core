# BIBL HANDSHAKE SPEC (TRION ↔ BTCP boundary, verified 2026-09-04)

BIBL = **Behavioral Intent Behavioral Layer** — the interpretive handshake
where TRION evidence becomes BTCP input. Neither side may cross it
unlabeled.

```
TRION side (producers)                    BIBL (interpreter)                BTCP side (consumers)
──────────────────────                    ─────────────────                 ────────────────────
Akashic state (FAISS vectors,       ──►  core/btcp/bibl_engine.py:    ──►  intent analysis: coherence
entity_history, ledger rows)             chain-state tiers (latency          vs min_NL_score×1000,
AWA gate state (frozen/open)             targets 50/50/150ms, D3)            gas CI_95 vs max_total_gas,
24 SignalTypes (NL, gas, BRT,            reads LIVE ledger/vectors           BRT window, jurisdiction
CHAIN_RELIABILITY, MEV...)                via beo_lookup →                    → route feasibility
behavioral records (BH)                   akashic_state.db                    → escrow parameters
                                          IntegrationHub consumes real        (min_coherence, TTL)
                                          anima-service signals (wired
                                          73d5e9e; phantom-import bug
                                          found & fixed)
```

## Verified handshake invariants (this sweep)

1. **No fabricated evidence:** BIBL witnesses resolve against the real
   Akashic ledger; the fallback path is labeled `self_attestation` (never
   silently substituted). `POST /api/v1/btcp/route` labels every
   caller-supplied field and states "not a TRION-verified route verdict".
2. **No truth mutation:** BIBL reads; it never writes TRION state. The write
   surfaces (add_batch, storage) are API-key gated (P-API-02 closed) and
   AWA-gated (d9f8d8e).
3. **Identity binding:** intent entity → BEO id (§6) → ledger key — same
   canonical id end-to-end (loop-closure fix b4a64fa restored this).
4. **Route binding:** routes reference registry chain ids only;
   off-registry verification rejected (P-PY-03); anchorBH==escrowId binds
   the escrow to the route's behavioral anchor.
5. **Direction:** TRION→BIBL is read-only; BTCP→TRION feedback flows only
   as new observed events (new BHs), never as a direct store write.

**Residual (labeled):** `/api/v1/btcp/bibl/snapshot` returns hand-seeded
demo chain states — now machine-labeled `demo:true` (2f6a431).
