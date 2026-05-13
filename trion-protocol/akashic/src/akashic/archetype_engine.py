"""
Archetype Engine — TRION L2
128-dimensional behavioral space, FAISS index, Genesis Inference
sim(G, A_k) = cosine_similarity(genesis_vector, archetype_k)
conf_genesis(t) = 1 - e^(-lambda * D(t))
"""
import math
from typing import List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

from sklearn.preprocessing import normalize


EMBEDDING_DIM = 128  # whitepaper spec — must stay fixed


@dataclass
class Archetype:
    archetype_id: str
    name: str
    vector: np.ndarray        # 128-dim normalized
    asset_class: str
    age_days_typical: float
    sample_count: int


class ArchetypeLibrary:
    """
    FAISS-backed 128-dim archetype library.
    Target: cosine sim search < 10ms at 1B+ records.
    """
    def __init__(self, dim: int = EMBEDDING_DIM):
        self.dim = dim
        self.archetypes: List[Archetype] = []
        self.index = None
        self._build_seed_archetypes()

    def _build_seed_archetypes(self):
        np.random.seed(42)

        seeds = [
            ("ARCH_NEW_TOKEN",    "New Token Launch",    "NEW_TOKEN",        30.0),
            ("ARCH_MATURE_DEX",   "Mature DEX Protocol", "MATURE_PROTOCOL", 730.0),
            ("ARCH_STABLECOIN",   "Stablecoin",          "STABLECOIN",      180.0),
            ("ARCH_GOV_TOKEN",    "Governance Token",    "GOVERNANCE_TOKEN", 365.0),
            ("ARCH_BRIDGE",       "Bridge Asset",        "BRIDGE_ASSET",    180.0),
            ("ARCH_WRAPPED",      "Wrapped Asset",       "WRAPPED_ASSET",    90.0),
            ("ARCH_MEME",         "Meme Token",          "NEW_TOKEN",        14.0),
            ("ARCH_LENDING",      "Lending Protocol",    "MATURE_PROTOCOL", 540.0),
            ("ARCH_YIELD",        "Yield Aggregator",    "MATURE_PROTOCOL", 365.0),
            ("ARCH_NFT_PLATFORM", "NFT Platform",        "MATURE_PROTOCOL", 270.0),
        ]

        for arch_id, name, asset_class, age in seeds:
            vec = np.random.randn(self.dim).astype(np.float32)
            vec = vec / np.linalg.norm(vec)
            self.archetypes.append(Archetype(
                archetype_id=arch_id,
                name=name,
                vector=vec,
                asset_class=asset_class,
                age_days_typical=age,
                sample_count=0,
            ))

        self._build_index()

    def _build_index(self):
        if not self.archetypes:
            return
        if FAISS_AVAILABLE:
            self.index = faiss.IndexFlatIP(self.dim)
            vecs = np.stack([a.vector for a in self.archetypes]).astype(np.float32)
            self.index.add(vecs)
        self._vectors = np.stack([a.vector for a in self.archetypes])

    def features_to_genesis_vector(self, features: dict) -> np.ndarray:
        f = [
            features.get("f1", 0.0), features.get("f2", 0.0),
            features.get("f3", 0.0), features.get("f4", 0.0),
            features.get("f5", 0.0), features.get("f6", 0.0),
            features.get("f7", 0.0), features.get("f8", 0.0),
            features.get("f9", 0.0),
        ]
        vec = []
        vec.extend(f)
        vec.extend([x**2 for x in f])
        vec.extend([x**0.5 for x in f])
        for i in range(len(f)):
            for j in range(i+1, len(f)):
                vec.append(f[i] * f[j])
        while len(vec) < 128:
            vec.append(0.0)
        vec = np.array(vec[:128], dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def find_best_archetype(
        self, genesis_vector: np.ndarray, top_k: int = 3
    ) -> List[Tuple[Archetype, float]]:
        g = genesis_vector.reshape(1, -1).astype(np.float32)

        if FAISS_AVAILABLE and self.index is not None:
            scores, indices = self.index.search(g, top_k)
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx >= 0:
                    results.append((self.archetypes[idx], float(score)))
            return results
        else:
            sims = self._vectors @ g.T
            sims = sims.flatten()
            top_indices = np.argsort(sims)[::-1][:top_k]
            return [(self.archetypes[i], float(sims[i])) for i in top_indices]

    def genesis_inference(
        self,
        features: dict,
        d_value: float,
        lambda_decay: float = 0.05,
    ) -> dict:
        genesis_vec = self.features_to_genesis_vector(features)
        matches = self.find_best_archetype(genesis_vec, top_k=3)

        if not matches:
            return {"error": "No archetypes available"}

        best_arch, best_sim = matches[0]

        conf_genesis = 1.0 - math.exp(-lambda_decay * d_value)
        conf_genesis = max(0.0, min(1.0, conf_genesis))

        direct_signal    = sum(features.values()) / len(features)
        archetype_signal = best_sim
        blended = conf_genesis * direct_signal + (1.0 - conf_genesis) * archetype_signal

        return {
            "blended_signal":       round(blended, 6),
            "direct_signal":        round(direct_signal, 6),
            "archetype_signal":     round(archetype_signal, 6),
            "conf_genesis":         round(conf_genesis, 6),
            "archetype_id":         best_arch.archetype_id,
            "archetype_name":       best_arch.name,
            "archetype_similarity": round(best_sim, 6),
            "asset_class_inferred": best_arch.asset_class,
            "top_3_archetypes": [
                {"id": a.archetype_id, "sim": round(s, 4)} for a, s in matches
            ],
        }

    def trajectory_anomaly(
        self, current_features: dict, archetype: Archetype, kl_threshold: float = 2.0
    ) -> Tuple[float, bool]:
        g = self.features_to_genesis_vector(current_features)
        arch_vec = archetype.vector

        def softmax(v):
            e = np.exp(v - v.max())
            return e / e.sum()

        p = softmax(np.abs(g))
        q = softmax(np.abs(arch_vec)) + 1e-10

        kl_div = float(np.sum(p * np.log(p / q)))
        return kl_div, kl_div > kl_threshold
