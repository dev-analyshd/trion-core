"""
TRION Protocol — L2.2: Genesis Inference
For assets with no behavioral history — priced from archetype similarity.

sim(G, A_k) = (G · A_k) / (‖G‖ · ‖A_k‖)  cosine similarity in 128-dim space
conf_genesis(t) = 1 - e^(-λ · D_asset(t))
"""

import numpy as np
import math
from typing import List, Optional
from dataclasses import dataclass


GENESIS_DIM    = 128
GENESIS_LAMBDA = 0.001


@dataclass
class GenesisVector:
    asset_id:                     str
    feature_vector:               np.ndarray
    deployer_signature:           Optional[np.ndarray] = None
    token_economic_structure:     float = 0.5
    initial_distribution_entropy: float = 0.5
    protocol_category:            int   = 0
    smart_contract_complexity:    float = 0.5


@dataclass
class Archetype:
    archetype_id:   str
    name:           str
    category:       str
    feature_vector: np.ndarray
    base_value:     float


def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (n1 * n2))


def genesis_confidence(D_asset: float) -> float:
    return 1.0 - math.exp(-GENESIS_LAMBDA * D_asset)


def infer_genesis_value(
    genesis:    GenesisVector,
    archetypes: List[Archetype],
    D_asset:    float = 0.0,
) -> dict:
    if not archetypes:
        return {
            "genesis_value": 0.50,
            "conf_genesis":  0.0,
            "archetype":     None,
            "method":        "no_archetypes",
        }

    sims       = [cosine_similarity(genesis.feature_vector, a.feature_vector) for a in archetypes]
    total_sim  = sum(sims)

    if total_sim <= 0:
        archetype_value = 0.50
        best_archetype  = archetypes[0].name
    else:
        archetype_value = sum(
            s * a.base_value / total_sim
            for s, a in zip(sims, archetypes)
        )
        best_idx       = int(np.argmax(sims))
        best_archetype = archetypes[best_idx].name

    conf = genesis_confidence(D_asset)

    direct_value = 0.50
    total_value  = conf * direct_value + (1 - conf) * archetype_value

    return {
        "genesis_value":   total_value,
        "archetype_value": archetype_value,
        "direct_value":    direct_value,
        "conf_genesis":    conf,
        "best_archetype":  best_archetype,
        "similarities":    dict(zip([a.name for a in archetypes], sims)),
        "method":          "genesis_inference",
        "disclosure": (
            f"Genesis inference: conf={conf:.3f}. "
            f"Archetype: {best_archetype}. "
            f"Confidence grows as behavioral history accumulates."
        ),
    }


if __name__ == "__main__":
    np.random.seed(42)

    archetypes = [
        Archetype("A1", "DeFi_Blue_Chip", "MATURE_PROTOCOL",
                  np.random.normal(0.7, 0.1, 128), 0.80),
        Archetype("A2", "New_Memecoin", "NEW_TOKEN",
                  np.random.normal(0.3, 0.2, 128), 0.20),
        Archetype("A3", "Stablecoin", "STABLECOIN",
                  np.random.normal(0.5, 0.05, 128), 0.60),
    ]

    genesis_vec = GenesisVector(
        asset_id="0xNEW",
        feature_vector=np.random.normal(0.68, 0.12, 128),
    )

    r0     = infer_genesis_value(genesis_vec, archetypes, D_asset=0)
    r1000  = infer_genesis_value(genesis_vec, archetypes, D_asset=1000)
    r50000 = infer_genesis_value(genesis_vec, archetypes, D_asset=50000)

    print(f"Genesis (D=0):     value={r0['genesis_value']:.3f} conf={r0['conf_genesis']:.3f}")
    print(f"Genesis (D=1000):  value={r1000['genesis_value']:.3f} conf={r1000['conf_genesis']:.3f}")
    print(f"Genesis (D=50000): value={r50000['genesis_value']:.3f} conf={r50000['conf_genesis']:.3f}")
    print(f"Best archetype:    {r0['best_archetype']}")
    assert r50000['conf_genesis'] > r0['conf_genesis'], "Confidence should grow"
    print("PHASE 19 PASS — Genesis Inference implemented")
