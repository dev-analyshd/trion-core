// Deploy BTCPEscrow on Arb Sepolia + OP Sepolia + ETH Sepolia
import fs from 'fs';
import path from 'path';
import { ethers } from 'ethers';
import { fileURLToPath } from 'url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PK = '***REDACTED-EVM-DEPLOYER-KEY***';
const art = JSON.parse(fs.readFileSync(path.join(__dirname, 'compiled', 'BTCPEscrow.json'), 'utf-8'));
const chains = [
  { name: 'Arbitrum Sepolia', chainId: 421614,  rpc: 'https://sepolia-rollup.arbitrum.io/rpc' },
  { name: 'OP Sepolia',      chainId: 11155420, rpc: 'https://sepolia.optimism.io' },
  { name: 'ETH Sepolia',     chainId: 11155111, rpc: 'https://ethereum-sepolia-rpc.publicnode.com' },
];
const recordPath = path.join(__dirname, 'evm_sepolia_deployments.json');
let record;
try { record = JSON.parse(fs.readFileSync(recordPath, 'utf-8')); }
catch { record = { network: 'evm-sepolia-multi-chain', deployer: '0xdBbf66CAD621dA3Ec186D18b29a135d2A5d42d20', contracts: [] }; }
for (const c of chains) {
  console.log(`\n═══ ${c.name} (chainId ${c.chainId}) ═══`);
  const provider = new ethers.JsonRpcProvider(c.rpc, c.chainId, { staticNetwork: true });
  const wallet = new ethers.Wallet(PK, provider);
  const bal = await provider.getBalance(wallet.address);
  console.log(`  Balance: ${ethers.formatEther(bal)} ETH`);
  if (bal < ethers.parseEther('0.0003')) { console.log('  ✗ insufficient balance'); continue; }
  const factory = new ethers.ContractFactory(art.abi, art.bytecode, wallet);
  const contract = await factory.deploy();
  await contract.waitForDeployment();
  const addr = await contract.getAddress();
  console.log(`  ✓ BTCPEscrow: ${addr}`);
  const chainTag = c.name.replace(' ', '').replace('Sepolia', 'Sepolia');
  record.contracts.push({ name: `BTCPEscrow@${chainTag}`, chain: c.name.toLowerCase().replace(' ','-'), chainId: c.chainId, address: addr });
  fs.writeFileSync(recordPath, JSON.stringify(record, null, 2));
}
console.log('\n═══ FINAL EVM DEPLOYMENT COUNT ═══');
console.log(`  TOTAL: ${record.contracts.length} contracts`);
