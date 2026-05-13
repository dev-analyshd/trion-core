/**
 * TRION BEO Attestation Tool
 * Run: WALLET=0x... pnpm --filter @workspace/starknet-trion attest
 *
 * Fetches the TRION resurrection/trajectory status for a Starknet wallet,
 * determines its credibility tier, and writes an on-chain attestation
 * to the BEOAttestation contract.
 *
 * Tiers:
 *   0 = BOOTSTRAP  (genesis_confidence < 0.30)
 *   1 = GENESIS    (0.30 <= genesis_confidence < 0.80)
 *   2 = MATURITY   (genesis_confidence >= 0.80)
 */
import 'dotenv/config';
import axios from 'axios';
import { Contract, shortString, cairo } from 'starknet';
import { getWorkingProvider, getAccount } from './provider.js';
import { STARKNET_CONFIG, TRION_TIER } from './config.js';
import { BEO_ATTESTATION_ABI } from './abi/BEOAttestation.js';

function classifyTier(genesisConfidence: number): number {
  if (genesisConfidence >= 0.80) return TRION_TIER.MATURITY;
  if (genesisConfidence >= 0.30) return TRION_TIER.GENESIS;
  return TRION_TIER.BOOTSTRAP;
}

async function main() {
  const walletAddress = process.env.WALLET ?? process.argv[2];
  if (!walletAddress) {
    throw new Error('Usage: WALLET=0x... pnpm attest  (or pass wallet address as first arg)');
  }

  const attestationAddress = STARKNET_CONFIG.contracts.BEOAttestation;
  if (!attestationAddress) {
    throw new Error('BEO_ATTESTATION_ADDRESS not set — run deploy.ts first');
  }

  console.log('═══════════════════════════════════════════════════════════');
  console.log('   TRION BEO Attestation                                   ');
  console.log('═══════════════════════════════════════════════════════════\n');
  console.log(`Wallet to attest: ${walletAddress}`);

  // Fetch from FAISS
  const faissBase = STARKNET_CONFIG.trion.faissBaseUrl;
  const entityId = walletAddress;

  const resRes = await axios.get(`${faissBase}/api/v1/resurrection_status/${entityId}`, { timeout: 8000 });
  const data = resRes.data;

  const beoId = data.beo_id as string;
  const gc    = data.confidence as number ?? 0;
  const tier  = classifyTier(gc);

  console.log(`BEO ID:             ${beoId}`);
  console.log(`Genesis Confidence: ${(gc * 100).toFixed(2)}%`);
  console.log(`Tier:               ${Object.keys(TRION_TIER).find(k => TRION_TIER[k as keyof typeof TRION_TIER] === tier)}`);

  const provider = await getWorkingProvider();
  const account  = getAccount(provider);
  const contract = new Contract({ abi: BEO_ATTESTATION_ABI, address: attestationAddress, providerOrAccount: account });

  const beoFelt    = BigInt('0x' + beoId.slice(0, 31));
  const gcBp       = BigInt(Math.round(Math.min(1, Math.max(0, gc)) * 10000));

  console.log('\nSubmitting attestation...');
  const tx = await contract.attest(
    walletAddress,
    beoFelt,
    BigInt(tier),
    gcBp,
  );

  console.log(`✓ Attested!`);
  console.log(`  Tx:      ${tx.transaction_hash}`);
  console.log(`  Voyager: ${STARKNET_CONFIG.explorer.voyager}/tx/${tx.transaction_hash}`);
  console.log(`  Contract: ${STARKNET_CONFIG.explorer.voyager}/contract/${attestationAddress}`);
}

main().catch(e => {
  console.error('\n✗ Attestation failed:', e.message);
  process.exit(1);
});
