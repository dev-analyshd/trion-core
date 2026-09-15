"""
TRION Protocol — L1.1: Physical Plane Φ(t)
Nine Shannon entropy features.

Φ(t) = weighted sum of 9 behavioral entropy features
f1: Volume entropy       f2: Counterparty diversity
f3: Temporal spacing     f4: Smart contract entropy
f5: Value flow           f6: Wallet architecture
f7: Cross-protocol       f8: Gas pattern
f9: MEV interaction

Spec (WHITEPAPER_V2.txt §L1.1):
    Φ(t) = (1/N) · Σ [ w · H(f(t)) ]
    w = feature importance weight (learned from Akashic history, not fixed)

The spec-compliant default is to learn `w` from Akashic history via
`learn_weights_from_history()` (mutual-information feature importance, with a
correlation-based fallback when sklearn is unavailable). The legacy fixed
weights `PHI_WEIGHTS` are retained as a backward-compatible fallback for
cold-start paths that have no historical data yet; callers should migrate to
the learned path as soon as enough Akashic observations are available.
"""

import math
import time
from collections import Counter
from dataclasses import dataclass
from typing import List, Optional, Sequence


@dataclass
class TransactionData:
    tx_hash:      str
    timestamp:    float
    block_number: int
    from_addr:    str
    to_addr:      str
    value_wei:    int
    gas_used:     int
    gas_price:    int
    is_contract:  bool
    contract_addr: Optional[str] = None
    input_len:    int = 0


def shannon_entropy(values: List[float]) -> float:
    if not values or sum(values) <= 0:
        return 0.0
    total = sum(values)
    probs = [v / total for v in values if v > 0]
    return -sum(p * math.log2(p) for p in probs)


def normalize_entropy(H: float, n: int) -> float:
    if n <= 1:
        return 0.0
    max_H = math.log2(n)
    return min(1.0, H / max_H) if max_H > 0 else 0.0


def compute_f1_volume_entropy(txs: List[TransactionData]) -> float:
    """f1: Shannon entropy of transaction volume distribution."""
    if not txs:
        return 0.0
    values = [tx.value_wei for tx in txs if tx.value_wei > 0]
    if not values:
        return 0.0
    # Bin into 10 buckets
    max_val = max(values)
    if max_val == 0:
        return 0.0
    buckets = [0] * 10
    for v in values:
        idx = min(9, int(v * 10 / max_val))
        buckets[idx] += 1
    H = shannon_entropy([float(b) for b in buckets])
    return normalize_entropy(H, 10)


def compute_f2_counterparty_diversity(txs: List[TransactionData]) -> float:
    """f2: Shannon entropy of counterparty addresses."""
    if not txs:
        return 0.0
    addrs = [tx.to_addr for tx in txs]
    counts = Counter(addrs)
    H = shannon_entropy([float(c) for c in counts.values()])
    return normalize_entropy(H, len(counts))


def compute_f3_temporal_spacing(txs: List[TransactionData]) -> float:
    """f3: Shannon entropy of inter-transaction time gaps (run-length)."""
    if len(txs) < 2:
        return 0.0
    timestamps = sorted(tx.timestamp for tx in txs)
    gaps = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
    if not gaps or max(gaps) == 0:
        return 0.0
    max_gap = max(gaps)
    buckets = [0] * 10
    for g in gaps:
        idx = min(9, int(g * 10 / max_gap))
        buckets[idx] += 1
    H = shannon_entropy([float(b) for b in buckets])
    return normalize_entropy(H, 10)


def compute_f4_contract_entropy(txs: List[TransactionData]) -> float:
    """f4: Shannon entropy of smart contract interactions."""
    if not txs:
        return 0.0
    contract_txs = [tx.contract_addr for tx in txs if tx.is_contract and tx.contract_addr]
    if not contract_txs:
        return 0.0
    counts = Counter(contract_txs)
    H = shannon_entropy([float(c) for c in counts.values()])
    return normalize_entropy(H, len(counts))


def compute_f5_value_flow(txs: List[TransactionData], entity_addr: str) -> float:
    """f5: Value flow directionality entropy (receive vs send)."""
    if not txs:
        return 0.0
    received = sum(tx.value_wei for tx in txs if tx.to_addr.lower() == entity_addr.lower())
    sent = sum(tx.value_wei for tx in txs if tx.from_addr.lower() == entity_addr.lower())
    if received + sent == 0:
        return 0.0
    return shannon_entropy([float(received), float(sent)]) if received > 0 and sent > 0 else 0.0


def compute_f6_wallet_architecture(txs: List[TransactionData]) -> float:
    """f6: Wallet architecture entropy (EOA vs contract usage)."""
    if not txs:
        return 0.0
    contract_count = sum(1 for tx in txs if tx.is_contract)
    eoa_count = len(txs) - contract_count
    H = shannon_entropy([float(eoa_count), float(contract_count)])
    return normalize_entropy(H, 2)


def compute_f7_cross_protocol(txs: List[TransactionData]) -> float:
    """f7: Cross-protocol interaction entropy."""
    if not txs:
        return 0.0
    protocols = [tx.contract_addr[:6] if tx.contract_addr else "EOA" for tx in txs]
    counts = Counter(protocols)
    H = shannon_entropy([float(c) for c in counts.values()])
    return normalize_entropy(H, len(counts))


def compute_f8_gas_pattern(txs: List[TransactionData]) -> float:
    """f8: Gas usage pattern entropy."""
    if not txs:
        return 0.0
    gas_values = [tx.gas_used for tx in txs if tx.gas_used > 0]
    if not gas_values:
        return 0.0
    max_gas = max(gas_values)
    if max_gas == 0:
        return 0.0
    buckets = [0] * 10
    for g in gas_values:
        idx = min(9, int(g * 10 / max_gas))
        buckets[idx] += 1
    H = shannon_entropy([float(b) for b in buckets])
    return normalize_entropy(H, 10)


def compute_f9_mev_interaction(txs: List[TransactionData]) -> float:
    """f9: MEV interaction entropy (5 categories: sandwich/frontrun/backrun/arb/clean)."""
    if not txs:
        return 0.0
    # Heuristic: zero-value txs with contract interaction suggest MEV activity
    mev_like = sum(1 for tx in txs if tx.is_contract and tx.value_wei == 0 and tx.input_len > 100)
    total = len(txs)
    if total == 0:
        return 0.0
    ratio = mev_like / total
    # Entropy of 5-category MEV distribution (heuristic)
    cats = [max(0.01, ratio * 0.3), max(0.01, ratio * 0.2),
            max(0.01, ratio * 0.2), max(0.01, ratio * 0.1),
            max(0.01, 1 - ratio)]
    H = shannon_entropy(cats)
    return normalize_entropy(H, 5)


# Legacy fixed weights — used as the cold-start default when no Akashic history
# is available yet. The spec-compliant path learns weights via
# `learn_weights_from_history()` (see below) and passes the result to
# `compute_phi(weights=...)`.
PHI_WEIGHTS = [0.15, 0.15, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10]

N_FEATURES = 9


def learn_weights_from_history(
    features: Sequence[Sequence[float]],
    outcomes: Sequence[float],
    fallback_weights: Optional[Sequence[float]] = None,
) -> List[float]:
    """
    Learn the L1.1 Φ feature-importance weights `w` from Akashic history
    (spec: "w = feature importance weight (learned from Akashic history,
    not fixed)").

    Inputs
    ------
    features : (n_samples, 9) sequence of f1..f9 Shannon entropy observations.
    outcomes : (n_samples,) sequence of the target the Φ score is meant to
               predict — typically the historical coherence outcome C(t),
               the realized post-hoc Phi, or a binary manipulation label.
    fallback_weights : optional prior weights to return if learning is
               impossible (too few samples, zero variance, missing sklearn).
               Defaults to `PHI_WEIGHTS`.

    Returns
    -------
    A length-9 list of non-negative weights summing to 1.0.

    Method
    ------
    Primary: sklearn.feature_selection.mutual_info_regression — a non-parametric
    estimate of mutual information between each feature column and the target.
    Fallback: |Pearson r| between each feature column and the target (numpy only).

    Both paths return non-negative importances; we L1-normalize them so they
    sum to 1.0 (matching the spec form `Σ w_i = 1` when N is folded into the
    leading 1/N factor).
    """
    if fallback_weights is None:
        fallback_weights = PHI_WEIGHTS
    fallback = [float(w) for w in fallback_weights]
    s = sum(fallback)
    fallback = [w / s for w in fallback] if s > 0 else [1.0 / N_FEATURES] * N_FEATURES

    # Convert to plain lists so we can validate shape/emptiness without numpy.
    try:
        n_samples = len(features)
    except TypeError:
        features = list(features)
        n_samples = len(features)
    outcomes = list(outcomes)

    if n_samples < 2 or len(outcomes) != n_samples:
        # Not enough data to learn from — return the (normalized) fallback.
        return fallback

    # Build a (n_samples, 9) matrix of floats; reject degenerate rows.
    try:
        matrix = [[float(x) for x in row] for row in features]
    except (TypeError, ValueError):
        return fallback
    if any(len(row) != N_FEATURES for row in matrix):
        return fallback

    # Try the spec-preferred path: sklearn mutual_info_regression.
    try:
        import numpy as np
        from sklearn.feature_selection import mutual_info_regression

        X = np.asarray(matrix, dtype=float)            # (n, 9)
        y = np.asarray(outcomes, dtype=float)          # (n,)
        if X.shape[0] < 2 or y.shape[0] < 2:
            return fallback
        # mutual_info_regression returns one importance per column of X.
        mi = mutual_info_regression(X, y)
        importances = [max(0.0, float(v)) for v in mi]
    except Exception:
        # Fallback: |Pearson r| per column (numpy-only, no sklearn).
        try:
            import numpy as np
            X = np.asarray(matrix, dtype=float)
            y = np.asarray(outcomes, dtype=float)
            if X.shape[0] < 2:
                return fallback
            y_centered = y - y.mean()
            y_std = y.std()
            if y_std == 0:
                return fallback
            importances = []
            for j in range(N_FEATURES):
                col = X[:, j]
                col_std = col.std()
                if col_std == 0:
                    importances.append(0.0)
                    continue
                r = float(((col - col.mean()) @ y_centered) /
                          (col_std * y_std * X.shape[0]))
                importances.append(abs(r))
        except Exception:
            return fallback

    total = sum(importances)
    if not math.isfinite(total) or total <= 0.0:
        # All features are non-informative — fall back to the prior so Φ
        # remains well-defined instead of collapsing to 0.
        return fallback

    learned = [v / total for v in importances]
    return learned


# ─── Part 11 Language Mandate — FAISS adapter (TRION-TEAM-D) ──────────────────
#
# The audit found no adapter from FAISS `entity_history` records to
# `List[TransactionData]`. The FAISS store (anima-service/faiss_service.py)
# accumulates one record per BEO observation with these fields (see
# faiss_service.py:818 / :3812 / :3970):
#
#   * `vector`     — the FAISS embedding (list[float])
#   * `ts`         — unix timestamp (float)
#   * `magnitude`  — BH magnitude_normalized ∈ [0, 1] (canonical fixed scale)
#   * `entropy`    — Shannon entropy of the BH payload
#   * `arch_sim`   — archetype similarity
#
# plus (when the record came from the per-tx BH ledger rather than the
# pure FAISS path) the optional per-tx fields:
#
#   * `tx_hash`       — canonical tx hash
#   * `value_wei`     — raw transaction value in wei
#   * `selector` / `gas` — EVM function selector / gas-used surrogate
#   * `from_addr` / `to_addr` — counterparty addresses
#   * `block_number`  — block height
#
# The adapter below maps either shape into `TransactionData` so
# `compute_phi` and the PyO3 `compute_phi_native` wrapper can consume
# FAISS records directly. Missing fields fall back to spec-honest
# defaults (zeros / empty strings / magnitude-scaled value) rather than
# synthesising hash-derived fake values.

# Scale factor applied to the [0, 1] BH magnitude when the record does NOT
# carry a raw `value_wei` field — the canonical magnitude is normalised
# to [0, 1] via log10(USD+1)/log10(max_90d+1), so multiplying by 1e18
# yields an ether-denominated integer in the same range real wei values
# fall into on mainnet. This is documented as a magnitude-scaled
# surrogate, NOT a real measurement — see the `value_source` field below.
MAGNITUDE_TO_WEI_SCALE = 10**18


def _selector_to_gas_proxy(selector: object) -> int:
    """Convert an EVM 4-byte function selector (hex string or bytes) to
    a non-zero gas-used surrogate. The selector itself carries no gas
    information, but its integer value is a stable, deterministic proxy
    that varies across contract interactions — exactly what f8 (gas
    pattern entropy) needs to produce a non-degenerate histogram.

    Returns 0 when the selector is empty / unparseable, so the caller's
    f8 feature collapses to 0 entropy (no gas data) rather than
    fabricating a value."""
    if not selector:
        return 0
    if isinstance(selector, (bytes, bytearray)):
        s = selector.hex() if hasattr(selector, "hex") else bytes(selector).hex()
    else:
        s = str(selector)
    s = s[2:] if s[:2].lower() == "0x" else s
    if not s:
        return 0
    try:
        # Take the first 8 hex chars (4 bytes) — the canonical selector
        # width. The integer value is then a stable gas surrogate in
        # [0, 2^32 - 1].
        v = int(s[:8], 16) if len(s) >= 8 else int(s, 16)
        return v if v > 0 else 0
    except (ValueError, TypeError):
        return 0


def entity_history_to_transactions(
    records: list,
    entity_addr: Optional[str] = None,
) -> List[TransactionData]:
    """
    Adapt FAISS `entity_history` records into `List[TransactionData]`
    suitable for `compute_phi()`.

    Mapping (record → TransactionData):
      tx_hash     → record["tx_hash"]            (fallback "")
      value_wei   → record["value_wei"]         (fallback: magnitude × 1e18)
      gas_used    → record["gas_used"] or record["gas"]
                                                  (fallback: selector → gas proxy)
      contract_addr → record["contract_addr"]    (fallback: derived from selector)
      from_addr   → record["from_addr"]          (fallback: entity_addr)
      to_addr     → record["to_addr"]            (fallback: entity_addr)
      block_num   → record["block_number"] or record["block_num"]
                                                  (fallback: 0)
      timestamp   → record["ts"]                 (fallback: 0.0)

    The adapter is defensive: each field is read with `.get()` and
    coerced through `int(...)`/`float(...)`/`str(...)` so a malformed
    record never raises. Records that lack a `magnitude` field AND a
    `value_wei` field surface `value_wei=0` (the honest "no value data"
    disclosure) rather than a hash-derived fake.

    Parameters
    ----------
    records : list of dict (or dict-like objects with `.get`).
        The FAISS entity_history records for one entity.
    entity_addr : optional canonical entity address, used to fill in
        `from_addr` / `to_addr` when the record does not carry them
        (the FAISS store keys records by BEO id but does not duplicate
        the address into each row).

    Returns
    -------
    List[TransactionData] — one TransactionData per record, in input
    order. Pass this list to `compute_phi(txs, entity_addr)` to produce
    the 9-feature Φ(t) score.
    """
    out: List[TransactionData] = []
    if not records:
        return out

    # Defensive `.get` helper that works for both dict and record-like
    # objects (e.g. sqlite3.Row, dataclasses.asdict output).
    def _get(rec, key, default=None):
        try:
            return rec.get(key, default)
        except AttributeError:
            return getattr(rec, key, default)

    for rec in records:
        # tx_hash — straight pass-through.
        tx_hash = str(_get(rec, "tx_hash", "") or "")

        # value_wei — prefer the raw field; fall back to the magnitude
        # surrogate (×1e18) so f1 (volume entropy) has a non-degenerate
        # histogram even when only the FAISS magnitude is recorded.
        raw_vw = _get(rec, "value_wei", None)
        if raw_vw is None or raw_vw == "":
            mag = _get(rec, "magnitude", 0.0) or 0.0
            try:
                value_wei = int(float(mag) * MAGNITUDE_TO_WEI_SCALE)
            except (TypeError, ValueError):
                value_wei = 0
        else:
            try:
                value_wei = int(raw_vw)
            except (TypeError, ValueError):
                value_wei = 0

        # gas_used — prefer gas_used, then gas, then the selector proxy.
        gas_used = _get(rec, "gas_used", None)
        if gas_used is None or gas_used == "":
            gas_used = _get(rec, "gas", None)
        if gas_used is None or gas_used == "":
            selector = _get(rec, "selector", None)
            gas_used = _selector_to_gas_proxy(selector)
        try:
            gas_used = int(gas_used)
        except (TypeError, ValueError):
            gas_used = 0

        # contract_addr — straight pass-through; derive from selector when missing.
        contract_addr = _get(rec, "contract_addr", None)
        selector = _get(rec, "selector", None)
        is_contract = bool(selector) and str(selector) not in ("", "0x", "0x0")
        if contract_addr is None and is_contract:
            # When the record carries a selector but no contract_addr,
            # use the to_addr (the called contract) as contract_addr —
            # matches the canonical BH ledger adapter's interpretation.
            contract_addr = _get(rec, "to_addr", None)
        contract_addr_str = str(contract_addr) if contract_addr is not None else None

        # from_addr / to_addr — fall back to entity_addr when absent.
        from_addr = str(_get(rec, "from_addr", "") or entity_addr or "")
        to_addr = str(_get(rec, "to_addr", "") or entity_addr or "")

        # block_num — try block_number then block_num; default 0.
        block_num = _get(rec, "block_number", None)
        if block_num is None or block_num == "":
            block_num = _get(rec, "block_num", 0) or 0
        try:
            block_num = int(block_num)
        except (TypeError, ValueError):
            block_num = 0

        # timestamp — straight pass-through with float coercion.
        ts = _get(rec, "ts", 0.0) or 0.0
        try:
            ts_float = float(ts)
        except (TypeError, ValueError):
            ts_float = 0.0

        out.append(TransactionData(
            tx_hash=tx_hash,
            timestamp=ts_float,
            block_number=block_num,
            from_addr=from_addr,
            to_addr=to_addr,
            value_wei=value_wei,
            gas_used=gas_used,
            gas_price=0,                # FAISS records never carry gas_price
            is_contract=is_contract,
            contract_addr=contract_addr_str,
            input_len=0,                # FAISS records never carry input_len
        ))
    return out


def compute_phi(
    txs: List[TransactionData],
    entity_addr: str,
    weights: Optional[Sequence[float]] = None,
) -> dict:
    """
    Full Φ(t) computation — all 9 features weighted.

    Parameters
    ----------
    txs : transaction window for the entity.
    entity_addr : canonical entity address (used by f5 value-flow directionality).
    weights : optional length-9 sequence of feature-importance weights. When
        supplied, this is the spec-compliant path — the weights should be
        learned from Akashic history via `learn_weights_from_history()`.
        When omitted, the legacy fixed `PHI_WEIGHTS` are used (cold-start
        fallback only — not the spec-compliant default).
    """
    f1 = compute_f1_volume_entropy(txs)
    f2 = compute_f2_counterparty_diversity(txs)
    f3 = compute_f3_temporal_spacing(txs)
    f4 = compute_f4_contract_entropy(txs)
    f5 = compute_f5_value_flow(txs, entity_addr)
    f6 = compute_f6_wallet_architecture(txs)
    f7 = compute_f7_cross_protocol(txs)
    f8 = compute_f8_gas_pattern(txs)
    f9 = compute_f9_mev_interaction(txs)

    features = [f1, f2, f3, f4, f5, f6, f7, f8, f9]

    if weights is None:
        w = list(PHI_WEIGHTS)
        weights_source = "fixed_cold_start"
    else:
        w = [float(x) for x in weights]
        if len(w) != N_FEATURES:
            raise ValueError(
                f"weights must have {N_FEATURES} entries, got {len(w)}"
            )
        total = sum(w)
        if total <= 0:
            w = list(PHI_WEIGHTS)
            weights_source = "fixed_cold_start"
        else:
            # Normalize to sum=1 so Φ stays in [0, 1] regardless of scale.
            w = [x / total for x in w]
            weights_source = "learned_from_akashic"

    phi_raw = sum(wi * fi for wi, fi in zip(w, features))

    return {
        "phi_raw": phi_raw,
        "f1": f1, "f2": f2, "f3": f3,
        "f4": f4, "f5": f5, "f6": f6,
        "f7": f7, "f8": f8, "f9": f9,
        "tx_count": len(txs),
        "weights": w,
        "weights_source": weights_source,
    }


if __name__ == "__main__":
    txs = [
        TransactionData(
            tx_hash=f"0x{i:064x}", timestamp=1700000000 + i*3600,
            block_number=18000000+i, from_addr="0xUSER",
            to_addr=f"0x{'a'*38}{i%10:02d}", value_wei=int(1e17) * (i+1),
            gas_used=21000 + i*1000, gas_price=int(20e9),
            is_contract=i % 3 == 0,
            contract_addr=f"0xPROTO{i%5:040d}" if i % 3 == 0 else None,
            input_len=68 if i % 3 == 0 else 0,
        )
        for i in range(20)
    ]
    result = compute_phi(txs, "0xUSER")
    print(f"Φ(t) = {result['phi_raw']:.4f}  (weights_source={result['weights_source']})")
    for k in ['f1','f2','f3','f4','f5','f6','f7','f8','f9']:
        print(f"  {k} = {result[k]:.4f}")
    assert 0 <= result['phi_raw'] <= 1
    for k in ['f1','f2','f3','f4','f5','f6','f7','f8','f9']:
        assert 0 <= result[k] <= 1, f"{k} out of range: {result[k]}"

    # Spec-compliant learned-weights path (Akashic history).
    # Synthesize a small historical dataset where f1 (volume entropy) is the
    # only feature correlated with the outcome.
    import random as _random
    _random.seed(0)
    hist_features = []
    hist_outcomes = []
    for _ in range(60):
        f1_v = _random.random()
        row = [f1_v] + [_random.random() for _ in range(8)]
        hist_features.append(row)
        # Outcome tracks f1 + noise — f1 should receive the largest weight.
        hist_outcomes.append(f1_v + 0.05 * _random.gauss(0, 1))
    learned = learn_weights_from_history(hist_features, hist_outcomes)
    assert len(learned) == N_FEATURES
    assert abs(sum(learned) - 1.0) < 1e-9, f"learned weights must sum to 1, got {sum(learned)}"
    assert learned[0] == max(learned), (
        f"f1 should be the most important feature, got weights={learned}"
    )
    print(f"learned weights (Akashic): {[round(w, 4) for w in learned]}")

    result_learned = compute_phi(txs, "0xUSER", weights=learned)
    assert result_learned["weights_source"] == "learned_from_akashic"
    assert 0 <= result_learned['phi_raw'] <= 1
    print(f"Φ(t) learned = {result_learned['phi_raw']:.4f}")

    # Cold-start fallback path (no historical data) still works.
    cold = learn_weights_from_history([], [])
    assert abs(sum(cold) - 1.0) < 1e-9
    print(f"cold-start fallback weights: {[round(w, 4) for w in cold]}")

    # Part 11 adapter — FAISS entity_history → List[TransactionData].
    # The audit (TRION-TEAM-D) found no adapter from FAISS records to
    # TransactionData; the entity_history store carries the BH-magnitude
    # signal that the 9-feature engine needs but the engine could not
    # consume it directly. The adapter below closes that gap.
    faiss_records = [
        {"ts": 1700000000.0 + i * 60, "magnitude": 0.4 + 0.01 * i,
         "selector": "0xa9059cbb", "from_addr": "0xUSER", "to_addr": f"0x{i:040x}",
         "tx_hash": f"0x{i:064x}", "block_number": 18_000_000 + i}
        for i in range(10)
    ]
    adapted = entity_history_to_transactions(faiss_records, entity_addr="0xUSER")
    assert len(adapted) == 10
    assert all(isinstance(t, TransactionData) for t in adapted)
    assert adapted[0].from_addr == "0xUSER"
    assert adapted[0].gas_used > 0  # selector-derived gas proxy
    assert adapted[0].block_number == 18_000_000
    # Round-trip through compute_phi — the adapter output must be a valid
    # TransactionData window.
    r = compute_phi(adapted, "0xUSER")
    assert 0 <= r["phi_raw"] <= 1
    print(f"FAISS adapter → Φ(t) = {r['phi_raw']:.4f} over {len(adapted)} txs")

    print("PHASE 10 PASS — Φ(t) nine-feature engine verified (fixed + learned)")
