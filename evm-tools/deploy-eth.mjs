// Deploy BTCPEscrow on ETH Sepolia — bound to a freshly deployed TRIONOracleV3
// (S3/C2 fix: consensus-gated release by default; TRUSTED_RELAYER_MODE=1 skips
// the binding for LOCAL DEV ONLY). Env: EVM_PRIVATE_KEY | PRIVATE_KEY,
// VALIDATOR_ADDRESSES (csv of extra validators).
import fs from 'fs';
import path from 'path';
import { ethers } from 'ethers';
const PK = process.env.EVM_PRIVATE_KEY || process.env.PRIVATE_KEY;
const TRUSTED_RELAYER_MODE = process.env.TRUSTED_RELAYER_MODE === '1';
const COMPILED = 'compiled';
const provider = new ethers.JsonRpcProvider('https://ethereum-sepolia-rpc.publicnode.com', 11155111, { staticNetwork: true });
const wallet = new ethers.Wallet(PK, provider);
function loadArt(name) { return JSON.parse(fs.readFileSync(path.join(COMPILED, `${name}.json`), 'utf-8')); }
async function deploy(name) {
  const art = loadArt(name);
  const factory = new ethers.ContractFactory(art.abi, art.bytecode, wallet);
  const c = await factory.deploy();
  await c.waitForDeployment();
  return await c.getAddress();
}
console.log(`ETH Sepolia balance: ${ethers.formatEther(await provider.getBalance(wallet.address))} ETH`);

// 1) Consensus oracle — deployer is bootstrap validator #1 (the relayer).
const oracleAddr = await deploy('TRIONOracleV3');
const oracle = new ethers.Contract(oracleAddr, loadArt('TRIONOracleV3').abi, wallet);
console.log(`✓ TRIONOracleV3: ${oracleAddr}`);
for (const v of (process.env.VALIDATOR_ADDRESSES || '').split(',').map(s => s.trim()).filter(Boolean)) {
  await oracle.addValidator(v);
  console.log(`  ✓ validator registered: ${v}`);
}
const validatorCount = await oracle.validatorCount();
const quorum = await oracle.minRouteAttestations();
console.log(`  · validators=${validatorCount} → route quorum N=${quorum}`);
if (validatorCount < 2) {
  console.warn('  ⚠ <2 validators: verdicts can never reach quorum (bound escrows fail closed).');
  console.warn('    Set VALIDATOR_ADDRESSES for a real deployment.');
}

// 2) Escrow — bound to the oracle by default.
const escrowAddr = await deploy('BTCPEscrow');
console.log(`✓ BTCPEscrow deployed on ETH Sepolia: ${escrowAddr}`);
if (!TRUSTED_RELAYER_MODE) {
  const escrow = new ethers.Contract(escrowAddr, loadArt('BTCPEscrow').abi, wallet);
  await escrow.setTRIONOracle(oracleAddr);
  console.log(`✓ escrow BOUND to oracle ${oracleAddr} (signature-quorum release)`);
} else {
  console.warn('⚠ TRUSTED_RELAYER_MODE=1 — escrow NOT bound (LOCAL DEV ONLY, DD S3/C2).');
}

const rec = JSON.parse(fs.readFileSync('evm_sepolia_deployments.json', 'utf-8'));
rec.contracts.push({ name: 'TRIONOracleV3@EthSepolia', chain: 'ethereum-sepolia', chainId: 11155111, address: oracleAddr });
rec.contracts.push({ name: 'BTCPEscrow@EthSepolia', chain: 'ethereum-sepolia', chainId: 11155111, address: escrowAddr, trionOracle: TRUSTED_RELAYER_MODE ? null : oracleAddr });
fs.writeFileSync('evm_sepolia_deployments.json', JSON.stringify(rec, null, 2));
