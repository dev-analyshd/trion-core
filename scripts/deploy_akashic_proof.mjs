/**
 * Deploy AkashicProof contract to 0G Chain.
 * Run: node scripts/deploy_akashic_proof.mjs
 *
 * Prerequisites:
 *   npm install ethers
 *   Compile ABI first: npx hardhat compile
 *   Set ZG_PRIVATE_KEY env var
 */
import { ethers } from "ethers";
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "fs";
import { createRequire } from "module";

const require = createRequire(import.meta.url);

const RPC         = process.env.ZG_RPC         ?? "https://evmrpc-testnet.0g.ai";
const PRIVATE_KEY = process.env.ZG_PRIVATE_KEY  ?? process.env.DEPLOYER_PRIVATE_KEY ?? "";
const CHAIN_ID    = parseInt(process.env.ZG_CHAIN_ID ?? "16600");

if (!PRIVATE_KEY) {
  console.error("ERROR: ZG_PRIVATE_KEY not set");
  process.exit(1);
}

async function main() {
  console.log("╔══════════════════════════════════════════════╗");
  console.log("║  AkashicProof Contract Deployment — 0G Chain ║");
  console.log("╚══════════════════════════════════════════════╝");
  console.log(`Network:  ${RPC}`);
  console.log(`Chain ID: ${CHAIN_ID}`);

  const provider = new ethers.JsonRpcProvider(RPC);
  const signer   = new ethers.Wallet(PRIVATE_KEY, provider);
  const network  = await provider.getNetwork();

  console.log(`Deployer: ${signer.address}`);
  const balance = await provider.getBalance(signer.address);
  console.log(`Balance:  ${ethers.formatEther(balance)} OG`);

  if (balance === 0n) {
    console.error("ERROR: Deployer has no balance. Get testnet tokens from the 0G faucet.");
    process.exit(1);
  }

  // Load compiled ABI + bytecode
  const artifactPath = "artifacts/contracts/AkashicProof.sol/AkashicProof.json";
  if (!existsSync(artifactPath)) {
    console.error(`ERROR: ${artifactPath} not found. Run: npx hardhat compile`);
    process.exit(1);
  }

  const artifact = JSON.parse(readFileSync(artifactPath, "utf-8"));
  const factory  = new ethers.ContractFactory(artifact.abi, artifact.bytecode, signer);

  console.log("\nDeploying AkashicProof...");
  const contract    = await factory.deploy({ gasLimit: 3_000_000 });
  const deployTx    = contract.deploymentTransaction();
  console.log(`Tx hash: ${deployTx?.hash}`);

  await contract.waitForDeployment();
  const address = await contract.getAddress();

  console.log(`\n✓ AkashicProof deployed: ${address}`);
  console.log(`  Explorer: https://chainscan-newton.0g.ai/address/${address}`);

  // Save deployment record
  mkdirSync("0g-state/proofs", { recursive: true });
  const record = {
    contractAddress: address,
    deployerAddress: signer.address,
    txHash:          deployTx?.hash,
    chainId:         CHAIN_ID,
    network:         RPC,
    deployedAt:      new Date().toISOString(),
    explorerUrl:     `https://chainscan-newton.0g.ai/address/${address}`,
  };
  writeFileSync("0g-state/proofs/contract_deployment.json", JSON.stringify(record, null, 2));
  console.log("  Record saved: 0g-state/proofs/contract_deployment.json");

  // Verify deployed contract
  const deployed = new ethers.Contract(address, artifact.abi, provider);
  const proof    = await deployed.getFullProof();
  console.log(`\n✓ Verification:`);
  console.log(`  Protocol: ${proof[0]}`);
  console.log(`  Version:  ${proof[1]}`);
  console.log(`  Repo:     ${proof[9]}`);

  console.log(`\n  Set this in your environment:`);
  console.log(`  ZG_AKASHIC_CONTRACT=${address}`);
  console.log(`  ZG_AKASHIC_CONTRACT=${address}  # add to .env`);

  return address;
}

main()
  .then(address => {
    console.log(`\n✓ Done. Contract: ${address}`);
    process.exit(0);
  })
  .catch(err => {
    console.error("Deployment failed:", err.message ?? err);
    process.exit(1);
  });
