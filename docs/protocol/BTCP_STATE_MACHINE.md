# BTCP + TRION — Canonical State Machines

Master command §25 deliverable (Agent F, Wave 1).  This document is the
**register of record** for every protocol state machine: the states that
exist, the transitions that are legal, who may cause them, what
cryptographic evidence each transition demands, and how replay / timeout /
emergency / substitution attempts are answered.  Where the running Python
engine, the Rust reference, and the on-chain contracts disagree, the
disagreement is stated explicitly and becomes a Wave 2 / Wave 3 work item.

Hierarchy of truth (per `docs/audit/AUTONOMOUS_MASTER_WORKLOG.md`):
spec/BTCP_SPEC.txt governs BTCP absolutely; the implementation is evidence,
not authority.  Where the spec is silent (e.g. the PENDING_AKASHIC escrow
state, the EMERGENCY_REVERTED terminal, the dispute panel), the
implementation's documented engineering decision is cited as such
(`ENG-DECISION`).

Companion documents:

- `docs/security/CANONICAL_INVARIANTS.md` — the invariant register
  (§24); each invariant links back to the transition rows below that it
  protects.
- `docs/protocol/CANONICAL_CERTIFICATE.md` *(Agent E, in flight)* — the
  canonical consensus certificate.  This document deliberately references
  it by role ("the certificate") and never by field name, so the state
  machines below stay valid whatever the certificate's final shape is.
  Wherever a transition table column says "consensus certificate", the
  binding requirement is: the certificate must commit to (a) the anchored
  execution evidence (anchor BH / execution BH), (b) the intent/route
  identity, (c) the emitting validator cohort, and (d) the coherence and
  threshold values used at emission — *which* fields carry those four
  commitments is Agent E's to define.

---

## Part I — The BTCP machines

Five concurrent machines realize one intent.  They are coordinated (route
finalization requires escrow resolution; BITP PASTE requires both escrows)
but independently stateful:

| Machine | Owner layer | States |
|---|---|---|
| M1 Route lifecycle (§4.2 six steps) | py `BTCPOrchestrator`, rust `btcp_router` | 8 (incl. 3 terminal) |
| M2 Escrow lifecycle (§14.3, E1, Gaps 8/9) | py `EscrowMonitor`, contracts `BTCP_ESCROW`/`BTCPEscrow` | 6 (incl. 3 terminal) |
| M3 BITP clipboard (§5.1 CUT/MATCH/PASTE) | `BITPMatcher` py/rust, `bitp_clipboard` table | 4 |
| M4 Behavioral Limit Order (§5.5) | `BehavioralLimitOrder.sol`, `blo_orders` table | 4 |
| M5 Dispute / Conscious Layer (Gap I, Fix 2 impact) | `DisputeResolver` py, `dispute_resolution.rs` | 4 |

### M1 — Route lifecycle

States (source of truth: `core/btcp/orchestrator.py:75-84` `RouteStatus`;
persisted per route in the SQLite state store and projected into
`btcp_routes.status` / `btcp_intent_registry.status`):

```
PENDING → INTENT_CREATED → PROOFS_GENERATED → SOURCE_EXECUTED
        → DEST_EXECUTED → COMPLETED                     (happy path)
any active state → FAILED | TIMEOUT                     (terminal sinks)
COMPLETED | FAILED | TIMEOUT                            (terminal, frozen)
```

`PENDING` is the pre-step-2 state (intent not yet accepted).
`INTENT_CREATED` = steps 1–2 done (intent object registered, BIBL analysis
available).  `PROOFS_GENERATED` = steps 3–5 done (ZK proof set + VM
encodings + gas estimates).  `SOURCE_EXECUTED`/`DEST_EXECUTED` = step 4
per-chain native execution.  `COMPLETED` = step 6 (finalization, Akashic
recording, validator-pool payout).  `FAILED`/`TIMEOUT` map to intent-registry
status `FAILED`/`EXPIRED` (`_intent_registry_status`, orchestrator.py:267).

#### M1 transition table

| # | from | to | valid callers | cryptographic evidence required | preconditions | replay behavior | timeout behavior | emergency/pause | forbidden alternatives |
|---|------|----|---------------|--------------------------------|---------------|-----------------|------------------|-----------------|------------------------|
| R1 | PENDING | INTENT_CREATED | intent owner (via orchestrator `create_route` step 2) | intent commitment proof (privacy ≥ BASIC; zk `IntentWitness` over the real intent fields) | addresses valid for both chains; amount ≥ 0; deadline > now | same intent (id+nonce) re-submission is a no-op (cross-chain message `idx_msg_nonce_unique`, state_store.py:225) | deadline passed → intent never registers (caller error) | pausing intake = API-layer concern (Wave 3) | fabricating an intent id (time-only ids are collision-hardened; see INV-014) |
| R2 | PENDING / INTENT_CREATED | PROOFS_GENERATED | orchestrator step 5 (`PrivacyRouter.generate_proofs`) | real ZK proofs over real witnesses; missing witnesses defer honestly (`zk_pending`, fail-closed at verify) | intent object exists | regenerating proofs is idempotent (same witness → same commitment) | n/a | zk_pending routes are NOT "proven" (verify fails closed) | fabricating proof bytes over placeholder witnesses (removed in prior wave; INV-009) |
| R3 | PROOFS_GENERATED | SOURCE_EXECUTED | VM adapter layer / relayer (step 4) | chain-native tx receipt on the source chain bound to the encoded intent | proofs verify (or are honestly deferred); route not past deadline | tx hash idempotence is chain-native; route row records it once | deadline passed → transition refused (escalates to TIMEOUT) | chain outage → FailureClassifier EXTERNAL, route → FAILED with intent preserved | executing without prior proofs/encoding |
| R4 | SOURCE_EXECUTED | DEST_EXECUTED | VM adapter layer / relayer | tx receipt on destination chain + consensus certificate over the anchor BH (step 3 proof) | source leg executed; certificate fresh (expiry window by value tier, `CERT_WINDOWS`, modules.py:92) | re-submission of the same certificate is idempotent (attestation quorum dedupes per signer) | certificate expiry (A3 windows) → refuse, escalate TIMEOUT | reorg > safe confirmations → failure classified EXTERNAL, escrow revert | accepting an expired / stale certificate (INV-005) |
| R5 | DEST_EXECUTED | COMPLETED | orchestrator step 6 (`_record_route_status`) | both execution receipts + consensus certificate; escrow M2 in RELEASED for both legs | both legs executed; settlement verified | replay is a no-op: unique `(epoch, pool, route)` reward guard (state_store.py:247) + terminal-state freeze; replayed event pays pools once | n/a (terminal) | n/a | paying validator pools without execution evidence; resurrecting the route afterwards (INV-006, INV-013) |
| R6 | any active (PENDING…DEST_EXECUTED) | FAILED | failure classifier (Fix 2) / relayer / dispute resolver | failure record: cause indicators (chain outage, NL collapse, reorg, MF spike vs entity indicators) | route exists, not terminal | re-assertion idempotent (terminal) | timeout classified by cause; EXTERNAL preserves intent (entity chooses WAIT/CANCEL/REROUTE) | emergency revert of escrows → route FAILED | penalizing the entity for EXTERNAL cause (BEO impact zero, INV-017) |
| R7 | any active | TIMEOUT | escrow monitor (M2 timeout) / deadline scheduler | escrow timeout evidence (block > lock+timeout) or deadline expiry | escrow in HOLDING past timeout, or deadline passed | idempotent (terminal) | this IS the timeout path | n/a | releasing funds after timeout (INV-004) |
| R8 | COMPLETED → COMPLETED | — | supervisor replay of the step-6 event | (none new — no-op) | route already COMPLETED | **no-op by law**: no persistence write, no reward recompute — closes the cross-midnight-epoch double-pay window (INV-006) | n/a | n/a | any different target state from a terminal state |
| R9 | FAILED/TIMEOUT → FAILED/TIMEOUT (same) | — | supervisor replay | (none new — no-op) | route already in that terminal state | no-op | n/a | n/a | any different target state |

**Illegal transitions (rejected, fail-closed)** — the master-command §8
questions answered concretely for M1:

- *Resurrection*: COMPLETED → FAILED, FAILED → COMPLETED (would re-collect
  validator rewards or rewrite a settled audit trail) — rejected.
- *Reordering*: DEST_EXECUTED → SOURCE_EXECUTED, COMPLETED →
  PROOFS_GENERATED (backwards numeric transitions) — rejected.
- *Substitution*: the caller cannot swap entity/route/execution-BH/
  amount/destination mid-flight — those fields are fixed at intent
  creation and are hashed into the intent commitment, the route row
  (`anchor_bh`, `execution_chain`, `entity_id`) and every proof; a
  changed value fails proof verification and certificate binding
  (`anchorBH == escrowId` on-chain, BTCPEscrow.sol:241 /
  BTCP_ESCROW.vy:169).
- *Caller-supplied security truth*: proof thresholds (coherence floor,
  HHI ceiling, quorum, sig shape) are protocol constants, not call
  arguments (INV-010/011/012); behavioral *witness scores* supplied by
  the caller are labeled self-attested and never treated as TRION
  attestation (INV-016).
- *Double-execute*: funds move exactly once per escrow (M2 terminal
  semantics); rewards pay once per (epoch, pool, route); cross-chain
  messages dedupe on (sender, chains, nonce).

### M2 — Escrow lifecycle

States (py `EscrowState`, escrow_monitor.py:47-53; superset of the
schema.sql `HOLDING|RELEASED|REVERTED` enum, documented in
state_store.py:39-44; on-chain Vyper: `IDLE|HOLDING|RELEASED|REVERTED`,
BTCP_ESCROW.vy:37-40; Solidity adds `PENDING_AKASHIC` +
`EMERGENCY_REVERTED`, BTCPEscrow.sol:102):

```
IDLE → HOLDING → (PENDING_AKASHIC) → RELEASED | REVERTED | EMERGENCY_REVERTED
```

#### M2 transition table

| # | from | to | valid callers | cryptographic evidence required | preconditions | replay behavior | timeout behavior | emergency/pause | forbidden alternatives |
|---|------|----|---------------|--------------------------------|---------------|-----------------|------------------|-----------------|------------------------|
| E1 | IDLE | HOLDING | anyone with funds (Vyper `lock`, permissionless; py `lock_escrow`; Solidity: relayer only, `onlyRelayer`) | locked value itself (msg.value); escrow_id derived on-chain from (intent_hash ‖ entity ‖ block) in Vyper — not caller-chosen | escrow_id unused (state IDLE); amount > 0; timeout > 0; destination ≠ 0 | duplicate escrow_id rejected ("escrow exists"); same-block same-intent collision fails closed | deadline starts at lock block | Solidity `whenNotPaused` blocks NEW locks only; existing escrows continue their lifecycle | locking with a zero/absurd timeout to brick funds; choosing your own escrow_id (Solidity tier accepts caller id — Wave 2 item) |
| E2 | HOLDING | PENDING_AKASHIC | escrow monitor (E1 resolution: Akashic unavailable at execution time) | akashic outage observation | escrow in HOLDING | idempotent flag set | after 24h (AKASHIC_RECOVERY_SECONDS) auto-degrades to revert | n/a | using PENDING_AKASHIC to dodge the coherence gate |
| E3 | HOLDING | RELEASED | permissionless caller presenting a valid route verdict (Vyper `release`); relayer/consensus authority (Solidity/SVM); py monitor `release_escrow` (settlement engine) | consensus certificate: quorum ≥ floor, freshness ≤ 300s, `coherence ≥ threshold`, **verdict bound to THIS escrow** (anchorBH == escrowId) | settlement verified first (G1 two-phase, py `verify_settlement`); not past timeout; coherence ≥ protocol floor | second release refused (state ≠ HOLDING); funds move exactly once | release after timeout refused (block check, escrow_monitor.py:236) | pause never blocks settling escrows (existing lifecycle proceeds) | releasing on a verdict attested for a different escrow (route-spoof, M3 fix); caller lowering the coherence floor (INV-003) |
| E4 | PENDING_AKASHIC | RELEASED | escrow monitor after Akashic recovery | same as E3 + akashic recovery within 24h | within AKASHIC_RECOVERY_SECONDS; coherence ≥ floor | same as E3 | window expiry → only revert remains | n/a | "recovering" after 24h with a stale coherence value |
| E5 | HOLDING / PENDING_AKASHIC | REVERTED | anyone after timeout (permissionless escape, py + Vyper); relayer for coherence-failure/route-invalid; py also on execution_confirmed=FALSE | timeout: block height evidence; failure: consensus verdict / MF signal | escrow in HOLDING or PENDING_AKASHIC (or Disputed in rust) | second revert refused (terminal) | 24h akashic window expiry forces TIMEOUT/AKASHIC_OUTAGE_24H reason | cascade revert to parent escrow (Gap 9) fires automatically | reverting an escrow whose counterparty escrow already RELEASED (two-phase discipline) |
| E6 | HOLDING / PENDING_AKASHIC | EMERGENCY_REVERTED | **anyone** after 7 days (Gap 8 escape hatch; no TRION signal needed) | elapsed-time evidence only (lock_timestamp + 7d) | 7 days elapsed; state still HOLDING/PENDING_AKASHIC | idempotent (terminal) | this IS the ultimate timeout | this IS the emergency path — deliberately permissionless | triggering before 7 days; TRION being able to block it |
| E7 | REVERTED (child) | REVERTED (parent) | cascade (Gap 9) | child revert evidence | parent exists and is HOLDING/PENDING_AKASHIC; child timeout < parent timeout by construction | recursion follows the parent chain once | n/a | n/a | cascade out of a terminal parent |

Terminal freeze: RELEASED / REVERTED / EMERGENCY_REVERTED have **no**
outgoing transitions; every mutator checks the current state first and
returns False on a terminal source (py escrow_monitor.py:229, 247, 258,
279, 309).  On-chain this is enforced by `assert record.state == HOLDING`
(Vyper) / `require(... == HOLDING ...)` (Solidity) plus
check-effects-interactions ordering (state flips **before** the transfer).

### M3 — BITP clipboard (§5.1)

States: `POSTED` (CUT complete, commitment on the Akashic clipboard) →
`MATCHED` (complement found) → `FULFILLED` (PASTE executed) /
`EXPIRED` (no complement before expiry → becomes a BLO, M4).  Projection
table `bitp_clipboard.status` (spec §schema).

| transition | valid callers | evidence | preconditions | replay | timeout | emergency | forbidden |
|---|---|---|---|---|---|---|---|
| CUT → POSTED | intent owner | commitment_hash = Hash_DNA(entity ‖ intent_hash ‖ behavioral_proof_root ‖ timestamp ‖ nonce) | assets held on source chain; behavioral proof root exists | same commitment re-posted = no-op (akashic upsert) | expiry set at post | n/a | posting without holding the asset (balance reservation, Gap E) |
| POSTED → MATCHED | BITP matcher (protocol, not the entity) | complement proof (assets mirrored, magnitude within behavioral_price_tolerance) | **intent_B.entity_id ≠ intent_A.entity_id** (spec §5.1 MATCH phase; anti-wash); **intent_B.expiry > now**; distinct chains | a matched pair cannot re-match (clipboard entry consumed) | expired candidates are skipped (rust `find_complement`, bitp_matcher.rs:220) | n/a | **self-match** — the same entity filling both sides to fake a price discovery (py matcher now rejects this; INV-007); matching an expired intent |
| MATCHED → FULFILLED | TRION PASTE emitter | both native transfer receipts + BTCP_ESCROW references | both escrows in HOLDING, settlement verified | idempotent per commitment pair | escrow timeouts (M2) revert the paste | emergency revert (M2 E6) | wrapped tokens, bridge contracts, cross-chain asset movement (all forbidden by construction — `execute_paste` returns `cross_chain_movement: 0`) |

### M4 — Behavioral Limit Order (§5.5)

States: `OPEN → PARTIALLY_FILLED → FILLED`, `OPEN/PARTIALLY_FILLED →
EXPIRED` (BLOStatus, spec §5.5; `BehavioralLimitOrder.sol`).

| transition | valid callers | evidence | preconditions | replay | timeout | emergency | forbidden |
|---|---|---|---|---|---|---|---|
| OPEN → PARTIALLY_FILLED | any bidder entity | fill amount + bidder behavioral health (BTCP_score × counterparty health ranking) | bidder ≠ poster; amount ≤ remaining | partial fills accumulate monotonically (filled_amount only grows) | n/a | n/a | over-fill; filling with a worse behavioral rank than a standing better bid |
| → FILLED | any bidder | final fill receipt | filled_amount = magnitude | terminal | n/a | n/a | resurrection |
| → EXPIRED | anyone (permissionless) | block > expiry_block AND unfilled remainder | unfilled remainder > 0 | idempotent (terminal) | this IS the timeout path — **no penalty**, behavioral record notes the honest attempt | n/a | penalizing an expired BLO; keeping the commitment alive past expiry |

### M5 — Dispute / Conscious Layer (Gap I)

States: `OPEN → RESOLVED_GUILTY | RESOLVED_NOT_GUILTY | DISMISSED`
(`DisputeStatus`, dispute_resolution.py:26-30).

| transition | valid callers | evidence | preconditions | replay | timeout | emergency | forbidden |
|---|---|---|---|---|---|---|---|
| → OPEN | claimant (with challenge bond) | claim + evidence hashes; bond = 5% of challenged value (CHALLENGE_BOND_BPS) | route exists; distinct claimant/respondent | case id derived from content hash | **72h dispute window (DISPUTE_WINDOW_SECONDS) — declared, NOT yet enforced in vote acceptance (INV-018, open)** | n/a | opening with insufficient bond |
| vote cast | selected annotator only (3-of-5 panel) | annotator's vote + rationale hash | case OPEN; annotator in selected panel; **annotator has not voted yet**; within dispute window (spec) | double-vote by the same annotator rejected (dispute_resolution.py:251) | votes after 72h window: spec requires rejection — py UNENFORCED (INV-018) | n/a | voting twice; voting in a resolved case; a non-panel entity voting |
| OPEN → resolved | implicit at 3-of-5 majority, full panel, or panel exhaustion | the vote set itself | ≥3 agreeing votes (GUILTY or NOT_GUILTY); a panel shorter than 5 resolves at exhaustion (every member voted) — DISMISSED on a split — so short panels cannot hang OPEN forever | terminal; resolved cases reject votes | n/a | n/a | resolving with <3 agreeing; reopening a resolved case; **slash without a GUILTY verdict** (stake-and-slash binds to RESOLVED_GUILTY — py resolution records but does not move stake; INV-018 partial) |

---

## Part II — The TRION machine (observation → verdict)

Master command §25: OBSERVE → NORMALIZE → HASH → INDEX → ANALYZE →
CONSENSUS → VERDICT.  Derived from the live pipeline:
`core/realtime/bh_streamer.py` (BHStreamer: 96 workers polling chain RPCs)
→ `compute_bh` (canonical behavioral-hash construction) → bh_ledger.db /
`FAISSAccumulator` (vector index) → Akashic/BIBL + anima analysis planes →
`core/spiritual/consensus.compute_dw_bft_consensus` (DW-BFT, Σ(t), HHI) →
oracle publication (`TRIONOracleV3.publishBTCPRoute` +
`submitRouteAttestation` on EVM; per-VM oracle equivalents).

States (7 + failure sinks):

```
OBSERVE → NORMALIZE → HASH → INDEX → ANALYZE → CONSENSUS → VERDICT(PUBLISHED)
                    ↘ (per-chain failure: fork/outage → SUSPENDED, re-observe)
```

| # | from | to | valid callers | cryptographic evidence required | preconditions | replay behavior | timeout behavior | emergency/pause | forbidden alternatives |
|---|------|----|---------------|--------------------------------|---------------|-----------------|------------------|-----------------|------------------------|
| T1 | — | OBSERVE | streamer/indexer workers (chain-agnostic, permissionless readers) | raw block + tx payloads from chain RPCs | chain integrated or OOA-observed (§5.2: unknown chains → OOA adapter, never silent EVM default) | re-fetching the same block yields the same events (idempotent) | RPC timeout → retry with backoff; chain outage → chain marked down, BIBL tier-1 state stale-flagged | indexer supervisor restart is safe (idempotent re-ingestion) | trusting a single RPC endpoint (endpoint diversity, `EndpointDiversity`); silent default-chain classification |
| T2 | OBSERVE | NORMALIZE | streamer `_process_block` | — | raw events present | deterministic per tx | n/a | n/a | normalizing magnitudes with the wrong per-chain decimals (now registry-driven) |
| T3 | NORMALIZE | HASH | `compute_bh` (bh_streamer.py:182) | the BH itself: SHA3-based Hash_DNA over (entity=sha3(bh_id), context, magnitude, chain, block, timestamps) | normalized fields valid | same tx → same BH (cross-language golden-vector parity py/rust) | n/a | n/a | **field-value divergence between writers** (py/rust parity is hash-consistent; values converged in Task 20; INV-019) |
| T4 | HASH | INDEX | ledger writer + `FAISSAccumulator.on_bh` | ledger row keyed by bh_id; faiss vector tagged with the real VM family | BH well-formed | re-inserting the same bh_id is an upsert/no-op (idempotent writers) | flush daemon batches on interval | restart reloads from ledger (no loss) | indexing a BH under a wrong chain id / VM family (labels now classified, Task 20 fix) |
| T5 | INDEX | ANALYZE | BIBL engine / akashic lookup planes (read-only consumers) | snapshot of indexed state | chain state fresh (staleness tracked) | analysis re-runs are pure functions of the index | stale chains: NL/coherence flagged; routing validity gate refuses (router `route_is_valid`) | fork detected (BIBLEngine.detect_fork) → chain suspended from routing | routing on stale or forked state (INV-020) |
| T6 | ANALYZE | CONSENSUS | validator cohort (spiritual plane) | DW-BFT computation: diversity weights d_j, HHI, Σ(t) coherence, threshold margin, safety condition | validator set registered; ≥3 distinct validators; HHI ≤ 0.5 (scale-normalized) | consensus recomputation is deterministic over the same validator inputs | degradation tracked (consensus_degradation.py) | HHI CRITICAL → safety_holds = False, emission blocked (fail-closed) | emitting with Σ(t) ≤ Θ(t) (threshold margin < 0 → proof rejected, INV-011); concentrated validator set; replaying yesterday's coherence for today's verdict (freshness, INV-005) |
| T7 | CONSENSUS | VERDICT (published) | registered validators / oracle owner via `publishBTCPRoute` + `submitRouteAttestation` | signature-verified attestation quorum: ≥ minRouteAttestations() = max(2, ⌈2/3·validatorCount⌉) DISTINCT ECDSA-recovered signers over the route-verdict hash; values immutable after first etch | route pre-registered (etch-then-attest); values consistent across batches (mismatch = dispute, revert) | duplicate attestors accepted but not re-counted; timestamp refreshed only by NEW attestors (M2 freshness) | verdict stale after 300s at consumption (escrow gate) | attestation count cannot be inflated by msg.sender authority (S3/C2 fix — msg.sender carries no authority in submitRouteAttestation) | publishing a verdict with an unverified quorum; mutating etched route values; marking a route safe without coherence ≥ threshold |
| T8 | any TRION state | SUSPENDED (chain) | BIBL fork/outage detection | fork assessment evidence | chain diverged or timed out | re-observation lifts suspension | the suspension IS the timeout response | n/a | routing through a suspended chain |

**Verdict consumption** (ties the two machines together): the escrow
release gate (M2 E3) is the only place a VERDICT becomes value movement,
and it re-checks everything independently — binding
(`anchorBH == escrowId`), safety, quorum floor, freshness (≤ 300s),
coherence ≥ threshold.  No single layer's honesty is assumed: the py
engine, the rust reference, and the contracts each re-verify.

---

## Part III — Cross-layer status of the machines (Wave 2/3 work orders)

| machine | py engine | rust reference | EVM (Solidity) | Vyper | SVM/Soroban | Move | TON | Cairo/Starknet | other VMs |
|---|---|---|---|---|---|---|---|---|---|
| M1 route | enforced (this wave: transition table + terminal freeze) | router: no persistent status machine (routes are values) | `BTCPRoute.sol` status enum | n/a | btcp_route programs | btcp_route.move | route.fc | btcp_route.cairo | cosmwasm/near/pvm ports |
| M2 escrow | enforced (states + guards; this wave: coherence floor) | `btcp_escrow_monitor.rs` (Holding/Disputed→Reverted) | `BTCPEscrow.sol` (richest: pause, cascade, pending-akashic) | `BTCP_ESCROW.vy` (two-state, permissionless, oracle-gated) | btcp_escrow (release authority key) | btcp_escrow.move (relayer-gated `coherence_verified` flag) | escrow.fc (relayer/owner op codes) | btcp_escrow.cairo | — |
| M3 BITP | py matcher: entity + (opt-in) expiry checks (this wave); **clipboard persistence is rust/Akashic domain** | `bitp_matcher.rs` (entity + expiry enforced) | — (no BITP contract; PASTE is behavioral) | — | — | — | — | — | — |
| M4 BLO | — (no py BLO engine; scheduler only) | blo_scheduler.rs | `BehavioralLimitOrder.sol` | — | — | — | — | — | — |
| M5 dispute | py resolver (3-of-5, bond, persistence) | dispute_resolution.rs | (slash path via TRIONStaking.vy / staking contracts) | — | — | — | — | — | — |

Gaps found while writing this table (all registered as work items in
`docs/security/CANONICAL_INVARIANTS.md`):

1. **Solidity escrow accepts caller-chosen `escrowId` and
   `minCoherence`** at lock time (onlyRelayer, but no floor) — Wave 2
   (Agent G) should derive/validate like the Vyper tier.
2. **Move escrow release** trusts a relayer-set `coherence_verified`
   flag — no on-chain quorum/freshness binding — Wave 2 (Agent I).
3. **SVM escrow** has a release-authority key with a bootstrap
   all-zero fallback (documented trusted-relayer assumption) — Wave 2
   (Agent H).
4. **Py dispute window (72h) is declared but unenforced** in
   `cast_vote` — fixed area documented; enforcement is a Wave 1-F code
   candidate (see invariant register).
5. **Py BITP expiry check is opt-in** (`current_time` param) to preserve
   legacy callers; the rust tier and the Akashic clipboard enforce it
   unconditionally — parity note for Agent E's certificate work.
6. **Route status machine** existed implicitly in py (any→any mutation);
   this wave's fix makes the table above executable law (transition
   validation + terminal freeze + replay no-op).
