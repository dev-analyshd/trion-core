// TRION Protocol — Complete Chain Registry
// 25+ chains · 11 VM families · Bitcoin + all major L1s
// CC0 — Hudu Yusuf (Analys) · 2026

export type VMType =
  | "EVM" | "UTXO" | "SVM" | "PVM" | "TVM" | "NEAR"
  | "MVM" | "COSMOS" | "MOVE" | "STARKNET" | "SUI";

export interface ChainConfig {
  id:           number;
  name:         string;
  vm:           VMType;
  symbol:       string;
  rpc:          string;
  explorer:     string;
  isTestnet:    boolean;
  envKey:       string;
  decimals:     number;
  btcpSupport:  boolean;
  trionSupport: boolean;
}

export const CHAIN: Record<string, number> = {
  // ── EVM Testnets (existing) ──
  ETH_SEPOLIA:     11155111,
  ARB_SEPOLIA:     421614,
  BASE_SEPOLIA:    84532,
  BNB_TESTNET:     97,
  HASHKEY_TESTNET: 133,
  ZG_GALILEO:      16602,

  // ── Bitcoin & UTXO ──
  BTC_TESTNET:     2000,
  BTC_TAPROOT:     2001,
  BTC_SEGWIT:      2002,
  LTC_TESTNET:     2010,
  DOGE_TESTNET:    2020,
  DASH_TESTNET:    2030,

  // ── Tron ──
  TRON_SHASTA:     3001,

  // ── Cosmos Ecosystem ──
  COSMOS_TESTNET:  4001,
  DYDX_TESTNET:    4002,
  SEI_TESTNET:     4003,
  KAVA_TESTNET:    4004,
  INITIA_TESTNET:  4005,
  INJECTIVE_TESTNET: 4006,

  // ── Move Ecosystem ──
  APTOS_TESTNET:   5001,
  MOVEMENT_TESTNET: 5002,

  // ── Sui ──
  SUI_TESTNET:     6001,

  // ── StarkNet ──
  STARKNET_TESTNET: 7001,

  // ── Stellar/Pi ──
  PI_TESTNET:      8001,
  STELLAR_TESTNET: 8002,

  // ── SVM (existing) ──
  SOL_DEVNET:      900,

  // ── PVM (existing) ──
  DOT_WESTEND:     901,

  // ── TVM (existing) ──
  TON_TESTNET:     1101,

  // ── NEAR (existing) ──
  NEAR_TESTNET:    1201,
};

export const CHAIN_CONFIGS: ChainConfig[] = [
  // ── BITCOIN ──
  {
    id: CHAIN.BTC_TESTNET, name: "Bitcoin Testnet4",
    vm: "UTXO", symbol: "tBTC",
    rpc: "https://mempool.space/testnet4/api",
    explorer: "https://mempool.space/testnet4",
    isTestnet: true, envKey: "BTC_WIF_TAPROOT",
    decimals: 8, btcpSupport: true, trionSupport: true,
  },
  {
    id: CHAIN.LTC_TESTNET, name: "Litecoin Testnet",
    vm: "UTXO", symbol: "tLTC",
    rpc: "https://litecoinspace.org/testnet/api",
    explorer: "https://litecoinspace.org/testnet",
    isTestnet: true, envKey: "LTC_WIF",
    decimals: 8, btcpSupport: true, trionSupport: true,
  },
  {
    id: CHAIN.DOGE_TESTNET, name: "Dogecoin Testnet",
    vm: "UTXO", symbol: "tDOGE",
    rpc: "https://api.blockcypher.com/v1/doge/test3",
    explorer: "https://live.blockcypher.com/doge-testnet",
    isTestnet: true, envKey: "DOGE_WIF",
    decimals: 8, btcpSupport: true, trionSupport: true,
  },
  {
    id: CHAIN.DASH_TESTNET, name: "Dash Testnet",
    vm: "UTXO", symbol: "tDASH",
    rpc: "https://api.blockcypher.com/v1/dash/test",
    explorer: "https://live.blockcypher.com/dash-testnet",
    isTestnet: true, envKey: "DASH_WIF",
    decimals: 8, btcpSupport: true, trionSupport: true,
  },
  // ── TRON ──
  {
    id: CHAIN.TRON_SHASTA, name: "Tron Shasta Testnet",
    vm: "TVM", symbol: "TRX",
    rpc: "https://api.shasta.trongrid.io",
    explorer: "https://shasta.tronscan.org",
    isTestnet: true, envKey: "TRON_PRIVATE_KEY",
    decimals: 6, btcpSupport: true, trionSupport: true,
  },
  // ── COSMOS ECOSYSTEM ──
  {
    id: CHAIN.COSMOS_TESTNET, name: "Cosmos Theta Testnet",
    vm: "COSMOS", symbol: "ATOM",
    rpc: "https://rpc.sentry-01.theta-testnet.polypore.xyz",
    explorer: "https://testnet.mintscan.io/cosmoshub-testnet",
    isTestnet: true, envKey: "COSMOS_MNEMONIC_HEX",
    decimals: 6, btcpSupport: true, trionSupport: true,
  },
  {
    id: CHAIN.DYDX_TESTNET, name: "dYdX Testnet",
    vm: "COSMOS", symbol: "DYDX",
    rpc: "https://dydx-testnet-rpc.publicnode.com",
    explorer: "https://testnet.mintscan.io/dydx-testnet",
    isTestnet: true, envKey: "DYDX_MNEMONIC_HEX",
    decimals: 18, btcpSupport: true, trionSupport: true,
  },
  {
    id: CHAIN.SEI_TESTNET, name: "Sei Testnet",
    vm: "COSMOS", symbol: "SEI",
    rpc: "https://rpc-testnet.sei-apis.com",
    explorer: "https://testnet.seistream.app",
    isTestnet: true, envKey: "SEI_MNEMONIC_HEX",
    decimals: 6, btcpSupport: true, trionSupport: true,
  },
  {
    id: CHAIN.KAVA_TESTNET, name: "Kava Testnet",
    vm: "COSMOS", symbol: "KAVA",
    rpc: "https://rpc.testnet.kava.io",
    explorer: "https://testnet.mintscan.io/kava-testnet",
    isTestnet: true, envKey: "KAVA_PRIVATE_KEY",
    decimals: 6, btcpSupport: true, trionSupport: true,
  },
  {
    id: CHAIN.INITIA_TESTNET, name: "Initia Testnet",
    vm: "COSMOS", symbol: "INIT",
    rpc: "https://rpc.testnet.initia.xyz",
    explorer: "https://scan.testnet.initia.xyz",
    isTestnet: true, envKey: "INITIA_PRIVATE_KEY",
    decimals: 6, btcpSupport: true, trionSupport: true,
  },
  {
    id: CHAIN.INJECTIVE_TESTNET, name: "Injective Testnet",
    vm: "COSMOS", symbol: "INJ",
    rpc: "https://testnet.sentry.tm.injective.network",
    explorer: "https://testnet.explorer.injective.network",
    isTestnet: true, envKey: "INJECTIVE_PRIVATE_KEY",
    decimals: 18, btcpSupport: true, trionSupport: true,
  },
  // ── MOVE ECOSYSTEM ──
  {
    id: CHAIN.APTOS_TESTNET, name: "Aptos Testnet",
    vm: "MOVE", symbol: "APT",
    rpc: "https://fullnode.testnet.aptoslabs.com/v1",
    explorer: "https://explorer.aptoslabs.com/?network=testnet",
    isTestnet: true, envKey: "APTOS_PRIVATE_KEY",
    decimals: 8, btcpSupport: true, trionSupport: true,
  },
  {
    id: CHAIN.MOVEMENT_TESTNET, name: "Movement Testnet",
    vm: "MOVE", symbol: "MOVE",
    rpc: "https://aptos.testnet.bardock.movementlabs.xyz/v1",
    explorer: "https://explorer.movementlabs.xyz/?network=testnet",
    isTestnet: true, envKey: "MOVEMENT_PRIVATE_KEY",
    decimals: 8, btcpSupport: true, trionSupport: true,
  },
  // ── SUI ──
  {
    id: CHAIN.SUI_TESTNET, name: "Sui Testnet",
    vm: "SUI", symbol: "SUI",
    rpc: "https://fullnode.testnet.sui.io:443",
    explorer: "https://suiscan.xyz/testnet",
    isTestnet: true, envKey: "SUI_PRIVATE_KEY",
    decimals: 9, btcpSupport: true, trionSupport: true,
  },
  // ── STARKNET ──
  {
    id: CHAIN.STARKNET_TESTNET, name: "StarkNet Sepolia",
    vm: "STARKNET", symbol: "STRK",
    rpc: "https://starknet-sepolia.public.blastapi.io/rpc/v0_7",
    explorer: "https://sepolia.starkscan.co",
    isTestnet: true, envKey: "STARKNET_PRIVATE_KEY",
    decimals: 18, btcpSupport: true, trionSupport: true,
  },
  // ── PI / STELLAR ──
  {
    id: CHAIN.PI_TESTNET, name: "Pi Network Testnet",
    vm: "MVM", symbol: "PI",
    rpc: "https://api.testnet.minepi.com",
    explorer: "https://api.testnet.minepi.com",
    isTestnet: true, envKey: "PI_SECRET",
    decimals: 7, btcpSupport: false, trionSupport: true,
  },
];

export function getConfig(chainId: number): ChainConfig | undefined {
  return CHAIN_CONFIGS.find(c => c.id === chainId);
}

export function getByVM(vm: VMType): ChainConfig[] {
  return CHAIN_CONFIGS.filter(c => c.vm === vm);
}

export const ALL_VM_FAMILIES = [
  "EVM", "UTXO", "SVM", "PVM", "TVM", "NEAR",
  "COSMOS", "MOVE", "SUI", "STARKNET", "MVM",
] as const;

export const TOTAL_CHAINS = CHAIN_CONFIGS.length;

console.log(`TRION Chain Registry: ${TOTAL_CHAINS} chains · ${ALL_VM_FAMILIES.length} VM families`);
