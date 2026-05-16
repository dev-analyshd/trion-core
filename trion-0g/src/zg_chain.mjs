/**
 * TRION × 0G Chain Integration
 * Read/write operations on all 5 TRION contracts deployed on 0G Galileo.
 *
 * Deployed contracts (all on 0G Galileo, chain_id 16602):
 *   TRIONExecutionGate:   0xDB5910Dc6CfD219D00F64be1F23DA0289901356d
 *   TRIONOracleV3:        0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C
 *   LiquidityOcean:       0x105c7F6c16d2c92FEad10336C2b6A047F999a5A7
 *   TravelRuleCompliance: 0x5e7DBE6cc90d6260be2781dc312812834715EBaB
 *   BTCPSimpleEscrow:     0x388f98831c749D7Acad2046329c9CeC94A8b248d
 */

import { ethers } from "ethers";

export const ZG_RPC      = "https://evmrpc-testnet.0g.ai";
export const ZG_CHAIN_ID = 16602;
export const ZG_EXPLORER = "https://chainscan-galileo.0g.ai";

export const CONTRACTS = {
  TRIONExecutionGate:   "0xDB5910Dc6CfD219D00F64be1F23DA0289901356d",
  TRIONOracleV3:        "0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C",
  LiquidityOcean:       "0x105c7F6c16d2c92FEad10336C2b6A047F999a5A7",
  TravelRuleCompliance: "0x5e7DBE6cc90d6260be2781dc312812834715EBaB",
  BTCPSimpleEscrow:     "0x388f98831c749D7Acad2046329c9CeC94A8b248d",
};

const GATE_ABI = [
  "function getStats() external view returns (uint256 allowed, uint256 blocked, uint256 published, uint256 anomalies, string memory storageRoot, uint256 storageSyncBlock)",
  "function checkExecution(address entity) external view returns (uint8 status, uint32 phi_t, uint32 theta, uint32 drop_pct, uint64 blockNum)",
  "function lastPublishedSignal() external view returns (uint256 packed, bytes32 beoHash, bytes32 daProofHash)",
];

/**
 * getChainStatus — read live stats from all deployed contracts.
 */
export async function getChainStatus() {
  const provider = new ethers.JsonRpcProvider(ZG_RPC);
  const gate     = new ethers.Contract(CONTRACTS.TRIONExecutionGate, GATE_ABI, provider);
  const result   = {
    chain:          "0G Galileo",
    chain_id:       ZG_CHAIN_ID,
    rpc:            ZG_RPC,
    explorer:       ZG_EXPLORER,
    contracts:      Object.entries(CONTRACTS).map(([name, addr]) => ({
      name,
      address:     addr,
      explorer_url:`${ZG_EXPLORER}/address/${addr}`,
    })),
    gate_stats:     null,
    last_signal:    null,
    block_number:   null,
    timestamp:      Math.floor(Date.now() / 1000),
  };

  try {
    const [stats, block] = await Promise.all([
      gate.getStats(),
      provider.getBlockNumber(),
    ]);
    result.gate_stats = {
      allowed:      Number(stats[0]),
      blocked:      Number(stats[1]),
      published:    Number(stats[2]),
      anomalies:    Number(stats[3]),
      storage_root: stats[4],
      sync_block:   Number(stats[5]),
    };
    result.block_number = block;
    result.ok = true;
  } catch (e) {
    result.ok    = false;
    result.error = e.message?.slice(0, 100);
  }

  return result;
}

/**
 * checkExecution — call TRIONExecutionGate.checkExecution() for an address.
 */
export async function checkExecution(entityAddress) {
  const STATUS = { 0: "UNREGISTERED", 1: "SAFE", 2: "ELEVATED", 3: "COLLAPSE", 4: "HOSTILE" };
  try {
    const addr     = ethers.isAddress(entityAddress) ? entityAddress : ethers.ZeroAddress;
    const provider = new ethers.JsonRpcProvider(ZG_RPC);
    const gate     = new ethers.Contract(CONTRACTS.TRIONExecutionGate, GATE_ABI, provider);
    const result   = await gate.checkExecution(addr);
    const code     = Number(result[0]);
    return {
      ok:                true,
      entity:            entityAddress,
      status_code:       code,
      status:            STATUS[code] || "UNKNOWN",
      phi_t:             Number(result[1]) / 1e6,
      theta:             Number(result[2]) / 1e6,
      drop_pct:          Number(result[3]) / 1e4,
      block:             Number(result[4]),
      execution_allowed: code <= 2,
      gate:              CONTRACTS.TRIONExecutionGate,
      explorer:          `${ZG_EXPLORER}/address/${CONTRACTS.TRIONExecutionGate}`,
    };
  } catch (e) {
    const msg = e.message || "";
    // Contract reverts when entity is not registered — treat as UNREGISTERED (not an error)
    if (msg.includes("revert") || msg.includes("require(false)") || msg.includes("no data")) {
      return {
        ok:                true,
        entity:            entityAddress,
        status_code:       0,
        status:            "UNREGISTERED",
        phi_t:             0,
        theta:             0,
        drop_pct:          0,
        block:             0,
        execution_allowed: false,
        note:              "Entity not registered in TRIONExecutionGate — no behavioral profile on-chain yet",
        gate:              CONTRACTS.TRIONExecutionGate,
        explorer:          `${ZG_EXPLORER}/address/${CONTRACTS.TRIONExecutionGate}`,
      };
    }
    return { ok: false, error: msg.slice(0, 150) };
  }
}
