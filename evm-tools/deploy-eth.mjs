// Deploy BTCPEscrow on ETH Sepolia
import fs from 'fs';
import path from 'path';
import { ethers } from 'ethers';
const PK = process.env.EVM_PRIVATE_KEY || process.env.PRIVATE_KEY;
const art = JSON.parse(fs.readFileSync(path.join('compiled', 'BTCPEscrow.json'), 'utf-8'));
const provider = new ethers.JsonRpcProvider('https://ethereum-sepolia-rpc.publicnode.com', 11155111, { staticNetwork: true });
const wallet = new ethers.Wallet(PK, provider);
console.log(`ETH Sepolia balance: ${ethers.formatEther(await provider.getBalance(wallet.address))} ETH`);
const factory = new ethers.ContractFactory(art.abi, art.bytecode, wallet);
const c = await factory.deploy();
await c.waitForDeployment();
const addr = await c.getAddress();
console.log(`✓ BTCPEscrow deployed on ETH Sepolia: ${addr}`);
console.log(`  tx: https://sepolia.etherscan.io/tx/${c.deploymentTransaction().hash}`);
const rec = JSON.parse(fs.readFileSync('evm_sepolia_deployments.json','utf-8'));
rec.contracts.push({ name: 'BTCPEscrow@EthSepolia', chain: 'ethereum-sepolia', chainId: 11155111, address: addr, txHash: c.deploymentTransaction().hash });
fs.writeFileSync('evm_sepolia_deployments.json', JSON.stringify(rec, null, 2));
