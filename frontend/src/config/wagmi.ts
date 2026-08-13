/**
 * Wagmi config — wallet connection for TRION Protocol
 * Supports 11 chains including BOT Chain (677)
 */
import { createConfig, http, cookieStorage, createStorage } from 'wagmi';
import {
  mainnet, base, arbitrum, optimism, polygon, bsc, avalanche,
  zksync, linea, scroll,
} from 'wagmi/chains';
import { metaMask, injected, coinbaseWallet } from 'wagmi/connectors';
import { defineChain } from 'viem';

// BOT Chain (ChainID 677)
export const botChain = defineChain({
  id: 677,
  name: 'BOT Chain',
  nativeCurrency: { name: 'BOT', symbol: 'BOT', decimals: 18 },
  rpcUrls: {
    default: { http: ['https://rpc.botchain.ai'] },
    public: { http: ['https://rpc.botchain.ai'] },
  },
  blockExplorers: {
    default: { name: 'BOT Scan', url: 'https://scan.botchain.ai' },
  },
});

// Contract addresses — AUTO-DETECT pattern
// null = not deployed yet; UI shows "Contracts deploying soon" gracefully
export const CONTRACTS: Record<string, Record<number, string | null>> = {
  btcpEscrow: {
    [mainnet.id]: null, [base.id]: null, [arbitrum.id]: null, [botChain.id]: null,
  },
  btcpIntent: {
    [mainnet.id]: null, [base.id]: null, [arbitrum.id]: null, [botChain.id]: null,
  },
  btcpRoute: {
    [mainnet.id]: null, [base.id]: null, [arbitrum.id]: null, [botChain.id]: null,
  },
  pmoRegistry: {
    [mainnet.id]: null, [base.id]: null, [botChain.id]: null,
  },
  beoIdentity: {
    [mainnet.id]: null, [base.id]: null,
    [botChain.id]: null,
  },
  oracleV3: {
    [botChain.id]: null,
  },
  bhLedger: {
    [botChain.id]: null,
  },
};

export function getContract(contractMap: Record<number, string | null>, chainId: number): string | null {
  return contractMap[chainId] || null;
}

export function isBTCPDeployed(chainId: number): boolean {
  return !!(CONTRACTS.btcpEscrow[chainId] || CONTRACTS.btcpIntent[chainId] || CONTRACTS.btcpRoute[chainId]);
}

export const supportedChains = [
  mainnet, base, arbitrum, optimism, polygon, bsc, avalanche,
  zksync, linea, scroll, botChain,
] as const;

export const wagmiConfig = createConfig({
  chains: [
    mainnet, base, arbitrum, optimism, polygon, bsc, avalanche,
    zksync, linea, scroll, botChain,
  ],
  connectors: [
    metaMask(),
    coinbaseWallet({ appName: 'TRION Protocol' }),
    injected(),
  ],
  transports: {
    [mainnet.id]: http(),
    [base.id]: http(),
    [arbitrum.id]: http(),
    [optimism.id]: http(),
    [polygon.id]: http(),
    [bsc.id]: http(),
    [avalanche.id]: http(),
    [zksync.id]: http(),
    [linea.id]: http(),
    [scroll.id]: http(),
    [botChain.id]: http('https://rpc.botchain.ai'),
  },
  storage: createStorage({ storage: cookieStorage }),
});
