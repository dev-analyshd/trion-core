// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./interfaces/ITRIONOracleV3.sol";

/**
 * @title AttackSimulator
 * @notice Records immutable on-chain proof that TRION's thermodynamic oracle
 *         would have detected and blocked historical DeFi exploits.
 *
 *         For each historical attack:
 *           1. A real on-chain TRION signal (published by the relayer) is
 *              referenced by its txId.
 *           2. `recordAttackProof` reads C(t) and Θ(t) from the live oracle.
 *           3. If C(t) < Θ(t) (SILENCE), `wouldHaveBlocked = true` is emitted
 *              as a permanent, public on-chain event.
 *           4. `demoAttackBlock` additionally reverts with the SILENCE reason
 *              so the blocked tx appears on Arbiscan as a failed attack.
 *
 * Deployed oracle (Arbitrum Sepolia): 0xb819c63c02Ed5aB49017C0f3f2568A14624658b3
 */
contract AttackSimulator {
    ITRIONOracleV3 public immutable oracle;

    // ─── Events ────────────────────────────────────────────────────────────────

    /**
     * @dev Emitted once per attack proof recording.
     *      coherence and threshold are stored at ×10^6 precision (matching
     *      the oracle's packed uint32 format, where 1e6 == 1.0).
     */
    event AttackProofRecorded(
        string   attackName,
        bytes32  indexed oracleSignalId,
        uint256  historicalBlock,
        bytes32  historicalTxHash,
        uint32   coherence,
        uint32   threshold,
        bool     wouldHaveBlocked
    );

    /**
     * @dev Emitted when a live demo call is blocked by TRION (revert path).
     */
    event AttackDemonstrationBlocked(
        string  attackName,
        bytes32 indexed oracleSignalId,
        uint32  coherence,
        uint32  threshold
    );

    // ─── Constructor ────────────────────────────────────────────────────────────

    constructor(address _oracle) {
        oracle = ITRIONOracleV3(_oracle);
    }

    // ─── Public Functions ───────────────────────────────────────────────────────

    /**
     * @notice Records immutable proof that TRION would have detected an attack.
     *         Always succeeds — the event itself is the on-chain proof.
     *
     * @param attackName      Human-readable label, e.g. "Jimbos Protocol"
     * @param oracleSignalId  bytes32 txId of a real TRION signal already
     *                        on-chain (published by the relayer)
     * @param historicalBlock The Arbitrum block of the historical exploit
     * @param historicalTxHash The keccak256 of the attacker's tx hash
     */
    function recordAttackProof(
        string  calldata attackName,
        bytes32          oracleSignalId,
        uint256          historicalBlock,
        bytes32          historicalTxHash
    ) external {
        (uint8 status, uint32 coherence, uint32 threshold,,) =
            oracle.getSignalInfo(oracleSignalId);

        // status == 1 → C(t) < Θ(t): SILENCE / thermodynamic collapse
        bool wouldHaveBlocked = (status == 1);

        emit AttackProofRecorded(
            attackName,
            oracleSignalId,
            historicalBlock,
            historicalTxHash,
            coherence,
            threshold,
            wouldHaveBlocked
        );
    }

    /**
     * @notice Live demonstration mode: reads the current oracle signal and
     *         REVERTS if TRION is in a SILENCE state, proving real-time
     *         protection. The revert itself appears on Arbiscan as a
     *         "transaction blocked by thermodynamic oracle".
     *
     * @param attackName      Label for the attack being simulated
     * @param oracleSignalId  bytes32 txId of a live on-chain TRION signal
     */
    function demoAttackBlock(
        string  calldata attackName,
        bytes32          oracleSignalId
    ) external {
        (uint8 status, uint32 coherence, uint32 threshold,,) =
            oracle.getSignalInfo(oracleSignalId);

        emit AttackDemonstrationBlocked(attackName, oracleSignalId, coherence, threshold);

        require(
            status != 1,
            "TRION: SILENCE active - transaction blocked by thermodynamic oracle"
        );
    }

    /**
     * @notice Batch-record multiple attack proofs in a single transaction.
     */
    function batchRecordAttackProofs(
        string[]  calldata attackNames,
        bytes32[] calldata oracleSignalIds,
        uint256[] calldata historicalBlocks,
        bytes32[] calldata historicalTxHashes
    ) external {
        require(
            attackNames.length == oracleSignalIds.length &&
            attackNames.length == historicalBlocks.length &&
            attackNames.length == historicalTxHashes.length,
            "AttackSimulator: array length mismatch"
        );

        for (uint256 i = 0; i < attackNames.length; i++) {
            (uint8 status, uint32 coherence, uint32 threshold,,) =
                oracle.getSignalInfo(oracleSignalIds[i]);

            bool wouldHaveBlocked = (status == 1);

            emit AttackProofRecorded(
                attackNames[i],
                oracleSignalIds[i],
                historicalBlocks[i],
                historicalTxHashes[i],
                coherence,
                threshold,
                wouldHaveBlocked
            );
        }
    }
}
