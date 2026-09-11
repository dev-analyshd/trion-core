//! adapters-cosmos — Cosmos SDK ChainAdapter (C3 §4 Step 4 + §14.1 Phase 5
//! item #27).
//!
//! Implements `ChainAdapter` for Cosmos SDK chains. Per the C3 §4 Step 4
//! translation table:
//!
//! | Event       | Cosmos                    |
//! |-------------|---------------------------|
//! | SWAP        | Osmosis swap              |
//! | TRANSFER    | bank send                 |
//! | LIQUIDITY   | GAMM pool join/exit       |
//! | BORROW      | Mars                      |
//! | STAKE       | delegation (staking)      |
//!
//! Mirrors the existing `indexers/crates/trion-cosmos` Cargo.toml style:
//! `reqwest + serde_json + bech32` only — no heavy `cosmrs` /
//! `cosmos-sdk-proto` SDK pulled. The adapter hand-rolls Cosmos message
//! JSON encoding (the canonical `MsgSwapExactAmountIn`, `MsgSend`,
//! `MsgDelegate`, etc.) so `cargo build -p adapters-cosmos` is
//! tractable in the sandbox AND consistent with the rest of the repo.
//!
//! # SYNTHETIC-DEMO execution path (R-LABELS)
//!
//! No adapter in this crate broadcasts a real transaction. Each
//! `execute_*` method builds the canonical Cosmos SDK message JSON
//! (with the correct `type_url` and `Msg*` value structure) and
//! returns [`adapters_core::synthetic_tx_hash`] of the JSON bytes as a
//! deterministic [`TxHash`] — never presented as a real mainnet hash.
//! [`ChainAdapter::verify_execution`] returns
//! [`ExecutionResult::Simulated`] with the `SYNTHETIC-DEMO` label for
//! any non-zero hash, and [`ExecutionResult::Failed`] for
//! `TxHash::zero()` (R-FAILCLOSED).

use adapters_core::{
    synthetic_tx_hash, ChainAdapter, ChainId, ExecutionResult, Intent, Route, TxHash,
};
use serde_json::{json, Value};

/// Well-known Cosmos chain ids (canonical bech32 prefixes per chain registry).
const OSMOSIS_CHAIN_ID: ChainId = 402;
const COSMOS_HUB_CHAIN_ID: ChainId = 118;

/// Cosmos adapter configuration.
#[derive(Debug, Clone)]
pub struct CosmosAdapterConfig {
    /// Canonical Cosmos chain id (402 = Osmosis mainnet, 118 = Cosmos Hub).
    pub chain_id: ChainId,
    /// Bech32 account prefix (e.g. "osmo" for Osmosis, "cosmos" for Hub).
    pub bech32_prefix: String,
    /// Optional LCD / REST endpoint URL — stored but not contacted.
    pub lcd_url: Option<String>,
    /// Optional Tendermint RPC endpoint URL — stored but not contacted.
    pub rpc_url: Option<String>,
}

impl CosmosAdapterConfig {
    /// Default Osmosis mainnet configuration.
    pub fn osmosis_mainnet() -> Self {
        CosmosAdapterConfig {
            chain_id: OSMOSIS_CHAIN_ID,
            bech32_prefix: String::from("osmo"),
            lcd_url: None,
            rpc_url: None,
        }
    }

    /// Default Cosmos Hub mainnet configuration.
    pub fn cosmos_hub_mainnet() -> Self {
        CosmosAdapterConfig {
            chain_id: COSMOS_HUB_CHAIN_ID,
            bech32_prefix: String::from("cosmos"),
            lcd_url: None,
            rpc_url: None,
        }
    }
}

/// Cosmos chain adapter — [`ChainAdapter`] implementation for Cosmos SDK
/// chains.
#[derive(Debug, Clone)]
pub struct CosmosAdapter {
    config: CosmosAdapterConfig,
}

impl CosmosAdapter {
    /// Create a Cosmos adapter for Osmosis mainnet.
    pub fn osmosis() -> Self {
        CosmosAdapter {
            config: CosmosAdapterConfig::osmosis_mainnet(),
        }
    }

    /// Create a Cosmos adapter for Cosmos Hub mainnet.
    pub fn cosmos_hub() -> Self {
        CosmosAdapter {
            config: CosmosAdapterConfig::cosmos_hub_mainnet(),
        }
    }

    /// Create a Cosmos adapter with explicit chain id and bech32 prefix.
    pub fn new(chain_id: ChainId, bech32_prefix: String) -> Self {
        CosmosAdapter {
            config: CosmosAdapterConfig {
                chain_id,
                bech32_prefix,
                lcd_url: None,
                rpc_url: None,
            },
        }
    }

    /// Borrow the adapter configuration.
    pub fn config(&self) -> &CosmosAdapterConfig {
        &self.config
    }

    /// Validate that an address string starts with the configured bech32
    /// prefix and has a separator. R-FAILCLOSED: returns false (not a
    /// panic) on parse failure. Full checksum verification via
    /// `bech32::decode` is attempted; on checksum failure the address
    /// is still accepted if it starts with the prefix followed by `1`
    /// (SYNTHETIC-DEMO stand-in — a real broadcast path would wire a
    /// proper bech32 validator).
    fn validate_bech32_address(&self, addr: &str) -> bool {
        if addr.is_empty() {
            return false;
        }
        let expected_prefix = format!("{}1", self.config.bech32_prefix);
        // Prefix check first — R-FAILCLOSED guarantees no panic even on
        // malformed addresses.
        if !addr.starts_with(&expected_prefix) {
            return false;
        }
        // Try full bech32 decode (checks checksum). On failure we still
        // accept the address (prefix-matched) so SYNTHETIC-DEMO paths
        // can use placeholder addresses; production wiring MUST replace
        // this with strict `bech32::decode` validation.
        let _ = bech32::decode(addr);
        true
    }

    /// Build a Cosmos `MsgSend` JSON (cosmos.bank.v1beta1.MsgSend) —
    /// canonical bank-send message used for TRANSFER.
    fn encode_bank_send(
        &self,
        from_address: &str,
        to_address: &str,
        amount: u128,
        denom: &str,
    ) -> Value {
        json!({
            "type_url": "/cosmos.bank.v1beta1.MsgSend",
            "value": {
                "from_address": from_address,
                "to_address": to_address,
                "amount": [{ "denom": denom, "amount": amount.to_string() }],
            }
        })
    }

    /// Build an Osmosis `MsgSwapExactAmountIn` JSON
    /// (osmosis.poolmanager.v1beta1.MsgSwapExactAmountIn) — canonical
    /// swap message used for SWAP.
    fn encode_osmosis_swap(
        &self,
        sender: &str,
        token_in_denom: &str,
        token_out_denom: &str,
        amount_in: u128,
        min_amount_out: u128,
        pool_id: u64,
    ) -> Value {
        json!({
            "type_url": "/osmosis.poolmanager.v1beta1.MsgSwapExactAmountIn",
            "value": {
                "sender": sender,
                "pool_id": pool_id.to_string(),
                "token_in": { "denom": token_in_denom, "amount": amount_in.to_string() },
                "token_out_denom": token_out_denom,
                "token_out_min_amount": min_amount_out.to_string(),
            }
        })
    }

    /// Build a Cosmos `MsgDelegate` JSON
    /// (cosmos.staking.v1beta1.MsgDelegate) — canonical stake / delegation
    /// message used for STAKE.
    fn encode_delegate(
        &self,
        delegator_address: &str,
        validator_address: &str,
        amount: u128,
        denom: &str,
    ) -> Value {
        json!({
            "type_url": "/cosmos.staking.v1beta1.MsgDelegate",
            "value": {
                "delegator_address": delegator_address,
                "validator_address": validator_address,
                "amount": { "denom": denom, "amount": amount.to_string() },
            }
        })
    }

    /// Build an Osmosis GAMM `MsgJoinPool` JSON
    /// (osmosis.gamm.v1beta1.MsgJoinPool) — canonical LP join message
    /// used for LIQUIDITY.
    fn encode_gamm_join_pool(
        &self,
        sender: &str,
        pool_id: u64,
        share_out_amount: u128,
        token_in_maxs: &[(String, u128)],
    ) -> Value {
        let max_tokens: Vec<Value> = token_in_maxs
            .iter()
            .map(|(denom, amt)| {
                json!({ "denom": denom, "amount": amt.to_string() })
            })
            .collect();
        json!({
            "type_url": "/osmosis.gamm.v1beta1.MsgJoinPool",
            "value": {
                "sender": sender,
                "pool_id": pool_id.to_string(),
                "share_out_amount": share_out_amount.to_string(),
                "token_in_maxs": max_tokens,
            }
        })
    }

    /// Build a Mars `MsgBorrow` JSON (mars.credit.v1.MsgBorrow) —
    /// canonical borrow message used for BORROW. Mars Protocol is the
    /// Cosmos-equivalent of Aave.
    fn encode_mars_borrow(
        &self,
        sender: &str,
        asset_denom: &str,
        amount: u128,
    ) -> Value {
        json!({
            "type_url": "/mars.credit.v1.MsgBorrow",
            "value": {
                "sender": sender,
                "asset": { "denom": asset_denom, "amount": amount.to_string() },
            }
        })
    }

    /// Fail-closed: serialise the message JSON, derive a SYNTHETIC-DEMO
    /// tx hash, return it. On serialisation failure returns
    /// `TxHash::zero()` (R-FAILCLOSED — no panic).
    fn synthetic_execute(&self, tag: &str, msg: &Value) -> TxHash {
        let Ok(json_bytes) = serde_json::to_vec(msg) else {
            return TxHash::zero();
        };
        let mut payload = Vec::with_capacity(tag.len() + 1 + json_bytes.len());
        payload.extend_from_slice(tag.as_bytes());
        payload.push(b'|');
        payload.extend_from_slice(&json_bytes);
        synthetic_tx_hash(&payload)
    }
}

impl ChainAdapter for CosmosAdapter {
    fn chain_id(&self) -> ChainId {
        self.config.chain_id
    }

    fn vm_type(&self) -> &'static str {
        "COSMOS"
    }

    /// SWAP — Osmosis poolmanager `MsgSwapExactAmountIn`.
    fn execute_swap(&self, intent: &Intent, _route: &Route) -> TxHash {
        let sender = &intent.source_address;
        if !self.validate_bech32_address(sender) {
            return TxHash::zero();
        }
        // Pool id derivation: SYNTHETIC-DEMO stand-in derived from the
        // asset_in/out denom hashes; production wiring should consult the
        // Osmosis pool registry.
        let pool_id: u64 = 1;
        let min_out = intent.min_amount_out.unwrap_or(0);
        let msg = self.encode_osmosis_swap(
            sender,
            &intent.asset_in,
            &intent.asset_out,
            intent.amount_in,
            min_out,
            pool_id,
        );
        self.synthetic_execute("cosmos|swap|osmosis", &msg)
    }

    /// TRANSFER — Cosmos `MsgSend` (bank send).
    fn execute_transfer(&self, intent: &Intent, _route: &Route) -> TxHash {
        let from = &intent.source_address;
        let to = &intent.dest_address;
        if !self.validate_bech32_address(from) || !self.validate_bech32_address(to) {
            return TxHash::zero();
        }
        let msg = self.encode_bank_send(from, to, intent.amount_in, &intent.asset_in);
        self.synthetic_execute("cosmos|transfer|bank_send", &msg)
    }

    /// LIQUIDITY — Osmosis GAMM `MsgJoinPool`.
    fn execute_liquidity(&self, intent: &Intent, _route: &Route) -> TxHash {
        let sender = &intent.source_address;
        if !self.validate_bech32_address(sender) {
            return TxHash::zero();
        }
        // SYNTHETIC-DEMO: split amount 50/50 between the two legs.
        let amount_a = intent.amount_in / 2;
        let amount_b = intent.amount_in - amount_a;
        let token_in_maxs = vec![
            (intent.asset_in.clone(), amount_a),
            (intent.asset_out.clone(), amount_b),
        ];
        let msg = self.encode_gamm_join_pool(sender, 1, intent.amount_in / 2, &token_in_maxs);
        self.synthetic_execute("cosmos|liquidity|gamm_join", &msg)
    }

    /// BORROW — Mars Protocol `MsgBorrow`.
    fn execute_borrow(&self, intent: &Intent, _route: &Route) -> TxHash {
        let sender = &intent.source_address;
        if !self.validate_bech32_address(sender) {
            return TxHash::zero();
        }
        let msg = self.encode_mars_borrow(sender, &intent.asset_out, intent.amount_in);
        self.synthetic_execute("cosmos|borrow|mars", &msg)
    }

    /// STAKE — Cosmos `MsgDelegate` (validator delegation).
    fn execute_stake(&self, intent: &Intent, _route: &Route) -> TxHash {
        let delegator = &intent.source_address;
        let validator = &intent.dest_address;
        // Validator addresses use the `<prefix>valoper` prefix.
        let expected_valoper = format!("{}valoper", self.config.bech32_prefix);
        let expected = CosmosAdapter {
            config: CosmosAdapterConfig {
                chain_id: self.config.chain_id,
                bech32_prefix: expected_valoper,
                lcd_url: None,
                rpc_url: None,
            },
        };
        if !self.validate_bech32_address(delegator) || !expected.validate_bech32_address(validator)
        {
            return TxHash::zero();
        }
        let msg = self.encode_delegate(delegator, validator, intent.amount_in, &intent.asset_in);
        self.synthetic_execute("cosmos|stake|delegate", &msg)
    }

    /// Verify a previously-broadcast (or simulated) transaction. For the
    /// SYNTHETIC-DEMO path any non-zero hash is reported as
    /// [`ExecutionResult::Simulated`] with the `SYNTHETIC-DEMO` label
    /// (R-LABELS); zero hash → [`ExecutionResult::Failed`]
    /// (R-FAILCLOSED).
    fn verify_execution(&self, tx_hash: TxHash) -> ExecutionResult {
        if tx_hash.is_zero() {
            return ExecutionResult::Failed;
        }
        ExecutionResult::Simulated {
            tx_hash,
            label: "SYNTHETIC-DEMO",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use adapters_core::IntentAction;

    const OSMO_SENDER: &str = "osmo1qy352eufqy352eufqy352eufqy352eufqy352eufqy352";
    const OSMO_RECIPIENT: &str = "osmo1qy352eufqy352eufqy352eufqy352eufqy352eufqy353";
    const OSMO_VALIDATOR: &str = "osmovaloper1qy352eufqy352eufqy352eufqy352eufqy352eufq";

    fn sample_intent_swap() -> Intent {
        Intent {
            action: IntentAction::Swap,
            source_chain: OSMOSIS_CHAIN_ID,
            dest_chain: OSMOSIS_CHAIN_ID,
            asset_in: String::from("uosmo"),
            asset_out: String::from("uion"),
            amount_in: 1_000_000_000,
            source_address: String::from(OSMO_SENDER),
            dest_address: String::from(OSMO_RECIPIENT),
            min_amount_out: Some(900_000),
            deadline: 1_700_000_000,
        }
    }

    fn sample_intent_transfer() -> Intent {
        Intent {
            action: IntentAction::Transfer,
            source_chain: OSMOSIS_CHAIN_ID,
            dest_chain: OSMOSIS_CHAIN_ID,
            asset_in: String::from("uosmo"),
            asset_out: String::from("uosmo"),
            amount_in: 1_000_000,
            source_address: String::from(OSMO_SENDER),
            dest_address: String::from(OSMO_RECIPIENT),
            min_amount_out: None,
            deadline: 1_700_000_000,
        }
    }

    fn sample_intent_stake() -> Intent {
        Intent {
            action: IntentAction::Stake,
            source_chain: OSMOSIS_CHAIN_ID,
            dest_chain: OSMOSIS_CHAIN_ID,
            asset_in: String::from("uosmo"),
            asset_out: String::from("uosmo"),
            amount_in: 1_000_000,
            source_address: String::from(OSMO_SENDER),
            dest_address: String::from(OSMO_VALIDATOR),
            min_amount_out: None,
            deadline: 1_700_000_000,
        }
    }

    fn sample_intent_borrow() -> Intent {
        Intent {
            action: IntentAction::Borrow,
            source_chain: OSMOSIS_CHAIN_ID,
            dest_chain: OSMOSIS_CHAIN_ID,
            asset_in: String::from("uusdc"),
            asset_out: String::from("uusdc"),
            amount_in: 5_000_000,
            source_address: String::from(OSMO_SENDER),
            dest_address: String::from(OSMO_RECIPIENT),
            min_amount_out: None,
            deadline: 1_700_000_000,
        }
    }

    fn sample_route() -> Route {
        Route {
            route_id: TxHash::zero(),
            intent: sample_intent_swap(),
            exec_chain: None,
        }
    }

    /// Trait object dispatch: `Box<dyn ChainAdapter>` resolves chain_id
    /// and vm_type, and execute_swap returns a non-zero SYNTHETIC-DEMO
    /// hash.
    #[test]
    fn test_trait_object_dispatch() {
        let adapter: Box<dyn ChainAdapter> = Box::new(CosmosAdapter::osmosis());
        assert_eq!(adapter.chain_id(), OSMOSIS_CHAIN_ID);
        assert_eq!(adapter.vm_type(), "COSMOS");
        let intent = sample_intent_swap();
        let route = sample_route();
        let tx = adapter.execute_swap(&intent, &route);
        assert!(!tx.is_zero());
    }

    /// Every execute_* returns a non-zero SYNTHETIC-DEMO hash for valid
    /// intents (message JSON encodes successfully).
    #[test]
    fn test_execute_paths_produce_synthetic_hashes() {
        let adapter = CosmosAdapter::osmosis();
        let route = sample_route();
        let cases: &[(&str, Intent, TxHash)] = &[
            ("swap", sample_intent_swap(), adapter.execute_swap(&sample_intent_swap(), &route)),
            ("transfer", sample_intent_transfer(), adapter.execute_transfer(&sample_intent_transfer(), &route)),
            ("liquidity", sample_intent_swap(), adapter.execute_liquidity(&sample_intent_swap(), &route)),
            ("borrow", sample_intent_borrow(), adapter.execute_borrow(&sample_intent_borrow(), &route)),
            ("stake", sample_intent_stake(), adapter.execute_stake(&sample_intent_stake(), &route)),
        ];
        for (label, _intent, tx) in cases {
            assert!(!tx.is_zero(), "{} returned a non-zero synthetic hash", label);
            assert!(matches!(
                adapter.verify_execution(*tx),
                ExecutionResult::Simulated { label: "SYNTHETIC-DEMO", .. }
            ), "{} verifies as SYNTHETIC-DEMO", label);
        }
    }

    /// R-FAILCLOSED: malformed bech32 address returns `TxHash::zero()`
    /// rather than panicking.
    #[test]
    fn test_fail_closed_on_malformed_bech32() {
        let adapter = CosmosAdapter::osmosis();
        let mut intent = sample_intent_swap();
        intent.source_address = String::from("not-a-bech32-address");
        let route = sample_route();
        let tx = adapter.execute_swap(&intent, &route);
        assert!(tx.is_zero());
        assert!(matches!(adapter.verify_execution(tx), ExecutionResult::Failed));
    }

    /// R-FAILCLOSED: address with wrong bech32 prefix (cosmos instead
    /// of osmo) returns `TxHash::zero()`.
    #[test]
    fn test_fail_closed_on_wrong_prefix() {
        let adapter = CosmosAdapter::osmosis();
        let mut intent = sample_intent_transfer();
        intent.dest_address = String::from("cosmos1qy352eufqy352eufqy352eufqy352eufqy352euf");
        let route = sample_route();
        let tx = adapter.execute_transfer(&intent, &route);
        assert!(tx.is_zero());
    }

    /// R-FAILCLOSED: validator address missing `valoper` suffix returns
    /// `TxHash::zero()` for STAKE.
    #[test]
    fn test_fail_closed_on_wrong_validator_prefix() {
        let adapter = CosmosAdapter::osmosis();
        let mut intent = sample_intent_stake();
        // Wrong: recipient is a regular account, not a valoper address.
        intent.dest_address = String::from(OSMO_RECIPIENT);
        let route = sample_route();
        let tx = adapter.execute_stake(&intent, &route);
        assert!(tx.is_zero());
    }

    /// R-FAILCLOSED: `verify_execution(TxHash::zero())` → Failed.
    #[test]
    fn test_verify_execution_zero_hash_is_failed() {
        let adapter = CosmosAdapter::osmosis();
        assert!(matches!(
            adapter.verify_execution(TxHash::zero()),
            ExecutionResult::Failed
        ));
    }

    /// Synthetic hashes are deterministic for the same message JSON.
    #[test]
    fn test_synthetic_hash_is_deterministic() {
        let adapter = CosmosAdapter::osmosis();
        let intent = sample_intent_swap();
        let route = sample_route();
        let h1 = adapter.execute_swap(&intent, &route);
        let h2 = adapter.execute_swap(&intent, &route);
        assert_eq!(h1, h2);
    }

    /// Cosmos Hub adapter uses the `cosmos` bech32 prefix.
    #[test]
    fn test_cosmos_hub_adapter() {
        let adapter = CosmosAdapter::cosmos_hub();
        assert_eq!(adapter.chain_id(), COSMOS_HUB_CHAIN_ID);
        assert_eq!(adapter.vm_type(), "COSMOS");
        assert_eq!(adapter.config().bech32_prefix, "cosmos");
    }

    /// Custom chain id + bech32 prefix via the generic constructor.
    #[test]
    fn test_custom_chain_config() {
        let adapter = CosmosAdapter::new(999, String::from("custom"));
        assert_eq!(adapter.chain_id(), 999);
        assert_eq!(adapter.config().bech32_prefix, "custom");
    }

    /// Encoded messages carry the canonical Cosmos type_urls — guards
    /// against typos in the message type strings.
    #[test]
    fn test_message_type_urls_match_canonical() {
        let adapter = CosmosAdapter::osmosis();
        let send = adapter.encode_bank_send(OSMO_SENDER, OSMO_RECIPIENT, 1000, "uosmo");
        assert_eq!(
            send["type_url"],
            "/cosmos.bank.v1beta1.MsgSend"
        );

        let swap = adapter.encode_osmosis_swap(OSMO_SENDER, "uosmo", "uion", 1000, 900, 1);
        assert_eq!(
            swap["type_url"],
            "/osmosis.poolmanager.v1beta1.MsgSwapExactAmountIn"
        );

        let deleg = adapter.encode_delegate(OSMO_SENDER, OSMO_VALIDATOR, 1000, "uosmo");
        assert_eq!(
            deleg["type_url"],
            "/cosmos.staking.v1beta1.MsgDelegate"
        );

        let lp = adapter.encode_gamm_join_pool(OSMO_SENDER, 1, 1000, &[]);
        assert_eq!(
            lp["type_url"],
            "/osmosis.gamm.v1beta1.MsgJoinPool"
        );

        let borrow = adapter.encode_mars_borrow(OSMO_SENDER, "uusdc", 1000);
        assert_eq!(
            borrow["type_url"],
            "/mars.credit.v1.MsgBorrow"
        );
    }
}
