"""
Resurrection Inference — TRION L2
Whitepaper: Delta_resurrection = w_d*e^(-kappa*T) * w_c*sim(S_pre, S_react) * w_x*g(C)
5 dormancy types with distinct kappa values
4 classification outcomes
"""
import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import numpy as np


class DormancyType(Enum):
    ABANDONED        = "ABANDONED"
    HIBERNATION      = "HIBERNATION"
    MIGRATION        = "MIGRATION"
    REGULATORY_PAUSE = "REGULATORY_PAUSE"
    EXPLOIT_RECOVERY = "EXPLOIT_RECOVERY"


class ResurrectionOutcome(Enum):
    GENUINE_CONTINUATION = "GENUINE_CONTINUATION"
    NEW_ENTITY_OLD_SHELL = "NEW_ENTITY_OLD_SHELL"
    HOSTILE_TAKEOVER     = "HOSTILE_TAKEOVER"
    ZOMBIE               = "ZOMBIE"


KAPPA = {
    DormancyType.ABANDONED:        0.008,
    DormancyType.HIBERNATION:      0.003,
    DormancyType.MIGRATION:        0.000,
    DormancyType.REGULATORY_PAUSE: 0.001,
    DormancyType.EXPLOIT_RECOVERY: 0.005,
}

W_D = 0.40
W_C = 0.35
W_X = 0.25


@dataclass
class ResurrectionInput:
    dormancy_type:        DormancyType
    dormancy_days:        float
    pre_dormancy_vector:  np.ndarray
    reactivation_vector:  np.ndarray
    cross_chain_evidence: float
    ownership_changed:    bool
    team_continuity:      float
    community_continuity: float


def compute_resurrection(inp: ResurrectionInput) -> dict:
    kappa = KAPPA[inp.dormancy_type]
    T     = inp.dormancy_days

    decay_factor = math.exp(-kappa * T)

    def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        na = np.linalg.norm(a)
        nb = np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    behavioral_continuity = cosine_sim(inp.pre_dormancy_vector, inp.reactivation_vector)
    cross_chain           = max(0.0, min(1.0, inp.cross_chain_evidence))

    delta = W_D * decay_factor * W_C * behavioral_continuity * W_X * cross_chain
    delta = max(0.0, min(1.0, delta * 3.0))

    outcome = classify_resurrection(delta, inp, behavioral_continuity, decay_factor)

    return {
        "delta_resurrection":   round(delta, 6),
        "decay_factor":         round(decay_factor, 6),
        "behavioral_continuity": round(behavioral_continuity, 6),
        "cross_chain_evidence": round(cross_chain, 6),
        "dormancy_type":        inp.dormancy_type.value,
        "dormancy_days":        T,
        "outcome":              outcome.value,
        "kappa_used":           kappa,
    }


def classify_resurrection(
    delta: float, inp: ResurrectionInput,
    beh_continuity: float, decay_factor: float
) -> ResurrectionOutcome:
    if inp.ownership_changed and beh_continuity < 0.40:
        return ResurrectionOutcome.HOSTILE_TAKEOVER

    if decay_factor < 0.10 and beh_continuity < 0.30 and inp.cross_chain_evidence < 0.10:
        return ResurrectionOutcome.ZOMBIE

    if beh_continuity < 0.50:
        return ResurrectionOutcome.NEW_ENTITY_OLD_SHELL

    if beh_continuity > 0.70 and (inp.team_continuity > 0.60 or
                                   inp.cross_chain_evidence > 0.50):
        return ResurrectionOutcome.GENUINE_CONTINUATION

    return ResurrectionOutcome.NEW_ENTITY_OLD_SHELL
