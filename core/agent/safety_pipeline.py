"""
TRION AI Agent Safety Pipeline
================================
TRION as mandatory behavioral validation middleware for AI agents.
Any AI agent must route decisions through this pipeline to receive:
  - Coherence stamp (is this action safe / coherent?)
  - Risk classification
  - Behavioral constraint enforcement
  - Evolutionary fitness scoring
  - SILENCE gate (block unsafe actions)

Usage:
    pipeline = TRIONAgentPipeline()
    result = pipeline.validate_action(agent_id, action, context)
    if result.allowed:
        execute(action)
    else:
        handle_blocked(result.reason)
"""

import time
import hashlib
import math
import logging
import sys
import os
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

logger = logging.getLogger(__name__)


class ActionType(Enum):
    TRADE = "trade"
    TRANSFER = "transfer"
    VOTE = "vote"
    DEPLOY = "deploy"
    CALL = "call"
    MINT = "mint"
    BURN = "burn"
    BRIDGE = "bridge"
    STAKE = "stake"
    UNSTAKE = "unstake"
    APPROVE = "approve"
    QUERY = "query"
    UNKNOWN = "unknown"


class ValidationOutcome(Enum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    MODIFIED = "MODIFIED"   # allowed with constraints applied
    DEFERRED = "DEFERRED"   # allowed after delay (cooling period)
    SILENCED = "SILENCED"   # blocked due to low coherence


@dataclass
class AgentAction:
    action_type: ActionType
    entity_id: str                   # contract/wallet being acted upon
    value_usd: float                 # estimated USD value
    chain_id: int
    raw_data: Dict = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)


@dataclass
class ValidationResult:
    outcome: ValidationOutcome
    allowed: bool
    coherence_score: float           # computed C(t) for this action
    risk_score: float
    confidence: float
    reason: str
    constraints: List[str]           # applied constraints if MODIFIED
    recommendations: List[str]
    fitness_delta: float             # expected agent fitness change
    behavioral_stamp: str            # tamper-proof TRION stamp
    processing_time_ms: float
    blocked_by: Optional[str] = None  # which gate blocked it


@dataclass
class AgentProfile:
    agent_id: str
    created_at: int
    total_actions: int = 0
    allowed_actions: int = 0
    blocked_actions: int = 0
    avg_coherence: float = 0.5
    fitness_score: float = 0.5       # evolves over time
    behavioral_history: List[float] = field(default_factory=list)
    reputation: float = 0.5
    trust_level: str = "PROBATION"   # PROBATION | TRUSTED | VERIFIED | EXEMPLARY


# In-memory agent registry (production: use DB)
_AGENT_REGISTRY: Dict[str, AgentProfile] = {}


class TRIONAgentPipeline:
    """
    TRION safety pipeline. Agents must route all significant actions through here.
    
    Gates (in order):
    1. SILENCE gate — block if coherence below minimum threshold
    2. RISK gate — block CRITICAL risk actions  
    3. VALUE gate — block value above agent's authorized limit
    4. MANIPULATION gate — block if action matches manipulation pattern
    5. EVOLUTION gate — reward/penalize based on fitness
    """

    SILENCE_THRESHOLD = 0.25       # coherence below this → SILENCE
    RISK_BLOCK_THRESHOLD = 0.85    # risk above this → BLOCK
    DEFAULT_VALUE_LIMIT = 100_000  # USD per action for PROBATION agents

    VALUE_LIMITS = {
        "PROBATION": 10_000,
        "TRUSTED": 100_000,
        "VERIFIED": 1_000_000,
        "EXEMPLARY": float("inf"),
    }

    def __init__(self, faiss_url: str = "http://127.0.0.1:8000",
                 oracle_url: str = "http://127.0.0.1:5000"):
        self.faiss_url = faiss_url
        self.oracle_url = oracle_url

    def _get_or_create_agent(self, agent_id: str) -> AgentProfile:
        if agent_id not in _AGENT_REGISTRY:
            _AGENT_REGISTRY[agent_id] = AgentProfile(
                agent_id=agent_id,
                created_at=int(time.time()),
            )
        return _AGENT_REGISTRY[agent_id]

    def _compute_action_coherence(self, action: AgentAction,
                                   agent: AgentProfile) -> float:
        # Base coherence from agent history
        base = agent.avg_coherence

        # Action-type risk modifiers
        risk_mods = {
            ActionType.QUERY: 0.0,
            ActionType.STAKE: -0.05,
            ActionType.UNSTAKE: -0.08,
            ActionType.TRANSFER: -0.10,
            ActionType.TRADE: -0.12,
            ActionType.VOTE: -0.05,
            ActionType.APPROVE: -0.15,
            ActionType.BRIDGE: -0.20,
            ActionType.DEPLOY: -0.18,
            ActionType.MINT: -0.25,
            ActionType.BURN: -0.22,
            ActionType.CALL: -0.10,
            ActionType.UNKNOWN: -0.30,
        }
        mod = risk_mods.get(action.action_type, -0.10)

        # Value modifier (large values are less coherent for new agents)
        value_mod = 0.0
        limit = self.VALUE_LIMITS[agent.trust_level]
        if limit > 0 and action.value_usd > 0:
            ratio = min(1.0, action.value_usd / limit)
            value_mod = -ratio * 0.2

        # Frequency penalty (too many actions too fast)
        freq_mod = 0.0
        history = agent.behavioral_history[-10:]
        if len(history) >= 5:
            avg_recent = sum(history[-5:]) / 5
            if avg_recent < 0.4:
                freq_mod = -0.15

        coherence = base + mod + value_mod + freq_mod
        return round(max(0.0, min(1.0, coherence)), 4)

    def _compute_risk_score(self, action: AgentAction) -> float:
        risk = 0.0

        # High-value actions are riskier
        if action.value_usd > 1_000_000:
            risk += 0.4
        elif action.value_usd > 100_000:
            risk += 0.25
        elif action.value_usd > 10_000:
            risk += 0.10

        # Risky action types
        risky = {
            ActionType.BRIDGE: 0.30,
            ActionType.MINT: 0.35,
            ActionType.DEPLOY: 0.25,
            ActionType.BURN: 0.20,
            ActionType.APPROVE: 0.15,
            ActionType.UNKNOWN: 0.40,
        }
        risk += risky.get(action.action_type, 0.05)

        # Check metadata for manipulation signals
        if action.metadata.get("flash_loan"):
            risk += 0.35
        if action.metadata.get("mev_bundle"):
            risk += 0.20
        if action.metadata.get("sandwich_detected"):
            risk += 0.30

        return round(min(1.0, risk), 4)

    def _check_manipulation_pattern(self, action: AgentAction,
                                     agent: AgentProfile) -> Tuple[bool, str]:
        # Circular flow detection
        history = agent.behavioral_history
        if len(history) > 10:
            if all(abs(h - history[-1]) < 0.05 for h in history[-5:]):
                return True, "Behavioral uniformity detected — possible bot/wash pattern"

        # Rapid large transfers
        if (action.action_type == ActionType.TRANSFER and
                action.value_usd > 500_000 and
                agent.total_actions < 10):
            return True, "Large transfer from new agent — insufficient behavioral history"

        # Flash loan + trade in same context
        if (action.metadata.get("flash_loan") and
                action.action_type == ActionType.TRADE):
            return True, "Flash loan combined with trade — potential price manipulation"

        return False, ""

    def _evolve_agent(self, agent: AgentProfile, outcome: ValidationOutcome,
                      coherence: float) -> float:
        # Update agent fitness via evolutionary pressure
        if outcome == ValidationOutcome.ALLOWED:
            delta = +0.02 * coherence
        elif outcome == ValidationOutcome.BLOCKED:
            delta = -0.05
        elif outcome == ValidationOutcome.SILENCED:
            delta = -0.10
        elif outcome == ValidationOutcome.MODIFIED:
            delta = +0.005
        else:
            delta = 0.0

        agent.fitness_score = round(max(0.0, min(1.0, agent.fitness_score + delta)), 4)
        agent.avg_coherence = round(
            (agent.avg_coherence * agent.total_actions + coherence) /
            (agent.total_actions + 1), 4
        )
        agent.behavioral_history.append(coherence)
        if len(agent.behavioral_history) > 100:
            agent.behavioral_history = agent.behavioral_history[-100:]

        # Trust level evolution
        if agent.fitness_score >= 0.85 and agent.total_actions >= 100:
            agent.trust_level = "EXEMPLARY"
        elif agent.fitness_score >= 0.70 and agent.total_actions >= 50:
            agent.trust_level = "VERIFIED"
        elif agent.fitness_score >= 0.55 and agent.total_actions >= 20:
            agent.trust_level = "TRUSTED"
        else:
            agent.trust_level = "PROBATION"

        return delta

    def validate_action(self, agent_id: str, action: AgentAction) -> ValidationResult:
        t0 = time.time()
        agent = self._get_or_create_agent(agent_id)
        agent.total_actions += 1

        coherence = self._compute_action_coherence(action, agent)
        risk = self._compute_risk_score(action)
        constraints = []
        recommendations = []
        blocked_by = None

        # Gate 1: SILENCE
        if coherence < self.SILENCE_THRESHOLD:
            outcome = ValidationOutcome.SILENCED
            reason = f"SILENCE gate: coherence {coherence:.3f} below minimum {self.SILENCE_THRESHOLD}"
            blocked_by = "SILENCE_GATE"
            agent.blocked_actions += 1
        # Gate 2: RISK
        elif risk >= self.RISK_BLOCK_THRESHOLD:
            outcome = ValidationOutcome.BLOCKED
            reason = f"RISK gate: risk score {risk:.3f} exceeds threshold {self.RISK_BLOCK_THRESHOLD}"
            blocked_by = "RISK_GATE"
            agent.blocked_actions += 1
        # Gate 3: VALUE
        elif action.value_usd > self.VALUE_LIMITS[agent.trust_level]:
            outcome = ValidationOutcome.BLOCKED
            reason = (f"VALUE gate: ${action.value_usd:,.0f} exceeds limit "
                      f"${self.VALUE_LIMITS[agent.trust_level]:,.0f} "
                      f"for trust level {agent.trust_level}")
            blocked_by = "VALUE_GATE"
            recommendations.append(f"Build behavioral history to reach TRUSTED level (current: {agent.trust_level})")
            agent.blocked_actions += 1
        # Gate 4: MANIPULATION
        else:
            is_manip, manip_reason = self._check_manipulation_pattern(action, agent)
            if is_manip:
                outcome = ValidationOutcome.BLOCKED
                reason = f"MANIPULATION gate: {manip_reason}"
                blocked_by = "MANIPULATION_GATE"
                agent.blocked_actions += 1
            else:
                # Gate 5: CONSTRAINTS (MODIFIED if needs limits)
                if risk > 0.50:
                    outcome = ValidationOutcome.MODIFIED
                    reason = "Action allowed with behavioral constraints applied"
                    constraints.append(f"Max slippage: 1.0%")
                    constraints.append(f"Max position: {min(action.value_usd, 50_000):.0f} USD")
                    recommendations.append("Consider splitting large actions into smaller tranches")
                    agent.allowed_actions += 1
                else:
                    outcome = ValidationOutcome.ALLOWED
                    reason = f"All gates passed. Coherence: {coherence:.3f}, Risk: {risk:.3f}"
                    agent.allowed_actions += 1

        fitness_delta = self._evolve_agent(agent, outcome, coherence)

        # Behavioral stamp
        raw = f"{agent_id}:{action.action_type.value}:{coherence}:{risk}:{int(t0)}"
        stamp = hashlib.sha256(raw.encode()).hexdigest()[:16]

        allowed = outcome in (ValidationOutcome.ALLOWED, ValidationOutcome.MODIFIED,
                              ValidationOutcome.DEFERRED)
        confidence = round(abs(coherence - risk) * 0.5 + 0.5, 4)

        return ValidationResult(
            outcome=outcome,
            allowed=allowed,
            coherence_score=coherence,
            risk_score=risk,
            confidence=confidence,
            reason=reason,
            constraints=constraints,
            recommendations=recommendations,
            fitness_delta=fitness_delta,
            behavioral_stamp=stamp,
            processing_time_ms=round((time.time() - t0) * 1000, 2),
            blocked_by=blocked_by,
        )

    def get_agent_profile(self, agent_id: str) -> dict:
        agent = self._get_or_create_agent(agent_id)
        return asdict(agent)

    def list_agents(self) -> List[dict]:
        return [asdict(a) for a in _AGENT_REGISTRY.values()]

    def train_agent(self, agent_id: str, positive_examples: List[dict],
                    negative_examples: List[dict]) -> dict:
        agent = self._get_or_create_agent(agent_id)
        for ex in positive_examples:
            coherence = ex.get("coherence", 0.7)
            agent.behavioral_history.append(coherence)
            agent.avg_coherence = round(
                (agent.avg_coherence * 0.9 + coherence * 0.1), 4
            )
            agent.fitness_score = min(1.0, agent.fitness_score + 0.01)
        for ex in negative_examples:
            coherence = ex.get("coherence", 0.2)
            agent.behavioral_history.append(coherence)
            agent.fitness_score = max(0.0, agent.fitness_score - 0.02)
        return {
            "agent_id": agent_id,
            "new_fitness": agent.fitness_score,
            "new_coherence": agent.avg_coherence,
            "trust_level": agent.trust_level,
            "trained_on": len(positive_examples) + len(negative_examples),
        }


# Singleton instance
_pipeline_instance: Optional[TRIONAgentPipeline] = None


def get_pipeline() -> TRIONAgentPipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = TRIONAgentPipeline()
    return _pipeline_instance
