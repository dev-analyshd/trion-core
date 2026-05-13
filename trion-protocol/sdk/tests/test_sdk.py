import sys
sys.path.insert(0, '../src')
from trion_sdk import (
    TRIONClient, BehavioralHash, TRIONSignal, ConfidenceInterval,
    LivingIndex, PlaneBreakdown, connect
)


def _make_bh(input_bytes: bytes, entity_id: str = "test") -> "BehavioralHash":
    """Helper: correctly construct a BH with complement_invariant_hex."""
    import hashlib
    sense_raw     = hashlib.sha3_256(input_bytes + b'\x00').digest()
    anti_raw      = hashlib.sha3_256(input_bytes + b'\xff').digest()
    complement    = bytes(~b & 0xFF for b in sense_raw)
    antisense_raw = bytes(a ^ c for a, c in zip(anti_raw, complement))
    # complement_invariant = NOT(anti_raw) = sense XOR antisense
    invariant     = bytes(~b & 0xFF for b in anti_raw)
    return BehavioralHash(
        entity_id=entity_id,
        sense_hex=sense_raw.hex(),
        antisense_hex=antisense_raw.hex(),
        complement_invariant_hex=invariant.hex(),
        event_type="SWAP",
        magnitude_normalized=0.65,
        chain_id=42161,
        block_hash="0xabc",
    )


def test_bh_verify_valid_pair():
    """BH.verify() must return True for a correctly constructed pair."""
    bh = _make_bh(b"TRION_SDK_TEST_INPUT")
    assert bh.verify(), "Valid BH must verify"
    print(f"[PASS] BH.verify() True for valid pair")


def test_bh_verify_detects_tamper():
    """BH.verify() must return False when sense is tampered."""
    bh = _make_bh(b"TRION_SDK_TAMPER_TEST")
    assert bh.verify(), "Original must verify"

    tampered = BehavioralHash(
        entity_id=bh.entity_id,
        sense_hex=bytes(b ^ (0xFF if i == 0 else 0)
                        for i, b in enumerate(bytes.fromhex(bh.sense_hex))).hex(),
        antisense_hex=bh.antisense_hex,
        complement_invariant_hex=bh.complement_invariant_hex,
        event_type=bh.event_type,
        magnitude_normalized=bh.magnitude_normalized,
        chain_id=bh.chain_id,
        block_hash=bh.block_hash,
    )
    assert not tampered.verify(), "Tampered sense must fail verify"
    print(f"[PASS] BH.verify() False for tampered sense")


def test_trion_signal_validate_ci_none():
    sig = TRIONSignal(
        asset_id="X", signal_type="VALUATION", c_score=0.72,
        phi_adj=0.75, m_adj=0.70, sigma=0.80, k_score=0.0, a_score=0.0,
        ci_95=None, conf_genesis=0.60, tc_valid=True, theta=0.55,
        asset_type="MATURE_PROTOCOL",
    )
    errors = sig.validate()
    assert any("CI_95" in e for e in errors), "None CI_95 must raise validation error"
    print(f"[PASS] validate() catches None CI_95")


def test_trion_signal_validate_ci_ordered():
    ci = ConfidenceInterval(lo=0.70, hi=0.60)  # deliberately wrong order
    sig = TRIONSignal(
        asset_id="X", signal_type="VALUATION", c_score=0.72,
        phi_adj=0.75, m_adj=0.70, sigma=0.80, k_score=0.0, a_score=0.0,
        ci_95=ci, conf_genesis=0.60, tc_valid=True, theta=0.55,
        asset_type="MATURE_PROTOCOL",
    )
    errors = sig.validate()
    assert any("CI_95" in e for e in errors), "Unordered CI_95 must raise validation error"
    print(f"[PASS] validate() catches unordered CI_95")


def test_trion_signal_silence_detected():
    sig = TRIONSignal(
        asset_id="Y", signal_type="SILENCE", c_score=0.30,
        phi_adj=0.20, m_adj=0.15, sigma=0.30, k_score=0.0, a_score=0.0,
        ci_95=ConfidenceInterval(0.20, 0.40), conf_genesis=0.05,
        tc_valid=False, theta=0.55, asset_type="NEW_TOKEN",
    )
    assert sig.is_silence()
    print(f"[PASS] TRIONSignal.is_silence() works")


def test_connect_factory():
    client = connect("http://localhost:5000")
    assert isinstance(client, TRIONClient)
    assert client.base_url == "http://localhost:5000"
    print(f"[PASS] connect() factory returns TRIONClient")


def test_confidence_interval_methods():
    ci = ConfidenceInterval(lo=0.65, hi=0.88)
    assert abs(ci.width() - 0.23) < 1e-6
    assert ci.contains(0.75)
    assert not ci.contains(0.50)
    print(f"[PASS] ConfidenceInterval: width={ci.width():.2f}, contains(0.75)={ci.contains(0.75)}")


def test_all_sdk_classes_importable():
    classes = [TRIONClient, BehavioralHash, TRIONSignal,
               ConfidenceInterval, LivingIndex, PlaneBreakdown]
    for cls in classes:
        assert cls is not None
    print(f"[PASS] All {len(classes)} SDK classes importable")


if __name__ == "__main__":
    test_bh_verify_valid_pair()
    test_bh_verify_detects_tamper()
    test_trion_signal_validate_ci_none()
    test_trion_signal_validate_ci_ordered()
    test_trion_signal_silence_detected()
    test_connect_factory()
    test_confidence_interval_methods()
    test_all_sdk_classes_importable()
    print("\n[SDK] ALL TESTS PASSED")
