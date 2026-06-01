# @version ^0.3.10
# TRION Protocol — TRION Token (Vyper)
# Whitepaper Section 21: "Validator staking, slashing, TRION token — Vyper"
#
# ERC-20 with:
#   - Public Good Charter enforcement (15% of supply reserved)
#   - Behavioral staking integration (minting gated by AWA conditions)
#   - Epoch-based inflation cap (2% per year maximum)
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

# Epoch-based inflation cap: 2% per year
MAX_ANNUAL_INFLATION_BPS: constant(uint256) = 200           # 2.00%
epoch_start:     public(uint256)                            # timestamp of last epoch reset
epoch_minted:    public(uint256)                            # minted in current epoch
epoch_duration:  public(uint256)                            # seconds per epoch (default 365d)

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
):
    self.name     = "TRION Behavioral Oracle Token"
    self.symbol   = "TRION"
    self.decimals = 18

    self.governance       = _governance
    self.public_good_reserve = _public_good_addr
    self.staking_contract = _staking_contract
    self.awa_enforced     = True
    self.epoch_duration   = 365 * 24 * 3600
    self.epoch_start      = block.timestamp
    self.epoch_minted     = 0

    # Initial supply to governance (for distribution)
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
    self.allowance[msg.sender][spender] = amount
    log Approval(msg.sender, spender, amount)
    return True

# ── Governance Minting ────────────────────────────────────────────────────────
@external
def governance_mint(recipient: address, amount: uint256) -> bool:
    """
    Mint new TRION tokens. Only callable by governance.
    Enforces:
      1. AWA must be ENFORCED (behavioral truth layer healthy)
      2. Annual inflation cap (2% of current supply per epoch)
      3. Public Good Charter: 15% of minted amount auto-routed to public_good_reserve
    """
    assert msg.sender == self.governance, "TRION: governance only"
    assert self.awa_enforced, "TRION: AWA suspended — minting frozen"

    # Reset epoch if elapsed
    if block.timestamp >= self.epoch_start + self.epoch_duration:
        self.epoch_start  = block.timestamp
        self.epoch_minted = 0

    # Inflation cap: max 2% of totalSupply per epoch
    max_epoch_mint: uint256 = self.totalSupply * MAX_ANNUAL_INFLATION_BPS / 10000
    assert self.epoch_minted + amount <= max_epoch_mint, "TRION: annual inflation cap exceeded"

    # Public Good Charter: 15% routed automatically
    pg_amount: uint256 = amount * PUBLIC_GOOD_BPS / 10000
    net_amount: uint256 = amount - pg_amount

    self.totalSupply                      += amount
    self.balanceOf[recipient]             += net_amount
    self.balanceOf[self.public_good_reserve] += pg_amount
    self.epoch_minted                     += amount
    self.total_governance_minted          += amount
    self.public_good_minted               += pg_amount

    log Transfer(empty(address), recipient, net_amount)
    log Transfer(empty(address), self.public_good_reserve, pg_amount)
    log PublicGoodMint(self.public_good_reserve, pg_amount, "AWA public good charter 15%")
    return True

# ── Staking Integration ───────────────────────────────────────────────────────
@external
def slash_validator(validator: address, slash_amount: uint256, condition: String[64]) -> bool:
    """
    Called by the staking contract to slash a misbehaving validator.
    Slashed tokens are sent to the public_good_reserve (not burned — information preserved).
    """
    assert msg.sender == self.staking_contract, "TRION: staking contract only"
    assert self.balanceOf[validator] >= slash_amount, "TRION: insufficient validator balance"

    self.balanceOf[validator]                -= slash_amount
    self.balanceOf[self.public_good_reserve] += slash_amount

    log Transfer(validator, self.public_good_reserve, slash_amount)
    log ValidatorSlash(validator, slash_amount, condition)
    return True

# ── AWA Integration ───────────────────────────────────────────────────────────
@external
def set_awa_enforced(enforced: bool):
    """
    Called by governance to freeze/unfreeze minting based on AWA status.
    AWA SUSPENDED or EMERGENCY → minting frozen.
    AWA ENFORCED → minting allowed (subject to caps).
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
    self.staking_contract = new_staking

# ── View Functions ────────────────────────────────────────────────────────────
@view
@external
def remaining_epoch_mint() -> uint256:
    """Remaining mintable tokens in current epoch before inflation cap."""
    if block.timestamp >= self.epoch_start + self.epoch_duration:
        return self.totalSupply * MAX_ANNUAL_INFLATION_BPS / 10000
    max_epoch: uint256 = self.totalSupply * MAX_ANNUAL_INFLATION_BPS / 10000
    if self.epoch_minted >= max_epoch:
        return 0
    return max_epoch - self.epoch_minted

@view
@external
def public_good_percentage() -> uint256:
    """Public Good Charter percentage in basis points (always 1500 = 15%)."""
    return PUBLIC_GOOD_BPS
