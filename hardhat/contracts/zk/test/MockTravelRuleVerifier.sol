// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title MockTravelRuleVerifier — testing twin of the snarkjs-generated
///        Groth16 / PLONK verifier for the zk_travel_rule circuit.
/// @dev   Used ONLY by the Hardhat test suite at
///        contracts/zk/test/zk_contracts.test.ts. NOT part of the
///        production deployment surface. The mock returns a configurable
///        bool to enable positive / negative proof verification tests
///        without requiring a real Groth16 trusted setup (per Phase 1 §1
///        BLOCKER: setup time >110s exceeds sandbox timeout).

import { ITravelRuleVerifier, ITravelRuleVerifierNominator } from "../TravelRuleCompliance.sol";

contract MockTravelRuleVerifier is ITravelRuleVerifier, ITravelRuleVerifierNominator {
    bool public returnValue;
    address public nominatorAddr;

    constructor(bool _returnValue) {
        returnValue = _returnValue;
        nominatorAddr = msg.sender;
    }

    function verifyProof(bytes calldata, uint256[] calldata) external view returns (bool) {
        return returnValue;
    }

    function nominator() external view returns (address) {
        return nominatorAddr;
    }

    function setNominator(address successor) external {
        require(msg.sender == nominatorAddr, "NOT_NOMINATOR");
        nominatorAddr = successor;
    }
}
