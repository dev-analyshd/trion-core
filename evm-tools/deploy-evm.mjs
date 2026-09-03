// Deploy TRION BTCP contracts on EVM Base Sepolia
import fs from 'fs';
import path from 'path';
import { ethers } from 'ethers';
import { fileURLToPath } from 'url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const COMPILED = path.join(__dirname, 'compiled');
const PK = '***REDACTED-EVM-DEPLOYER-KEY***';
const RPC = 'https://base-sepolia-rpc.publicnode.com';
const CHAIN_ID = 84532;
const provider = new ethers.JsonRpcProvider(RPC, CHAIN_ID, { staticNetwork: true });
const wallet = new ethers.Wallet(PK, provider);
function loadArt(name) { return JSON.parse(fs.readFileSync(path.join(COMPILED, `${name}.json`), 'utf-8')); }
async function deploy(name) {
  const art = loadArt(name);
  const factory = new ethers.ContractFactory(art.abi, art.bytecode, wallet);
  const c = await factory.deploy();
  await c.waitForDeployment();
  return await c.getAddress();
}
async function main() {
  console.log('═══ TRION × EVM Base Sepolia — BTCP Contract Deploy ═══');
  console.log(`  Deployer: ${wallet.address}`);
  console.log(`  Balance:  ${ethers.formatEther(await provider.getBalance(wallet.address))} ETH\n`);
  const results = [];
  for (const name of ['BTCPEscrow', 'BTCPIntent', 'BTCPRoute', 'LiquidityOcean']) {
    const addr = await deploy(name);
    console.log(`  ✓ ${name}: ${addr}`);
    results.push({ name: `${name}@BaseSepolia`, address: addr });
  }
  const record = { network: 'evm-sepolia-multi-chain', deployer: wallet.address, contracts: results };
  fs.writeFileSync(path.join(__dirname, 'evm_sepolia_deployments.json'), JSON.stringify(record, null, 2));
  console.log('\n  ✅ Deployment complete');
}
main().catch(e => { console.error('✗', e.message); process.exit(1); });
