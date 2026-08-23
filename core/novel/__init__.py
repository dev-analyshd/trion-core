"""TRION Protocol — core.novel

Novel Primitives:
- Chameleon Protocol: adaptive noise under adversarial conditions
- Coordination Collapse Theorem: HHI-based validator monopoly prevention
- BIRP: Behavioral Identity Recovery Protocol (5-phase recovery)
- Semi-Immutability: bytecode immutable, behavioral expression adapts
  (implemented in core/spiritual/epigenetic.py)
- BCK: Behavioral Causal Keys
  (implemented in core/spiritual/living_security/genomic_genealogy.py)
- Behavioral ZK: zero-knowledge behavioral credentials
  (implemented in akashic/anima_regulatory.py)
"""

from .chameleon import (
    ChameleonProtocol, ThreatLevel, ExpressionMode, AWAState, ChameleonExpression,
    CHAMELEON_BASE_SIGMA, CHAMELEON_MAX_SIGMA, PROBE_WINDOW_SECS,
    PROBE_THRESHOLD_COUNT, ESCALATION_FACTOR,
)

from .coordination_collapse import (
    CoordinationCollapseTheorem,
)

from .behavioral_identity_recovery import (
    BIRPRecoveryEngine, RecoveryResult,
    TxRecord, BehavioralFingerprint, BehavioralCommitment,
    WitnessShard, RecoveryProof, WitnessAttestation,
    extract_behavioral_fingerprint, enroll_behavioral_identity,
    verify_behavioral_commitment, cosine_distance, issue_witness_shards,
    DELTA_RECOVERY, MIN_WITNESS_SHARDS, QUORUM_THRESHOLD,
    FINGERPRINT_DIMENSIONS, COMMITMENT_SALT_BYTES,
    RECOVERY_TTL_SECS, FEATURE_VERSION,
)

from .birp import (
    BIRPManager, BIRPPhase, BIRPOutcome, BIRPPhaseResult,
    BIRPRequest, DNACodeRegistration, ValidatorVote, BIRPMessage,
    BIRP_BATCH_MAX, BIRP_DEFAULT_TTL,
)

__all__ = [
    # Chameleon Protocol
    'ChameleonProtocol', 'ThreatLevel', 'ExpressionMode', 'AWAState',
    'ChameleonExpression',
    'CHAMELEON_BASE_SIGMA', 'CHAMELEON_MAX_SIGMA',
    'PROBE_WINDOW_SECS', 'PROBE_THRESHOLD_COUNT', 'ESCALATION_FACTOR',
    # Coordination Collapse Theorem
    'CoordinationCollapseTheorem',
    # BIRP (behavioral_identity_recovery module)
    'BIRPRecoveryEngine', 'RecoveryResult',
    'TxRecord', 'BehavioralFingerprint', 'BehavioralCommitment',
    'WitnessShard', 'RecoveryProof', 'WitnessAttestation',
    'extract_behavioral_fingerprint', 'enroll_behavioral_identity',
    'verify_behavioral_commitment', 'cosine_distance', 'issue_witness_shards',
    'DELTA_RECOVERY', 'MIN_WITNESS_SHARDS', 'QUORUM_THRESHOLD',
    'FINGERPRINT_DIMENSIONS', 'COMMITMENT_SALT_BYTES',
    'RECOVERY_TTL_SECS', 'FEATURE_VERSION',
    # BIRP Service (birp module)
    'BIRPManager', 'BIRPPhase', 'BIRPOutcome', 'BIRPPhaseResult',
    'BIRPRequest', 'DNACodeRegistration', 'ValidatorVote', 'BIRPMessage',
    'BIRP_BATCH_MAX', 'BIRP_DEFAULT_TTL',
]
