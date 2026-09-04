"""
BTCP canonical invariant battery (Agent F, Wave 1)
==================================================

Adversarial + positive tests for the invariants registered in
docs/security/CANONICAL_INVARIANTS.md (INV-001 … INV-022).  Each test is
named after its invariant; the attack tests name the attack they model
per the master command §8 question list:

  * can the caller supply security-critical values?     (INV-003, 010, 012, 016)
  * can it replay / reorder / double-execute?           (INV-002, 006, 013, 015)
  * can an attacker substitute entity / route / values? (INV-007, 008, 014)
  * can it bypass freshness / quorum / terminal law?    (INV-005, 011, 012, 004)

Happy paths are asserted alongside every rejection so the fail-closed
fixes are proven non-breaking (legitimate inputs keep succeeding).

Run: pytest tests/btcp/test_invariants.py -q
"""

import os
import time

import pytest

from core.btcp.orchestrator import (          # noqa: E402
    BTCPOrchestrator,
    PrivacyLevel,
    RouteStatus,
)
from core.btcp import orchestrator as orch_mod
from core.btcp.escrow_monitor import (        # noqa: E402
    EscrowMonitor,
    EscrowState,
    RevertReason,
    MIN_COHERENCE_FLOOR,
)
from core.btcp.dispute_resolution import (    # noqa: E402
    DisputeResolver,
    DisputeStatus,
    Vote,
)
from core.btcp.modules import (               # noqa: E402
    BITPMatcher,
    BITPIntent,
    BTCPProofBuilder,
    ValidatorSignature,
    OOAAnchor,
    FailureClassifier,
)
from core.btcp import router as btcp_router  # noqa: E402


# ── fixtures ─────────────────────────────────────────────────────────────────

SRC = "0x" + "11" * 20
DST = "0x" + "22" * 20


@pytest.fixture()
def orch(tmp_path):
    """Hermetic orchestrator on a temp state DB with fresh entity nonces."""
    monkey_local = pytest.MonkeyPatch()
    monkey_local.setattr(orch_mod, "_ENTITY_NONCES", {})
    o = BTCPOrchestrator(state_db=str(tmp_path / "btcp_state.db"))
    yield o
    monkey_local.undo()
    o._store.close()


@pytest.fixture()
def escrow_mon(tmp_path):
    mon = EscrowMonitor(state_db=str(tmp_path / "escrow.db"))
    yield mon
    mon._store.close()


@pytest.fixture()
def resolver(tmp_path):
    r = DisputeResolver(state_db=str(tmp_path / "dispute.db"))
    for aid, stake in [("a1", 100), ("a2", 80), ("a3", 60), ("a4", 50),
                       ("a5", 40), ("a6", 30)]:
        r.register_annotator(aid, stake)
    yield r
    r._store.close()


def _create(orch_obj, **kw):
    result = orch_obj.create_route(
        source_chain=1,
        dest_chain=137,
        source_address=kw.pop("source_address", SRC),
        dest_address=kw.pop("dest_address", DST),
        amount=kw.pop("amount", 1_000_000),
        asset="ETH",
        **kw,
    )
    assert result.success, result.errors
    return result


def _full_behavioral_data():
    sense = bytes(range(32))
    return {
        "genomic_sense": sense.hex(),
        "genomic_antisense": bytes(b ^ 0xFF for b in sense).hex(),
        "block_number": 18_500_000,
        "coherence": 0.75, "manipulation": 0.15,
        "liquidity": 0.80, "depth": 500.0,
    }


_IAP = {
    "total_gas": 2_400_000, "entity_gas": 240_000,
    "total_btcp_fee_wei": int(0.02 * 10**18),
    "entity_share_wei": int(0.002 * 10**18),
    "num_participants": 12,
}


# ── INV-001: zero bridge ────────────────────────────────────────────────────

def test_inv001_zero_bridge(orch):
    result = _create(orch, privacy_level=PrivacyLevel.BASIC)
    route = result.route
    assert route.assets_bridged is False

    matcher = BITPMatcher()
    a = BITPIntent(b"\x01" * 32, b"\xAA" * 32, b"\xBB" * 32, 1000.0, 1, 10**12)
    b = BITPIntent(b"\x02" * 32, b"\xBB" * 32, b"\xAA" * 32, 1000.0, 137, 10**12)
    paste = matcher.execute_paste(a, b)
    assert paste["cross_chain_movement"] == 0
    assert paste["bridge"] == "NONE"
    assert paste["asset_x_stays_on_chain_a"] is True


# ── INV-002: escrow terminal semantics ──────────────────────────────────────

def test_inv002_happy_lock_verify_release(escrow_mon):
    escrow_mon.lock_escrow("e1", "r1", b"\x01" * 32, 1000.0, 1000, block_number=100)
    assert escrow_mon.verify_settlement("e1")
    assert escrow_mon.release_escrow("e1", coherence=0.80, block_number=200)
    assert escrow_mon.get_escrow("e1").state == EscrowState.RELEASED


def test_inv002_double_release_rejected(escrow_mon):
    """ATTACK: double-execute — release the same escrow twice."""
    escrow_mon.lock_escrow("e2", "r2", b"\x01" * 32, 1000.0, 1000, block_number=100)
    escrow_mon.verify_settlement("e2")
    assert escrow_mon.release_escrow("e2", coherence=0.80, block_number=200)
    assert not escrow_mon.release_escrow("e2", coherence=0.80, block_number=201)
    assert escrow_mon.get_escrow("e2").state == EscrowState.RELEASED


def test_inv002_revert_after_release_rejected(escrow_mon):
    """ATTACK: resurrect a settled escrow into REVERTED (double refund)."""
    escrow_mon.lock_escrow("e3", "r3", b"\x01" * 32, 1000.0, 1000, block_number=100)
    escrow_mon.verify_settlement("e3")
    assert escrow_mon.release_escrow("e3", coherence=0.80, block_number=200)
    assert not escrow_mon.revert_escrow("e3", RevertReason.MANUAL)
    assert escrow_mon.get_escrow("e3").state == EscrowState.RELEASED


# ── INV-003: settlement + protocol-floor coherence ─────────────────────────

def test_inv003_two_phase_release(escrow_mon):
    """ATTACK: bypass G1 — release before settlement verification."""
    escrow_mon.lock_escrow("e4", "r4", b"\x01" * 32, 1000.0, 1000, block_number=100)
    assert not escrow_mon.release_escrow("e4", coherence=0.99, block_number=150)
    assert escrow_mon.get_escrow("e4").state == EscrowState.HOLDING


def test_inv003_coherence_floor(escrow_mon):
    """ATTACK: caller supplies min_coherence=0.0 to defeat the coherence gate.

    The protocol floor (0.55) must apply regardless of the caller's
    argument — callers may tighten, never loosen.
    """
    escrow_mon.lock_escrow("e5", "r5", b"\x01" * 32, 1000.0, 1000, block_number=100)
    escrow_mon.verify_settlement("e5")
    # coherence 0.30 < floor 0.55 → rejected even with min_coherence=0.0
    assert not escrow_mon.release_escrow(
        "e5", coherence=0.30, min_coherence=0.0, block_number=150)
    assert not escrow_mon.release_escrow(
        "e5", coherence=0.30, min_coherence=-1.0, block_number=150)
    # happy: coherence above the floor with the default threshold
    assert escrow_mon.release_escrow("e5", coherence=0.80, block_number=150)


def test_inv003_caller_may_tighten_not_loosen(escrow_mon):
    escrow_mon.lock_escrow("e6", "r6", b"\x01" * 32, 1000.0, 1000, block_number=100)
    escrow_mon.verify_settlement("e6")
    # tighten to 0.9: coherence 0.85 now insufficient
    assert not escrow_mon.release_escrow(
        "e6", coherence=0.85, min_coherence=0.90, block_number=150)
    assert escrow_mon.get_escrow("e6").state == EscrowState.HOLDING
    # 0.85 still clears the floor
    assert escrow_mon.release_escrow("e6", coherence=0.85, block_number=150)


def test_inv003_pending_akashic_floor(escrow_mon):
    escrow_mon.lock_escrow("e7", "r7", b"\x01" * 32, 1000.0, 1000, block_number=100)
    assert escrow_mon.enter_pending_akashic("e7")
    assert not escrow_mon.release_from_pending_akashic(
        "e7", coherence=0.30, min_coherence=0.0)
    assert escrow_mon.release_from_pending_akashic(
        "e7", coherence=0.80, min_coherence=0.0)  # floor satisfied
    assert escrow_mon.get_escrow("e7").state == EscrowState.RELEASED


def test_inv003_floor_value_is_the_proof_builder_default():
    """One coherence number everywhere: escrow floor == proof threshold."""
    assert MIN_COHERENCE_FLOOR == BTCPProofBuilder.DEFAULT_COHERENCE_THRESHOLD


# ── INV-004: no release after timeout ───────────────────────────────────────

def test_inv004_release_after_timeout_rejected(escrow_mon):
    """ATTACK: bypass the timeout — release past lock+timeout window."""
    escrow_mon.lock_escrow("e8", "r8", b"\x01" * 32, 1000.0, 100, block_number=100)
    escrow_mon.verify_settlement("e8")
    assert not escrow_mon.release_escrow("e8", coherence=0.99, block_number=300)
    # revert-on-timeout is permissionless and works
    assert escrow_mon.revert_escrow("e8", RevertReason.TIMEOUT, block_number=300)
    assert escrow_mon.get_escrow("e8").state == EscrowState.REVERTED


# ── INV-005: verdict freshness ──────────────────────────────────────────────

def _three_sig_proof(**overrides):
    good = dict(
        anchor_bh=b"\x01" * 32, intent_hash=b"\x02" * 32,
        route_type=1, certification_block=18_000_000, value_usd=5_000.0,
        validator_signatures=[
            ValidatorSignature(b"\x03" * 32, b"\x04" * 65, 0.8),
            ValidatorSignature(b"\x13" * 32, b"\x14" * 65, 0.7),
            ValidatorSignature(b"\x23" * 32, b"\x24" * 65, 0.6),
        ],
        diversity_weights=[0.8, 0.7, 0.6], hhi=1500.0,
        coherence=0.85, threshold=0.55,
    )
    good.update(overrides)
    return BTCPProofBuilder().build_proof(**good)


def test_inv005_fresh_certificate_accepted():
    proof = _three_sig_proof()
    assert BTCPProofBuilder().verify_proof(proof, current_block=18_000_001)


def test_inv005_expired_certificate_rejected():
    """ATTACK: replay an expired consensus verdict (A3 window)."""
    proof = _three_sig_proof()  # $5K route → 50_000-block window
    assert not BTCPProofBuilder().verify_proof(
        proof, current_block=18_000_000 + 50_001)


# ── INV-006: payout exactly once ────────────────────────────────────────────

def test_inv006_reward_replay_no_double_pay(orch, monkeypatch):
    """ATTACK: replay the completion event in a DIFFERENT UTC epoch.

    The store's (epoch, pool, route) replay guard only collapses
    same-epoch replays; without the update no-op semantics a replay
    after midnight would double-pay the pools.
    """
    result = _create(orch, amount=1_000_000)
    rid = result.route.route_id

    monkeypatch.setattr(orch_mod, "_route_reward_epoch", lambda ts: 100)
    assert orch.update_route_status(rid, RouteStatus.COMPLETED)
    assert len(orch._store.read_btcp_table("btcp_route_rewards")) == 2

    # replay lands in the next epoch — must be a no-op, not a second payout
    monkeypatch.setattr(orch_mod, "_route_reward_epoch", lambda ts: 200)
    assert orch.update_route_status(rid, RouteStatus.COMPLETED)  # idempotent
    assert orch.update_route_status(rid, RouteStatus.COMPLETED)
    rewards = orch._store.read_btcp_table("btcp_route_rewards")
    assert len(rewards) == 2  # one anchor leg + one execution leg, no more
    total = 1_000_000 * 0.001
    by_pool = {r["validator_address"]: r["final_reward"] for r in rewards}
    assert by_pool["anchor_pool:1"] == pytest.approx(total * 0.60)
    assert by_pool["execution_pool:137"] == pytest.approx(total * 0.40)


def test_inv006_failed_route_pays_nothing(orch):
    result = _create(orch)
    assert orch.update_route_status(result.route.route_id, RouteStatus.FAILED)
    assert orch._store.read_btcp_table("btcp_route_rewards") == []
    row = orch._store.read_btcp_table("btcp_routes")[0]
    assert row["status"] == "FAILED" and row["finalized_at"] is not None


# ── INV-007: BITP distinct, unexpired counterparty ──────────────────────────

def test_inv007_happy_match():
    matcher = BITPMatcher()
    a = BITPIntent(b"\x01" * 32, b"\xAA" * 32, b"\xBB" * 32, 1000.0, 1, 10**12)
    b = BITPIntent(b"\x02" * 32, b"\xBB" * 32, b"\xAA" * 32, 1000.0, 137, 10**12)
    assert matcher.find_complement(a, [b]) is b


def test_inv007_self_match_rejected():
    """ATTACK: substitution/wash — the same entity fills both sides."""
    matcher = BITPMatcher()
    a = BITPIntent(b"\x01" * 32, b"\xAA" * 32, b"\xBB" * 32, 1000.0, 1, 10**12)
    self_fill = BITPIntent(
        b"\x01" * 32, b"\xBB" * 32, b"\xAA" * 32, 1000.0, 137, 10**12)
    assert matcher.find_complement(a, [self_fill]) is None
    # a self-candidate plus a real one: only the real one may match
    b = BITPIntent(b"\x02" * 32, b"\xBB" * 32, b"\xAA" * 32, 1000.0, 137, 10**12)
    assert matcher.find_complement(a, [self_fill, b]) is b


def test_inv007_expired_candidate_skipped():
    """ATTACK: match against an expired commitment (spec §5.1 expiry)."""
    matcher = BITPMatcher()
    now = 1_000_000
    a = BITPIntent(b"\x01" * 32, b"\xAA" * 32, b"\xBB" * 32, 1000.0, 1, now + 500)
    stale = BITPIntent(
        b"\x02" * 32, b"\xBB" * 32, b"\xAA" * 32, 1000.0, 137, now - 1)
    fresh = BITPIntent(
        b"\x03" * 32, b"\xBB" * 32, b"\xAA" * 32, 1000.0, 137, now + 500)
    assert matcher.find_complement(a, [stale], current_time=now) is None
    assert matcher.find_complement(a, [stale, fresh], current_time=now) is fresh
    # expired SEEKING intent cannot match at all
    a_exp = BITPIntent(b"\x01" * 32, b"\xAA" * 32, b"\xBB" * 32, 1000.0, 1, now - 1)
    assert matcher.find_complement(a_exp, [fresh], current_time=now) is None


# ── INV-008 / INV-014: intent identity ──────────────────────────────────────

def test_inv008_rapid_identical_routes_do_not_clobber(orch):
    """ATTACK: same-microsecond identical submission collides onto one route.

    The legacy id derivation hashed time.time() alone; the id now mixes a
    random session tag + a process-global monotonic sequence.
    """
    ids = []
    for _ in range(3):
        result = _create(orch, privacy_level=PrivacyLevel.BASIC)
        ids.append(result.route.route_id)
    assert len(set(ids)) == 3
    # all three persisted, none clobbered
    persisted = orch._store.get_routes()
    for rid in ids:
        assert rid in persisted
    intents = orch._store.read_btcp_table("btcp_intent_registry")
    assert len(intents) == 3


def test_inv008_nonce_monotonic_per_entity(orch):
    """Spec §4.1: the intent nonce is a per-entity monotonic counter."""
    nonces = [
        _create(orch, privacy_level=PrivacyLevel.BASIC).route.intent.nonce
        for _ in range(4)
    ]
    assert nonces == sorted(nonces)
    assert len(set(nonces)) == 4
    # a different entity seeds independently
    other = _create(
        orch, source_address="0x" + "33" * 20,
        privacy_level=PrivacyLevel.BASIC).route.intent.nonce
    assert other not in nonces


# ── INV-009: honest proof deferral ──────────────────────────────────────────

def test_inv009_pending_proof_fails_closed(orch):
    """ATTACK: present a deferred (zk_pending) route as fully proven."""
    result = _create(orch, privacy_level=PrivacyLevel.STANDARD)
    pending = [n for n, p in result.route.proofs.items()
               if isinstance(p, dict) and p.get("status") == "zk_pending"]
    assert pending, "STANDARD route without strands must defer honestly"
    valid, errors = orch.verify_route_proofs(result.route.route_id)
    assert not valid
    assert any("pending" in e.lower() for e in errors)


def test_inv009_real_witnesses_verify(orch):
    result = _create(
        orch, privacy_level=PrivacyLevel.FULL,
        behavioral_data=_full_behavioral_data(),
        iap_economics=_IAP,
    )
    valid, errors = orch.verify_route_proofs(result.route.route_id)
    assert valid, errors


# ── INV-010: protocol-owned proof threshold ─────────────────────────────────

def test_inv010_threshold_clamped():
    """ATTACK: caller passes coherence_threshold=0.0 to the proof builder.

    The threshold must clamp to the protocol default (0.55) — the
    threshold_margin cannot be made trivially non-negative.
    """
    from core.spiritual.consensus import build_demo_validators
    pb = BTCPProofBuilder()
    validators = build_demo_validators(12)
    proof, attestation = pb.build_proof_from_validators(
        anchor_bh=b"\x05" * 32, intent_hash=b"\x06" * 32,
        route_type=1, certification_block=18_000_000, value_usd=5_000.0,
        validators=validators,
        validator_signatures=[
            ValidatorSignature(b"\x07" * 32, b"\x08" * 65, 0.8),
            ValidatorSignature(b"\x17" * 32, b"\x18" * 65, 0.7),
            ValidatorSignature(b"\x27" * 32, b"\x28" * 65, 0.6),
        ],
        coherence_threshold=0.0,   # attack: attempt to zero the gate
    )
    # the proof was built with the floor, not the caller's zero:
    assert proof.consensus_proof.threshold_margin == pytest.approx(
        attestation.sigma - BTCPProofBuilder.DEFAULT_COHERENCE_THRESHOLD)
    # a legitimate TIGHTER threshold is honored
    proof2, att2 = pb.build_proof_from_validators(
        anchor_bh=b"\x05" * 32, intent_hash=b"\x06" * 32,
        route_type=1, certification_block=18_000_000, value_usd=5_000.0,
        validators=validators,
        validator_signatures=[
            ValidatorSignature(b"\x07" * 32, b"\x08" * 65, 0.8),
            ValidatorSignature(b"\x17" * 32, b"\x18" * 65, 0.7),
            ValidatorSignature(b"\x27" * 32, b"\x28" * 65, 0.6),
        ],
        coherence_threshold=0.7,
    )
    assert proof2.consensus_proof.threshold_margin == pytest.approx(att2.sigma - 0.7)


# ── INV-011: consensus proof structural contract ────────────────────────────

def test_inv011_structural_contract():
    """ATTACK battery: each structural violation rejected (rust parity)."""
    pb = BTCPProofBuilder()
    three = [
        ValidatorSignature(b"\x03" * 32, b"\x04" * 65, 0.8),
        ValidatorSignature(b"\x13" * 32, b"\x14" * 65, 0.7),
        ValidatorSignature(b"\x23" * 32, b"\x24" * 65, 0.6),
    ]
    block = 18_000_001

    # happy path first: the well-formed proof verifies
    assert pb.verify_proof(_three_sig_proof(), current_block=block)

    # < 3 signers (rust: InsufficientSigners)
    assert not pb.verify_proof(
        _three_sig_proof(validator_signatures=three[:2]), current_block=block)
    # duplicate signer (rust: DuplicateSigner)
    assert not pb.verify_proof(
        _three_sig_proof(validator_signatures=[three[0], three[0], three[1]]),
        current_block=block)
    # malformed signature shape (rust: MalformedSignature)
    bad = [ValidatorSignature(b"\x03" * 32, b"\x04" * 64, 0.8)] + three[1:]
    assert not pb.verify_proof(
        _three_sig_proof(validator_signatures=bad), current_block=block)
    # too concentrated (HHI > 0.5 on the rust scale)
    assert not pb.verify_proof(_three_sig_proof(hhi=0.9), current_block=block)
    # too concentrated (HHI > 5000 on the python 0-10000 scale)
    assert not pb.verify_proof(_three_sig_proof(hhi=9000.0), current_block=block)
    # coherence below threshold (negative margin)
    assert not pb.verify_proof(
        _three_sig_proof(coherence=0.30, threshold=0.55), current_block=block)
    # zero coherence
    assert not pb.verify_proof(_three_sig_proof(coherence=0.0), current_block=block)


# ── INV-012: quorum recomputed at verification ──────────────────────────────

def _build_real_consensus_proof(n_keys=3, **overrides):
    from core.spiritual.signature_aggregation import ValidatorSignatureAggregator
    agg = ValidatorSignatureAggregator()
    keys = [agg.generate_keypair() for _ in range(n_keys)]
    pb = BTCPProofBuilder()
    return pb.build_consensus_proof(b"\x0a" * 32, keys, **overrides)


def test_inv012_honest_consensus_proof_verifies():
    proof = _build_real_consensus_proof()
    assert proof["threshold_met"] is True
    assert BTCPProofBuilder().verify_consensus_proof(proof)


def test_inv012_forged_quorum_claim_rejected():
    """ATTACK: forge {threshold_met: true} with a sub-quorum signer set.

    The verifier must RECOMPUTE the quorum (protocol floor 2/3) instead
    of trusting the proof dict's own claims: 3 real signers out of a
    claimed total of 10 is 0.3 < 2/3 — not a consensus even though every
    signature is real and threshold_met is forged to True.
    """
    proof = _build_real_consensus_proof()
    forged = dict(proof)
    forged["total_validators"] = 10
    forged["threshold_met"] = True
    assert not BTCPProofBuilder().verify_consensus_proof(forged)

    # honest sub-quorum build (3 of 10, threshold_met honestly False)
    honest = _build_real_consensus_proof(total_validators=10)
    assert honest["threshold_met"] is False
    assert not BTCPProofBuilder().verify_consensus_proof(honest)


def test_inv012_lowered_quorum_fraction_ignored():
    """ATTACK: lower the claimed quorum_fraction below the 2/3 floor."""
    proof = _build_real_consensus_proof(total_validators=6)  # 3 of 6 = 0.5
    forged = dict(proof)
    forged["quorum_fraction"] = 0.5   # below the protocol floor
    forged["threshold_met"] = True
    assert not BTCPProofBuilder().verify_consensus_proof(forged)


# ── INV-013: route status machine law ───────────────────────────────────────

def test_inv013_forward_progress_allowed(orch):
    """Happy: the legitimate ladder works, including the suite's
    PROOFS_GENERATED → COMPLETED fast path."""
    result = _create(orch)
    rid = result.route.route_id
    assert orch.update_route_status(rid, RouteStatus.SOURCE_EXECUTED)
    assert orch.update_route_status(rid, RouteStatus.DEST_EXECUTED)
    assert orch.update_route_status(rid, RouteStatus.COMPLETED)
    assert orch.get_route(rid).status == RouteStatus.COMPLETED

    result2 = _create(orch)
    assert orch.update_route_status(result2.route.route_id, RouteStatus.COMPLETED)


def test_inv013_resurrection_rejected(orch):
    """ATTACK: resurrection — rewrite a COMPLETED route to FAILED."""
    result = _create(orch)
    rid = result.route.route_id
    assert orch.update_route_status(rid, RouteStatus.COMPLETED)
    assert not orch.update_route_status(rid, RouteStatus.FAILED)
    assert not orch.update_route_status(rid, RouteStatus.PROOFS_GENERATED)
    assert orch.get_route(rid).status == RouteStatus.COMPLETED


def test_inv013_failed_terminal_frozen(orch):
    """ATTACK: FAILED → COMPLETED to collect validator rewards after failure."""
    result = _create(orch)
    rid = result.route.route_id
    assert orch.update_route_status(rid, RouteStatus.FAILED)
    assert not orch.update_route_status(rid, RouteStatus.COMPLETED)
    assert orch.get_route(rid).status == RouteStatus.FAILED
    assert orch._store.read_btcp_table("btcp_route_rewards") == []


def test_inv013_reorder_rejected(orch):
    """ATTACK: reorder — walk the status ladder backwards."""
    result = _create(orch)
    rid = result.route.route_id
    assert orch.update_route_status(rid, RouteStatus.SOURCE_EXECUTED)
    assert orch.update_route_status(rid, RouteStatus.DEST_EXECUTED)
    assert not orch.update_route_status(rid, RouteStatus.SOURCE_EXECUTED)
    assert orch.get_route(rid).status == RouteStatus.DEST_EXECUTED


def test_inv013_failure_always_reachable(orch):
    """Failure sinks are reachable from EVERY active state (escrow timeout
    / failure classification can strike at any step)."""
    for from_status, to_status in [
        (RouteStatus.PROOFS_GENERATED, RouteStatus.TIMEOUT),
        (RouteStatus.SOURCE_EXECUTED, RouteStatus.FAILED),
        (RouteStatus.DEST_EXECUTED, RouteStatus.TIMEOUT),
    ]:
        result = _create(orch)
        rid = result.route.route_id
        # walk to from_status first (forward-only, starting from the
        # creation status PROOFS_GENERATED)
        ladder = [s for s in RouteStatus
                  if RouteStatus.PROOFS_GENERATED.value <= s.value <= from_status.value]
        for step in ladder:
            assert orch.update_route_status(rid, step)
        assert orch.get_route(rid).status == from_status
        assert orch.update_route_status(rid, to_status), \
            f"{from_status.name} -> {to_status.name} must be legal"
        assert orch.get_route(rid).status == to_status


def test_inv013_failure_reachable_from_intent_created(orch, monkeypatch):
    """INTENT_CREATED (proof generation failed at creation) may still fail."""
    def _boom(*args, **kwargs):
        raise ValueError("proof layer unavailable")
    monkeypatch.setattr(orch.privacy_router, "generate_proofs", _boom)
    result = orch.create_route(
        source_chain=1, dest_chain=137, source_address=SRC,
        dest_address=DST, amount=1_000_000, asset="ETH",
    )
    assert result.route.status == RouteStatus.INTENT_CREATED
    assert orch.update_route_status(result.route.route_id, RouteStatus.FAILED)
    assert orch.get_route(result.route.route_id).status == RouteStatus.FAILED


def test_inv013_same_status_replay_is_noop(orch):
    """Replay of the CURRENT status: True (idempotent), zero side effects."""
    result = _create(orch)
    rid = result.route.route_id
    assert orch.update_route_status(rid, RouteStatus.COMPLETED)
    rows_before = len(orch._store.read_btcp_table("btcp_routes"))
    updated_before = orch.get_route(rid).updated_at
    assert orch.update_route_status(rid, RouteStatus.COMPLETED)
    assert orch.get_route(rid).updated_at == updated_before  # untouched
    assert len(orch._store.read_btcp_table("btcp_routes")) == rows_before


def test_inv013_unknown_route_rejected(orch):
    assert not orch.update_route_status("route_nope", RouteStatus.COMPLETED)
    assert not orch.update_route_status("route_nope", RouteStatus.FAILED)


# ── INV-015 / INV-018: dispute resolution law ───────────────────────────────

def test_inv015_happy_3of5_guilty(resolver):
    case = resolver.open_case("route1", "0xC", "0xR", "stale anchor",
                               challenged_value=10_000)
    assert case.challenge_bond == 500.0  # 5% bond gate
    for a, v in zip(case.selected_annotators,
                    [Vote.NOT_GUILTY] * 2 + [Vote.GUILTY] * 3):
        assert resolver.cast_vote(case.case_id, a, v, "reviewed")
    assert resolver.get_case(case.case_id).status == DisputeStatus.RESOLVED_GUILTY


def test_inv015_double_vote_rejected(resolver):
    """ATTACK: double-execute — one annotator votes twice."""
    case = resolver.open_case("route2", "0xC", "0xR", "wash trade")
    ann = case.selected_annotators[0]
    assert resolver.cast_vote(case.case_id, ann, Vote.GUILTY, "first")
    assert not resolver.cast_vote(case.case_id, ann, Vote.NOT_GUILTY, "second")
    assert resolver.get_case(case.case_id).votes[ann].vote == Vote.GUILTY


def test_inv015_non_panel_vote_rejected(resolver):
    """ATTACK: substitution — a non-panel entity votes."""
    case = resolver.open_case("route3", "0xC", "0xR", "claim")
    assert not resolver.cast_vote(case.case_id, "intruder", Vote.GUILTY, "fake")
    assert "intruder" not in resolver.get_case(case.case_id).votes


def test_inv015_no_majority_dismissed(tmp_path):
    """A 4-annotator panel splitting 2-2 resolves DISMISSED (no majority)."""
    r = DisputeResolver(state_db=str(tmp_path / "d4.db"))
    for aid, stake in [("b1", 90), ("b2", 80), ("b3", 70), ("b4", 60)]:
        r.register_annotator(aid, stake)
    case = r.open_case("route4", "0xC", "0xR", "split panel")
    assert len(case.selected_annotators) == 4
    votes = [Vote.GUILTY, Vote.GUILTY, Vote.NOT_GUILTY, Vote.NOT_GUILTY]
    for a, v in zip(case.selected_annotators, votes):
        assert r.cast_vote(case.case_id, a, v, "reviewed")
    assert r.get_case(case.case_id).status == DisputeStatus.DISMISSED


def test_inv018_case_freeze_after_resolution(resolver):
    """ATTACK: reorder — vote in an already-resolved case."""
    case = resolver.open_case("route5", "0xC", "0xR", "fast")
    for a, v in zip(case.selected_annotators[:3], [Vote.GUILTY] * 3):
        assert resolver.cast_vote(case.case_id, a, v, "x")
    assert resolver.get_case(case.case_id).status == DisputeStatus.RESOLVED_GUILTY
    remaining = case.selected_annotators[3:]
    for a in remaining:
        assert not resolver.cast_vote(case.case_id, a, Vote.NOT_GUILTY, "late")


@pytest.mark.xfail(
    strict=False,
    reason="INV-015/018: the 72h dispute window is declared "
           "(DISPUTE_WINDOW_SECONDS) but not yet enforced in cast_vote — "
           "registered as the open Wave-1 item in the invariant register",
)
def test_inv015_window_expiry_rejects_votes(resolver):
    """ATTACK: bypass freshness — vote after the 72-hour dispute window."""
    case = resolver.open_case("route6", "0xC", "0xR", "stale case")
    stale = resolver.get_case(case.case_id)
    stale.opened_at = time.time() - 100 * 3600  # 100h ago
    ann = stale.selected_annotators[0]
    assert not resolver.cast_vote(case.case_id, ann, Vote.GUILTY, "late vote")


# ── INV-016: witness provenance labeling ────────────────────────────────────

def test_inv016_witness_provenance_labeled(orch):
    result = _create(
        orch, privacy_level=PrivacyLevel.FULL,
        behavioral_data=_full_behavioral_data(),
        iap_economics=_IAP,
    )
    proofs = result.route.proofs
    bc = proofs["behavioral_credential"]
    assert bc["witness_source"] == "caller_self_attested"
    iap = proofs["iap_share"]
    assert iap["witness_source"] == "caller_supplied_batch_economics"
    # the thresholds inside the credential are protocol constants, not
    # caller values (INV-016's second half)
    pub = bc.get("public_inputs", {})
    assert pub.get("threshold_coherence", 0.55) == 0.55
    assert pub.get("threshold_manipulation", 0.30) == 0.30
    # and the caller's self-attested scores do not move the goalposts:
    # the proof still verifies because the CLAIM meets the floor
    valid, _ = orch.verify_route_proofs(result.route.route_id)
    assert valid


def test_inv016_self_attested_low_scores_still_labeled(orch):
    """A caller claiming incoherent behavior still gets an honest proof —
    the credential records the failing claim instead of passing it off."""
    bd = _full_behavioral_data()
    bd["coherence"] = 0.10  # below the protocol threshold
    result = _create(
        orch, privacy_level=PrivacyLevel.FULL,
        behavioral_data=bd, iap_economics=_IAP,
    )
    bc = result.route.proofs["behavioral_credential"]
    assert bc["witness_source"] == "caller_self_attested"


# ── INV-017: failure classification ladder ──────────────────────────────────

def test_inv017_external_cause_zero_penalty():
    """EXTERNAL indicators alone → EXTERNAL_CAUSE (BEO impact zero)."""
    fc = FailureClassifier()
    assert fc.classify(True, True, False, False,
                       False, False, False, False) == "EXTERNAL_CAUSE"
    assert fc.classify(False, False, True, False,
                       False, False, False, False) == "EXTERNAL_CAUSE"
    # entity indicators alone → ENTITY_CAUSE
    assert fc.classify(False, False, False, False,
                       True, True, False, False) == "ENTITY_CAUSE"
    # ambiguous: benefit of the doubt twice, third escalates
    assert fc.classify(False, False, False, False, False, False, False, False,
                       prior_ambiguous_count=0) == "EXTERNAL_CAUSE"
    assert fc.classify(False, False, False, False, False, False, False, False,
                       prior_ambiguous_count=2) == "ENTITY_CAUSE"


def test_inv017_route_failure_records_cause(orch):
    result = _create(orch)
    assert orch.update_route_status(result.route.route_id, RouteStatus.FAILED)
    row = orch._store.read_btcp_table("btcp_routes")[0]
    assert row["failure_cause"] is not None
    assert row["finalized_at"] is not None


# ── INV-020: routing validity gates ─────────────────────────────────────────

def test_inv020_route_validity_gates():
    from core.btcp.router import (
        BIBLState, Route, RouteType, route_is_valid, select_optimal_route,
    )
    state = BIBLState(
        nl_scores={1: 0.85}, gas_forecasts={1: 5.0}, gas_reference=31.0,
        cc_coherence={1: 0.9}, mf_scores={1: 0.02}, finality_dist={1: 2.0},
    )

    def route(**kw):
        base = dict(
            route_id="t", entity_id=b"\x01" * 32,
            route_type=RouteType.SINGLE_CHAIN, anchor_chain=1,
            execution_chain=1, gas_total=5.0, finality_confidence=0.95,
            beo_continuity=0.8, cc_coherence=0.9, intent_value=1000.0,
        )
        base.update(kw)
        return Route(**base)

    # happy: the healthy route is valid
    assert route_is_valid(route(), state, validator_count=10)
    # low finality refused
    assert not route_is_valid(route(finality_confidence=0.50), state, 10)
    # low NL refused
    low_nl = BIBLState(nl_scores={1: 0.03}, gas_forecasts={1: 5.0},
                       gas_reference=31.0, cc_coherence={1: 0.9},
                       mf_scores={1: 0.02}, finality_dist={1: 2.0})
    assert not route_is_valid(route(), low_nl, 10)
    # high MF (manipulation) collapses the score → refused
    mani = BIBLState(nl_scores={1: 0.85}, gas_forecasts={1: 5.0},
                     gas_reference=31.0, cc_coherence={1: 0.9},
                     mf_scores={1: 0.98}, finality_dist={1: 2.0})
    assert not route_is_valid(route(), mani, 10)
    # < 3 validators covering the route → refused
    assert not route_is_valid(route(), state, validator_count=2)
    # optimal selection returns None when nothing is valid
    assert select_optimal_route(1000.0, b"\x01" * 32, low_nl, [1], {1: 1}) is None


def test_inv020_ooa_confidence_capped():
    """OOA chains never out-confidence integrated chains (spec §5.2)."""
    ooa = OOAAnchor()
    deep = ooa.compute_ooa_confidence(10_000_000, integrated_confidence=1.0)
    assert deep < 1.0
    assert deep <= ooa.OOA_CONF_MAX + 1e-12
    assert ooa.compute_ooa_threshold(0.55) > 0.55  # penalized threshold


# ── INV-021: balance reservation (Gap E) ────────────────────────────────────

def test_inv021_reservation_blocks_double_spend(tmp_path, monkeypatch):
    """ATTACK: double-execute — two concurrent routes spend one balance."""
    from core.btcp.state_store import BtcpStateStore
    store = BtcpStateStore(state_db=str(tmp_path / "bal.db"))
    monkeypatch.setattr(btcp_router, "_balance_store", store)
    monkeypatch.setattr(btcp_router, "_balance_reservations", {})
    ent = b"\x07" * 32
    try:
        assert btcp_router.reserve_balance(ent, 400.0, 1000.0)
        # second concurrent reservation must not fit
        assert not btcp_router.reserve_balance(ent, 700.0, 1000.0)
        assert btcp_router.reserved_balance(ent) == 400.0
        # release restores capacity
        btcp_router.release_balance(ent, 400.0)
        assert btcp_router.reserve_balance(ent, 700.0, 1000.0)
    finally:
        store.close()


# ── State-machine document conformance (docs truth) ─────────────────────────

def test_state_machine_doc_lists_every_code_state():
    """Every persisted state appears in the canonical transition tables —
    the doc and the code cannot drift apart silently."""
    doc_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "docs", "protocol", "BTCP_STATE_MACHINE.md")
    assert os.path.exists(doc_path), "docs/protocol/BTCP_STATE_MACHINE.md must exist"
    doc = open(doc_path, encoding="utf-8").read()
    for status in RouteStatus:
        assert status.name in doc, f"route state {status.name} missing from the doc"
    for state in EscrowState:
        assert state.name in doc, f"escrow state {state.name} missing from the doc"
    for status in DisputeStatus:
        assert status.name in doc, f"dispute state {status.name} missing from the doc"


def test_invariant_register_covers_every_tested_inv():
    doc_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "docs", "security", "CANONICAL_INVARIANTS.md")
    assert os.path.exists(doc_path), "docs/security/CANONICAL_INVARIANTS.md must exist"
    doc = open(doc_path, encoding="utf-8").read()
    for inv_id in range(1, 23):
        tag = f"INV-{inv_id:03d}"
        assert f"### {tag}" in doc, f"{tag} missing from the invariant register"
