// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title BTCPGasAbstraction
 * @notice TRION BTCP Gap A — Gas Abstraction Layer (BTCP Master Spec §10 Gap A / Fix J)
 *
 *         Users pay gas in SOURCE-chain value (or TRION token). The abstraction
 *         layer covers EXECUTION-chain gas natively. An entity never needs to
 *         hold the execution chain's gas token.
 *
 *         G_total(route R) = Σ_chains [ G_chain(i) × execution_fraction(i) ]
 *
 * @dev    Flow:
 *           1. Relayer quotes a route: gas_total (USD, 1e6), source chain token.
 *           2. User (or BTCPIntent contract) deposits `amount` of `payment_token`
 *              (address(0) = native ETH) covering the quote + service fee.
 *           3. GasTank pays execution gas on destination chains via relayer
 *              reimbursement — the user never holds dest-chain gas.
 *           4. Refunds on route revert are automatic and permissionless.
 *
 *         Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
 *         License: CC0
 */

interface IERC20Minimal {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

contract BTCPGasAbstraction {
    // ── Errors ────────────────────────────────────────────────────────────────
    error ZeroAddress();
    error ZeroAmount();
    error NotRelayer();
    error NotOwner();
    error QuoteExpired();
    error InsufficientDeposit(uint256 required, uint256 provided);
    error NothingToRefund(bytes32 intentHash);
    error DepositAlreadyClaimed(bytes32 intentHash);

    // ── Events ────────────────────────────────────────────────────────────────
    event QuotePosted(bytes32 indexed intentHash, uint256 gasTotalUsd, uint256 serviceFeeUsd, uint64 expiresAt);
    event DepositPosted(bytes32 indexed intentHash, address indexed payer, address token, uint256 amount);
    event GasCovered(bytes32 indexed intentHash, address indexed executionChainRelayer, uint256 amountUsd, uint64 executionChain);
    event DepositRefunded(bytes32 indexed intentHash, address indexed payer, uint256 amount);
    event RelayerUpdated(address oldRelayer, address newRelayer);
    event ServiceFeeUpdated(uint256 oldBps, uint256 newBps);

    // ── Types ─────────────────────────────────────────────────────────────────
    struct Quote {
        uint256 gasTotalUsd;     // ×1e6 — Σ_chains G_chain(i) × execution_fraction(i)
        uint256 serviceFeeUsd;   // ×1e6 — protocol fee on top of gas
        uint64  expiresAt;       // unix seconds — quote validity window
        bool    active;
    }

    struct Deposit {
        address payer;
        address token;           // address(0) = native ETH
        uint256 amount;          // in token smallest unit
        bool    claimed;
        bool    exists;
    }

    // ── Storage ───────────────────────────────────────────────────────────────
    address public owner;
    address public relayer;

    /// Protocol service fee in basis points on top of the gas quote (default 1.5%).
    uint256 public serviceFeeBps = 150;

    /// intentHash → Quote
    mapping(bytes32 => Quote) public quotes;

    /// intentHash → Deposit
    mapping(bytes32 => Deposit) public deposits;

    /// TRION token accepted for gas payment (optional preferred token).
    address public trionToken;

    /// Accepted payment tokens (address(0) = ETH always accepted).
    mapping(address => bool) public acceptedTokens;

    // ── Modifiers ─────────────────────────────────────────────────────────────
    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyRelayer() {
        if (msg.sender != relayer && msg.sender != owner) revert NotRelayer();
        _;
    }

    // ── Constructor ───────────────────────────────────────────────────────────
    constructor(address _relayer, address _trionToken) {
        if (_relayer == address(0)) revert ZeroAddress();
        owner       = msg.sender;
        relayer     = _relayer;
        trionToken  = _trionToken; // may be address(0) — ETH-only mode
        acceptedTokens[address(0)] = true;
        if (_trionToken != address(0)) acceptedTokens[_trionToken] = true;
    }

    // ── Quote management (relayer) ────────────────────────────────────────────

    /**
     * @notice Post a gas quote for a BTCP intent.
     * @param intentHash   The BTCP intent hash.
     * @param gasTotalUsd  Total predicted gas across all chains, USD ×1e6.
     * @param quoteTtlSec  Validity window of the quote in seconds.
     */
    function postQuote(
        bytes32 intentHash,
        uint256 gasTotalUsd,
        uint64  quoteTtlSec
    ) external onlyRelayer {
        if (gasTotalUsd == 0) revert ZeroAmount();
        uint256 fee = (gasTotalUsd * serviceFeeBps) / 10_000;
        quotes[intentHash] = Quote({
            gasTotalUsd:   gasTotalUsd,
            serviceFeeUsd: fee,
            expiresAt:     uint64(block.timestamp + quoteTtlSec),
            active:        true
        });
        emit QuotePosted(intentHash, gasTotalUsd, fee, uint64(block.timestamp + quoteTtlSec));
    }

    // ── Deposits (user or BTCPIntent on behalf of user) ───────────────────────

    /**
     * @notice Deposit native ETH to cover a route's gas quote.
     * @param intentHash The BTCP intent hash whose quote is being covered.
     */
    function depositGas(bytes32 intentHash) external payable {
        if (msg.value == 0) revert ZeroAmount();
        Quote storage q = quotes[intentHash];
        if (!q.active || block.timestamp > q.expiresAt) revert QuoteExpired();
        uint256 required = q.gasTotalUsd + q.serviceFeeUsd;
        if (msg.value < required) revert InsufficientDeposit(required, msg.value);

        deposits[intentHash] = Deposit({
            payer:   msg.sender,
            token:   address(0),
            amount:  msg.value,
            claimed: false,
            exists:  true
        });
        emit DepositPosted(intentHash, msg.sender, address(0), msg.value);
    }

    /**
     * @notice Deposit an ERC-20 (e.g. TRION) to cover a route's gas quote.
     * @dev     Caller must have approved this contract first.
     */
    function depositGasToken(bytes32 intentHash, address token, uint256 amount) external {
        if (token == address(0) || amount == 0) revert ZeroAmount();
        if (!acceptedTokens[token]) revert ZeroAddress(); // token not accepted
        Quote storage q = quotes[intentHash];
        if (!q.active || block.timestamp > q.expiresAt) revert QuoteExpired();
        uint256 required = q.gasTotalUsd + q.serviceFeeUsd;
        if (amount < required) revert InsufficientDeposit(required, amount);

        IERC20Minimal(token).transferFrom(msg.sender, address(this), amount);
        deposits[intentHash] = Deposit({
            payer:   msg.sender,
            token:   token,
            amount:  amount,
            claimed: false,
            exists:  true
        });
        emit DepositPosted(intentHash, msg.sender, token, amount);
    }

    // ── Gas coverage (relayer, after execution) ───────────────────────────────

    /**
     * @notice Relayer claims gas reimbursement after executing on the destination
     *         chain. Reimbursement is capped at the quoted gas (service fee
     *         always stays in the tank for the protocol).
     * @param intentHash     The intent whose deposit funds the execution.
     * @param relayerPayee   Address receiving the reimbursement (execution chain gas sponsor).
     * @param executionChain TRION chain id of the execution chain (for the event).
     * @param spentUsd       Actual gas spent, USD ×1e6 (≤ quote.gasTotalUsd).
     */
    function coverGas(
        bytes32 intentHash,
        address relayerPayee,
        uint64  executionChain,
        uint256 spentUsd
    ) external onlyRelayer {
        if (relayerPayee == address(0)) revert ZeroAddress();
        Deposit storage d = deposits[intentHash];
        if (!d.exists) revert QuoteExpired();
        if (d.claimed) revert DepositAlreadyClaimed(intentHash);

        Quote storage q = quotes[intentHash];
        uint256 payableUsd = spentUsd;
        if (payableUsd > q.gasTotalUsd) payableUsd = q.gasTotalUsd;

        d.claimed = true;
        _payOut(relayerPayee, d.token, payableUsd, d.amount, q);
        emit GasCovered(intentHash, relayerPayee, payableUsd, executionChain);
    }

    // ── Refunds ───────────────────────────────────────────────────────────────

    /**
     * @notice Permissionless refund when a route reverts or times out.
     *         Returns the FULL deposit (unused gas + service fee) to the payer.
     */
    function refund(bytes32 intentHash) external {
        Deposit storage d = deposits[intentHash];
        if (!d.exists || d.claimed) revert NothingToRefund(intentHash);
        d.claimed = true;

        if (d.token == address(0)) {
            (bool ok, ) = d.payer.call{value: d.amount}("");
            require(ok, "ETH refund failed");
        } else {
            IERC20Minimal(d.token).transfer(d.payer, d.amount);
        }
        emit DepositRefunded(intentHash, d.payer, d.amount);
    }

    // ── Views ─────────────────────────────────────────────────────────────────

    function quoteFor(bytes32 intentHash) external view returns (Quote memory) {
        return quotes[intentHash];
    }

    function depositFor(bytes32 intentHash) external view returns (Deposit memory) {
        return deposits[intentHash];
    }

    /// Total required (gas + fee) for an active quote, USD ×1e6.
    function requiredAmount(bytes32 intentHash) external view returns (uint256) {
        Quote storage q = quotes[intentHash];
        return q.gasTotalUsd + q.serviceFeeUsd;
    }

    // ── Admin ─────────────────────────────────────────────────────────────────

    function setRelayer(address newRelayer) external onlyOwner {
        if (newRelayer == address(0)) revert ZeroAddress();
        emit RelayerUpdated(relayer, newRelayer);
        relayer = newRelayer;
    }

    function setServiceFee(uint256 newBps) external onlyOwner {
        if (newBps > 1_000) revert ZeroAmount(); // cap 10%
        emit ServiceFeeUpdated(serviceFeeBps, newBps);
        serviceFeeBps = newBps;
    }

    function setAcceptedToken(address token, bool accepted) external onlyOwner {
        if (token == address(0)) revert ZeroAddress();
        acceptedTokens[token] = accepted;
    }

    /// Withdraw protocol service-fee surplus only (does not touch user deposits).
    function withdrawFees(address to, address token, uint256 amount) external onlyOwner {
        if (to == address(0) || amount == 0) revert ZeroAmount();
        if (token == address(0)) {
            (bool ok, ) = to.call{value: amount}("");
            require(ok, "ETH withdraw failed");
        } else {
            IERC20Minimal(token).transfer(to, amount);
        }
    }

    receive() external payable {
        // Accept direct gas-tank top-ups (protocol-funded execution buffer).
    }

    // ── Internal ──────────────────────────────────────────────────────────────

    /**
     * @dev Pro-rata payout: converts a USD×1e6 amount to the deposited token
     *      at the deposit's implied rate (amount / requiredUsd). Keeps the
     *      service fee in the tank when the full quote is claimed.
     */
    function _payOut(
        address payee,
        address token,
        uint256 usdAmount,
        uint256 depositAmount,
        Quote storage q
    ) internal {
        uint256 requiredUsd = q.gasTotalUsd + q.serviceFeeUsd;
        if (requiredUsd == 0) revert ZeroAmount();
        uint256 tokenAmount = (usdAmount * depositAmount) / requiredUsd;
        if (tokenAmount == 0) revert ZeroAmount();
        if (tokenAmount > depositAmount) tokenAmount = depositAmount;

        if (token == address(0)) {
            (bool ok, ) = payee.call{value: tokenAmount}("");
            require(ok, "ETH payout failed");
        } else {
            IERC20Minimal(token).transfer(payee, tokenAmount);
        }
    }
}
