# THREAT MODEL + RED TEAM / REGRESSION / FAILURE-INJECTION RESULTS (2026-09-04)

## STRIDE-style summary

| Threat | Vector | Status |
|---|---|---|
| Spoofing | forged certs, validator impersonation, XFF spoofing, GET-write | all closed & pinned |
| Tampering | BH strand tamper, ledger corruption, cert payload mutation | complementarity + digest + tuple binding |
| Repudiation | equivocation | nonce ordering + equivocation evidence event |
| Information disclosure | unlabeled synthetic truth, caller-supplied masquerade | labeled (65+ flags; route fields labeled) |
| Denial of service | freeze-liveness, griefing (1-wei lock front-run) | funds fail-closed revert to funder; documented LOW |
| Elevation | owner/relayer release authority | eliminated on every release-capable tier (16/16 matrix) |

## SECURITY REGRESSION REPORT (§26 — originals reproduced, then re-blocked)

All six historical exploits were re-implemented against `git show`-extracted
PRE-FIX code, executed (EXPLOITED confirmed), then re-run on current HEAD:

| # | Exploit | Old code | Current HEAD |
|---|---|---|---|
| 1 | Route-spoof (unrelated safe route releases 2 ETH) | **EXPLOITED** | ORACLE_ROUTE_NOT_BOUND_TO_ESCROW / CERT_ROUTE_MISMATCH |
| 2 | svm-native no-authority RELEASE | **EXPLOITED (documented — crate deleted)** | crate absent; SVM release = cert-gated |
| 3 | NaN forges max magnitude | **EXPLOITED (1e9 nano)** | ValueError |
| 4 | Unauthenticated GET write (publish + DA) | **EXPLOITED** | 401 |
| 5 | Vyper release after timeout | **EXPLOITED (1 ETH past expiry)** | BTCP: escrow expired → refund |
| 6 | Cross-process nonce collision | **EXPLOITED (dup nonce, dropped row)** | 400/400 distinct (BEGIN IMMEDIATE) |

**Verdict: 6/6 CLOSED, each failing for the documented correct reason.**

## RED TEAM PASS 4 (independent — beyond the committed batteries)

11 fresh attacks: **9 defended, 2 findings**:
- **RED-4-F1 (MEDIUM): AWA freeze bypass on zg/storage/store, zg/sync,
  zg/compute/infer** → **FIXED d9f8d8e** + regression tests (both methods,
  5 surfaces, open-gate control).
- **MED-LOW (open, documented): same valid certificate settles two
  same-chain escrow deployments with identical tuples** (cert has no
  contract-address binding). Remediation path recorded: add this-chain
  address to the certificate digest (mirrors the dest-chain gate).

Defended live: epoch equivocation (grace-bounded), TTL exact-boundary,
weight-truncation parity, malformed fuzz (zero 5xx), SQLite corruption
(honest skip), FAISS corruption (fail-loud), cert replay across escrows,
XFF spoofing (ignored), settlement-check front-run (relayer-gated,
write-once).

## FAILURE-INJECTION REPORT (§28)

13/13 fail-closed; 2 fail-loud by design; control cert settles. Full
matrix in RED-4.md §Part 3. Committed batteries re-run this sweep:
adversarial **215/215** (with PQC installed), contracts 52/52, golden
134/134 + 30/30, unit **1031+3 new** passing.
