"""
TRION Protocol Python SDK v1.0
Client for the TRION Oracle API.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


# ── Typed dataclasses ────────────────────────────────────────────────────────

@dataclass
class PlaneBreakdown:
    phi_adj: float
    m_adj:   float
    sigma:   float
    k_score: float
    a_score: float


@dataclass
class ConfidenceInterval:
    lo: float
    hi: float

    @classmethod
    def from_tuple(cls, t: Tuple[float, float]) -> "ConfidenceInterval":
        return cls(lo=t[0], hi=t[1])

    def width(self) -> float:
        return self.hi - self.lo

    def contains(self, value: float) -> bool:
        return self.lo <= value <= self.hi


@dataclass
class BehavioralHash:
    entity_id:              str
    sense_hex:              str
    antisense_hex:          str
    event_type:             str
    magnitude_normalized:   float
    chain_id:               int
    block_hash:             str
    complement_invariant_hex: str = ""   # NOT(anti_raw) — stored for tamper detection

    def verify(self) -> bool:
        """
        Local tamper-evident verification.
        Checks: sense XOR antisense == complement_invariant (stored separately).
        Returns False if complement_invariant_hex is absent.
        """
        try:
            sense     = bytes.fromhex(self.sense_hex)
            antisense = bytes.fromhex(self.antisense_hex)
            if len(sense) != 32 or len(antisense) != 32:
                return False
            if not self.complement_invariant_hex:
                return False
            stored_invariant = bytes.fromhex(self.complement_invariant_hex)
            if len(stored_invariant) != 32:
                return False
            xor_result = bytes(s ^ a for s, a in zip(sense, antisense))
            return xor_result == stored_invariant
        except Exception:
            return False


@dataclass
class TRIONSignal:
    asset_id:     str
    signal_type:  str
    c_score:      Optional[float]
    phi_adj:      float
    m_adj:        float
    sigma:        float
    k_score:      float
    a_score:      float
    ci_95:        Optional[ConfidenceInterval]
    conf_genesis: float
    tc_valid:     bool
    theta:        float
    asset_type:   str

    def is_silence(self) -> bool:
        return self.signal_type == "SILENCE"

    def validate(self) -> List[str]:
        errors: List[str] = []
        if self.ci_95 is None:
            errors.append("CI_95 must never be null")
        elif self.ci_95.lo >= self.ci_95.hi:
            errors.append(f"CI_95 not ordered: [{self.ci_95.lo}, {self.ci_95.hi}]")
        if self.conf_genesis is None:
            errors.append("conf_genesis must never be null")
        if self.c_score is not None and not (0.0 <= self.c_score <= 1.0):
            errors.append(f"c_score out of [0,1]: {self.c_score}")
        return errors


@dataclass
class LivingIndex:
    asset_id:  str
    li_score:  float
    grade:     str
    sec_t:     float
    phi_adj:   float
    m_adj:     float
    sigma:     float
    k_score:   float
    a_score:   float
    conf_genesis: float


# ── Transport ────────────────────────────────────────────────────────────────

def _get(url: str, timeout: int = 10) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {url}") from e
    except Exception as e:
        raise RuntimeError(f"Request failed: {e}") from e


def _post(url: str, payload: dict, timeout: int = 10) -> dict:
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {url}") from e
    except Exception as e:
        raise RuntimeError(f"Request failed: {e}") from e


# ── Client ───────────────────────────────────────────────────────────────────

class TRIONClient:
    """
    TRION Protocol Python SDK — v1.0
    Typed, zero-dependency client for the TRION Oracle API.
    """

    def __init__(self, base_url: str, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout  = timeout

    # ── Signal queries ───────────────────────────────────────────────────────

    def get_signal(self, entity_id: str) -> TRIONSignal:
        """Fetch the current TRION signal for an entity."""
        raw = _get(f"{self.base_url}/api/v1/signal/{entity_id}", self.timeout)
        ci  = None
        if raw.get("ci_95"):
            ci_raw = raw["ci_95"]
            if isinstance(ci_raw, (list, tuple)) and len(ci_raw) == 2:
                ci = ConfidenceInterval(lo=ci_raw[0], hi=ci_raw[1])
        return TRIONSignal(
            asset_id=entity_id,
            signal_type=raw.get("signal_type", "SILENCE"),
            c_score=raw.get("c_score"),
            phi_adj=raw.get("phi_adj", 0.0),
            m_adj=raw.get("m_adj", 0.0),
            sigma=raw.get("sigma", 0.0),
            k_score=raw.get("k_score", 0.0),
            a_score=raw.get("a_score", 0.0),
            ci_95=ci,
            conf_genesis=raw.get("conf_genesis", 0.0),
            tc_valid=raw.get("tc_valid", False),
            theta=raw.get("theta", 0.55),
            asset_type=raw.get("asset_type", "MATURE_PROTOCOL"),
        )

    def get_trion(self, entity_id: str) -> dict:
        """Raw TRION signal dict (all fields)."""
        return _get(f"{self.base_url}/api/v1/trion/{entity_id}", self.timeout)

    def get_signal_batch(self, entity_ids: List[str]) -> List[dict]:
        """Batch signal lookup — 1 to 50 entities."""
        return _post(
            f"{self.base_url}/api/v1/signal/batch",
            {"entity_ids": entity_ids},
            self.timeout,
        )

    # ── Behavioral Hash ──────────────────────────────────────────────────────

    def compute_bh(
        self,
        entity_id: str,
        event_type: str,
        usd_value: float,
        max_observed_90d: float,
        chain_id: int,
        context: str = "",
        block_hash: str = "0x0",
    ) -> BehavioralHash:
        payload = {
            "entity_id_hex":    hashlib.sha3_256(entity_id.encode()).hexdigest(),
            "event_type":       event_type,
            "usd_value":        usd_value,
            "max_observed_90d": max_observed_90d,
            "chain_id":         chain_id,
            "context":          context,
            "block_hash":       block_hash,
        }
        raw = _post(f"{self.base_url}/api/v1/bh", payload, self.timeout)
        return BehavioralHash(
            entity_id=entity_id,
            sense_hex=raw.get("sense_hex", ""),
            antisense_hex=raw.get("antisense_hex", ""),
            event_type=event_type,
            magnitude_normalized=raw.get("magnitude_normalized", 0.0),
            chain_id=chain_id,
            block_hash=block_hash,
        )

    def get_bh_ledger(self, entity_id: str, limit: int = 100) -> dict:
        """Retrieve BH ledger history for an entity."""
        return _get(
            f"{self.base_url}/api/v1/bh/ledger/{entity_id}?limit={limit}",
            self.timeout,
        )

    def get_bh_stats(self) -> dict:
        return _get(f"{self.base_url}/api/v1/bh/stats", self.timeout)

    # ── Living Index ─────────────────────────────────────────────────────────

    def get_living_index(self, entity_id: str) -> LivingIndex:
        raw = _get(f"{self.base_url}/api/v1/living_index/{entity_id}", self.timeout)
        return LivingIndex(
            asset_id=entity_id,
            li_score=raw.get("li_score", 0.0),
            grade=raw.get("grade", "BOOTSTRAP"),
            sec_t=raw.get("sec_t", 0.0),
            phi_adj=raw.get("phi_adj", 0.0),
            m_adj=raw.get("m_adj", 0.0),
            sigma=raw.get("sigma", 0.0),
            k_score=raw.get("k_score", 0.0),
            a_score=raw.get("a_score", 0.0),
            conf_genesis=raw.get("conf_genesis", 0.0),
        )

    # ── Emergence ────────────────────────────────────────────────────────────

    def get_emergence(self, entity_id: str) -> dict:
        return _get(f"{self.base_url}/api/v1/emergence/{entity_id}", self.timeout)

    # ── Security ─────────────────────────────────────────────────────────────

    def get_immune(self, entity_id: str) -> dict:
        return _get(f"{self.base_url}/api/v1/immune/{entity_id}", self.timeout)

    # ── Governance ───────────────────────────────────────────────────────────

    def get_moat(self) -> dict:
        return _get(f"{self.base_url}/api/v1/moat", self.timeout)

    def get_bootstrap_status(self) -> dict:
        return _get(f"{self.base_url}/api/v1/bootstrap/status", self.timeout)

    # ── Subscription ─────────────────────────────────────────────────────────

    def subscribe(
        self,
        entity_id: str,
        callback:  Callable[[TRIONSignal], None],
        interval_s: float = 60.0,
        max_polls:  int   = 0,
    ) -> None:
        """
        Poll-based subscription. Calls callback each interval.
        max_polls=0 means infinite.
        """
        polls = 0
        while True:
            try:
                sig = self.get_signal(entity_id)
                callback(sig)
            except Exception as exc:
                print(f"[SDK] Poll error for {entity_id}: {exc}")
            polls += 1
            if max_polls and polls >= max_polls:
                break
            time.sleep(interval_s)

    # ── Signal verification ──────────────────────────────────────────────────

    @staticmethod
    def verify_signal(signal: TRIONSignal) -> List[str]:
        """
        Static signal validation — checks structural invariants.
        Returns list of violation strings (empty = valid).
        """
        return signal.validate()


# ── Factory function ─────────────────────────────────────────────────────────

def connect(base_url: str, timeout: int = 10) -> TRIONClient:
    """Convenience factory: trion_sdk.connect('http://localhost:5000')"""
    return TRIONClient(base_url=base_url, timeout=timeout)
