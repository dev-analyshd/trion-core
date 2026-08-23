"""
TRION Universal Behavioral Language (UBL)
==========================================
A standardized encoding of behavioral state that allows any system
(blockchains, AI agents, traditional finance, biological systems)
to express and compare behavioral patterns in a common format.

UBL vector = 12 dimensions:
  [0]  phi_entropy      — physical entropy (9→1 compressed)
  [1]  phi_complexity   — structural complexity
  [2]  phi_flow         — directional flow energy
  [3]  mental_score     — observer effect / attention
  [4]  sigma_score      — network consensus
  [5]  karma_score      — historical consistency
  [6]  anima_score      — predictive/future coherence
  [7]  lifecycle_stage  — 0=birth, 0.25=growth, 0.5=maturity, 0.75=decline, 1=death
  [8]  risk_level       — 0=safe, 1=critical
  [9]  manipulation_mf  — manipulation fingerprint score
  [10] coherence_c      — master C(t) coherence score
  [11] thermodynamic_f  — free energy (thermodynamic health)

UBL allows:
  - Cross-chain entity comparison
  - AI agent behavior encoding
  - Protocol compatibility scoring
  - Inter-system behavioral translation
  - Unified risk language
"""

import math
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import numpy as np


@dataclass
class UBLVector:
    entity_id: str
    timestamp: int
    # 12 UBL dimensions
    phi_entropy: float
    phi_complexity: float
    phi_flow: float
    mental_score: float
    sigma_score: float
    karma_score: float
    anima_score: float
    lifecycle_stage: float    # 0=birth → 1=death
    risk_level: float
    manipulation_mf: float
    coherence_c: float
    thermodynamic_f: float
    # Metadata
    source_chain: str
    source_vm: str            # EVM | SVM | PVM | TVM | MOVE | COSMOS | UTXO | AI_AGENT
    encoding_version: str = "UBL-1.0"


LIFECYCLE_STAGE_MAP = {
    "BIRTH": 0.0, "GROWTH": 0.25, "MATURITY": 0.5,
    "DECLINE": 0.75, "DEATH": 1.0
}
LIFECYCLE_STAGE_REVERSE = {v: k for k, v in LIFECYCLE_STAGE_MAP.items()}

RISK_MAP = {"SAFE": 0.0, "LOW": 0.2, "MEDIUM": 0.45, "HIGH": 0.70, "CRITICAL": 1.0}


class UBLEncoder:
    """Encodes any behavioral signal into UBL format."""

    def from_phi_and_planes(
        self,
        entity_id: str,
        phi_vector: List[float],
        mental: float = 0.5,
        sigma: float = 0.5,
        karma: float = 0.5,
        anima: float = 0.5,
        coherence: float = 0.5,
        lifecycle_stage: str = "MATURITY",
        risk_label: str = "MEDIUM",
        manipulation_score: float = 0.0,
        thermo_free_energy: float = 0.5,
        source_chain: str = "unknown",
        source_vm: str = "EVM",
    ) -> UBLVector:
        phi = np.array(phi_vector, dtype=np.float32)

        # Compress phi to 3 summary dimensions
        phi_entropy = float(phi[:3].mean()) if len(phi) >= 3 else 0.5
        phi_complexity = float(phi[3:6].mean()) if len(phi) >= 6 else 0.5
        phi_flow = float(phi[6:9].mean()) if len(phi) >= 9 else 0.5

        return UBLVector(
            entity_id=entity_id,
            timestamp=int(time.time()),
            phi_entropy=round(phi_entropy, 4),
            phi_complexity=round(phi_complexity, 4),
            phi_flow=round(phi_flow, 4),
            mental_score=round(mental, 4),
            sigma_score=round(sigma, 4),
            karma_score=round(karma, 4),
            anima_score=round(anima, 4),
            lifecycle_stage=round(LIFECYCLE_STAGE_MAP.get(lifecycle_stage, 0.5), 4),
            risk_level=round(RISK_MAP.get(risk_label, 0.45), 4),
            manipulation_mf=round(manipulation_score, 4),
            coherence_c=round(coherence, 4),
            thermodynamic_f=round(thermo_free_energy, 4),
            source_chain=source_chain,
            source_vm=source_vm,
        )

    def from_ai_agent(
        self,
        agent_id: str,
        fitness_score: float,
        avg_coherence: float,
        blocked_ratio: float,
        trust_level: str,
        action_diversity: float = 0.5,
    ) -> UBLVector:
        trust_map = {"PROBATION": 0.1, "TRUSTED": 0.5, "VERIFIED": 0.8, "EXEMPLARY": 1.0}
        risk = 1.0 - trust_map.get(trust_level, 0.3)

        return UBLVector(
            entity_id=agent_id,
            timestamp=int(time.time()),
            phi_entropy=round(action_diversity, 4),
            phi_complexity=round(fitness_score, 4),
            phi_flow=round(avg_coherence, 4),
            mental_score=round(trust_map.get(trust_level, 0.3), 4),
            sigma_score=round(1.0 - blocked_ratio, 4),
            karma_score=round(fitness_score, 4),
            anima_score=round(avg_coherence, 4),
            lifecycle_stage=0.25 if fitness_score > 0.5 else 0.5,
            risk_level=round(risk, 4),
            manipulation_mf=round(blocked_ratio, 4),
            coherence_c=round(avg_coherence, 4),
            thermodynamic_f=round(fitness_score, 4),
            source_chain="agent_network",
            source_vm="AI_AGENT",
        )

    def to_vector(self, ubl: UBLVector) -> np.ndarray:
        return np.array([
            ubl.phi_entropy, ubl.phi_complexity, ubl.phi_flow,
            ubl.mental_score, ubl.sigma_score, ubl.karma_score,
            ubl.anima_score, ubl.lifecycle_stage, ubl.risk_level,
            ubl.manipulation_mf, ubl.coherence_c, ubl.thermodynamic_f,
        ], dtype=np.float32)

    def similarity(self, ubl_a: UBLVector, ubl_b: UBLVector) -> float:
        va = self.to_vector(ubl_a)
        vb = self.to_vector(ubl_b)
        na = np.linalg.norm(va)
        nb = np.linalg.norm(vb)
        if na == 0 or nb == 0:
            return 0.0
        return round(float(np.dot(va, vb) / (na * nb)), 4)

    def behavioral_distance(self, ubl_a: UBLVector, ubl_b: UBLVector) -> float:
        va = self.to_vector(ubl_a)
        vb = self.to_vector(ubl_b)
        return round(float(np.linalg.norm(va - vb)), 4)

    def to_dict(self, ubl: UBLVector) -> Dict:
        d = asdict(ubl)
        d["lifecycle_stage_label"] = next(
            (k for k, v in LIFECYCLE_STAGE_MAP.items()
             if abs(v - ubl.lifecycle_stage) < 0.15), "UNKNOWN"
        )
        d["risk_label"] = next(
            (k for k, v in RISK_MAP.items()
             if abs(v - ubl.risk_level) < 0.15), "UNKNOWN"
        )
        # Convert numpy floats → Python floats for JSON serialization
        d["vector"] = [float(v) for v in self.to_vector(ubl)]
        return d

    def interpret(self, ubl: UBLVector) -> str:
        parts = []
        lc = next((k for k, v in LIFECYCLE_STAGE_MAP.items()
                   if abs(v - ubl.lifecycle_stage) < 0.15), "MATURITY")
        risk = next((k for k, v in RISK_MAP.items()
                    if abs(v - ubl.risk_level) < 0.15), "MEDIUM")
        parts.append(f"Entity [{ubl.entity_id[:10]}] on {ubl.source_chain}/{ubl.source_vm}")
        parts.append(f"is in {lc} lifecycle stage.")
        parts.append(f"Coherence C(t)={ubl.coherence_c:.3f}.")
        parts.append(f"Risk: {risk}. Thermodynamic free energy: {ubl.thermodynamic_f:.3f}.")
        if ubl.manipulation_mf > 0.5:
            parts.append(f"WARNING: High manipulation fingerprint ({ubl.manipulation_mf:.3f}).")
        return " ".join(parts)


# Standard UBL schema definition
UBL_SCHEMA = {
    "version": "UBL-1.0",
    "description": "Universal Behavioral Language — TRION standard for cross-system behavioral encoding",
    "dimensions": {
        0: {"name": "phi_entropy", "description": "Physical entropy (behavior disorder)", "range": [0, 1]},
        1: {"name": "phi_complexity", "description": "Structural complexity", "range": [0, 1]},
        2: {"name": "phi_flow", "description": "Directional energy flow", "range": [0, 1]},
        3: {"name": "mental_score", "description": "Observer effect / attention level", "range": [0, 1]},
        4: {"name": "sigma_score", "description": "Network consensus / BFT agreement", "range": [0, 1]},
        5: {"name": "karma_score", "description": "Historical consistency / track record", "range": [0, 1]},
        6: {"name": "anima_score", "description": "Predictive/forward coherence", "range": [0, 1]},
        7: {"name": "lifecycle_stage", "description": "Life stage: 0=birth, 1=death", "range": [0, 1]},
        8: {"name": "risk_level", "description": "Risk: 0=safe, 1=critical", "range": [0, 1]},
        9: {"name": "manipulation_mf", "description": "Manipulation fingerprint score", "range": [0, 1]},
        10: {"name": "coherence_c", "description": "Master TRION coherence C(t)", "range": [0, 1]},
        11: {"name": "thermodynamic_f", "description": "Thermodynamic free energy", "range": [0, 1]},
    },
    "supported_sources": ["EVM", "SVM", "PVM", "TVM", "MOVE", "COSMOS", "UTXO", "AI_AGENT", "TRADITIONAL_FINANCE"],
}


_encoder: Optional[UBLEncoder] = None


def get_encoder() -> UBLEncoder:
    global _encoder
    if _encoder is None:
        _encoder = UBLEncoder()
    return _encoder
