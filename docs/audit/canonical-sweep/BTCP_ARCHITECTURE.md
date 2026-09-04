# BTCP ARCHITECTURE (canonical reconstruction, verified 2026-09-04)

BTCP = **the action layer**: turns behavioral evidence into authorized
cross-chain settlement without bridges. The 6-step orchestration:

```
1 INTENT     §4.1 field set (action, value, max_total_gas, min_finality,
             min_NL_score×1000, chain_pref, privacy, btcp_version, nonce,
             behavioral_proof_root) — parity 10/10 across the 5
             representations (py modules.py ↔ rust bitp_matcher.rs ↔ tests)
2 BIBL       intent analysis consuming real TRION evidence (NL, gas CI_95,
             BRT window, jurisdiction; BEO witnesses bound to the live
             Akashic ledger — caller-supplied fields labeled)
3 ROUTE      7 RouteTypes; status machine enforced (9e2b84f); registry-bound
             verification — off-registry routes rejected (P-PY-03 closed)
4 ESCROW     behavioral escrow: lock under anchorBH==escrowId binding,
             PENDING_AKASHIC window, timeout revert, 7-day emergency exit,
             cascade reverts; CEI + EIP-2 s-guard (EVM)
5 PROOF/     canonical 346-byte certificate (TRION-CERT-V1, domain-
  ATTEST     separated, settlement-tuple-bound, second-based TTL,
             HHI≤4000, AWA bit) verified against a forward-only per-epoch
             validator registry with diversity-weighted quorum
             (w_j=s_j·d_j×1e6, threshold from registry state — never from
             the proof) — on EVERY release-capable VM tier (SWEEP-C:
             EVM/SVM/Move/TON/Cairo VERIFIED; Vyper oracle-verdict path;
             NEAR partial; PVM honest non-production)
6 EXECUTE    release only with a valid certificate for THIS chain/escrow/
  SETTLE     tuple; idempotent nonce; destination fixed at lock; failure
             classification + dispute resolution (72h window xfail-registered)
```

**No-bridge settlement paths:** BITP direct match (self-match rejected,
expiry-aware, proof-root+nonce-bound commitment), netting engine,
LiquidityOcean §6.1 weighted-NL routing, gas abstraction, IAP.

**The release authority chain (the security core, verified by 16/16
attack matrix + 6/6 exploit reproductions on pre-fix code):**
registry(epoch) → certificate(quorum) → escrow binding → destination.
Single relayers/owners can pause but never release value; emission of truth
is AWA-gated; execution of value is certificate-gated.

**Open items:** CUT commitment py↔rust byte-format (needs one canonical
ruling), EVM lockEscrow coherence floor, cert contract-address binding
(same-tuple cross-deployment replay — MED-LOW, documented), Vyper direct
cert codec (spec §7 itself defers).
