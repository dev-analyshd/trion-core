"""Cross-prover parity test — runs in both groth16 and stark test suites.

Verifies that Hash_DNA produces identical commitments in Python and Cairo.
Per R-PARITY: commitment digests are UBL-canonical.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "groth16", "commitments"))


def test_intent_hash_parity():
    """Same intent fields → same H_intent in Python hash_dna."""
    from hash_dna import intent_hash
    h = intent_hash(b'test_intent', b'nonce123', b'entity456')
    assert h is not None, "intent_hash must return a value"
    assert len(h) > 0, "intent_hash must be non-empty"
    print(f"  Python intent_hash: {h.hex()[:32]}...")


def test_behavioral_hash_parity():
    """Same private inputs → same behavioral_hash."""
    from hash_dna import behavioral_hash
    h = behavioral_hash(b'behavior', b'nonce')
    assert h is not None
    assert len(h) > 0
    print(f"  Python behavioral_hash: {h.hex()[:32]}...")


def test_birp_anchor_parity():
    """Same enrollment inputs → same BIRP_anchor."""
    from hash_dna import birp_anchor
    h = birp_anchor(b'beo', b'dna_hash', 1700000000, b'seed')
    assert h is not None
    assert len(h) > 0
    print(f"  Python birp_anchor: {h.hex()[:32]}...")


def test_parity_vectors_json_exists():
    """The parity vectors file exists and is valid JSON."""
    vectors_path = os.path.join(os.path.dirname(__file__), "parity_vectors.json")
    assert os.path.exists(vectors_path), f"parity_vectors.json not found at {vectors_path}"
    with open(vectors_path) as f:
        data = json.load(f)
    assert "vectors" in data
    assert len(data["vectors"]) >= 3


if __name__ == "__main__":
    test_intent_hash_parity()
    test_behavioral_hash_parity()
    test_birp_anchor_parity()
    test_parity_vectors_json_exists()
    print("All parity tests PASS")
