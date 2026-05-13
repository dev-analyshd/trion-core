import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-ethers";
import "@nomicfoundation/hardhat-verify";

const RELAYER_PRIVATE_KEY = process.env["RELAYER_PRIVATE_KEY"];
if (!RELAYER_PRIVATE_KEY) {
  throw new Error(
    "RELAYER_PRIVATE_KEY environment variable is required but not set. " +
    "Add it via Replit Secrets. Never commit private keys to source."
  );
}

const ARB_SEPOLIA_RPC =
  process.env["ARBITRUM_SEPOLIA_RPC"] ??
  process.env["ARBITRUM_SEPOLIA_RPC_URL"] ??
  "https://arbitrum-sepolia-rpc.publicnode.com";

const ETH_SEPOLIA_RPC =
  process.env["ETH_SEPOLIA_RPC"] ??
  "https://ethereum-sepolia.publicnode.com";

const HSK_MAINNET_RPC =
  process.env["HSK_MAINNET_RPC"] ?? "https://mainnet.hsk.xyz";

const HSK_TESTNET_RPC =
  process.env["HSK_TESTNET_RPC"] ?? "https://testnet.hsk.xyz";

const ETHERSCAN_API_KEY = process.env["ETHERSCAN_API_KEY"] ?? "";

const ZERO_G_TESTNET_RPC =
  process.env["ZERO_G_TESTNET_RPC"] ?? "https://evmrpc-testnet.0g.ai";

const ZERO_G_MAINNET_RPC =
  process.env["ZERO_G_MAINNET_RPC"] ?? "https://evmrpc.0g.ai";

const BNB_TESTNET_RPC =
  process.env["BNB_RPC_URL"] ?? "https://bsc-testnet-rpc.publicnode.com";

const BASE_SEPOLIA_RPC =
  process.env["BASE_RPC_URL"] ?? "https://base-sepolia-rpc.publicnode.com";

const OP_SEPOLIA_RPC =
  process.env["OP_SEPOLIA_RPC"] ?? "https://sepolia.optimism.io";

const LINEA_RPC =
  process.env["LINEA_RPC"] ?? "https://rpc.linea.build";

const SCROLL_RPC =
  process.env["SCROLL_RPC"] ?? "https://rpc.scroll.io";

const MANTLE_RPC =
  process.env["MANTLE_RPC"] ?? "https://rpc.mantle.xyz";

const POLYGON_MAINNET_RPC =
  process.env["POLYGON_RPC"] ?? "https://polygon-bor-rpc.publicnode.com";

const POLYGON_AMOY_RPC =
  process.env["POLYGON_AMOY_RPC"] ?? "https://rpc-amoy.polygon.technology";

const config: HardhatUserConfig = {
  solidity: {
    version: "0.8.28",
    settings: {
      evmVersion: "cancun",
      optimizer: { enabled: true, runs: 200 },
      viaIR: true,
    },
  },
  paths: {
    artifacts: "./hardhat-artifacts",
    cache: "./hardhat-cache",
  },
  networks: {
    arbitrumSepolia: {
      url: ARB_SEPOLIA_RPC,
      accounts: [RELAYER_PRIVATE_KEY],
      gasPrice: 100000000,
    },
    ethSepolia: {
      url: ETH_SEPOLIA_RPC,
      accounts: [RELAYER_PRIVATE_KEY],
      chainId: 11155111,
    },
    hashkeyChain: {
      url: HSK_MAINNET_RPC,
      accounts: [RELAYER_PRIVATE_KEY],
      chainId: 177,
      gasPrice: "auto",
    },
    hashkeyTestnet: {
      url: HSK_TESTNET_RPC,
      accounts: [RELAYER_PRIVATE_KEY],
      chainId: 133,
      gasPrice: "auto",
    },
    zeroGTestnet: {
      url: ZERO_G_TESTNET_RPC,
      accounts: [RELAYER_PRIVATE_KEY],
      chainId: 16602,
      gasPrice: "auto",
    },
    zeroGMainnet: {
      url: ZERO_G_MAINNET_RPC,
      accounts: [RELAYER_PRIVATE_KEY],
      chainId: 16661,
      gasPrice: "auto",
    },
    bnbTestnet: {
      url: BNB_TESTNET_RPC,
      accounts: [RELAYER_PRIVATE_KEY],
      chainId: 97,
      gasPrice: 5_000_000_000, // 5 gwei — BNB testnet default
    },
    baseSepolia: {
      url: BASE_SEPOLIA_RPC,
      accounts: [RELAYER_PRIVATE_KEY],
      chainId: 84532,
      gasPrice: "auto",
    },
    optimismSepolia: {
      url: OP_SEPOLIA_RPC,
      accounts: [RELAYER_PRIVATE_KEY],
      chainId: 11155420,
      gasPrice: "auto",
    },
    lineaMainnet: {
      url: LINEA_RPC,
      accounts: [RELAYER_PRIVATE_KEY],
      chainId: 59144,
      gasPrice: "auto",
    },
    scrollMainnet: {
      url: SCROLL_RPC,
      accounts: [RELAYER_PRIVATE_KEY],
      chainId: 534352,
      gasPrice: "auto",
    },
    mantleMainnet: {
      url: MANTLE_RPC,
      accounts: [RELAYER_PRIVATE_KEY],
      chainId: 5000,
      gasPrice: "auto",
    },
    polygonMainnet: {
      url: POLYGON_MAINNET_RPC,
      accounts: [RELAYER_PRIVATE_KEY],
      chainId: 137,
      gasPrice: "auto",
    },
    polygonAmoy: {
      url: POLYGON_AMOY_RPC,
      accounts: [RELAYER_PRIVATE_KEY],
      chainId: 80002,
      gasPrice: "auto",
    },
  },
  etherscan: {
    apiKey: {
      arbitrumSepolia: ETHERSCAN_API_KEY,
      ethSepolia: ETHERSCAN_API_KEY,
      hashkeyChain: "no-api-key-needed",
      hashkeyTestnet: "no-api-key-needed",
    },
    customChains: [
      {
        network: "optimismSepolia",
        chainId: 11155420,
        urls: {
          apiURL: "https://api.etherscan.io/v2/api?chainid=11155420",
          browserURL: "https://sepolia-optimism.etherscan.io",
        },
      },
      {
        network: "lineaMainnet",
        chainId: 59144,
        urls: {
          apiURL: "https://api.lineascan.build/api",
          browserURL: "https://lineascan.build",
        },
      },
      {
        network: "scrollMainnet",
        chainId: 534352,
        urls: {
          apiURL: "https://api.scrollscan.com/api",
          browserURL: "https://scrollscan.com",
        },
      },
      {
        network: "mantleMainnet",
        chainId: 5000,
        urls: {
          apiURL: "https://api.mantlescan.xyz/api",
          browserURL: "https://mantlescan.xyz",
        },
      },
      {
        network: "polygonMainnet",
        chainId: 137,
        urls: {
          apiURL: "https://api.polygonscan.com/api",
          browserURL: "https://polygonscan.com",
        },
      },
      {
        network: "polygonAmoy",
        chainId: 80002,
        urls: {
          apiURL: "https://api-amoy.polygonscan.com/api",
          browserURL: "https://amoy.polygonscan.com",
        },
      },
      {
        network: "arbitrumSepolia",
        chainId: 421614,
        urls: {
          apiURL: "https://api.etherscan.io/v2/api?chainid=421614",
          browserURL: "https://sepolia.arbiscan.io",
        },
      },
      {
        network: "ethSepolia",
        chainId: 11155111,
        urls: {
          apiURL: "https://api.etherscan.io/v2/api?chainid=11155111",
          browserURL: "https://sepolia.etherscan.io",
        },
      },
      {
        network: "hashkeyChain",
        chainId: 177,
        urls: {
          apiURL: "https://explorer.hsk.xyz/api",
          browserURL: "https://explorer.hsk.xyz",
        },
      },
      {
        network: "hashkeyTestnet",
        chainId: 133,
        urls: {
          apiURL: "https://testnet.explorer.hsk.xyz/api",
          browserURL: "https://testnet.explorer.hsk.xyz",
        },
      },
    ],
  },
};

export default config;
