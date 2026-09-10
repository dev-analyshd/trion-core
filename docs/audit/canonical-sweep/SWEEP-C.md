# SWEEP-C — Contract Tiers: Canonical Certificate Verification, State Machine, Attack Matrix, Binding Chain

**Task ID:** SWEEP-C (Team J — smart contracts / VM)
**Repo:** /home/z/trion-core @ HEAD c6c38e4 (research-only; no repo files modified, no state-changing git)
**Toolchain actually used:** solc 0.8.24 (py-solc-x, `via_ir=True`, optimize 200 runs), vyper 0.3.10, eth-tester/py-evm + web3 8.0.0, node (TON layout test).

---

## 1. Per-tier certificate verification table

| Tier | Release path (file:line) | Mechanism (file:line) | Compile result | Verdict |
|---|---|---|---|---|
| **Solidity EVM** | `BTCPEscrow.releaseEscrowCanonical` — contracts/solidity/BTCPEscrow.sol:356-398 (permissionless; also legacy `releaseEscrow` :740 with `_consensusGate` :233-267) | Full §6 on raw 346-byte P: `CanonicalCertificate.checkPayload` (libraries/CanonicalCertificate.sol:227-242, width/domain/kind/version/HHI/AWA/isSafe/TTL/freshness); epoch registry conformance — `epochActive`/`validatorCount`/`totalPower`/`threshold`==registry (BTCPEscrow.sol:444-456, H-01/H-03); EIP-191 over keccak256(P) (CanonicalCertificate.sol:254-256); sorted distinct signers + EIP-2 low-s (BTCPEscrow.sol:517-534, CanonicalCertificate.sol:375-394); envelope weight-claim cross-check vs registry (BTCPEscrow.sol:536-549); **w_j = s_j·d_j/1e6** from registry (TrionEpochRegistry.sol:151-154, stored :51-55); threshold-from-registry (TrionEpochRegistry.sol:208-210); L4.2 tier quorum 3s>2t / 4s≥3t / 20s≥17t (CanonicalCertificate.sol:329-338); nonce guard + conflict evidence (BTCPEscrow.sol:557-580) | **solc 0.8.24 viaIR OK** — BTCPEscrow 16,332 B; TRIONOracleV3 14,750 B; TrionEpochRegistry 3,962 B; TRIONExecutionGate 10,562 B | **VERIFIED** |
| **Solidity Oracle (observability)** | `TRIONOracleV3.submitCertificateAttestation` — TRIONOracleV3.sol:491-529 | Same §6 discipline (:532-568 registry, :578-633 signatures+weights, :646-689 nonce/conflict); consumers re-verify at the point of value movement (explicitly required, BTCPEscrow.sol:269-283) | OK (above) | **VERIFIED** (index surface; escrow re-verifies) |
| **Vyper** | `BTCP_ESCROW.vy release` — contracts/vyper/BTCP_ESCROW.vy:168-248 (permissionless) | Quorum **derived from oracle live state**, not a static floor-2: `minRouteAttestations()` view consulted (:235-239, `required = max(2, oracle_quorum)`; interface mismatch fails closed — no try/catch in Vyper); verdict **bound to this escrow** `anchor_bh == escrow_id` (:221); expiry guard — no release after block timeout (:205-206); destination binding — pays only stored `record.destination` (:246); freshness 300 s (:241); coherence ≥ threshold (:242). **No 346-byte canonical-certificate codec in the Vyper tier** — it consumes the oracle verdict (this is exactly what CANONICAL_CERTIFICATE.md §7 line 422 claims for Vyper: "release() consumes the registry-backed verdict; replaces the static attestations ≥ 2 floor") | **vyper 0.3.10 OK** — BTCP_ESCROW 2,887 B; TRIONToken 6,457 B; TRIONStaking 7,817 B | **PARTIAL** (verdict-consumption + dynamic quorum VERIFIED; full cert codec ABSENT, doc-consistent) |
| **SVM / Anchor** | `release_escrow` — contracts/svm/programs/btcp_escrow/src/lib.rs:888-1210 | Ed25519 via runtime **Ed25519SigVerify instruction introspection** with three-way exact match (runtime-verified pk/sig/msg == registered key / envelope sig / THIS payload) (:551-605); epoch registry **PDA ["trion","validators",epoch_be]** (:76, :265-291); grace window (:948-956); threshold == registered Θ(t) (:989); weight quorum tiers (:1061-1111, u128); binding escrow/route/intent/entity/tuple/chains/anchorBH (:1114-1131); consumed-cert PDA ["trion","consumed",escrow_id] (:300-316, :1148); **old single-oracle-key release authority eliminated** — bound TRION key is PAUSE-only (:55-63, :167-172), no dev fallback (NoEpochRegistered before epoch 1, :948) | n/a (cargo not run — static) | **VERIFIED** |
| **Move** | `release_escrow` — contracts/move/sources/btcp_escrow.move:439-467 / `release_escrow_with_sigs` :470-576+ | Canonical cert codec contracts/move/sources/canonical_cert.move (346-byte payload :63, field readers :180+, `verify_structure` :320-337, family-2 Ed25519 over RAW P :96, sha3-256 cert hash :312-313); §6 steps 1-6 in `trion_epoch_registry::verify_certificate` (trion_epoch_registry.move:343-407+, `signature_verify_strict` native); binding incl. BCS-escrow-id, route, intent, entity, chains, destination, amount (:532-558+); nonce/consumed (:478-496, §8.2); **relayer `coherence_verified` flag eliminated** (header :10-37 — relayer retains only safe-direction authority, release permissionless, `verify_coherence` entry removed) | n/a (static) | **VERIFIED** |
| **TON** | `release_escrow` op 0x02 — contracts/ton/escrow.fc:481-694 (permissionless, :45-47) | **CHKSIGNU** via `check_signature` (stdlib.fc:24, asm "CHKSIGNU") over BE32(cell_hash(P-root)) (escrow.fc:575, :616) against registered ed25519 pubkeys; epoch **dict in escrow storage** (ref 1, :75-77, registry entry :135-146); **forward-only registration** — `epoch <= current_epoch + 1` (:794) and already-registered epoch immutable (:800-801); weight quorum recomputed from registered weights (:632-635, quorum tiers :333-339); binding tuple (:643-651); nonce/consumed dict + idempotent resubmit (:653-666); settlement CEI (:677-693); oracle.fc honestly re-scoped as non-certificate route store (:33-45) | `node contracts/ton/cell_layout.test.js` **PASS — 37 layouts/bodies verified** (all cells ≤1023 bits) | **VERIFIED** |
| **NEAR** | `submit` certificate path — contracts/near/src/trion_oracle.rs (§6 walk :560-669) | **`env::ed25519_verify`** at trion_oracle.rs:587-592 (family 2, raw P); epoch registry LookupMap `(epoch, validator_id)` (:65, :321, register_epoch :359-427); envelope weight-claim cross-check (:582-586); u128 tier quorum (`quorum_met` :284) from registered D_consensus (:596-601); etch-or-match binding incl. settlement tuple (:603-623); nonce + conflict evidence (:625-645); `certificate_hash` sha3-256 (:270). **No NEAR escrow release entrypoint exists in contracts/near** (module set is oracle/route/gate/token/staking, lib.rs:9-20) — verdict consumption is oracle-record-side | n/a (static) | **PARTIAL** (oracle-side full §6 VERIFIED; no escrow value-movement path on NEAR) |
| **Cairo / Starknet** | `release_escrow(escrow_id, cert, sigs)` — contracts/starknet/src/btcp_escrow.cairo:80-83 (caller-coherence entrypoint REMOVED :20-31) | **felt-chunked family-3**: 346 B → 12 felts + Poseidon `stark_digest` (trion_certificate.cairo:343-358, chunking parity with py `stark_felt_chunks()`); **ECDSA** `starknet::ecdsa::verify_ecdsa_signature` (:363-370); check_structure range discipline (:209-337); u128 wrap-proof L4.2 quorum (:372-388); epoch registry + grace (trion_epoch_registry.cairo); binding vs escrow record incl. settlement tuple (btcp_escrow.cairo:27, release body); consumed_nonce/digest maps (:198-207); ExecutionGate quorum-gated publication: contracts/cairo/src/trion_execution_gate.cairo `publish_signal` requires family-3 quorum (:6-14, :48, :62 — legacy registered-validator-caller authority removed) | n/a (static; exercised by tests/contracts/test_btcp_escrow_cairo.py — passing) | **VERIFIED** |
| **PVM / ink!** | (no certificate release path) | **Honesty marker present**: `PRODUCTION_STATUS: "RESEARCH_NON_PRODUCTION"` — contracts/pvm/legacy_oracle.rs:73-77 (+ :2, :261, `is_oracle_of_record()` always false :62); cert verification explicitly NOT implemented (:31-46, both families unavailable); pinned by tests/contracts/test_pvm_oracle.py | n/a | **ABSENT (by honest design — marker VERIFIED)** |

**Headline claim status:** "every VM release path verifies the canonical certificate against a per-epoch registry with diversity-weighted quorum" holds for EVM/SVM/Move/TON/Cairo, holds on the oracle side for NEAR, and is explicitly a verdict-consumption design for Vyper (per the spec's own §7 table) and an honest non-implementation for PVM.

## 2. State machine conformance (§22, docs/protocol/BTCP_STATE_MACHINE.md)

Doc arithmetic verified: **26 states** = M1 8 + M2 6 + M3 4 + M4 4 + M5 4 (BTCP machines); **33 transitions** = M1 R1–R9 (9) + M2 E1–E7 (7) + M3 (3) + M4 (3) + M5 (3) + TRION T1–T8 (8). Counting convention is mixed (BTCP states, BTCP+TRION transitions) — the numbers reconcile only under that convention.

M2 escrow states per tier:

| Implementation | States present | vs claimed 6-state M2 (IDLE/HOLDING/PENDING_AKASHIC/RELEASED/REVERTED/EMERGENCY_REVERTED) |
|---|---|---|
| Python `EscrowState` — core/btcp/escrow_monitor.py:47-53 | all 6 (+ RevertReason 7, :56-63) | **conformant** |
| Solidity `enum State` — BTCPEscrow.sol:105-112 | all 6 (+ RevertReason 7, :115-123) | **conformant** |
| Cairo starknet — btcp_escrow.cairo:146-149 | HOLDING/RELEASED/REVERTED/EMERGENCY_REVERTED (4) | subset — no IDLE/PENDING_AKASHIC |
| Vyper — BTCP_ESCROW.vy:64-67 | IDLE/HOLDING/RELEASED/REVERTED (4) | subset — no PENDING_AKASHIC/EMERGENCY_REVERTED (documented two-state design) |
| SVM — btcp_common/src/lib.rs:171-176 | Holding/Released/Reverted/EmergencyReverted (4) | subset |
| Move — btcp_escrow.move:118-122 | HOLDING/PENDING_AKASHIC/RELEASED/REVERTED/EMERGENCY_REVERTED (5) | subset — no IDLE (record existence = locked) |
| TON — escrow.fc STATE_* consts | HOLDING/RELEASED/REVERTED/EMERGENCY (get_methods :838-865) | subset |

Terminal freeze verified everywhere: Solidity requires `state == HOLDING || PENDING_AKASHIC` on release (:366-369, :747) and terminal states have no outgoing transitions; Vyper `state == HOLDING` guards (BTCP_ESCROW.vy:199, :263); Move terminal no-op/same-hash-only or abort (:485-496); TON `state == STATE_HOLDING` (:674); Cairo `state == HOLDING` (:588, :678, :758); py returns False on terminal sources (escrow_monitor.py:245, :280, :300+).

RESURRECTED is **not** an escrow (M2) state anywhere — it is an intent-level status (BTCPIntent.sol `Status {…RESURRECTED}`, contracts/svm/programs/btcp_common/src/lib.rs `IntentStatus::Resurrected` with FAILED→RESURRECTED legal, :171-176) and exists on-chain (EVM/SVM/Cairo intent contracts) but **not** in py `RouteStatus` (core/btcp/orchestrator.py:77-87 — 8 states, no RESURRECTED). M1 route machine: 8 states in py, 7 on-chain intent (no PROOFS_GENERATED/DEST_EXECUTED split, adds RESURRECTED) — documented Part III, minor naming drift.

## 3. Attack matrix (throwaway eth-tester/py-evm harness, /tmp/sweepc/attack_matrix.py)

Real `contracts/solidity` contracts compiled solc 0.8.24 viaIR, deployed on eth_tester (chainid pinned 1), 5-validator tier-1 epoch (w=800000 each, total 4e6) + 7-validator tier-2 epoch. Release submitted by the **attacker** account (permissionless path).

| # | Attack | Expected | Actual (revert reason) | Verdict |
|---|---|---|---|---|
| A1 | Release on never-locked escrow | REVERT | REVERTED: `ESCROW_NOT_FOUND` | REVERTED |
| A2 | Release without G1 settlement check | REVERT | REVERTED: `SETTLEMENT_NOT_VERIFIED` | REVERTED |
| A3 | Forge quorum with 1 validator (batch=1) | REVERT | REVERTED: `BELOW_MIN_SIGNERS` | REVERTED |
| A4 | Sub-quorum weight batch (3/7 signers, tier-2 0.75 bar; 1.5e6 of 3.5e6) | REVERT | REVERTED: `WEIGHT_QUORUM_UNMET` | REVERTED |
| A5 | Forged envelope diversity claim (1e6 vs registered 8e5) | REVERT | REVERTED: `ENVELOPE_WEIGHT_CLAIM_MISMATCH` | REVERTED |
| A6 | Certificate destined for foreign chain (dest_chain=999 vs chainid 1) | REVERT | REVERTED: `CERT_DEST_CHAIN_NOT_THIS_CHAIN` | REVERTED |
| A7 | Expired certificate (ttl=60 s, issued 10 000 s ago) | REVERT | REVERTED: `CERT: expired` | REVERTED |
| A8 | Certificate bound to wrong route | REVERT | REVERTED: `CERT_ROUTE_MISMATCH` | REVERTED |
| A9 | Settlement-tuple substitution (cert pays attacker address) | REVERT | REVERTED: `CERT_DESTINATION_MISMATCH` | REVERTED |
| A10 | Legit release then double release / cert replay | settle once; replay REVERT | first SETTLED, paid exactly 1 ETH once; replay REVERTED: `NOT_RELEASABLE` | REVERTED |
| A11 | Re-bind epoch registry (downgrade) | REVERT | REVERTED: `REGISTRY_ALREADY_BOUND` | REVERTED |
| A12 | Re-bind TRION oracle after first bind | REVERT | REVERTED: `ORACLE_ALREADY_BOUND` | REVERTED |
| A13 | Bind oracle lacking `minRouteAttestations` view (EOA / registry address) | REVERT at bind time | REVERTED (fail-closed, empty reason data — cosmetic) | REVERTED |
| A14 | Oracle certificate replay (same nonce+digest) | no-op (idempotent) | accepted as no-op — no new record, no settlement | IDEMPOTENT-OK |
| A14b | Conflicting certificate at same (epoch, escrow, nonce) | rejected + evidence | conflicting cert NOT recorded (binding unchanged); `certificateConflictRecorded=true`, both digests stored, `CertificateEquivocation` event emitted | DEFENDED (fail-closed) |
| A14c | Release with the FIRST cert after conflict evidence | settles with accepted verdict | SETTLED (the accepted verdict is still consumable; the conflicting one is not) | as specified |

**Total: 16 attempted → 16 correctly defended / 0 EXPLOITED.** Registry conformance also caught an accidental mismatch during harness bring-up (`VALIDATOR_COUNT_MISMATCH` when the cert claimed a wrong validator_count) — extra confirmation of H-01/H-03 checks.

## 4. Binding chain (§23)

- **intent → route → escrow → BH**: lock-time binding tuple stored (SVM `Escrow` stores anchor_bh/execution_bh/intent_hash at lock, lib.rs:180-211; Move `Escrow` resource :188-212; EVM escrow carries routeId/entityId, cert carries intentHash/anchorBh/executionBh checked against what the VM stores — EVM checks escrow_id/route_id/entity_id/tuple (BTCPEscrow.sol:480-497), Move checks all 10 fields incl. intent_hash/anchor/execution (btcp_escrow.move:532-568)).
- **routeBinding / anchorBH == escrowId in release paths**: EVM legacy `_consensusGate` BTCPEscrow.sol:252 (`ORACLE_ROUTE_NOT_BOUND_TO_ESCROW`); EVM canonical — escrow looked up BY `escrowIdOf(payload)` (:364) + `CERT_NOT_BOUND_TO_ESCROW` (:480); Vyper BTCP_ESCROW.vy:221; SVM lib.rs:1114+1127; Move :537-539; TON escrow.fc:643-644; Cairo release body binding; NEAR etch-or-match :608-622.
- **Settlement tuple in certificate digest**: destination (offset 165) + amount (offset 197) are inside the signed 346-byte P (CanonicalCertificate.sol:87-88, decode :185-186); checked against escrow's own state at release: EVM BTCPEscrow.sol:483-489 (with 12-zero-byte padding discipline), Move :555-558, TON :647-648, SVM :1118-1122, NEAR :617-618, Cairo settlement-tuple binding (btcp_escrow.cairo:27). Attack A9 confirms on a live EVM.
- **Dest-chain gate (1270c5c)**: EVM full-width comparison `uint256(CanonicalCertificate.destChainOf(payload)) == block.chainid` (BTCPEscrow.sol:494-497); SVM `cert.dest_chain == config.self_chain` (lib.rs:1126); Move E_DEST_CHAIN_MISMATCH (:551-554); TON binding; adversarial `test_high_chainid_truncation_aliases_registry_chain`, `test_chain_id_masking_aliases_2p32_offset`, `test_cert_for_foreign_dest_chain_settles_here` all pass. Attack A6 confirms live.
- **Replay firewall**: nonce scope (epoch, escrow_id) per tier (EVM :304, SVM :300-316, TON consumed_dict, NEAR highest_nonce, Cairo consumed_nonce) + terminal-state freeze as the exactly-once guard (A10/A14).

## 5. Batteries run (all pass in this environment)

| Battery | Result |
|---|---|
| `PYTHONPATH=. python -m pytest tests/contracts -q` | **52 passed** (3.24 s) — includes sol/vy/svm/move/ton/near/cairo/pvm contract tests + source-sync |
| `pytest tests/adversarial/test_red_team_wave4.py test_red_team_pass3.py test_final_red_team.py -q` | **81 passed** (32.98 s) — certificate attack batteries (cross-chain cert confusion, double-pay across deployments, tier-1 2/3 boundary, replay, akashic-flip, quorum/chainid masking) |
| `pytest tests/unit/test_certificate_domain_separation.py -q` | **68 passed** — 346-byte golden payload + family digests |
| `node contracts/ton/cell_layout.test.js` | **PASS: 37 layouts/bodies verified** |
| Throwaway attack matrix (/tmp/sweepc/attack_matrix.py + attack_reasons*.py) | 16/16 defended, 0 exploited (results: /tmp/sweepc/attack_results.json) |

## 6. Tokenomics (Vyper TRIONToken.vy, vyper 0.3.10 compiles)

- Genesis split **15% public-good / 85% treasury-allocator** enforced in constructor (TRIONToken.vy:183-193, `PUBLIC_GOOD_BPS=1500` :83).
- **Burn-on-use fee**: 0.05% per transfer (TRANSFER_FEE_BPS=5 :89); 15% of fee → public good, 85% burned, supply decremented ( :209-230). Fixed supply 1e9×1e18 minted once (:79, :186); `governance_mint` always reverts (:292-301); 50/50 insurance/burn slash split (:317-335). All claims verified.

## 7. Divergences (severity)

1. **[Medium — doc-consistent but headline overstates]** Vyper tier has **no canonical-certificate codec**; release() consumes the Solidity oracle's `routeBinding` verdict + dynamic quorum. CANONICAL_CERTIFICATE.md §7 (line 422) says exactly this, but the blanket claim "every VM release path verifies the canonical certificate" is only true for 5 of 8 tiers.
2. **[Medium — known Wave 2 item, still open]** Solidity `lockEscrow` accepts **caller-chosen `escrowId` and `minCoherence` with no protocol floor** (onlyRelayer; BTCPEscrow.sol:585-600 checks `minCoherence <= 1e6` but no ≥0.55 floor — INV-003 floor enforced in py/Move/SVM but NOT on the EVM escrow). A relayer can lock with minCoherence=0, weakening only the escrow-local tightening (the cert's own threshold/quorum gates still apply).
3. **[Low]** NEAR has **no escrow value-movement path** — certificate verification is oracle-record-side only (trion_oracle.rs); M2 consumption on NEAR is absent (matches state doc Part III).
4. **[Low]** M2 state-space narrower on non-EVM tiers (Vyper/SVM/Cairo 4 states, Move 5) vs EVM/py 6 — PENDING_AKASHIC/EMERGENCY_REVERTED missing on some tiers; documented in Part III but not invariant-identical.
5. **[Low]** Intent status drift: on-chain intents (EVM/SVM/Cairo) add **RESURRECTED**; py RouteStatus (8 states) has none and splits PROOFS_GENERATED/DEST_EXECUTED that contracts don't — M1 projection is nominal, not exact.
6. **[Info]** `setTRIONOracle` bind-time interface check against a code-less address reverts with **empty revert data** (no reason string) — fail-closed holds (A13), cosmetic only.
7. **[Info]** EVM legacy `releaseEscrow` keeps the documented trusted-relayer bootstrap mode when the oracle is unbound (dev-only opt-out, one-way binding); the canonical path has no fallback (registry must be bound).
8. **[None]** PVM honestly marked `RESEARCH_NON_PRODUCTION` (legacy_oracle.rs:73-77) — no false claims found in any tier's comments; where a tier lacks the mechanism, the code says so.

## 8. Artifacts

- Attack matrix script + results: `/tmp/sweepc/attack_matrix.py`, `/tmp/sweepc/attack_reasons.py`, `/tmp/sweepc/attack_reasons2.py`, `/tmp/sweepc/attack_results.json` (throwaway, outside repo).
- Compiled artifacts (for reference): `/tmp/sweepc/evm_compiled.json`, `/tmp/sweepc/*.vy.json`.
- No repository files were modified; no git state changed.
