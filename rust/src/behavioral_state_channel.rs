//! behavioral_state_channel.rs — BSC open/operate/close lifecycle
//! Per BTCP Master Implementation Spec §Water Principle 7
//!
//! Water as vapor: 50 interactions = 2 on-chain transactions (open + close)
//! = 50× cheaper per interaction. Operates at BIBL layer (inter-block).

use crate::types::*;
use std::collections::HashMap;

/// Behavioral State Channel — off-chain interaction with on-chain anchors
/// Protocol needing 50+ cross-chain interactions per hour.
/// First flow carves the channel. Subsequent flows are near-frictionless.
#[derive(Debug, Default)]
pub struct BehavioralStateChannel {
    channels: HashMap<H256, BehavioralStateChannelData>,
}

impl BehavioralStateChannel {
    pub fn new() -> Self {
        BehavioralStateChannel {
            channels: HashMap::new(),
        }
    }

    /// Open a behavioral state channel between two entities
    /// Both entities lock collateral on their respective chains via BTCP_ESCROW
    pub fn open_bsc(
        &mut self,
        entity_a: BEOId,
        entity_b: BEOId,
        chain_a: ChainId,
        chain_b: ChainId,
        collateral_a: u128,
        collateral_b: u128,
    ) -> H256 {
        let channel_id = H256::sha3(
            format!(
                "{}:{}:{}:{}:{}",
                entity_a.to_hex(),
                entity_b.to_hex(),
                chain_a,
                chain_b,
                current_timestamp()
            )
            .as_bytes(),
        );

        let channel = BehavioralStateChannelData {
            channel_id,
            entity_a,
            entity_b,
            chain_a,
            chain_b,
            collateral_a,
            collateral_b,
            state: ChannelState::Open,
            interaction_count: 0,
            akashic_record: H256::zero(),
        };

        self.channels.insert(channel_id, channel);
        channel_id
    }

    /// Record an interaction within the channel (off-chain, BIBL layer)
    pub fn record_interaction(
        &mut self,
        channel_id: &H256,
        interaction_data: &[u8],
    ) -> bool {
        if let Some(channel) = self.channels.get_mut(channel_id) {
            if channel.state != ChannelState::Open {
                return false;
            }

            channel.interaction_count += 1;

            // Update Akashic record hash
            let new_record = H256::sha3(
                format!(
                    "{}:{}:{}",
                    channel.akashic_record.to_hex(),
                    hex::encode(interaction_data),
                    channel.interaction_count
                )
                .as_bytes(),
            );
            channel.akashic_record = new_record;

            return true;
        }
        false
    }

    /// Close the channel — final Akashic record anchored on-chain
    pub fn close_channel(&mut self, channel_id: &H256) -> Option<H256> {
        if let Some(channel) = self.channels.get_mut(channel_id) {
            if channel.state == ChannelState::Open {
                channel.state = ChannelState::Closing;
                // In production: submit final akashic_record to BTCP_ESCROW
                channel.state = ChannelState::Closed;
                return Some(channel.akashic_record);
            }
        }
        None
    }

    /// Initiate dispute resolution (Conscious Layer 3-of-5)
    pub fn initiate_dispute(&mut self, channel_id: &H256) -> bool {
        if let Some(channel) = self.channels.get_mut(channel_id) {
            if channel.state == ChannelState::Open
                || channel.state == ChannelState::Closing
            {
                channel.state = ChannelState::Disputed;
                return true;
            }
        }
        false
    }

    /// Get channel by ID
    pub fn get_channel(&self, channel_id: &H256) -> Option<&BehavioralStateChannelData> {
        self.channels.get(channel_id)
    }

    /// Get all channels
    pub fn all_channels(&self) -> Vec<&BehavioralStateChannelData> {
        self.channels.values().collect()
    }

    /// Calculate cost savings vs individual on-chain transactions
    pub fn cost_savings(&self, channel_id: &H256) -> Option<f64> {
        self.channels.get(channel_id).map(|c| {
            if c.interaction_count == 0 {
                return 0.0;
            }
            // 2 on-chain tx (open + close) vs N individual tx
            let individual_cost = c.interaction_count as f64;
            let bsc_cost = 2.0;
            (individual_cost - bsc_cost) / individual_cost
        })
    }
}

fn current_timestamp() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_open_and_close_channel() {
        let mut bsc = BehavioralStateChannel::new();

        let entity_a = H256::sha3(b"entity_A");
        let entity_b = H256::sha3(b"entity_B");

        let channel_id = bsc.open_bsc(
            entity_a, entity_b, 42161, 900,
            1_000_000_000_000_000_000u128,
            5_000_000_000u128,
        );

        let channel = bsc.get_channel(&channel_id).unwrap();
        assert_eq!(channel.state, ChannelState::Open);
        assert_eq!(channel.interaction_count, 0);

        let final_record = bsc.close_channel(&channel_id);
        assert!(final_record.is_some());

        let channel = bsc.get_channel(&channel_id).unwrap();
        assert_eq!(channel.state, ChannelState::Closed);
    }

    #[test]
    fn test_record_interactions() {
        let mut bsc = BehavioralStateChannel::new();

        let entity_a = H256::sha3(b"entity_A");
        let entity_b = H256::sha3(b"entity_B");
        let channel_id = bsc.open_bsc(
            entity_a, entity_b, 42161, 900,
            1_000_000_000_000_000_000u128,
            5_000_000_000u128,
        );

        // Record 50 interactions
        for i in 0..50 {
            let success = bsc.record_interaction(&channel_id, format!("interaction_{}", i).as_bytes());
            assert!(success);
        }

        let channel = bsc.get_channel(&channel_id).unwrap();
        assert_eq!(channel.interaction_count, 50);
        assert_ne!(channel.akashic_record, H256::zero());

        // Calculate savings
        let savings = bsc.cost_savings(&channel_id).unwrap();
        println!("Cost savings with 50 interactions: {:.0}%", savings * 100.0);
        assert!(savings > 0.9); // > 90% savings
    }

    #[test]
    fn test_dispute() {
        let mut bsc = BehavioralStateChannel::new();

        let entity_a = H256::sha3(b"entity_A");
        let entity_b = H256::sha3(b"entity_B");
        let channel_id = bsc.open_bsc(
            entity_a, entity_b, 42161, 900,
            1_000_000_000_000_000_000u128,
            5_000_000_000u128,
        );

        assert!(bsc.initiate_dispute(&channel_id));

        let channel = bsc.get_channel(&channel_id).unwrap();
        assert_eq!(channel.state, ChannelState::Disputed);
    }
}
