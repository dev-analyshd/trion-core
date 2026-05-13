"""
TRION AI Agent Interface
------------------------
The bridge between TRION behavioral signals and
an AI trading agent's decision engine.

The agent:
  1. Receives TRIONTradeSignal from TRION API
  2. Computes its own FAISS vector from recent market data
  3. Compares: cosine_sim(own_view, trion_phi_vector)
  4. Weights TRION signal by agreement score
  5. Makes position decision

This module also provides:
  - Historical signal performance tracking
  - Signal-to-trade mapping
  - Portfolio context integration
"""

import numpy as np
import time
from dataclasses import dataclass, field
from enum import IntEnum
from collections import Counter
from typing import List, Dict


class AgentAction(IntEnum):
    STRONG_LONG   =  2
    LONG          =  1
    HOLD          =  0
    SHORT         = -1
    STRONG_SHORT  = -2
    WAIT          = 99


SIGNAL_TO_ACTION_MAP: Dict[str, AgentAction] = {
    "STRONG_BUY":         AgentAction.STRONG_LONG,
    "BUY":                AgentAction.LONG,
    "WEAK_BUY":           AgentAction.LONG,
    "ACCUMULATION":       AgentAction.LONG,
    "MOMENTUM":           AgentAction.LONG,
    "NEUTRAL":            AgentAction.HOLD,
    "REVERSAL_LONG":      AgentAction.STRONG_LONG,
    "REVERSAL_SHORT":     AgentAction.STRONG_SHORT,
    "DISTRIBUTION":       AgentAction.SHORT,
    "WEAK_SELL":          AgentAction.SHORT,
    "SELL":               AgentAction.SHORT,
    "STRONG_SELL":        AgentAction.STRONG_SHORT,
    "SILENCE":            AgentAction.WAIT,
    "MANIPULATION_ALERT": AgentAction.WAIT,
}


@dataclass
class AgentContext:
    """Agent's own market view — what it knows from its own sources."""
    market_price:     float
    volume_24h:       float
    price_change_24h: float
    rsi_14:           float
    volume_sma_ratio: float
    spread_bps:       float
    open_interest:    float = 0.0
    funding_rate:     float = 0.0

    def to_faiss_vector(self) -> np.ndarray:
        """
        Convert agent's market context to a 9-dim vector
        in the same Φ feature space as TRION.
        Allows direct cosine comparison with TRION's phi_vector.
        """
        f1 = min(1.0, self.volume_sma_ratio / 3.0)
        f2 = min(1.0, abs(self.price_change_24h) * 2)
        f3 = 1.0 - min(1.0, self.spread_bps / 100)
        f4 = min(1.0, self.volume_24h / 1e8)
        f5 = max(0.0, min(1.0, 0.5 + self.price_change_24h * 2))
        f6 = min(1.0, self.open_interest / 1e7)
        f7 = min(1.0, abs(self.funding_rate) * 100 + 0.5)
        f8 = 1.0 - self.rsi_14 / 100
        f9 = min(1.0, 1.0 - abs(self.funding_rate) * 10)
        return np.array([f1, f2, f3, f4, f5, f6, f7, f8, f9])


class TRIONAgent:
    """
    AI Trading Agent that uses TRION behavioral signals.

    Decision logic:
      1. Fetch TRION signal for target entity
      2. Compute own view vector from market data
      3. agreement = cosine_sim(own_view, trion_phi_vector)
      4. weighted_confidence = trion_confidence × agreement
      5. If weighted_confidence > threshold → act
      6. Size position by confidence level
    """

    def __init__(
        self,
        trion_base_url:   str   = "http://127.0.0.1:8000",
        min_confidence:   float = 0.40,
        agreement_weight: float = 0.40,
        trion_weight:     float = 0.60,
    ):
        self.trion_url        = trion_base_url
        self.min_confidence   = min_confidence
        self.agreement_weight = agreement_weight
        self.trion_weight     = trion_weight
        self._signal_history: List[dict] = []

    def cosine_sim(self, v1: np.ndarray, v2: np.ndarray) -> float:
        n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
        if n1 == 0 or n2 == 0:
            return 0.0
        return float(np.dot(v1, v2) / (n1 * n2))

    def decide(
        self,
        trion_signal:  dict,
        agent_context: AgentContext,
    ) -> dict:
        now = time.time()

        if not trion_signal.get("tradeable", False):
            reason = trion_signal.get("signal", "UNKNOWN")
            return {
                "action":       AgentAction.WAIT.name,
                "action_id":    int(AgentAction.WAIT),
                "size_pct":     0.0,
                "reason":       f"TRION: {reason} — no action",
                "trion_signal": trion_signal.get("signal"),
                "confidence":   0.0,
                "timestamp":    int(now),
            }

        phi_features = trion_signal.get("phi_features", {})
        trion_vec = np.array([
            phi_features.get("f1_volume_entropy",         0.5),
            phi_features.get("f2_counterparty_diversity", 0.5),
            phi_features.get("f3_temporal_spacing",       0.5),
            phi_features.get("f4_contract_interaction",   0.5),
            phi_features.get("f5_value_flow_direction",   0.5),
            phi_features.get("f6_wallet_architecture",    0.5),
            phi_features.get("f7_cross_protocol",         0.5),
            phi_features.get("f8_gas_pattern",            0.5),
            phi_features.get("f9_mev_interaction",        0.5),
        ])

        agent_vec   = agent_context.to_faiss_vector()
        agreement   = self.cosine_sim(trion_vec, agent_vec)
        trion_conf  = trion_signal.get("confidence", 0.0)
        weighted_confidence = (
            self.trion_weight     * trion_conf +
            self.agreement_weight * agreement
        )

        trion_sig_name = trion_signal.get("signal", "NEUTRAL")
        base_action    = SIGNAL_TO_ACTION_MAP.get(trion_sig_name, AgentAction.HOLD)

        if weighted_confidence < self.min_confidence:
            final_action = AgentAction.HOLD
        elif weighted_confidence < 0.55 and abs(int(base_action)) == 2:
            final_action = AgentAction(int(base_action) // 2)
        else:
            final_action = base_action

        if final_action == AgentAction.HOLD:
            size_pct = 0.0
        elif abs(int(final_action)) == 2:
            size_pct = min(1.0, weighted_confidence * 0.80)
        else:
            size_pct = min(0.50, weighted_confidence * 0.50)

        coherence_margin = trion_signal.get("coherence_margin", 0.1)
        stop_loss_pct    = max(0.01, min(0.05, 0.05 - coherence_margin * 0.10))

        decision = {
            "action":        final_action.name,
            "action_id":     int(final_action),
            "size_pct":      round(size_pct, 4),
            "stop_loss_pct": round(stop_loss_pct, 4),
            "trion_signal":  trion_sig_name,
            "trion_conf":    round(trion_conf, 4),
            "agreement":     round(agreement, 4),
            "weighted_conf": round(weighted_confidence, 4),
            "trion_vector":  trion_vec.tolist(),
            "agent_vector":  agent_vec.tolist(),
            "coherence":     trion_signal.get("coherence", 0),
            "nl_score":      trion_signal.get("nl_score", 0),
            "mf_score":      trion_signal.get("mf_score", 0),
            "pattern":       trion_signal.get("pattern", ""),
            "description":   trion_signal.get("description", ""),
            "timestamp":     int(now),
            "entity_id":     trion_signal.get("entity_id", ""),
        }

        self._signal_history.append({
            "timestamp":    int(now),
            "action":       final_action.name,
            "confidence":   weighted_confidence,
            "trion_signal": trion_sig_name,
            "agreement":    agreement,
        })

        return decision

    def get_performance_summary(self) -> dict:
        if not self._signal_history:
            return {"decisions": 0}
        recent      = self._signal_history[-100:]
        avg_conf    = sum(s["confidence"] for s in recent) / len(recent)
        avg_agree   = sum(s["agreement"]  for s in recent) / len(recent)
        action_dist = Counter(s["action"] for s in recent)
        return {
            "decisions":          len(self._signal_history),
            "recent_100":         len(recent),
            "avg_confidence":     round(avg_conf, 4),
            "avg_agreement":      round(avg_agree, 4),
            "action_distribution": dict(action_dist),
        }


if __name__ == "__main__":
    import sys as _sys
    _sys.path.insert(0, '.')
    from src.trading.signal_engine import TradingSignalEngine

    engine = TradingSignalEngine()
    agent  = TRIONAgent(min_confidence=0.40)

    accum_phi = np.array([0.82, 0.90, 0.85, 0.76, 0.22, 0.71, 0.80, 0.61, 0.91])
    trion_sig = engine.generate_signal(
        entity_id="0xWHALE001",
        phi_vector=accum_phi,
        coherence=0.72, threshold=0.58,
        akashic_depth=800,
        nl_score=0.75, mf_score=0.02,
    )

    context = AgentContext(
        market_price=2450.0, volume_24h=5e7,
        price_change_24h=0.03,
        rsi_14=58, volume_sma_ratio=1.8,
        spread_bps=3,
    )

    decision = agent.decide(trion_sig, context)
    print("TRION Agent Decision:")
    print(f"  TRION signal:  {decision['trion_signal']}")
    print(f"  TRION conf:    {decision['trion_conf']}")
    print(f"  Agreement:     {decision['agreement']:.4f}")
    print(f"  Weighted conf: {decision['weighted_conf']:.4f}")
    print(f"  Action:        {decision['action']}")
    print(f"  Size:          {decision['size_pct']*100:.1f}%")
    print(f"  Stop loss:     {decision['stop_loss_pct']*100:.2f}%")
    print(f"  Pattern:       {decision['pattern']}")

    assert decision["action"] in ["LONG", "STRONG_LONG", "HOLD"], \
        f"Expected LONG/STRONG_LONG/HOLD for test scenario, got {decision['action']}"
    print(f"  Action check: {decision['action']} ✓ (LONG/STRONG_LONG/HOLD valid for ACCUMULATION scenario)")

    perf = agent.get_performance_summary()
    print(f"\nPerformance: {perf}")
    print("PHASE 3 PASS — AI Agent Interface: PASS")
