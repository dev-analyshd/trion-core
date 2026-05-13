use serde::{Deserialize, Serialize};

/// All 20 behavioral event types tracked by TRION
/// Whitepaper Section 2.1
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum EventType {
    Transfer,
    Swap,
    Liquidity,
    Stake,
    Unstake,
    Governance,
    Proposal,
    Borrow,
    Repay,
    Liquidate,
    Bridge,
    Deploy,
    Upgrade,
    Mint,
    Burn,
    OracleUpdate,
    MevCapture,
    FlashLoan,
    Airdrop,
    Claim,
}

impl EventType {
    pub fn type_byte(&self) -> u8 {
        match self {
            Self::Transfer      => 0x00,
            Self::Swap          => 0x01,
            Self::Liquidity     => 0x02,
            Self::Stake         => 0x03,
            Self::Unstake       => 0x04,
            Self::Governance    => 0x05,
            Self::Proposal      => 0x06,
            Self::Borrow        => 0x07,
            Self::Repay         => 0x08,
            Self::Liquidate     => 0x09,
            Self::Bridge        => 0x0A,
            Self::Deploy        => 0x0B,
            Self::Upgrade       => 0x0C,
            Self::Mint          => 0x0D,
            Self::Burn          => 0x0E,
            Self::OracleUpdate  => 0x0F,
            Self::MevCapture    => 0x10,
            Self::FlashLoan     => 0x11,
            Self::Airdrop       => 0x12,
            Self::Claim         => 0x13,
        }
    }
}

impl std::fmt::Display for EventType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{:?}", self)
    }
}
