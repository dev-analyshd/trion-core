"""
Archetype Engine — TRION L2 (Akashic Index)
128-dimensional behavioral space, FAISS cosine similarity search.
Genesis Inference: conf_genesis(t) = 1 - e^(-lambda * D(t))
Trajectory Anomaly: KL divergence from archetype.

From trion-protocol/ whitepaper scaffold (all tests passing).
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass
import numpy as np

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False


EMBEDDING_DIM = 128  # whitepaper spec — fixed


@dataclass
class Archetype:
    archetype_id:     str
    name:             str
    vector:           np.ndarray    # 128-dim unit vector
    asset_class:      str
    age_days_typical: float
    sample_count:     int = 0


class ArchetypeLibrary:
    """
    FAISS-backed 128-dim archetype library.
    Cosine similarity search target: < 10ms at 1B+ records.
    Falls back to numpy dot product when FAISS is unavailable.
    """

    SEED_ARCHETYPES = [
        ("ARCH_NEW_TOKEN",    "New Token Launch",    "NEW_TOKEN",         30.0),
        ("ARCH_MATURE_DEX",   "Mature DEX Protocol", "MATURE_PROTOCOL",  730.0),
        ("ARCH_STABLECOIN",   "Stablecoin",          "STABLECOIN",       180.0),
        ("ARCH_GOV_TOKEN",    "Governance Token",    "GOVERNANCE_TOKEN", 365.0),
        ("ARCH_BRIDGE",       "Bridge Asset",        "BRIDGE_ASSET",     180.0),
        ("ARCH_WRAPPED",      "Wrapped Asset",       "WRAPPED_ASSET",     90.0),
        ("ARCH_MEME",         "Meme Token",          "NEW_TOKEN",         14.0),
        ("ARCH_LENDING",      "Lending Protocol",    "MATURE_PROTOCOL",  540.0),
        ("ARCH_YIELD",        "Yield Aggregator",    "MATURE_PROTOCOL",  365.0),
        ("ARCH_NFT_PLATFORM", "NFT Platform",        "MATURE_PROTOCOL",  270.0),
    ]

    def __init__(self, dim: int = EMBEDDING_DIM, seed: int = 42):
        self.dim       = dim
        self.archetypes: List[Archetype] = []
        self.index     = None
        self._vectors: Optional[np.ndarray] = None
        self._build_seeds(seed)

    def _build_seeds(self, seed: int):
        rng = np.random.RandomState(seed)
        for arch_id, name, asset_class, age in self.SEED_ARCHETYPES:
            vec = rng.randn(self.dim).astype(np.float32)
            vec = vec / np.linalg.norm(vec)
            self.archetypes.append(Archetype(
                archetype_id=arch_id, name=name,
                vector=vec, asset_class=asset_class,
                age_days_typical=age,
            ))
        self._rebuild_index()

    def _rebuild_index(self):
        if not self.archetypes:
            return
        self._vectors = np.stack([a.vector for a in self.archetypes]).astype(np.float32)
        if FAISS_AVAILABLE:
            self.index = faiss.IndexFlatIP(self.dim)
            self.index.add(self._vectors)

    def features_to_genesis_vector(self, features: Dict[str, float]) -> np.ndarray:
        """
        Expand 9 features into 128-dim genesis vector.
        Layout: [f1..f9 | f_i^2 | f_i^0.5 | f_i*f_j cross-terms | padding]
        """
        f = [features.get(f"f{i}", 0.0) for i in range(1, 10)]
        vec: List[float] = []
        vec.extend(f)
        vec.extend([x**2 for x in f])
        vec.extend([x**0.5 for x in f])
        for i in range(len(f)):
            for j in range(i+1, len(f)):
                vec.append(f[i] * f[j])
        while len(vec) < self.dim:
            vec.append(0.0)
        arr = np.array(vec[:self.dim], dtype=np.float32)
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr = arr / norm
        return arr

    def find_best_archetype(
        self, genesis_vector: np.ndarray, top_k: int = 3
    ) -> List[Tuple[Archetype, float]]:
        g = genesis_vector.reshape(1, -1).astype(np.float32)
        if FAISS_AVAILABLE and self.index is not None:
            scores, indices = self.index.search(g, top_k)
            return [(self.archetypes[int(idx)], float(score))
                    for score, idx in zip(scores[0], indices[0]) if idx >= 0]
        sims = (self._vectors @ g.T).flatten()
        top  = np.argsort(sims)[::-1][:top_k]
        return [(self.archetypes[int(i)], float(sims[i])) for i in top]

    def genesis_inference(
        self,
        features:      Dict[str, float],
        d_value:       float,
        lambda_decay:  float = 0.05,
    ) -> dict:
        """
        Returns blended signal, conf_genesis = 1-e^(-lambda*D), archetype match.
        """
        genesis_vec = self.features_to_genesis_vector(features)
        matches     = self.find_best_archetype(genesis_vec, top_k=3)
        if not matches:
            return {"error": "no archetypes"}

        best_arch, best_sim = matches[0]
        conf_genesis = max(0.0, min(1.0, 1.0 - math.exp(-lambda_decay * d_value)))

        direct_signal    = sum(features.values()) / max(len(features), 1)
        archetype_signal = best_sim
        blended = conf_genesis * direct_signal + (1.0 - conf_genesis) * archetype_signal

        return {
            "blended_signal":        round(blended, 6),
            "direct_signal":         round(direct_signal, 6),
            "archetype_signal":      round(archetype_signal, 6),
            "conf_genesis":          round(conf_genesis, 6),
            "archetype_id":          best_arch.archetype_id,
            "archetype_name":        best_arch.name,
            "archetype_similarity":  round(best_sim, 6),
            "asset_class_inferred":  best_arch.asset_class,
            "top_3_archetypes": [
                {"id": a.archetype_id, "sim": round(s, 4)} for a, s in matches
            ],
        }

    def trajectory_anomaly(
        self, current_features: Dict[str, float], archetype: Archetype,
        kl_threshold: float = 2.0
    ) -> Tuple[float, bool]:
        """KL divergence between current feature distribution and archetype."""
        g = self.features_to_genesis_vector(current_features)

        def softmax(v: np.ndarray) -> np.ndarray:
            e = np.exp(v - v.max())
            return e / e.sum()

        p = softmax(np.abs(g))
        q = softmax(np.abs(archetype.vector)) + 1e-10
        kl_div = float(np.sum(p * np.log(p / q)))
        return kl_div, kl_div > kl_threshold
