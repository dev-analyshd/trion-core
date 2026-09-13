"""TRION ZK root package — re-exports from facade.

All 'from zk import ...' sites resolve here. The facade provides
ZKProofSystem, witness classes, and merkle_root.
"""
from zk.facade import (
    ZKProofSystem,
    IntentWitness,
    ComplementarityWitness,
    BehavioralCredentialWitness,
    TravelRuleWitness,
    IAPShareWitness,
    CircuitType,
    merkle_root,
)

__all__ = [
    "ZKProofSystem",
    "IntentWitness",
    "ComplementarityWitness",
    "BehavioralCredentialWitness",
    "TravelRuleWitness",
    "IAPShareWitness",
    "CircuitType",
    "merkle_root",
]
