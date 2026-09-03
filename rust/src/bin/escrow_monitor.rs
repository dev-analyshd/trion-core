//! BTCP Escrow Monitor binary
//! Watches BTCP_ESCROW contracts on dual chains, triggers release/revert

use trion_btcp::*;
use std::env;

fn main() {
    println!("TRION BTCP Escrow Monitor v{}", BTCP_VERSION);
    println!("==============================================");

    let mut monitor = EscrowMonitor::new();

    // Demo: create dual-chain escrows for a route
    let route_id = H256::sha3(b"demo_route");
    let entity_a = H256::sha3(b"entity_A");
    let entity_b = H256::sha3(b"entity_B");

    let escrow_a_id = H256::sha3(b"escrow_arbitrum");
    let escrow_b_id = H256::sha3(b"escrow_solana");

    // Create escrows on both chains (created_block = observed chain height;
    // timeouts are anchored to the real lock height, not block 0)
    let escrow_a = monitor.create_escrow(
        escrow_a_id,
        entity_a,
        1_500_000_000_000_000_000u128, // 1.5 ETH
        42161, // Arbitrum
        100,       // timeout blocks
        200_000_000, // locked at observed Arbitrum height
    );

    let escrow_b = monitor.create_escrow(
        escrow_b_id,
        entity_b,
        5_000_000_000u128, // 5 SOL lamports equivalent
        900, // Solana
        100, // timeout blocks
        300_000_000, // locked at observed Solana slot
    );

    // Link escrows to route
    monitor.link_escrows_to_route(route_id, escrow_a_id, escrow_b_id);

    println!("\nDual-Chain Escrows Created:");
    println!("  Chain A (Arbitrum): {} — {} units — {:?}",
        escrow_a.chain_id, escrow_a.amount, escrow_a.state);
    println!("  Chain B (Solana):   {} — {} units — {:?}",
        escrow_b.chain_id, escrow_b.amount, escrow_b.state);

    // Process timeouts (should be none — checked just after lock height)
    let reverted = monitor.process_timeouts(200_000_050);
    println!("\nTimeouts at block 200_000_050: {}", reverted.len());

    // Demonstrate atomic release
    println!("\nExecuting atomic dual-chain release...");
    let success = monitor.atomic_release(&route_id);
    println!("Atomic release success: {}", success);

    // Verify both released
    if let Some((a, b)) = monitor.get_route_escrows(&route_id) {
        println!("  Escrow A: {:?}", a.state);
        println!("  Escrow B: {:?}", b.state);
    }

    println!("\nEscrow Monitor ready.");

    // Keep running if in service mode
    if env::args().any(|a| a == "--service") {
        println!("Running in service mode (Ctrl+C to exit)...");
        loop {
            std::thread::sleep(std::time::Duration::from_secs(60));
        }
    }
}
