# SECURITY REGRESSION REPORT (§26 — Master Sweep 2026-09-04)

Method: every historical exploit was re-implemented against `git show`-extracted
PRE-FIX code, EXECUTED to confirm the original compromise, then re-run
identically on current HEAD to confirm it now fails for the correct reason.
Full transcripts: `RED-4.md` (this directory) §Part 1.

| # | Exploit (original commit era) | Pre-fix result | HEAD result | Verdict |
|---|---|---|---|---|
| 1 | Route-spoof: unrelated quorum-safe routeId releases escrow value | 2 escrows / 2 ETH released | `ORACLE_ROUTE_NOT_BOUND_TO_ESCROW`, `CERT_ROUTE_MISMATCH`, `ESCROW_NOT_FOUND`; valid-tuple control still settles | **CLOSED** |
| 2 | svm-native RELEASE: no authority check, caller-supplied coherence | documented EXPLOITED (crate removed) | crate absent from tree; SVM release is certificate-gated (SWEEP-C verified) | **CLOSED** |
| 3 | NaN magnitude → u64-max nano | magnitude_nano = 1e9 forged | `ValueError` (P-PY-01) | **CLOSED** |
| 4 | Unauthenticated GET write (`/api/v1/publish`, `zg/da/submit`) | on-chain publish + DA submission executed | 401; write never reached | **CLOSED** |
| 5 | Vyper release after timeout | fresh verdict paid destination 1 ETH past expiry | `BTCP: escrow expired` → funder refunded | **CLOSED** |
| 6 | Cross-process nonce collision | two subprocesses minted the same nonce; second row silently dropped | distinct nonces, 3/3 rows (atomic BEGIN IMMEDIATE) | **CLOSED** |

**6/6 CLOSED.** No regression found in any previously-fixed class.
