import { constants } from 'starknet';

export const STARKNET_CONFIG = {
  chainId: constants.StarknetChainId.SN_MAIN,
  chainIdHex: '0x534e5f4d41494e',
  networkName: 'Starknet Mainnet',

  rpcEndpoints: [
    process.env.STARKNET_RPC_URL ?? 'https://starknet-mainnet.g.alchemy.com/starknet/version/rpc/v0_8/demo',
    'https://api.cartridge.gg/x/starknet/mainnet',
    'https://free-rpc.nethermind.io/mainnet-juno/rpc/v0_8',
  ],

  explorer: {
    voyager: 'https://voyager.online',
    starkscan: 'https://starkscan.co',
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
