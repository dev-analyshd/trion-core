# STATE MACHINE SPEC (§22 — Master Sweep 2026-09-04)

**Primary artifact:** `docs/protocol/BTCP_STATE_MACHINE.md` (26 states /
33 transitions). **This sweep's conformance check (SWEEP-C):** arithmetic
reconciles; the M2 6-state escrow core conforms on EVM + Python; Vyper/SVM/
Cairo carry 4-state subsets; Move 5. RESURRECTED exists at intent level
only (absent from python RouteStatus — consistent with the doc).

## Escrow core (EVM BTCPEscrow.sol — verified by 16/16 attack matrix)

```
IDLE ──lock──► HOLDING ──verify+cert──► PENDING_AKASHIC ──release──► RELEASED
                 │  timeout/grief             │ timeout                    ▲
                 ▼                            ▼                           │
             REVERTED ◄──cascade──── EMERGENCY_REVERTED (7d, anyone)      │
                 (funder refunded; CEI; amount cleared; accounting        │
                  decremented fail-closed on underflow)                   │
```

| State | Valid entry | Authorized actors | Forbidden (verified reverting) |
|---|---|---|---|
| IDLE | deploy | — | release (ESCROW_NOT_FOUND) |
| HOLDING | lock (escrowId==anchorBH bound) | relayer/anyone (value-free) | release without cert (SETTLEMENT_NOT_VERIFIED / BELOW_MIN_SIGNERS / WEIGHT_QUORUM_UNMET) |
| PENDING_AKASHIC | verify + quorum cert | registered validators via cert | expired flip (984087e closed) |
| RELEASED | valid cert, TTL fresh, this-chain | permissionless caller | double release / replay (NOT_RELEASABLE — funds moved exactly once) |
| REVERTED | timeout / cascade | anyone / system | re-lock (terminal, amount=0, sentinel=escrow_id) |
| EMERGENCY_REVERTED | 7d emergency window | anyone | bypass before 7d (BTCP: emergency not yet) |

## Intent / route machines (Python, SQLite-persisted — restart-durable, verified)

- Intent: REGISTERED → MATCHED → EXECUTING → SETTLED / FAILED → RESURRECTED
  (nonce atomic across processes — 400/400; 49f368e verified live).
- Route: 7 types × status machine (9e2b84f) — illegal status jumps rejected;
  off-registry routes rejected (P-PY-03).

**Persistence/recovery (§24, LIVE-2):** restart roundtrip exact
(escrow/route/nonce continuation); 8×50 concurrent locks 400/400, integrity
ok; partial/garbage rows skipped honestly; corrupt FAISS → fail-loud boot.
