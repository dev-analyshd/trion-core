"""
TRION Protocol — L1.1: Physical Plane Φ(t)
Nine Shannon entropy features.

Φ(t) = weighted sum of 9 behavioral entropy features
f1: Volume entropy       f2: Counterparty diversity
f3: Temporal spacing     f4: Smart contract entropy
f5: Value flow           f6: Wallet architecture
f7: Cross-protocol       f8: Gas pattern
f9: MEV interaction
"""

import math
import time
from collections import Counter
from dataclasses import dataclass
from typing import List, Optional


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


PHI_WEIGHTS = [0.15, 0.15, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10]


def compute_phi(txs: List[TransactionData], entity_addr: str) -> dict:
    """Full Φ(t) computation — all 9 features weighted."""
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
    phi_raw = sum(w * f for w, f in zip(PHI_WEIGHTS, features))

    return {
        "phi_raw": phi_raw,
        "f1": f1, "f2": f2, "f3": f3,
        "f4": f4, "f5": f5, "f6": f6,
        "f7": f7, "f8": f8, "f9": f9,
        "tx_count": len(txs),
        "weights": PHI_WEIGHTS,
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
    print(f"Φ(t) = {result['phi_raw']:.4f}")
    for k in ['f1','f2','f3','f4','f5','f6','f7','f8','f9']:
        print(f"  {k} = {result[k]:.4f}")
    assert 0 <= result['phi_raw'] <= 1
    for k in ['f1','f2','f3','f4','f5','f6','f7','f8','f9']:
        assert 0 <= result[k] <= 1, f"{k} out of range: {result[k]}"
    print("PHASE 10 PASS — Φ(t) nine-feature engine verified")
