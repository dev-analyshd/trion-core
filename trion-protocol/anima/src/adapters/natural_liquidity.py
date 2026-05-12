"""
Natural Liquidity Score (NL) — TRION L7
NL = LD * LO * LC * LS
NL < 0.30 -> LIQUIDITY_HEALTH signal.
"""

NL_WARNING_THRESHOLD = 0.30


def compute_nl(ld: float, lo: float, lc: float, ls: float) -> dict:
    for name, val in [("LD", ld), ("LO", lo), ("LC", lc), ("LS", ls)]:
        if not 0 <= val <= 1:
            raise ValueError(f"{name} must be in [0,1], got {val}")
    nl = ld * lo * lc * ls
    return {
        "nl_score":                    round(nl, 6),
        "ld": ld, "lo": lo, "lc": lc, "ls": ls,
        "emit_liquidity_health_signal": nl < NL_WARNING_THRESHOLD,
        "warning_threshold":           NL_WARNING_THRESHOLD,
    }
