# TRION Protocol SDK — Trust Model

> **One sentence:** this SDK **reads, packs, and classifies** — it never
> *verifies*, never *signs*, and never *decides* consensus. Every
> security-relevant verdict is produced server-side (the Akashic Oracle API)
> or on-chain (the TRION oracle contracts). Anything computed inside this
> SDK is a local convenience computation over data the caller supplied.

## What this SDK does

| Capability | Where truth comes from |
|---|---|
| `fetchSignal` / `fetchBTCPRoute` / `fetchBITPClipboard` | HTTP responses from the TRION Oracle API. The API is the authority for the signal values; the SDK does not recompute or re-attest them. |
| `isSafe` / `isSilence` / `isManipulationAlert` / `coherenceMargin` … | **Local interpretation** of a server-returned `signal_type` / coherence / threshold. They are classification helpers, not verification. If the server says `SILENCE`, the SDK reports silence — it cannot discover a forged or stale signal. |
| `packSignal` / `signalToPacked` | Bit-packing of caller-provided numbers into the 256-bit on-chain layout. Packing is pure serialization — a packed value is **data, not truth**. |
| `unpackSignal` / `interpretPacked` | Decoding of values already stored on-chain. On-chain storage is the authority for *those bytes*; the SDK only re-derives floats. |
| `minValidators` / `coverageMultiplier` / `btcpScoreTier` / `mfScoreLevel` | Spec-formula helpers computed **client-side on caller inputs**. They are advisory arithmetic (C1 / C2 / tier tables), never a quorum or slashing decision. |
| `checkBITPTolerance` | A local comparison of two caller-supplied rates against a caller-chosen tolerance (default 0.02). Your own numbers, your own check. |
| `checkSanctions` | Fail-closed wrapper around the server sanctions oracle: on transport failure it returns `sanctioned: true` with the `SCREENING_UNAVAILABLE` marker and `confidence: 0` — "cannot screen", never "clean". Screening truth is the server's; a `confidence < 1` result must be treated as unverified. |
| WASM signal processor (`verifyCoherenceWasm`, `entropyWasm`) | **Local convenience compute.** Despite the word "verify" in the function name, it recomputes a coherence score over inputs **you** supply in the browser — it verifies a formula evaluation, not an oracle attestation, not a signature, not consensus. |

## What this SDK deliberately does NOT do

* **No signing.** There is no private-key API, no `signMessage`, no
  transaction construction. On-chain publication requires a quorum of
  registered-validator signatures over the canonical message; the SDK
  produces none of them. If you built a packed signal with
  `signalToPacked`, it is inert data until a validator (relayer) signs it
  and a contract verifies the quorum.
* **No signature verification.** Nothing in the SDK validates validator
  signatures, certificates, or quorum claims. Any such check must be
  performed server-side or on-chain. A `BTCPRouteData` row fetched over
  HTTP carries the API's word for its `validators_signed` count — treat it
  as reported metadata, not verified consensus.
* **No quorum/threshold truth.** The SDK never computes "quorum reached",
  "threshold met", or "safe to release escrow". `minValidators` computes
  the *spec formula* for how many validators a route *should* involve —
  it cannot tell you how many actually signed.
* **No trust in packed bytes.** `signalToPacked` accepts any
  `TRIONSignal`-shaped object, including ones you constructed by hand.
  The packing function makes no claim that the values are oracle-derived.
  Publishing them is gated by the on-chain quorum, not by this SDK.

## Threat model notes

* The SDK fetches over plain `fetch()` — **use HTTPS** and treat a
  network-level attacker as able to substitute any response. There is no
  response signing to detect that today (server-side W3-M work added
  provenance labels; end-to-end response signatures remain an open item).
* `signal_ttl_blocks`, `validator_hhi`, `validators_signed` etc. in
  `BTCPRouteData`/`BTCPRouteSignalMetadata` are **reported by the API**.
  On-chain truth lives in the TRIONOracleV3/TRIONExecutionGate contracts
  (quorum-gated `publishSignal`/route attestations). If your decision is
  security-critical, read it from the contract, not from the SDK.
* Sanctions results: a `sanctioned: false` with `confidence < 1` (or a
  zero-coverage oracle) means "unverified", not "clean" — mirror of the
  server-side fail-closed contract.

## Layout (honest status)

* `TrionSDK.ts` — the typed SDK documented above (canonical).
* `sdk/src/` — sibling copies of overlapping clients
  (`index.ts`, `trion.ts`, `trion-sdk.ts`, `client.ts`) plus the WASM
  signal processor sources. These overlap heavily with `TrionSDK.ts`
  (registered as an audit item: "SDK duplication / wasm P0"); consolidation
  is tracked as Wave 4 dead-code work. Until then, the trust model above
  applies to every copy: none of them sign, verify signatures, or compute
  quorum truth.
* `trion_sdk.py` — the Python sibling client; same trust model (read +
  classify, no signing, no verification).
