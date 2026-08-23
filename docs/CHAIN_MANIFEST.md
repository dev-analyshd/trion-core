# TRION Protocol — Chain Manifest & VM Family Index

**126 chains · 18 VM families · live indexers with public RPC failover**

Every chain is indexed by a dedicated Rust indexer crate (or the multi-chain
`trion-evm` crate for EVM) using **public keyless RPC endpoints** with fallback.
All indexers produce the canonical 93-byte dual-strand Behavioral Hash and
128-dimensional entropy-feature vectors per the whitepaper L0.1/L1.1.

---

## VM Family → Indexer Mapping

| VM Family | Chains | Indexer Crate | Primary RPC (public) | Fallbacks |
|---|---|---|---|---|
| **EVM** | 58 chains | `trion-evm` (55) + `trion-botchain` | per-chain (publicnode.com etc.) | 2–5 per chain |
| **SVM** | Solana | `trion-svm` | api.mainnet-beta.solana.com | — |
| **COSMOS** | 20 chains | `trion-cosmos` (6 live) | polkachu/kjnodes/publicnode LCD | rotation |
| **MOVE** | Aptos, Sui, Movement | `trion-aptos`, `trion-sui`, `trion-movement` | fullnode.mainnet.aptoslabs.com, fullnode.mainnet.sui.io | 3 each |
| **NEAR** | NEAR mainnet | `trion-near` | rpc.mainnet.near.org | fastnear, lava |
| **TON** | TON mainnet/testnet | `trion-ton` | toncenter.com/api/v2 | — |
| **STARKNET** | Starknet (Cairo) | `trion-starknet` | Alchemy demo/Cartridge/Juno | 4 total |
| **TRON** | TRON mainnet | `trion-tron` | api.trongrid.io | — |
| **UTXO** | BTC, LTC, DOGE, DASH | `trion-utxo` | BlockCypher | — |
| **STELLAR (MVM)** | Stellar / Pi | `trion-pi` | horizon.stellar.org | lobstr |
| **PVM** | Polkadot, Kusama | `trion-pvm` | Sidecar REST | JSON-RPC |
| **XRPL** | XRP Ledger | `trion-xrpl` | s1.ripple.com:51234 | s2, xrplcluster |
| **WAVES** | Waves | `trion-waves` | nodes.wavesnodes.com | wavesnode.com |
| **VECHAIN** | VeChainThor | `trion-vechain` | mainnet.vechain.org | 2 more |
| **MULTIVERSX** | MultiversX | `trion-multiversx` | api.multiversx.com | gateway, .eu |
| **HEDERA** | Hedera | `trion-hedera` | mainnet.hashio.io/api | subquery, thirdweb |
| **ALGORAND** | Algorand | `trion-algorand` | mainnet-api.algonode.cloud | purestake, algoexplorer |
| **CARDANO** | Cardano | `trion-cardano` | api.koios.rest/api/v1 | guild.koios |

**22 indexer crates total** — `cargo check --workspace` passes with 0 errors, 0 warnings.

---

## EVM Chains (58, via `trion-evm`)

Ethereum (1), Arbitrum (42161), Base (8453), Optimism (10), Polygon (137),
BNB (56), Mantle (5000), Linea (59144), Scroll (534352), HashKey (177),
0G Mainnet (16661), Avalanche (43114), Fantom (250), Sonic (146), zkSync (324),
Berachain (80094), X Layer (196), XDC (50), Story (1514), Blast (81457),
Manta (169), Mode (34443), Taiko (167000), Fraxtal (252), Metis (1088),
Celo (42220), Gnosis (100), Moonbeam (1284), Kaia (8217), Core (1116),
Bitlayer (200901), BOB (60808), Rootstock (30), Cronos (25),
Aurora (1313161554), Harmony (1666600000), IoTeX (4689), Conflux (1030),
Monad (10143), Filecoin (314), Hyperliquid (999), Abstract (2741),
Zora (7777777), WEMIX (1111), OKT (66), Oasis Sapphire (23294), Telos (40),
Kroma (255), Cyber (7560), Sei EVM (1329), Canto (7700), Neon (245022934),
IOTA EVM (8822), BOT Chain (677), 0G Newton (16602), + testnets.

---

## Bridge Pair Elimination

```
BRIDGE_PAIRS_ELIMINATED(N) = N × (N−1) / 2

  5 chains →    10 pairs
 20 chains →   190 pairs
 50 chains → 1,225 pairs
100 chains → 4,950 pairs
126 chains → 7,875 pairs  ← current registry
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
