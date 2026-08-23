/**
 * TRION StarkNet — Real Transaction Executor (Sepolia)
 *
 * Derives the StarkNet account address from STARKNET_PRIVATE_KEY (against the
 * known Argent/OZ class hashes), attempts 5 real signed self-transfers of 1 wei
 * ETH on Sepolia, and ingests behavioral vectors into FAISS. If the account is
 * not deployed or has zero balance, gracefully falls back to producing real
 * Stark-curve signatures over recent block hashes (BLOCK_PROOFs), the same
 * pattern as the TON executor.
 *
 * Required env:
 *   STARKNET_PRIVATE_KEY       (hex)
 *   FAISS_URL                  (default: http://127.0.0.1:8000)
 *
 * Optional env:
 *   STARKNET_ACCOUNT_ADDRESS   (override derived address)
 */

import "dotenv/config";
import { Account, Contract, RpcProvider, ec, hash, CallData, num, cairo } from "starknet";
import fs from "node:fs";
import { getWorkingProvider } from "./src/provider.js";

const FAISS_URL  = process.env.FAISS_URL ?? "http://127.0.0.1:8000";
const CHAIN_ID   = 1300;
const VM_TYPE    = "STARKVM";
const N_TX       = parseInt(process.env.STK_TX_COUNT ?? "5");
const RESULTS_OUT = "/tmp/starknet_execution_results.json";

// Standard StarkNet Sepolia ETH token (universal across versions)
const ETH_TOKEN = "0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7";

const KNOWN_CLASS_HASHES: Record<string, { ch: string; build: (pub: string) => string[]; salt: (pub: string) => string }> = {
  "Argent X V3":         { ch: "0x036078334509b514626504edc9fb252328d1a240e4e948bef8d0c08dff45927f", build: pub => CallData.compile({ owner: pub, guardian: "0x0" }), salt: pub => pub },
  "Argent X V4":         { ch: "0x029927c8af6bccf3f6fda035981e765a7bdbf18a2dc0d630494f8758aa908e2b", build: pub => CallData.compile({ owner: pub, guardian: "0x0" }), salt: pub => pub },
  "OpenZeppelin 0.6":    { ch: "0x061dac032f228abef9c6626f995015233097ae253a7f72d68552db02f2971b8f", build: pub => CallData.compile({ publicKey: pub }),               salt: pub => pub },
  "OpenZeppelin 0.7":    { ch: "0x04ad3c1dc8413453db314497945b6903e1c766495a1e60492d44d33b5a1f3c0",   build: pub => CallData.compile({ publicKey: pub }),               salt: pub => pub },
};

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }

function shannonEntropy(values: number[]): number {
  const total = values.reduce((a, b) => a + b, 0);
  if (total === 0) return 0;
  return -values.filter(v => v > 0).map(v => { const p = v / total; return p * Math.log2(p); }).reduce((a, b) => a + b, 0);
}

function makeVector(blockNum: number, txIndex: number, signed: boolean, phi: number): number[] {
  const v = new Array(128).fill(0);
  const ent = shannonEntropy([txIndex + 1, blockNum % 100 + 1, signed ? 5 : 1]);
  v[0] = Math.min(1, txIndex / N_TX);
  v[1] = signed ? 1 : 0;
  v[2] = ent / 3.0;
  v[3] = (blockNum % 1000) / 1000;
  v[4] = phi;
  for (let i = 5; i < 128; i++) v[i] = Math.abs(Math.sin(blockNum * (i + 1))) * 0.1;
  return v;
}

async function ingestToFaiss(entityId: string, vector: number[], phi: number) {
  const payload = {
    vectors: [{ entity_id: entityId, vector, magnitude: phi, entropy: vector[2], chain_id: CHAIN_ID, vm_type: VM_TYPE }],
  };
  try {
    const res = await fetch(`${FAISS_URL}/index/add_batch`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload), signal: AbortSignal.timeout(10000),
    });
    return await res.json();
  } catch (e: any) {
    return { error: e?.message ?? String(e) };
  }
}

async function findAccountAddress(provider: RpcProvider, pk: string): Promise<{ address: string; flavour: string; pubKey: string } | null> {
  // Allow explicit override
  if (process.env.STARKNET_ACCOUNT_ADDRESS) {
    return { address: process.env.STARKNET_ACCOUNT_ADDRESS, flavour: "override", pubKey: ec.starkCurve.getStarkKey(pk) };
  }
  const pubKey = ec.starkCurve.getStarkKey(pk);
  // Probe each known wallet flavour; pick the first whose computed address has on-chain code
  for (const [name, { ch, build, salt }] of Object.entries(KNOWN_CLASS_HASHES)) {
    const cd  = build(pubKey);
    const s   = salt(pubKey);
    const addr = hash.calculateContractAddressFromHash(s, ch, cd, 0);
    try {
      const code = await provider.getClassHashAt(addr);
      if (code && code !== "0x0") return { address: addr, flavour: name + " (deployed)", pubKey };
    } catch { /* not deployed at this address — keep searching */ }
  }
  // Nothing deployed — return Argent V3 counterfactual address (the common default)
  const def = KNOWN_CLASS_HASHES["Argent X V3"];
  const addr = hash.calculateContractAddressFromHash(def.salt(pubKey), def.ch, def.build(pubKey), 0);
  return { address: addr, flavour: "Argent X V3 (counterfactual, undeployed)", pubKey };
}

async function getEthBalance(provider: RpcProvider, address: string): Promise<bigint> {
  try {
    const r = await provider.callContract({ contractAddress: ETH_TOKEN, entrypoint: "balanceOf", calldata: [address] });
    return BigInt(r[0]) + (BigInt(r[1]) << 128n);
  } catch { return 0n; }
}

async function isAccountDeployed(provider: RpcProvider, address: string): Promise<boolean> {
  try { const ch = await provider.getClassHashAt(address); return !!ch && ch !== "0x0"; }
  catch { return false; }
}

async function fireRealTransfers(provider: RpcProvider, account: Account, address: string, balance: bigint) {
  const results: any[] = [];
  // Send 1 wei back to self each time — minimum cost, maximum signal
  const transferCalldata = CallData.compile({ recipient: address, amount: cairo.uint256(1n) });

  // starknet v9: use account.getNonce() and let SDK auto-manage nonces
  let currentNonce: bigint;
  try {
    currentNonce = BigInt(await account.getNonce());
    console.log(`  ℹ Starting nonce: ${currentNonce}`);
  } catch (e: any) {
    console.warn(`  ⚠ Could not fetch nonce (${e?.message?.slice(0, 40)}), defaulting to 0`);
    currentNonce = 0n;
  }

  for (let i = 1; i <= N_TX; i++) {
    console.log(`\n  TX ${i}/${N_TX} — Building StarkNet self-transfer of 1 wei ETH (nonce=${currentNonce})...`);
    try {
      // starknet v9: execute() manages nonce internally; pass nonce as override only
      const { transaction_hash } = await (account as any).execute(
        {
          contractAddress: ETH_TOKEN,
          entrypoint:      "transfer",
          calldata:        transferCalldata,
        },
      );
      currentNonce++;
      console.log(`  ✓ TX broadcast: ${transaction_hash}`);
      const phi = 0.20 + i * 0.08;
      await ingestToFaiss(`STARKNET_TX_${transaction_hash}`, makeVector(i * 1000, i, true, phi), phi);
      console.log(`  ✓ FAISS ingested phi=${phi.toFixed(2)}`);
      results.push({ idx: i, real: true, hash: transaction_hash });
    } catch (e: any) {
      console.error(`  ✗ broadcast failed: ${e?.message ?? e}`);
      results.push({ idx: i, real: false, error: String(e?.message ?? e) });
      // Re-sync nonce from chain after any failure
      try {
        const resyncedNonce = BigInt(await account.getNonce());
        if (resyncedNonce > currentNonce) {
          console.log(`  ↻ Nonce re-synced: ${currentNonce} → ${resyncedNonce}`);
          currentNonce = resyncedNonce;
        }
      } catch { /* keep current nonce */ }
    }
    await sleep(3000);
  }
  return results;
}

async function fireBlockProofs(provider: RpcProvider, pk: string, derivedAddr: string) {
  // Sign recent block hashes with the Stark curve (real signatures, no on-chain submission)
  const results: any[] = [];
  let head: number;
  try { head = await provider.getBlockNumber(); }
  catch { head = 0; }

  for (let i = 0; i < N_TX; i++) {
    const blockNum = Math.max(0, head - i);
    let blockHash = "0x0";
    try {
      const b: any = await provider.getBlockWithTxHashes(blockNum);
      blockHash = b?.block_hash ?? "0x0";
    } catch { /* keep 0x0 */ }
    // hash a (blockHash, address, idx) tuple, sign with Stark curve
    const msgHash = hash.computeHashOnElements([blockHash, derivedAddr, num.toHex(i)]);
    let sigHex = "0x0";
    try {
      const sig = ec.starkCurve.sign(msgHash, pk);
      sigHex = sig.toCompactHex ? `0x${sig.toCompactHex()}` : `0x${sig.toString(16)}`;
    } catch (e: any) {
      console.error(`  ✗ Stark sign failed: ${e?.message ?? e}`);
    }
    const proofId = `STARKNET_BLOCK_PROOF_${blockNum}_${i}`;
    console.log(`  ✓ Signed block ${blockNum} (${blockHash.slice(0, 18)}…) → proof ${proofId}`);
    const phi = 0.05 + i * 0.04;
    await ingestToFaiss(proofId, makeVector(blockNum, i, true, phi), phi);
    console.log(`  ✓ FAISS ingested phi=${phi.toFixed(2)}`);
    results.push({ idx: i, real: false, blockHash, signature: sigHex, proofId });
    await sleep(800);
  }
  return results;
}

async function main() {
  console.log("╔══════════════════════════════════════════════════════════════════╗");
  console.log("║   TRION StarkNet — Real Transaction Executor (Sepolia)          ║");
  console.log("╚══════════════════════════════════════════════════════════════════╝");

  const pk = (process.env.STARKNET_PRIVATE_KEY ?? "").trim();
  if (!pk) {
    console.error("STARKNET_PRIVATE_KEY not set — cannot sign");
    process.exit(1);
  }

  const provider = await getWorkingProvider();
  const found = await findAccountAddress(provider, pk);
  if (!found) {
    console.error("Could not derive a StarkNet address from the provided key");
    process.exit(1);
  }
  console.log(`  Public key:    ${found.pubKey}`);
  console.log(`  Account addr:  ${found.address}`);
  console.log(`  Flavour:       ${found.flavour}`);

  const deployed = await isAccountDeployed(provider, found.address);
  const balance  = deployed ? await getEthBalance(provider, found.address) : 0n;
  console.log(`  Deployed:      ${deployed}`);
  console.log(`  ETH balance:   ${(Number(balance) / 1e18).toFixed(6)} ETH`);

  let results: any[];
  if (deployed && balance > 1000n) {
    // starknet v9: Account constructor takes a single options object
    const account = new Account({ provider: provider as any, address: found.address, signer: pk } as any);
    console.log(`\n  → Mode: REAL TRANSFERS (account is deployed and funded)`);
    results = await fireRealTransfers(provider, account, found.address, balance);
  } else {
    const reason = !deployed ? "account not yet deployed on Sepolia" : "balance too low for transfer";
    console.log(`\n  → Mode: BLOCK PROOFS (${reason})`);
    console.log(`     fund the account at https://starknet-faucet.vercel.app to switch to real transfers`);
    results = await fireBlockProofs(provider, pk, found.address);
  }

  console.log("\n  ════════════════════════════════════════");
  console.log("  STARKNET EXECUTION SUMMARY");
  console.log("  ════════════════════════════════════════");
  results.forEach(r => {
    if (r.real) console.log(`  TX ${r.idx}: ${r.hash}`);
    else if (r.proofId) console.log(`  TX ${r.idx + 1}: ${r.proofId}`);
    else console.log(`  TX ${r.idx}: ✗ ${r.error}`);
  });
  fs.writeFileSync(RESULTS_OUT, JSON.stringify({ address: found.address, flavour: found.flavour, deployed, balance: balance.toString(), results }, null, 2));
  console.log(`\n  Results saved to ${RESULTS_OUT}`);
}

main().catch(e => { console.error("\n✗ StarkNet execute fatal:", e?.message ?? e); process.exit(1); });
