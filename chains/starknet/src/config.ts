import { constants } from 'starknet';

export const STARKNET_CONFIG = {
  chainId: constants.StarknetChainId.SN_SEPOLIA,
  chainIdHex: '0x534e5f5345504f4c4941',
  networkName: 'Starknet Sepolia Testnet',

  // Order matters: getWorkingProvider() probes each in turn with both a chainId
  // check and a real getBlockWithTxs call, picking the first that works.
  // Verified 2026-04-30 from this Replit egress:
  //   ✓ Alchemy demo (v0_8) — clean, fast
  //   ✓ Cartridge — clean, fast
  //   ✗ Nethermind free-rpc — fetch failed (network unreachable from here)
  //   ✗ Blast public — discontinued (returns -32000 redirecting to Alchemy)
  //   ✗ drpc.org — chainId works but getBlockWithTxs flips between -32601 and 200 (load-balanced)
  rpcEndpoints: [
    process.env.STARKNET_RPC_URL ?? 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_8/demo',
    'https://api.cartridge.gg/x/starknet/sepolia',
    'https://free-rpc.nethermind.io/sepolia-juno/rpc/v0_8',
  ],

  explorer: {
    voyager: 'https://sepolia.voyager.online',
    starkscan: 'https://sepolia.starkscan.co',
  },

  trion: {
    apiBaseUrl: process.env.TRION_API_URL ?? 'http://127.0.0.1:3001',
    faissBaseUrl: process.env.FAISS_SERVICE_URL ?? 'http://127.0.0.1:8000',
  },

  contracts: {
    TRIONOracle:    process.env.TRION_ORACLE_ADDRESS    ?? '',
    BEOAttestation: process.env.BEO_ATTESTATION_ADDRESS ?? '',
    BTCFiGuard:     process.env.BTCFI_GUARD_ADDRESS     ?? '0x3171dc5a60af7048ef2f8b303fb715f1400a7cace576eeff71273b837243975',
  },
} as const;

export const TRION_TIER = {
  BOOTSTRAP: 0,
  GENESIS: 1,
  MATURITY: 2,
} as const;

export const TRAJECTORY_ALERT = {
  CLEAR: 0,
  WARN: 1,
  MANIPULATION: 2,
} as const;
