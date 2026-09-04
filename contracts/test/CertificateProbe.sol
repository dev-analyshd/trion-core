// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title CertificateProbe — test-only exposure of CanonicalCertificate internals
/// @notice Used by tests/contracts/test_canonical_certificate_sol.py (real EVM
///         via eth_tester) to pin the 346-byte payload, the EVM-family digests
///         and the L4.2 tier quorum against the Python reference encoder and
///         the golden vector. NOT part of the production surface.
import "../solidity/libraries/CanonicalCertificate.sol";

contract CertificateProbe {
    using CanonicalCertificate for CanonicalCertificate.Cert;

    function payload(CanonicalCertificate.Cert calldata cert)
        external
        pure
        returns (bytes memory)
    {
        return CanonicalCertificate.encodePayload(cert);
    }

    function digest(CanonicalCertificate.Cert calldata cert)
        external
        pure
        returns (bytes32)
    {
        return CanonicalCertificate.payloadDigest(cert);
    }

    function ethDigest(CanonicalCertificate.Cert calldata cert)
        external
        pure
        returns (bytes32)
    {
        return CanonicalCertificate.ethSignedDigest(cert);
    }

    function destinationOf(address a) external pure returns (bytes32) {
        return CanonicalCertificate.destinationToBytes32(a);
    }

    function quorum(uint256 signed, uint256 total, uint256 d)
        external
        pure
        returns (bool)
    {
        return CanonicalCertificate.quorumMet(signed, total, d);
    }

    function structural(CanonicalCertificate.Cert calldata cert) external pure {
        CanonicalCertificate.checkStructureAndConsensus(cert);
    }

    function fresh(CanonicalCertificate.Cert calldata cert, uint256 now)
        external
        pure
    {
        CanonicalCertificate.checkFreshness(cert, now);
    }
}
