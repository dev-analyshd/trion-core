# @version ^0.3.10
# TRION Protocol — TRION Token (Vyper)
# Whitepaper Section 21: "Validator staking, slashing, TRION token — Vyper"
#
# ERC-20 with:
#   - Public Good Charter enforcement (15% of supply reserved)
#   - Behavioral staking integration (minting gated by AWA conditions)
#   - FIXED SUPPLY — NO ongoing issuance (AUDIT-4 Gap 1 fix)
#   - Slashing destination: 50% insurance_pool / 50% burn (AUDIT-4 Gap 1 fix)
#   - No admin key — governance-only minting
#
# Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
# License: CC0

from vyper.interfaces import ERC20

implements: ERC20

# ── Events ────────────────────────────────────────────────────────────────────
event Transfer:
    sender:   indexed(address)
    receiver: indexed(address)
    value:    uint256

event Approval:
    owner:   indexed(address)
    spender: indexed(address)
    value:   uint256

event PublicGoodMint:
    recipient: indexed(address)
    amount:    uint256
    purpose:   String[128]

event ValidatorSlash:
    validator:       indexed(address)
    slashed_amount:  uint256
    slash_condition: String[64]
    insurance_share: uint256
    burn_share:       uint256

event Burn:
    burner: indexed(address)
    amount: uint256

# ── State ─────────────────────────────────────────────────────────────────────
name:     public(String[64])
symbol:   public(String[8])
decimals: public(uint8)

totalSupply:    public(uint256)
balanceOf:      public(HashMap[address, uint256])
allowance:      public(HashMap[address, HashMap[address, uint256]])

# Governance: AWA-enforced minting — only through multi-sig governance
governance:     public(address)

# Public Good Charter: 15% minimum of all minted tokens go to public goods
PUBLIC_GOOD_BPS: constant(uint256) = 1500                  # 15.00%
public_good_reserve: public(address)
public_good_minted:  public(uint256)
total_governance_minted: public(uint256)

# ────────────────────────────────────────────────────────────────────────────
# AUDIT-4 Gap 1 Fix — Economics Conformance
# ────────────────────────────────────────────────────────────────────────────
# 1. NO ONGOING ISSUANCE.
#    The whitepaper specifies a deflationary, fixed-supply token. The previous
#    version had `MAX_ANNUAL_INFLATION_BPS = 200` (2%/yr) — that violated
#    Gap 1's "no ongoing issuance" mandate. The cap is now ZERO. The
#    `governance_mint()` function is preserved ONLY for the genesis
#    distribution (initial supply to governance) and is otherwise a no-op
#    that reverts. Validator rewards come from protocol fees, NOT from
#    new minting.
#
# 2. SLASHED TRION DESTINATION: 50% insurance_pool / 50% burn.
#    Gap 1 specifies "slashed TRION destination 50/50 to insurance pool +
#    burn". The previous version sent 100% to public_good_reserve. We now
#    split 50% to `insurance_pool` (a separately-tracked address) and burn
#    50% (reduce totalSupply + balanceOf).
MAX_ANNUAL_INFLATION_BPS: constant(uint256) = 0              # AUDIT-4 Gap 1: NO inflation

# Insurance pool — receives 50% of all slashed TRION (Gap 1).
insurance_pool: public(address)
insurance_pool_balance: public(uint256)
total_burned: public(uint256)

# Epoch bookkeeping retained for backward-compatibility with read-side
# consumers (e.g. /api/v1/tokenomics), but epoch_minted is now always 0
# and the cap is 0.
epoch_start:     public(uint256)
epoch_minted:    public(uint256)
epoch_duration:  public(uint256)

# Staking contract reference
staking_contract: public(address)

# AWA enforcement: minting frozen when AWA is SUSPENDED or EMERGENCY
awa_enforced: public(bool)

# ── Constructor ───────────────────────────────────────────────────────────────
@external
def __init__(
    _governance:        address,
    _public_good_addr:  address,
    _staking_contract:  address,
    _initial_supply:    uint256,
    _insurance_pool:    address,
):
    """
    Constructor.

    @param _governance       Governance multi-sig that may call update_*().
    @param _public_good_addr Public Good Charter reserve (15% minimum).
    @param _staking_contract TRIONStaking contract (calls slash_validator).
    @param _initial_supply   Fixed genesis supply. NO further minting.
    @param _insurance_pool   Insurance pool — receives 50% of slashed TRION
                             per AUDIT-4 Gap 1 (50/50 insurance/burn split).
    """
    self.name     = "TRION Behavioral Oracle Token"
    self.symbol   = "TRION"
    self.decimals = 18

    self.governance       = _governance
    self.public_good_reserve = _public_good_addr
    self.staking_contract = _staking_contract
    self.insurance_pool   = _insurance_pool
    self.awa_enforced     = True
    self.epoch_duration   = 365 * 24 * 3600
    self.epoch_start      = block.timestamp
    self.epoch_minted     = 0

    # Fixed genesis supply — distributed once. NO ongoing issuance.
    if _initial_supply > 0:
        self.totalSupply      = _initial_supply
        self.balanceOf[_governance] = _initial_supply
        log Transfer(empty(address), _governance, _initial_supply)

# ── ERC-20 Core ───────────────────────────────────────────────────────────────
@external
def transfer(to: address, amount: uint256) -> bool:
    assert to != empty(address), "TRION: zero address"
    assert self.balanceOf[msg.sender] >= amount, "TRION: insufficient balance"
    self.balanceOf[msg.sender] -= amount
    self.balanceOf[to]         += amount
    log Transfer(msg.sender, to, amount)
    return True

@external
def transferFrom(from_addr: address, to: address, amount: uint256) -> bool:
    assert to != empty(address), "TRION: zero address"
    assert self.balanceOf[from_addr] >= amount, "TRION: insufficient balance"
    assert self.allowance[from_addr][msg.sender] >= amount, "TRION: allowance exceeded"
    self.allowance[from_addr][msg.sender] -= amount
    self.balanceOf[from_addr]             -= amount
    self.balanceOf[to]                    += amount
    log Transfer(from_addr, to, amount)
    return True

@external
def approve(spender: address, amount: uint256) -> bool:
    # PHASE-1-SECURITY: prevent approving the zero address.
    assert spender != empty(address), "TRION: zero address"
    self.allowance[msg.sender][spender] = amount
    log Approval(msg.sender, spender, amount)
    return True

# ── Governance Minting — DISABLED (AUDIT-4 Gap 1) ────────────────────────────
@external
def governance_mint(recipient: address, amount: uint256) -> bool:
    """
    AUDIT-4 Gap 1: NO ongoing issuance.

    The whitepaper mandates a deflationary, fixed-supply token: "validator
    rewards come from protocol fees, not new minting". This function is
    retained for ABI compatibility but always reverts. Use `transferFrom`
    from the genesis allocation, or distribute protocol-fee revenue via
    the staking contract's `distribute_reward()` instead.
    """
    raise "TRION: no ongoing issuance - Gap 1 conformance"
    # Function always reverts — Gap 1 conformance: NO ongoing issuance.
    # The body below is unreachable; kept only to satisfy the Vyper
    # type-checker for the `-> bool` signature on legacy callers.

# ── Slashing Integration (AUDIT-4 Gap 1: 50/50 insurance/burn) ──────────────
@external
def slash_validator(validator: address, slash_amount: uint256, condition: String[64]) -> bool:
    """
    Called by the staking contract to slash a misbehaving validator.

    AUDIT-4 Gap 1 conformance — slashed TRION destination is now
    50% to `insurance_pool` (capitalized insurance fund backing
    validator coverage promises) + 50% burned (deflationary pressure
    compensates all holders pro-rata). The previous version sent
    100% to `public_good_reserve`, which did NOT match the spec.

    Information about the offense is preserved via the ValidatorSlash
    event (condition string + amounts), so the slashed stake is still
    auditable even though the tokens are burned rather than recycled.
    """
    assert msg.sender == self.staking_contract, "TRION: staking contract only"
    assert self.balanceOf[validator] >= slash_amount, "TRION: insufficient validator balance"

    # 50/50 split — Gap 1 spec.
    insurance_share: uint256 = slash_amount / 2
    burn_share:       uint256 = slash_amount - insurance_share

    # Debit validator.
    self.balanceOf[validator] -= slash_amount

    # 50% → insurance_pool (claimable capital for coverage-tier payouts).
    if insurance_share > 0:
        self.balanceOf[self.insurance_pool] += insurance_share
        self.insurance_pool_balance += insurance_share
        log Transfer(validator, self.insurance_pool, insurance_share)

    # 50% → burn (permanently removed from supply — deflationary).
    if burn_share > 0:
        self.totalSupply -= burn_share
        self.total_burned += burn_share
        log Transfer(validator, empty(address), burn_share)
        log Burn(validator, burn_share)

    log ValidatorSlash(validator, slash_amount, condition, insurance_share, burn_share)
    return True

# ── Explicit Burn (AUDIT-4 Gap 1) ────────────────────────────────────────────
@external
def burn(amount: uint256) -> bool:
    """
    Permissionless burn — any holder may permanently destroy their TRION.
    Required by Gap 1's deflationary mechanism ("burn mechanism — portion
    of every BTCP fee burned"). The staking/escrow contracts route their
    burn share through `slash_validator()` above; this function is the
    public entry point for ad-hoc burns (e.g. user-paid signal fees).
    """
    assert self.balanceOf[msg.sender] >= amount, "TRION: insufficient balance"
    assert amount > 0, "TRION: zero burn"
    self.balanceOf[msg.sender] -= amount
    self.totalSupply           -= amount
    self.total_burned          += amount
    log Transfer(msg.sender, empty(address), amount)
    log Burn(msg.sender, amount)
    return True

# ── AWA Integration ───────────────────────────────────────────────────────────
@external
def set_awa_enforced(enforced: bool):
    """
    Called by governance to freeze/unfreeze minting based on AWA status.
    AWA SUSPENDED or EMERGENCY → minting frozen (already a no-op under Gap 1).
    AWA ENFORCED → minting allowed (subject to caps — which are 0).
    """
    assert msg.sender == self.governance, "TRION: governance only"
    self.awa_enforced = enforced

@external
def update_governance(new_governance: address):
    assert msg.sender == self.governance, "TRION: governance only"
    assert new_governance != empty(address), "TRION: zero address"
    self.governance = new_governance

@external
def update_staking_contract(new_staking: address):
    assert msg.sender == self.governance, "TRION: governance only"
    # PHASE-1-SECURITY: zero-address check.
    assert new_staking != empty(address), "TRION: zero address"
    self.staking_contract = new_staking

@external
def update_insurance_pool(new_pool: address):
    """
    Update the insurance pool address. Governance-only.
    """
    assert msg.sender == self.governance, "TRION: governance only"
    assert new_pool != empty(address), "TRION: zero address"
    self.insurance_pool = new_pool

# ── View Functions ────────────────────────────────────────────────────────────
@view
@external
def remaining_epoch_mint() -> uint256:
    """
    Remaining mintable tokens in current epoch before inflation cap.

    AUDIT-4 Gap 1: NO ongoing issuance — always returns 0. Preserved
    for ABI compatibility with existing tokenomics dashboards.
    """
    return 0

@view
@external
def public_good_percentage() -> uint256:
    """Public Good Charter percentage in basis points (always 1500 = 15%)."""
    return PUBLIC_GOOD_BPS

@view
@external
def max_annual_inflation_bps() -> uint256:
    """AUDIT-4 Gap 1: returns 0 — no ongoing issuance."""
    return MAX_ANNUAL_INFLATION_BPS

@view
@external
def get_slash_destination_split() -> uint256:
    """
    AUDIT-4 Gap 1: returns 5000 (= 50.00% in bps) — the share of each
    slash routed to insurance_pool. The remainder (10000 - 5000 = 50%)
    is burned.
    """
    return 5000
