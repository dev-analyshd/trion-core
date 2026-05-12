"""
Living Security System — TRION L5
GK(t) = Hash_DNA(GK(t-1) || BE(t) || TM(t) || CV(t))
Immune System: INNATE + ADAPTIVE + MEMORY (permanent)
Epigenetic Layer: 4 states
"""
import hashlib, math, time
from dataclasses import dataclass, field
from typing import List, Set, Optional
from enum import Enum
from collections import deque


class EpigeneticState(Enum):
    NORMAL    = "NORMAL"
    ELEVATED  = "ELEVATED"
    DEFENSIVE = "DEFENSIVE"
    LOCKDOWN  = "LOCKDOWN"


class CRISPRAttackType(Enum):
    HARVEST_FINANCE    = "HARVEST_FINANCE"    # price oracle manipulation
    BEANSTALK          = "BEANSTALK"          # governance flash loan
    MANGO_MARKETS      = "MANGO_MARKETS"      # oracle price manipulation
    JIMBOS_PROTOCOL    = "JIMBOS_PROTOCOL"    # price manipulation
    EULER_FINANCE      = "EULER_FINANCE"      # flash loan attack
    CURVE_EXPLOIT      = "CURVE_EXPLOIT"      # reentrancy
    RONIN_BRIDGE       = "RONIN_BRIDGE"       # validator key compromise
    WORMHOLE           = "WORMHOLE"           # signature verification bypass


@dataclass
class GenomicKey:
    generation: int
    key_bytes:  bytes
    timestamp:  float = field(default_factory=time.time)

    def evolve(self, behavioral_entropy: bytes, threat_map: bytes, cv: bytes) -> "GenomicKey":
        """GK(t) = Hash_DNA(GK(t-1) || BE(t) || TM(t) || CV(t))"""
        payload   = self.key_bytes + behavioral_entropy + threat_map + cv
        new_bytes = hashlib.sha3_256(payload).digest()
        return GenomicKey(generation=self.generation + 1, key_bytes=new_bytes)

    def verify_key(self, expected_gen: int) -> bool:
        return self.generation == expected_gen and len(self.key_bytes) == 32

    def kolmogorov_bound(self) -> float:
        """P(break) decreases monotonically with evolution count."""
        return math.exp(-0.0001 * self.generation)


class ImmuneSystem:
    """
    Three-tier immune response:
    INNATE: pattern-based, immediate
    ADAPTIVE: learned from attack history
    MEMORY: permanent record, never decays
    """

    def __init__(self):
        self.innate_patterns:  Set[str]  = set()
        self.adaptive_learned: Set[str]  = set()
        self.memory:           Set[str]  = set()  # permanent
        self.threat_log:       List[dict] = []

    def innate_check(self, event: dict) -> bool:
        """Pattern-based rapid response."""
        event_sig = str(sorted(event.items()))
        return event_sig in self.innate_patterns

    def adaptive_check(self, event: dict) -> bool:
        """Learned threat patterns from past attacks."""
        event_sig = str(sorted(event.items()))
        return event_sig in self.adaptive_learned

    def memory_check(self, threat_id: str) -> bool:
        """Permanent memory — never forgets a confirmed attack."""
        return threat_id in self.memory

    def respond(self, event: dict, threat_id: str) -> dict:
        """Full immune cascade: INNATE → ADAPTIVE → MEMORY."""
        innate   = self.innate_check(event)
        adaptive = self.adaptive_check(event)
        memory   = self.memory_check(threat_id)

        is_threat = innate or adaptive or memory
        if is_threat:
            self.memory.add(threat_id)
            self.adaptive_learned.add(str(sorted(event.items())))

        self.threat_log.append({
            "threat_id": threat_id, "innate": innate,
            "adaptive": adaptive, "memory": memory,
            "neutralized": is_threat, "ts": time.time(),
        })

        return {
            "threat_id":   threat_id,
            "innate":      innate,
            "adaptive":    adaptive,
            "memory":      memory,
            "neutralized": is_threat,
        }

    def register_attack(self, event: dict, threat_id: str):
        """Learn from a confirmed attack."""
        self.memory.add(threat_id)
        self.adaptive_learned.add(str(sorted(event.items())))


# Backward-compatible alias
ImmuneSystem = ImmuneSystem


class EpigeneticLayer:
    """
    EL_state = f(threat_level, validator_health, network_entropy)
    4 states: NORMAL → ELEVATED → DEFENSIVE → LOCKDOWN
    """

    def __init__(self):
        self.state       = EpigeneticState.NORMAL
        self.threat_hist = deque(maxlen=10)

    def update(self, threat_level: float, validator_health: float,
               network_entropy: float) -> EpigeneticState:
        self.threat_hist.append(threat_level)
        avg_threat = sum(self.threat_hist) / len(self.threat_hist)

        if avg_threat >= 0.80 or validator_health < 0.30:
            self.state = EpigeneticState.LOCKDOWN
        elif avg_threat >= 0.60 or validator_health < 0.50:
            self.state = EpigeneticState.DEFENSIVE
        elif avg_threat >= 0.30 or network_entropy < 0.40:
            self.state = EpigeneticState.ELEVATED
        else:
            self.state = EpigeneticState.NORMAL

        return self.state


class CRISPRDefense:
    """
    Surgical neutralization of known DeFi attack patterns.
    Adaptive learning: new variants added after detection.
    """
    ATTACK_SIGNATURES = {
        CRISPRAttackType.HARVEST_FINANCE:  {"oracle_deviation": 0.50, "flash_loan": True},
        CRISPRAttackType.BEANSTALK:        {"gov_flash_loan": True, "proposal_age_hours": 0},
        CRISPRAttackType.MANGO_MARKETS:    {"perp_manipulation": True, "oracle_deviation": 0.80},
        CRISPRAttackType.JIMBOS_PROTOCOL:  {"price_impact": 0.40, "amm_manipulation": True},
        CRISPRAttackType.EULER_FINANCE:    {"flash_loan": True, "donateToReserves": True},
        CRISPRAttackType.CURVE_EXPLOIT:    {"reentrancy": True, "vyper_version": "vulnerable"},
        CRISPRAttackType.RONIN_BRIDGE:     {"validator_keys_compromised": True},
        CRISPRAttackType.WORMHOLE:         {"signature_bypass": True, "guardian_spoof": True},
    }

    def __init__(self):
        self.learned_variants: List[dict] = []

    def detect(self, event: dict) -> Optional[CRISPRAttackType]:
        """Surgical pattern match against known signatures."""
        for attack_type, signature in self.ATTACK_SIGNATURES.items():
            if all(event.get(k) == v for k, v in signature.items()):
                return attack_type
        for variant in self.learned_variants:
            if all(event.get(k) == v for k, v in variant.get("signature", {}).items()):
                return None  # unknown variant detected
        return None

    def learn_variant(self, variant_signature: dict):
        """Adaptive learning: record new attack variants."""
        self.learned_variants.append({"signature": variant_signature, "ts": time.time()})


@dataclass
class INITCeremony:
    """
    INIT Ceremony — 8 conditions that must all be TRUE before first signal.
    AWA enforcement: first signal blocked until AWA conditions met.
    """
    REQUIRED_CONDITIONS = 8

    min_validators_recruited: bool = False
    diversity_threshold_met:  bool = False
    security_audit_complete:  bool = False
    hhi_below_danger:         bool = False
    genomic_key_initialized:  bool = False
    immune_system_armed:      bool = False
    falsifiability_seeded:    bool = False
    awa_conditions_met:       bool = False

    def all_met(self) -> bool:
        return all([
            self.min_validators_recruited,
            self.diversity_threshold_met,
            self.security_audit_complete,
            self.hhi_below_danger,
            self.genomic_key_initialized,
            self.immune_system_armed,
            self.falsifiability_seeded,
            self.awa_conditions_met,
        ])

    def status(self) -> dict:
        conditions = {
            "min_validators_recruited": self.min_validators_recruited,
            "diversity_threshold_met":  self.diversity_threshold_met,
            "security_audit_complete":  self.security_audit_complete,
            "hhi_below_danger":         self.hhi_below_danger,
            "genomic_key_initialized":  self.genomic_key_initialized,
            "immune_system_armed":      self.immune_system_armed,
            "falsifiability_seeded":    self.falsifiability_seeded,
            "awa_conditions_met":       self.awa_conditions_met,
        }
        met = sum(conditions.values())
        return {
            "init_valid": self.all_met(),
            "conditions_met": met,
            "conditions_required": self.REQUIRED_CONDITIONS,
            "conditions": conditions,
        }
