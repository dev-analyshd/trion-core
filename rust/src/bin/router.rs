//! BTCP Router binary
//! Standalone BTCP routing service

use trion_btcp::*;
use std::env;

fn main() {
    println!("TRION BTCP Zero-Bridge Router v{}", BTCP_VERSION);
    println!("========================================");

    let mut router = BTCPRouter::new();
    let bibl = BIBLEngine::new();

    // Demo: create a test route
    let intent = Intent {
        intent_id: H256::zero(),
        entity_id: H256::sha3(b"demo_entity"),
        source_address: "0x1F98431c8aD98523631AE4a59f267346ea31F984".to_string(),
        dest_address: "Vote111111111111111111111111111111111111111".to_string(),
        source_chain: 42161,
        dest_chain: 900,
        asset_in: "ETH".to_string(),
        asset_out: "SOL".to_string(),
        amount_in: 1_500_000_000_000_000_000u128,
        intent_type: "SWAP".to_string(),
        deadline: 1787141851,
        nonce: 42,
        constraints: IntentConstraints::default(),
        btcp_version: SemVer::new(1, 0, 0),
    };

    let analyses = vec![
        BIBLAnalysis {
            chain_id: 42161,
            nl_score: 0.82,
            gas_forecast: GasForecast::default(),
            cc_coherence: 0.85,
            beo_state: BEOState::default(),
            mf_score: 0.05,
            block_capacity: 0.9,
            finality_dist: FinalityDistribution::default(),
        },
        BIBLAnalysis {
            chain_id: 900,
            nl_score: 0.78,
            gas_forecast: GasForecast::default(),
            cc_coherence: 0.80,
            beo_state: BEOState::default(),
            mf_score: 0.03,
            block_capacity: 0.85,
            finality_dist: FinalityDistribution {
                mean_sec: 0.4,
                ci95: 0.98,
                safe_confirmations: 32,
            },
        },
    ];

    let route = router.create_route(intent, &analyses, 0.95, None);

    println!("\nRoute Created:");
    println!("  ID: {}", route.route_id);
    println!("  Type: {:?}", route.route_type);
    println!("  BTCP Score: {:.4}", route.btcp_score);
    println!("  Valid: {}", router.route_is_valid(&route));
    println!("  Status: {:?}", route.status);

    println!("\nBIBL Engine: {} chains tracked", bibl.get_all_states().len());
    println!("\nBTCP Router ready.");

    // Keep running if in service mode
    if env::args().any(|a| a == "--service") {
        println!("Running in service mode (Ctrl+C to exit)...");
        loop {
            std::thread::sleep(std::time::Duration::from_secs(60));
        }
    }
}
