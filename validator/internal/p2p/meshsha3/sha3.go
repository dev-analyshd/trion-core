// Package meshsha3 provides a minimal SHA3-256 (Keccak) implementation
// for cross-system compatibility with the Rust trion-common hash_dna pipeline.
//
// Go's standard library (crypto/sha256) implements SHA-2, NOT SHA-3. The TRION
// protocol's Behavioral Hash (L0.1) and Genomic Key (L4.3) use SHA3-256
// exclusively. Using crypto/sha256 would produce a different hash than the
// Rust/Python implementations, breaking cross-system attestation verification.
//
// This implementation is a clean-room Keccak-f[1600] permutation following
// FIPS 202. It is not constant-time but is sufficient for behavioral hashing
// where side-channel resistance is provided by the dual-strand construction
// itself. For production HSM-backed signing, use golang.org/x/crypto/sha3.
package meshsha3

// SHA3-256 constants (FIPS 202 §6.1)
const (
	rate     = 136 // 1088 bits / 8 = 136 bytes
	outputSz = 32  // 256 bits / 8 = 32 bytes
	dsbyte   = 0x06
)

// round constants for Keccak-f[1600]
var rc = [24]uint64{
	0x0000000000000001, 0x0000000000008082, 0x800000000000808a, 0x8000000080008000,
	0x000000000000808b, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
	0x000000000000008a, 0x0000000000000088, 0x0000000080008009, 0x000000008000000a,
	0x000000008000808b, 0x800000000000008b, 0x8000000000008089, 0x8000000000008003,
	0x8000000000008002, 0x8000000000000080, 0x000000000000800a, 0x800000008000000a,
	0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
}

// rotation offsets
var rotc = [24]uint{
	1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 2, 14,
	27, 41, 56, 8, 25, 43, 62, 18, 39, 61, 20, 44,
}

// pi-lane permutation
var piln = [24]uint{
	10, 7, 11, 17, 18, 3, 5, 16, 8, 21, 24, 4,
	15, 23, 19, 13, 12, 2, 20, 14, 22, 9, 6, 1,
}

func keccakf(st *[25]uint64) {
	for round := 0; round < 24; round++ {
		// Theta
		var bc [5]uint64
		for i := 0; i < 5; i++ {
			bc[i] = st[i] ^ st[i+5] ^ st[i+10] ^ st[i+15] ^ st[i+20]
		}
		for i := 0; i < 5; i++ {
			t := bc[(i+4)%5] ^ ((bc[(i+1)%5] << 1) | (bc[(i+1)%5] >> 63))
			for j := 0; j < 25; j += 5 {
				st[j+i] ^= t
			}
		}
		// Rho + Pi
		t := st[1]
		for i := 0; i < 24; i++ {
			j := piln[i]
			tmp := st[j]
			st[j] = (t << rotc[i]) | (t >> (64 - rotc[i]))
			t = tmp
		}
		// Chi
		for j := 0; j < 25; j += 5 {
			var b [5]uint64
			for i := 0; i < 5; i++ {
				b[i] = st[j+i]
			}
			for i := 0; i < 5; i++ {
				st[j+i] = b[i] ^ (^b[(i+1)%5] & b[(i+2)%5])
			}
		}
		// Iota
		st[0] ^= rc[round]
	}
}

// Sum256 returns the SHA3-256 hash of the input data.
// This matches `sha3::Sha3_256::digest()` in Rust and
// `hashlib.sha3_256()` in Python.
func Sum256(data []byte) [outputSz]byte {
	var st [25]uint64
	var buf [rate]byte
	ds := make([]byte, len(data)+1)
	copy(ds, data)
	ds[len(data)] = dsbyte

	// Absorb full blocks
	for len(ds) >= rate {
		for i := 0; i < rate; i++ {
			st[i/8] ^= uint64(ds[i]) << (uint(i%8) * 8)
		}
		keccakf(&st)
		ds = ds[rate:]
	}

	// Final block (with padding)
	for i := range buf {
		buf[i] = 0
	}
	copy(buf[:], ds)
	// 0x06 (domain-separation) is already at position len(data) (which is < rate now)
	// Add final 0x80 bit at end of rate
	buf[rate-1] ^= 0x80
	for i := 0; i < rate; i++ {
		st[i/8] ^= uint64(buf[i]) << (uint(i%8) * 8)
	}
	keccakf(&st)

	// Squeeze
	var out [outputSz]byte
	for i := 0; i < outputSz/8; i++ {
		for j := 0; j < 8; j++ {
			out[i*8+j] = byte(st[i] >> (uint(j) * 8))
		}
	}
	return out
}
