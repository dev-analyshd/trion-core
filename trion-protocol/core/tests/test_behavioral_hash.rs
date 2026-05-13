use trion_core::{BehavioralHash, HashDNA, EventType, normalize_magnitude};
use chrono::Utc;

#[test]
fn test_hash_dna_verify() {
    let bh = BehavioralHash::new(
        "BEO_test123".to_string(),
        EventType::Transfer,
        1_000_000.0,
        10_000_000.0,
        "USDC".to_string(),
        Utc::now(),
        42161,
        "0xabc123".to_string(),
    ).unwrap();
    assert!(bh.verify(), "Fresh BH must verify");
    assert!(bh.magnitude_normalized >= 0.0);
    assert!(bh.magnitude_normalized <= 1.0);
}

#[test]
fn test_xor_invariant_holds() {
    let dna = HashDNA::new(b"TRION_L0_test_input");
    // sense XOR antisense == complement_invariant == NOT(anti_raw)
    let mut xor_result = [0u8; 32];
    for i in 0..32 {
        xor_result[i] = dna.sense[i] ^ dna.antisense[i];
    }
    assert_eq!(xor_result, dna.complement_invariant,
        "Dual-strand XOR invariant: sense XOR antisense must equal NOT(anti_raw)");
}

#[test]
fn test_tamper_detection_sense() {
    let mut dna = HashDNA::new(b"original_input");
    assert!(dna.verify(), "Unmodified DNA must verify");
    dna.sense[0] ^= 0xFF;
    assert!(!dna.verify(), "Tampered sense must fail verification");
}

#[test]
fn test_tamper_detection_antisense() {
    let mut dna = HashDNA::new(b"original_input_2");
    assert!(dna.verify(), "Unmodified DNA must verify");
    dna.antisense[7] ^= 0x01;
    assert!(!dna.verify(), "Tampered antisense must fail verification");
}

#[test]
fn test_magnitude_normalization() {
    let mag = normalize_magnitude(100_000.0, 10_000_000.0);
    assert!(mag > 0.0 && mag < 1.0);

    let mag_max = normalize_magnitude(10_000_000.0, 10_000_000.0);
    assert!((mag_max - 1.0).abs() < 1e-6);

    let mag_zero = normalize_magnitude(0.0, 10_000_000.0);
    assert_eq!(mag_zero, 0.0);
}

#[test]
fn test_all_event_types_unique_bytes() {
    use std::collections::HashSet;
    let types = vec![
        EventType::Transfer, EventType::Swap, EventType::Liquidity,
        EventType::Stake, EventType::Unstake, EventType::Governance,
        EventType::Proposal, EventType::Borrow, EventType::Repay,
        EventType::Liquidate, EventType::Bridge, EventType::Deploy,
        EventType::Upgrade, EventType::Mint, EventType::Burn,
        EventType::OracleUpdate, EventType::MevCapture, EventType::FlashLoan,
        EventType::Airdrop, EventType::Claim,
    ];
    let bytes: HashSet<u8> = types.iter().map(|t| t.type_byte()).collect();
    assert_eq!(bytes.len(), 20, "All 20 event types must have unique type bytes");
}

#[test]
fn test_beo_cluster_validity() {
    use trion_core::AddressCluster;

    let strong = AddressCluster::compute(
        vec!["0xAAA".to_string(), "0xBBB".to_string()],
        0.95, 0.88, 0.80, 0.82,
    );
    assert!(strong.is_valid);
    assert!(strong.confidence > 0.75);
    assert!(strong.entity_id.is_some());

    let weak = AddressCluster::compute(
        vec!["0xCCC".to_string(), "0xDDD".to_string()],
        0.10, 0.15, 0.20, 0.05,
    );
    assert!(!weak.is_valid);
    assert!(weak.entity_id.is_none());
}

#[test]
fn test_different_inputs_different_dna() {
    let dna1 = HashDNA::new(b"input_one");
    let dna2 = HashDNA::new(b"input_two");
    assert_ne!(dna1.sense, dna2.sense, "Different inputs must produce different sense");
    assert_ne!(dna1.antisense, dna2.antisense, "Different inputs must produce different antisense");
}
