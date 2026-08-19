//! btcp_version_handler.rs — Semver compatibility, min_verifier routing
//! Per BTCP Master Implementation Spec §Phase 2
//!
//! major (v1→v2): breaking — 6-month transition; unupgraded → OOA
//! minor (v2.0→v2.1): non-breaking — new features optional
//! patch: always backward compatible
//! Upgrade incentive: ADAPTER_VERSION_BONUS routing preference

use crate::types::*;

/// Adapter version bonus — routing preference for latest adapter
pub const ADAPTER_VERSION_BONUS: f64 = 1.1; // 10% routing preference

/// BTCP Version Handler — semver compatibility management
#[derive(Debug, Default)]
pub struct VersionHandler;

impl VersionHandler {
    pub fn new() -> Self {
        VersionHandler
    }

    /// Parse semver string
    pub fn parse_semver(&self, version: &str) -> Option<SemVer> {
        SemVer::parse(version)
    }

    /// Check if verifier is compatible with proof requirements
    /// verifier_version >= min_verifier_version
    pub fn is_compatible(&self, verifier_version: &SemVer, min_version: &SemVer) -> bool {
        verifier_version >= min_version
    }

    /// Check convenience with string inputs
    pub fn check_compatibility(&self, proof_ver: &str, verifier_ver: &str) -> bool {
        let proof = match self.parse_semver(proof_ver) {
            Some(v) => v,
            None => return false,
        };
        let verifier = match self.parse_semver(verifier_ver) {
            Some(v) => v,
            None => return false,
        };
        self.is_compatible(&verifier, &proof)
    }

    /// Determine if version change is breaking
    /// Major version change = breaking
    pub fn is_breaking_change(&self, old_version: &SemVer, new_version: &SemVer) -> bool {
        new_version.major > old_version.major
    }

    /// Calculate BTCP score reduction for outdated chains
    /// Proportionally reduces score based on versions behind
    pub fn version_penalty(&self, current: &SemVer, chain_version: &SemVer) -> f64 {
        let major_behind = current.major.saturating_sub(chain_version.major);
        let minor_behind = current.minor.saturating_sub(chain_version.minor);

        if major_behind > 0 {
            return 0.5; // 50% penalty for major version behind
        }

        // Minor version penalty: 5% per minor version behind, max 20%
        let penalty = (minor_behind as f64 * 0.05).min(0.20);
        penalty
    }

    /// Get adapter version bonus multiplier
    pub fn adapter_version_bonus(&self) -> f64 {
        ADAPTER_VERSION_BONUS
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_semver() {
        let handler = VersionHandler::new();

        let v = handler.parse_semver("2.1.0").unwrap();
        assert_eq!(v.major, 2);
        assert_eq!(v.minor, 1);
        assert_eq!(v.patch, 0);

        assert!(handler.parse_semver("invalid").is_none());
        assert!(handler.parse_semver("1.2").is_none());
    }

    #[test]
    fn test_is_compatible() {
        let handler = VersionHandler::new();

        let verifier = SemVer::new(2, 1, 0);
        let min = SemVer::new(2, 0, 0);
        assert!(handler.is_compatible(&verifier, &min));

        let old_verifier = SemVer::new(1, 9, 0);
        assert!(!handler.is_compatible(&old_verifier, &min));
    }

    #[test]
    fn test_check_compatibility_strings() {
        let handler = VersionHandler::new();
        assert!(handler.check_compatibility("2.0.0", "2.1.0"));
        assert!(!handler.check_compatibility("3.0.0", "2.1.0"));
    }

    #[test]
    fn test_is_breaking_change() {
        let handler = VersionHandler::new();

        assert!(handler.is_breaking_change(&SemVer::new(1, 0, 0), &SemVer::new(2, 0, 0)));
        assert!(!handler.is_breaking_change(&SemVer::new(2, 0, 0), &SemVer::new(2, 1, 0)));
        assert!(!handler.is_breaking_change(&SemVer::new(2, 1, 0), &SemVer::new(2, 1, 5)));
    }

    #[test]
    fn test_version_penalty() {
        let handler = VersionHandler::new();
        let current = SemVer::new(2, 5, 0);

        // Major version behind: heavy penalty
        let old = SemVer::new(1, 0, 0);
        assert_eq!(handler.version_penalty(&current, &old), 0.5);

        // 2 minor versions behind: 10% penalty
        let slightly_old = SemVer::new(2, 3, 0);
        assert_eq!(handler.version_penalty(&current, &slightly_old), 0.10);

        // Up to date: no penalty
        let current_v = SemVer::new(2, 5, 0);
        assert_eq!(handler.version_penalty(&current, &current_v), 0.0);
    }

    #[test]
    fn test_adapter_version_bonus() {
        let handler = VersionHandler::new();
        assert_eq!(handler.adapter_version_bonus(), ADAPTER_VERSION_BONUS);
        assert_eq!(ADAPTER_VERSION_BONUS, 1.1);
    }
}
