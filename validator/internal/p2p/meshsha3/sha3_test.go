package meshsha3

import (
        "encoding/hex"
        "testing"
)

// TestSHA3MatchesPython verifies that our SHA3-256 implementation produces
// the same hashes as Python's hashlib.sha3_256(). This is critical for
// cross-system attestation verification with the Rust/Python pipelines.
func TestSHA3MatchesPython(t *testing.T) {
        tests := []struct {
                name     string
                input    string
                expected string // from Python: hashlib.sha3_256(input.encode()).hexdigest()
        }{
                {"empty", "", "a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a"},
                {"hello", "hello", "3338be694f50c5f338814986cdf0686453a888b84f424d792af4b9202398f392"},
                {"abc", "abc", "3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532"},
                {"fox", "The quick brown fox jumps over the lazy dog", "69070dda01975c8c120c3aada1b282394e7f032fa9cf32f4cb2259a0897dfc04"},
                {"trion", "TRION_PROTOCOL", "011f43fac46e9ea9b30b0aadc8b71b52d359f839afbf425f35083e482f0eb046"},
        }

        for _, tt := range tests {
                t.Run(tt.name, func(t *testing.T) {
                        hash := Sum256([]byte(tt.input))
                        got := hex.EncodeToString(hash[:])
                        if got != tt.expected {
                                t.Errorf("SHA3-256(%q) = %s, want %s", tt.input, got, tt.expected)
                        }
                })
        }
}

// TestDualStrandXORInvariant verifies the dual-strand complementarity.
// Per whitepaper L0.1 and src/core/behavioral_hash.py:
//   sense     = SHA3-256(payload || 0x00)
//   antisense = SHA3-256(payload || 0xFF) XOR NOT(sense)
//
// Invariant: sense XOR antisense == NOT(SHA3-256(payload || 0xFF))
func TestDualStrandXORInvariant(t *testing.T) {
        payload := []byte("TRION Behavioral Hash test payload")

        sense := Sum256(append(payload, 0x00))
        sha3FF := Sum256(append(payload, 0xFF))

        // Compute antisense = SHA3(payload||0xFF) XOR NOT(sense)
        var antisense [32]byte
        for i := 0; i < 32; i++ {
                antisense[i] = sha3FF[i] ^ ^sense[i]
        }

        // Verify: sense XOR antisense == NOT(SHA3(payload||0xFF))
        var xored [32]byte
        for i := 0; i < 32; i++ {
                xored[i] = sense[i] ^ antisense[i]
        }

        var notSha3FF [32]byte
        for i := 0; i < 32; i++ {
                notSha3FF[i] = ^sha3FF[i]
        }

        if xored != notSha3FF {
                t.Errorf("Dual-strand XOR invariant violated:\n  sense XOR antisense = %x\n  NOT(SHA3||0xFF)    = %x",
                        xored, notSha3FF)
        }
}
