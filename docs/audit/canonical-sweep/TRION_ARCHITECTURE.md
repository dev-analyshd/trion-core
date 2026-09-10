# TRION ARCHITECTURE (canonical reconstruction, verified 2026-09-04)

TRION = **the sensing and memory layer**: it observes chain behavior and
produces scored, gated behavioral truth. It never executes transfers.

```
SENSE       129 chains / 18 VM families → two ingestion paths:
            (a) core/realtime/bh_streamer.py — 96 pure-Python workers over
                public RPCs (the path that runs without cargo; LIVE-2: 69 BH/s,
                real block heads ETH 25,906,540 / SOL slot 444,343,783 / BTC 965,523)
            (b) indexers/crates — 21 Rust crates + trion-common (production
                path; cargo = external boundary)
NORMALIZE   canonical 93-byte BH: entity_id(32) event(1) magnitude_nano(8)
            context(8) timestamp(8) chain_id(4) block_hash(32), big-endian;
            sense=SHA3-256(p‖0x00), antisense=SHA3-256(p‖0xFF)⊕NOT(sense)
STORE       BH ledger (SQLite WAL, 54k+ rows live) + FAISS 128-dim IVFPQ
            Akashic index (60k+ vectors live) — write key == read key
            (loop-closure fix b4a64fa, regression-pinned)
AKASHIC     64 k-means archetypes, BEO 4-factor merge (funding/co-occurrence/
            deployer + confidence>0.75), entity_history, depth D(t)
COHERENCE   5-plane C(t)=.25Φ+.30M+.25Σ+.10K+.10A; Θ=0.55+0.37V;
            master equation T(t)=[C≥Θ]·C·e^{M·t} (moat clamp 36)
SIGNAL      24 canonical SignalTypes (py/rust byte-identical; T(t) gate;
            silence payload when C<Θ — "silence is information", MD §11)
ORACLE      AWA EmissionGate (MD §17 six-condition canonical set: signal
            weights monopoly, validator selection control, public good ≥15%,
            SDP active, right-to-invisibility, gratitude=1) — frozen ⇒ every
            publication surface 503 silence:true (publish, route, 0G DA,
            storage, sync, compute — RED-4-F1 closed d9f8d8e)
FEEDBACK    executed BTCP trades return as new events → new BHs
```

**Boundary:** TRION ends at the published, AWA-gated signal + the Akashic
state BIBL reads. **Verified non-fabrication:** BIBL binds BEO witnesses to
the real ledger (beo_lookup → akashic_state.db; fallback labeled
self-attestation); route analysis labels every caller-supplied field.

**Trust boundaries:** untrusted RPCs → deterministic normalization →
immutable ledger → local stores → AWA gate → public surfaces. No wall clock
or session state may enter a BH (§5; SystemTime residue: none in indexers
this sweep — SWEEP-B).
