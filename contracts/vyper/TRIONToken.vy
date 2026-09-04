# @version ^0.3.10
# TRION Protocol — TRION Token (Vyper) — reference token implementation
#
# Canonical tokenomics: docs/TOKENOMICS.md (resolves DD finding 5.4
# "one supply, three stories" — supply, decimals and genesis distribution are
# now identical across the Vyper / NEAR / TON / ink! implementations).
# Whitepaper Part 15.3:
#   "Token supply: fixed at genesis. No inflation mechanism."
#   "Token deflationary: consumption bonding burns small fraction on each use."
#   item 5 (Public Good Charter): "15% of fee revenue automatically routed to
#   public good pool."
#
# ERC-20 with:
#   - FIXED SUPPLY — TOTAL_SUPPLY constant = 1,000,000,000 TRION @ 18 decimals
#     (10^27 raw units), minted exactly ONCE in the constructor.
#     NO minting afterwards (governance_mint always reverts).
#   - GENESIS DISTRIBUTION (on-chain enforced): PUBLIC_GOOD_BPS = 15% of the
#     genesis supply is credited to the public-good reserve address; the
#     remaining 85% is credited to the treasury & vesting allocator address.
#   - BURN-ON-USE (WP 15.3): every transfer pays a 0.05% (TRANSFER_FEE_BPS)
#     consumption fee; 15% of each collected fee (PUBLIC_GOOD_BPS, WP 15.3
#     item 5) is forwarded to the public-good reserve and the remaining 85%
#     of the fee is burned (deflationary). The WP fixes no numeric burn rate
#     ("burns small fraction on each use"); 0.05% is fixed by docs/TOKENOMICS.md.
#   - Permissionless burn()/burnFrom() (deflationary mechanism).
#   - Behavioral staking integration: slash_validator — 50% insurance_pool /
#     50% burn (AUDIT-4 Gap 1 fix).
#   - No admin key — governance-only parameter updates.
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

event ValidatorSlash:
    validator:       indexed(address)
    slashed_amount:  uint256
    slash_condition: String[64]
    insurance_share: uint256
    burn_share:       uint256

event Burn:
    burner: indexed(address)
    amount: uint256

event ConsumptionFee:
    payer:           indexed(address)
    fee:             uint256
    burned:          uint256
    public_good_share: uint256

# ── State ─────────────────────────────────────────────────────────────────────
name:     public(String[64])
symbol:   public(String[8])
decimals: public(uint8)

totalSupply:    public(uint256)
balanceOf:      public(HashMap[address, uint256])
allowance:      public(HashMap[address, HashMap[address, uint256]])

# Governance: only through multi-sig governance
governance:     public(address)

# ── Canonical constants (docs/TOKENOMICS.md — identical in every chain impl) ──
# Fixed genesis supply: 1,000,000,000 TRION @ 18 decimals = 10^27 raw units.
TOTAL_SUPPLY: constant(uint256) = 1000000000 * 10 ** 18

# Public Good Charter: 15% — of the genesis supply (constructor carve-out)
# AND of every collected consumption fee (WP 15.3 item 5). ENFORCED on-chain.
PUBLIC_GOOD_BPS: constant(uint256) = 1500                  # 15.00%

# Burn-on-use consumption fee: 0.05% of every transfer (WP 15.3 "consumption
# bonding burns small fraction on each use" — no numeric rate in the WP; the
# 0.05% rate is fixed by docs/TOKENOMICS.md). 15% of each collected fee is
# forwarded to the public-good reserve, the remaining 85% is burned.
TRANSFER_FEE_BPS: constant(uint256) = 5                    # 0.05%

# AUDIT-4 Gap 1: NO ongoing issuance — inflation cap is ZERO.
MAX_ANNUAL_INFLATION_BPS: constant(uint256) = 0

public_good_reserve: public(address)
public_good_minted:  public(uint256)
total_governance_minted: public(uint256)

# ────────────────────────────────────────────────────────────────────────────
# AUDIT-4 Gap 1 Fix — Economics Conformance
# ────────────────────────────────────────────────────────────────────────────
# 1. NO ONGOING ISSUANCE.
#    The whitepaper specifies a deflationary, fixed-supply token. The genesis
#    supply is minted once in the constructor and `governance_mint()` always
#    reverts. Validator rewards come from protocol fees, NOT from new minting.
#
# 2. SLASHED TRION DESTINATION: 50% insurance_pool / 50% burn.
#    Gap 1 specifies "slashed TRION destination 50/50 to insurance pool +
#    burn". Implemented in slash_validator() below.
#
# 3. BURN-ON-USE (WP 15.3 deflationary mechanism).
#    _transfer() charges TRANSFER_FEE_BPS on every transfer; 15% of the fee
#    is routed to public_good_reserve (WP 15.3 item 5) and 85% is burned.

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

# Treasury & vesting allocator — receives 85% of the genesis supply; executes
# the off-chain vesting/ecosystem schedule documented in docs/TOKENOMICS.md.
treasury_allocator: public(address)

# Staking contract reference
staking_contract: public(address)

# AWA enforcement: minting frozen when AWA is SUSPENDED or EMERGENCY
awa_enforced: public(bool)

# ── Constructor ───────────────────────────────────────────────────────────────
@external
def __init__(
    _governance:         address,
    _public_good_addr:   address,
    _treasury_allocator: address,
    _staking_contract:   address,
    _insurance_pool:     address,
):
    """
    Constructor — the ONLY place supply is created.

    Mints the fixed TOTAL_SUPPLY (1,000,000,000 TRION @ 18 decimals) exactly
    once and distributes it on-chain (docs/TOKENOMICS.md):
      - PUBLIC_GOOD_BPS (15%)  -> public-good reserve address
      - remainder     (85%)    -> treasury & vesting allocator address

    @param _governance         Governance multi-sig that may call update_*().
    @param _public_good_addr   Public Good Charter reserve (15% of genesis).
    @param _treasury_allocator Treasury & vesting allocator (85% of genesis;
                               executes the docs/TOKENOMICS.md schedule).
    @param _staking_contract   TRIONStaking contract (calls slash_validator).
    @param _insurance_pool     Insurance pool — receives 50% of slashed TRION
                               per AUDIT-4 Gap 1 (50/50 insurance/burn split).
    """
    assert _governance         != empty(address), "TRION: zero governance"
    assert _public_good_addr   != empty(address), "TRION: zero public good reserve"
    assert _treasury_allocator != empty(address), "TRION: zero treasury allocator"
    assert _insurance_pool     != empty(address), "TRION: zero insurance pool"

    self.name     = "TRION Behavioral Oracle Token"
    self.symbol   = "TRION"
    self.decimals = 18

    self.governance           = _governance
    self.public_good_reserve  = _public_good_addr
    self.treasury_allocator   = _treasury_allocator
    self.staking_contract     = _staking_contract
    self.insurance_pool       = _insurance_pool
    self.awa_enforced         = True
    self.epoch_duration       = 365 * 24 * 3600
    self.epoch_start          = block.timestamp
    self.epoch_minted         = 0
    self.total_governance_minted = 0

    # Fixed genesis supply — minted once, distributed on-chain. NO issuance
    # afterwards. 15% public-good reserve / 85% treasury & vesting allocator.
    public_good_amount: uint256 = (TOTAL_SUPPLY * PUBLIC_GOOD_BPS) / 10000
    allocator_amount:   uint256 = TOTAL_SUPPLY - public_good_amount

    self.totalSupply = TOTAL_SUPPLY

    self.balanceOf[_public_good_addr] = public_good_amount
    self.public_good_minted = public_good_amount
    log Transfer(empty(address), _public_good_addr, public_good_amount)

    self.balanceOf[_treasury_allocator] = allocator_amount
    log Transfer(empty(address), _treasury_allocator, allocator_amount)

# ── ERC-20 Core (with burn-on-use consumption fee — WP 15.3) ─────────────────
@internal
def _transfer(sender: address, to: address, amount: uint256):
    """
    Shared transfer core. Charges the burn-on-use consumption fee:
      fee             = amount * TRANSFER_FEE_BPS / 10000        (0.05%)
      public_good_part = fee * PUBLIC_GOOD_BPS / 10000           (15% of fee)
      burn_part        = fee - public_good_part                  (85% of fee)
    Recipient receives amount - fee; public_good_part is forwarded to the
    public-good reserve (WP 15.3 item 5); burn_part is destroyed.
    """
    assert to != empty(address), "TRION: zero address"
    assert self.balanceOf[sender] >= amount, "TRION: insufficient balance"

    fee: uint256 = (amount * TRANSFER_FEE_BPS) / 10000
    public_good_part: uint256 = 0
    burn_part: uint256 = 0
    if fee > 0:
        public_good_part = (fee * PUBLIC_GOOD_BPS) / 10000
        burn_part = fee - public_good_part

    self.balanceOf[sender] -= amount
    self.balanceOf[to]     += amount - fee

    if public_good_part > 0:
        self.balanceOf[self.public_good_reserve] += public_good_part
        log Transfer(sender, self.public_good_reserve, public_good_part)

    if burn_part > 0:
        self.totalSupply  -= burn_part
        self.total_burned += burn_part
        log Transfer(sender, empty(address), burn_part)
        log Burn(sender, burn_part)

    if fee > 0:
        log ConsumptionFee(sender, fee, burn_part, public_good_part)

    log Transfer(sender, to, amount - fee)

@external
def transfer(to: address, amount: uint256) -> bool:
    self._transfer(msg.sender, to, amount)
    return True

@external
def transferFrom(from_addr: address, to: address, amount: uint256) -> bool:
    assert self.allowance[from_addr][msg.sender] >= amount, "TRION: allowance exceeded"
    self.allowance[from_addr][msg.sender] -= amount
    self._transfer(from_addr, to, amount)
    return True

@external
def approve(spender: address, amount: uint256) -> bool:
    # PHASE-1-SECURITY: prevent approving the zero address.
    assert spender != empty(address), "TRION: zero address"
    self.allowance[msg.sender][spender] = amount
    log Approval(msg.sender, spender, amount)
    return True

# ── Explicit Burn (AUDIT-4 Gap 1 / WP 15.3 deflation) ────────────────────────
@external
def burn(amount: uint256) -> bool:
    """
    Permissionless burn — any holder may permanently destroy their TRION.
    Deflationary mechanism per WP 15.3 ("consumption bonding burns small
    fraction on each use") and AUDIT-4 Gap 1. The staking/escrow contracts
    route their burn share through `slash_validator()`; this function is the
    public entry point for ad-hoc burns (e.g. user-paid signal fees).
    """
    assert amount > 0, "TRION: zero burn"
    assert self.balanceOf[msg.sender] >= amount, "TRION: insufficient balance"
    self.balanceOf[msg.sender] -= amount
    self.totalSupply           -= amount
    self.total_burned          += amount
    log Transfer(msg.sender, empty(address), amount)
    log Burn(msg.sender, amount)
    return True

@external
def burnFrom(from_addr: address, amount: uint256) -> bool:
    """
    Burn on behalf of an approved holder (spending an allowance).
    Same deflationary accounting as burn().
    """
    assert amount > 0, "TRION: zero burn"
    assert self.balanceOf[from_addr] >= amount, "TRION: insufficient balance"
    assert self.allowance[from_addr][msg.sender] >= amount, "TRION: allowance exceeded"
    self.allowance[from_addr][msg.sender] -= amount
    self.balanceOf[from_addr] -= amount
    self.totalSupply           -= amount
    self.total_burned          += amount
    log Transfer(from_addr, empty(address), amount)
    log Burn(from_addr, amount)
    return True

# ── Governance Minting — DISABLED (WP 15.3: fixed supply, no inflation) ──────
@external
def governance_mint(recipient: address, amount: uint256) -> bool:
    """
    WP 15.3: "Token supply: fixed at genesis. No inflation mechanism."

    The entire supply was minted once in the constructor. This function is
    retained for ABI compatibility but ALWAYS reverts. Use `transferFrom`
    from the genesis allocation, or distribute protocol-fee revenue via the
    staking contract's `distribute_reward()` instead.
    """
    raise "TRION: fixed supply at genesis - no inflation (WP 15.3)"

# ── Slashing Integration (AUDIT-4 Gap 1: 50/50 insurance/burn) ──────────────
@external
def slash_validator(validator: address, slash_amount: uint256, condition: String[64]) -> bool:
    """
    Called by the staking contract to slash a misbehaving validator.

    AUDIT-4 Gap 1 conformance — slashed TRION destination is 50% to
    `insurance_pool` + 50% burned. Information about the offense is
    preserved via the ValidatorSlash event.
    """
    assert msg.sender == self.staking_contract, "TRION: staking contract only"
    assert self.balanceOf[validator] >= slash_amount, "TRION: insufficient validator balance"
    assert slash_amount > 0, "TRION: zero slash"

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

# ── AWA Integration ───────────────────────────────────────────────────────────
@external
def set_awa_enforced(enforced: bool):
    """
    Called by governance to freeze/unfreeze minting based on AWA status.
    AWA SUSPENDED or EMERGENCY → minting frozen (already a no-op — supply is
    fixed at genesis). AWA ENFORCED → minting allowed (cap is 0 regardless).
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

    WP 15.3 / AUDIT-4 Gap 1: NO ongoing issuance — always returns 0.
    Preserved for ABI compatibility with existing tokenomics dashboards.
    """
    return 0

@view
@external
def public_good_percentage() -> uint256:
    """Public Good Charter percentage in basis points (always 1500 = 15%)."""
    return PUBLIC_GOOD_BPS

@view
@external
def transfer_fee_bps() -> uint256:
    """Burn-on-use consumption fee in basis points (always 5 = 0.05%)."""
    return TRANSFER_FEE_BPS

@view
@external
def genesis_public_good_amount() -> uint256:
    """Genesis carve-out actually credited to the public-good reserve (raw units)."""
    return (TOTAL_SUPPLY * PUBLIC_GOOD_BPS) / 10000

@view
@external
def genesis_allocator_amount() -> uint256:
    """Genesis amount actually credited to the treasury & vesting allocator (raw units)."""
    return TOTAL_SUPPLY - (TOTAL_SUPPLY * PUBLIC_GOOD_BPS) / 10000

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
