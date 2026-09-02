// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title BTCPGasAbstraction — BTCP Gap A: Gas Abstraction Layer
 * Users pay in source-chain value (or TRION); the tank covers execution-chain gas.
 * G_total(route) = Σ_chains [G_chain(i) × execution_fraction(i)]
 */

interface IERC20Minimal {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

contract BTCPGasAbstraction {
    error ZeroAddress();
    error ZeroAmount();
    error NotRelayer();
    error NotOwner();
    error QuoteExpired();
    error InsufficientDeposit(uint256 required, uint256 provided);
    error NothingToRefund(bytes32 intentHash);
    error AlreadyClaimed(bytes32 intentHash);
    error DepositAlreadyExists(bytes32 intentHash);   // SECURITY: overwrite guard
    error QuoteNotExpired(bytes32 intentHash);        // SECURITY: refund only after quote expiry
    error OnlyPayer(bytes32 intentHash);              // SECURITY: refund goes to payer only
    error TokenRefundFailed(bytes32 intentHash);      // SECURITY: payer remainder transfer failed

    event QuotePosted(bytes32 indexed intentHash, uint256 gasTotalUsd, uint256 serviceFeeUsd, uint64 expiresAt);
    event DepositPosted(bytes32 indexed intentHash, address indexed payer, address token, uint256 amount);
    event GasCovered(bytes32 indexed intentHash, address indexed payee, uint256 amountUsd, uint64 chain);
    event DepositRefunded(bytes32 indexed intentHash, address indexed payer, uint256 amount);
    /// @notice SECURITY FIX (P1): the payer's unspent remainder (deposit above
    ///         the actual cost: spent gas + earned service fee) refunded at
    ///         coverGas time — previously this was silently forfeited.
    event DepositRemainderRefunded(bytes32 indexed intentHash, address indexed payer, uint256 amount);
    event RelayerUpdated(address oldRelayer, address newRelayer);

    struct Quote {
        uint256 gasTotalUsd;
        uint256 serviceFeeUsd;
        uint64 expiresAt;
        bool active;
    }

    struct Deposit {
        address payer;
        address token;
        uint256 amount;
        bool claimed;
        bool exists;
    }

    address public owner;
    address public relayer;
    uint256 public serviceFeeBps = 150;
    mapping(bytes32 => Quote) public quotes;
    mapping(bytes32 => Deposit) public deposits;
    address public trionToken;
    mapping(address => bool) public acceptedTokens;

    modifier onlyOwner() { if (msg.sender != owner) revert NotOwner(); _; }
    modifier onlyRelayer() { if (msg.sender != relayer && msg.sender != owner) revert NotRelayer(); _; }

    constructor(address _relayer, address _trionToken) {
        if (_relayer == address(0)) revert ZeroAddress();
        owner = msg.sender;
        relayer = _relayer;
        trionToken = _trionToken;
        acceptedTokens[address(0)] = true;
        if (_trionToken != address(0)) acceptedTokens[_trionToken] = true;
    }

    function postQuote(bytes32 intentHash, uint256 gasTotalUsd, uint64 quoteTtlSec) external onlyRelayer {
        if (gasTotalUsd == 0) revert ZeroAmount();
        uint256 fee = (gasTotalUsd * serviceFeeBps) / 10_000;
        quotes[intentHash] = Quote(gasTotalUsd, fee, uint64(block.timestamp + quoteTtlSec), true);
        emit QuotePosted(intentHash, gasTotalUsd, fee, uint64(block.timestamp + quoteTtlSec));
    }

    function depositGas(bytes32 intentHash) external payable {
        if (msg.value == 0) revert ZeroAmount();
        Quote storage q = quotes[intentHash];
        if (!q.active || block.timestamp > q.expiresAt) revert QuoteExpired();
        // SECURITY: a second deposit must never overwrite (and permanently
        // brick) the first depositor's funds.
        if (deposits[intentHash].exists) revert DepositAlreadyExists(intentHash);
        uint256 required = q.gasTotalUsd + q.serviceFeeUsd;
        if (msg.value < required) revert InsufficientDeposit(required, msg.value);
        deposits[intentHash] = Deposit(msg.sender, address(0), msg.value, false, true);
        _activeDepositsEth += msg.value;  // SECURITY: fee-sweep accounting
        emit DepositPosted(intentHash, msg.sender, address(0), msg.value);
    }

    function depositGasToken(bytes32 intentHash, address token, uint256 amount) external {
        if (token == address(0) || amount == 0) revert ZeroAmount();
        if (!acceptedTokens[token]) revert ZeroAddress();
        Quote storage q = quotes[intentHash];
        if (!q.active || block.timestamp > q.expiresAt) revert QuoteExpired();
        // SECURITY: overwrite guard — protects the existing depositor's funds
        if (deposits[intentHash].exists) revert DepositAlreadyExists(intentHash);
        uint256 required = q.gasTotalUsd + q.serviceFeeUsd;
        if (amount < required) revert InsufficientDeposit(required, amount);
        IERC20Minimal(token).transferFrom(msg.sender, address(this), amount);
        deposits[intentHash] = Deposit(msg.sender, token, amount, false, true);
        emit DepositPosted(intentHash, msg.sender, token, amount);
    }

    function coverGas(bytes32 intentHash, address payee, uint64 executionChain, uint256 spentUsd) external onlyRelayer {
        if (payee == address(0)) revert ZeroAddress();
        Deposit storage d = deposits[intentHash];
        if (!d.exists) revert QuoteExpired();
        if (d.claimed) revert AlreadyClaimed(intentHash);
        Quote storage q = quotes[intentHash];
        uint256 payableUsd = spentUsd > q.gasTotalUsd ? q.gasTotalUsd : spentUsd;
        d.claimed = true;
        // SECURITY FIX (P1 — overpayment forfeit): the gas reimbursement is
        // what was actually spent (capped at the quoted gas total) and is NOT
        // scaled up by any deposit overpayment. The payer receives back
        // everything above the actual cost (spent gas + earned service fee).
        // Previously the old proportional formula inflated the payee's share
        // on overpaid deposits and the leftover remainder was frozen in the
        // contract — unrefundable (d.claimed blocks refund()) and unsweepable
        // (still counted in _activeDepositsEth) — so the payer simply lost it.
        uint256 gasReimbursement = payableUsd > d.amount ? d.amount : payableUsd;
        uint256 feePortion = q.serviceFeeUsd;
        if (feePortion + gasReimbursement > d.amount) feePortion = d.amount - gasReimbursement; // defensive rounding clamp
        uint256 remainder = d.amount - gasReimbursement - feePortion;
        if (gasReimbursement == 0) revert ZeroAmount();
        if (d.token == address(0)) {
            // SECURITY: fee-sweep accounting — the deposit is fully settled
            // here (reimbursement + refund + fee), so release it from the
            // active-deposit ledger; only the earned service fee (feePortion)
            // becomes sweepable excess.
            _activeDepositsEth -= d.amount;
            (bool ok, ) = payee.call{value: gasReimbursement}("");
            require(ok, "ETH payout failed");
            if (remainder > 0) {
                (bool refundOk, ) = d.payer.call{value: remainder}("");
                require(refundOk, "ETH remainder refund failed");
                emit DepositRemainderRefunded(intentHash, d.payer, remainder);
            }
        } else {
            IERC20Minimal(d.token).transfer(payee, gasReimbursement);
            if (remainder > 0) {
                if (!IERC20Minimal(d.token).transfer(d.payer, remainder)) {
                    revert TokenRefundFailed(intentHash);
                }
                emit DepositRemainderRefunded(intentHash, d.payer, remainder);
            }
        }
        emit GasCovered(intentHash, payee, payableUsd, executionChain);
    }

    function refund(bytes32 intentHash) external {
        Deposit storage d = deposits[intentHash];
        if (!d.exists || d.claimed) revert NothingToRefund(intentHash);
        // SECURITY: only the payer can pull their own refund back.
        if (msg.sender != d.payer) revert OnlyPayer(intentHash);
        // SECURITY: refund is only permitted once the quote has expired —
        // otherwise a payer could front-run coverGas after execution and
        // strand the relayer's gas costs (race/griefing).
        Quote storage q = quotes[intentHash];
        if (q.active && block.timestamp <= q.expiresAt) revert QuoteNotExpired(intentHash);
        d.claimed = true;
        if (d.token == address(0)) {
            _activeDepositsEth -= d.amount;  // SECURITY: fee-sweep accounting
            (bool ok, ) = d.payer.call{value: d.amount}("");
            require(ok, "ETH refund failed");
        } else {
            IERC20Minimal(d.token).transfer(d.payer, d.amount);
        }
        emit DepositRefunded(intentHash, d.payer, d.amount);
    }

    /// @notice Owner sweep for the unclaimed service-fee remainder after a
    /// deposit has been claimed. Never touches unclaimed deposits.
    function sweepFees(address payable to) external onlyOwner {
        if (to == address(0)) revert ZeroAddress();
        // The contract balance minus still-live (unclaimed, refundable)
        // deposits is accumulated service-fee remainder. We bound the sweep
        // by tracking it lazily: sweep at most the current balance minus the
        // sum of active deposits is not computable on-chain without iteration,
        // so we require every active deposit's funds be accounted via the
        // coveredTotal ledger below.
        uint256 excess = address(this).balance - _activeDepositsEth;
        if (excess == 0) revert ZeroAmount();
        (bool ok, ) = to.call{value: excess}("");
        require(ok, "ETH sweep failed");
        emit FeesSwept(to, excess);
    }

    // ── SECURITY: active ETH-deposit ledger (for safe fee sweeping) ─────────
    uint256 private _activeDepositsEth;
    event FeesSwept(address indexed to, uint256 amount);

    function requiredAmount(bytes32 intentHash) external view returns (uint256) {
        Quote storage q = quotes[intentHash];
        return q.gasTotalUsd + q.serviceFeeUsd;
    }

    function setRelayer(address newRelayer) external onlyOwner {
        if (newRelayer == address(0)) revert ZeroAddress();
        emit RelayerUpdated(relayer, newRelayer);
        relayer = newRelayer;
    }

    function setServiceFee(uint256 newBps) external onlyOwner {
        if (newBps > 1_000) revert ZeroAmount();
        serviceFeeBps = newBps;
    }

    receive() external payable {}
}
