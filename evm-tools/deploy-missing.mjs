// Deploy missing BTCP contracts (Intent, Route, LiquidityOcean) on Arb/OP/ETH Sepolia
import fs from 'fs';
import path from 'path';
import { ethers } from 'ethers';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const COMPILED = path.join(__dirname, 'compiled');
const PK = '***REDACTED-EVM-DEPLOYER-KEY***';

function loadArt(name) { return JSON.parse(fs.readFileSync(path.join(COMPILED, `${name}.json`), 'utf-8')); }

const chains = [
  { name: 'Arbitrum Sepolia', chainId: 421614,  rpc: 'https://sepolia-rollup.arbitrum.io/rpc', explorer: 'https://sepolia.arbiscan.io', existingEscrow: '0x506E59a84Bf0279a37e96046C92879BE8681578d' },
  { name: 'OP Sepolia',      chainId: 11155420, rpc: 'https://sepolia.optimism.io',            explorer: 'https://optimism-sepolia.blockscout.com', existingEscrow: '0xb617c96EA602A8FC79163E1745a68c38540f1c79' },
  { name: 'ETH Sepolia',     chainId: 11155111, rpc: 'https://ethereum-sepolia-rpc.publicnode.com', explorer: 'https://sepolia.etherscan.io', existingEscrow: '0xa1e1C9eEd94290757Bc08876EbCC30E1e39B9b82' },
];

// Load existing deployment record
const recordPath = path.join(__dirname, 'evm_sepolia_deployments.json');
let record;
try { record = JSON.parse(fs.readFileSync(recordPath, 'utf-8')); }
catch { record = { network: 'evm-sepolia-multi-chain', deployer: '0xdBbf66CAD621dA3Ec186D18b29a135d2A5d42d20', contracts: [] }; }

async function deploy(provider, wallet, name) {
  const art = loadArt(name);
  const factory = new ethers.ContractFactory(art.abi, art.bytecode, wallet);
  const c = await factory.deploy();
  await c.waitForDeployment();
  return await c.getAddress();
}

for (const c of chains) {
  console.log(`\n═══ ${c.name} (chainId ${c.chainId}) ═══`);
  const provider = new ethers.JsonRpcProvider(c.rpc, c.chainId, { staticNetwork: true });
  const wallet = new ethers.Wallet(PK, provider);
  const bal = await provider.getBalance(wallet.address);
  console.log(`  Balance: ${ethers.formatEther(bal)} ETH`);
  if (bal < ethers.parseEther('0.0003')) { console.log('  ✗ insufficient balance — skipping'); continue; }

  // Check which contracts already exist on this chain
  const chainTag = c.name.replace(' ', '').replace('Sepolia', 'Sepolia');
  const existing = record.contracts.filter(x => x.name.endsWith(`@${chainTag}`));
  const hasIntent = existing.some(x => x.name.startsWith('BTCPIntent'));
  const hasRoute = existing.some(x => x.name.startsWith('BTCPRoute'));
  const hasOcean = existing.some(x => x.name.startsWith('LiquidityOcean'));
  console.log(`  Existing: Escrow ✓, Intent ${hasIntent?'✓':'✗'}, Route ${hasRoute?'✓':'✗'}, Ocean ${hasOcean?'✓':'✗'}`);

  if (!hasIntent) {
    try {
      const addr = await deploy(provider, wallet, 'BTCPIntent');
      console.log(`  ✓ BTCPIntent: ${addr}`);
      record.contracts.push({ name: `BTCPIntent@${chainTag}`, chain: c.name.toLowerCase().replace(' ','-'), chainId: c.chainId, address: addr, explorer: `${c.explorer}/address/${addr}` });
    } catch(e) { console.log(`  ✗ BTCPIntent: ${e.message.slice(0,80)}`); }
  }
  if (!hasRoute) {
    try {
      const addr = await deploy(provider, wallet, 'BTCPRoute');
      console.log(`  ✓ BTCPRoute: ${addr}`);
      record.contracts.push({ name: `BTCPRoute@${chainTag}`, chain: c.name.toLowerCase().replace(' ','-'), chainId: c.chainId, address: addr, explorer: `${c.explorer}/address/${addr}` });
    } catch(e) { console.log(`  ✗ BTCPRoute: ${e.message.slice(0,80)}`); }
  }
  if (!hasOcean) {
    try {
      const addr = await deploy(provider, wallet, 'LiquidityOcean');
      console.log(`  ✓ LiquidityOcean: ${addr}`);
      record.contracts.push({ name: `LiquidityOcean@${chainTag}`, chain: c.name.toLowerCase().replace(' ','-'), chainId: c.chainId, address: addr, explorer: `${c.explorer}/address/${addr}` });
    } catch(e) { console.log(`  ✗ LiquidityOcean: ${e.message.slice(0,80)}`); }
  }
  fs.writeFileSync(recordPath, JSON.stringify(record, null, 2));
}

console.log('\n═══ FINAL EVM DEPLOYMENT COUNT ═══');
const byChain = {};
for (const c of record.contracts) { byChain[c.name.split('@')[1]] = (byChain[c.name.split('@')[1]] || 0) + 1; }
for (const [k,v] of Object.entries(byChain)) console.log(`  ${k}: ${v} contracts`);
console.log(`  TOTAL: ${record.contracts.length} contracts`);
