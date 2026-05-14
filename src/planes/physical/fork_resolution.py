"""
TRION Protocol — L2.6 Fork Resolution Protocol
Chapter 7.2: Fork Divergence

FORK_DIVERGENCE signal — emitted when a fork event is detected.

History inheritance:
    CC_A = proportion of pre-fork holders still holding chain A
    CC_B = proportion of pre-fork holders still holding chain B

These are behavioral loyalty metrics — they measure the revealed preferences
of participants rather than relying on social consensus or political decisions.

The fork that retains more of the original community has stronger behavioral
continuity — and thus inherits more of the pre-fork behavioral history.

History inheritance weights:
    w_A = CC_A / (CC_A + CC_B)    if CC_A + CC_B > 0
    w_B = CC_B / (CC_A + CC_B)    if CC_A + CC_B > 0

Fork chain confidence:
    conf_A(t) = conf_genesis · (1 - e^(-λ_A · D_A(t)))
    conf_B(t) = conf_genesis · (1 - e^(-λ_B · D_B(t)))

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class PreForkHolder:
    """A holder from before the fork event."""
    entity_id:    str
    pre_fork_balance: float   # Token balance at fork block
    post_fork_a:  float       # Balance on chain A after fork
    post_fork_b:  float       # Balance on chain B after fork


@dataclass
class ForkProfile:
    """Complete characterization of a fork event."""
    fork_id:            str
    chain_a_id:         str   # Original chain (or majority chain)
    chain_b_id:         str   # Fork chain
    fork_block:         int
    fork_timestamp:     float
    pre_fork_holders:   list[PreForkHolder]
    description:        str   # "ETH/ETC", "BTC/BCH", etc.


@dataclass
class ForkResolutionResult:
    """
    Output of fork resolution — history inheritance weights + FORK_DIVERGENCE signal.
    """
    fork_id:                  str
    chain_a_id:               str
    chain_b_id:               str

    cc_a:                     float   # Continuity Coefficient A
    cc_b:                     float   # Continuity Coefficient B

    history_weight_a:         float   # w_A — fraction of pre-fork history chain A inherits
    history_weight_b:         float   # w_B — fraction of pre-fork history chain B inherits

    holder_count_pre_fork:    int
    holders_retained_a:       int
    holders_retained_b:       int
    holders_split:            int     # Holding both chains

    dominant_chain:           str     # Chain with higher CC
    contested:                bool    # CC_A and CC_B both > 0.40

    signal_type:              str     # Always "FORK_DIVERGENCE"
    warning:                  Optional[str]


def compute_fork_resolution(
    profile:         ForkProfile,
    balance_threshold: float = 0.10,  # Min fraction of pre-fork balance to count as "holding"
) -> ForkResolutionResult:
    """
    Compute CC_A, CC_B and history inheritance weights from holder behavior.

    CC_A = proportion of pre-fork holders still holding chain A
    CC_B = proportion of pre-fork holders still holding chain B

    A holder "still holds chain X" if post_fork_X >= balance_threshold × pre_fork_balance.
    """
    holders = profile.pre_fork_holders
    n = len(holders)

    if n == 0:
        return ForkResolutionResult(
            fork_id=profile.fork_id,
            chain_a_id=profile.chain_a_id,
            chain_b_id=profile.chain_b_id,
            cc_a=0.5, cc_b=0.5,
            history_weight_a=0.5, history_weight_b=0.5,
            holder_count_pre_fork=0,
            holders_retained_a=0, holders_retained_b=0, holders_split=0,
            dominant_chain=profile.chain_a_id,
            contested=False,
            signal_type="FORK_DIVERGENCE",
            warning="No pre-fork holder data — defaulting to equal weights",
        )

    retained_a = 0
    retained_b = 0
    split_holders = 0

    for holder in holders:
        if holder.pre_fork_balance <= 0:
            continue
        threshold = holder.pre_fork_balance * balance_threshold
        holds_a = holder.post_fork_a >= threshold
        holds_b = holder.post_fork_b >= threshold

        if holds_a:
            retained_a += 1
        if holds_b:
            retained_b += 1
        if holds_a and holds_b:
            split_holders += 1

    cc_a = retained_a / n if n > 0 else 0.5
    cc_b = retained_b / n if n > 0 else 0.5

    # History inheritance weights
    total_cc = cc_a + cc_b
    if total_cc > 0:
        weight_a = cc_a / total_cc
        weight_b = cc_b / total_cc
    else:
        weight_a = 0.5
        weight_b = 0.5

    dominant = profile.chain_a_id if cc_a >= cc_b else profile.chain_b_id
    contested = (cc_a > 0.40) and (cc_b > 0.40)

    warning = None
    if contested:
        warning = (
            f"Contested fork: CC_A={cc_a:.3f} CC_B={cc_b:.3f}. "
            "Both chains retain significant community. History inheritance disputed."
        )
    elif cc_a < 0.20 and cc_b < 0.20:
        warning = (
            f"Fork abandonment: CC_A={cc_a:.3f} CC_B={cc_b:.3f}. "
            "Community has largely abandoned both chains."
        )

    return ForkResolutionResult(
        fork_id             = profile.fork_id,
        chain_a_id          = profile.chain_a_id,
        chain_b_id          = profile.chain_b_id,
        cc_a                = cc_a,
        cc_b                = cc_b,
        history_weight_a    = weight_a,
        history_weight_b    = weight_b,
        holder_count_pre_fork = n,
        holders_retained_a  = retained_a,
        holders_retained_b  = retained_b,
        holders_split       = split_holders,
        dominant_chain      = dominant,
        contested           = contested,
        signal_type         = "FORK_DIVERGENCE",
        warning             = warning,
    )


def compute_fork_confidence(
    conf_genesis:    float,
    akashic_depth:   float,
    lam:             float = 0.001,
) -> float:
    """
    Post-fork confidence decay formula:
        conf_chain(t) = conf_genesis · (1 - e^(-λ · D(t)))

    As the chain accumulates depth D(t), confidence grows from genesis level.
    λ controls how fast confidence approaches conf_genesis.
    """
    return conf_genesis * (1.0 - math.exp(-lam * akashic_depth))


if __name__ == "__main__":
    # Simulate ETH/ETC-like fork — most holders stay on ETH (chain A)
    holders = []
    for i in range(1000):
        pre = 100.0
        if i < 800:  # 80% hold chain A
            holders.append(PreForkHolder(f"h{i}", pre, pre * 0.95, pre * 0.05))
        elif i < 920:  # 12% hold chain B
            holders.append(PreForkHolder(f"h{i}", pre, pre * 0.02, pre * 0.90))
        else:  # 8% hold both
            holders.append(PreForkHolder(f"h{i}", pre, pre * 0.85, pre * 0.80))

    profile = ForkProfile(
        fork_id="eth_etc_simulation",
        chain_a_id="ETH",
        chain_b_id="ETC",
        fork_block=1920000,
        fork_timestamp=1469020839.0,
        pre_fork_holders=holders,
        description="ETH/ETC fork simulation",
    )

    result = compute_fork_resolution(profile)
    print(f"CC_A={result.cc_a:.4f} CC_B={result.cc_b:.4f}")
    print(f"w_A={result.history_weight_a:.4f} w_B={result.history_weight_b:.4f}")
    print(f"Dominant: {result.dominant_chain}")
    assert result.cc_a > result.cc_b
    assert result.history_weight_a > 0.5
    print("L2.6 Fork Resolution: PASS")
