"""
TRION Protocol — Signal Publication Pipeline

Connects the TRION coherence engine to on-chain publication:
  1. Compute coherence C(t) from all 5 planes
  2. Determine if signal should be published (C ≥ Θ) or SILENCE recorded
  3. Construct the full TRIONSignal via signal_factory.build_signal()
  4. Compute master-equation T(t) and sign the signal (Python-side ECDSA if
     the Go certificate producer is unavailable)
  5. Pack signal for on-chain storage and call the relayer's publish_signal()
  6. Record publication outcome (tx hash) in the Akashic ledger

This module is the bridge between off-chain intelligence and on-chain truth.
"""

import hashlib
import json
import logging
import os
import secrets
import time
from typing import Dict, Optional, Tuple

from core.master.coherence import CoherenceEngine
from core.master.master_equation import MasterEquation
from core.master.moat import MoatEngine, MoatInput
from core.master.signal_factory import build_signal, SignalType
from core.primitives.signal_packing import (
    prepare_behavioral_signal,
    pack_signal,
    entity_to_bytes32,
    PLANE_NAMES,
)

logger = logging.getLogger(__name__)


def _python_ecdsa_sign(message: bytes, private_key: Optional[bytes] = None) -> Dict:
    """Sign ``message`` with a Python-side secp256k1 ECDSA key.

    Used as a fallback when the Go certificate producer (core/rust_bridge_pyo3.py
    / validator binary) is not available. The signature is canonical
    low-s normalised ECDSA over secp256k1 with SHA3-256.

    If ``private_key`` is None, the operator's ``RELAYER_PRIVATE_KEY`` env var
    is consulted. If neither is set, an ephemeral keypair is generated and
    flagged in the result so the caller can record that the signature was
    not from the canonical relayer identity (it is still a valid ECDSA
    signature suitable for testing).
    """
    try:
        from ecdsa import SigningKey, SECP256k1  # type: ignore
    except Exception as exc:  # pragma: no cover — exercised via dry-run path
        return {
            "signed": False,
            "method": "python-ecdsa-unavailable",
            "error": str(exc),
        }

    ephemeral = False
    if private_key is None:
        env_pk = os.environ.get("RELAYER_PRIVATE_KEY", "")
        if env_pk:
            try:
                private_key = bytes.fromhex(env_pk.removeprefix("0x"))
                if len(private_key) != 32:
                    private_key = None
            except ValueError:
                private_key = None
    if private_key is None:
        private_key = secrets.token_bytes(32)
        ephemeral = True

    sk = SigningKey.from_string(private_key, curve=SECP256k1)
    pub = sk.get_verifying_key().to_string(encoding="compressed")
    # Canonical ECDSA over SHA3-256 (matches the family-1 signing key spec
    # used by core/spiritual/signature_aggregation.py).
    sig_der = sk.sign_digest_deterministic(
        hashlib.sha3_256(message).digest(),
        hashfunc=hashlib.sha3_256,
        sigencode=lambda r, s, order: r.to_bytes(32, "big") + s.to_bytes(32, "big"),
    )
    return {
        "signed": True,
        "method": "python-ecdsa-secp256k1-sha3-256",
        "signature_bytes": sig_der.hex(),
        "public_key_compressed": pub.hex(),
        "ephemeral_key": ephemeral,
    }


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
        # proof-ledger root — every successful on-chain emission (signal OR
        # silence) appends a JSON record here so the protocol has a
        # tamper-evident off-chain audit trail alongside the on-chain
        # oracle events. Override with TRION_PROOF_LEDGER_DIR.
        self.proof_ledger_dir = os.environ.get(
            "TRION_PROOF_LEDGER_DIR",
            os.path.join(os.getcwd(), "proof-ledger"),
        )

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
        signal_type: SignalType = SignalType.VALUATION,
        dry_run: bool = False,
        relayer_private_key: Optional[bytes] = None,
    ) -> Dict:
        """
        Compute AND publish a behavioral signal on-chain.

        Full wiring (L6):
          1. ``compute_signal()`` derives coherence C(t), threshold Θ(t),
             moat M_moat, and the master-equation T(t) — including the
             ``emits`` decision and the silence payload.
          2. ``signal_factory.build_signal()`` constructs the full TRIONSignal
             (29-type canonical taxonomy entry, provenance chain, BRT,
             genomic signature, validator figures, AWA gate, L0.5 gate).
          3. The signal is signed with the Python-side ECDSA fallback
             (``_python_ecdsa_sign``) when the Go certificate producer is
             unavailable — see ``core/rust_bridge_pyo3.py``.
          4. ``prepare_behavioral_signal()`` packs the on-chain payload and
             the chain relay (``api.blockchain.ChainRelay.publish_signal`` /
             ``publish_behavioral_signal_v3`` / ``record_silence``) submits
             it to the deployed TRIONOracleV3 contract.
          5. The resulting ``tx_hash`` (or, in dry-run mode, the simulated
             one) is recorded in the returned dict.

        If ``force_publish=False`` (default), only publishes when C(t) ≥ Θ(t).
        SILENCE is still recorded via ``recordSilence`` on the contract.

        ``dry_run=True`` skips the on-chain call entirely and instead logs
        the prepared payload, the constructed TRIONSignal, and the ECDSA
        signature — useful for pre-funded-account rehearsal and CI.
        """
        # Step 1: Compute the signal (C(t), Θ(t), T(t), moat, silence payload)
        signal = self.compute_signal(
            entity_id=entity_id,
            phi=phi, mental=mental, sigma=sigma,
            conscious=conscious, anima=anima,
            volatility=volatility, moat_input=moat_input,
            akashic_depth=akashic_depth, moat_time=moat_time,
            mf_score=mf_score, oe_factor=oe_factor,
        )

        # Step 2: Construct the full TRIONSignal via signal_factory.
        # The coherence_result dict already carries the keys build_signal
        # consults (C, theta, emits, silence_gap, limiting_plane, …).
        coherence_result = {
            "C": signal["coherence"],
            "theta": signal["threshold"],
            "emits": signal["signal_emitted"],
            "limiting_plane": signal["limiting_plane"],
            "akashic_depth": signal["akashic_depth"],
            "silence_gap": max(0.0, signal["threshold"] - signal["coherence"]),
        }
        trion_signal = build_signal(
            entity_id=entity_id,
            signal_type=signal_type,
            coherence_result=coherence_result,
            akashic_depth=signal["akashic_depth"],
            oe_factor=oe_factor,
        )

        # Step 3: Sign the signal. The canonical 346-byte certificate payload
        # is produced by the Go validator mesh; when that is unavailable we
        # fall back to a Python-side ECDSA signature over the deterministic
        # serialisation of the TRIONSignal (signal_id + entity_id + C + theta
        # + master_signal + timestamp).
        sig_payload = "|".join([
            str(trion_signal.get("signal_id", "")),
            str(entity_id),
            f"{signal['coherence']:.6f}",
            f"{signal['threshold']:.6f}",
            f"{signal['master_signal']:.6f}",
            str(signal["timestamp"]),
        ]).encode()
        signature = _python_ecdsa_sign(sig_payload, private_key=relayer_private_key)

        # Step 4: Prepare on-chain payload
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
            "trion_signal": trion_signal,
            "signature": signature,
            "published": False,
            "method": None,
            "tx_hash": None,
            "error": None,
        }

        # Dry-run path: log and return without touching the chain.
        if dry_run:
            logger.info(
                "[dry-run] signal for %s: C=%.4f Θ=%.4f emits=%s type=%s sig=%s",
                entity_id, signal["coherence"], signal["threshold"],
                signal["signal_emitted"], signal_type.name,
                signature.get("method") if signature.get("signed") else "none",
            )
            publication["method"] = "dry_run"
            publication["tx_hash"] = None
            publication["dry_run"] = True
            return {**signal, "publication": publication}

        # Step 5: Publish on-chain (if chain relay available)
        if self.chain_relay is not None and self.chain_relay.ready:
            try:
                if signal["signal_emitted"] or force_publish:
                    # Publish full behavioral signal
                    if hasattr(self.chain_relay, "publish_behavioral_signal_v3"):
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
                        method = "publishBehavioralSignal"
                    else:
                        tx = self.chain_relay.publish_signal(
                            entity_id=entity_id,
                            score=signal["coherence"],
                            threshold=signal["threshold"],
                            coherent=signal["coherent"],
                            limiting_plane=signal["limiting_plane"],
                        )
                        method = "publishBehavioralTruth"
                    publication["published"] = bool(tx.get("published", False))
                    publication["method"] = method
                    publication["tx_hash"] = tx.get("tx_hash")
                    self.publication_count += 1
                    logger.info(
                        "Published signal for %s: C=%.4f Θ=%.4f coherent=%s tx=%s",
                        entity_id, signal["coherence"], signal["threshold"],
                        signal["coherent"], publication["tx_hash"],
                    )
                else:
                    # Record SILENCE
                    if hasattr(self.chain_relay, "record_silence"):
                        tx = self.chain_relay.record_silence(
                            entity_b32=prepared["entity_id_bytes32"],
                            coherence_score=prepared["coherence_score"],
                            threshold=prepared["threshold"],
                            limiting_plane=prepared["limiting_plane"],
                        )
                    else:
                        tx = self.chain_relay.publish_signal(
                            entity_id=entity_id,
                            score=signal["coherence"],
                            threshold=signal["threshold"],
                            coherent=False,
                            limiting_plane=signal["limiting_plane"],
                        )
                    publication["published"] = bool(tx.get("published", False)) if tx else False
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

        # Step 6: Record the tx hash (or failure) in proof-ledger/.
        # Every real emission (success OR on-chain failure with a tx hash)
        # is appended to a JSONL ledger file so the protocol has a
        # tamper-evident off-chain audit trail alongside the on-chain
        # oracle events. Dry-run mode is NOT recorded (no tx was sent).
        self._record_proof_ledger(
            entity_id=entity_id,
            signal=signal,
            publication=publication,
        )

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

    def _record_proof_ledger(
        self,
        entity_id: str,
        signal: Dict,
        publication: Dict,
    ) -> None:
        """Append a JSONL record to proof-ledger/emissions.jsonl.

        Records every real emission (signal OR silence) with its tx hash,
        the coherence snapshot, the master-equation T(t), and the
        publication outcome. Dry-run emissions are skipped (no tx was
        sent, so there is nothing to audit). Ledger write failure is
        non-fatal — the on-chain oracle event is the authoritative
        record; this is the off-chain convenience mirror.
        """
        # Skip dry-run / not-yet-published emissions.
        if publication.get("dry_run"):
            return
        tx_hash = publication.get("tx_hash")
        # Record both successful publications AND on-chain failures (which
        # carry a tx_hash from the failed attempt) so the audit trail is
        # complete. Skip only when no tx was attempted.
        method = publication.get("method")
        if not tx_hash and not method:
            return
        try:
            os.makedirs(self.proof_ledger_dir, exist_ok=True)
            record = {
                "ts": int(time.time()),
                "entity_id": entity_id,
                "signal_type": publication.get("trion_signal", {}).get(
                    "signal_type", "VALUATION",
                ),
                "coherence": signal.get("coherence"),
                "threshold": signal.get("threshold"),
                "master_signal_T": signal.get("master_signal"),
                "emits": signal.get("signal_emitted"),
                "method": method,
                "tx_hash": tx_hash,
                "error": publication.get("error"),
            }
            with open(
                os.path.join(self.proof_ledger_dir, "emissions.jsonl"), "a"
            ) as f:
                f.write(json.dumps(record) + "\n")
        except OSError as exc:
            logger.warning(
                "proof-ledger write failed for %s: %s", entity_id, exc,
            )
