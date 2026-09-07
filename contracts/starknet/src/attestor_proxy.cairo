#[starknet::interface]
trait IAttestorProxy<TContractState> {
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
pub mod AttestorProxy {
    use starknet::{
        ContractAddress, get_caller_address,
        storage::{StoragePointerReadAccess, StoragePointerWriteAccess},
    };

    #[storage]
    struct Storage {
        owner: ContractAddress,
    }

    #[derive(Drop, starknet::Event)]
    struct AttestCalled {
        #[key]
        route_id: felt252,
        coherence: u64,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    enum Event {
        AttestCalled: AttestCalled,
    }

    #[constructor]
    fn constructor(ref self: ContractState, owner: ContractAddress) {
        self.owner.write(owner);
    }

    #[abi(embed_v0)]
    impl AttestorProxyImpl of super::IAttestorProxy<ContractState> {
        fn attest(
            ref self: ContractState,
            escrow: ContractAddress,
            route_id: felt252,
            coherence: u64,
            execution_bh: felt252,
            attestation_time: u64,
        ) {
            let caller = get_caller_address();
            assert(caller == self.owner.read(), 'PROXY: not owner');
            // Emit event for the attestation (the actual call to the escrow
            // will be done by the main account via a multicall that includes
            // both the proxy.attest() and escrow.submit_route_attestation()).
            // For now, the proxy just emits an event confirming the attest request.
            self.emit(AttestCalled { route_id, coherence });
        }

        fn get_owner(self: @ContractState) -> ContractAddress {
            self.owner.read()
        }
    }
}
