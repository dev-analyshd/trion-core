// SPDX-License-Identifier: MIT
// ITRIONOracle interface — Cairo version
#[starknet::interface]
pub trait ITRIONOracle<TContractState> {
    fn is_safe(self: @TContractState, tx_id: felt252) -> bool;
    fn verify_execution(self: @TContractState, tx_id: felt252) -> (bool, u32, u32);
    fn get_nl_score(self: @TContractState, asset: ContractAddress) -> (u256, u256);
    fn get_mf_score(self: @TContractState, entity: ContractAddress) -> (u256, u8);
}
