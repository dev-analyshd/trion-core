# RED TEAM REPORT — INDEPENDENT PASS 4 (2026-09-04)

Context: three prior committed passes exist (tests/adversarial/test_red_team_*.py,
81 tests). Pass 4 was written fresh, without reading those batteries first,
to attack what they missed. Full detail: `RED-4.md`.

## Fresh attack battery — 11 attempted / 9 defended / 2 findings

Defended (live, on current code): epoch-boundary equivocation (grace-bounded,
SIGNER_NOT_IN_EPOCH_SET / VALIDATOR_EPOCH_INACTIVE) · TTL exact boundary (no
off-by-one) · weight-quorum integer truncation (py encoder ↔ sol verifier
identical flooring; exact-integer tiers; MIN_SIGNERS floor) · malformed-input
fuzz across 6 write endpoints (zero 5xx) · SQLite corrupted rows (honest skip,
stderr) · corrupt FAISS index (fail-loud import exit) · certificate replay
across two escrowIds (binding key + idempotent nonce) · XFF spoofing on rate
limiter (ignored by default; 429s still fire) · settlement-check front-run
(relayer-gated, write-once).

## Findings

1. **RED-4-F1 (MEDIUM) — AWA emission-freeze bypass on
   `/api/v1/zg/storage/store`, `/api/v1/zg/sync`, `/api/v1/zg/compute/infer`:**
   with the gate frozen and a valid key, all three executed external
   publication / subprocess spawn. The earlier P-API-05 fix had covered only
   `zg/da/submit`. **FIXED this sweep (d9f8d8e)** — all three now 503
   `silence:true`; regression tests cover both methods of every surface plus
   an open-gate control.
2. **MED-LOW (open, documented):** one valid certificate can settle two
   same-chain escrow *deployments* carrying an identical settlement tuple
   (2× payment across deployments, not within one contract). The certificate
   digest binds chain/escrow/tuple but not the contract address. Remediation
   recorded (add this-chain address to the digest, mirroring the dest-chain
   gate); flagged for the next contract revision cycle since it changes the
   certificate format.

## Committed battery re-run (this environment, PQC installed)

`tests/adversarial` **215/215 passed** (the prior "1 failure" was the PQC
library gap — environmental, closed here). `tests/contracts` 52/52.
Certificate golden vectors 68/68.
