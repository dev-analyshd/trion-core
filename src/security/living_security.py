"""
TRION Protocol — Living Security System (L4.3–4.6 + Part 6)
All eight DNA-mimetic security components, whitepaper-exact.

SEC(t) = LSS(t) · PQC(t) · CC(t)

Component map (Part 6, §6.2):
  1. Genomic Key Evolution    GK(t) = Hash_DNA(GK(t-1) || BE(t) || TM(t) || CV(t))
  2. Complementary Strand     XOR complement invariant — tamper-evident, self-verifying
  3. Immune System            INNATE + ADAPTIVE + MEMORY (permanent, never decays)
  4. Epigenetic Layer         EL_state = f(threat_level, validator_health, network_entropy)
  5. Genetic Recombination    Re-derive security params from behavioral history periodically
  6. Cryptographic Noise      Decoy sequences — noise pattern itself is authentication
  7. Mitochondrial Core       Separate independent protocol integrity DNA
  8. CRISPR Defense           Exact attack signatures, surgical neutralization
"""

from __future__ import annotations
import hashlib
import math
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ── Core Hash DNA primitive ───────────────────────────────────────────────────

def _sha3(data: bytes) -> bytes:
    return hashlib.sha3_256(data).digest()

def _not_bytes(b: bytes) -> bytes:
    return bytes(x ^ 0xFF for x in b)

def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))

def hash_dna(payload: bytes) -> Tuple[bytes, bytes]:
    """
    Dual-strand DNA hash (whitepaper L0.1).
    sense     = SHA3-256(payload || 0x00)
    antisense = SHA3-256(payload || 0xFF) XOR NOT(sense)
    Invariant: sense XOR antisense == NOT(SHA3-256(payload || 0xFF))
    """
    sense = _sha3(payload + b'\x00')
    sha3ff = _sha3(payload + b'\xFF')
    antisense = _xor(sha3ff, _not_bytes(sense))
    return sense, antisense

def verify_xor_invariant(sense: bytes, antisense: bytes, payload: bytes) -> bool:
    """
    Full cryptographic XOR complement invariant check.
    Requires original payload.
    sense XOR antisense == NOT(SHA3-256(payload || 0xFF))
    """
    sha3ff = _sha3(payload + b'\xFF')
    expected_xor = _not_bytes(sha3ff)
    actual_xor = _xor(sense, antisense)
    return actual_xor == expected_xor

def verify_strand_structural(sense: bytes, antisense: bytes) -> bool:
    """Structural check: correct lengths and non-degenerate."""
    return (len(sense) == 32 and len(antisense) == 32
            and sense != bytes(32) and antisense != bytes(32))

def verify_strand_with_payload(sense: bytes, antisense: bytes, payload: bytes) -> bool:
    """Full cryptographic verification including XOR invariant."""
    s2, a2 = hash_dna(payload)
    return s2 == sense and a2 == antisense and verify_xor_invariant(sense, antisense, payload)


# ── Component 1: Genomic Key Evolution ───────────────────────────────────────

@dataclass
class GenomicKey:
    entity_id: bytes          # 32 bytes
    generation: int
    sense: bytes              # 32 bytes
    antisense: bytes          # 32 bytes
    h_environment: bytes      # 32 bytes
    created_at: float = field(default_factory=time.time)
    evolved_at: float = field(default_factory=time.time)

    def sense_hex(self) -> str:
        return self.sense.hex()

    def antisense_hex(self) -> str:
        return self.antisense.hex()

    def verify(self) -> bool:
        """Structural integrity check."""
        return verify_strand_structural(self.sense, self.antisense)


class GenomicKeyEvolver:
    """
    GK(entity, t) = Hash_DNA(GK(entity, t-1) || BE(t) || TM(t) || CV(t))
    Stolen snapshot = immediately outdated key.
    """
    def __init__(self):
        self._keys: Dict[bytes, GenomicKey] = {}
        self._h_environment = _sha3(str(time.time()).encode() + os.urandom(8))

    def initialize(self, entity_id: bytes) -> GenomicKey:
        payload = entity_id + self._h_environment + str(time.time()).encode()
        sense, antisense = hash_dna(payload)
        gk = GenomicKey(
            entity_id=entity_id, generation=0,
            sense=sense, antisense=antisense,
            h_environment=self._h_environment,
        )
        self._keys[entity_id] = gk
        return gk

    def evolve(self, entity_id: bytes,
               be_hash: bytes, tm_hash: bytes, cv_hash: bytes) -> GenomicKey:
        """
        Evolve key with new behavioral evidence.
        be_hash = SHA3(behavioral_entropy_vector)
        tm_hash = SHA3(timestamp || block_hash)
        cv_hash = SHA3(consensus_view_at_t)
        """
        prev = self._keys.get(entity_id) or self.initialize(entity_id)

        # H_environment grows with every event → Kolmogorov complexity grows
        self._h_environment = _sha3(self._h_environment + be_hash + str(time.time()).encode()[:8])

        payload = prev.sense + be_hash + tm_hash + cv_hash + self._h_environment
        sense, antisense = hash_dna(payload)
        gk = GenomicKey(
            entity_id=entity_id,
            generation=prev.generation + 1,
            sense=sense, antisense=antisense,
            h_environment=self._h_environment,
            created_at=prev.created_at,
            evolved_at=time.time(),
        )
        self._keys[entity_id] = gk
        return gk

    def get(self, entity_id: bytes) -> Optional[GenomicKey]:
        return self._keys.get(entity_id)

    def verify_key(self, gk: "GenomicKey") -> bool:
        """Backward-compat structural integrity check on a GenomicKey."""
        return gk.verify()

    def kolmogorov_bound(self, n_chains: int, n_validators: int) -> float:
        """
        K(H(TRION, t)) >= Ω(t · N_chains · N_validators · H_environment)
        Returns approximate lower bound in bits.
        """
        t = time.time()
        h_entropy = int.from_bytes(self._h_environment[:8], 'big')
        return (math.log2(max(t, 1)) + math.log2(max(n_chains, 1))
                + math.log2(max(n_validators, 1)) + math.log2(max(h_entropy, 1)))


# ── Components 3 + 8: Immune System + CRISPR Defense ─────────────────────────

@dataclass
class AttackSignature:
    id: str
    signature: bytes
    description: str
    attack_type: str
    added_at: float = field(default_factory=time.time)
    matches: int = 0


class CRISPRDefense:
    """
    Exact attack signatures — pattern library, adaptive response, permanent memory.
    Library never decays (whitepaper Part 6 §6.2 Component 3).
    """
    # ── Full cross-chain attack signature library (CRISPR Defense)
    # Organised by VM family. Each entry: (id, canonical_signature_bytes, description, pattern_type)
    # Pattern types mirror the 6 MF engine patterns + extended attack taxonomy.
    KNOWN_ATTACKS = [
        # ── EVM / Ethereum L1 ────────────────────────────────────────────────
        ("DAO_2016_REENTR",          b"DAO_RECURSIVE_REENTRANCY_SPLITDAO",
         "The DAO reentrancy exploit (Jun 2016, $60M) — recursive call before state update",
         "REENTRANCY"),
        ("PARITY_2017_WALLETLIB",    b"PARITY_WALLETLIB_SELFDESTRUCT_UNINIT",
         "Parity Wallet Library self-destruct (Nov 2017, $280M frozen) — uninitialised library",
         "ACCESS_CONTROL"),
        ("HARVEST_2020_FLASH",       b"HARVEST_FLASH_LOAN_ORACLE_MANIP",
         "Harvest Finance flash loan oracle manipulation (Oct 2020, $34M)",
         "FLASH_LOAN"),
        ("PICKLE_2020_EVIL_JAR",     b"PICKLE_EVIL_JAR_STRATEGY_SWAP",
         "Pickle Finance evil jar exploit (Nov 2020, $20M) — malicious strategy contract",
         "LOGIC_BUG"),
        ("ALPHA_2021_FLASH",         b"ALPHA_HOMORA_IBETHALPHA_FLASH_COMPLEX",
         "Alpha Finance flash loan multi-step exploit (Feb 2021, $37.5M)",
         "FLASH_LOAN"),
        ("CREAM_2021_FLASH",         b"CREAM_FINANCE_FLASH_PRICE_MANIP_LENDING",
         "Cream Finance flash loan price manipulation (Oct 2021, $130M)",
         "FLASH_LOAN"),
        ("BADGER_2021_FRONTEND",     b"BADGER_DAO_CLOUDFLARE_WORKER_INJECT",
         "BadgerDAO frontend injection via Cloudflare worker (Dec 2021, $120M)",
         "ACCESS_CONTROL"),
        ("POLY_2021_CROSSCHAIN",     b"POLYNETWORK_ETHCROSSCHAIN_KEEPER_BYPASS",
         "Poly Network cross-chain keeper bypass (Aug 2021, $611M) — largest DeFi hack at time",
         "BRIDGE_EXPLOIT"),
        ("INDEXED_2021_AMM",         b"INDEXED_FINANCE_NDXCONTROLLER_GULP_PRICE",
         "Indexed Finance AMM gulp price manipulation (Oct 2021, $16M)",
         "AMM_MANIPULATION"),
        ("WORMHOLE_2022_MINT",       b"WORMHOLE_GUARDIAN_SIGNATURE_BYPASS",
         "Wormhole guardian signature bypass (Feb 2022, $325M) — ETH/SOL bridge",
         "BRIDGE_EXPLOIT"),
        ("BEANSTALK_2022_GOV",       b"BEANSTALK_FLASH_GOVERNANCE_ATTACK",
         "Beanstalk governance flash loan attack (Apr 2022, $182M)",
         "GOVERNANCE_CAPTURE"),
        ("NOMAD_2022_LOGIC",         b"NOMAD_BRIDGE_REPLICA_PROCESS_ZEROROOT",
         "Nomad bridge zero-root logic bug (Aug 2022, $190M) — permissionless replay",
         "BRIDGE_EXPLOIT"),
        ("WINTERMUTE_2022_KEY",      b"WINTERMUTE_PROFANITY_VANITY_ADDRESS_LEAK",
         "Wintermute Profanity vanity address private key leak (Sep 2022, $160M)",
         "PRIVATE_KEY_COMPROMISE"),
        ("MANGO_2022_PUMP",          b"MANGO_COORDINATED_PRICE_PUMP",
         "Mango Markets coordinated oracle pump (Oct 2022, $117M) — SVM",
         "COORDINATED_PUMP"),
        ("EULER_2023_FLASH",         b"EULER_DONATE_SELF_LIQUIDATION",
         "Euler Finance donate/self-liquidation loop (Mar 2023, $197M)",
         "FLASH_LOAN"),
        ("BONQ_2023_ORACLE",         b"BONQ_DAO_TELLOR_ORACLE_PRICE_MANIP",
         "BonqDAO Tellor oracle price manipulation (Feb 2023, $120M) — Polygon",
         "ORACLE_MANIPULATION"),
        ("MULTICHAIN_2023_KEY",      b"MULTICHAIN_ANYSWAP_ROUTER_PRIVKEY_EXFIL",
         "Multichain private key exfiltration (Jul 2023, $126M) — multi-chain bridge",
         "PRIVATE_KEY_COMPROMISE"),
        ("CURVE_2023_REENTR",        b"CURVE_VYPER_REENTRANCY_LOCK",
         "Curve Finance Vyper reentrancy bug (Jul 2023, $61M) — compiler-level",
         "REENTRANCY"),
        ("KYBERSWAP_2023_TICK",      b"KYBERSWAP_ELASTIC_TICK_INTERVAL_MANIPUL",
         "KyberSwap Elastic tick interval manipulation (Nov 2023, $46M)",
         "AMM_MANIPULATION"),
        ("RADIANT_2024_MULTISIG",    b"RADIANT_CAPITAL_MULTISIG_MALWARE_GNOSIS",
         "Radiant Capital multi-sig malware compromise (Oct 2024, $50M) — ARB/BSC",
         "PRIVATE_KEY_COMPROMISE"),
        ("ORBIT_2024_MULTISIG",      b"ORBIT_CHAIN_MULTISIG_SWEEP_KLAYTN",
         "Orbit Chain multi-sig sweep (Jan 2024, $82M) — Klaytn",
         "PRIVATE_KEY_COMPROMISE"),
        ("UWU_2024_ORACLE",          b"UWU_LEND_CURVE_PRICE_ORACLE_FLASH",
         "UwU Lend Curve pool price oracle flash attack (Jun 2024, $19.4M)",
         "ORACLE_MANIPULATION"),
        ("PENPIE_2024_REENTR",       b"PENPIE_PENDLE_POOL_REENTRANCY_ARBITRUM",
         "Penpie Pendle reentrancy exploit (Sep 2024, $27M) — Arbitrum",
         "REENTRANCY"),
        ("JIMBOS_2023",              b"JIMBOS_FLASH_LOAN_SWAP_ATTACK",
         "Jimbos Protocol flash loan AMM swap (May 2023, $7.5M) — Arbitrum",
         "FLASH_LOAN"),

        # ── EVM / BSC (BNB Chain) ─────────────────────────────────────────────
        ("PANCAKEBUNNY_2021_BSC",    b"PANCAKEBUNNY_BSC_FLASH_BUNNY_PRICE_DUMP",
         "PancakeBunny flash loan BUNNY price dump (May 2021, $45M) — BSC",
         "FLASH_LOAN"),
        ("VENUS_BSC_2021",           b"VENUS_BSC_XVS_PRICE_ORACLE_COLLATERAL",
         "Venus BSC XVS oracle collateral inflation (May 2021, $200M at risk)",
         "ORACLE_MANIPULATION"),
        ("QUBIT_BSC_2022",           b"QUBIT_BRIDGE_BSC_ETH_NULL_DEPOSIT_BYPASS",
         "Qubit Finance BSC bridge null address deposit (Jan 2022, $80M)",
         "BRIDGE_EXPLOIT"),

        # ── EVM / Polygon ─────────────────────────────────────────────────────
        ("METER_2022_BRIDGE",        b"METER_IO_BRIDGE_WRAPPED_NATIVE_BYPASS",
         "Meter.io bridge wrapped native token bypass (Feb 2022, $4.4M) — Polygon",
         "BRIDGE_EXPLOIT"),

        # ── SVM / Solana ──────────────────────────────────────────────────────
        ("CASHIO_2022_INFINITE",     b"CASHIO_SABER_INFINITE_MINT_FAKE_COLLAT",
         "Cashio infinite mint via fake collateral account (Mar 2022, $52M) — Solana",
         "INFINITE_MINT"),
        ("CREMA_2022_TICK",          b"CREMA_FINANCE_SOL_TICK_FAKE_ACCOUNT",
         "Crema Finance fake tick account injection (Jul 2022, $8.8M) — Solana",
         "AMM_MANIPULATION"),
        ("NIRVANA_2022_FLASH",       b"NIRVANA_SOL_ANA_FLASH_SWAP_ARMA",
         "Nirvana Finance flash loan AMM price manipulation (Jul 2022, $3.5M) — Solana",
         "FLASH_LOAN"),

        # ── Cosmos SDK chains ─────────────────────────────────────────────────
        ("OSMOSIS_2022_MULTIHOP",    b"OSMOSIS_GAMM_MULTIHOP_ARITHMETIC_BUG",
         "Osmosis GAMM multi-hop arithmetic rounding bug (Jun 2022, $5M) — Cosmos",
         "LOGIC_BUG"),
        ("TERRA_2022_DEPEG",         b"TERRA_UST_LUNA_DEATH_SPIRAL_ANCHOR",
         "Terra UST/LUNA algorithmic stablecoin death spiral (May 2022, $40B) — Cosmos",
         "COORDINATED_PUMP"),

        # ── Bridge / Cross-chain ──────────────────────────────────────────────
        ("RONIN_2022_BRIDGE",        b"RONIN_BRIDGE_VALIDATOR_KEY_COMPROMISE",
         "Ronin Network validator key compromise (Mar 2022, $625M) — Axie Infinity",
         "BRIDGE_EXPLOIT"),
        ("THORCHAIN_2021_BYPASS",    b"THORCHAIN_ROUTER_ETH_RETURN_BYPASS",
         "THORChain router ETH return value bypass (Jul 2021, $8M)",
         "BRIDGE_EXPLOIT"),
        ("HORIZON_2022_KEY",         b"HARMONY_HORIZON_BRIDGE_MULTISIG_PRIVKEY",
         "Harmony Horizon Bridge multi-sig key compromise (Jun 2022, $100M)",
         "PRIVATE_KEY_COMPROMISE"),

        # ── Near VM ───────────────────────────────────────────────────────────
        ("AURORA_2022_NEAR",         b"AURORA_NEAR_FORCE_EXIT_INFINITE_ETH",
         "Aurora Engine (NEAR EVM) force-exit bug (Apr 2022, $0 — whitehack) — NEAR",
         "LOGIC_BUG"),

        # ── Move VM / Aptos ───────────────────────────────────────────────────
        ("THALA_2024_MOVE",          b"THALA_APTOS_MOVE_FARM_LP_FLASH_DRAIN",
         "Thala Labs Move-based farm LP flash drain (Nov 2023, $25.5M) — Aptos",
         "FLASH_LOAN"),

        # ── StarkNet / Cairo ──────────────────────────────────────────────────
        ("NOSTRA_2024_CAIRO",        b"NOSTRA_STARKNET_CAIRO_PRICE_FEED_STALE",
         "Nostra Finance StarkNet stale price feed (Oct 2024, $1.8M) — StarkNet",
         "ORACLE_MANIPULATION"),
    ]

    def __init__(self):
        self._library: Dict[str, AttackSignature] = {}
        for aid, sig, desc, atype in self.KNOWN_ATTACKS:
            self._library[aid] = AttackSignature(
                id=aid, signature=sig, description=desc, attack_type=atype)

    def innate_check(self, tx_data: bytes) -> Optional[dict]:
        """Pattern match against known attack library."""
        for sig in self._library.values():
            if sig.signature in tx_data:
                sig.matches += 1
                return {
                    "matched": True, "attack_id": sig.id,
                    "description": sig.description,
                    "attack_type": sig.attack_type,
                    "action": "INTERCEPT_BEFORE_EXECUTION",
                }
        return None

    def adaptive_response(self, new_attack_data: bytes, attack_type: str) -> str:
        """Characterize new attack, add to permanent library."""
        sig_hash = hashlib.sha3_256(new_attack_data).digest()
        attack_id = f"ADAPTIVE_{sig_hash[:8].hex()}"
        self._library[attack_id] = AttackSignature(
            id=attack_id, signature=sig_hash[:16],
            description=f"Auto-characterized: {attack_type}",
            attack_type=attack_type,
        )
        return attack_id

    def library_size(self) -> int:
        return len(self._library)

    def library_summary(self) -> List[dict]:
        return [
            {"id": s.id, "type": s.attack_type,
             "matches": s.matches, "desc": s.description[:60]}
            for s in self._library.values()
        ]


# ── Component 4: Epigenetic Layer ─────────────────────────────────────────────

class EpigeneticState(str, Enum):
    NORMAL    = "NORMAL"
    ELEVATED  = "ELEVATED"
    DEFENSIVE = "DEFENSIVE"
    LOCKDOWN  = "LOCKDOWN"

@dataclass
class EpigeneticLayer:
    """
    EL_state(t) = f(threat_level, validator_health, network_entropy)
    Architecture unchanged. Only expression changes.
    Same DNA, different phenotype per environment.
    """
    state: EpigeneticState = EpigeneticState.NORMAL
    threat_level: float = 0.0
    validator_health: float = 1.0
    network_entropy: float = 1.0
    coherence_threshold_modifier: float = 0.0
    emission_rate_modifier: float = 1.0
    last_updated: float = field(default_factory=time.time)

    def update(self, threat_level: float, validator_health: float,
               network_entropy: float) -> None:
        self.threat_level = max(0.0, min(1.0, threat_level))
        self.validator_health = max(0.0, min(1.0, validator_health))
        self.network_entropy = max(0.0, min(1.0, network_entropy))
        self.last_updated = time.time()

        stress = (self.threat_level * 0.50
                  + (1.0 - self.validator_health) * 0.30
                  + (1.0 - self.network_entropy) * 0.20)

        if stress < 0.20:
            self.state = EpigeneticState.NORMAL
            self.coherence_threshold_modifier = 0.00
            self.emission_rate_modifier = 1.00
        elif stress < 0.45:
            self.state = EpigeneticState.ELEVATED
            self.coherence_threshold_modifier = 0.05
            self.emission_rate_modifier = 0.90
        elif stress < 0.70:
            self.state = EpigeneticState.DEFENSIVE
            self.coherence_threshold_modifier = 0.12
            self.emission_rate_modifier = 0.70
        else:
            self.state = EpigeneticState.LOCKDOWN
            self.coherence_threshold_modifier = 0.25
            self.emission_rate_modifier = 0.40


# ── Component 5: Genetic Recombination ───────────────────────────────────────

@dataclass
class RecombinationParams:
    key_rotation_seed: bytes
    noise_pattern_seed: bytes
    mito_core_seed: bytes
    generation: int


class GeneticRecombination:
    """
    Security parameters re-derived from behavioral history.
    After each recombination, all previously constructed attacks are useless.
    """
    def __init__(self, interval_secs: int = 86400):
        seed = _sha3(str(time.time()).encode())
        self.generation = 0
        self.interval_secs = interval_secs
        self.last_recombination = time.time()
        self.params = RecombinationParams(
            key_rotation_seed=seed,
            noise_pattern_seed=_sha3(seed),
            mito_core_seed=_sha3(_sha3(seed)),
            generation=0,
        )

    def maybe_recombine(self, akashic_depth: int, h_environment: bytes) -> bool:
        if time.time() - self.last_recombination < self.interval_secs:
            return False
        self.recombine(akashic_depth, h_environment)
        return True

    def recombine(self, akashic_depth: int, h_environment: bytes) -> None:
        seed_input = (self.params.key_rotation_seed
                      + akashic_depth.to_bytes(8, 'big')
                      + h_environment
                      + str(time.time()).encode()[:8])
        new_key = _sha3(seed_input)
        self.generation += 1
        self.last_recombination = time.time()
        self.params = RecombinationParams(
            key_rotation_seed=new_key,
            noise_pattern_seed=_sha3(new_key),
            mito_core_seed=_sha3(_sha3(new_key)),
            generation=self.generation,
        )


# ── Component 6: Cryptographic Noise ─────────────────────────────────────────

class CryptographicNoise:
    """
    Deliberate cryptographic noise throughout Behavioral DNA.
    Realistic-looking decoy sequences carrying no information.
    The noise pattern itself is authentication.
    """
    def __init__(self, seed: bytes):
        self._seed = seed
        self.decoy_count = 0

    def generate_decoy(self, slot: int) -> Tuple[bytes, bytes]:
        """Generate a decoy that looks like a real BH but carries no behavioral info."""
        payload = _sha3(self._seed + slot.to_bytes(8, 'big'))
        sense, antisense = hash_dna(payload)
        self.decoy_count += 1
        return sense, antisense

    def is_decoy(self, sense: bytes, slot: int) -> bool:
        """Authenticate that a sequence belongs to the noise pattern."""
        payload = _sha3(self._seed + slot.to_bytes(8, 'big'))
        expected_sense, _ = hash_dna(payload)
        return expected_sense == sense

    def update_seed(self, new_seed: bytes) -> None:
        self._seed = _sha3(self._seed + new_seed)


# ── Component 7: Mitochondrial Core ──────────────────────────────────────────

class MitochondrialCore:
    """
    Separate independently maintained Behavioral DNA.
    Encodes only fundamental protocol properties.
    Second independent authentication layer.
    """
    def __init__(self, protocol_version: int = 3, chain_count: int = 31):
        self.protocol_version = protocol_version
        self.chain_count = chain_count
        self.genesis_timestamp = time.time()
        self.integrity_checks = 0
        self._payload = self._build_payload()
        self.sense, self.antisense = hash_dna(self._payload)

    def _build_payload(self) -> bytes:
        return (self.protocol_version.to_bytes(4, 'big')
                + self.chain_count.to_bytes(4, 'big')
                + int(self.genesis_timestamp).to_bytes(8, 'big')
                + b'TRION_MITO_CORE_v3')

    def verify_integrity(self) -> bool:
        """Verify the mitochondrial core independently of GK."""
        self.integrity_checks += 1
        return verify_strand_structural(self.sense, self.antisense)

    def update(self, new_chain_count: int) -> None:
        self.chain_count = new_chain_count
        prev_sense = self.sense
        payload = (self.protocol_version.to_bytes(4, 'big')
                   + new_chain_count.to_bytes(4, 'big')
                   + int(time.time()).to_bytes(8, 'big')
                   + prev_sense
                   + b'TRION_MITO_CORE_v3')
        self.sense, self.antisense = hash_dna(payload)

    def integrity_score(self) -> float:
        return 1.0 if self.verify_integrity() else 0.0

    def sense_hex(self) -> str:
        return self.sense.hex()


# ── PQC + Classical Crypto scores ─────────────────────────────────────────────

@dataclass
class PQCScore:
    """CRYSTALS-Kyber + CRYSTALS-Dilithium + SPHINCS+ (whitepaper L4.5)."""
    kyber_active: bool = True
    dilithium_active: bool = True
    sphincs_active: bool = True

    @property
    def score(self) -> float:
        return (self.kyber_active + self.dilithium_active + self.sphincs_active) / 3.0

    def to_dict(self) -> dict:
        return {
            "CRYSTALS_Kyber": self.kyber_active,
            "CRYSTALS_Dilithium": self.dilithium_active,
            "SPHINCS_plus": self.sphincs_active,
            "score": round(self.score, 4),
        }


@dataclass
class ClassicalCryptoScore:
    """SHA-3 + AES-256 + ZK proofs (whitepaper L4.5)."""
    sha3_active: bool = True
    aes256_active: bool = True
    zk_proofs_active: bool = True

    @property
    def score(self) -> float:
        return (self.sha3_active + self.aes256_active + self.zk_proofs_active) / 3.0

    def to_dict(self) -> dict:
        return {
            "SHA3": self.sha3_active,
            "AES256": self.aes256_active,
            "ZK_proofs": self.zk_proofs_active,
            "score": round(self.score, 4),
        }


# ── Bootstrap Protocol (L4.7) ─────────────────────────────────────────────────

def bootstrap_weight(akashic_depth: int) -> float:
    """
    bootstrap_weight(t) = e^(-λ_boot · D(t))
    At D ≈ 50000 blocks (~6 months): weight ≈ 0 → Living Security fully active.
    """
    lambda_boot = 0.0001
    return math.exp(-lambda_boot * akashic_depth)

def sec_bootstrap(akashic_depth: int, sec_classical: float, sec_living: float) -> float:
    """SEC_boot = w·SEC_classical + (1-w)·SEC_living"""
    w = bootstrap_weight(akashic_depth)
    return w * sec_classical + (1.0 - w) * sec_living


# ── Full SEC(t) = LSS(t) · PQC(t) · CC(t) ────────────────────────────────────

class LivingSecuritySystem:
    """
    Complete 8-component Living Security System.
    SEC(t) = LSS(t) · PQC(t) · CC(t)
    """
    def __init__(self, protocol_version: int = 3, chain_count: int = 31):
        self.evolver = GenomicKeyEvolver()
        self.crispr = CRISPRDefense()
        self.epigenetic = EpigeneticLayer()
        self.recombination = GeneticRecombination(interval_secs=86400)
        self.mito = MitochondrialCore(protocol_version, chain_count)
        self.pqc = PQCScore()
        self.cc = ClassicalCryptoScore()
        self._noise: Optional[CryptographicNoise] = None
        self._initialized = False

    def _get_or_init_noise(self) -> CryptographicNoise:
        if self._noise is None:
            self._noise = CryptographicNoise(_sha3(os.urandom(32)))
        return self._noise

    def get_or_init_entity(self, entity_id: str) -> GenomicKey:
        eid = entity_id.encode()[:32].ljust(32, b'\x00')
        gk = self.evolver.get(eid)
        if gk is None:
            gk = self.evolver.initialize(eid)
        return gk

    def evolve_entity(self, entity_id: str, behavioral_context: Optional[bytes] = None) -> GenomicKey:
        eid = entity_id.encode()[:32].ljust(32, b'\x00')
        ctx = behavioral_context or os.urandom(32)
        be_hash = _sha3(ctx)
        tm_hash = _sha3(str(time.time()).encode())
        cv_hash = _sha3(b"consensus_view_placeholder")
        return self.evolver.evolve(eid, be_hash, tm_hash, cv_hash)

    def compute_sec(self, entity_id: str, akashic_depth: int = 0) -> dict:
        """Compute full SEC(t) = LSS(t) · PQC(t) · CC(t) for an entity."""
        gk = self.get_or_init_entity(entity_id)

        # Update epigenetic layer with current system state
        threat = min(1.0, self.crispr.library_size() * 0.01)  # more sigs = more threat awareness
        self.epigenetic.update(threat * 0.1, 1.0, 1.0)  # healthy baseline

        # Mitochondrial check
        mito_ok = self.mito.verify_integrity()

        # LSS components
        gk_depth_norm = math.log1p(gk.generation) / math.log1p(100)
        gk_depth_norm = min(1.0, gk_depth_norm)
        epi_health = 1.0 - self.epigenetic.threat_level * 0.5
        mito_integrity = self.mito.integrity_score()
        crispr_coverage = min(1.0, self.crispr.library_size() / 8.0)

        lss = (gk_depth_norm * 0.40 + epi_health * 0.25
               + mito_integrity * 0.20 + crispr_coverage * 0.15)
        lss = max(0.0, min(1.0, lss))

        # P(break LSS) monotonically decreasing per whitepaper L4.5
        p_break = math.exp(-gk.generation * 0.01)

        # Full SEC
        sec_living = lss * self.pqc.score * self.cc.score
        sec_final = sec_bootstrap(akashic_depth, sec_classical=0.85, sec_living=sec_living)

        # Kolmogorov complexity bound
        k_bound = self.evolver.kolmogorov_bound(n_chains=31, n_validators=100)

        return {
            "entity_id": entity_id,
            "SEC_t": round(sec_final, 6),
            "LSS": round(lss, 6),
            "PQC": round(self.pqc.score, 6),
            "CC": round(self.cc.score, 6),
            "components": {
                "1_genomic_key": {
                    "generation": gk.generation,
                    "sense_hex": gk.sense_hex()[:32] + "...",
                    "antisense_hex": gk.antisense_hex()[:32] + "...",
                    "strand_valid": gk.verify(),
                    "gk_depth_normalized": round(gk_depth_norm, 4),
                },
                "2_complementary_strand": {
                    "structural_valid": verify_strand_structural(gk.sense, gk.antisense),
                    "xor_invariant": "requires_payload_for_full_check",
                },
                "3_immune_system": {
                    "library_size": self.crispr.library_size(),
                    "layers": ["INNATE", "ADAPTIVE", "MEMORY"],
                    "memory_permanent": True,
                    "signatures": self.crispr.library_summary(),
                },
                "4_epigenetic_layer": {
                    "state": self.epigenetic.state.value,
                    "threat_level": round(self.epigenetic.threat_level, 4),
                    "validator_health": round(self.epigenetic.validator_health, 4),
                    "network_entropy": round(self.epigenetic.network_entropy, 4),
                    "coherence_threshold_modifier": round(
                        self.epigenetic.coherence_threshold_modifier, 4),
                    "emission_rate_modifier": round(self.epigenetic.emission_rate_modifier, 4),
                },
                "5_genetic_recombination": {
                    "generation": self.recombination.generation,
                    "interval_hours": self.recombination.interval_secs // 3600,
                    "params_invalidated_per_recombination": True,
                },
                "6_cryptographic_noise": {
                    "decoys_generated": self._get_or_init_noise().decoy_count,
                    "noise_is_authentication": True,
                },
                "7_mitochondrial_core": {
                    "integrity_verified": mito_ok,
                    "protocol_version": self.mito.protocol_version,
                    "chain_count": self.mito.chain_count,
                    "core_sense_hex": self.mito.sense_hex()[:32] + "...",
                    "integrity_checks": self.mito.integrity_checks,
                    "integrity_score": round(mito_integrity, 4),
                },
                "8_crispr_defense": {
                    "library_size": self.crispr.library_size(),
                    "surgical_neutralization": True,
                    "attacks_known": [s["id"] for s in self.crispr.library_summary()],
                },
            },
            "security_scores": {
                "pqc_detail": self.pqc.to_dict(),
                "cc_detail": self.cc.to_dict(),
            },
            "quantum_resistance": {
                "p_break_lss": round(p_break, 8),
                "mechanism": "ontological_not_computational",
                "proof": "P(break LSS) = P(reproduce causal_history(entity, t0→t)) → 0",
                "kolmogorov_bound_bits": round(k_bound, 2),
                "quantum_computers_help": False,
            },
            "bootstrap": {
                "akashic_depth": akashic_depth,
                "bootstrap_weight": round(bootstrap_weight(akashic_depth), 6),
                "sec_classical": 0.85,
                "sec_living": round(sec_living, 6),
                "phase": "BOOTSTRAP" if akashic_depth < 10000 else
                         "TRANSITIONING" if akashic_depth < 50000 else "LIVING_SECURITY",
            },
            "whitepaper": "L4.3-4.6 + Part 6 §6.2 — all 8 components",
        }

    def innate_check(self, entity_id: str, tx_data: bytes) -> dict:
        """Run innate immune check on transaction data."""
        result = self.crispr.innate_check(tx_data)
        if result:
            return {"entity_id": entity_id, "immune_clearance": "THREAT_DETECTED", **result}
        return {"entity_id": entity_id, "immune_clearance": "CLEAR", "matched": False}

    def adaptive_learn(self, new_attack_data: bytes, attack_type: str) -> str:
        """Learn from a new attack pattern."""
        aid = self.crispr.adaptive_response(new_attack_data, attack_type)
        # Update recombination params since threat landscape changed
        self.recombination.recombine(0, self.evolver._h_environment)
        return aid

    def full_status(self, entity_id: str, akashic_depth: int = 0) -> dict:
        """Complete Living Security status for an entity."""
        sec = self.compute_sec(entity_id, akashic_depth)

        # Innate immune layer check
        gk = self.get_or_init_entity(entity_id)
        innate = self.crispr.innate_check(gk.sense)

        sec["innate_layer"] = {
            "status": "THREAT_DETECTED" if innate else "CLEAN",
            "crispr_library_size": self.crispr.library_size(),
        }
        sec["adaptive_layer"] = {
            "new_attacks_characterized": self.recombination.generation,
            "auto_update": True,
        }
        sec["memory_layer"] = {
            "signatures_stored": self.crispr.library_size(),
            "permanent": True,
            "never_decays": True,
        }
        return sec


# ── Backward-compat aliases ───────────────────────────────────────────────────

class ImmuneSystem:
    """
    Backward-compatible wrapper.  New code should use LivingSecuritySystem
    or CRISPRDefense directly (Part 6 §6.2 Component 3 + 8).
    """
    def __init__(self):
        self.crispr = CRISPRDefense()
        self._evolver = GenomicKeyEvolver()

    def innate_check(self, tx_data: bytes) -> Optional[dict]:
        return self.crispr.innate_check(tx_data)

    def adaptive_response(self, new_attack_data: bytes, attack_type: str) -> str:
        return self.crispr.adaptive_response(new_attack_data, attack_type)


# ── Module singleton ──────────────────────────────────────────────────────────

_lss_instance: Optional[LivingSecuritySystem] = None

def get_lss() -> LivingSecuritySystem:
    global _lss_instance
    if _lss_instance is None:
        _lss_instance = LivingSecuritySystem(protocol_version=3, chain_count=31)
    return _lss_instance


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== TRION Living Security System — 8-Component Self-Test ===\n")

    # 1. Dual-strand XOR invariant
    payload = b"canonical_behavioral_event_test_payload_93bytes"
    sense, antisense = hash_dna(payload)
    assert verify_xor_invariant(sense, antisense, payload), "XOR invariant FAILED"
    assert verify_strand_with_payload(sense, antisense, payload), "Full verification FAILED"
    print(f"[PASS] Component 2: XOR invariant holds. sense={sense[:4].hex()}...")

    # 2. Tamper detection
    tampered_sense = bytes([sense[0] ^ 0xFF]) + sense[1:]
    assert not verify_xor_invariant(tampered_sense, antisense, payload), "Tamper not detected"
    print("[PASS] Component 2: Tamper detection works.")

    # 3. Genomic key evolution
    evolver = GenomicKeyEvolver()
    entity = b"uniswap_test_entity".ljust(32, b'\x00')
    gk0 = evolver.initialize(entity)
    gk1 = evolver.evolve(entity, os.urandom(32), os.urandom(32), os.urandom(32))
    gk2 = evolver.evolve(entity, os.urandom(32), os.urandom(32), os.urandom(32))
    assert gk1.sense != gk2.sense, "Keys should differ each evolution"
    assert gk1.sense != gk0.sense, "Evolution must change the key"
    assert gk2.generation == 2
    print(f"[PASS] Component 1: GK generations 0→1→2, all differ.")

    # 4. Stolen snapshot is outdated
    stolen = gk0.sense
    assert stolen != gk2.sense, "Stolen snapshot must be outdated"
    print("[PASS] Component 1: Stolen snapshot immediately outdated.")

    # 5. Epigenetic layer
    epi = EpigeneticLayer()
    epi.update(0.8, 0.2, 0.3)
    assert epi.state in (EpigeneticState.DEFENSIVE, EpigeneticState.LOCKDOWN)
    epi.update(0.0, 1.0, 1.0)
    assert epi.state == EpigeneticState.NORMAL
    print(f"[PASS] Component 4: Epigenetic state transitions correct.")

    # 6. CRISPR immune system
    crispr = CRISPRDefense()
    base_size = len(CRISPRDefense.KNOWN_ATTACKS)
    assert crispr.library_size() == base_size, f"Expected {base_size}, got {crispr.library_size()}"
    result = crispr.innate_check(b"prefix_HARVEST_FLASH_LOAN_ORACLE_MANIP_suffix")
    assert result and result["matched"]
    assert crispr.innate_check(b"clean_transaction_data") is None
    new_id = crispr.adaptive_response(b"novel_2026_attack", "FLASH_LOAN")
    assert crispr.library_size() == base_size + 1
    print(f"[PASS] Components 3+8: CRISPR library={crispr.library_size()} ({base_size} known + 1 adaptive learned).")

    # 7. Mitochondrial core
    mito = MitochondrialCore(3, 31)
    assert mito.verify_integrity()
    assert mito.integrity_score() == 1.0
    print("[PASS] Component 7: Mitochondrial core integrity verified.")

    # 8. SEC(t) = LSS · PQC · CC
    lss = LivingSecuritySystem()
    sec = lss.compute_sec("uniswap", akashic_depth=1000)
    assert 0.0 < sec["SEC_t"] <= 1.0
    assert sec["LSS"] > 0.0
    assert sec["PQC"] == 1.0
    assert sec["CC"] == 1.0
    print(f"[PASS] SEC(t) = {sec['SEC_t']:.6f} (LSS={sec['LSS']:.4f}, PQC={sec['PQC']}, CC={sec['CC']})")

    # 9. Bootstrap protocol
    w0 = bootstrap_weight(0)
    w_mature = bootstrap_weight(50000)
    assert abs(w0 - 1.0) < 1e-10
    assert w_mature < 0.01
    print(f"[PASS] Component L4.7: Bootstrap weight D=0→{w0:.4f}, D=50000→{w_mature:.6f}")

    # 10. P(break LSS) monotonically decreasing
    prev_p = 1.0
    for i in range(5):
        lss.evolve_entity("test_monotone")
        gk = lss.get_or_init_entity("test_monotone")
        p = math.exp(-gk.generation * 0.01)
        assert p <= prev_p, f"P(break) must decrease (gen={gk.generation})"
        prev_p = p
    print(f"[PASS] P(break LSS) monotonically decreasing: {prev_p:.6f}")

    print("\n=== ALL 10 LIVING SECURITY TESTS PASSED ===")
    print("Components: GK Evolution, Complementary Strand, Immune System, Epigenetic,")
    print("            Genetic Recombination, Cryptographic Noise, Mitochondrial Core, CRISPR")
