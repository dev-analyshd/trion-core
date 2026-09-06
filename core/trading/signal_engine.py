"""
TRION Trading Signal Engine
---------------------------
Converts five-plane behavioral coherence into
structured trading signals for AI agent consumption.

Flow:
  1. Fetch entity behavioral data from FAISS
  2. Compute Φ(t) nine features
  3. Compute C(t) five-plane coherence
  4. Match against pattern archetypes (cosine similarity)
  5. Apply NL liquidity filter
  6. Apply MF manipulation filter
  7. Emit TRIONTradeSignal

Output consumed by AI agent via REST or FAISS vector comparison.
"""

import numpy as np
import os
import time
import sys
sys.path.insert(0, '.')

from core.trading.pattern_archetypes import (
    match_archetype, TradingSignal, ARCHETYPE_MATRIX, ARCHETYPES
)


class TradingSignalEngine:

    def __init__(self, faiss_url: str = "http://127.0.0.1:8000"):
        self.faiss_url = faiss_url
        # X-API-Key for the FAISS service (SEC-01) — same resolution order as
        # faiss_service.py itself: FAISS_API_KEY → FAISS_SERVICE_API_KEY →
        # TRION_API_KEY.  Empty → None → header omitted (the GET then fails
        # closed on the service side, which is the safe posture).  Resolved
        # once here like core/realtime/bh_streamer.py's FAISSAccumulator —
        # core must not import from the api/ package above it.
        self._faiss_api_key = (
            os.environ.get("FAISS_API_KEY")
            or os.environ.get("FAISS_SERVICE_API_KEY")
            or os.environ.get("TRION_API_KEY")
            or ""
        ).strip() or None

    def _faiss_headers(self) -> dict:
        return {"X-API-Key": self._faiss_api_key} if self._faiss_api_key else {}

    async def fetch_entity_vector(self, entity_id: str) -> dict:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(
                    f"{self.faiss_url}/api/v1/signal/{entity_id}",
                    headers=self._faiss_headers(),
                )
                if r.status_code == 200:
                    return r.json()
        except Exception:
            pass
        return {}

    def phi_from_faiss_vector(
        self,
        vector:    list,
        magnitude: float = 0.5,
    ) -> np.ndarray:
        """
        Convert a raw FAISS vector (16-dim) to the 9 Φ features.
        FAISS stores compressed behavioral representations.
        We project back to the interpretable 9-feature space.
        """
        v = np.array(vector[:16] if len(vector) >= 16 else vector)
        projection = np.array([
            [0.30, 0.20, 0.10, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05,
             0.02, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01],
            [0.05, 0.30, 0.15, 0.10, 0.05, 0.05, 0.05, 0.05, 0.05,
             0.02, 0.02, 0.02, 0.02, 0.01, 0.01, 0.00],
            [0.05, 0.10, 0.30, 0.10, 0.10, 0.05, 0.05, 0.05, 0.05,
             0.03, 0.03, 0.02, 0.01, 0.01, 0.00, 0.00],
            [0.05, 0.05, 0.10, 0.30, 0.10, 0.10, 0.05, 0.05, 0.05,
             0.03, 0.02, 0.02, 0.01, 0.01, 0.01, 0.00],
            [0.10, 0.05, 0.05, 0.10, 0.30, 0.10, 0.10, 0.05, 0.05,
             0.03, 0.03, 0.01, 0.01, 0.01, 0.01, 0.00],
            [0.05, 0.05, 0.05, 0.05, 0.10, 0.30, 0.15, 0.10, 0.05,
             0.03, 0.02, 0.02, 0.01, 0.01, 0.01, 0.00],
            [0.05, 0.05, 0.05, 0.05, 0.05, 0.10, 0.30, 0.15, 0.10,
             0.03, 0.02, 0.02, 0.01, 0.01, 0.01, 0.00],
            [0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.10, 0.35, 0.15,
             0.03, 0.02, 0.02, 0.01, 0.01, 0.01, 0.00],
            [0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.10, 0.40,
             0.05, 0.03, 0.02, 0.02, 0.01, 0.01, 0.01],
        ])  # shape: (9, 16)

        v_pad = np.zeros(16)
        v_pad[:len(v)] = v
        v_norm = v_pad / (np.linalg.norm(v_pad) + 1e-9)
        phi_features = projection @ v_norm
        phi_features = np.clip(phi_features * magnitude * 3, 0, 1)
        return phi_features

    def generate_signal(
        self,
        entity_id:     str,
        phi_vector:    np.ndarray,
        coherence:     float,
        threshold:     float,
        akashic_depth: float,
        nl_score:      float = 0.75,
        mf_score:      float = 0.0,
        chain_id:      int   = 421614,
        asset_address: str   = "",
    ) -> dict:
        now = time.time()

        if coherence < threshold:
            return {
                "entity_id":   entity_id,
                "signal":      "SILENCE",
                "signal_id":   -1,
                "confidence":  0.0,
                "tradeable":   False,
                "reason":      "SILENCE",
                "silence_gap": threshold - coherence,
                "coherence":   coherence,
                "threshold":   threshold,
                "explanation": (
                    f"TRION SILENCE: C(t)={coherence:.4f} below "
                    f"Θ(t)={threshold:.4f}. Behavioral coherence "
                    "insufficient. Do not trade."
                ),
                "timestamp":   int(now),
            }

        if mf_score >= 0.70:
            return {
                "entity_id":   entity_id,
                "signal":      "MANIPULATION_ALERT",
                "signal_id":   -2,
                "confidence":  0.0,
                "tradeable":   False,
                "reason":      "MANIPULATION_ALERT",
                "mf_score":    mf_score,
                "explanation": (
                    f"MANIPULATION_ALERT: MF_score={mf_score:.3f}. "
                    "Behavioral pattern indicates coordinated activity. "
                    "Do not trade."
                ),
                "timestamp":   int(now),
            }

        liquidity_warning = nl_score < 0.30

        pattern_result = match_archetype(phi_vector, coherence, akashic_depth)

        base_confidence   = pattern_result.get("confidence", 0.0)
        coherence_margin  = (coherence - threshold) / (1.0 - threshold + 1e-9)
        coherence_bonus   = coherence_margin * 0.20
        mf_discount       = mf_score * 0.50
        liq_discount      = max(0, (0.30 - nl_score)) * 0.30
        final_confidence  = max(0, min(1.0,
            base_confidence + coherence_bonus - mf_discount - liq_discount
        ))

        tradeable = (
            final_confidence >= 0.40 and
            not liquidity_warning and
            mf_score < 0.30
        )

        risk = (
            "HIGH"   if final_confidence >= 0.65 else
            "MEDIUM" if final_confidence >= 0.45 else
            "LOW"
        )

        return {
            "entity_id":      entity_id,
            "chain_id":       chain_id,
            "asset_address":  asset_address,
            "signal":         pattern_result.get("signal", "NEUTRAL"),
            "signal_id":      pattern_result.get("signal_id", 3),
            "confidence":     round(final_confidence, 4),
            "risk":           risk,
            "tradeable":      tradeable,
            "pattern":        pattern_result.get("pattern", ""),
            "description":    pattern_result.get("description", ""),
            "archetype_similarity": round(
                pattern_result.get("raw_similarity", 0), 4
            ),
            "coherence":        round(coherence, 4),
            "threshold":        round(threshold, 4),
            "coherence_margin": round(coherence_margin, 4),
            "nl_score":         round(nl_score, 4),
            "mf_score":         round(mf_score, 4),
            "akashic_depth":    akashic_depth,
            "phi_features": {
                "f1_volume_entropy":         round(float(phi_vector[0]), 4),
                "f2_counterparty_diversity": round(float(phi_vector[1]), 4),
                "f3_temporal_spacing":       round(float(phi_vector[2]), 4),
                "f4_contract_interaction":   round(float(phi_vector[3]), 4),
                "f5_value_flow_direction":   round(float(phi_vector[4]), 4),
                "f6_wallet_architecture":    round(float(phi_vector[5]), 4),
                "f7_cross_protocol":         round(float(phi_vector[6]), 4),
                "f8_gas_pattern":            round(float(phi_vector[7]), 4),
                "f9_mev_interaction":        round(float(phi_vector[8]), 4),
            },
            "pattern_similarities": pattern_result.get("all_similarities", {}),
            "warnings":   ["LIQUIDITY_HEALTH"] if liquidity_warning else [],
            "timestamp":  int(now),
            "ttl_seconds": 60,
            "reasoning": {
                "base_confidence":    round(base_confidence, 4),
                "coherence_bonus":    round(coherence_bonus, 4),
                "mf_discount":        round(mf_discount, 4),
                "liquidity_discount": round(liq_discount, 4),
                "final_confidence":   round(final_confidence, 4),
            },
        }


if __name__ == "__main__":
    engine = TradingSignalEngine()

    accumulation_vec = np.array(
        [0.82, 0.90, 0.85, 0.76, 0.22, 0.71, 0.80, 0.61, 0.91]
    )
    sig1 = engine.generate_signal(
        entity_id="0xWHALE001",
        phi_vector=accumulation_vec,
        coherence=0.72, threshold=0.58,
        akashic_depth=800,
        nl_score=0.75, mf_score=0.02,
    )
    print(f"Signal 1 — {sig1['pattern']}:")
    print(f"  Signal:     {sig1['signal']}")
    print(f"  Confidence: {sig1['confidence']}")
    print(f"  Tradeable:  {sig1['tradeable']}")
    print(f"  Risk:       {sig1['risk']}")

    sig2 = engine.generate_signal(
        entity_id="0xENTITY002",
        phi_vector=accumulation_vec,
        coherence=0.42, threshold=0.58,
        akashic_depth=100,
    )
    print(f"\nSignal 2 — SILENCE: {sig2['signal']} tradeable={sig2['tradeable']}")

    sig3 = engine.generate_signal(
        entity_id="0xATTACKER",
        phi_vector=accumulation_vec,
        coherence=0.72, threshold=0.58,
        akashic_depth=500,
        mf_score=0.95,
    )
    print(f"\nSignal 3 — Manipulation: {sig3['signal']} tradeable={sig3['tradeable']}")

    assert sig1['tradeable']
    assert not sig2['tradeable']
    assert not sig3['tradeable']
    print("\nPHASE 2 PASS — Signal Engine: PASS")
