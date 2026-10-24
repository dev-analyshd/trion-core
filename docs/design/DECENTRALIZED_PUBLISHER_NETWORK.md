# Decentralized Publisher Network — Design

> Eliminates the single-TRION liveness assumption from §6.2 of
> `DBP_PRIMITIVE_SPEC.md`. Safety is already trustless (SHA-256 +
> CSV refund). Liveness of the *release* path currently depends on
> TRION publishing the 80-byte DBP `payload`. This document defines
> a t-of-n publisher network + open relayer marketplace so the
> release path is live as long as **any single publisher** and
> **any single relayer** remain online.

Status: Draft — Design Phase. Scope: Stacks-side registry + Bitcoin-side
relayer flow. No changes to the DBP primitive (`Compute`/`Commit`/`Verify`
unchanged from the formal spec).

---

## 1. The Key Insight

DBP's `Compute(block_data) → payload` is a **pure, public,
deterministic** function — no secret, no oracle input, no interactive
recipient. Therefore:

> **The publisher network does not decide WHAT to publish. It decides
> WHEN to publish.** Once the coherence gate `C(t) ≥ Θ(t)` passes, any
> publisher that can read Bitcoin block headers re-derives the exact
> same 80-byte `payload` and calls `publish-preimage` on V5.

`publish-preimage` is already permissionless on V5 (Clarity re-checks
`SHA-256(payload || 0x00) == committed-anchor-bh`). What is missing:
(a) an *incentive* to call it, (b) a *slashable commitment* forcing
at least one publisher to call it, (c) a *relay market* carrying the
published `payload` from Stacks into a Bitcoin witness.

---

## 2. Architecture

```
   Bitcoin L1 ── Vault UTXO (Taproot)
                 Leaf1: OP_SHA256 <H> OP_EQUAL  (release)
                 Leaf2: <borrower> CSV<Δ>        (refund)
                  ▲ release tx (w/ payload)   ▲ refund tx (borrower sig)
                  │                            │
         Relayer Pool (permissionless)         │
         first-to-confirm → 40% bounty        │
                  │ reads payload              │
                  ▼                            │
   Stacks (Clarity) ───────────────────────────┘
     TRIONCoherenceVaultV5      PublisherRegistry-v1
       register-vault              register (stake)
       publish-preimage ◄──────── heartbeat
       refund-vault               slash / withdraw
              ▲
     BountyEscrow ◄── lender's 30 bps borrow fee
     (40% publisher / 40% relayer / 20% treasury)
              ▲
              │ runs Compute(block_data)
       Publisher Pool  (n publishers, t=1 of n, each stakes STX + tTRION)
```

Three roles; only the publisher role requires a slashable stake.

---

## 3. Roles

| Role | Who | Stake? | Reward |
|------|-----|--------|--------|
| **Publisher** | Operator running `Compute` against BTC headers + a Stacks node. | Yes — STX + tTRION, slashed on liveness failure. | 40% of bounty. |
| **Relayer** | Any Bitcoin wallet reading `payload` from Stacks and broadcasting release tx. | None. Open. | 40% of bounty. |
| **Bounty Payer** | Lender, at borrow time. | n/a | Liquidation guarantee. |

A single entity may occupy multiple roles; bounty splits are independent
to discourage collusion.

---

## 4. PublisherRegistry Contract (Stacks)

New Clarity contract `publisher-registry-v1.clar`, alongside V5 and
BTCPLend. Four public functions:

**`register (pubkey (buff 33), endpoint (buff 64))`** — Stakes
`MIN_STAKE = 5_000 STX` + `10_000 tTRION` (governance-adjustable).
Records publisher in active set; emits `publisher-registered`. No
vetting, no committee — the stake is the bond.

**`heartbeat ()`** — Called once per Stacks epoch (~10 min). Updates
`last-heartbeat`. A publisher whose heartbeat falls `HEARTBEAT_GRACE = 6`
epochs behind is moved to `DORMANT` (not counted in active set, not
slashable for new obligations).

**`withdraw ()`** — Unstakes after `UNSTAKE_DELAY = 144` Bitcoin blocks
(~24 h). During the exit window, any pending publish obligation must
first resolve (publish or slash). Prevents hit-and-run exit.

**`slash (publisher principal, vault-id (buff 32), proof)`** —
Permissionless. Proof is on-chain: (i) vault entered its publish
window at `T_enter`; (ii) `T_enter + SLASH_WINDOW` blocks elapsed;
(iii) vault still `LOCKED` (no `publish-preimage`); (iv) publisher
was `ACTIVE` at `T_enter` with current heartbeat. On valid proof:
`slash-points += 1`, `stake_stx -= SLASH_AMOUNT → BountyEscrow[vault]`.
After `MAX_SLASHES = 3` → `EVICTED`, remaining stake returned.

---

## 5. Redundancy: t-of-n with t = 1

We do not need a quorum. The preimage is *deterministic*, so all
publishers compute the *same* `payload`. First to call `publish-preimage`
wins; subsequent calls revert with `ERR-ALREADY-RELEASED` (already
enforced by V5).

```
publish window opens at C(t) ≥ Θ(t)
   ▼
 Pub A ─► publish() ─► succeeds, state := RELEASE_TRIGGERED  (first wins)
 Pub B ─► publish() ─► reverts ERR-ALREADY-RELEASED
 Pub C ─► publish() ─► reverts ERR-ALREADY-RELEASED   ... n
```

With `n` independent publishers, liveness is `1 - ∏(1 - p_i)` where
`p_i` is each publisher's uptime. For `n = 5`, `p_i = 0.95`:
`1 - 0.05^5 ≈ 1 - 3×10⁻⁷`. This is the trustless-liveness guarantee.

---

## 6. Bounty System

### 6.1 Funding

At `borrow` time, the lender pays `bounty-bps = 30 bps` on the
borrowed tTRION amount. The fee is forwarded to a per-vault
`BountyEscrow` map entry in `publisher-registry-v1`:

```
borrow(amount, anchor-bh) →
   ... BTCPLend logic ...
   (stx-transfer? bounty-amount tx-sender publisher-registry)
   (contract-call? publisher-registry open-escrow vault-id ...)
```

### 6.2 Split: `40 / 40 / 20`

| Share | Recipient | Trigger |
|-------|-----------|---------|
| 40% | First publisher to call `publish-preimage` | V5 already records `preimage-publisher`; payout credited via `claim-publish-bounty`. |
| 40% | First relayer to confirm the Bitcoin release tx | Relayer submits SPV proof to `claim-relay-bounty`. |
| 20% | Protocol treasury | Covers slashing adjudication gas. |

### 6.3 Refund path: no bounty

If the borrower refunds via CSV (Leaf 2), no publish occurred and the
lender took no loss. Escrow is returned to the lender (minus a small
gas reimbursement). **The bounty only fires when the liquidation path
is taken** — the correct incentive (publishers paid to liquidate, not
to procrastinate).

---

## 7. Slashable Stake — The Liveness Bond

### 7.1 When does the publish window open?

The coherence gate `C(t) ≥ Θ(t)` is computed off-chain. A vault is
*eligible* for publish when all hold:

```
(elapsed ≥ DEFAULT_THRESHOLD_BLOCKS since lock)        // hard floor
AND (coherence gate passed for the borrower's BEO)
AND (BTCPLend.liquidate(user) is callable)             // debt, LTV > 0.9
AND (vault.state == ACTIVE)                            // not yet released
```

The publisher signals "I am monitoring this vault" by emitting an
off-chain signature `sig_pub(pubkey, vault-id, eligible-burn-height)`,
gossiped but not on-chain. Used only as evidence in slash adjudication:
if a publisher signed "monitoring V" and V entered its publish window
and no one published within `SLASH_WINDOW`, the publisher is slashable.

### 7.2 SLASH_WINDOW = 12 Bitcoin blocks (~2 h)

Generous enough that brief network partitions are not slashable; tight
enough that stalled liquidations cannot drift.

### 7.3 What gets slashed, who gets it

```
SLASH_AMOUNT = min(stake_stx, vault.amount_sats / 100)   // 1% of BTC
SLASH_AMOUNT → BountyEscrow[vault-id].lender-share       // compensates lender
slash-points += 1
```

After 3 slash points: `EVICTED`, remaining stake returned.

---

## 8. Relayer Marketplace

### 8.1 Why a separate relayer role?

* **Publisher**: needs STX for gas, BTC header subscription, Compute impl.
* **Relayer**: needs BTC sats for release-tx fee, BTC mempool subscription,
  and the pre-constructed release PSBT (borrower deposits it at lock time
  as a DA blob on Stacks).

Splitting roles maximises the set of parties that can carry the flow
forward. A single entity can be both.

### 8.2 First-to-confirm wins

Bitcoin is the source of truth. The release-tx that confirms first
resolves the race. Reorg handling: relayer payout is held for `6`
Bitcoin confirmations before releasing.

### 8.3 Pre-constructed release PSBT

At `register-vault` time, the borrower submits a 96-byte descriptor:
input (vault UTXO), output (`lender-btc-addr`,
`amount-sats - network_fee`), witness template (3 items:
`<80-byte placeholder>` + `<script>` + `<controlBlock>`).

A relayer reads this template from Stacks, fills in the published
`payload` as witness item 0, signs nothing (Path 1 has no signature),
broadcasts. This is exactly the spend proven in
`edd5aa4a568e9974a4373038d6ee5270723d80c0770879113090e7e79fbf8f44`.

---

## 9. End-to-End Publish Flow

```
t₀  Borrower locks BTC, registers vault on Stacks (state = LOCKED, escrow funded)
t₁  Loan defaults (BTCPLend.liquidate becomes callable)
    Coherence gate C(t) ≥ Θ(t) passes off-chain
    Publishers compute payload = Compute(lock_block_data)
t₂  Publish window opens:
    Pub A ─► publish-preimage(vault-id, payload)
              └ succeeds, state := RELEASE_TRIGGERED, BountyEscrow credits 40% to A
    Pub B ─► publish-preimage(vault-id, payload) └ reverts ERR-ALREADY-RELEASED
t₃  Relayer R reads payload from Stacks event, fills PSBT, broadcasts release-tx on Bitcoin
t₄  Bitcoin block N confirms release-tx. Relayer R submits SPV proof → BountyEscrow credits 40% to R
t₅  Lender's BTC output spendable. Vault marked LIQUIDATED (terminal); 20% treasury released

IF no publisher publishes within t₂ + SLASH_WINDOW:
    Any observer calls slash(publisher_i, vault-id, proof)
      └ stake_i -= SLASH_AMOUNT → escrow.lender-share, slash-points += 1
      └ repeat for each monitoring publisher
      └ after SLASH_WINDOW*2: vault → PUBLISHER-DEFAULTED
         borrower's CSV refund is the only release,
         lender takes the slashed stake as partial compensation.
```

---

## 10. Failure Modes & Mitigations

| Failure | Detection | Mitigation |
|---------|-----------|------------|
| All publishers offline | No `publish-preimage` within `SLASH_WINDOW` | After `SLASH_WINDOW*2`: lender's claim becomes the *slashed stake* (not the BTC). Borrower refunds via CSV. Lender partially compensated. |
| Wrong payload published | Clarity `sha256(payload\|\|0x00) != anchor-bh` → revert | No state change, no slash (V5 already rejects). |
| Relayer submits dust/stale release tx | Bitcoin mempool rejects | Multiple relayers race; PSBT has pre-committed fee floor. |
| Collusion: publishers withhold | Equivalent to "all offline" | 1-of-n + stake means collusion needs *all n* to defect — uneconomical vs. the bounty. |
| Stacks reorg undoes `publish-preimage` | Relayer sees stale payload | Relayer waits 6 Stacks blocks before broadcasting. |
| Borrower repays after publish but before BTC spent | Repay succeeds but vault is `RELEASE-TRIGGERED` | See `DEFI_INTEGRATION_FLOW.md` §9: `release-clawback` flow. |

---

## 11. Trust Assumptions Resolved

Revisiting DBP spec §6.2:

> Liveness of the release path requires TRION to publish `payload`.
> If TRION is offline, the release path is unusable until someone
> runs `Compute` and publishes.

**Resolved.** With this design:

* **WHO publishes**: any of `n` staked publishers (1-of-n).
* **WHO relays**: any Bitcoin-aware agent (open marketplace).
* **Economic guarantee**: as long as `1` publisher and `1` relayer
  are online and economically rational (bounty > gas + work), the
  release path is live.
* **Worst case**: if every publisher defects, borrower still refunds
  via CSV (Leaf 2) — *safety* unchanged from §6.1; only lender
  recovery degrades to the slashed stake.

Closes Open Problem #1 in `DBP_PRIMITIVE_SPEC.md`.

---

## 12. Open Questions

1. **Heartbeat cost**: 100 publishers × 144 epochs/day × ~0.001 STX ≈ 14 STX/day total. Batched heartbeat (one tx for many publishers) deserves study.
2. **Publisher churn**: a publisher can register cheaply, monitor nothing, exit. `UNSTAKE_DELAY` mitigates already-open vaults. For vaults opened after exit, require `≥ MIN_ACTIVE_PUBLISHERS = 3` publishers to have signed monitoring at lock time.
3. **Cross-VM publisher**: can a Cairo/Solidity publisher call into Stacks `publish-preimage`? Out of scope — requires a cross-chain message bridge, which DBP itself is meant to replace.
4. **Bounty denomination**: bounty in tTRION matches BTCPLend accounting, but lenders want BTC. May add a tTRION→BTC swap route at payout time.
