/*!
 * TRION Polkadot (PVM) Behavioral Indexer — Rust
 * ===============================================
 * Dual-mode: prefers Substrate REST Sidecar for rich 9-feature extraction;
 * falls back automatically to direct JSON-RPC (chain_getBlock) when all
 * public sidecar instances are unreachable.
 * Produces 128-dim vectors AND per-tx canonical BH (L0.1 ledger).
 *
 * PVM behavioral dimensions (9 Shannon entropy features):
 *   f1 — Extrinsic type diversity  H(pallet.method distribution)  [sidecar] / tx_density [rpc]
 *   f2 — Account activity entropy  H(signer frequency)            [sidecar] / 0.5 [rpc]
 *   f3 — Fee entropy               H(fee bins)                    [sidecar] / 0.5 [rpc]
 *   f4 — Transfer value entropy    H(value bins)                  [sidecar] / 0.5 [rpc]
 *   f5 — Weight entropy            H(weight bins)                 [sidecar] / 0.5 [rpc]
 *   f6 — Call depth entropy        H(batch_call_counts)           [sidecar] / 0.5 [rpc]
 *   f7 — Era/mortality entropy     H(mortal/immortal fraction)    [sidecar] / 0.5 [rpc]
 *   f8 — Tip entropy               H(tip bins)                    [sidecar] / 0.5 [rpc]
 *   f9 — Success/failure entropy   H(success vs failed)           [sidecar] / fill [rpc]
 */

use anyhow::Result;
use serde_json::{json, Value};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::time::{sleep, Duration};
use tracing::{info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, canonical_bh, event_type_name,
    freq_entropy, histogram_entropy,
    entropy::ratio_entropy, BatchPayload, FaissClient, IndexerState, TxBhBatch, TxBhEntry, VectorEntry,
};

const CHAIN_ID:  u64  = 900;
const CHAIN_LBL: &str = "DOT_MAINNET";
const VM_TYPE:   &str = "PVM";

const SIDECAR_URLS: &[&str] = &[
    "https://polkadot-api-sidecar.parity.io",
    "https://polkadot.public.curie.radiumblock.co/http",
    "https://dot-api-sidecar.parity.io",
];

const RPC_URLS: &[&str] = &[
    "https://polkadot.api.onfinality.io/public",
    "https://polkadot-rpc.dwellir.com",
    "https://polkadot.public.blastapi.io",
    "https://1rpc.io/dot",
    "https://polkadot-rpc.publicnode.com",
];

const SIDECAR_FAIL_THRESHOLD: u32 = 6;

// ── Sidecar helpers ────────────────────────────────────────────────────────────

async fn sidecar_fetch_block(client: &reqwest::Client, base: &str, n: u64) -> Result<Value> {
    let url = format!("{}/blocks/{}", base, n);
    let resp = client.get(&url).send().await?;
    if resp.status().is_success() { return Ok(resp.json().await?); }
    anyhow::bail!("Sidecar HTTP {}", resp.status())
}

async fn sidecar_fetch_latest(client: &reqwest::Client, base: &str) -> Result<u64> {
    let url = format!("{}/blocks/head", base);
    let resp: Value = client.get(&url).send().await?.json().await?;
    let num = resp["number"].as_str().unwrap_or("0").parse::<u64>().unwrap_or(0);
    if num == 0 { anyhow::bail!("sidecar returned block number 0"); }
    Ok(num)
}

// ── Direct JSON-RPC helpers ────────────────────────────────────────────────────

async fn rpc_call(client: &reqwest::Client, url: &str, method: &str, params: Value) -> Result<Value> {
    let body = json!({ "jsonrpc": "2.0", "id": 1, "method": method, "params": params });
    let resp = client.post(url)
        .header("Content-Type", "application/json")
        .json(&body)
        .send().await?;
    if !resp.status().is_success() { anyhow::bail!("RPC HTTP {}", resp.status()); }
    let v: Value = resp.json().await?;
    if let Some(e) = v.get("error") { anyhow::bail!("RPC error: {}", e); }
    Ok(v["result"].clone())
}

async fn rpc_fetch_latest(client: &reqwest::Client, url: &str) -> Result<u64> {
    let hash   = rpc_call(client, url, "chain_getFinalizedHead", json!([])).await?;
    let header = rpc_call(client, url, "chain_getHeader", json!([hash])).await?;
    let hex    = header["number"].as_str().unwrap_or("0x0");
    let num    = u64::from_str_radix(hex.trim_start_matches("0x"), 16).unwrap_or(0);
    if num == 0 { anyhow::bail!("RPC returned block number 0"); }
    Ok(num)
}

async fn rpc_fetch_block(client: &reqwest::Client, url: &str, num: u64) -> Result<Value> {
    let hash = rpc_call(client, url, "chain_getBlockHash", json!([num])).await?;
    rpc_call(client, url, "chain_getBlock", json!([hash])).await
}

// ── Feature extractors ─────────────────────────────────────────────────────────

fn extract_features_sidecar(block: &Value) -> [f64; 9] {
    let exts = match block["extrinsics"].as_array() {
        Some(a) => a, None => return [0.5f64; 9],
    };
    if exts.is_empty() { return [0.5f64; 9]; }

    let mut pallet_methods: Vec<String> = Vec::new();
    let mut signers:        Vec<String> = Vec::new();
    let mut fees:           Vec<f64>    = Vec::new();
    let mut values:         Vec<f64>    = Vec::new();
    let mut weights:        Vec<f64>    = Vec::new();
    let mut call_counts:    Vec<f64>    = Vec::new();
    let (mut mortal, mut immortal) = (0u64, 0u64);
    let mut tips:           Vec<f64>    = Vec::new();
    let (mut success, mut failed) = (0u64, 0u64);

    for ext in exts {
        let pallet = ext["method"]["pallet"].as_str().unwrap_or("unknown");
        let method = ext["method"]["method"].as_str().unwrap_or("unknown");
        pallet_methods.push(format!("{}.{}", pallet, method));
        if let Some(sig) = ext["signature"].as_object() {
            if let Some(signer) = sig.get("signer") { signers.push(signer.to_string()); }
            let era = &sig["era"];
            if era.is_null() || era.as_str() == Some("Immortal") { immortal += 1; } else { mortal += 1; }
            let tip = sig["tip"].as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0);
            tips.push(tip);
        } else {
            immortal += 1;
        }
        if let Some(fee) = ext["info"]["partialFee"].as_str().and_then(|s| s.parse::<f64>().ok()) { fees.push(fee); }
        if let Some(args) = ext["args"].as_object() {
            if let Some(v) = args.get("value").and_then(|v| v.as_str()).and_then(|s| s.parse::<f64>().ok()) {
                values.push(v);
            }
        }
        if let Some(w) = ext["info"]["weight"]["refTime"].as_str().and_then(|s| s.parse::<f64>().ok()) { weights.push(w); }
        let calls = ext["args"]["calls"].as_array().map(|a| a.len()).unwrap_or(1);
        call_counts.push(calls as f64);
        let ok = ext["events"].as_array()
            .map(|evts| evts.iter().any(|e| e["method"]["method"].as_str() == Some("ExtrinsicSuccess")))
            .unwrap_or(true);
        if ok { success += 1; } else { failed += 1; }
    }

    [
        freq_entropy(&pallet_methods),
        freq_entropy(&signers),
        histogram_entropy(&fees, 8),
        histogram_entropy(&values, 8),
        histogram_entropy(&weights, 8),
        histogram_entropy(&call_counts, 8),
        ratio_entropy(mortal, mortal + immortal),
        histogram_entropy(&tips, 8),
        ratio_entropy(success, success + failed),
    ]
}

fn extract_features_rpc(block: &Value, block_num: u64) -> [f64; 9] {
    let exts      = block["block"]["extrinsics"].as_array();
    let ext_count = exts.map(|a| a.len()).unwrap_or(0);
    if ext_count == 0 { return [0.5f64; 9]; }
    let f1 = (ext_count as f64 / 100.0).min(1.0);
    let slot_frac = (block_num % 1000) as f64 / 1000.0;
    let lengths: Vec<f64> = exts.map(|a| {
        a.iter().map(|e| e.as_str().map(|s| (s.len() / 2) as f64).unwrap_or(0.0)).collect()
    }).unwrap_or_default();
    let len_entropy = histogram_entropy(&lengths, 8);
    [f1, 0.5, 0.5, 0.5, 0.5, slot_frac, 0.5, 0.5, len_entropy]
}

// ── Per-tx Behavioral Hash pipeline ──────────────────────────────────────────

static MAX_PLANCK: AtomicU64 = AtomicU64::new(10_000_000_000); // 1 DOT in planck

fn dot_magnitude(planck: u64) -> f64 {
    let old = MAX_PLANCK.load(Ordering::Relaxed);
    if planck > old { MAX_PLANCK.store(planck, Ordering::Relaxed); }
    let max = MAX_PLANCK.load(Ordering::Relaxed).max(1) as f64;
    let v   = planck as f64;
    ((v + 1.0).log10() / (max + 1.0).log10()).clamp(0.0, 1.0)
}

fn classify_dot_extrinsic(pallet: &str, method: &str) -> u8 {
    match pallet {
        "balances" | "assets" => match method {
            "transfer" | "transfer_all" | "transfer_keep_alive" | "transfer_allow_death" => 0, // TRANSFER
            "force_transfer"                                                               => 0,
            _                                                                              => 0,
        },
        "staking"             => match method {
            "bond" | "bond_extra" | "nominate" | "validate" => 8, // STAKE
            "unbond" | "withdraw_unbonded" | "chill"         => 9, // UNSTAKE
            _                                                 => 8,
        },
        "democracy" | "governance" | "referenda" | "conviction_voting" => 6, // GOVERNANCE
        "treasury"  => match method {
            "spend" | "approve_proposal"     => 6,  // GOVERNANCE
            "claim"                          => 19, // CLAIM
            _                                => 6,
        },
        "vesting"   => 9,  // UNSTAKE (vesting withdrawal)
        "utility"   => 0,  // TRANSFER (batch calls treated as generic)
        "contracts" | "evm" => match method {
            "instantiate" | "instantiate_with_code" => 11, // DEPLOY
            "call"                                   => 1,  // SWAP (generic contract call)
            _                                        => 11,
        },
        "nominationPools" => match method {
            "join" | "bond_extra" | "create" => 8, // STAKE
            "unbond" | "withdraw_unbonded"   => 9, // UNSTAKE
            "claim_payout"                   => 19, // CLAIM
            _                                => 8,
        },
        _ => 0, // TRANSFER
    }
}

fn pvm_bh_batch_sidecar(block: &Value, chain_id: u64, label: &str, block_num: u64, block_hash: &str, ts: u64) -> TxBhBatch {
    let exts = match block["extrinsics"].as_array() {
        Some(a) => a,
        None    => return TxBhBatch { chain_id, chain_label: label.to_string(), block_num, block_hash: block_hash.to_string(), timestamp: ts, entries: vec![] },
    };
    let mut entries: Vec<TxBhEntry> = Vec::new();

    for ext in exts {
        let tx_hash = ext["hash"].as_str().unwrap_or("").to_string();
        if tx_hash.is_empty() { continue; }

        // Skip unsigned (inherent) extrinsics
        if ext["signature"].is_null() { continue; }

        let signer = ext["signature"]["signer"].as_str().unwrap_or(
            ext["signature"]["signer"]["id"].as_str().unwrap_or("unknown")
        ).to_string();
        let pallet = ext["method"]["pallet"].as_str().unwrap_or("unknown");
        let method = ext["method"]["method"].as_str().unwrap_or("unknown");
        let et     = classify_dot_extrinsic(pallet, method);

        let planck = ext["args"]["value"].as_str()
            .and_then(|s| s.parse::<u64>().ok())
            .or_else(|| ext["args"]["amount"].as_str().and_then(|s| s.parse::<u64>().ok()))
            .unwrap_or(0);

        let mag = dot_magnitude(planck);
        let eid = bh_id(&signer);
        let (sense_hex, antisense_hex) = canonical_bh(&eid, et, mag, 0, ts, chain_id, block_hash);

        entries.push(TxBhEntry {
            tx_hash, from_addr: signer, to_addr: String::new(),
            event_type: et, event_type_name: event_type_name(et).to_string(),
            entity_id: eid, magnitude_norm: mag, value_wei: planck.to_string(),
            selector: format!("{}.{}", pallet, method),
            timestamp: ts, chain_id, chain_label: label.to_string(), block_num,
            block_hash: block_hash.to_string(), sense_hex, antisense_hex,
        });
    }

    TxBhBatch { chain_id, chain_label: label.to_string(), block_num, block_hash: block_hash.to_string(), timestamp: ts, entries }
}

// ── Main ───────────────────────────────────────────────────────────────────────

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(12_000u64);
    let faiss     = FaissClient::new(&faiss_url)?;
    let mut state = IndexerState::new("pvm_dot_mainnet");
    let client    = reqwest::Client::builder().timeout(Duration::from_secs(15)).build()?;

    info!("TRION PVM Rust Indexer — chain={} label={} poll={}ms (dual-mode: sidecar+rpc)", CHAIN_ID, CHAIN_LBL, poll_ms);

    let mut sidecar_idx   = 0usize;
    let mut rpc_idx       = 0usize;
    let mut sidecar_fails = 0u32;
    let mut use_rpc_mode  = false;

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }

        if use_rpc_mode && sidecar_idx % SIDECAR_URLS.len() == 0 {
            let probe = SIDECAR_URLS[0];
            if sidecar_fetch_latest(&client, probe).await.is_ok() {
                info!("Sidecar recovered — switching back to rich-feature mode");
                use_rpc_mode = false;
                sidecar_fails = 0;
            }
        }

        let latest = if !use_rpc_mode {
            let sidecar = SIDECAR_URLS[sidecar_idx % SIDECAR_URLS.len()];
            match sidecar_fetch_latest(&client, sidecar).await {
                Ok(n) => { sidecar_fails = 0; n }
                Err(e) => {
                    warn!("PVM sidecar [{}] error: {} — rotating", sidecar, e);
                    sidecar_idx += 1;
                    sidecar_fails += 1;
                    if sidecar_fails >= SIDECAR_FAIL_THRESHOLD {
                        warn!("PVM: {} consecutive sidecar failures — switching to JSON-RPC mode", sidecar_fails);
                        use_rpc_mode = true;
                    }
                    sleep(Duration::from_millis(poll_ms)).await;
                    continue;
                }
            }
        } else {
            let rpc = RPC_URLS[rpc_idx % RPC_URLS.len()];
            match rpc_fetch_latest(&client, rpc).await {
                Ok(n) => n,
                Err(e) => {
                    warn!("PVM RPC [{}] error: {} — rotating", rpc, e);
                    rpc_idx += 1;
                    sleep(Duration::from_millis(poll_ms)).await;
                    continue;
                }
            }
        };

        let last = state.last_block();
        let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        for block_num in from..=latest {
            let (features, block_data, mode_label) = if !use_rpc_mode {
                let sidecar = SIDECAR_URLS[sidecar_idx % SIDECAR_URLS.len()];
                match sidecar_fetch_block(&client, sidecar, block_num).await {
                    Ok(b) => {
                        let f = extract_features_sidecar(&b);
                        (f, b, "sidecar")
                    }
                    Err(e) => {
                        warn!("[{}] sidecar block {} error: {} — rotating", CHAIN_LBL, block_num, e);
                        sidecar_idx += 1;
                        sidecar_fails += 1;
                        if sidecar_fails >= SIDECAR_FAIL_THRESHOLD { use_rpc_mode = true; }
                        continue;
                    }
                }
            } else {
                let rpc = RPC_URLS[rpc_idx % RPC_URLS.len()];
                match rpc_fetch_block(&client, rpc, block_num).await {
                    Ok(b) => {
                        let f = extract_features_rpc(&b, block_num);
                        (f, b, "rpc")
                    }
                    Err(e) => {
                        warn!("[{}] RPC block {} error: {} — rotating", CHAIN_LBL, block_num, e);
                        rpc_idx += 1;
                        continue;
                    }
                }
            };

            let phi       = features.iter().sum::<f64>() / 9.0;
            let eid       = block_entity_id(CHAIN_LBL, block_num);
            let bh        = bh_id(&eid);
            let vector    = build_vector(&features, &format!("{}:{}", CHAIN_LBL, block_num));
            let ts        = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();
            let ts_u64    = ts as u64;
            let block_hash = bh_id(&format!("pvm_block:{}:{}", CHAIN_LBL, block_num));

            let payload = BatchPayload {
                vectors: vec![VectorEntry {
                    entity_id: eid, vector, magnitude: phi, entropy: phi, timestamp: ts,
                    bh_id: bh, block_num, chain_id: CHAIN_ID, chain_label: CHAIN_LBL.into(), vm_type: VM_TYPE.into(),
                    funding_source: None, block_hash_hex: None, event_type: None, sense_hex: None, antisense_hex: None,
                }],
                block_num, block_features: features.to_vec(), block_phi: phi,
                chain_id: CHAIN_ID, chain_label: CHAIN_LBL.into(), vm_type: VM_TYPE.into(),
            };

            match faiss.add_batch(&payload).await {
                Ok(added) => {
                    // Only emit per-tx BHs in sidecar mode (rich data)
                    let bh_stored = if mode_label == "sidecar" {
                        let tx_batch = pvm_bh_batch_sidecar(&block_data, CHAIN_ID, CHAIN_LBL, block_num, &block_hash, ts_u64);
                        faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0)
                    } else { 0 };
                    info!("[{}] block={} φ={:.4} added={} bh_stored={} mode={}", CHAIN_LBL, block_num, phi, added, bh_stored, mode_label);
                }
                Err(e) => warn!("[{}] FAISS failed: {}", CHAIN_LBL, e),
            }
            state.save(block_num).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
