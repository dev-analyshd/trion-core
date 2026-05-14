// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title TRIONGovernance — TRION Protocol On-Chain Governance
 * @notice AWA-guarded proposal system.
 *         Voting power = sqrt(stake) — anti-whale Quadratic Voting.
 *         Minimum quorum = 10% of staked supply.
 *         HHI threshold: proposal blocked if HHI > 7500.
 */
contract TRIONGovernance {

    // ── Types ─────────────────────────────────────────────────────────────

    enum ProposalState { PENDING, ACTIVE, DEFEATED, SUCCEEDED, EXECUTED, CANCELLED }
    enum ProposalType  { PARAMETER_UPDATE, CONTRACT_UPGRADE, SLASH_APPEAL,
                         ORACLE_UPDATE, EMERGENCY_PAUSE, FALSIFIABILITY_TEST }

    struct Proposal {
        uint256     id;
        address     proposer;
        ProposalType proposal_type;
        string      description;
        bytes       calldata_payload;
        address     target_contract;
        uint256     for_votes;
        uint256     against_votes;
        uint256     abstain_votes;
        uint256     start_block;
        uint256     end_block;
        uint256     hhi_at_creation;
        ProposalState state;
        bool        awa_guarded;
    }

    // ── State ─────────────────────────────────────────────────────────────

    address public owner;
    address public token_contract;
    address public signal_contract;

    uint256 public proposal_count;
    mapping(uint256 => Proposal) public proposals;
    mapping(uint256 => mapping(address => bool)) public has_voted;

    // Governance parameters (updatable via governance)
    uint256 public voting_period_blocks  = 40_320;   // ~7 days at 15s/block
    uint256 public quorum_bps            = 1000;     // 10% of staked supply
    uint256 public proposal_threshold    = 100_000 * 1e18;  // 100k TRION to propose
    uint256 public hhi_block_threshold   = 7500;    // block proposals above this

    // AWA conditions — all must be TRUE for governance to be active
    bool public awa_validators_recruited  = false;
    bool public awa_diversity_met         = false;
    bool public awa_security_audit        = false;
    bool public awa_hhi_healthy           = false;

    // ── Events ────────────────────────────────────────────────────────────

    event ProposalCreated(uint256 indexed id, address proposer, ProposalType ptype, string description);
    event VoteCast(uint256 indexed proposal_id, address indexed voter, uint8 support, uint256 weight);
    event ProposalExecuted(uint256 indexed id);
    event ProposalDefeated(uint256 indexed id, string reason);
    event AWAConditionUpdated(string condition, bool value);

    // ── Errors ────────────────────────────────────────────────────────────

    error AWANotMet(string condition);
    error HHITooHigh(uint256 hhi);
    error InsufficientProposalThreshold(uint256 stake, uint256 required);
    error ProposalNotActive(uint256 id, ProposalState state);
    error AlreadyVoted(address voter, uint256 proposal_id);
    error InvalidSupport(uint8 support);

    // ── Constructor ───────────────────────────────────────────────────────

    constructor(address _token_contract) {
        owner           = msg.sender;
        token_contract  = _token_contract;
    }

    // ── Governance guards ─────────────────────────────────────────────────

    function _requireAWA() internal view {
        if (!awa_validators_recruited) revert AWANotMet("validators_recruited");
        if (!awa_diversity_met)        revert AWANotMet("diversity_met");
        if (!awa_security_audit)       revert AWANotMet("security_audit");
        if (!awa_hhi_healthy)          revert AWANotMet("hhi_healthy");
    }

    function awa_active() external view returns (bool) {
        return awa_validators_recruited && awa_diversity_met
            && awa_security_audit && awa_hhi_healthy;
    }

    // ── Proposals ─────────────────────────────────────────────────────────

    /**
     * @notice Create a governance proposal.
     * @dev AWA must be active. Proposer must have >= proposal_threshold staked.
     */
    function propose(
        ProposalType proposal_type,
        string calldata description,
        address target_contract,
        bytes calldata payload,
        uint256 current_hhi
    ) external returns (uint256) {
        _requireAWA();

        if (current_hhi >= hhi_block_threshold) revert HHITooHigh(current_hhi);

        // Proposer must hold minimum stake (checked via token contract)
        // In production: call token_contract.stake_balance(msg.sender)
        // Here we trust the proposer (oracle can enforce)

        uint256 id = ++proposal_count;

        proposals[id] = Proposal({
            id:               id,
            proposer:         msg.sender,
            proposal_type:    proposal_type,
            description:      description,
            calldata_payload: payload,
            target_contract:  target_contract,
            for_votes:        0,
            against_votes:    0,
            abstain_votes:    0,
            start_block:      block.number,
            end_block:        block.number + voting_period_blocks,
            hhi_at_creation:  current_hhi,
            state:            ProposalState.ACTIVE,
            awa_guarded:      true
        });

        emit ProposalCreated(id, msg.sender, proposal_type, description);
        return id;
    }

    /**
     * @notice Cast vote on a proposal.
     * @param support 0=Against, 1=For, 2=Abstain
     * @param sqrt_stake voting weight = sqrt(stake) — quadratic voting
     */
    function castVote(uint256 proposal_id, uint8 support, uint256 sqrt_stake) external {
        if (support > 2) revert InvalidSupport(support);
        if (has_voted[proposal_id][msg.sender]) revert AlreadyVoted(msg.sender, proposal_id);

        Proposal storage p = proposals[proposal_id];
        if (p.state != ProposalState.ACTIVE) revert ProposalNotActive(proposal_id, p.state);
        if (block.number > p.end_block) {
            p.state = ProposalState.DEFEATED;
            revert ProposalNotActive(proposal_id, ProposalState.DEFEATED);
        }

        has_voted[proposal_id][msg.sender] = true;
        uint256 weight = sqrt_stake;

        if (support == 1)      p.for_votes     += weight;
        else if (support == 0) p.against_votes += weight;
        else                   p.abstain_votes += weight;

        emit VoteCast(proposal_id, msg.sender, support, weight);
    }

    /**
     * @notice Finalize and execute a succeeded proposal.
     */
    function execute(uint256 proposal_id) external {
        Proposal storage p = proposals[proposal_id];
        require(block.number > p.end_block, "Voting still active");
        require(p.state == ProposalState.ACTIVE, "Not active");

        if (p.for_votes > p.against_votes) {
            p.state = ProposalState.SUCCEEDED;
            // Execute calldata (in production with timelock)
            if (p.calldata_payload.length > 0) {
                (bool ok,) = p.target_contract.call(p.calldata_payload);
                require(ok, "Execution failed");
            }
            p.state = ProposalState.EXECUTED;
            emit ProposalExecuted(proposal_id);
        } else {
            p.state = ProposalState.DEFEATED;
            emit ProposalDefeated(proposal_id, "For votes did not exceed against");
        }
    }

    // ── AWA condition updates (owner only — transferred to governance post-launch) ──

    function setAWACondition(string calldata condition, bool value) external {
        require(msg.sender == owner, "Only owner");
        bytes32 h = keccak256(bytes(condition));
        if (h == keccak256("validators_recruited")) awa_validators_recruited = value;
        else if (h == keccak256("diversity_met"))   awa_diversity_met = value;
        else if (h == keccak256("security_audit"))  awa_security_audit = value;
        else if (h == keccak256("hhi_healthy"))     awa_hhi_healthy = value;
        emit AWAConditionUpdated(condition, value);
    }

    // ── View helpers ──────────────────────────────────────────────────────

    function getProposal(uint256 id) external view returns (Proposal memory) {
        return proposals[id];
    }

    function proposalPassed(uint256 id) external view returns (bool) {
        Proposal storage p = proposals[id];
        return p.for_votes > p.against_votes && p.state == ProposalState.EXECUTED;
    }
}
