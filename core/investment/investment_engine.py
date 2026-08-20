"""
TRION Investment Signal Engine
================================
Translates TRION behavioral analysis into actionable investment decisions.
Goes far beyond price charts: behavioral alpha from C(t), archetype trajectory,
thermodynamic free energy, lifecycle stage, and manipulation detection.

Output for any token/protocol/wallet:
  - Decision: STRONG_BUY | BUY | WATCH | AVOID | STRONG_AVOID | SHORT
  - Confidence: 0-1
  - Expected behavioral trajectory
  - Risk-adjusted behavioral score
  - Time horizon recommendation
  - Entry/exit conditions
"""

import time
import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import numpy as np

from core.akashic.archetype import match_archetype, ARCHETYPES


@dataclass
class InvestmentSignal:
    entity_id: str
    timestamp: int
    # Primary signal
    decision: str              # STRONG_BUY | BUY | WATCH | AVOID | STRONG_AVOID | SHORT
    confidence: float          # 0-1
    behavioral_alpha: float    # edge vs. pure price-based analysis
    # Scores
    coherence_score: float
    archetype_score: float     # how favorable the archetype is
    lifecycle_score: float     # lifecycle stage favorability
    thermo_score: float        # thermodynamic health
    manipulation_free_score: float
    # Risk
    risk_level: str
    max_drawdown_estimate: float   # estimated max loss if thesis wrong
    # Trajectory
    archetype: str
    lifecycle_stage: str
    phase: str                 # thermodynamic phase
    trajectory: str            # IMPROVING | STABLE | DETERIORATING | UNKNOWN
    # Time horizon
    recommended_horizon: str   # HOURS | DAYS | WEEKS | MONTHS | LONG_TERM
    entry_conditions: List[str]
    exit_conditions: List[str]
    # Narrative
    thesis: str


DECISION_THRESHOLDS = {
    "STRONG_BUY":   (0.80, 1.00),
    "BUY":          (0.62, 0.80),
    "WATCH":        (0.42, 0.62),
    "AVOID":        (0.22, 0.42),
    "STRONG_AVOID": (0.10, 0.22),
    "SHORT":        (0.00, 0.10),
}

ARCHETYPE_FAVORABILITY = {
    "Organic Growth": 0.92,
    "Healthy DeFi Protocol": 0.88,
    "Accumulation": 0.72,
    "Stablecoin Protocol": 0.70,
    "Dormant Contract": 0.40,
    "Distribution": 0.22,
    "Wash Trading": 0.15,
    "Bot Swarm": 0.12,
    "Governance Attack": 0.05,
    "Liquidity Drain": 0.03,
    "Ponzi Structure": 0.02,
    "Flash Exploit": 0.01,
    "Death Spiral": 0.00,
    "Unknown": 0.35,
}

LIFECYCLE_FAVORABILITY = {
    "BIRTH": 0.55,    # risky but high upside
    "GROWTH": 0.82,   # best entry point
    "MATURITY": 0.68, # stable, lower upside
    "DECLINE": 0.20,  # danger
    "DEATH": 0.02,    # almost certainly lose
}

PHASE_FAVORABILITY = {
    "SOLID": 0.65,   # stable but low energy
    "LIQUID": 0.80,  # optimal
    "GAS": 0.45,     # volatile
    "PLASMA": 0.05,  # exploit/crash
}


class InvestmentEngine:

    def analyze(
        self,
        entity_id: str,
        phi_vector: List[float],
        coherence: float,
        manipulation_score: float = 0.0,
        lifecycle_stage: str = "MATURITY",
        thermo_phase: str = "LIQUID",
        thermo_free_energy: float = 0.5,
        market_volatility: float = 0.3,
        epigenetic_drift: float = 0.0,
        reputation_score: float = 0.5,
        chain_id: int = 1,
    ) -> InvestmentSignal:
        t0 = int(time.time())

        # 1. Archetype match
        arch_result = match_archetype(phi_vector)
        archetype_name = arch_result["archetype_name"]
        arch_fav = ARCHETYPE_FAVORABILITY.get(archetype_name, 0.35)

        # 2. Lifecycle favorability
        lc_fav = LIFECYCLE_FAVORABILITY.get(lifecycle_stage, 0.5)

        # 3. Thermodynamic favorability
        thermo_fav = PHASE_FAVORABILITY.get(thermo_phase, 0.5)
        thermo_combined = thermo_fav * 0.6 + thermo_free_energy * 0.4

        # 4. Manipulation penalty
        manip_penalty = 1.0 - (manipulation_score * 0.8)

        # 5. Coherence weight
        coherence_weight = coherence

        # 6. Epigenetic drift penalty (large drift = unpredictable)
        drift_penalty = max(0.0, 1.0 - epigenetic_drift * 0.5)

        # 7. Reputation boost
        rep_boost = reputation_score * 0.1

        # 8. Composite behavioral alpha score
        behavioral_alpha = (
            arch_fav * 0.30 +
            lc_fav * 0.20 +
            thermo_combined * 0.20 +
            coherence_weight * 0.20 +
            manip_penalty * 0.10
        ) * drift_penalty + rep_boost

        behavioral_alpha = round(min(1.0, max(0.0, behavioral_alpha)), 4)

        # 9. Decision
        decision = "WATCH"
        for d, (lo, hi) in DECISION_THRESHOLDS.items():
            if lo <= behavioral_alpha < hi:
                decision = d
                break

        # 10. Confidence
        signals = [arch_fav, lc_fav, thermo_combined, coherence_weight]
        confidence_raw = 1.0 - float(np.std(signals))
        confidence = round(min(1.0, max(0.1, confidence_raw)), 4)

        # 11. Risk level
        if decision in ("STRONG_BUY", "BUY"):
            risk_level = "LOW" if behavioral_alpha > 0.75 else "MEDIUM"
        elif decision in ("AVOID", "STRONG_AVOID"):
            risk_level = "HIGH"
        elif decision == "SHORT":
            risk_level = "CRITICAL"
        else:
            risk_level = "MEDIUM"

        # 12. Max drawdown estimate
        if decision in ("STRONG_BUY", "BUY"):
            drawdown = round((1.0 - behavioral_alpha) * 0.5, 4)
        elif decision in ("AVOID", "STRONG_AVOID"):
            drawdown = round(0.5 + (1.0 - behavioral_alpha) * 0.4, 4)
        elif decision == "SHORT":
            drawdown = 0.95
        else:
            drawdown = round((1.0 - behavioral_alpha) * 0.35, 4)

        # 13. Trajectory
        if epigenetic_drift < 0.1 and coherence > 0.6:
            trajectory = "STABLE"
        elif epigenetic_drift > 0.4 or coherence < 0.3:
            trajectory = "DETERIORATING"
        elif arch_fav > 0.6 and lc_fav > 0.6:
            trajectory = "IMPROVING"
        else:
            trajectory = "STABLE"

        # 14. Time horizon
        if lifecycle_stage == "GROWTH" and arch_fav > 0.7:
            horizon = "WEEKS"
        elif lifecycle_stage == "MATURITY":
            horizon = "MONTHS"
        elif lifecycle_stage in ("DECLINE", "DEATH"):
            horizon = "HOURS"
        elif lifecycle_stage == "BIRTH":
            horizon = "DAYS"
        else:
            horizon = "WEEKS"

        # 15. Entry conditions
        entry = []
        if decision in ("BUY", "STRONG_BUY"):
            entry.append(f"C(t) > {max(0.5, coherence - 0.05):.2f}")
            entry.append(f"Archetype confirms {archetype_name}")
            if manipulation_score > 0.3:
                entry.append("Wait for manipulation score to drop below 0.30")
            if epigenetic_drift > 0.25:
                entry.append("Wait for behavioral drift to stabilize below 0.20")

        # 16. Exit conditions
        exit_ = []
        if decision in ("BUY", "STRONG_BUY"):
            exit_.append(f"C(t) drops below {max(0.3, coherence - 0.20):.2f}")
            exit_.append("Archetype shifts to Distribution or Liquidity Drain")
            exit_.append("Lifecycle stage enters DECLINE")
            exit_.append("Manipulation score exceeds 0.60")
        elif decision in ("SHORT", "STRONG_AVOID"):
            exit_.append("C(t) recovers above 0.60")
            exit_.append("New governance or team shows behavioral improvement")

        # 17. Investment thesis
        thesis_parts = [
            f"{entity_id[:16]} shows '{archetype_name}' behavioral pattern",
            f"in {lifecycle_stage} stage with C(t)={coherence:.3f}.",
            f"Thermodynamic phase: {thermo_phase} (free energy={thermo_free_energy:.3f}).",
        ]
        if manipulation_score > 0.4:
            thesis_parts.append(f"CAUTION: Elevated manipulation fingerprint ({manipulation_score:.3f}).")
        if epigenetic_drift > 0.3:
            thesis_parts.append(f"CAUTION: Significant behavioral drift ({epigenetic_drift:.3f}) — possible regime change.")
        thesis_parts.append(f"Decision: {decision} with {confidence:.0%} confidence.")

        return InvestmentSignal(
            entity_id=entity_id,
            timestamp=t0,
            decision=decision,
            confidence=confidence,
            behavioral_alpha=behavioral_alpha,
            coherence_score=round(coherence, 4),
            archetype_score=round(arch_fav, 4),
            lifecycle_score=round(lc_fav, 4),
            thermo_score=round(thermo_combined, 4),
            manipulation_free_score=round(manip_penalty, 4),
            risk_level=risk_level,
            max_drawdown_estimate=drawdown,
            archetype=archetype_name,
            lifecycle_stage=lifecycle_stage,
            phase=thermo_phase,
            trajectory=trajectory,
            recommended_horizon=horizon,
            entry_conditions=entry,
            exit_conditions=exit_,
            thesis=" ".join(thesis_parts),
        )

    def scan_portfolio(self, entities: List[Dict]) -> Dict:
        signals = []
        for e in entities:
            sig = self.analyze(
                entity_id=e.get("entity_id", "unknown"),
                phi_vector=e.get("phi_vector", [0.5] * 9),
                coherence=e.get("coherence", 0.5),
                manipulation_score=e.get("manipulation_score", 0.0),
                lifecycle_stage=e.get("lifecycle_stage", "MATURITY"),
                thermo_phase=e.get("thermo_phase", "LIQUID"),
                thermo_free_energy=e.get("thermo_free_energy", 0.5),
                market_volatility=e.get("market_volatility", 0.3),
            )
            signals.append(asdict(sig))

        buy_signals = [s for s in signals if s["decision"] in ("STRONG_BUY", "BUY")]
        avoid_signals = [s for s in signals if s["decision"] in ("STRONG_AVOID", "SHORT")]

        return {
            "total_entities": len(signals),
            "buy_signals": len(buy_signals),
            "avoid_signals": len(avoid_signals),
            "watch_signals": len(signals) - len(buy_signals) - len(avoid_signals),
            "avg_behavioral_alpha": round(
                sum(s["behavioral_alpha"] for s in signals) / max(len(signals), 1), 4
            ),
            "signals": signals,
        }


_investment_engine: Optional[InvestmentEngine] = None


def get_investment_engine() -> InvestmentEngine:
    global _investment_engine
    if _investment_engine is None:
        _investment_engine = InvestmentEngine()
    return _investment_engine
