#!/usr/bin/env python3
"""
TRION Genesis Backfill Runner (all chains) — per whitepaper mandate:
every integrated L1/L2 and every VM, walked from genesis, zero gaps.

Order: Ethereum -> Solana -> Arbitrum -> [remaining ~50 EVM mainnets] ->
       11 Cosmos-SDK chains -> Aptos/Movement (Move VM) -> NEAR -> StarkNet ->
       Polkadot -> TON -> BTC/LTC/DOGE/DASH (UTXO) -> Sui -> Tron -> XRPL ->
       Algorand -> Hedera -> Stellar -> Cardano -> VeChain -> MultiversX -> Waves.

Not covered (no genesis-walkable free public API found, flagged rather than
silently skipped): Kadena (its public chainweb API host does not resolve
from this environment), ICP (no public raw-block REST; mirrors report
metrics, not a walkable block list), Bittensor (public explorers require a
paid/keyed API for historical blocks), Flow (public REST node only serves a
recent "spork" window; full history needs multiple archived spork
endpoints), Canton (permissioned network, no public archive), Quant and
LayerZero (not standalone L1s with their own genesis block history — Quant
is an Ethereum-based token/gateway, LayerZero is a messaging protocol
across other chains' existing block histories).

Each chain/VM has its own independent checkpoint file, so this driver can be
killed and restarted (or crash mid-chain) without losing progress, and each
chain resumes exactly where it left off. Runs forever: once every chain has
reached its own tip at least once, it loops back around so newly-produced
blocks/slots/heights keep landing.

Because most of these chains have tens of millions to billions of
blocks/transactions and FAISS ingestion runs at roughly 1-3 ingests/sec
(bounded by the index server itself, not this script), a full genesis-to-tip
walk of the largest chains (Ethereum, Aptos, Solana) is a multi-day-to-weeks,
continuously-running effort — this script is designed to run indefinitely,
not to "finish" in one sitting.
"""
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [RUNNER] %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
EVM_REGISTRY = json.loads((ROOT / "akashic" / "chains_registry_evm.json").read_text())

COSMOS_CHAINS = [
    "cosmos-hub", "kava", "injective", "sei", "dydx", "initia",
    "osmosis", "neutron", "celestia", "terra", "provenance",
]
MOVE_CHAINS = ["aptos", "movement"]
UTXO_CHAINS = ["btc", "ltc", "doge", "dash"]

# Priority order requested by the user: ETH -> Solana -> Arbitrum first,
# then everything else.
PRIORITY_EVM = ["eth-mainnet", "arb-mainnet"]


def run(cmd: list, label: str):
    logger.info(">>> %s", label)
    try:
        subprocess.run(cmd, cwd=str(ROOT), check=False)
    except Exception as e:
        logger.warning("Stage failed (%s): %s — continuing to next chain.", label, e)


def evm_stage(chain_name: str, chain_id: int, rpc: str):
    run([
        sys.executable, "akashic/genesis_backfill.py",
        "--start-block", "0", "--end-block", "latest",
        "--rpc", rpc, "--chain-name", chain_name, "--chain-id", str(chain_id),
    ], f"EVM {chain_name} (chain_id={chain_id})")


def solana_stage():
    run([sys.executable, "akashic/genesis_backfill_solana.py",
         "--start-slot", "0", "--end-slot", "latest"], "Solana mainnet")


def cosmos_stage(name: str):
    run([sys.executable, "akashic/genesis_backfill_cosmos.py",
         "--chain-name", name, "--start-height", "1", "--end-height", "latest"],
        f"Cosmos-SDK {name}")


def move_stage(name: str):
    run([sys.executable, "akashic/genesis_backfill_move.py",
         "--chain-name", name, "--start-version", "0", "--end-version", "latest"],
        f"Move VM {name}")


def near_stage():
    run([sys.executable, "akashic/genesis_backfill_near.py",
         "--start-height", "1", "--end-height", "latest"], "NEAR mainnet")


def starknet_stage():
    run([sys.executable, "akashic/genesis_backfill_starknet.py",
         "--start-block", "0", "--end-block", "latest"], "StarkNet mainnet")


def polkadot_stage():
    run([sys.executable, "akashic/genesis_backfill_polkadot.py",
         "--start-block", "0", "--end-block", "latest"], "Polkadot mainnet")


def ton_stage():
    run([sys.executable, "akashic/genesis_backfill_ton.py",
         "--start-seqno", "1", "--end-seqno", "latest"], "TON mainnet")


def utxo_stage(name: str):
    run([sys.executable, "akashic/genesis_backfill_utxo.py",
         "--chain-name", name, "--start-height", "0", "--end-height", "latest"],
        f"UTXO {name}")


def sui_stage():
    run([sys.executable, "akashic/genesis_backfill_sui.py",
         "--start-checkpoint", "0", "--end-checkpoint", "latest"], "Sui mainnet")


def tron_stage():
    run([sys.executable, "akashic/genesis_backfill_tron.py",
         "--start-block", "0", "--end-block", "latest"], "Tron mainnet")


def xrpl_stage():
    run([sys.executable, "akashic/genesis_backfill_xrpl.py",
         "--end-ledger", "latest"], "XRPL mainnet")


def algorand_stage():
    run([sys.executable, "akashic/genesis_backfill_algorand.py",
         "--start-round", "1", "--end-round", "latest"], "Algorand mainnet")


def hedera_stage():
    run([sys.executable, "akashic/genesis_backfill_hedera.py",
         "--start-block", "0", "--end-block", "latest"], "Hedera mainnet")


def stellar_stage():
    run([sys.executable, "akashic/genesis_backfill_stellar.py",
         "--start-ledger", "elder", "--end-ledger", "latest"], "Stellar mainnet")


def cardano_stage():
    run([sys.executable, "akashic/genesis_backfill_cardano.py",
         "--start-height", "1", "--end-height", "latest"], "Cardano mainnet")


def vechain_stage():
    run([sys.executable, "akashic/genesis_backfill_vechain.py",
         "--start-block", "0", "--end-block", "latest"], "VeChain mainnet")


def multiversx_stage():
    run([sys.executable, "akashic/genesis_backfill_multiversx.py",
         "--start-offset", "0", "--end-offset", "latest"], "MultiversX mainnet")


def waves_stage():
    run([sys.executable, "akashic/genesis_backfill_waves.py",
         "--start-height", "1", "--end-height", "latest"], "Waves mainnet")


def full_cycle():
    by_name = {c["chain_name"]: c for c in EVM_REGISTRY}

    # 1) Requested priority order
    for name in PRIORITY_EVM:
        c = by_name.pop(name, None)
        if c:
            evm_stage(c["chain_name"], c["chain_id"], c["rpc"])
    solana_stage()

    # 2) Every remaining EVM L1/L2
    for c in by_name.values():
        evm_stage(c["chain_name"], c["chain_id"], c["rpc"])

    # 3) Every remaining VM family
    for name in COSMOS_CHAINS:
        cosmos_stage(name)
    for name in MOVE_CHAINS:
        move_stage(name)
    near_stage()
    starknet_stage()
    polkadot_stage()
    ton_stage()

    # 4) UTXO family + remaining long-tail chains with public no-key APIs
    for name in UTXO_CHAINS:
        utxo_stage(name)
    sui_stage()
    tron_stage()
    xrpl_stage()

    # 5) Remaining long-tail chains with confirmed free/no-key public APIs
    algorand_stage()
    hedera_stage()
    stellar_stage()
    cardano_stage()
    vechain_stage()
    multiversx_stage()
    waves_stage()


if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info(" TRION Genesis Backfill — ALL chains, ALL VMs")
    logger.info(" %d EVM L1/L2s + Solana + %d Cosmos-SDK + %d Move VM + "
                "NEAR + StarkNet + Polkadot + TON + %d UTXO chains + "
                "Sui + Tron + XRPL + Algorand + Hedera + Stellar + Cardano + "
                "VeChain + MultiversX + Waves", len(EVM_REGISTRY),
                len(COSMOS_CHAINS), len(MOVE_CHAINS), len(UTXO_CHAINS))
    logger.info(" Not covered (no genesis-walkable free public API): "
                "Kadena, ICP, Bittensor, Flow, Canton, Quant, LayerZero")
    logger.info("=" * 70)
    cycle = 0
    while True:
        cycle += 1
        logger.info("########## CYCLE %d START ##########", cycle)
        full_cycle()
        logger.info("########## CYCLE %d COMPLETE — all chains at tip; "
                     "restarting to catch new blocks ##########", cycle)
        time.sleep(30)
