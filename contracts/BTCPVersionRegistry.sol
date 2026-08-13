// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title BTCPVersionRegistry — Protocol version compatibility tracking
/// @notice Ensures cross-chain BTCP routes only execute between compatible versions.
/// @dev Implements whitepaper BTCP §10 (Version Registry — semver compatibility).
contract BTCPVersionRegistry {
    struct Version {
        uint16 major;
        uint16 minor;
        uint16 patch;
        uint16 minVerifierVersion; // minimum verifier version required to accept
        bool   active;
        uint256 activatedAt;
    }

    /// @notice All registered versions, keyed by versionHash (keccak256(major.minor.patch))
    mapping(bytes32 => Version) public versions;
    bytes32[] public versionList;
    bytes32 public currentVersion;

    /// @notice Feature flags per version (keccak256(versionHash || featureName) => enabled)
    mapping(bytes32 => bool) public featureFlags;

    address public owner;

    event VersionRegistered(bytes32 indexed versionHash, uint16 major, uint16 minor, uint16 patch, uint16 minVerifier);
    event VersionActivated(bytes32 indexed versionHash);
    event VersionDeactivated(bytes32 indexed versionHash);
    event FeatureFlagSet(bytes32 indexed versionHash, string feature, bool enabled);

    modifier onlyOwner() { require(msg.sender == owner, "NOT_OWNER"); _; }

    constructor() {
        owner = msg.sender;
        // Register v1.0.0 as the initial version
        _registerVersion(1, 0, 0, 1);
        _activateVersion(_versionHash(1, 0, 0));
    }

    /// @notice Register a new protocol version.
    function registerVersion(
        uint16 major,
        uint16 minor,
        uint16 patch,
        uint16 minVerifierVersion
    ) external onlyOwner returns (bytes32) {
        return _registerVersion(major, minor, patch, minVerifierVersion);
    }

    function _registerVersion(
        uint16 major,
        uint16 minor,
        uint16 patch,
        uint16 minVerifierVersion
    ) internal returns (bytes32) {
        bytes32 vHash = _versionHash(major, minor, patch);
        require(!versions[vHash].active || versions[vHash].activatedAt == 0, "VERSION_EXISTS");
        versions[vHash] = Version({
            major: major,
            minor: minor,
            patch: patch,
            minVerifierVersion: minVerifierVersion,
            active: false,
            activatedAt: 0
        });
        versionList.push(vHash);
        emit VersionRegistered(vHash, major, minor, patch, minVerifierVersion);
        return vHash;
    }

    /// @notice Activate a version (only one version can be current at a time).
    function activateVersion(bytes32 vHash) external onlyOwner returns (bool) {
        return _activateVersion(vHash);
    }

    function _activateVersion(bytes32 vHash) internal returns (bool) {
        require(versions[vHash].activatedAt == 0 || versions[vHash].active == false, "ALREADY_ACTIVE");
        // Deactivate current
        if (currentVersion != bytes32(0)) {
            versions[currentVersion].active = false;
            emit VersionDeactivated(currentVersion);
        }
        versions[vHash].active = true;
        versions[vHash].activatedAt = block.timestamp;
        currentVersion = vHash;
        emit VersionActivated(vHash);
        return true;
    }

    /// @notice Set a feature flag for a specific version.
    function setFeatureFlag(bytes32 vHash, string calldata feature, bool enabled) external onlyOwner returns (bool) {
        require(versions[vHash].activatedAt > 0, "VERSION_NOT_REGISTERED");
        bytes32 flagHash = keccak256(abi.encodePacked(vHash, feature));
        featureFlags[flagHash] = enabled;
        emit FeatureFlagSet(vHash, feature, enabled);
        return true;
    }

    /// @notice Check if a version is compatible with the current version.
    /// @dev Compatible if same major version and verifier version >= minVerifierVersion.
    function isCompatible(uint16 major, uint16 minor, uint16 patch, uint16 verifierVersion) external view returns (bool) {
        Version storage current = versions[currentVersion];
        if (major != current.major) return false;
        if (verifierVersion < current.minVerifierVersion) return false;
        return true;
    }

    /// @notice Check if a feature is enabled for a version.
    function hasFeature(bytes32 vHash, string calldata feature) external view returns (bool) {
        bytes32 flagHash = keccak256(abi.encodePacked(vHash, feature));
        return featureFlags[flagHash];
    }

    function getCurrentVersion() external view returns (Version memory) {
        return versions[currentVersion];
    }

    function _versionHash(uint16 major, uint16 minor, uint16 patch) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(major, minor, patch));
    }
}
