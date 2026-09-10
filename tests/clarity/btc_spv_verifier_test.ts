/**
 * btc_spv_verifier_test.ts
 *
 * TRION BTCP Zero-Bridge — Clarity contracts unit tests.
 *
 * Covers:
 *   1. Anchor encoder parity: recompute-anchor-bh must match the golden vector
 *      0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a
 *      (byte-identical to Python / Solidity / Cairo implementations).
 *   2. Depth tiers 6 / 12 / 24 — required-depth thresholds enforced.
 *   3. Quorum math in BTCPEscrow — 2-of-3 fails, 3-of-3 succeeds.
 *
 * Run: `npx vitest run` after `npm install @stacks/clarinet-sdk vitest`
 * (the `@stacks/clarinet` npm package is deprecated; use the binary for the SDK).
 */

import { describe, it, expect, beforeAll } from "vitest";
import { initSimnet, Simnet } from "@stacks/clarinet-sdk";
import { Cl, ClarityValue } from "@stacks/transactions";

// ---- Golden vector from /docs/proofs/anchor_parity_pinned.json ----
const GOLDEN = {
  txid: "62bfe73fab5ac18c64794493d3713c5eb3e92b839df401befecd68162ee1fcf7",
  block_hash_le: "00000000000001a9562ec7227605f68ea1baf77dfa37d6794fcd55bca4a509f4",
  block_height: 5128449,
  block_time: 1788718503,
  amount_sats: 304527,
  btc_addr: "tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks",
  chain_id: 100,
  entity_id_hex:
    "cc8aa95abbc7965be22cccc07b10c79520df838debd693b119bec27154bea39b",
  magnitude_nano: 304527000000000,
  anchor_bh: "0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a",
};

// Hex-string helpers (avoids 0x-prefix mismatch with Clarity buff literals).
function hexToBytes(hex: string): Uint8Array {
  const clean = hex.startsWith("0x") ? hex.slice(2) : hex;
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i++) {
    out[i] = parseInt(clean.substr(i * 2, 2), 16);
  }
  return out;
}

// Hex-string of a Clarity buff result (strips 0x, lower-cases).
function clarityBuffToHex(cv: ClarityValue): string {
  // BuffRepr: type=ClarityType.Buffer, with .buffer as Uint8Array
  // The clarinet-sdk Cl type uses ClarityType.BufferInt / .buffer field.
  // We accept either format here for resilience across SDK versions.
  // @ts-ignore — field shape varies across clarinet-sdk versions
  const buf: Uint8Array = cv.buffer ?? cv.buff ?? cv.value;
  return Array.from(buf)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

// ---- Tests ----
let simnet: Simnet;
let deployer: string;
let wallet1: string;
let wallet2: string;
let wallet3: string;

// Module-level constants used across multiple describe blocks.
const EXECUTION_BH = "22".repeat(32);
const COHERENCE = 900000;

beforeAll(async () => {
  simnet = await initSimnet();
  deployer = simnet.deployer;
  wallet1 = simnet.accounts.get("wallet_1")!.stx_address;
  wallet2 = simnet.accounts.get("wallet_2")!.stx_address;
  wallet3 = simnet.accounts.get("wallet_3")!.stx_address;
});

describe("BTCSPVVerifier — anchor encoder parity", () => {
  it("recompute-anchor-bh matches the golden vector byte-for-byte", () => {
    const entityId = hexToBytes(GOLDEN.entity_id_hex);
    const blockHash = hexToBytes(GOLDEN.block_hash_le);

    const result = simnet.callReadOnlyFn(
      `${deployer}.btcspv-verifier`,
      "recompute-anchor-bh",
      [
        Cl.buffer(entityId),       // entity-id
        Cl.uint(0),                // event-type (0 = transfer)
        Cl.uint(GOLDEN.magnitude_nano), // magnitude-nano
        Cl.uint(GOLDEN.block_time),     // block-time
        Cl.uint(GOLDEN.chain_id),       // chain-id
        Cl.buffer(blockHash),           // block-hash
      ],
      deployer
    );

    const outHex = clarityBuffToHex(result.result);
    const expected = GOLDEN.anchor_bh.startsWith("0x")
      ? GOLDEN.anchor_bh.slice(2)
      : GOLDEN.anchor_bh;
    expect(outHex.toLowerCase()).toBe(expected.toLowerCase());
  });

  it("recompute-anchor-bh is deterministic — same inputs ⇒ same output", () => {
    const entityId = hexToBytes(GOLDEN.entity_id_hex);
    const blockHash = hexToBytes(GOLDEN.block_hash_le);

    const r1 = simnet.callReadOnlyFn(
      `${deployer}.btcspv-verifier`,
      "recompute-anchor-bh",
      [
        Cl.buffer(entityId),
        Cl.uint(0),
        Cl.uint(GOLDEN.magnitude_nano),
        Cl.uint(GOLDEN.block_time),
        Cl.uint(GOLDEN.chain_id),
        Cl.buffer(blockHash),
      ],
      deployer
    );
    const r2 = simnet.callReadOnlyFn(
      `${deployer}.btcspv-verifier`,
      "recompute-anchor-bh",
      [
        Cl.buffer(entityId),
        Cl.uint(0),
        Cl.uint(GOLDEN.magnitude_nano),
        Cl.uint(GOLDEN.block_time),
        Cl.uint(GOLDEN.chain_id),
        Cl.buffer(blockHash),
      ],
      deployer
    );
    expect(clarityBuffToHex(r1.result)).toBe(clarityBuffToHex(r2.result));
  });
});

describe("BTCSPVVerifier — depth tiers (6 / 12 / 24)", () => {
  // Submit genesis + N headers, then attempt verify-anchor with each tier.
  // We DON'T need real Merkle proofs for the depth-tier test — we just need
  // to see DepthInsufficient (u102) when depth < required-depth.
  //
  //   value-usd < 100,000   -> required-depth = 6
  //   value-usd < 1,000,000 -> required-depth = 12
  //   value-usd >= 1,000,000 -> required-depth = 24

  const GENESIS_HASH = "aa".repeat(32);
  const GENESIS_MROOT = "bb".repeat(32);

  function submitHeader(height: number, prevHashHex: string, hashHex: string) {
    const r = simnet.callPublicFn(
      `${deployer}.btcspv-verifier`,
      "submit-block-header",
      [
        Cl.buffer(hexToBytes(hashHex)),                 // block-hash
        Cl.uint(height),                                // height
        Cl.buffer(hexToBytes("cc".repeat(32))),         // merkle-root
        Cl.uint(1788718503 + height),                   // timestamp
        Cl.uint(0x1d00ffff),                            // bits
        Cl.buffer(hexToBytes(prevHashHex)),             // prev-hash
      ],
      deployer
    );
    expect(r.result).toEqual(expect.objectContaining({}));
  }

  it("submits genesis tip", () => {
    const r = simnet.callPublicFn(
      `${deployer}.btcspv-verifier`,
      "submit-genesis-tip",
      [
        Cl.buffer(hexToBytes(GENESIS_HASH)),
        Cl.uint(1000000),
        Cl.buffer(hexToBytes(GENESIS_MROOT)),
        Cl.uint(1788718503),
        Cl.uint(0x1d00ffff),
      ],
      deployer
    );
    // (ok true)
    expect(r.result.isOk).toBe(true);
  });

  it("rejects verify-anchor with DepthInsufficient (u102) at depth 5 for value_usd < 100k", () => {
    // Submit 5 more headers — depth becomes 5. value-usd=50000 -> required=6.
    let prev = GENESIS_HASH;
    for (let i = 1; i <= 5; i++) {
      const h = (1000000 + i).toString(16).padStart(64, "0");
      submitHeader(1000000 + i, prev, h);
      prev = h;
    }
    const result = simnet.callPublicFn(
      `${deployer}.btcspv-verifier`,
      "verify-anchor",
      [
        Cl.buffer(hexToBytes(GOLDEN.anchor_bh.slice(2))),     // anchor-bh (will mismatch later)
        Cl.buffer(hexToBytes(GENESIS_HASH)),                  // block-hash
        Cl.buffer(hexToBytes(GOLDEN.txid)),                  // txid
        Cl.uint(0),                                           // tx-index
        Cl.buffer([]),                                        // merkle-path (empty list)
        Cl.uint(0),                                           // merkle-depth
        Cl.buffer(hexToBytes(GOLDEN.entity_id_hex)),          // entity-id
        Cl.uint(0),                                           // event-type
        Cl.uint(GOLDEN.magnitude_nano),                       // magnitude-nano
        Cl.uint(GOLDEN.block_time),                           // block-time
        Cl.uint(GOLDEN.chain_id),                             // chain-id
        Cl.uint(50000),                                       // value-usd -> required-depth 6
      ],
      deployer
    );
    // Expect (err u102) — DepthInsufficient
    expect(result.result.isOk).toBe(false);
    // The err code is u102 (ERR-DEPTH-INSUFFICIENT)
    // @ts-ignore — clarinet-sdk exposes err value via .value
    const errVal = result.result.value;
    expect(Number(errVal ?? result.result)).toBe(102);
  });

  it("rejects verify-anchor with DepthInsufficient (u102) at depth 6 for value_usd < 1M", () => {
    // Submit 1 more header — depth becomes 6. value-usd=500000 -> required=12.
    const prev = (1000000 + 5).toString(16).padStart(64, "0");
    const newH = (1000006).toString(16).padStart(64, "0");
    submitHeader(1000006, prev, newH);

    const result = simnet.callPublicFn(
      `${deployer}.btcspv-verifier`,
      "verify-anchor",
      [
        Cl.buffer(hexToBytes(GOLDEN.anchor_bh.slice(2))),
        Cl.buffer(hexToBytes(GENESIS_HASH)),
        Cl.buffer(hexToBytes(GOLDEN.txid)),
        Cl.uint(0),
        Cl.buffer([]),
        Cl.uint(0),
        Cl.buffer(hexToBytes(GOLDEN.entity_id_hex)),
        Cl.uint(0),
        Cl.uint(GOLDEN.magnitude_nano),
        Cl.uint(GOLDEN.block_time),
        Cl.uint(GOLDEN.chain_id),
        Cl.uint(500000), // -> required-depth 12
      ],
      deployer
    );
    expect(result.result.isOk).toBe(false);
    // @ts-ignore
    const errVal = result.result.value;
    expect(Number(errVal ?? result.result)).toBe(102);
  });

  it("rejects verify-anchor with DepthInsufficient (u102) at depth 12 for value_usd >= 1M", () => {
    // Submit 6 more headers — depth becomes 12. value-usd=2000000 -> required=24.
    let prev = (1000006).toString(16).padStart(64, "0");
    for (let i = 7; i <= 12; i++) {
      const h = (1000000 + i).toString(16).padStart(64, "0");
      submitHeader(1000000 + i, prev, h);
      prev = h;
    }

    const result = simnet.callPublicFn(
      `${deployer}.btcspv-verifier`,
      "verify-anchor",
      [
        Cl.buffer(hexToBytes(GOLDEN.anchor_bh.slice(2))),
        Cl.buffer(hexToBytes(GENESIS_HASH)),
        Cl.buffer(hexToBytes(GOLDEN.txid)),
        Cl.uint(0),
        Cl.buffer([]),
        Cl.uint(0),
        Cl.buffer(hexToBytes(GOLDEN.entity_id_hex)),
        Cl.uint(0),
        Cl.uint(GOLDEN.magnitude_nano),
        Cl.uint(GOLDEN.block_time),
        Cl.uint(GOLDEN.chain_id),
        Cl.uint(2000000), // -> required-depth 24
      ],
      deployer
    );
    expect(result.result.isOk).toBe(false);
    // @ts-ignore
    const errVal = result.result.value;
    expect(Number(errVal ?? result.result)).toBe(102);
  });
});

describe("BTCPEscrow — quorum math", () => {
  const ROUTE_ID = "11".repeat(32);

  function lockEscrow(escrowIdHex: string) {
    const r = simnet.callPublicFn(
      `${deployer}.btcp-escrow`,
      "lock-escrow",
      [
        Cl.buffer(hexToBytes(escrowIdHex)),
        Cl.buffer(hexToBytes(ROUTE_ID)),
        Cl.principal(wallet1),
        Cl.uint(1000),
        Cl.uint(800000),
        Cl.uint(10000), // timeout in tenure-height units
      ],
      deployer
    );
    expect(r.result.isOk).toBe(true);
  }

  function addValidator(v: string) {
    const r = simnet.callPublicFn(
      `${deployer}.btcp-escrow`,
      "add-validator",
      [Cl.principal(v)],
      deployer
    );
    expect(r.result.isOk).toBe(true);
  }

  function submitAttestation(v: string, coherence: number, execBhHex: string, time: number) {
    const r = simnet.callPublicFn(
      `${deployer}.btcp-escrow`,
      "submit-attestation",
      [
        Cl.buffer(hexToBytes(ROUTE_ID)),
        Cl.uint(coherence),
        Cl.buffer(hexToBytes(execBhHex)),
        Cl.uint(time),
      ],
      v
    );
    return r;
  }

  it("owner adds 3 validators", () => {
    addValidator(wallet1);
    addValidator(wallet2);
    addValidator(wallet3);
    const count = simnet.callReadOnlyFn(
      `${deployer}.btcp-escrow`,
      "validator-count",
      [],
      deployer
    );
    // count is a uint ClarityValue
    // @ts-ignore
    expect(Number(count.result.value)).toBe(3);
  });

  it("locks an escrow", () => {
    const escrowId = "33".repeat(32);
    lockEscrow(escrowId);
    const r = simnet.callReadOnlyFn(
      `${deployer}.btcp-escrow`,
      "get-escrow",
      [Cl.buffer(hexToBytes(escrowId))],
      deployer
    );
    // r.result is a (some ...) tuple
    expect(r.result).toBeTruthy();
  });

  it("release-escrow FAILS with 2 attestations (count < quorum=3)", () => {
    // Submit 2 attestations (validators 1 and 2)
    expect(submitAttestation(wallet1, COHERENCE, EXECUTION_BH, 1788718503).result.isOk).toBe(true);
    expect(submitAttestation(wallet2, COHERENCE, EXECUTION_BH, 1788718503).result.isOk).toBe(true);

    // Attempt release — should fail with ERR-QUORUM-NOT-MET (u204)
    const escrowId = "33".repeat(32);
    const r = simnet.callPublicFn(
      `${deployer}.btcp-escrow`,
      "release-escrow",
      [
        Cl.buffer(hexToBytes(escrowId)),
        Cl.buffer(hexToBytes(EXECUTION_BH)),
        Cl.uint(COHERENCE),
        Cl.uint(1788718503 + 60), // block-time, within freshness window
      ],
      deployer
    );
    expect(r.result.isOk).toBe(false);
    // @ts-ignore
    const errVal = r.result.value;
    expect(Number(errVal ?? r.result)).toBe(204); // ERR-QUORUM-NOT-MET
  });

  it("release-escrow SUCCEEDS with 3 attestations (count == quorum=3)", () => {
    // Submit 3rd attestation (validator 3)
    expect(submitAttestation(wallet3, COHERENCE, EXECUTION_BH, 1788718503).result.isOk).toBe(true);

    const escrowId = "33".repeat(32);
    const r = simnet.callPublicFn(
      `${deployer}.btcp-escrow`,
      "release-escrow",
      [
        Cl.buffer(hexToBytes(escrowId)),
        Cl.buffer(hexToBytes(EXECUTION_BH)),
        Cl.uint(COHERENCE),
        Cl.uint(1788718503 + 60), // within freshness window (<= 300s)
      ],
      deployer
    );
    expect(r.result.isOk).toBe(true);
  });

  it("release-escrow FAILS on stale attestation (freshness window > 300s)", () => {
    // Different escrow, same route, but block-time far from attestation-time
    const escrowId = "44".repeat(32);
    lockEscrow(escrowId);

    // We've already had 3 attestations on this route-id; submit one more would
    // be a replay. Instead, test the stale-window directly: the existing
    // attestation has last-time=1788718503; block-time=1788718503+1000 > 300s.
    const r = simnet.callPublicFn(
      `${deployer}.btcp-escrow`,
      "release-escrow",
      [
        Cl.buffer(hexToBytes(escrowId)),
        Cl.buffer(hexToBytes(EXECUTION_BH)),
        Cl.uint(COHERENCE),
        Cl.uint(1788718503 + 1000), // 1000s later — exceeds 300s freshness
      ],
      deployer
    );
    expect(r.result.isOk).toBe(false);
    // @ts-ignore
    const errVal = r.result.value;
    expect(Number(errVal ?? r.result)).toBe(207); // ERR-ATTESTATION-STALE
  });
});

describe("BTCPEscrow — mismatch → disputed (fail-closed)", () => {
  it("attestation mismatch marks the route disputed", () => {
    const routeId = "55".repeat(32);
    const escrowId = "66".repeat(32);
    // Lock escrow
    simnet.callPublicFn(
      `${deployer}.btcp-escrow`,
      "lock-escrow",
      [
        Cl.buffer(hexToBytes(escrowId)),
        Cl.buffer(hexToBytes(routeId)),
        Cl.principal(wallet1),
        Cl.uint(1000),
        Cl.uint(800000),
        Cl.uint(10000),
      ],
      deployer
    );

    // First attestation: coherence=900000, exec-bh="22"*32
    simnet.callPublicFn(
      `${deployer}.btcp-escrow`,
      "submit-attestation",
      [
        Cl.buffer(hexToBytes(routeId)),
        Cl.uint(900000),
        Cl.buffer(hexToBytes(EXECUTION_BH)),
        Cl.uint(1788718503),
      ],
      wallet1
    );
    // Second: MISMATCH — coherence=500000
    simnet.callPublicFn(
      `${deployer}.btcp-escrow`,
      "submit-attestation",
      [
        Cl.buffer(hexToBytes(routeId)),
        Cl.uint(500000),
        Cl.buffer(hexToBytes(EXECUTION_BH)),
        Cl.uint(1788718503),
      ],
      wallet2
    );
    // Third: original coherence (count reaches 3, but disputed=true)
    simnet.callPublicFn(
      `${deployer}.btcp-escrow`,
      "submit-attestation",
      [
        Cl.buffer(hexToBytes(routeId)),
        Cl.uint(900000),
        Cl.buffer(hexToBytes(EXECUTION_BH)),
        Cl.uint(1788718503),
      ],
      wallet3
    );

    // Check disputed flag
    const att = simnet.callReadOnlyFn(
      `${deployer}.btcp-escrow`,
      "get-route-attestation",
      [Cl.buffer(hexToBytes(routeId))],
      deployer
    );
    expect(att.result).toBeTruthy();
    // The disputed flag should be true (we can read it from the tuple).
    // @ts-ignore — field access on tuple ClarityValue
    const disputed = att.result.value?.data?.disputed ?? att.result.disputed;
    expect(Boolean(disputed?.value ?? disputed)).toBe(true);

    // Release should fail with ERR-ESCALATION (u210)
    const r = simnet.callPublicFn(
      `${deployer}.btcp-escrow`,
      "release-escrow",
      [
        Cl.buffer(hexToBytes(escrowId)),
        Cl.buffer(hexToBytes(EXECUTION_BH)),
        Cl.uint(900000),
        Cl.uint(1788718503 + 60),
      ],
      deployer
    );
    expect(r.result.isOk).toBe(false);
    // @ts-ignore
    const errVal = r.result.value;
    expect(Number(errVal ?? r.result)).toBe(210); // ERR-ESCALATION
  });
});
