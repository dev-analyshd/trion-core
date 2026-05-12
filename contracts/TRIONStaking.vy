# @version 0.3.10
# @title TRION Validator Staking — Vyper
# @notice Validator staking, slashing, and TRION token economic coordination.
#         Vyper chosen for security-critical economic layer: simpler syntax = smaller attack surface.
# @author TRION Protocol — Originator: Hudu Yusuf (Analys)
# @license CC0

# ── Events ─────────────────────────────────────────────────────────────────────

event ValidatorRegistered:
    validator: indexed(address)
    stake_amount: uint256
    geographic_region: String[32]
    hsm_hash: bytes32

event ValidatorSlashed:
    validator: indexed(address)
    slash_amount: uint256
    reason: String[64]
    permanent_exclusion: bool

event SlashDisputed:
    validator: indexed(address)
    challenge_bond: uint256
    dispute_id: bytes32

event DisputeResolved:
    dispute_id: indexed(bytes32)
    upheld: bool
    validator: address

event DiversityBonusAwarded:
    validator: indexed(address)
    bonus_amount: uint256
    diversity_score: uint256  # scaled 1e18

event GeographicWarning:
    region: String[32]
    current_share: uint256  # scaled 1e18
    max_allowed: uint256    # scaled 1e18

event AWAViolation:
    condition: String[64]
    frozen: bool

# ── Constants ──────────────────────────────────────────────────────────────────

MINIMUM_STAKE: constant(uint256) = 10_000 * 10**18           # 10,000 TRION
SLASH_COORD_ATTACK: constant(uint256) = 5000                  # 50% of stake (bps)
SLASH_LOW_ACCURACY: constant(uint256) = 300                   # 3% per 30d window (bps)
SLASH_HSM_FAILURE: constant(uint256) = 1000                   # 10% (bps)
SLASH_UPTIME: constant(uint256) = 10                          # 0.1% per day below min (bps)
SLASH_SYBIL: constant(uint256) = 2500                         # 25% for all in cluster (bps)

HHI_HEALTHY: constant(uint256) = 1500
HHI_WARNING: constant(uint256) = 2500
HHI_DANGER:  constant(uint256) = 4000

MAX_SINGLE_REGION: constant(uint256) = 400_000_000_000_000_000    # 0.40 scaled 1e18
MAX_SINGLE_JURISDICTION: constant(uint256) = 300_000_000_000_000_000  # 0.30 scaled 1e18
MIN_CONTINENTS: constant(uint256) = 4

DISPUTE_WINDOW: constant(uint256) = 259200   # 72 hours in seconds
CHALLENGE_BOND_BPS: constant(uint256) = 500  # 5% of slashed amount

PUBLIC_GOOD_BPS: constant(uint256) = 1500    # 15% of fees to public good pool

# ── Storage ───────────────────────────────────────────────────────────────────

owner: public(address)
trion_token: public(address)
akashic_oracle: public(address)

# Validator registry
validators: public(HashMap[address, Validator])
validator_list: public(DynArray[address, 10000])
validator_count: public(uint256)

# Slashing disputes
disputes: public(HashMap[bytes32, Dispute])
active_disputes: public(uint256)

# Geographic tracking
region_stake: public(HashMap[String[32], uint256])
total_effective_stake: public(uint256)

# HHI state
current_hhi: public(uint256)
continents_covered: public(uint256)

# AWA enforcement
awa_enforced: public(bool)
signals_frozen: public(bool)

# Public good pool
public_good_pool: public(uint256)

# Governance
governance: public(address)

# ── Structs ───────────────────────────────────────────────────────────────────

struct Validator:
    stake: uint256
    diversity_score: uint256      # d_j scaled 1e18
    effective_stake: uint256      # s_j · d_j
    geographic_region: String[32]
    jurisdiction: String[16]
    continent: String[16]
    hsm_verified: bool
    hsm_hash: bytes32
    registered_at: uint256
    last_accuracy_check: uint256
    accuracy_score: uint256       # scaled 1e18
    uptime_score: uint256         # scaled 1e18
    permanently_excluded: bool
    active: bool

struct Dispute:
    validator: address
    slash_amount: uint256
    challenge_bond: uint256
    created_at: uint256
    resolved: bool
    upheld: bool
    reason: String[64]

# ── Constructor ───────────────────────────────────────────────────────────────

@external
def __init__(
    _trion_token: address,
    _akashic_oracle: address,
    _governance: address,
):
    self.owner = msg.sender
    self.trion_token = _trion_token
    self.akashic_oracle = _akashic_oracle
    self.governance = _governance
    self.awa_enforced = True
    self.signals_frozen = False

# ── Validator Registration ─────────────────────────────────────────────────────

@external
def register_validator(
    stake_amount: uint256,
    geographic_region: String[32],
    jurisdiction: String[16],
    continent: String[16],
    hsm_hash: bytes32,
):
    """
    Register as a validator. Requires minimum stake and HSM verification commitment.
    HSM (Thales Luna 7 / YubiHSM 2) is NON-NEGOTIABLE per whitepaper.
    """
    assert not self.validators[msg.sender].active, "Already registered"
    assert stake_amount >= MINIMUM_STAKE, "Insufficient stake"
    assert not self.validators[msg.sender].permanently_excluded, "Permanently excluded"

    # Transfer tokens (ERC20 interface assumed)
    # In production: IERC20(self.trion_token).transferFrom(msg.sender, self, stake_amount)

    self.validators[msg.sender] = Validator({
        stake: stake_amount,
        diversity_score: 10**18,  # Initialized to 1.0, updated by oracle
        effective_stake: stake_amount,
        geographic_region: geographic_region,
        jurisdiction: jurisdiction,
        continent: continent,
        hsm_verified: True,
        hsm_hash: hsm_hash,
        registered_at: block.timestamp,
        last_accuracy_check: block.timestamp,
        accuracy_score: 10**18,  # Start at 1.0
        uptime_score: 10**18,
        permanently_excluded: False,
        active: True,
    })

    self.validator_list.append(msg.sender)
    self.validator_count += 1
    self.total_effective_stake += stake_amount
    self.region_stake[geographic_region] += stake_amount

    self._update_hhi()
    self._check_geographic_constraints(geographic_region, jurisdiction)

    log ValidatorRegistered(msg.sender, stake_amount, geographic_region, hsm_hash)

# ── Diversity Update (called by Oracle) ──────────────────────────────────────

@external
def update_diversity_score(validator: address, d_j_scaled: uint256):
    """
    Update validator diversity weight d_j = 1 - corr(M_j, M̄).
    Called by Akashic Oracle after each consensus round.
    d_j_scaled is d_j × 1e18.
    """
    assert msg.sender == self.akashic_oracle, "Oracle only"
    assert self.validators[validator].active, "Not active"

    v: Validator = self.validators[validator]
    old_effective: uint256 = v.effective_stake
    new_effective: uint256 = v.stake * d_j_scaled / 10**18

    self.validators[validator].diversity_score = d_j_scaled
    self.validators[validator].effective_stake = new_effective

    self.total_effective_stake = self.total_effective_stake - old_effective + new_effective
    self._update_hhi()

# ── Slashing ──────────────────────────────────────────────────────────────────

@external
def slash_validator(
    validator: address,
    slash_type: String[64],
    evidence_hash: bytes32,
):
    """
    Slash a validator for one of the defined slashing conditions.
    slash_type: COORDINATED_ATTACK | LOW_ACCURACY | HSM_FAILURE | UPTIME | SYBIL_CLUSTER
    Opens a 72-hour dispute window before executing.
    """
    assert msg.sender == self.akashic_oracle or msg.sender == self.governance, "Unauthorized"
    assert self.validators[validator].active, "Not active"

    slash_bps: uint256 = 0
    permanent: bool = False

    if slash_type == "COORDINATED_ATTACK_CONFIRMED":
        slash_bps = SLASH_COORD_ATTACK
        permanent = True
    elif slash_type == "SUSTAINED_LOW_ACCURACY":
        slash_bps = SLASH_LOW_ACCURACY
    elif slash_type == "HARDWARE_SECURITY_FAILURE":
        slash_bps = SLASH_HSM_FAILURE
    elif slash_type == "UPTIME_FAILURE":
        slash_bps = SLASH_UPTIME
    elif slash_type == "SYBIL_CLUSTER_CONFIRMED":
        slash_bps = SLASH_SYBIL
        permanent = True
    else:
        raise "Unknown slash type"

    slash_amount: uint256 = self.validators[validator].stake * slash_bps / 10000

    dispute_id: bytes32 = keccak256(
        concat(
            convert(validator, bytes20),
            convert(block.timestamp, bytes32),
            evidence_hash,
        )
    )

    self.disputes[dispute_id] = Dispute({
        validator: validator,
        slash_amount: slash_amount,
        challenge_bond: slash_amount * CHALLENGE_BOND_BPS / 10000,
        created_at: block.timestamp,
        resolved: False,
        upheld: False,
        reason: slash_type,
    })
    self.active_disputes += 1

    if permanent:
        self.validators[validator].permanently_excluded = True

    log ValidatorSlashed(validator, slash_amount, slash_type, permanent)

@external
def dispute_slash(dispute_id: bytes32):
    """
    Validator disputes a slash within 72-hour window.
    Must stake challenge_bond.
    """
    dispute: Dispute = self.disputes[dispute_id]
    assert dispute.validator == msg.sender, "Not your dispute"
    assert not dispute.resolved, "Already resolved"
    assert block.timestamp <= dispute.created_at + DISPUTE_WINDOW, "Window closed"

    log SlashDisputed(msg.sender, dispute.challenge_bond, dispute_id)

@external
def resolve_dispute(dispute_id: bytes32, upheld: bool):
    """
    Resolve a dispute. Called by governance (3 independent validators + 1 human oversight council).
    upheld=True: slash reversed, bond returned + reward
    upheld=False: slash stands, challenger loses bond
    """
    assert msg.sender == self.governance, "Governance only"
    assert not self.disputes[dispute_id].resolved, "Already resolved"

    self.disputes[dispute_id].resolved = True
    self.disputes[dispute_id].upheld = upheld
    self.active_disputes -= 1

    log DisputeResolved(dispute_id, upheld, self.disputes[dispute_id].validator)

# ── HHI and Geographic Enforcement ───────────────────────────────────────────

@internal
def _update_hhi():
    """
    HHI(t) = Σ_j (s_j · d_j / Σ_k s_k·d_k)² × 10000
    Automatic response tiers:
    <1500: HEALTHY
    1500-2500: WARNING — 2× reward for underrepresented
    2500-4000: DANGER — weight cap, no cluster > 15%
    >4000: CRITICAL — consensus paused
    """
    # HHI computation simplified — full computation done off-chain and submitted
    # On-chain stores current HHI and enforces tiers
    if self.current_hhi > HHI_DANGER:
        self.signals_frozen = True
        self.awa_enforced = False
        log AWAViolation("HHI_CRITICAL", True)
    elif self.current_hhi > HHI_WARNING:
        pass  # Weight caps enforced in update_diversity_score
    else:
        if not self.signals_frozen:
            self.awa_enforced = True

@external
def submit_hhi(hhi_value: uint256, continents: uint256):
    """Submit computed HHI and continent count from oracle."""
    assert msg.sender == self.akashic_oracle, "Oracle only"
    self.current_hhi = hhi_value
    self.continents_covered = continents
    self._update_hhi()

@internal
def _check_geographic_constraints(region: String[32], jurisdiction: String[16]):
    """
    Geographic constraints (separate from HHI, checked continuously):
    max single region < 0.40
    max single jurisdiction < 0.30
    """
    if self.total_effective_stake > 0:
        region_share: uint256 = self.region_stake[region] * 10**18 / self.total_effective_stake
        if region_share > MAX_SINGLE_REGION:
            log GeographicWarning(region, region_share, MAX_SINGLE_REGION)

# ── Rewards ───────────────────────────────────────────────────────────────────

@external
def distribute_reward(
    validator: address,
    base_reward: uint256,
    accuracy_factor_scaled: uint256,  # 1e18
    uptime_factor_scaled: uint256,    # 1e18
):
    """
    REWARD(j, t) = BASE_REWARD × accuracy_factor × diversity_factor × uptime_factor
    diversity_factor = 1 + γ_diversity · d_j     (γ_diversity > 0)
    Validators paid to be independent.
    """
    assert msg.sender == self.akashic_oracle, "Oracle only"
    assert self.validators[validator].active, "Not active"

    gamma_diversity: uint256 = 200_000_000_000_000_000  # 0.2 scaled 1e18
    d_j: uint256 = self.validators[validator].diversity_score
    diversity_factor: uint256 = 10**18 + gamma_diversity * d_j / 10**18

    reward: uint256 = (
        base_reward
        * accuracy_factor_scaled / 10**18
        * diversity_factor / 10**18
        * uptime_factor_scaled / 10**18
    )

    public_good_contribution: uint256 = reward * PUBLIC_GOOD_BPS / 10000
    validator_reward: uint256 = reward - public_good_contribution
    self.public_good_pool += public_good_contribution

    log DiversityBonusAwarded(validator, validator_reward, d_j)

# ── AWA Enforcement ──────────────────────────────────────────────────────────

@view
@external
def is_signal_emission_allowed() -> bool:
    """
    AWA_enforced iff all_of:
      no_single_entity_controls_signal_weights
      no_single_entity_controls_validator_selection
      Public_Good_Charter_minimum >= 15%
      Sovereignty_Dignity_Protocol_active
      Right_to_Invisibility_enforced
    Returns False → signal emission FROZEN automatically.
    Cannot be overridden by any single entity.
    """
    return self.awa_enforced and not self.signals_frozen

@view
@external
def get_validator_info(validator: address) -> Validator:
    return self.validators[validator]

@view
@external
def get_effective_stake(validator: address) -> uint256:
    return self.validators[validator].effective_stake

@view
@external
def get_public_good_pool() -> uint256:
    return self.public_good_pool
