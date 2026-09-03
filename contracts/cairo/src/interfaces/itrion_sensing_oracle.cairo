// SPDX-License-Identifier: CC0-1.0
// ITRIONSensingOracle interface — Cairo version
#[starknet::interface]
pub trait ITRIONSensingOracle<TContractState> {
    fn is_coherent(self: @TContractState, entity_id: felt252) -> bool;
    fn get_coherence_detail(self: @TContractState, entity_id: felt252) -> (u256, u256, bool, u8, u64, bool);
}
