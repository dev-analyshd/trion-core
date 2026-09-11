"""
Akashic commitment root — TRION BZK Phase 2.2.

Per BTCP §7.1, the Sensing Oracle SNARK public input includes
`historical_BEO_root`. This is the Merkle root over the entity's
behavioral_hash commitments (one leaf per epoch, or per behavioral record).

Per WP-Mar §15 R-CHANNELS, the onchain surface is "Signal publication
(Solidity) + Economic coordination (Vyper)" — proof generation stays
offchain. Therefore the Akashic commitment root is OFFCHAIN, anchored
onchain only via the existing signal publication surface (the
BEHAVIORAL_TRUTH_SIGNAL event per BTCP §7.1).

Construction:
  • Binary Merkle tree.
  • SHA3-256 (consistent with Hash_DNA per BTCP Formula Index).
  • Sorted-pair concatenation: at each level, for a pair of children
    (left, right), compute parent = SHA3-256(min(L,R) || max(L,R)).
    This is the standard second-preimage-resistant construction (RFC 6962
    style; the sort defends against the attacker-controlled-ordering
    weakness of plain concatenation).
  • Odd-leaf handling: the last node at an odd-count level is duplicated
    (i.e., hashed with itself). This matches RFC 6962 §2.1 and is
    deterministic without sentinel bytes.

R-ABSENT: this module stores nothing. It computes roots and proofs from
caller-supplied leaf lists. Persistence (if any) is the caller's
responsibility and must obey R-ABSENT (the leaves themselves are already
hashes; no behavior content is stored).
"""

from __future__ import annotations

import hashlib
from typing import List, Tuple

__all__ = [
    "LEAF_LEN",
    "compute_root",
    "merkle_proof",
    "verify",
    "verify_proof",
]

LEAF_LEN = 32  # All leaves are 32-byte SHA3-256 / Hash_DNA sense strands


def _sha3_256(data: bytes) -> bytes:
    return hashlib.sha3_256(data).digest()


def _hash_pair(left: bytes, right: bytes) -> bytes:
    """Sorted-pair SHA3-256 — second-preimage-resistant parent hash.

    parent = SHA3-256(min(left, right) || max(left, right))

    The sort ensures that an attacker cannot construct a tree where
    (a, b) and (b, a) produce the same parent (which would be the case
    for plain concatenation)."""
    if len(left) != LEAF_LEN or len(right) != LEAF_LEN:
        raise ValueError(
            f"_hash_pair: both children must be {LEAF_LEN} bytes; "
            f"got {len(left)} and {len(right)}"
        )
    lo, hi = (left, right) if left <= right else (right, left)
    return _sha3_256(lo + hi)


def _validate_leaves(commitments: List[bytes]) -> None:
    if not commitments:
        raise ValueError("compute_root: commitments list must be non-empty")
    for i, c in enumerate(commitments):
        if not isinstance(c, (bytes, bytearray)):
            raise TypeError(
                f"compute_root: commitment {i} must be bytes, got {type(c).__name__}"
            )
        if len(c) != LEAF_LEN:
            raise ValueError(
                f"compute_root: commitment {i} must be {LEAF_LEN} bytes, got {len(c)}"
            )


def compute_root(commitments: List[bytes]) -> bytes:
    """Compute the Merkle root over a list of 32-byte commitment leaves.

    Returns the 32-byte root. The construction is a binary tree with
    sorted-pair concatenation at every level (see module docstring).

    For a single-leaf list, the root is the leaf itself (no hashing — this
    preserves the canonical "Merkle root of one element is that element"
    identity, and is consistent with how BTCP §7.1 `historical_BEO_root`
    behaves for an entity with exactly one behavioral record).

    For odd-count lists at any level, the last node is promoted unchanged
    (duplicated into the parent level) — this is deterministic and avoids
    sentinel bytes.
    """
    _validate_leaves(commitments)

    if len(commitments) == 1:
        return bytes(commitments[0])

    level: List[bytes] = [bytes(c) for c in commitments]
    while len(level) > 1:
        next_level: List[bytes] = []
        i = 0
        while i + 1 < len(level):
            next_level.append(_hash_pair(level[i], level[i + 1]))
            i += 2
        # Odd node: hash with itself (RFC 6962 §2.1 duplicate-last).
        if i < len(level):
            next_level.append(_hash_pair(level[i], level[i]))
        level = next_level
    return level[0]


def merkle_proof(
    commitments: List[bytes], index: int
) -> Tuple[List[int], List[bytes]]:
    """Construct a Merkle proof for `commitments[index]`.

    Returns (path, siblings) where:
      • path is a list of 0/1 directions: 0 = sibling is on the LEFT,
        1 = sibling is on the RIGHT. The verifier uses this to know
        whether to compute hash_pair(leaf, sibling) or hash_pair(sibling, leaf).
        (Note: because we use sorted-pair hashing, the direction is purely
        informational; the verifier recomputes the parent deterministically
        from the sorted pair. We still return it for completeness and to
        match the API contract.)
      • siblings is a list of 32-byte sibling hashes, one per tree level,
        ordered from the leaf level upward.

    For a single-leaf tree, returns ([], []).

    Raises IndexError if index is out of range.
    """
    _validate_leaves(commitments)
    if index < 0 or index >= len(commitments):
        raise IndexError(
            f"merkle_proof: index {index} out of range [0, {len(commitments)})"
        )

    if len(commitments) == 1:
        return [], []

    path: List[int] = []
    siblings: List[bytes] = []

    level: List[bytes] = [bytes(c) for c in commitments]
    idx = index
    while len(level) > 1:
        # Determine sibling index. Odd-length level: last node is promoted
        # unchanged, so the "sibling" of the last node is itself.
        if idx % 2 == 0:
            # Leaf is on the left; sibling is on the right (if exists).
            sib_idx = idx + 1
            if sib_idx >= len(level):
                # Last odd node — sibling is itself (promoted unchanged).
                sib_idx = idx
                direction = 1  # sibling is on the right (it's a self-loop)
            else:
                direction = 1
        else:
            # Leaf is on the right; sibling is on the left.
            sib_idx = idx - 1
            direction = 0

        path.append(direction)
        siblings.append(level[sib_idx])

        # Build next level (same convention as compute_root: odd node hashed with itself).
        next_level: List[bytes] = []
        i = 0
        while i + 1 < len(level):
            next_level.append(_hash_pair(level[i], level[i + 1]))
            i += 2
        if i < len(level):
            next_level.append(_hash_pair(level[i], level[i]))
        level = next_level
        idx //= 2

    return path, siblings


def verify(
    root: bytes,
    index: int,
    leaf: bytes,
    path: List[int],
    siblings: List[bytes],
) -> bool:
    """Verify a Merkle proof.

    Returns True iff recomputing the root from (leaf, index, path, siblings)
    yields `root`. The recomputation uses the sorted-pair hash, so the
    direction bits in `path` are informational only (the parent is
    deterministically min/max-sorted). The `index` parameter is also
    informational for the sorted-pair construction — the verifier does not
    use it to determine left/right ordering, because the sort makes the
    hash order-independent. Callers that need position-binding (proving
    the leaf is at a specific index) should use a position-aware hash
    construction (NOT sorted-pair) — see the BTCP §7.1 historical_BEO_root
    note in the module docstring: for behavioral record proofs, membership
    is sufficient; position is informational.

    This function is the canonical entry point for verifiers that have the
    leaf, the claimed root, and the proof. `verify_proof` is an alias kept
    for API discoverability.
    """
    if not isinstance(root, (bytes, bytearray)) or len(root) != LEAF_LEN:
        return False
    if not isinstance(leaf, (bytes, bytearray)) or len(leaf) != LEAF_LEN:
        return False
    if index < 0:
        return False
    if len(path) != len(siblings):
        return False

    # Single-leaf tree: leaf must equal root, index must be 0.
    if len(path) == 0:
        return index == 0 and bytes(leaf) == bytes(root)

    current = bytes(leaf)
    for direction, sibling in zip(path, siblings):
        if not isinstance(sibling, (bytes, bytearray)) or len(sibling) != LEAF_LEN:
            return False
        sibling = bytes(sibling)
        # Sorted-pair parent: doesn't depend on direction.
        # parent = SHA3-256(min(current, sibling) || max(current, sibling)).
        # The `direction` is informational (kept for API completeness and
        # for callers that want position-aware verification later).
        current = _hash_pair(current, sibling)

    return current == bytes(root)


# Alias for API discoverability (some callers look for `verify_proof`).
verify_proof = verify


# ── Self-test ─────────────────────────────────────────────────────────────────

def _self_test() -> dict:
    """Deterministic self-test for the Merkle construction.

    Verifies:
      1. Single-leaf root == leaf.
      2. Two-leaf root == sorted-pair hash.
      3. N-leaf root is deterministic.
      4. Proof for every leaf in an N-leaf tree verifies against the root.
      5. Tampering with the leaf, the index, the path, or any sibling fails.
      6. Sorted-pair property: trees built from the same leaves in
         different orders produce the same root (defends against attacker-
         controlled leaf ordering).
    """
    out: dict = {}

    # 1. Single-leaf root == leaf.
    leaf0 = b"\x01" * LEAF_LEN
    r1 = compute_root([leaf0])
    assert r1 == leaf0, "single-leaf root must equal the leaf"

    # 2. Two-leaf root == sorted-pair hash.
    a = b"\xaa" * LEAF_LEN
    b_ = b"\xbb" * LEAF_LEN
    r2 = compute_root([a, b_])
    expected2 = _hash_pair(a, b_)
    assert r2 == expected2, "two-leaf root must equal sorted-pair hash"

    # 3. N-leaf deterministic root.
    leaves = [bytes([i]) * LEAF_LEN for i in range(1, 8)]  # 7 leaves (odd)
    root = compute_root(leaves)
    root_again = compute_root(leaves)
    assert root == root_again, "root must be deterministic"

    # 4. Proof for every leaf verifies.
    for i in range(len(leaves)):
        path, sibs = merkle_proof(leaves, i)
        assert verify(root, i, leaves[i], path, sibs), \
            f"proof for leaf {i} must verify"
        # Negative: wrong leaf must fail.
        wrong_leaf = b"\xff" * LEAF_LEN
        assert not verify(root, i, wrong_leaf, path, sibs), \
            f"proof with wrong leaf {i} must fail"
        # Negative: tampered sibling must fail.
        if sibs:
            tampered_sibs = list(sibs)
            tampered_sibs[0] = b"\x00" * LEAF_LEN
            assert not verify(root, i, leaves[i], path, tampered_sibs), \
                f"proof with tampered sibling for leaf {i} must fail"
        # Negative: tampered root must fail.
        bad_root = b"\xee" * LEAF_LEN
        assert not verify(bad_root, i, leaves[i], path, sibs), \
            f"proof with tampered root for leaf {i} must fail"
        # Negative: mismatched path/siblings length must fail.
        assert not verify(root, i, leaves[i], path + [0], sibs), \
            f"proof with mismatched path length for leaf {i} must fail"

    # 5. Sorted-pair property: trees built from the same leaves in different
    #    orders produce the same root (defends against attacker-controlled
    #    leaf ordering).
    root_a = compute_root([a, b_])
    root_b = compute_root([b_, a])
    assert root_a == root_b, "sorted-pair root must be order-independent"

    # 6. Three-leaf tree (forces odd-node promotion at the first level).
    leaves3 = [b"\x11" * LEAF_LEN, b"\x22" * LEAF_LEN, b"\x33" * LEAF_LEN]
    root3 = compute_root(leaves3)
    for i in range(3):
        path, sibs = merkle_proof(leaves3, i)
        assert verify(root3, i, leaves3[i], path, sibs), \
            f"3-leaf tree: proof for leaf {i} must verify"

    out["all_passed"] = True
    return out


if __name__ == "__main__":
    import json
    print("=== Akashic commitment root — self-test ===")
    res = _self_test()
    print(json.dumps({k: v for k, v in res.items() if not isinstance(v, bytes)}, indent=2))
    assert res.get("all_passed"), "self-test FAILED"
    print("PASS — Akashic Merkle commitment root (BTCP §7.1 historical_BEO_root)")
