# SECURITY MODEL (canonical reconstruction, verified 2026-09-04)

## Attacker model (all assumed possible)

Malicious user · malicious relayer · malicious/bzantine validator ·
compromised RPC · stale oracle · corrupted local DB · compromised signer ·
malicious chain · manipulated intent · route substitution · replay ·
equivocation — every class exercised this sweep (RED-4: 6 reproductions +
11 fresh attacks + 13 failure injections).

## Trust boundary inventory (one interpretation each — verified)

| Boundary | Rule | Enforcement (verified) |
|---|---|---|
| Chain RPC → BH | untrusted input, deterministic canonicalization | §1–§9 pure functions; NaN raises; chain ids validated (py) / registry consts (rust) |
| BH → ledger/store | append-only, complementarity self-verification | antisense ⊕ sense == NOT(SHA3(p‖0xFF)); tamper → valid:false |
| Store → signals | no synthetic data unlabeled in truth paths | is_synthetic labeling (65+ literals); caller-supplied truth labeled |
| Truth emission | AWA gate, fail-closed | frozen ⇒ 503 silence on ALL publication surfaces incl. zg (d9f8d8e) |
| Intent → route | registry-only chains, status machine | off-registry rejected; nonce atomic (cross-process verified 400/400) |
| Route → escrow | anchorBH==escrowId binding | route-spoof exploit reproduced then blocked (CERT_ROUTE_MISMATCH) |
| Certificate → release | quorum from registry, never from proof | threshold-from-registry; weight truncation py↔sol identical; MIN_SIGNERS=3 |
| Epoch boundary | forward-only registries | epoch-1 cert vs epoch-2 → SIGNER_NOT_IN_EPOCH_SET |
| Certificate reuse | settlement-tuple + dest-chain + nonce binding | 2-escrow replay → NOT_RELEASABLE; foreign chain → CERT_DEST_CHAIN_NOT_THIS_CHAIN |
| TTL | second-based, ≤ boundary | expiry exploit reproduced then blocked (BTCP: escrow expired) |
| API writes | key required regardless of method | GET-write exploit reproduced then blocked (401) |
| Rate limit | trusted-proxy-only XFF (last entry) | spoof ignored, 429 fires |
| Keys | never in tree/history (purged), KMS/HSM path | red-flag sweep 5/5 clean |

## Cryptographic assumptions

FIPS **SHA3-256** for the BH strand pair (never mixed with Keccak — the
HashDNA digest-mixing bug class was found and fixed in the prior waves);
**Keccak-256 + EIP-191** for EVM-family certificate digests (domain-
separated from BH by construction); ECDSA low-s (EIP-2) / Ed25519 / STARK
ECDSA per VM; ML-KEM/ML-DSA/SPHINCS+ (PQC) for L4 living-security layers
(installed and passing in this environment); Schnorr multisig on the Go
mesh. Replay defense: per-intent nonces (atomic), per-cert nonce ordering
with equivocation evidence, block-hash+timestamp pinning.

## Fail-closed requirement (§28)

**13/13 injection points fail closed** (oracle unregistered, FAISS down,
ledger missing, registry unreadable, KMS bogus, quorum unmet, freshness
expired, config broken…). Two fail-LOUD by design (registry import, FAISS
boot). Zero silent-accept paths found.
