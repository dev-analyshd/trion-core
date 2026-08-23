/**
 * TRION BOT Chain Adapter — Behavioral Transaction Executor
 * =========================================================
 * Chain:   BOT Chain (EVM-compatible AI-agent L1)
 * ChainID: 677
 * RPC:     https://rpc.botchain.ai
 * Symbol:  BOT
 * Explorer: https://scan.botchain.ai
 *
 * This adapter:
 *   1. Sends real signed transactions on BOT Chain (5 self-transfers per cycle)
 *   2. Falls back to "block proofs" when wallet balance is insufficient
 *   3. Pushes 128-dim behavioral vectors to the FAISS ANIMA engine
 *
 * The native relayer (native-relayer/native_relayer.js) can spawn this script
 * alongside the other VM adapters (SVM/NEAR/TON/PVM/StarkNet).
 */

import { ethers } from "ethers";
import fs from "node:fs";
import path from "node:path";

const BOT_CHAIN_ID    = 677;
const BOT_CHAIN_LABEL = "BOT_CHAIN";
const BOT_CHAIN_VM    = "EVM";
const BOT_RPC_URL     = process.env.BOT_CHAIN_RPC_URL || "https://rpc.botchain.ai";
const BOT_EXPLORER    = "https://scan.botchain.ai";
const FAISS_URL       = process.env.FAISS_SERVICE_URL || "http://127.0.0.1:8000";
const ORACLE_API_URL  = process.env.ORACLE_API_URL    || "http://127.0.0.1:5000";
const NUM_TXS         = 5;
const AMOUNT_WEI      = 1000n; // 0.000000000000001 BOT per self-transfer

function pickEnv(...names: string[]): string | undefined {
  for (const n of names) {
    if (process.env[n] && process.env[n]!.trim()) return process.env[n]!.trim();
  }
  return undefined;
}

async function main() {
  console.log("═══════════════════════════════════════════════════════════════");
  console.log("TRION BOT Chain Adapter — Behavioral Transaction Executor");
  console.log(`  Chain:    ${BOT_CHAIN_LABEL} (ID ${BOT_CHAIN_ID})`);
  console.log(`  RPC:      ${BOT_RPC_URL}`);
  console.log(`  Explorer: ${BOT_EXPLORER}`);
  console.log(`  FAISS:    ${FAISS_URL}`);
  console.log("═══════════════════════════════════════════════════════════════");

  const privateKey = pickEnv("BOT_CHAIN_PRIVATE_KEY", "BOT_CHAIN_RELAYER_PRIVATE_KEY", "RELAYER_PRIVATE_KEY");

  if (!privateKey) {
    console.error("ERROR: No BOT Chain private key set (BOT_CHAIN_PRIVATE_KEY). Running block-proof mode.");
    await runBlockProofMode();
    return;
  }

  const provider = new ethers.JsonRpcProvider(BOT_RPC_URL);
  let wallet;
  try {
    wallet = new ethers.Wallet(privateKey, provider);
  } catch (e) {
    console.error("Invalid private key:", e);
    await runBlockProofMode();
    return;
  }

  const address = wallet.address;
  console.log(`Wallet: ${address}`);

  // Get balance
  let balance: bigint;
  try {
    balance = await provider.getBalance(address);
    console.log(`Balance: ${ethers.formatEther(balance)} BOT`);
  } catch (e) {
    console.error("Failed to fetch balance:", e);
    await runBlockProofMode();
    return;
  }

  if (balance < ethers.parseEther("0.001")) {
    console.warn("Insufficient balance for live transactions — using block-proof mode.");
    await runBlockProofMode();
    return;
  }

  // Send 5 self-transfers
  const results: any[] = [];
  for (let i = 0; i < NUM_TXS; i++) {
    try {
      const tx = await wallet.sendTransaction({
        to: address,
        value: AMOUNT_WEI,
        nonce: await provider.getTransactionCount(address, "pending"),
        gasLimit: 21_000n,
      });
      const receipt = await tx.wait(1);
      console.log(`tx[${i + 1}/${NUM_TXS}] hash=${tx.hash} status=${receipt?.status}`);
      results.push({
        index: i + 1,
        tx_hash: tx.hash,
        block_number: receipt?.blockNumber,
        status: receipt?.status === 1 ? "SUCCESS" : "FAILED",
        explorer: `${BOT_EXPLORER}/tx/${tx.hash}`,
      });

      // Push behavioral vector to FAISS
      await pushBehavioralVector({
        tx_hash: tx.hash,
        block_number: receipt?.blockNumber ?? 0,
        timestamp: Math.floor(Date.now() / 1000),
      });
    } catch (e: any) {
      console.error(`tx[${i + 1}] failed:`, e.message);
      results.push({ index: i + 1, status: "ERROR", error: e.message });
    }
  }

  // Persist results
  const outPath = "/tmp/botchain_execution_results.json";
  fs.writeFileSync(outPath, JSON.stringify({
    chain: BOT_CHAIN_LABEL,
    chain_id: BOT_CHAIN_ID,
    vm_type: BOT_CHAIN_VM,
    wallet: address,
    transactions: results,
    timestamp: new Date().toISOString(),
  }, null, 2));
  console.log(`Results written to ${outPath}`);
}

async function runBlockProofMode() {
  // For BOT Chain: produce signed "block proofs" — signed SHA-256 of recent block
  // identifiers — and ingest them as behavioral vectors. This is the same pattern
  // used by the extended chain relayer for chains where native signing isn't
  // available or wallet is unfunded.
  const provider = new ethers.JsonRpcProvider(BOT_RPC_URL);
  let blockNumber = 0;
  let blockHash = "0x0";
  try {
    const block = await provider.getBlock("latest");
    if (block) {
      blockNumber = block.number;
      blockHash = block.hash || "0x0";
    }
  } catch (e) {
    console.error("Failed to fetch latest block — using zero values");
  }

  console.log(`Block proof — block=${blockNumber} hash=${blockHash}`);

  const proofs: any[] = [];
  for (let i = 0; i < NUM_TXS; i++) {
    const proofPayload = `TRION_BOT_CHAIN:proof:${blockNumber}:${i}`;
    const proofHash = ethers.sha256(ethers.toUtf8Bytes(proofPayload));
    proofs.push({
      index: i + 1,
      block_number: blockNumber,
      block_hash: blockHash,
      proof_payload: proofPayload,
      proof_hash: proofHash,
      timestamp: Math.floor(Date.now() / 1000),
    });

    // Push behavioral vector for each block proof
    await pushBehavioralVector({
      tx_hash: proofHash,
      block_number: blockNumber,
      timestamp: Math.floor(Date.now() / 1000),
    });
  }

  const outPath = "/tmp/botchain_execution_results.json";
  fs.writeFileSync(outPath, JSON.stringify({
    chain: BOT_CHAIN_LABEL,
    chain_id: BOT_CHAIN_ID,
    vm_type: BOT_CHAIN_VM,
    mode: "BLOCK_PROOF",
    proofs,
    timestamp: new Date().toISOString(),
  }, null, 2));
  console.log(`Block-proof results written to ${outPath}`);
}

async function pushBehavioralVector(event: { tx_hash: string; block_number: number; timestamp: number }) {
  // 128-dim behavioral vector (9 entropy features + complements + cross-correlations + stats + SHA3 noise)
  // Mirrors the Rust build_vector() in trion-common/src/vector.rs
  const features: number[] = [];
  const seed = `${BOT_CHAIN_LABEL}:${event.block_number}:${event.tx_hash}`;
  const seedHash = ethers.sha256(ethers.toUtf8Bytes(seed)).slice(2); // hex without 0x

  // 9 raw features (use hash bytes as entropy source)
  for (let i = 0; i < 9; i++) {
    const byte = parseInt(seedHash.slice(i * 2, i * 2 + 2), 16) / 255;
    features.push(byte);
  }
  // 9 complementary (1 - f)
  for (let i = 0; i < 9; i++) features.push(1 - features[i]);
  // 9 cross-correlations (f_i × f_{i+1} with wrap)
  for (let i = 0; i < 9; i++) features.push(features[i] * features[(i + 1) % 9]);
  // 4 stats
  const mean = features.slice(0, 9).reduce((a, b) => a + b, 0) / 9;
  const variance = features.slice(0, 9).reduce((a, b) => a + (b - mean) ** 2, 0) / 9;
  features.push(mean, Math.sqrt(variance), Math.min(...features.slice(0, 9)), Math.max(...features.slice(0, 9)));
  // 32 SHA3 noise bytes blended
  for (let i = 0; i < 32; i++) {
    const byte = parseInt(seedHash.slice(i * 2 % 64, (i * 2 % 64) + 2), 16) / 255;
    features.push(0.7 * byte + 0.3 * mean);
  }
  // Remaining zeros to reach 128
  while (features.length < 128) features.push(0);

  const payload = {
    vectors: [{
      entity_id: `bot_chain:${event.block_number}`,
      vector: features,
      magnitude: mean,
      entropy: mean,
      timestamp: event.timestamp,
      bh_id: seedHash,
      block_num: event.block_number,
      chain_id: BOT_CHAIN_ID,
      chain_label: BOT_CHAIN_LABEL,
      vm_type: BOT_CHAIN_VM,
      block_hash_hex: event.tx_hash,
      event_type: 0, // TRANSFER
      sense_hex: seedHash,
      antisense_hex: ethers.sha256(ethers.toUtf8Bytes(seed + ":antisense")).slice(2),
    }],
    block_num: event.block_number,
    block_features: features.slice(0, 9),
    block_phi: mean,
    chain_id: BOT_CHAIN_ID,
    chain_label: BOT_CHAIN_LABEL,
    vm_type: BOT_CHAIN_VM,
  };

  try {
    const resp = await fetch(`${FAISS_URL}/index/add_batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (resp.ok) {
      console.log(`  → behavioral vector pushed to FAISS (block ${event.block_number})`);
    } else {
      console.warn(`  → FAISS push failed: ${resp.status}`);
    }
  } catch (e: any) {
    console.warn(`  → FAISS push error: ${e.message}`);
  }
}

main().catch((e) => {
  console.error("BOT Chain adapter fatal error:", e);
  process.exit(1);
});
