// SPDX-License-Identifier: MIT
// ITRIONAggregatorV3 — Chainlink-compatible interface, Cairo version
#[starknet::interface]
pub trait ITRIONAggregatorV3<TContractState> {
    fn decimals(self: @TContractState) -> u8;
    fn description(self: @TContractState) -> ByteArray;
    fn version(self: @TContractState) -> u256;
    fn get_round_data(self: @TContractState, round_id: u80) -> (u80, i256, u64, u64, u80);
    fn latest_round_data(self: @TContractState) -> (u80, i256, u64, u64, u80);
    fn latest_answer(self: @TContractState) -> i256;
}
