# TRION / BTCP — Canonical Invariant Register

Master command §24 deliverable (Agent F, Wave 1).  This register is the
**work order for Waves 2 and 3**: every invariant is stated once, cited to
its authority (spec / whitepaper / documented engineering decision), its
enforcement status is pinned per layer with `file:line` evidence as of
HEAD (Wave-1-F), and the test that proves it (existing or added this
wave, `tests/btcp/test_invariants.py`) is named.  Remediation ownership
follows the wave plan (W2: G EVM/Solidity, H Solana, I Move, J TON, K
Cairo, L Vyper; W3: C registry, D Akashic/math, M API/relayer, N storage,
O deployment).

Status vocabulary:

- **ENFORCED** — fail-closed at that layer today (attack rejected).
- **PARTIAL** — some path(s) enforce, others don't (or the check exists
  but a caller can weaken its parameters).
- **UNENFORCED** — declared/required but no check in code at that layer.
- **N/A** — the layer structurally cannot enforce it (e.g. a pure
  computation module), or the concept doesn't exist there.

Layer keys: **py** = `core/btcp/*.py` (the operative Python engine),
**rs** = `rust/src/*` (reference implementation, statically verified —
no cargo in this environment), **Sol** = `contracts/solidity`,
**Vy** = `contracts/vyper`, **SVM** = `contracts/svm` (+ soroban),
**Move** = `contracts/move`, **TON** = `contracts/ton`,
**Cai** = `contracts/cairo` + `contracts/starknet`.

The state-machine hooks each invariant protects are in
`docs/protocol/BTCP_STATE_MACHINE.md` (M1–M5, T1–T8).  Certificate-field
bindings are deliberately expressed by role (anchor/execution evidence,
intent identity, validator cohort, coherence/threshold) — see
`docs/protocol/CANONICAL_CERTIFICATE.md` (Agent E, in flight).

---

## Core invariants (INV-001 … INV-018, master command §24 seed)

### INV-001 — Zero-bridge / assets never leave their chain

**Statement.** A BTCP route never moves an asset across chains: value is
locked in escrow on the source chain and released *natively* to the
counterparty after behavioral verification.  No wrapped tokens, no
bridge contracts, no lock/mint.  `assets_bridged` is always `False` and
BITP PASTE reports `cross_chain_movement: 0`.

**Authority.** BTCP_SPEC §4.2 step 3 ("executes natively — no bridge
contract, no wrapped token"), §5.1 BITP RESULT block; orchestrator.py:104
(zero-bridge field contract).

**Enforced today:** py ENFORCED (orchestrator.py:109 `assets_bridged`
frozen False; `execute_paste` modules.py:586-601 hardcodes zero movement)
· rs ENFORCED (bitp_matcher.rs PASTE semantics) · Sol/Vy/SVM/Move/TON/Cai
N/A-for-this-invariant (escrow contracts are single-chain by design —
the invariant holds structurally: there is no bridge code to call).

**Test.** `test_invariants.py::test_inv001_zero_bridge` (route +
paste both assert zero movement / no bridge); pre-existing
`tests/golden_test.py` STEP-7 checks.

**Remediation.** none (monitor for regressions in W4-Q dead-code sweep).

### INV-002 — Escrow terminal semantics: funds move exactly once, whole, to exactly one of two parties

**Statement.** From HOLDING, an escrow transitions to RELEASED (funds →
destination) or REVERTED/EMERGENCY_REVERTED (funds → funder) — never
both, never twice, never partially.  Terminal states have no outgoing
transitions.

**Authority.** BTCP_ESCROW.vy:29-30, 212-219 (invariants block);
spec §14.3 pseudocode; BTCP_SPEC build list line 148 ("Two-state atomic
escrow (HOLDING → RELEASED | REVERTED)").

**Enforced today:** py ENFORCED (state guards escrow_monitor.py:229, 247,
258, 279, 309 — every mutator checks the source state) · rs ENFORCED
(btcp_escrow_monitor.rs:109-135 state guards) · Sol ENFORCED (state
requires + check-effects-interactions, BTCPEscrow.sol `_consensusGate`
callers) · Vy ENFORCED (assert state == HOLDING, BTCP_ESCROW.vy:154, 194
+ state-before-transfer ordering, :176, :198) · SVM ENFORCED (state
require in release/revert) · Move ENFORCED (assert state, btcp_escrow.move:128,
157) · TON ENFORCED (op handlers check state) · Cai ENFORCED
(btcp_escrow.cairo state assert).

**Test.** `test_invariants.py::test_inv002_double_release_rejected`,
`::test_inv002_revert_after_release_rejected`.

**Remediation.** none.

### INV-003 — Release requires settlement verified + protocol-floor coherence

**Statement.** Escrow release requires (a) prior settlement verification
(G1 two-phase) and (b) `coherence ≥ threshold` where the threshold can
never be lowered by the caller below the protocol floor (Σ-floor 0.55 —
the same constant as the proof builder's `DEFAULT_COHERENCE_THRESHOLD`).
Callers may tighten (raise) the threshold, never loosen it.

**Authority.** BTCP_SPEC Gap D/§14.3 ("C(t) ≥ Θ(t)"); whitepaper §4.3
2/3-BFT floor; ENG-DECISION: floor value 0.55 mirrors
modules.py:143 (BTCPProofBuilder.DEFAULT_COHERENCE_THRESHOLD) — the
coherence gate is one number everywhere.

**Enforced today:** py PARTIAL→ENFORCED this wave: two-phase flag was
enforced (escrow_monitor.py:231), but `min_coherence` was a
caller-supplied parameter with no floor — a caller could pass 0.0
(attack: zero-coherence release).  This wave adds
`MIN_COHERENCE_FLOOR` clamping in `release_escrow` /
`release_from_pending_akashic`.  The *coherence value itself* remains
caller-supplied at the py layer (its integrity is the certificate's job
on-chain) — see INV-011.  rs PARTIAL (monitor is a state machine; the
verdict gate lives in the oracle/escrow contract) · Sol PARTIAL
(`minCoherence` is a lock-time relayer argument with an upper bound but
no floor — BTCPEscrow.sol:294 `require(minCoherence <= 1_000_000)`;
oracle-side threshold check exists in `_consensusGate`:260-261) · Vy
ENFORCED (threshold comes from the oracle verdict, not the caller:
BTCP_ESCROW.vy:173) · SVM PARTIAL (min_n with MAX bound only, release
authority key) · Move PARTIAL (relayer-set `coherence_verified` flag,
btcp_escrow.move:117-125 — no on-chain quorum binding) · TON PARTIAL
(relayer/owner-gated release, escrow.fc:40) · Cai PARTIAL (threshold
arguments checked for range, not floor).

**Test.** `test_invariants.py::test_inv003_coherence_floor` (release with
min_coherence=0.0 supplied by the caller is still gated at 0.55),
`::test_inv003_two_phase_release` (release before verify_settlement
fails).

**Remediation.** W2-G (floor on lock-time minCoherence), W2-I (bind
coherence verdict on-chain instead of relayer flag), W2-H/J/K/L parity.

### INV-004 — No release after timeout

**Statement.** Once an escrow is past its timeout window (block >
lock_block + timeout_blocks), release is refused; the only remaining
paths are revert / emergency revert.  Conversely, revert-on-timeout is
permissionless and cannot be blocked by TRION.

**Authority.** BTCP_SPEC §14.3 `revert_on_timeout`; escrow_monitor.py
state machine docstring lines 15-18.

**Enforced today:** py ENFORCED (escrow_monitor.py:236-237 block-number
timeout check inside release; revert permissionless) · rs ENFORCED
(`is_timed_out`, btcp_escrow_monitor.rs:147-155) · Sol ENFORCED (timeout
guard in release path + permissionless revert) · Vy ENFORCED
(BTCP_ESCROW.vy:195) · SVM ENFORCED · Move ENFORCED (timeout escape
hatch, btcp_escrow.move:139-152) · TON ENFORCED · Cai ENFORCED.

**Test.** `test_invariants.py::test_inv004_release_after_timeout_rejected`.

**Remediation.** none.

### INV-005 — Verdict freshness

**Statement.** A consensus verdict is consumable only within its
freshness window (≤ 300 s at the escrow gate on-chain; certification
windows by value tier for proofs — A3).  A stale verdict can never move
funds, and only NEW distinct attestations refresh a verdict's timestamp.

**Authority.** BTCP_ESCROW.vy:172 (300s); TRIONOracleV3.sol
submitRouteAttestation (M2 freshness comment); modules.py:92-104
CERT_WINDOWS (A3 value-tiered proof expiry); BTCP_SPEC Fix 3.

**Enforced today:** py ENFORCED structurally (verify_proof checks
certification_expiry, modules.py:290; py escrow release takes a
current-block argument, escrow_monitor.py:236) — py escrow has no
wall-clock verdict freshness because py release does not consume an
on-chain verdict (documented asymmetry) · rs ENFORCED (verify_proof
expiry check, btcp_proof_builder.rs:184) · Sol ENFORCED (300 s in
`_consensusGate`:259; M2 freshness in TRIONOracleV3) · Vy ENFORCED · SVM
PARTIAL (no freshness field in bootstrap mode) · Move UNENFORCED (no
timestamp binding on the coherence flag) · TON PARTIAL · Cai PARTIAL.

**Test.** `test_invariants.py::test_inv005_expired_certificate_rejected`
(proof expired at current_block).

**Remediation.** W2-I (Move freshness), W2-H/J/K parity, W2-G (keep).

### INV-006 — Validator-pool payout happens exactly once per completed route

**Statement.** A route's completion pays its validator pools (0.1% route
value, 60/40 anchor/execution) exactly once — regardless of how many
times the completion event is replayed, whenever it is replayed, or
across process restarts.  Failed/timeout routes pay nothing.

**Authority.** BTCP_SPEC Fix 4; ENG-DECISION (schema.sql deviation,
state_store.py:39-44): UNIQUE(epoch, validator_address, route_id).

**Enforced today:** py PARTIAL→ENFORCED this wave: the store guard
(state_store.py:254 `idx_rewards_replay_guard`) only collapses replays
inside the *same UTC epoch* — a completion event replayed after midnight
would create a second (epoch, pool, route) row and double-pay.  This
wave's `update_route_status` no-op semantics (same-status replays
perform no persistence/recording at all) close that window; terminal
freeze prevents FAILED→COMPLETED resurrection from paying. · rs
N/A (payout is py/schema + on-chain domain) · Sol N/A-for-this-VM (fee
split math mirrored in `validator_fee_calculator.rs` / modules.py:1090)
· other VMs N/A.

**Test.** `test_invariants.py::test_inv006_reward_replay_no_double_pay`
(includes the cross-midnight-epoch simulation: monkeypatched epoch
boundary, replay, still exactly 2 reward rows),
`::test_inv006_failed_route_pays_nothing`.

**Remediation.** W3-N (TimescaleDB writers must reproduce the replay
guard; schema.sql has no such constraint — documented deviation).

### INV-007 — BITP complement must be a distinct, unexpired counterparty

**Statement.** A BITP match requires `intent_B.entity_id ≠
intent_A.entity_id` (anti-wash / anti-self-dealing: an entity must not
be able to fill both sides of its own commitment and fabricate a price
discovery), and both intents must be unexpired at match time
(`expiry > now`).

**Authority.** BTCP_SPEC §5.1 MATCH phase conditions (explicit list);
rust parity: bitp_matcher.rs:209-222 (expired seeking intent → None;
same-entity candidates skipped).

**Enforced today:** py UNENFORCED→ENFORCED this wave for the entity
check (find_complement had NO entity check — a self-match returned a
"match"); expiry is now enforceable via the new optional `current_time`
parameter (rust enforces unconditionally; py default None preserves
legacy pure-function callers, expiry enforced at the Akashic clipboard
tier) · rs ENFORCED (bitp_matcher.rs:216-218 entity, :220 expiry) ·
Sol/Vy/… N/A (no on-chain BITP matcher; PASTE is behavioral).

**Test.** `test_invariants.py::test_inv007_self_match_rejected`,
`::test_inv007_expired_candidate_skipped` (with current_time).

**Remediation.** W3-D (Akashic clipboard must never serve expired
candidates); note for Agent E: the certificate should bind both
counterparty identities.

### INV-008 — Intent registration is idempotent and collision-free

**Statement.** Registering an intent is keyed by content (intent_hash /
intent_id): re-registering the same intent is a no-op; two *different*
submissions never silently collide into one route; the intent nonce is
a per-entity monotonic counter (spec §4.1), not a wall-clock read.

**Authority.** BTCP_SPEC §4.1 (`nonce: per-entity monotonic counter`,
`intent registered by hash`); BTCPIntent.sol:55-64 (`INTENT_EXISTS`,
`DEADLINE_PAST`).

**Enforced today:** py PARTIAL→ENFORCED this wave: the cross-chain
message guard (`idx_msg_nonce_unique`, state_store.py:232) prevented
same-nonce message duplication, but `create_route` derived intent_id
from `time.time()` alone and the nonce from `int(time.time()*1000) % 2³²`
— same-microsecond identical submissions collided (silent route
clobber) and the nonce was not per-entity monotonic.  This wave: intent
ids mix a process-global monotonic counter + random session tag
(collision-free), nonces are per-entity monotonic within the
orchestrator (seeded from wall-clock ms, documented cross-restart
caveat) · rs ENFORCED (register_intent keyed by intent hash,
btcp_router.rs:154) · Sol ENFORCED (BTCPIntent.sol:55) · other
contracts: intent contracts mirror the EXISTS guard (starknet
btcp_intent.cairo, ton intent.fc, svm btcp_intent, move btcp_intent) —
W2 agents verify per-family.

**Test.** `test_invariants.py::test_inv008_rapid_identical_routes_do_not_clobber`
(two identical rapid create_route calls → two distinct routes/rows),
`::test_inv008_nonce_monotonic_per_entity`.

**Remediation.** W3-D (persisted per-entity nonce counter — the
cross-restart monotonicity caveat); W2 per-VM intent-contract audit.

### INV-009 — No fabricated proof bytes (honest deferral)

**Statement.** Every emitted proof is real cryptography over real
witness data derived from the intent; when a circuit's witness is
unavailable the route records an honest `zk_pending` deferral and
`verify_proofs` fails closed — never a "proof" over placeholder or
random values.

**Authority.** ENG-DECISION documented in orchestrator.py:336-347
(honesty contract); BTCP_SPEC §5.6 (ZK commitment phases).

**Enforced today:** py ENFORCED (PrivacyRouter.generate_proofs
deferral paths orchestrator.py:417-428, 496-508; verify_proofs marks
pending as invalid, orchestrator.py:533-538) · rs N/A (rust ZK is
circuit-spec domain) · contracts N/A (on-chain verification consumes
proofs; production circuits are zk-circuits/, W2/W4).

**Test.** `test_invariants.py::test_inv009_pending_proof_fails_closed`
(a zk_pending route is NOT verified; a real-witness route is).

**Remediation.** W4-P (red team the deferral honesty across circuits).

### INV-010 — Proof-builder coherence threshold is protocol-owned

**Statement.** The coherence threshold Θ used when *building* a BTCP
proof may only be raised above the protocol default (0.55), never
lowered; `threshold_margin = coherence − Θ` therefore cannot be
trivially non-negative by caller choice of Θ.

**Authority.** modules.py:140-143 (whitepaper §4.3 2/3-BFT → Σ(t) >
0.55 default); BTCP_SPEC §4.2 step 3 (ConsensusProof carries
coherence_score + threshold_margin).

**Enforced today:** py PARTIAL→ENFORCED this wave:
`build_proof_from_validators(coherence_threshold=None)` accepted any
caller value (attack: threshold=0.0 → any coherence passes).  Now
clamped to ≥ DEFAULT_COHERENCE_THRESHOLD.  The raw `build_proof` path
keeps its explicit threshold argument for parity with the rust builder,
documented as a trusted internal API (no external caller passes a
lowered value; verified by grep this wave).  rs ENFORCED (threshold is
a builder constant, btcp_proof_builder.rs) · Sol ENFORCED (threshold
comes from the etched oracle route values, TRIONOracleV3.sol:204-230
immutable-after-first-write) · Vy ENFORCED (oracle-supplied) · other
VMs PARTIAL/UNENFORCED — W2 work orders.

**Test.** `test_invariants.py::test_inv010_threshold_clamped` (build with
coherence_threshold=0.0 → margin still computed against 0.55 → proof
rejected when coherence < 0.55).

**Remediation.** W2-G/H/I/J/K/L (threshold constants per family).

### INV-011 — Consensus proof structural contract (signers, HHI, distinct, shape, expiry)

**Statement.** A consensus proof verifies only when: certification not
expired; ≥ 3 validator signatures; coherence > 0; threshold margin ≥ 0;
HHI ≤ 0.5 (scale-normalized); all signers distinct; every signature
exactly 65 bytes (secp256k1 r‖s‖v shape).

**Authority.** rust/src/btcp_proof_builder.rs:184-220 (canonical
structural contract); modules.py:272-313 mirrors it (parity is
test-enforced).

**Enforced today:** py ENFORCED (modules.py verify_proof) · rs ENFORCED
(static parity verified this wave; runtime verification needs cargo —
external-toolchain policy) · Sol ENFORCED (submitRouteAttestation:
recovered distinct signers, sorted, quorum — TRIONOracleV3.sol:250+) ·
Vy ENFORCED (attestations ≥ 2 hard floor at consumption,
BTCP_ESCROW.vy:171) · SVM PARTIAL (authority key in bootstrap) · Move
UNENFORCED (flag only) · TON PARTIAL · Cai PARTIAL.

**Test.** `test_invariants.py::test_inv011_structural_contract`
(<3 signers, duplicate signer, wrong-length signature, concentrated HHI,
negative margin — each rejected).

**Remediation.** W2-I (Move: replace flag with attestation set),
W2-H/J/K parity.

### INV-012 — Aggregated-signature quorum is recomputed at verification, never trusted from the proof dict

**Statement.** When verifying a self-contained consensus proof
(`verify_consensus_proof`), the verifier recomputes `signer_count /
total_validators ≥ quorum` with the protocol quorum floor (2/3) — the
proof's own `threshold_met` / `quorum_fraction` fields are claims, not
authority.  A 1-of-1 or 2-of-10 "consensus" must not verify even with
real signatures over it.

**Authority.** modules.py:323 (DEFAULT_QUORUM_FRACTION = 2/3);
TRIONOracleV3 S3/C2 fix (msg.sender carries no authority; count only
grows via signature-verified DISTINCT validators — the same principle).

**Enforced today:** py PARTIAL→ENFORCED this wave: `verify_consensus_proof`
previously trusted `threshold_met` from the proof dict (attack: forge
{threshold_met: true, total_validators: 1} with one real signature).
Now recomputed with `max(claimed quorum, 2/3)`.  · rs N/A (no dict-form
proof in rust) · Sol ENFORCED (on-chain recompute) · other VMs — see
INV-011 statuses.

**Test.** `test_invariants.py::test_inv012_forged_quorum_claim_rejected`
(real signature, forged threshold_met/total — rejected).

**Remediation.** W2 families with self-contained proof dicts.

### INV-013 — Route status machine: no resurrection, no reordering, monotonic progress

**Statement.** Route status transitions follow the M1 table exactly:
terminal states (COMPLETED/FAILED/TIMEOUT) are frozen (a same-status
replay is an idempotent no-op; any *different* target is rejected);
FAILED/TIMEOUT are reachable from any active state; execution-progress
transitions are forward-only (numeric order PENDING → INTENT_CREATED →
PROOFS_GENERATED → SOURCE_EXECUTED → DEST_EXECUTED → COMPLETED).

**Authority.** BTCP_SPEC §4.2 (six-step sequence — the steps are ordered);
docs/protocol/BTCP_STATE_MACHINE.md M1 (this register's companion);
ENG-DECISION: forward-numeric order is the code's existing IntEnum
ladder (orchestrator.py:75-84).

**Enforced today:** py UNENFORCED→ENFORCED this wave: `update_route_status`
accepted ANY from→to pair (attack: COMPLETED → FAILED → COMPLETED
resurrection; DEST_EXECUTED → SOURCE_EXECUTED reordering; a replayed
completion re-recording rows).  Now the M1 table is executable law.  ·
rs N/A (rust router has no persisted status machine) · Sol ENFORCED
(BTCPRoute.sol:92 `ALREADY_VERIFIED` on re-finalize) · other VMs: route
contracts enforce single finalization — W2 verify per family.

**Test.** `test_invariants.py::test_inv013_resurrection_rejected`,
`::test_inv013_reorder_rejected`, `::test_inv013_failure_always_reachable`,
`::test_inv013_forward_progress_allowed` (the test-suite's legitimate
PROOFS_GENERATED → COMPLETED jump keeps working).

**Remediation.** W2 per-VM route-contract audit.

### INV-014 — Intent identity is content/sequence-derived, not caller-collideable

**Statement.** Route/intent ids and nonces are derived by the protocol
(monotonic sequence + per-entity counters), so no caller can clobber or
pre-guess another route's identity.

**Authority.** spec §4.1 nonce; BTCP_ESCROW.vy:98-112 (derived escrow_id
"not caller-supplied, unlike the Solidity tier" — the Vyper comment is
itself the authority that this is a known risk).

**Enforced today:** py PARTIAL→ENFORCED this wave (see INV-008 fix) ·
Sol PARTIAL (BTCPEscrow.lockEscrow takes a caller-supplied escrowId +
routeId — relayer-trusted but derived nowhere) · Vy ENFORCED (derived) ·
other VMs PARTIAL — W2 verify.

**Test.** same as INV-008 battery.

**Remediation.** W2-G (derive or validate escrow_id like the Vyper tier).

### INV-015 — Dispute resolution: 3-of-5 majority, one vote per annotator, panel-only, bond-gated

**Statement.** A dispute resolves only with ≥3 agreeing votes from
distinct *selected-panel* annotators; each annotator votes at most once;
votes are only accepted while the case is OPEN; opening a case requires
the 5% challenge bond; slashing binds exclusively to a GUILTY verdict.

**Authority.** BTCP_SPEC Gap I ("Conscious Layer 3-of-5 +
stake-and-slash"); dispute_resolution.py:33-36 constants.

**Enforced today:** py PARTIAL: distinct-vote + panel + OPEN-state +
majority + bond all ENFORCED (dispute_resolution.py:247-266, 241); a
**panel-exhaustion resolution** was added this wave so a panel shorter
than 5 resolves at exhaustion instead of hanging OPEN forever
(previously DISMISSED was unreachable dead code — a 2-2 split on a
short panel froze the case eternally); the **72h dispute window is
declared (line 35) but NOT enforced in cast_vote** — votes after the
window are currently accepted (the open item, asserted by an xfail
test); slash-on-guilty is recorded but stake movement is the
staking-contract domain.  · rs PARTIAL (dispute_resolution.rs mirrors
the vote logic) · Sol/Vy PARTIAL (staking contracts exist; the
dispute→slash wiring is W2).  Other VMs N/A.

**Test.** `test_invariants.py::test_inv015_double_vote_rejected`,
`::test_inv015_non_panel_vote_rejected`,
`::test_inv015_no_majority_dismissed`,
`::test_inv015_window_expiry_rejects_votes` (documented current
behavior + the spec gap).

**Remediation.** W1-F registered open item (enforce window — belongs
with the dispute-lifecycle redesign to avoid breaking 3-of-5 semantics
mid-wave), W2-G/L (dispute→slash wiring).

### INV-016 — Behavioral-credential witness provenance is explicit

**Statement.** Behavioral-credential (and IAP-share) proofs generated
from caller-supplied `behavioral_data` / `iap_economics` are labeled
with their witness source (`witness_source: caller_self_attested`):
the cryptography is real, but the *scores* are the caller's claims
until bound to the Akashic behavioral ledger.  A self-attested
credential must never be consumed as a TRION attestation.

**Authority.** ENG-DECISION (this wave — the honesty-contract principle
of orchestrator.py:336-347 extended from proof *bytes* to witness
*provenance*); spec §5.1 CUT phase ("behavioral_proof = complete BEO
history as credential" — the real source is BEO, not the caller).

**Enforced today:** py PARTIAL→ENFORCED (labeling) this wave: proofs built
from caller data carry the witness_source marker; the *binding to BEO*
remains UNENFORCED at py (no Akashic lookup in the proof path — that
wiring is W3-D).  Thresholds themselves are protocol-owned (coherence
0.55 / manipulation 0.30 hardcoded, orchestrator.py:451-452 — callers
cannot move the goalposts).  · rs N/A · contracts N/A (credentials are
off-chain).

**Test.** `test_invariants.py::test_inv016_witness_provenance_labeled`
(FULL-level route from caller behavioral_data carries
`witness_source: caller_self_attested`; thresholds in the proof are the
protocol constants, not caller values).

**Remediation.** W3-D (bind behavioral witnesses to the Akashic BEO
ledger), W3-M (API layer must forward provenance, never strip it — see
Wave-3 note below).

### INV-017 — Failure classification protects the entity from EXTERNAL causes

**Statement.** A failed route is classified EXTERNAL vs ENTITY per Fix 2
(chain outage / NL collapse / reorg / MF spike vs invalid proof /
collateral withdrawal / conflicting intents / systematic timeout);
EXTERNAL causes have zero BEO impact; ambiguous failures give the
entity the benefit of doubt twice, the third within 90 days escalates
to ENTITY; after an EXTERNAL failure the entity chooses
WAIT/CANCEL/REROUTE with the intent preserved.

**Authority.** BTCP_SPEC Fix 2 (btcp_failure_classifier block);
modules.py:829-877.

**Enforced today:** py ENFORCED (FailureClassifier.classify implements
the indicator ladder; route failure cause lands in
`btcp_routes.failure_cause`, orchestrator.py:786-788) · rs ENFORCED
(btcp_failure_classifier.rs) · contracts N/A (classification is
off-chain; its *effects* — intent preservation, escrow return — are the
escrow machine's E5/E6 paths, which are ENFORCED).

**Test.** `test_invariants.py::test_inv017_external_cause_zero_penalty`
(classifier ladder + failure_cause recorded as EXTERNAL for
external-only indicators).

**Remediation.** none at py; W4-P adversarial review of the ladder.

### INV-018 — Dispute window and case lifecycle are time-bounded

**Statement.** A dispute case is open for exactly the 72-hour window;
votes after the window are rejected; an unresolved case at window close
resolves DISMISSED (insufficient majority); a resolved case is frozen.

**Authority.** dispute_resolution.py:35 (DISPUTE_WINDOW_SECONDS = 72h);
spec Gap I resolution framework.

**Enforced today:** py PARTIAL: resolved-case freeze ENFORCED
(cast_vote requires OPEN), double-vote ENFORCED; **window expiry
UNENFORCED** (see INV-015).  · rs PARTIAL (same shape) · contracts N/A.

**Test.** `test_invariants.py::test_inv018_case_freeze_after_resolution`.

**Remediation.** W1-F registered open item (window enforcement), W2-G
if a dispute contract lands.

---

## Additional invariants discovered by this audit (INV-019 …)

### INV-019 — Cross-language BH parity: same tx → same behavioral hash

**Statement.** The Python streamer and the Rust indexers produce
byte-identical behavioral hashes for the same transaction (field
values: entity = sha3(bh_id), context = 0, per-chain decimals, real
block times).

**Authority.** Worklog Task 20 (cross-language golden-vector
consistency; commit 19decc3); bh_streamer.py:182 compute_bh.

**Enforced today:** py ENFORCED (golden vectors; parity tests) · rs
ENFORCED statically (determinism of field construction verified by
review; runtime needs cargo — external-toolchain policy).

**Test.** `tests/unit/bh_cross_language_vector.py` (existing).

**Remediation.** external toolchain (cargo) for runtime confirmation.

### INV-020 — Routing refuses stale/suspended/manipulated chains

**Statement.** A route is valid only when the execution chain's NL >
0.05, finality confidence > 0.80, BTCP_score > 0.10, ≥3 validators
cover it, and the chain is not fork-suspended; OOA chains route with a
penalized threshold and capped confidence (never out-confidence
integrated chains).

**Authority.** BTCP_SPEC §4.2 step 2 (BIBL analysis + route selection);
router.py:62-65 constants; BIBLEngine.is_chain_suspended.

**Enforced today:** py ENFORCED (router.route_is_valid:235-251; OOA
conf cap modules.py:740) — the *inputs* (validator counts, NL) are
caller-supplied at the py simulation layer (they are indexer outputs in
production; binding is W3-C/D) · rs ENFORCED (btcp_router.rs config
gates) · contracts N/A (routing is off-chain).

**Test.** `test_invariants.py::test_inv020_route_validity_gates`
(low finality / low NL / <3 validators / low score each rejected; OOA
confidence < integrated).

**Remediation.** W3-C (registry-fed validator counts), W3-D (BIBL
state feed).

### INV-021 — Balance reservation prevents concurrent double-spend (Gap E)

**Statement.** Intents reserve against the entity's available balance
in real time; concurrent routes cannot collectively reserve more than
the available amount; reservations survive restarts and are released on
finalization/revert.

**Authority.** BTCP_SPEC Gap E (Behavioral Balance Reservation);
router.py:68-147.

**Enforced today:** py ENFORCED (reserve_balance:111-122; persisted,
reload-capable) — the `available` input is caller-supplied at the py
layer (BEO ledger is the real source — W3-D) · rs ENFORCED
(btcp_router.rs:118) · contracts N/A.

**Test.** `test_invariants.py::test_inv021_reservation_blocks_double_spend`
(second concurrent reservation exceeding availability rejected; release
restores capacity).

**Remediation.** W3-D (bind `available` to the BEO/ledger source).

### INV-022 — BLO fills are monotonic and expiry is permissionless & penalty-free

**Statement.** `filled_amount` only grows (no over-fill, no un-fill);
anyone can expire an unfilled BLO after its expiry block; expiry
records an honest behavioral note with NO penalty.

**Authority.** BTCP_SPEC §5.5 (partial fill + expiry semantics);
BehavioralLimitOrder.sol.

**Enforced today:** py N/A (no py BLO engine — BLOScheduler is
window-selection only) · Sol ENFORCED (BehavioralLimitOrder.sol fill
arithmetic + expiry) · rust blo_scheduler.rs PARTIAL (scheduling only) ·
other VMs: no BLO contract — W2-K/L optional.

**Test.** py layer N/A — covered by `tests/contracts` (Solidity) in W2
scope.

**Remediation.** W2-G (verify partial-fill monotonicity under
reentrancy), W4-P.

---

## Wave-3 API note (for Agent M — no edits made by F)

`api/btcp_continuum_routes.py` (`/api/v1/btcp/orchestrate`) forwards
caller `behavioral_data` / `iap_economics` into
`BTCPOrchestrator.create_route` verbatim (api/btcp_continuum_routes.py:1382-1393
`behavioral_data=data.get(...)`).  With this wave's INV-016 fix the
orchestrator labels those witnesses self-attested and refuses to treat
them as protocol attestation — the API layer itself manufactures no
security truth (thresholds, quorum, validator sets are never taken from
requests; chain ids/addresses are validated, privacy_level is
enum-checked).  Remaining Wave-3 items: (1) surface
`witness_source`/`zk_pending` in the API response contract so consumers
cannot mistake self-attested credentials for TRION attestations;
(2) consider capping caller-supplied `price_tolerance` on `/bitp/match`
(currently unbounded — matcher integrity beyond tolerance is INV-007's
entity/expiry checks, but a pathological tolerance ≥ 1 matches any
magnitude); (3) `/validator_fee` accepts caller validator-count inputs
(simulation-only — fine, but label it).

## Summary scorecard (per layer)

| Layer | ENFORCED (post-this-wave) | PARTIAL | UNENFORCED | Notes |
|---|---|---|---|---|
| py `core/btcp` | INV-001,002,003,004,005,006,007,008,009,010,011,012,013,014,017,019,020,021 | INV-015/018 (72h window), INV-016 (BEO binding) | — | 0 hard UNENFORCED remain after this wave's fixes |
| rust `rust/src` (static) | 001,002,004,005,007,008,010,011,017,019,020,021 | 015/018; 016 N/A | — | runtime verification pending cargo |
| EVM Solidity | 001,002,004,005,011,012,013 | 003,010,014,015 | — | Wave 2 work: minCoherence floor, derived ids, dispute wiring |
| Vyper | 001,002,003,004,005,010,011 | 015 (dispute wiring) | — | strongest escrow tier |
| SVM/Soroban | 001,002,004,013 | 003,005,010,011,012,014 | — | release-authority bootstrap fallback (W2-H) |
| Move | 001,002,004,008,013 | 003,014 | 005,011,012 | relayer-flag coherence (W2-I) |
| TON | 001,002,004,008 | 003,005,010,011,014 | — | W2-J |
| Cairo/Starknet | 001,002,004 | 003,005,010,011,014 | — | W2-K |

(Counting rule: an invariant that is N/A at a layer is noted in the
row's status cells, not counted as a failure.)
