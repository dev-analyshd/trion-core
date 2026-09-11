//! adapters-move — Move VM ChainAdapter (C3 §4 Step 4 + §14.1 Phase 5
//! item #28).
//!
//! Implements `ChainAdapter` for Move VM chains (Aptos and Sui). Per the
//! C3 §4 Step 4 translation table:
//!
//! | Event       | Move                       |
//! |-------------|----------------------------|
//! | SWAP        | Aptos DEX (e.g. Liquidswap)|
//! | TRANSFER    | coin transfer              |
//! | LIQUIDITY   | liquidity module           |
//! | BORROW      | Aries Markets              |
//! | STAKE       | staking module             |
//!
//! Mirrors the existing `indexers/crates/trion-aptos` Cargo.toml style:
//! `reqwest + serde_json + hex` only — no heavy `aptos-sdk` SDK pulled
//! (would balloon compile time). The adapter hand-rolls Aptos
//! transaction payload JSON encoding (the canonical
//! `entry_function_payload` with module address + function name +
//! type_arguments + arguments).
//!
//! # SYNTHETIC-DEMO execution path (R-LABELS)
//!
//! No adapter in this crate broadcasts a real transaction. Each
//! `execute_*` method builds the canonical Aptos entry_function_payload
//! JSON and returns [`adapters_core::synthetic_tx_hash`] of the JSON
//! bytes as a deterministic [`TxHash`] — never presented as a real
//! mainnet hash. [`ChainAdapter::verify_execution`] returns
//! [`ExecutionResult::Simulated`] with the `SYNTHETIC-DEMO` label for
//! any non-zero hash, and [`ExecutionResult::Failed`] for
//! `TxHash::zero()` (R-FAILCLOSED).

use adapters_core::{
    synthetic_tx_hash, ChainAdapter, ChainId, ExecutionResult, Intent, Route, TxHash,
};
use serde_json::{json, Value};

/// Canonical Aptos mainnet chain id (per Aptos REST API).
const APTOS_MAINNET_CHAIN_ID: ChainId = 1;

/// Canonical Move adapter configuration.
#[derive(Debug, Clone)]
pub struct MoveAdapterConfig {
    /// Canonical Move VM chain id (1 = Aptos mainnet).
    pub chain_id: ChainId,
    /// VM family label — distinguishes Aptos ("APTOS") from Sui ("SUI")
    /// for log lines (R-GENERIC: never in trait method names).
    pub move_flavor: MoveFlavor,
    /// Optional REST API endpoint URL — stored but not contacted.
    pub rest_url: Option<String>,
}

/// Move VM flavour — Aptos or Sui (both use Move but have different
/// transaction payload encodings).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MoveFlavor {
    Aptos,
    Sui,
}

impl MoveFlavor {
    /// Lowercase label for log lines (R-GENERIC: not in method names).
    pub fn as_str(&self) -> &'static str {
        match self {
            MoveFlavor::Aptos => "APTOS",
            MoveFlavor::Sui => "SUI",
        }
    }
}

impl Default for MoveAdapterConfig {
    fn default() -> Self {
        MoveAdapterConfig::aptos_mainnet()
    }
}

impl MoveAdapterConfig {
    /// Default Aptos mainnet configuration.
    pub fn aptos_mainnet() -> Self {
        MoveAdapterConfig {
            chain_id: APTOS_MAINNET_CHAIN_ID,
            move_flavor: MoveFlavor::Aptos,
            rest_url: None,
        }
    }

    /// Default Sui mainnet configuration.
    pub fn sui_mainnet() -> Self {
        MoveAdapterConfig {
            chain_id: 99, // Sui mainnet canonical id per chain registry
            move_flavor: MoveFlavor::Sui,
            rest_url: None,
        }
    }
}

/// Move VM chain adapter — [`ChainAdapter`] implementation for Aptos.
#[derive(Debug, Clone)]
pub struct MoveAdapter {
    config: MoveAdapterConfig,
}

impl MoveAdapter {
    /// Create a Move adapter for Aptos mainnet.
    pub fn aptos() -> Self {
        MoveAdapter {
            config: MoveAdapterConfig::aptos_mainnet(),
        }
    }

    /// Create a Move adapter for Sui mainnet.
    pub fn sui() -> Self {
        MoveAdapter {
            config: MoveAdapterConfig::sui_mainnet(),
        }
    }

    /// Borrow the adapter configuration.
    pub fn config(&self) -> &MoveAdapterConfig {
        &self.config
    }

    /// Validate an Aptos hex address (`0x` + 1-64 hex chars). Aptos
    /// addresses may be displayed with leading zeros omitted (e.g.
    /// `0x1` for the framework address). R-FAILCLOSED: returns false
    /// (not a panic) on parse failure.
    fn validate_aptos_address(&self, addr: &str) -> bool {
        if !addr.starts_with("0x") {
            return false;
        }
        let trimmed = &addr[2..];
        if trimmed.is_empty() || trimmed.len() > 64 {
            return false;
        }
        hex::decode(trimmed).is_ok()
    }

    /// Build an Aptos `entry_function_payload` JSON for a coin transfer
    /// (the canonical `0x1::coin::transfer<CoinType>(address, u64)`
    /// entry function). Used for TRANSFER.
    fn encode_coin_transfer(
        &self,
        coin_type: &str,
        to_address: &str,
        amount: u64,
    ) -> Value {
        json!({
            "type": "entry_function_payload",
            "function": "0x1::coin::transfer",
            "type_arguments": [coin_type],
            "arguments": [to_address, amount.to_string()],
        })
    }

    /// Build an Aptos `entry_function_payload` JSON for a Liquidswap swap
    /// (the canonical
    /// `0xf544c4bf2c6a0e6f0c1e31c6a3ab9a4a0a3a4a0a3a4a0a3a4a0a3a4a0a3a4a::swap::swap_exact_coin_for_coin<X,Y,Z>(...)`
    /// entry function — placeholder module address; production wiring
    /// must populate the real Liquidswap router address).
    fn encode_liquidswap_swap(
        &self,
        router_address: &str,
        from_coin_type: &str,
        to_coin_type: &str,
        amount_in: u64,
        min_amount_out: u64,
    ) -> Value {
        let function_id = format!("{}::swap::swap_exact_coin_for_coin", router_address);
        json!({
            "type": "entry_function_payload",
            "function": function_id,
            "type_arguments": [from_coin_type, to_coin_type, "0x1::aptos_coin::AptosCoin"],
            "arguments": [
                amount_in.to_string(),
                min_amount_out.to_string(),
            ],
        })
    }

    /// Build an Aptos `entry_function_payload` JSON for an Aries Markets
    /// borrow (placeholder module address).
    fn encode_aries_borrow(
        &self,
        market_address: &str,
        asset_coin_type: &str,
        amount: u64,
    ) -> Value {
        let function_id = format!("{}::borrow", market_address);
        json!({
            "type": "entry_function_payload",
            "function": function_id,
            "type_arguments": [asset_coin_type],
            "arguments": [amount.to_string()],
        })
    }

    /// Build an Aptos `entry_function_payload` JSON for a staking module
    /// `add_stake(u64)` (placeholder module address — production wiring
    /// uses the canonical `0x1::stake::add_stake` or a liquid staking
    /// module).
    fn encode_stake(&self, stake_module: &str, amount: u64) -> Value {
        let function_id = format!("{}::add_stake", stake_module);
        json!({
            "type": "entry_function_payload",
            "function": function_id,
            "type_arguments": ["0x1::aptos_coin::AptosCoin"],
            "arguments": [amount.to_string()],
        })
    }

    /// Build an Aptos `entry_function_payload` JSON for adding liquidity
    /// (placeholder module address).
    fn encode_add_liquidity(
        &self,
        lp_module: &str,
        coin_a: &str,
        coin_b: &str,
        amount_a: u64,
        amount_b: u64,
    ) -> Value {
        let function_id = format!("{}::add_liquidity", lp_module);
        json!({
            "type": "entry_function_payload",
            "function": function_id,
            "type_arguments": [coin_a, coin_b],
            "arguments": [
                amount_a.to_string(),
                amount_b.to_string(),
            ],
        })
    }

    /// Fail-closed: serialise the payload JSON, derive a SYNTHETIC-DEMO
    /// tx hash, return it. On serialisation failure returns
    /// `TxHash::zero()` (R-FAILCLOSED — no panic).
    fn synthetic_execute(&self, tag: &str, payload: &Value) -> TxHash {
        let Ok(json_bytes) = serde_json::to_vec(payload) else {
            return TxHash::zero();
        };
        let mut combined = Vec::with_capacity(tag.len() + 1 + json_bytes.len());
        combined.extend_from_slice(tag.as_bytes());
        combined.push(b'|');
        combined.extend_from_slice(&json_bytes);
        synthetic_tx_hash(&combined)
    }
}

impl ChainAdapter for MoveAdapter {
    fn chain_id(&self) -> ChainId {
        self.config.chain_id
    }

    fn vm_type(&self) -> &'static str {
        "MOVE"
    }

    /// SWAP — Liquidswap (or generic Aptos DEX) swap entry function.
    fn execute_swap(&self, intent: &Intent, _route: &Route) -> TxHash {
        // SYNTHETIC-DEMO placeholder router address — production wiring
        // must populate the real Liquidswap / PancakeSwap router.
        let router = "0x2d44c0e6d0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0";
        if !self.validate_aptos_address(router) {
            return TxHash::zero();
        }
        // Truncate u128 amount to u64 (Move amounts are u64).
        let Ok(amount_in) = u64::try_from(intent.amount_in) else {
            return TxHash::zero();
        };
        let min_out = intent
            .min_amount_out
            .and_then(|v| u64::try_from(v).ok())
            .unwrap_or(0);
        let payload = self.encode_liquidswap_swap(
            router,
            &intent.asset_in,
            &intent.asset_out,
            amount_in,
            min_out,
        );
        self.synthetic_execute("move|swap|liquidswap", &payload)
    }

    /// TRANSFER — Aptos `0x1::coin::transfer<CoinType>(to, amount)`.
    fn execute_transfer(&self, intent: &Intent, _route: &Route) -> TxHash {
        let to = &intent.dest_address;
        if !self.validate_aptos_address(to) {
            return TxHash::zero();
        }
        let Ok(amount_u64) = u64::try_from(intent.amount_in) else {
            return TxHash::zero();
        };
        let payload = self.encode_coin_transfer(&intent.asset_in, to, amount_u64);
        self.synthetic_execute("move|transfer|coin", &payload)
    }

    /// LIQUIDITY — generic Aptos LP `add_liquidity` entry function.
    fn execute_liquidity(&self, intent: &Intent, _route: &Route) -> TxHash {
        let lp_module = "0x2d44c0e6d0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0";
        let Ok(amount_a) = u64::try_from(intent.amount_in / 2) else {
            return TxHash::zero();
        };
        let Ok(amount_b) = u64::try_from(intent.amount_in - intent.amount_in / 2) else {
            return TxHash::zero();
        };
        let payload = self.encode_add_liquidity(
            lp_module,
            &intent.asset_in,
            &intent.asset_out,
            amount_a,
            amount_b,
        );
        self.synthetic_execute("move|liquidity|lp_add", &payload)
    }

    /// BORROW — Aries Markets borrow entry function.
    fn execute_borrow(&self, intent: &Intent, _route: &Route) -> TxHash {
        let market_address =
            "0x2d44c0e6d0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0";
        let Ok(amount_u64) = u64::try_from(intent.amount_in) else {
            return TxHash::zero();
        };
        let payload = self.encode_aries_borrow(market_address, &intent.asset_out, amount_u64);
        self.synthetic_execute("move|borrow|aries", &payload)
    }

    /// STAKE — Aptos staking module `add_stake(u64)`.
    fn execute_stake(&self, intent: &Intent, _route: &Route) -> TxHash {
        let stake_module = "0x1::stake";
        let Ok(amount_u64) = u64::try_from(intent.amount_in) else {
            return TxHash::zero();
        };
        let payload = self.encode_stake(stake_module, amount_u64);
        self.synthetic_execute("move|stake|stake", &payload)
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

    const APTOS_SENDER: &str =
        "0x1111111111111111111111111111111111111111111111111111111111111111";
    const APTOS_RECIPIENT: &str =
        "0x2222222222222222222222222222222222222222222222222222222222222222";
    const APT_COIN_TYPE: &str = "0x1::aptos_coin::AptosCoin";
    const USDC_TYPE: &str =
        "0xf22bede237a07e121b56d91a491eb6bc5fcd5219d3986d4f53a7c1f9a0e8a0a::usdc::USDC";

    fn sample_intent_swap() -> Intent {
        Intent {
            action: IntentAction::Swap,
            source_chain: APTOS_MAINNET_CHAIN_ID,
            dest_chain: APTOS_MAINNET_CHAIN_ID,
            asset_in: String::from(APT_COIN_TYPE),
            asset_out: String::from(USDC_TYPE),
            amount_in: 1_000_000_000,
            source_address: String::from(APTOS_SENDER),
            dest_address: String::from(APTOS_RECIPIENT),
            min_amount_out: Some(900_000),
            deadline: 1_700_000_000,
        }
    }

    fn sample_intent_transfer() -> Intent {
        Intent {
            action: IntentAction::Transfer,
            source_chain: APTOS_MAINNET_CHAIN_ID,
            dest_chain: APTOS_MAINNET_CHAIN_ID,
            asset_in: String::from(APT_COIN_TYPE),
            asset_out: String::from(APT_COIN_TYPE),
            amount_in: 1_000_000_000,
            source_address: String::from(APTOS_SENDER),
            dest_address: String::from(APTOS_RECIPIENT),
            min_amount_out: None,
            deadline: 1_700_000_000,
        }
    }

    fn sample_intent_borrow() -> Intent {
        Intent {
            action: IntentAction::Borrow,
            source_chain: APTOS_MAINNET_CHAIN_ID,
            dest_chain: APTOS_MAINNET_CHAIN_ID,
            asset_in: String::from(APT_COIN_TYPE),
            asset_out: String::from(USDC_TYPE),
            amount_in: 5_000_000_000u128,
            source_address: String::from(APTOS_SENDER),
            dest_address: String::from(APTOS_RECIPIENT),
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
        let adapter: Box<dyn ChainAdapter> = Box::new(MoveAdapter::aptos());
        assert_eq!(adapter.chain_id(), APTOS_MAINNET_CHAIN_ID);
        assert_eq!(adapter.vm_type(), "MOVE");
        let intent = sample_intent_swap();
        let route = sample_route();
        let tx = adapter.execute_swap(&intent, &route);
        assert!(!tx.is_zero());
    }

    /// Every execute_* returns a non-zero SYNTHETIC-DEMO hash for valid
    /// intents (payload JSON encodes successfully).
    #[test]
    fn test_execute_paths_produce_synthetic_hashes() {
        let adapter = MoveAdapter::aptos();
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

    /// R-FAILCLOSED: malformed Aptos address returns `TxHash::zero()`
    /// rather than panicking.
    #[test]
    fn test_fail_closed_on_malformed_address() {
        let adapter = MoveAdapter::aptos();
        let mut intent = sample_intent_transfer();
        intent.dest_address = String::from("not-an-address");
        let route = sample_route();
        let tx = adapter.execute_transfer(&intent, &route);
        assert!(tx.is_zero());
        assert!(matches!(adapter.verify_execution(tx), ExecutionResult::Failed));
    }

    /// R-FAILCLOSED: amount exceeding u64::MAX returns `TxHash::zero()`.
    #[test]
    fn test_fail_closed_on_amount_overflow() {
        let adapter = MoveAdapter::aptos();
        let mut intent = sample_intent_transfer();
        intent.amount_in = u128::from(u64::MAX) + 1;
        let route = sample_route();
        let tx = adapter.execute_transfer(&intent, &route);
        assert!(tx.is_zero());
    }

    /// R-FAILCLOSED: `verify_execution(TxHash::zero())` → Failed.
    #[test]
    fn test_verify_execution_zero_hash_is_failed() {
        let adapter = MoveAdapter::aptos();
        assert!(matches!(
            adapter.verify_execution(TxHash::zero()),
            ExecutionResult::Failed
        ));
    }

    /// Synthetic hashes are deterministic for the same payload JSON.
    #[test]
    fn test_synthetic_hash_is_deterministic() {
        let adapter = MoveAdapter::aptos();
        let intent = sample_intent_swap();
        let route = sample_route();
        let h1 = adapter.execute_swap(&intent, &route);
        let h2 = adapter.execute_swap(&intent, &route);
        assert_eq!(h1, h2);
    }

    /// Sui flavour adapter: chain id 99 + SUI label.
    #[test]
    fn test_sui_flavor() {
        let adapter = MoveAdapter::sui();
        assert_eq!(adapter.chain_id(), 99);
        assert_eq!(adapter.vm_type(), "MOVE");
        assert_eq!(adapter.config().move_flavor.as_str(), "SUI");
    }

    /// Aptos entry_function_payload structure matches canonical shape
    /// (type, function, type_arguments, arguments keys present).
    #[test]
    fn test_payload_structure_canonical() {
        let adapter = MoveAdapter::aptos();
        let transfer = adapter.encode_coin_transfer(APT_COIN_TYPE, APTOS_RECIPIENT, 1_000);
        assert_eq!(transfer["type"], "entry_function_payload");
        assert_eq!(transfer["function"], "0x1::coin::transfer");
        assert_eq!(transfer["type_arguments"][0], APT_COIN_TYPE);
        assert_eq!(transfer["arguments"][0], APTOS_RECIPIENT);
        assert_eq!(transfer["arguments"][1], "1000");

        let stake = adapter.encode_stake("0x1::stake", 5_000);
        assert_eq!(stake["function"], "0x1::stake::add_stake");
        assert_eq!(stake["arguments"][0], "5000");
    }
}
