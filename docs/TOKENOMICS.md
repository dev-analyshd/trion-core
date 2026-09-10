# TRION Token — Canonical Tokenomics

**Status:** canonical reference (single source of truth for TRION token supply,
decimals, genesis distribution and deflation mechanics).
**Resolves:** due-diligence finding **C8 / 5.4 — "one supply, three stories"**
(token contracts contradicted each other and the whitepaper; no distribution
existed anywhere in the contract layer).
**Implementations governed by this document:**

| Chain | Contract |
|---|---|
| EVM (Vyper — reference) | `contracts/vyper/TRIONToken.vy` |
| NEAR | `contracts/near/src/trion_token.rs` |
| TON | `contracts/ton/token.fc` (mirror: `chains/ton/contracts/token.fc`) |
| Polkadot PVM (ink!) | `contracts/pvm/token/src/lib.rs` |

**Whitepaper basis — Part 15.3 (TRION Token Utility), verbatim:**

> "Token supply: fixed at genesis. No inflation mechanism."
> "Token deflationary: consumption bonding burns small fraction on each use."
> (Public Good Charter, item 5): "15% of fee revenue automatically routed to
> public good pool. Public good pool disbursed by governance vote."

---

## 1. One supply

- **Fixed genesis supply:** **1,000,000,000 TRION** (one billion whole units),
  minted **exactly once** at genesis. There is **no mint path after genesis**
  in any implementation (Vyper `governance_mint()` reverts; NEAR
  `governance_mint()` panics; TON has no mint opcode after the one-shot
  `0x07 genesis_distribution`; ink! has no mint message at all).
- **Decimals:** **18 on every chain.** This fixes the DD-noted thousand-fold
  unit discrepancy (NEAR was 24 decimals vs. 18 elsewhere).
  *TON nuance:* the TON ledger tracks **whole units** (the `u64`
  `total_supply` cannot hold 10^27); `decimals = 18` is stored as display
  metadata so all chains present the same 1B @ 18-dec token. All other
  implementations ledger raw 18-decimal units (10^27).
- **Supply is monotonically non-increasing after genesis:** burns (see §3)
  reduce `total_supply`; nothing ever increases it. "Fixed at genesis" means
  no issuance — not that circulating supply is constant forever.
- **Slashing** (all four implementations) removes 50% of the slashed amount
  to an insurance pool and **burns the other 50%** (Audit-4 Gap 1), which is
  one of the burn paths below.

## 2. Genesis distribution — canonical allocation table

**1,000,000,000 TRION (100%) at genesis, split across two on-chain custody
roots, then sub-allocated by policy:**

| # | Bucket | % | Tokens (whole TRION) | Vesting / release (policy) | Custody root |
|---|---|---|---|---|---|
| 1 | Ecosystem / Community | 30% | 300,000,000 | Grants & integrations, governance-approved | Treasury & Vesting Allocator |
| 2 | Team | 15% | 150,000,000 | **4-year linear vesting, 1-year cliff** (nothing liquid pre-cliff) | Treasury & Vesting Allocator |
| 3 | Protocol Treasury | 20% | 200,000,000 | Governance-controlled operating reserve | Treasury & Vesting Allocator |
| 4 | Early Backers | 12% | 120,000,000 | **3-year linear vesting** | Treasury & Vesting Allocator |
| 5 | Validators / Staking rewards | 8% | 80,000,000 | Released per epoch from the staking budget (rewards are fee-funded, **not** minted) | Treasury & Vesting Allocator |
| 6 | Public Good Reserve | 10% | 100,000,000 | Disbursed by governance vote (WP 15.3 item 5) | Public Good Reserve |
| 7 | Liquidity | 5% | 50,000,000 | Seeded to AMM pools at launch | Public Good Reserve |
| | **Total** | **100%** | **1,000,000,000** | | |

**What the contracts actually enforce at genesis** (identical arithmetic in
all four implementations):

```
public_good_amount  = TOTAL_SUPPLY * PUBLIC_GOOD_BPS / 10_000
                    = 10^27 * 1500 / 10000 = 1.5 × 10^26 raw = 150,000,000 TRION  (15%)
allocator_amount    = TOTAL_SUPPLY - public_good_amount
                    = 8.5 × 10^26 raw = 850,000,000 TRION                        (85%)
```

- **Public Good Reserve custody root — 15% (150,000,000 TRION).** `PUBLIC_GOOD_BPS
  = 1500` (15%), the constant already declared in the Vyper/NEAR contracts,
  now *actually enforced*: at genesis the contracts credit 15% of supply to
  the public-good reserve address. This root carries the **Public Good
  Reserve (10%)** and **Liquidity (5%)** buckets — both non-vesting public
  distributions.
- **Treasury & Vesting Allocator custody root — 85% (850,000,000 TRION).**
  This root carries buckets 1–5: 30% + 15% + 20% + 12% + 8% = **85% exactly**,
  so the two roots account for the entire 1,000,000,000 TRION with no
  remainder and no double counting.

**Cross-check (arithmetic identity):**

```
150,000,000 (public good root)  = 100,000,000 (public good) + 50,000,000 (liquidity)
850,000,000 (allocator root)     = 300,000,000 + 150,000,000 + 200,000,000
                                   + 120,000,000 + 80,000,000
1,000,000,000                    = 150,000,000 + 850,000,000  ✓
```

> **The allocation table is a plan.** What the contracts enforce is exactly:
> (a) the fixed 1B supply minted once; (b) the 15% / 85% genesis split between
> the two custody roots; (c) no minting afterwards; (d) burn paths. The
> bucket-level sub-allocation, all vesting schedules, liquidity seeding and
> disbursement cadence are **policy**, executed by the custody-root holders —
> no contract in this repository locks or streams vested balances (the ink!
> implementation additionally records the team/backer vesting parameters
> on-chain as immutable informational markers).

## 3. Burn-on-use (deflationary mechanism)

Whitepaper Part 15.3 specifies the mechanism but **no numeric burn rate**
("consumption bonding burns small fraction on each use"). The rate is fixed
by this document:

- **Consumption fee: 0.05% (5 bps) of every token transfer**
  (`TRANSFER_FEE_BPS = 5`).
- Of each collected fee: **15% (`PUBLIC_GOOD_BPS`) is forwarded to the
  public-good reserve** — enforcing WP 15.3 item 5 ("15% of fee revenue
  automatically routed to public good pool") — and the **remaining 85% is
  burned** (permanently destroyed, `totalSupply` decreases).

Worked example (transfer of 1,000,000 TRION):

```
fee              = 1,000,000 × 0.0005        = 500 TRION
public good part = 500 × 15%                  = 75 TRION   → public-good reserve
burn part        = 500 × 85%                  = 425 TRION   → destroyed
recipient receives                              999,500 TRION
```

In addition, every implementation exposes a **permissionless burn**
(Vyper `burn()`/`burnFrom()`; NEAR `burn()`; TON opcode `0x08`;
ink! `burn()`) so consuming protocols can burn fee shares on any chain,
and 50% of every validator slash is burned.

## 4. Enforcement matrix — on-chain vs. policy

| Mechanism | Vyper (reference) | NEAR | TON | ink! |
|---|---|---|---|---|
| Fixed 1B supply minted once | constructor | `new()` | opcode `0x07`, owner-guarded, first-call-only (`genesis_done` latch) | constructor |
| 15% public-good carve-out | **enforced** | **enforced** | **enforced** | **enforced** |
| 85% treasury & vesting allocator | **enforced** | **enforced** | **enforced** | **enforced** |
| 18 decimals | yes (raw 10^27) | yes (raw 10^27) | yes (whole-unit ledger, `decimals = 18` metadata) | yes (raw 10^27) |
| Mint after genesis | `governance_mint()` **reverts** | `governance_mint()` **panics** | no mint opcode | none |
| Permissionless burn | `burn` / `burnFrom` | `burn` | opcode `0x08` | `burn` |
| 0.05% fee hook (85% burn / 15% public good) | **enforced** in `transfer`/`transferFrom` | policy (rate published via `transfer_fee_bps`) | policy (fee burn via `0x08` from consuming contracts) | policy (rate published via `transfer_fee_bps`) |
| Vesting schedule | policy | policy | policy | immutable informational markers (`vesting_*`) |
| Slash 50% insurance / 50% burn | enforced | enforced | enforced | enforced |

**Policy remains off-chain** (executed by custody-root holders, auditable via
transfers and governance records, not enforced by these contracts):

1. Sub-allocation of the 85% allocator root into buckets 1–5.
2. Team vesting (4y linear, 1y cliff) and early-backer vesting (3y linear).
3. Liquidity seeding (5%) from the public-good root.
4. Validator reward release cadence (rewards are fee-funded — never minted).
5. Public-good pool disbursements (governance vote, WP 15.3 item 5).
6. Burn-on-use fee collection on NEAR/TON/ink! (consuming contracts must call
   the burn entry points; only the Vyper reference implementation charges the
   fee inside the token itself).

## 5. Notes for integrators

- **Fee-on-transfer semantics (EVM only):** the Vyper reference token deviates
  from strict ERC-20 — recipients of `transfer`/`transferFrom` receive
  `amount − fee` (0.05%). Integrations must use the Vyper token's balance
  after transfer, not the instructed amount.
- **TON deployment procedure:** after deploying `token.fc`, the deployer MUST
  send one `0x07 genesis_distribution` message (body: `op(32) ||
  public_good_reserve_addr(267) || treasury_allocator_addr(267)`, 566 bits)
  from the owner address. It mints the full allocation exactly once; any
  replay fails with `ERR_GENESIS_DONE (109)`.
- **Validator rewards are fee-funded**, never minted (WP 15.3 / Audit-4
  Gap 1): the 8% staking bucket is a pre-funded budget, not an emission tap.
- The `/api/v1/token/distribution` endpoint is being aligned to this document
  by the API lead; this file is the canonical source.
