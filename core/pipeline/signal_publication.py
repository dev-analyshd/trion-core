"""
TRION Protocol — Signal Publication Pipeline

Connects the TRION coherence engine to on-chain publication:
  1. Compute coherence C(t) from all 5 planes
  2. Determine if signal should be published (C ≥ Θ) or SILENCE recorded
  3. Pack signal for on-chain storage
  4. Call oracle contract via ChainRelay
  5. Record publication outcome in Akashic ledger

This module is the bridge between off-chain intelligence and on-chain truth.
"""

import logging
import time
from typing import Dict, Optional, Tuple

from core.master.coherence import CoherenceEngine
from core.master.master_equation import MasterEquation
from core.master.moat import MoatEngine, MoatInput
from core.primitives.signal_packing import (
    prepare_behavioral_signal,
    pack_signal,
    entity_to_bytes32,
    PLANE_NAMES,
)

logger = logging.getLogger(__name__)


class SignalPublicationPipeline:
    """
    End-to-end pipeline: compute signal → pack → publish on-chain.

    Usage:
        pipeline = SignalPublicationPipeline()
        result = pipeline.publish(
            entity_id="0x...",
            phi=0.48, mental=0.99, sigma=0.25, conscious=0.10, anima=0.56,
            volatility=0.3,
        )
    """

    def __init__(
        self,
        coherence_engine: Optional[CoherenceEngine] = None,
        master_equation: Optional[MasterEquation] = None,
        moat_engine: Optional[MoatEngine] = None,
        chain_relay=None,  # api.blockchain.ChainRelay, optional
        profile: str = "DEFAULT",
    ):
        self.coherence = coherence_engine or CoherenceEngine()
        self.master_eq = master_equation or MasterEquation()
        self.moat = moat_engine or MoatEngine()
        self.chain_relay = chain_relay
        self.profile = profile
        self.publication_count = 0
        self.silence_count = 0

    def compute_signal(
        self,
        entity_id: str,
        phi: float,
        mental: float,
        sigma: float,
        conscious: float,
        anima: float,
        volatility: float = 0.0,
        moat_input: Optional[MoatInput] = None,
        akashic_depth: float = 100.0,
        moat_time: float = 1.0,
        mf_score: float = 0.0,
        oe_factor: float = 0.0,
    ) -> Dict:
        """
        Compute the full TRION signal for an entity without publishing.

        Returns dict with coherence, threshold, master_signal, moat, planes, etc.
        """
        from core.master.coherence import CoherenceInput, AssetProfile

        # Step 1: Adjust planes for manipulation fingerprints and observer effect
        phi_adj = self.coherence.apply_mf_to_phi(phi, mf_score)
        m_adj = self.coherence.apply_oe_to_m(mental, oe_factor)

        # Map profile name to AssetProfile enum
        profile_enum = AssetProfile.DEFAULT
        try:
            profile_enum = AssetProfile[self.profile.upper()]
        except (KeyError, AttributeError):
            pass

        # Step 2: Compute coherence C(t) via CoherenceInput dataclass
        coh_input = CoherenceInput(
            phi_adj=phi_adj,
            m_adj=m_adj,
            sigma=sigma,
            k_plane=conscious,
            anima=anima,
            volatility=volatility,
            akashic_depth=akashic_depth,
            moat_time=moat_time,
            profile=profile_enum,
        )
        coh_result = self.coherence.compute_coherence(coh_input)

        coherence = coh_result.get("C", 0.0)
        threshold = coh_result.get("theta", 0.7)
        coherent = coh_result.get("emits", False)
        limiting_plane = coh_result.get("limiting_plane", "Physical")

        # Step 3: Compute economic moat M_moat
        if moat_input is None:
            moat_input = MoatInput(
                akashic_depth=akashic_depth,
                k_plane=conscious,
                m_adj=m_adj,
                f_registry=0,
                moat_time=moat_time,
            )
        moat_result = self.moat.compute(moat_input)
        moat_factor = moat_result.get("moat_factor", 0.0)

        # Step 4: Compute master equation T(t) — takes coherence_result dict
        master_result = self.master_eq.compute(coh_result)
        master_signal = master_result.t
        signal_emitted = master_result.emits
        master_margin = master_result.margin
        master_trend = master_result.trend

        return {
            "entity_id": entity_id,
            "coherence": coherence,
            "threshold": threshold,
            "coherent": coherent,
            "limiting_plane": limiting_plane,
            "moat_factor": moat_factor,
            "moat_components": moat_result.get("components", {}),
            "master_signal": master_signal,
            "signal_emitted": signal_emitted,
            "master_margin": master_margin,
            "master_trend": master_trend,
            "silence_reason": master_result.silence_reason,
            "planes": {
                "phi": phi,
                "mental": mental,
                "sigma": sigma,
                "conscious": conscious,
                "anima": anima,
            },
            "planes_adjusted": {
                "phi_adj": phi_adj,
                "m_adj": m_adj,
            },
            "volatility": volatility,
            "akashic_depth": akashic_depth,
            "profile": self.profile,
            "timestamp": int(time.time()),
        }

    def publish(
        self,
        entity_id: str,
        phi: float,
        mental: float,
        sigma: float,
        conscious: float,
        anima: float,
        volatility: float = 0.0,
        moat_input: Optional[MoatInput] = None,
        akashic_depth: float = 100.0,
        moat_time: float = 1.0,
        mf_score: float = 0.0,
        oe_factor: float = 0.0,
        block_number: Optional[int] = None,
        force_publish: bool = False,
    ) -> Dict:
        """
        Compute AND publish a behavioral signal on-chain.

        If force_publish=False (default), only publishes when C(t) ≥ Θ(t).
        SILENCE is still recorded via emitSilence on the contract.

        Returns dict with computation result + publication outcome.
        """
        # Step 1: Compute the signal
        signal = self.compute_signal(
            entity_id=entity_id,
            phi=phi, mental=mental, sigma=sigma,
            conscious=conscious, anima=anima,
            volatility=volatility, moat_input=moat_input,
            akashic_depth=akashic_depth, moat_time=moat_time,
            mf_score=mf_score, oe_factor=oe_factor,
        )

        # Step 2: Prepare on-chain payload
        prepared = prepare_behavioral_signal(
            entity_id=entity_id,
            coherence=signal["coherence"],
            threshold=signal["threshold"],
            moat_factor=signal["moat_factor"],
            phi=phi, mental=mental, sigma=sigma,
            conscious=conscious, anima=anima,
            block_number=block_number,
            timestamp=signal["timestamp"],
        )

        publication = {
            "prepared": prepared,
            "published": False,
            "method": None,
            "tx_hash": None,
            "error": None,
        }

        # Step 3: Publish on-chain (if chain relay available)
        if self.chain_relay is not None and self.chain_relay.ready:
            try:
                if signal["signal_emitted"] or force_publish:
                    # Publish full behavioral signal
                    tx = self.chain_relay.publish_behavioral_signal_v3(
                        entity_b32=prepared["entity_id_bytes32"],
                        commitment=prepared["public_commitment"],
                        coherence_score=prepared["coherence_score"],
                        threshold=prepared["threshold"],
                        moat_factor=prepared["moat_factor"],
                        coherent=prepared["coherent"],
                        limiting_plane=prepared["limiting_plane"],
                        phi_plane=prepared["phi_plane"],
                        mental_plane=prepared["mental_plane"],
                        sigma_plane=prepared["sigma_plane"],
                        conscious_plane=prepared["conscious_plane"],
                        anima_plane=prepared["anima_plane"],
                    )
                    publication["published"] = True
                    publication["method"] = "publishBehavioralSignal"
                    publication["tx_hash"] = tx.get("tx_hash")
                    self.publication_count += 1
                    logger.info(
                        "Published signal for %s: C=%.4f Θ=%.4f coherent=%s tx=%s",
                        entity_id, signal["coherence"], signal["threshold"],
                        signal["coherent"], publication["tx_hash"],
                    )
                else:
                    # Record SILENCE
                    tx = self.chain_relay.record_silence(
                        entity_b32=prepared["entity_id_bytes32"],
                        coherence_score=prepared["coherence_score"],
                        threshold=prepared["threshold"],
                        limiting_plane=prepared["limiting_plane"],
                    )
                    publication["published"] = True
                    publication["method"] = "recordSilence"
                    publication["tx_hash"] = tx.get("tx_hash") if tx else None
                    self.silence_count += 1
                    logger.info(
                        "Recorded SILENCE for %s: C=%.4f < Θ=%.4f",
                        entity_id, signal["coherence"], signal["threshold"],
                    )
            except Exception as e:
                publication["error"] = str(e)
                logger.error("Publication failed for %s: %s", entity_id, e)
        else:
            publication["error"] = "chain_relay not ready"
            logger.warning("Chain relay not ready — signal computed but not published")

        return {
            **signal,
            "publication": publication,
        }

    def publish_batch(
        self,
        entities: list,  # List of dicts with entity_id + plane values
        volatility: float = 0.0,
    ) -> list:
        """Publish signals for multiple entities in batch."""
        results = []
        for entity in entities:
            result = self.publish(
                entity_id=entity["entity_id"],
                phi=entity["phi"],
                mental=entity["mental"],
                sigma=entity["sigma"],
                conscious=entity["conscious"],
                anima=entity["anima"],
                volatility=volatility,
                moat_input=entity.get("moat_input"),
                block_number=entity.get("block_number"),
            )
            results.append(result)
        return results

    def stats(self) -> Dict:
        """Return pipeline statistics."""
        return {
            "publication_count": self.publication_count,
            "silence_count": self.silence_count,
            "profile": self.profile,
            "chain_ready": self.chain_relay.ready if self.chain_relay else False,
        }
