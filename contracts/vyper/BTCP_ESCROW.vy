# @version ^0.3.10
# ═════════════════════════════════════════════════════════════════════════════
# BTCP_ESCROW — Behavioral Transaction Continuity Protocol Escrow
# TRION Protocol — whitepaper §14.3 reference implementation (Vyper)
#
# Two-state atomic escrow:
#     HOLDING → RELEASED   (TRION consensus verified: C(t) ≥ Θ(t))
#     HOLDING → REVERTED   (timeout)
#
# TRION consensus is the ONLY oracle:
#   - release() is permissionless but requires a btcp_route_signal whose
#     verifyExecution(txId) returns isSafe AND coherence ≥ threshold on the
#     linked TRION oracle. No relayer key. No multi-sig. No governance.
#     No owner functions exist in this contract at all.
#   - The oracle itself enforces the quorum + freshness discipline on the
#     route verdict (see TRIONOracleV3.publishBTCPRoute quorum attestations).
#   - M-03 fix (Wave 2): the release quorum is NOT a static floor anymore —
#     release() consults the oracle's minRouteAttestations() view (the LIVE
#     validator-set-derived quorum max(2, ⌈2/3·validatorCount⌉)) and requires
#     attestations ≥ that value. Vyper has no try/catch: if the bound oracle
#     lacks the view, returns malformed data, or reverts, the whole release
#     reverts — the interface-mismatch case FAILS CLOSED (strictly stronger
#     than the Solidity _consensusGate floor-2 fallback, which the audit
#     flags as M-05). No silent degradation to a weaker quorum is possible.
#
# Replay/settlement discipline in this tier (audit H-05 / M-04 note):
#   - Settlement tuple: release() pays only the escrow's OWN stored
#     destination/amount (fixed at lock()); no release-time argument can
#     substitute them. The verdict is bound to THIS escrow via
#     anchorBH == escrow_id, and escrow_id is derived from
#     (intent_hash ‖ entity_id ‖ block) — so a verdict can only ever settle
#     the exact escrow (and its exact tuple) the quorum attested for.
#   - Replay: escrow states are terminal (RELEASED/REVERTED have no outgoing
#     transitions) — release-exactly-once is the escrow state machine's job;
#     per-(route, signer) attestation idempotency is the oracle's job.
#     Certificate-nonce tracking belongs to the canonical-certificate path
#     (CANONICAL_CERTIFICATE.md §8) that Agent G is landing as the V4 oracle
#     entrypoint; this tier upgrades to it once that interface exists.
#   - Pause: deliberately ABSENT — whitepaper §14.3 invariant "No multi-sig.
#     No governance. No owner. No pause. TRION consensus is the only
#     oracle". Emission-side freezes (AWA, HHI CRITICAL tier) are enforced
#     by the oracle, and the 300 s freshness window bounds any stale/frozen
#     verdict here.
#
# Differences from the whitepaper pseudocode (§14.3), disclosed:
#   1. Refunds are sent to the address that called lock() (the funder),
#      not to a derived `entity_id.address`. BEO entity_ids are behavioral
#      hashes, not addresses — deriving a payable target from a behavioral
#      hash can burn funds. The spec's intent ("return to entity") is
#      satisfied because the locker IS the entity in the lock() flow.
#   2. `revert_on_timeout` is permissionless (the whitepaper's own code
#      allows anyone to call it — only the timeout guard protects it).
#   3. token field retained (spec: "ETH only in this version") and is
#      always empty(address).
#
# No partial execution possible by design — amount is transferred whole,
# exactly once, and state transitions out of HOLDING are terminal.
#
# Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
# License: CC0
# ═════════════════════════════════════════════════════════════════════════════

# ── Constants: escrow states ──────────────────────────────────────────────────
IDLE:     constant(uint8) = 0
HOLDING:  constant(uint8) = 1
RELEASED: constant(uint8) = 2
REVERTED: constant(uint8) = 3

# ── Oracle interface (TRIONOracleV3) ─────────────────────────────────────────
interface ITRIONOracleV3:
    def verifyExecution(txId: bytes32) -> (bool, uint32, uint32): view
    def routeBinding(routeId: bytes32) -> (bytes32, uint256, bool, uint256, uint256, uint256): view
    # M-03: the dynamic, live-set-derived route verdict quorum —
    # max(2, ⌈2/3 · validatorCount⌉) distinct signature-verified validators.
    # A bound oracle WITHOUT this view is an interface mismatch: calls to it
    # revert and release() fails closed (no fallback to any static floor).
    def minRouteAttestations() -> uint256: view

# ── Storage ──────────────────────────────────────────────────────────────────
struct EscrowRecord:
    intent_hash:     bytes32
    entity_id:       bytes32     # BEO identity (behavioral hash, not payable)
    amount:          uint256
    token:           address     # always empty(address) — ETH only, this version
    funder:          address     # who locked the funds (receives the refund)
    lock_block:      uint256
    timeout_blocks:  uint256
    state:           uint8
    destination:     address

trion_oracle: public(ITRIONOracleV3)
escrows: public(HashMap[bytes32, EscrowRecord])   # escrow_id → record

# ── Events (per whitepaper §14.3) ────────────────────────────────────────────
event EscrowLocked:
    escrow_id:      indexed(bytes32)
    entity_id:      bytes32
    amount:         uint256
    expires_block:  uint256

event EscrowReleased:
    escrow_id:      indexed(bytes32)
    entity_id:      bytes32
    amount:         uint256

event EscrowReverted:
    escrow_id:      indexed(bytes32)
    entity_id:      bytes32
    amount:         uint256


@external
def __init__(trion: address):
    """Bind the escrow to the TRION oracle. Irreversible — no admin path."""
    assert trion != empty(address), "BTCP: zero oracle"
    self.trion_oracle = ITRIONOracleV3(trion)


@external
@payable
def lock(
    intent_hash:     bytes32,
    entity_id:       bytes32,
    timeout_blocks:  uint256,
    destination:     address,
) -> bytes32:
    """
    Lock msg.value for an intent. Permissionless — anyone may lock.

    The escrow_id is derived (not caller-supplied, unlike the Solidity
    tier) so lockers cannot collide with or pre-guess existing escrows:
        escrow_id = keccak256(intent_hash ‖ entity_id ‖ block_number)
    A same-block double lock with identical intent+entity would collide
    by construction of the spec formula — the `state == IDLE` guard
    rejects the second attempt (fail-closed).
    """
    assert msg.value > 0, "BTCP: zero amount"
    assert timeout_blocks > 0, "BTCP: zero timeout"
    assert destination != empty(address), "BTCP: zero destination"

    escrow_id: bytes32 = keccak256(
        concat(intent_hash, entity_id, convert(block.number, bytes32))
    )
    assert self.escrows[escrow_id].state == IDLE, "BTCP: escrow exists"

    self.escrows[escrow_id] = EscrowRecord({
        intent_hash:     intent_hash,
        entity_id:       entity_id,
        amount:          msg.value,
        token:           empty(address),   # ETH only in this version
        funder:          msg.sender,
        lock_block:      block.number,
        timeout_blocks:  timeout_blocks,
        state:           HOLDING,
        destination:     destination,
    })

    log EscrowLocked(
        escrow_id,
        entity_id,
        msg.value,
        block.number + timeout_blocks,
    )
    return escrow_id


@external
def release(escrow_id: bytes32, btcp_route_signal: bytes32):
    """
    Release escrowed funds to destination — TRION consensus gated.

    Permissionless: anyone may submit, but the submission must carry a
    btcp_route_signal that the linked oracle verifies as safe AND that is
    bound to THIS escrow:

        anchor_bh, attestations, is_safe, coherence, threshold, ts =
            trion_oracle.routeBinding(btcp_route_signal)

        require anchor_bh == escrow_id      <- binding (route-spoof fix)
        require is_safe
        required = max(2,                    <- M-03: quorum from the ORACLE's
            trion_oracle.minRouteAttestations())   live validator-set state,
                                                NEVER a hardcoded floor
        require attestations >= required
        require block.timestamp - ts <= 300  <- freshness
        require coherence >= threshold

    The oracle's attestation counter only grows through ECDSA-verified
    attestations from DISTINCT registered validators
    (TRIONOracleV3.submitRouteAttestation), so `attestations` is a
    signature-quorum count and `required` is derived from the live
    validator set — two attestations can no longer release any amount when
    the registered set requires a larger supermajority (M-03 regression
    class). A bound oracle that lacks minRouteAttestations() (or returns
    malformed data) makes this whole call revert: interface mismatches
    fail CLOSED, never degrade to a floor.
    """
    record: EscrowRecord = self.escrows[escrow_id]
    assert record.state == HOLDING, "BTCP: not in HOLDING state"

    # P-VY-01 (final red-team pass): expiry guard — an escrow past its
    # block timeout must travel the funder-protection (revert/refund) path,
    # never be released to the destination by a fresh late quorum verdict.
    # Solidity-tier parity (releaseEscrow's EXPIRED check).
    assert block.number <= record.lock_block + record.timeout_blocks, \
        "BTCP: escrow expired"

    # Verify TRION consensus proof — BOUND to this escrow via anchorBH.
    # (M3 fix: a quorum-safe verdict attested for a DIFFERENT escrow can
    # never release this one; one fresh verdict cannot be replayed across
    # multiple unrelated escrows.)
    anchor_bh: bytes32 = empty(bytes32)
    attestations: uint256 = 0
    is_safe: bool = False
    coherence: uint256 = 0
    threshold: uint256 = 0
    ts: uint256 = 0
    anchor_bh, attestations, is_safe, coherence, threshold, ts = self.trion_oracle.routeBinding(
        btcp_route_signal
    )
    assert anchor_bh == escrow_id, "BTCP: verdict not bound to this escrow"
    assert is_safe, "BTCP: TRION consensus proof invalid"

    # M-03 fix (Wave 2): quorum is DERIVED FROM THE ORACLE'S LIVE CANONICAL
    # STATE, not a hardcoded floor. minRouteAttestations() is the V3 view
    # max(2, ⌈2/3 · validatorCount⌉) — it grows with the registered validator
    # set, so a 7-validator set (required 5) can never be released on 2
    # attestations. Because Vyper has no try/catch, an oracle that is
    # missing this view (or returns garbage) reverts the entire release:
    # interface mismatch FAILS CLOSED — the audit's M-05 fallback class is
    # structurally impossible here. The local floor of 2 is kept only as a
    # defensive clamp (max(2, view)) so a misbehaving oracle that reports a
    # sub-floor quorum can never weaken the gate below the hard floor —
    # the exact discipline of the Solidity _consensusGate.
    oracle_quorum: uint256 = self.trion_oracle.minRouteAttestations()
    required: uint256 = 2
    if oracle_quorum > required:
        required = oracle_quorum
    assert attestations >= required, "BTCP: quorum unmet"

    assert block.timestamp - ts <= 300, "BTCP: verdict stale"
    assert coherence >= threshold, "BTCP: coherence below threshold"

    # Check-effects-interactions: terminal state BEFORE transfer
    self.escrows[escrow_id].state = RELEASED
    send(record.destination, record.amount)

    log EscrowReleased(escrow_id, record.entity_id, record.amount)


@external
def revert_on_timeout(escrow_id: bytes32):
    """
    Revert escrowed funds to the funder after timeout. Permissionless —
    the block-number guard is the only gate.

    BTCP_TIMEOUT is recorded downstream in the Akashic Index by the
    relayer watching the EscrowReverted event (whitepaper Fix 2:
    EXTERNAL_CAUSE → intent preserved; entity chooses
    WAIT | CANCEL | REROUTE).
    """
    record: EscrowRecord = self.escrows[escrow_id]
    assert record.state == HOLDING, "BTCP: not in HOLDING state"
    assert block.number > record.lock_block + record.timeout_blocks, "BTCP: timeout not reached"

    # Check-effects-interactions: terminal state BEFORE transfer
    self.escrows[escrow_id].state = REVERTED
    send(record.funder, record.amount)    # return to the entity that locked

    log EscrowReverted(escrow_id, record.entity_id, record.amount)


@external
@view
def escrow_state(escrow_id: bytes32) -> uint8:
    """Read the escrow state (0 IDLE, 1 HOLDING, 2 RELEASED, 3 REVERTED)."""
    return self.escrows[escrow_id].state


# ═════════════════════════════════════════════════════════════════════════════
# INVARIANTS (whitepaper §14.3):
#   • Two terminal outcomes only: RELEASED or REVERTED — no partial
#     execution, no re-lock, no state resurrection.
#   • No multi-sig. No governance. No owner. No pause.
#     TRION consensus is the only oracle.
#   • Funds move exactly once out of HOLDING, whole, to exactly one of
#     {destination on release, funder on timeout}.
# ═════════════════════════════════════════════════════════════════════════════
