// Deploy BTCPEscrow (+ TRIONOracleV3, bound) on Arb Sepolia + OP Sepolia + ETH Sepolia.
//
// S3/C2 fix: each chain deploys its own TRIONOracleV3 (route-verdict
// signatures bind chainid + oracle address, so attestations are NOT
// cross-chain reusable) and binds the escrow to it — releases then require
// the validator signature quorum, not the relayer's word. TRUSTED_RELAYER_MODE=1
// skips binding (LOCAL DEV ONLY). Env: EVM_PRIVATE_KEY | PRIVATE_KEY,
// VALIDATOR_ADDRESSES (csv of extra validators).
import fs from 'fs';
import path from 'path';
import { ethers } from 'ethers';
import { fileURLToPath } from 'url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TRUSTED_RELAYER_MODE = process.env.TRUSTED_RELAYER_MODE === '1';
const PK = process.env.EVM_PRIVATE_KEY || process.env.PRIVATE_KEY;
function loadArt(name) { return JSON.parse(fs.readFileSync(path.join(__dirname, 'compiled', `${name}.json`), 'utf-8')); }
const chains = [
  { name: 'Arbitrum Sepolia', chainId: 421614,  rpc: 'https://sepolia-rollup.arbitrum.io/rpc' },
  { name: 'OP Sepolia',      chainId: 11155420, rpc: 'https://sepolia.optimism.io' },
  { name: 'ETH Sepolia',     chainId: 11155111, rpc: 'https://ethereum-sepolia-rpc.publicnode.com' },
];
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
  if (bal < ethers.parseEther('0.0003')) { console.log('  ✗ insufficient balance'); continue; }

  // 1) Consensus oracle (S3/C2): deployer = bootstrap validator #1 (relayer).
  const oracleAddr = await deploy(provider, wallet, 'TRIONOracleV3');
  const oracle = new ethers.Contract(oracleAddr, loadArt('TRIONOracleV3').abi, wallet);
  console.log(`  ✓ TRIONOracleV3: ${oracleAddr}`);
  for (const v of (process.env.VALIDATOR_ADDRESSES || '').split(',').map(s => s.trim()).filter(Boolean)) {
    await oracle.addValidator(v);
    console.log(`    ✓ validator: ${v}`);
  }
  const validatorCount = await oracle.validatorCount();
  console.log(`  · validators=${validatorCount} → route quorum N=${await oracle.minRouteAttestations()}`);
  if (validatorCount < 2) console.warn('  ⚠ <2 validators: verdicts never reach quorum (fail-closed) — set VALIDATOR_ADDRESSES.');

  // 2) Escrow, bound to this chain's oracle by default.
  const escrowAddr = await deploy(provider, wallet, 'BTCPEscrow');
  console.log(`  ✓ BTCPEscrow: ${escrowAddr}`);
  if (!TRUSTED_RELAYER_MODE) {
    const escrow = new ethers.Contract(escrowAddr, loadArt('BTCPEscrow').abi, wallet);
    await escrow.setTRIONOracle(oracleAddr);
    console.log(`  ✓ escrow BOUND to oracle ${oracleAddr} (signature-quorum release)`);
  } else {
    console.warn('  ⚠ TRUSTED_RELAYER_MODE=1 — escrow NOT bound (LOCAL DEV ONLY, DD S3/C2).');
  }

  const chainTag = c.name.replace(' ', '').replace('Sepolia', 'Sepolia');
  record.contracts.push({ name: `TRIONOracleV3@${chainTag}`, chain: c.name.toLowerCase().replace(' ', '-'), chainId: c.chainId, address: oracleAddr });
  record.contracts.push({ name: `BTCPEscrow@${chainTag}`, chain: c.name.toLowerCase().replace(' ', '-'), chainId: c.chainId, address: escrowAddr, trionOracle: TRUSTED_RELAYER_MODE ? null : oracleAddr });
  fs.writeFileSync(recordPath, JSON.stringify(record, null, 2));
}
console.log('\n═══ FINAL EVM DEPLOYMENT COUNT ═══');
console.log(`  TOTAL: ${record.contracts.length} contracts`);
