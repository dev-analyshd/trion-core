/**
 * BIRP Bridge — Behavioral Identity Recovery Protocol
 * TRION Protocol — Starknet Sepolia
 *
 * Primitive 6: Privacy-preserving behavioral attestation.
 *
 * Flow:
 *   1. Fetch BEO score from TRION oracle (off-chain)
 *   2. Compute commitment = poseidon_hash(beo_id_felt, salt)
 *   3. Determine tier from C(t) and behavioral signals
 *   4. Submit commitment + tier on-chain to BIRPAttestation contract
 *   5. Return proof receipt
 */

import { RpcProvider, Account, Contract, cairo, hash, num, stark } from "starknet";
import axios from "axios";
import * as dotenv from "dotenv";
import { getProvider } from "./provider.js";
import { STARKNET_CONFIG } from "./config.js";

dotenv.config();

const TRION_API = process.env.TRION_API_URL ?? "http://127.0.0.1:3001";

// Deployed BIRPAttestation contract address (Starknet Sepolia)
// Set after deployment via: pnpm --filter @workspace/starknet-trion run deploy:birp
const BIRP_ADDRESS = process.env.BIRP_ATTESTATION_ADDRESS ?? "";

// ─── ABI (minimal, matching BIRPAttestation.cairo) ──────────────────────────
const BIRP_ABI = [
  {
    name: "submit_proof",
    type: "function",
    inputs: [
      { name: "commitment",    type: "core::felt252" },
      { name: "tier",          type: "core::integer::u8"  },
      { name: "confidence_bp", type: "core::integer::u64" },
      { name: "oracle_sig_r",  type: "core::felt252" },
      { name: "oracle_sig_s",  type: "core::felt252" },
    ],
    outputs: [],
    state_mutability: "external",
  },
  {
    name: "verify_commitment",
    type: "function",
    inputs: [{ name: "commitment", type: "core::felt252" }],
    outputs: [{ type: "BIRPProof" }],
    state_mutability: "view",
  },
  {
    name: "is_above_tier",
    type: "function",
    inputs: [
      { name: "commitment", type: "core::felt252" },
      { name: "min_tier",   type: "core::integer::u8" },
    ],
    outputs: [{ type: "core::bool" }],
    state_mutability: "view",
  },
  {
    name: "total_proofs",
    type: "function",
    inputs: [],
    outputs: [{ type: "core::integer::u64" }],
    state_mutability: "view",
  },
];

export interface BIRPResult {
  entity_id:     string;
  commitment:    string;
  salt:          string;
  tier:          number;
  tier_label:    string;
  confidence_bp: number;
  c_score:       number;
  threshold:     number;
  tx_hash?:      string;
  submitted:     boolean;
  error?:        string;
}

/**
 * Compute a BIRP commitment: poseidon_hash(beo_id_felt, salt).
 * The salt keeps the BEO identity private — only the commitment goes on-chain.
 */
function computeCommitment(beoIdHex: string, salt: string): string {
  const beoFelt = num.toBigInt("0x" + beoIdHex.replace(/^0x/, "").slice(0, 62));
  const saltFelt = num.toBigInt(salt.startsWith("0x") ? salt : "0x" + salt);
  return num.toHexString(hash.computePoseidonHash(beoFelt, saltFelt));
}

/**
 * Map C(t) and behavioral signals to a BIRP tier.
 * Tier 0 = SAFE, 1 = CAUTION, 2 = HIGH_RISK, 3 = HOSTILE
 */
function deriveTier(signal: Record<string, unknown>): { tier: number; label: string; confidence_bp: number } {
  const coherence  = Number(signal.coherence   ?? 0);
  const threshold  = Number(signal.threshold   ?? 0.65);
  const mf_score   = Number(signal.mf_score    ?? 0);
  const sig_type   = String(signal.signal_type ?? "");
  const conf_gen   = Number(signal.conf_genesis ?? 0);

  if (sig_type === "SILENCE" || sig_type === "MANIPULATION_ALERT" || mf_score > 0.60) {
    return { tier: 3, label: "HOSTILE",   confidence_bp: Math.round((mf_score || 0.9) * 10000) };
  }
  if (coherence < threshold * 0.85 || sig_type === "BOOTSTRAP") {
    return { tier: 2, label: "HIGH_RISK", confidence_bp: Math.round(conf_gen * 10000) };
  }
  if (coherence >= threshold && coherence >= 0.80) {
    return { tier: 0, label: "SAFE",      confidence_bp: Math.round(Math.min(1, coherence) * 10000) };
  }
  return {   tier: 1, label: "CAUTION",   confidence_bp: Math.round(Math.min(1, coherence) * 10000) };
}

/**
 * Generate and submit a BIRP proof for an entity.
 *
 * @param entityId   Arbitrum address or BEO entity ID
 * @param submitOnChain  If true, submits the commitment to Starknet
 */
export async function generateBIRPProof(
  entityId: string,
  submitOnChain = true,
): Promise<BIRPResult> {
  // 1. Fetch TRION signal
  let signal: Record<string, unknown>;
  try {
    const res = await axios.get(`${TRION_API}/api/v1/trion/signal/${encodeURIComponent(entityId)}`, { timeout: 8000 });
    signal = res.data as Record<string, unknown>;
  } catch (err: unknown) {
    return { entity_id: entityId, commitment: "", salt: "", tier: 2, tier_label: "HIGH_RISK",
             confidence_bp: 0, c_score: 0, threshold: 0.65, submitted: false,
             error: `Oracle fetch failed: ${String(err)}` };
  }

  const beo_id = String(signal.entity_id ?? entityId).replace(/^0x/, "");
  const { tier, label: tier_label, confidence_bp } = deriveTier(signal);

  // 2. Generate random salt for commitment privacy
  const salt = "0x" + Buffer.from(stark.randomAddress().replace("0x", ""), "hex").slice(0, 16).toString("hex");
  const commitment = computeCommitment(beo_id, salt);

  const result: BIRPResult = {
    entity_id:     entityId,
    commitment,
    salt,
    tier,
    tier_label,
    confidence_bp,
    c_score:   Number(signal.coherence  ?? 0),
    threshold: Number(signal.threshold  ?? 0),
    submitted: false,
  };

  if (!submitOnChain || !BIRP_ADDRESS) {
    console.log(`[BIRP] Proof generated (not submitted — no contract address):`, result);
    return result;
  }

  // 3. Submit commitment on-chain
  const privateKey = process.env.STARKNET_PRIVATE_KEY;
  if (!privateKey) {
    result.error = "STARKNET_PRIVATE_KEY not set";
    return result;
  }

  try {
    const provider = getProvider();
    const accountAddress = process.env.STARKNET_ACCOUNT_ADDRESS ?? "";
    const account  = new Account(provider, accountAddress, privateKey);
    const contract = new Contract(BIRP_ABI, BIRP_ADDRESS, account);

    // Oracle sig placeholders (0,0) — verifier trusts relayer key in current impl
    const tx = await contract.invoke("submit_proof", [
      commitment,
      cairo.felt(tier),
      cairo.uint256(confidence_bp).low,
      "0x0",
      "0x0",
    ]);

    await provider.waitForTransaction(tx.transaction_hash);
    result.tx_hash  = tx.transaction_hash;
    result.submitted = true;
    console.log(`[BIRP] Proof submitted: commitment=${commitment} tier=${tier_label} tx=${tx.transaction_hash}`);
  } catch (err: unknown) {
    result.error    = `Starknet submit failed: ${String(err)}`;
    result.submitted = false;
  }

  return result;
}

/**
 * Verify a commitment on-chain without revealing the underlying BEO.
 */
export async function verifyBIRPCommitment(commitment: string): Promise<{
  active: boolean;
  tier: number;
  tier_label: string;
  confidence_bp: number;
  submitted_at: number;
} | null> {
  if (!BIRP_ADDRESS) return null;
  try {
    const provider = getProvider();
    const contract = new Contract(BIRP_ABI, BIRP_ADDRESS, provider);
    const proof    = await contract.call("verify_commitment", [commitment]);
    if (!proof || !proof[0]) return null;
    const p       = proof[0] as Record<string, unknown>;
    const active  = Boolean(p.active);
    const tier    = Number(p.tier ?? 255);
    const LABELS  = ["SAFE", "CAUTION", "HIGH_RISK", "HOSTILE", "UNKNOWN"];
    return {
      active,
      tier,
      tier_label:    LABELS[tier] ?? "UNKNOWN",
      confidence_bp: Number(p.confidence_bp ?? 0),
      submitted_at:  Number(p.submitted_at ?? 0),
    };
  } catch {
    return null;
  }
}

// CLI entry
if (process.argv[1].endsWith("birp-bridge.ts") || process.argv[1].endsWith("birp-bridge.js")) {
  const entityId = process.argv[2] ?? "NETWORK";
  const submit   = process.argv[3] !== "--no-submit";
  generateBIRPProof(entityId, submit).then(r => {
    console.log(JSON.stringify(r, null, 2));
    process.exit(r.submitted || !submit ? 0 : 1);
  });
}
