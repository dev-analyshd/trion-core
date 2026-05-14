# Security Policy — TRION Protocol

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x (testnet) | ✅ Active development |
| 0.x (alpha) | ❌ Deprecated |

## Reporting a Vulnerability

**Do NOT open a public GitHub issue for security vulnerabilities.**

Report security issues directly to: trionprotocolbh@gmail.com

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if known)

We will respond within 48 hours and work with you on a coordinated disclosure.

## Scope

### In Scope
- `src/core/coherence_engine.py` — C(t) master equation
- `src/manipulation/fingerprint_detector.py` — MF detection logic
- `src/planes/physical/nl_engine.py` — Natural Liquidity computation
- `contracts/` — all Solidity contracts
- `akashic/faiss_service.py` — FAISS API endpoints

### Out of Scope
- Testnet keys / wallets (use testnet funds only, no real value)
- Known bootstrap limitations (Σ=0.25, K=0.10, A=0.10 are by design)

## Behavioral Security Architecture

TRION implements Living Security — cryptographic keys derived from behavioral entropy:

- **Genomic Keys**: Base key ⊕ SHA3(behavioral_vector ‖ block_hash ‖ time_window)
- **CRISPR Library**: 7 known attack fingerprints with evolution vectors
- **Chameleon Protocol**: Pre-signed emergency governance transitions

These are defense mechanisms, not vulnerabilities. Do not attempt to exploit them.

## Known Bootstrap Limitations (Not Vulnerabilities)

During testnet, three planes operate at bootstrap values per whitepaper §4.7:
- Σ (Spiritual) = 0.25 — awaiting validator network
- K (Conscious) = 0.10 — awaiting annotation network
- A (ANIMA) = 0.10 — awaiting D(t) ≥ D_minimum

These are disclosed honestly at `/api/v1/system/bootstrap`. They are not security vulnerabilities.
