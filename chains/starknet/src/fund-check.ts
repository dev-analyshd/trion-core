/**
 * TRION Fund Checker
 * Run: pnpm --filter @workspace/starknet-trion fund-check
 *
 * Checks account balance and prints faucet links if low.
 * Starknet Sepolia faucets:
 *   https://starknet-faucet.vercel.app
 *   https://faucet.reddio.com (Starknet Sepolia)
 */
import 'dotenv/config';
import { getWorkingProvider, getAccount, printAccountInfo } from './provider.js';
import { STARKNET_CONFIG } from './config.js';

async function main() {
  console.log('═══════════════════════════════════════════════════════════');
  console.log('   TRION × Starknet — Account Fund Check                   ');
  console.log('═══════════════════════════════════════════════════════════\n');

  const provider = await getWorkingProvider();
  const account  = getAccount(provider);

  await printAccountInfo(account, provider);

  console.log('\n── Starknet Sepolia Faucets ──────────────────────────────');
  console.log('  https://starknet-faucet.vercel.app');
  console.log('  https://faucet.reddio.com');
  console.log(`\n── Your Address ──────────────────────────────────────────`);
  console.log(`  ${account.address}`);
  console.log(`\n── Explorer ──────────────────────────────────────────────`);
  console.log(`  ${STARKNET_CONFIG.explorer.voyager}/contract/${account.address}`);
  console.log(`  ${STARKNET_CONFIG.explorer.starkscan}/contract/${account.address}`);
}

main().catch(e => {
  console.error('\n✗ Fund check failed:', e.message);
  process.exit(1);
});
