// Forwarder — calls submit_route_attestation on the escrow.
// The escrow sees THIS contract's address as the caller (validator).

#[starknet::interface]
trait IForwarder<TContractState> {
    fn attest(
        ref self: TContractState,
        escrow: starknet::ContractAddress,
        route_id: felt252,
        coherence: u64,
        execution_bh: felt252,
        attestation_time: u64,
    );
    fn get_owner(self: @TContractState) -> starknet::ContractAddress;
}

#[starknet::contract]
pub mod Forwarder {
    use starknet::{
        ContractAddress, get_caller_address,
        storage::{StoragePointerReadAccess, StoragePointerWriteAccess},
        syscalls::call_contract_syscall,
    };
    use core::array::ArrayTrait;
<<<<<<< HEAD
    use core::array::SpanTrait;
=======
>>>>>>> a914c8e (feat(btcp-v3): fix all 4 limitations — SPV-wired escrow + DeFi pool)
    use starknet::SyscallResultTrait;

    #[storage]
    struct Storage {
        owner: ContractAddress,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    enum Event {
        AttestForwarded: AttestForwarded,
    }

    #[derive(Drop, starknet::Event)]
    struct AttestForwarded {
        #[key]
        escrow: ContractAddress,
        route_id: felt252,
        caller: ContractAddress,
    }

    #[constructor]
    fn constructor(ref self: ContractState, owner: ContractAddress) {
        self.owner.write(owner);
    }

    #[abi(embed_v0)]
    impl ForwarderImpl of super::IForwarder<ContractState> {
        fn attest(
            ref self: ContractState,
            escrow: ContractAddress,
            route_id: felt252,
            coherence: u64,
            execution_bh: felt252,
            attestation_time: u64,
        ) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'FWD: not owner');
            self.emit(AttestForwarded { escrow, route_id, caller });
            // Build calldata for submit_route_attestation
            let mut calldata = ArrayTrait::new();
            ArrayTrait::append(ref calldata, route_id);
            ArrayTrait::append(ref calldata, coherence.into());
            ArrayTrait::append(ref calldata, execution_bh);
            ArrayTrait::append(ref calldata, attestation_time.into());
            // Call the escrow — it sees THIS contract as the caller (validator)
            call_contract_syscall(
                escrow,
                selector!("submit_route_attestation"),
                calldata.span(),
            ).unwrap_syscall();
        }

        fn get_owner(self: @ContractState) -> ContractAddress {
            self.owner.read()
        }
    }
}
