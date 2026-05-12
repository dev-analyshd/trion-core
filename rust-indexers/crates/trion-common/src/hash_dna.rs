/*!
 * HashDNA — L0.1 Behavioral Hash + entity ID generation.
 *
 * TWO separate concepts:
 *
 * 1. `bh_id(address)` — stable entity routing key (NOT the whitepaper BH).
 *    = SHA3-256(normalise(address))  →  64 hex chars.
 *
 * 2. `canonical_bh(...)` — whitepaper-exact L0.1 Behavioral Hash.
 *    93-byte payload:
 *      entity_id(32) || event_type(1) || magnitude_nano(8) ||
 *      context(8)    || timestamp(8)  || chain_id(4) || block_hash(32)
 *    sense     = SHA3-256(payload || 0x00)
 *    antisense = SHA3-256(payload || 0xFF) XOR NOT(sense)
 *    Invariant: sense XOR antisense == NOT(SHA3-256(payload || 0xFF))
 *
 * 3. `classify_event_type(selector)` — maps EVM 4-byte method selector to the
 *    canonical whitepaper EventType byte (0-19).
 *
 * EventType byte encoding (whitepaper L0.1 §2 — 20 canonical types):
 *   0=TRANSFER  1=SWAP       2=LIQUIDITY  3=BORROW    4=REPAY
 *   5=LIQUIDATE 6=GOVERNANCE 7=PROPOSAL   8=STAKE     9=UNSTAKE
 *  10=BRIDGE   11=DEPLOY    12=UPGRADE   13=MINT     14=BURN
 *  15=FLASH_LOAN 16=ORACLE_UPDATE 17=MEV_CAPTURE 18=AIRDROP 19=CLAIM
 */

use sha3::{Digest, Sha3_256};

// ── EventType classification ──────────────────────────────────────────────────

/// Classify an EVM method selector (first 8 hex chars of tx `input`) into
/// the canonical whitepaper EventType byte (0-19).
///
/// `selector` should be 8 lowercase hex chars (e.g. "38ed1739").
/// Returns 0 (TRANSFER) when selector is empty or unknown.
pub fn classify_event_type(selector: &str) -> u8 {
    let sel = selector.trim_start_matches("0x").to_lowercase();
    match sel.as_str() {
        // ── SWAP (1) ──────────────────────────────────────────────────────────
        "38ed1739" | // Uniswap V2 swapExactTokensForTokens
        "8803dbee" | // Uniswap V2 swapTokensForExactTokens
        "414bf389" | // Uniswap V3 exactInputSingle
        "c04b8d59" | // Uniswap V3 exactInput
        "db3e2198" | // Uniswap V3 exactOutputSingle
        "f28c0498" | // Uniswap V3 exactOutput
        "12aa3caf" | // 1inch V5 aggregation router
        "e449022e" | // 1inch V5 uniswapV3Swap
        "7c025200" | // 0x fillOrder
        "d9627aa4" | // 0x fillRfqOrder
        "791ac947" | // Uniswap V2 swapExactTokensForETH
        "fb3bdb41" | // Uniswap V2 swapETHForExactTokens
        "18cbafe5" | // Uniswap V2 swapExactETHForTokens
        "b6f9de95" | // Uniswap V2 swapExactETHForTokensSupportingFee
        "5c11d795"   // Uniswap V2 swapExactTokensForETHSupportingFee
            => 1,

        // ── LIQUIDITY (2) ────────────────────────────────────────────────────
        "e8e33700" | // Uniswap V2 addLiquidity
        "f305d719" | // Uniswap V2 addLiquidityETH
        "baa2abde" | // Uniswap V2 removeLiquidity
        "02751cec" | // Uniswap V2 removeLiquidityETH
        "88316456" | // Uniswap V3 mint (add liquidity range)
        "a34123a7" | // Uniswap V3 burn (remove range)
        "fc6f7865" | // Uniswap V3 collect fees
        "e8eda9df" | // AAVE V2 deposit
        "69328dec" | // AAVE V2 withdraw
        "617ba037" | // AAVE V3 supply
        "2e1a7d4d"   // WETH unwrap / remove liquidity
            => 2,

        // ── BORROW (3) ───────────────────────────────────────────────────────
        "a415bcad" | // AAVE V2/V3 borrow
        "c5ebeaec" | // Compound borrow
        "1249c58b" | // Compound borrow (V2 alt)
        "4b8a3529"   // MakerDAO draw (DAI)
            => 3,

        // ── REPAY (4) ────────────────────────────────────────────────────────
        "573ade81" | // AAVE repay
        "0e752702" | // Compound repay
        "4e4d9fea" | // Compound repayBorrow (V2)
        "83cc71c7"   // MakerDAO wipe
            => 4,

        // ── LIQUIDATE (5) ────────────────────────────────────────────────────
        "e6b43c49" | // AAVE liquidationCall
        "e7c77cb8"   // Compound liquidateBorrow
            => 5,

        // ── GOVERNANCE (6) ───────────────────────────────────────────────────
        "56781388" | // Compound Governor castVote
        "15373e3d" | // Governor Bravo castVote
        "7df5bd3b" | // Uniswap Governor castVote
        "095ea7b3"   // ERC20 approve (governance-adjacent signal)
            => 6,

        // ── PROPOSAL (7) ─────────────────────────────────────────────────────
        "7d5e81e2" | // OpenZeppelin Governor propose
        "da95691a"   // Governor Bravo propose
            => 7,

        // ── STAKE (8) ────────────────────────────────────────────────────────
        "a1903eab" | // Lido submit (ETH→stETH)
        "3a4b66f1" | // Generic stake()
        "e2bbb158" | // MasterChef deposit
        "b6b55f25"   // Generic deposit/stake
            => 8,

        // ── UNSTAKE (9) ──────────────────────────────────────────────────────
        "441a3e70" | // MasterChef withdraw
        "38d07436"   // Generic unstake
            => 9,

        // ── BRIDGE (10) ──────────────────────────────────────────────────────
        "9f8420b3" | // LayerZero send
        "0f41a04d" | // Arbitrum depositEth
        "8ef1332e" | // Optimism depositETH
        "b1a1a882"   // Hop bridge send
            => 10,

        // ── MINT (13) ────────────────────────────────────────────────────────
        "a0712d68" | // Compound cToken mint (supply)
        "40c10f19" | // ERC20 mint
        "d0def521"   // NFT safeMint
            => 13,

        // ── BURN (14) ────────────────────────────────────────────────────────
        "db006a75" | // Compound redeem
        "42966c68" | // ERC20 burn
        "9dc29fac"   // ERC20 burnFrom
            => 14,

        // ── FLASH_LOAN (15) ──────────────────────────────────────────────────
        "ab9c4b5d" | // AAVE flashLoan
        "5cffe9de"   // AAVE flashLoanSimple
            => 15,

        // ── ORACLE_UPDATE (16) ───────────────────────────────────────────────
        "a2e62045" | // Chainlink updateAnswer
        "c9807539"   // Chainlink OCR transmit
            => 16,

        // ── TRANSFER (0) / default ────────────────────────────────────────────
        "a9059cbb" | // ERC20 transfer
        "23b872dd"   // ERC20 transferFrom
            => 0,

        // Deploy: empty input → classified by caller checking input length
        // Everything else defaults to TRANSFER
        _ => 0,
    }
}

/// Map event type byte to its canonical whitepaper name.
pub fn event_type_name(et: u8) -> &'static str {
    match et {
        0  => "TRANSFER",
        1  => "SWAP",
        2  => "LIQUIDITY",
        3  => "BORROW",
        4  => "REPAY",
        5  => "LIQUIDATE",
        6  => "GOVERNANCE",
        7  => "PROPOSAL",
        8  => "STAKE",
        9  => "UNSTAKE",
        10 => "BRIDGE",
        11 => "DEPLOY",
        12 => "UPGRADE",
        13 => "MINT",
        14 => "BURN",
        15 => "FLASH_LOAN",
        16 => "ORACLE_UPDATE",
        17 => "MEV_CAPTURE",
        18 => "AIRDROP",
        19 => "CLAIM",
        _  => "TRANSFER",
    }
}

// ── Canonical BH (whitepaper L0.1 §3.1) ──────────────────────────────────────

/// Compute the whitepaper-canonical Behavioral Hash for a single transaction
/// event.
///
/// 93-byte payload layout (all big-endian):
///   [0..32]  entity_id_bytes  — 32 bytes decoded from entity_id_hex
///   [32]     event_type       — 1 byte (0-19)
///   [33..41] magnitude_nano   — u64 BE: magnitude_norm * 1e9
///   [41..49] context          — u64 BE: venue/layer flags
///   [49..57] timestamp_secs   — u64 BE
///   [57..61] chain_id         — u32 BE
///   [61..93] block_hash_bytes — 32 bytes decoded from block_hash_hex
///
/// sense     = SHA3-256(payload || 0x00)
/// antisense = SHA3-256(payload || 0xFF) XOR NOT(sense)   (byte-wise complement)
///
/// Invariant: sense XOR antisense == NOT(SHA3-256(payload || 0xFF))
///
/// Returns (sense_hex, antisense_hex) — each 64 lowercase hex chars.
pub fn canonical_bh(
    entity_id_hex:  &str,   // 64 hex chars (or shorter — zero-padded to 32 bytes)
    event_type:     u8,     // 0-19 per whitepaper §2
    magnitude_norm: f64,    // [0.0, 1.0] — encoded as nanounit
    context:        u64,    // 8-byte venue/layer flags
    timestamp_secs: u64,
    chain_id:       u64,
    block_hash_hex: &str,   // 64 hex chars (or shorter — zero-padded)
) -> (String, String) {
    let mut payload = Vec::with_capacity(94); // 93 + 1 suffix byte

    // entity_id: 32 bytes
    payload.extend_from_slice(&hex_to_32bytes(entity_id_hex));

    // event_type: 1 byte
    payload.push(event_type);

    // magnitude as nanounit: 8 bytes BE
    let mag_nano = (magnitude_norm.clamp(0.0, 1.0) * 1_000_000_000.0) as u64;
    payload.extend_from_slice(&mag_nano.to_be_bytes());

    // context: 8 bytes BE
    payload.extend_from_slice(&context.to_be_bytes());

    // timestamp: 8 bytes BE
    payload.extend_from_slice(&timestamp_secs.to_be_bytes());

    // chain_id: 4 bytes BE (u32)
    payload.extend_from_slice(&(chain_id as u32).to_be_bytes());

    // block_hash: 32 bytes
    payload.extend_from_slice(&hex_to_32bytes(block_hash_hex));

    debug_assert_eq!(payload.len(), 93, "canonical BH payload must be 93 bytes");

    // Dual-strand hashing
    let mut p0  = payload.clone(); p0.push(0x00);
    let mut pff = payload;         pff.push(0xFF);

    let sense:  [u8; 32] = Sha3_256::digest(&p0).into();
    let sha3ff: [u8; 32] = Sha3_256::digest(&pff).into();

    // antisense = sha3ff XOR NOT(sense)  (complement transform)
    let antisense: Vec<u8> = sha3ff.iter()
        .zip(sense.iter())
        .map(|(&ff, &s)| ff ^ !s)
        .collect();

    (hex::encode(sense), hex::encode(antisense))
}

fn hex_to_32bytes(s: &str) -> [u8; 32] {
    let s = s.trim_start_matches("0x");
    let mut out = [0u8; 32];
    let chars: Vec<char> = s.chars().collect();
    let byte_count = (chars.len() / 2).min(32);
    for i in 0..byte_count {
        let hi = chars[i * 2].to_digit(16).unwrap_or(0) as u8;
        let lo = chars.get(i * 2 + 1).and_then(|c| c.to_digit(16)).unwrap_or(0) as u8;
        out[i] = (hi << 4) | lo;
    }
    out
}

// ── Simple entity routing ID ──────────────────────────────────────────────────

/// Stable entity-routing key: SHA3-256(normalise(address)).
/// This is NOT the whitepaper BH — it is the entity lookup key used as the
/// primary FAISS index key and BEO canonical ID.
pub fn bh_id(raw: &str) -> String {
    let normalised = normalise(raw);
    hex::encode(Sha3_256::digest(normalised.as_bytes()))
}

/// Block-level pseudo-entity for block-aggregate vectors.
/// e.g. "arb_sepolia:18000000"
pub fn block_entity_id(chain_label: &str, block_num: u64) -> String {
    format!("{}:{}", chain_label.to_lowercase(), block_num)
}

fn normalise(raw: &str) -> String {
    let s = raw.trim().to_lowercase();
    if s.starts_with("0x") && s.len() >= 42 { return s; }
    if s.len() == 40 && s.chars().all(|c| c.is_ascii_hexdigit()) {
        return format!("0x{}", s);
    }
    s
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bh_id_case_insensitive() {
        let a = bh_id("0xDEADBEEF000000000000000000000000DEADBEEF");
        let b = bh_id("0xdeadbeef000000000000000000000000deadbeef");
        assert_eq!(a, b);
    }

    #[test]
    fn bh_id_len_64() {
        assert_eq!(bh_id("solana:slot:123456").len(), 64);
    }

    #[test]
    fn canonical_bh_output_lengths() {
        let (s, a) = canonical_bh(
            "abababababababababababababababababababababababababababababababababab",
            1, 0.5, 0, 1_700_000_000, 421_614,
            "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        );
        assert_eq!(s.len(), 64);
        assert_eq!(a.len(), 64);
        assert_ne!(s, a);
    }

    #[test]
    fn canonical_bh_antisense_invariant() {
        // Verify: antisense == sha3ff XOR NOT(sense)
        // => sense XOR antisense == NOT(sha3ff) == NOT(SHA3-256(payload||0xFF))
        let entity_hex = "ab".repeat(32);
        let block_hex  = "cc".repeat(32);
        let (sense_hex, antisense_hex) = canonical_bh(
            &entity_hex, 0, 0.5, 0, 1_700_000_000, 1, &block_hex,
        );
        let sense:     Vec<u8> = (0..32)
            .map(|i| u8::from_str_radix(&sense_hex[i*2..i*2+2], 16).unwrap()).collect();
        let antisense: Vec<u8> = (0..32)
            .map(|i| u8::from_str_radix(&antisense_hex[i*2..i*2+2], 16).unwrap()).collect();

        // Rebuild payload
        let mut payload = Vec::with_capacity(93);
        payload.extend_from_slice(&hex_to_32bytes(&entity_hex));
        payload.push(0u8);
        payload.extend_from_slice(&500_000_000u64.to_be_bytes());
        payload.extend_from_slice(&0u64.to_be_bytes());
        payload.extend_from_slice(&1_700_000_000u64.to_be_bytes());
        payload.extend_from_slice(&1u32.to_be_bytes());
        payload.extend_from_slice(&hex_to_32bytes(&block_hex));
        let mut pff = payload; pff.push(0xFF);
        let sha3ff: [u8; 32] = Sha3_256::digest(&pff).into();

        for i in 0..32 {
            assert_eq!(
                antisense[i], sha3ff[i] ^ !sense[i],
                "antisense invariant failed at byte {i}"
            );
        }
    }

    #[test]
    fn classify_selectors() {
        assert_eq!(classify_event_type("38ed1739"), 1);  // SWAP
        assert_eq!(classify_event_type("a9059cbb"), 0);  // TRANSFER
        assert_eq!(classify_event_type("a415bcad"), 3);  // BORROW
        assert_eq!(classify_event_type("ab9c4b5d"), 15); // FLASH_LOAN
        assert_eq!(classify_event_type(""),         0);  // default TRANSFER
    }

    #[test]
    fn event_type_names() {
        assert_eq!(event_type_name(0),  "TRANSFER");
        assert_eq!(event_type_name(1),  "SWAP");
        assert_eq!(event_type_name(15), "FLASH_LOAN");
        assert_eq!(event_type_name(19), "CLAIM");
        assert_eq!(event_type_name(20), "TRANSFER"); // out-of-range → default
    }
}
