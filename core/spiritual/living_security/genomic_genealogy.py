"""
TRION Protocol — Validator Genomic Genealogy Graph
Primitive 2 extension: Behavioral Causal Keys — cross-validator lineage tracking.

Each validator has a GenomicKey that evolves across generations.
This module tracks the genealogy DAG of validator keys:
  - Genesis keys (generation 0) are root nodes
  - Key rotation creates a new generation (child node)
  - Lineage distance between validators informs trust weighting
  - Byzantine validators' offspring inherit reduced trust

Genomic Key Evolution Rule (from whitepaper Primitive 2):
  Key_gen_N = H(Key_gen_{N-1} || rotation_trigger || block_hash || validator_sig)

Genealogy properties:
  - Depth:       longer lineage = more behavioral history = higher base trust
  - Width:       number of descendants = influence score
  - Divergence:  how far two validators' lineage has forked
  - Contamination: if ancestor was slashed, contamination propagates

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


# ── Constants ─────────────────────────────────────────────────────────────────

MAX_GENEALOGY_DEPTH         = 1000     # maximum generations tracked
SLASH_CONTAMINATION_DECAY   = 0.5     # per-hop contamination decay factor
LINEAGE_TRUST_BONUS_PER_GEN = 0.005  # per generation depth bonus (capped)
MAX_LINEAGE_TRUST_BONUS     = 0.20   # cap on lineage trust bonus
DIVERGENCE_THRESHOLD        = 10     # generations of divergence = unrelated


# ── Genomic Key Node ──────────────────────────────────────────────────────────

@dataclass
class GenomicKeyNode:
    """
    One node in the validator genomic genealogy DAG.
    Represents a single key generation for a validator.
    """
    node_id:           str         # unique: validator_id + ":" + str(generation)
    validator_id:      str
    generation:        int         # 0 = genesis
    key_hash:          str         # hex — H(prev_key || trigger || block_hash || sig)
    parent_node_id:    Optional[str]
    created_at:        float
    block_number:      int
    rotation_trigger:  str         # "GENESIS", "SCHEDULED", "THREAT", "RECOVERY"
    slashed:           bool = False
    slash_reason:      Optional[str] = None
    contamination:     float = 0.0  # [0, 1] inherited slash contamination


# ── Genealogy DAG ─────────────────────────────────────────────────────────────

class GenomicGenealogyGraph:
    """
    Directed Acyclic Graph of validator genomic key lineage.

    Nodes:   GenomicKeyNode (one per validator per generation)
    Edges:   parent → child (key rotation event)

    Queries:
      - lineage_depth(validator_id) → int
      - common_ancestor(v1, v2) → Optional[GenomicKeyNode]
      - lineage_divergence(v1, v2) → int (generations since common ancestor)
      - contamination_score(validator_id) → float
      - trust_modifier(validator_id) → float  (additive bonus from lineage)
      - descendants(validator_id) → List[str]
    """

    def __init__(self):
        self._nodes:     Dict[str, GenomicKeyNode]       = {}  # node_id → node
        self._validator_chain: Dict[str, List[str]]      = {}  # validator_id → [node_ids] ordered
        self._children:  Dict[str, List[str]]            = {}  # node_id → [child_node_ids]

    # ── Key Registration ──────────────────────────────────────────────────────

    def register_genesis_key(
        self,
        validator_id:  str,
        key_material:  bytes,
        block_number:  int = 0,
    ) -> GenomicKeyNode:
        """Register a genesis key (generation 0) for a new validator."""
        key_hash = hashlib.sha3_256(
            key_material + validator_id.encode() + b"GENESIS"
        ).hexdigest()

        node_id  = f"{validator_id}:0"
        node = GenomicKeyNode(
            node_id          = node_id,
            validator_id     = validator_id,
            generation       = 0,
            key_hash         = key_hash,
            parent_node_id   = None,
            created_at       = time.time(),
            block_number     = block_number,
            rotation_trigger = "GENESIS",
        )
        self._nodes[node_id] = node
        self._validator_chain[validator_id] = [node_id]
        self._children[node_id] = []
        return node

    def rotate_key(
        self,
        validator_id:     str,
        rotation_trigger: str,
        block_hash:       str,
        validator_sig:    bytes,
        block_number:     int = 0,
    ) -> Optional[GenomicKeyNode]:
        """
        Rotate a validator's genomic key, creating a new generation.
        Key_gen_N = H(Key_gen_{N-1} || trigger || block_hash || sig)
        """
        chain = self._validator_chain.get(validator_id)
        if not chain:
            return None

        parent_node_id  = chain[-1]
        parent          = self._nodes[parent_node_id]
        new_generation  = parent.generation + 1

        if new_generation > MAX_GENEALOGY_DEPTH:
            return None

        new_key_hash = hashlib.sha3_256(
            bytes.fromhex(parent.key_hash) +
            rotation_trigger.encode() +
            block_hash.encode() +
            validator_sig
        ).hexdigest()

        # Inherit contamination (decays per hop)
        inherited_contamination = parent.contamination * SLASH_CONTAMINATION_DECAY

        node_id = f"{validator_id}:{new_generation}"
        node = GenomicKeyNode(
            node_id          = node_id,
            validator_id     = validator_id,
            generation       = new_generation,
            key_hash         = new_key_hash,
            parent_node_id   = parent_node_id,
            created_at       = time.time(),
            block_number     = block_number,
            rotation_trigger = rotation_trigger,
            contamination    = inherited_contamination,
        )

        self._nodes[node_id] = node
        chain.append(node_id)
        self._children.setdefault(parent_node_id, []).append(node_id)
        self._children[node_id] = []
        return node

    # ── Slashing ──────────────────────────────────────────────────────────────

    def slash_validator(
        self,
        validator_id: str,
        reason:       str,
    ) -> int:
        """
        Mark current key as slashed. Contamination = 1.0.
        Propagates to all descendant nodes with decay.
        Returns number of nodes contaminated.
        """
        chain = self._validator_chain.get(validator_id)
        if not chain:
            return 0

        current_node_id = chain[-1]
        current         = self._nodes[current_node_id]
        current.slashed      = True
        current.slash_reason = reason
        current.contamination = 1.0

        contaminated = self._propagate_contamination(current_node_id, 1.0, visited=set())
        return contaminated

    def _propagate_contamination(
        self,
        node_id:     str,
        contamination: float,
        visited:     Set[str],
    ) -> int:
        """DFS propagation of slash contamination through descendants."""
        if node_id in visited or contamination < 0.01:
            return 0
        visited.add(node_id)

        count = 0
        for child_id in self._children.get(node_id, []):
            child = self._nodes.get(child_id)
            if child:
                child_contamination = contamination * SLASH_CONTAMINATION_DECAY
                child.contamination = max(child.contamination, child_contamination)
                count += 1
                count += self._propagate_contamination(child_id, child_contamination, visited)
        return count

    # ── Lineage Queries ───────────────────────────────────────────────────────

    def lineage_depth(self, validator_id: str) -> int:
        """Number of generations for this validator (0 = genesis only)."""
        chain = self._validator_chain.get(validator_id, [])
        return len(chain) - 1 if chain else 0

    def current_node(self, validator_id: str) -> Optional[GenomicKeyNode]:
        """Return the most recent key node for this validator."""
        chain = self._validator_chain.get(validator_id, [])
        if not chain:
            return None
        return self._nodes.get(chain[-1])

    def lineage_path(self, validator_id: str) -> List[GenomicKeyNode]:
        """Full lineage path from genesis to current generation."""
        chain = self._validator_chain.get(validator_id, [])
        return [self._nodes[nid] for nid in chain if nid in self._nodes]

    def common_ancestor(
        self,
        validator_a: str,
        validator_b: str,
    ) -> Optional[GenomicKeyNode]:
        """
        Find the most recent common ancestor between two validators.
        Common ancestry indicates validators originated from the same key ceremony.
        """
        ancestors_a: Set[str] = set()
        for nid in self._validator_chain.get(validator_a, []):
            node = self._nodes.get(nid)
            while node:
                ancestors_a.add(node.key_hash)
                if node.parent_node_id:
                    node = self._nodes.get(node.parent_node_id)
                else:
                    break

        for nid in reversed(self._validator_chain.get(validator_b, [])):
            node = self._nodes.get(nid)
            while node:
                if node.key_hash in ancestors_a:
                    return node
                if node.parent_node_id:
                    node = self._nodes.get(node.parent_node_id)
                else:
                    break
        return None

    def lineage_divergence(self, validator_a: str, validator_b: str) -> int:
        """
        Generations since common ancestor. DIVERGENCE_THRESHOLD = unrelated.
        Low divergence = high correlation risk in diversity-weighted BFT.
        """
        ancestor = self.common_ancestor(validator_a, validator_b)
        if ancestor is None:
            return DIVERGENCE_THRESHOLD

        depth_a = self.lineage_depth(validator_a)
        depth_b = self.lineage_depth(validator_b)
        anc_gen = ancestor.generation
        return (depth_a - anc_gen) + (depth_b - anc_gen)

    def contamination_score(self, validator_id: str) -> float:
        """
        Current contamination score [0, 1] for this validator.
        0 = clean lineage, 1 = directly slashed.
        """
        node = self.current_node(validator_id)
        return node.contamination if node else 0.0

    def trust_modifier(self, validator_id: str) -> float:
        """
        Additive trust modifier from lineage depth and contamination.
        trust_modifier = lineage_bonus - contamination_penalty

        Positive: long, clean lineage earns bonus stake weight.
        Negative: contaminated or shallow lineage reduces stake weight.
        """
        depth         = self.lineage_depth(validator_id)
        contamination = self.contamination_score(validator_id)
        lineage_bonus = min(MAX_LINEAGE_TRUST_BONUS, depth * LINEAGE_TRUST_BONUS_PER_GEN)
        penalty       = contamination * 0.50   # up to 50% stake weight reduction

        return round(lineage_bonus - penalty, 4)

    def descendants(self, validator_id: str) -> List[str]:
        """
        All validator IDs that share lineage descendants with this validator.
        Useful for detecting colluding validator families.
        """
        chain = self._validator_chain.get(validator_id, [])
        result: Set[str] = set()
        for nid in chain:
            self._collect_descendants(nid, result)
        result.discard(validator_id)
        return sorted(result)

    def _collect_descendants(self, node_id: str, result: Set[str]) -> None:
        for child_id in self._children.get(node_id, []):
            child = self._nodes.get(child_id)
            if child:
                result.add(child.validator_id)
                self._collect_descendants(child_id, result)

    def network_summary(self) -> dict:
        """Summary statistics of the genealogy graph."""
        all_validators = list(self._validator_chain.keys())
        depths         = [self.lineage_depth(v) for v in all_validators]
        contaminations = [self.contamination_score(v) for v in all_validators]
        slashed_count  = sum(
            1 for v in all_validators
            if any(self._nodes.get(nid, GenomicKeyNode("", "", 0, "", None, 0, 0, "")).slashed
                   for nid in self._validator_chain.get(v, []))
        )

        return {
            "total_validators":    len(all_validators),
            "total_nodes":         len(self._nodes),
            "max_depth":           max(depths) if depths else 0,
            "mean_depth":          round(sum(depths) / max(len(depths), 1), 2),
            "contaminated_count":  sum(1 for c in contaminations if c > 0.01),
            "slashed_count":       slashed_count,
            "clean_validators":    sum(1 for c in contaminations if c < 0.01),
        }

    def divergence_matrix(self, validator_ids: List[str]) -> Dict[str, Dict[str, int]]:
        """
        Pairwise lineage divergence matrix.
        Used by diversity-weighted BFT to penalize correlated validators.
        """
        matrix: Dict[str, Dict[str, int]] = {}
        for a in validator_ids:
            matrix[a] = {}
            for b in validator_ids:
                if a == b:
                    matrix[a][b] = 0
                else:
                    matrix[a][b] = self.lineage_divergence(a, b)
        return matrix


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    graph = GenomicGenealogyGraph()

    # Register 5 validators
    for i in range(5):
        vid = f"VAL-{i:03d}"
        graph.register_genesis_key(vid, f"genesis_secret_{i}".encode(), block_number=i * 100)

    # Rotate keys for VAL-000 and VAL-001 (simulating shared key ceremony for VAL-000's 2nd gen)
    graph.rotate_key("VAL-000", "SCHEDULED", "0xBLOCK001", b"sig001", block_number=500)
    graph.rotate_key("VAL-000", "SCHEDULED", "0xBLOCK002", b"sig002", block_number=1000)
    graph.rotate_key("VAL-001", "THREAT",    "0xBLOCK003", b"sig003", block_number=600)
    graph.rotate_key("VAL-002", "SCHEDULED", "0xBLOCK004", b"sig004", block_number=700)

    # Slash VAL-002
    contaminated = graph.slash_validator("VAL-002", "WASH_TRADING_DETECTED")
    print(f"Slashed VAL-002 — contaminated {contaminated} descendants")

    # Query depths
    for i in range(5):
        vid = f"VAL-{i:03d}"
        depth = graph.lineage_depth(vid)
        mod   = graph.trust_modifier(vid)
        cont  = graph.contamination_score(vid)
        print(f"{vid}: depth={depth} trust_mod={mod:+.4f} contamination={cont:.4f}")

    # Divergence matrix
    vids   = ["VAL-000", "VAL-001", "VAL-002"]
    matrix = graph.divergence_matrix(vids)
    print(f"\nDivergence matrix:")
    for a in vids:
        row = [f"{matrix[a][b]:2d}" for b in vids]
        print(f"  {a}: {row}")

    # Network summary
    summary = graph.network_summary()
    print(f"\nNetwork: {summary}")

    assert graph.lineage_depth("VAL-000") == 2
    assert graph.lineage_depth("VAL-003") == 0
    assert graph.contamination_score("VAL-002") == 1.0
    assert graph.trust_modifier("VAL-002") < 0

    print("GENOMIC-GENEALOGY PASS — Validator key lineage graph implemented")
