"""
TRION Protocol — L2.6 Fork Resolution Protocol
Chapter 7.2: Fork Divergence

FORK_DIVERGENCE signal — emitted when a fork event is detected.

History inheritance (whitepaper L2.6 spec):
    CC_A = proportion of pre-fork holders still holding chain A
    CC_B = proportion of pre-fork holders still holding chain B

These are behavioral loyalty metrics — they measure the revealed preferences
of participants rather than relying on social consensus or political decisions.

The fork that retains more of the original community has stronger behavioral
continuity — and thus inherits more of the pre-fork behavioral history.

Asymmetric inheritance rule (whitepaper L2.6):
    If CC_A >> CC_B  (CC_A > DOMINANCE_THRESHOLD):
        w_A = 1.0                          # full D_inherited
        w_B = (1 - CC_A)                   # confidence discount on weaker fork
    If CC_B >> CC_A  (CC_B > DOMINANCE_THRESHOLD):
        w_B = 1.0                          # full D_inherited
        w_A = (1 - CC_B)                   # confidence discount on weaker fork
    If CC_A ≈ CC_B  (neither > DOMINANCE_THRESHOLD):
        w_A = 0.5,  w_B = 0.5              # equal split
        divergence_flag = True             # disputed history inheritance

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


# Whitepaper L2.6 spec: a fork is DOMINANT when its continuity coefficient
# exceeds this threshold — it inherits FULL pre-fork history (D_inherited = 1.0)
# while the weaker fork receives a confidence-discounted share (1 - CC_dominant).
# When NEITHER fork exceeds this threshold (CC_A ≈ CC_B), history is split
# 50/50 with divergence_flag = True (disputed inheritance).
DOMINANCE_THRESHOLD: float = 0.60


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
    contested:                bool    # CC_A and CC_B both > 0.40 (legacy flag)
    divergence_flag:          bool    # Spec L2.6: True when neither fork is
                                                #   dominant (CC_A ≈ CC_B); history
                                                #   inheritance is disputed.
    confidence_discount_a:    float   # 1 - CC_dominant applied to non-dominant
    confidence_discount_b:    float   # fork; 0.0 for dominant fork

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

    History inheritance follows the asymmetric rule (whitepaper L2.6 spec):
        - If CC_A > DOMINANCE_THRESHOLD (0.60) and CC_A > CC_B:
            w_A = 1.0 (full D_inherited), w_B = 1 - CC_A (confidence discount)
        - If CC_B > DOMINANCE_THRESHOLD (0.60) and CC_B > CC_A:
            w_B = 1.0 (full D_inherited), w_A = 1 - CC_B (confidence discount)
        - Else (CC_A ≈ CC_B, neither dominant):
            w_A = 0.5, w_B = 0.5, divergence_flag = True (disputed inheritance)
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
            divergence_flag=True,
            confidence_discount_a=0.5,
            confidence_discount_b=0.5,
            signal_type="FORK_DIVERGENCE",
            warning="No pre-fork holder data — defaulting to equal weights",
        )

    retained_a = 0
    retained_b = 0
    split_holders = 0
    valid_holders = 0

    for holder in holders:
        if holder.pre_fork_balance <= 0:
            continue
        valid_holders += 1
        threshold = holder.pre_fork_balance * balance_threshold
        holds_a = holder.post_fork_a >= threshold
        holds_b = holder.post_fork_b >= threshold

        if holds_a:
            retained_a += 1
        if holds_b:
            retained_b += 1
        if holds_a and holds_b:
            split_holders += 1

    cc_a = retained_a / valid_holders if valid_holders > 0 else 0.5
    cc_b = retained_b / valid_holders if valid_holders > 0 else 0.5

    # Asymmetric inheritance rule (whitepaper L2.6 spec):
    #   * If exactly one fork's CC exceeds DOMINANCE_THRESHOLD, that fork is
    #     DOMINANT and inherits FULL pre-fork history (w = 1.0). The weaker
    #     fork receives D_inherited × (1 - CC_dominant) with a confidence
    #     discount applied to its post-fork confidence.
    #   * If NEITHER fork is dominant (CC_A ≈ CC_B, both below threshold, or
    #     both above threshold with similar loyalty), history is split 50/50
    #     and divergence_flag is raised (disputed inheritance).
    a_dominant = cc_a > DOMINANCE_THRESHOLD and cc_a > cc_b
    b_dominant = cc_b > DOMINANCE_THRESHOLD and cc_b > cc_a

    if a_dominant:
        weight_a = 1.0
        weight_b = max(0.0, 1.0 - cc_a)
        discount_a = 0.0
        discount_b = weight_b
        dominant = profile.chain_a_id
        divergence_flag = False
        warning = (
            f"Fork A ({profile.chain_a_id}) dominant: "
            f"CC_A={cc_a:.3f} > DOMINANCE_THRESHOLD={DOMINANCE_THRESHOLD}. "
            f"Full D_inherited granted to {profile.chain_a_id}; "
            f"{profile.chain_b_id} inherits {weight_b:.3f} × D_inherited "
            f"with confidence discount."
        )
    elif b_dominant:
        weight_a = max(0.0, 1.0 - cc_b)
        weight_b = 1.0
        discount_a = weight_a
        discount_b = 0.0
        dominant = profile.chain_b_id
        divergence_flag = False
        warning = (
            f"Fork B ({profile.chain_b_id}) dominant: "
            f"CC_B={cc_b:.3f} > DOMINANCE_THRESHOLD={DOMINANCE_THRESHOLD}. "
            f"Full D_inherited granted to {profile.chain_b_id}; "
            f"{profile.chain_a_id} inherits {weight_a:.3f} × D_inherited "
            f"with confidence discount."
        )
    else:
        # CC_A ≈ CC_B: contested — equal split with divergence_flag
        weight_a = 0.5
        weight_b = 0.5
        discount_a = 0.5
        discount_b = 0.5
        dominant = profile.chain_a_id if cc_a >= cc_b else profile.chain_b_id
        divergence_flag = True
        warning = (
            f"Contested fork: CC_A={cc_a:.3f} CC_B={cc_b:.3f} "
            f"(neither exceeds DOMINANCE_THRESHOLD={DOMINANCE_THRESHOLD}). "
            "Both chains inherit D_inherited × 0.5 with divergence_flag=True "
            "(disputed history inheritance)."
        )

    # Legacy flag: both chains retain significant community (both > 0.40).
    contested = (cc_a > 0.40) and (cc_b > 0.40)

    # Edge case: full abandonment
    if cc_a < 0.20 and cc_b < 0.20:
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
        divergence_flag     = divergence_flag,
        confidence_discount_a = discount_a,
        confidence_discount_b = discount_b,
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
    print(f"ETH/ETC (CC_A dominant): CC_A={result.cc_a:.4f} CC_B={result.cc_b:.4f}")
    print(f"w_A={result.history_weight_a:.4f} w_B={result.history_weight_b:.4f} "
          f"discount_a={result.confidence_discount_a:.4f} "
          f"discount_b={result.confidence_discount_b:.4f} "
          f"divergence_flag={result.divergence_flag}")
    assert result.cc_a > result.cc_b
    # Asymmetric rule: CC_A=0.88 > 0.60 → ETH dominant → w_A = 1.0, w_B = 1 - 0.88 = 0.12
    assert result.history_weight_a == 1.0
    assert abs(result.history_weight_b - (1.0 - result.cc_a)) < 1e-9
    assert result.dominant_chain == "ETH"
    assert not result.divergence_flag
    print("  ETH/ETC asymmetric inheritance: PASS")

    # Contested fork: 50/50 split — neither chain is dominant (both < 0.60)
    holders_tie = [
        PreForkHolder(f"th{i}", 100.0,
                      90.0 if i < 50 else 0.0,
                      0.0 if i < 50 else 90.0)
        for i in range(100)
    ]
    profile_tie = ForkProfile("eth_etc_tie", "ETH", "ETC", 1920000, 1469020839.0,
                              holders_tie, "Contested ETH/ETC")
    result_tie = compute_fork_resolution(profile_tie)
    print(f"Tie (neither dominant): CC_A={result_tie.cc_a:.4f} CC_B={result_tie.cc_b:.4f}")
    print(f"w_A={result_tie.history_weight_a:.4f} w_B={result_tie.history_weight_b:.4f} "
          f"divergence_flag={result_tie.divergence_flag}")
    assert abs(result_tie.cc_a - 0.5) < 1e-9
    assert abs(result_tie.cc_b - 0.5) < 1e-9
    # Neither > 0.60 → contested → 50/50 with divergence_flag=True
    assert result_tie.history_weight_a == 0.5
    assert result_tie.history_weight_b == 0.5
    assert result_tie.divergence_flag
    print("  Tie → divergence_flag=True: PASS")

    print("L2.6 Fork Resolution: PASS")
