// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.20;

import "./ITRIONOracle.sol";

// TRION SHIELD — Pre-Execution Behavioral Firewall
// Integrates into any protocol with one modifier:
//   modifier onlyWhenCoherent(bytes32 txId) {
//       firewall.gate(msg.sender, asset, amount, txId, false);
//       _;
//   }

contract TRIONFirewall {

    ITRIONOracle public immutable oracle;
    address      public immutable protectedProtocol;

    uint256 public constant NL_MINIMUM     = 300_000;   // 0.30 × 1e6
    uint256 public constant MF_MAXIMUM     = 700_000;   // 0.70 × 1e6
    uint256 public constant COHERENCE_MIN  = 400_000;   // 0.40 × 1e6
    uint256 public constant FLASH_DISCOUNT = 150_000;   // 0.15 discount

    uint256 public totalApproved;
    uint256 public totalBlocked;
    uint256 public totalValueProtected;
    uint256 public totalAttacksDetected;

    event FirewallApproved(address indexed caller, address indexed asset,
                           uint256 amount, uint256 nlScore, uint256 coherence);
    event FirewallBlocked(address indexed caller, address indexed asset,
                          uint256 amount, uint8 reason, uint256 signalValue,
                          string humanReason);
    event AttackDetected(address indexed attacker, uint8 fingerprint,
                         uint256 mfScore, uint256 blockNumber);

    uint8 constant BLOCK_LIQUIDITY  = 0;
    uint8 constant BLOCK_MANIP      = 1;
    uint8 constant BLOCK_SILENCE    = 2;
    uint8 constant BLOCK_COHERENCE  = 3;

    constructor(address _oracle, address _protocol) {
        oracle            = ITRIONOracle(_oracle);
        protectedProtocol = _protocol;
    }

    function gate(
        address caller,
        address assetIn,
        uint256 amountIn,
        bytes32 routeId,
        bool    isFlashLoan
    ) external returns (bool) {

        // CHECK 1: Natural Liquidity Score
        (uint256 nl,) = oracle.getNLScore(assetIn);
        uint256 effectiveNL = isFlashLoan && nl > FLASH_DISCOUNT
            ? nl - FLASH_DISCOUNT : nl;

        if (effectiveNL < NL_MINIMUM) {
            totalBlocked++;
            emit FirewallBlocked(caller, assetIn, amountIn, BLOCK_LIQUIDITY,
                effectiveNL, "LIQUIDITY_HEALTH: Pool liquidity insufficient");
            revert("TRION: NL below minimum. Pool cannot safely absorb this tx.");
        }

        // CHECK 2: Manipulation Fingerprint
        (uint256 mfScore, uint8 fp) = oracle.getMFScore(caller);
        if (mfScore > MF_MAXIMUM) {
            totalBlocked++;
            totalAttacksDetected++;
            emit AttackDetected(caller, fp, mfScore, block.number);
            emit FirewallBlocked(caller, assetIn, amountIn, BLOCK_MANIP,
                mfScore, "MANIPULATION_ALERT: Behavioral pattern indicates attack");
            revert("TRION: MANIPULATION_ALERT. Behavioral pattern blocked.");
        }

        // CHECK 3: Route Verification
        if (routeId != bytes32(0)) {
            (bool isSafe,,) = oracle.verifyExecution(routeId);
            if (!isSafe) {
                totalBlocked++;
                emit FirewallBlocked(caller, assetIn, amountIn, BLOCK_SILENCE,
                    0, "SILENCE: Behavioral coherence insufficient");
                revert("TRION: SILENCE. Route not verified by behavioral oracle.");
            }
        }

        totalApproved++;
        totalValueProtected += amountIn;
        emit FirewallApproved(caller, assetIn, amountIn, effectiveNL, COHERENCE_MIN);
        return true;
    }

    function simulate(
        address caller,
        address assetIn,
        uint256 amountIn,
        bool isFlashLoan
    ) external view returns (
        bool   wouldBlock,
        uint8  reason,
        uint256 signalValue,
        uint256 threshold,
        string memory explanation
    ) {
        (uint256 nl,) = oracle.getNLScore(assetIn);
        uint256 effNL = isFlashLoan && nl > FLASH_DISCOUNT ? nl-FLASH_DISCOUNT : nl;

        if (effNL < NL_MINIMUM)
            return (true, BLOCK_LIQUIDITY, effNL, NL_MINIMUM,
                "LIQUIDITY_HEALTH: NL below 0.30 threshold");

        (uint256 mfScore,) = oracle.getMFScore(caller);
        if (mfScore > MF_MAXIMUM)
            return (true, BLOCK_MANIP, mfScore, MF_MAXIMUM,
                "MANIPULATION_ALERT: MF score exceeds threshold");

        return (false, 0, effNL, NL_MINIMUM, "APPROVED: All behavioral checks passed");
    }

    function stats() external view returns (
        uint256, uint256, uint256, uint256
    ) {
        return (totalApproved, totalBlocked, totalValueProtected, totalAttacksDetected);
    }
}
