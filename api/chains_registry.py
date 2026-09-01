"""
TRION Protocol — Chains Registry
100-chain catalog with BH FAISS stats.
All BH proof counts and block heights are deterministic per chain using
a hash seed so they remain consistent across API calls.
"""
import hashlib
import time

# ── Chain catalog ─────────────────────────────────────────────────────────────
CHAINS = [
    {"id": "0g-mainnet", "name": "0G Mainnet", "vm": "EVM", "chain_id": 16661, "status": "live", "color": "#1B7CE5", "indexer": "trion-evm", "bh_label": "ZG_MAINNET", "note": "TRIONExecutionGate LIVE \u2014 0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b"},
    {"id": "0g-galileo", "name": "0G Galileo", "vm": "EVM", "chain_id": 16602, "status": "testnet", "color": "#1B7CE5", "indexer": "trion-evm", "note": "Testnet \u2014 OracleV3, Liquidity, TravelRule, Escrow"},
    {"id": "eth-mainnet", "name": "Ethereum", "vm": "EVM", "chain_id": 1, "status": "live", "color": "#627EEA", "indexer": "trion-evm", "note": "Per-tx BH live \u2014 Rust EVM indexer"},
    {"id": "arb-mainnet", "name": "Arbitrum One", "vm": "EVM", "chain_id": 42161, "status": "live", "color": "#28A0F0", "indexer": "trion-evm", "note": "462M+ blocks \u2014 per-tx BH live"},
    {"id": "base-mainnet", "name": "Base", "vm": "EVM", "chain_id": 8453, "status": "live", "color": "#0052FF", "indexer": "trion-evm", "note": "45M+ blocks \u2014 per-tx BH live"},
    {"id": "op-mainnet", "name": "Optimism", "vm": "EVM", "chain_id": 10, "status": "live", "color": "#FF0420", "indexer": "trion-evm", "note": "151M+ blocks \u2014 per-tx BH live"},
    {"id": "polygon", "name": "Polygon", "vm": "EVM", "chain_id": 137, "status": "live", "color": "#8247E5", "indexer": "trion-evm"},
    {"id": "bnb-mainnet", "name": "BNB Smart Chain", "vm": "EVM", "chain_id": 56, "status": "live", "color": "#F3BA2F", "indexer": "trion-evm"},
    {"id": "avalanche", "name": "Avalanche C-Chain", "vm": "EVM", "chain_id": 43114, "status": "live", "color": "#E84142", "indexer": "trion-evm"},
    {"id": "mantle", "name": "Mantle", "vm": "EVM", "chain_id": 5000, "status": "live", "color": "#3D3D3D", "indexer": "trion-evm", "note": "95M+ blocks"},
    {"id": "linea", "name": "Linea", "vm": "EVM", "chain_id": 59144, "status": "live", "color": "#61DFFF", "indexer": "trion-evm", "note": "30M+ blocks"},
    {"id": "scroll", "name": "Scroll", "vm": "EVM", "chain_id": 534352, "status": "live", "color": "#F5AC37", "indexer": "trion-evm", "note": "33M+ blocks"},
    {"id": "hashkey", "name": "HashKey Chain", "vm": "EVM", "chain_id": 177, "status": "live", "color": "#00A3E0", "indexer": "trion-evm"},
    {"id": "fantom", "name": "Fantom Opera", "vm": "EVM", "chain_id": 250, "status": "live", "color": "#1969FF", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "sonic", "name": "Sonic", "vm": "EVM", "chain_id": 146, "status": "live", "color": "#FC7928", "indexer": "trion-evm"},
    {"id": "zksync-era", "name": "zkSync Era", "vm": "EVM", "chain_id": 324, "status": "live", "color": "#8C8DFC", "indexer": "trion-evm"},
    {"id": "berachain", "name": "Berachain", "vm": "EVM", "chain_id": 80094, "status": "live", "color": "#8B5C2A", "indexer": "trion-evm"},
    {"id": "xlayer", "name": "X Layer", "vm": "EVM", "chain_id": 196, "status": "live", "color": "#3C3C3C", "indexer": "trion-evm"},
    {"id": "xdc", "name": "XDC Network", "vm": "EVM", "chain_id": 50, "status": "live", "color": "#2550A4", "indexer": "trion-evm"},
    {"id": "story-ip", "name": "Story Protocol", "vm": "EVM", "chain_id": 1514, "status": "live", "color": "#3DDC97", "indexer": "trion-evm"},
    {"id": "blast", "name": "Blast", "vm": "EVM", "chain_id": 81457, "status": "live", "color": "#D4AC0D", "indexer": "trion-evm"},
    {"id": "manta", "name": "Manta Pacific", "vm": "EVM", "chain_id": 169, "status": "live", "color": "#50CECA", "indexer": "trion-evm", "bh_label": "MANTA_PACIFIC"},
    {"id": "mode", "name": "Mode Network", "vm": "EVM", "chain_id": 34443, "status": "live", "color": "#9FB300", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "taiko", "name": "Taiko", "vm": "EVM", "chain_id": 167000, "status": "live", "color": "#E91E8C", "indexer": "trion-evm"},
    {"id": "fraxtal", "name": "Fraxtal", "vm": "EVM", "chain_id": 252, "status": "live", "color": "#555555", "indexer": "trion-evm"},
    {"id": "metis", "name": "Metis Andromeda", "vm": "EVM", "chain_id": 1088, "status": "live", "color": "#00DACC", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "celo", "name": "Celo", "vm": "EVM", "chain_id": 42220, "status": "live", "color": "#35D07F", "indexer": "trion-evm"},
    {"id": "gnosis", "name": "Gnosis Chain", "vm": "EVM", "chain_id": 100, "status": "live", "color": "#04795B", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "moonbeam", "name": "Moonbeam", "vm": "EVM", "chain_id": 1284, "status": "live", "color": "#53CBC9", "indexer": "trion-evm"},
    {"id": "kaia", "name": "Kaia", "vm": "EVM", "chain_id": 8217, "status": "live", "color": "#FA4036", "indexer": "trion-evm"},
    {"id": "core", "name": "CORE Chain", "vm": "EVM", "chain_id": 1116, "status": "live", "color": "#FF9A3C", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "bitlayer", "name": "Bitlayer", "vm": "EVM", "chain_id": 200901, "status": "live", "color": "#F7931A", "indexer": "trion-evm"},
    {"id": "bob", "name": "BOB Network", "vm": "EVM", "chain_id": 60808, "status": "live", "color": "#F05A28", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "rootstock", "name": "Rootstock", "vm": "EVM", "chain_id": 30, "status": "live", "color": "#FF9000", "indexer": "trion-evm"},
    {"id": "cronos", "name": "Cronos", "vm": "EVM", "chain_id": 25, "status": "live", "color": "#1C3A78", "indexer": "trion-evm"},
    {"id": "aurora", "name": "Aurora", "vm": "EVM", "chain_id": 1313161554, "status": "live", "color": "#78D64B", "indexer": "trion-evm"},
    {"id": "harmony", "name": "Harmony ONE", "vm": "EVM", "chain_id": 1666600000, "status": "live", "color": "#00AEE9", "indexer": "trion-evm"},
    {"id": "iotex", "name": "IoTeX", "vm": "EVM", "chain_id": 4689, "status": "live", "color": "#44B8B1", "indexer": "trion-evm"},
    {"id": "conflux", "name": "Conflux eSpace", "vm": "EVM", "chain_id": 1030, "status": "live", "color": "#44B0F5", "indexer": "trion-evm"},
    {"id": "monad", "name": "Monad", "vm": "EVM", "chain_id": 10143, "status": "live", "color": "#7C3AED", "indexer": "trion-evm", "bh_label": "MONAD_MAINNET"},
    {"id": "filecoin", "name": "Filecoin FEVM", "vm": "EVM", "chain_id": 314, "status": "live", "color": "#0090FF", "indexer": "trion-evm"},
    {"id": "hyperliquid", "name": "HyperLiquid EVM", "vm": "EVM", "chain_id": 999, "status": "live", "color": "#00D6BC", "indexer": "trion-evm"},
    {"id": "abstract", "name": "Abstract", "vm": "EVM", "chain_id": 2741, "status": "live", "color": "#22C55E", "indexer": "trion-evm"},
    {"id": "zora", "name": "Zora Network", "vm": "EVM", "chain_id": 7777777, "status": "live", "color": "#A855F7", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "wemix", "name": "WEMIX 3.0", "vm": "EVM", "chain_id": 1111, "status": "live", "color": "#00B2FF", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "okt-chain", "name": "OKX Chain", "vm": "EVM", "chain_id": 66, "status": "live", "color": "#3C3C3C", "indexer": "trion-evm"},
    {"id": "oasis-sapphire", "name": "Oasis Sapphire", "vm": "EVM", "chain_id": 23294, "status": "live", "color": "#0092F6", "indexer": "trion-evm"},
    {"id": "telos", "name": "Telos EVM", "vm": "EVM", "chain_id": 40, "status": "live", "color": "#571AFF", "indexer": "trion-evm"},
    {"id": "kroma", "name": "Kroma", "vm": "EVM", "chain_id": 255, "status": "live", "color": "#E53E3E", "indexer": "trion-evm"},
    {"id": "cyber", "name": "Cyber L3", "vm": "EVM", "chain_id": 7560, "status": "live", "color": "#2FFF8C", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "sei-evm", "name": "Sei EVM", "vm": "EVM", "chain_id": 1329, "status": "live", "color": "#9E2020", "indexer": "trion-evm"},
    {"id": "canto", "name": "Canto", "vm": "EVM", "chain_id": 7700, "status": "live", "color": "#06FC99", "indexer": "trion-evm"},
    {"id": "neon-evm", "name": "Neon EVM", "vm": "EVM", "chain_id": 245022934, "status": "live", "color": "#663399", "indexer": "trion-evm"},
    {"id": "iota-evm", "name": "IOTA EVM", "vm": "EVM", "chain_id": 8822, "status": "live", "color": "#0FC1B7", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "bot-chain", "name": "BOT Chain", "vm": "EVM", "chain_id": 677, "status": "live", "color": "#00FFA3", "indexer": "trion-botchain", "note": "AI-agent EVM L1"},
    {"id": "polygon-zkevm", "name": "Polygon zkEVM", "vm": "EVM", "chain_id": 1101, "status": "live", "color": "#7B3FE4", "indexer": "trion-evm"},
    {"id": "immutable-x", "name": "Immutable X", "vm": "EVM", "chain_id": 13371, "status": "live", "color": "#17B5CB", "indexer": "trion-evm"},
    {"id": "gravity", "name": "Gravity", "vm": "EVM", "chain_id": 1625, "status": "live", "color": "#6B5EFF", "indexer": "trion-evm"},
    {"id": "worldchain", "name": "Worldchain", "vm": "EVM", "chain_id": 480, "status": "live", "color": "#374151", "indexer": "trion-evm"},
    {"id": "unichain", "name": "Unichain", "vm": "EVM", "chain_id": 130, "status": "live", "color": "#FF007A", "indexer": "trion-evm"},
    {"id": "ink", "name": "Ink", "vm": "EVM", "chain_id": 57073, "status": "live", "color": "#6366F1", "indexer": "trion-evm"},
    {"id": "soneium", "name": "Soneium", "vm": "EVM", "chain_id": 1868, "status": "live", "color": "#8B5CF6", "indexer": "trion-evm"},
    {"id": "apechain", "name": "Apechain", "vm": "EVM", "chain_id": 33139, "status": "live", "color": "#0055FB", "indexer": "trion-evm"},
    {"id": "shape", "name": "Shape", "vm": "EVM", "chain_id": 360, "status": "live", "color": "#5B48DC", "indexer": "trion-evm"},
    {"id": "arb-sepolia", "name": "Arbitrum Sepolia", "vm": "EVM", "chain_id": 421614, "status": "testnet", "color": "#28A0F0", "indexer": "trion-evm"},
    {"id": "base-sepolia", "name": "Base Sepolia", "vm": "EVM", "chain_id": 84532, "status": "testnet", "color": "#0052FF", "indexer": "trion-evm"},
    {"id": "op-sepolia", "name": "Optimism Sepolia", "vm": "EVM", "chain_id": 11155420, "status": "testnet", "color": "#FF0420", "indexer": "trion-evm"},
    {"id": "eth-sepolia", "name": "Ethereum Sepolia", "vm": "EVM", "chain_id": 11155111, "status": "testnet", "color": "#627EEA", "indexer": "trion-evm"},
    {"id": "bnb-testnet", "name": "BNB Testnet", "vm": "EVM", "chain_id": 97, "status": "testnet", "color": "#F3BA2F", "indexer": "trion-evm"},
    {"id": "solana", "name": "Solana", "vm": "SVM", "chain_id": 101, "status": "live", "color": "#9945FF", "indexer": "trion-svm"},
    {"id": "solana-dev", "name": "Solana Devnet", "vm": "SVM", "chain_id": 103, "status": "testnet", "color": "#9945FF", "indexer": "trion-svm", "bh_label": "SOLANA_DEVNET"},
    {"id": "btc", "name": "Bitcoin", "vm": "UTXO", "chain_id": 0, "status": "live", "color": "#F7931A", "indexer": "native-vm"},
    {"id": "ltc", "name": "Litecoin", "vm": "UTXO", "chain_id": 0, "status": "live", "color": "#A0A0A0", "indexer": "native-vm"},
    {"id": "doge", "name": "Dogecoin", "vm": "UTXO", "chain_id": 0, "status": "live", "color": "#C2A633", "indexer": "native-vm"},
    {"id": "dash", "name": "Dash", "vm": "UTXO", "chain_id": 0, "status": "live", "color": "#008CE7", "indexer": "native-vm"},
    {"id": "cardano", "name": "Cardano", "vm": "eUTXO", "chain_id": 0, "status": "indexed", "color": "#0D1E2D", "indexer": "trion-cardano"},
    {"id": "cosmos", "name": "Cosmos Hub", "vm": "Cosmos SDK", "chain_id": 0, "status": "live", "color": "#2E3148", "indexer": "trion-cosmos"},
    {"id": "kava", "name": "Kava", "vm": "Cosmos SDK", "chain_id": 0, "status": "live", "color": "#FF433E", "indexer": "trion-cosmos"},
    {"id": "inj", "name": "Injective", "vm": "Cosmos SDK", "chain_id": 0, "status": "live", "color": "#00F2FE", "indexer": "trion-cosmos"},
    {"id": "sei", "name": "SEI Network", "vm": "Cosmos SDK", "chain_id": 10005, "status": "live", "color": "#9E1F1F", "indexer": "trion-cosmos", "note": "gap-filled from shared manifest"},
    {"id": "dydx", "name": "dYdX Chain", "vm": "Cosmos SDK", "chain_id": 10006, "status": "live", "color": "#6966FF", "indexer": "trion-cosmos", "note": "gap-filled from shared manifest"},
    {"id": "initia", "name": "Initia", "vm": "Cosmos SDK", "chain_id": 0, "status": "live", "color": "#FF6B35", "indexer": "trion-cosmos"},
    {"id": "osmosis", "name": "Osmosis", "vm": "Cosmos SDK", "chain_id": 0, "status": "indexed", "color": "#750BBB", "indexer": "trion-cosmos"},
    {"id": "celestia", "name": "Celestia", "vm": "Cosmos SDK", "chain_id": 0, "status": "indexed", "color": "#7B2FBE", "indexer": "trion-cosmos"},
    {"id": "neutron", "name": "Neutron", "vm": "Cosmos SDK", "chain_id": 0, "status": "indexed", "color": "#333333", "indexer": "trion-cosmos"},
    {"id": "terra", "name": "Terra Classic", "vm": "Cosmos SDK", "chain_id": 0, "status": "indexed", "color": "#0E3CA5", "indexer": "trion-cosmos"},
    {"id": "provenance", "name": "Provenance", "vm": "Cosmos SDK", "chain_id": 0, "status": "indexed", "color": "#6B46C1", "indexer": "trion-cosmos"},
    {"id": "aptos", "name": "Aptos", "vm": "Move VM", "chain_id": 0, "status": "live", "color": "#00C2FF", "indexer": "trion-aptos"},
    {"id": "movement", "name": "Movement", "vm": "Move VM", "chain_id": 0, "status": "live", "color": "#FF6B35", "indexer": "trion-movement"},
    {"id": "sui", "name": "SUI", "vm": "Sui VM", "chain_id": 0, "status": "live", "color": "#6FBCF0", "indexer": "trion-sui"},
    {"id": "starknet", "name": "StarkNet", "vm": "Cairo VM", "chain_id": 0, "status": "live", "color": "#FEBB53", "indexer": "trion-starknet"},
    {"id": "ton", "name": "TON", "vm": "TVM", "chain_id": 0, "status": "live", "color": "#0088CC", "indexer": "trion-ton"},
    {"id": "tron", "name": "TRON", "vm": "TVM", "chain_id": 0, "status": "live", "color": "#FF0013", "indexer": "native-vm"},
    {"id": "dot", "name": "Polkadot", "vm": "PVM", "chain_id": 0, "status": "live", "color": "#E6007A", "indexer": "trion-dot"},
    {"id": "near", "name": "NEAR Protocol", "vm": "NEAR VM", "chain_id": 0, "status": "live", "color": "#00C08B", "indexer": "trion-near"},
    {"id": "pi", "name": "Pi Network", "vm": "Stellar", "chain_id": 8001, "status": "live", "color": "#9D4EDD", "indexer": "trion-pi"},
    {"id": "xrpl", "name": "XRP Ledger", "vm": "XRP Ledger", "chain_id": 31000, "status": "indexed", "color": "#00AAE4", "indexer": "trion-xrpl", "note": "gap-filled from shared manifest"},
    {"id": "algo", "name": "Algorand", "vm": "AVM", "chain_id": 0, "status": "indexed", "color": "#000000", "indexer": "trion-algo"},
    {"id": "hedera", "name": "Hedera", "vm": "HBAR VM", "chain_id": 0, "status": "indexed", "color": "#222222", "indexer": "trion-hedera"},
    {"id": "vechain", "name": "VeChain", "vm": "VET VM", "chain_id": 29000, "status": "indexed", "color": "#15BDFF", "indexer": "trion-vet", "note": "gap-filled from shared manifest"},
    {"id": "kadena", "name": "Kadena", "vm": "Chainweb", "chain_id": 0, "status": "indexed", "color": "#E1176A", "indexer": "trion-kadena"},
    {"id": "icp", "name": "Internet Computer", "vm": "Wasm", "chain_id": 0, "status": "indexed", "color": "#29ABE2", "indexer": "trion-icp"},
    {"id": "bittensor", "name": "Bittensor", "vm": "Wasm", "chain_id": 0, "status": "indexed", "color": "#8090C0", "indexer": "trion-bittensor"},
    {"id": "multiversx", "name": "MultiversX", "vm": "Wasm", "chain_id": 0, "status": "indexed", "color": "#23F7DD", "indexer": "trion-mvx"},
    {"id": "zilliqa", "name": "Zilliqa", "vm": "LLVM", "chain_id": 0, "status": "indexed", "color": "#49C1BF", "indexer": "trion-zil"},
    {"id": "flow", "name": "Flow", "vm": "Cadence VM", "chain_id": 0, "status": "indexed", "color": "#00EF8B", "indexer": "trion-flow"},
    {"id": "juno", "name": "Juno", "vm": "Cosmos SDK", "chain_id": 10002, "status": "live", "color": "#888888", "indexer": "trion-cosmos", "note": "gap-filled from shared manifest"},
    {"id": "kujira", "name": "Kujira", "vm": "Cosmos SDK", "chain_id": 10007, "status": "indexed", "color": "#888888", "indexer": "trion-cosmos", "note": "gap-filled from shared manifest"},
    {"id": "stargaze", "name": "Stargaze", "vm": "Cosmos SDK", "chain_id": 10008, "status": "indexed", "color": "#888888", "indexer": "trion-cosmos", "note": "gap-filled from shared manifest"},
    {"id": "terra-phoenix", "name": "Terra Phoenix", "vm": "Cosmos SDK", "chain_id": 10010, "status": "indexed", "color": "#888888", "indexer": "trion-cosmos", "note": "gap-filled from shared manifest"},
    {"id": "persistence", "name": "Persistence", "vm": "Cosmos SDK", "chain_id": 10011, "status": "indexed", "color": "#888888", "indexer": "trion-cosmos", "note": "gap-filled from shared manifest"},
    {"id": "comdex", "name": "Comdex", "vm": "Cosmos SDK", "chain_id": 10012, "status": "indexed", "color": "#888888", "indexer": "trion-cosmos", "note": "gap-filled from shared manifest"},
    {"id": "chihuahua", "name": "Chihuahua", "vm": "Cosmos SDK", "chain_id": 10013, "status": "indexed", "color": "#888888", "indexer": "trion-cosmos", "note": "gap-filled from shared manifest"},
    {"id": "saga", "name": "Saga", "vm": "Cosmos SDK", "chain_id": 10016, "status": "indexed", "color": "#888888", "indexer": "trion-cosmos", "note": "gap-filled from shared manifest"},
    {"id": "noble", "name": "Noble", "vm": "Cosmos SDK", "chain_id": 10017, "status": "indexed", "color": "#888888", "indexer": "trion-cosmos", "note": "gap-filled from shared manifest"},
    {"id": "axelar", "name": "Axelar", "vm": "Cosmos SDK", "chain_id": 10019, "status": "indexed", "color": "#888888", "indexer": "trion-cosmos", "note": "gap-filled from shared manifest"},
    {"id": "flare", "name": "Flare", "vm": "EVM", "chain_id": 14, "status": "indexed", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "ethereum-classic", "name": "Ethereum Classic", "vm": "EVM", "chain_id": 61, "status": "indexed", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "okb-chain-oktc", "name": "OKB Chain (OKTC)", "vm": "EVM", "chain_id": 66, "status": "indexed", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "polygon-pos", "name": "Polygon PoS", "vm": "EVM", "chain_id": 137, "status": "live", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "hashkey-mainnet", "name": "HashKey Mainnet", "vm": "EVM", "chain_id": 177, "status": "live", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "boba-network", "name": "Boba Network", "vm": "EVM", "chain_id": 288, "status": "indexed", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "optopia", "name": "Optopia", "vm": "EVM", "chain_id": 300, "status": "indexed", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "filecoin-evm", "name": "Filecoin EVM", "vm": "EVM", "chain_id": 314, "status": "indexed", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "astar-evm", "name": "Astar EVM", "vm": "EVM", "chain_id": 592, "status": "indexed", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "botchain", "name": "BotChain", "vm": "EVM", "chain_id": 677, "status": "indexed", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "moonriver", "name": "Moonriver", "vm": "EVM", "chain_id": 1285, "status": "live", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "kava-evm", "name": "Kava EVM", "vm": "EVM", "chain_id": 2222, "status": "indexed", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "kaia-klaytn", "name": "Kaia (Klaytn)", "vm": "EVM", "chain_id": 8217, "status": "indexed", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "chiado-gnosis", "name": "Chiado (Gnosis)", "vm": "EVM", "chain_id": 10200, "status": "indexed", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "ethereum-holesky", "name": "Ethereum Holesky", "vm": "EVM", "chain_id": 17000, "status": "testnet", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "avalanche-fuji", "name": "Avalanche Fuji", "vm": "EVM", "chain_id": 43113, "status": "testnet", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "polygon-amoy", "name": "Polygon Amoy", "vm": "EVM", "chain_id": 80002, "status": "testnet", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "botanix", "name": "Botanix", "vm": "EVM", "chain_id": 201022, "status": "indexed", "color": "#888888", "indexer": "trion-evm", "note": "gap-filled from shared manifest"},
    {"id": "hedera-testnet", "name": "Hedera Testnet", "vm": "HBAR VM", "chain_id": 28001, "status": "testnet", "color": "#888888", "indexer": "trion-hedera", "note": "gap-filled from shared manifest"},
    {"id": "aptos-mainnet", "name": "Aptos Mainnet", "vm": "Move VM", "chain_id": 20000, "status": "live", "color": "#888888", "indexer": "trion-aptos", "note": "gap-filled from shared manifest"},
    {"id": "aptos-testnet", "name": "Aptos Testnet", "vm": "Move VM", "chain_id": 20001, "status": "testnet", "color": "#888888", "indexer": "trion-aptos", "note": "gap-filled from shared manifest"},
    {"id": "sui-mainnet", "name": "Sui Mainnet", "vm": "Move VM", "chain_id": 20100, "status": "live", "color": "#888888", "indexer": "trion-aptos", "note": "gap-filled from shared manifest"},
    {"id": "sui-testnet", "name": "Sui Testnet", "vm": "Move VM", "chain_id": 20101, "status": "testnet", "color": "#888888", "indexer": "trion-aptos", "note": "gap-filled from shared manifest"},
    {"id": "movement-mainnet", "name": "Movement Mainnet", "vm": "Move VM", "chain_id": 20200, "status": "indexed", "color": "#888888", "indexer": "trion-aptos", "note": "gap-filled from shared manifest"},
    {"id": "movement-bardock", "name": "Movement Bardock", "vm": "Move VM", "chain_id": 20201, "status": "testnet", "color": "#888888", "indexer": "trion-aptos", "note": "gap-filled from shared manifest"},
    {"id": "near-mainnet", "name": "NEAR Mainnet", "vm": "NEAR VM", "chain_id": 23000, "status": "live", "color": "#888888", "indexer": "trion-near", "note": "gap-filled from shared manifest"},
    {"id": "near-testnet", "name": "NEAR Testnet", "vm": "NEAR VM", "chain_id": 23001, "status": "testnet", "color": "#888888", "indexer": "trion-near", "note": "gap-filled from shared manifest"},
    {"id": "polkadot-westend", "name": "Polkadot Westend", "vm": "Polkadot VM", "chain_id": 25001, "status": "indexed", "color": "#888888", "indexer": "trion-pvm", "note": "gap-filled from shared manifest"},
    {"id": "kusama", "name": "Kusama", "vm": "Polkadot VM", "chain_id": 25002, "status": "indexed", "color": "#888888", "indexer": "trion-pvm", "note": "gap-filled from shared manifest"},
    {"id": "starknet-mainnet", "name": "Starknet Mainnet", "vm": "Cairo VM", "chain_id": 24000, "status": "live", "color": "#888888", "indexer": "trion-starknet", "note": "gap-filled from shared manifest"},
    {"id": "starknet-sepolia", "name": "Starknet Sepolia", "vm": "Cairo VM", "chain_id": 24001, "status": "testnet", "color": "#888888", "indexer": "trion-starknet", "note": "gap-filled from shared manifest"},
    {"id": "stellar-mainnet", "name": "Stellar Mainnet", "vm": "Stellar", "chain_id": 27000, "status": "indexed", "color": "#888888", "indexer": "trion-pi", "note": "gap-filled from shared manifest"},
    {"id": "stellar-testnet", "name": "Stellar Testnet", "vm": "Stellar", "chain_id": 27001, "status": "testnet", "color": "#888888", "indexer": "trion-pi", "note": "gap-filled from shared manifest"},
    {"id": "solana-mainnet", "name": "Solana Mainnet", "vm": "SVM", "chain_id": 900, "status": "live", "color": "#888888", "indexer": "trion-svm", "note": "gap-filled from shared manifest"},
    {"id": "solana-testnet", "name": "Solana Testnet", "vm": "SVM", "chain_id": 902, "status": "testnet", "color": "#888888", "indexer": "trion-svm", "note": "gap-filled from shared manifest"},
    {"id": "ton-mainnet", "name": "TON Mainnet", "vm": "TVM", "chain_id": 22000, "status": "live", "color": "#888888", "indexer": "trion-ton", "note": "gap-filled from shared manifest"},
    {"id": "ton-testnet", "name": "TON Testnet", "vm": "TVM", "chain_id": 22001, "status": "testnet", "color": "#888888", "indexer": "trion-ton", "note": "gap-filled from shared manifest"},
    {"id": "tron-mainnet", "name": "Tron Mainnet", "vm": "TVM", "chain_id": 26000, "status": "live", "color": "#888888", "indexer": "trion-tron", "note": "gap-filled from shared manifest"},
    {"id": "tron-shasta", "name": "Tron Shasta", "vm": "TVM", "chain_id": 26001, "status": "testnet", "color": "#888888", "indexer": "trion-tron", "note": "gap-filled from shared manifest"},
    {"id": "bitcoin-testnet4", "name": "Bitcoin Testnet4", "vm": "UTXO", "chain_id": 21001, "status": "testnet", "color": "#888888", "indexer": "trion-utxo", "note": "gap-filled from shared manifest"},
    {"id": "bitcoin-cash", "name": "Bitcoin Cash", "vm": "UTXO", "chain_id": 21002, "status": "indexed", "color": "#888888", "indexer": "trion-utxo", "note": "gap-filled from shared manifest"},
    {"id": "cardano-preprod", "name": "Cardano Preprod", "vm": "UTXO", "chain_id": 21007, "status": "testnet", "color": "#888888", "indexer": "trion-utxo", "note": "gap-filled from shared manifest"},
    {"id": "algorand-testnet", "name": "Algorand Testnet", "vm": "UTXO", "chain_id": 21009, "status": "testnet", "color": "#888888", "indexer": "trion-utxo", "note": "gap-filled from shared manifest"},
    {"id": "waves", "name": "Waves", "vm": "Waves", "chain_id": 30000, "status": "indexed", "color": "#888888", "indexer": "trion-waves", "note": "gap-filled from shared manifest"},
]


# BH proof baselines per status tier
_PROOF_BASE = {"live": 2_400_000, "testnet": 180_000, "indexed": 45_000}
# Block height baselines per VM family
_BLOCK_BASE = {
    "EVM": 50_000_000, "SVM": 280_000_000, "UTXO": 840_000,
    "eUTXO": 9_800_000, "Cosmos SDK": 18_000_000, "Move VM": 3_200_000,
    "Sui VM": 95_000_000, "Cairo VM": 620_000, "TVM": 42_000_000,
    "PVM": 8_500_000, "NEAR VM": 120_000_000, "Stellar": 47_000_000,
    "XRP Ledger": 88_000_000, "AVM": 36_000_000, "HBAR VM": 62_000_000,
    "VET VM": 19_000_000, "Chainweb": 4_200_000, "Wasm": 7_800_000,
    "LLVM": 5_100_000, "Cadence VM": 88_000_000,
}


def _seed(chain_id: str) -> int:
    """Deterministic 32-bit seed from chain id string."""
    h = hashlib.sha256(chain_id.encode()).digest()
    return int.from_bytes(h[:4], "big")


def get_bh_stats(chain: dict, live_records: int | None = None) -> dict:
    """
    Return BH stats for a chain.

    HONEST DATA MODEL (audit remediation):
      - When `live_records` (real bh_ledger.db count for this chain) is
        available, bh_proofs is the REAL count and stats_source="ledger".
      - Otherwise the deterministic baseline is returned explicitly labeled
        stats_source="estimated" — capacity-planning figures derived from
        the chain's status/VM, NOT live measurements. Never presented as
        indexed data.
    """
    s = _seed(chain["id"])
    status = chain["status"]
    vm = chain["vm"]

    if live_records is not None:
        return {
            "bh_proofs": int(live_records),
            "faiss_vectors": int(live_records),   # every BH has a FAISS vector
            "last_block": 0,
            "last_indexed_ts": None,
            "indexer": chain.get("indexer", "trion-evm"),
            "stats_source": "ledger",
        }

    # Deterministic capacity estimate (NOT live data)
    base_proofs = _PROOF_BASE.get(status, 45_000)
    base_block = _BLOCK_BASE.get(vm, 10_000_000)

    # jitter within ±30% using seed
    jitter = (s % 1000) / 1000.0 * 0.6 - 0.3
    bh_proofs = int(base_proofs * (1 + jitter))
    last_block = int(base_block * (1 + jitter * 0.5))

    # FAISS vectors: 70-90% of proof count
    faiss_frac = 0.70 + (s % 200) / 1000.0
    faiss_vectors = int(bh_proofs * faiss_frac)

    return {
        "bh_proofs": bh_proofs,
        "faiss_vectors": faiss_vectors,
        "last_block": last_block,
        "last_indexed_ts": None,   # never fabricate freshness for estimates
        "indexer": chain.get("indexer", "trion-evm"),
        "stats_source": "estimated",
    }


def enrich(chain: dict, live_records: int | None = None) -> dict:
    """Return chain dict enriched with BH stats (real ledger counts preferred)."""
    return {**chain, **get_bh_stats(chain, live_records)}


def get_live_chain_stats() -> dict:
    """
    Query bh_ledger.db for real per-chain BH record counts.
    Returns {chain_label: count} from live SQLite data.
    Falls back to empty dict if the DB is unavailable.
    Result is cached for 60 s to avoid per-request DB hits.
    """
    import sqlite3 as _sql
    import os as _os
    import time as _t
    import threading as _th
    _f = get_live_chain_stats
    if not hasattr(_f, "_cache"):
        _f._cache = {}
        _f._ts    = 0.0
        _f._lock  = _th.Lock()
    now = _t.time()
    with _f._lock:
        if _f._cache and (now - _f._ts) < 60:
            return dict(_f._cache)
    db_path = _os.path.normpath(
        _os.path.join(_os.path.dirname(__file__), "..", "bh_ledger.db")
    )
    try:
        conn = _sql.connect(db_path, timeout=3.0)
        conn.execute("PRAGMA query_only=1")
        rows = conn.execute(
            "SELECT chain_label, COUNT(*) FROM bh_ledger GROUP BY chain_label"
        ).fetchall()
        conn.close()
        result = {r[0]: r[1] for r in rows}
    except Exception:
        result = {}
    with _f._lock:
        _f._cache = result
        _f._ts    = now
    return result


def get_all_chains():
    return CHAINS


def get_enriched_chains():
    """Return all chains enriched with BH stats — REAL ledger counts preferred.

    Audit remediation: chains with live bh_ledger.db records report the actual
    count with stats_source="ledger"; all others are explicitly labeled
    stats_source="estimated" (deterministic capacity figures, never presented
    as indexed state).
    """
    live_stats = get_live_chain_stats()
    enriched = []
    for c in CHAINS:
        # Resolve the bh_ledger chain_label for this catalog entry
        explicit = c.get("bh_label")
        if explicit:
            label_candidates = [explicit]
        else:
            label_candidates = [
                c["id"].upper().replace("-", "_"),
                c["name"].upper().replace(" ", "_").replace("-", "_"),
                c["id"].upper().replace("-", "_") + "_MAINNET",
                c["id"].upper().replace("-", "_") + "_DEVNET",
            ]
        live_records = None
        for lbl in label_candidates:
            if lbl in live_stats:
                live_records = live_stats[lbl]
                break

        e = enrich(c, live_records)
        if live_records is not None:
            e["bh_records_live"] = live_records
        enriched.append(e)
    return enriched
