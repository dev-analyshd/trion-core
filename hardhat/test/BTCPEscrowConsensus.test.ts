/**
 * BTCPEscrowConsensus.test.ts
 *
 * S3/C2 verification — escrow release is gated by the oracle's SIGNATURE
 * QUORUM, not the relayer's word (DD finding: "escrow release trusts a
 * centralized relayer; 'consensus is the only oracle' claim contradicted").
 *
 * Mirrors contracts/solidity/BTCPEscrow.sol + TRIONOracleV3.sol (self-
 * contained copies in hardhat/contracts/, same pattern as
 * TRIONExecutionGate.sol). Covers:
 *  (a) binding the oracle (one-way setTRIONOracle)
 *  (b) submitting 2 validator attestations with REAL ECDSA signatures via
 *      submitRouteAttestation (aggregated batch, permissionless submitter)
 *  (c) releasing the escrow through the consensus gate
 *  (d) release REVERTS when only the relayer (no quorum) attempts it —
 *      including the legacy publishBTCPRoute allow-list path which can no
 *      longer push a route toward quorum
 *  plus: dynamic quorum max(2, ⌈2/3·validatorCount⌉), non-validator /
 *      unsorted / disputed-batch rejection, and the documented dev-only
 *      trusted-relayer mode (oracle unbound).
 */

import { expect } from "chai";
import { ethers } from "hardhat";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";

type Contract = Awaited<ReturnType<typeof ethers.getContractFactory>> extends never ? never : any;

// ── Constants ────────────────────────────────────────────────────────────────

const COHERENCE   = 900_000n; // ×1e6
const THRESHOLD   = 800_000n; // ×1e6 — isSafe = coherence ≥ threshold
const MIN_COH     = 800_000n; // escrow's minCoherence
const ONE_ETH     = ethers.parseEther("1");
const TIMEOUT     = 100_000;

// ── Fixtures ─────────────────────────────────────────────────────────────────

async function deployOracle(extraValidators: SignerWithAddress[] = []) {
  const [deployer, val1, val2, val3, rogue, dest] = await ethers.getSigners();
  const Factory = await ethers.getContractFactory("TRIONOracleV3");
  const oracle: Contract = await Factory.connect(deployer).deploy();
  await oracle.waitForDeployment();
  for (const v of extraValidators) {
    await oracle.connect(deployer).addValidator(v.address);
  }
  return { oracle, oracleAddr: await oracle.getAddress(), deployer, val1, val2, val3, rogue, dest };
}

/** Sign the route verdict digest exactly as TRIONOracleV3.routeVerdictHash defines it. */
async function signRouteVerdict(
  signer: SignerWithAddress,
  chainId: bigint,
  oracleAddr: string,
  routeId: string,
  anchorBH: string,
  executionBH: string,
  coherence: bigint,
  threshold: bigint,
): Promise<string> {
  const msgHash = ethers.keccak256(
    ethers.solidityPacked(
      ["uint256", "address", "bytes32", "bytes32", "bytes32", "uint256", "uint256"],
      [chainId, oracleAddr, routeId, anchorBH, executionBH, coherence, threshold],
    ),
  );
  // ethers v6: signMessage applies "\x19Ethereum Signed Message:\n32" itself —
  // matching MessageHashUtils.toEthSignedMessageHash on-chain.
  return signer.signMessage(ethers.getBytes(msgHash));
}

/** Sort signers ascending by address (contract requires increasing recovered signers). */
function byAddress(a: SignerWithAddress, b: SignerWithAddress): number {
  const x = a.address.toLowerCase();
  const y = b.address.toLowerCase();
  return x < y ? -1 : x > y ? 1 : 0;
}

async function lockAndVerify(
  escrow: Contract,
  relayer: SignerWithAddress,
  dest: SignerWithAddress,
  escrowId: string,
  routeId: string,
) {
  await escrow.connect(relayer).lockEscrow(
    escrowId, routeId, ethers.id("entity"), dest.address,
    MIN_COH, TIMEOUT, ethers.ZeroHash,
    { value: ONE_ETH },
  );
  await escrow.connect(relayer).verifySettlementCheck(escrowId, ethers.id("check"));
}

// ─────────────────────────────────────────────────────────────────────────────

describe("BTCPEscrow consensus-gated release (S3/C2 — signature-quorum oracle)", () => {
  it("registers validators and derives the dynamic route quorum max(2, ⌈2/3·count⌉)", async () => {
    const { oracle, val1, val2, val3 } = await deployOracle();
    // 1 validator (deployer) → N = 2
    expect(await oracle.validatorCount()).to.equal(1n);
    expect(await oracle.minRouteAttestations()).to.equal(2n);

    await oracle.addValidator(val1.address); // 2 → N = 2
    expect(await oracle.validatorCount()).to.equal(2n);
    expect(await oracle.minRouteAttestations()).to.equal(2n);

    await oracle.addValidator(val2.address); // 3 → ⌈2⌉ = 2
    expect(await oracle.minRouteAttestations()).to.equal(2n);

    await oracle.addValidator(val3.address); // 4 → ⌈8/3⌉ = 3
    expect(await oracle.minRouteAttestations()).to.equal(3n);

    // re-registering an existing validator is rejected (keeps the count honest)
    await expect(oracle.addValidator(val1.address)).to.be.revertedWith("TRION: already validator");
  });

  it("(d) relayer alone (no quorum) CANNOT release — even with a route etched via the legacy allow-list path", async () => {
    const { oracle, oracleAddr, deployer, dest } = await deployOracle(); // deployer = validator #1
    const EscrowFactory = await ethers.getContractFactory("BTCPEscrow");
    const escrow: Contract = await EscrowFactory.connect(deployer).deploy();
    await escrow.waitForDeployment();

    const escrowId = ethers.id("escrow-relayer-only");
    const routeId = ethers.id("route-relayer-only");
    await lockAndVerify(escrow, deployer, dest, escrowId, routeId);

    // (a) bind the oracle — one-way
    await escrow.connect(deployer).setTRIONOracle(oracleAddr);
    expect(await escrow.trionOracle()).to.equal(oracleAddr);

    // No route at all → binding failure first (H1)
    await expect(
      escrow.connect(deployer).releaseEscrow(escrowId, ethers.id("execBH"), COHERENCE),
    ).to.be.revertedWith("ORACLE_ROUTE_NOT_BOUND_TO_ESCROW");

    // Legacy path: the owner/relayer (a registered validator) etches the
    // perfect-looking verdict metadata — but it records NO attestations.
    await oracle.connect(deployer).publishBTCPRoute(routeId, escrowId, ethers.id("execBH"), COHERENCE, THRESHOLD);
    expect(await oracle.routeAttestationCount(routeId)).to.equal(0n);
    expect(await oracle.routeVerdictFinalized(routeId)).to.equal(false);

    // The relayer then attempts release — fails on quorum (fail-closed).
    await expect(
      escrow.connect(deployer).releaseEscrow(escrowId, ethers.id("execBH"), COHERENCE),
    ).to.be.revertedWith("ORACLE_QUORUM_UNMET");
  });

  it("(b)+(c) 2 real validator signatures finalize the verdict and release the escrow via the consensus gate", async () => {
    const { oracle, oracleAddr, deployer, val1, rogue, dest } = await deployOracle([]); // deployer + none → count 1
    await oracle.addValidator(val1.address); // count 2 → N = 2
    const chainId = (await ethers.provider.getNetwork()).chainId;

    const EscrowFactory = await ethers.getContractFactory("BTCPEscrow");
    const escrow: Contract = await EscrowFactory.connect(deployer).deploy();
    await escrow.waitForDeployment();

    const escrowId = ethers.id("escrow-consensus");
    const routeId = ethers.id("route-consensus");
    const execBH = ethers.id("execBH-consensus");
    await lockAndVerify(escrow, deployer, dest, escrowId, routeId);
    await escrow.connect(deployer).setTRIONOracle(oracleAddr);

    // Single relayer-owned validator signature — not quorum (2 needed).
    const oneSig = await signRouteVerdict(deployer, chainId, oracleAddr, routeId, escrowId, execBH, COHERENCE, THRESHOLD);
    await oracle.connect(rogue).submitRouteAttestation(routeId, escrowId, execBH, COHERENCE, THRESHOLD, [oneSig]);
    expect(await oracle.routeAttestationCount(routeId)).to.equal(1n);
    await expect(
      escrow.connect(deployer).releaseEscrow(escrowId, execBH, COHERENCE),
    ).to.be.revertedWith("ORACLE_QUORUM_UNMET");

    // (b) Two DISTINCT validator signatures — submitted by a NON-validator
    // EOA (permissionless: authority lives in the signatures).
    const signers = [deployer, val1].sort(byAddress);
    const sigs = await Promise.all(
      signers.map((s) => signRouteVerdict(s, chainId, oracleAddr, routeId, escrowId, execBH, COHERENCE, THRESHOLD)),
    );
    await expect(
      oracle.connect(rogue).submitRouteAttestation(routeId, escrowId, execBH, COHERENCE, THRESHOLD, sigs),
    )
      .to.emit(oracle, "RouteAttestationSubmitted")
      .to.emit(oracle, "RouteVerdictFinalized");

    expect(await oracle.routeAttestationCount(routeId)).to.equal(2n);
    expect(await oracle.routeVerdictFinalized(routeId)).to.equal(true);
    const [, attestationCount, isSafe, coherence, threshold] = await oracle.routeBinding(routeId);
    expect(attestationCount).to.equal(2n);
    expect(isSafe).to.equal(true);
    expect(coherence).to.equal(COHERENCE);
    expect(threshold).to.equal(THRESHOLD);

    // (c) The relayer now executes the release — gated by the consensus verdict.
    const destBefore = await ethers.provider.getBalance(dest.address);
    await expect(escrow.connect(deployer).releaseEscrow(escrowId, execBH, COHERENCE))
      .to.emit(escrow, "EscrowReleased");
    expect(await ethers.provider.getBalance(dest.address) - destBefore).to.equal(ONE_ETH);
    expect((await escrow.getEscrowCore(escrowId)).state).to.equal(3n); // State.RELEASED
  });

  it("aggregated attestation batches are fail-closed: non-validator, unsorted, disputed, empty", async () => {
    const { oracle, oracleAddr, deployer, val1, rogue } = await deployOracle([]);
    await oracle.addValidator(val1.address);
    const chainId = (await ethers.provider.getNetwork()).chainId;

    const routeId = ethers.id("route-negative");
    const escrowId = ethers.id("escrow-negative");
    const execBH = ethers.id("execBH-neg");

    // empty batch
    await expect(
      oracle.connect(rogue).submitRouteAttestation(routeId, escrowId, execBH, COHERENCE, THRESHOLD, []),
    ).to.be.revertedWith("TRION: empty attestation batch");

    // non-validator signer (rogue is not registered)
    const rogueSig = await signRouteVerdict(rogue, chainId, oracleAddr, routeId, escrowId, execBH, COHERENCE, THRESHOLD);
    await expect(
      oracle.connect(rogue).submitRouteAttestation(routeId, escrowId, execBH, COHERENCE, THRESHOLD, [rogueSig]),
    ).to.be.revertedWith("TRION: attester not validator");

    // unsorted / duplicate signers — same signature twice is not increasing
    const dupSig = await signRouteVerdict(deployer, chainId, oracleAddr, routeId, escrowId, execBH, COHERENCE, THRESHOLD);
    await expect(
      oracle.connect(rogue).submitRouteAttestation(routeId, escrowId, execBH, COHERENCE, THRESHOLD, [dupSig, dupSig]),
    ).to.be.revertedWith("TRION: signer ordering required");

    // First valid batch etches the values …
    const sorted = [deployer, val1].sort(byAddress);
    const sigs = await Promise.all(
      sorted.map((s) => signRouteVerdict(s, chainId, oracleAddr, routeId, escrowId, execBH, COHERENCE, THRESHOLD)),
    );
    await oracle.connect(rogue).submitRouteAttestation(routeId, escrowId, execBH, COHERENCE, THRESHOLD, sigs);
    expect(await oracle.routeAttestationCount(routeId)).to.equal(2n);

    // … a later batch with CONFLICTING values is a dispute → fail closed.
    const conflicting = await Promise.all(
      sorted.map((s) =>
        signRouteVerdict(s, chainId, oracleAddr, routeId, escrowId, execBH, 123_456n, THRESHOLD),
      ),
    );
    await expect(
      oracle.connect(rogue).submitRouteAttestation(routeId, escrowId, execBH, 123_456n, THRESHOLD, conflicting),
    ).to.be.revertedWith("TRION: route values mismatch - disputed");

    // Re-submitting the SAME batch is an idempotent no-op (no double count).
    await oracle.connect(rogue).submitRouteAttestation(routeId, escrowId, execBH, COHERENCE, THRESHOLD, sigs);
    expect(await oracle.routeAttestationCount(routeId)).to.equal(2n);
  });

  it("dynamic quorum: a 2-of-4-validators verdict is NOT releasable until the 3rd attestation lands", async () => {
    const { oracle, oracleAddr, deployer, val1, val2, val3, dest } = await deployOracle([]);
    await oracle.addValidator(val1.address);
    await oracle.addValidator(val2.address);
    await oracle.addValidator(val3.address); // 4 validators → N = 3
    expect(await oracle.minRouteAttestations()).to.equal(3n);
    const chainId = (await ethers.provider.getNetwork()).chainId;

    const EscrowFactory = await ethers.getContractFactory("BTCPEscrow");
    const escrow: Contract = await EscrowFactory.connect(deployer).deploy();
    await escrow.waitForDeployment();
    const escrowId = ethers.id("escrow-dynamic");
    const routeId = ethers.id("route-dynamic");
    const execBH = ethers.id("execBH-dynamic");
    await lockAndVerify(escrow, deployer, dest, escrowId, routeId);
    await escrow.connect(deployer).setTRIONOracle(oracleAddr);

    const twoOfFour = [deployer, val1].sort(byAddress);
    const twoSigs = await Promise.all(
      twoOfFour.map((s) => signRouteVerdict(s, chainId, oracleAddr, routeId, escrowId, execBH, COHERENCE, THRESHOLD)),
    );
    await oracle.submitRouteAttestation(routeId, escrowId, execBH, COHERENCE, THRESHOLD, twoSigs);
    expect(await oracle.routeAttestationCount(routeId)).to.equal(2n);
    expect(await oracle.routeVerdictFinalized(routeId)).to.equal(false);

    // 2 < N=3 → the escrow gate (which reads the oracle's dynamic quorum) reverts.
    await expect(
      escrow.connect(deployer).releaseEscrow(escrowId, execBH, COHERENCE),
    ).to.be.revertedWith("ORACLE_QUORUM_UNMET");

    // Third distinct attestation (val2 signs; batch carries only the new sig) finalizes.
    const thirdSig = await signRouteVerdict(val2, chainId, oracleAddr, routeId, escrowId, execBH, COHERENCE, THRESHOLD);
    await oracle.submitRouteAttestation(routeId, escrowId, execBH, COHERENCE, THRESHOLD, [thirdSig]);
    expect(await oracle.routeVerdictFinalized(routeId)).to.equal(true);

    const destBefore = await ethers.provider.getBalance(dest.address);
    await escrow.connect(deployer).releaseEscrow(escrowId, execBH, COHERENCE);
    expect(await ethers.provider.getBalance(dest.address) - destBefore).to.equal(ONE_ETH);
  });

  it("H1 binding still holds: a quorum-safe verdict for a DIFFERENT escrow cannot release this one", async () => {
    const { oracle, oracleAddr, deployer, val1, dest } = await deployOracle([]);
    await oracle.addValidator(val1.address);
    const chainId = (await ethers.provider.getNetwork()).chainId;

    const EscrowFactory = await ethers.getContractFactory("BTCPEscrow");
    const escrow: Contract = await EscrowFactory.connect(deployer).deploy();
    await escrow.waitForDeployment();
    const escrowId = ethers.id("escrow-h1");
    const routeId = ethers.id("route-h1");
    const execBH = ethers.id("execBH-h1");
    await lockAndVerify(escrow, deployer, dest, escrowId, routeId);
    await escrow.connect(deployer).setTRIONOracle(oracleAddr);

    // Validators finalize a verdict for the route but bind it to ANOTHER escrow.
    const foreignEscrow = ethers.id("someone-elses-escrow");
    const sorted = [deployer, val1].sort(byAddress);
    const sigs = await Promise.all(
      sorted.map((s) => signRouteVerdict(s, chainId, oracleAddr, routeId, foreignEscrow, execBH, COHERENCE, THRESHOLD)),
    );
    await oracle.submitRouteAttestation(routeId, foreignEscrow, execBH, COHERENCE, THRESHOLD, sigs);
    expect(await oracle.routeVerdictFinalized(routeId)).to.equal(true);

    await expect(
      escrow.connect(deployer).releaseEscrow(escrowId, execBH, COHERENCE),
    ).to.be.revertedWith("ORACLE_ROUTE_NOT_BOUND_TO_ESCROW");
  });

  it("trusted-relayer mode (oracle unbound) remains available for local dev — and binding is one-way", async () => {
    const [, , , , , dest] = await ethers.getSigners();
    const [deployer] = await ethers.getSigners();
    const EscrowFactory = await ethers.getContractFactory("BTCPEscrow");
    const escrow: Contract = await EscrowFactory.connect(deployer).deploy();
    await escrow.waitForDeployment();

    const escrowId = ethers.id("escrow-unbound");
    const routeId = ethers.id("route-unbound");
    await lockAndVerify(escrow, deployer, dest, escrowId, routeId);
    expect(await escrow.trionOracle()).to.equal(ethers.ZeroAddress);

    // Unbound: documented dev-only trusted-relayer release still works.
    const destBefore = await ethers.provider.getBalance(dest.address);
    await escrow.connect(deployer).releaseEscrow(escrowId, ethers.id("exec"), COHERENCE);
    expect(await ethers.provider.getBalance(dest.address) - destBefore).to.equal(ONE_ETH);

    // One-way binding: cannot rebind or clear once set.
    const OracleFactory = await ethers.getContractFactory("TRIONOracleV3");
    const oracle: Contract = await OracleFactory.connect(deployer).deploy();
    await oracle.waitForDeployment();
    await escrow.connect(deployer).setTRIONOracle(await oracle.getAddress());
    await expect(
      escrow.connect(deployer).setTRIONOracle(await oracle.getAddress()),
    ).to.be.revertedWith("ORACLE_ALREADY_BOUND");
    await expect(
      escrow.connect(deployer).setTRIONOracle(ethers.ZeroAddress),
    ).to.be.revertedWith("ZERO_ORACLE");
  });
});
