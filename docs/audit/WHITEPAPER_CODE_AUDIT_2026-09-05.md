# Whitepaper-to-Code Delta Audit — 2026-09-05

## Scope and method

This is a **delta audit**, not a claim that a production network was operated.
It re-checks the authoritative whitepapers and the open items in the canonical
matrix against the repository at commit `c0ccb14`, with particular attention to
execution gates: a formula or state classifier does not satisfy a whitepaper
requirement unless the route/publication boundary consumes it.

Authority order is the one fixed by
[`CANONICAL_SPEC_MATRIX.md`](CANONICAL_SPEC_MATRIX.md): `WHITEPAPER_MD.txt`,
then `WHITEPAPER_V2.txt`, then `BTCP_SPEC.txt`; the per-layer specifications
are subordinate where they disagree.  This matters because the per-layer
documents contain known, recorded obsolete formulations.

Evidence collected:

* Read the canonical conflict/resolution table and the open-requirement
  entries in `CANONICAL_SPEC_MATRIX.md`.
* Inspected the degradation classifier and the only BTCP route-creation entry
  point (`core/master/degradation.py` and `core/btcp/orchestrator.py`).
* Inspected the ZK implementation and circuit-suite status disclosures.
* Ran the self-contained whitepaper, signal-registry, conservation, and golden
  vector tests with the interpreter already available in the environment.

## Verdict

**NOT READY to claim full whitepaper conformance.** The repository has a strong
set of source-level implementations and 226 passing selected conformance tests,
but one newly confirmed **high-severity enforcement defect** means the L5.3
degradation guarantee is not met at the BTCP route boundary.  The previous
matrix's externally dependent and research-only qualifications also remain
valid: a validator fleet is not present and the Groth16 circuit artifacts are
not reproducible from the repository.

The audit does **not** find evidence that those two latter capabilities are
silently represented as deployed.  Their source documentation labels the
limitations.  They remain release blockers for any claim that depends on live
validator consensus or production ZK proofs.

## Findings

### WP-2026-09-05-01 — Tier-1 degradation permits new routes

**Severity: High**  
**Whitepaper requirement:** MD L5.3 requires that when
`0.5 * Θ <= C < Θ`, the system emit `STALE_SCORE`, use at most a 50-block
last-confirmed BIBL snapshot, **suspend new routes**, and permit in-flight
routes to complete.  The requirement and the prior remediation are recorded in
matrix entry R-ME-07.

**Evidence:** `classify_degradation()` correctly identifies `TIER_1` and
publishes a 50-block maximum, but sets `new_routes_suspended` only for `TIER_2`
and `EMERGENCY`.  Its own disclosure text says the opposite for `TIER_1`.
`BTCPOrchestrator.create_route()` neither imports nor invokes the degradation
classifier/gate, so route creation continues regardless of coherence.

**Impact:** A new cross-chain intent can be constructed using below-threshold
coherence during the exact stale-score condition intended to block it.  The
reported safety of already in-flight routes does not make admission of a new
route safe.

**Required remediation:**

1. Treat `TIER_1`, `TIER_2`, and `EMERGENCY` as `new_routes_suspended=True`.
2. Inject a trusted, current coherence/threshold source into
   `BTCPOrchestrator.create_route()` and fail closed before intent creation when
   the resulting state suspends new routes.
3. Persist the last-confirmed BIBL snapshot with its block height and reject it
   after 50 blocks; a numeric field alone is not a snapshot cache.
4. Add boundary tests for nominal admission, Tier 1 denial, Tier 2 denial,
   emergency denial, the 50-block expiry, and completion of a route admitted
   before degradation.

**Status:** Open.  No behavior change was made in this audit-only change.

### WP-2026-09-05-02 — Production ZK claims must remain deferred

**Severity: High for privacy/MEV claims; not a hidden-code defect**  
The Python `zk/` layer explicitly calls itself a “Groth16-style proof
simulation” built on secp256k1/Schnorr-Pedersen primitives.  The Circom suite
states that its checkboxes are not reproducible from the committed repository:
no `.r1cs`, `.zkey`, proof, verification-key, or deployed verifier artifacts
are present, and a production multiparty ceremony is still unchecked.

**Impact:** Do not claim Groth16 soundness, zero front-run window, or
production privacy protection from the Python simulator.  The current labels
are appropriately conservative; weakening them would be a release-blocking
misrepresentation.

**Required remediation:** Add a reproducible pinned Circom/SnarkJS build job,
recorded witness/prove/verify evidence, verification keys linked to generated
Solidity verifiers, and a ceremony/deployment attestation before upgrading the
status from research-only.

**Status:** Open and honestly disclosed.

### WP-2026-09-05-03 — Live consensus remains an external deployment gap

**Severity: Critical for a live-consensus launch; not resolvable by unit tests**  
The canonical matrix records no validator onboarding, staked fleet, or HSM
attestation, despite the whitepaper's fleet and geographic requirements.  It
also records the on-chain two-signature oracle quorum as bootstrap rather than
the full validator-set supermajority.

**Impact:** Source-level DW-BFT/HHI calculations cannot establish the
whitepaper's consensus security properties without an independently observable
fleet.

**Required remediation:** Complete onboarding with hardware/HSM attestation,
deploy the required geographically distributed validator set, configure the
on-chain quorum to the deployed validator set, and publish a repeatable live
fleet conformance run.

**Status:** Open; retain bootstrap/research disclosure in all release material.

## Confirmed strengths

* The selected conformance battery passed **226 tests** with **7 expected
  optional-PQC skips**.  It covers the whitepaper gap closures, signal
  registry, information-conservation checks, and golden vectors.
* The AWA source now names and stores the six canonical MD §17 conditions and
  documents its operational quorum/HHI checks as a fail-closed superset.  This
  supersedes the older matrix wording that said the canonical SDP and
  Right-to-Invisibility conditions were absent; endpoint wiring still needs a
  dependency-complete API test run.
* The circuit documentation and the existing matrix accurately label
  unbuilt/external artifacts rather than representing simulated ZK operations
  as production Groth16 verification.

## Test and environment notes

The full `uv` test command could not resolve dependencies because this
environment's package tunnel could not fetch `bitcoinlib`.  The installed
interpreter also lacks `flask`, `ecdsa`, `eth_tester`, and therefore cannot
collect API, BTCP, or Solidity integration tests.  These are environment
limitations, not test passes or failures of the code under audit.  The passing
subset above is deliberately reported separately and must not be extrapolated
to the full suite.

## Release claim guidance

Until WP-2026-09-05-01 is remediated and the external prerequisites are
verified, release material may claim source-level whitepaper implementations
and the tested components listed above, but must not claim:

1. complete L5.3 degradation-route enforcement;
2. live diversity-weighted consensus/fleet security; or
3. production Groth16-backed privacy/MEV guarantees.
