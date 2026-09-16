# Cross-VM Certificate Verification Audit

**Audit scope**: every VM contract that consumes TRION canonical certificates
(the 346-byte payload P defined in
`contracts/solidity/libraries/CanonicalCertificate.sol` and the canonical
certificate specification `CANONICAL_CERTIFICATE.md`).

**Audit question**: does each VM have a `verifyCertificate`-equivalent function
that performs **all four** canonical verification steps?

1. **Width check** — payload must be exactly 346 bytes (`PAYLOAD_WIDTH = 346`).
2. **Signer recovery** — recover signer addresses / pubkeys from each
   envelope signature; reject unknown / inactive signers (registry
   membership).
3. **Quorum** — L4.2 tier table over REGISTERED weights (never envelope
   claims): tier 1 (D ≥ 0.60) requires `3·signed > 2·total`; tier 2
   (0.40 ≤ D < 0.60) requires `4·signed ≥ 3·total`; tier 3 (D < 0.40)
   requires `20·signed ≥ 17·total`.
4. **Escrow binding + replay protection** — bind the certificate's
   escrow_id / route_id / intent_hash / entity_id / destination / amount /
   anchor_bh / execution_bh to the on-chain escrow record, and enforce
   strictly-increasing nonce per `(epoch, escrow_id)` so the same
   certificate cannot be replayed.

A VM that performs only attestation counting (e.g. `att.count ≥ quorum_required`)
without payload-width / signature-recovery / weight-quorum / binding /
nonce checks is **INCOMPLETE** and must not be used as a canonical TRION
verification entrypoint.

## Audit results

| # | VM | Contract file | Function | Status | Notes |
|---|----|----------------|----------|--------|-------|
| 1 | **EVM (Arbitrum)** | `contracts/solidity/BTCPEscrow.sol` | `_verifyCanonicalCertificate(payload, weights, sigs)` | ✅ COMPLETE | Calls `CanonicalCertificate.checkPayload` (346 width), `ethSignedDigestOf`, `recoverSigner` (EIP-2 s-malleability guard), `quorumMet` (L4.2 tier table), and the escrow-bound digest `escrowBoundEthDigestOf(payload, escrowDeployment)` for replay protection. |
| 2 | **EVM (Arbitrum)** | `contracts/solidity/TRIONOracleV3.sol` | `_verifyCertificateSignatures(ethDigest, signatures)` + `_checkSignerAndWeight` + `_checkEpochAndRegistry` + `_recordCanonicalVerdict` | ✅ COMPLETE | Full canonical path with epoch registry binding, weight quorum, escrow binding (`canonicalBinding(escrowId)`), conflict detection (`certificateConflict(epoch, escrowId)`). |
| 3 | **Starknet (Cairo)** | `contracts/starknet/src/btcp_escrow.cairo` | `verify_release_certificate(escrow_id, rec, cert, sigs)` | ✅ COMPLETE | §6 steps 1–8 implemented inline: structure (via `check_structure`), envelope, epoch, freshness, signatures (STARK-curve ECDSA via `verify_signature` over Poseidon digest), quorum (`quorum_met`), binding (`escrow_id_matches`, `route_id_matches`, `destination_matches`, `amount_matches`), nonce / consumed (`consumed_nonce`, `consumed_digest`), conflict evidence (`CertificateConflict` event). |
| 4 | **Starknet twin (Cairo)** | `contracts/cairo/src/trion_certificate.cairo` | helper library (`check_structure`, `verify_signature`, `quorum_met`, `is_fresh`, `escrow_id_matches`, `route_id_matches`, `destination_matches`, `amount_matches`, `entity_key`) | ✅ COMPLETE (helpers) | Same canonical library, mirrored from `contracts/starknet/src/`. Consumed by `contracts/cairo/src/trion_execution_gate.cairo`. |
| 5 | **Move (Aptos / Sui)** | `contracts/move/sources/trion_epoch_registry.move` + `contracts/move/sources/btcp_escrow.move` | `verify_certificate(payload, sigs, now)` + `btcp_escrow::release_escrow` | ✅ COMPLETE | `verify_certificate` performs steps 1–6 (structure, envelope, epoch, freshness, registry cross-check, Ed25519 signature verification, L4.2 quorum). `btcp_escrow::release_escrow` performs steps 7–8 (binding via `canonical_cert::escrow_id` / `route_id` / `intent_hash` / `entity_id` / `source_chain` / `dest_chain` / `destination` / `amount` / `anchor_bh` / `execution_bh`; nonce / consumed via `consumed_epoch` + `consumed_nonce`). |
| 6 | **SVM (Solana — Anchor, canonical)** | `contracts/svm/programs/btcp_escrow/src/lib.rs` | `release_escrow(ctx, payload, cert_epoch, envelope)` | ✅ COMPLETE | §6 steps 1–8 inline: parse 346-byte payload (`parse_certificate`), envelope distinct-signers, epoch (registry + grace), freshness, Ed25519 signature verification (via `verify_ed25519_signature`), L4.2 quorum, escrow binding (escrow_id / route_id / intent_hash / entity_id / source_chain / dest_chain / destination / amount / anchor_bh / execution_bh), nonce / consumed PDA (`["trion","consumed",escrow_id]`). |
| 7 | **NEAR (Rust)** | `contracts/near/src/trion_oracle.rs` | `publish_btcp_route(payload, attestations)` | ✅ COMPLETE | §6 steps 1–9 inline: structure (`parse_payload`, 346 width), envelope (sorted-distinct, min signers), epoch (registry + grace), freshness (block-timestamp clock), consensus preconditions (HHI / AWA / coherence ≥ threshold), signatures (Ed25519 via NEAR host function `env::ed25519_verify`), quorum (`quorum_met`), binding (route_id / anchor_bh / execution_bh / coherence / threshold / escrow_id / entity_id / intent_hash / destination / amount / source_chain / dest_chain), nonce ordering + conflict evidence (`highest_nonce`, `nonce_digest`, `CertificateEquivocation` log). |
| 8 | **Solana — Anchor (legacy demo)** | `contracts/solana/programs/btcp_escrow/src/lib.rs` | `release_escrow(ctx, execution_bh, coherence, current_time)` | ❌ INCOMPLETE | Uses simple attestation counting (`submit_attestation` increments `att.count`; `release_escrow` checks `att.count >= escrow.quorum_required`). No 346-byte payload, no signature recovery over canonical P, no L4.2 weight quorum, no binding to canonical cert fields, no per-epoch nonce. **This contract is a pre-canonical demo — use `contracts/svm/programs/btcp_escrow/` (entry #6) for the canonical SVM path.** |
| 9 | **Soroban (Rust)** | `contracts/soroban/btcp-escrow/src/lib.rs` | `release_escrow(env, escrow_id, execution_bh, coherence, current_time)` | ❌ INCOMPLETE | Same simple attestation pattern as #8. No canonical-certificate verification. |
| 10 | **PVM / Polkadot (Substrate)** | `contracts/pvm/btcp_route/src/lib.rs` | `verify_coherence(route_id)` + `release_escrow(route_id)` | ❌ INCOMPLETE | No payload, no signatures, no quorum, no binding. Calls `verify_coherence(route_id)` which just sets a flag on the route record. |
| 11 | **CosmWasm (Cosmos)** | `contracts/cosmwasm/src/contract.rs` | (no `release_escrow` found in audit) | ❌ INCOMPLETE | No canonical certificate verification path defined. |
| 12 | **Clarity (Stacks)** | `contracts/clarity/BTCPEscrow.clar` | `release-escrow(escrow-id, execution-bh, coherence, current-time)` | ❌ INCOMPLETE | Same simple attestation-counting pattern as #8 / #9 / #10. The Stacks VM lacks a STARK/Ed25519 host function suitable for canonical certificate verification; the canonical Stacks verification path runs through `BTCPRoute.clar` + the TRION relayer instead. See `proofs/btcp-zero-bridge/stacks/` for the verified parity proof. |

## Verdict

**5 of 12 VM contracts have full canonical certificate verification.**
The 7 incomplete VMs are demo / pre-canonical / parity-target variants
that the BTC↔VM zero-bridge proof suite (`proofs/btcp-zero-bridge/`) covers
via cross-VM parity tests rather than on-chain canonical verification.
The canonical TRION certificate verification path for production is:

1. **EVM** — `contracts/solidity/BTCPEscrow.sol::_verifyCanonicalCertificate`
2. **Starknet** — `contracts/starknet/src/btcp_escrow.cairo::verify_release_certificate`
3. **Move** — `contracts/move/sources/trion_epoch_registry.move::verify_certificate` + `btcp_escrow.move::release_escrow`
4. **SVM** — `contracts/svm/programs/btcp_escrow/src/lib.rs::release_escrow`
5. **NEAR** — `contracts/near/src/trion_oracle.rs::publish_btcp_route`

These five contracts are the canonical TRION certificate verification
entrypoints; the other seven are documented as incomplete and route
through the canonical five via the relayer / parity proof suite.

## Recommended action for incomplete VMs

Any consumer that needs on-chain canonical verification MUST deploy one of
the five canonical contracts above (or a verified parity twin). The
incomplete variants (Solana-Anchor-legacy, Soroban, PVM, CosmWasm,
Clarity/Stacks) should be marked as **DEPRECATED — non-canonical** in
their headers and routed through the relayer for canonical verification.
A `verifyCertificate`-equivalent can be added to them only after their
host VM exposes the necessary cryptographic primitives (STARK-curve ECDSA
or Ed25519 host function with small-subgroup rejection).

This audit document is the canonical reference; it is linked from
`docs/SECURITY.md` and `proofs/MANIFEST.md`.
