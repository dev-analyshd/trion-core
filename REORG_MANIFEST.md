# REORG_MANIFEST — ZK Reorganization (P0)

> **FIRST LAW:** No file moves, deletes, or edits until this manifest is committed.
> Every line carries a disposition: MOVE / DELETE / ARCHIVE / KEEP with reason.

## 0. Inventory Summary

| Tree | Tracked files | Description |
|---|---|---|
| `zk-circuits/` | 35 | Circom circuits (5), commitments (7), tests (12), README, package.json |
| `zk-starknet/` | 19 | Cairo circuits (8), contract subpackage (6), Scarb configs (2), evidence (3) |
| `docs/zk/` | 10 | BZK mission documentation (EVIDENCE) |
| `docs/zk_starknet/` | 2 | ZK-Starknet mission documentation (EVIDENCE) |
| `contracts/zk/` | 7 | Solidity ZK verifier contracts (EVM-compat artifacts) |
| `core/zk/` | 6 | Python ZK integration (awa_freeze, chameleon_tiers, etc.) |
| `hardhat/contracts/zk/` | 5 | Hardhat twin contracts (EVM-compat artifacts) |
| `docs/proofs/` (zk-related) | 9 | Proof JSONs and reports (EVIDENCE) |

**Scarb projects (5 total — 3 are non-ZK, 2 are ZK):**
| Project | Name | ZK? | Disposition |
|---|---|---|---|
| `chains/starknet/Scarb.toml` | `trion_oracle` | NO | KEEP in place (non-ZK Cairo contracts) |
| `contracts/cairo/Scarb.toml` | `trion_cairo` | NO | KEEP in place (old edition non-ZK) |
| `contracts/starknet/Scarb.toml` | `trion_oracle` | NO | KEEP in place (non-ZK, same name — NOT a ZK duplicate) |
| `zk-starknet/Scarb.toml` | `trion_zk_starknet` | YES | MOVE to `zk/stark/Scarb.toml` |
| `zk-starknet/contract/Scarb.toml` | `zk_verifier_contract` | YES | MOVE to `zk/stark/contract/Scarb.toml` |

**Import edges (5 sites import `from zk import ...`):**
| File | Line | Imports |
|---|---|---|
| `core/btcp/orchestrator.py` | 32 | `ZKProofSystem, IntentWitness, ComplementarityWitness, BehavioralCredentialWitness, TravelRuleWitness, IAPShareWitness, CircuitType` |
| `scripts/tests/integration_test.py` | 203 | `ZKProofSystem, IntentWitness, ComplementarityWitness` |
| `tests/adversarial/test_adversarial_suite.py` | 145 | `merkle_root, ZKProofSystem` |
| `tests/invention_verification.py` | 250 | `ZKProofSystem, IntentWitness` |
| `scripts/init_trion.py` | 200 | String references (not import) |

**Facade decision:** Create `zk/facade/__init__.py` containing the `ZKProofSystem` class
(currently stubbed in `core/btcp/orchestrator.py`). Thin `zk/__init__.py` re-exports
from facade. This keeps all `from zk import ...` sites working without edits.
The orchestrator stub is removed (replaced by the facade).

---

## 1. GROTH16 TREE → `zk/groth16/`

Source: `zk-circuits/`

| Source path | Target path | Disposition | Reason |
|---|---|---|---|
| `zk-circuits/README.md` | `zk/groth16/README.md` | MOVE | Root ZK circuits README |
| `zk-circuits/package.json` | `zk/groth16/package.json` | MOVE | snarkjs/circom scripts |
| `zk-circuits/zk_intent_commitment/` | `zk/groth16/zk_intent_commitment/` | MOVE | S1 circuit (3 files) |
| `zk-circuits/zk_complementarity_proof/` | `zk/groth16/zk_complementarity_proof/` | MOVE | S1 Phase 2 circuit (3 files) |
| `zk-circuits/zk_iap_share_proof/` | `zk/groth16/zk_iap_share_proof/` | MOVE | S2 circuit (3 files) |
| `zk-circuits/zk_travel_rule/` | `zk/groth16/zk_travel_rule/` | MOVE | S3 circuit (3 files) |
| `zk-circuits/zk_behavioral_credential/` | `zk/groth16/zk_behavioral_credential/` | MOVE | S4 circuit (3 files) |
| `zk-circuits/commitments/` | `zk/groth16/commitments/` | MOVE | Commitment layer (7 files) |
| `zk-circuits/tests/` | `zk/groth16/tests/` | MOVE | Z-battery tests (12 files, EVIDENCE) |

---

## 2. STARK TREE → `zk/stark/`

Source: `zk-starknet/`

| Source path | Target path | Disposition | Reason |
|---|---|---|---|
| `zk-starknet/Scarb.toml` | `zk/stark/Scarb.toml` | MOVE | Main ZK Cairo workspace |
| `zk-starknet/Scarb.lock` | (delete) | DELETE | Lockfile — regenerates on `scarb build` |
| `zk-starknet/src/hash_dna.cairo` | `zk/stark/src/hash_dna.cairo` | MOVE | Hash_DNA Cairo module |
| `zk-starknet/src/lib.cairo` | `zk/stark/src/lib.cairo` | MOVE | Library entry point |
| `zk-starknet/src/s1_intent_commitment.cairo` | `zk/stark/src/s1_intent_commitment.cairo` | MOVE | S1 Cairo circuit |
| `zk-starknet/src/s2_iap_share.cairo` | `zk/stark/src/s2_iap_share.cairo` | MOVE | S2 Cairo circuit |
| `zk-starknet/src/s3_travel_rule.cairo` | `zk/stark/src/s3_travel_rule.cairo` | MOVE | S3 Cairo circuit |
| `zk-starknet/src/s4_sensing_oracle.cairo` | `zk/stark/src/s4_sensing_oracle.cairo` | MOVE | S4 Cairo circuit |
| `zk-starknet/src/s5_birp.cairo` | `zk/stark/src/s5_birp.cairo` | MOVE | S5 Cairo circuit |
| `zk-starknet/src/zk_verifier.cairo` | `zk/stark/src/zk_verifier.cairo` | MOVE | ZK verifier contract source |
| `zk-starknet/contract/Scarb.toml` | `zk/stark/contract/Scarb.toml` | MOVE | Contract subpackage config |
| `zk-starknet/contract/Scarb.lock` | (delete) | DELETE | Lockfile — regenerates |
| `zk-starknet/contract/src/lib.cairo` | `zk/stark/contract/src/lib.cairo` | MOVE | Contract source (copy of zk_verifier) |
| `zk-starknet/contract/r4_proofs.py` | `zk/stark/contract/r4_proofs.py` | MOVE | On-chain proof script (EVIDENCE) |
| `zk-starknet/contract/r4_onchain_proofs.json` | `zk/stark/contract/r4_onchain_proofs.json` | MOVE | On-chain proof results (EVIDENCE) |
| `zk-starknet/contract/zk_verifier_deployment_result.json` | `zk/stark/contract/zk_verifier_deployment_result.json` | MOVE | Deployment evidence (tx hash, address) |
| `zk-starknet/contract/zk_verifier.sierra.json` | (delete) | DELETE | Empty artifact (2 bytes: `{}`) — junk; real sierra is in `target/dev/` |
| `zk-starknet/contract/zk_verifier_compiled.sierra` | (delete) | DELETE | Duplicate build artifact — junk |
| `zk-starknet/contract/zk_verifier_compiled.json` | (delete) | DELETE | Duplicate build artifact — junk |

---

## 3. SHARED → `zk/shared/`

New directory. Contents created in P7 (cross-prover parity pins).

| Target path | Disposition | Reason |
|---|---|---|
| `zk/shared/parity_vectors.json` | CREATE (P7) | Canonical vectors for cross-prover parity |
| `zk/shared/test_parity.py` | CREATE (P7) | Parity test that runs in both suites |

---

## 4. FACADE → `zk/facade/`

New directory. Contains the ZKProofSystem class (moved from orchestrator stub).

| Target path | Disposition | Reason |
|---|---|---|
| `zk/facade/__init__.py` | CREATE | ZKProofSystem + witness classes + merkle_root re-export |
| `zk/__init__.py` | CREATE | Thin re-export: `from zk.facade import *` |

**Import fix:** After creating `zk/__init__.py`, all `from zk import ...` sites
resolve automatically. The orchestrator stub (lines 42-89) is removed and
replaced with the facade. No import-site edits needed.

---

## 5. ARCHIVE → `zk/archive/`

| Source path | Target path | Disposition | Reason |
|---|---|---|---|
| (none needed) | `zk/archive/PROVENANCE.md` | CREATE | Documents what was archived and why |

**No files need archiving.** All evidence files stay in their current locations
(`docs/zk/`, `docs/zk_starknet/`, `docs/proofs/`). The only files being deleted
are true junk (lockfiles, empty artifacts, duplicate build outputs). No
superseded circuits or retraction notes need archiving — they're already in
`docs/zk/PHASE9_AGREEMENT_GATE.md` (with retraction notice) and stay there.

---

## 6. EVIDENCE FILES (MUST SURVIVE — NEVER DELETE)

| Path | Count | Status |
|---|---|---|
| `docs/zk/` (10 files) | 10 | KEEP in place — BZK mission evidence |
| `docs/zk_starknet/` (2 files) | 2 | KEEP in place — ZK-Starknet mission evidence |
| `docs/proofs/` (9 zk-related files) | 9 | KEEP in place — proof JSONs and reports |
| `zk-circuits/tests/` (12 files) | 12 | MOVE to `zk/groth16/tests/` — Z-battery evidence |
| `zk-starknet/contract/r4_onchain_proofs.json` | 1 | MOVE to `zk/stark/contract/` — on-chain evidence |
| `zk-starknet/contract/zk_verifier_deployment_result.json` | 1 | MOVE to `zk/stark/contract/` — deployment evidence |
| `zk-starknet/contract/r4_proofs.py` | 1 | MOVE to `zk/stark/contract/` — proof script |
| Worklog entries (`/home/z/my-project/worklog.md`) | N/A | KEEP — outside repo, never touched |

**Evidence set identity check (P3 will verify):** count = 35 items above. After reorg,
same 35 items must exist (some at new paths under `zk/groth16/` and `zk/stark/`).

---

## 7. JUNK TO DELETE (manifest-listed only)

| Source path | Size | Reason |
|---|---|---|
| `zk-starknet/Scarb.lock` | ~3KB | Lockfile — regenerates on `scarb build` |
| `zk-starknet/contract/Scarb.lock` | ~3KB | Lockfile — regenerates |
| `zk-starknet/contract/zk_verifier.sierra.json` | 2 bytes | Empty artifact (`{}`) — real sierra in `target/dev/` |
| `zk-starknet/contract/zk_verifier_compiled.sierra` | ~0 bytes | Duplicate build artifact |
| `zk-starknet/contract/zk_verifier_compiled.json` | ~0 bytes | Duplicate build artifact |
| `contracts/starknet/Scarb.lock` | ~3KB | Lockfile — non-ZK project, not moved but cleaned |

**Total: 6 files deleted. All are build outputs or lockfiles. Zero evidence files deleted.**

---

## 8. NON-ZK FILES THAT STAY IN PLACE

| Path | Reason |
|---|---|
| `contracts/zk/` (7 files) | Solidity ZK verifier contracts — EVM-compat artifacts, stay with contracts/ |
| `core/zk/` (6 files) | Python ZK integration layer — stays with core/ |
| `hardhat/contracts/zk/` (5 files) | Hardhat twin contracts — stay with hardhat/ |
| `chains/starknet/Scarb.toml` | Non-ZK Cairo contracts — stays in place |
| `contracts/cairo/Scarb.toml` | Non-ZK old edition contracts — stays in place |
| `contracts/starknet/Scarb.toml` | Non-ZK contracts — stays in place (name collision is with chains/starknet/, not ZK) |

---

## 9. CI / DOCS PATH UPDATES NEEDED AFTER MOVE

| File | Current path | New path | Update type |
|---|---|---|---|
| `.github/workflows/ci-python.yml` | (no zk paths) | (no change) | None |
| `.github/workflows/ci-typescript.yml` | (no zk paths) | (no change) | None |
| `docs/RUN_IT_YOURSELF.md` | `cd zk-circuits` | `cd zk/groth16` | Text update |
| `docs/RUN_IT_YOURSELF.md` | `zk-circuits/commitments/leakage_grep.sh` | `zk/groth16/commitments/leakage_grep.sh` | Text update |
| `core/btcp/orchestrator.py` | Stub ZKProofSystem (lines 42-89) | Remove stub; import from `zk` package | Code update |
| `tests/unit/test_no_sys_path_hacks.py` | `zk-circuits/tests/z*.py` in allowlist | `zk/groth16/tests/z*.py` in allowlist | Test update |
| `README.md` | `zk-circuits/` references | `zk/groth16/` references | Text update |

---

## 10. DISPOSITION COUNTS

| Disposition | Count |
|---|---|
| MOVE (git mv) | 30 directories/files |
| DELETE (junk) | 6 files |
| ARCHIVE | 0 (no superseded evidence needs archiving) |
| KEEP (in place) | 25+ files (non-ZK, evidence docs) |
| CREATE (new) | 4 files (zk/__init__.py, zk/facade/__init__.py, zk/shared/*, zk/archive/PROVENANCE.md) |

**P0 ACCEPTANCE: manifest committed before any move. ✓**
