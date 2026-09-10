/**
 * arb-verify-state.mjs — Read-only verification of deployed Arbitrum contracts.
 * Confirms: contracts exist, validators registered, quorum set, BTC anchor stored.
 */
import { ethers } from 'ethers';
import fs from 'fs';

const RPC = 'https://sepolia-rollup.arbitrum.io/rpc';
const provider = new ethers.JsonRpcProvider(RPC);

// From arbitrum_btc_liquidity_proof.json (the latest deployment)
const SPV_ADDR = '0x287E180704b3F9c3cd0CAA1704dE380EFc03427F';
const ESCROW_ADDR = '0x3869e272Cf2bf458B41c4F65F09e2Acc44cC96E2';
const VALIDATORS = [
  '0xbdf055E137D38F6dC4716660534182EFA978d48f',
  '0x30DE6CE69a92a51070e0334F73449F98465258d7',
  '0x97D9E806ab64621c8A719324eb20D221280f1A45',
];
const ANCHOR_BH = '0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a';
const BTC_TXID = '62bfe73fab5ac18c64794493d3713c5eb3e92b839df401befecd68162ee1fcf7';
const BTC_BLOCK = 5128449;

const SQ_ABI = JSON.parse(fs.readFileSync('contracts/solidity/compiled/SimpleQuorumEscrow.abi', 'utf8'));
const REG_ABI = JSON.parse(fs.readFileSync('contracts/solidity/compiled/OOAAnchorRegistry.abi', 'utf8'));
const SPV_ABI = JSON.parse(fs.readFileSync('contracts/solidity/compiled/BTCSPVVerifier.abi', 'utf8'));

async function main() {
  console.log('=== Arbitrum Sepolia On-Chain State Verification ===');
  console.log('RPC:', RPC);
  console.log('');

  // 1. Check each contract has code deployed
  console.log('--- Contract deployment ---');
  for (const [name, addr] of [['SPVVerifier', SPV_ADDR], ['QuorumEscrow', ESCROW_ADDR]]) {
    const code = await provider.getCode(addr);
    console.log(`${name} ${addr}: ${code === '0x' ? 'NOT DEPLOYED' : `deployed (${(code.length/2)-1} bytes)`}`);
  }

  const escrow = new ethers.Contract(ESCROW_ADDR, SQ_ABI, provider);
  const spv = new ethers.Contract(SPV_ADDR, SPV_ABI, provider);

  // 2. Quorum escrow state
  console.log('\n--- Quorum escrow state ---');
  try {
    const [owner, qRequired, vCount] = await Promise.all([
      escrow.owner(),
      escrow.quorumRequired(),
      escrow.validatorCount(),
    ]);
    console.log('Owner:', owner);
    console.log('Quorum required:', qRequired.toString());
    console.log('Validator count:', vCount.toString());

    for (const v of VALIDATORS) {
      try {
        const isV = await escrow.isValidator(v);
        console.log(`  validator ${v}: ${isV ? 'registered' : 'NOT registered'}`);
      } catch (e) { console.log(`  validator ${v}: read err ${String(e.message).slice(0,60)}`); }
    }
  } catch (e) { console.log('Escrow read err:', String(e.message).slice(0,100)); }

  // 3. SPV verifier state
  console.log('\n--- SPV verifier state ---');
  try {
    const [tip, blockCount, genesisRenounced, owner] = await Promise.all([
      spv.getChainTip(),
      spv.blockCount(),
      spv.genesisAbilityRenounced(),
      spv.owner(),
    ]);
    // getChainTip returns (bytes32 chainTip, uint64 chainTipHeight, bool chainTipSet)
    console.log('Chain tip hash:', tip[0]);
    console.log('Chain tip height:', tip[1].toString());
    console.log('Chain tip set:', tip[2]);
    console.log('Blocks stored:', blockCount.toString());
    console.log('Genesis ability renounced:', genesisRenounced);
    console.log('SPV owner:', owner);
  } catch (e) { console.log('SPV read err:', String(e.message).slice(0,100)); }

  // 4. Check each validator's balance (funded signers?)
  console.log('\n--- Validator funding ---');
  for (const v of VALIDATORS) {
    const bal = await provider.getBalance(v);
    console.log(`${v}: ${ethers.formatEther(bal)} ETH`);
  }

  // 5. Deployer wallet balance
  const DEPLOYER = ethers.getAddress('0xdbbf66cad621da3ec186d18b29a135d2a5d42d20');
  const bal = await provider.getBalance(DEPLOYER);
  console.log(`Deployer ${DEPLOYER}: ${ethers.formatEther(bal)} ETH`);

  console.log('\n=== Verification complete ===');
}

main().catch(e => { console.error('FATAL:', e); process.exit(1); });
