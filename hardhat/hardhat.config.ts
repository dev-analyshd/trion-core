import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";

// ── Key management: FAIL CLOSED on mainnets ─────────────────────────────────
// The well-known Hardhat #0 dev key is ONLY permitted for the local in-process
// network (`npx hardhat test`, `npx hardhat node`). Attaching it as the
// `accounts` fallback for LIVE networks was a real mainnet blocker: anyone can
// broadcast from the publicly-known key, so a mainnet deployment made without
// RELAYER_PRIVATE_KEY set would be instantly controllable by third parties.
//
// Policy enforced below:
//   • Local/test/compile → dev-key fallback allowed
//   • Testnets           → allowed but WARNED
//   • Mainnets           → hard FAIL unless the key is explicitly provided
const HARDHAT_DEFAULT_PRIVKEY =
  "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"; // Hardhat #0 — never use on mainnet

// Chain IDs where a publicly-known key is an unconditional security failure.
const MAINNET_CHAIN_IDS = new Set<number>([
  1,      // Ethereum
  10,     // Optimism
  56,     // BNB Smart Chain
  137,    // Polygon
  8453,   // Base
  42161,  // Arbitrum One
  43114,  // Avalanche
  177,    // HashKey Chain mainnet
  5000,   // Mantle mainnet
  59144,  // Linea mainnet
  534352, // Scroll mainnet
  16661,  // 0G Aristotle mainnet (live RPC eth_chainId = 0x4115 = 16661)
]);

// The network the user is actually TARGETING via --network <name>, if any.
// Fail-closed semantics: the fatal error fires only when a MAINNET is the
// active target (deploy/run/verify) — never while merely loading the config
// for compile/test/console, which never sign mainnet transactions.
const MAINNET_NETWORK_NAMES = new Set<string>([
  "hashkeyChain", "zeroGMainnet", "lineaMainnet",
  "scrollMainnet", "mantleMainnet", "polygonMainnet",
]);
function _targetedNetwork(): string | null {
  const i = process.argv.indexOf("--network");
  if (i !== -1 && i + 1 < process.argv.length) return process.argv[i + 1];
  const m = process.argv.find((a) => a.startsWith("--network="));
  return m ? m.split("=")[1] : null;
}
const _target = _targetedNetwork();

function accountsFor(networkName: string, chainId: number, envVar = "RELAYER_PRIVATE_KEY"): string[] {
  const key = process.env[envVar];
  if (key && /^0x[0-9a-fA-F]{64}$/.test(key)) return [key];

  const isMainnetTarget = _target === networkName && MAINNET_CHAIN_IDS.has(chainId);
  if (isMainnetTarget) {
    throw new Error(
      `[hardhat] FATAL: network '${networkName}' (chainId ${chainId}) is a MAINNET. ` +
      `Set ${envVar} before any live-network task. Refusing to fall back to the ` +
      `publicly-known Hardhat dev key — that would hand deployment control to anyone.`
    );
  }
  // Config load / local tasks / other networks: safe placeholder that no
  // mainnet can ever reach (mainnet targets throw above before using it).
  if (_target === networkName && !MAINNET_CHAIN_IDS.has(chainId)) {
    console.warn(
      `[hardhat] ${envVar} is not set for testnet '${networkName}' — using Hardhat ` +
      `dev account. NEVER deploy anything of value this way.`
    );
  }
  return [HARDHAT_DEFAULT_PRIVKEY];
}

// Kept for backwards compatibility with scripts importing it for local runs.
const RELAYER_PRIVATE_KEY = process.env["RELAYER_PRIVATE_KEY"] || HARDHAT_DEFAULT_PRIVKEY;

// DEPLOY_0G_PRIVATE is the dedicated mainnet deployer key for 0G Aristotle.
// Falls back to RELAYER_PRIVATE_KEY for testnet networks.
const DEPLOY_0G_PRIVATE = process.env["DEPLOY_0G_PRIVATE"] || RELAYER_PRIVATE_KEY;

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
    // Self-contained harness. hardhat/contracts/ holds byte-identical twins of
    // the canonical contracts under contracts/solidity/ (BTCPEscrow,
    // TRIONExecutionGate, TRIONOracleV3, TrionEpochRegistry, ReentrantAttacker
    // + their libraries/ and interfaces/ imports) so this suite compiles and
    // runs without pointing Hardhat at the full contracts/solidity tree (25+
    // contracts that have never been validated under this toolchain).
    // Twin policy: byte-identity, enforced by
    // tests/contracts/test_solidity_source_sync.py — when a canonical contract
    // changes, copy it over here (do NOT hand-edit the twins).
    sources:   "./contracts",
    tests:     "./test",
    artifacts: "./hardhat-artifacts",
    cache:     "./hardhat-cache",
  },
  typechain: {
    outDir:  "./hardhat-artifacts/typechain-types",
    target:  "ethers-v6",
  },
  networks: {
    arbitrumSepolia: {
      url: ARB_SEPOLIA_RPC,
      accounts: accountsFor("arbitrumSepolia", 421614),
      gasPrice: 100000000,
    },
    ethSepolia: {
      url: ETH_SEPOLIA_RPC,
      accounts: accountsFor("ethSepolia", 11155111),
      chainId: 11155111,
    },
    hashkeyChain: {
      url: HSK_MAINNET_RPC,
      accounts: accountsFor("hashkeyChain", 177), // MAINNET — key required
      chainId: 177,
      gasPrice: "auto",
    },
    hashkeyTestnet: {
      url: HSK_TESTNET_RPC,
      accounts: accountsFor("hashkeyTestnet", 133),
      chainId: 133,
      gasPrice: "auto",
    },
    zeroGTestnet: {
      url: ZERO_G_TESTNET_RPC,
      accounts: accountsFor("zeroGTestnet", 16602),
      chainId: 16602,
      gasPrice: "auto",
    },
    zeroGMainnet: {
      url: ZERO_G_MAINNET_RPC,
      accounts: accountsFor("zeroGMainnet", 16661, "DEPLOY_0G_PRIVATE"),
      chainId: 16661, // verified live: eth_chainId → 0x4115
      gasPrice: "auto",
    },
    bnbTestnet: {
      url: BNB_TESTNET_RPC,
      accounts: accountsFor("bnbTestnet", 97),
      chainId: 97,
      gasPrice: 5_000_000_000, // 5 gwei — BNB testnet default
    },
    baseSepolia: {
      url: BASE_SEPOLIA_RPC,
      accounts: accountsFor("baseSepolia", 84532),
      chainId: 84532,
      gasPrice: "auto",
    },
    optimismSepolia: {
      url: OP_SEPOLIA_RPC,
      accounts: accountsFor("optimismSepolia", 11155420),
      chainId: 11155420,
      gasPrice: "auto",
    },
    lineaMainnet: {
      url: LINEA_RPC,
      accounts: accountsFor("lineaMainnet", 59144), // MAINNET — key required
      chainId: 59144,
      gasPrice: "auto",
    },
    scrollMainnet: {
      url: SCROLL_RPC,
      accounts: accountsFor("scrollMainnet", 534352), // MAINNET — key required
      chainId: 534352,
      gasPrice: "auto",
    },
    mantleMainnet: {
      url: MANTLE_RPC,
      accounts: accountsFor("mantleMainnet", 5000), // MAINNET — key required
      chainId: 5000,
      gasPrice: "auto",
    },
    polygonMainnet: {
      url: POLYGON_MAINNET_RPC,
      accounts: accountsFor("polygonMainnet", 137), // MAINNET — key required
      chainId: 137,
      gasPrice: "auto",
    },
    polygonAmoy: {
      url: POLYGON_AMOY_RPC,
      accounts: accountsFor("polygonAmoy", 80002),
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
