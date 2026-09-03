/**
 * TRION Protocol — Starknet Sepolia Contract Verification
 * Reads back the on-chain state of all 7 deployed contracts.
 */
import 'dotenv/config';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { RpcProvider } from 'starknet';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SN = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'starknet_sepolia_deployments.json'), 'utf-8'));
function addr(name) { return SN.contracts.find(c => c.name === name).address; }
const provider = new RpcProvider({ nodeUrl: 'https://starknet-sepolia-rpc.publicnode.com' });

async function call(contractAddress, entrypoint, calldata = []) {
  try { const res = await provider.callContract({ contractAddress, entrypoint, calldata }); return { success: true, result: res }; }
  catch (e) { return { success: false, error: e.message.slice(0, 150) }; }
}

async function main() {
  console.log('═══════════════════════════════════════════════════════════');
  console.log('  TRION Protocol — Starknet Sepolia Contract Verification ');
  console.log('═══════════════════════════════════════════════════════════\n');
  const deployer = '0x7cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
  let pass = 0, total = 0;

  const checks = [
    { name: 'TRIONOracle',    address: addr('TRIONOracle'),    entrypoint: 'get_owner',        expected: deployer },
    { name: 'TRIONOracle',    address: addr('TRIONOracle'),    entrypoint: 'get_score_count' },
    { name: 'BEOAttestation', address: addr('BEOAttestation'), entrypoint: 'get_attester',    expected: deployer },
    { name: 'BEOAttestation', address: addr('BEOAttestation'), entrypoint: 'total_attestations' },
    { name: 'BTCFiGuard',     address: addr('BTCFiGuard'),     entrypoint: 'get_owner',        expected: deployer },
    { name: 'BTCFiGuard',     address: addr('BTCFiGuard'),     entrypoint: 'get_oracle',       expected: addr('TRIONOracle') },
    { name: 'BTCFiGuard',     address: addr('BTCFiGuard'),     entrypoint: 'get_safe_threshold' },
    { name: 'BTCPIntent',     address: addr('BTCPIntent'),     entrypoint: 'intent_count' },
    { name: 'BTCPRoute',      address: addr('BTCPRoute'),      entrypoint: 'route_count' },
    { name: 'BTCPEscrow',     address: addr('BTCPEscrow'),     entrypoint: 'escrow_count' },
    { name: 'LiquidityOcean', address: addr('LiquidityOcean'), entrypoint: 'get_owner',        expected: deployer },
    { name: 'LiquidityOcean', address: addr('LiquidityOcean'), entrypoint: 'get_routing_threshold' },
    { name: 'LiquidityOcean', address: addr('LiquidityOcean'), entrypoint: 'get_chain_count' },
    { name: 'LiquidityOcean', address: addr('LiquidityOcean'), entrypoint: 'get_ocean_score' },
  ];

  for (const c of checks) {
    const res = await call(c.address, c.entrypoint);
    total++;
    if (res.success) {
      const val = res.result[0];
      const ok = c.expected ? val === c.expected : true;
      console.log(`  ${ok ? '✓' : '✗'} ${c.name.padEnd(18)}.${c.entrypoint.padEnd(22)} = ${val}`);
      if (ok) pass++;
    } else {
      console.log(`  ✗ ${c.name.padEnd(18)}.${c.entrypoint.padEnd(22)} = ERROR: ${res.error}`);
    }
  }
  console.log(`\n  ${pass}/${total} contract reads succeeded`);
  console.log('═══════════════════════════════════════════════════════════\n');
}
main().catch(e => { console.error('✗', e.message); process.exit(1); });
