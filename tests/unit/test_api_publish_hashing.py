"""SEC-20 regression — on-chain publication digests are canonical SHA3-256.

api/blockchain.py historically keyed the on-chain oracle entity id
(_entity_to_bytes32) and the public commitment (_commitment) with SHA-256,
while the canonical behavioral-hash pipeline is SHA3-256 everywhere
(core/primitives/behavioral_hash.py, indexers trion-common hash_dna.rs).
An on-chain "signal for entity X" therefore matched no canonical BEO
ledger entry for X. These vectors pin the remediated digests — SHA3-256
of the exact publication preimages — so the Flask publish path cannot
silently diverge from the canonical pipeline again.

Run: pytest tests/unit/test_api_publish_hashing.py -q
"""
import hashlib

from api.blockchain import ChainRelay

# (entity_id, coherence score, unix ts) — one EVM-style id, one strict alias.
VECTORS = [
    {
        "id": "pub_v1_evm_style_entity",
        "entity_id": "0x" + "11" * 20,
        "score": 0.876543,
        "ts": 1_700_000_000,
        "expected_entity_sha3_256":
            "639e8d60048f4dfa01715b6d4f46fdd4013401e135b95234ec9755df9d7527be",
        "expected_commitment_sha3_256":
            "6479daefc6fcba6473e1384f97f2ee585c4787202382f72893285ac3060ea6a1",
    },
    {
        "id": "pub_v2_strict_alias_entity",
        "entity_id": "akashic-observer-07",
        "score": 0.42,
        "ts": 1_234_567_890,
        "expected_entity_sha3_256":
            "52e641b81fcffa4a583d535254140468a3af67059543898bf4ad650e57b1280f",
        "expected_commitment_sha3_256":
            "f56e9a050d7abd225b9de3b302e9a0d687b75d6a47e095e4da3f0bfc9ce1bef7",
    },
]


def _relay() -> ChainRelay:
    """ChainRelay without the __init__ network boot (unit-test fast path —
    the digest helpers are pure functions of their arguments)."""
    return object.__new__(ChainRelay)


def test_entity_id_digest_is_pinned_sha3_256():
    relay = _relay()
    for vec in VECTORS:
        got = relay._entity_to_bytes32(vec["entity_id"])
        assert got.hex() == vec["expected_entity_sha3_256"], (
            f"{vec['id']}: on-chain entity id digest drifted — the publish "
            "path must stay keyed to the canonical SHA3-256 pipeline")
        assert len(got) == 32


def test_commitment_digest_is_pinned_sha3_256():
    relay = _relay()
    for vec in VECTORS:
        got = relay._commitment(vec["entity_id"], vec["score"], vec["ts"])
        assert got.hex() == vec["expected_commitment_sha3_256"], (
            f"{vec['id']}: public commitment digest drifted from the pinned "
            "SHA3-256 corpus")
        assert len(got) == 32


def test_commitment_preimage_is_the_public_form():
    """The commitment is SHA3-256 of "{entity}:{score:.6f}:{ts//300}" — the
    time-bucketed, behavior-free preimage the docstring promises."""
    relay = _relay()
    for vec in VECTORS:
        preimage = (f"{vec['entity_id']}:{vec['score']:.6f}"
                    f":{vec['ts'] // 300}").encode()
        assert relay._commitment(vec["entity_id"], vec["score"], vec["ts"]) \
            == hashlib.sha3_256(preimage).digest()


def test_digests_diverge_from_the_legacy_sha256_identity():
    """SEC-20 specifically: the SHA-256 shadow identity (which matched no
    canonical BEO entry) must NOT come back."""
    relay = _relay()
    for vec in VECTORS:
        legacy = hashlib.sha256(vec["entity_id"].encode()).digest()
        assert relay._entity_to_bytes32(vec["entity_id"]) != legacy
        legacy_commit = hashlib.sha256(
            (f"{vec['entity_id']}:{vec['score']:.6f}:{vec['ts'] // 300}")
            .encode()).digest()
        assert relay._commitment(vec["entity_id"], vec["score"], vec["ts"]) \
            != legacy_commit


def test_time_bucket_bounds_the_commitment():
    """Same 300s bucket → same commitment; next bucket → different (the
    commitment rotates per time window by construction)."""
    relay = _relay()
    eid, score, ts = "bucket-entity", 0.5, 999_999_900   # exact bucket edge
    assert relay._commitment(eid, score, ts) \
        == relay._commitment(eid, score, ts + 299)
    assert relay._commitment(eid, score, ts) \
        != relay._commitment(eid, score, ts + 300)
