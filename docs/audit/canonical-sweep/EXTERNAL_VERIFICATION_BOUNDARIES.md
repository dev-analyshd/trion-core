# EXTERNAL VERIFICATION BOUNDARIES (§33 — Master Sweep 2026-09-04)

Everything below CANNOT be proven locally and is **never marked PASS merely
because code exists**. Status legend: BLOCKED-TOOLCHAIN vs BLOCKED-EXTERNAL.

## Toolchain-blocked (software exists; compiler/harness absent in sandbox)
- `cargo build/test` — 21 indexer crates + rust BTCP modules + the 4
  block-hash fixes (static parity holds; rust pinned vector byte-identical).
- `go build/test` — validator mesh + health monitor (Go engine statically
  verified, Tendermint-semantics, tested in prior env).
- `func` (TON compile), `scarb` (Cairo), `aptos move`, `anchor` (SVM),
  near-sdk build, hardhat TS deps, TimescaleDB (deploy-gated tables).

## Genuinely external (hardware/keys/networks/third parties)
- **Validator fleet** — no cert-emitting fleet exists; Go tree has no
  certificate code (D1, doc now honest). Emission-side signing is external.
- **Funded relayer wallets** — zero-bridge live E2E (real intent → real
  behavioral evidence → … → observable settlement state) requires funded
  EVM/SOL keys and the redeployed upgraded contracts at recorded addresses.
- **Production keys/HSM** — KMS/HSM paths code-verified (mock-YubiHSM
  end-to-end); real HSM hardware needed.
- **Live chain deployments** — 0G mainnet contract has no code (Galileo is
  the live deployment); on-chain redeploy of upgraded escrow/oracle/registry.
- **External audit firm, real Groth16 setups, live PQC smoke on hardware,
  bounty capitalization + PGP publication** — all disclosed, none claimed.

## Honest residuals inside the codebase (documented, not external)
CUT commitment py↔rust byte-format · EVM lockEscrow 0.55 floor · certificate
contract-address binding (MED-LOW cross-deployment replay) · AWA governance
route demo harness values (labeled) · SDK duplicate surfaces (isolated) ·
72h dispute window (registered xfail) · clipboard match-set restart
volatility (store rows persist lifecycle).
