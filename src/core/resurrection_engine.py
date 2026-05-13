"""
Resurrection Inference Engine — TRION L2
Whitepaper formula: Delta_r = W_D * e^(-kappa*T) * W_C * sim(S_pre, S_react) * W_X * g(C)

5 dormancy types with distinct kappa decay constants.
4 classification outcomes with whitepaper-specified thresholds.

From trion-protocol/ whitepaper scaffold (fully tested).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List
import numpy as np


class DormancyType(Enum):
    ABANDONED        = "ABANDONED"         # kappa=0.008 — permanent decay
    HIBERNATION      = "HIBERNATION"       # kappa=0.003 — slow decay
    MIGRATION        = "MIGRATION"         # kappa=0.000 — no decay
    REGULATORY_PAUSE = "REGULATORY_PAUSE"  # kappa=0.001 — minimal decay
    EXPLOIT_RECOVERY = "EXPLOIT_RECOVERY"  # kappa=0.005 — medium decay


class ResurrectionOutcome(Enum):
    GENUINE_CONTINUATION = "GENUINE_CONTINUATION"
    NEW_ENTITY_OLD_SHELL = "NEW_ENTITY_OLD_SHELL"
    HOSTILE_TAKEOVER     = "HOSTILE_TAKEOVER"
    ZOMBIE               = "ZOMBIE"


KAPPA: dict = {
    DormancyType.ABANDONED:        0.008,
    DormancyType.HIBERNATION:      0.003,
    DormancyType.MIGRATION:        0.000,
    DormancyType.REGULATORY_PAUSE: 0.001,
    DormancyType.EXPLOIT_RECOVERY: 0.005,
}

W_D = 0.40   # Dormancy decay weight
W_C = 0.35   # Behavioral continuity weight
W_X = 0.25   # Cross-chain evidence weight


@dataclass
class ResurrectionInput:
    dormancy_type:        DormancyType
    dormancy_days:        float
    pre_dormancy_vector:  np.ndarray   # 128-dim behavioral embedding before dormancy
    reactivation_vector:  np.ndarray   # 128-dim behavioral embedding on reactivation
    cross_chain_evidence: float        # [0,1] signal from other chains
    ownership_changed:    bool
    team_continuity:      float        # [0,1] team overlap score
    community_continuity: float        # [0,1] community overlap score


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def compute_resurrection(inp: ResurrectionInput) -> dict:
    """
    Delta_r = W_D * e^(-kappa*T) * W_C * sim(S_pre, S_react) * W_X * g(C)
    Scaled to [0,1]. Multiplied by 3.0 to use full range.
    """
    kappa        = KAPPA[inp.dormancy_type]
    decay_factor = math.exp(-kappa * inp.dormancy_days)
    beh_cont     = _cosine_sim(inp.pre_dormancy_vector, inp.reactivation_vector)
    cross_chain  = max(0.0, min(1.0, inp.cross_chain_evidence))

    delta = W_D * decay_factor * W_C * beh_cont * W_X * cross_chain
    delta = max(0.0, min(1.0, delta * 3.0))

    outcome = _classify(delta, inp, beh_cont, decay_factor)

    return {
        "delta_resurrection":    round(delta, 6),
        "decay_factor":          round(decay_factor, 6),
        "behavioral_continuity": round(beh_cont, 6),
        "cross_chain_evidence":  round(cross_chain, 6),
        "dormancy_type":         inp.dormancy_type.value,
        "dormancy_days":         inp.dormancy_days,
        "outcome":               outcome.value,
        "kappa":                 kappa,
    }


def _classify(
    delta:        float,
    inp:          ResurrectionInput,
    beh_cont:     float,
    decay_factor: float,
) -> ResurrectionOutcome:
    if inp.ownership_changed and beh_cont < 0.40:
        return ResurrectionOutcome.HOSTILE_TAKEOVER
    if decay_factor < 0.10 and beh_cont < 0.30 and inp.cross_chain_evidence < 0.10:
        return ResurrectionOutcome.ZOMBIE
    if beh_cont < 0.50:
        return ResurrectionOutcome.NEW_ENTITY_OLD_SHELL
    if beh_cont > 0.70 and (inp.team_continuity > 0.60 or
                             inp.cross_chain_evidence > 0.50):
        return ResurrectionOutcome.GENUINE_CONTINUATION
    return ResurrectionOutcome.NEW_ENTITY_OLD_SHELL
