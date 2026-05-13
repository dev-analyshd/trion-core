// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title TRIONToken — TRION Protocol Governance & Utility Token
 * @notice Fixed supply 1,000,000,000 TRION (1B).
 * @dev L10.7 whitepaper allocation:
 *   35% Validator Network
 *   20% Protocol Treasury
 *   15% Community Distribution
 *   12% Team + Contributors (4yr vest)
 *   10% Ecosystem Fund
 *    5% Strategic Partners
 *    3% Public Sale
 */
contract TRIONToken {

    // ── ERC-20 core ───────────────────────────────────────────────────────

    string  public constant name     = "TRION Protocol";
    string  public constant symbol   = "TRION";
    uint8   public constant decimals = 18;
    uint256 public constant TOTAL_SUPPLY = 1_000_000_000 * 1e18;

    mapping(address => uint256) private _balances;
    mapping(address => mapping(address => uint256)) private _allowances;

    // ── Protocol roles ────────────────────────────────────────────────────

    address public owner;
    address public signal_contract;

    // ── Allocation buckets (whitepaper L10.7) ─────────────────────────────

    uint256 public constant VALIDATOR_ALLOCATION    = 350_000_000 * 1e18;
    uint256 public constant TREASURY_ALLOCATION     = 200_000_000 * 1e18;
    uint256 public constant COMMUNITY_ALLOCATION    = 150_000_000 * 1e18;
    uint256 public constant TEAM_ALLOCATION         = 120_000_000 * 1e18;
    uint256 public constant ECOSYSTEM_ALLOCATION    = 100_000_000 * 1e18;
    uint256 public constant PARTNERS_ALLOCATION     =  50_000_000 * 1e18;
    uint256 public constant PUBLIC_SALE_ALLOCATION  =  30_000_000 * 1e18;

    // ── Token utility classes ─────────────────────────────────────────────

    // 1. Validator staking (min stake = 10,000 TRION)
    uint256 public constant MIN_VALIDATOR_STAKE = 10_000 * 1e18;

    // 2. Signal access fee (per query, burned)
    uint256 public signal_access_fee = 1 * 1e18;

    // 3. Governance voting (1 TRION = 1 vote, capped at sqrt(stake))
    // 4. Ecosystem fund participation
    // 5. Slashing collateral

    mapping(address => uint256) public stake_balance;
    uint256 public total_staked;

    // ── Events ────────────────────────────────────────────────────────────

    event Transfer(address indexed from, address indexed to, uint256 amount);
    event Approval(address indexed owner, address indexed spender, uint256 amount);
    event Staked(address indexed validator, uint256 amount);
    event Unstaked(address indexed validator, uint256 amount);
    event Slashed(address indexed validator, uint256 amount, string reason);
    event FeeCollected(address indexed user, uint256 fee);

    // ── Errors ────────────────────────────────────────────────────────────

    error InsufficientBalance(uint256 have, uint256 need);
    error InsufficientAllowance(uint256 have, uint256 need);
    error InsufficientStake(uint256 have, uint256 need);
    error Unauthorized(address caller);

    // ── Constructor ───────────────────────────────────────────────────────

    constructor(
        address validator_treasury,
        address protocol_treasury,
        address community_fund,
        address team_multisig,
        address ecosystem_fund,
        address partners_multisig,
        address public_sale_contract
    ) {
        owner = msg.sender;

        _mint(validator_treasury,   VALIDATOR_ALLOCATION);
        _mint(protocol_treasury,    TREASURY_ALLOCATION);
        _mint(community_fund,       COMMUNITY_ALLOCATION);
        _mint(team_multisig,        TEAM_ALLOCATION);
        _mint(ecosystem_fund,       ECOSYSTEM_ALLOCATION);
        _mint(partners_multisig,    PARTNERS_ALLOCATION);
        _mint(public_sale_contract, PUBLIC_SALE_ALLOCATION);
    }

    // ── ERC-20 ────────────────────────────────────────────────────────────

    function totalSupply() external pure returns (uint256) { return TOTAL_SUPPLY; }

    function balanceOf(address account) external view returns (uint256) {
        return _balances[account];
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        _allowances[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function allowance(address _owner, address spender) external view returns (uint256) {
        return _allowances[_owner][spender];
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 allowed = _allowances[from][msg.sender];
        if (allowed < amount) revert InsufficientAllowance(allowed, amount);
        _allowances[from][msg.sender] = allowed - amount;
        _transfer(from, to, amount);
        return true;
    }

    // ── Validator staking ─────────────────────────────────────────────────

    function stake(uint256 amount) external {
        if (_balances[msg.sender] < amount)
            revert InsufficientBalance(_balances[msg.sender], amount);
        if (stake_balance[msg.sender] + amount < MIN_VALIDATOR_STAKE)
            revert InsufficientStake(stake_balance[msg.sender] + amount, MIN_VALIDATOR_STAKE);

        _balances[msg.sender] -= amount;
        stake_balance[msg.sender] += amount;
        total_staked += amount;
        emit Staked(msg.sender, amount);
    }

    function unstake(uint256 amount) external {
        if (stake_balance[msg.sender] < amount)
            revert InsufficientBalance(stake_balance[msg.sender], amount);

        stake_balance[msg.sender] -= amount;
        total_staked -= amount;
        _balances[msg.sender] += amount;
        emit Unstaked(msg.sender, amount);
    }

    // ── Signal access fee (burned) ─────────────────────────────────────────

    function paySignalFee() external {
        uint256 fee = signal_access_fee;
        if (_balances[msg.sender] < fee)
            revert InsufficientBalance(_balances[msg.sender], fee);
        _balances[msg.sender] -= fee;
        // Burned — reduces circulating supply (deflationary)
        emit FeeCollected(msg.sender, fee);
        emit Transfer(msg.sender, address(0), fee);
    }

    // ── Admin ─────────────────────────────────────────────────────────────

    function setSignalAccessFee(uint256 new_fee) external {
        if (msg.sender != owner) revert Unauthorized(msg.sender);
        signal_access_fee = new_fee;
    }

    // ── Internal ──────────────────────────────────────────────────────────

    function _transfer(address from, address to, uint256 amount) internal {
        if (_balances[from] < amount)
            revert InsufficientBalance(_balances[from], amount);
        _balances[from] -= amount;
        _balances[to]   += amount;
        emit Transfer(from, to, amount);
    }

    function _mint(address to, uint256 amount) internal {
        _balances[to] += amount;
        emit Transfer(address(0), to, amount);
    }
}
