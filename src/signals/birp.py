"""
TRION Protocol — Section 19: BIRP — Behavioral Intercept & Relay Protocol
BIRP is the delivery layer between TRION Oracle and consumer contracts.

Signal lifecycle:
  Oracle computes C(t) → BIRP packages → Smart contract verifies → Executes

BIRP message format:
  birp_msg = {
    signal_id, entity_id, signal_value, ci_95,
    coherence, threshold, margin,
    mf_score, oracle_sig, timestamp, ttl,
    plane_breakdown, biological_time,
    chameleon_applied, silence_metadata
  }

Batch support: up to 50 signals per batch.
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict


BIRP_BATCH_MAX     = 50
BIRP_DEFAULT_TTL   = 3600


@dataclass
class BIRPMessage:
    signal_id:         str
    entity_id:         str
    signal_type:       str
    signal_value:      Optional[float]
    ci_95:             List[float]
    coherence:         float
    threshold:         float
    margin:            float
    mf_score:          float
    timestamp:         int
    ttl:               int
    plane_breakdown:   dict
    biological_time:   dict
    chameleon_applied: bool     = True
    silence:           bool     = False
    oracle_sig:        str      = ""
    bootstrap_phase:   bool     = True
    extra:             dict     = field(default_factory=dict)


def sign_birp_message(msg: BIRPMessage, signing_key: bytes) -> str:
    payload = "|".join([
        msg.signal_id, msg.entity_id, msg.signal_type,
        str(msg.signal_value), str(msg.coherence),
        str(msg.threshold), str(msg.timestamp),
    ])
    mac = hmac.new(signing_key, payload.encode(), hashlib.sha3_256)
    return mac.hexdigest()


def verify_birp_message(msg: BIRPMessage, signing_key: bytes) -> bool:
    expected = sign_birp_message(msg, signing_key)
    return hmac.compare_digest(expected, msg.oracle_sig)


def build_birp_message(
    signal:         dict,
    signing_key:    bytes,
    chameleon_data: Optional[dict] = None,
) -> BIRPMessage:
    msg = BIRPMessage(
        signal_id         = signal.get("signal_id", ""),
        entity_id         = signal.get("entity_id", ""),
        signal_type       = signal.get("signal_type", "UNKNOWN"),
        signal_value      = signal.get("signal_value"),
        ci_95             = signal.get("ci_95", [0.0, 1.0]),
        coherence         = signal.get("coherence", 0.0),
        threshold         = signal.get("threshold", 0.0),
        margin            = signal.get("margin", 0.0),
        mf_score          = signal.get("mf_score", 0.0),
        timestamp         = signal.get("timestamp", int(time.time())),
        ttl               = BIRP_DEFAULT_TTL,
        plane_breakdown   = signal.get("plane_breakdown", {}),
        biological_time   = signal.get("biological_time", {}),
        chameleon_applied = chameleon_data is not None,
        silence           = signal.get("silence", False),
        bootstrap_phase   = signal.get("bootstrap_phase", True),
    )
    msg.oracle_sig = sign_birp_message(msg, signing_key)
    return msg


def batch_birp_messages(
    signals:     List[dict],
    signing_key: bytes,
) -> List[BIRPMessage]:
    if len(signals) > BIRP_BATCH_MAX:
        raise ValueError(f"Batch size {len(signals)} exceeds maximum {BIRP_BATCH_MAX}")
    return [build_birp_message(s, signing_key) for s in signals]


def birp_to_dict(msg: BIRPMessage) -> dict:
    return {
        "signal_id":         msg.signal_id,
        "entity_id":         msg.entity_id,
        "signal_type":       msg.signal_type,
        "signal_value":      msg.signal_value,
        "ci_95":             msg.ci_95,
        "coherence":         msg.coherence,
        "threshold":         msg.threshold,
        "margin":            msg.margin,
        "mf_score":          msg.mf_score,
        "timestamp":         msg.timestamp,
        "ttl":               msg.ttl,
        "plane_breakdown":   msg.plane_breakdown,
        "biological_time":   msg.biological_time,
        "chameleon_applied": msg.chameleon_applied,
        "silence":           msg.silence,
        "oracle_sig":        msg.oracle_sig,
        "bootstrap_phase":   msg.bootstrap_phase,
    }


if __name__ == "__main__":
    import os
    key = os.urandom(32)

    sample_signal = {
        "signal_id": "test-sig-001", "entity_id": "0xAABBCC",
        "signal_type": "VALUATION", "signal_value": 0.72,
        "ci_95": [0.65, 0.79], "coherence": 0.72, "threshold": 0.62,
        "margin": 0.10, "mf_score": 0.0, "timestamp": int(time.time()),
        "plane_breakdown": {}, "biological_time": {"circadian_phase": 0.5},
        "silence": False, "bootstrap_phase": True,
    }

    msg    = build_birp_message(sample_signal, key)
    valid  = verify_birp_message(msg, key)
    tamper = BIRPMessage(**vars(msg))
    tamper.coherence = 0.99
    invalid = verify_birp_message(tamper, key)

    assert valid,    "Valid message should pass"
    assert not invalid, "Tampered message should fail"

    signals = [dict(sample_signal, signal_id=f"sig-{i}") for i in range(10)]
    batch   = batch_birp_messages(signals, key)
    assert len(batch) == 10
    assert all(verify_birp_message(m, key) for m in batch)

    print(f"BIRP sign/verify:    PASS")
    print(f"Tamper detection:    PASS")
    print(f"Batch (10 msgs):     PASS")
    print("PHASE 19 PASS — BIRP Behavioral Intercept & Relay Protocol implemented")
