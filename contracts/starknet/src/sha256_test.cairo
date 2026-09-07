/// Minimal SHA-256 isolation test — determines if compute_sha256_byte_array
/// works on 80-byte inputs on Starknet Sepolia.
#[starknet::interface]
trait ISha256Test<TContractState> {
    fn test_sha256_64(self: @TContractState, data: Span<u8>) -> u256;
    fn test_sha256_80(self: @TContractState, data: Span<u8>) -> u256;
    fn test_double_sha256_80(self: @TContractState, data: Span<u8>) -> u256;
}

#[starknet::contract]
pub mod Sha256Test {
    use core::sha256::compute_sha256_byte_array;

    fn sha256_u256(data: @ByteArray) -> u256 {
        let hash_result = compute_sha256_byte_array(data);
        let mut value: u256 = 0;
        for word in hash_result.span() {
            value *= 0x100000000_u256;
            value = value + (*word).into();
        };
        value
    }

    fn double_sha256(data: @ByteArray) -> u256 {
        let first = sha256_u256(data);
        let mut first_bytes: ByteArray = "";
        // convert u256 to 32-byte ByteArray (big-endian)
        // u256 = { high: u128, low: u128 }. Big-endian = high first, then low.
        let mut i: usize = 0;
        while i != 16 {
            // byte i (0=MSB) of high u128 = (high / 256^(15-i)) % 256
            let mut pow: u128 = 1;
            let mut k: usize = 0;
            while k != (15 - i) { pow = pow * 256_u128; k += 1; };
            let b: u8 = ((first.high / pow) % 256_u128).try_into().unwrap();
            first_bytes.append_byte(b);
            i += 1;
        };
        let mut j: usize = 0;
        while j != 16 {
            let mut pow: u128 = 1;
            let mut k: usize = 0;
            while k != (15 - j) { pow = pow * 256_u128; k += 1; };
            let b: u8 = ((first.low / pow) % 256_u128).try_into().unwrap();
            first_bytes.append_byte(b);
            j += 1;
        };
        sha256_u256(@first_bytes)
    }

    fn span_to_byte_array(data: Span<u8>, len: usize) -> ByteArray {
        let mut ba: ByteArray = "";
        let mut i: usize = 0;
        while i != len {
            ba.append_byte(*data.at(i));
            i += 1;
        };
        ba
    }

    #[storage]
    struct Storage {}

    #[abi(embed_v0)]
    impl Sha256TestImpl of super::ISha256Test<ContractState> {
        fn test_sha256_64(self: @ContractState, data: Span<u8>) -> u256 {
            let ba = span_to_byte_array(data, 64);
            sha256_u256(@ba)
        }

        fn test_sha256_80(self: @ContractState, data: Span<u8>) -> u256 {
            let ba = span_to_byte_array(data, 80);
            sha256_u256(@ba)
        }

        fn test_double_sha256_80(self: @ContractState, data: Span<u8>) -> u256 {
            let ba = span_to_byte_array(data, 80);
            double_sha256(@ba)
        }
    }
}
