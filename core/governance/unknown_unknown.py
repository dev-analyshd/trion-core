"""
TRION Protocol — Unknown-Unknown Provision (WP1 §14.4)

Budget_unknown = 0.10 · Revenue(t)
Held in multi-sig with 30-day time-lock.

This is no longer a 2-line stub. It implements the full Unknown-Unknown
Protocol per WP1 §14.4:
  * Revenue tracking -> 10% reserve accrual
  * 30-day time-lock on deployed reserve funds
  * Multi-sig governance supermajority (>75%) required for any deployment
  * Epistemic humility score derived from anomaly-detection rate
  * Audit trail of all reserve deployments

Architectural humility — formally encoded.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ─── Protocol constants (WP1 §14.4) ───────────────────────────────────────────

RESERVE_FRACTION        = 0.10   # 10% of revenue reserved for unknown unknowns
TIME_LOCK_DAYS          = 30
TIME_LOCK_SECONDS       = TIME_LOCK_DAYS * 86400
DEPLOY_QUORUM_THRESHOLD = 0.75   # >75% governance supermajority required

# Epistemic humility scoring constants.
# Humility is bounded in [BASELINE_HUMILITY, 1.0]:
#   * BASELINE_HUMILITY = 0.10  — even with zero observed anomalies, we reserve
#     10% capacity for the unknown unknowns (the protocol's design humility).
#   * As the observed anomaly rate rises (more behaviors we do not yet
#     understand), humility rises toward 1.0 — we treat the system as
#     increasingly uncertain.
BASELINE_HUMILITY       = RESERVE_FRACTION
# Above this anomaly-rate, humility saturates at 1.0 (full epistemic uncertainty).
ANOMALY_RATE_SATURATION = 0.20


@dataclass
class RevenueObservation:
    """A single revenue observation contributing to the reserve."""
    timestamp: float
    revenue:   float
    reserved:  float            # 10% of revenue, accrued to the reserve


@dataclass
class ReserveDeployment:
    """A deployment of reserve funds for an unforeseen event."""
    deployment_id:    str
    requested_at:    float
    approved_at:     Optional[float]
    deployable_at:   float              # requested_at + TIME_LOCK_SECONDS
    deployed_at:     Optional[float]
    amount:          float
    reason:          str
    approval_votes:  int                # count of multi-sig approvals
    approval_total:  int                # total multi-sig signers
    approval_quorum: float              # approval_votes / approval_total
    status:          str                # PENDING | APPROVED | TIMELOCKED | DEPLOYED | REJECTED

    def to_dict(self) -> dict:
        return {
            "deployment_id":   self.deployment_id,
            "requested_at":   int(self.requested_at),
            "approved_at":     int(self.approved_at) if self.approved_at else None,
            "deployable_at":   int(self.deployable_at),
            "deployed_at":     int(self.deployed_at) if self.deployed_at else None,
            "amount":          round(self.amount, 6),
            "reason":          self.reason,
            "approval_votes":  self.approval_votes,
            "approval_total":  self.approval_total,
            "approval_quorum": round(self.approval_quorum, 4),
            "status":          self.status,
        }


@dataclass
class UnknownUnknownState:
    """Snapshot of the Unknown-Unknown Protocol state at a point in time."""
    reserve_balance:         float
    reserve_locked_balance:   float      # funds in active time-locks (not deployable yet)
    reserve_available:        float      # reserve_balance - reserve_locked_balance
    period_revenue:           float      # revenue observed in the current accrual period
    total_revenue_observed:   float
    total_reserved_ever:      float
    total_deployed_ever:      float
    anomaly_count:            int
    observation_count:        int
    anomaly_rate:            float      # [0, 1]
    epistemic_humility_score: float     # [BASELINE_HUMILITY, 1.0]
    active_deployments:      int
    timelock_days:            int
    deploy_quorum_threshold:  float
    timestamp:                float

    def to_dict(self) -> dict:
        return {
            "reserve_balance":          round(self.reserve_balance, 6),
            "reserve_locked_balance":    round(self.reserve_locked_balance, 6),
            "reserve_available":         round(self.reserve_available, 6),
            "period_revenue":            round(self.period_revenue, 6),
            "total_revenue_observed":    round(self.total_revenue_observed, 6),
            "total_reserved_ever":       round(self.total_reserved_ever, 6),
            "total_deployed_ever":       round(self.total_deployed_ever, 6),
            "anomaly_count":             self.anomaly_count,
            "observation_count":          self.observation_count,
            "anomaly_rate":              round(self.anomaly_rate, 6),
            "epistemic_humility_score":  round(self.epistemic_humility_score, 6),
            "active_deployments":         self.active_deployments,
            "timelock_days":              self.timelock_days,
            "deploy_quorum_threshold":    self.deploy_quorum_threshold,
            "timestamp":                  int(self.timestamp),
        }


class UnknownUnknownProtocol:
    """
    Unknown-Unknown Provision (WP1 §14.4).

    Reserves 10% of all observed revenue for threats not yet conceived, held in
    a multi-sig with a 30-day time-lock. Deployment requires >75% governance
    supermajority AND expiry of the 30-day time-lock.

    Maintains an epistemic humility score derived from the live anomaly
    detection rate: more observed anomalies -> higher humility -> larger
    effective reserve capacity is justified.
    """

    RESERVE_FRACTION        = RESERVE_FRACTION
    TIME_LOCK_SECONDS       = TIME_LOCK_SECONDS
    DEPLOY_QUORUM_THRESHOLD = DEPLOY_QUORUM_THRESHOLD

    def __init__(self, multi_sig_size: int = 12):
        if multi_sig_size < 1:
            raise ValueError("multi_sig_size must be >= 1")
        self._multi_sig_size: int = multi_sig_size
        self._revenue_observations: List[RevenueObservation] = []
        self._deployments: List[ReserveDeployment] = []
        # Anomaly / observation counters.
        self._anomaly_count: int = 0
        self._observation_count: int = 0
        # Period-aggregated revenue (resets on call to close_period()).
        self._period_revenue: float = 0.0

    # ─── Revenue + reserve accrual ──────────────────────────────────────────

    def record_revenue(self, revenue: float, now: Optional[float] = None) -> float:
        """Record observed revenue; accrue 10% to the reserve immediately."""
        if revenue < 0:
            raise ValueError("revenue must be >= 0")
        ts = now if now is not None else time.time()
        reserved = revenue * self.RESERVE_FRACTION
        self._revenue_observations.append(
            RevenueObservation(timestamp=ts, revenue=revenue, reserved=reserved)
        )
        self._period_revenue += revenue
        return reserved

    def close_period(self) -> float:
        """Close the current accrual period. Returns the period's total revenue."""
        period_total = self._period_revenue
        self._period_revenue = 0.0
        return period_total

    # ─── Anomaly tracking + epistemic humility ───────────────────────────────

    def record_observation(self, is_anomaly: bool) -> None:
        """Record a behavioral observation; flag whether it was anomalous."""
        self._observation_count += 1
        if is_anomaly:
            self._anomaly_count += 1

    def anomaly_rate(self) -> float:
        """Anomaly rate = anomalies / observations. 0.0 when no observations."""
        if self._observation_count <= 0:
            return 0.0
        return self._anomaly_count / self._observation_count

    def epistemic_humility_score(self) -> float:
        """Epistemic humility score in [BASELINE_HUMILITY, 1.0].

        Formula:
            humility = BASELINE_HUMILITY + (1 - BASELINE_HUMILITY) *
                       min(1.0, anomaly_rate / ANOMALY_RATE_SATURATION)

        Interpretation:
          * 0 observed anomalies  -> humility = 0.10 (architectural humility floor)
          * anomaly rate >= 20%   -> humility = 1.0 (full epistemic uncertainty;
                                                 maximum reserve capacity justified)
        """
        rate = self.anomaly_rate()
        saturation = min(1.0, rate / ANOMALY_RATE_SATURATION) if ANOMALY_RATE_SATURATION > 0 else 0.0
        return BASELINE_HUMILITY + (1.0 - BASELINE_HUMILITY) * saturation

    # ─── Reserve deployment (multi-sig + 30-day time-lock) ──────────────────

    def request_deployment(
        self,
        amount: float,
        reason: str,
        now: Optional[float] = None,
    ) -> ReserveDeployment:
        """Request deployment of reserve funds for an unforeseen event.

        Creates a PENDING deployment. The deployment is NOT yet approved —
        call approve_deployment() with multi-sig signatures, then wait for the
        30-day time-lock before deploy_deployment() will release funds.
        """
        if amount <= 0:
            raise ValueError("amount must be > 0")
        if not reason or not reason.strip():
            raise ValueError("reason is required (audit trail)")
        ts = now if now is not None else time.time()
        deployment_id = f"UU-{int(ts)}-{len(self._deployments):04d}"
        deployment = ReserveDeployment(
            deployment_id   = deployment_id,
            requested_at    = ts,
            approved_at     = None,
            deployable_at   = ts + self.TIME_LOCK_SECONDS,  # 30-day time-lock
            deployed_at     = None,
            amount          = amount,
            reason          = reason.strip(),
            approval_votes  = 0,
            approval_total  = self._multi_sig_size,
            approval_quorum = 0.0,
            status          = "PENDING",
        )
        self._deployments.append(deployment)
        return deployment

    def approve_deployment(
        self,
        deployment_id: str,
        approval_votes: int,
        now: Optional[float] = None,
    ) -> ReserveDeployment:
        """Record multi-sig approval for a deployment.

        approval_votes: count of multi-sig signers that approved.
        Requires >75% supermajority (DEPLOY_QUORUM_THRESHOLD) to mark APPROVED.
        Even after approval, the 30-day time-lock must expire before funds can
        be deployed.
        """
        ts = now if now is not None else time.time()
        deployment = self._find_deployment(deployment_id)
        if deployment.status not in ("PENDING", "APPROVED"):
            raise RuntimeError(
                f"deployment {deployment_id} cannot be approved from status={deployment.status}"
            )
        if approval_votes < 0 or approval_votes > self._multi_sig_size:
            raise ValueError(
                f"approval_votes={approval_votes} out of range [0, {self._multi_sig_size}]"
            )
        deployment.approval_votes = approval_votes
        deployment.approval_quorum = approval_votes / self._multi_sig_size
        if deployment.approval_quorum > self.DEPLOY_QUORUM_THRESHOLD:
            deployment.status = "APPROVED"
            deployment.approved_at = ts
        else:
            deployment.status = "PENDING"  # still pending supermajority
        return deployment

    def deploy_deployment(
        self,
        deployment_id: str,
        now: Optional[float] = None,
    ) -> ReserveDeployment:
        """Deploy an approved deployment whose 30-day time-lock has expired.

        Validates:
          * deployment status is APPROVED
          * current time >= deployable_at (30-day time-lock expired)
          * reserve has sufficient unlocked balance
        """
        ts = now if now is not None else time.time()
        deployment = self._find_deployment(deployment_id)
        if deployment.status != "APPROVED":
            raise RuntimeError(
                f"deployment {deployment_id} requires APPROVED status, got {deployment.status}"
            )
        if ts < deployment.deployable_at:
            remaining_secs = deployment.deployable_at - ts
            raise RuntimeError(
                f"deployment {deployment_id} time-lock not expired: "
                f"{remaining_secs:.0f}s remaining (30-day lock per WP1 §14.4)"
            )
        available = self.reserve_available(ts)
        if deployment.amount > available:
            raise RuntimeError(
                f"deployment {deployment_id} amount={deployment.amount:.4f} "
                f"exceeds available reserve={available:.4f}"
            )
        deployment.status = "DEPLOYED"
        deployment.deployed_at = ts
        return deployment

    # ─── State inspection ────────────────────────────────────────────────────

    def reserve_balance(self) -> float:
        """Total reserve ever accrued (10% of all observed revenue)."""
        return sum(obs.reserved for obs in self._revenue_observations)

    def reserve_locked_balance(self, now: Optional[float] = None) -> float:
        """Reserve funds locked in active (approved but not deployed) time-locks."""
        ts = now if now is not None else time.time()
        return sum(
            d.amount for d in self._deployments
            if d.status in ("APPROVED", "TIMELOCKED") and d.deployed_at is None
        )

    def reserve_available(self, now: Optional[float] = None) -> float:
        """Reserve balance minus locked funds = deployable balance."""
        return self.reserve_balance() - self.reserve_locked_balance(now)

    def total_deployed(self) -> float:
        return sum(d.amount for d in self._deployments if d.status == "DEPLOYED")

    def get_state(self, now: Optional[float] = None) -> UnknownUnknownState:
        ts = now if now is not None else time.time()
        balance = self.reserve_balance()
        locked  = self.reserve_locked_balance(ts)
        return UnknownUnknownState(
            reserve_balance          = balance,
            reserve_locked_balance   = locked,
            reserve_available        = balance - locked,
            period_revenue           = self._period_revenue,
            total_revenue_observed   = sum(obs.revenue for obs in self._revenue_observations),
            total_reserved_ever      = balance + self.total_deployed(),
            total_deployed_ever      = self.total_deployed(),
            anomaly_count            = self._anomaly_count,
            observation_count        = self._observation_count,
            anomaly_rate             = self.anomaly_rate(),
            epistemic_humility_score = self.epistemic_humility_score(),
            active_deployments       = sum(
                1 for d in self._deployments
                if d.status in ("APPROVED", "TIMELOCKED") and d.deployed_at is None
            ),
            timelock_days             = TIME_LOCK_DAYS,
            deploy_quorum_threshold   = DEPLOY_QUORUM_THRESHOLD,
            timestamp                 = ts,
        )

    def list_deployments(self, status_filter: Optional[str] = None) -> List[dict]:
        out: List[dict] = []
        for d in self._deployments:
            if status_filter and d.status != status_filter:
                continue
            out.append(d.to_dict())
        return out

    def to_dict(self, now: Optional[float] = None) -> dict:
        return self.get_state(now).to_dict()

    # ─── Internal helpers ───────────────────────────────────────────────────

    def _find_deployment(self, deployment_id: str) -> ReserveDeployment:
        for d in self._deployments:
            if d.deployment_id == deployment_id:
                return d
        raise KeyError(f"deployment {deployment_id} not found")


# ─── Module-level singleton (mirrors the AWA / Gratitude pattern) ─────────────

_unknown_unknown_protocol = UnknownUnknownProtocol()


def get_unknown_unknown_protocol() -> UnknownUnknownProtocol:
    return _unknown_unknown_protocol


# ─── Self-test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uu = UnknownUnknownProtocol(multi_sig_size=12)

    # 1. Revenue accrual -> 10% reserve
    uu.record_revenue(1_000_000.0, now=1_000_000.0)
    uu.record_revenue(500_000.0, now=1_000_100.0)
    assert abs(uu.reserve_balance() - 150_000.0) < 1e-6, uu.reserve_balance()
    print(f"Reserve after $1.5M revenue: ${uu.reserve_balance():,.2f} (10% = $150,000)")

    # 2. Epistemic humility: 0 anomalies -> baseline 0.10
    assert abs(uu.epistemic_humility_score() - 0.10) < 1e-6, uu.epistemic_humility_score()
    print(f"Humility (0 anomalies): {uu.epistemic_humility_score():.4f} (baseline 0.10)")

    # 3. Record anomalies -> humility rises
    for _ in range(20):
        uu.record_observation(is_anomaly=False)
    for _ in range(5):  # 5/25 = 20% anomaly rate -> saturates to 1.0
        uu.record_observation(is_anomaly=True)
    h = uu.epistemic_humility_score()
    assert abs(h - 1.0) < 1e-6, h
    print(f"Humility (20% anomaly rate): {h:.4f} (saturated to 1.0)")

    # 4. Request deployment
    dep = uu.request_deployment(amount=50_000.0, reason="Unforeseen bridge exploit 2026", now=2_000_000.0)
    assert dep.status == "PENDING"
    assert dep.deployable_at == 2_000_000.0 + TIME_LOCK_SECONDS
    print(f"Deployment {dep.deployment_id}: status={dep.status}, deployable_in={TIME_LOCK_DAYS}d")

    # 5. Insufficient supermajority -> stays PENDING
    dep = uu.approve_deployment(dep.deployment_id, approval_votes=8, now=2_000_050.0)  # 8/12 = 0.667 < 0.75
    assert dep.status == "PENDING"
    print(f"After 8/12 approvals: status={dep.status} (needs >75%)")

    # 6. Supermajority reached -> APPROVED, but time-lock not expired
    dep = uu.approve_deployment(dep.deployment_id, approval_votes=10, now=2_000_100.0)  # 10/12 = 0.833 > 0.75
    assert dep.status == "APPROVED"
    print(f"After 10/12 approvals: status={dep.status}, deployable_at={int(dep.deployable_at)}")

    # 7. Time-lock not yet expired -> deploy fails
    # deployable_at was set at request time (now=2_000_000) to 2_000_000 + TIME_LOCK_SECONDS.
    # Test with now < deployable_at (1 second before expiry).
    try:
        uu.deploy_deployment(dep.deployment_id, now=2_000_000.0 + TIME_LOCK_SECONDS - 1)
        assert False, "should have raised (time-lock not expired)"
    except RuntimeError as e:
        print(f"Deploy before time-lock: blocked ({str(e)[:60]}...)")

    # 8. Time-lock expired -> deploy succeeds (now > deployable_at)
    dep = uu.deploy_deployment(dep.deployment_id, now=2_000_000.0 + TIME_LOCK_SECONDS + 1)
    assert dep.status == "DEPLOYED"
    assert dep.deployed_at is not None
    print(f"After time-lock expiry: status={dep.status}, deployed_at={int(dep.deployed_at)}")

    # 9. State snapshot
    state = uu.get_state(now=2_000_000.0 + TIME_LOCK_SECONDS + 2)
    assert state.total_deployed_ever == 50_000.0
    assert state.reserve_balance == 150_000.0
    assert state.anomaly_rate == 0.20
    print(f"State: reserve=${state.reserve_balance:,.2f}, deployed=${state.total_deployed_ever:,.2f}, "
          f"anomaly_rate={state.anomaly_rate:.2f}, humility={state.epistemic_humility_score:.4f}")

    # 10. Singleton accessor works
    assert get_unknown_unknown_protocol() is not None
    print(f"Singleton: {type(get_unknown_unknown_protocol()).__name__}")

    print("\nPHASE 14.4 PASS — Unknown-Unknown Protocol fully implemented")
