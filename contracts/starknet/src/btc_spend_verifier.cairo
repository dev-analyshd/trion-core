/// TRION Protocol — BTCSpendVerifier (Starknet) — Trustless Spend Proof
/// =====================================================================
/// Verifies that a spending transaction is included in a real Bitcoin block
/// by checking its merkle proof against the SPV verifier's stored block header.
///
/// This closes LIMITATION 2: report_spend becomes PERMISSIONLESS and TRUSTLESS.
/// Anyone can prove a spend by providing the spending tx's merkle proof.
/// No relayer/owner gating required.

use starknet::ContractAddress;
use core::array::{ArrayTrait, SpanTrait, Span};
use starknet::SyscallResultTrait;
use starknet::Zeroable;

// SPV verifier get_block_header selector
const GET_BLOCK_HEADER_SEL: felt252 = 0x275a3ba0c3a920dc9a4c088eca3f23addb8c049d79b76c10226c5343856d49e;

/// Bitcoin double-SHA256 over a ByteArray, returned as u256 (big-endian display).
fn sha256_u256(data: @ByteArray) -> u256 {
    let hash_result = core::sha256::compute_sha256_byte_array(data);
    let mut value: u256 = 0;
    let mut i: usize = 0;
    let span = hash_result.span();
    while i != 8 {
        let word: u32 = *span.at(i);
        value = value * 0x100000000_u256 + word.into();
        i += 1;
    };
    value
}

fn u256_to_byte_array(v: u256) -> ByteArray {
    let mut bytes = "";
    let mut i: usize = 0;
    while i != 16 {
        let pow: u128 = 1_u128 << ((15 - i) * 8);
        let b: u8 = ((v.high / pow) % 256_u128).try_into().unwrap();
        bytes.append_byte(b);
        i += 1;
    };
    let mut j: usize = 0;
    while j != 16 {
        let pow: u128 = 1_u128 << ((15 - j) * 8);
        let b: u8 = ((v.low / pow) % 256_u128).try_into().unwrap();
        bytes.append_byte(b);
        j += 1;
    };
    bytes
}

fn u128_byte(v: u128, idx: usize) -> u8 {
    let mut pow: u128 = 1;
    let mut k: usize = 0;
    while k != (15 - idx) { pow = pow * 256_u128; k += 1; };
    ((v / pow) % 256_u128).try_into().unwrap()
}

fn reverse_u256_bytes(v: u256) -> u256 {
    let mut result: u256 = u256 { low: 0, high: 0 };
    let mut bytes: Array<u8> = ArrayTrait::new();
    let mut i: usize = 0;
    while i != 16 {
        bytes.append(u128_byte(v.high, i));
        i += 1;
    };
    let mut j: usize = 0;
    while j != 16 {
        bytes.append(u128_byte(v.low, j));
        j += 1;
    };
    // Reverse the 32 bytes
    let mut k: usize = 0;
    let mut high_val: u128 = 0;
    while k != 16 {
        let b: u128 = (*bytes.at(31 - k)).into();
        high_val = high_val * 256_u128 + b;
        k += 1;
    };
    let mut l: usize = 0;
    let mut low_val: u128 = 0;
    while l != 16 {
        let b: u128 = (*bytes.at(15 - l)).into();
        low_val = low_val * 256_u128 + b;
        l += 1;
    };
    u256 { low: low_val, high: high_val }
}

fn double_sha256(data: @ByteArray) -> u256 {
    let first = sha256_u256(data);
    let first_bytes = u256_to_byte_array(first);
    sha256_u256(@first_bytes)
}

/// Verify a Bitcoin Merkle proof.
/// txid is (lo, hi) as two u128 in DISPLAY (big-endian) order.
/// Returns the recomputed root in DISPLAY order.
fn verify_merkle_proof(
    txid_lo: u128, txid_hi: u128,
    tx_index: u32,
    merkle_path: Span<u256>,
) -> u256 {
    let mut current_display: u256 = txid_hi.into() * 0x100000000000000000000000000000000_u256
        + txid_lo.into();
    let mut current_le = reverse_u256_bytes(current_display);
    let mut index = tx_index;
    let mut i: usize = 0;
    let path_len = merkle_path.len();
    while i != path_len {
        let sibling: u256 = *merkle_path[i];
        let sibling_le = reverse_u256_bytes(sibling);
        let is_left = (index & 1) == 0;
        let mut combined = "";
        if is_left {
            let cb = u256_to_byte_array(current_le);
            let sb = u256_to_byte_array(sibling_le);
            let mut x: usize = 0;
            while x != 32 { combined.append_byte(cb.at(x).unwrap()); x += 1; };
            let mut y: usize = 0;
            while y != 32 { combined.append_byte(sb.at(y).unwrap()); y += 1; };
        } else {
            let sb = u256_to_byte_array(sibling_le);
            let cb = u256_to_byte_array(current_le);
            let mut x: usize = 0;
            while x != 32 { combined.append_byte(sb.at(x).unwrap()); x += 1; };
            let mut y: usize = 0;
            while y != 32 { combined.append_byte(cb.at(y).unwrap()); y += 1; };
        };
        current_le = double_sha256(@combined);
        index = index / 2;
        i += 1;
    };
    reverse_u256_bytes(current_le)
}

#[starknet::contract]
pub mod BTCSpendVerifier {
    use super::{verify_merkle_proof, Span};
    use starknet::{
        ContractAddress, get_caller_address,
        storage::{StoragePointerReadAccess, StoragePointerWriteAccess},
        syscalls::call_contract_syscall,
    };
    use core::array::ArrayTrait;
    use core::array::SpanTrait;
    use starknet::SyscallResultTrait;

    #[storage]
    struct Storage {
        owner: ContractAddress,
        spv_verifier: ContractAddress,
    }

    #[event] #[derive(Drop, starknet::Event)]
    pub enum Event {
        SpendVerified: SpendVerified,
        SpendRejected: SpendRejected,
    }
    #[derive(Drop, starknet::Event)]
    pub struct SpendVerified {
        pub txid_lo: u128, pub txid_hi: u128,
        pub block_hash: u256, pub merkle_root: u256,
    }
    #[derive(Drop, starknet::Event)]
    pub struct SpendRejected {
        pub txid_lo: u128, pub txid_hi: u128, pub reason: u8,
    }

    #[constructor]
    fn constructor(ref self: ContractState, owner: ContractAddress, spv: ContractAddress) {
        self.owner.write(owner);
        self.spv_verifier.write(spv);
    }

    /// Read the stored merkle_root from the SPV verifier for a given block_hash.
    /// Calls SPV.get_block_header(block_hash) → returns (height, merkle_root, time, exists, bits).
    fn read_spv_merkle_root(self: @ContractState, block_hash: u256) -> (u256, bool) {
        let spv = self.spv_verifier.read();
        let mut calldata: Array<felt252> = ArrayTrait::new();
        calldata.append(block_hash.low.into());
        calldata.append(block_hash.high.into());
        let result = call_contract_syscall(spv, super::GET_BLOCK_HEADER_SEL, calldata.span());
        let result_span = result.unwrap_syscall();
        // Returns: (height: u64, merkle_root: u256{low,high}, time: u64, exists: bool, bits: u32)
        let height: u64 = (*result_span.at(0_usize)).try_into().unwrap();
        let merkle_root_low: u128 = (*result_span.at(1_usize)).try_into().unwrap();
        let merkle_root_high: u128 = (*result_span.at(2_usize)).try_into().unwrap();
        let merkle_root = u256 { low: merkle_root_low, high: merkle_root_high };
        let exists_val: felt252 = *result_span.at(3_usize);
        let exists: bool = exists_val == 1;
        (merkle_root, exists)
    }

    #[starknet::interface]
    pub trait IBTCSpendVerifier<T> {
        /// PERMISSIONLESS + TRUSTLESS: verify that a spending tx is included in a real Bitcoin block.
        /// Returns true if the merkle proof is valid against the SPV verifier's stored block header.
        /// This proves the spending tx is real and confirmed — no relayer/owner gating.
        fn verify_spend_merkle(
            self: @T,
            spending_txid_lo: u128,
            spending_txid_hi: u128,
            spending_block_hash: u256,
            spending_tx_index: u32,
            spending_merkle_path: Span<u256>,
        ) -> bool;
    }

    #[abi(embed_v0)]
    impl SpendVerifierImpl of IBTCSpendVerifier<ContractState> {
        fn verify_spend_merkle(
            self: @ContractState,
            spending_txid_lo: u128,
            spending_txid_hi: u128,
            spending_block_hash: u256,
            spending_tx_index: u32,
            spending_merkle_path: Span<u256>,
        ) -> bool {
            // Step 1: read the stored merkle root from the SPV verifier
            let (stored_root, exists) = self.read_spv_merkle_root(spending_block_hash);
            assert(exists, 'SPEND: block not stored');

            // Step 2: recompute the merkle root from the spending tx's proof
            let recomputed_root = verify_merkle_proof(
                spending_txid_lo, spending_txid_hi,
                spending_tx_index, spending_merkle_path,
            );

            // Step 3: the recomputed root must match the stored root
            assert(recomputed_root == stored_root, 'SPEND: merkle mismatch');

            self.emit(SpendVerified {
                txid_lo: spending_txid_lo, txid_hi: spending_txid_hi,
                block_hash: spending_block_hash, merkle_root: stored_root,
            });
            true
        }
    }
}
