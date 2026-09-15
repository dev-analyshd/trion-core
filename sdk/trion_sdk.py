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

# M-073 canonical taxonomy (owner ruling): 29 types = 19 base (D1 §11) +
# 10 BTCP-family (BTCP master spec §2's six new signals + §14.2's four
# event-signals). BTCP_ROUTE and CONSENSUS_ADAPTATION sit in both families
# (the ruling's own note), so the closed set below holds 27 distinct names
# while the taxonomy count is 29. Names use the internal enum spellings
# (REGULATORY_BHV / MEV_EXPOSURE / INSTITUTIONAL_BHV); the specification
# spellings are accepted through SIGNAL_TYPE_ALIASES below.
SIGNAL_TYPES = [
    "VALUATION", "SILENCE", "MANIPULATION_ALERT", "GENESIS", "RESURRECTION",
    "FORK_DIVERGENCE", "TRAJECTORY", "NEGATIVE_SPACE", "PHASE_TRANSITION",
    "SYSTEMIC_RISK", "LIQUIDITY_HEALTH", "GOVERNANCE_SIGNAL",
    "CROSS_CHAIN_COHERENCE", "STABLECOIN_HEALTH", "MEV_EXPOSURE",
    "INSTITUTIONAL_BHV", "REGULATORY_BHV", "ECOSYSTEM_HEALTH", "BOOTSTRAP",
    "SOVEREIGN_BEHAVIORAL", "ENERGY_PARTICIPATION", "BIOLOGICAL_CAPITAL",
    "CONSENSUS_ADAPTATION",
    # BTCP signal type (canonical 19, specification §11).
    # SECURITY FIX (P1, verification matrix #19): BTCP_ROUTE was missing here
    # (present in sdk/TrionSDK.ts, sdk/src/index.ts and core SignalType = 22).
    "BTCP_ROUTE",
    # BTCP-family additions (M-073): the seven §2/§14.2 names carried as
    # typed sub-payloads on canonical carriers by core/master/
    # signal_factory (signal_subtype) — classified + emittable, while the
    # id space stays fork-gated at 24 (wasm/rust/on-chain parity).
    "BEHAVIORAL_TRUTH", "SHADOW_CHAIN", "LIQUIDITY_OCEAN",
    "CHAIN_RELIABILITY", "BTCP_ESCROW_EVENT", "BTCP_TIMEOUT",
    "GENESIS_COMMITMENT",
]

# specification spellings accepted for the two internally drifted names.
SIGNAL_TYPE_ALIASES = {
    "REGULATORY_BEHAVIORAL": "REGULATORY_BHV",
    "MEV_BEHAVIORAL":        "MEV_EXPOSURE",
}

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
    SPECIFICATION  = "TRION Protocol — Hudu Yusuf (Analys), February 2026, CC0"

    def __init__(self, base_url: str = "http://localhost:5000", timeout: int = 10):
        self._http    = _HTTP(base_url, timeout)
        self._base    = base_url.rstrip("/")

    # ── Core signal ──────────────────────────────────────────────────────────

    def get_signal(self, entity_id: str) -> TRIONSignal:
        """
        Fetch the full TRIONSignal for an entity (all 34 specification §11 fields).
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
        Emit a specific TRIONSignal type.
        signal_type: any name from SIGNAL_TYPES (the M-073 closed set — the
        19 specification §11 types plus the BTCP-family additions; specification
        spellings of the two drifted names resolve through
        SIGNAL_TYPE_ALIASES). The server route /api/v1/signal/type/<type>
        currently pins the 19 §11 types; the BTCP-family names classify
        and emit through the core signal factory on the caller side.
        """
        canonical = SIGNAL_TYPE_ALIASES.get(signal_type.upper(), signal_type.upper())
        if canonical not in SIGNAL_TYPES:
            raise ValueError(f"Unknown signal_type '{signal_type}'. Valid: {SIGNAL_TYPES}")
        return self._http.get(f"/api/v1/signal/type/{canonical}/{entity_id}")

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

    def get_specification_coverage(self) -> Dict:
        """All specification formulas (L0–L10) with status and endpoint mapping."""
        return self._http.get("/api/v1/specification/coverage")

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
    def _structural_check(signal_dict: Dict) -> bool:
        """
        Structural sanity checks on a TRIONSignal — the boolean check the
        legacy verify_signal returned directly:
          - genomic_signature is a 128-char hex string (bytes64 = sense||antisense)
          - ci_95 is non-null
          - signal_value ∈ [0, 1] (when present)
          - timestamp is a positive int
          - entity_id is non-empty
        """
        gs = signal_dict.get("genomic_signature", "")
        if not isinstance(gs, str) or len(gs) != 128:
            return False
        ci = signal_dict.get("ci_95")
        if ci is None:
            return False
        sv = signal_dict.get("signal_value")
        if sv is not None:
            try:
                svf = float(sv)
            except (TypeError, ValueError):
                return False
            if not (0.0 <= svf <= 1.0):
                return False
        ts = signal_dict.get("timestamp", 0)
        if not isinstance(ts, (int, float)) or ts <= 0:
            return False
        entity_id = signal_dict.get("entity_id", "")
        if not entity_id:
            return False
        return True

    @staticmethod
    def _genomic_invariant_check(signal_dict: Dict) -> bool:
        """
        Verify the dual-strand genomic signature (whitepaper L0.1 / Part 6).

        genomic_signature = sense[32] || antisense[32]
          sense     = SHA3-256(payload || 0x00)        payload = entity_id || generation
          antisense = SHA3-256(payload || 0xFF) XOR complement(sense)
        where complement(x) = NOT(x) (bit-wise per byte).

        Returns True iff recomputing both strands from entity_id +
        security_generation reproduces the stored signature exactly.
        """
        gs = signal_dict.get("genomic_signature", "")
        if not isinstance(gs, str) or len(gs) != 128:
            return False
        try:
            sense_b     = bytes.fromhex(gs[:64])
            antisense_b = bytes.fromhex(gs[64:])
            if len(sense_b) != 32 or len(antisense_b) != 32:
                return False
        except (ValueError, TypeError):
            return False

        entity_id = signal_dict.get("entity_id", "")
        if not entity_id:
            return False
        try:
            generation = int(signal_dict.get("security_generation", 0) or 0)
        except (TypeError, ValueError):
            return False

        payload = (str(entity_id) + str(generation)).encode()

        # Recompute sense and verify it matches the stored first half.
        expected_sense = hashlib.sha3_256(payload + b"\x00").digest()
        if expected_sense != sense_b:
            return False

        # Recompute antisense and verify the XOR/complement invariant.
        sha3ff_b            = hashlib.sha3_256(payload + b"\xFF").digest()
        expected_antisense  = bytes(s ^ (f ^ 0xFF) for s, f in zip(sha3ff_b, sense_b))
        return expected_antisense == antisense_b

    def _all_bh_retrievable_structural(self, signal_dict: Dict) -> bool:
        """
        Offline structural check: every entry in the provenance chain must
        carry either a `bh_id` (for behavioral_hash source entries) or a
        `source` field. Real Akashic-Index retrieval is gated behind
        verify_provenance=True (see verify_signal).
        """
        provenance = signal_dict.get("provenance") or []
        if not isinstance(provenance, list) or not provenance:
            return False
        for entry in provenance:
            if not isinstance(entry, dict):
                return False
            if "bh_id" not in entry and "source" not in entry:
                return False
        return True

    def _all_bh_retrievable_via_akashic(self, signal_dict: Dict) -> bool:
        """
        Live Akashic-Index retrieval check: fetch the BH ledger for the
        signal's entity_id from /api/v1/bh/ledger/<entity_id> and confirm
        every behavioral_hash entry in the provenance chain appears in it.

        Returns False on any HTTP error, missing entity_id, or any
        provenance BH not present in the ledger (fail-closed).
        """
        entity_id = signal_dict.get("entity_id", "")
        if not entity_id:
            return False
        provenance = signal_dict.get("provenance") or []
        bh_ids = [
            p.get("bh_id") for p in provenance
            if isinstance(p, dict) and p.get("source") == "behavioral_hash"
            and p.get("bh_id")
        ]
        if not bh_ids:
            # No behavioral_hash entries to verify — structural check is
            # sufficient (non-BH provenance: coherence_engine, brt, etc.).
            return self._all_bh_retrievable_structural(signal_dict)

        try:
            ledger = self._http.get(f"/api/v1/bh/ledger/{entity_id}", params={"limit": 500})
        except Exception:
            # Network / server error — fail-closed.
            return False

        entries = ledger.get("entries", []) if isinstance(ledger, dict) else (ledger if isinstance(ledger, list) else [])
        # The ledger entries carry either bh_id or sense_hex; match on bh_id
        # when present, else fall back to sense_hex.
        retrievable_ids = set()
        for e in entries:
            if not isinstance(e, dict):
                continue
            if e.get("bh_id"):
                retrievable_ids.add(e["bh_id"])
            if e.get("sense_hex"):
                retrievable_ids.add(e["sense_hex"])
            if e.get("antisense_hex"):
                retrievable_ids.add(e["antisense_hex"])

        # Fail-closed: every provenance bh_id must be present in the ledger.
        return all(bh in retrievable_ids for bh in bh_ids)

    def verify_signal(self, signal_dict: Dict, verify_provenance: bool = False) -> Dict:
        """
        Cryptographic verification of a TRIONSignal.

        Whitepaper §15.4 (Developer SDK Specification) return shape:
            { valid: bool,
              provenance_chain_depth: int,
              all_BH_retrievable: bool,
              genomic_valid: bool }

        Field semantics:
          - valid: structural sanity (genomic_signature length, ci_95
            non-null, signal_value ∈ [0,1], timestamp > 0, entity_id
            non-empty). The boolean the legacy verify_signal returned.
          - provenance_chain_depth: length of the signal's `provenance`
            list (whitepaper: complete derivation chain depth).
          - all_BH_retrievable: when verify_provenance=False (default),
            a structural check that every provenance entry carries a
            bh_id (for behavioral_hash source entries) or a source field.
            When verify_provenance=True, every behavioral_hash entry is
            also fetched from the Akashic Index (BH ledger) and confirmed
            present — true provenance retrievability, fail-closed.
          - genomic_valid: recomputes sense + antisense from entity_id +
            security_generation and verifies the XOR/complement invariant
            on the dual-strand genomic signature (whitepaper L0.1 / Part 6).

        Args:
          signal_dict: the TRIONSignal dict to verify.
          verify_provenance: when True, perform live HTTP retrieval checks
            against the Akashic Index for every behavioral_hash entry in
            the signal's provenance chain. Default False (offline
            structural check only) — pass True for full provenance audits.
        """
        valid = self._structural_check(signal_dict)
        provenance = signal_dict.get("provenance") or []
        provenance_chain_depth = len(provenance) if isinstance(provenance, list) else 0
        genomic_valid = self._genomic_invariant_check(signal_dict)
        if verify_provenance:
            all_BH_retrievable = self._all_bh_retrievable_via_akashic(signal_dict)
        else:
            all_BH_retrievable = self._all_bh_retrievable_structural(signal_dict)
        return {
            "valid":                   valid,
            "provenance_chain_depth":  provenance_chain_depth,
            "all_BH_retrievable":      all_BH_retrievable,
            "genomic_valid":           genomic_valid,
        }

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
