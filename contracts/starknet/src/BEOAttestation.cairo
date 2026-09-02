/// TRION Protocol — BEO Identity Attestation
/// Starknet Sepolia Contract
///
/// Binds Starknet wallet addresses to their BEO identity fingerprint and
/// credibility tier. Compatible with Starknet's native account abstraction
/// (Argent/Braavos). Any protocol can call get_beo() to resolve identity.
///
/// Tiers: 0=BOOTSTRAP (Conf<0.30), 1=GENESIS (0.30-0.80), 2=MATURITY (>0.80)

#[starknet::interface]
pub trait IBEOAttestation<TContractState> {
    fn attest(
        ref self: TContractState,
        wallet: starknet::ContractAddress,
        beo_id: felt252,
        tier: u8,
        genesis_confidence_bp: u64,
    );
    fn revoke(ref self: TContractState, wallet: starknet::ContractAddress);
    fn get_beo(self: @TContractState, wallet: starknet::ContractAddress) -> BEOIdentity;
    fn get_wallet(self: @TContractState, beo_id: felt252) -> starknet::ContractAddress;
    fn is_attested(self: @TContractState, wallet: starknet::ContractAddress) -> bool;
    fn get_attester(self: @TContractState) -> starknet::ContractAddress;
    fn set_attester(ref self: TContractState, new_attester: starknet::ContractAddress);
    fn total_attestations(self: @TContractState) -> u64;
}

#[derive(Drop, Serde, Copy, starknet::Store)]
pub struct BEOIdentity {
    /// SHA3-256 BEO fingerprint as felt252 (truncated to fit)
    pub beo_id: felt252,
    /// 0=BOOTSTRAP, 1=GENESIS, 2=MATURITY
    pub tier: u8,
    /// Genesis confidence in basis points (0-10000)
    pub genesis_confidence_bp: u64,
    /// Block timestamp when attested
    pub attested_at: u64,
    /// Whether this attestation is currently valid
    pub active: bool,
}

#[starknet::contract]
pub mod BEOAttestation {
    use super::{BEOIdentity, IBEOAttestation};
    use starknet::{
        ContractAddress, get_caller_address, get_block_timestamp,
        storage::{Map, StorageMapReadAccess, StorageMapWriteAccess, StoragePointerReadAccess, StoragePointerWriteAccess}
    };

    #[storage]
    struct Storage {
        attester: ContractAddress,
        wallet_to_beo: Map<ContractAddress, BEOIdentity>,
        beo_to_wallet: Map<felt252, ContractAddress>,
        total: u64,
    }

    #[event]
    #[derive(Drop, starknet::Event)]
    pub enum Event {
        Attested: Attested,
        Revoked: Revoked,
        AttesterChanged: AttesterChanged,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Attested {
        #[key]
        pub wallet: ContractAddress,
        #[key]
        pub beo_id: felt252,
        pub tier: u8,
        pub genesis_confidence_bp: u64,
        pub timestamp: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct Revoked {
        #[key]
        pub wallet: ContractAddress,
        pub beo_id: felt252,
        pub timestamp: u64,
    }

    #[derive(Drop, starknet::Event)]
    pub struct AttesterChanged {
        pub old_attester: ContractAddress,
        pub new_attester: ContractAddress,
    }

    #[constructor]
    fn constructor(ref self: ContractState, attester: ContractAddress) {
        self.attester.write(attester);
        self.total.write(0);
    }

    #[abi(embed_v0)]
    impl BEOAttestationImpl of IBEOAttestation<ContractState> {
        fn attest(
            ref self: ContractState,
            wallet: ContractAddress,
            beo_id: felt252,
            tier: u8,
            genesis_confidence_bp: u64,
        ) {
            let caller = get_caller_address();
            assert(caller == self.attester.read(), 'BEO: unauthorized attester');
            assert(tier <= 2_u8, 'BEO: invalid tier');
            assert(genesis_confidence_bp <= 10000_u64, 'BEO: gc_bp out of range');

            let ts = get_block_timestamp();
            let was_active = self.wallet_to_beo.read(wallet).active;

            let identity = BEOIdentity {
                beo_id,
                tier,
                genesis_confidence_bp,
                attested_at: ts,
                active: true,
            };

            self.wallet_to_beo.write(wallet, identity);
            self.beo_to_wallet.write(beo_id, wallet);

            if !was_active {
                let current = self.total.read();
                self.total.write(current + 1);
            }

            self.emit(Attested { wallet, beo_id, tier, genesis_confidence_bp, timestamp: ts });
        }

        fn revoke(ref self: ContractState, wallet: ContractAddress) {
            let caller = get_caller_address();
            assert(caller == self.attester.read(), 'BEO: unauthorized attester');

            let existing = self.wallet_to_beo.read(wallet);
            assert(existing.active, 'BEO: not attested');

            let ts = get_block_timestamp();
            let beo_id = existing.beo_id;

            let revoked = BEOIdentity {
                beo_id: existing.beo_id,
                tier: existing.tier,
                genesis_confidence_bp: existing.genesis_confidence_bp,
                attested_at: existing.attested_at,
                active: false,
            };
            self.wallet_to_beo.write(wallet, revoked);

            self.emit(Revoked { wallet, beo_id, timestamp: ts });
        }

        fn get_beo(self: @ContractState, wallet: ContractAddress) -> BEOIdentity {
            self.wallet_to_beo.read(wallet)
        }

        fn get_wallet(self: @ContractState, beo_id: felt252) -> ContractAddress {
            self.beo_to_wallet.read(beo_id)
        }

        fn is_attested(self: @ContractState, wallet: ContractAddress) -> bool {
            self.wallet_to_beo.read(wallet).active
        }

        fn get_attester(self: @ContractState) -> ContractAddress {
            self.attester.read()
        }

        fn set_attester(ref self: ContractState, new_attester: ContractAddress) {
            let caller = get_caller_address();
            assert(caller == self.attester.read(), 'BEO: unauthorized attester');
            let old = self.attester.read();
            self.attester.write(new_attester);
            self.emit(AttesterChanged { old_attester: old, new_attester });
        }

        fn total_attestations(self: @ContractState) -> u64 {
            self.total.read()
        }
    }
}
