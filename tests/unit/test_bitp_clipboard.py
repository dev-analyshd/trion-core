"""tests/unit/test_bitp_clipboard.py — Akashic clipboard tier (W3-D).

W2-F handoff (worklog): "py BITP expiry opt-in (rust + clipboard enforce
unconditionally)" — the W3-D remediation is the AkashicClipboard tier in
core/btcp/modules.py:

  * spec §5.1 three-phase flow: CUT (post commitment) → MATCH (find
    complement) → PASTE (remove both);
  * EXPIRY ENFORCED UNCONDITIONALLY: ``now`` is a REQUIRED match argument;
    expired seeking intents match nothing, expired candidates are pruned
    and never served (INV-007);
  * anti-wash: self-matches (same entity on both sides) never match;
  * §17 commitment = H(intent || behavioral_proof_root || nonce) — a
    different nonce or proof root is a different commitment (rust
    bitp_matcher.rs::execute_cut parity);
  * BITPIntent.behavioral_proof_root (§17 rust-parity field) is NOT part
    of the §4.1 hash();
  * optional store write-through (W3-N record_bitp_clipboard call-site):
    CUT → POSTED, MATCH → MATCHED (both sides, counterparty_hash +
    matched_at + materialized chain_b), PASTE → FILLED, prune → EXPIRED;
  * store failure is tolerated (live clipboard semantics unaffected).
"""

import pytest

from core.btcp.modules import BITPIntent, BITPMatcher, AkashicClipboard
from core.btcp.state_store import BtcpStateStore


A_ID = b"\x01" * 8
B_ID = b"\x02" * 8
ASSET_X = b"\xaa" * 20
ASSET_Y = b"\xbb" * 20
NOW = 1_000.0
DL = 2_000


def _intent(entity=A_ID, asset_in=ASSET_X, asset_out=ASSET_Y, chain=1,
            magnitude=100.0, deadline=DL, **kw):
    return BITPIntent(
        entity_id=entity, asset_in=asset_in, asset_out=asset_out,
        magnitude=magnitude, chain_id=chain, deadline=deadline, **kw
    )


def _complement(entity=B_ID, chain=137, magnitude=100.0, deadline=DL):
    return _intent(entity=entity, asset_in=ASSET_Y, asset_out=ASSET_X,
                   chain=chain, magnitude=magnitude, deadline=deadline)


# ─── CUT / MATCH / PASTE lifecycle ────────────────────────────────────────────


class TestLifecycle:
    def test_cut_returns_commitment_and_stores_entry(self):
        cb = AkashicClipboard()
        ia = _intent()
        commitment = cb.execute_cut(ia)
        assert isinstance(commitment, bytes) and len(commitment) == 32
        assert cb.clipboard_size() == 1

    def test_match_finds_complement_and_paste_removes_both(self):
        cb = AkashicClipboard()
        ca = cb.execute_cut(_intent())
        cb.execute_cut(_complement())
        matched = cb.find_complement(_intent(), now=NOW)
        assert matched is not None and matched.entity_id == B_ID
        assert cb.clipboard_size() == 2          # match does not consume
        assert cb.execute_paste(ca, cb._commitment(matched)) is True
        assert cb.clipboard_size() == 0

    def test_paste_requires_both_live(self):
        cb = AkashicClipboard()
        ca = cb.execute_cut(_intent())
        cb.execute_cut(_complement())
        matched = cb.find_complement(_intent(), now=NOW)
        cb.execute_paste(ca, cb._commitment(matched))
        assert cb.execute_paste(ca, cb._commitment(matched)) is False

    def test_paste_unknown_commitments_is_false(self):
        cb = AkashicClipboard()
        assert cb.execute_paste(b"\x00" * 32, b"\x11" * 32) is False

    def test_no_complement_returns_none(self):
        cb = AkashicClipboard()
        cb.execute_cut(_intent())                # same direction — no complement
        assert cb.find_complement(_intent(entity=B_ID), now=NOW) is None

    def test_assets_untouched_by_cut_match_paste(self):
        """The clipboard moves commitments, never assets (spec §5.1)."""
        cb = AkashicClipboard()
        cb.execute_cut(_intent())
        cb.execute_cut(_complement())
        matched = cb.find_complement(_intent(), now=NOW)
        assert matched is not None
        # nothing in the tier touches chains — matcher state only
        assert cb.clipboard_size() == 2


# ─── UNCONDITIONAL expiry enforcement (W2-F) ──────────────────────────────────


class TestExpiryEnforced:
    def test_now_is_required(self):
        """Rust parity: the storage tier takes ``now`` — no opt-in path."""
        import inspect
        sig = inspect.signature(AkashicClipboard.find_complement)
        assert "now" in sig.parameters
        assert sig.parameters["now"].default is inspect.Parameter.empty

    def test_expired_seeking_intent_matches_nothing(self):
        cb = AkashicClipboard()
        cb.execute_cut(_complement())            # live candidate
        expired = _intent(entity=B_ID, deadline=500)
        assert cb.find_complement(expired, now=NOW) is None

    def test_expired_candidates_are_pruned_never_served(self):
        cb = AkashicClipboard()
        cb.execute_cut(_complement(deadline=500))    # expired candidate
        cb.execute_cut(_complement(entity=b"\x03" * 8, deadline=500))
        fresh_seeker = _intent(entity=b"\x04" * 8)
        assert cb.find_complement(fresh_seeker, now=NOW) is None
        assert cb.clipboard_size() == 0            # both pruned
        assert cb.expired_dropped == 2

    def test_expiry_boundary_is_inclusive(self):
        """deadline == now ⇒ expired (now >= deadline), mirrors rust."""
        cb = AkashicClipboard()
        cb.execute_cut(_complement(deadline=int(NOW)))
        assert cb.find_complement(_intent(), now=NOW) is None

    def test_unexpired_matches_at_boundary_minus_one(self):
        cb = AkashicClipboard()
        cb.execute_cut(_complement(deadline=DL))
        assert cb.find_complement(_intent(), now=DL - 1) is not None

    def test_clipboard_size_prunes_with_now(self):
        cb = AkashicClipboard()
        cb.execute_cut(_complement(deadline=500))
        assert cb.clipboard_size(now=NOW) == 0
        assert cb.expired_dropped == 1

    def test_pure_matcher_keeps_optional_time(self):
        """The pure BITPMatcher stays a legacy-compatible pure function;
        enforcement lives in the clipboard (storage) tier."""
        import inspect
        sig = inspect.signature(BITPMatcher.find_complement)
        assert sig.parameters["current_time"].default is None
        m = BITPMatcher()
        assert m.find_complement(_intent(), [_complement(deadline=500)]) \
            is not None   # pure path: no time supplied, no expiry check


# ─── Anti-wash (spec §5.1, INV-007) ───────────────────────────────────────────


class TestAntiWash:
    def test_self_match_never_served(self):
        cb = AkashicClipboard()
        cb.execute_cut(_complement(entity=A_ID, chain=137))  # same entity
        assert cb.find_complement(_intent(), now=NOW) is None


# ─── §17 commitment binding ───────────────────────────────────────────────────


class TestCommitment:
    def test_commitment_is_sha3_256(self):
        cb = AkashicClipboard()
        assert len(cb._commitment(_intent())) == 32

    def test_different_nonce_different_commitment(self):
        cb = AkashicClipboard()
        assert cb._commitment(_intent(nonce=1)) != cb._commitment(_intent(nonce=2))

    def test_different_proof_root_different_commitment(self):
        """§17: the behavioral proof root binds the commitment (rust
        BITPIntentData.behavioral_proof_root parity)."""
        cb = AkashicClipboard()
        root_a = b"\x05" * 32
        root_b = b"\x06" * 32
        assert cb._commitment(_intent(behavioral_proof_root=root_a)) \
            != cb._commitment(_intent(behavioral_proof_root=root_b))

    def test_default_proof_root_is_zero_root(self):
        """None ≡ rust H256::default() — the 64-hex-zero segment."""
        cb = AkashicClipboard()
        no_root = cb._commitment(_intent())
        zero_root = cb._commitment(_intent(behavioral_proof_root=b"\x00" * 32))
        assert no_root == zero_root

    def test_different_fields_different_commitment(self):
        cb = AkashicClipboard()
        base = cb._commitment(_intent())
        assert cb._commitment(_intent(magnitude=101.0)) != base
        assert cb._commitment(_intent(deadline=DL + 1)) != base
        assert cb._commitment(_intent(btcp_version="1.1.0")) != base

    def test_chain_id_is_not_a_commitment_segment(self):
        """Rust parity: the 8-segment commitment text has no chain field
        (rust BITPIntentData carries none) — chain_id is a legacy py
        routing field, deliberately outside the §17 commitment."""
        cb = AkashicClipboard()
        assert cb._commitment(_intent(chain=1)) == cb._commitment(_intent(chain=4))

    def test_proof_root_not_in_section_4_1_hash(self):
        """hash() pins the §4.1 field set — the proof root enters only via
        the §17 clipboard commitment (append-only hash policy)."""
        a = _intent()
        b = _intent(behavioral_proof_root=b"\x07" * 32)
        assert a.hash() == b.hash()
        assert a.behavioral_proof_root is None
        assert b.behavioral_proof_root == b"\x07" * 32


# ─── Store write-through (W3-N record_bitp_clipboard call-site) ──────────────


class _BrokenStore:
    def record_bitp_clipboard(self, *a, **k):
        raise RuntimeError("store down")


def _rows(store):
    return {r["commitment_hash"]: r for r in store.read_btcp_table("bitp_clipboard")}


class TestStoreWriteThrough:
    def test_cut_records_posted_row(self, tmp_path):
        store = BtcpStateStore(state_db=str(tmp_path / "s.db"))
        try:
            cb = AkashicClipboard(store=store)
            ia = _intent()
            commitment = cb.execute_cut(ia)
            rows = _rows(store)
            row = rows[commitment.hex()]
            assert row["status"] == "POSTED"
            assert row["entity_id"] == A_ID.hex()
            assert row["asset_x"] == ASSET_X.hex()
            assert row["asset_y"] == ASSET_Y.hex()
            assert row["chain_a"] == 1
            # the target chain is genuinely unknown at CUT (matcher picks
            # it at MATCH) — documented sentinel, not a registered chain
            assert row["chain_b"] == AkashicClipboard.CHAIN_B_UNDETERMINED
            assert row["intent_hash"] == ia.hash().hex()
            assert row["counterparty_hash"] is None
            assert row["matched_at"] is None
        finally:
            store.close()

    def test_proof_root_column_written(self, tmp_path):
        store = BtcpStateStore(state_db=str(tmp_path / "s.db"))
        try:
            cb = AkashicClipboard(store=store)
            root = b"\x09" * 32
            commitment = cb.execute_cut(_intent(behavioral_proof_root=root))
            assert _rows(store)[commitment.hex()]["behavioral_proof_root"] \
                == root.hex()
            # None root → NULL column (honest absent, not zeros)
            commitment2 = cb.execute_cut(_intent(entity=B_ID))
            assert _rows(store)[commitment2.hex()]["behavioral_proof_root"] \
                is None
        finally:
            store.close()

    def test_match_records_both_sides_matched(self, tmp_path):
        store = BtcpStateStore(state_db=str(tmp_path / "s.db"))
        try:
            cb = AkashicClipboard(store=store)
            ca = cb.execute_cut(_intent())
            matched = _complement()
            cbm = cb.execute_cut(matched)
            ia = _intent()
            found = cb.find_complement(ia, now=NOW)
            assert found is not None
            rows = _rows(store)
            row_a, row_b = rows[ca.hex()], rows[cbm.hex()]
            assert row_a["status"] == "MATCHED" and row_b["status"] == "MATCHED"
            assert row_a["counterparty_hash"] == cbm.hex()
            assert row_b["counterparty_hash"] == ca.hex()
            assert row_a["matched_at"] == NOW and row_b["matched_at"] == NOW
            # chain_b materialized with the real complement chain
            assert row_a["chain_b"] == 137
            assert row_b["chain_b"] == 1
        finally:
            store.close()

    def test_match_from_unposted_seeker_updates_candidate_only(self, tmp_path):
        store = BtcpStateStore(state_db=str(tmp_path / "s.db"))
        try:
            cb = AkashicClipboard(store=store)
            cbm = cb.execute_cut(_complement())
            cb.find_complement(_intent(entity=b"\x77" * 8), now=NOW)
            rows = _rows(store)
            assert len(rows) == 1                    # no fabricated seeker row
            assert rows[cbm.hex()]["status"] == "MATCHED"
        finally:
            store.close()

    def test_paste_records_filled(self, tmp_path):
        store = BtcpStateStore(state_db=str(tmp_path / "s.db"))
        try:
            cb = AkashicClipboard(store=store)
            ca = cb.execute_cut(_intent())
            cbm = cb.execute_cut(_complement())
            cb.find_complement(_intent(), now=NOW)
            assert cb.execute_paste(ca, cbm) is True
            rows = _rows(store)
            assert rows[ca.hex()]["status"] == "FILLED"
            assert rows[cbm.hex()]["status"] == "FILLED"
        finally:
            store.close()

    def test_prune_records_expired(self, tmp_path):
        store = BtcpStateStore(state_db=str(tmp_path / "s.db"))
        try:
            cb = AkashicClipboard(store=store)
            cc = cb.execute_cut(_complement(deadline=500))
            cb.find_complement(_intent(), now=NOW)   # prunes the expired entry
            assert _rows(store)[cc.hex()]["status"] == "EXPIRED"
        finally:
            store.close()

    def test_broken_store_does_not_break_the_clipboard(self, capsys):
        cb = AkashicClipboard(store=_BrokenStore())
        ca = cb.execute_cut(_intent())
        cb.execute_cut(_complement())
        matched = cb.find_complement(_intent(), now=NOW)
        assert matched is not None
        assert cb.execute_paste(ca, cb._commitment(matched)) is True
        assert cb.clipboard_size() == 0
        err = capsys.readouterr().err
        assert "bitp_clipboard row write failed" in err

    def test_no_store_is_memory_only(self):
        cb = AkashicClipboard()
        assert cb._store is None
        cb.execute_cut(_intent())
        assert cb.clipboard_size() == 1
