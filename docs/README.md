# TRION Protocol — Documentation Index

| Section | Contents |
|---------|---------|
| **Canonical docs (Waves 1–3 — read first for conformance)** | |
| [audit/CANONICAL_SPEC_MATRIX.md](audit/CANONICAL_SPEC_MATRIX.md) | 107 normative requirements + K1–K22 conflict resolutions (the contract) |
| [protocol/CANONICAL_BH.md](protocol/CANONICAL_BH.md) | Canonical 93-byte Behavioral Hash + golden vectors |
| [protocol/CANONICAL_CERTIFICATE.md](protocol/CANONICAL_CERTIFICATE.md) | 346-byte cross-VM certificate, weight quorum, replay/TTL rules |
| [protocol/BTCP_STATE_MACHINE.md](protocol/BTCP_STATE_MACHINE.md) | BTCP machines M1–M5, 26 states / 33 transitions |
| [security/CANONICAL_INVARIANTS.md](security/CANONICAL_INVARIANTS.md) | INV-001…022 invariant register with enforcement status |
| **Reference docs** | |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture (post Wave 1–3 truth) |
| [api/endpoints.md](api/endpoints.md) | REST API reference (the live route set is 282 — see `api/app.py`) |
| [architecture/five_planes.md](architecture/five_planes.md) | Five behavioral planes: Φ M Σ K A |
| [architecture/bootstrap.md](architecture/bootstrap.md) | Cold-start bootstrapping sequence |
| [architecture/chameleon.md](architecture/chameleon.md) | Chameleon Protocol — adversarial noise defense |
| [architecture/living_security.md](architecture/living_security.md) | 8-component DNA-mimetic security system |
| [CHAIN_MANIFEST.md](CHAIN_MANIFEST.md) | 129 chains · 18 VM families (recomputed from the registry) |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Deployment guide (custody + topology truth) |
| [proofs/attack_simulations.md](proofs/attack_simulations.md) | Historical attack simulation results |
| [proofs/falsifiability.md](proofs/falsifiability.md) | Falsifiability conditions F1–F15 |
| [deployments/](deployments/) | Self-reported deployment records (honestly labeled) |
| **Live research/formal sources (moved out of docs/research — archived copies in [research/archive/](research/archive/))** | |
| [`../formal/src/TRION/Theorems.hs`](../formal/src/TRION/Theorems.hs) | Haskell type-level formal verification (7 theorems) |
| [`../math/src/TRIONMath.jl`](../math/src/TRIONMath.jl) | Julia entropy verification suite |
| [`../signal-processing/src/`](../signal-processing/src/) | C++ FFT behavioral entropy engine |
| [`../validator/`](../validator/) | Go validator mesh (DW-BFT; external toolchain) |
| [audit/](audit/) | Audit reports (in-repo, honestly labeled — see the audit README) |


## Quick Links
- **Whitepaper formula coverage:** `GET /api/v1/whitepaper/coverage`
- **Live signal:** `GET /api/v1/signal/{entity}`mz
- **Main README:** [../README.md](../README.md)
