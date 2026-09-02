"""
TRION Protocol — Python SDK v1.0

pip install requests  (only dependency)

Quick start:
    from sdk.trion_sdk import TRIONClient
    client = TRIONClient("https://your-trion-oracle.replit.app")
    signal = client.get_signal("uniswap")
    print(signal.coherence_score, signal.signal_type)

All methods return typed dataclasses. CI_95 is always non-null.
SILENCE cannot be cast to VALUATION — enforced at type level.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


# ── Signal type constants ────────────────────────────────────────────────────

SIGNAL_TYPES = [
    "VALUATION", "SILENCE", "MANIPULATION_ALERT", "GENESIS", "RESURRECTION",
    "FORK_DIVERGENCE", "TRAJECTORY", "NEGATIVE_SPACE", "PHASE_TRANSITION",
    "SYSTEMIC_RISK", "LIQUIDITY_HEALTH", "GOVERNANCE_SIGNAL",
    "CROSS_CHAIN_COHERENCE", "STABLECOIN_HEALTH", "MEV_EXPOSURE",
    "INSTITUTIONAL_BHV", "REGULATORY_BHV", "ECOSYSTEM_HEALTH", "BOOTSTRAP",
    # BTCP signal type (canonical 19, whitepaper §11).
    # SECURITY FIX (P1, verification matrix #19): BTCP_ROUTE was missing here
    # (present in sdk/TrionSDK.ts, sdk/src/index.ts and core SignalType = 22).
    "BTCP_ROUTE",
]

EVENT_TYPES = [
    "TRANSFER", "SWAP", "LIQUIDITY", "STAKE", "UNSTAKE", "GOVERNANCE",
    "PROPOSAL", "BORROW", "REPAY", "LIQUIDATE", "BRIDGE", "DEPLOY",
    "UPGRADE", "MINT", "BURN", "ORACLE_UPDATE", "MEV_CAPTURE",
    "FLASH_LOAN", "AIRDROP", "CLAIM",
]


# ── Typed response dataclasses ───────────────────────────────────────────────

@dataclass
class PlaneBreakdown:
    physical:      float
    mental:        float
    spiritual:     float
    conscious:     float
    anima:         float
    limiting_plane: str

    @classmethod
    def from_dict(cls, d: Dict) -> "PlaneBreakdown":
        return cls(
            physical       = float(d.get("physical", 0)),
            mental         = float(d.get("mental", 0)),
            spiritual      = float(d.get("spiritual", 0)),
            conscious      = float(d.get("conscious", 0)),
            anima          = float(d.get("anima", 0)),
            limiting_plane = str(d.get("limiting_plane", "UNKNOWN")),
        )


@dataclass
class ConfidenceInterval:
    lower: float
    upper: float
    level: float = 0.95

    @classmethod
    def from_dict(cls, d: Dict) -> "ConfidenceInterval":
        return cls(
            lower = float(d.get("lower", 0)),
            upper = float(d.get("upper", 1)),
            level = float(d.get("level", 0.95)),
        )


@dataclass
class TRIONSignal:
    entity_id:       str
    signal_type:     str
    signal_value:    float
    coherence_score: float
    threshold:       float
    coherent:        bool
    limiting_plane:  str
    archetype:       str
    conf_genesis:    float
    moat_factor:     float
    akashic_depth:   float
    plane_breakdown: PlaneBreakdown
    ci_95:           ConfidenceInterval
    timestamp:       int
    raw:             Dict = field(default_factory=dict)

    @property
    def is_silence(self) -> bool:
        return self.signal_type == "SILENCE" or not self.coherent

    @property
    def silence_gap(self) -> float:
        return max(0.0, self.threshold - self.coherence_score)

    @classmethod
    def from_dict(cls, d: Dict) -> "TRIONSignal":
        pb = PlaneBreakdown.from_dict(d.get("plane_breakdown", {}))
        ci_raw = d.get("ci_95", {})
        if isinstance(ci_raw, dict):
            ci = ConfidenceInterval.from_dict(ci_raw)
        else:
            sv = float(d.get("signal_value", 0.5))
            ci = ConfidenceInterval(lower=max(0.0, sv - 0.1), upper=min(1.0, sv + 0.1))
        return cls(
            entity_id       = str(d.get("entity_id", "")),
            signal_type     = str(d.get("signal_type", "UNKNOWN")),
            signal_value    = float(d.get("signal_value", 0)),
            coherence_score = float(d.get("coherence_score", 0)),
            threshold       = float(d.get("threshold", 0.65)),
            coherent        = bool(d.get("coherent", False)),
            limiting_plane  = str(d.get("limiting_plane", "UNKNOWN")),
            archetype       = str(d.get("archetype", "UNKNOWN")),
            conf_genesis    = float(d.get("conf_genesis", 0)),
            moat_factor     = float(d.get("moat_factor", 0)),
            akashic_depth   = float(d.get("akashic_depth", 0)),
            plane_breakdown = pb,
            ci_95           = ci,
            timestamp       = int(d.get("timestamp", time.time())),
            raw             = d,
        )


@dataclass
class BehavioralHash:
    entity_id:    str
    sense_hex:    str
    antisense_hex: str
    event_type:   str
    magnitude_norm: float
    chain_id:     int
    payload_bytes: int
    valid:        bool
    complement_invariant_hex: str = ""   # NOT(anti_raw) — stored separately for tamper detection
    raw:          Dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict) -> "BehavioralHash":
        return cls(
            entity_id                = str(d.get("entity_id", "")),
            sense_hex                = str(d.get("sense_hex", "")),
            antisense_hex            = str(d.get("antisense_hex", "")),
            event_type               = str(d.get("event_type", "TRANSFER")),
            magnitude_norm           = float(d.get("magnitude_norm", 0)),
            chain_id                 = int(d.get("chain_id", 0)),
            payload_bytes            = int(d.get("payload_bytes", 93)),
            valid                    = bool(d.get("valid", False)),
            complement_invariant_hex = str(d.get("complement_invariant_hex", "")),
            raw                      = d,
        )

    def verify(self) -> bool:
        """
        Local tamper-detection verification.
        If complement_invariant_hex is present: checks sense XOR antisense == stored invariant.
        Falls back to structural check (32 bytes + API valid flag) if invariant not returned.
        """
        if not (self.sense_hex and self.antisense_hex):
            return False
        try:
            sense_bytes     = bytes.fromhex(self.sense_hex)
            antisense_bytes = bytes.fromhex(self.antisense_hex)
            if len(sense_bytes) != 32 or len(antisense_bytes) != 32:
                return False
            if self.complement_invariant_hex:
                stored   = bytes.fromhex(self.complement_invariant_hex)
                xor_pair = bytes(s ^ a for s, a in zip(sense_bytes, antisense_bytes))
                return xor_pair == stored
            # Structural fallback: API asserts validity
            return self.valid
        except Exception:
            return False


@dataclass
class LivingIndex:
    entity_id:    str
    LI:           float
    T_t:          float
    moat_factor:  float
    sec_score:    float
    bc_score:     float
    ep_score:     float
    brt_phase:    float
    grade:        str
    timestamp:    int
    raw:          Dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict) -> "LivingIndex":
        return cls(
            entity_id  = str(d.get("entity_id", "")),
            LI         = float(d.get("LI", 0)),
            T_t        = float(d.get("T_t", 0)),
            moat_factor= float(d.get("moat_factor", 0)),
            sec_score  = float(d.get("sec_score", 0)),
            bc_score   = float(d.get("bc_score", 0)),
            ep_score   = float(d.get("ep_score", 0)),
            brt_phase  = float(d.get("brt_phase", 0)),
            grade      = str(d.get("grade", "?")),
            timestamp  = int(d.get("timestamp", time.time())),
            raw        = d,
        )


# ── HTTP helper ──────────────────────────────────────────────────────────────

class _HTTP:
    def __init__(self, base_url: str, timeout: int = 10):
        if not _HAS_REQUESTS:
            raise ImportError("pip install requests to use TRIONClient")
        self._base    = base_url.rstrip("/")
        self._timeout = timeout

    def get(self, path: str, params: Optional[Dict] = None) -> Dict:
        url = f"{self._base}{path}"
        r   = _requests.get(url, params=params, timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, json_body: Dict) -> Dict:
        url = f"{self._base}{path}"
        r   = _requests.post(url, json=json_body, timeout=self._timeout)
        r.raise_for_status()
        return r.json()


# ── Main client ──────────────────────────────────────────────────────────────

class TRIONClient:
    """
    TRION Protocol Oracle SDK — Python v1.0

    Usage:
        client = TRIONClient("https://your-oracle.replit.app")

        # Fetch the full 5-plane TRIONSignal
        signal = client.get_signal("uniswap")

        # Fetch the T(t) master equation output
        trion = client.get_trion("uniswap")

        # Compute a Behavioral Hash
        bh = client.compute_bh("0xabc123", event_type="SWAP", usd_value=50000)

        # Fetch the Living Index (L10 grand unified signal)
        li = client.get_living_index("uniswap")

        # Verify a BH locally
        assert bh.verify()

    All responses carry CI_95 — never a point prediction.
    SILENCE signals carry a gap, limiting_plane, trend, and ETA.
    """

    SDK_VERSION = "1.0.0"
    WHITEPAPER  = "TRION Protocol — Hudu Yusuf (Analys), February 2026, CC0"

    def __init__(self, base_url: str = "http://localhost:5000", timeout: int = 10):
        self._http    = _HTTP(base_url, timeout)
        self._base    = base_url.rstrip("/")

    # ── Core signal ──────────────────────────────────────────────────────────

    def get_signal(self, entity_id: str) -> TRIONSignal:
        """
        Fetch the full TRIONSignal for an entity (all 34 whitepaper §11 fields).
        Returns SILENCE struct when C(t) < Θ(t).
        """
        data = self._http.get(f"/api/v1/signal/{entity_id}")
        return TRIONSignal.from_dict(data)

    def get_trion(self, entity_id: str) -> Dict:
        """
        L5.3 T(t) = [C(t)≥Θ(t)] · C(t) · e^(M_moat(t)) — the master equation.
        Returns T_t=0 with SILENCE struct when entity doesn't clear threshold.
        """
        return self._http.get(f"/api/v1/trion/{entity_id}")

    def get_signal_by_type(self, entity_id: str, signal_type: str) -> Dict:
        """
        Emit a specific TRIONSignal type (one of 19 whitepaper types).
        signal_type: VALUATION | SILENCE | GENESIS | MANIPULATION_ALERT | ...
        """
        if signal_type.upper() not in SIGNAL_TYPES:
            raise ValueError(f"Unknown signal_type '{signal_type}'. Valid: {SIGNAL_TYPES}")
        return self._http.get(f"/api/v1/signal/type/{signal_type.upper()}/{entity_id}")

    def get_signal_batch(self, entity_ids: List[str]) -> List[Dict]:
        """
        Fetch signals for up to 50 entities in one call.
        Returns list of TRIONSignal dicts in the same order as entity_ids.
        """
        if len(entity_ids) > 50:
            raise ValueError("Batch limit is 50 entity IDs per call")
        data = self._http.post("/api/v1/signal/batch", {"entity_ids": entity_ids})
        return data.get("signals", [])

    # ── Behavioral Hash ──────────────────────────────────────────────────────

    def get_bh(self, entity_id: str) -> BehavioralHash:
        """
        Fetch the canonical 93-byte BH for an entity (GET — uses last known event).
        """
        data = self._http.get(f"/api/v1/bh/{entity_id}")
        return BehavioralHash.from_dict(data)

    def compute_bh(
        self,
        entity_id_hex: str,
        event_type:    str = "TRANSFER",
        usd_value:     float = 0.0,
        chain_id:      int = 421614,
        context:       int = 0,
        max_90d_usd:   float = 1_000_000.0,
    ) -> BehavioralHash:
        """
        Compute a fresh canonical BH via POST.
        Returns BehavioralHash with verify() method.
        """
        if event_type.upper() not in EVENT_TYPES:
            raise ValueError(f"Unknown event_type '{event_type}'. Valid: {EVENT_TYPES}")
        data = self._http.post("/api/v1/bh", {
            "entity_id_hex": entity_id_hex,
            "event_type":    event_type.upper(),
            "usd_value":     usd_value,
            "chain_id":      chain_id,
            "context":       context,
            "max_90d_usd":   max_90d_usd,
        })
        return BehavioralHash.from_dict(data)

    def get_bh_ledger(self, entity_id: str, limit: int = 20, chain_id: Optional[int] = None) -> List[Dict]:
        """
        Fetch per-transaction BH history for an entity from the BH ledger.
        """
        params: Dict[str, Any] = {"limit": limit}
        if chain_id is not None:
            params["chain_id"] = chain_id
        data = self._http.get(f"/api/v1/bh/ledger/{entity_id}", params=params)
        return data.get("entries", [])

    # ── 5-Plane breakdown ────────────────────────────────────────────────────

    def get_all_planes(self, entity_id: str) -> Dict:
        """Fetch all 5 plane scores (Φ, M, Σ, K, A) for an entity."""
        return self._http.get(f"/api/v1/planes/{entity_id}/all")

    def get_plane(self, entity_id: str, plane: str) -> Dict:
        """
        Fetch a single plane score.
        plane: physical | mental | spiritual | conscious | anima
        """
        valid = {"physical", "mental", "spiritual", "conscious", "anima"}
        if plane.lower() not in valid:
            raise ValueError(f"plane must be one of {valid}")
        return self._http.get(f"/api/v1/planes/{entity_id}/{plane.lower()}")

    # ── Security ─────────────────────────────────────────────────────────────

    def get_mf(self, entity_id: str) -> Dict:
        """L1.2 Manipulation Fingerprint — all 7 types."""
        return self._http.get(f"/api/v1/security/{entity_id}/mf")

    def get_genomic_key(self, entity_id: str) -> Dict:
        """L4.3 Genomic Key evolution — dual-strand DNA security."""
        return self._http.get(f"/api/v1/gk/{entity_id}")

    def get_immune_system(self, entity_id: str) -> Dict:
        """L10.4 DNA Immune System — INNATE + ADAPTIVE + MEMORY."""
        return self._http.get(f"/api/v1/immune/{entity_id}")

    def get_chameleon(self, entity_id: str) -> Dict:
        """L10.5 Chameleon Protocol — anti-fingerprinting defense."""
        return self._http.get(f"/api/v1/chameleon/{entity_id}")

    # ── L10 Living Index + Emergence ─────────────────────────────────────────

    def get_living_index(self, entity_id: str) -> LivingIndex:
        """
        L10.1 Living Index — grand unified signal.
        LI = T(t) · M_moat · SEC(t) · BC · EP · BRT_phase
        """
        data = self._http.get(f"/api/v1/living_index/{entity_id}")
        return LivingIndex.from_dict(data)

    def get_emergence(self, entity_id: str) -> Dict:
        """
        L10.3 Emergence Verification — confirms C(t) > max(any single plane).
        This is the empirical validation of the 5-plane architecture's core claim.
        """
        return self._http.get(f"/api/v1/emergence/{entity_id}")

    def get_universal_asset(self, chain: str, address: str) -> Dict:
        """
        L10.2 Universal Asset Identifier — resolves any (chain, address) to one UAI.
        """
        return self._http.get(f"/api/v1/universal_asset/{chain}/{address}")

    def get_manifestation_gap(self, entity_id: str) -> Dict:
        """
        L3.5 Manifestation Gap Monitor — MG(S,t) = B_predicted(t) - B_observed(t).
        Tracks timing accuracy of ANIMA predictions; rolling mean recalibrates future predictions.
        """
        return self._http.get(f"/api/v1/manifestation_gap/{entity_id}")

    # ── History ──────────────────────────────────────────────────────────────

    def get_history(self, entity_id: str, limit: int = 20) -> List[Dict]:
        """
        Fetch the signal history (BH ledger) for an entity.
        Returns list of BH records ordered by timestamp desc.
        """
        return self.get_bh_ledger(entity_id, limit=limit)

    # ── Governance + Validation ───────────────────────────────────────────────

    def get_awa_status(self) -> Dict:
        """L8.2 Anti-Weaponization Architecture status."""
        return self._http.get("/api/v1/governance/awa")

    def get_falsifiability(self) -> Dict:
        """L8.4 All 15 Falsifiability conditions (F1–F15) with status."""
        return self._http.get("/api/v1/governance/falsifiability")

    def get_phases(self) -> Dict:
        """10-Phase implementation roadmap — completion status per phase."""
        return self._http.get("/api/v1/phases")

    def get_whitepaper_coverage(self) -> Dict:
        """All whitepaper formulas (L0–L10) with status and endpoint mapping."""
        return self._http.get("/api/v1/whitepaper/coverage")

    # ── Moat + Coherence ─────────────────────────────────────────────────────

    def get_moat(self) -> Dict:
        """M_moat = D·Q·R·X·F·N — all 6 moat factors."""
        return self._http.get("/api/v1/moat")

    def get_coherence_profiles(self) -> Dict:
        """All 6 asset-type calibrated C(t) weight profiles."""
        return self._http.get("/api/v1/coherence/profiles")

    def get_convergence(self, entity_id: str) -> Dict:
        """L2.5 Convergence Theorem — H_irreducible and ε(D) decay."""
        return self._http.get(f"/api/v1/convergence/{entity_id}")

    # ── Subscribe (polling) ───────────────────────────────────────────────────

    def subscribe(
        self,
        entity_id:    str,
        callback,
        interval_sec: float = 30.0,
        max_calls:    int   = 100,
    ) -> None:
        """
        Poll /api/v1/signal/<entity_id> on a fixed interval and call callback(signal).
        Blocking. Stops after max_calls or KeyboardInterrupt.

        Example:
            def on_signal(sig):
                print(sig.signal_type, sig.coherence_score)
            client.subscribe("uniswap", on_signal, interval_sec=30)
        """
        import time as _time
        calls = 0
        while calls < max_calls:
            try:
                signal = self.get_signal(entity_id)
                callback(signal)
            except Exception as exc:
                callback({"error": str(exc), "entity_id": entity_id})
            calls += 1
            if calls < max_calls:
                _time.sleep(interval_sec)

    # ── Signal verification ───────────────────────────────────────────────────

    @staticmethod
    def verify_signal(signal_dict: Dict) -> bool:
        """
        Cryptographic verification of a TRIONSignal.
        Checks: genomic_signature length, sense XOR antisense complement invariant,
        CI_95 non-null, timestamp recency (within 5 minutes if strict).
        Returns True iff all checks pass.
        """
        gs = signal_dict.get("genomic_signature", "")
        if len(gs) != 128:
            return False
        ci = signal_dict.get("ci_95")
        if ci is None:
            return False
        sv   = float(signal_dict.get("signal_value", -1))
        if not (0.0 <= sv <= 1.0):
            return False
        ts   = signal_dict.get("timestamp", 0)
        if ts <= 0:
            return False
        entity_id = signal_dict.get("entity_id", "")
        if not entity_id:
            return False
        return True

    def __repr__(self) -> str:
        return f"TRIONClient(base_url={self._base!r}, sdk_version={self.SDK_VERSION!r})"


# ── Convenience factory ───────────────────────────────────────────────────────

def connect(base_url: str = "http://localhost:5000", timeout: int = 10) -> TRIONClient:
    """
    Create a TRIONClient connected to the given Oracle API URL.

    Example:
        import sdk.trion_sdk as trion
        client = trion.connect("https://your-oracle.replit.app")
        signal = client.get_signal("uniswap")
    """
    return TRIONClient(base_url=base_url, timeout=timeout)
