// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title HashDNA — Formal Hash_DNA Specification Library (Gap 7 Resolution)
/// @notice keccak256-based behavioral hash for BTCP cross-chain proofs.
/// @dev This is the Solidity on-chain counterpart of core/primitives/hash_dna.py.
///
/// Hash_DNA(event) = keccak256(
///     DOMAIN_SEPARATOR_BEHAVIORAL    // bytes32: domain separation
///     || entity_id                     // bytes32: BEO identifier
///     || event_type_id                 // uint256: 1-20 vocabulary enum
///     || magnitude_normalized          // uint256: 18-decimal normalized
///     || magnitude_currency_id         // bytes32: canonical asset ID
///     || timestamp                     // uint256: unix seconds
///     || block_number                  // uint256: source chain block
///     || block_hash                    // bytes32: source block hash
///     || chain_id                      // uint256: TRION chain identifier
///     || counterparty_id               // bytes32: BEO of counterparty (0 if none)
///     || protocol_id                   // bytes32: canonical protocol identifier
///     || context_hash                  // bytes32: keccak256 of event-specific fields
///     || btcp_version                  // uint32: protocol version
///     || nonce                         // uint256: entity nonce for replay prevention
/// )
///
/// Domain Separation:
///     DOMAIN_SEPARATOR_BEHAVIORAL = keccak256("TRION_BEHAVIORAL_HASH_V1" || chain_id || contract_address)
///
/// Magnitude Normalization:
///     magnitude_normalized = raw_amount × 10^(18 - asset_decimals)
///
/// Canonical Asset Identifier:
///     magnitude_currency_id = keccak256(chain_id_of_origin || contract_address || symbol)
library HashDNA {
    // ── Domain Separator ────────────────────────────────────────────────────

    /// @notice Compute the domain separator for behavioral hashing.
    /// @param chainId         The TRION chain identifier
    /// @param contractAddress The TRION contract address on this chain
    /// @return bytes32 domain separator
    function computeDomainSeparator(
        uint256 chainId,
        address contractAddress
    ) internal pure returns (bytes32) {
        return keccak256(
            abi.encodePacked(
                "TRION_BEHAVIORAL_HASH_V1",  // label
                chainId,                       // 32 bytes
                contractAddress                // 20 bytes
            )
        );
    }

    /// @notice Compute the canonical asset identifier (currency_id).
    /// @param chainIdOfOrigin  The chain where the asset originates
    /// @param contractAddress  The asset's contract address
    /// @param symbol           The asset's symbol (e.g., "USDC")
    /// @return bytes32 canonical asset ID
    function computeCurrencyId(
        uint256 chainIdOfOrigin,
        address contractAddress,
        string memory symbol
    ) internal pure returns (bytes32) {
        return keccak256(
            abi.encodePacked(
                chainIdOfOrigin,    // 32 bytes
                contractAddress,    // 20 bytes
                symbol              // variable
            )
        );
    }

    /// @notice Normalize magnitude to 18 decimals.
    /// @param rawAmount     The raw amount in the asset's native decimals
    /// @param assetDecimals The asset's decimal places
    /// @return uint256 normalized to 18 decimals
    function normalizeMagnitude(
        uint256 rawAmount,
        uint8 assetDecimals
    ) internal pure returns (uint256) {
        if (assetDecimals == 18) {
            return rawAmount;
        } else if (assetDecimals < 18) {
            return rawAmount * (10 ** (18 - assetDecimals));
        } else {
            // assetDecimals > 18 — truncate (lossy)
            return rawAmount / (10 ** (assetDecimals - 18));
        }
    }

    // ── Context Hash Constructors ───────────────────────────────────────────

    /// @notice SWAP context hash: keccak256(asset_in_id || asset_out_id || price || slippage)
    function contextHashSwap(
        bytes32 assetInId,
        bytes32 assetOutId,
        uint256 price,
        uint256 slippageBps
    ) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(assetInId, assetOutId, price, slippageBps));
    }

    /// @notice TRANSFER context hash
    function contextHashTransfer(
        bytes32 assetId,
        uint256 destinationChainId,
        address destinationAddress
    ) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(assetId, destinationChainId, destinationAddress));
    }

    /// @notice BORROW context hash
    function contextHashBorrow(
        bytes32 collateralAssetId,
        bytes32 borrowedAssetId,
        uint256 ltvBps
    ) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(collateralAssetId, borrowedAssetId, ltvBps));
    }

    /// @notice STAKE context hash
    function contextHashStake(
        bytes32 validatorId,
        uint256 durationBlocks,
        bytes32 rewardAssetId
    ) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(validatorId, durationBlocks, rewardAssetId));
    }

    /// @notice LIQUIDITY context hash
    function contextHashLiquidity(
        bytes32 tokenAId,
        bytes32 tokenBId,
        uint256 feeTierBps
    ) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(tokenAId, tokenBId, feeTierBps));
    }

    /// @notice No context → bytes32(0)
    function contextHashNone() internal pure returns (bytes32) {
        return bytes32(0);
    }

    // ── Hash_DNA Computation ────────────────────────────────────────────────

    struct HashDNAEvent {
        bytes32 domainSeparator;       // precomputed via computeDomainSeparator()
        bytes32 entityId;              // BEO identifier
        uint256 eventTypeId;           // 1-20 vocabulary enum
        uint256 magnitudeNormalized;   // 18-decimal normalized
        bytes32 magnitudeCurrencyId;   // canonical asset ID
        uint256 timestamp;             // unix seconds
        uint256 blockNumber;           // source chain block
        bytes32 blockHash;             // source block hash
        uint256 chainId;               // TRION chain identifier
        bytes32 counterpartyId;        // BEO of counterparty (0 if none)
        bytes32 protocolId;            // canonical protocol identifier
        bytes32 contextHash;           // keccak256 of event-specific fields
        uint32 btcpVersion;            // protocol version
        uint256 nonce;                 // entity nonce for replay prevention
    }

    /// @notice Compute Hash_DNA per the formal specification.
    /// @param event The fully-populated HashDNAEvent struct
    /// @return bytes32 keccak256 digest
    function hashDNA(HashDNAEvent memory event) internal pure returns (bytes32) {
        // Validate event type
        require(event.eventTypeId >= 1 && event.eventTypeId <= 20, "INVALID_EVENT_TYPE");

        return keccak256(
            abi.encodePacked(
                event.domainSeparator,        // 32 bytes
                event.entityId,               // 32 bytes
                event.eventTypeId,            // 32 bytes (uint256)
                event.magnitudeNormalized,    // 32 bytes (uint256)
                event.magnitudeCurrencyId,    // 32 bytes
                event.timestamp,              // 32 bytes (uint256)
                event.blockNumber,            // 32 bytes (uint256)
                event.blockHash,              // 32 bytes
                event.chainId,                // 32 bytes (uint256)
                event.counterpartyId,         // 32 bytes
                event.protocolId,             // 32 bytes
                event.contextHash,            // 32 bytes
                event.btcpVersion,            //  4 bytes (uint32)
                event.nonce                   // 32 bytes (uint256)
            )
        );
        // Total packed length: 13 × 32 + 4 = 420 bytes
    }

    /// @notice Convenience: build event struct from raw inputs and compute hash.
    function computeHashDNA(
        bytes32 domainSeparator,
        bytes32 entityId,
        uint256 eventTypeId,
        uint256 rawAmount,
        uint8 assetDecimals,
        bytes32 magnitudeCurrencyId,
        uint256 timestamp,
        uint256 blockNumber,
        bytes32 blockHash,
        uint256 chainId,
        bytes32 counterpartyId,
        bytes32 protocolId,
        bytes32 contextHash,
        uint32 btcpVersion,
        uint256 nonce
    ) internal pure returns (bytes32) {
        HashDNAEvent memory event = HashDNAEvent({
            domainSeparator:      domainSeparator,
            entityId:             entityId,
            eventTypeId:          eventTypeId,
            magnitudeNormalized:  normalizeMagnitude(rawAmount, assetDecimals),
            magnitudeCurrencyId:  magnitudeCurrencyId,
            timestamp:            timestamp,
            blockNumber:          blockNumber,
            blockHash:            blockHash,
            chainId:              chainId,
            counterpartyId:       counterpartyId,
            protocolId:           protocolId,
            contextHash:          contextHash,
            btcpVersion:          btcpVersion,
            nonce:                nonce
        });
        return hashDNA(event);
    }
}
