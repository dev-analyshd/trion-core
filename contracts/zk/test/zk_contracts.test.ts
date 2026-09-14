/**
 * zk_contracts.test.ts — TRION BZK Phase 4 acceptance test.
 *
 * Hardhat test suite covering the Phase 4 verifier contracts:
 *  1. TravelRuleCompliance.sol (BTCP Fix 1 Step 4 + Chameleon tiers + AWA freeze)
 *  2. IntentCommitmentRegistry.sol (BTCP §5.6 Phase 1 commit + Phase 3 atomic reveal)
 *  3. ComplementarityVerifier.sol (generic Groth16 verifier wrapper)
 *
 * Per mission Phase 4.4 R-CHANNELS surface audit:
 *  - submits a valid commitment, emits IntentCommitted
 *  - submits an invalid commitment (zero H_intent), reverts
 *  - submits a travel-rule proof at MEDIUM tier (>$1000), emits TRAVEL_RULE_COMPLIANT=TRUE
 *  - submits without proof at CRITICAL tier, reverts with CriticalTierRequiresProof
 *  - injects AWA violation (awaFrozen=true), attempts emission, reverts with AWAFrozen
 *  - greps the contract source for ABSENT fields (per R-ABSENT)
 *
 * Per R-FAILCLOSED: every error in the contracts is a named custom error;
 * the test asserts each named error explicitly.
 *
 * Per R-INVISIBILITY: the AWA freeze has NO override path. The test
 * asserts that no address other than the AWA oracle can thaw the freeze.
 *
 * Per R-CHANNELS: contracts emit signal publication events only; no
 * onchain proof generation. The verifier contracts are mocked — the
 * test asserts the wiring, not the cryptography (which is the Phase 3
 * circuit round-trip's responsibility, blocked per Phase 1 §1).
 */

import { expect } from "chai";
import { ethers } from "hardhat";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";

// ── Mock verifier contracts (testing twins of the snarkjs-generated
//    Groth16 verifier contracts that would be plugged in for real
//    Phase 3 prove/verify round-trips). The mocks satisfy the
//    ITravelRuleVerifier / IComplementarityVerifier / IGroth16Verifier
//    interfaces without requiring a real Groth16 trusted setup.
//
//    The mocks live under hardhat/contracts/zk/test/ alongside this test
//    so Hardhat compiles them. They are NOT part of the production
//    deployment surface (R-CHANNELS: signal publication only). ──────

import {
  TravelRuleCompliance,
  IntentCommitmentRegistry,
  ComplementarityVerifier,
  MockTravelRuleVerifier,
  MockComplementarityGroth16Verifier,
} from "../hardhat-artifacts/typechain-types";

// ── Helpers ──────────────────────────────────────────────────────────────────

const ZERO_BYTES32 = ethers.ZeroHash;

function bytes32(s: string): string {
  return ethers.id(s);
}

/** Build a fake 256-byte Groth16 proof (8 × 32-byte field elements).
 *  Real proofs come from snarkjs; for testing the wiring we use any
 *  256-byte buffer (the mock verifier does NOT check the contents). */
function fakeProof(): string {
  return ethers.hexlify(ethers.randomBytes(256));
}

// ── Phase 4.1 — TravelRuleCompliance ──────────────────────────────────────────

describe("TravelRuleCompliance (BZK Phase 4.1)", function () {
  let awaOracle: SignerWithAddress;
  let deployer: SignerWithAddress;
  let relayer: SignerWithAddress;
  let stranger: SignerWithAddress;
  let trc: TravelRuleCompliance;
  let mockVerifier: MockTravelRuleVerifier;

  beforeEach(async () => {
    [deployer, awaOracle, relayer, stranger] = await ethers.getSigners();

    // Deploy a mock Groth16 / PLONK verifier that always returns true
    // (testing twin of the snarkjs-generated verifier contract).
    const MockV = await ethers.getContractFactory("MockTravelRuleVerifier");
    mockVerifier = (await MockV.deploy(true)) as unknown as MockTravelRuleVerifier;
    await mockVerifier.waitForDeployment();

    // Deploy TravelRuleCompliance with the AWA oracle.
    const TRC = await ethers.getContractFactory("TravelRuleCompliance");
    trc = (await TRC.deploy(await awaOracle.getAddress())) as unknown as TravelRuleCompliance;
    await trc.waitForDeployment();

    // Wire up the mock verifier for the GROTH16 proving system.
    await trc.setVerifier(0 /* GROTH16 */, await mockVerifier.getAddress());

    // Thaw the AWA freeze so we can test the proof submission path.
    await trc.connect(awaOracle).setAwaState(false);
  });

  // ── 1. Constructor sets the AWA freeze to TRUE by default ─────────────────
  it("constructor: awaFrozen defaults to TRUE (R-FAILCLOSED)", async () => {
    const TRC = await ethers.getContractFactory("TravelRuleCompliance");
    const fresh = (await TRC.deploy(await awaOracle.getAddress())) as unknown as TravelRuleCompliance;
    await fresh.waitForDeployment();
    expect(await fresh.awaFrozen()).to.equal(true);
  });

  // ── 2. Constructor rejects address(0) ─────────────────────────────────────
  it("constructor: rejects address(0) AWA oracle (R-FAILCLOSED)", async () => {
    const TRC = await ethers.getContractFactory("TravelRuleCompliance");
    await expect(TRC.deploy(ethers.ZeroAddress))
      .to.be.revertedWithCustomError(trc, "ZeroAddress");
  });

  // ── 3. AWA freeze: submitProof reverts when frozen ───────────────────────
  it("AWA freeze: submitProof reverts with AWAFrozen (R-INVISIBILITY)", async () => {
    await trc.connect(awaOracle).setAwaState(true);
    const entityId = bytes32("entity:1");
    const txHash = bytes32("tx:1");
    const jurisdiction = bytes32("jur:US");
    const disclosureHash = bytes32("dh:1");
    await expect(
      trc.submitProof(
        entityId, txHash, jurisdiction, disclosureHash,
        1 /* MEDIUM */, 0 /* GROTH16 */, "0x", [], 0,
      ),
    ).to.be.revertedWithCustomError(trc, "AWAFrozen");
  });

  // ── 4. AWA freeze: emitCompliant reverts when frozen ──────────────────────
  it("AWA freeze: emitCompliant reverts with AWAFrozen (R-INVISIBILITY)", async () => {
    // Thaw, submit a valid proof, then re-freeze.
    const entityId = bytes32("entity:2");
    const txHash = bytes32("tx:2");
    const jurisdiction = bytes32("jur:US");
    const disclosureHash = bytes32("dh:2");
    const pi = [
      BigInt(txHash), BigInt(jurisdiction), BigInt(disclosureHash),
    ];
    await trc.submitProof(
      entityId, txHash, jurisdiction, disclosureHash,
      1 /* MEDIUM */, 0 /* GROTH16 */, fakeProof(), pi, 2_000n * 10n ** 8n,
    );
    // Re-freeze.
    await trc.connect(awaOracle).setAwaState(true);
    await expect(trc.emitCompliant(entityId, txHash))
      .to.be.revertedWithCustomError(trc, "AWAFrozen");
  });

  // ── 5. AWA freeze: NO override path — stranger cannot thaw ───────────────
  it("AWA freeze: stranger cannot thaw (R-INVISIBILITY)", async () => {
    await trc.connect(awaOracle).setAwaState(true);
    await expect(trc.connect(stranger).setAwaState(false))
      .to.be.revertedWithCustomError(trc, "NotAwaOracle");
    // Deployer also cannot thaw (R-INVISIBILITY: "Cannot be overridden
    // by any single entity").
    await expect(trc.connect(deployer).setAwaState(false))
      .to.be.revertedWithCustomError(trc, "NotAwaOracle");
  });

  // ── 6. MEDIUM tier > $1000 with valid proof: emits TRAVEL_RULE_COMPLIANT ──
  it("MEDIUM tier >$1000 with valid proof: emits TRAVEL_RULE_COMPLIANT=TRUE (BTCP Fix 1 Step 4)", async () => {
    const entityId = bytes32("entity:3");
    const txHash = bytes32("tx:3");
    const jurisdiction = bytes32("jur:US");
    const disclosureHash = bytes32("dh:3");
    const pi = [
      BigInt(txHash), BigInt(jurisdiction), BigInt(disclosureHash),
    ];
    await expect(
      trc.submitProof(
        entityId, txHash, jurisdiction, disclosureHash,
        1 /* MEDIUM */, 0 /* GROTH16 */, fakeProof(), pi, 2_000n * 10n ** 8n,
      ),
    )
      .to.emit(trc, "TravelRuleProofSubmitted")
      .to.emit(trc, "TRAVEL_RULE_COMPLIANT");
    expect(await trc.recordCount()).to.equal(1n);
  });

  // ── 7. MEDIUM tier > $1000 without proof: reverts ─────────────────────────
  it("MEDIUM tier >$1000 without proof: reverts MediumTierRequiresProof", async () => {
    const entityId = bytes32("entity:4");
    const txHash = bytes32("tx:4");
    const jurisdiction = bytes32("jur:US");
    const disclosureHash = bytes32("dh:4");
    await expect(
      trc.submitProof(
        entityId, txHash, jurisdiction, disclosureHash,
        1 /* MEDIUM */, 0 /* GROTH16 */, "0x", [], 2_000n * 10n ** 8n,
      ),
    ).to.be.revertedWithCustomError(trc, "MediumTierRequiresProof");
  });

  // ── 8. CRITICAL tier without proof: reverts ────────────────────────────────
  it("CRITICAL tier without proof: reverts CriticalTierRequiresProof", async () => {
    const entityId = bytes32("entity:5");
    const txHash = bytes32("tx:5");
    const jurisdiction = bytes32("jur:US");
    const disclosureHash = bytes32("dh:5");
    await expect(
      trc.submitProof(
        entityId, txHash, jurisdiction, disclosureHash,
        3 /* CRITICAL */, 0 /* GROTH16 */, "0x", [], 0,
      ),
    ).to.be.revertedWithCustomError(trc, "CriticalTierRequiresProof");
  });

  // ── 9. Invalid (zero) inputs each revert with named errors ───────────────
  it("zero entityId reverts InvalidEntityId", async () => {
    await expect(
      trc.submitProof(
        ZERO_BYTES32, bytes32("tx:6"), bytes32("jur:US"), bytes32("dh:6"),
        1 /* MEDIUM */, 0 /* GROTH16 */, "0x", [], 0,
      ),
    ).to.be.revertedWithCustomError(trc, "InvalidEntityId");
  });
  it("zero txHash reverts InvalidTxHash", async () => {
    await expect(
      trc.submitProof(
        bytes32("entity:6"), ZERO_BYTES32, bytes32("jur:US"), bytes32("dh:6"),
        1 /* MEDIUM */, 0 /* GROTH16 */, "0x", [], 0,
      ),
    ).to.be.revertedWithCustomError(trc, "InvalidTxHash");
  });
  it("zero jurisdictionId reverts InvalidJurisdictionId", async () => {
    await expect(
      trc.submitProof(
        bytes32("entity:7"), bytes32("tx:7"), ZERO_BYTES32, bytes32("dh:7"),
        1 /* MEDIUM */, 0 /* GROTH16 */, "0x", [], 0,
      ),
    ).to.be.revertedWithCustomError(trc, "InvalidJurisdictionId");
  });
  it("zero disclosureHash reverts InvalidDisclosureHash", async () => {
    await expect(
      trc.submitProof(
        bytes32("entity:8"), bytes32("tx:8"), bytes32("jur:US"), ZERO_BYTES32,
        1 /* MEDIUM */, 0 /* GROTH16 */, "0x", [], 0,
      ),
    ).to.be.revertedWithCustomError(trc, "InvalidDisclosureHash");
  });
  it("wrong publicInputs length reverts InvalidPublicInputs (BTCP Fix 1 Step 3)", async () => {
    await expect(
      trc.submitProof(
        bytes32("entity:9"), bytes32("tx:9"), bytes32("jur:US"), bytes32("dh:9"),
        1 /* MEDIUM */, 0 /* GROTH16 */, fakeProof(), [1n, 2n], 0,
      ),
    ).to.be.revertedWithCustomError(trc, "InvalidPublicInputs");
  });

  // ── 10. Failed proof verification reverts TravelRuleProofInvalid ─────────
  it("invalid proof reverts TravelRuleProofInvalid (R-FAILCLOSED)", async () => {
    // Deploy a mock verifier that returns false.
    const MockV = await ethers.getContractFactory("MockTravelRuleVerifier");
    const falseMock = (await MockV.deploy(false)) as unknown as MockTravelRuleVerifier;
    await falseMock.waitForDeployment();
    // Replace the verifier via the two-step handover.
    // First: the existing mock's nominator must call setVerifier (it does
    // since MockTravelRuleVerifier exposes nominator() = deployer).
    await trc.setVerifier(0, await falseMock.getAddress());

    const entityId = bytes32("entity:10");
    const txHash = bytes32("tx:10");
    const jurisdiction = bytes32("jur:US");
    const disclosureHash = bytes32("dh:10");
    const pi = [BigInt(txHash), BigInt(jurisdiction), BigInt(disclosureHash)];
    await expect(
      trc.submitProof(
        entityId, txHash, jurisdiction, disclosureHash,
        1 /* MEDIUM */, 0 /* GROTH16 */, fakeProof(), pi, 2_000n * 10n ** 8n,
      ),
    ).to.be.revertedWithCustomError(trc, "TravelRuleProofInvalid");
  });

  // ── 11. Idempotency — same (entityId, txHash) reverts ─────────────────────
  it("duplicate submission reverts TravelRuleProofAlreadySubmitted", async () => {
    const entityId = bytes32("entity:11");
    const txHash = bytes32("tx:11");
    const jurisdiction = bytes32("jur:US");
    const disclosureHash = bytes32("dh:11");
    const pi = [BigInt(txHash), BigInt(jurisdiction), BigInt(disclosureHash)];
    await trc.submitProof(
      entityId, txHash, jurisdiction, disclosureHash,
      1 /* MEDIUM */, 0 /* GROTH16 */, fakeProof(), pi, 2_000n * 10n ** 8n,
    );
    await expect(
      trc.submitProof(
        entityId, txHash, jurisdiction, disclosureHash,
        1 /* MEDIUM */, 0 /* GROTH16 */, fakeProof(), pi, 2_000n * 10n ** 8n,
      ),
    ).to.be.revertedWithCustomError(trc, "TravelRuleProofAlreadySubmitted");
  });

  // ── 12. AWA oracle two-step handover ─────────────────────────────────────
  it("AWA oracle handover: two-step, no single-transaction takeover", async () => {
    await trc.connect(awaOracle).nominateAwaOracle(await stranger.getAddress());
    // Not the pending oracle yet — deployer cannot accept.
    await expect(trc.connect(deployer).acceptAwaOracleNomination())
      .to.be.revertedWithCustomError(trc, "NotAwaOracle");
    // Stranger accepts.
    await trc.connect(stranger).acceptAwaOracleNomination();
    expect(await trc.awaOracle()).to.equal(await stranger.getAddress());
  });

  // ── 13. R-ABSENT grep — source has no forbidden ABSENT-field tokens ──────
  // (Run by leakage_grep_contracts.sh as a separate acceptance gate.
  // The test below asserts that the script returns exit 0.)
  it("leakage_grep_contracts.sh returns exit 0 (R-ABSENT clean)", async () => {
    const { execSync } = await import("child_process");
    const path = await import("path");
    // The test runs from hardhat/test/zk_contracts.test.ts. The script
    // lives at <repo-root>/contracts/zk/leakage_grep_contracts.sh.
    // 2 ups: hardhat/test/ -> hardhat/ -> <repo-root>/.
    const scriptPath = path.resolve(
      __dirname, "..", "..", "contracts", "zk", "leakage_grep_contracts.sh",
    );
    let exitCode = 0;
    let stderr = "";
    try {
      execSync(`bash ${scriptPath}`, { stdio: "pipe" });
    } catch (err: any) {
      exitCode = err.status ?? 1;
      stderr = err.stderr?.toString() ?? "";
    }
    expect(exitCode, `leakage_grep_contracts.sh must exit 0 (R-ABSENT clean). stderr=${stderr}`).to.equal(0);
  });
});

// ── Phase 4.2 + 4.3 — IntentCommitmentRegistry + ComplementarityVerifier ─────

describe("IntentCommitmentRegistry + ComplementarityVerifier (BZK Phase 4.2 + 4.3)", function () {
  let deployer: SignerWithAddress;
  let stranger: SignerWithAddress;
  let registry: IntentCommitmentRegistry;
  let compVerifier: ComplementarityVerifier;
  let mockGroth16: MockComplementarityGroth16Verifier;

  beforeEach(async () => {
    [deployer, stranger] = await ethers.getSigners();

    // Deploy a mock Groth16 leaf verifier (testing twin of the
    // snarkjs-generated zk_complementarity_proof/verifier.sol).
    const MockG = await ethers.getContractFactory("MockComplementarityGroth16Verifier");
    mockGroth16 = (await MockG.deploy(true)) as unknown as MockComplementarityGroth16Verifier;
    await mockGroth16.waitForDeployment();

    // Deploy the ComplementarityVerifier wrapper.
    const CompV = await ethers.getContractFactory("ComplementarityVerifier");
    compVerifier = (await CompV.deploy()) as unknown as ComplementarityVerifier;
    await compVerifier.waitForDeployment();

    // Register the mock Groth16 leaf verifier under the default circuit ID.
    const defaultCircuitId = await compVerifier.DEFAULT_CIRCUIT_ID();
    await compVerifier.setVerifier(defaultCircuitId, await mockGroth16.getAddress());

    // Deploy IntentCommitmentRegistry.
    const Reg = await ethers.getContractFactory("IntentCommitmentRegistry");
    registry = (await Reg.deploy()) as unknown as IntentCommitmentRegistry;
    await registry.waitForDeployment();

    // Wire the ComplementarityVerifier wrapper as the registry's verifier.
    await registry.setVerifier(await compVerifier.getAddress());
  });

  // ── 1. Phase 1 commit: emits IntentCommitted ─────────────────────────────
  it("commitIntent: emits IntentCommitted (BTCP §5.6 Phase 1)", async () => {
    const H_intent = bytes32("intent:1");
    const entityId = bytes32("entity:1");
    const tx = await registry.commitIntent(H_intent, entityId);
    const rcpt = await tx.wait();
    expect(rcpt).to.not.be.null;
    const ev = rcpt!.logs
      .map((l) => {
        try { return registry.interface.parseLog(l); } catch { return null; }
      })
      .find((e) => e && e.name === "IntentCommitted");
    expect(ev, "IntentCommitted event must be emitted").to.not.be.undefined;
    expect(ev!.args[0]).to.equal(entityId);
    expect(ev!.args[1]).to.equal(H_intent);
    expect(ev!.args[2]).to.equal(BigInt((await ethers.provider.getBlock(rcpt!.blockNumber))!.timestamp));
    expect(await registry.commitCount()).to.equal(1n);
  });

  // ── 2. Phase 1 commit: zero H_intent reverts ─────────────────────────────
  it("commitIntent: zero H_intent reverts ZeroHIntent (R-FAILCLOSED)", async () => {
    await expect(registry.commitIntent(ZERO_BYTES32, bytes32("entity:1")))
      .to.be.revertedWithCustomError(registry, "ZeroHIntent");
  });

  // ── 3. Phase 1 commit: zero entityId reverts ─────────────────────────────
  it("commitIntent: zero entityId reverts ZeroEntityId (R-FAILCLOSED)", async () => {
    await expect(registry.commitIntent(bytes32("intent:1"), ZERO_BYTES32))
      .to.be.revertedWithCustomError(registry, "ZeroEntityId");
  });

  // ── 4. Phase 1 commit: idempotency ───────────────────────────────────────
  it("commitIntent: duplicate H_intent reverts IntentAlreadyCommitted", async () => {
    const H_intent = bytes32("intent:2");
    const entityId = bytes32("entity:2");
    await registry.commitIntent(H_intent, entityId);
    await expect(registry.commitIntent(H_intent, entityId))
      .to.be.revertedWithCustomError(registry, "IntentAlreadyCommitted");
  });

  // ── 5. Phase 3 atomic reveal: valid complementarity proof ────────────────
  it("revealIntent: valid proof emits IntentRevealed (BTCP §5.6 Phase 3)", async () => {
    const H_A = bytes32("intent:A");
    const H_B = bytes32("intent:B");
    const e_A = bytes32("entity:A");
    const e_B = bytes32("entity:B");
    await registry.commitIntent(H_A, e_A);
    await registry.commitIntent(H_B, e_B);
    const pi = [BigInt(H_A), BigInt(H_B), BigInt(e_A), BigInt(e_B), 0n];
    await expect(registry.revealIntent(H_A, H_B, fakeProof(), pi))
      .to.emit(registry, "IntentRevealed");
    expect(await registry.revealCount()).to.equal(1n);
    expect(await registry.isRevealed(H_A)).to.equal(true);
    expect(await registry.isRevealed(H_B)).to.equal(true);
  });

  // ── 6. Phase 3 atomic reveal: invalid proof reverts, both stay hidden ────
  it("revealIntent: invalid proof reverts ComplementarityProofFailed, both stay hidden (BTCP §5.6 Phase 3)", async () => {
    const H_A = bytes32("intent:A2");
    const H_B = bytes32("intent:B2");
    const e_A = bytes32("entity:A2");
    const e_B = bytes32("entity:B2");
    await registry.commitIntent(H_A, e_A);
    await registry.commitIntent(H_B, e_B);

    // Swap the mock Groth16 leaf verifier for one that returns false.
    const MockG = await ethers.getContractFactory("MockComplementarityGroth16Verifier");
    const falseMock = (await MockG.deploy(false)) as unknown as MockComplementarityGroth16Verifier;
    await falseMock.waitForDeployment();
    const defaultCircuitId = await compVerifier.DEFAULT_CIRCUIT_ID();
    await compVerifier.setVerifier(defaultCircuitId, await falseMock.getAddress());

    const pi = [BigInt(H_A), BigInt(H_B), BigInt(e_A), BigInt(e_B), 0n];
    await expect(registry.revealIntent(H_A, H_B, fakeProof(), pi))
      .to.be.revertedWithCustomError(registry, "ComplementarityProofFailed");
    // BTCP §5.6 Phase 3 verbatim: "both intents remain hidden, no
    // information leaked".
    expect(await registry.isRevealed(H_A)).to.equal(false);
    expect(await registry.isRevealed(H_B)).to.equal(false);
    expect(await registry.revealCount()).to.equal(0n);
  });

  // ── 7. Phase 3 atomic reveal: wrong public-inputs length reverts ─────────
  it("revealIntent: wrong publicInputs length reverts InvalidPublicInputsLength", async () => {
    const H_A = bytes32("intent:A3");
    const H_B = bytes32("intent:B3");
    await registry.commitIntent(H_A, bytes32("entity:A3"));
    await registry.commitIntent(H_B, bytes32("entity:B3"));
    await expect(registry.revealIntent(H_A, H_B, fakeProof(), [1n, 2n, 3n]))
      .to.be.revertedWithCustomError(registry, "InvalidPublicInputsLength");
  });

  // ── 8. Phase 3 atomic reveal: missing prior commit reverts ───────────────
  it("revealIntent: missing prior commit reverts IntentNotFound", async () => {
    const H_A = bytes32("intent:A4");
    const H_B = bytes32("intent:B4");   // never committed
    await registry.commitIntent(H_A, bytes32("entity:A4"));
    const pi = [BigInt(H_A), BigInt(H_B), 1n, 2n, 0n];
    await expect(registry.revealIntent(H_A, H_B, fakeProof(), pi))
      .to.be.revertedWithCustomError(registry, "IntentNotFound");
  });

  // ── 9. Phase 3 atomic reveal: double-reveal reverts ─────────────────────
  it("revealIntent: double-reveal reverts IntentAlreadyRevealed", async () => {
    const H_A = bytes32("intent:A5");
    const H_B = bytes32("intent:B5");
    const e_A = bytes32("entity:A5");
    const e_B = bytes32("entity:B5");
    await registry.commitIntent(H_A, e_A);
    await registry.commitIntent(H_B, e_B);
    const pi = [BigInt(H_A), BigInt(H_B), BigInt(e_A), BigInt(e_B), 0n];
    await registry.revealIntent(H_A, H_B, fakeProof(), pi);
    await expect(registry.revealIntent(H_A, H_B, fakeProof(), pi))
      .to.be.revertedWithCustomError(registry, "IntentAlreadyRevealed");
  });

  // ── 10. ComplementarityVerifier: proof length / public-input length checks
  it("ComplementarityVerifier: wrong proof length reverts InvalidProofBytes", async () => {
    const shortProof = ethers.hexlify(ethers.randomBytes(128));
    const pi = [1n, 2n, 3n, 4n, 5n];
    await expect(compVerifier.verifyProof(shortProof, pi))
      .to.be.revertedWithCustomError(compVerifier, "InvalidProofBytes");
  });
  it("ComplementarityVerifier: wrong publicInputs length reverts InvalidPublicInputsLength", async () => {
    const pi = [1n, 2n, 3n];   // should be 5
    await expect(compVerifier.verifyProof(fakeProof(), pi))
      .to.be.revertedWithCustomError(compVerifier, "InvalidPublicInputsLength");
  });

  // ── 11. Two-step verifier handover: no single-transaction takeover ───────
  it("ComplementarityVerifier: two-step handover blocks single-entity takeover", async () => {
    // Deployer is the initial nominator (set in setVerifier above).
    // Stranger cannot directly replace the verifier via setVerifier
    // (NotCircuitNominator revert).
    const MockG = await ethers.getContractFactory("MockComplementarityGroth16Verifier");
    const newMock = (await MockG.deploy(true)) as unknown as MockComplementarityGroth16Verifier;
    await newMock.waitForDeployment();
    const defaultCircuitId = await compVerifier.DEFAULT_CIRCUIT_ID();
    // Stranger is not the nominator — must revert.
    await expect(compVerifier.connect(stranger).setVerifier(defaultCircuitId, await newMock.getAddress()))
      .to.be.revertedWithCustomError(compVerifier, "NotCircuitNominator");
    // Two-step: deployer nominates stranger; stranger calls setVerifier.
    await compVerifier.connect(deployer).nominateSuccessor(defaultCircuitId, await stranger.getAddress());
    await compVerifier.connect(stranger).setVerifier(defaultCircuitId, await newMock.getAddress());
    const meta = await compVerifier.getVerifier(defaultCircuitId);
    expect(meta[0]).to.equal(await newMock.getAddress());
  });
});
