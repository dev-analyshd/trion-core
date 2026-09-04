/**
 * initialize_programs.ts
 *
 * Initializes the config PDA account for all three BTCP Solana programs.
 * Must be run once immediately after deployment.
 * Sets the deployer wallet as both owner and initial relayer.
 *
 * Usage:
 *   npx ts-node scripts/initialize_programs.ts
 *
 * Environment:
 *   SOLANA_KEYPAIR  - path to wallet keypair (default: ~/.config/solana/id.json)
 *   SOLANA_CLUSTER  - devnet | mainnet-beta (default: devnet)
 *   BTCP_ESCROW_ID  - deployed btcp_escrow program ID
 *   BTCP_INTENT_ID  - deployed btcp_intent program ID
 *   BTCP_ROUTE_ID   - deployed btcp_route program ID
 */

import * as anchor from "@project-serum/anchor";
import {
  Connection,
  Keypair,
  PublicKey,
  clusterApiUrl,
  LAMPORTS_PER_SOL,
} from "@solana/web3.js";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

// ── Configuration ────────────────────────────────────────────────────────────
const CLUSTER = process.env.SOLANA_CLUSTER || "devnet";
const KEYPAIR_PATH =
  process.env.SOLANA_KEYPAIR || path.join(os.homedir(), ".config", "solana", "id.json");

const PROGRAM_IDS = {
  escrow: new PublicKey(
    process.env.BTCP_ESCROW_ID || "BTCP111111111111111111111111111111111111111"
  ),
  intent: new PublicKey(
    process.env.BTCP_INTENT_ID || "BTCP222222222222222222222222222222222222222"
  ),
  route: new PublicKey(
    process.env.BTCP_ROUTE_ID || "BTCP333333333333333333333333333333333333333"
  ),
};

const SEED_CONFIG = Buffer.from("config");

// ── Minimal IDLs for initialize instruction ──────────────────────────────────
// We don't need the full IDL — just enough to call `initialize`.
// NOTE (Wave 2 / C-03): btcp_escrow.initialize now takes the deployment's
// canonical chain id (config/chain_registry.json — Solana = 900) and the
// certificate launch-threshold policy; the intent/route programs keep the
// argument-less form.
const BASE_IDL = {
  version: "0.1.0",
  name: "btcp_program",
  instructions: [
    {
      name: "initialize",
      accounts: [
        { name: "config", isMut: true, isSigner: false, pda: { seeds: [{ kind: "const", value: "config" }] } },
        { name: "payer", isMut: true, isSigner: true },
        { name: "systemProgram", isMut: false, isSigner: false },
      ],
      args: [],
    },
    {
      name: "setRelayer",
      accounts: [
        { name: "config", isMut: true, isSigner: false, pda: { seeds: [{ kind: "const", value: "config" }] } },
        { name: "owner", isMut: false, isSigner: true },
      ],
      args: [{ name: "newRelayer", type: "publicKey" }],
    },
  ],
};

const ESCROW_MINIMAL_IDL = {
  ...BASE_IDL,
  instructions: [
    {
      ...BASE_IDL.instructions[0],
      args: [
        { name: "selfChain", type: "u32" },
        { name: "minValidatorCount", type: "u32" },
      ],
    },
    BASE_IDL.instructions[1],
  ],
};

// btcp_escrow deploy-time policy (C-03 hardening):
//  - SELF_CHAIN: canonical TRION registry chain id of this deployment
//    (default 900 = Solana mainnet; devnet also 900 — the registry
//    distinguishes clusters, ids do not).
//  - MIN_VALIDATOR_COUNT: certificate launch threshold (V2 §9.2 — 100 on
//    mainnet; 3 = the hard liveness floor for devnet).
const SELF_CHAIN = Number(process.env.BTCP_SELF_CHAIN || 900);
const MIN_VALIDATOR_COUNT = Number(process.env.BTCP_MIN_VALIDATORS || 3);

// ── Helpers ──────────────────────────────────────────────────────────────────
function loadKeypair(p: string): Keypair {
  const data = JSON.parse(fs.readFileSync(p, "utf-8"));
  return Keypair.fromSecretKey(new Uint8Array(data));
}

async function initializeProgram(
  provider: anchor.AnchorProvider,
  programId: PublicKey,
  label: string,
  idl: any = BASE_IDL,
  args: any[] = []
): Promise<PublicKey> {
  const program = new anchor.Program(idl, programId, provider);

  const [configPda, bump] = PublicKey.findProgramAddressSync(
    [SEED_CONFIG],
    programId
  );

  console.log(`\n📋 Initializing ${label}...`);
  console.log(`   Program ID: ${programId.toBase58()}`);
  console.log(`   Config PDA: ${configPda.toBase58()} (bump: ${bump})`);

  try {
    const txSig = await (program.methods as any)
      .initialize(...args)
      .accounts({
        config: configPda,
        payer: provider.wallet.publicKey,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .rpc();

    console.log(`   ✅ Tx: ${txSig}`);
    console.log(`   Config PDA initialized successfully`);
  } catch (err: any) {
    if (err.message?.includes("already in use")) {
      console.log(`   ℹ️  Config PDA already initialized`);
    } else {
      throw err;
    }
  }

  return configPda;
}

// ── Main ─────────────────────────────────────────────────────────────────────
async function main() {
  console.log("═══════════════════════════════════════════════════════════════════");
  console.log("  BTCP Solana Programs — Config Initialization");
  console.log(`  Cluster: ${CLUSTER}`);
  console.log("═══════════════════════════════════════════════════════════════════");

  // Load wallet
  const wallet = loadKeypair(KEYPAIR_PATH);
  console.log(`\n👛 Wallet: ${wallet.publicKey.toBase58()}`);

  // Connect
  const connection = new Connection(
    CLUSTER === "mainnet-beta"
      ? clusterApiUrl("mainnet-beta")
      : clusterApiUrl("devnet"),
    "confirmed"
  );

  const balance = await connection.getBalance(wallet.publicKey);
  console.log(`💰 Balance: ${balance / LAMPORTS_PER_SOL} SOL`);

  if (balance < 0.05 * LAMPORTS_PER_SOL) {
    console.log("⚠️  Low balance — need SOL for rent (≈0.004 SOL per config PDA)");
    process.exit(1);
  }

  const provider = new anchor.AnchorProvider(
    connection,
    new anchor.Wallet(wallet),
    { commitment: "confirmed" }
  );

  // Initialize all three programs
  const results: Record<string, string> = {};

  results.btcp_escrow = (
    await initializeProgram(
      provider,
      PROGRAM_IDS.escrow,
      "btcp_escrow",
      ESCROW_MINIMAL_IDL,
      [SELF_CHAIN, MIN_VALIDATOR_COUNT]
    )
  ).toBase58();

  results.btcp_intent = (
    await initializeProgram(provider, PROGRAM_IDS.intent, "btcp_intent")
  ).toBase58();

  results.btcp_route = (
    await initializeProgram(provider, PROGRAM_IDS.route, "btcp_route")
  ).toBase58();

  // Output summary
  console.log("\n═══════════════════════════════════════════════════════════════════");
  console.log("  ✅ Initialization Complete");
  console.log("═══════════════════════════════════════════════════════════════════");
  console.log("\nConfig PDAs:");
  for (const [prog, pda] of Object.entries(results)) {
    console.log(`  ${prog}: ${pda}`);
  }
  console.log("\nOwner + Initial Relayer + Initial Registry Admin:", wallet.publicKey.toBase58());
  console.log("\n💡 Next steps:");
  console.log("   1. setRelayer() → your TRION relayer keypair");
  console.log("   2. setRegistryAdmin() → the TRION registrar (epoch registrations)");
  console.log("   3. bindPauseAuthority() → the TRION pause key (pause-only, never release)");
  console.log("   4. registerEpoch(1, entries, threshold) → first validator epoch");
  console.log("      (until epoch 1 is registered, NO certificate can release — fail-closed)");
}

main().catch((err) => {
  console.error("\n❌ Error:", err);
  process.exit(1);
});
