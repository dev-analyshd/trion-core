"""
TRION Protocol — L1.1: BTCP Score
Behavioral Transaction Continuity Protocol Score

BTCP_score = [0.25×NL + 0.20×normalize_gas + 0.20×finality_conf
             + 0.15×CC_coherence + 0.20×BEO_continuity] × (1 - MF_score)

normalize_gas = max(0, 1 - G_total/G_99th_percentile)
"""

from dataclasses import dataclass


@dataclass
class BTCPRouteData:
    nl_score:       float
    gas_total:      float
    gas_99th:       float
    finality_conf:  float
    cc_coherence:   float
    beo_continuity: float
    mf_score:       float


def compute_btcp_score(route: BTCPRouteData) -> dict:
    normalize_gas = max(0.0, 1.0 - route.gas_total / max(route.gas_99th, 0.01))

    components = {
        "nl":             route.nl_score       * 0.25,
        "gas":            normalize_gas         * 0.20,
        "finality":       route.finality_conf   * 0.20,
        "cc_coherence":   route.cc_coherence    * 0.15,
        "beo_continuity": route.beo_continuity  * 0.20,
    }

    raw_score  = sum(components.values())
    btcp_score = raw_score * (1.0 - route.mf_score)
    btcp_score = max(0.0, min(1.0, btcp_score))

    is_safe = btcp_score >= 0.50 and route.nl_score >= 0.30

    return {
        "btcp_score":    btcp_score,
        "raw_score":     raw_score,
        "mf_discount":   1.0 - route.mf_score,
        "components":    components,
        "is_safe":       is_safe,
        "nl_healthy":    route.nl_score >= 0.30,
        "normalize_gas": normalize_gas,
    }


def compute_bitp_match_quality(
    price_efficiency:   float,
    behavioral_trust:   float,
    fill_completeness:  float,
    time_priority:      float,
) -> float:
    """BITP Matching Score."""
    return (
        price_efficiency  * 0.40 +
        behavioral_trust  * 0.30 +
        fill_completeness * 0.20 +
        time_priority     * 0.10
    )


if __name__ == "__main__":
    healthy_route = BTCPRouteData(
        nl_score=0.75, gas_total=5.0, gas_99th=50.0,
        finality_conf=0.95, cc_coherence=0.80,
        beo_continuity=0.90, mf_score=0.0,
    )
    stressed_route = BTCPRouteData(
        nl_score=0.15, gas_total=45.0, gas_99th=50.0,
        finality_conf=0.60, cc_coherence=0.40,
        beo_continuity=0.50, mf_score=0.30,
    )
    r1 = compute_btcp_score(healthy_route)
    r2 = compute_btcp_score(stressed_route)

    print(f"Healthy route BTCP:  {r1['btcp_score']:.4f} safe={r1['is_safe']}")
    print(f"Stressed route BTCP: {r2['btcp_score']:.4f} safe={r2['is_safe']}")

    assert r1['btcp_score'] > r2['btcp_score'], "Healthy should score higher"
    assert r1['is_safe'],  "Healthy route should be safe"
    assert not r2['is_safe'], "Stressed route should not be safe"
    print("PHASE 21 PASS — BTCP Score engine implemented")
