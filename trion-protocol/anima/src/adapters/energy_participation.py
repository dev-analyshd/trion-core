"""
Energy Participation Index (EP) — TRION L7
EP = VC * PA * DC
Added as f10 in Physical Layer v2 (Phase 9).
"""


def compute_ep(vc: float, pa: float, dc: float) -> dict:
    ep = vc * pa * dc
    return {
        "ep_score": round(ep, 6),
        "vc": vc, "pa": pa, "dc": dc,
        "note": "Feeds into Phi as f10 starting Phase 9",
    }
