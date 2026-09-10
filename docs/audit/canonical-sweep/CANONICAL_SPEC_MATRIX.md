# CANONICAL SPEC MATRIX — Master-sweep re-verification (2026-09-04)

**Primary artifact:** `docs/audit/CANONICAL_SPEC_MATRIX.md` (the repo's own
107-row normative-requirement matrix, produced by the prior 83-commit
reconstruction).

**This sweep's re-verification (SWEEP-D, fresh eyes, seed 42):**
- Parsed row count: **exactly 107** (53 COMPLIANT / 37 PARTIAL / 8 mixed /
  5 RESEARCH-ONLY / 1 MISSING / 1 DEVIANT / 2 cross-refs).
- 20 requirements re-verified at code level (10 random + 10 highest-security):
  **17 CONFIRMED, 3 CONFIRMED-WITH-NUANCE, 0 CONTRADICTED, 0 NOT-FOUND.**
  All 3 nuances are the matrix lagging *behind* already-landed fixes
  (AWA freeze tests exist; conservation audit exists; shadow persistence
  labeled) — conservative direction.
- K1–K22 spec-conflict banners: commit 713c42c is pure-insertion (33+/0−);
  6/6 spot-checked banners exist and resolve to the recorded hierarchy ruling.

**Hierarchy of truth (enforced):** WHITEPAPER_MD (Mar-2026 semantics) >
WHITEPAPER_V2 (Feb-2026, v1 BH field set) > BTCP_SPEC (Apr-2026) > L0–L9
drafts (superseded sections banner-marked) > implementation > tests > docs.
Marketing has zero authority. `upload/` whitepaper is NOT part of this repo's
history (external org document).

**Formula conformance (re-executed this sweep):**
`tests/master_formula_verification.py` → **105 passed / 0 failed / 0 skipped,
"ALL FORMULAS ENFORCED AS SPECIFIED"** (the prior "1 documented" item was the
PQC-env skip; this environment has PQC libs installed, so it ran and passed).
`tests/invention_verification.py` → 44/44. Golden test → 30/30
(129 chains / 18 VMs / 105 formulas / 36 inventions).

**Post-sweep updates to the matrix state:**
- CLOSED this sweep: entity-id write/read loop (L0.2/L3.1), AWA gate coverage
  of zg surfaces (MD §17), BH §9 block-hash substitution (4 indexers), TS §6
  entity rule, certificate-doc fleet-signing overstatement, BIBL snapshot demo
  labeling.
- STILL OPEN (carried): CUT commitment py↔rust byte-format divergence (§17),
  EVM lockEscrow coherence floor, certificate contract-address binding,
  AWA `/api/v1/governance/awa` demo inputs (harness values, labeled).

Full row-level detail: see the primary artifact and `SWEEP-D.md` §2.
