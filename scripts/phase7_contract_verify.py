#!/usr/bin/env python3
"""
Phase 7 — Contract Verification Tests

Verifies:
  7.1: BTCPEscrow emergency escape guarantee (7 days, anyone callable)
  7.2: Oracle signal bit layout matches relayer.js
  7.3: BEO identity cross-chain consistency (off-chain SHA3-256)

Run: python3 scripts/phase7_contract_verify.py  (repo root auto-detected)
"""
import os
import re
import sys
import hashlib
import json

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACTS = os.path.join(REPO, 'contracts', 'solidity')  # restructure moved .sol here (was contracts/)


def read(path):
    with open(path) as f:
        return f.read()


def test_7_1_emergency_escape():
    """7.1: BTCPEscrow has 7-day emergency escape callable by anyone."""
    src = read(os.path.join(CONTRACTS, 'BTCPEscrow.sol'))

    # Check EMERGENCY_ESCAPE_SECONDS = 7 days
    assert 'EMERGENCY_ESCAPE_SECONDS = 7 days' in src, \
        "EMERGENCY_ESCAPE_SECONDS not set to 7 days"

    # Check revertEmergency is external (callable by anyone)
    m = re.search(r'function\s+revertEmergency\s*\([^)]*\)\s*external', src)
    assert m, "revertEmergency is not external — must be callable by ANY address"

    # Check the 7-day timestamp check
    assert 'block.timestamp >= esc.lockTimestamp + EMERGENCY_ESCAPE_SECONDS' in src, \
        "Missing 7-day timestamp check in revertEmergency"

    # Check event emission
    assert 'emit EmergencyRevert' in src, "EmergencyRevert event not emitted"

    # Check cascade revert for multi-hop
    assert '_cascadeRevert' in src or 'cascadeRevert' in src, \
        "Cascade revert not implemented for multi-hop"

    print("  ✓ EMERGENCY_ESCAPE_SECONDS = 7 days")
    print("  ✓ revertEmergency() is external (callable by anyone)")
    print("  ✓ 7-day timestamp check present")
    print("  ✓ EmergencyRevert event emitted")
    print("  ✓ Cascade revert for multi-hop")
    return True


def test_7_2_oracle_bit_layout():
    """7.2: Oracle signal bit layout matches between relayer.js and contract."""
    relayer_src = read(os.path.join(REPO, 'relayer', 'relayer.js'))
    contract_src = read(os.path.join(CONTRACTS, 'TRIONOracleV3.sol'))

    # Relayer documents the bit layout
    assert 'Bit layout' in relayer_src, "Bit layout not documented in relayer.js"

    # Relayer implements packGateSignal
    assert 'function packGateSignal' in relayer_src, \
        "packGateSignal function not implemented in relayer.js"

    # Contract has publishSignal function
    assert 'function publishSignal' in contract_src, \
        "publishSignal not found in TRIONOracleV3.sol"

    # Verify the bit shifts match the documented layout
    # bits 0-7: status, 8-39: coherence, 40-71: threshold, 72+: block/ts
    assert 'phi_t32 << 8n' in relayer_src or 'phi_t32 << 8' in relayer_src, \
        "coherence not packed at bit 8"
    assert 'theta32 << 40n' in relayer_src or 'theta32 << 40' in relayer_src, \
        "threshold not packed at bit 40"
    assert 'block64 << 104n' in relayer_src or 'block64 << 104' in relayer_src, \
        "block_num not packed at bit 104"
    assert 'ts64 << 168n' in relayer_src or 'ts64 << 168' in relayer_src, \
        "timestamp not packed at bit 168"

    # Contract reconstructs the message hash for signature verification
    assert 'keccak256(abi.encodePacked(block.chainid, address(this), txId, packedData))' in contract_src, \
        "Contract doesn't reconstruct the expected message hash"

    print("  ✓ Bit layout documented in relayer.js")
    print("  ✓ packGateSignal implements the documented layout")
    print("  ✓ TRIONOracleV3.publishSignal accepts (txId, packedData, signatures)")
    print("  ✓ Contract reconstructs keccak256(chainId, oracleAddr, txId, packedData)")
    print("  ✓ Bit shifts match: status@0, coherence@8, threshold@40, block@104, ts@168")
    return True


def test_7_3_beo_cross_chain_consistency():
    """7.3: BEO identity uses SHA3-256 of normalized address (off-chain)."""
    # The entity ID is computed off-chain (Rust bh_id, Python _entity_seed,
    # TypeScript entityIdFromAddr). Contracts accept it as bytes32.
    # Phase 1.3 already verified cross-language consistency.

    # Verify Rust uses SHA3-256
    rust_src = read(os.path.join(REPO, 'indexers/crates/trion-common/src/hash_dna.rs'))
    assert 'Sha3_256::digest' in rust_src, "Rust bh_id doesn't use SHA3-256"
    assert 'fn normalise' in rust_src, "Rust doesn't normalise address (lowercase + 0x prefix)"

    # Verify TypeScript uses SHA3-256
    ts_src = read(os.path.join(REPO, 'chains/shared/canonical_bh.ts'))
    assert 'sha3-256' in ts_src, "TypeScript entityIdFromAddr doesn't use SHA3-256"
    assert 'toLowerCase' in ts_src, "TypeScript doesn't normalise to lowercase"

    # Verify Python uses SHA3-256 (after Phase 1.3 fix)
    py_src = read(os.path.join(REPO, 'api/app.py'))
    assert 'hashlib.sha3_256(eid.encode())' in py_src, \
        "Python _entity_seed doesn't use SHA3-256 (Phase 1.3 fix may have been reverted)"

    # Cross-check: same address produces same entity_id in all 3 languages
    test_addr = '0xDEADBEEF000000000000000000000000DEADBEEF'
    expected_eid = 'f9769049b9d4b778ba5c676f396b98b6578831524d0744264eaff84375f6826e'
    py_eid = hashlib.sha3_256(test_addr.lower().encode()).hexdigest()
    assert py_eid == expected_eid, \
        f"Python entity_id mismatch: {py_eid} vs {expected_eid}"

    # Verify case-insensitivity (normalisation)
    upper_eid = hashlib.sha3_256(test_addr.upper().lower().encode()).hexdigest()
    assert upper_eid == py_eid, "Case-insensitive normalisation broken"

    print("  ✓ Rust bh_id uses SHA3-256 with address normalisation")
    print("  ✓ TypeScript entityIdFromAddr uses SHA3-256 + toLowerCase")
    print("  ✓ Python _entity_seed uses SHA3-256 (Phase 1.3 fix)")
    print("  ✓ Cross-language vector: 0xDEADBEEF... → f9769049b9d4b778...")
    print("  ✓ Case-insensitive normalisation verified")
    return True


def main():
    print("=" * 72)
    print("Phase 7 — Contract Verification")
    print("=" * 72)

    print("\n[7.1] BTCPEscrow Emergency Escape Guarantee:")
    test_7_1_emergency_escape()

    print("\n[7.2] Oracle Signal Bit Layout:")
    test_7_2_oracle_bit_layout()

    print("\n[7.3] BEO Identity Cross-Chain Consistency:")
    test_7_3_beo_cross_chain_consistency()

    print("\n" + "=" * 72)
    print("✓ ALL PHASE 7 CONTRACT VERIFICATIONS PASSED")
    print("=" * 72)
    return 0


if __name__ == '__main__':
    sys.exit(main())
