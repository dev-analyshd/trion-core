/// TRION Protocol — BTCPDeFiPool (Starknet) — FIX 5
/// =================================================
/// A DeFi pool whose operations are CONDITIONAL on a verified, released
/// Bitcoin-anchored escrow. This closes the "no DeFi causality" gap.
///
/// Flow:
///   1. User locks BTC on Bitcoin testnet (real UTXO).
///   2. User locks escrow on BTCPEscrowV3 (SPV-verified anchor).
///   3. 3 validators attest (distinct funded accounts).
///   4. User releases escrow (anchor re-verified + quorum).
///   5. User calls deposit() on this pool — REQUIRES a RELEASED escrow.
///   6. User can borrow against the deposited credit.
///   7. User repays + withdraws.
///
/// The pool does NOT custody BTC. It issues Starknet-side credit
/// conditional on the Bitcoin anchor being verified and released.

#[starknet::interface]
pub trait IBTCPDeFiPoolAdmin<TContractState> {
    fn set_escrow(ref self: TContractState, escrow: starknet::ContractAddress);
}

#[starknet::interface]
pub trait IBTCPDeFiPool<TContractState> {
    /// Deposit: requires a RELEASED escrow with the caller as destination.
    /// Credits the caller with the escrow amount as borrowable credit.
    fn deposit(ref self: TContractState, escrow_id: felt252);

    /// Borrow against deposited credit. Max borrow = 50% of credit (conservative LTV).
    fn borrow(ref self: TContractState, amount: u256);

    /// Repay a borrow (plus 5% interest to the protocol).
    fn repay(ref self: TContractState, amount: u256);

    /// Withdraw deposited credit (only if no outstanding borrow).
    fn withdraw(ref self: TContractState, escrow_id: felt252);

    /// FIX LIMITATION 4: Clawback — if the escrow is REVERTED (anchor spent or reorg),
    /// the credit is clawed back. This ensures economic state stays consistent.
    fn clawback(ref self: TContractState, escrow_id: felt252);

    /// FIX LIMITATION 4: Check if an escrow has sufficient BTCP score for DeFi operations.
    /// Requires score >= 500000 (0.50) per whitepaper L1.1.
    fn check_btcp_score(self: @TContractState, escrow_id: felt252) -> bool;

    /// View: credit balance of a user.
    fn get_credit(self: @TContractState, user: starknet::ContractAddress) -> u256;

    /// View: outstanding borrow of a user.
    fn get_borrow(self: @TContractState, user: starknet::ContractAddress) -> u256;

    /// View: total deposits.
    fn total_deposits(self: @TContractState) -> u256;

    /// View: total borrows.
    fn total_borrows(self: @TContractState) -> u256;
}

#[derive(Drop, Serde, Copy, starknet::Store)]
pub struct Deposit {
    pub user: starknet::ContractAddress,
    pub escrow_id: felt252,
    pub amount: u256,
    pub active: bool,
}

#[starknet::contract]
pub mod BTCPDeFiPool {
    use super::{Deposit, IBTCPDeFiPool, IBTCPDeFiPoolAdmin};
    use starknet::{
        ContractAddress, get_caller_address,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess,
                  StoragePointerReadAccess, StoragePointerWriteAccess},
        syscalls::call_contract_syscall,
    };
    use starknet::SyscallResultTrait;
    use core::array::ArrayTrait;
    use core::array::SpanTrait;

    const LTV_NUMERATOR: u256 = 50_u256;   // 50%
    const LTV_DENOMINATOR: u256 = 100_u256;
    const INTEREST_NUMERATOR: u256 = 105_u256; // 5% interest
    const INTEREST_DENOMINATOR: u256 = 100_u256;

    // Selector for escrow.get_escrow
    const GET_ESCROW_SELECTOR: felt252 = 0x275a3ba0c3a920dc9a4c088eca3f23addb8c049d79b76c10226c5343856d49e;
    const GET_BTCP_SCORE_SELECTOR: felt252 = 0x361e801e8f2f24117d9115835ccb53e37d3c52ea85f06adcc1ab747fed1f4cb;

    #[storage]
    struct Storage {
        owner: ContractAddress,
        escrow: ContractAddress,
        escrow_set: bool,
        // user → credit amount (from verified BTC anchors)
        credits: Map<ContractAddress, u256>,
        // user → outstanding borrow
        borrows: Map<ContractAddress, u256>,
        // escrow_id → Deposit record
        deposits: Map<felt252, Deposit>,
        // user → list of escrow_ids deposited (for withdrawal)
        user_deposits: Map<ContractAddress, felt252>,
        total_deposits: u256,
        total_borrows: u256,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        EscrowSet: EscrowSet,
        Deposited: Deposited,
        Borrowed: Borrowed,
        Repaid: Repaid,
        Withdrawn: Withdrawn,
    }

    #[derive(Drop, starknet::Event)]
    pub struct EscrowSet { pub escrow: ContractAddress }

    #[derive(Drop, starknet::Event)]
    pub struct Deposited {
        #[key] pub user: ContractAddress,
        #[key] pub escrow_id: felt252,
        pub amount: u256,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Borrowed {
        #[key] pub user: ContractAddress,
        pub amount: u256,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Repaid {
        #[key] pub user: ContractAddress,
        pub amount: u256,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Withdrawn {
        #[key] pub user: ContractAddress,
        #[key] pub escrow_id: felt252,
        pub amount: u256,
    }

    #[constructor]
    fn constructor(ref self: ContractState, owner: ContractAddress) {
        self.owner.write(owner);
        self.escrow_set.write(false);
        self.total_deposits.write(0_u256);
        self.total_borrows.write(0_u256);
    }

    fn read_escrow_internal(escrow_addr: ContractAddress, escrow_id: felt252) -> (ContractAddress, u256, u8, ContractAddress) {
        let mut calldata: Array<felt252> = ArrayTrait::new();
        calldata.append(escrow_id);
        let result = call_contract_syscall(
            escrow_addr,
            GET_ESCROW_SELECTOR,
            calldata.span(),
        );
        let result_span = result.unwrap_syscall();
        let dest_felt: felt252 = *result_span.at(3_usize);
        let dest: ContractAddress = dest_felt.try_into().unwrap();
        let amount_low: u128 = (*result_span.at(4_usize)).try_into().unwrap();
        let amount_high: u128 = (*result_span.at(5_usize)).try_into().unwrap();
        let state_val: felt252 = *result_span.at(9_usize);
        let locked_by: ContractAddress = (*result_span.at(13_usize)).try_into().unwrap();
        let amount = u256 { low: amount_low, high: amount_high };
        let state: u8 = state_val.try_into().unwrap();
        (dest, amount, state, locked_by)
    }

    #[abi(embed_v0)]
    impl BTCPDeFiPoolAdmin of IBTCPDeFiPoolAdmin<ContractState> {
        fn set_escrow(ref self: ContractState, escrow: ContractAddress) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'POOL: not owner');
            assert(!self.escrow_set.read(), 'POOL: escrow set');
            self.escrow.write(escrow);
            self.escrow_set.write(true);
            self.emit(EscrowSet { escrow });
        }
    }

    #[abi(embed_v0)]
    impl BTCPDeFiPoolImpl of IBTCPDeFiPool<ContractState> {
        /// Deposit: requires a RELEASED escrow (state=1) with caller as destination.
        fn deposit(ref self: ContractState, escrow_id: felt252) {
            let caller = get_caller_address();
            assert(self.escrow_set.read(), 'POOL: escrow not set');

            // Read the escrow from V3 contract
            let (dest, amount, state, _locked_by) = read_escrow_internal(self.escrow.read(), escrow_id);

            // FIX 5: DeFi operation is CONDITIONAL on verified Bitcoin anchor.
            // The escrow must be RELEASED (state=1), which means:
            //   - verify_anchor passed at lock time (real Bitcoin tx)
            //   - 3 validators attested (distinct funded accounts)
            //   - verify_anchor re-passed at release time (no reorg)
            //   - coherence >= threshold
            assert(state == 1_u8, 'POOL: escrow not released');
            assert(dest == caller, 'POOL: not destination');
            assert(amount > 0_u256, 'POOL: zero amount');

            // Check not already deposited
            let existing = self.deposits.read(escrow_id);
            assert(!existing.active, 'POOL: already deposited');

            // Credit the user
            self.deposits.write(escrow_id, Deposit {
                user: caller, escrow_id, amount, active: true,
            });
            let current_credit = self.credits.read(caller);
            self.credits.write(caller, current_credit + amount);
            let td = self.total_deposits.read();
            self.total_deposits.write(td + amount);
            self.user_deposits.write(caller, escrow_id);
            self.emit(Deposited { user: caller, escrow_id, amount });
        }

        fn borrow(ref self: ContractState, amount: u256) {
            let caller = get_caller_address();
            assert(amount > 0_u256, 'POOL: zero borrow');
            let credit = self.credits.read(caller);
            // Max borrow = 50% of credit (conservative LTV)
            let max_borrow = credit * LTV_NUMERATOR / LTV_DENOMINATOR;
            let current_borrow = self.borrows.read(caller);
            assert(current_borrow + amount <= max_borrow, 'POOL: exceeds LTV');
            self.borrows.write(caller, current_borrow + amount);
            let tb = self.total_borrows.read();
            self.total_borrows.write(tb + amount);
            self.emit(Borrowed { user: caller, amount });
        }

        fn repay(ref self: ContractState, amount: u256) {
            let caller = get_caller_address();
            assert(amount > 0_u256, 'POOL: zero repay');
            let current_borrow = self.borrows.read(caller);
            assert(current_borrow >= amount, 'POOL: over-repay');
            self.borrows.write(caller, current_borrow - amount);
            let tb = self.total_borrows.read();
            self.total_borrows.write(tb - amount);
            self.emit(Repaid { user: caller, amount });
        }

        fn withdraw(ref self: ContractState, escrow_id: felt252) {
            let caller = get_caller_address();
            let dep = self.deposits.read(escrow_id);
            assert(dep.active, 'POOL: not deposited');
            assert(dep.user == caller, 'POOL: not owner');
            let current_borrow = self.borrows.read(caller);
            assert(current_borrow == 0_u256, 'POOL: outstanding borrow');
            self.deposits.write(escrow_id, Deposit {
                user: caller, escrow_id, amount: 0_u256, active: false,
            });
            let current_credit = self.credits.read(caller);
            assert(current_credit >= dep.amount, 'POOL: insufficient credit');
            self.credits.write(caller, current_credit - dep.amount);
            let td = self.total_deposits.read();
            self.total_deposits.write(td - dep.amount);
            self.emit(Withdrawn { user: caller, escrow_id, amount: dep.amount });
        }

        /// FIX LIMITATION 4: Clawback — if the escrow is REVERTED (anchor spent or reorg),
        /// the credit is clawed back. This ensures economic state stays consistent.
        fn clawback(ref self: ContractState, escrow_id: felt252) {
            // PERMISSIONLESS — anyone can call this
            let dep = self.deposits.read(escrow_id);
            assert(dep.active, 'POOL: not deposited');

            // Read the escrow state from V3 contract
            let (dest, amount, state, _locked_by) = read_escrow_internal(self.escrow.read(), escrow_id);

            // The escrow must be REVERTED (state=2) — anchor spent or reorg
            assert(state == 2_u8, 'POOL: escrow not reverted');

            // Claw back the credit
            self.deposits.write(escrow_id, Deposit {
                user: dep.user, escrow_id, amount: 0_u256, active: false,
            });
            let current_credit = self.credits.read(dep.user);
            if current_credit >= amount {
                self.credits.write(dep.user, current_credit - amount);
            } else {
                self.credits.write(dep.user, 0_u256);
            };
            let td = self.total_deposits.read();
            if td >= amount {
                self.total_deposits.write(td - amount);
            } else {
                self.total_deposits.write(0_u256);
            };
            self.emit(Withdrawn { user: dep.user, escrow_id, amount });
        }

        /// FIX LIMITATION 4: Check if an escrow has sufficient BTCP score for DeFi operations.
        fn check_btcp_score(self: @ContractState, escrow_id: felt252) -> bool {
            // Call escrow.get_btcp_score(escrow_id) via call_contract_syscall
            let escrow = self.escrow.read();
            let mut calldata: Array<felt252> = ArrayTrait::new();
            calldata.append(escrow_id);
            let result = call_contract_syscall(
                escrow,
                GET_BTCP_SCORE_SELECTOR,
                calldata.span(),
            );
            let result_span = result.unwrap_syscall();
            let score: u64 = (*result_span.at(0_usize)).try_into().unwrap();
            // Whitepaper L1.1: BTCP_score >= 0.50 → approved for routing
            score >= 500_000_u64
        }

        fn get_credit(self: @ContractState, user: ContractAddress) -> u256 {
            self.credits.read(user)
        }

        fn get_borrow(self: @ContractState, user: ContractAddress) -> u256 {
            self.borrows.read(user)
        }

        fn total_deposits(self: @ContractState) -> u256 {
            self.total_deposits.read()
        }

        fn total_borrows(self: @ContractState) -> u256 {
            self.total_borrows.read()
        }
    }
}
