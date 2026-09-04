# TRION Protocol — Chain Manifest & VM Family Index

**129 chains · 18 VM families · source: `config/chain_registry.json` (canonical)**

Counts in this manifest are recomputed from `config/chain_registry.json` —
the repo's single source of truth for chain/VM coverage (129 chains across
18 VM families: 41 integrated with a live indexer + oracle, 23 testnets,
65 registered and awaiting indexer). Every integrated chain is indexed by a
dedicated Rust indexer crate (or the multi-chain `trion-evm` crate for EVM)
using **public keyless RPC endpoints** with fallback.
All indexers produce the canonical 93-byte dual-strand Behavioral Hash and
128-dimensional entropy-feature vectors per the whitepaper L0.1/L1.1.

---

## VM Family → Indexer Mapping

| VM Family | Chains | Indexer Crate | Primary RPC (public) | Fallbacks |
|---|---|---|---|---|
| **EVM** | 71 chains | `trion-evm` (55 inline) + `trion-botchain` | per-chain (publicnode.com etc.) | 2–5 per chain |
| **SVM** | 3 chains (Solana mainnet/devnet/testnet) | `trion-svm` | api.mainnet-beta.solana.com | — |
| **COSMOS** | 20 chains | `trion-cosmos` (5 integrated) | polkachu/kjnodes/publicnode LCD | rotation |
| **MOVE** | 6 chains (Aptos, Sui, Movement × mainnet/testnet) | `trion-aptos`, `trion-sui`, `trion-movement` | fullnode.mainnet.aptoslabs.com, fullnode.mainnet.sui.io | 3 each |
| **NEAR** | 2 chains (mainnet/testnet) | `trion-near` | rpc.mainnet.near.org | fastnear, lava |
| **TON** | 2 chains (mainnet/testnet) | `trion-ton` | toncenter.com/api/v2 | — |
| **STARKNET** | 2 chains (mainnet/sepolia) | `trion-starknet` | Alchemy demo/Cartridge/Juno | 4 total |
| **TRON** | 2 chains (mainnet/shasta) | `trion-tron` | api.trongrid.io | — |
| **UTXO** | 6 chains (BTC, BTC Testnet4, BCH, DOGE, LTC, DASH) | `trion-utxo` | BlockCypher | — |
| **STELLAR** | 2 chains (mainnet/testnet) | `trion-pi` | horizon.stellar.org | lobstr |
| **PVM** | 3 chains (Polkadot, Westend, Kusama) | `trion-pvm` | Sidecar REST | JSON-RPC |
| **XRPL** | 1 chain | `trion-xrpl` | s1.ripple.com:51234 | s2, xrplcluster |
| **WAVES** | 1 chain | `trion-waves` | nodes.wavesnodes.com | wavesnode.com |
| **VECHAIN** | 1 chain | `trion-vechain` | mainnet.vechain.org | 2 more |
| **MULTIVERSX** | 1 chain | `trion-multiversx` | api.multiversx.com | gateway, .eu |
| **HEDERA** | 2 chains (mainnet/testnet) | `trion-hedera` | mainnet.hashio.io/api | subquery, thirdweb |
| **ALGORAND** | 2 chains (mainnet/testnet) | `trion-algorand` | mainnet-api.algonode.cloud | purestake, algoexplorer |
| **CARDANO** | 2 chains (mainnet/preprod) | `trion-cardano` | api.koios.rest/api/v1 | guild.koios |

**22 indexer crates total** — `cargo check --workspace` passes with 0 errors, 0 warnings.

---

## EVM Chains (71, via `trion-evm`)

Sorted by TRION canonical chain id (source: `config/chain_registry.json`):

Ethereum (1), Optimism (10), Flare (14), Cronos (25), Rootstock (30),
Telos EVM (40), XDC Network (50), BNB Smart Chain (56), Ethereum Classic (61),
OKB Chain (OKTC) (66), BNB Testnet (97), Gnosis (100), Polygon PoS (137),
Sonic (146), Manta Pacific (169), HashKey Mainnet (177), X Layer (196),
Fantom (250), Fraxtal (252), Kroma (255), Boba Network (288), Optopia (300),
Filecoin EVM (314), zkSync Era (324), Astar EVM (592), BotChain (677),
Conflux (1030), Metis (1088), Polygon zkEVM (1101), WEMIX (1111), Core (1116),
Moonbeam (1284), Moonriver (1285), Sei EVM (1329), Story Protocol (1514),
Kava EVM (2222), Abstract (2741), IoTeX (4689), Mantle (5000), Cyber (7560),
Canto (7700), Kaia (Klaytn) (8217), Base (8453), Iota EVM (8822), Monad (10143),
Chiado (Gnosis) (10200), 0G Mainnet (16661), Ethereum Holesky (17000),
Oasis Sapphire (23294), Mode (34443), Arbitrum One (42161), Celo (42220),
Avalanche Fuji (43113), Avalanche C-Chain (43114), Linea (59144), BOB (60808),
Polygon Amoy (80002), Berachain (80094), Blast (81457), Base Sepolia (84532),
Taiko (167000), Bitlayer (200901), Botanix (201022), Arbitrum Sepolia (421614),
Scroll (534352), Zora (7777777), Ethereum Sepolia (11155111),
Optimism Sepolia (11155420), Neon EVM (245022934), Aurora (1313161554),
Harmony (1666600000).

55 of the 71 are inlined in `trion-evm` (the 16 remaining are
registry-listed gap-fill/testnet entries indexed on demand); `trion-botchain`
serves the BotChain entry.

---

## Bridge Pair Elimination

```
BRIDGE_PAIRS_ELIMINATED(N) = N × (N−1) / 2

  5 chains →    10 pairs
 20 chains →   190 pairs
 50 chains → 1,225 pairs
100 chains → 4,950 pairs
129 chains → 8,256 pairs  ← current registry (config/chain_registry.json)
```

---

## Indexer Output Contract

Every indexer, regardless of VM family, emits:

1. **Block-level vector** → `POST /index/add_batch`
   - 9 Shannon-entropy features (VM-specific extraction)
   - 128-dim vector via `build_vector()` (features + complement + cross-correlations + SHA3 noise)
   - Φ(t) = mean of 9 features

2. **Per-transaction canonical BHs** → `POST /index/add_tx_bh_batch`
   - 93-byte payload per tx, dual-strand sense/antisense
   - Event type classified to the canonical 20-type table
   - Magnitude normalized log10 against rolling max

3. **State persistence** → `/tmp/trion_<label>.json` (resume from last block)

### Canonical Event-Type Table (L0.1 §2)

```
0 TRANSFER    5 GOVERNANCE   10 BRIDGE      15 ORACLE_UPDATE
1 SWAP        6 PROPOSAL     11 DEPLOY      16 MEV_CAPTURE
2 LIQUIDITY   7 BORROW       12 UPGRADE     17 FLASH_LOAN
3 STAKE       8 REPAY        13 MINT        18 AIRDROP
4 UNSTAKE     9 LIQUIDATE    14 BURN        19 CLAIM
```

All 22 crates verified against this table (event-type drift fixed across
SVM, Cosmos, Aptos, Movement, TRON, PVM, NEAR, TON indexers).
