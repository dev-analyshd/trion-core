# Babylon BTC Staking — And The Full Landscape Of BTC Lock Mechanisms

**Phase 1 Research Report — TRION BTCP Zero-Bridge**
**Author:** Phase 1 Researcher (general-purpose agent)
**Status:** RESEARCH ONLY — no code, no git commits, no design decisions
**Date:** 2026-10-14
**Scope:** Babylon BTC Staking (v1 / v2 / TBV), tBTC v2, sBTC, wBTC, DLCs, and current Bitcoin Script capabilities. The goal is to identify what makes **every** existing BTC lock mechanism trust-dependent, and to surface the design space in which TRION's HashDNA-driven "Coherence Vault" can be **fundamentally different**.

---

## Table of Contents

- §1 — Babylon BTC Staking: full technical breakdown
- §2 — tBTC v2: full technical breakdown
- §3 — sBTC: full technical breakdown
- §4 — wBTC: full technical breakdown
- §5 — DLCs (Discrete Log Contracts): full technical breakdown
- §6 — Comparison matrix (all 5 mechanisms)
- §7 — The fundamental weakness of all existing solutions
- §8 — Bitcoin Script capabilities (what CAN be verified today)
- §9 — How TRION can be fundamentally different (5+ design principles)
- §10 — The "Coherence Vault" concept: a BTC lock triggered by HashDNA, not a committee
- §11 — Sources

---

## §1 — Babylon BTC Staking: full technical breakdown

Babylon is **two protocols, not one**. The Bitcoin community (and even parts of the Babylon docs) often conflate them. For TRION it is essential to keep them separate, because their **trust models are fundamentally different**:

| Protocol | What it does | Trust model | Production status |
|---|---|---|---|
| **Babylon BTC Staking v1 / v2** | Lock BTC on Bitcoin L1 to provide economic security (finality votes) to Babylon Genesis, a Cosmos-SDK PoS chain | **Covenant committee** (M-of-N multisig) co-signs unbonding & slashing. Committee cannot steal but can censor. | Mainnet Phase-1 (Aug 2024), Phase-2 (Apr 2025). Live. TVL ≈ $3B per OpenZeppelin's Apr-2026 research. |
| **Babylon Trustless Bitcoin Vault (TBV)** | Lock BTC on Bitcoin L1 to use as collateral in DeFi (Aave V4) on Ethereum — **without** wrapping or bridging | **No committee** for spend. ZK proof of Ethereum redemption event verified inside Bitcoin Script via the **BABE** protocol. | Public testnet (Bitcoin signet + Ethereum testnet). Aave V4 integration Temp-Check May 25, 2026. |

Both protocols ship from Babylon Labs. Both lock real BTC in Taproot outputs on L1. But the *trigger* for releasing the BTC is different in each:

- **BTC Staking v1/v2** → release is triggered by **a committee's threshold signature** over an off-chain covenant.
- **TBV** → release is triggered by **a ZK-verified proof of an Ethereum event** verified inside Bitcoin Script.

Both of these matter enormously for TRION's design (§9, §10).

### §1.1 Stakeholders (Babylon BTC Staking v1 / v2)

Per Babylon's own `docs/staking-script.md` (the canonical specification in the `babylonlabs-io/babylon` repo):

> The Bitcoin Staking protocol involves the following stakeholders:
> * **Bitcoin Staker** — the controller and beneficiary of the Bitcoin stake, identified by their Bitcoin public key (`<StakerPk>`). Notably, *"the staker public key does not need to match the UTXO funder of the staking transaction. The funding UTXO can originate from any source, including multi-sig, MPC, or threshold-controlled accounts."*
> * **Finality Providers** — *"Bitcoin Staking supports delegated staking, allowing voting power from a stake to be assigned to a finality provider. A finality provider is identified by their EOTS public key (`<FinalityProviderPk>`) and participates in the finality voting round of a specific BSN."* The finality provider is the analogue of a PoS validator. Today, only one FP per stake is allowed and only the Babylon Genesis chain is supported.
> * **Covenant Committee** — *"identified by the Bitcoin public keys of its members `CovenantPk1..CovenantPkN`. Its role is to protect BSNs against attacks from the BTC stakers and finality providers. It achieves this by representing itself as an M-out-of-N multi-signature that co-signs BTC transactions with the BTC staker. Through co-signing, the covenant committee enforces spending rules on the staked Bitcoin, so that they can only be spent in a protocol compliant manner. The co-signatures are published on the Babylon Genesis chain and are a pre-requisite for the stake's activation."* Critically, Babylon's own spec states: *"There's no way the covenant committee can act against the stakers, except rejecting their staking requests."* — i.e. **the committee can censor but cannot steal**.
> * **Babylon Genesis chain** — *"the first BSN and acts as the control layer for the BTC staking protocol. All Bitcoin stakes and finality providers must be registered on the Babylon Genesis chain."* This is a Cosmos-SDK chain that implements the control-plane logic via custom modules: `x/epoching`, `x/checkpointing`, `x/btcstaking`, `x/finality`.

The key insight from this list: **Babylon is a federated design**. The committee is a federation. The "trustless" claim is *trust the committee not to censor and trust the Babylon Genesis chain not to lie about finality-provider misbehavior*.

### §1.2 The Three Spending Paths (Staking Output)

The staking output is a **Taproot output that can ONLY be spent through the script spending path**. The key-path spend is disabled by using the **NUMS (Nothing-Up-My-Sleeve) point** defined in BIP-341 as the internal key:

```
H = lift_x(0x50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0)
```

This NUMS point is *"derived by hashing the standard uncompressed encoding of the secp256k1 base point G as the X coordinate"* — i.e. nobody knows the discrete log of `H`, so key-path spend is impossible. **Every spend MUST go through one of the three script paths committed in the Taproot tree.**

The three script paths (verbatim from `docs/staking-script.md`):

#### Path 1 — Timelock Path (canonical, in Bitcoin Script)

```bitcoin
<StakerPK> OP_CHECKSIGVERIFY  <TimelockBlocks> OP_CHECKSEQUENCEVERIFY
```

* `<StakerPK>` — the BTC staker's public key (Schnorr / x-only Taproot key).
* `<TimelockBlocks>` — number of Bitcoin blocks the funds are locked. **Must be < 65535** (CSV limit). At Phase-1 launch, the maximum staking time was capped at **64,000 Bitcoin blocks** (~15 months).
* After the timelock expires, **only the staker can withdraw**. No committee signature needed.

This is a pure relative timelock (`OP_CHECKSEQUENCEVERIFY` = BIP-112, BIP-68). The staker alone can withdraw after the lock expires.

#### Path 2 — Unbonding Path (on-demand early exit)

```bitcoin
<StakerPk> OP_CHECKSIGVERIFY
<CovenantPk1> OP_CHECKSIG <CovenantPk2> OP_CHECKSIGADD ... <CovenantPkN> OP_CHECKSIGADD
<CovenantThreshold> OP_NUMEQUAL
```

This path lets the staker exit *before* the timelock expires. **It requires:**
1. The staker's signature (only the staker can initiate).
2. A `CovenantThreshold`-of-N quorum of covenant committee signatures (using Taproot's `OP_CHECKSIGADD`, BIP-342).

* The covenant committee keys are *"lexicographically sorted public keys of the covenant committee as defined in the Babylon Genesis parameters."*
* The threshold is *"a Babylon parameter specifying the number of how many covenant committee member signatures are required."*
* The unbonding output (where this path sends the BTC) has its own timelock (301 blocks ≈ 50 hours per Babylon docs) **plus** its own slashing path (so the stake can still be slashed during unbonding).

The covenant committee's role here is to **enforce that the staker goes through the proper unbonding flow** (a separate unbonding transaction that re-locks the funds for the unbonding period) rather than just withdrawing immediately. **This is the censorship point**: if the covenant committee refuses to co-sign, the staker cannot exit early and must wait out the full timelock.

#### Path 3 — Slashing Path (punishment)

```bitcoin
<StakerPk> OP_CHECKSIGVERIFY
<FinalityProviderPk> OP_CHECKSIGVERIFY
<CovenantPk1> OP_CHECKSIG <CovenantPk2> OP_CHECKSIGADD ... <CovenantPkN> OP_CHECKSIGADD
<CovenantThreshold> OP_NUMEQUAL
```

This is the critical safety path. Note the additional `<FinalityProviderPk>` compared to the unbonding path.

The mechanism (from Babylon's spec):

> *"This path can only be executed with the collaboration of the BTC staker, finality provider, and covenant committee. The staker is required to submit a pre-signature for spending the slashing path in order for their stake to be accepted. The covenant signatures are required to protect against non protocol-compliant withdrawals."*

The trick is **Extractable One-Time Signatures (EOTS)**, built on Schnorr (BIP-340). EOTS works as follows:

1. The finality provider commits, on Babylon Genesis, to a per-block Schnorr nonce.
2. When finalizing a block, the FP signs with that nonce (one finality vote per block).
3. If the FP ever double-signs (votes on two conflicting blocks at the same height), they must **reuse the same nonce** — and reuse of a Schnorr nonce leaks the private key.
4. Anyone who observes the double-sign can extract the FP's EOTS private key from the two signatures.
5. With the FP's private key in hand, the slashing path becomes spendable: the staker has pre-signed their portion at stake activation, the FP's key is now public, and the covenant committee co-signs.
6. The slashing transaction sends a slashed fraction to a **burn address** (specified in Babylon Genesis parameters) and the remainder to a **slashing refund output** that locks the funds for a short timelock before the staker can recover them.

> *"For a staking request to become active, the BTC staker must include a valid (unsigned) unbonding transaction in the staking request. It becomes active only when the Babylon Genesis chain receives `CovenantThreshold` signatures by the covenant committee. Since the unbonding path does not include `<FinalityProviderPk>`, the staker can exit at any time without needing the finality provider's consent. In contrast, the slashing path does include `<FinalityProviderPk>` and requires a pre-signed slashing transaction by both the staker and a `CovenantThreshold` of the covenant emulation committee to become active. This ensures that the finality provider's cooperation is needed to prevent slashing, but not to execute it. If a finality provider misbehaves, their key is exposed and can be used to execute the slashing."*

So **slashing is permissionless once the FP double-signs**: the FP's exposed key is the trigger, and nobody — not the committee, not Babylon — can prevent the slashing transaction from being broadcast. The committee's signature is **already pre-committed at stake activation**.

### §1.3 The Four Transaction Types

Babylon defines four transaction types in its staking protocol:

| # | Transaction | Purpose | Spends | Creates |
|---|---|---|---|---|
| 1 | **Staking Transaction** | Lock BTC into the staking script | arbitrary inputs | staking output (Taproot, NUMS internal key, 3-path script tree) |
| 2 | **Unbonding Transaction** | On-demand early exit | staking output | unbonding output (Taproot, NUMS, 2-path: timelock + slashing) |
| 3 | **Slashing Transaction** | Punish double-signing FP | staking output OR unbonding output | (a) burn-address output (slashed fraction); (b) slashing refund output (timelocked to staker) |
| 4 | **Withdrawal Transaction** | Recover unlocked BTC | staking / unbonding / slashing refund output | arbitrary outputs (staker's wallet) |

State machine (from `docs/staking-script.md`):

```
Staking tx ─→ Staking output
                ├──(timelock)─→ Withdrawal (staker recovers)
                ├──(unbonding)─→ Unbonding output
                │                 ├──(timelock)─→ Withdrawal (staker recovers)
                │                 └──(slashing)─→ Burn + Slashing refund ─→ Withdrawal
                └──(slashing)──→ Burn + Slashing refund ─→ Withdrawal
```

### §1.4 Phase-1 vs Phase-2 (Babylon BTC Staking "v1" and "v2")

- **Phase-1** (Aug 16, 2024): Mainnet launch. *"In Phase-1, the covenant committee is a multi-signature verification scheme to secure the on-demand unbonding process."* BTC is locked but does **not** yet secure a PoS chain. *"During Phase-1, every stake is set with a maximum staking time (i.e., the time-lock in the Bitcoin staking script) of 64,000 Bitcoin blocks."* No slashing is active because there is no PoS chain to finalize.
- **Phase-2** (Apr 10–24, 2025): Babylon Genesis chain launches as a PoS chain. *"Your Finality Provider (FP) must register on the Babylon Genesis chain before your stake can transition and be delegated."* Stakers earn **BABY tokens** as rewards. Slashing becomes live: FPs that double-sign on Babylon Genesis leak their EOTS keys and get slashed.
- **Phase-2 Caps** (Dec 10, 2024, "Cap-3"): Adds throughput / TVL limits.
- **Phase-2 Stake transition**: only the **top 60 FPs by delegated stake** are active; the rest are inactive.

OpenZeppelin's security research (Apr 1, 2026) confirms the architecture:

> *"Babylon is a layered system coordinating Bitcoin-side staking transactions with a Cosmos SDK chain (Babylon Genesis), which acts as the control plane for stake activation, voting power, finality, checkpointing, and rewards."*
>
> *"Compliance hinges on covenant committee (offchain) threshold signatures for certain spends and on pre-signed slashing transactions that become executable if a finality provider misbehaves."*

### §1.5 The Trust Model of Babylon BTC Staking v1/v2 — What Can Each Party Do?

| Party | Steal BTC? | Censor (refuse to co-sign)? | Trigger slashing? | Recover stake after timelock? |
|---|---|---|---|---|
| **Bitcoin Staker** | ❌ (cannot redirect to a different address — every spend path requires the staker's own key check, except slashing which goes to a burn + refund-to-staker) | ✅ (the staker can simply not initiate unbonding — they keep their BTC locked until timelock) | ❌ (the staker cannot forge the FP's EOTS key) | ✅ (after timelock, staker signs alone) |
| **Finality Provider** | ❌ (no path in the script spends to the FP) | ❌ (FP is not a signatory on unbonding or withdrawal paths) | ✅ — **but only by misbehaving** (the FP's own double-sign leaks their key, which then allows the slashing path to fire). The FP cannot trigger slashing on someone else. | ❌ (no role in withdrawal) |
| **Covenant Committee** | ❌ — *"There's no way the covenant committee can act against the stakers, except rejecting their staking requests."* The committee has no path that redirects BTC to itself. | ✅ **— THE KEY CENSORSHIP POINT.** The committee can refuse to co-sign the unbonding path, forcing the staker to wait out the full timelock. The committee can also refuse to sign the pre-activation covenant quorum, blocking the stake from going active (the BTC stays in the timelock path and is recoverable after expiry — so this is liveness censorship, not theft). | ❌ (committee's slashing-path signature is pre-committed at activation; it cannot retroactively *withhold* slashing once the FP's key leaks) | ❌ (no role) |
| **Babylon Genesis chain** | ❌ (cannot redirect BTC — only block/spoof the slash signal) | ⚠️ Indirect: a supermajority of Babylon validators could censor the slash signal (refuse to include the EOTS-evidence tx) or lie about FP registration. But this affects *whether slashing fires*, not whether BTC can be stolen. | ⚠️ Indirect: a Byzantine Babylon majority could *fabricate* a slash signal — but the slash path requires the FP's **actual leaked EOTS private key**, which Babylon cannot forge. So even a 100% Byzantine Babylon cannot slash an honest FP. | ❌ |
| **Bitcoin miners** | ⚠️ 51% attack on Bitcoin L1 could reorg staking txs (theoretical) | ⚠️ Could censor staking transactions indefinitely (requires sustained 51%) | ❌ | ⚠️ Could reorg withdrawal txs |

**Net summary:** *Nobody can steal the staker's BTC.* The covenant committee can censor unbonding (forcing the staker to wait out the timelock). The FP can trigger self-slashing by misbehaving (and once they do, the slash is unstoppable). A Byzantine Babylon chain cannot forge slashing (because it cannot forge the FP's leaked EOTS key — that's a Schnorr-math guarantee, not a Babylon promise).

### §1.6 Babylon Trustless Bitcoin Vault (TBV) — The "V2" That Doesn't Get Enough Attention

TBV is a **fundamentally different protocol** from BTC Staking. Both ship from Babylon Labs but they have different mechanisms, different trust models, and different triggers.

Per the Babylon TBV docs (`docs.babylonlabs.io/trustless-bitcoin-vault/start-here/what-is-tbv`):

> *"The Babylon Trustless Bitcoin Vaults (TBV) protocol enables Bitcoin holders to use their BTC as collateral in DeFi applications on Ethereum without bridging or wrapping their assets."*
>
> *"The depositor's BTC stays on the Bitcoin Network, held in a Taproot script that the depositor co-signs at creation. An Ethereum-side protocol contract tracks each BTC vault, which is a single Bitcoin output (one UTXO) holding the depositor's locked BTC, and lets an integrated DeFi application use it as collateral."*

Key structural differences from BTC Staking v1/v2:

| Property | BTC Staking v1/v2 | TBV |
|---|---|---|
| **Trigger for release** | Covenant committee threshold signature (off-chain, M-of-N multisig) | ZK proof of Ethereum redemption event, verified inside Bitcoin Script |
| **Pre-signed paths?** | Only slashing path is pre-signed | **Every legitimate spend is pre-signed at vault creation** |
| **Custody model** | Covenant committee co-signs | Self-custodial: "the depositor's keys participate in every depositor-controlled release path" |
| **BTC location** | Taproot output (NUMS internal key, 3-path tree) | Taproot output (multi-leaf script tree) |
| **Settlement to DeFi** | None — BTC secures PoS chain, earns BABY rewards | BTC is collateral on Ethereum via an Aave V4 spoke; user borrows USDC/USDT/WBTC |
| **Activation** | Activates when covenant quorum signs on Babylon Genesis | "Collateral activation atomically binds the Ethereum-side activation of Bitcoin collateral to the lockup of BTC in the co-signed Taproot script" |
| **Redemption (peg-out)** | N/A (no peg-out) | "Collateral redemption uses a BABE-based challenge procedure that lets Bitcoin verify proofs of Ethereum redemption events using only existing Bitcoin Script primitives. No Bitcoin fork is required." |

From the "TBV vs Alternatives" doc:

> *"Each spending path is encoded as a separate Taproot leaf at vault creation. Every legitimate spend is constructed and signed in advance by the depositor and the protocol participants. After the vault is created, no party can fabricate a new spend; the only spends Bitcoin will accept are the ones already encoded in the script."*
>
> *"Ethereum Events are verified inside Bitcoin script: When a vault is redeemed, a zero-knowledge proof of the corresponding Ethereum redemption event is verified inside a Bitcoin Taproot script. Verification uses the BABE construction: garbled circuits and Winternitz One-Time Signature (WOTS) commitments fit inside Bitcoin's existing script capabilities and require no Bitcoin fork. Bitcoin's own consensus rules enforce that BTC is released only when the matching Ethereum state has occurred."*
>
> *"The depositor's signatures are required at vault creation, before activation, and on every depositor-controlled release path. A self-claim path using the depositor's WOTS key, plus claimer artifacts downloaded at peg-in, is committed at vault creation. This lets the depositor exit independently if the Vault Provider is offline or unresponsive. A relative CSV timelock of 2016 BTC blocks (~14 days) on the Pre-PegIn output recovers the BTC for vaults created under the current parameter version."*

This is **BitVM-style verification**. The release of BTC is gated by a **SNARK proof of an Ethereum event** that is verified *inside Bitcoin Script itself*, using only hash/preimage commitments (WOTS) and a challenge-response protocol.

### §1.7 BABE — The Cryptographic Primitive That Makes TBV Possible

BABE stands for "Bitcoin Adoption for Better Ethereum" (the name is unofficial — it appears in the Babylon docs and in the paper by Garg, Kolonelos, Sergeevitch, Sridhar, Tse, Jan 2026). The abstract from the Babylon research page:

> *"Verifying succinct proofs on Bitcoin is essential for scaling Bitcoin and enabling trustless use of Bitcoin assets on other blockchains, but remains challenging due to limited scripting expressiveness and small block space. While BitVM2 and BitVM3 have made progress, they suffer from either high on-chain transaction fees or massive off-chain storage requirements, 42 GiB per garbled circuit. BABE introduces a new proof verification protocol that preserves BitVM3's on-chain cost savings while reducing off-chain storage and setup costs by three orders of magnitude. The protocol achieves this by combining a witness encryption scheme for linear pairing relations with an efficient garbled circuit for scalar multiplication on elliptic curves, enabling practical Groth16 proof verification on Bitcoin."*

BABE makes SNARK verification on Bitcoin **~1000× cheaper** than prior approaches. From the Aave V4 governance temp-check (May 25, 2026):

> *"BaBe makes SNARK proof verification on Bitcoin approximately 1000x cheaper than prior approaches, making trustless Bitcoin DeFi practical at scale."*

BABE itself relies on:
1. **Taproot pre-signed spending paths** (BIP-341, active since 2021).
2. **BitVM-style verification** — hash commitments, Winternitz / Lamport one-time signatures, challenge-response (BitVM1 paper, 2023+).
3. **SP1 (or similar) succinct ZK proofs** of the Ethereum event (~few hundred bytes).
4. **Winternitz One-Time Signatures (WOTS)** for the depositor's self-claim path.

None of these require any Bitcoin soft fork. They are all built from `OP_HASH256`, `OP_EQUAL`, `OP_CHECKSIG`, `OP_CHECKSEQUENCEVERIFY`, and Taproot's multi-leaf script trees.

### §1.8 Babylon on Aave V4 (May 2026)

The Aave V4 Temp-Check proposal (May 25, 2026, governance.aave.com/t/temp-check-babylon-trustless-btc-vault-integration-on-aave-v4/24964):

> *"The Aave V4 integration with Babylon Trustless Bitcoin Vaults protocol enables onboarding of non-custodial native BTC collateral on Aave."*
>
> *"This would allow native BTC as collateral and introduce two new V4 Spokes, one for borrowing against BTC and one for post-liquidation settlement."* — @aave

Architecture (from `docs.babylonlabs.io/trustless-bitcoin-vault/technical-details/aave-v4-integration`):

- **Aave V4 Hub** — central liquidity contract. Lenders supply USDC / USDT / WBTC and earn interest.
- **Babylon Core Lending Spoke** — dedicated lending market for BTC-vault collateral. Draws borrowable assets from the Hub on borrow, restores them on repay.
- **AaveAdapter** — user-facing entry point. Coordinates add-collateral / borrow / repay / withdraw / trigger-redemption.
- **AaveAdapterPositionProxy** — per-depositor proxy contract that holds the depositor's lending position. One proxy per depositor on first deposit. Multiple vaults can back the same position.
- **AaveAdapterConfig** — manages LLP registration, position-size parameters; gated by TimelockController.
- **AaveAdapterLens** — read-only contract for aggregated state queries.

Collateral record (the "wrapped BTC" that is not a wrapped BTC):

> *"Aave v4 markets recognize collateral as an ERC-20 balance, but a BTCVault is an indivisible Bitcoin UTXO. To express that UTXO as an Aave-readable balance, the adapter creates a collateral record of the locked BTC for the Aave market to read. The record is a transfer-restricted ERC-20 internal to the Aave Adapter — a technical requirement for expressing the vault as Aave-readable collateral, not a token users hold, trade, or bridge, and not a wrapped BTC."*
>
> *1:1 with BTC, 8-decimal precision. Created and closed only. Transfer-restricted. No secondary market."*

**Borrow flow:** depositor → AaveAdapter → position proxy → Babylon Core Lending Spoke → Aave v4 Hub. Hub releases USDC/USDT/WBTC, traveling back the same path to the depositor.

**Liquidation model** (the most novel part):

- **Two paths:**
  1. **LLP-routed liquidation** (`liquidateWithLLP`) — *permissionless*. Any Ethereum address can trigger when health factor < 1.0. Liquidator repays debt and receives instant settlement (WBTC at launch) from the Liquidation Liquidity Provider (LLP). The seized vault enters LLP escrow; a registered Arbitrageur (App Keeper) later acquires the escrowed vault and finalizes BTC redemption on Bitcoin L1.
  2. **Direct-redemption liquidation** (`liquidate`) — *permissioned*. Liquidator must be a registered App Keeper (Arbitrageur) with a Bitcoin redeem key. They repay necessary debt and redeem the seized vault directly to a Bitcoin redeem key.
- **Full-vault constraint:** *"UTXOs are indivisible: a Bitcoin output cannot be partially spent. The protocol therefore seizes vaults whole, never fractionally."*
- **Partial-position support:** A position holds one or more vaults. When liquidation is triggered, the protocol walks the ordered vault list and seizes the minimum prefix needed to restore the health factor. Recommended pattern: two vaults — a "sacrificial" vault at the front (larger), and a "protected" vault later.
- **Fairness mechanism:** over-seizure surplus returned to depositor. Either as debt reduction (Fairness debt repayment) or WBTC payment (Fairness payment on full liquidation).
- **Pricing:** Chainlink BTC/USD oracle for health-factor; Chainlink WBTC/USD oracle for fairness payments.

**Testnet parameters:** peg-in ≈ 2 hours (Bitcoin confirmations); peg-out ≈ 3 days (challenge window). No real money on testnet.

### §1.9 Phase-1 vs Phase-2 vs TBV — Summary

| Property | BTC Staking Phase-1 | BTC Staking Phase-2 | TBV (post-2025) |
|---|---|---|---|
| Lock real BTC on Bitcoin L1? | ✅ | ✅ | ✅ |
| Trust model | Covenant committee (censor only) | Covenant committee (censor only) + EOTS slashing | Pre-signed paths + ZK proof verified in Bitcoin Script |
| Trigger for release | Staker sig + Covenant quorum | Staker sig + Covenant quorum (or EOTS-exposed FP for slash) | ZK proof of Ethereum event |
| Can committee steal? | ❌ | ❌ | N/A (no committee for spend) |
| Can committee censor? | ✅ (refuse to co-sign unbonding) | ✅ (refuse to co-sign unbonding) | ❌ (depositor self-claim + 2016-block CSV recovery) |
| Synthetic minting? | ❌ (BTC stays as BTC; BABY rewards on Genesis) | ❌ | ❌ (collateral record is non-transferable, internal to Aave Adapter) |
| Slashing trigger | None (Phase-1) | FP EOTS double-sign on Babylon Genesis (off-chain) | N/A — liquidation triggered by Chainlink BTC/USD oracle on Ethereum |
| Trigger verifiable in Bitcoin Script? | N/A (covenant sig only) | ❌ (EOTS evidence is verified on Babylon Genesis, not in Bitcoin Script) | ✅ (BABE verifies ZK proof of Ethereum redemption event in Bitcoin Script) |

The TBV is the closest thing in the industry to a "trustless" BTC lock. But it's still not zero-trust — see §7 for why.

---

## §2 — tBTC v2: full technical breakdown

tBTC v2 is the Threshold Network's BTC bridge. It is a **federated threshold-signature** bridge, with **permissioned** signers and **synthetic minting** (tBTC ERC-20 on Ethereum).

### §2.1 How tBTC v2 works

From the canonical source (`github.com/threshold-network/tbtc-v2` README):

> *"tBTCv2 uses the Random Beacon and Sortition Pool to generate governable-sized (starting at 51-of-100) threshold ECDSA Bitcoin wallets at a governable frequency."*

And from `tbtc.network`:

> *"Trust-Minimized by Design. Bitcoin custody is held by an honest majority threshold signer set that rotates on a fixed cadence. No single entity can move the BTC."*

Mechanism:

1. **Depositor** locks BTC on Bitcoin L1 into a P2SH / P2WSH / Taproot output controlled by a **threshold ECDSA public key** (a single aggregated pubkey, but the private key is sharded across N signers).
2. The **sortition pool** (on Ethereum) **randomly selects** a signing set of 100 signers for each new wallet.
3. The 100 selected signers run a **distributed key generation (DKG)** ceremony to jointly produce the wallet's public key, with the private key sharded into 100 shares (one per signer).
4. **51 of 100** signers must collaboratively produce a threshold ECDSA signature to authorize any spend (sweep of the depositor's BTC into the wallet, or a peg-out).
5. Once the BTC is confirmed on L1 (swept into the threshold wallet), an equal amount of **tBTC (ERC-20)** is minted on Ethereum.
6. To redeem, a user burns tBTC on Ethereum, the signers threshold-sign a Bitcoin transaction paying out the BTC from the wallet to the user's address.

### §2.2 The signer set

From the bitcoinlayers.org research article on Threshold tBTC:

> *"The bitcoin wallets that store the bitcoin backing tBTC are managed by a permissioned signer set. The signers of the wallets participate as stakers in an Ethereum staking contract to become eligible for signing privileges."*
>
> *"Signers must stake T tokens before being approved by the Threshold DAO to become a signer."*
>
> *"When a new wallet is created, a randomized process, known as the sortition pool, will select signers who will be responsible for custodying funds and signing transactions for respective bitcoin wallets. If signers colluded, and had sufficient amount of signing power for a bitcoin wallet, they could steal funds from a wallet they managed."*

The signer set is **permissioned** — signers must be approved by the Threshold DAO. This is in contrast to sBTC's open-membership design (§3).

### §2.3 Wallet rotation

> *"tBTC creates new wallets periodically to store the bitcoin backing tBTC. Every wallet undergoes its own distributed key generation ceremony and has a unique signer setup. This distributes the risk of collusion and theft across a number of wallets and signer groups."*

This is the rotation cadence. By periodically rotating the signer set, the protocol limits the value at risk in any single wallet (an attacker who wants to steal a wallet's BTC must compromise a 51% collusion of the specific 100 signers for that wallet, before the wallet rotates).

### §2.4 The 51-of-100 threshold

From the tBTC v2 README:

> *"51-of-100"* — i.e. a simple majority of the sortition-selected signers can authorize any spend.

This is a **majority-trust** model, not a supermajority. Compared to sBTC's 71% threshold (§3), tBTC v2 is more aggressive on capital efficiency but more vulnerable to a collusion attack.

### §2.5 Trust model

| Question | Answer |
|---|---|
| Is there a custodian? | No single custodian; **federation of signers**. |
| Can the federation steal the BTC? | **Yes.** A 51-of-100 collusion can sign an arbitrary Bitcoin transaction redirecting the BTC. |
| Can the federation censor? | **Yes.** Signers can refuse to co-sign peg-outs, blocking redemptions. |
| Are the signers permissioned? | **Yes.** Signers must be approved by the Threshold DAO. (Stated to become permissionless in the future, but is currently permissioned.) |
| Real BTC locks or synthetic minting? | **Synthetic minting.** tBTC ERC-20 on Ethereum, backed 1:1 by BTC in threshold wallets. |
| What is the trigger for slashing? | Signers must stake T tokens. If they sign a fraudulent Bitcoin transaction (one not authorized by the Ethereum side), their T stake can be slashed. The fraud proof is a Bitcoin signature not corresponding to an Ethereum burn event. |
| Can the trigger be verified in Bitcoin Script? | **No.** The slashing trigger is verified on Ethereum (the T staking contract), not in Bitcoin Script. Bitcoin Script just sees a threshold ECDSA signature and accepts it. |

### §2.6 Cross-chain trust differences (Ethereum vs Base vs other chains)

From bitcoinlayers.org:

> *"Trust assumptions related to tBTC change per the chain it is deployed on. Ethereum is the accounting layer. For example, the tBTC gateway between Ethereum and Base is managed by a 6/9 multisig. This is a stronger trust assumption when compared to using tBTC on Ethereum."*

So tBTC on L2s is often **even more centralized** than on Ethereum mainnet — gateways are sometimes 6-of-9 multisigs.

### §2.7 How tBTC v2 differs from Babylon BTC Staking

| Property | Babylon BTC Staking v1/v2 | tBTC v2 |
|---|---|---|
| Lock real BTC? | ✅ | ✅ |
| Synthetic minting? | ❌ (no token minted; BTC secures PoS) | ✅ (tBTC ERC-20) |
| Trust model | Covenant committee (censor only; cannot steal) | Threshold signer federation (can steal with 51% collusion; can censor) |
| Trigger for slashing | FP EOTS double-sign (off-chain, on Babylon Genesis) | Fraudulent Bitcoin signature (verified on Ethereum) |
| Permissioned? | No (anyone can stake) | Yes (signer set approved by Threshold DAO) |
| Verifiable in Bitcoin Script? | ❌ (slashing trigger is off-chain) | ❌ (slashing trigger is on Ethereum) |

---

## §3 — sBTC: full technical breakdown

sBTC is Stacks' decentralized two-way Bitcoin peg. It is the **most theoretically decentralized** of the federation-based bridges, because the signer set is **open-membership** (anyone can become a signer if they lock enough STX) and the peg-out operations happen **on Bitcoin L1** (censorship-resistant).

### §3.1 How sBTC works

From the sBTC design paper (`stacks-network.github.io/stacks/sbtc.html`):

> *"We present a novel decentralized Bitcoin peg mechanism. Using this peg, a BTC-pegged asset can be issued on Bitcoin layers that is 1:1 pegged to BTC and does not rely on centralized or pre-determined actors for its functionality. Instead, the peg mechanism operates in a decentralized manner using an open-membership group of dynamic actors that are economically incentivized and can start or stop contributing to the peg functionality."*

Mechanism:

1. **Peg-in:** User locks BTC on Bitcoin L1, sends an op-return-style notice to the Stacks layer (via a Bitcoin transaction). Stackers (the dynamic signer set) observe this lock and mint sBTC on Stacks 1:1.
2. **Peg-out:** User burns sBTC on Stacks, sending a peg-out request via a Bitcoin transaction. Stackers threshold-sign a Bitcoin transaction paying out the BTC to the user's address.
3. **Threshold signing:** The Stackers (the set of addresses that locked STX in the current PoX reward cycle) collectively hold a threshold ECDSA / Schnorr key. **71% of Stackers** must cooperate to sign any peg-out.

### §3.2 The signer set — Proof of Transfer (PoX)

sBTC's signer set is **not permissioned**. Anyone can become a Stacker by locking STX in the Stacks PoX contract. This is the key innovation vs tBTC v2.

From the sBTC paper:

> *"The Stacks layer has a unique consensus protocol, Proof of Transfer (PoX), that leverages Bitcoin's Proof of Work (PoW) protocol and naturally supports sBTC. In PoX, Stackers lock up their capital and perform the task of threshold signing for peg-out transactions, and in return, are rewarded in BTC. Stacks miners spend BTC to mine Stacks blocks. It is this BTC that is distributed to Stackers as rewards."*

So Stackers are paid in BTC (from Stacks miners, who themselves spend BTC to mine). This creates the economic incentive to operate the peg honestly:

> *"This allows an incentive-compatible economic guarantee for a successful peg: for Stacks miners, it is always incentive-compatible to mine on the canonical fork, and for Stackers, faithfully maintaining the peg is always their most profitable course of action."*

### §3.3 The 71% threshold — and the trust model

From the sBTC paper's security assumptions section:

> *"A super majority of Stackers (71%) can steal BTC from the Bitcoin script/wallet on the Bitcoin L1. Stackers will forfeit their STX capital and BTC rewards if they do this, and it might be economically irrational (given they lock more capital than the value of sBTC supply) but it is theoretically possible. The more decentralized the set of Stackers, the harder is this type of attack to pull off; other than economic incentives, it's logistically challenging to convince hundreds or thousands of independent entities and people to coordinate and collude with each other to attempt such an attack."*

So:
- **71% collusion can steal BTC** (supermajority).
- Stackers forfeit their STX capital and BTC rewards — economic disincentive.
- The liveness ratio (§3.4) is meant to ensure STX locked > sBTC supply, so the theft is unprofitable.

And the 51% attack from Bitcoin miners:

> *"Bitcoin L1 miners can censor stacking operations in a long-range 51% attack and attempt to steal the BTC from the Bitcoin script/wallet. This potential attack is economically extremely hard to pull off, given (a) it requires Bitcoin miners to 51% attack the Bitcoin L1 chain for months (potentially 6+ months) and (b) purchase a large percent of STX liquid supply (at least 14%, worth approx $50M in Dec 2022)."*

### §3.4 Liveness Ratio — The Economic Safety Valve

The sBTC design includes a **Liveness Ratio** that constrains the maximum sBTC supply relative to the STX locked by Stackers. Per the sBTC paper:

> *"The design of both Normal and Recovery modes require careful consideration of the incentives for Stacks miners, stackers, and users."*

The exact formula isn't fully spelled out in the public paper, but the principle is: **the value of STX locked by Stackers must exceed the value of sBTC in circulation**, so that stealing the BTC (which would slash their STX) is unprofitable.

### §3.5 Why sBTC is more decentralized than tBTC v2

From the sBTC paper's comparison section:

> *"Both sBTC and tBTC rely on a signer set with economic security (similar to sBTC) and most of the differences between sBTC and tBTC stem from the tight integration of the Stacks layer with Bitcoin L1: Stacks has Bitcoin read support (so no need to rely on Bitcoin SPV), Stacks Nakamoto release transactions follow Bitcoin finality, and peg-out requests happen on Bitcoin L1 (vs relying on an external system like Ethereum)."*

So the key differences are:
1. **Open-membership** signer set (sBTC) vs **permissioned** signer set (tBTC v2).
2. **Peg-out requests happen on Bitcoin L1** (sBTC) — meaning Stacks miners cannot censor them; they are subject to Bitcoin's censorship resistance. tBTC v2 peg-outs happen on Ethereum.
3. **Stacks forks with Bitcoin L1** — Stacks state automatically follows Bitcoin L1 forks. This eliminates a class of fork attacks.
4. **71% threshold** (sBTC) vs **51% threshold** (tBTC v2) — sBTC is more conservative.

### §3.6 sBTC signer set today

From bitcoinlayers.org's review (2026):

> *"sBTC is a bridge between bitcoin and stacks managed by 14 institutional signers. sBTC on Stacks is backed by BTC held in a wallet managed by these signers."*

So while the **protocol design** is open-membership, the **current implementation** is a federation of 14 institutional signers. This is meant to expand over time as the protocol matures, but in production today it is functionally a federation.

From the Stacks docs (`docs.stacks.co/learn/sbtc/sbtc-signers`, Sep 11, 2026):

> *"A decentralized signer set is a living network, and rotation is part of its design. Signers commit infrastructure, key shares, and operational capacity."*

### §3.7 Trust model

| Question | Answer |
|---|---|
| Is there a custodian? | No single custodian; **federation** (currently 14 institutional signers; designed to be open-membership). |
| Can the federation steal the BTC? | **Yes.** A 71% collusion can sign an arbitrary Bitcoin transaction redirecting the BTC. (Economically irrational if liveness ratio holds.) |
| Can the federation censor? | **Harder than tBTC.** Peg-out requests are Bitcoin L1 transactions, so they inherit Bitcoin's censorship resistance. But the signers can refuse to threshold-sign the payout, blocking redemption. |
| Are the signers permissioned? | **No** (in design) — anyone can become a Stacker by locking STX. **Yes** (in current production) — only 14 approved institutional signers. |
| Real BTC locks or synthetic minting? | **Synthetic minting.** sBTC on Stacks, backed 1:1 by BTC in threshold wallets. |
| What is the trigger for slashing? | Signers' STX is slashed if they sign a fraudulent Bitcoin transaction (one not authorized by a Stacks peg-out). |
| Can the trigger be verified in Bitcoin Script? | **No.** Slashing trigger is verified on Stacks, not in Bitcoin Script. |
| Bitcoin L1 finality? | **Yes** — Stacks settles on Bitcoin L1 with 100% Bitcoin finality (Nakamoto release). |

---

## §4 — wBTC (Wrapped Bitcoin): full technical breakdown

wBTC is the simplest and most centralized of all the bridges. It is a **single-custodian** model with synthetic minting.

### §4.1 How wBTC works

From the original WBTC whitepaper (Jan 24, 2019, `wbtc.network/assets/wrapped-tokens-whitepaper.pdf`):

> *"This whitepaper proposes a framework for issuing asset backed tokens by addressing challenges with scalability, trust, regulation, and custody."*

And from Bitstamp's guide (`bitstamp.net/learn/cryptocurrency-guide/what-is-wrapped-bitcoin-wbtc`):

> *"WBTC is minted by a single custodian—BitGo—in exchange for BTC provided by merchants and held as collateral in a 1:1 ratio."*

Mechanism:

1. **Merchant** (a DAO-approved entity, e.g. a centralized exchange or a wrapping service) accepts BTC from a user.
2. Merchant performs KYC/AML on the user.
3. Merchant initiates a mint request with **BitGo** (the custodian).
4. BitGo verifies, takes custody of the BTC (in BitGo's cold wallets), and mints wBTC ERC-20 on Ethereum 1:1.
5. To redeem: user burns wBTC, BitGo releases the corresponding BTC from custody.

### §4.2 The custodian

From BitGo's own blog (`bitgo.com/resources/blog/launching-wrapped-bitcoin-wbtc-on-base`, Feb 28, 2024):

> *"As the designated custodian for WBTC, we've been committed to bringing BTC liquidity to other chains in a trusted and secure manner."*

And from BitGo (Feb 20, 2024):

> *"As the sole custodian for Wrapped Bitcoin (WBTC), BitGo's integration with Osmosis launches a fully backed native WBTC on Osmosis."*

In August 2024, BitGo announced a move to **multi-jurisdictional custody** to "diversify both custodial jurisdictions and locations for the underlying Bitcoin" — but BitGo remains the single custodian.

In October 2026, WBTC announced exploration of a **multi-custodian** model:

> *"WBTC is exploring a multi-custodian model for its Bitcoin reserves, moving away from a single-custodian setup to reduce reliance on any one [custodian]."* — wbtc.network/articles/wbtc-announces-exploration-of-multi-custodian-bitcoin-reserves (Oct 13, 2026)

But this is still in exploration — wBTC today is single-custodian.

### §4.3 Trust model

| Question | Answer |
|---|---|
| Is there a custodian? | **Yes.** BitGo is the sole custodian (with multi-jurisdictional cold storage since Aug 2024). |
| Can the custodian steal the BTC? | **Yes.** BitGo holds the keys; if compromised or coerced, they can sign an arbitrary Bitcoin transaction. |
| Can the custodian censor? | **Yes.** BitGo can refuse to mint or redeem wBTC for any user (KYC/AML blacklist). |
| Can the custodian be compelled? | **Yes.** BitGo is a regulated entity; it can be compelled by courts to freeze accounts. |
| Are merchants permissioned? | **Yes.** Merchants must be approved by the WBTC DAO. |
| Real BTC locks or synthetic minting? | **Synthetic minting.** wBTC ERC-20 on Ethereum (and several L2s), backed 1:1 by BTC in BitGo custody. |
| What is the trigger for slashing? | **None.** There is no slashing mechanism. If BitGo misbehaves, there is no on-chain recourse. |
| Can the trigger be verified in Bitcoin Script? | **N/A.** No slashing exists. |

### §4.4 wBTC vs BitGo custody model

The WBTC DAO is the governance layer (a multisig of institutional members including BitGo, Kyber, Republic, Ren, etc.), but the **custody** is BitGo-only. The DAO can swap out the custodian via governance, but during the swap window the BTC is still held by BitGo.

### §4.5 Risks

From the "WBTC: The Custodial Experiment That Failed" critique (`medium.com/@thankgodhumphrey7/wbtc-the-custodial-experiment-that-failed`):

> *"WBTC's design placed a heavy burden on the actors responsible for holding billions of dollars in Bitcoin. BitGo and its associated merchants..."*

The wBTC design is a single point of failure. If BitGo is compromised, goes bankrupt, or is compelled to freeze assets, wBTC holders have no on-chain recourse.

---

## §5 — DLCs (Discrete Log Contracts): full technical breakdown

DLCs are the most "Bitcoin-native" of the lock mechanisms. They were invented by Tadge Dryja (2017) and use **adaptor signatures** to condition Bitcoin payments on **oracle attestations**. They are real BTC locks (UTXOs), not synthetic minting.

### §5.1 How DLCs work

From the Bitcoin Optech topic page (`bitcoinops.org/en/topics/discreet-log-contracts`):

> *"Discreet Log Contracts (DLCs) are a method for two or more parties to enter into a contract that depends on the outcome of an event attested to by an oracle (or several oracles). After the event happens, the oracle publishes a commitment to the outcome of the event that the winning party can use to claim their funds. The oracle doesn't need to know the terms of the contract (or even that a contract was made). The transactions creating and settling the contract can be made indistinguishable from many other Bitcoin transactions or they can be executed within an LN channel. This makes DLCs more private and efficient than other known oracle-based contract methods. Additionally, DLCs are arguably more secure than earlier oracle-based methods because an oracle that commits to a false result generates clear evidence of fraud."*

The cryptographic foundation is the **adaptor signature** (also called pre-signature or one-time signature). From spark.money's research (`spark.money/research/discreet-log-contracts-bitcoin`, Feb 20, 2026):

> *"The cryptographic foundation of DLCs is the adaptor signature (sometimes called a signature adaptor or pre-signature). An adaptor signature is..."*

And from the DLC spec (`github.com/discreetlogcontracts/dlcspecs/blob/master/ECDSA-adaptor.md`):

> *"DLCs work by conditioning a transaction on the revelation of an oracle's signature. Adaptor signatures are an efficient form of verifiable signature..."*

Mechanism:

1. **Two parties** (e.g. Alice and Bob) want to bet on an event whose outcome will be attested by an oracle (Olivia).
2. Olivia commits, ahead of time, to a set of possible outcomes (e.g. "BTC price > $100k on Dec 31" → outcome=Yes or No). For each possible outcome, Olivia pre-commits to a specific **Schnorr / ECDSA nonce**.
3. Olivia publishes the nonces (one per outcome) ahead of time. The nonces are public.
4. Alice and Bob construct a **funding transaction** that locks BTC into a 2-of-2 multisig output (or a Taproot output with multi-party adaptor signatures).
5. They each pre-sign **Contract Execution Transactions (CETs)** for each possible outcome. The trick: each CET is signed with an **adaptor signature** that can only be completed if Alice/Bob learns the **oracle's nonce secret** corresponding to that outcome.
6. When the event happens, Olivia signs the outcome message (e.g. "Yes, BTC > $100k") using her private key with the corresponding nonce. The signature reveals the nonce secret.
7. The winning party (Alice if "Yes") uses the oracle's published signature to **complete the adaptor signature** on their CET and broadcast it, claiming the BTC.
8. The losing party cannot complete their CET (because they'd need a different nonce secret that the oracle never reveals).

### §5.2 The original Schnorr construction vs the ECDSA variant

From Bitcoin Optech:

> *"The original DLC construction was specific to schnorr signatures. Later, a version was developed to use signature adaptors that are compatible with Bitcoin's existing ECDSA signature scheme."*

Since Bitcoin's Taproot upgrade (Nov 2021), Schnorr signatures are natively supported (BIP-340). So DLCs can use either:
- **Schnorr adaptor signatures** (post-Taproot, simpler, more efficient).
- **ECDSA adaptor signatures** (pre-Taproot, more complex, but compatible with all existing Bitcoin transactions).

### §5.3 The oracle model

The oracle is the trust bottleneck of a DLC. The oracle:
- Commits to a set of outcomes (with nonces).
- Signs one outcome when the event happens.
- Cannot forge signatures for outcomes that didn't happen (because each outcome has a unique nonce, and the oracle only knows one nonce's secret).

**Fraud evidence:** If the oracle signs two different outcomes (i.e. equivocates), both signatures are published on-chain, and anyone can verify the oracle's fraud by computing the oracle's private key from the two signatures (using the same Schnorr-nonce-reuse math that Babylon's EOTS uses).

> *"An oracle that commits to a false result generates clear evidence of fraud."* — Bitcoin Optech

So the oracle **cannot** secretly lie; it can only lie publicly (signing two outcomes), which immediately exposes its private key and destroys its reputation. This is a **cryptographic** guarantee, not a game-theoretic one.

### §5.4 Multi-oracle DLCs

For higher assurance, DLCs can use **multiple oracles** with different threshold schemes:
- **Any-of-N**: any one oracle attesting allows execution (lower trust, but any single oracle can lie).
- **All-of-N**: all oracles must agree (higher trust, but censorship if any one oracle goes offline).
- **K-of-N**: K of N oracles must agree (balanced).

Each combination can be cryptographically enforced with adaptor signatures.

### §5.5 DLC use cases

- **Derivatives:** Bitcoin-settled BTC/USD futures, options.
- **Insurance:** BTC payout if a flight is delayed, a hurricane hits, etc.
- **Loans:** BTC locked as collateral, with the loan terms (liquidation trigger = BTC/USD price drop) attested by an oracle. (E.g. Lava Loans, 2023.)
- **Multiparty contracts:** Coin swaps, prediction markets.

### §5.6 Trust model

| Question | Answer |
|---|---|
| Is there a custodian? | **No.** BTC stays in a 2-of-2 multisig (or Taproot adaptor) between the parties. |
| Can the counterparty steal the BTC? | **No.** Counterparty cannot redirect BTC unilaterally. |
| Can the counterparty censor? | **Yes (liveness).** If the counterparty refuses to co-sign the funding transaction or the refund transaction, the protocol can stall. Mitigated by **refund transactions** with timelocks. |
| Can the oracle lie? | **Yes, but at the cost of exposing its private key.** The lie is publicly detectable. The oracle's signature is the trigger. |
| Can the oracle censor? | **Yes (by refusing to attest).** If the oracle goes offline, the DLC cannot execute. Mitigated by multi-oracle setups with any-of-N. |
| Real BTC locks or synthetic minting? | **Real BTC locks.** BTC stays in a UTXO; no synthetic minting. |
| What is the trigger for execution? | The oracle's signature on an outcome message. |
| Can the trigger be verified in Bitcoin Script? | **Yes — partially.** This is the key insight. The oracle's signature is verified by the adaptor signature mechanism: the winning party completes the adaptor using the oracle's published signature. The verification happens implicitly through the Schnorr/ECDSA math, **not** through explicit opcode verification of the oracle's signature. (See §8 for what Bitcoin Script CAN and CANNOT do here.) |

### §5.7 Why DLCs are "almost" trustless — but not quite

The remaining trust in a DLC is:
1. **Oracle liveness** — if the oracle goes offline, the DLC cannot execute (until the refund timelock expires).
2. **Oracle honesty** — if the oracle signs a false outcome, it loses its private key and reputation, but the false outcome *does execute*. (Unless a fraud-proof window with multiple oracles is used.)
3. **Counterparty liveness** — if a counterparty goes offline during setup or refund, you need timelocked refunds to recover.

The DLC *itself* (the Bitcoin transaction structure) is trustless. The oracle is the trust bottleneck.

### §5.8 CTV + CSFS would make DLCs much more efficient

From Bitcoin Optech:

> *"Proposal for vault-enabling opcodes could also make DLCs much more efficient"* (2022)
> *"Summary and criticism of CTV + CSFS benefits for discreet log contracts (DLCs)"* (2025)

If `OP_CHECKTEMPLATEVERIFY` (BIP 119) and `OP_CHECKSIGFROMSTACK` (BIP 348) were activated, DLCs could be constructed more efficiently — see §8 for details.

---

## §6 — Comparison Matrix (all 5 mechanisms)

### §6.1 Trust model

| Mechanism | Trust assumption | Who can steal BTC? | Who can censor? | Real BTC locks? | Synthetic minting? |
|---|---|---|---|---|---|
| **Babylon BTC Staking v1/v2** | Covenant committee (M-of-N multisig) co-signs unbonding & slashing | **Nobody** (no script path redirects to committee) | **Covenant committee** (refuses to co-sign unbonding) + **Babylon Genesis validators** (can censor slash signal) | ✅ Real BTC in Taproot output | ❌ (BABY rewards on Babylon Genesis, but no synthetic BTC) |
| **Babylon TBV** | Pre-signed paths + ZK proof verified in Bitcoin Script via BABE | **Nobody** (every spend pre-signed at creation; only ZK-verified proofs unlock) | **No one for spend** (depositor self-claim + 2016-block CSV recovery) | ✅ Real BTC in Taproot output | ❌ (collateral record is non-transferable, internal to Aave Adapter) |
| **tBTC v2** | Federation of 100 signers, 51-of-100 threshold ECDSA | **Yes — 51-of-100 collusion** can sign arbitrary Bitcoin tx | **Yes — signers** can refuse to co-sign peg-outs; **Threshold DAO** can blacklist | ✅ Real BTC in threshold wallet | ✅ tBTC ERC-20 on Ethereum |
| **sBTC** | Federation of Stackers (currently 14 institutional), 71% threshold | **Yes — 71% Stackers** can sign arbitrary Bitcoin tx | **Signers** can refuse to co-sign; mitigated by L1 peg-out requests | ✅ Real BTC in threshold wallet | ✅ sBTC on Stacks |
| **wBTC** | Single custodian (BitGo) | **Yes — BitGo** can sign arbitrary Bitcoin tx | **Yes — BitGo** can refuse mint/redeem; can be compelled | ✅ Real BTC in BitGo custody | ✅ wBTC ERC-20 on Ethereum (and L2s) |
| **DLCs** | Oracle(s) attest to outcome; counterparty co-signs funding/refund | **Counterparty** cannot steal; **oracle** can sign false outcome (loses key, but execution happens) | **Counterparty** can stall (mitigated by timelocked refunds); **oracle** can refuse to attest (mitigated by multi-oracle) | ✅ Real BTC in 2-of-2 multisig / Taproot | ❌ (no token minted; DLC settles in BTC) |

### §6.2 Slashing / liquidation trigger

| Mechanism | Slashing/liquidation trigger | Trigger location | Trigger verifiable in Bitcoin Script? |
|---|---|---|---|
| **Babylon BTC Staking v1/v2** | FP double-signs on Babylon Genesis (EOTS nonce reuse → private key leaks) | Babylon Genesis chain (off-Bitcoin) | ❌ No. EOTS evidence verified on Babylon Genesis, not in Bitcoin Script. Bitcoin Script only checks that the FP's leaked key + staker's pre-sig + covenant sig are all valid. |
| **Babylon TBV** | Health factor < 1.0 on Aave V4 → liquidation event on Ethereum | Ethereum (Aave V4 Hub) | ✅ **YES** — BABE verifies a ZK proof of the Ethereum redemption event inside Bitcoin Script using only existing primitives. |
| **tBTC v2** | Signers sign a fraudulent Bitcoin tx (one not authorized by Ethereum burn) | Ethereum (T staking contract) | ❌ No. Verified on Ethereum. |
| **sBTC** | Signers sign a fraudulent Bitcoin tx (one not authorized by Stacks peg-out) | Stacks layer | ❌ No. Verified on Stacks. |
| **wBTC** | None | N/A | N/A |
| **DLCs** | Oracle signs an outcome | Oracle (off-chain, then on-chain via signature publication) | ⚠ Partial. The oracle's signature is verified **implicitly** via adaptor signature math (the winning party uses the oracle's signature to complete the adaptor). Bitcoin Script does NOT explicitly call `OP_CHECKSIGFROMSTACK` against the oracle's signature — that would require BIP 348. |

### §6.3 Capital efficiency and liveness

| Mechanism | Time-to-peg-in | Time-to-peg-out | Capital efficiency |
|---|---|---|---|
| **Babylon BTC Staking v1/v2** | ~10 min (1 Bitcoin confirmation for activation) | Timelock (up to 64000 blocks ≈ 15 months), or unbonding (301 blocks ≈ 50 hours) | BTC is locked for the duration; no leverage |
| **Babylon TBV** | ~2 hours (Bitcoin confirmations on signet) | ~3 days (challenge window) | BTC is collateral; user can borrow against it |
| **tBTC v2** | ~1 hour (Bitcoin confirmations) | ~1 hour (signer response) | Signers must stake T tokens; BTC is freely usable as tBTC |
| **sBTC** | ~10 min | ~24 hours (150 blocks per sBTC paper, though peg-out is initiated on L1) | Stackers must lock STX (liveness ratio) |
| **wBTC** | Minutes (merchant KYC) | Hours (BitGo settlement) | No collateral constraints; instant issuance |
| **DLCs** | Immediate (between two parties) | Refund timelock (typically days); execution when oracle attests | Two-party; capital is locked until outcome |

---

## §7 — The Fundamental Weakness of All Existing Solutions

### §7.1 The Four Archetypes of Trust

Every existing BTC lock mechanism falls into one of four archetypes:

1. **Custodian (wBTC)** — single entity holds the keys.
2. **Federation (tBTC v2, sBTC, Babylon BTC Staking v1/v2)** — M-of-N committee must cooperate.
3. **Oracle (DLCs)** — oracle attests to an outcome.
4. **ZK-verified (Babylon TBV)** — proof of an off-chain event verified in Bitcoin Script.

None of these has **zero trust assumptions**. Every one of them asks the BTC holder to trust *someone other than Bitcoin L1 consensus*.

### §7.2 The Trust Hierarchy (from worst to best)

| Rank | Mechanism | Trust assumption | Severity |
|---|---|---|---|
| 6 | wBTC | Single custodian (BitGo) | Catastrophic — single point of failure, regulatable, freezable |
| 5 | tBTC v2 | Permissioned federation (51-of-100, DAO-approved) | Severe — 51% collusion can steal; DAO can blacklist |
| 4 | sBTC (current prod) | 14-institutional-signer federation (71% threshold) | Moderate — collusion theoretically possible, logistically hard |
| 3 | sBTC (design) | Open-membership federation (71% threshold, STX-staked) | Lower — open-membership, but still 71% collusion can steal |
| 2 | Babylon BTC Staking v1/v2 | Covenant committee (M-of-N) co-signs | Low — **committee cannot steal**, only censor; slashing is EOTS-guaranteed |
| 1 | Babylon TBV | Pre-signed paths + ZK proof verified in Bitcoin Script | Lowest existing — but still requires trust in the ZK proof system, the SP1 prover, the BABE protocol, and the Ethereum event being proven |

### §7.3 Why even Babylon TBV is not "zero trust"

Babylon TBV is the closest existing solution to "zero trust", but it still has these residual trust assumptions:

1. **Trust in the SP1 / Groth16 proof system** — if the ZK proof system has a soundness bug, a malicious prover could forge a proof of an Ethereum redemption event that didn't happen.
2. **Trust in the BABE protocol** — the garbled circuit construction that compresses the ZK verification into Bitcoin Script. If BABE has a bug, the verification could be bypassed.
3. **Trust in the Ethereum event being proven** — the proof attests to an Ethereum event (e.g. "depositor burned their collateral record on Aave V4"). If the Ethereum contract has a bug (e.g. the AaveAdapter allows unauthorized burns), the BTC can be released for invalid reasons.
4. **Trust in the depositor's WOTS key** — the self-claim path uses WOTS, which is one-time. If the depositor reuses a WOTS key, they lose their BTC.
5. **Trust in the Vault Provider's liveness during peg-in** — if the Vault Provider disappears between peg-in and activation, the BTC is in the "Pre-PegIn output" with a 2016-block (~14 day) CSV timelock. After that, the depositor recovers via the self-claim path. This is recovery, not theft, but it requires the depositor to actively monitor and act.
6. **Trust in the Bitcoin script invariants** — if the Taproot script tree is malformed (e.g. a script path is missing), the BTC could be unrecoverable or stuck.
7. **Trust in the Ethereum Chainlink oracles** — liquidation is triggered by Chainlink BTC/USD. If Chainlink is compromised, a position can be falsely liquidated (the BTC isn't stolen, but the depositor is force-liquidated at a bad price).

So **even Babylon TBV has trust assumptions**. They're just *cryptographic* trust (in ZK proofs and garbled circuits) rather than *fiduciary* trust (in a custodian or committee).

### §7.4 The Trust-Bypass Equation

For a BTC lock to be **truly zero-trust** (no custodian, no federation, no oracle, no ZK proof system), the trigger for release must be **verifiable by Bitcoin L1 consensus alone**. That means:

1. The trigger must be expressible in **current Bitcoin Script** (no soft fork).
2. The trigger must be **deterministic** — no off-chain committee, no off-chain oracle.
3. The trigger must be **publicly observable** — anyone can verify it by inspecting Bitcoin L1.
4. The trigger must be **unforgeable** — no party can fabricate the trigger.

The ONLY such triggers available in current Bitcoin Script are:
- **Timelocks** (OP_CHECKLOCKTIMEVERIFY / OP_CHECKSEQUENCEVERIFY) — deterministic, but boring (just "wait N blocks").
- **Hash preimage revelation** (OP_HASH256 / OP_HASH160 / OP_SHA256 / OP_RIPEMD160 + OP_EQUAL) — the classic HTLC pattern. The trigger is "reveal a preimage that hashes to X". Deterministic, publicly observable, unforgeable (assuming the hash function is collision-resistant).
- **Signature verification** (OP_CHECKSIG / OP_CHECKSIGVERIFY / OP_CHECKSIGADD) — the trigger is "produce a valid signature under public key P". Deterministic, publicly observable, unforgeable (assuming the signature scheme is unforgeable).

Anything beyond these three requires either (a) a soft fork (CTV, CSFS, CAT, TXHASH) or (b) a BitVM-style optimistic challenge protocol with pre-signed paths (which is what Babylon TBV does, and which has the residual trust assumptions listed in §7.3).

### §7.5 The Fundamental Weakness — Restated

> **Every existing BTC lock mechanism either (a) trusts a custodian, (b) trusts a federation, (c) trusts an oracle, (d) trusts a ZK proof system, or (e) requires a Bitcoin soft fork.**
>
> **There is no existing BTC lock mechanism that (i) is deployable on Bitcoin mainnet today, (ii) has zero trust assumptions beyond Bitcoin L1 consensus, and (iii) has a trigger more expressive than "wait N blocks" or "reveal a hash preimage".**

This is the gap that TRION's "Coherence Vault" (§10) aims to fill — by using a **hash preimage revelation** as the trigger, where the preimage is derived from TRION's HashDNA behavioral coherence computation, computed **off-chain** but **publicly verifiable** by anyone with the same input data.

---

## §8 — Bitcoin Script Capabilities (What CAN Be Verified Today)

This section is the foundation for §9 and §10. We need to know **exactly** what Bitcoin Script can verify on mainnet today, without any soft fork.

### §8.1 Active Opcodes (Mainnet, as of 2026)

From the Spark Bitcoin Opcode Reference (`spark.money/tools/bitcoin-opcode-reference`):

**Hash functions:**

| Opcode | Hex | Description |
|---|---|---|
| `OP_RIPEMD160` | 0xa6 | Hash top item with RIPEMD-160 (20-byte output) |
| `OP_SHA1` | 0xa7 | Hash top item with SHA-1 (20-byte output) |
| `OP_SHA256` | 0xa8 | Hash top item with SHA-256 (32-byte output) |
| `OP_HASH160` | 0xa9 | SHA-256 then RIPEMD-160 (20-byte output, used in P2PKH/P2SH) |
| `OP_HASH256` | 0xaa | Double SHA-256 (32-byte output, Bitcoin's own txid hash) |

**Bitcoin Script does NOT have:**
- `OP_SHA3-256` — no SHA-3 family hash function.
- `OP_KECCAK256` — no Keccak.
- `OP_BLAKE2B`, `OP_BLAKE3` — no Blake family.
- Any hash function beyond SHA-256, SHA-1, RIPEMD-160.

**Signature verification:**

| Opcode | Hex | Description |
|---|---|---|
| `OP_CHECKSIG` | 0xac | Pop pubkey and signature; push 1 if valid for the transaction |
| `OP_CHECKSIGVERIFY` | 0xad | OP_CHECKSIG followed by OP_VERIFY |
| `OP_CHECKMULTISIG` | 0xae | M-of-N multisig verification (disabled in Tapscript) |
| `OP_CHECKMULTISIGVERIFY` | 0xaf | OP_CHECKMULTISIG followed by OP_VERIFY |
| `OP_CHECKSIGADD` | 0xba | Tapscript only (BIP 342); replaces OP_CHECKMULTISIG with incremental signature counting |

**Critical limitation:** `OP_CHECKSIG` and `OP_CHECKSIGADD` verify signatures against the **transaction sighash** — i.e. the signature must be a signature over the spending transaction itself. **Bitcoin Script CANNOT verify a signature over arbitrary data.**

To verify a signature over arbitrary data, you would need `OP_CHECKSIGFROMSTACK` (BIP 348), which is **proposed but not active** (see §8.3).

**Timelocks:**

| Opcode | Hex | Description |
|---|---|---|
| `OP_CHECKLOCKTIMEVERIFY` (CLTV) | 0xb1 | BIP 65; fail if top stack value exceeds tx nLockTime; enforces **absolute** time locks (block height or Unix timestamp) |
| `OP_CHECKSEQUENCEVERIFY` (CSV) | 0xb2 | BIP 112; fail if top stack value exceeds tx nSequence; enforces **relative** time locks (blocks since confirmation) |

**Arithmetic (active):**

| Opcode | Hex | Description |
|---|---|---|
| `OP_ADD` | 0x93 | a + b |
| `OP_SUB` | 0x94 | a - b |
| `OP_1ADD` / `OP_1SUB` | 0x8b / 0x8c | Add / subtract 1 |
| `OP_NEGATE` | 0x8f | Flip sign |
| `OP_ABS` | 0x90 | Absolute value |
| `OP_NOT` | 0x91 | Push 1 if top is 0, else push 0 |
| `OP_NUMEQUAL` | 0x9c | Push 1 if a equals b (numeric) |
| `OP_LESSTHAN` / `OP_GREATERTHAN` | 0x9f / 0xa0 | Numeric comparison |
| `OP_WITHIN` | 0xa5 | Push 1 if x is within [min, max) |
| `OP_MIN` / `OP_MAX` | 0xa3 / 0xa4 | Min / max |

**Disabled arithmetic (since 2010):**

| Opcode | Status | Reason |
|---|---|---|
| `OP_MUL` | Disabled | Implementation bug |
| `OP_DIV`, `OP_MOD` | Disabled | Implementation bug |
| `OP_LSHIFT`, `OP_RSHIFT` | Disabled | Implementation bug |

So Bitcoin Script **cannot multiply** two numbers, **cannot divide**, **cannot compute modular exponentiation**. This is a hard limit on what it can verify cryptographically.

**Stack and flow control:**

All standard opcodes active: `OP_DUP`, `OP_DROP`, `OP_SWAP`, `OP_ROT`, `OP_PICK`, `OP_ROLL`, `OP_2DUP`, `OP_3DUP`, `OP_OVER`, `OP_NIP`, `OP_TUCK`, `OP_IFDUP`, `OP_DEPTH`, `OP_SIZE`, `OP_IF` / `OP_NOTIF` / `OP_ELSE` / `OP_ENDIF`, `OP_VERIFY`, `OP_RETURN`, `OP_TOALTSTACK` / `OP_FROMALTSTACK`.

**No loops.** Bitcoin Script has only `OP_IF` / `OP_ELSE` / `OP_ENDIF` for branching. No `OP_WHILE`, no recursion. Execution is bounded by the script size limit (4 MB for Taproot leaf scripts).

### §8.2 What Bitcoin Script CAN Verify Today (Summary)

Given the opcodes above, Bitcoin Script can verify:

1. **Hash preimage revelation** — "I will reveal a 32-byte value X such that `SHA256(X) = H`" (via `OP_SHA256 <H> OP_EQUAL`).
   - 20-byte hash: `OP_HASH160` (SHA-256 then RIPEMD-160).
   - 32-byte hash: `OP_SHA256` (single SHA-256) or `OP_HASH256` (double SHA-256, Bitcoin's txid hash).
2. **Schnorr / ECDSA signatures over the spending transaction** — via `OP_CHECKSIG` / `OP_CHECKSIGVERIFY` / `OP_CHECKSIGADD`. The signature must commit to the spending transaction's sighash (BIP-143 for SegWit, BIP-341 for Taproot).
3. **Absolute timelocks** — via `OP_CHECKLOCKTIMEVERIFY` (BIP-65).
4. **Relative timelocks** — via `OP_CHECKSEQUENCEVERIFY` (BIP-112).
5. **M-of-N multisig** — via `OP_CHECKSIGADD` (Taproot) or `OP_CHECKMULTISIG` (legacy).
6. **Conditional branching** — via `OP_IF` / `OP_ELSE` / `OP_ENDIF`.
7. **Numeric comparison** — `OP_EQUAL`, `OP_NUMEQUAL`, `OP_LESSTHAN`, `OP_GREATERTHAN`, `OP_WITHIN`.
8. **Simple arithmetic** — `OP_ADD`, `OP_SUB`, `OP_MIN`, `OP_MAX` (no multiplication, no division).

### §8.3 What Bitcoin Script CANNOT Verify Today

1. **A Schnorr / ECDSA signature over arbitrary data** (not the spending tx). This would require `OP_CHECKSIGFROMSTACK` (BIP 348), which is **proposed but not active**. Without CSFS, you cannot verify that "Alice signed message M" inside Bitcoin Script. You can only verify that "Alice signed this spending transaction".
2. **SHA3-256, Keccak-256, Blake2b, Blake3** — none of these hash functions are available. Only SHA-256, SHA-1, RIPEMD-160, and double-SHA-256.
3. **Concatenation of stack elements** — `OP_CAT` was disabled in 2010. BIP 347 proposes reactivating it in Tapscript, but it is **not active**. Without `OP_CAT`, you cannot concatenate two stack values to form a longer preimage. (Workarounds exist using `OP_SIZE` and pre-computed hashes, but they're limited.)
4. **Recurse / introspect the spending transaction** — without `OP_TXHASH` (BIP 346) or `OP_CTV` (BIP 119), Bitcoin Script cannot commit to specific spending-transaction templates. (Workaround: pre-signed transactions where the spending tx is fixed at signing time.)
5. **Verify a ZK proof natively** — there is no `OP_VERIFY_ZK` opcode. (Babylon TBV works around this via BitVM-style optimistic challenge + WOTS commitments — see §1.6, §1.7.)
6. **Verify a Merkle proof of an off-chain event** — not without `OP_CAT` (to concatenate path elements) and either `OP_TXHASH` or pre-signed paths. (BitVM uses WOTS to commit to Merkle roots.)

### §8.4 The Three Design Patterns for Bitcoin-Native Triggers

Given the above, there are exactly **three patterns** for building a "trigger" in Bitcoin Script today:

#### Pattern A — HTLC (Hash Time-Locked Contract)

```bitcoin
OP_IF
    OP_SHA256 <H> OP_EQUALVERIFY  <PayeePk> OP_CHECKSIG
OP_ELSE
    <TimelockBlocks> OP_CHECKSEQUENCEVERIFY OP_DROP  <RefunderPk> OP_CHECKSIG
OP_ENDIF
```

- Trigger: someone reveals a 32-byte preimage X such that `SHA256(X) = H`.
- Fallback: timelock expires, refunder recovers.
- **This is the only pattern that allows an off-chain-determined value (the preimage) to trigger an on-chain release.**

#### Pattern B — Multi-Signature with Pre-Signed Refund

```bitcoin
OP_IF
    <AlicePk> OP_CHECKSIGVERIFY  <BobPk> OP_CHECKSIG  // 2-of-2 multisig
OP_ELSE
    <TimelockBlocks> OP_CHECKSEQUENCEVERIFY OP_DROP  <AlicePk> OP_CHECKSIG  // refund after timeout
OP_ENDIF
```

- Trigger: Alice and Bob both sign the spending transaction (cooperation).
- Fallback: timelock expires, Alice recovers.
- This is the Lightning / DLC pattern. Babylon BTC Staking's unbonding path is a variant of this (staker + covenant quorum).

#### Pattern C — BitVM-Style Optimistic Challenge (Pre-Signed + WOTS-Committed)

This is what Babylon TBV uses. The structure is complex but conceptually:

1. At peg-in, the depositor and the protocol co-sign a **tree of pre-signed transactions** — every legitimate spending path is pre-signed at creation.
2. Each spending path is gated by a **WOTS (Winternitz One-Time Signature)** commitment: the script reveals a series of hash preimages that correspond to a specific computation outcome (e.g. "the ZK proof verified successfully").
3. The challenger (anyone, in BitVM2) can dispute a false claim by revealing a contradictory WOTS preimage — proving the prover equivocated.
4. If no challenge succeeds within a timelock, the claim executes.

- Trigger: a ZK proof of an off-chain event, verified via WOTS commitments inside Bitcoin Script.
- Fallback: challenge window expires.
- This is the most expressive pattern but is **complex and expensive** (large scripts, many pre-signed txs).

### §8.5 The Key Question: Can Bitcoin Script Verify a HashDNA Sense Hash?

TRION's HashDNA (per the audit docs) is defined as:

> `BH(event, t) = Hash_DNA(entity_id ‖ event_type ‖ magnitude_norm ‖ ctx ‖ ts ‖ chain_id ‖ block_hash)`
>
> `sense = SHA3-256(payload ‖ 0x00); antisense = SHA3-256(payload ‖ 0xFF) ⊕ NOT(sense)`

The 93-byte preimage layout: `entity_id[32] | event_type[1] | mag_nano[8] | ctx[8] | ts[8] | chain_id[4] | block_hash[32]`.

**The problem:** Bitcoin Script cannot compute SHA3-256. It only has SHA-256, SHA-1, RIPEMD-160, and double-SHA-256.

**Three possible adaptations:**

#### Option 1 — Use Bitcoin's Native Hash Function (SHA-256 / Double SHA-256)

Define a Bitcoin-compatible HashDNA:

```
BHDNA(payload) = HASH256(payload) = SHA256(SHA256(payload))
```

This is the same hash function Bitcoin uses for txids and block hashes. It is **natively supported** by `OP_HASH256`. The dual-strand property can be preserved:

```
sense_btc   = HASH256(payload ‖ 0x00)
antisense_btc = HASH256(payload ‖ 0xFF) ⊕ NOT(sense_btc)
```

where `⊕` is XOR (Bitcoin Script has `OP_XOR`? — actually no, Bitcoin Script does NOT have `OP_XOR` directly. But you can emulate XOR using bit operations or by revealing preimages separately.)

Actually, **Bitcoin Script does not have `OP_XOR`**. So the XOR step needs to be computed off-chain and the result revealed as a preimage. The script can verify `OP_HASH256 <preimage> OP_EQUAL` against a committed `sense_btc` value, but cannot compute the XOR itself.

**Workaround:** Commit to both `sense_btc` and `antisense_btc` as two separate 32-byte values in the script. The triggering party must reveal BOTH preimages:
```
OP_HASH256 <sense_btc_hash> OP_EQUALVERIFY
OP_HASH256 <antisense_btc_hash> OP_EQUALVERIFY
```
This loses the dual-strand property (because the relationship between sense and antisense isn't enforced on-chain — both preimages are independent), but it preserves the **commitment** to the behavioral event.

#### Option 2 — Use RIPEMD-160 for Compactness

```
BHDNA_compact(payload) = HASH160(payload) = RIPEMD160(SHA256(payload))
```

This produces a 20-byte hash (smaller script), supported by `OP_HASH160`. Used by P2PKH and P2SH addresses. But it loses more bits (160 vs 256), so collision resistance is weaker.

#### Option 3 — Use BitVM-Style Verification to Verify SHA3-256 Computation

BitVM-style verification can verify ANY computation, including SHA3-256. But this requires:
- A large pre-signed transaction graph.
- WOTS commitments to each intermediate state.
- A challenge window (optimistic).

This is the most general approach, but it is the most complex and expensive. **For TRION's Coherence Vault, Option 1 (use Bitcoin's native double-SHA-256) is likely the right choice** because it gives the simplest, cheapest, and most robust Bitcoin-native trigger.

### §8.6 Can Bitcoin Script Verify a "Coherence Score"?

TRION's coherence score is a numeric value (e.g. 0.92) computed off-chain from a set of behavioral hashes. The question: can Bitcoin Script verify that a given coherence score is correct, given a set of behavioral hashes?

**The challenge:** Computing the coherence score requires:
1. Reading the behavioral hashes (off-chain).
2. Applying TRION's coherence function (e.g. cosine similarity, weighted sum, threshold).
3. Producing a single numeric score.

Bitcoin Script cannot do step 2 directly because:
- It cannot multiply (no `OP_MUL`).
- It cannot compute cosine similarity (no division, no square root).
- It cannot iterate over a variable-length set of hashes (no loops).

**But Bitcoin Script CAN verify a precomputed coherence score via hash preimage revelation.** The pattern:

1. Off-chain, the TRION network computes the coherence score `C` for a given behavioral event set `S`.
2. The TRION network publishes a commitment `H = SHA256(S || C || nonce)` on Bitcoin L1 (e.g. via an OP_RETURN, or as a preimage hash in a Taproot leaf).
3. To unlock the BTC, the unlocking party must reveal:
   - The full set `S` of behavioral hashes.
   - The coherence score `C`.
   - The nonce.
4. The Bitcoin Script verifies:
   - `SHA256(S || C || nonce) == H` (the commitment matches).
   - `C >= threshold` (the coherence score exceeds the threshold, via `OP_GREATERTHAN` or `OP_WITHIN`).
   - Optionally: each behavioral hash in `S` matches its own commitment (via separate `OP_HASH256` checks).

This is the **"reveal a preimage" pattern (HTLC variant)**. The trigger is the revelation of the preimage `S || C || nonce` that hashes to `H` AND satisfies `C >= threshold`.

**Key insight:** This pattern doesn't require any soft fork. It only uses `OP_SHA256`, `OP_EQUAL`, `OP_GREATERTHAN`, `OP_CHECKSIG`, and `OP_CHECKSEQUENCEVERIFY`. All of these are active today.

**Limitation:** The "verification" is **not** that the coherence score is correctly computed — that requires re-running TRION's coherence function, which Bitcoin Script cannot do. The verification is only that **someone committed to a specific `(S, C)` pair ahead of time**, and the unlocking party reveals that committed pair plus the threshold check.

So the trust assumption shifts from "trust the committee" to "trust the committer" — i.e. whoever published `H = SHA256(S || C || nonce)` on Bitcoin L1 must be trusted to (a) compute `C` correctly and (b) commit honestly.

**This is a fundamental limit.** Without `OP_CAT` + `OP_CHECKSIGFROMSTACK` (both proposed but not active), Bitcoin Script cannot verify an arbitrary computation over revealed data. It can only verify:
- That the revealed data hashes to a committed value.
- That the revealed data satisfies a simple comparison (equal, less-than, greater-than, within).

The "coherence" computation must be done off-chain and committed on-chain. The on-chain verification is "did the committed coherence score exceed the threshold?".

### §8.7 The Soft-Fork Horizon

If `OP_CAT` (BIP 347) and `OP_CHECKSIGFROMSTACK` (BIP 348) were activated:

- `OP_CAT` would allow concatenating stack elements → enabling Merkle proof verification, multi-message signature verification, and recursive covenant constructions.
- `OP_CHECKSIGFROMSTACK` would allow verifying Schnorr signatures over arbitrary messages (not just the spending tx) → enabling DLCs to be more efficient, oracle-based contracts to be verified natively, and **direct verification of behavioral hashes signed by TRION validators**.

With both, you could verify:
- A Schnorr signature over `(S, C)` under a TRION-aggregate public key.
- That the signature commits to a specific coherence score `C`.
- That `C >= threshold`.

This would eliminate the need for the "committed hash preimage" pattern and allow true **on-chain verification of off-chain coherence attestation**.

But BIP 347 and BIP 348 are **not active**. Per the Spark opcode reference (March 2026):
> *"BIP 347 was marked specification-complete in March 2026 but still requires a separate soft fork activation."*
> *"BIP 348 specification was merged in December 2024 and is available for testing on signet."*

No confirmed activation timeline. **TRION must design for current mainnet Script.**

---

## §9 — How TRION Can Be Fundamentally Different (5+ Design Principles)

Given §1-§8, here are 5+ design principles that make TRION's Coherence Vault **fundamentally different** from every existing BTC lock mechanism.

### §9.1 Principle 1 — No Custodian, No Federation, No Oracle, No ZK Proof System

Every existing mechanism trusts *someone*:
- wBTC → BitGo
- tBTC v2 → 100 signers + Threshold DAO
- sBTC → 14-71% Stackers
- Babylon BTC Staking v1/v2 → Covenant committee
- Babylon TBV → ZK proof system + SP1 + BABE + Vault Provider
- DLCs → Oracle

TRION's Coherence Vault should trust **only Bitcoin L1 consensus + the cryptographic hardness of SHA-256**.

**How:** The trigger for BTC release is a **hash preimage revelation** that commits to a behavioral event (a HashDNA) and a coherence score. The hash function is Bitcoin's native `OP_SHA256` / `OP_HASH256`. No external attestation, no committee signature, no ZK proof.

### §9.2 Principle 2 — The Trigger Is Behavioral, Not Custodial

Every existing mechanism's trigger is either:
- **Time-based** (Babylon BTC Staking timelock; wBTC redemption window; DLC refund).
- **Custody-based** (tBTC, sBTC, wBTC — the custodian/federation signs).
- **Off-chain event-based** (Babylon TBV — Ethereum event verified via ZK; DLCs — oracle attests).

None of them trigger release based on **the behavioral coherence of an entity over time**.

**TRION's design:** The trigger is *"the entity behaved coherently for N consecutive rounds, and the latest coherence score exceeds threshold T"*. This is a **behavioral predicate**, not a custody predicate or an event predicate.

The behavioral predicate is computed off-chain by the TRION network (using HashDNA + the 7-plane coherence function). The on-chain trigger is the revelation of a preimage that hashes to a commitment, where the commitment was published by the TRION network on Bitcoin L1.

This is **fundamentally new**. No existing BTC lock mechanism has a behavioral trigger.

### §9.3 Principle 3 — The Trigger Is Publicly Verifiable, Not Permissioned

Every existing mechanism's trigger requires either:
- **A specific party's signature** (custodian, federation, committee).
- **A specific oracle's attestation** (DLCs).
- **A specific ZK proof** (Babylon TBV).

None of them allow **anyone** to trigger the release by simply revealing a preimage.

**TRION's design:** The trigger is a preimage revelation. **Anyone** who learns the preimage can trigger the release. The preimage is the behavioral event + coherence score + nonce. The preimage is published by the TRION network (in a public forum — e.g. on Bitcoin L1 via OP_RETURN, or on the TRION mesh).

This means:
- **No committee** needs to co-sign.
- **No oracle** needs to attest.
- **No custodian** needs to approve.
- **Anyone** can trigger the release, but only **after** the behavioral predicate is satisfied (i.e. the preimage is only revealed once the coherence threshold is met).

This is the **HTLC pattern** (Pattern A in §8.4), but applied to behavioral coherence instead of payment routing.

### §9.4 Principle 4 — The Trigger Is Hash-Committed, Not Signature-Committed

Every existing mechanism commits to its trigger via a signature:
- wBTC: BitGo's signature on a mint/redeem tx.
- tBTC v2: 51-of-100 threshold ECDSA signature.
- sBTC: 71% threshold signature.
- Babylon BTC Staking: covenant committee signatures.
- Babylon TBV: WOTS + ZK proof.
- DLCs: oracle signature + adaptor signatures.

None of them commit via a **hash preimage** that the unlocking party must reveal.

**TRION's design:** The commitment is `H = SHA256(behavioral_event || coherence_score || nonce)`. The unlocking party must reveal `(behavioral_event, coherence_score, nonce)` such that `SHA256(...) = H` AND `coherence_score >= threshold`.

This is the **HTLC preimage revelation pattern**, which is **cryptographically simpler** than any signature-based trigger. It has:
- **No key management** (no private keys to lose).
- **No multi-party signing** (no threshold cryptography).
- **No ZK proof** (no prover/verifier complexity).
- **One-way commitment** (once `H` is committed, it cannot be reversed).

### §9.5 Principle 5 — The Trigger Is Dual-Strand, Not Single-Strand

TRION's HashDNA has a dual-strand property: `sense` and `antisense`. Every existing mechanism's trigger is single-strand (one hash, one signature, one proof).

**TRION's design:** The commitment is two hashes: `H_sense = SHA256(payload || 0x00)` and `H_antisense = SHA256(payload || 0xFF)`. The unlocking party must reveal both preimages. This gives:
- **Tamper detection** — if someone tries to forge a behavioral event with a different payload, they must produce both preimages, which requires breaking SHA-256 (or knowing the original payload).
- **Behavioral binding** — the dual-strand structure binds the behavioral event to the coherence score in a way that single-strand hashes cannot.

(Note: As discussed in §8.5, Bitcoin Script cannot compute the XOR operation `antisense = sense ⊕ NOT(something)` directly, so the dual-strand property is a **commitment** property, not an on-chain verification property. The script verifies `SHA256(P || 0x00) == H_sense` and `SHA256(P || 0xFF) == H_antisense` independently. This still gives the dual-strand binding, because the two preimages share the same `P` payload.)

### §9.6 Principle 6 — The Trigger Is Bounded by Bitcoin's Own Time, Not External Time

Every existing mechanism uses Bitcoin's `OP_CHECKSEQUENCEVERIFY` or `OP_CHECKLOCKTIMEVERIFY` for fallback / refund:
- Babylon BTC Staking: timelock path (CSV).
- Babylon TBV: 2016-block CSV recovery.
- tBTC v2, sBTC: refund paths in their wallet scripts.
- DLCs: refund timelocks.
- wBTC: no on-chain refund (off-chain settlement).

**TRION's design:** Same — use `OP_CHECKSEQUENCEVERIFY` for the refund path. But **TRION's behavioral trigger also operates on Bitcoin time**: the behavioral event being committed must reference a specific Bitcoin block hash (which is already in HashDNA's 93-byte payload: `block_hash[32]`).

This means:
- The behavioral event is **anchored to a specific Bitcoin block**.
- The coherence score is computed over **Bitcoin-anchored behavioral events**.
- The trigger is **time-bounded by Bitcoin's own block production**.

This is subtle but important: the trigger is not just "any time the coherence score exceeds threshold" — it's "the coherence score exceeded threshold *as of Bitcoin block N*". The block hash is part of the preimage, so the trigger is cryptographically anchored to Bitcoin L1 time.

### §9.7 Principle 7 — The Trigger Is Observation-Only, Not Integration-Required

Every existing mechanism requires **integration** with Bitcoin L1:
- wBTC: BitGo runs a Bitcoin node and signs transactions.
- tBTC v2: Signers run Bitcoin nodes and threshold-sign.
- sBTC: Stackers run Bitcoin nodes and threshold-sign.
- Babylon BTC Staking: Stakers create Bitcoin transactions; covenant committee co-signs.
- Babylon TBV: Vault Provider runs Bitcoin nodes; pre-signed paths; BitVM challenge.
- DLCs: Parties run Bitcoin nodes and pre-sign CETs.

**TRION's design (per the existing TRION BTC Zero-Bridge design):** Observation-Only Anchoring (OOA). TRION observes Bitcoin's public blockchain via API (Esplora) — no integration needed. The BTC lock is a **standard Bitcoin transaction** (P2WPKH or P2TR) whose unlocking conditions are determined by Bitcoin Script alone.

The TRION network publishes behavioral commitments on Bitcoin L1 (via OP_RETURN or Taproot leaves) and observes them. The unlocking transaction is a standard Bitcoin transaction that satisfies the script.

This is **observation-only** — TRION doesn't need to run a Bitcoin node, doesn't need to threshold-sign, doesn't need to co-sign. The BTC is locked by Bitcoin Script, and unlocked by anyone who can reveal the correct preimage.

### §9.8 Summary of Design Principles

| Principle | TRION Coherence Vault | All existing mechanisms |
|---|---|---|
| 1. Trust assumption | Only Bitcoin L1 + SHA-256 | Custodian / federation / oracle / ZK proof |
| 2. Trigger type | Behavioral coherence score | Time / custody / off-chain event |
| 3. Trigger party | Anyone (preimage revelation) | Specific party (custodian / committee / oracle) |
| 4. Commitment type | Hash preimage | Signature |
| 5. Strand structure | Dual-strand (sense + antisense) | Single-strand |
| 6. Time anchor | Bitcoin block hash in preimage | Bitcoin timelock only |
| 7. Bitcoin integration | Observation-only | Active integration (signing, threshold, etc.) |

---

## §10 — The "Coherence Vault" Concept: A BTC Lock Triggered by HashDNA, Not a Committee

This section sketches the Coherence Vault design. It is **conceptual** — not code, not a final spec. The goal is to surface the design space and the key decisions.

### §10.1 High-Level Concept

A Coherence Vault is a **Bitcoin Taproot output** that locks BTC until one of two conditions is met:

1. **Behavioral release:** A preimage is revealed that hashes (via Bitcoin's native `OP_SHA256` / `OP_HASH256`) to a committed value, AND the preimage encodes a coherence score that exceeds a threshold. Anyone with the preimage can spend the BTC.

2. **Timelocked refund:** If no behavioral release happens within N Bitcoin blocks, the original staker can recover the BTC via a relative timelock (`OP_CHECKSEQUENCEVERIFY`).

There is **no committee**, **no federation**, **no oracle**, **no ZK proof**, **no custodian**. The only trust assumptions are:
- Bitcoin L1 consensus.
- The cryptographic hardness of SHA-256.
- The TRION network's commitment (off-chain) to publish the correct behavioral preimage on Bitcoin L1.

### §10.2 The Bitcoin Script (Conceptual)

A Taproot output with two script-path leaves:

#### Leaf 1 — Behavioral Release Path

```bitcoin
// Stack input: <coherence_score> <nonce> <behavioral_event> <sig>
// Where behavioral_event is the 93-byte HashDNA payload
// (entity_id || event_type || mag_nano || ctx || ts || chain_id || block_hash)

// Compute hash of the behavioral event (using Bitcoin's native SHA-256)
<behavioral_event> OP_HASH256 <committed_behavioral_hash> OP_EQUALVERIFY

// Compute hash of (behavioral_event || coherence_score || nonce)
// Note: OP_CAT is not active, so we cannot concatenate on-stack.
// Workaround: commit to two separate hashes.
//   H1 = HASH256(behavioral_event)
//   H2 = HASH256(behavioral_event || coherence_score || nonce)
// The unlocking party reveals (coherence_score, nonce) and provides a witness.
// In practice, this requires either OP_CAT or a multi-leaf pre-commitment structure.

// For now, the simplest version: commit to the entire preimage as a single hash.
// H = HASH256(behavioral_event || coherence_score || nonce)
// The script verifies HASH256(revealed_preimage) == H, then extracts coherence_score
// from the preimage and checks >= threshold.

// Without OP_CAT, the script cannot extract coherence_score from the preimage.
// So we need a different approach:

// Approach A: Use OP_CHECKSIGFROMSTACK (not active).
//   sig over (behavioral_event, coherence_score, nonce) is verified.
//   This is the ideal but requires a soft fork.

// Approach B: Use a multi-leaf Taproot structure where each leaf corresponds to a
//   specific coherence score bucket. E.g.:
//   - Leaf for coherence_score >= 0.95
//   - Leaf for coherence_score >= 0.90
//   - Leaf for coherence_score >= 0.85
//   - ...
//   The unlocking party picks the leaf that matches their score.
//   Each leaf commits to a specific (behavioral_hash, threshold) pair.
//   The script verifies: HASH256(revealed_preimage) == committed_hash.

// Approach C: Use BitVM-style optimistic verification (BABE).
//   This is what Babylon TBV does. It allows verifying arbitrary computation
//   (including the coherence function) inside Bitcoin Script, but with a
//   challenge window and WOTS commitments.

// For the MVP of the Coherence Vault, Approach B (multi-leaf bucketing) is the simplest.

<coherence_bucket_hash> OP_HASH256 OP_EQUALVERIFY
<threshold> OP_GREATERTHANOREQUAL  // Not a real opcode; use OP_WITHIN or OP_GREATERTHAN
<staker_pk> OP_CHECKSIGVERIFY       // Staker must also sign (anti-theft)
OP_TRUE  // Release the BTC
```

(Note: the actual script would be more carefully constructed. The above is a conceptual sketch to surface the design decisions.)

#### Leaf 2 — Refund Path

```bitcoin
<refund_blocks> OP_CHECKSEQUENCEVERIFY OP_DROP
<staker_pk> OP_CHECKSIG
```

After `refund_blocks` Bitcoin blocks, the staker can recover the BTC.

### §10.3 The Behavioral Event Being Committed

The behavioral event is TRION's 93-byte HashDNA payload:

```
entity_id[32] | event_type[1] | mag_nano[8] | ctx[8] | ts[8] | chain_id[4] | block_hash[32]
```

The `block_hash` field anchors the behavioral event to a specific Bitcoin block. The `entity_id` identifies the entity (BEO) whose behavior is being scored. The `event_type` and `mag_nano` capture the behavioral signal (e.g. "MEV_CAPTURE" with magnitude X). The `ctx` and `ts` and `chain_id` capture the context.

The coherence score is computed off-chain by the TRION network over a sequence of these behavioral events. The score is a function of:
- The entity's behavioral consistency over time.
- The 7-plane coherence model (per TRION's existing implementation).
- The threshold for the specific vault (set at vault creation).

### §10.4 The Commitment Publication Flow

1. **Vault creation (on Bitcoin L1):** The staker creates a Taproot output with the two script-path leaves. The behavioral commitment (`committed_behavioral_hash`, `threshold`) is embedded in the script. The staker also publishes the behavioral event (the 93-byte payload) on Bitcoin L1 via an OP_RETURN in the same transaction.

2. **Off-chain coherence computation (on TRION mesh):** The TRION network observes the behavioral events (from Bitcoin L1 and other chains) and computes the coherence score for the entity. The score is published on the TRION mesh.

3. **Behavioral release (on Bitcoin L1):** Once the coherence score exceeds the threshold, the TRION network reveals the preimage (the 93-byte behavioral event + coherence score + nonce) on Bitcoin L1 (via another OP_RETURN, or via the witness stack of the spending transaction). The spending transaction unlocks the BTC.

4. **Refund (on Bitcoin L1):** If the coherence score never exceeds the threshold within `refund_blocks` blocks, the staker signs a refund transaction after the timelock expires.

### §10.5 Trust Model of the Coherence Vault

| Question | Answer |
|---|---|
| Is there a custodian? | **No.** |
| Can a federation steal the BTC? | **No.** No federation exists. |
| Can a committee censor? | **No.** No committee exists. |
| Can the TRION network censor? | **Only by not publishing the preimage.** If the TRION network refuses to publish the preimage, the behavioral release path cannot fire, and the staker must wait for the refund timelock. **This is a liveness censorship, not a theft.** |
| Can the TRION network steal the BTC? | **No.** The TRION network can only publish the preimage; it cannot redirect the BTC (the script pays to the staker's key on the behavioral release path, or to the staker's key on the refund path). |
| Can the TRION network forge the coherence score? | **Only by publishing a false behavioral event + coherence score + nonce that hashes to the committed value.** This requires breaking SHA-256 (or knowing the original committed preimage). |
| Can a third party (not the staker, not TRION) trigger the release? | **Yes, if they learn the preimage.** This is the permissionless property — anyone with the preimage can trigger the release. The TRION network should publish the preimage publicly so that anyone can trigger the release (e.g. for atomic swap scenarios). |
| Real BTC locks? | **Yes.** BTC is locked in a Taproot output on Bitcoin L1. |
| Synthetic minting? | **No.** No token is minted. |
| Trigger verifiable in Bitcoin Script? | **Yes** — `OP_HASH256` + `OP_EQUAL` + `OP_GREATERTHAN` (or `OP_WITHIN` for the threshold check). All active today. |
| Soft fork required? | **No.** Uses only mainnet opcodes. |

### §10.6 Comparison to Existing Mechanisms

| Property | Coherence Vault | Babylon TBV | Babylon BTC Staking | tBTC v2 | sBTC | wBTC | DLCs |
|---|---|---|---|---|---|---|---|
| Trust | Bitcoin L1 + SHA-256 | ZK proof + BABE + Vault Provider | Covenant committee | 51-of-100 signers | 71% Stackers | BitGo | Oracle |
| Trigger | Behavioral coherence | Ethereum event (via ZK) | FP EOTS / committee sig | Threshold sig | Threshold sig | Custodian sig | Oracle sig |
| Trigger party | Anyone (preimage) | ZK prover | FP / committee | Signers | Stackers | BitGo | Winning party |
| Trigger verifiable in Bitcoin Script? | ✅ Yes (today) | ✅ Yes (via BABE, today) | ❌ No (off-chain) | ❌ No (off-chain) | ❌ No (off-chain) | N/A | ⚠ Partial (adaptor) |
| Soft fork required? | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No |
| Real BTC locks? | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Synthetic minting? | ❌ No | ❌ No | ❌ No | ✅ Yes (tBTC) | ✅ Yes (sBTC) | ✅ Yes (wBTC) | ❌ No |
| Refund path? | ✅ Yes (CSV) | ✅ Yes (CSV 2016 blocks) | ✅ Yes (timelock) | ⚠ Indirect | ⚠ Indirect | ❌ No | ✅ Yes |
| Can trigger be subverted? | Only by breaking SHA-256 | Only by breaking ZK soundness | By covenant refusing to sign | By 51% collusion | By 71% collusion | By BitGo | By oracle equivocation (loses key) |
| Liveness assumption | TRION publishes preimage | Vault Provider online | Covenant online | Signers online | Stackers online | BitGo online | Counterparty + oracle online |
| Behavioral predicate? | ✅ Yes (coherence) | ❌ No (event-based) | ❌ No (slashing-based) | ❌ No | ❌ No | ❌ No | ❌ No |

### §10.7 The Honest Limitations of the Coherence Vault

The Coherence Vault is **not magic**. It has honest limitations:

1. **The coherence score is computed off-chain.** Bitcoin Script cannot verify the coherence computation. The script only verifies the hash preimage + threshold check. So the trust in "the coherence score is correctly computed" is shifted to the TRION network. This is **better than** trusting a committee (because the TRION network's commitment is hash-bound to a specific behavioral event), but it is not zero-trust in the strong sense.

2. **The behavioral event is observed off-chain.** The TRION network observes the entity's behavior (on Bitcoin and other chains) and computes the behavioral hashes. Bitcoin Script cannot independently verify that the behavioral event "actually happened" — it can only verify that the committed hash matches the revealed preimage.

3. **The TRION network can refuse to publish the preimage.** This is a liveness censorship, mitigated by the refund timelock. But it means the staker might have to wait `refund_blocks` blocks to recover their BTC if TRION misbehaves.

4. **Without `OP_CAT`, the script cannot easily extract fields from the preimage.** This means the "coherence score >= threshold" check has to be done via multi-leaf bucketing (Approach B in §10.2) or via BitVM-style verification (Approach C). Both add complexity.

5. **Without `OP_CHECKSIGFROMSTACK`, the script cannot verify a TRION-aggregate signature over the behavioral event.** This means the commitment must be a hash preimage, not a signature. The hash preimage is **asymmetric** (anyone with the preimage can trigger), whereas a signature would be **symmetric** (only the TRION aggregate key can trigger). The asymmetric property is **desirable** for permissionless release, but it means the TRION network cannot retroactively "un-publish" a preimage (which is actually a feature, not a bug — once revealed, the release is unstoppable).

### §10.8 The Path to Stronger Guarantees (Future Soft Forks)

If `OP_CAT` (BIP 347) and `OP_CHECKSIGFROMSTACK` (BIP 348) are activated:

1. **Direct signature verification:** The TRION network could Schnorr-sign `(behavioral_event, coherence_score)` under an aggregate public key. The script would verify the signature directly via `OP_CHECKSIGFROMSTACK`. No preimage revelation needed.

2. **Field extraction:** With `OP_CAT`, the script could concatenate the revealed preimage fields and re-compute the coherence function (if it's simple enough — e.g. a weighted sum or a threshold check on individual behavioral hashes).

3. **Merkle proof verification:** With `OP_CAT`, the script could verify Merkle proofs of behavioral events committed in a TRION-published Merkle root.

Until then, the Coherence Vault uses the **hash preimage revelation** pattern, which is the strongest trigger available in current Bitcoin Script.

### §10.9 Why This Is Fundamentally Different

Every existing BTC lock mechanism:
- Trusts an entity (custodian, federation, oracle, committee, or ZK prover).
- Has a trigger that requires a specific party to act (sign, attest, prove).
- Has a trust assumption that, if violated, results in theft or censorship.

The Coherence Vault:
- Trusts only Bitcoin L1 consensus + SHA-256.
- Has a trigger that anyone can execute by revealing a preimage.
- Has a trust assumption (TRION publishes the correct preimage) that, if violated, results in liveness censorship (mitigated by refund), **not** theft.

This is the fundamental difference: **the trust assumption is liveness, not safety**. The TRION network can stall a Coherence Vault (by refusing to publish the preimage), but it cannot steal the BTC. This is the same safety property as a timelock, but with a more expressive trigger (behavioral coherence instead of just "wait N blocks").

---

## §11 — Sources

### §11.1 Babylon BTC Staking (v1/v2)

- Babylon BTC Staking spec (canonical): `https://github.com/babylonlabs-io/babylon/blob/main/docs/staking-script.md` (fetched Oct 14, 2026; raw markdown saved at `/home/z/my-project/tool-results/babylon-research/babylon-staking-script-raw.md`).
- Babylon BTC Staking mainnet launch (Phase-1): `https://babylonlabs.io/blog/babylon-bitcoin-staking-mainnet-launch-phase-1` (Aug 16, 2024).
- Phase-2 BTC staking participation guide: `https://babylonlabs.io/blog/phase-2-btc-staking-participation-guide` (Apr 22, 2025).
- Phase-2 FP registration: `https://docs.babylonlabs.io/operators/finality_providers/phase_2_registration_guide`.
- Babylon's Bitcoin Staking Contract (blog): `https://babylonlabs.io/blog/babylon-s-bitcoin-staking-contract` (May 7, 2023).
- Bitcoin Staking 101 — Technical Preliminaries: `https://babylonlabs.io/blog/technical-preliminaries-of-bitcoin-staking` (May 7, 2024).
- Covenant emulator (code): `https://github.com/babylonlabs-io/covenant-emulator` (raw README saved at `/home/z/my-project/tool-results/babylon-research/babylon-covenant-emulator.md`).
- OpenZeppelin security research on Babylon: `https://www.openzeppelin.com/news/state-changes-at-the-boundary-lessons-from-security-research-on-babylon` (Apr 1, 2026; full text extracted at `/home/z/my-project/tool-results/babylon-research/openzeppelin-babylon2.json`).
- Figment guide to Babylon staking contract: `https://www.figment.io/insights/babylons-bitcoin-staking-contract-explained` (Sep 12, 2024).
- Aave governance thread on Babylon staking penalties: `https://governance.aave.com/t/staking-penalties-on-babylon-s-bitcoin-staking-protocol/22198` (May 28, 2025).
- Xangle research: `https://xangle.io/en/research/detail/2106` (Sep 23, 2024).
- Blockdaemon Cap-3 guide: `https://www.blockdaemon.com/blog/institutional-guide-to-babylon-cap-3` (Dec 10, 2024).
- Bitcoin Foundation explainer: `https://bitcoinfoundation.org/news/bitcoin/babylon-protocol-explained-bitcoin-staking-without-bridges`.

### §11.2 Babylon TBV (Trustless Bitcoin Vault)

- What is TBV?: `https://docs.babylonlabs.io/trustless-bitcoin-vault/start-here/what-is-tbv` (fetched Oct 14, 2026).
- How it works: `https://docs.babylonlabs.io/trustless-bitcoin-vault/start-here/how-it-works`.
- TBV vs alternatives: `https://docs.babylonlabs.io/trustless-bitcoin-vault/start-here/tbv-vs-alternatives` (fetched Oct 14, 2026).
- BABE verification research: `https://docs.babylonlabs.io/trustless-bitcoin-vault/research/babe_verification` (fetched Oct 14, 2026).
- Aave v4 integration: `https://docs.babylonlabs.io/trustless-bitcoin-vault/technical-details/aave-v4-integration` (fetched Oct 14, 2026).
- Aave V4 Temp-Check: `https://governance.aave.com/t/temp-check-babylon-trustless-btc-vault-integration-on-aave-v4/24964` (May 25, 2026).
- FXStreet coverage: `https://www.fxstreet.com/cryptocurrencies/news/babylon-labs-introduces-proposal-to-enable-real-bitcoin-as-collateral-on-aave-v4-202605260521` (May 26, 2026).
- The Defiant coverage: `https://thedefiant.io/news/defi/aave-babylon-native-btc-spoke-governance-r4l0sp` (May 13, 2026).
- HashKey Cloud integration: `https://defiprime.com/hashkey-cloud-to-integrate-babylon-bitcoin-vaults` (Oct 7, 2026).
- BABE paper (eprint): `https://eprint.iacr.org/2026/065` (Garg, Kolonelos, Sergeevitch, Sridhar, Tse; Jan 2026).
- Sherlock case study on Babylon BaBe: `https://sherlock.xyz/case-studies/babylon`.

### §11.3 tBTC v2

- tBTC v2 GitHub README: `https://github.com/threshold-network/tbtc-v2`.
- tBTC website: `https://tbtc.network`.
- Threshold Network: `https://www.threshold.network`.
- Bitcoin Layers — Threshold tBTC: `https://www.bitcoinlayers.org/infrastructure/threshold-tbtc` (fetched Oct 14, 2026).
- cirBTC vs tBTC 2026 comparison: `https://eco.com/support/en/articles/15220190-cirbtc-vs-tbtc-2026-custodial-vs-threshold-secured-wrapped-btc` (Jul 31, 2026).
- Threshold Network stake-based fee waivers: `https://www.theblock.co/press-releases/threshold-network-introduces-stake-based-fee-waivers-to-strengthen-tbtc-386727` (Jan 22, 2026).
- Gate.com collateral risk assessment: `https://www.gate.com/learn/articles/collateral-risk-assessment-threshold-btc/1262` (Apr 8, 2026).

### §11.4 sBTC

- sBTC design paper: `https://stacks-network.github.io/stacks/sbtc.html` (May 20, 2026; fetched Oct 14, 2026).
- sBTC signers docs: `https://docs.stacks.co/learn/sbtc/sbtc-signers` (Sep 11, 2026).
- sBTC GitHub: `https://github.com/stacks-network/sbtc`.
- sBTC signer set selection discussion (#624): `https://github.com/stacks-network/sbtc/discussions/624`.
- Hiro blog on sBTC signers: `https://www.hiro.so/blog/who-are-the-sbtc-signers-breaking-down-sip-028` (Dec 10, 2024).
- Bitcoin Layers — Stacks: `https://www.bitcoinlayers.org/layers/stacks`.
- BlockEden analysis: `https://blockeden.xyz/blog/2026/04/18/stacks-nakamoto-sbtc-bitcoin-l2-decentralization` (Apr 18, 2026).
- Gate.com sBTC explainer: `https://www.gate.com/learn/articles/what-is-stacks-btc-sbtc/12444` (Mar 28, 2026).

### §11.5 wBTC

- WBTC whitepaper: `https://wbtc.network/assets/wrapped-tokens-whitepaper.pdf` (Jan 24, 2019).
- BitGo blog — WBTC on Base: `https://www.bitgo.com/resources/blog/launching-wrapped-bitcoin-wbtc-on-base` (Feb 28, 2024).
- BitGo blog — WBTC on Osmosis: `https://www.bitgo.com/resources/blog/launching-wrapped-bitcoin-on-osmosis` (Feb 20, 2024).
- BitGo blog — Multi-jurisdictional custody: `https://www.bitgo.com/resources/blog/bitgo-to-move-wbtc-to-multi-jurisdictional-custody-to-accelerate-global` (Aug 9, 2024).
- WBTC multi-custodian exploration: `https://www.wbtc.network/articles/wbtc-announces-exploration-of-multi-custodian-bitcoin-reserves` (Oct 13, 2026).
- Bitstamp WBTC explainer: `https://www.bitstamp.net/en-gb/learn/cryptocurrency-guide/what-is-wrapped-bitcoin-wbtc`.
- Hiro developer's guide to wBTC: `https://www.hiro.so/blog/a-developers-guide-to-wrapped-bitcoin-wbtc`.
- "WBTC: The Custodial Experiment That Failed" critique: `https://medium.com/@thankgodhumphrey7/wbtc-the-custodial-experiment-that-failed-bd456e962b9a`.

### §11.6 DLCs

- Bitcoin Optech — DLCs topic page: `https://bitcoinops.org/en/topics/discreet-log-contracts`.
- Spark research on DLCs: `https://www.spark.money/research/discreet-log-contracts-bitcoin` (Feb 20, 2026).
- MIT DCI DLC project: `https://www.dci.mit.edu/projects/discreet-log-contracts`.
- DLC specs — ECDSA adaptor: `https://github.com/discreetlogcontracts/dlcspecs/blob/master/ECDSA-adaptor.md`.
- ResearchGate — Bitcoin Oracle Contracts: `https://www.researchgate.net/publication/362969206_Bitcoin_Oracle_Contracts_Discreet_Log_Contracts_in_Practice`.
- Firefish DLC explainer: `https://firefish.io/resources/demystifying-discreet-log-contracts-dlcs`.
- arXiv — From Multi-sig to DLCs: `https://arxiv.org/pdf/2602.09822` (2026).
- Conduition — Off-chain ticketing for DLCs: `https://conduition.io/scriptless/ticketed-dlc` (Jan 4, 2024).
- OnrampBitcoin DLC definition: `https://onrampbitcoin.com/learn/terms/discreet-log-contract-dlc`.

### §11.7 Bitcoin Script capabilities

- Spark Bitcoin Script Opcode Reference: `https://www.spark.money/tools/bitcoin-opcode-reference` (fetched Oct 14, 2026).
- BIP 347 (OP_CAT in Tapscript): `https://bips.dev/347`.
- BIP 348 (OP_CHECKSIGFROMSTACK): `https://github.com/bitcoin/bips/blob/master/bip-0348.md`.
- BIP 119 (OP_CHECKTEMPLATEVERIFY): `https://hashrateindex.com/blog/op-ctv-bip-119-guide` (Feb 6, 2024).
- BIP 346 (OP_TXHASH): `https://bitcoin.org/bip/346`.
- Bitcoin Optech — OP_CAT topic: `https://bitcoinops.org/en/topics/op_cat`.
- Galaxy research — Bitcoin's next major upgrade: `https://www.galaxy.com/insights/research/bitcoins-next-major-upgrade-op-cat-and-op-ctv` (Mar 14, 2025).
- Blockstream — OP_CAT for covenants: `https://blog.blockstream.com/op_cat-the-purr-fect-solution-for-covenants` (Jul 2, 2024).
- Bitcoin developer reference: `https://developer.bitcoin.org/reference/transactions.html`.

### §11.8 BitVM (background for BABE)

- zkSecurity BitVM deep dive: `https://blog.zksecurity.xyz/posts/bitvm` (Mar 3, 2025; fetched Oct 14, 2026).
- BitVM org — SNARK verifier plan: `https://bitvm.org/snark.html`.
- BitVM org — BitVM2: `https://bitvm.org/bitvm2.html`.
- BitVM GitHub: `https://github.com/BitVM/BitVM`.
- LambdaClass BitVM explainer: `https://blog.lambdaclass.com/bitvm-enabling-efficient-verifiable-computation-in-bitcoin` (Jun 26, 2025).
- BitVMX paper: `https://arxiv.org/pdf/2405.06842` (Lerner, 2024).
- Rootstock BitVMX explainer: `https://rootstock.io/blog/bitvmx-made-easy-part-1` (Mar 25, 2025).
- Spark BitVM research: `https://www.spark.money/research/bitvm-trustless-bitcoin-verification` (Jun 17, 2026).

### §11.9 TRION Internal Context

- TRION BTC ↔ Starknet Zero-Bridge test results: `/home/z/my-project/trion-core/proofs/btcp-zero-bridge/starknet/BTC_STARKNET_ZERO_BRIDGE.md`.
- TRION audit docs (HashDNA spec): `/home/z/my-project/trion-core/docs/audit/CANONICAL_SPEC_MATRIX.md` (K1, K3 sections).
- TRION complete audit: `/home/z/my-project/trion-core/docs/audit/TRION_COMPLETE_AUDIT.md` (L0.1, L0.9, P1 sections).
- TRION execution path map: `/home/z/my-project/trion-core/docs/audit/master-audit/EXECUTION_PATH_MAP.md` (canonical BH reference).
- HashDNA implementations: `core/primitives/hash_dna.py` (Python, keccak256 BTCP-layer), `indexers/crates/trion-common/src/hash_dna.rs` (Rust, 93-byte canonical SHA3-256 dual-strand).

---

## End of Report

**Status:** Research only. No code. No git commits. No design decisions.

**Next steps for the TRION team:**
1. Validate the conceptual design in §10 against TRION's existing HashDNA / BEO / coherence-7plane implementation.
2. Decide on the trigger pattern (Approach A: hash preimage; Approach B: multi-leaf bucketing; Approach C: BitVM-style BABE verification).
3. Specify the exact Bitcoin Script (Taproot leaf scripts) for the Coherence Vault.
4. Test on Bitcoin signet with a minimal vault (single behavioral event, single threshold).
5. Compare to Babylon TBV's design (§1.6-§1.8) to confirm TRION's Coherence Vault is **fundamentally different** on the 7 axes in §9.8.

**Key finding (one line):** TRION's Coherence Vault is fundamentally different from every existing BTC lock mechanism because it uses a **hash-preimage revelation of a behavioral coherence score** as the trigger — no custodian, no federation, no oracle, no ZK proof, no soft fork — with only a liveness trust assumption (TRION publishes the preimage), not a safety trust assumption (TRION cannot steal the BTC). This is the strongest trust property achievable in current Bitcoin Script.
