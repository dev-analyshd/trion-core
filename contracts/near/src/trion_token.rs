//! TRION Protocol — NEAR TRION Token (NEP-141)
//! ============================================
//! NEP-141 fungible token with:
//!   - FIXED SUPPLY — 1,000,000,000 TRION @ 18 decimals, minted exactly once
//!     at genesis in `new()`; 0% ongoing inflation (WP 15.3 / Audit-4 Gap 1)
//!   - REAL GENESIS DISTRIBUTION (mirrors contracts/vyper/TRIONToken.vy):
//!     PUBLIC_GOOD_BPS = 15% of supply credited to the public-good reserve,
//!     the remaining 85% to the treasury & vesting allocator
//!     (canonical table: docs/TOKENOMICS.md)
//!   - DECIMALS = 18 — unified with the Vyper / TON / ink! implementations
//!     (was 24, a thousand-fold unit discrepancy vs. the other chains)
//!   - Permissionless `burn` (deflationary mechanism, WP 15.3)
//!   - 7-type slashing (5 -> 7 in Audit-4), 50/50 insurance_pool / burn split
//!
//! Mirrors contracts/vyper/TRIONToken.vy on NEAR.

use near_sdk::borsh::{self, BorshDeserialize, BorshSerialize};
use near_sdk::collections::LookupMap;
use near_sdk::{env, near_bindgen, AccountId, PanicOnDefault};

/// Fixed genesis supply: 1,000,000,000 TRION at 18 decimals = 10^27 raw units
/// (docs/TOKENOMICS.md — identical across every chain implementation).
const TOTAL_SUPPLY_RAW: u128 = 1_000_000_000_000_000_000_000_000_000; // 1e27
/// Public Good Charter: 15% of the genesis supply (and of fee revenue on the
/// Vyper reference implementation) routed to the public-good reserve.
const PUBLIC_GOOD_BPS:    u128 = 1500;                    // 15.00%
const ZERO_INFLATION_BPS: u16  = 0;                       // Audit-4 Gap 1

/// 7 slashing conditions (Audit-4 Gap 1 fix: 5 -> 7).
#[derive(BorshDeserialize, BorshSerialize, Clone, Debug)]
#[derive(serde::Serialize, serde::Deserialize)]
pub enum SlashCondition {
    DoubleSign,
    CoherenceCollapse,
    AWAViolation,
    Censorship,
    LongRangeAttack,
    BridgeMisbehavior,
    SybilAttack,
}

#[near_bindgen]
#[derive(BorshDeserialize, BorshSerialize, PanicOnDefault)]
pub struct TRIONToken {
    name:        String,
    symbol:      String,
    decimals:    u8,
    total_supply:u128,
    balances:    LookupMap<AccountId, u128>,
    allowances:  LookupMap<AccountId, LookupMap<AccountId, u128>>,
    governance:  AccountId,
    public_good_reserve: AccountId,
    public_good_minted:  u128,
    /// Treasury & vesting allocator — receives 85% of genesis; executes the
    /// off-chain vesting/ecosystem schedule in docs/TOKENOMICS.md.
    treasury_allocator:  AccountId,
    insurance_pool:       AccountId,
    insurance_pool_balance: u128,
    total_burned:         u128,
    staking_contract:    Option<AccountId>,
    awa_enforced:         bool,
}

#[near_bindgen]
impl TRIONToken {
    /// Genesis constructor — the ONLY place supply is created.
    ///
    /// Mints the fixed 10^27 raw units (1,000,000,000 TRION @ 18 decimals)
    /// exactly once and distributes it (docs/TOKENOMICS.md, matching the
    /// Vyper reference implementation):
    ///   - 15% (PUBLIC_GOOD_BPS)  -> `public_good_reserve`
    ///   - 85% (remainder)        -> `treasury_allocator`
    #[init]
    pub fn new(
        governance:          AccountId,
        public_good_reserve: AccountId,
        treasury_allocator:  AccountId,
        insurance_pool:      AccountId,
    ) -> Self {
        let mut balances = LookupMap::new(b"b");

        // Genesis distribution — on-chain enforced, exactly once.
        let public_good_amount = TOTAL_SUPPLY_RAW * PUBLIC_GOOD_BPS / 10_000; // 15%
        let allocator_amount   = TOTAL_SUPPLY_RAW - public_good_amount;      // 85%
        balances.insert(&public_good_reserve, &public_good_amount);
        balances.insert(&treasury_allocator,  &allocator_amount);
        env::log_str(&format!(
            "GenesisDistribution:public_good={}:{}:treasury={}:{}",
            public_good_reserve, public_good_amount, treasury_allocator, allocator_amount
        ));

        Self {
            name:                 "TRION Protocol".into(),
            symbol:               "TRION".into(),
            decimals:             18,
            total_supply:         TOTAL_SUPPLY_RAW,
            balances,
            allowances:           LookupMap::new(b"a"),
            governance:           governance,
            public_good_reserve:  public_good_reserve,
            public_good_minted:   public_good_amount,
            treasury_allocator:   treasury_allocator,
            insurance_pool,
            insurance_pool_balance: 0,
            total_burned:         0,
            staking_contract:    None,
            awa_enforced:         true,
        }
    }

    /// NEP-141: ft_transfer
    pub fn ft_transfer(&mut self, receiver_id: AccountId, amount: u128, memo: Option<String>) {
        let sender = env::predecessor_account_id();
        assert!(amount > 0, "TRION: zero amount");
        let bal = self.balances.get(&sender).unwrap_or(0);
        assert!(bal >= amount, "TRION: insufficient balance");
        self.balances.insert(&sender, &(bal - amount));
        let rbal = self.balances.get(&receiver_id).unwrap_or(0);
        self.balances.insert(&receiver_id, &(rbal + amount));
        if let Some(m) = memo {
            env::log_str(&format!("TRIONTransfer:{}:{}:{}", sender, receiver_id, m));
        }
    }

    /// NEP-141: ft_balance_of
    pub fn ft_balance_of(&self, account_id: AccountId) -> u128 {
        self.balances.get(&account_id).unwrap_or(0)
    }

    /// NEP-141: ft_total_supply
    pub fn ft_total_supply(&self) -> u128 { self.total_supply }

    /// NEP-141: ft_metadata
    pub fn ft_metadata(&self) -> (String, String, u8) {
        (self.name.clone(), self.symbol.clone(), self.decimals)
    }

    /// Audit-4 Gap 1 / WP 15.3: 0% inflation — `governance_mint` always panics.
    /// The entire supply was minted once in `new()`; validator rewards come
    /// from protocol fees, NOT from new minting.
    pub fn governance_mint(&mut self, _recipient: AccountId, _amount: u128, _purpose: String) {
        // No-op panic — 0% inflation policy enforced on-chain.
        env::panic_str("TRION: fixed supply at genesis — governance_mint disabled (WP 15.3)");
    }

    /// Permissionless burn — any holder may permanently destroy their TRION
    /// (deflationary mechanism, WP 15.3 "consumption bonding burns small
    /// fraction on each use"). Mirrors burn() in the Vyper reference token.
    pub fn burn(&mut self, amount: u128) {
        let burner = env::predecessor_account_id();
        assert!(amount > 0, "TRION: zero burn");
        let bal = self.balances.get(&burner).unwrap_or(0);
        assert!(bal >= amount, "TRION: insufficient balance");
        self.balances.insert(&burner, &(bal - amount));
        self.total_supply -= amount;
        self.total_burned  += amount;
        env::log_str(&format!("Burn:{}:{}", burner, amount));
    }

    /// Audit-4 Gap 1: slashed TRION destination = 50% insurance_pool / 50% burn.
    /// Slashing types expanded to 7 (was 5).
    pub fn slash_validator(
        &mut self,
        validator: AccountId,
        amount:   u128,
        condition: SlashCondition,
    ) {
        let caller = env::predecessor_account_id();
        assert_eq!(caller, self.governance, "TRION: not governance");
        assert!(self.awa_enforced, "TRION: AWA not enforced");

        let bal = self.balances.get(&validator).unwrap_or(0);
        let slash_amount = bal.min(amount);
        assert!(slash_amount > 0, "TRION: zero slash");

        let insurance_share = slash_amount / 2;
        let burn_share       = slash_amount - insurance_share;

        self.balances.insert(&validator, &(bal - slash_amount));
        let ibal = self.balances.get(&self.insurance_pool).unwrap_or(0);
        self.balances.insert(&self.insurance_pool, &(ibal + insurance_share));
        self.insurance_pool_balance += insurance_share;
        self.total_burned          += burn_share;
        self.total_supply          -= burn_share;  // burn reduces supply

        env::log_str(&format!(
            "ValidatorSlashed:{}:amount={}:insurance={}:burn={}",
            validator, slash_amount, insurance_share, burn_share
        ));
    }

    pub fn total_burned(&self)            -> u128 { self.total_burned }
    pub fn insurance_pool_balance(&self) -> u128 { self.insurance_pool_balance }
    pub fn public_good_minted(&self)     -> u128 { self.public_good_minted }
    pub fn awa_enforced(&self)            -> bool { self.awa_enforced }

    /// Genesis carve-out actually credited to the public-good reserve (raw units).
    pub fn genesis_public_good_amount(&self) -> u128 {
        TOTAL_SUPPLY_RAW * PUBLIC_GOOD_BPS / 10_000
    }

    /// Genesis amount actually credited to the treasury & vesting allocator (raw units).
    pub fn genesis_allocator_amount(&self) -> u128 {
        TOTAL_SUPPLY_RAW - TOTAL_SUPPLY_RAW * PUBLIC_GOOD_BPS / 10_000
    }

    /// Burn-on-use consumption fee in basis points — 0.05% (docs/TOKENOMICS.md).
    /// The fee-on-transfer split (85% burned / 15% routed to the public-good
    /// reserve) is enforced by the Vyper reference implementation.
    pub fn transfer_fee_bps(&self) -> u128 { 5 }

    pub fn set_staking_contract(&mut self, staking: AccountId) {
        assert_eq!(env::predecessor_account_id(), self.governance, "TRION: not governance");
        self.staking_contract = Some(staking);
    }
}
