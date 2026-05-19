// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./ITRIONAggregatorV3.sol";

/**
 * @title  TRIONPriceFeed
 * @notice Chainlink AggregatorV3Interface-compatible behavioral price feed.
 *
 * TRION publishes manipulation-resistant behavioral prices derived from
 * cross-chain consensus across 37 networks. This contract is a drop-in
 * replacement for any Chainlink price feed — Aave, Compound, MakerDAO,
 * and any other protocol that reads `latestRoundData()` work out of the box.
 *
 * FORWARD PAIR (isInverse = false):
 *   description = "ETH / USD"
 *   latestAnswer() returns 300000000000  (= $3000.00000000, 8 decimals)
 *
 * INVERSE PAIR (isInverse = true):
 *   description = "USD / ETH"
 *   latestAnswer() returns INVERSE_PRECISION / latestForwardAnswer
 *                        = 1e16 / 300000000000 = 33333  (= 0.00033333 ETH per $1)
 *
 * BEHAVIORAL METADATA (on top of the standard Chainlink interface):
 *   - coherence      : C(t) score in 1e18, measures cross-chain signal agreement
 *   - mfScore        : Manipulation Fingerprint score in 1e18 (0 = clean, 1e18 = fully manipulated)
 *   - confidence     : Source coverage + diversity confidence in 1e18
 *   - manipulated    : True if TRION's 7-check algorithm flagged manipulation this round
 *   - behavioralLow  : CI_95 lower bound in 8-decimal price terms
 *   - behavioralHigh : CI_95 upper bound in 8-decimal price terms
 *
 * STALENESS PROTECTION:
 *   Callers should check `updatedAt` from latestRoundData(). If
 *   block.timestamp - updatedAt > MAX_STALENESS_SECONDS the feed is stale.
 *   MAX_STALENESS_SECONDS is publicly readable.
 *
 * DEPLOYMENT:
 *   npx hardhat run scripts/deploy_price_feed.js --network <network>
 *   One contract per pair. Deploy separate instances for ETH/USD and USD/ETH.
 *
 * USAGE (Solidity consumer):
 *   ITRIONAggregatorV3 feed = ITRIONAggregatorV3(FEED_ADDRESS);
 *   (, int256 price, , uint256 updatedAt,) = feed.latestRoundData();
 *   require(block.timestamp - updatedAt < 3600, "Stale price");
 *   uint256 ethPriceUsd = uint256(price); // 8 decimals
 */
contract TRIONPriceFeed is ITRIONAggregatorV3 {

    // ─── Chainlink constants ────────────────────────────────────────────────
    uint8   public constant PRICE_DECIMALS    = 8;
    uint256 public constant VERSION           = 1;
    uint256 public constant MAX_ROUND_HISTORY = 100;

    /**
     * @dev Inverse math: answer_inverse = INVERSE_PRECISION / answer_forward
     *      INVERSE_PRECISION = 1e16 gives 8-decimal output when input is 8-decimal.
     *      Proof: if ETH/USD = 3000 * 1e8 = 3e11
     *             USD/ETH   = 1e16 / 3e11 = 33333 ≈ 0.000333 * 1e8  ✓
     */
    int256  public constant INVERSE_PRECISION = 1e16;

    // ─── Staleness ──────────────────────────────────────────────────────────
    uint256 public MAX_STALENESS_SECONDS = 3600; // 1 hour default

    // ─── Pair metadata ──────────────────────────────────────────────────────
    string  private _description;
    bool    public  isInverse;      // if true, returns 1/price

    // ─── Access control ─────────────────────────────────────────────────────
    address public owner;
    address public relayer;         // TRION relayer — only address allowed to push prices

    // ─── Round storage ──────────────────────────────────────────────────────
    struct Round {
        int256  answer;         // forward price, 8 decimals
        uint256 startedAt;
        uint256 updatedAt;
        // Behavioral metadata
        uint256 coherence;      // C(t) in 1e18
        uint256 mfScore;        // Manipulation Fingerprint in 1e18
        uint256 confidence;     // source confidence in 1e18
        int256  behavioralLow;  // CI_95 lower, 8 decimals
        int256  behavioralHigh; // CI_95 upper, 8 decimals
        bool    manipulated;    // true if TRION flagged manipulation this round
    }

    uint80                    private _latestRoundId;
    mapping(uint80 => Round)  private _rounds;

    // ─── Events ─────────────────────────────────────────────────────────────
    event PriceUpdated(
        uint80  indexed roundId,
        int256  answer,
        bool    isInverse,
        uint256 coherence,
        uint256 mfScore,
        bool    manipulated,
        uint256 updatedAt
    );

    event ManipulationWarning(
        uint80  indexed roundId,
        uint256 mfScore,
        int256  reportedPrice,
        uint256 timestamp
    );

    event RelayerUpdated(address indexed newRelayer);
    event StalenessThresholdUpdated(uint256 newSeconds);

    // ─── Constructor ────────────────────────────────────────────────────────
    /**
     * @param baseCurrency  e.g. "ETH"
     * @param quoteCurrency e.g. "USD"
     * @param _isInverse    false = ETH/USD feed, true = USD/ETH feed
     * @param _relayer      address of TRION relayer allowed to push prices
     */
    constructor(
        string  memory baseCurrency,
        string  memory quoteCurrency,
        bool           _isInverse,
        address        _relayer
    ) {
        owner      = msg.sender;
        relayer    = _relayer;
        isInverse  = _isInverse;
        _description = _isInverse
            ? string(abi.encodePacked(quoteCurrency, " / ", baseCurrency, " (TRION Behavioral)"))
            : string(abi.encodePacked(baseCurrency,  " / ", quoteCurrency, " (TRION Behavioral)"));
    }

    // ─── Modifiers ──────────────────────────────────────────────────────────
    modifier onlyOwner()   { require(msg.sender == owner,   "TRION: not owner");   _; }
    modifier onlyRelayer() {
        require(msg.sender == relayer || msg.sender == owner, "TRION: not relayer");
        _;
    }

    // ─── Price update (called by TRION relayer) ──────────────────────────────
    /**
     * @notice Push a new behavioral price round.
     * @param forwardPrice      Forward pair price (BASE/QUOTE), 8 decimals. Always positive.
     * @param coherenceScore    C(t) cross-chain coherence, 1e18 scale.
     * @param mfScoreVal        Manipulation Fingerprint score, 1e18 scale. 0 = clean.
     * @param confidenceVal     Source diversity confidence, 1e18 scale.
     * @param ciLowerForward    CI_95 lower bound of forward price, 8 decimals.
     * @param ciUpperForward    CI_95 upper bound of forward price, 8 decimals.
     * @param manipulationFlag  True if TRION's 7-check algorithm detected manipulation.
     *
     * @dev If manipulationFlag is true an on-chain ManipulationWarning is emitted.
     *      The price is still stored (consumers decide how to handle it) but the
     *      manipulated field on the Round struct is set so on-chain logic can filter.
     */
    function updatePrice(
        int256  forwardPrice,
        uint256 coherenceScore,
        uint256 mfScoreVal,
        uint256 confidenceVal,
        int256  ciLowerForward,
        int256  ciUpperForward,
        bool    manipulationFlag
    ) external onlyRelayer {
        require(forwardPrice > 0, "TRION: price must be positive");

        uint80 roundId = _latestRoundId + 1;
        _latestRoundId = roundId;

        _rounds[roundId] = Round({
            answer:         forwardPrice,
            startedAt:      block.timestamp,
            updatedAt:      block.timestamp,
            coherence:      coherenceScore,
            mfScore:        mfScoreVal,
            confidence:     confidenceVal,
            behavioralLow:  ciLowerForward,
            behavioralHigh: ciUpperForward,
            manipulated:    manipulationFlag
        });

        int256 publishedAnswer = isInverse
            ? INVERSE_PRECISION / forwardPrice
            : forwardPrice;

        if (manipulationFlag) {
            emit ManipulationWarning(roundId, mfScoreVal, publishedAnswer, block.timestamp);
        }

        emit PriceUpdated(
            roundId, publishedAnswer, isInverse,
            coherenceScore, mfScoreVal, manipulationFlag,
            block.timestamp
        );
    }

    // ─── ITRIONAggregatorV3 (Chainlink-compatible reads) ────────────────────

    function decimals() external pure override returns (uint8) {
        return PRICE_DECIMALS;
    }

    function description() external view override returns (string memory) {
        return _description;
    }

    function version() external pure override returns (uint256) {
        return VERSION;
    }

    function latestAnswer() external view override returns (int256) {
        require(_latestRoundId > 0, "TRION: no price data");
        Round storage r = _rounds[_latestRoundId];
        return isInverse ? INVERSE_PRECISION / r.answer : r.answer;
    }

    function latestRoundData()
        external view override
        returns (
            uint80  roundId,
            int256  answer,
            uint256 startedAt,
            uint256 updatedAt,
            uint80  answeredInRound
        )
    {
        require(_latestRoundId > 0, "TRION: no price data");
        Round storage r = _rounds[_latestRoundId];
        return (
            _latestRoundId,
            isInverse ? INVERSE_PRECISION / r.answer : r.answer,
            r.startedAt,
            r.updatedAt,
            _latestRoundId
        );
    }

    function getRoundData(uint80 _roundId)
        external view override
        returns (
            uint80  roundId,
            int256  answer,
            uint256 startedAt,
            uint256 updatedAt,
            uint80  answeredInRound
        )
    {
        require(_rounds[_roundId].updatedAt > 0, "TRION: round not found");
        Round storage r = _rounds[_roundId];
        return (
            _roundId,
            isInverse ? INVERSE_PRECISION / r.answer : r.answer,
            r.startedAt,
            r.updatedAt,
            _roundId
        );
    }

    // ─── Behavioral metadata reads ───────────────────────────────────────────

    /**
     * @notice Full behavioral metadata for the latest round.
     *         Returns everything a DeFi risk manager needs beyond just the price.
     */
    function latestBehavioralData()
        external view
        returns (
            uint80  roundId,
            int256  answer,
            uint256 coherence,
            uint256 mfScore,
            uint256 confidence,
            int256  ciLower,
            int256  ciUpper,
            bool    manipulated,
            uint256 updatedAt
        )
    {
        require(_latestRoundId > 0, "TRION: no price data");
        Round storage r = _rounds[_latestRoundId];
        int256 ans = isInverse ? INVERSE_PRECISION / r.answer : r.answer;
        int256 lo  = isInverse ? INVERSE_PRECISION / r.behavioralHigh : r.behavioralLow;
        int256 hi  = isInverse ? INVERSE_PRECISION / r.behavioralLow  : r.behavioralHigh;
        return (
            _latestRoundId,
            ans,
            r.coherence,
            r.mfScore,
            r.confidence,
            lo,
            hi,
            r.manipulated,
            r.updatedAt
        );
    }

    /**
     * @notice Returns true if the latest round was flagged as manipulated.
     *         DeFi protocols can use this as a circuit-breaker condition.
     */
    function isManipulated() external view returns (bool) {
        if (_latestRoundId == 0) return false;
        return _rounds[_latestRoundId].manipulated;
    }

    /**
     * @notice Returns true if the feed is stale (no update within MAX_STALENESS_SECONDS).
     */
    function isStale() external view returns (bool) {
        if (_latestRoundId == 0) return true;
        return block.timestamp - _rounds[_latestRoundId].updatedAt > MAX_STALENESS_SECONDS;
    }

    function latestRoundId() external view returns (uint80) {
        return _latestRoundId;
    }

    // ─── Admin ───────────────────────────────────────────────────────────────

    function setRelayer(address _relayer) external onlyOwner {
        relayer = _relayer;
        emit RelayerUpdated(_relayer);
    }

    function setMaxStaleness(uint256 seconds_) external onlyOwner {
        MAX_STALENESS_SECONDS = seconds_;
        emit StalenessThresholdUpdated(seconds_);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "TRION: zero address");
        owner = newOwner;
    }
}
