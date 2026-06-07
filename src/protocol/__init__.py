"""
TRION Protocol — Protocol-Contract Intelligence Layer

Extends TRION's behavioral truth engine beyond individual wallets to DeFi
protocol contracts, solving the many-to-one identity aggregation problem.

Architecture:
  segmentation.py         — (contract, caller) pair extraction from bh_ledger
  role_classifier.py      — DeFi role detection from event_type patterns
  distribution_coherence.py — Jensen-Shannon divergence Mental-plane substitute
  protocol_health.py      — Aggregate health score from user distribution
"""

from .segmentation import ProtocolSegmenter, SubEntity
from .role_classifier import RoleClassifier, DeFiRole
from .distribution_coherence import DistributionCoherenceEngine
from .protocol_health import ProtocolHealthEngine

__all__ = [
    "ProtocolSegmenter", "SubEntity",
    "RoleClassifier", "DeFiRole",
    "DistributionCoherenceEngine",
    "ProtocolHealthEngine",
]
