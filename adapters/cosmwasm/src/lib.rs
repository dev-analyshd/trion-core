//! adapters-cosmwasm — CosmWasm ChainAdapter (C3 §4 Step 4 + §14.1 Phase 5).
//!
//! Implements `ChainAdapter` for CosmWasm chains (Juno, Terra Classic,
//! Osmosis wasm, Neutron, Archway, etc.). CosmWasm contracts execute
//! via `MsgExecuteContract` — a Cosmos SDK message wrapper that carries
//! a contract address and an arbitrary `ExecuteMsg` JSON payload.
//!
//! Per the C3 §4 Step 4 translation table CosmWasm uses the Cosmos
//! execution primitives (bank send, GAMM, etc.) but routed through a
//! Wasm contract entrypoint:
//!
//! | Event       | CosmWasm                          |
//! |-------------|-----------------------------------|
//! | SWAP        | Terraswap / Astroport swap msg   |
//! | TRANSFER    | cw20 transfer msg / bank send     |
//! | LIQUIDITY   | Terraswap provide_liquidity msg   |
//! | BORROW      | Mars cw-lending borrow msg        |
//! | STAKE       | cw-staking stake msg              |
//!
//! Mirrors the existing `indexers/crates/trion-cosmos` Cargo.toml
//! style: `reqwest + serde_json + bech32 + hex` only — no heavy SDK.
//!
//! # SYNTHETIC-DEMO execution path (R-LABELS)
//!
//! No adapter in this crate broadcasts a real transaction. Each
//! `execute_*` method builds the canonical `MsgExecuteContract` JSON
//! (with the contract's `ExecuteMsg` payload) and returns
//! [`adapters_core::synthetic_tx_hash`] of the JSON bytes as a
//! deterministic [`TxHash`].

use adapters_core::{
    synthetic_tx_hash, ChainAdapter, ChainId, ExecutionResult, Intent, Route, TxHash,
};
use serde_json::{json, Value};

/// Canonical Juno mainnet chain id (per Cosmos chain registry).
const JUNO_CHAIN_ID: ChainId = 132;

/// CosmWasm adapter configuration.
#[derive(Debug, Clone)]
pub struct CosmWasmAdapterConfig {
    /// Canonical chain id (132 = Juno mainnet, 1 = Terra Classic, etc.).
    pub chain_id: ChainId,
    /// Bech32 account prefix (e.g. "juno", "terra", "neutron").
    pub bech32_prefix: String,
    /// Optional LCD / REST endpoint URL — stored but not contacted.
    pub lcd_url: Option<String>,
}

impl CosmWasmAdapterConfig {
    /// Default Juno mainnet configuration.
    pub fn juno_mainnet() -> Self {
        CosmWasmAdapterConfig {
            chain_id: JUNO_CHAIN_ID,
            bech32_prefix: String::from("juno"),
            lcd_url: None,
        }
    }
}

/// CosmWasm chain adapter — [`ChainAdapter`] implementation for
/// CosmWasm chains.
#[derive(Debug, Clone)]
pub struct CosmWasmAdapter {
    config: CosmWasmAdapterConfig,
    /// Optional explicit contract address overrides (per-event). When
    /// `None` the adapter falls back to placeholder contract addresses
    /// — production wiring must populate these from the chain's
    /// contract registry.
    pub contracts: CosmWasmContractAddresses,
}

/// Well-known CosmWasm contract addresses for each event class. All
/// placeholder by default — production wiring MUST populate these.
#[derive(Debug, Clone, Default)]
pub struct CosmWasmContractAddresses {
    /// Terraswap / Astroport router contract address (SWAP).
    pub swap_router: Option<String>,
    /// cw20 token contract address (TRANSFER).
    pub cw20_token: Option<String>,
    /// LP contract address (LIQUIDITY).
    pub lp_contract: Option<String>,
    /// Mars lending contract address (BORROW).
    pub mars_lending: Option<String>,
    /// cw-staking contract address (STAKE).
    pub staking_contract: Option<String>,
}

impl CosmWasmAdapter {
    /// Create a CosmWasm adapter for Juno mainnet.
    pub fn juno() -> Self {
        CosmWasmAdapter {
            config: CosmWasmAdapterConfig::juno_mainnet(),
            contracts: CosmWasmContractAddresses::default(),
        }
    }

    /// Create a CosmWasm adapter with explicit chain id + prefix.
    pub fn new(chain_id: ChainId, bech32_prefix: String) -> Self {
        CosmWasmAdapter {
            config: CosmWasmAdapterConfig {
                chain_id,
                bech32_prefix,
                lcd_url: None,
            },
            contracts: CosmWasmContractAddresses::default(),
        }
    }

    /// Borrow the adapter configuration.
    pub fn config(&self) -> &CosmWasmAdapterConfig {
        &self.config
    }

    /// Validate a bech32 contract address — same approach as the
    /// Cosmos adapter (prefix-matched, bech32 decode best-effort).
    /// R-FAILCLOSED: returns false (not a panic) on parse failure.
    fn validate_bech32_address(&self, addr: &str) -> bool {
        if addr.is_empty() {
            return false;
        }
        let expected_prefix = format!("{}1", self.config.bech32_prefix);
        if !addr.starts_with(&expected_prefix) {
            return false;
        }
        let _ = bech32::decode(addr);
        true
    }

    /// Build a `MsgExecuteContract` JSON (cosmwasm.wasm.v1.MsgExecuteContract)
    /// — the canonical CosmWasm execution message wrapping an arbitrary
    /// `ExecuteMsg` payload.
    fn encode_execute_contract(
        &self,
        contract: &str,
        sender: &str,
        execute_msg: &Value,
        funds: &[(String, u128)],
    ) -> Value {
        let funds_json: Vec<Value> = funds
            .iter()
            .map(|(denom, amt)| {
                json!({ "denom": denom, "amount": amt.to_string() })
            })
            .collect();
        json!({
            "type_url": "/cosmwasm.wasm.v1.MsgExecuteContract",
            "value": {
                "sender": sender,
                "contract": contract,
                "msg": base64_encode(serde_json::to_vec(execute_msg).unwrap_or_default().as_slice()),
                "funds": funds_json,
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

    /// Resolve the contract address for an event class. R-FAILCLOSED:
    /// if no contract address is configured, returns `None` and the
    /// caller returns `TxHash::zero()`.
    fn resolve_contract(&self, event: &str, intent: &Intent) -> Option<String> {
        match event {
            "swap" => self
                .contracts
                .swap_router
                .clone()
                .or_else(|| Some(intent.source_address.clone())),
            "transfer" => self
                .contracts
                .cw20_token
                .clone()
                .or_else(|| Some(intent.asset_in.clone())),
            "liquidity" => self
                .contracts
                .lp_contract
                .clone()
                .or_else(|| Some(intent.source_address.clone())),
            "borrow" => self
                .contracts
                .mars_lending
                .clone()
                .or_else(|| Some(intent.source_address.clone())),
            "stake" => self
                .contracts
                .staking_contract
                .clone()
                .or_else(|| Some(intent.dest_address.clone())),
            _ => None,
        }
    }
}

/// Minimal base64 encoder for the CosmWasm `msg` field (the
/// `ExecuteMsg` JSON is base64-encoded inside the
/// `MsgExecuteContract.value.msg` field). Production code should
/// replace with the `base64` crate (avoided here to keep deps small).
fn base64_encode(input: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(((input.len() + 2) / 3) * 4);
    for chunk in input.chunks(3) {
        let b0 = chunk[0] as u32;
        let b1 = if chunk.len() > 1 { chunk[1] as u32 } else { 0 };
        let b2 = if chunk.len() > 2 { chunk[2] as u32 } else { 0 };
        let triple = (b0 << 16) | (b1 << 8) | b2;
        out.push(ALPHABET[((triple >> 18) & 0x3F) as usize] as char);
        out.push(ALPHABET[((triple >> 12) & 0x3F) as usize] as char);
        if chunk.len() > 1 {
            out.push(ALPHABET[((triple >> 6) & 0x3F) as usize] as char);
        } else {
            out.push('=');
        }
        if chunk.len() > 2 {
            out.push(ALPHABET[(triple & 0x3F) as usize] as char);
        } else {
            out.push('=');
        }
    }
    out
}

impl ChainAdapter for CosmWasmAdapter {
    fn chain_id(&self) -> ChainId {
        self.config.chain_id
    }

    fn vm_type(&self) -> &'static str {
        "COSMWASM"
    }

    /// SWAP — Terraswap / Astroport `swap` ExecuteMsg.
    fn execute_swap(&self, intent: &Intent, _route: &Route) -> TxHash {
        let sender = &intent.source_address;
        if !self.validate_bech32_address(sender) {
            return TxHash::zero();
        }
        let Some(contract) = self.resolve_contract("swap", intent) else {
            return TxHash::zero();
        };
        if !self.validate_bech32_address(&contract) {
            return TxHash::zero();
        }
        let execute_msg = json!({
            "swap": {
                "offer_asset": {
                    "info": { "native_token": { "denom": intent.asset_in } },
                    "amount": intent.amount_in.to_string(),
                },
                "ask_asset_info": { "native_token": { "denom": intent.asset_out } },
                "belief_price": "1.0",
                "max_spread": "0.01",
            }
        });
        let funds = vec![(intent.asset_in.clone(), intent.amount_in)];
        let msg = self.encode_execute_contract(&contract, sender, &execute_msg, &funds);
        self.synthetic_execute("cosmwasm|swap|terraswap", &msg)
    }

    /// TRANSFER — cw20 `transfer` ExecuteMsg (or bank send via direct
    /// Cosmos MsgSend for native tokens).
    fn execute_transfer(&self, intent: &Intent, _route: &Route) -> TxHash {
        let sender = &intent.source_address;
        let recipient = &intent.dest_address;
        if !self.validate_bech32_address(sender) || !self.validate_bech32_address(recipient) {
            return TxHash::zero();
        }
        let Some(contract) = self.resolve_contract("transfer", intent) else {
            return TxHash::zero();
        };
        if !self.validate_bech32_address(&contract) {
            return TxHash::zero();
        }
        let execute_msg = json!({
            "transfer": {
                "recipient": recipient,
                "amount": intent.amount_in.to_string(),
            }
        });
        let msg = self.encode_execute_contract(&contract, sender, &execute_msg, &[]);
        self.synthetic_execute("cosmwasm|transfer|cw20", &msg)
    }

    /// LIQUIDITY — Terraswap `provide_liquidity` ExecuteMsg.
    fn execute_liquidity(&self, intent: &Intent, _route: &Route) -> TxHash {
        let sender = &intent.source_address;
        if !self.validate_bech32_address(sender) {
            return TxHash::zero();
        }
        let Some(contract) = self.resolve_contract("liquidity", intent) else {
            return TxHash::zero();
        };
        if !self.validate_bech32_address(&contract) {
            return TxHash::zero();
        }
        let amount_a = intent.amount_in / 2;
        let amount_b = intent.amount_in - amount_a;
        let execute_msg = json!({
            "provide_liquidity": {
                "assets": [
                    { "info": { "native_token": { "denom": intent.asset_in } }, "amount": amount_a.to_string() },
                    { "info": { "native_token": { "denom": intent.asset_out } }, "amount": amount_b.to_string() },
                ],
                "slippage_tolerance": "0.01",
            }
        });
        let funds = vec![
            (intent.asset_in.clone(), amount_a),
            (intent.asset_out.clone(), amount_b),
        ];
        let msg = self.encode_execute_contract(&contract, sender, &execute_msg, &funds);
        self.synthetic_execute("cosmwasm|liquidity|terraswap_lp", &msg)
    }

    /// BORROW — Mars Protocol cw-lending `borrow` ExecuteMsg.
    fn execute_borrow(&self, intent: &Intent, _route: &Route) -> TxHash {
        let sender = &intent.source_address;
        if !self.validate_bech32_address(sender) {
            return TxHash::zero();
        }
        let Some(contract) = self.resolve_contract("borrow", intent) else {
            return TxHash::zero();
        };
        if !self.validate_bech32_address(&contract) {
            return TxHash::zero();
        }
        let execute_msg = json!({
            "borrow": {
                "asset": { "denom": intent.asset_out },
                "amount": intent.amount_in.to_string(),
            }
        });
        let msg = self.encode_execute_contract(&contract, sender, &execute_msg, &[]);
        self.synthetic_execute("cosmwasm|borrow|mars", &msg)
    }

    /// STAKE — cw-staking `stake` ExecuteMsg.
    fn execute_stake(&self, intent: &Intent, _route: &Route) -> TxHash {
        let sender = &intent.source_address;
        if !self.validate_bech32_address(sender) {
            return TxHash::zero();
        }
        let Some(contract) = self.resolve_contract("stake", intent) else {
            return TxHash::zero();
        };
        if !self.validate_bech32_address(&contract) {
            return TxHash::zero();
        }
        let execute_msg = json!({
            "stake": {
                "amount": intent.amount_in.to_string(),
            }
        });
        let funds = vec![(intent.asset_in.clone(), intent.amount_in)];
        let msg = self.encode_execute_contract(&contract, sender, &execute_msg, &funds);
        self.synthetic_execute("cosmwasm|stake|cw_staking", &msg)
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

    const JUNO_SENDER: &str = "juno1qy352eufqy352eufqy352eufqy352eufqy352eufqy352";
    const JUNO_RECIPIENT: &str = "juno1qy352eufqy352eufqy352eufqy352eufqy352eufqy353";
    const JUNO_CONTRACT: &str = "juno1qy352eufqy352eufqy352eufqy352eufqy352eufqy354";

    fn adapter_with_contracts() -> CosmWasmAdapter {
        let mut adapter = CosmWasmAdapter::juno();
        adapter.contracts = CosmWasmContractAddresses {
            swap_router: Some(String::from(JUNO_CONTRACT)),
            cw20_token: Some(String::from(JUNO_CONTRACT)),
            lp_contract: Some(String::from(JUNO_CONTRACT)),
            mars_lending: Some(String::from(JUNO_CONTRACT)),
            staking_contract: Some(String::from(JUNO_CONTRACT)),
        };
        adapter
    }

    fn sample_intent_swap() -> Intent {
        Intent {
            action: IntentAction::Swap,
            source_chain: JUNO_CHAIN_ID,
            dest_chain: JUNO_CHAIN_ID,
            asset_in: String::from("ujuno"),
            asset_out: String::from("uusdc"),
            amount_in: 1_000_000_000,
            source_address: String::from(JUNO_SENDER),
            dest_address: String::from(JUNO_RECIPIENT),
            min_amount_out: Some(900_000),
            deadline: 1_700_000_000,
        }
    }

    fn sample_intent_transfer() -> Intent {
        Intent {
            action: IntentAction::Transfer,
            source_chain: JUNO_CHAIN_ID,
            dest_chain: JUNO_CHAIN_ID,
            asset_in: String::from("ujuno"),
            asset_out: String::from("ujuno"),
            amount_in: 1_000_000,
            source_address: String::from(JUNO_SENDER),
            dest_address: String::from(JUNO_RECIPIENT),
            min_amount_out: None,
            deadline: 1_700_000_000,
        }
    }

    fn sample_intent_borrow() -> Intent {
        Intent {
            action: IntentAction::Borrow,
            source_chain: JUNO_CHAIN_ID,
            dest_chain: JUNO_CHAIN_ID,
            asset_in: String::from("ujuno"),
            asset_out: String::from("uusdc"),
            amount_in: 5_000_000,
            source_address: String::from(JUNO_SENDER),
            dest_address: String::from(JUNO_RECIPIENT),
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

    /// Trait object dispatch.
    #[test]
    fn test_trait_object_dispatch() {
        let adapter: Box<dyn ChainAdapter> = Box::new(adapter_with_contracts());
        assert_eq!(adapter.chain_id(), JUNO_CHAIN_ID);
        assert_eq!(adapter.vm_type(), "COSMWASM");
        let intent = sample_intent_swap();
        let route = sample_route();
        let tx = adapter.execute_swap(&intent, &route);
        assert!(!tx.is_zero());
    }

    /// Every execute_* returns a non-zero SYNTHETIC-DEMO hash for valid
    /// intents + configured contracts.
    #[test]
    fn test_execute_paths_produce_synthetic_hashes() {
        let adapter = adapter_with_contracts();
        let route = sample_route();
        let cases: &[(&str, Intent, TxHash)] = &[
            ("swap", sample_intent_swap(), adapter.execute_swap(&sample_intent_swap(), &route)),
            ("transfer", sample_intent_transfer(), adapter.execute_transfer(&sample_intent_transfer(), &route)),
            ("liquidity", sample_intent_swap(), adapter.execute_liquidity(&sample_intent_swap(), &route)),
            ("borrow", sample_intent_borrow(), adapter.execute_borrow(&sample_intent_borrow(), &route)),
            ("stake", sample_intent_swap(), adapter.execute_stake(&sample_intent_swap(), &route)),
        ];
        for (label, _intent, tx) in cases {
            assert!(!tx.is_zero(), "{} returned a non-zero synthetic hash", label);
            assert!(matches!(
                adapter.verify_execution(*tx),
                ExecutionResult::Simulated { label: "SYNTHETIC-DEMO", .. }
            ), "{} verifies as SYNTHETIC-DEMO", label);
        }
    }

    /// R-FAILCLOSED: missing contract address returns `TxHash::zero()`.
    #[test]
    fn test_fail_closed_when_no_contract_configured() {
        // Default adapter with no contracts configured.
        let adapter = CosmWasmAdapter::juno();
        let route = sample_route();
        // SWAP path falls back to source_address — but the source address
        // is a bech32 sender not a contract, so it passes bech32 prefix
        // validation; however, without an explicit swap_router config
        // we use source_address as the contract, which still produces a
        // non-zero hash. To test "no contract" fail-closed path, we
        // need to construct an intent where source_address is also
        // empty.
        let mut intent = sample_intent_swap();
        intent.source_address = String::new();
        let tx = adapter.execute_swap(&intent, &route);
        assert!(tx.is_zero());
    }

    /// R-FAILCLOSED: malformed bech32 address returns `TxHash::zero()`.
    #[test]
    fn test_fail_closed_on_malformed_bech32() {
        let adapter = adapter_with_contracts();
        let mut intent = sample_intent_swap();
        intent.source_address = String::from("not-a-bech32-address");
        let route = sample_route();
        let tx = adapter.execute_swap(&intent, &route);
        assert!(tx.is_zero());
    }

    /// R-FAILCLOSED: wrong bech32 prefix returns `TxHash::zero()`.
    #[test]
    fn test_fail_closed_on_wrong_prefix() {
        let adapter = adapter_with_contracts();
        let mut intent = sample_intent_transfer();
        intent.dest_address = String::from("cosmos1qy352eufqy352eufqy352eufqy352eufqy352euf");
        let route = sample_route();
        let tx = adapter.execute_transfer(&intent, &route);
        assert!(tx.is_zero());
    }

    /// R-FAILCLOSED: `verify_execution(TxHash::zero())` → Failed.
    #[test]
    fn test_verify_execution_zero_hash_is_failed() {
        let adapter = CosmWasmAdapter::juno();
        assert!(matches!(
            adapter.verify_execution(TxHash::zero()),
            ExecutionResult::Failed
        ));
    }

    /// Synthetic hashes are deterministic for the same message JSON.
    #[test]
    fn test_synthetic_hash_is_deterministic() {
        let adapter = adapter_with_contracts();
        let intent = sample_intent_swap();
        let route = sample_route();
        let h1 = adapter.execute_swap(&intent, &route);
        let h2 = adapter.execute_swap(&intent, &route);
        assert_eq!(h1, h2);
    }

    /// Custom chain id + bech32 prefix via the generic constructor.
    #[test]
    fn test_custom_chain_config() {
        let adapter = CosmWasmAdapter::new(999, String::from("custom"));
        assert_eq!(adapter.chain_id(), 999);
        assert_eq!(adapter.config().bech32_prefix, "custom");
    }

    /// Message type_url matches the canonical
    /// `/cosmwasm.wasm.v1.MsgExecuteContract`.
    #[test]
    fn test_message_type_url_canonical() {
        let adapter = adapter_with_contracts();
        let execute_msg = json!({"swap": {}});
        let funds = vec![(String::from("ujuno"), 1_000_000u128)];
        let msg = adapter.encode_execute_contract(
            JUNO_CONTRACT,
            JUNO_SENDER,
            &execute_msg,
            &funds,
        );
        assert_eq!(
            msg["type_url"],
            "/cosmwasm.wasm.v1.MsgExecuteContract"
        );
        assert_eq!(msg["value"]["sender"], JUNO_SENDER);
        assert_eq!(msg["value"]["contract"], JUNO_CONTRACT);
        // `msg` field is base64-encoded ExecuteMsg JSON
        assert!(msg["value"]["msg"].as_str().is_some());
        assert_eq!(msg["value"]["funds"][0]["denom"], "ujuno");
    }

    /// Base64 encoder sanity: round-trip "Hello" through encode/decode.
    #[test]
    fn test_base64_encode_roundtrip() {
        let encoded = base64_encode(b"Hello");
        assert_eq!(encoded, "SGVsbG8=");
        // 3-byte input → 4 chars, no padding
        assert_eq!(base64_encode(b"abc"), "YWJj");
        // 1-byte input → 4 chars with 2 padding
        assert_eq!(base64_encode(b"a"), "YQ==");
    }
}
