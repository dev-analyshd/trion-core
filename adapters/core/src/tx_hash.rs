//! `TxHash` — chain-agnostic transaction hash newtype.
//!
//! `TxHash::zero()` is the canonical "no transaction broadcast" sentinel
//! returned by every `execute_*` method on fail-closed network error
//! (R-FAILCLOSED). It is provably distinguishable from any real hash
//! because real hashes are SHA-256 / Keccak outputs with negligible
//! collision probability against the all-zero 32-byte pattern.

use serde::{Deserialize, Serialize};
use std::fmt;

/// 32-byte transaction hash. Chain-agnostic: every adapter normalises
/// its native hash representation (EVM Keccak-256, Solana base58Signature,
/// Cosmos TxHash hex, Move Aptos hex, CosmWasm hex) into this 32-byte form.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default, Serialize, Deserialize)]
pub struct TxHash(pub [u8; 32]);

impl TxHash {
    /// The fail-closed sentinel: returned by every `execute_*` method on
    /// network error or when the adapter is not connected. R-FAILCLOSED.
    pub const fn zero() -> Self {
        TxHash([0u8; 32])
    }

    /// Construct from a 32-byte slice (panics if length != 32).
    pub fn from_bytes(bytes: [u8; 32]) -> Self {
        TxHash(bytes)
    }

    /// Construct from a hex string (with or without `0x` prefix).
    pub fn from_hex(s: &str) -> Result<Self, hex::FromHexError> {
        let trimmed = s.trim_start_matches("0x");
        let bytes = hex::decode(trimmed)?;
        if bytes.len() != 32 {
            return Err(hex::FromHexError::InvalidStringLength);
        }
        let mut arr = [0u8; 32];
        arr.copy_from_slice(&bytes);
        Ok(TxHash(arr))
    }

    /// True iff this is the [`TxHash::zero()`] fail-closed sentinel.
    pub fn is_zero(&self) -> bool {
        self.0 == [0u8; 32]
    }

    /// Hex representation with `0x` prefix.
    pub fn to_hex(&self) -> String {
        format!("0x{}", hex::encode(self.0))
    }
}

impl fmt::Display for TxHash {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.to_hex())
    }
}
