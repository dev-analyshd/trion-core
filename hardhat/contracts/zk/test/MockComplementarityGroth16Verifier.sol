// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title MockComplementarityGroth16Verifier — testing twin of the
///        snarkjs-generated Groth16 verifier for the
///        zk_complementarity_proof circuit.
/// @dev   Used ONLY by the Hardhat test suite at
///        contracts/zk/test/zk_contracts.test.ts. NOT part of the
///        production deployment surface. The mock returns a configurable
///        bool to enable positive / negative proof verification tests
///        without requiring a real Groth16 trusted setup (per Phase 1 §1
///        BLOCKER: setup time >110s exceeds sandbox timeout).

import { IGroth16Verifier } from "../ComplementarityVerifier.sol";

contract MockComplementarityGroth16Verifier is IGroth16Verifier {
    bool public returnValue;

    constructor(bool _returnValue) {
        returnValue = _returnValue;
    }

    function verifyProof(
        uint256[2] calldata,
        uint256[2][2] calldata,
        uint256[2] calldata,
        uint256[5] calldata
    ) external view returns (bool) {
        return returnValue;
    }
}
