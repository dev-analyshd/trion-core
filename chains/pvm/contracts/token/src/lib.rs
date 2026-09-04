//! TRIONToken — ink! (Polkadot PVM)
//!
//! Canonical tokenomics: docs/TOKENOMICS.md (resolves DD finding 5.4
//! "one supply, three stories"). Supply, decimals and the genesis
//! distribution are identical across the Vyper / NEAR / TON / ink!
//! implementations:
//!   - fixed supply 1,000,000,000 TRION @ 18 decimals, minted exactly ONCE
//!     in the constructor — NO minting afterwards (WP 15.3: "Token supply:
//!     fixed at genesis. No inflation mechanism.");
//!   - genesis distribution: 15% (PUBLIC_GOOD_BPS) to the public-good
//!     reserve, 85% to the treasury & vesting allocator;
//!   - permissionless burn() (WP 15.3 deflation: "consumption bonding burns
//!     small fraction on each use");
//!   - team / early-backer vesting schedule recorded on-chain as immutable
//!     markers (see vesting_* getters) — the schedule itself is executed by
//!     the treasury & vesting allocator per docs/TOKENOMICS.md;
//!   - 7-type slashing, 50/50 insurance/burn split.
#![cfg_attr(not(feature = "std"), no_std, no_main)]

#[ink::contract]
mod trion_token {
    use ink::storage::Mapping;
    use super::*;

    /// Fixed genesis supply: 1,000,000,000 TRION @ 18 decimals = 10^27 raw
    /// (docs/TOKENOMICS.md — identical across every chain implementation).
    const TOTAL_SUPPLY: Balance = 1_000_000_000_000_000_000_000_000_000;
    /// Public Good Charter: 15% of the genesis supply (WP 15.3 item 5).
    const PUBLIC_GOOD_BPS: Balance = 1500;
    /// Token decimals — unified to 18 across all TRION implementations.
    const DECIMALS: u8 = 18;
    /// Burn-on-use consumption fee: 0.05% per transfer. Enforced by the
    /// Vyper reference implementation (_transfer fee hook); recorded here as
    /// the canonical policy rate (docs/TOKENOMICS.md).
    const TRANSFER_FEE_BPS: Balance = 5;

    /// Team vesting marker: 15% of supply, 4-year linear, 1-year cliff.
    const TEAM_ALLOCATION_BPS: Balance = 1500;
    const TEAM_VEST_SECS: u64 = 4 * 365 * 24 * 60 * 60;
    const TEAM_CLIFF_SECS: u64 = 365 * 24 * 60 * 60;
    /// Early-backer vesting marker: 12% of supply, 3-year linear.
    const BACKERS_ALLOCATION_BPS: Balance = 1200;
    const BACKERS_VEST_SECS: u64 = 3 * 365 * 24 * 60 * 60;

    #[ink(storage)]
    pub struct TrionToken {
        total_supply: Balance,
        balances: Mapping<AccountId, Balance>,
        allowances: Mapping<(AccountId, AccountId), Balance>,
        admin: AccountId,
        insurance_pool: AccountId,
        /// Genesis custody root: public-good reserve (15% of supply).
        public_good_reserve: AccountId,
        /// Genesis custody root: treasury & vesting allocator (85%).
        treasury_allocator: AccountId,
    }

    #[ink(event)]
    pub struct Transfer { from: Option<AccountId>, to: Option<AccountId>, value: Balance }

    #[ink(event)]
    pub struct Slashed { validator: AccountId, amount: Balance, reason: u8 }

    #[ink(event)]
    pub struct Burn { burner: AccountId, amount: Balance }

    impl TrionToken {
        /// Genesis constructor — the ONLY place supply is created.
        ///
        /// Mints the fixed 10^27 raw units (1,000,000,000 TRION @ 18
        /// decimals) exactly once and distributes it (docs/TOKENOMICS.md,
        /// matching the Vyper reference implementation):
        ///   - 15% (PUBLIC_GOOD_BPS) -> `public_good_reserve`
        ///   - 85% (remainder)       -> `treasury_allocator`
        ///
        /// The deployer (`admin`) receives NOTHING at genesis — the previous
        /// behaviour (100% to deployer) contradicted every other
        /// implementation and the whitepaper.
        #[ink(constructor)]
        pub fn new(
            public_good_reserve: AccountId,
            treasury_allocator: AccountId,
            insurance_pool: AccountId,
        ) -> Self {
            assert!(
                public_good_reserve != treasury_allocator,
                "public good reserve and allocator must differ"
            );
            let mut balances = Mapping::default();
            let public_good_amount = TOTAL_SUPPLY * PUBLIC_GOOD_BPS / 10_000; // 15%
            let allocator_amount = TOTAL_SUPPLY - public_good_amount;        // 85%
            balances.insert(public_good_reserve, &public_good_amount);
            balances.insert(treasury_allocator, &allocator_amount);
            Self::env().emit_event(Transfer {
                from: None,
                to: Some(public_good_reserve),
                value: public_good_amount,
            });
            Self::env().emit_event(Transfer {
                from: None,
                to: Some(treasury_allocator),
                value: allocator_amount,
            });
            Self {
                total_supply: TOTAL_SUPPLY,
                balances,
                allowances: Mapping::default(),
                admin: Self::env().caller(),
                insurance_pool,
                public_good_reserve,
                treasury_allocator,
            }
        }

        #[ink(message)]
        pub fn balance_of(&self, who: AccountId) -> Balance {
            self.balances.get(who).unwrap_or(0)
        }

        #[ink(message)]
        pub fn transfer(&mut self, to: AccountId, value: Balance) -> bool {
            let from = self.env().caller();
            let from_bal = self.balances.get(from).unwrap_or(0);
            assert!(from_bal >= value, "insufficient balance");
            assert!(value > 0, "zero amount");
            self.balances.insert(from, &(from_bal - value));
            let to_bal = self.balances.get(to).unwrap_or(0);
            self.balances.insert(to, &(to_bal + value));
            self.env().emit_event(Transfer { from: Some(from), to: Some(to), value });
            true
        }

        /// Permissionless burn — any holder may permanently destroy their
        /// TRION (deflationary mechanism, WP 15.3). Mirrors burn() in the
        /// Vyper / NEAR / TON implementations. Reduces total_supply.
        #[ink(message)]
        pub fn burn(&mut self, amount: Balance) -> bool {
            let burner = self.env().caller();
            assert!(amount > 0, "zero burn");
            let bal = self.balances.get(burner).unwrap_or(0);
            assert!(bal >= amount, "insufficient balance");
            self.balances.insert(burner, &(bal - amount));
            self.total_supply -= amount;
            self.env().emit_event(Burn { burner, amount });
            true
        }

        /// Slash a validator — 50% to insurance pool, 50% burned
        #[ink(message)]
        pub fn slash(&mut self, validator: AccountId, amount: Balance, reason: u8) {
            assert_eq!(self.env().caller(), self.admin, "not admin");
            let bal = self.balances.get(validator).unwrap_or(0);
            let slash_amount = if bal >= amount { amount } else { bal };
            // 50% to insurance pool
            let insurance = slash_amount / 2;
            self.balances.insert(validator, &(bal - slash_amount));
            let pool_bal = self.balances.get(self.insurance_pool).unwrap_or(0);
            self.balances.insert(self.insurance_pool, &(pool_bal + insurance));
            // 50% burned (removed from supply)
            self.total_supply -= slash_amount - insurance;
            self.env().emit_event(Slashed { validator, amount: slash_amount, reason });
        }

        #[ink(message)]
        pub fn total_supply(&self) -> Balance { self.total_supply }

        // ── Tokenomics metadata (docs/TOKENOMICS.md) ────────────────────────

        /// Token decimals — 18, unified across all chain implementations.
        #[ink(message)]
        pub fn decimals(&self) -> u8 { DECIMALS }

        /// Public Good Charter share in basis points (15% — enforced at
        /// genesis by every TRION implementation).
        #[ink(message)]
        pub fn public_good_bps(&self) -> Balance { PUBLIC_GOOD_BPS }

        /// Burn-on-use consumption fee rate in basis points (0.05% —
        /// enforced by the Vyper reference implementation's transfer hook;
        /// canonical policy rate per docs/TOKENOMICS.md).
        #[ink(message)]
        pub fn transfer_fee_bps(&self) -> Balance { TRANSFER_FEE_BPS }

        /// Genesis custody root: public-good reserve address (15% of supply).
        #[ink(message)]
        pub fn public_good_reserve(&self) -> AccountId { self.public_good_reserve }

        /// Genesis custody root: treasury & vesting allocator (85%).
        #[ink(message)]
        pub fn treasury_allocator(&self) -> AccountId { self.treasury_allocator }

        /// Genesis carve-out actually credited to the public-good reserve.
        #[ink(message)]
        pub fn genesis_public_good_amount(&self) -> Balance {
            TOTAL_SUPPLY * PUBLIC_GOOD_BPS / 10_000
        }

        /// Genesis amount actually credited to the treasury & allocator.
        #[ink(message)]
        pub fn genesis_allocator_amount(&self) -> Balance {
            TOTAL_SUPPLY - TOTAL_SUPPLY * PUBLIC_GOOD_BPS / 10_000
        }

        // ── Vesting markers (immutable schedule commitments; execution is
        //    performed by the treasury & vesting allocator per
        //    docs/TOKENOMICS.md — these markers do NOT lock balances) ──────

        /// Team bucket size in raw units (15% of supply).
        #[ink(message)]
        pub fn vesting_team_allocation(&self) -> Balance {
            TOTAL_SUPPLY * TEAM_ALLOCATION_BPS / 10_000
        }

        /// Team vesting duration (4 years, linear).
        #[ink(message)]
        pub fn vesting_team_duration_secs(&self) -> u64 { TEAM_VEST_SECS }

        /// Team cliff (1 year — nothing liquid before it).
        #[ink(message)]
        pub fn vesting_team_cliff_secs(&self) -> u64 { TEAM_CLIFF_SECS }

        /// Early-backer bucket size in raw units (12% of supply).
        #[ink(message)]
        pub fn vesting_backers_allocation(&self) -> Balance {
            TOTAL_SUPPLY * BACKERS_ALLOCATION_BPS / 10_000
        }

        /// Early-backer vesting duration (3 years, linear).
        #[ink(message)]
        pub fn vesting_backers_duration_secs(&self) -> u64 { BACKERS_VEST_SECS }
    }
}
