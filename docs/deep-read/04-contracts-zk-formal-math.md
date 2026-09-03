# Deep Read: contracts/ + hardhat/ + zk-circuits/ + zk/ + formal/ + math/

**Agent:** 2-d (parallel deep-read, 9 agents) · **Repo:** /home/z/trion-core @ main · **Scope:** 119 tracked files (contracts 77, hardhat 17, zk-circuits 17, zk 1, formal 4, math 3). ~104 files read fully or in substantial part; 15 generated artifacts / lockfiles (hardhat-artifacts, build-info 654KB, package-lock.json, 3×Cargo.lock, svm program Cargo.tomls) verified for existence + size only.

---

## Overview

TRION's on-chain footprint spans 8 VM families. The **Solidity layer is the only production-quality tier**: 33 contracts with genuine security engineering (quorum ECDSA with EIP-2 s-malleability guards, two-step ownership, CEI pattern, fail-closed gates, circuit breakers, aggregate-locked-balance sweep accounting). The **hardhat suite is real and good** (517-line test, 14 behaviors incl. AWA freeze + malleable-twin rejection). The **non-EVM ports degrade progressively**: SVM (Anchor) is a faithful-but-older port with one serious footgun (locks the funder's ENTIRE wallet balance); NEAR is bookkeeping-only; Move modules are thin scaffolds with a stubbed AWA check and a caller-supplied "gate"; CosmWasm has two genuine bugs (infinite-recursion deserializer, multi-denom escrow fund duplication); Soroban is a state-machine stub with no custody. The **ZK layer is two parallel systems**: real Circom/Groth16 circuits (sound structure, no build artifacts committed) and a real Python Schnorr-Pedersen Σ-protocol over secp256k1 (genuine algebra, but policy predicates are prover-asserted flags, not proven). The **formal layer (Haskell) is 9 theorems as types + boolean self-checks, not machine-checked proofs** — and the T8 "deletion-proof" claim is refutable. The **Julia math module is real numeric code with real tests**.

Trust model across nearly all contracts: a single **owner + relayer** writes all oracle/registry state; "TRION consensus" happens off-chain and is only *recorded* on-chain. Quorum-signature verification exists only in TRIONExecutionGate, AkashicProof, and TRIONOracleV3's legacy `publishSignal`.

---

## Per-directory findings

### contracts/solidity/ (33 files — all read)

- **TRIONSensingOracle.sol** (185 ln, CC0) — Relayer-published behavioral coherence signals per `entityId`; `BehavioralTruth`/`SilenceSignal` events; batch publish ≤50; `isCoherent()` enforces `FRESHNESS_BLOCKS = 300` freshness; owner can add/remove relayers, 1-step `transferOwnership`. Quality: clean, well-bounded inputs (score/threshold ≤ 1e6, plane ≤4). Issues: no quorum (single relayer decides truth); freshness is 300 *blocks* here vs 300 *seconds* in TRIONOracleV3 — inconsistent freshness units across the oracle family; ownership transfer is single-step (no accept step) unlike ExecutionGate.
- **ConfidentialCoherenceVault.sol** (138 ln, MIT, OZ) — ERC-20 vault gated on TRION coherence for BOTH wrap and unwrap. **Coherence-gate binding fix is present and correct**: `registeredBEO`/`beoOwner` enforce a 1:1 immutable address↔BEO binding, and `coherenceWrap/Unwrap` require `entityId == registeredBEO[msg.sender]` *and* `isCoherent(own)` — closing the "pass someone else's coherent entityId" bypass. Custom errors, SafeERC20, owner-settable oracle (swap risk: owner can point `trionOracle` at a fake always-coherent oracle — centralization vector). Residual issue: `registerBEO` has no proof of BEO ownership — anyone can squat any *unclaimed* coherent entityId before its true owner registers (identity front-running; no fund theft since funds are the caller's own).
- **TRIONExecutionGate.sol** (689 ln — the flagship, deployed on 0G) — Validator quorum ECDSA over EIP-191 `keccak(chainid‖this‖entityId‖packedData)`; distinct-signer dedup (O(n²)); EIP-2 high-s rejection + zero-address recovery check in `_recoverSigner` (lines 663–688); fail-closed `checkExecution` (uninitialized → BLOCKED); **AUDIT-3 G3 AWA enforcement** (quorum ≥ ⌈2/3·validatorCount⌉, HHI <4000, gratitude ≥1, publicGoodBps ≥1500) gates `publishSignal`, `confirmStorageSync`, and blocks ALL execution when frozen; two-step ownership with auto-validator enrollment; `pruneDecisions` (≤500/call) for the unbounded `decisions` mapping; custom nonReentrant + pause. Issues: (a) `updateAWAState` is `onlyValidator` — **a single validator can un-freeze AWA by submitting healthy values**, contradicting the WP2 §17 "cannot be overridden by any single entity" comment (line 33–37 vs 289–299); (b) `nonReentrant` on `checkExecution` is decorative (no external calls) — the test itself admits this and fakes it via `hardhat_setStorageAt`; (c) `addValidator` raises `validatorCount`, which can silently push `quorumRequired` below the 2/3 floor → AWA frozen (fail-closed DoS, not exploitable); (d) `packedData` bits [104–231] (block/timestamp) documented but never validated.
- **BTCPEscrow.sol** (498 ln) — Two-state escrow, 6 states, 7 revert reasons, PENDING_AKASHIC 24h, 7-day emergency escape callable by anyone, cascade revert for multi-hop parents, two-phase settlement check (G1), CEI everywhere (state cleared + `_lockedBalance -= amount` BEFORE `.call{value}`), custom ReentrancyGuard, pause blocks ingress only. **`sweepETH` fix verified correct**: `sweepableExcess()`/`sweepETH()` sweep only `balance − _lockedBalance`, owner can never drain HOLDING/PENDING funds; every path that decrements `_lockedBalance` atomically transfers the same value, so the invariant holds (subtraction underflow impossible in practice; checked-arithmetic would panic cleanly if broken). Issues: `releaseFromPendingAkashic` measures the 24h window from **lockTimestamp**, not from entering PENDING_AKASHIC (so an escrow pending at hour 23 gets a 1h window, not 24h — semantic bug); 7-arg `lockEscrow` duplicates `_lockEscrowInternal` instead of delegating; `require(msg.sender != address(0))` is dead code; unbounded `escrowList`.
- **BTCPIntent.sol** (145 ln) — Intent registry; relayer-only; status FSM (PENDING→ROUTING→EXECUTING→COMPLETED/FAILED/EXPIRED, FAILED→RESURRECTED) correctly mirrored in Rust; zero-address relayer check. No user signatures — the relayer registers intents on users' behalf (trust model).
- **BTCCPRoute.sol** → **BTCPRoute.sol** (121 ln) — anchorBH→executionBH linkage, finalize with ≤1e6 score bounds. Registry-only; all relayer-trusted.
- **BehavioralLimitOrder.sol** (168 ln) — BLO order book: post/fill/expire, pair-hash index, `findComplements` two-pass filter (view-only). `fillOrder` takes `fillerEntityId` as a *parameter* (relayer-supplied, unauthenticated). Orders never remove from `openOrders`/`ordersByPair` (unbounded arrays; findComplements scans all history).
- **LiquidityOcean.sol** (132 ln) — per-chain NL/TVL registry, weighted ocean score, `getBestChain`. `_recomputeOcean` iterates ALL chains per update (gas grows unboundedly); `nlScore*weight` can overflow only above 1e12 (inputs bounded ≤1e6, so safe).
- **GenesisCommitment.sol** (124 ln) — sponsor bonds, 5-layer Sybil config; **`sponsorAkashicDepth` and `behavioralUniqueness` are relayer-supplied calldata** — the anti-Sybil layer is trust-based, not verified on-chain. `releaseBond` pays `c.committer` (relayer) — consistent since relayer fronted the bond.
- **TravelRuleCompliance.sol** (145 ln) — FATF storage of commitment hashes + tiers; **proofs are never verified on-chain** ("relayer performs off-chain Schnorr-Pedersen verification and marks it verified") — the docstring's "ZK Travel Rule" is really "relayer says it's compliant". `hasValidProof` O(proofList) scan ignoring `jurisdictionHash`; threshold map present but unused in the check.
- **BTCPVersionRegistry.sol** (122 ln) — semver registry, single active version, feature flags. `_activateVersion` re-activating a previously-deactivated version is allowed (activatedAt != 0 && active == false passes) — re-activation rewrites `activatedAt`, minor accounting quirk. `isCompatible` ignores minor/patch (per spec).
- **BTCFiGuard.sol** (124 ln) — risk-tier classifier (SAFE/CAUTION/HIGH_RISK/HOSTILE) reading `ITRIONScoreReader`; `updateCount == 0 → HIGH_RISK` (fail-closed). Pure logic, clean.
- **BEOAttestation.sol** (131 ln) — 1:1 wallet↔BEO attestation with tiers; attester-revocable; `revoke` deletes the reverse map but leaves the forward record resolvable (identity remains, active=false). Clean.
- **TRIONFirewall.sol** (126 ln, CC0) — 3-check `gate()` (NL ≥0.30, MF ≤0.70, route verified) + `simulate` view. Honest about being a read-gate; `protectedProtocol` immutable but never enforced (anyone may call gate).
- **TRIONLiquidityGuard.sol** (86 ln) — NL gate with 1h freshness; `checkNL` is non-view (emits event) though named like a view. `setOracle` has no zero-check (only owner-gated).
- **TRIONOracle.sol** (V1, 231 ln) — BIRP signals; **`quorumCount` is a relayer-supplied parameter** (self-reported quorum, not proven); `block.timestamp - signalTimestamp` can underflow-panic if a future timestamp is submitted. MF filter rejects ≥0.70 by early return (silently drops, no revert).
- **TRIONOracleV3.sol** (289 ln) — Inlined ECDSA/MessageHashUtils/Ownable (EIP-2 compliant); `publishBTCPRoute` (owner-or-validator, **no quorum** — a single validator can mark any route safe, weaker than ExecutionGate); rich `publishBehavioralSignal` with 5-plane packing; legacy `publishSignal` requires **sorted** distinct validator signatures (elegant dedup); `verifyExecution`: routes checked first with **300-second freshness (`BTCP_ROUTE_FRESHNESS_SECONDS = 300`) — the verdict-expiry fix is present** ("previously routes never expired"); legacy fallback requires status==1 ∧ <300s ∧ <50 blocks. Default `quorumRequired = 2` with only 1 validator at deploy → legacy path unusable until a second validator is added (harmless bootstrap quirk). Note `publishSignal` has no per-entity replay protection beyond txId uniqueness.
- **TRIONGuardV3.sol** (116 ln) — `onlyWhenCoherent(txId)` modifier reading ITRIONGuardOracle; **24h bypass verified present**: `BYPASS_MAX_WINDOW = 24 hours`, lazy auto-expiry inside the modifier, 1h cool-down after expiry, all bypass use event-logged. Weaknesses: (a) the "cannot keep the firewall disabled indefinitely" claim is weak — the 1h cool-down means the owner can keep the gate OFF ~24h/25h (≈96% of time); (b) expiry is lazy — the flag stays `true` until the next gated call; (c) `coherence == 0` is treated as Silence-block (good).
- **TRIONPriceFeed.sol** (332 ln) — Chainlink AggregatorV3 drop-in; forward/inverse pairs (`INVERSE_PRECISION = 1e16`, inverse CI bounds correctly swapped lo/hi); behavioral metadata (coherence, MF, CI, manipulated flag); staleness config. Solid design; single-relayer price source (the "37-network consensus" is off-chain trust); no round-history cap enforcement despite `MAX_ROUND_HISTORY = 100` constant (unbounded `_rounds` mapping).
- **TRIONProtectedVault.sol** (32 ln) — demo vault whose "attack vector" functions are mock balance mutations gated by `onlyWhenCoherent`. Demo-only by design.
- **AkashicProof.sol** (549 ln) — 0G storage/DA commitments; **AUDIT-4 Gap 15**: `submitMerkleRoot` with 2/3 validator quorum + nonce replay protection + same EIP-2 hardened `_recoverSigner`; legacy `onlyDeployer` write paths retained but deprecated (the "decentralization" is optional — DEPLOYER can still write everything directly). Unbounded snapshots/daCommitments/syncHistory arrays; O(n²) signature dedup.
- **AttackSimulator.sol** (150 ln) — records "would have blocked" proofs by reading live oracle signals; anyone can call `recordAttackProof` (event-only, honest); `demoAttackBlock` reverts on SILENCE. Marketing/demo tool; the "immutable proof" is just an event referencing a relayer-published signal.
- **ContinuumDEX.sol** (380 ln) — BID/CME/PMO/BDC engines. **Registry-only DEX**: no token custody, no AMM, no perps; `settlePMO` sets flags and emits events (CCP "distribution" is bookkeeping — `totalCCPDistributed +=` with no transfers); `confirmPMO` is relayer-only despite "each party must confirm independently" docstring; `updateBDCCredit` computes a formula but nothing consumes it. The "Hyperliquid-style perpetual + spot DEX" claim in the header is aspirational.
- **SanctionsOracle.sol** (288 ln) — AWA-protected sanctions flags; association cascade; appeal flow via Conscious Layer multisig; owner can't clear flags (only appeal path). Issue: `reviewAppeal(rejected)` restores `SANCTIONS_FLAG` even if the original was `SANCTIONS_ASSOCIATION` (admitted in comment); `submitAppeal` is permissionless and flips the entity to APPEAL_PENDING, which **is not sanctioned** per `isSanctioned()` — an entity can pause its own sanctions flag for the appeal duration (DoS-ish loophole worth noting).
- **BTCPGasAbstraction.sol** (185 ln) — quotes/deposits/cover/refund with overwrite guards, payer-only refund, refund-only-after-expiry, `_activeDepositsEth` ledger for safe fee sweep. Issues: (a) **overpayment loss** — `depositGas` accepts `msg.value > required`; after `coverGas`, the excess (`d.amount − tokenAmount`) is swept by the owner as "fees" (payer never gets it back); (b) `IERC20Minimal.transferFrom` return value ignored (no SafeERC20; USDT-style false-return tokens would silently fail); (c) `sweepFees` covers ETH only — ERC-20 fee remainders are stranded.
- **HashDNA.sol** (226 ln, library) — formal Hash_DNA spec: domain separator, currency IDs, 18-dec normalization (truncation for >18), context-hash constructors, 14-field packed hash with event-type range check. Well-specified; **library never imported by any contract in the repo and not in the hardhat compile set** — and it uses `event` as a parameter/variable name (a Solidity keyword), which is a compile-risk worth verifying; nothing in-repo compiles it.
- **MockOracle.sol / MockTRIONToken.sol** — test stubs; MockTRIONToken mint is permissionless (testnet-only, documented).
- **interfaces/** — ITRIONOracleV3 (174 ln, full packed-layout doc, viaIR rationale), ITRIONOracle (6 ln), ITRIONSensingOracle (35 ln), ITRIONAggregatorV3 (39 ln). Consistent with implementations.
- **test/ReentrantAttacker.sol** — attack harness; its `receive()` path can never trigger (gate sends no ETH) — acknowledged in the hardhat test comments.

### contracts/svm/ (14 files — Anchor 0.29, Solana)

- **btcp_common/src/lib.rs** (343 ln) — shared types (BEOIdentity, AssetId), enums mirrored from Solidity (RevertReason 4 values, EscrowState 3 values — i.e. the **pre-Phase-1.1 feature set**), full BTCPError catalogue, PDA seeds. High-quality shared crate.
- **btcp_escrow/src/lib.rs** (512 ln) — PDA escrow + vault PDA; release checks state/expiry/coherence; revert with anyone-on-timeout; set_relayer owner-only. **Serious footgun: `lock_escrow` takes NO amount parameter — `amount = ctx.accounts.vault_funder.lamports()` and transfers the funder's ENTIRE wallet balance into the vault** (line 136). Also lacks settlementCheckHash/PENDING_AKASHIC/emergency/cascade (parity gap vs Solidity); `escrow.amount` not zeroed on release (state guard suffices); bumps recomputed via `find_program_address` (wasteful but correct).
- **btcp_intent/src/lib.rs** (301 ln) — faithful port incl. FSM `can_transition_to` identical to Solidity; PDA per intent_hash; `init` guard via PDA uniqueness.
- **btcp_route/src/lib.rs** (299 ln) — faithful port of publish/finalize.
- **Anchor.toml vs declare_id! mismatch**: Anchor.toml uses placeholder IDs `BTCP1111…/BTCP2222…/BTCP3333…` while lib.rs declares `54r6RE…/EgPA8…/9B9Mb8…` — `anchor build` verification would fail as configured. `tests/` referenced by the INTEGRATION_GUIDE does not exist. `initialize_programs.ts` (184 ln) uses a hand-rolled minimal IDL and the deprecated `@project-serum/anchor` package. deploy.sh (215 ln) is a reasonable bash deployer.
- Cargo profile: `overflow-checks = true`, `opt-level = "z"`, `panic = "abort"` — good release hygiene.

### contracts/near/ (8 files)

- **trion_oracle.rs** (150 ln) — signals + routes; `verify_execution` has **no freshness/expiry check** (unlike Solidity's 300s) — a stale "safe" route is safe forever on NEAR. Single-relayer admin; `set_relayer` by relayer itself (no owner split).
- **trion_execution_gate.rs** (112 ln) — gate stats per gate_id; **`check_execution(gate_id, entity_id, phi, route_threshold)` takes phi as a caller-supplied parameter** — the "behavioral firewall" trusts the caller's claimed phi (same weakness as Move/CosmWasm ports). Owner can toggle `awa_enforced` off (inverts the fail-closed philosophy: AWA=false blocks everything here, so toggling off = full DoS rather than bypass).
- **btcp_route.rs** (133 ln) — faithful registry port.
- **trion_token.rs** (154 ln) — NEP-141 subset: **missing `ft_transfer_call`, storage-deposit semantics, `ft_metadata` shape, and any registration flow**; `governance_mint` always panics ("0% inflation") while `new()` mints nothing — **the 1B total supply is unreachable** (no distribution path exists). 7-type SlashCondition enum; slash splits 50/50 insurance/burn correctly.
- **trion_staking.rs** (120 ln) — **bookkeeping only**: `stake()` claims ft_transfer_call approval but never pulls tokens (the token doesn't even implement ft_transfer_call); `unstake` decrements a number and returns nothing; `pending_rewards` exists but there is **no claim function**. Coverage-tier multipliers as documented.
- Cargo.toml/lock present (near-sdk; generated lock verified only).

### contracts/move/ (6 files — Aptos; Sui claimed but Aptos-framework only)

- **btcp_escrow.move** (237 ln) — most complete Move module: HOLDING/PENDING_AKASHIC/RELEASED/REVERTED/EMERGENCY_REVERTED, escrow-under-locker-account (one escrow per account), Coin<T> held in resource, 7-day emergency callable by anyone, relayer authority resource. Issues: **release_escrow never checks timeout** (expired escrow still releasable — divergence from Solidity); `TrionToken` is a phantom placeholder struct — `coin::deposit<TrionToken>` requires a real registered coin type + CoinStore, so this cannot run as-is; no settlementCheckHash analog; per-account resource model means one escrow per address.
- **trion_oracle.move** (115 ln) — **`publish_signal` stores the Signal under the ADMIN's address, overwriting the single global signal each time; `get_signal(entity_addr)` reads per-entity storage that is never written** — publish/read storage models disagree (functional bug). `awa_enforced()` is a **hard-coded `return true` stub** (lines 100–104, "Simplified"). block_number/timestamp always 0.
- **btcp_intent.move / btcp_route.move** (48/53 ln) — minimal per-account resources; no auth, no FSM, no finalize semantics beyond a boolean. Scaffolds.
- **trion_execution_gate.move** (38 ln) — **`check_execution(entity_coherence, entity_threshold)` takes both values as parameters** — the caller grades their own homework; `paused`/thresholds stored but never consulted by check_execution.

### contracts/cosmwasm/ (5 files)

- **state.rs** (130 ln) — clean struct/key layout; denom capture fix documented ("was hardcoded uatom").
- **contract.rs** (799 ln) — combined oracle+escrow+intent+route+gate. **BUG 1 (fatal): `from_json_bytes` is infinitely recursive** — `fn from_json_bytes<T>(b) { from_json_bytes(b).map_err(...) }` calls itself instead of `serde_json::from_slice` (lines 21–23); every state read (release/revert/finalize/status-update/get-*) would stack-overflow at runtime — the contract cannot function as written. **BUG 2 (fund duplication): multi-denom escrow** — locking 100uatom+50ujuno stores `denom="uatom+ujuno"`, `amount=150`; release/revert then send **150 of EACH denom** (`Coin{denom: d, amount: esc.amount}` per split part) — 2× value out. Single-denom path is correct. Also: `verify_execution` query returns the raw route with **no freshness check**; `check_execution` takes phi as a parameter (trust-the-caller); `SetAwaEnforced` is a plain owner toggle (AWA is just a bool, unlike the 4-condition Solidity version); `execute_publish_btcp_route` stores routes under the *signals* prefix (namespacing collision by design, documented).
- lib.rs re-exports; Cargo.toml has serde_json + serde-json-wasm both (only serde_json used).

### contracts/soroban/ (2 files)

- **lib.rs** (239 ln) — admin + relayer list (idempotent add/remove), signals Map, escrow Map keyed by route_id. **`release_escrow` has NO coherence check and NO timeout — only relayer permission + HOLDING state**; no token custody (amount is an i128 bookkeeping number); `register_intent` keys the map by **entity_id, not intent_hash** (one intent per entity, silently overwrites); instance() storage (not persistent, size-capped). Honest header comment admits the "trusted-relayer pattern" but the escrow is not an escrow.

### contracts/vyper/ (2 files)

- **TRIONToken.vy** (311 ln) — fixed supply minted once in constructor; `governance_mint` always reverts (Gap 1, 0% inflation); slash 50/50 insurance/burn with correct supply accounting; permissionless burn; governance-gated admin updates; epoch views return 0 for dashboards. Solid, self-consistent. Minor: no infinite-allowance convention (approve max still decrements).
- **TRIONStaking.vy** (530 ln) — 7-type slash schedule, 72h dispute window, coverage tiers (1×/2.5×/5×/10× min stake), HHI tiers, geographic caps. **Economics are bookkeeping-only**: `register_validator` never transfers tokens ("In production: transferFrom" comment); `slash_validator` records a Dispute but never calls `TRIONToken.slash_validator` (no cross-contract call anywhere); `distribute_reward` computes a reward number and logs — **no tokens ever move**; bond forfeit never enforced. `_update_hhi` doesn't compute HHI (oracle-submitted value only).

### contracts/test/ + script/ + foundry.toml

- **Reentrancy.t.sol, Quorum.t.sol, Pause.t.sol — 3 EMPTY stub files** (pragma + comment only, "See hardhat/test/…"). **ExecutionGate.t.sol** (29 ln) is a near-stub: imports `"solidity/TRIONExecutionGate.sol"` (no remapping declared in foundry.toml) and uses `assertEq` **without importing forge-std** — the Foundry suite almost certainly does not compile as configured. `testFail` prefix is deprecated in modern forge.
- **script/Deploy.s.sol** — **entire body commented out**; a deployment-shaped placeholder.
- foundry.toml — solc 0.8.24, cancun, via_ir, optimizer 200 — sane; no remappings, no lib/ directory present.

### hardhat/ (17 files)

- **hardhat.config.ts** (324 ln) — **genuinely good key-management policy**: mainnet chain-ID set + `--network` target detection → hard FAIL if falling back to the public Hardhat #0 dev key on any mainnet; testnets warn; 14 networks incl. 0G mainnet (16661) with dedicated `DEPLOY_0G_PRIVATE`; custom Etherscan chains. Solidity 0.8.28/viaIR.
- **contracts/** — byte-identical copies of TRIONExecutionGate.sol and test/ReentrantAttacker.sol (verified by diff).
- **test/TRIONExecutionGate.test.ts** (517 ln) — the repo's best test artifact: 11 describe blocks / ~30 its covering fail-closed, quorum (2-of-2, duplicate-sig rejection, non-validator rejection), status gating, nonReentrant (via storage-slot surgery + honest commentary), pause, pruneDecisions (incl. 501-batch limit), two-step ownership, stats, **AWA freeze for all 3 condition bits + restore**, **EIP-2 malleable-twin rejection (crafted s' = n−s, v-flip)**, validator-set edge cases. Minor: the "removeValidator refuses owner/last" case asserts the same revert twice (never exercises the last-validator branch); imports typechain-types dir not present until compile.
- **scripts/deploy_oracle_v3.js** (99 ln) — deploys `TRIONOracleV3` and writes a proof-ledger JSON. **Bug: `TRIONOracleV3` is not in hardhat/contracts (only ExecutionGate + ReentrantAttacker), and no artifact exists → `getContractFactory("TRIONOracleV3")` fails in this self-contained setup.** Same for **deploy_price_feed.js** (`TRIONPriceFeed` artifact absent).
- **Artifacts (generated, verified only)**: build-info/c119….json 654KB; TRIONExecutionGate.json 65,626 B; ReentrantAttacker.json 2,976 B; IExecutionGate.json 864 B; dbg files 105 B each; solidity-files-cache.json 80 ln. package.json (hardhat 2.22, toolbox 5, ethers 6.13, typechain); tsconfig strict.

### zk-circuits/ (17 files — 5 circuits)

All five circuits are **real, structurally sound Circom 2.1.6 Groth16 circuits** using circomlib Poseidon/IsEqual/LessThan/Num2Bits — NOT scaffolds in the syntax sense; but no build outputs, zkeys, proofs, or verifier.sol are committed, so all "compiled/proven" claims are unverifiable from the repo.

- **zk_intent_commitment/circuit.circom** (65 ln, 642 constraints claimed) — proves knowledge of intent_fields+nonce+entity_id s.t. `intent_hash = Poseidon(fields‖nonce‖entity)` and `commitment = Poseidon(intent_hash‖nonce)`. Correct double-binding for the commit→reveal flow.
- **zk_complementarity_proof/circuit.circom** (130 ln, ~1,126 constraints claimed) — two Poseidon bindings + `IsEqual` on asset cross-matching + `|magA−magB| ≤ tol` via dual `LessThan(magBits+1)` with `+1` for ≤. Range analysis is correct (all inputs Num2Bits(magBits=64), so operands < 2^65 exactly fits LessThan(65)). Chain complementarity explicitly left optional (documented). README honestly labels itself "the recommended v1 Poseidon scaffold" vs the spec's 50k-constraint Hash_DNA variant.
- **zk_iap_share_proof/circuit.circom** (84 ln) — sum check `total = value_i + Σ others`, exact share identity `gas_i·total == gas_total·value_i`, and Num2Bits range checks sized to avoid BN254 overflow (valBits 96, gasBits 96, total valBits+8). Mathematically careful (the divisibility caveat is documented).
- **zk_travel_rule/circuit.circom** (72 ln) — Poseidon binding of 6 IVMS101 fields + nonce; `disclosure_submitted === 1`. **Soundness caveat: "submitted" is a public input pinned to 1 — it proves nothing about any real off-chain submission event; the comment admits it's a self-attestation.** Amount consistency with field[2] is real.
- **zk_behavioral_credential/circuit.circom** (96 ln) — triple Poseidon binding (behavioral_hash ← pattern‖entity‖epoch; pattern_commitment; credential) + 32-bit range checks on 1e6-scaled scores. The "coherence with BEO pattern" claim is really "the three public hashes are linked to the same private pattern" — no threshold logic inside the circuit.
- **Top README** claims: all 5 witness-validated; `zk_intent_commitment` proven+verified end-to-end with Groth16; soundness spot-check for complementarity. **None of this is reproducible from the committed tree** (no build/, no pot, no zkey, no proof.json). Status honestly lists unchecked boxes: production MPC ceremony, on-chain verifier deployments, recursive aggregation.
- package.json scripts are correct circom/snarkjs invocations (pot 2^14, per-circuit phase 2, verifier export loop). input.example.json for all five contain plausible field-element values with real-looking Poseidon digests (precomputed, cannot re-verify without circomlib).

### zk/__init__.py (1 file, 1,411 ln — Python ZK system v2.0.0)

- **Genuinely real cryptography**: secp256k1 via `ecdsa`; deterministic secondary generator H ≠ G; real Pedersen commitments `C = vG + rH` (value hashed to scalar via SHA3-256 mod n); **real Schnorr-Pedersen Σ-protocol** (R = aG+bH, Fiat-Shamir e = SHA3(transcript‖R‖C), z_v = a+ev, z_r = b+er; verifier checks z_vG+z_rH == R+eC and recomputes e); point compression/decompression with on-curve validation; binary SHA3 Merkle tree + proofs; Merkle-sum for IAP.
- Five circuits mirror the Circom set with multi-commitment PoK proofs sharing one transcript (domain-tagged `INTENT_COMMITMENT:v2`, etc.). Backwards-compatible ZKProof dataclass + new dict API (`prove_*`/`verify_*`), stored-proof registry.
- **Claims-vs-reality gaps**: (1) All policy predicates — `amount_range_proof.positive`, `passes_coherence/passes_manipulation/passes_depth`, `originator_verified/beneficiary_verified`, `compliant`, IAP `fair` — are **prover-computed booleans shipped in proof_data/public_inputs and merely read back by the verifier**; nothing forces a dishonest prover to set them truthfully (they're outside the Σ-protocol statement). The system proves *knowledge of committed preimages*, not the claimed compliance policies. (2) The intent proof's `nonce` is included **in plaintext** in proof_data (witness leak into the "proof" object — undermines the privacy story if proofs are shared). (3) IAP Merkle-sum leaves are built from **pseudo-shares** (`total_fee / num_participants`), not real participant values — decorative. (4) Verifier freshness checks compare against `proof.timestamp`, which is prover-supplied. (5) Docstring calls it "Groth16-style proof simulation" — honest, but downstream consumers may read "real Groth16".

### formal/ (4 files — Haskell)

- **src/TRION/Theorems.hs** (423 ln) — **9 theorems T1–T9 present as claimed**. Real content: smart constructors (mkCoherence range), Θ(t) linear-in-V computation with clamping, MF-adjusted Φ, PC-limit cap, HHI guard, phantom-typed SignalKind GADTs (T2 SILENCE≠VALUATION is a genuinely nice type-level separation), Nat-indexed BHLedger GADT with `bhAppend` as the only grower, SHA3-collision-resistance-as-axiom witness type.
- **Critical assessment**: these are **type-shaped modeling + boolean self-check functions on example values, not machine-checked proofs** — no proof assistant (no LiquidHaskell refinement types, no Agda/Coq/Lean); `main` just `print`s boolean results. The header's "when this module compiles… the invariants are proven by the type system" is overclaimed. Specifically: **T8's "no such function exists" deletion claim is false** — `dropAll :: BHLedger n -> BHLedger 'Zero; dropAll _ = BHEmpty` typechecks fine (phantom types prevent shrinking a *lineage*, not returning a different empty ledger). T9's `mkBHSense` doesn't hash at all (`p ++ "\x00"`) — the "collision surface equals SHA3-256" claim is carried entirely by the uninhabited-by-construction `SHA3256CR` witness (honestly labeled an axiom, and the docstring concedes compiling proves only structural properties). T1 "CoherenceConvergence" is just a range check; T3/T5/T7 are one-example unit tests.
- **app/Main.hs** — thin wrapper (audit fix: Theorems.hs originally misdeclared as main-is). **test/Spec.hs** (139 ln) — real hspec suite over exported constructors/proofs (audit fix TEST-2: was a stub); still example-based, not property-based. package.yaml — base-only library + trion-verify exe + hspec test.

### math/ (3 files — Julia)

- **src/TRIONMath.jl** (316 ln) — real implementations: Shannon entropy (freq + probs methods), magnitude log10 normalization, Φ weighted score, **5-profile five-plane coherence with sum-to-1 assert + clamp**, exponential convergence bound → H_irr, scale-invariance check (×10 renormalization equivalence), 95%±2% CI calibration, multiplicative moat, bootstrap decay e^(−λD), "Kolmogorov" bound (actually log2-products — not Kolmogorov complexity, just a growth bound), entropy budget. Standalone verification block prints 10 [PASS] lines.
- **test/runtests.jl** (148 ln) — real Test.jl suite (audit fix TEST-1: was `1+1==2` placeholder) covering every function incl. degenerate inputs, monotonicity, and error cases. Project.toml — Statistics/LinearAlgebra only, plausible UUID.

---

## Security patterns inventory

| Pattern | Where present | Notes |
|---|---|---|
| Quorum ECDSA (EIP-191, distinct-signer, EIP-2 low-s, zero-recovery check) | TRIONExecutionGate, AkashicProof, TRIONOracleV3 (legacy path, sorted-sig dedup) | Best-in-repo; O(n²) dedup; V3's `publishBTCPRoute` **skips quorum** |
| Fail-closed defaults | ExecutionGate (uninit blocked, AWA-frozen blocked), TRIONSensingOracle.isCoherent, TRIONOracleV3.verifyExecution, BTCFiGuard (updateCount=0→HIGH_RISK), Soroban is_execution_safe | Consistent on EVM; absent on CosmWasm/Soroban release paths |
| CEI + custom nonReentrant | BTCPEscrow (all payout fns), ExecutionGate, BTCPGasAbstraction (partial — no modifier but state-before-call) | Correct ordering verified line-by-line |
| Circuit breakers (pause) | ExecutionGate (full), BTCPEscrow (ingress-only by design) | Sensible |
| Two-step ownership | ExecutionGate only | Others use 1-step transferOwnership |
| Aggregate-locked-balance sweep accounting | BTCPEscrow (`_lockedBalance`), BTCPGasAbstraction (`_activeDepositsEth`) | The "sweepETH fix" and its analog both sound |
| Timelocked escape hatches | BTCPEscrow 7-day anyone-revert, refund-after-quote-expiry in GasAbstraction | Good liveness design |
| Freshness windows | SensingOracle 300 blocks; OracleV3 300 s + 50 blocks; LiquidityGuard 3600 s; TRIONOracle 3600 s; PriceFeed staleness config | **Units inconsistent** (blocks vs seconds); missing entirely on NEAR/CosmWasm/Soroban |
| Bypass controls | TRIONGuardV3 24h bypass + 1h cooldown + event logging | Re-armable ~daily → weak |
| Zero-address checks | Systematic "PHASE-1-SECURITY" comments across EVM | Occasionally dead code (`msg.sender != 0`) |
| DoS guards | Batch caps (50 signals, 500 prunes, ≤1e6 bounds) | Unbounded arrays persist in registries/decisions/escrowList |

---

## Code quality assessment

- **Solidity (7/10):** idiomatic 0.8.20/24, thorough NatSpec, custom errors in newer files, consistent ×1e6 fixed-point conventions, real audit-fix archaeology in comments (G3/G1/Gap 8/Gap 15). Downsides: dead code, duplicated lockEscrow path, unbounded growth everywhere, some registry contracts are events+structs with no enforcement (ContinuumDEX, AttackSimulator), HashDNA library orphaned/uncompiled.
- **Hardhat (8/10):** excellent key policy + a genuinely rigorous 517-line test (incl. EIP-2 twin forgery). Deploy scripts broken against the self-contained contract set.
- **SVM (6/10):** clean Anchor idioms, shared common crate, checked arithmetic — undermined by the whole-wallet-balance lock footgun, program-ID mismatch, missing tests, deprecated @project-serum/anchor.
- **NEAR (4/10):** compiles-plausible, but staking/token economics are bookkeeping; NEP-141 incomplete; oracle lacks freshness.
- **Move (3/10):** escrow module nearly real (minus coin registration + timeout check); oracle has a publish/read storage mismatch + stub AWA; gate is caller-supplied.
- **CosmWasm (2/10):** would not run (recursive deserializer) and can duplicate funds (multi-denom) — the two most severe bugs found in this read.
- **Soroban (2/10):** state stub, no custody, no checks.
- **Vyper (6/10):** well-structured economics scaffolding; no value movement anywhere.
- **zk-circuits (7/10 as code, 4/10 as evidence):** circuits themselves are careful and correct; zero committed artifacts to substantiate compile/prove claims.
- **zk Python (7/10):** real algebra, honest docstrings about "simulation"; policy predicates outside the proof statement is the core weakness.
- **formal (3/10 as proofs, 6/10 as Haskell):** nice GADT modeling; "machine-checkable proof" claim overstated; T8 refutable; T9 hash-free.
- **math (7/10):** real, tested, self-verifying; naming overclaims (Kolmogorov).

---

## Bugs / issues / vulnerabilities (file:line)

**Critical / high:**
1. `contracts/cosmwasm/src/contract.rs:21-23` — `from_json_bytes` infinite self-recursion → stack overflow on every state deserialization (release, revert, finalize, status update, all queries). Contract is non-functional as committed.
2. `contracts/cosmwasm/src/contract.rs:432-436 & 470-474` — multi-denom escrow payout duplication: sends `esc.amount` of *each* denom in the joined string (lock 100uatom+50ujuno → release 150uatom **and** 150ujuno). Value inflation.
3. `contracts/svm/programs/btcp_escrow/src/lib.rs:136` — `lock_escrow` locks the vault_funder's **entire lamport balance** (no amount parameter).
4. `contracts/move/sources/trion_oracle.move:61-82 vs 86-90` — publish stores one global Signal under the admin's address (overwritten each publish) while get_signal reads per-entity storage that is never populated → oracle returns E_SIGNAL_NOT_FOUND for every entity except admin.

**Medium:**
5. `contracts/solidity/BTCPGasAbstraction.sol:84,113-115,157` — depositor overpayment above `required` is forfeited to owner sweep after coverGas; no refund of remainder.
6. `contracts/solidity/BTCPGasAbstraction.sol:99,121,142` — `IERC20Minimal` transfer/transferFrom return values ignored (silent failure on bool-returning tokens); no SafeERC20.
7. `contracts/solidity/BTCPEscrow.sol:312` — PENDING_AKASHIC 24h window measured from `lockTimestamp` instead of the pending transition, shrinking the recovery window.
8. `contracts/solidity/TRIONOracleV3.sol:90-110` — `publishBTCPRoute` requires only owner/validator (no quorum): one validator can publish isSafe=true for any route — weaker than the escrow's consensus story.
9. `contracts/solidity/TRIONOracle.sol:128-142` — quorum is a relayer-supplied parameter (`quorumCount`); line 146 subtraction underflows (panic) on future-dated `signalTimestamp`.
10. `contracts/move/sources/btcp_escrow.move:120-138` — `release_escrow` has no timeout check (expired escrows releasable); also `TrionToken` phantom coin type makes the module non-deployable as-is.
11. `contracts/near/src/trion_oracle.rs:123-128` — `verify_execution` never expires routes (stale-safe forever), diverging from the 300s EVM fix.
12. `contracts/soroban/src/lib.rs:182-193` — `release_escrow` has neither coherence nor timeout checks; `register_intent` (210-229) keys by entity_id (overwrites prior intents).
13. `hardhat/scripts/deploy_oracle_v3.js:53` & `deploy_price_feed.js` — getContractFactory for contracts absent from the hardhat compile set (no TRIONOracleV3/TRIONPriceFeed artifacts) → scripts fail.
14. `contracts/svm/Anchor.toml` vs `declare_id!` in each program — program-ID mismatch breaks `anchor build`.
15. `contracts/solidity/TRIONGuardV3.sol:96-111` — 24h bypass re-armable after only 1h cooldown → firewall can be off ~96% of time by a persistent owner.

**Low / quality:**
16. `contracts/solidity/SanctionsOracle.sol:219-239` — `submitAppeal` (permissionless) flips flag to APPEAL_PENDING which `isSanctioned()` treats as NOT sanctioned for the appeal duration; `reviewAppeal` rejection restores SANCTIONS_FLAG even when the original was ASSOCIATION (line 259).
17. `contracts/solidity/TRIONExecutionGate.sol:289-299` — `updateAWAState` is single-validator callable, contradicting the "no single entity can override" freeze claim in the same file's header.
18. `contracts/solidity/BehavioralLimitOrder.sol:26-31,93-97` — unbounded `openOrders`/`ordersByPair` with no removal; `fillerEntityId` unauthenticated.
19. `contracts/solidity/TravelRuleCompliance.sol:98-111` — O(n) `hasValidProof` scan; jurisdiction thresholds computed but unused.
20. `contracts/solidity/AkashicProof.sol:314-457` — deprecated `onlyDeployer` write paths retained (centralization backdoor); unbounded snapshot/DA arrays.
21. `contracts/solidity/HashDNA.sol:165,208` — parameter named `event` (Solidity keyword); library is never compiled by any in-repo config (foundry test suite itself lacks forge-std import/remappings and likely doesn't compile: `contracts/test/ExecutionGate.t.sol:7`).
22. `contracts/test/{Reentrancy,Quorum,Pause}.t.sol` — empty stub files; `contracts/script/Deploy.s.sol` — fully commented-out deployment.
23. `contracts/solidity/TRIONPriceFeed.sol:52,87-88` — `MAX_ROUND_HISTORY` never enforced; unbounded rounds.
24. `contracts/near/src/trion_staking.rs:58-92` & `contracts/vyper/TRIONStaking.vy:249-251,452-486` — staking with no token custody and no reward/slash payout (comment-ware economics).
25. `contracts/near/src/trion_token.rs:108-111` — governance_mint always panics while `new()` mints nothing → total supply unreachable.
26. `zk/__init__.py:521-524,791-794,887-889` — policy booleans (range/compliance/pass flags) are prover-asserted, outside the Σ-protocol statement; `nonce` leaked in proof_data (line 520).
27. `formal/src/TRION/Theorems.hs:270-272` — the "no deletion function can exist" claim is false (`dropAll _ = BHEmpty` typechecks); T9's `mkBHSense` (line 330) doesn't hash.
28. `contracts/solidity/BTCPVersionRegistry.sol:78` — re-activation path rewrites `activatedAt` (minor accounting).
29. Dead code: `BTCPEscrow.sol:152,206` (`msg.sender != address(0)`); duplicated 7-arg lockEscrow body (159-183 vs 197-237).

---

## Claims vs reality

| Claim (README/docs) | Reality found |
|---|---|
| **ZK "6/6 PASS" / circuits compiled & witness-validated; intent circuit proven+verified end-to-end (Groth16)** | Circuits are real and well-formed (Poseidon bindings, correct LessThan range analysis, careful overflow notes) — but **zero build artifacts** (no .r1cs/.wasm/zkey/proof.json/verifier.sol committed). The claim is not reproducible from the repo; status checklist honestly leaves ceremony + verifier deployment unchecked. README itself calls complementarity a "Poseidon scaffold" vs the spec's 50k-constraint variant. |
| **README: Python zk is "real Σ-protocols"** | TRUE for the algebra: genuine Schnorr-Pedersen PoK with Fiat-Shamir over secp256k1 Pedersen commitments. But it is a **simulation layer**, not a SNARK, and all policy predicates (coherence-pass, travel-rule compliance, fair share, amount range) are unproven prover flags — the "proves compliance without revealing" framing overstates what's proven (knowledge of preimages only). |
| **"9 theorems" (formal/src/TRION/Theorems.hs)** | 9 theorems T1–T9 are present and self-check green — but they are GADT modeling + boolean example checks, **not machine-checked proofs** (no proof assistant). T8's deletion-impossibility claim is refutable with a one-line counterexample; T9's "hash" is string concatenation with the hardness assumption carried by an empty witness type. Header concedes "structural" only, in fine print. |
| **"7 theorems"?** | File and main() both say 9 (T1–T9), Spec.hs tests them; no 7-theorem artifact found in formal/. |
| **BTCPEscrow.sweepETH fix ("no governance override")** | **Verified genuine**: `_lockedBalance` aggregate + `sweepableExcess()` restrict sweeps to force-sent excess; all decrement paths are atomic with transfers. Sound. |
| **ConfidentialCoherenceVault coherence gate binding** | **Verified genuine**: 1:1 BEO↔address registration, caller-own-identity enforcement on wrap/unwrap. Residual identity-squatting vector (no proof of BEO ownership at register time). |
| **TRIONOracleV3 verdict expiry 300s** | **Verified**: `BTCP_ROUTE_FRESHNESS_SECONDS = 300` on routes + 300s/50-block on legacy signals. NOT ported to NEAR/CosmWasm/Soroban. |
| **TRIONGuardV3 "cannot keep firewall disabled indefinitely"** | Weakly true: 24h window + 1h cooldown still permits ~96% off-time; lazy expiry only evaluated on gated calls. |
| **"37-network consensus" / behavioral truth from validator quorum** | On-chain: single relayer (or owner) publishes nearly everything; quorum ECDSA exists only in ExecutionGate/AkashicProof/V3-legacy; TRIONOracle V1 trusts a self-reported quorumCount; V3 routes need one validator. |
| **ContinuumDEX "Hyperliquid-style perp + spot DEX"** | Registry of structs + events; no custody, no fills, no CCP value transfer. |
| **Multi-chain coverage ("8 VMs")** | EVM solid; SVM decent; NEAR/Move/CosmWasm/Soroban range from incomplete (NEAR token) to non-functional (CosmWasm recursion) to stubs (Move gate/oracle, Soroban escrow). |
| **Hardhat "self-contained test suite"** | True for tests; deploy scripts reference non-existent artifacts. Foundry side is stubs (3 empty .t.sol + commented-out Deploy.s.sol). |
| **Julia math ("theorem validation")** | Real, tested numeric implementations; naming overclaims (Kolmogorov bound is log-products). Self-verification prints 10 PASS lines — all arithmetically legit. |

**Next actions:** (1) fix CosmWasm `from_json_bytes` + multi-denom payout immediately; (2) parameterize SVM `lock_escrow` amount; (3) align Move oracle storage model or drop the module; (4) port the 300s freshness check to NEAR/CosmWasm/Soroban verify paths; (5) add quorum to `publishBTCPRoute` or document the single-validator trust assumption; (6) refund gas-abstraction overpayments; (7) commit zk build artifacts (r1cs/zkey hash/proof transcripts) or soften README claims; (8) replace prover-asserted policy booleans in `zk/__init__.py` with in-statement constraints; (9) rewrite formal claims as "type-modeled invariants + property tests" (or adopt LiquidHaskell); (10) restore Foundry suite with forge-std + remappings or delete the stubs.
