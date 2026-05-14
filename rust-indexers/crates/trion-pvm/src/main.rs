/*!
 * TRION Polkadot (PVM) Behavioral Indexer — Rust
 * ===============================================
 * Polls Substrate REST API (Sidecar) for extrinsic data.
 *
 * PVM behavioral dimensions (9 Shannon entropy features):
 *   f1 — Extrinsic type diversity  H(pallet.method distribution)
 *   f2 — Account activity entropy  H(signer frequency)
 *   f3 — Fee entropy               H(fee bins)
 *   f4 — Transfer value entropy    H(value bins)
 *   f5 — Weight entropy            H(weight bins)
 *   f6 — Call depth entropy        H(batch_call_counts)
 *   f7 — Era/mortality entropy     H(mortal/immortal fraction)
 *   f8 — Tip entropy               H(tip bins)
 *   f9 — Success/failure entropy   H(success vs failed)
 */

use anyhow::Result;
use serde_json::Value;
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::time::{sleep, Duration};
use tracing::{info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, freq_entropy, histogram_entropy,
    entropy::ratio_entropy, BatchPayload, FaissClient, IndexerState, VectorEntry,
};

const CHAIN_ID:  u64  = 901;
const CHAIN_LBL: &str = "DOT_WESTEND";
const VM_TYPE:   &str = "PVM";

// Use Sidecar REST API (much easier than WS for pure-REST Rust)
const SIDECAR_URLS: &[&str] = &[
    "https://westend-api-sidecar.parity.io",
    "https://westend-api.polkadot.io",
    "https://westend.public.curie.radiumblock.co/http",
];

async fn fetch_block(client: &reqwest::Client, sidecar: &str, block_num: u64) -> Result<Value> {
    let url = format!("{}/blocks/{}", sidecar, block_num);
    let resp = client.get(&url).send().await?;
    if resp.status().is_success() {
        return Ok(resp.json().await?);
    }
    anyhow::bail!("Sidecar HTTP {}", resp.status())
}

async fn fetch_latest(client: &reqwest::Client, sidecar: &str) -> Result<u64> {
    let url = format!("{}/blocks/head", sidecar);
    let resp: Value = client.get(&url).send().await?.json().await?;
    let num = resp["number"].as_str().unwrap_or("0").parse::<u64>().unwrap_or(0);
    Ok(num)
}

fn extract_features(block: &Value) -> [f64; 9] {
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
    let (mut success, mut failed)  = (0u64, 0u64);

    for ext in exts {
        let pallet = ext["method"]["pallet"].as_str().unwrap_or("unknown");
        let method = ext["method"]["method"].as_str().unwrap_or("unknown");
        pallet_methods.push(format!("{}.{}", pallet, method));

        if let Some(sig) = ext["signature"].as_object() {
            if let Some(signer) = sig.get("signer") {
                signers.push(signer.to_string());
            }
            let era = &sig["era"];
            if era.is_null() || era.as_str() == Some("Immortal") {
                immortal += 1;
            } else {
                mortal += 1;
            }
            let tip = sig["tip"].as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0);
            tips.push(tip);
        } else {
            immortal += 1;
        }

        if let Some(fee) = ext["info"]["partialFee"].as_str().and_then(|s| s.parse::<f64>().ok()) {
            fees.push(fee);
        }

        // Extract value from args for Balances.transfer etc.
        if let Some(args) = ext["args"].as_object() {
            if let Some(v) = args.get("value").and_then(|v| v.as_str()).and_then(|s| s.parse::<f64>().ok()) {
                values.push(v);
            }
        }

        if let Some(w) = ext["info"]["weight"]["refTime"].as_str().and_then(|s| s.parse::<f64>().ok()) {
            weights.push(w);
        }

        // Batch call depth
        let calls = ext["args"]["calls"].as_array().map(|a| a.len()).unwrap_or(1);
        call_counts.push(calls as f64);

        // Success from events
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

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(12_000u64);
    let faiss     = FaissClient::new(&faiss_url)?;
    let mut state = IndexerState::new("pvm_dot_westend");
    let client    = reqwest::Client::builder().timeout(Duration::from_secs(15)).build()?;

    info!("TRION PVM Rust Indexer — chain={} label={} poll={}ms", CHAIN_ID, CHAIN_LBL, poll_ms);

    let mut sidecar_idx = 0usize;

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }

        let sidecar = SIDECAR_URLS[sidecar_idx % SIDECAR_URLS.len()];
        let latest = match fetch_latest(&client, sidecar).await {
            Ok(n)  => n,
            Err(e) => { warn!("PVM latest block error: {} — rotating", e); sidecar_idx += 1; sleep(Duration::from_millis(poll_ms)).await; continue; }
        };
        let last = state.last_block();
        let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        for block_num in from..=latest {
            let block = match fetch_block(&client, sidecar, block_num).await {
                Ok(b)  => b,
                Err(e) => { warn!("[{}] block {} error: {} — rotating", CHAIN_LBL, block_num, e); sidecar_idx += 1; continue; }
            };
            let features = extract_features(&block);
            let phi      = features.iter().sum::<f64>() / 9.0;
            let eid      = block_entity_id(CHAIN_LBL, block_num);
            let bh       = bh_id(&eid);
            let vector   = build_vector(&features, &format!("{}:{}", CHAIN_LBL, block_num));
            let ts       = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();

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
                Ok(added) => info!("[{}] block={} φ={:.4} added={}", CHAIN_LBL, block_num, phi, added),
                Err(e)    => warn!("[{}] FAISS failed: {}", CHAIN_LBL, e),
            }
            state.save(block_num).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
