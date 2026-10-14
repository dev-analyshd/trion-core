# TRION Coherence Vault — Architecture

**Phase 2/3 implementation of the TRION BTCP Zero-Bridge.**
**Status:** Code complete. Not deployed. Not committed.
**Task ID:** PHASE-2-3-COHERENCE-VAULT

---

## 1. TL;DR

The TRION Coherence Vault is a Bitcoin Taproot output that locks BTC until
either:

1. A 93-byte HashDNA preimage is revealed (by **anyone**) — the BTC flows
   to a pre-specified lender address. **No committee signature needed.**
2. A CSV timelock expires — the borrower reclaims via their own key.
   **No committee signature needed.**

There is **no committee**, **no multisig**, **no federation**, **no oracle**,
**no ZK proof system**. The only trust assumptions are Bitcoin L1 consensus
and the cryptographic hardness of SHA-256.

This is structurally different from Babylon, where a committee must co-sign
every liquidation/refund and can therefore **censor** by refusing to sign.

---

## 2. The Two Spending Paths

The vault is a single Taproot output (`OP_1 <32-byte tweaked pubkey>`) with
two script-path leaves:

### Path 1 — Coherence Release (preimage reveal)

```bitcoin
# Witness: <94_byte_payload_concat_0x00>
# Script:
OP_SHA256
<committed_anchor_bh_32bytes>
OP_EQUAL
```

The 93-byte HashDNA payload is the preimage. The witness supplies
`payload || 0x00` (94 bytes); the script computes `SHA-256(payload || 0x00)`
and compares with the 32-byte `committed_anchor_bh` baked into the script at
lock time.

If the hashes match, the script leaves `1` on the stack and the spend is
authorized. **No signature is checked on this path.** Knowledge of the
preimage alone is sufficient.

### Path 2 — Borrower Refund (CSV timelock)

```bitcoin
# Witness: <borrower_schnorr_sig>
# Script:
<csv_blocks>
OP_CHECKSEQUENCEVERIFY
OP_DROP
<borrower_xonly_pubkey_32bytes>
OP_CHECKSIG
```

After `csv_blocks` confirmations on the vault UTXO (default 144 blocks ≈ 24h),
the borrower can sign a refund transaction with their BIP-340 key.

### Why only two paths?

- No committee path → committee cannot censor.
- No federation path → federation cannot steal.
- No oracle path → oracle cannot equivocate.
- No ZK prover path → prover cannot refuse to prove.

The **pre-signed release transaction** (see §4) ensures that even if a
malicious relayer reveals the preimage, the BTC still flows to the lender.
The borrower does not sign Path 1 — they don't need to, because the output
destination is fixed by the pre-constructed transaction, not by the witness.

---

## 3. How the Preimage Reveal Works

### 3.1 The 93-byte HashDNA payload

```
[0:32]   entity_id     32 bytes   (BEO identifier of the borrower)
[32]     event_type    1 byte     (event class)
[33:41]  mag_nano      8 bytes    (uint64 BE, magnitude × 10^9)
[41:49]  ctx           8 bytes    (uint64 BE, context index)
[49:57]  ts            8 bytes    (uint64 BE, unix seconds)
[57:61]  chain_id      4 bytes    (uint32 BE)
[61:93]  block_hash    32 bytes   (Bitcoin block hash)
```

### 3.2 The sense hash

```
sense = SHA-256(payload || 0x00)
```

This is the **committed_anchor_bh** baked into Path 1 of the Taproot
script. The witness reveals the preimage (94 bytes), the script computes
the hash and compares.

**Critical parity note:** the on-chain Bitcoin Script uses `OP_SHA256`
(bitcoin's native SHA-256). TRION's deployed parity uses the same hash
function (NOT SHA3-256 — see `trion-native-btc-lock-design.md` §8.5).
The hash is byte-identical across Python, Clarity, Cairo, and Solidity.

### 3.3 Publication flow

1. **Lock time (Bitcoin L1):** borrower creates the Taproot output with
   the two script-path leaves. The `committed_anchor_bh` (32 bytes) is
   baked into Path 1. The borrower funds the vault address.

2. **Registration (Stacks L2):** borrower calls `register-vault` on
   `TRIONCoherenceVault.clar`, recording: vault-id, borrower BEO,
   committed anchor_bh, lender BTC address, BTC amount, CSV blocks.
   This mirrors the Bitcoin commitments and emits a `coherence-vault-registered`
   event that relayers watch.

3. **Pre-constructed release tx (off-chain):** the borrower constructs a
   release transaction that spends the vault UTXO via Path 1 and pays
   the lender's address. The output is fixed. The TXID is determined by
   the input+output structure (not the witness), so the borrower does
   not need to sign anything.

4. **Trigger (Stacks L2):** when the TRION network (or anyone) determines
   the coherence release condition is met, they call `publish-preimage`
   on `TRIONCoherenceVault.clar`. The contract verifies
   `SHA-256(payload || 0x00) == committed-anchor-bh` using Clarity's
   native `sha256`. If valid, the vault state is set to
   `RELEASE-TRIGGERED` and a `coherence-vault-release-triggered` event
   is emitted — including the 93-byte payload in the event data.

5. **Relay (Bitcoin L1):** ANY relayer (the borrower, the lender, a
   third party) sees the event, takes the pre-constructed release tx,
   appends the witness `[payload || 0x00, releaseScript, controlBlock]`,
   and broadcasts to Bitcoin.

6. **Refund (Bitcoin L1):** if the preimage is never revealed, after
   `csv_blocks` confirmations the borrower signs a refund tx spending
   via Path 2.

---

## 4. Why Censorship Is Impossible

This is the core differentiator. Consider what an adversary can do:

### Babylon adversary (committee)

A committee that wants to censor a release can refuse to co-sign the
liquidation transaction. Since the script requires their signature,
the borrower cannot release the BTC. The 7-day escape hatch lets the
borrower refund, but **the lender loses** (the loan defaults).

### TRION adversary

There is no committee. The release path requires **only** the preimage.
The preimage is published on Stacks — a public blockchain. Anyone with
internet access can read it. Anyone with a Bitcoin node can broadcast
the pre-constructed release tx.

What can a censor do?

| Censor attempt                            | Why it fails |
|-------------------------------------------|---|
| Refuse to sign the release tx             | No signature is required on Path 1. |
| Bribe Stacks miners to censor the preimage tx | The preimage can be revealed on ANY blockchain (Ethereum, Solana, Bitcoin OP_RETURN) — Stacks is one option. Anyone can mirror it. |
| DDOS Bitcoin mempool                      | Bitcoin's mempool is decentralized; an attacker can delay but not prevent. Once mined, the release is final. |
| Replay the preimage on a different vault   | The committed anchor_bh is unique per vault (includes the borrower BEO + nonce). A preimage for vault A does not unlock vault B. |
| Change the output destination              | Impossible — the pre-constructed release tx's TXID depends on the output. Changing the output changes the TXID. The script only authorizes the spend; it does not specify the destination. |

The **only** thing a censor can do is delay broadcasting the release tx.
Once it's in the mempool, it's final. Once it's confirmed, the lender
has the BTC. This is strictly stronger than Babylon, where the committee
can permanently refuse.

---

## 5. The Trust Model

| Question                                  | TRION answer                                            |
|-------------------------------------------|---------------------------------------------------------|
| Can a custodian steal the BTC?             | **No.** No custodian exists.                            |
| Can a federation steal the BTC?            | **No.** No federation exists.                            |
| Can a committee censor?                    | **No.** No committee exists. The preimage is public.    |
| Can the TRION network censor?              | **Only by not publishing the preimage.** This is a liveness censorship, not a safety violation. Mitigated by the CSV refund path. |
| Can the TRION network steal the BTC?       | **No.** TRION can only publish the preimage; it cannot redirect the BTC (the output is pre-constructed to the lender). |
| Can the TRION network forge the preimage?   | **Only by breaking SHA-256** (or knowing the original payload). |
| Can a third party trigger release?          | **Yes, if they learn the preimage.** This is the permissionless property — by design. |
| Are BTC really locked?                     | **Yes.** Taproot output on Bitcoin L1. No synthetic minting. |
| Is the trigger verifiable in Bitcoin Script? | **Yes.** `OP_SHA256` + `OP_EQUAL`. Active today.       |
| Is a soft fork required?                   | **No.** Uses only mainnet opcodes.                      |

**The trust assumption is liveness, not safety.** TRION can stall a vault
(by refusing to publish the preimage), but it cannot steal the BTC. The
borrower's refund path provides a guaranteed escape after `csv_blocks`.

---

## 6. Eight Specific Differentiators from Babylon

The full comparison is in `trion-native-btc-lock-design.md` §9. The 8 key points:

1. **Identity** — Babylon: single Bitcoin UTXO script, no cross-chain identity. TRION: BEO = `SHA3-256(normalize(all addresses))` — a single behavioral identity spanning Bitcoin, Stacks, EVM, SVM, etc.
2. **Trigger** — Babylon: committee threshold signature over the attestation (committee can refuse → censor). TRION: 93-byte preimage that hashes to a committed value (preimage is public → **censor impossible**).
3. **Coherence gate** — Babylon: no coherence concept, trigger is binary (sign / don't sign). TRION: coherence `C(t)` must exceed dynamic threshold `Θ(t) = 0.55 + 0.37·V(t)`. Fail-closed: if `C(t) < Θ(t)`, no preimage is published.
4. **Validator quorum** — Babylon: stake-weighted, no diversity enforcement. TRION: stake × diversity, where diversity `d_j = 1 - corr(M_j, M̄)`. Coordination collapses own power (Coordination Collapse Theorem).
5. **Finality** — Babylon: rolling 7-day window for slashing + recovery (past 7 days = gone). TRION: Akashic Index is append-only — fraud is **detectable forever** by re-deriving `anchor_bh` from Bitcoin.
6. **Re-derivability** — Babylon: attestation is an off-chain message signed by the committee. TRION: `anchor_bh = SHA-256(93-byte payload)` — anyone can re-derive from Bitcoin block data. **No trust in TRION's claim is required.**
7. **Emergency escape** — Babylon: emergency escape requires the committee to release the bond. TRION: emergency escape is the CSV refund path — **permissionless**. The borrower (or anyone with their key) can refund after `csv_blocks`.
8. **Cross-chain continuity** — Babylon: BTC staking is siloed to Babylon's chain. TRION: each vault contributes to the borrower's Akashic Index. Future vaults use this history to compute a better coherence score → better loan terms. **Quadratic network effect**: N(N-1)/2 bridge pairs collapse.

**Bonus**: every existing BTC lock mechanism triggers on time / custody / off-chain events. None trigger on **behavioral coherence over time**. TRION's Coherence Vault is the first BTC lock with a behavioral trigger.

---

## 7. Migration Path (Progressive Trust Elimination)

The vault is **deployable today** with no soft fork. Each future soft fork
eliminates one layer of trust:

### Today — Coherence Vault v1 (no soft fork)

| Capability | Mechanism | Trust |
|---|---|---|
| Borrower lock | Taproot + BIP-340 | Trustless |
| Borrower refund | CSV (BIP-112) | Trustless |
| HashDNA sense hash verification | `OP_SHA256` | Trustless |
| Preimage revelation | anyone can relay | Trustless |
| Pre-constructed release tx | output fixed at lock time | Trustless |
| Coherence gate | enforced on Stacks (Clarity) | Liveness trust only |
| Anchor_bh commitment | Stacks + 4-way parity | Liveness trust only |
| Ex-post fraud detection | re-derive anchor_bh from Bitcoin | Trustless (forever) |

**Already strictly better than Babylon** (3 additional trustless properties):
the HashDNA sense hash is cryptographically verified on Bitcoin, the refund
escape is permissionless, and fraud is detectable forever.

### After `OP_CAT` soft fork (BIP-347) — Coherence Vault v2

| Capability | Eliminates |
|---|---|
| Antisense complementarity check on Bitcoin | Trust in Stacks for antisense |

With `OP_CAT`, Bitcoin Script can compute
`SHA-256(payload || 0xFF)` itself and verify the antisense hash. The full
HashDNA dual-strand construction becomes verifiable on Bitcoin.

### After `OP_CHECKSIGFROMSTACK` soft fork — Coherence Vault v3

| Capability | Eliminates |
|---|---|
| DW-BFT quorum signature over Stacks state | Trust in Stacks for diversity weights |
| Coherence score on Bitcoin | Trust in Stacks for `C(t)` |

With `OP_CHECKSIGFROMSTACK`, Bitcoin Script can verify a Schnorr signature
over arbitrary stack data. The DW-BFT quorum can sign over the Stacks state
containing diversity weights + coherence scores, and Bitcoin verifies the
signature directly.

### After `OP_CHECKMERKLEVERIFY` soft fork (hypothetical) — Coherence Vault v4

| Capability | Eliminates |
|---|---|
| Stacks state Merkle proof | Trust in Stacks for state inclusion |
| Stacks-PoX-to-Bitcoin anchor | Trust in Stacks block production |

With `OP_CHECKMERKLEVERIFY`, Bitcoin Script can verify Merkle proofs that
the Stacks state root is anchored to a Bitcoin block via PoX. The vault
becomes **fully trustless** — no committee, no Stacks trust, no TRION trust.

### Why Babylon has no migration path

Babylon's committee is fundamental to its design. Eliminating the committee
requires changing the Babylon protocol itself, not just Bitcoin Script.
The committee is the trust assumption; you cannot "soft fork" it away.

TRION's committee-equivalent (the coherence gate) is enforced on Stacks
**only because Bitcoin Script cannot yet verify it directly**. Each soft
fork moves one piece of that verification from Stacks to Bitcoin. The
end-state is a fully trustless vault.

---

## 8. File Layout & CLI

```
btc-tools/vault/
├── package.json              # ESM, bitcoinjs-lib v7, ecpair, tiny-secp256k1
├── coherence-vault.js        # 2-path Taproot vault + CLI
└── vault-state.json          # created on `create` (gitignored)

contracts/clarity/
└── TRIONCoherenceVault.clar  # register-vault, publish-preimage, refund-vault

docs/architecture/
└── trion-coherence-vault.md  # this file
```

CLI:
```bash
node coherence-vault.js create --borrower-wif <WIF> --lender-addr <addr> \
  --sats 100000 --csv-blocks 144 --payload <93B-hex-or-anchor-bh> [--out file]
node coherence-vault.js reveal-preimage --vault-state <file> --payload <93B-hex>
node coherence-vault.js refund --vault-state <file> --borrower-wif <WIF>
node coherence-vault.js build-payload --entity-id <32B-hex> --event-type <N> ... 
node coherence-vault.js derive-sense --payload <93B-hex>
node coherence-vault.js verify --vault-state <file>
```

## 9. Test Vector (verified)

```
borrower WIF      : cVYAhtCwjbQQ2tNAxsMNPDfzpTb6VG8WPxZjdvNktqdqKQHEiLEF
borrower x-only   : ff8f82d566995f5a743ecd463bcb01c7e6ffc131ab21fbfa58183f188f67bbc8
lender addr       : tb1q9wcwggadaejm3j5gamxz8n8uyla482zye4uuny
amount            : 100000 sats
csv-blocks        : 144 (~24h)
payload (93B hex) : 000000000000000000000000000000000000000000000000000000000000beef
                    01 000000003b9aca00 0000000000000002a 000000006553f100
                    00000001
                    aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
committed anchor_bh (= sense): 45d188e54ab0548c0aa6b8a647f9f9204cfde657590db67d5447198f9457612f
Vault Taproot address (testnet): tb1pf74geea2cpnmk3pj05juy7dvfdr6sfnnckepvr3ck8rfr70lp9sskuyahw
Release script (Path 1, hex): a82045d188e54ab0548c0aa6b8a647f9f9204cfde657590db67d5447198f9457612f87
Refund script  (Path 2, hex): 029000b27520ff8f82d566995f5a743ecd463bcb01c7e6ffc131ab21fbfa58183f188f67bbc8ac
```

ASM decoding (verified):
- Path 1: `OP_SHA256 <32-byte-hash> OP_EQUAL`
- Path 2: `<144> OP_CHECKSEQUENCEVERIFY OP_DROP <32-byte-x-only-pubkey> OP_CHECKSIG`

---

## 10. Open Questions (Honest Limitations)

1. **Coherence is computed off-chain.** Bitcoin Script cannot verify the
   coherence function. Trust in "the coherence score is correctly computed"
   is shifted to the TRION network + Stacks (where `publish-preimage` is
   callable by anyone, and the computation is replayable).

2. **Behavioral event is observed off-chain.** TRION observes the entity's
   behavior and computes the behavioral hashes. Bitcoin Script cannot
   independently verify the event "actually happened" — only that the
   committed hash matches.

3. **TRION can refuse to publish the preimage.** Liveness censorship,
   mitigated by the CSV refund path. The borrower must wait `csv_blocks`
   blocks to recover.

4. **Without `OP_CAT`, the script cannot extract fields from the
   preimage.** The full preimage is revealed; threshold/field verification
   happens off-chain + on Stacks.

5. **Without `OP_CHECKSIGFROMSTACK`, no aggregate TRION signature can
   be verified over the preimage.** The commitment is a hash preimage
   (asymmetric: anyone with the preimage can trigger). This is the desired
   permissionless property but means TRION cannot "un-publish" a
   preimage (which is actually a feature: once revealed, release is
   unstoppable).

These limitations shrink progressively with each soft fork (§7). None
require changing the TRION protocol itself — they're all about moving
verification from Stacks to Bitcoin.

---

## 11. References

- `docs/research/trion-native-btc-lock-design.md` §8 — original Coherence Vault design
- `docs/research/babylon-and-btc-lock-comparison.md` §9-10 — 7 design principles + Coherence Vault concept
- `contracts/clarity/BTCPEscrow.clar` — Babylon-style predecessor (committee-based)
- `btc-tools/vault/coherence-vault.js` — this implementation
- `contracts/clarity/TRIONCoherenceVault.clar` — this implementation
- BIP-340 (Schnorr), BIP-341 (Taproot), BIP-342 (Tapscript), BIP-112 (CSV)
- BIP-347 (OP_CAT, proposed), OP_CHECKSIGFROMSTACK (proposed)
