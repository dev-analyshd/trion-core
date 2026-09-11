//! adapters-evm — EVM ChainAdapter (C3 §4 Step 4 + §14.1 Phase 5 item #24).
//!
//! Implements `ChainAdapter` for EVM chains. Per the C3 §4 Step 4
//! translation table:
//!
//! | Event       | EVM                  |
//! |-------------|----------------------|
//! | SWAP        | Uniswap V2/V3 router |
//! | TRANSFER    | ERC-20 transfer      |
//! | LIQUIDITY   | LP position          |
//! | BORROW      | Aave Pool            |
//! | STAKE       | staking contract     |
//!
//! The existing trion-evm indexer (`indexers/crates/trion-evm`) uses
//! `reqwest + serde_json` only — no `ethers` or `alloy` crate is pulled
//! anywhere in the repo. This adapter mirrors that convention: it
//! hand-rolls the calldata encoding (RLP + Keccak-256 selector) instead
//! of pulling a 100k-line SDK, so `cargo build -p adapters-evm` is
//! tractable in the sandbox AND consistent with the rest of the repo.
//!
//! # SYNTHETIC-DEMO execution path (R-LABELS)
//!
//! No adapter in this crate broadcasts a real transaction. Each
//! `execute_*` method:
//! 1. Builds the chain-native calldata (real Uniswap V2 router
//!    `swapExactTokensForTokens` selector, real ERC-20 `transfer`
//!    selector, real Aave `borrow` selector, etc.).
//! 2. Returns [`adapters_core::synthetic_tx_hash`] of the calldata as
//!    a deterministic, reproducible [`TxHash`] — never presented as a
//!    real mainnet hash.
//! 3. [`ChainAdapter::verify_execution`] returns
//!    [`ExecutionResult::Simulated`] with the `SYNTHETIC-DEMO` label
//!    for any non-zero hash, and [`ExecutionResult::Failed`] for
//!    `TxHash::zero()` (R-FAILCLOSED).
//!
//! # R-FAILCLOSED
//!
//! `verify_execution` on a zero hash, on a network error, or on any
//! internal encoding failure returns [`ExecutionResult::Failed`] —
//! never panics.

use adapters_core::{
    synthetic_tx_hash, ChainAdapter, ChainId, ExecutionResult, Intent, Route, TxHash,
};

/// Gas-token symbol table for well-known EVM chains. Unmapped chain ids
/// fall back to "UNKNOWN" — never a guessed symbol (mirrors the
/// `rust/src/adapters/evm.rs` discipline).
const KNOWN_EVM_GAS_TOKENS: &[(ChainId, &str)] = &[
    (1, "ETH"),      // Ethereum mainnet
    (10, "ETH"),     // OP Mainnet
    (56, "BNB"),     // BNB Smart Chain
    (137, "POL"),    // Polygon PoS (MATIC → POL rename, Sept 2024)
    (8453, "ETH"),   // Base
    (42161, "ETH"),  // Arbitrum One
    (43114, "AVAX"), // Avalanche C-Chain
];

/// EVM adapter configuration.
#[derive(Debug, Clone)]
pub struct EvmAdapterConfig {
    /// EIP-155 chain id this adapter targets.
    pub chain_id: ChainId,
    /// Optional RPC endpoint URL — stored but not contacted. Real
    /// broadcast requires wiring to the trion-evm indexer RPC layer;
    /// until then every execute_* returns a SYNTHETIC-DEMO hash.
    pub rpc_url: Option<String>,
    /// Optional override for the native gas token symbol. When `None`
    /// the adapter falls back to the [`KNOWN_EVM_GAS_TOKENS`] table.
    pub gas_token_override: Option<String>,
    /// Optional explicit contract address overrides. When `None` the
    /// adapter uses well-known mainnet addresses (Uniswap V2 router,
    /// Aave V3 pool, etc.).
    pub addresses: EvmContractAddresses,
}

/// Well-known EVM contract addresses (per C3 §4 Step 4 translation table).
/// All zero by default — adapters that wire a real RPC client must
/// populate these from the chain's registry.
#[derive(Debug, Clone, Default)]
pub struct EvmContractAddresses {
    /// Uniswap V2 router (Ethereum mainnet:
    /// 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D).
    pub uniswap_v2_router: [u8; 20],
    /// Uniswap V3 router (Ethereum mainnet:
    /// 0xE592427A0AEce92De3Edee1F18E0157C05861564).
    pub uniswap_v3_router: [u8; 20],
    /// Aave V3 Pool (Ethereum mainnet:
    /// 0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2).
    pub aave_v3_pool: [u8; 20],
}

impl EvmAdapterConfig {
    /// Default mainnet addresses for chain id 1.
    pub fn mainnet_ethereum() -> Self {
        EvmAdapterConfig {
            chain_id: 1,
            rpc_url: None,
            gas_token_override: None,
            addresses: EvmContractAddresses {
                uniswap_v2_router: hex_literal_address(
                    "7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
                ),
                uniswap_v3_router: hex_literal_address(
                    "E592427A0AEce92De3Edee1F18E0157C05861564",
                ),
                aave_v3_pool: hex_literal_address(
                    "87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
                ),
            },
        }
    }
}

/// Decode a 40-char hex address literal (no `0x` prefix) into 20 bytes.
/// Panics only if the literal is malformed — used inside `const` contexts
/// on hard-coded well-known mainnet addresses.
fn hex_literal_address(hex40: &str) -> [u8; 20] {
    let mut out = [0u8; 20];
    let bytes = hex::decode(hex40).expect("well-known address hex literal must decode");
    assert_eq!(bytes.len(), 20, "address literal must be 20 bytes");
    out.copy_from_slice(&bytes);
    out
}

/// EVM chain adapter — [`ChainAdapter`] implementation for EVM chains.
#[derive(Debug, Clone)]
pub struct EvmAdapter {
    config: EvmAdapterConfig,
}

impl EvmAdapter {
    /// Create an EVM adapter with mainnet-Ethereum default addresses.
    pub fn new(chain_id: ChainId) -> Self {
        let mut config = EvmAdapterConfig::mainnet_ethereum();
        config.chain_id = chain_id;
        EvmAdapter { config }
    }

    /// Create an EVM adapter with an explicit RPC endpoint URL stored
    /// (but not contacted) for future wiring.
    pub fn with_rpc_url(chain_id: ChainId, rpc_url: String) -> Self {
        let mut config = EvmAdapterConfig::mainnet_ethereum();
        config.chain_id = chain_id;
        config.rpc_url = Some(rpc_url);
        EvmAdapter { config }
    }

    /// Borrow the adapter configuration.
    pub fn config(&self) -> &EvmAdapterConfig {
        &self.config
    }

    /// Native gas-token symbol for this adapter's chain.
    pub fn native_gas_token(&self) -> &str {
        if let Some(sym) = &self.config.gas_token_override {
            return sym.as_str();
        }
        for &(chain_id, symbol) in KNOWN_EVM_GAS_TOKENS {
            if chain_id == self.config.chain_id {
                return symbol;
            }
        }
        "UNKNOWN"
    }

    /// Build the calldata for an ERC-20 `transfer(address,uint256)` call.
    /// Selector: keccak256("transfer(address,uint256)")[0..4] = 0xa9059cbb.
    fn encode_erc20_transfer(&self, token: [u8; 20], to: [u8; 20], amount: u128) -> Vec<u8> {
        let mut calldata = Vec::with_capacity(4 + 32 + 32);
        calldata.extend_from_slice(&SELECTOR_ERC20_TRANSFER);
        calldata.extend_from_slice(&pad_address(to));
        calldata.extend_from_slice(&pad_u128(amount));
        let _ = token; // token address is the *to* field of the outer tx, not calldata
        calldata
    }

    /// Build the calldata for Uniswap V2 router
    /// `swapExactTokensForTokens(uint256,uint256,address[],address,uint256)`.
    /// Selector: 0x38ed1739.
    fn encode_uniswap_v2_swap(
        &self,
        amount_in: u128,
        amount_out_min: u128,
        path_addrs: &[[u8; 20]],
        recipient: [u8; 20],
        deadline: u64,
    ) -> Vec<u8> {
        let mut calldata = Vec::new();
        calldata.extend_from_slice(&SELECTOR_UNISWAP_V2_SWAP);
        calldata.extend_from_slice(&pad_u128(amount_in));
        calldata.extend_from_slice(&pad_u128(amount_out_min));
        // dynamic offset for `path` array (3 head slots before path)
        calldata.extend_from_slice(&pad_u128(0x60));
        calldata.extend_from_slice(&pad_address(recipient));
        calldata.extend_from_slice(&pad_u128(deadline as u128));
        // path array: length + each address padded to 32 bytes
        calldata.extend_from_slice(&pad_u128(path_addrs.len() as u128));
        for addr in path_addrs {
            calldata.extend_from_slice(&pad_address(*addr));
        }
        calldata
    }

    /// Build the calldata for Aave V3 Pool `borrow(address,uint256,uint256,uint16,address)`.
    /// Selector: 0xa415bcad.
    fn encode_aave_borrow(
        &self,
        asset: [u8; 20],
        amount: u128,
        interest_rate_mode: u8,
        referral_code: u16,
        on_behalf_of: [u8; 20],
    ) -> Vec<u8> {
        let mut calldata = Vec::with_capacity(4 + 32 * 5);
        calldata.extend_from_slice(&SELECTOR_AAVE_BORROW);
        calldata.extend_from_slice(&pad_address(asset));
        calldata.extend_from_slice(&pad_u128(amount));
        calldata.extend_from_slice(&pad_u128(interest_rate_mode as u128));
        calldata.extend_from_slice(&pad_u128(referral_code as u128));
        calldata.extend_from_slice(&pad_address(on_behalf_of));
        calldata
    }

    /// Build the calldata for a generic staking contract
    /// `stake(uint256)` (selector 0xa694fc3a).
    fn encode_stake(&self, amount: u128) -> Vec<u8> {
        let mut calldata = Vec::with_capacity(4 + 32);
        calldata.extend_from_slice(&SELECTOR_STAKE);
        calldata.extend_from_slice(&pad_u128(amount));
        calldata
    }

    /// Build the calldata for an LP `addLiquidity` call (Uniswap V2
    /// `addLiquidity(address,address,uint256,uint256,uint256,uint256,address,uint256)`,
    /// selector 0xe8e33700).
    fn encode_add_liquidity(
        &self,
        token_a: [u8; 20],
        token_b: [u8; 20],
        amount_a_desired: u128,
        amount_b_desired: u128,
        amount_a_min: u128,
        amount_b_min: u128,
        recipient: [u8; 20],
        deadline: u64,
    ) -> Vec<u8> {
        let mut calldata = Vec::with_capacity(4 + 32 * 8);
        calldata.extend_from_slice(&SELECTOR_ADD_LIQUIDITY);
        calldata.extend_from_slice(&pad_address(token_a));
        calldata.extend_from_slice(&pad_address(token_b));
        calldata.extend_from_slice(&pad_u128(amount_a_desired));
        calldata.extend_from_slice(&pad_u128(amount_b_desired));
        calldata.extend_from_slice(&pad_u128(amount_a_min));
        calldata.extend_from_slice(&pad_u128(amount_b_min));
        calldata.extend_from_slice(&pad_address(recipient));
        calldata.extend_from_slice(&pad_u128(deadline as u128));
        calldata
    }

    /// Fail-closed: encode the calldata, derive a SYNTHETIC-DEMO tx hash,
    /// and return it. On any encoding failure returns `TxHash::zero()`
    /// (R-FAILCLOSED — no panic).
    fn synthetic_execute(&self, tag: &str, calldata: &[u8]) -> TxHash {
        if calldata.is_empty() {
            return TxHash::zero();
        }
        let mut payload = Vec::with_capacity(tag.len() + 1 + calldata.len());
        payload.extend_from_slice(tag.as_bytes());
        payload.push(b'|');
        payload.extend_from_slice(calldata);
        synthetic_tx_hash(&payload)
    }
}

/// Keccak-256 selector for `transfer(address,uint256)` = 0xa9059cbb.
const SELECTOR_ERC20_TRANSFER: [u8; 4] = [0xa9, 0x05, 0x9c, 0xbb];
/// Keccak-256 selector for `swapExactTokensForTokens(uint256,uint256,address[],address,uint256)`
/// = 0x38ed1739.
const SELECTOR_UNISWAP_V2_SWAP: [u8; 4] = [0x38, 0xed, 0x17, 0x39];
/// Keccak-256 selector for Aave V3 `borrow(address,uint256,uint256,uint16,address)`
/// = 0xa415bcad.
const SELECTOR_AAVE_BORROW: [u8; 4] = [0xa4, 0x15, 0xbc, 0xad];
/// Keccak-256 selector for `stake(uint256)` = 0xa694fc3a.
const SELECTOR_STAKE: [u8; 4] = [0xa6, 0x94, 0xfc, 0x3a];
/// Keccak-256 selector for Uniswap V2 `addLiquidity(...)` = 0xe8e33700.
const SELECTOR_ADD_LIQUIDITY: [u8; 4] = [0xe8, 0xe3, 0x37, 0x00];

/// Pad a 20-byte address to 32 bytes (left-padded with zeros, per EVM
/// ABI encoding).
fn pad_address(addr: [u8; 20]) -> [u8; 32] {
    let mut out = [0u8; 32];
    out[12..].copy_from_slice(&addr);
    out
}

/// Pad a `u128` to 32 bytes big-endian (left-padded with zeros).
fn pad_u128(value: u128) -> [u8; 32] {
    let mut out = [0u8; 32];
    out[16..].copy_from_slice(&value.to_be_bytes());
    out
}

/// Parse a hex address string (with or without `0x` prefix) into a
/// 20-byte array. Returns `None` on parse failure (R-FAILCLOSED —
/// caller returns `TxHash::zero()`).
fn parse_address(s: &str) -> Option<[u8; 20]> {
    let trimmed = s.trim_start_matches("0x");
    if trimmed.len() != 40 {
        return None;
    }
    let bytes = hex::decode(trimmed).ok()?;
    if bytes.len() != 20 {
        return None;
    }
    let mut out = [0u8; 20];
    out.copy_from_slice(&bytes);
    Some(out)
}

impl ChainAdapter for EvmAdapter {
    fn chain_id(&self) -> ChainId {
        self.config.chain_id
    }

    fn vm_type(&self) -> &'static str {
        "EVM"
    }

    /// SWAP — Uniswap V2 router `swapExactTokensForTokens` calldata.
    fn execute_swap(&self, intent: &Intent, _route: &Route) -> TxHash {
        // Path: asset_in → asset_out (single hop for the SYNTHETIC-DEMO
        // path; a real router would expand to multi-hop via BIBL analysis).
        let token_in = match parse_address(&intent.asset_in) {
            Some(a) => a,
            None => return TxHash::zero(),
        };
        let token_out = match parse_address(&intent.asset_out) {
            Some(a) => a,
            None => return TxHash::zero(),
        };
        let recipient = match parse_address(&intent.dest_address) {
            Some(a) => a,
            None => return TxHash::zero(),
        };
        let amount_out_min = intent.min_amount_out.unwrap_or(0);
        let calldata = self.encode_uniswap_v2_swap(
            intent.amount_in,
            amount_out_min,
            &[token_in, token_out],
            recipient,
            intent.deadline,
        );
        self.synthetic_execute("evm|swap|uniswap_v2", &calldata)
    }

    /// TRANSFER — ERC-20 `transfer(address,uint256)` calldata.
    fn execute_transfer(&self, intent: &Intent, _route: &Route) -> TxHash {
        let token = match parse_address(&intent.asset_in) {
            Some(a) => a,
            None => return TxHash::zero(),
        };
        let recipient = match parse_address(&intent.dest_address) {
            Some(a) => a,
            None => return TxHash::zero(),
        };
        let calldata = self.encode_erc20_transfer(token, recipient, intent.amount_in);
        self.synthetic_execute("evm|transfer|erc20", &calldata)
    }

    /// LIQUIDITY — Uniswap V2 `addLiquidity(...)` calldata.
    fn execute_liquidity(&self, intent: &Intent, _route: &Route) -> TxHash {
        let token_a = match parse_address(&intent.asset_in) {
            Some(a) => a,
            None => return TxHash::zero(),
        };
        let token_b = match parse_address(&intent.asset_out) {
            Some(a) => a,
            None => return TxHash::zero(),
        };
        let recipient = match parse_address(&intent.dest_address) {
            Some(a) => a,
            None => return TxHash::zero(),
        };
        // SYNTHETIC-DEMO: split amount 50/50 between the two legs.
        let amount_a = intent.amount_in / 2;
        let amount_b = intent.amount_in - amount_a;
        let calldata = self.encode_add_liquidity(
            token_a,
            token_b,
            amount_a,
            amount_b,
            0,
            0,
            recipient,
            intent.deadline,
        );
        self.synthetic_execute("evm|liquidity|uniswap_v2_lp", &calldata)
    }

    /// BORROW — Aave V3 Pool `borrow(...)` calldata.
    fn execute_borrow(&self, intent: &Intent, _route: &Route) -> TxHash {
        let asset = match parse_address(&intent.asset_out) {
            Some(a) => a,
            None => return TxHash::zero(),
        };
        let on_behalf_of = match parse_address(&intent.dest_address) {
            Some(a) => a,
            None => return TxHash::zero(),
        };
        // Interest rate mode 2 = variable rate; referral code 0.
        let calldata = self.encode_aave_borrow(asset, intent.amount_in, 2, 0, on_behalf_of);
        self.synthetic_execute("evm|borrow|aave_v3", &calldata)
    }

    /// STAKE — generic staking contract `stake(uint256)` calldata.
    fn execute_stake(&self, intent: &Intent, _route: &Route) -> TxHash {
        let calldata = self.encode_stake(intent.amount_in);
        self.synthetic_execute("evm|stake|generic", &calldata)
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
    use sha3::{Digest, Keccak256};

    fn sample_intent_swap() -> Intent {
        Intent {
            action: IntentAction::Swap,
            source_chain: 1,
            dest_chain: 1,
            asset_in: String::from("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"), // WETH
            asset_out: String::from("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"), // USDC
            amount_in: 1_000_000_000_000_000_000u128, // 1 ETH
            source_address: String::from("0x1111111111111111111111111111111111111111"),
            dest_address: String::from("0x2222222222222222222222222222222222222222"),
            min_amount_out: Some(900_000000u128), // 900 USDC
            deadline: 1_700_000_000,
        }
    }

    fn sample_intent_transfer() -> Intent {
        Intent {
            action: IntentAction::Transfer,
            source_chain: 1,
            dest_chain: 1,
            asset_in: String::from("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"), // USDC
            asset_out: String::from("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
            amount_in: 1_000_000000u128, // 1000 USDC
            source_address: String::from("0x1111111111111111111111111111111111111111"),
            dest_address: String::from("0x3333333333333333333333333333333333333333"),
            min_amount_out: None,
            deadline: 1_700_000_000,
        }
    }

    fn sample_intent_borrow() -> Intent {
        Intent {
            action: IntentAction::Borrow,
            source_chain: 1,
            dest_chain: 1,
            asset_in: String::from("0x0000000000000000000000000000000000000000"),
            asset_out: String::from("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"), // WETH borrow
            amount_in: 5_000_000_000_000_000_000u128, // 5 ETH
            source_address: String::from("0x1111111111111111111111111111111111111111"),
            dest_address: String::from("0x4444444444444444444444444444444444444444"),
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

    /// Trait object dispatch: `Box<dyn ChainAdapter>` resolves chain_id,
    /// vm_type, and gas token; execution returns SYNTHETIC-DEMO hashes.
    #[test]
    fn test_trait_object_dispatch() {
        let adapter: Box<dyn ChainAdapter> = Box::new(EvmAdapter::new(1));
        assert_eq!(adapter.chain_id(), 1);
        assert_eq!(adapter.vm_type(), "EVM");
        let intent = sample_intent_swap();
        let route = sample_route();
        let tx = adapter.execute_swap(&intent, &route);
        assert!(!tx.is_zero(), "synthetic swap hash is non-zero");
    }

    /// Every execute_* returns a non-zero SYNTHETIC-DEMO hash for valid
    /// intents (calldata encodes successfully).
    #[test]
    fn test_execute_paths_produce_synthetic_hashes() {
        let adapter = EvmAdapter::new(1);
        let route = sample_route();

        let swap_tx = adapter.execute_swap(&sample_intent_swap(), &route);
        let transfer_tx = adapter.execute_transfer(&sample_intent_transfer(), &route);
        let liquidity_tx = adapter.execute_liquidity(&sample_intent_swap(), &route);
        let borrow_tx = adapter.execute_borrow(&sample_intent_borrow(), &route);
        let stake_tx = adapter.execute_stake(&sample_intent_swap(), &route);

        for (label, tx) in [
            ("swap", swap_tx),
            ("transfer", transfer_tx),
            ("liquidity", liquidity_tx),
            ("borrow", borrow_tx),
            ("stake", stake_tx),
        ] {
            assert!(!tx.is_zero(), "{} returned a non-zero synthetic hash", label);
            assert!(
                matches!(
                    adapter.verify_execution(tx),
                    ExecutionResult::Simulated { label: "SYNTHETIC-DEMO", .. }
                ),
                "{} verifies as SYNTHETIC-DEMO",
                label
            );
        }
    }

    /// R-FAILCLOSED: malformed asset address (not 40 hex chars) returns
    /// `TxHash::zero()` rather than panicking.
    #[test]
    fn test_fail_closed_on_malformed_address() {
        let adapter = EvmAdapter::new(1);
        let mut intent = sample_intent_swap();
        intent.asset_in = String::from("not-an-address");
        let route = sample_route();
        let tx = adapter.execute_swap(&intent, &route);
        assert!(tx.is_zero(), "malformed address → zero hash (fail-closed)");
        assert!(matches!(
            adapter.verify_execution(tx),
            ExecutionResult::Failed
        ));
    }

    /// R-FAILCLOSED: `verify_execution(TxHash::zero())` → Failed.
    #[test]
    fn test_verify_execution_zero_hash_is_failed() {
        let adapter = EvmAdapter::new(1);
        assert!(matches!(
            adapter.verify_execution(TxHash::zero()),
            ExecutionResult::Failed
        ));
    }

    /// Synthetic hashes are deterministic for the same calldata — same
    /// intent → same hash (reproducibility for downstream ledger checks).
    #[test]
    fn test_synthetic_hash_is_deterministic() {
        let adapter = EvmAdapter::new(1);
        let intent = sample_intent_swap();
        let route = sample_route();
        let h1 = adapter.execute_swap(&intent, &route);
        let h2 = adapter.execute_swap(&intent, &route);
        assert_eq!(h1, h2, "same intent → same synthetic hash");
    }

    /// chain_id mapping + gas token symbol mapping for well-known chains.
    #[test]
    fn test_gas_token_mapping() {
        for &(chain_id, symbol) in KNOWN_EVM_GAS_TOKENS {
            let adapter = EvmAdapter::new(chain_id);
            assert_eq!(adapter.chain_id(), chain_id);
            assert_eq!(adapter.native_gas_token(), symbol);
        }
        // Unmapped chain → UNKNOWN (never a guessed symbol)
        let unknown = EvmAdapter::new(999_999);
        assert_eq!(unknown.native_gas_token(), "UNKNOWN");
    }

    /// Storing an RPC URL does not change fail-closed semantics.
    #[test]
    fn test_with_rpc_url_still_synthetic() {
        let adapter = EvmAdapter::with_rpc_url(1, String::from("http://localhost:8545"));
        assert_eq!(adapter.config().rpc_url.as_deref(), Some("http://localhost:8545"));
        let tx = adapter.execute_transfer(&sample_intent_transfer(), &sample_route());
        assert!(!tx.is_zero(), "SYNTHETIC-DEMO path produces a non-zero hash");
        assert!(matches!(
            adapter.verify_execution(tx),
            ExecutionResult::Simulated { .. }
        ));
    }

    /// Selector sanity — verify the well-known 4-byte function selectors
    /// match the canonical Keccak-256 prefixes. Guards against typos in
    /// the SELECTOR_* constants.
    #[test]
    fn test_selectors_match_canonical_keccak() {
        // transfer(address,uint256)
        let mut h = Keccak256::new();
        h.update(b"transfer(address,uint256)");
        let d = h.finalize();
        assert_eq!(&d[0..4], &SELECTOR_ERC20_TRANSFER);

        // swapExactTokensForTokens(uint256,uint256,address[],address,uint256)
        let mut h = Keccak256::new();
        h.update(b"swapExactTokensForTokens(uint256,uint256,address[],address,uint256)");
        let d = h.finalize();
        assert_eq!(&d[0..4], &SELECTOR_UNISWAP_V2_SWAP);

        // borrow(address,uint256,uint256,uint16,address) [Aave V3]
        let mut h = Keccak256::new();
        h.update(b"borrow(address,uint256,uint256,uint16,address)");
        let d = h.finalize();
        assert_eq!(&d[0..4], &SELECTOR_AAVE_BORROW);

        // stake(uint256)
        let mut h = Keccak256::new();
        h.update(b"stake(uint256)");
        let d = h.finalize();
        assert_eq!(&d[0..4], &SELECTOR_STAKE);

        // addLiquidity(address,address,uint256,uint256,uint256,uint256,address,uint256)
        let mut h = Keccak256::new();
        h.update(b"addLiquidity(address,address,uint256,uint256,uint256,uint256,address,uint256)");
        let d = h.finalize();
        assert_eq!(&d[0..4], &SELECTOR_ADD_LIQUIDITY);
    }
}
