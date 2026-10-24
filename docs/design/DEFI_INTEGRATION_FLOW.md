# DeFi Integration Flow — Design

> End-to-end atomic flow connecting a Bitcoin Taproot vault (L1) to a
> Stacks lending contract (`BTCPLend.clar`), mediated by the TRION
> Coherence Vault (`TRIONCoherenceVaultV5.clar`) and the Publisher
> Network (`publisher-registry-v1.clar`).
>
> Goal: borrower locks BTC, borrows tTRION against it, and — on default —
> the lender receives BTC, with **no committee, no multisig, no signature
> on the release path**, only the DBP preimage and an open relayer market.

Status: Draft — Design Phase. Scope: workflow + state machine +
contract-call sequence + late-repay race resolution. Does not modify the
DBP primitive itself.

---

## 1. Components

| Layer | Contract / UTXO | Role |
|-------|-----------------|------|
| BTC L1 | Vault UTXO (Taproot) | Holds collateralised BTC. Two leaves: release (preimage) + refund (CSV). |
| BTC L1 | Lock / Release / Refund tx | Fund vault / spend Leaf 1 to lender / spend Leaf 2 to borrower. |
| Stacks | `TRIONCoherenceVaultV5.clar` | Vault registry, preimage publish, state machine. |
| Stacks | `BTCPLend.clar` | Lending accounting (deposits, borrows, interest, liquidation). |
| Stacks | `publisher-registry-v1.clar` | Publisher set, stake, bounty escrow, slash. |
| Stacks | `BTCSPVVerifier.clar` | Verifies Bitcoin tx inclusion proofs for relayer payout. |

Testnet addresses (from `e2e-full-results.json`):
`ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.trioncoherencevault-v5`,
`…btcplend-v4` (→ v5), `…triontesttoken-v4` (tTRION).

---

## 2. Vault State Machine

V5 has three states: `LOCKED`, `RELEASE-TRIGGERED`, `REFUNDED`.
The DeFi flow requires six. Proposed V6 extension:

```
              register-vault       borrow()       repay() + release-vault()
 (none) ──────────────────► LOCKED ──────► ACTIVE ───────────────────────► RELEASED
                            ▲               │                                  (terminal, happy)
                            │               │ publish-preimage() (default, C(t)≥Θ(t))
                            │               ▼
                            │           LIQUIDATING (= RELEASE-TRIGGERED)
                            │               │ release tx confirmed (SPV)
                            │               ▼
                            │           LIQUIDATED  (terminal)
                            │ csv-blocks elapsed, refund-vault()
                            └──────► REFUNDED  (terminal)
```

| State | Const | Trigger | Meaning |
|-------|-------|---------|---------|
| `LOCKED` | `u0` | `register-vault` | BTC locked, vault registered. No loan yet. |
| `ACTIVE` | `u3` | `borrow()` succeeds | Loan drawn; vault collateralises loan. |
| `LIQUIDATING` | `u1` | `publish-preimage` | Preimage published; awaiting BTC release tx. (= V5 `RELEASE-TRIGGERED`.) |
| `LIQUIDATED` | `u4` | SPV proof of release tx | BTC moved to lender. Loan settled. Terminal. |
| `REFUNDED` | `u2` | `refund-vault` (CSV elapsed) | Borrower took back BTC via Leaf 2. Terminal. |
| `RELEASED` | `u5` | `release-vault` (happy path) | Loan repaid, vault unencumbered. Terminal. |

---

## 3. Phase 1 — Lock BTC + Register Vault

**Bitcoin lock tx** funds a P2TR UTXO at block `B_lock`. Outputs:
```
[0] value = amount_sats
    scriptPubKey = Taproot v1, internal key = NUMS (forces script-path)
    merkle root = TAPLEAF_HASH(Leaf1 || Leaf2)
    Leaf1 (release): OP_SHA256 <H:32B> OP_EQUAL
    Leaf2 (refund):  <borrower_pubkey> OP_CHECKSIGVERIFY <csv_delta> OP_CHECKSEQUENCEVERIFY
```
`H = SHA-256(payload || 0x00)` (the "anchor_bh"), computed off-chain by
`btc-tools/vault/coherence-vault.js`.

**Stacks `register-vault`** (state → `LOCKED`):
```clarity
(contract-call? .trioncoherencevault-v5 register-vault
  vault-id borrower-beo committed-anchor-bh lender-btc-addr amount-sats csv-blocks)
```
`vault-id = SHA-256(borrower-beo || anchor-bh || lender-btc-addr || amount-sats || csv-blocks)`.

**Stacks `register-btc-collateral`** (BTCPLend):
```clarity
(contract-call? .btcplend-v5 register-btc-collateral btc-txid btc-block sats anchor-bh)
```
Collateral recorded but **not yet borrowable** — cross-check at `borrow`
time (§4).

---

## 4. Phase 2 — Borrow tTRION

```clarity
(contract-call? .btcplend-v5 borrow amount anchor-bh)  ;; must match registered collateral
```

Checks (existing + new):
1. Collateral exists, `not liquidated` — **existing**.
2. `current_debt + amount ≤ sats × LIQUIDATION-THRESHOLD (80%)` — **existing**.
3. **NEW (V6)**: `TRIONCoherenceVaultV5.is-vault-borrowable(vault-id)` — vault is `LOCKED` and within `BORROW_WINDOW_BLOCKS = 1008` of `B_lock` (1 week of BTC blocks).
4. **NEW**: `BTCSPVVerifier.confirms(btc-txid, btc-block, B_lock + 6)` — lock tx buried 6 Bitcoin confirmations.
5. **NEW**: `publisher-registry.open-escrow(vault-id, bounty-amount)` — lender funds escrow from 30 bps borrow fee.

State transitions:
* `TRIONCoherenceVaultV5.vaults[vault-id].state := ACTIVE`
* `BTCPLend.user-borrows[tx-sender] := { amount, since, anchor-bh }`
* tTRION transferred to borrower (existing flow).

Borrower is then free to swap / yield-farm on Stacks DeFi (out of scope).

---

## 5. Phase 3 — Normal Repayment (Happy Path)

```clarity
(contract-call? .btcplend-v5 repay amount)  ;; tTRION returned
```
When debt reaches zero, BTCPLend emits `loan-cleared`. Vault remains
`ACTIVE`. A new V6 function releases it:
```clarity
(contract-call? .trioncoherencevault-v5 release-vault vault-id)
```
Preconditions: `state == ACTIVE`; `tx-sender == registered-by`;
`BTCPLend.get-borrow(borrower).amount == 0`; `get-accrued-interest(borrower) == 0`.
Effect: `state := RELEASED`. Borrower now sweeps via Leaf 2 with
`csv_delta == 0` (no wait) — the preimage path is never used in the
happy path.

**Borrower sweep tx** (no preimage needed):
```
Inputs: vault_utxo
  witness (Leaf 2): <borrower_sig> <csv_delta:0> OP_CHECKSEQUENCEVERIFY <script> <controlBlock>
Outputs [0]: borrower's address, amount_sats - network_fee
```

---

## 6. Phase 4 — Default & Liquidation

**Default detection** (existing check): `BTCPLend.get-accrued-interest(user) + principal > sats × LIQUIDATION-LTV (90%)`.

**Coherence gate (off-chain)** — publisher network evaluates `C(t) = α·Φ(t) + β·M(t) + γ·Σ(t) + δ·K(t) + ε·A(t)`. When `C(t) ≥ Θ(t)` for the borrower's BEO, the publish window opens.
> The coherence gate is *not* a Stacks call — it is off-chain. Stacks only verifies the *outcome* (a valid preimage, which by Theorem 1 of DBP can only be produced by someone who ran `Compute` on the correct Bitcoin block — itself bound to coherence via the payload's `block_hash` field).

**Liquidation trigger sequence:**

1. **Lender** → `BTCPLend.liquidate(user)` (existing checks; LTV > 0.9; sets `collateral.liquidated := true`; deletes `user-borrows[user]`).
2. **NEW (V6 cross-contract)**: `BTCPLend` calls `(contract-call? .trioncoherencevault-v5 mark-liquidating vault-id)` → `state := LIQUIDATING` (= `RELEASE-TRIGGERED`); emits `coherence-vault-liquidating` event. BTC is **not yet moved**.
3. **Publisher race**: each publisher that saw the event computes `payload = Compute(lock_block_data)` and calls `(contract-call? .trioncoherencevault-v5 publish-preimage vault-id payload)`. First succeeds; later calls revert `ERR-ALREADY-RELEASED`. Winner's `preimage-publisher` recorded; `BountyEscrow` credits 40%.
4. **Relayer race**: relayer reads `payload` from the Stacks event, fills the pre-constructed release PSBT (witness item 0 = payload), broadcasts the release tx on Bitcoin. First to confirm wins.
5. **Relayer payout**: relayer submits SPV proof `(contract-call? .publisher-registry-v1 claim-relay-bounty vault-id btc-txid merkle-proof header-proof)`.
6. **Mark liquidated**: `CoherenceVault.mark-liquidated(vault-id, btc-txid, btc-block)` → `state := LIQUIDATED` (terminal). Releases 40% relayer bounty + 20% treasury.

**Bitcoin release tx (default path):**
```
Inputs: vault_utxo
  witness (Leaf 1):
    <payload:80B>                  ← DBP preimage (NO SIG)
    <script: OP_SHA256 <H> OP_EQUAL>      ← 35 B
    <controlBlock:65B>
Outputs [0]: lender_btc_addr, value = amount_sats - network_fee - relayer_fee
```
This is exactly the spend proven in testnet block 5197632, tx `edd5aa4a568e9974a4373038d6ee5270723d80c0770879113090e7e79fbf8f44`.

---

## 7. How BTCPLend Checks Vault State Before Borrow

A new read-only helper on `TRIONCoherenceVaultV5.clar`:

```clarity
(define-read-only (is-vault-borrowable (vault-id (buff 32)))
  (let ((v (unwrap! (map-get? vaults { vault-id: vault-id }) false)))
    (and (is-eq (get state v) VAULT-STATE-LOCKED)
         (<= burn-block-height (+ (get lock-burn-height v) BORROW_WINDOW_BLOCKS)))))
```

`BTCPLend.borrow` asserts `is-vault-borrowable` before crediting the loan.
This prevents borrowing against a vault already `RELEASE-TRIGGERED`, or
against an ancient `LOCKED` vault whose borrower has long since refunded
via CSV (race between two Stacks read-only views).
`BORROW_WINDOW_BLOCKS = 1008` (1 week of Bitcoin blocks). Tunable.

---

## 8. Coherence Gate → Publisher Network Trigger

```
Off-chain  ── publishers monitor BTCPLend; compute C(t) per borrower BEO.
              When C(t) ≥ Θ(t) AND vault == ACTIVE: publisher computes payload,
              gossips "monitoring" sig, awaits BTCPLend.liquidate.    ▼
On-chain   ── lender → BTCPLend.liquidate(user)
              ↓ cross-contract: CoherenceVault.mark-liquidating(vault)
              ↓ event: coherence-vault-liquidating               ▼
Pub race   ── Publisher.publish-preimage(vault, payload)
              → state stays RELEASE-TRIGGERED; BountyEscrow[publish] = 40%   ▼
Relay race ── Relayer broadcasts release tx (witness = 80B payload)
              Bitcoin confirms → SPV proof → payout (40%)
```

The split ensures: the *decision* to liquidate is the lender's (calling
`liquidate`), not the publishers'; the *gating* is the coherence gate,
evaluated off-chain by publishers; the *execution* (publishing preimage,
relaying to Bitcoin) is open and bounty-driven.

---

## 9. Late-Repay Race: Borrower Repays After Publish, Before BTC Spent

The most delicate race:
```
t₀  lender calls BTCPLend.liquidate(user)       (state → LIQUIDATING)
t₁  publisher calls publish-preimage           (state stays LIQUIDATING; preimage public)
t₂  borrower repays tTRION                     (sees preimage published, races to repay)
t₃  relayer broadcasts release tx on Bitcoin
t₄  Bitcoin confirms — BTC moves to lender
```
If `t₂ < t₄`: borrower has repaid but BTC is about to move to lender.
Without intervention, lender double-recovers (loan repaid in tTRION +
BTC taken in t₄).

### 9.1 Resolution: `release-clawback` (NEW, V6)

```clarity
(define-public (release-clawback (vault-id (buff 32)) (repay-proof (buff 32)))
  (begin
    (asserts! (is-eq (get state v) VAULT-STATE-RELEASE-TRIGGERED) ...)
    (asserts! (BTCPLend.get-borrow(borrower).amount == 0) ...)        ;; loan truly cleared
    (asserts! (not (BTCSPVVerifier.is-confirmed release-txid)) ...)   ;; BTC not yet spent
    ;; state := ACTIVE (back out of liquidation)
    (ok true)))
```
Effects: vault returns to `ACTIVE`; publisher's 40% bounty share is **returned to lender** (publish was honest; race lost fair and square); relayer's 40% share is unclaimed — no Bitcoin tx was spent; treasury's 20% refunded to lender.

### 9.2 Economic protection (both sides)

**Lender** is made whole: repaid (tTRION) + bounty fee returned. They did not lose BTC because the BTC never moved. Publisher spent gas and got nothing — acceptable cost of doing business, rare in practice (requires sub-2-block race). **Borrower** paid `bounty-bps` at borrow time. On clawback they get it back if they prove they repaid before the publish window closed. `release-clawback` requires `repay.height < publish.height + CLAWBACK_WINDOW` (6 Bitcoin blocks). After that window, the lender's claim is final and the BTC moves.

### 9.3 State transition for clawback

```
LIQUIDATING ──release-clawback (repay < publish + CLAWBACK_WINDOW)──► ACTIVE ──► RELEASED (happy path resumes)
```

---

## 10. Complete End-to-End Sequence (Default Path)

| # | Actor | Domain | Call / Tx |
|---|-------|--------|-----------|
| 1 | Borrower | BTC | Lock tx → vault UTXO (block B_lock) |
| 2 | Borrower | Stacks | `register-vault(...)` |
| 3 | Borrower | Stacks | `register-btc-collateral(...)` |
| 4 | Lender | Stacks | `deposit(tTRION)` (one-time) |
| 5 | Borrower | Stacks | `borrow(amount, anchor-bh)` → escrow funded |
| 6 | Borrower | Stacks DeFi | swap / yield (out of scope) |
| 7 | (default accrues) | — | LTV exceeds 0.9 |
| 8 | Lender | Stacks | `liquidate(borrower)` |
| 9 | Publisher | off-chain | compute `C(t) ≥ Θ(t)`, derive `payload` |
| 10 | Publisher (winner) | Stacks | `publish-preimage(vault-id, payload)` |
| 11 | Relayer (winner) | BTC | Broadcast release tx (witness = payload) |
| 12 | Bitcoin | L1 | Block N confirms release tx |
| 13 | Relayer | Stacks | `claim-relay-bounty(vault-id, btc-txid, proof)` |
| 14 | CoherenceVault | Stacks | `mark-liquidated(vault-id)` → LIQUIDATED |
| 15 | Lender | BTC | Spend received UTXO freely |

If borrower repays between steps 10 and 12 (within `CLAWBACK_WINDOW`):
step 11 is *cancelled*, vault returns to `ACTIVE`, lender keeps repaid
tTRION + refunded bounty, borrower proceeds via §5 happy path.

---

## 11. Security Properties (Recap)

| Property | Mechanism |
|----------|-----------|
| No funds stolen without SHA-256 break | Theorem 1 of DBP spec. |
| Borrower can always self-rescue | CSV refund path (Leaf 2), enforced by Bitcoin Script, independent of TRION/publishers/Stacks. |
| Lender can always recover (liveness) | 1-of-n publisher set + open relayer market. Worst case: borrower refunds via CSV, lender takes slashed publisher stake. |
| No double-recovery by lender | `release-clawback` requires BTC unspent + loan repaid; bounty refunded. |
| No double-spend by borrower | Once `publish-preimage` succeeds, vault is `RELEASE-TRIGGERED`; `refund-vault` is disabled (V5 `ERR-ALREADY-RELEASED`). |
| No stale-collateral fraud | `is-vault-borrowable` enforces `BORROW_WINDOW_BLOCKS` freshness + `LOCKED` state. |

---

## 12. Open Questions

1. **Permissionless `liquidate`** — V4 BTCPLend lets anyone call it once LTV > 0.9. Solvency-fine but allows griefing (early liquidation). Mitigation: require `tx-sender` to be the lender of record. V5 BTCPLend change.
2. **`BORROW_WINDOW_BLOCKS = 1008`** — 1 week of Bitcoin blocks. Tunable; staleness-vs-flexibility tradeoff.
3. **`release-clawback` gas** — paid by borrower, who is racing. May need refund from lender's bounty share.
4. **Interest accrual during LIQUIDATING** — does interest continue between `liquidate` and `mark-liquidated`? V6 design: no — `liquidate` snaps the debt; subsequent relayer confirmation only settles it.
5. **Multi-vault loans** — BTCPLend allows one collateral per user today. The DeFi flow assumes 1:1. Multi-vault is future work.
6. **tTRION → BTC swap at payout** — lender receives BTC directly from the release tx, but the bounty is in tTRION. May need a LiquidityOcean swap route for publisher/relayer to convert.
