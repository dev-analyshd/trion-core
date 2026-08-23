"""
TRION Thermodynamic Extension
================================
Extends C(t) with thermodynamic potentials from statistical mechanics.
Treats blockchain ecosystems as thermodynamic systems:

  Energy (E)       = transaction fee flow (gas × price)
  Temperature (T)  = market volatility (normalized)
  Entropy (S)      = behavioral disorder (Shannon entropy of tx distribution)
  Free Energy (F)  = F = E - T·S (available useful work)
  Enthalpy (H)     = E + P·V (total system energy including "volume pressure")
  Heat Capacity    = ΔS/ΔT (how fast entropy changes with temperature)
  Phase Transitions = detected regime changes (gas→liquid→solid analogy)

This module produces:
  - Thermodynamic health score
  - Free energy available for "useful work" (real productive activity)
  - Phase state: GAS (chaotic) | LIQUID (active) | SOLID (stable) | PLASMA (exploit)
  - Carnot efficiency: how efficiently the protocol converts energy to coherence
  - Critical temperature: the threshold where phase transition occurs
"""

import math
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ThermoState:
    entity_id: str
    timestamp: int
    # Core thermodynamic quantities
    energy: float           # normalized transaction energy (fee flow)
    temperature: float      # market volatility (0=cold, 1=hot)
    entropy: float          # behavioral disorder (0=ordered, 1=chaotic)
    free_energy: float      # F = E - T*S (useful work potential)
    enthalpy: float         # H = E + P*V (total system energy)
    # Phase state
    phase: str              # SOLID | LIQUID | GAS | PLASMA
    phase_stability: float  # 0=unstable, 1=stable
    # Derived
    carnot_efficiency: float   # theoretical max efficiency
    heat_capacity: float       # dS/dT
    critical_temperature: float  # phase transition threshold
    thermodynamic_health: float  # overall health score 0-1
    gibbs_free_energy: float    # G = H - T*S (another free energy measure)
    # Signals
    phase_transition_risk: float    # probability of regime change
    useful_work_fraction: float     # what fraction of energy goes to useful activity


class ThermoEngine:
    """
    Computes thermodynamic properties of on-chain entities.
    
    Phase states (blockchain analogy):
      SOLID  → Low activity, ordered, stable (e.g., cold storage, dormant protocol)
      LIQUID → Active, moderately ordered, normal operation
      GAS    → Highly active, disordered, speculative (bull market, high volatility)
      PLASMA → Extreme disorder, exploit/crash/manipulation in progress
    """

    # Phase transition boundaries
    TEMP_SOLID_LIQUID = 0.20    # T below this → SOLID
    TEMP_LIQUID_GAS = 0.60      # T above this → GAS
    TEMP_GAS_PLASMA = 0.85      # T above this → PLASMA

    ENTROPY_THRESHOLD_ORDER = 0.25   # very ordered
    ENTROPY_THRESHOLD_CHAOS = 0.75   # chaotic

    def compute(self, entity_id: str, phi_vector: List[float],
                market_volatility: float, fee_flow_normalized: float,
                tx_count: int = 100, block_time_s: float = 13.0) -> ThermoState:

        # 1. ENERGY: proportional to fee flow and tx volume
        energy = min(1.0, fee_flow_normalized * 0.6 + (tx_count / 5000.0) * 0.4)

        # 2. TEMPERATURE: market volatility
        temperature = min(1.0, market_volatility)

        # 3. ENTROPY: from phi vector Shannon diversity
        phi = np.array(phi_vector, dtype=np.float32)
        phi_safe = np.clip(phi, 1e-10, 1.0)
        phi_norm = phi_safe / phi_safe.sum()
        shannon = -float(np.sum(phi_norm * np.log2(phi_norm)))
        max_shannon = math.log2(len(phi_norm))
        entropy = min(1.0, shannon / (max_shannon + 1e-10))

        # 4. FREE ENERGY: F = E - T*S
        free_energy = max(0.0, energy - temperature * entropy)
        free_energy = round(min(1.0, free_energy), 4)

        # 5. PRESSURE: approximate as tx density
        pressure = min(1.0, tx_count / 10000.0)

        # 6. VOLUME: protocol "size" (approximated by phi complexity)
        volume = float(np.mean(phi)) * 2.0
        volume = min(1.0, volume)

        # 7. ENTHALPY: H = E + P*V
        enthalpy = min(1.0, energy + pressure * volume)

        # 8. GIBBS FREE ENERGY: G = H - T*S
        gibbs = max(0.0, min(1.0, enthalpy - temperature * entropy))

        # 9. HEAT CAPACITY: dS/dT (sensitivity of entropy to temperature)
        # Approximated from current state
        heat_capacity = abs(entropy - temperature) * 2.0

        # 10. CARNOT EFFICIENCY: 1 - T_cold/T_hot
        # T_cold = baseline temperature (0.1), T_hot = current temperature
        t_cold = 0.10
        t_hot = max(t_cold + 0.01, temperature)
        carnot_efficiency = 1.0 - (t_cold / t_hot)

        # 11. USEFUL WORK FRACTION: what fraction of energy is productive
        useful_work_fraction = free_energy / max(energy, 1e-10)
        useful_work_fraction = round(min(1.0, useful_work_fraction), 4)

        # 12. PHASE STATE
        if temperature >= self.TEMP_GAS_PLASMA:
            phase = "PLASMA"
            phase_stability = 0.05
        elif temperature >= self.TEMP_LIQUID_GAS:
            phase = "GAS"
            phase_stability = 0.35
        elif temperature >= self.TEMP_SOLID_LIQUID:
            phase = "LIQUID"
            phase_stability = 0.75
        else:
            phase = "SOLID"
            phase_stability = 0.90

        # Entropy adjustment to phase stability
        if entropy > self.ENTROPY_THRESHOLD_CHAOS:
            phase_stability = max(0.0, phase_stability - 0.30)
        elif entropy < self.ENTROPY_THRESHOLD_ORDER:
            phase_stability = min(1.0, phase_stability + 0.10)

        # 13. CRITICAL TEMPERATURE: phase transition threshold
        # From Landau theory: T_c ≈ coordination_number × exchange_energy
        critical_temperature = 0.5 + (1.0 - entropy) * 0.3

        # 14. PHASE TRANSITION RISK
        delta_T = abs(temperature - critical_temperature)
        phase_transition_risk = round(max(0.0, 1.0 - delta_T * 2.0), 4)

        # 15. THERMODYNAMIC HEALTH
        thermo_health = (
            free_energy * 0.35 +
            (1.0 - entropy * temperature) * 0.25 +
            carnot_efficiency * 0.20 +
            phase_stability * 0.20
        )
        thermo_health = round(min(1.0, max(0.0, thermo_health)), 4)

        return ThermoState(
            entity_id=entity_id,
            timestamp=int(time.time()),
            energy=round(energy, 4),
            temperature=round(temperature, 4),
            entropy=round(entropy, 4),
            free_energy=free_energy,
            enthalpy=round(enthalpy, 4),
            phase=phase,
            phase_stability=round(phase_stability, 4),
            carnot_efficiency=round(carnot_efficiency, 4),
            heat_capacity=round(heat_capacity, 4),
            critical_temperature=round(critical_temperature, 4),
            thermodynamic_health=thermo_health,
            gibbs_free_energy=round(gibbs, 4),
            phase_transition_risk=phase_transition_risk,
            useful_work_fraction=useful_work_fraction,
        )

    def detect_phase_transition(self, history: List[ThermoState]) -> Dict:
        if len(history) < 3:
            return {"transition_detected": False, "confidence": 0.0}

        phases = [s.phase for s in history[-10:]]
        temps = [s.temperature for s in history[-10:]]
        entropies = [s.entropy for s in history[-10:]]

        # Detect phase change
        phase_changes = sum(1 for i in range(1, len(phases)) if phases[i] != phases[i-1])
        temp_trend = (temps[-1] - temps[0]) if len(temps) > 1 else 0.0
        entropy_trend = (entropies[-1] - entropies[0]) if len(entropies) > 1 else 0.0

        transition_confidence = min(1.0, phase_changes * 0.3 +
                                    abs(temp_trend) * 0.4 +
                                    abs(entropy_trend) * 0.3)

        transition_type = None
        if temp_trend > 0.2 and entropy_trend > 0.2:
            transition_type = "HEATING_UP"  # bull run or attack incoming
        elif temp_trend < -0.2 and entropy_trend < -0.1:
            transition_type = "COOLING_DOWN"  # stabilization or decline
        elif entropy_trend > 0.3:
            transition_type = "ENTROPY_SURGE"  # potential exploit
        elif phase_changes >= 2:
            transition_type = "OSCILLATING"  # unstable system

        return {
            "transition_detected": transition_confidence > 0.4,
            "confidence": round(transition_confidence, 4),
            "transition_type": transition_type,
            "current_phase": phases[-1] if phases else "UNKNOWN",
            "temperature_trend": round(temp_trend, 4),
            "entropy_trend": round(entropy_trend, 4),
            "description": (
                f"System {'is' if transition_confidence > 0.4 else 'is not'} "
                f"undergoing phase transition. "
                f"Type: {transition_type or 'stable'}. "
                f"Temperature trending {'up' if temp_trend > 0 else 'down'}."
            )
        }

    def compute_ecosystem_entropy(self, entities: List[Dict]) -> Dict:
        if not entities:
            return {"ecosystem_entropy": 0.5, "entities": 0}

        entropies = [e.get("entropy", 0.5) for e in entities]
        temps = [e.get("temperature", 0.5) for e in entities]
        free_energies = [e.get("free_energy", 0.5) for e in entities]

        ecosystem_entropy = sum(entropies) / len(entropies)
        ecosystem_temp = sum(temps) / len(temps)
        total_free_energy = sum(free_energies)

        # Phase distribution
        phases = [e.get("phase", "LIQUID") for e in entities]
        phase_dist = {p: phases.count(p) / len(phases) for p in set(phases)}

        return {
            "ecosystem_entropy": round(ecosystem_entropy, 4),
            "ecosystem_temperature": round(ecosystem_temp, 4),
            "total_free_energy": round(total_free_energy, 4),
            "phase_distribution": phase_dist,
            "entities": len(entities),
            "health": round((1.0 - ecosystem_entropy) * 0.5 +
                           total_free_energy / max(len(entities), 1) * 0.5, 4),
        }


_thermo_engine: Optional[ThermoEngine] = None


def get_thermo_engine() -> ThermoEngine:
    global _thermo_engine
    if _thermo_engine is None:
        _thermo_engine = ThermoEngine()
    return _thermo_engine
