```
BIP: DBP
Title: Deterministic Behavioral Preimage — A Bitcoin Spend-Authorization Primitive
Author: dev-analyshd
Status: Draft
Type: Informational
Created: 2026-10-14
License: BSD-2-Clause
```

# Abstract

This BIP specifies the *Deterministic Behavioral Preimage* (DBP), a Bitcoin
spend-authorization primitive whose authorization material is the SHA-256
preimage of a value committed at lock time, and whose preimage is a
deterministic function of public chain data rather than a secret chosen by an
interactive counterparty. A DBP commitment composes natively with Bitcoin's
`OP_SHA256 … OP_EQUAL` Tapscript and requires no soft fork, no new opcode, and
no signature on the spend path. The primitive is demonstrated empirically by a
confirmed Bitcoin testnet spend in which an 80-byte DBP payload is the sole
witness item.

# Motivation

Cross-chain bridges that custody Bitcoin have lost more than **USD 3.2 billion**
to key compromise, multisig collusion, and signer censorship since 2022
(Wormhole, Ronin, Multichain, Nomad, etc.). Every loss shares the same root
cause: the release of BTC from the bridge vault requires a *signature* by a
*committee*, and that committee is a single point of failure. Existing
primitives do not solve this:

* **HTLCs** rely on a random secret chosen by an interactive recipient, who can refuse to reveal it.
* **Schnorr / ECDSA signatures** rely on a key holder, who can refuse to sign.
* **DLC oracles** rely on an oracle attestation, which can be withheld.
* **Timelocks (CSV/CLTV)** provide no conditional release — only an unconditional refund.

What is missing is a primitive whose **release authorization** is (i) a hash
preimage (so it composes with `OP_SHA256` on Bitcoin); (ii) *deterministically
derivable* from public chain data (so it is not "chosen" by any party); and
(iii) *publishable by anyone* once derived (so release execution is
censorship-resistant even if the issuing party is offline).

DBP provides exactly this. Combined with a CSV refund path under a single
Taproot output, DBP yields a vault whose **safety is trustless** (the borrower
always recovers their BTC after `csv_delta` blocks) and whose **liveness is
post-publication censorship-resistant** (any party who has read the published
payload may relay the spend). This BIP standardizes the 80-byte payload layout
and the commit/reveal/verify algorithms so other protocols may reuse DBP
verbatim, with shared test vectors.

# Specification

## Primitive definition

`DBP = (Setup, Compute, Commit, Reveal, Verify)`:

* `Setup(1^λ) → params`. Fixed: `H = SHA-256`, `L = 80`, and the layout below.
* `Compute(block_data, descriptor) → payload ∈ {0,1}^(8L)`. Deterministic,
  public, side-effect-free. Identical input ⇒ identical output in every impl.
* `Commit(payload) → H ∈ {0,1}^256`. `H := SHA-256(payload)`, a pure function;
  `H` is embedded in Bitcoin Script at lock time.
* `Reveal(payload)`. Informational: publishes `payload` to any public medium.
* `Verify(payload, H) → {0, 1}`. `= 1` iff `SHA-256(payload) == H` **and**
  `|payload| == 80`; otherwise `0`.

## Payload layout (80 bytes, big-endian)

```
offset width field          type       encoding / semantics
────── ───── ────────────── ────────── ──────────────────────────────────────────
  0    20    entity_id      bytes[20]  Leftmost 20 bytes of SHA3-256(normalise(btc_addr))
 20     1    event_type     uint8      canonical event id (TRANSFER=0, BRIDGE=10, …)
 21     8    magnitude_nano uint64     ⌊ magnitude_norm × 10^9 ⌋, big-endian
 29     8    timestamp      uint64     block time (median-time-past), Unix seconds, BE
 37     4    chain_id       uint32     chain registry id (Bitcoin = 100), big-endian
 41    32    block_hash     bytes[32]  SHA-256d of the Bitcoin block at lock time
 73     7    reserved       bytes[7]   0x00 … 0x00 (MUST be all-zero in v1)
────── ─────                                                            80 bytes total
```

Every field is derivable from public Bitcoin block data plus the locking
transaction; nothing is secret. `reserved` MUST be all-zero in v1; non-zero
`reserved` is a protocol violation and `Verify` MUST return `0`.

## Bitcoin Script template (Taproot script-path leaf)

```
scriptPubKey (Taproot output, script-path leaf 1 — release):
  OP_SHA256 <H:32B> OP_EQUAL

spend witness (script path, leaf 1):
  <payload:80B>  <script:35B>  <controlBlock:65B>

scriptPubKey (Taproot output, script-path leaf 2 — refund):
  <borrower_pubkey:32B> OP_CHECKSIGVERIFY
  <csv_delta>           OP_CHECKSEQUENCEVERIFY
```

The witness item `<payload>` is **not** a signature; it is the raw 80-byte DBP
payload. Leaf 2 (refund) is independent of DBP: it requires only the borrower's
signature and the passage of `csv_delta` blocks; the refund path is
unconditional after `csv_delta` and requires no cooperation from the DBP issuer.

# Rationale

**Why 80 bytes?** Smallest layout that fits (i) a 20-byte entity identifier
(compatible with Bitcoin's HASH160 width), (ii) a 32-byte block hash (binding
the payload to a real Bitcoin block), and (iii) sufficient metadata to be
self-describing — while remaining well under the 520-byte witness push limit.
At 1 sat/vB the resulting witness costs less than 25 vBytes.

**Why SHA-256 (and not SHA3-256 or HASH160)?** SHA-256 is the only hash
function natively available as a Tapscript opcode (`OP_SHA256`, BIP-342). Any
other function would require a soft fork or off-chain verification, defeating
the "no signature, no oracle" property. Preimage resistance over the 80-byte
domain is `2^128` classically and `2^64` under Grover — both adequate.

**Why no length/tag suffix?** DBP commits to a fixed 80-byte domain.
Length-extension attacks do not apply because `Verify` recomputes the full
hash from the entire payload, never from an intermediate state. A
domain-separation tag would consume payload bytes without adding security,
since the script template is already DBP-specific.

**Why Taproot (BIP-341/342)?** Taproot (i) allows multiple script-path leaves
under a single output (so DBP release and CSV refund share one UTXO), (ii)
makes script-path spends indistinguishable from key-path spends on-chain
before reveal, and (iii) carries the witness discount that keeps the 80-byte
push economical. Pre-SegWit P2SH loses both privacy and the discount.

**Why all-zero `reserved`?** A 7-byte reserved field lets future versions add
structured metadata without breaking v1 verifiers. Forcing it to zero in v1
makes v1 payloads trivially distinguishable from v2+ and lets `Verify` reject
malformed payloads cheaply.

# Backwards Compatibility

This BIP introduces no consensus change. It uses only opcodes available since
Bitcoin Core 0.16.2 (`OP_SHA256`, `OP_EQUAL`) and Tapscript semantics from
BIP-341/342 (active since Bitcoin Core 22.0, November 2021). Any wallet that
supports Taproot script-path spends can construct and broadcast a DBP spend
without modification; the only requirement is the ability to push an 80-byte
witness item, well within the 520-byte standardness limit. Pre-Taproot nodes
treat DBP outputs as ordinary P2SH-wrapped scripts; mixing DBP leaves with
non-DBP leaves in the same Taproot output is permitted by consensus but NOT
RECOMMENDED, as it complicates the liveness analysis.

# Test Vectors

All vectors are byte-exact; `H = SHA-256(payload)`. The `fields` row gives the
field-by-field breakdown (entity_id / event_type / magnitude / timestamp /
chain_id / block_hash / reserved); `payload` is the same bytes concatenated.

## Vector 1 — empirical (matches the on-chain BTC testnet spend)

```
fields     cc8aa95abbc7965be22cccc07b10c79520df838d  00  000114f737a8d600  000000006a9dada7  0064 00000000000001a9562ec7227605f68ea1baf77dfa37d6794fcd55bca4a509f4 00000000000000
payload    = cc8aa95abbc7965be22cccc07b10c79520df838d00000114f737a8d600000000006a9dada70000006400000000000001a9562ec7227605f68ea1baf77dfa37d6794fcd55bca4a509f400000000000000
H          = d93f341d6370c737b2c2f09ed88f7949fcdc87593440972a422c34a8bbbf92a2
spend txid = edd5aa4a568e9974a4373038d6ee5270723d80c0770879113090e7e79fbf8f44  (BTC testnet, block 5197632)
```

## Vector 2 — synthetic, BRIDGE event, all-zero magnitude

```
fields     1111111111111111111111111111111111111111  0a  0000000000000000  000000006b49d200  0064 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa 00000000000000
payload    = 11111111111111111111111111111111111111110a0000000000000000000000006b49d20000000064aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa00000000000000
H          = 28c5a958c456a6f4a7ecc0c608ef9d06f797452e5f13e350a8874765255b9e38
```

## Vector 3 — synthetic, non-Bitcoin chain_id (illustrative Stacks=200)

```
fields     deadbeefdeadbeefdeadbeefdeadbeefdeadbeef  00  0000000000000001  000000006b49d1ff  00c8 00000000000000000000000000000000000000000000000000000000000000ff 00000000000000
payload    = deadbeefdeadbeefdeadbeefdeadbeefdeadbeef000000000000000001000000006b49d1ff000000c800000000000000000000000000000000000000000000000000000000000000ff00000000000000
H          = 6085218aaf8ff9769396f7e896373f0473a7d654fae8d8244f2a9af5f35c5a03
```

## Negative vector — single-byte tamper of Vector 1

Flipping the last byte of `reserved` from `0x00` to `0x01` MUST change the
committed hash (so `Verify` rejects malformed v1 payloads):

```
payload'   = cc8aa95abbc7965be22cccc07b10c79520df838d00000114f737a8d600000000006a9dada70000006400000000000001a9562ec7227605f68ea1baf77dfa37d6794fcd55bca4a509f400000000000001
H'         = 5b9397bf5e7941ac7d90c4753fa7abaf09c0a9f318f438e41755a959808f3828
Verify(payload', H) = 0   (H ≠ H')
```

# Reference Implementation

Minimal TypeScript reference using `bitcoinjs-lib` v6.

```typescript
import * as bitcoin from "bitcoinjs-lib";
import { crypto } from "bitcoinjs-lib";

// Compute the 80-byte DBP payload.
export function dbpPayload(f: {
  entityId: Buffer; eventType: number; magnitudeNano: bigint;
  timestamp: number; chainId: number; blockHash: Buffer;
}): Buffer {
  const b = Buffer.alloc(80, 0x00);
  f.entityId.copy(b, 0);                       // 0..19
  b.writeUInt8(f.eventType, 20);                // 20
  b.writeBigUInt64BE(f.magnitudeNano, 21);     // 21..28
  b.writeBigUInt64BE(BigInt(f.timestamp), 29); // 29..36
  b.writeUInt32BE(f.chainId, 37);              // 37..40
  f.blockHash.copy(b, 41);                     // 41..72 (73..79 reserved = 0x00)
  return b;
}

export const dbpCommit = (p: Buffer): Buffer =>            // = SHA-256(payload)
  p.length === 80 ? crypto.sha256(p) : (() => { throw new Error("DBP payload must be 80 bytes"); })();
export const dbpVerify = (p: Buffer, H: Buffer): boolean =>  // = (SHA-256(p) == H) ∧ |p|==80
  p.length === 80 && crypto.sha256(p).equals(H);

// Taproot release leaf: OP_SHA256 <H> OP_EQUAL
export const dbpLeafScript = (H: Buffer): Buffer =>
  bitcoin.script.compile([bitcoin.opcodes.OP_SHA256, H, bitcoin.opcodes.OP_EQUAL])!;

// Compose release + CSV refund leaves under one Taproot output.
export function buildVault(
  borrowerKey: Buffer, csvDelta: number, H: Buffer, network: bitcoin.Network,
): { vaultAddress: string; leafRelease: Buffer; leafRefund: Buffer } {
  const leafRelease = dbpLeafScript(H);
  const leafRefund = bitcoin.script.compile([
    borrowerKey, bitcoin.opcodes.OP_CHECKSIGVERIFY,
    bitcoin.script.number.encode(csvDelta), bitcoin.opcodes.OP_CHECKSEQUENCEVERIFY,
  ])!;
  const p2tr = bitcoin.payments.p2tr({
    internalPubkey: borrowerKey,
    scriptTree: [{ output: leafRelease }, { output: leafRefund }],
    network,
  });
  return { vaultAddress: p2tr.address!, leafRelease, leafRefund };
}

// Assemble the witness for a preimage-reveal spend (NO signature).
export const buildRevealWitness = (
  payload: Buffer, leafRelease: Buffer, controlBlock: Buffer,
): Buffer[] => {
  if (payload.length !== 80) throw new Error("DBP payload must be 80 bytes");
  return [payload, leafRelease, controlBlock];
};
```

# Security Considerations

**Preimage resistance.** DBP security reduces to the preimage resistance of
SHA-256 over the 80-byte domain. A successful forge requires finding *any*
`payload'` with `SHA-256(payload') = H`, costing expected `O(2^128)` work
classically and `O(2^64)` quantum (Grover) — strictly stronger than
ECDSA/Schnorr key security at the same parameter size.

**Liveness vs safety.** DBP release-path liveness requires *some* party to
publish `payload` after `Compute` has run. `Compute` is deterministic and
public, so this can be done by anyone — including the borrower or any
third-party observer — once the relevant Bitcoin block is finalized. The
borrower's CSV refund path remains available unconditionally after
`csv_delta` blocks, so **safety does not depend on DBP liveness**: even if
the issuer disappears entirely, the borrower recovers their BTC after
`csv_delta` blocks; the disappearance only degrades *liveness of the release
path*, not safety. Safety rests on (i) SHA-256 preimage resistance, (ii) the
borrower's CSV refund path, and (iii) pre-specified destination addresses on
both leaves.

**Malleability and replay.** A published `payload` is non-secret by
construction; copying it into a second spend is the intended
permissionless-relay behaviour, not an attack. Replay protection across
distinct vaults is provided by `entity_id` being unique per vault; two vaults
sharing the same `entity_id` MUST NOT coexist under the same issuer.

**Reserved field & quantum resistance.** Non-zero `reserved` bytes are a v1
protocol violation; `Verify` MUST reject such payloads — the on-chain script
does not enforce this without `OP_CAT`-style introspection, so v1 verifiers
(Stacks contracts, indexers) are the enforcement point. The release path is
post-quantum (SHA-256/Grover → `2^64`); the CSV refund path relies on the
borrower's Schnorr/ECDSA key, which is NOT post-quantum. Borrowers in
long-duration vaults SHOULD rotate keys before quantum adversaries become
plausible.

# Acknowledgements

The DBP primitive was developed as part of the TRION Coherence Vault research
programme. The empirical test vector (Vector 1) was confirmed on Bitcoin
testnet at block 5197632 (`edd5aa4a…bf8f44`) on 2026-10-24. Thanks to the
Bitcoin Core, BIP-341/342, and NIST FIPS 180-4 authors. Document format
follows BIP 2.

# References

* BIP-2 — BIP process, status, and formatting conventions.
* BIP-341 — Taproot: SegWit version 1 spending rules.
* BIP-342 — Tapscript: Validation of Taproot script paths.
* NIST FIPS 180-4 — Secure Hash Standard (SHA-256).
* TRION Research — *DBP Formal Specification*, `docs/spec/DBP_PRIMITIVE_SPEC.md`.
* TRION Protocol — *TRION-Native Bitcoin Lock Design*, Phase 0 Report, 2026-09-14.
