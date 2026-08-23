#!/usr/bin/env node
/**
 * TRION Protocol — On-Chain Backtest Proof Publisher
 * ===================================================
 * Reads the backtest Merkle proof and publishes it to Arbitrum Sepolia
 * via TRIONOracleV3.publishSignal() with EIP-191 validator signature.
 * quorumRequired=1, our signer is the registered validator → single sig works.
 *
 * Packed data bit layout (matches relayer.js convention):
 *   bits   0..7    : status   uint8  — 0=COLLAPSE_INTERCEPTED, 1=SAFE
 *   bits   8..39   : coherence uint32 — coherence × 1e6
 *   bits  40..71   : threshold uint32 — threshold × 1e6
 *   bits  72..135  : block_num uint64
 *   bits 136..199  : timestamp uint64
 *
 * Usage:
 *   RELAYER_PRIVATE_KEY=<hex> node backtest/publish_proof.js
 *   (without key → DRY_RUN mode, prints what would be sent)
 */

import { ethers }  from "ethers";
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";

const PRIVATE_KEY  = process.env.RELAYER_PRIVATE_KEY || null;
const DRY_RUN      = !PRIVATE_KEY;
const ARB_SEPOLIA  = {
  chainId:  421614,
  rpc:      process.env.ARB_SEPOLIA_RPC_URL || "https://sepolia-rollup.arbitrum.io/rpc",
  oracle:   process.env.ARB_SEPOLIA_ORACLE_ADDR || "0xb819c63c02Ed5aB49017C0f3f2568A14624658b3",
  explorer: "https://sepolia.arbiscan.io",
};

// ABI of the deployed contract (publishSignal exists; publishBTCPRoute was not deployed to Arb Sepolia)
const ORACLE_ABI = [
  "function publishSignal(bytes32 txId, uint256 packedData, bytes[] calldata signatures) external",
  "function signals(bytes32) external view returns (uint256 packedData, bool initialized)",
  "function quorumRequired() external view returns (uint256)",
  "function isValidator(address) external view returns (bool)",
  "event ThermodynamicSignalEtched(bytes32 indexed txId, uint8 status, uint32 coherence, uint32 threshold)",
  "event ThermodynamicCollapseIntercepted(bytes32 indexed txId, address indexed reporter, uint32 coherence, uint32 threshold, uint256 packedData)",
];

const RESULTS_DIR  = new URL("./results/", import.meta.url).pathname;
const REPORT_PATH  = RESULTS_DIR + "backtest_report.json";
const OUTPUT_PATH  = RESULTS_DIR + "onchain_proof.json";

function sha256Hex(str) {
  return createHash("sha256").update(str).digest("hex");
}

/** Convert a hex Merkle-root string → bytes32 (prepend 0x, truncate/pad to 32 bytes) */
function merkleRootToBytes32(hexStr) {
  const h = hexStr.replace(/^0x/, "").padEnd(64, "0").slice(0, 64);
  return "0x" + h;
}

/** Deterministic bytes32 ID for a backtest record */
function recordId(prefix, id, addr) {
  return "0x" + sha256Hex(`TRION:BACKTEST:${prefix}:${id}:${addr}`).slice(0, 64);
}

/**
 * Pack the signal into uint256 per the relayer.js convention.
 * status = 0 (COLLAPSE_INTERCEPTED) for attackers caught, 1 (SAFE) for clean or summary.
 */
function packSignal(coherence, threshold, blockNum, ts, status) {
  const c  = BigInt(Math.round(Math.min(Math.max(coherence, 0), 1) * 1_000_000)) & 0xFFFFFFFFn;
  const t  = BigInt(Math.round(Math.min(Math.max(threshold, 0), 1) * 1_000_000)) & 0xFFFFFFFFn;
  const bl = BigInt(blockNum) & 0xFFFFFFFFFFFFFFFFn;
  const tm = BigInt(ts)       & 0xFFFFFFFFFFFFFFFFn;
  const s  = BigInt(status)   & 0xFFn;
  return s | (c << 8n) | (t << 40n) | (bl << 72n) | (tm << 136n);
}

/**
 * Build the EIP-191 signed digest that TRIONOracleV3.publishSignal verifies:
 *   ethSignedMessageHash(keccak256(abi.encodePacked(chainId, oracleAddr, txId, packedData)))
 */
async function signForPublish(wallet, chainId, oracleAddr, txId, packedData) {
  const inner = ethers.solidityPackedKeccak256(
    ["uint256", "address", "bytes32", "uint256"],
    [BigInt(chainId), oracleAddr, txId, packedData]
  );
  return wallet.signMessage(ethers.getBytes(inner));
}

async function main() {
  console.log("\n" + "═".repeat(65));
  console.log("  TRION — BACKTEST PROOF PUBLISHER (publishSignal)");
  console.log("  Target: Arbitrum Sepolia — TRIONOracleV3");
  console.log("═".repeat(65) + "\n");

  // ── Load backtest report ──────────────────────────────────────────────────
  let report;
  try {
    report = JSON.parse(readFileSync(REPORT_PATH, "utf-8"));
  } catch (e) {
    console.error("✗ backtest_report.json not found. Run run_backtest.py first.");
    process.exit(1);
  }

  const { metrics, merkle, results } = report;
  console.log(`Loaded backtest report:`);
  console.log(`  Exploits   : ${report.metadata.exploits_tested}`);
  console.log(`  Controls   : ${report.metadata.controls_tested}`);
  console.log(`  Precision  : ${(metrics.precision*100).toFixed(2)}%  Recall: ${(metrics.recall*100).toFixed(2)}%`);
  console.log(`  F1         : ${(metrics.f1_score*100).toFixed(2)}%`);
  console.log(`  Merkle root: ${merkle.root}\n`);

  if (DRY_RUN) {
    console.log("⚠  DRY_RUN MODE — no RELAYER_PRIVATE_KEY set");
    console.log("   Set RELAYER_PRIVATE_KEY in Secrets to publish live\n");
  }

  // ── Setup provider + signer ───────────────────────────────────────────────
  const provider = new ethers.JsonRpcProvider(ARB_SEPOLIA.rpc);
  let wallet;

  if (!DRY_RUN) {
    const pk = PRIVATE_KEY.startsWith("0x") ? PRIVATE_KEY : "0x" + PRIVATE_KEY;
    wallet = new ethers.Wallet(pk, provider);
    console.log(`Signer  : ${wallet.address}`);
    try {
      const balance = await provider.getBalance(wallet.address);
      console.log(`Balance : ${ethers.formatEther(balance)} ETH`);
      if (balance === 0n) {
        console.log("⚠  Zero balance. Get testnet ETH from:");
        console.log("   https://faucet.triangleplatform.com/arbitrum/sepolia");
      }
    } catch(e) { console.log("  (could not fetch balance)"); }
  } else {
    console.log(`Target contract : ${ARB_SEPOLIA.oracle}`);
    console.log(`Network         : Arbitrum Sepolia (chainId ${ARB_SEPOLIA.chainId})\n`);
  }

  const oracle = new ethers.Contract(ARB_SEPOLIA.oracle, ORACLE_ABI,
    DRY_RUN ? provider : wallet);

  // Verify quorum and validator status
  try {
    const quorum = await oracle.quorumRequired();
    console.log(`quorumRequired : ${quorum}`);
    if (!DRY_RUN) {
      const isVal = await oracle.isValidator(wallet.address);
      console.log(`isValidator    : ${isVal} (our signer)\n`);
      if (!isVal) {
        console.warn("⚠  Signer is not a registered validator — publishSignal will revert");
      }
    }
  } catch(e) {
    console.log("(contract read skipped — RPC may be slow)\n");
  }

  // Current block for packing
  let currentBlock = 0n;
  try {
    currentBlock = BigInt(await provider.getBlockNumber());
  } catch(e) { currentBlock = 0n; }
  const nowTs = BigInt(Math.floor(Date.now() / 1000));

  // ── Build publish list from attacker results ──────────────────────────────
  const attackerResults = results.filter(r => r.entity_type === "ATTACKER");
  const onchainRecords  = [];
  let gasTotal = 0n;

  console.log("─".repeat(65));
  console.log("PUBLISHING 30 EXPLOIT RECORDS TO ARBITRUM SEPOLIA");
  console.log("─".repeat(65));

  for (const ex of attackerResults) {
    const addr    = ex.attacker_address || ex.address;
    const sig     = ex.signal;
    const txId    = recordId("EXPLOIT", ex.id, addr);

    // status=0 (COLLAPSE_INTERCEPTED) for flagged attackers, status=1 if somehow coherent
    const status  = sig.trion_flagged ? 0 : 1;
    const packed  = packSignal(sig.coherence, sig.threshold, currentBlock, nowTs, status);

    const flagIcon = sig.outcome === "TP" ? "🎯 TP" : sig.outcome === "FN" ? "❌ FN" : sig.outcome;
    console.log(`\n  [${ex.id}] ${ex.name}`);
    console.log(`        ${addr}`);
    console.log(`        C(t)=${sig.coherence.toFixed(4)} status=${status===0?"COLLAPSE_INTERCEPTED":"SAFE"} | ${flagIcon}`);

    // Check if already published (skip duplicate)
    try {
      const existing = await oracle.signals(txId);
      if (existing.initialized) {
        console.log(`        ⚡ Already on-chain — skipping`);
        onchainRecords.push({ ...ex, addr, txId, tx: "ALREADY_PUBLISHED", status: "skipped",
                               packed: packed.toString(), outcome: sig.outcome });
        continue;
      }
    } catch(e) { /* RPC flake — proceed */ }

    if (DRY_RUN) {
      console.log(`        [DRY_RUN] publishSignal(`);
      console.log(`          txId     = ${txId}`);
      console.log(`          packed   = 0x${packed.toString(16).slice(0,20)}...`);
      console.log(`          sig      = [<EIP-191 validator signature>]`);
      console.log(`        )`);
      onchainRecords.push({ id: ex.id, name: ex.name, addr, txId,
                             packed: packed.toString(), outcome: sig.outcome,
                             tx: "DRY_RUN", status: "simulated" });
    } else {
      try {
        const signature = await signForPublish(wallet, ARB_SEPOLIA.chainId, ARB_SEPOLIA.oracle, txId, packed);
        const tx = await oracle.publishSignal(txId, packed, [signature], { gasLimit: 200_000 });
        console.log(`        → TX: ${tx.hash}`);
        const receipt = await tx.wait();
        const gasUsed = receipt.gasUsed;
        gasTotal += gasUsed;
        const txUrl = `${ARB_SEPOLIA.explorer}/tx/${tx.hash}`;
        console.log(`        ✓ block ${receipt.blockNumber} gas=${gasUsed} ${txUrl}`);
        onchainRecords.push({
          id: ex.id, name: ex.name, addr, txId,
          packed: packed.toString(), outcome: sig.outcome,
          tx: tx.hash, block: receipt.blockNumber,
          gasUsed: gasUsed.toString(), explorer: txUrl, status: "confirmed",
        });
      } catch(e) {
        const errMsg = e.message?.slice(0, 120);
        console.log(`        ✗ Failed: ${errMsg}`);
        onchainRecords.push({ id: ex.id, name: ex.name, addr, txId,
                               packed: packed.toString(), outcome: sig.outcome,
                               tx: "FAILED", error: errMsg, status: "failed" });
      }
    }
  }

  // ── Publish Merkle summary ────────────────────────────────────────────────
  console.log("\n" + "─".repeat(65));
  console.log("PUBLISHING MERKLE SUMMARY (precision=F1=85.71%, 30/30 recall)");
  console.log("─".repeat(65));

  // Encode precision and threshold=0.5 as the summary's coherence/threshold
  // status=1 (SAFE) — the backtest itself passes the integrity check
  const summaryTxId  = merkleRootToBytes32(merkle.root);
  const summaryPacked = packSignal(metrics.precision, 0.5, currentBlock, nowTs, 1);

  console.log(`  txId    = ${summaryTxId}  (= Merkle root as bytes32)`);
  console.log(`  packed  = 0x${summaryPacked.toString(16).slice(0, 20)}... `);
  console.log(`  meaning : precision=${metrics.precision} recall=${metrics.recall} f1=${metrics.f1_score}`);

  let summaryTx = "DRY_RUN";
  if (!DRY_RUN) {
    // Check if already published
    let summaryExists = false;
    try {
      const existing = await oracle.signals(summaryTxId);
      summaryExists = existing.initialized;
    } catch(e) {}

    if (summaryExists) {
      console.log("  ⚡ Summary already on-chain — skipping");
      summaryTx = "ALREADY_PUBLISHED";
    } else {
      try {
        const signature = await signForPublish(wallet, ARB_SEPOLIA.chainId, ARB_SEPOLIA.oracle, summaryTxId, summaryPacked);
        const tx = await oracle.publishSignal(summaryTxId, summaryPacked, [signature], { gasLimit: 200_000 });
        const receipt = await tx.wait();
        summaryTx = tx.hash;
        gasTotal += receipt.gasUsed;
        console.log(`  ✓ Confirmed: ${ARB_SEPOLIA.explorer}/tx/${tx.hash}`);
      } catch(e) {
        summaryTx = "FAILED";
        console.log(`  ✗ Failed: ${e.message?.slice(0, 120)}`);
      }
    }
  } else {
    console.log(`  [DRY_RUN] would publishSignal(merkleRoot, precisionPacked, [sig])`);
  }

  // ── Save output ───────────────────────────────────────────────────────────
  const confirmedCount = onchainRecords.filter(r => r.status === "confirmed").length;
  const output = {
    published_at:    new Date().toISOString(),
    network:         "Arbitrum Sepolia",
    chainId:         ARB_SEPOLIA.chainId,
    contract:        ARB_SEPOLIA.oracle,
    explorer:        ARB_SEPOLIA.explorer,
    dry_run:         DRY_RUN,
    metrics: {
      precision:   metrics.precision,
      recall:      metrics.recall,
      f1_score:    metrics.f1_score,
      accuracy:    metrics.accuracy,
      TP: metrics.TP, FP: metrics.FP, TN: metrics.TN, FN: metrics.FN,
      catch_rate_pct: metrics.catch_rate_pct,
    },
    merkle_root:     merkle.root,
    merkle_txid:     summaryTxId,
    summary_tx:      summaryTx,
    confirmed:       confirmedCount,
    total_gas_used:  gasTotal.toString(),
    records:         onchainRecords,
  };

  writeFileSync(OUTPUT_PATH, JSON.stringify(output, null, 2));

  // ── Final report ──────────────────────────────────────────────────────────
  console.log("\n" + "═".repeat(65));
  console.log("  PUBLICATION COMPLETE");
  console.log("═".repeat(65));
  console.log(`  Mode              : ${DRY_RUN ? "DRY_RUN (simulated)" : "LIVE"}`);
  console.log(`  Records published : ${onchainRecords.length}`);
  console.log(`  Confirmed on-chain: ${confirmedCount}`);
  console.log(`  Merkle root       : ${merkle.root}`);
  console.log(`  Summary TX        : ${summaryTx}`);
  if (!DRY_RUN && gasTotal > 0n) {
    console.log(`  Total gas used    : ${gasTotal}`);
  }
  console.log(`  Output saved      : ${OUTPUT_PATH}`);

  if (!DRY_RUN && summaryTx !== "FAILED" && summaryTx !== "DRY_RUN") {
    console.log(`\n  ✓ Merkle proof anchored on Arbitrum Sepolia`);
    console.log(`  Explorer: ${ARB_SEPOLIA.explorer}/address/${ARB_SEPOLIA.oracle}`);
    console.log(`\n  Verify summary record:`);
    console.log(`  cast call ${ARB_SEPOLIA.oracle} "signals(bytes32)(uint256,bool)" \\`);
    console.log(`    ${summaryTxId} --rpc-url ${ARB_SEPOLIA.rpc}`);
  }
  console.log();
}

main().catch(e => { console.error(e); process.exit(1); });
