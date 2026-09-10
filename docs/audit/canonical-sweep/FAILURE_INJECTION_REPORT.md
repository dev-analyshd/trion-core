# FAILURE-INJECTION REPORT (§28 — Master Sweep 2026-09-04)

Full matrix with commands: `RED-4.md` §Part 3.

| Broken dependency | Affected path | Behavior | Verdict |
|---|---|---|---|
| Oracle unregistered / no verdict | escrow release | revert SETTLEMENT_NOT_VERIFIED | FAIL-CLOSED |
| FAISS unavailable | /readyz, /planes/all (documented gates) | 503; other endpoints degrade honestly | FAIL-CLOSED |
| Ledger/store missing | BTCP state load | loud import/startup error | FAIL-LOUD (by design) |
| Registry file unreadable | chain derivation | loud import error, never stale numbers | FAIL-LOUD (by design) |
| KMS provider bogus | relayer boot | FATAL exit | FAIL-CLOSED |
| Quorum unmet (3/7 tier-2) | release | WEIGHT_QUORUM_UNMET | FAIL-CLOSED |
| Freshness expired | release | CERT: expired | FAIL-CLOSED |
| Certificate weight-claim mismatch | release | ENVELOPE_WEIGHT_CLAIM_MISMATCH | FAIL-CLOSED |
| Wrong dest-chain certificate | release | CERT_DEST_CHAIN_NOT_THIS_CHAIN | FAIL-CLOSED |
| Route mismatch | release | CERT_ROUTE_MISMATCH | FAIL-CLOSED |
| Same-nonce conflicting cert | attestation | rejected + equivocation evidence | FAIL-CLOSED |
| Corrupt SQLite row (load) | state load | row skipped, stderr message | FAIL-CLOSED (honest) |
| Corrupt FAISS index (boot) | service | exit 1 at import | FAIL-LOUD (by design) |
| Control (valid certificate) | release | settles exactly once | PASS |

**13/13 fail-closed, 2 fail-loud by design, 0 silent-accept paths.**
