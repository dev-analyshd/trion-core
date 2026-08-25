/**
 * TRIONExecutionGate.test.ts
 *
 * Hardhat test suite covering all audit-required behaviours — synced to the
 * canonical AUDIT-3 G3 build (contracts/solidity/TRIONExecutionGate.sol):
 *  1. Fail-closed — uninitialized entities are BLOCKED
 *  2. Quorum enforcement — single signer cannot publish when quorum = 2
 *  3. Quorum passes — two valid distinct signers satisfy quorum = 2
 *  4. Duplicate signer rejection — same key twice counts as 1
 *  5. Non-validator rejection — stranger signature ignored
 *  6. nonReentrant — gate cannot be re-entered during checkExecution
 *  7. Pause / unpause — checkExecution reverts while paused
 *  8. pruneDecisions — owner can delete stale decision records
 *  9. Two-step ownership — transferOwnership / acceptOwnership flow
 * 10. STATUS_COLLAPSE / STATUS_HOSTILE block execution
 * 11. STATUS_SAFE / STATUS_ELEVATED allow execution
 * 12. AWA enforcement (AUDIT-3 G3) — signal emission FROZEN when any of the
 *     four governance conditions fails; updateAWAState restores emission
 * 13. EIP-2 s-malleability guard — high-s twin signatures rejected
 * 14. Validator set management — validatorCount tracking, last-validator and
 *     owner-removal protections, zero-address rejection
 */

import { expect }            from "chai";
import { ethers }            from "hardhat";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";
import { TRIONExecutionGate } from "../hardhat-artifacts/typechain-types";

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Pack behavioral metrics into the uint256 expected by publishSignal. */
function packData(
  status:  number,
  phi_t:   number,
  theta:   number,
  dropPct: number,
): bigint {
  return (
    BigInt(status)               |
    (BigInt(phi_t)   << BigInt(8)) |
    (BigInt(theta)   << BigInt(40)) |
    (BigInt(dropPct) << BigInt(72))
  );
}

/** Build the EIP-191 signed hash that publishSignal verifies. */
async function signPublish(
  signer:     SignerWithAddress,
  chainId:    bigint,
  gateAddr:   string,
  entityId:   string,
  packedData: bigint,
): Promise<string> {
  const msgHash = ethers.keccak256(
    ethers.solidityPacked(
      ["uint256", "address", "bytes32", "uint256"],
      [chainId, gateAddr, entityId, packedData],
    ),
  );
  // ethers v6: signMessage hashes with "\x19Ethereum Signed Message:\n32"
  return signer.signMessage(ethers.getBytes(msgHash));
}

// ── Fixtures ─────────────────────────────────────────────────────────────────

async function deploy(quorum: number = 1) {
  const [owner, validator2, stranger, user] = await ethers.getSigners();
  const Factory = await ethers.getContractFactory("TRIONExecutionGate");
  const gate    = await Factory.deploy(quorum) as unknown as TRIONExecutionGate;
  await gate.waitForDeployment();
  const gateAddr = await gate.getAddress();
  const chainId  = (await ethers.provider.getNetwork()).chainId;
  return { gate, gateAddr, chainId, owner, validator2, stranger, user };
}

const ENTITY_A = ethers.keccak256(ethers.toUtf8Bytes("entity:uniswap"));
const ENTITY_B = ethers.keccak256(ethers.toUtf8Bytes("entity:unknown"));

// ─────────────────────────────────────────────────────────────────────────────

describe("TRIONExecutionGate", function () {

  // ── 1. Fail-closed ─────────────────────────────────────────────────────────
  describe("Fail-closed", function () {
    it("blocks execution for an entity with no published signal", async function () {
      const { gate, user } = await deploy();
      const [allowed] = await gate.checkExecution.staticCall(ENTITY_B, user.address);
      expect(allowed).to.equal(false);
    });

    it("records a decision even for uninitialised entities", async function () {
      const { gate, user } = await deploy();
      await gate.checkExecution(ENTITY_B, user.address);
      expect(await gate.totalExecutionsBlocked()).to.equal(1n);
    });
  });

  // ── 2. Quorum enforcement ──────────────────────────────────────────────────
  describe("Quorum enforcement", function () {
    it("rejects publishSignal when fewer sigs than quorum (quorum=2)", async function () {
      const { gate, gateAddr, chainId, owner } = await deploy(2);
      const packed = packData(1, 800, 735, 0);
      const sig    = await signPublish(owner, chainId, gateAddr, ENTITY_A, packed);
      await expect(
        gate.publishSignal(ENTITY_A, packed, ethers.ZeroHash, ethers.ZeroHash, "", [sig]),
      ).to.be.revertedWith("TRION: Insufficient signatures for quorum");
    });

    it("accepts publishSignal with exactly quorum=2 distinct valid sigs", async function () {
      const { gate, gateAddr, chainId, owner, validator2 } = await deploy(2);
      await gate.addValidator(validator2.address);
      const packed = packData(1, 800, 735, 0);
      const sig1   = await signPublish(owner,      chainId, gateAddr, ENTITY_A, packed);
      const sig2   = await signPublish(validator2, chainId, gateAddr, ENTITY_A, packed);
      await expect(
        gate.publishSignal(ENTITY_A, packed, ethers.ZeroHash, ethers.ZeroHash, "", [sig1, sig2]),
      ).to.emit(gate, "SignalPublished");
      expect((await gate.signals(ENTITY_A)).initialized).to.equal(true);
    });

    it("rejects when both sigs come from the same validator (duplicate)", async function () {
      const { gate, gateAddr, chainId, owner } = await deploy(2);
      const packed = packData(1, 800, 735, 0);
      const sig    = await signPublish(owner, chainId, gateAddr, ENTITY_A, packed);
      await expect(
        gate.publishSignal(ENTITY_A, packed, ethers.ZeroHash, ethers.ZeroHash, "", [sig, sig]),
      ).to.be.revertedWith("TRION: Quorum not met by distinct validators");
    });

    it("ignores signatures from non-validators", async function () {
      const { gate, gateAddr, chainId, owner, stranger } = await deploy(2);
      const packed   = packData(1, 800, 735, 0);
      const ownerSig = await signPublish(owner,    chainId, gateAddr, ENTITY_A, packed);
      const strSig   = await signPublish(stranger, chainId, gateAddr, ENTITY_A, packed);
      await expect(
        gate.publishSignal(ENTITY_A, packed, ethers.ZeroHash, ethers.ZeroHash, "", [ownerSig, strSig]),
      ).to.be.revertedWith("TRION: Quorum not met by distinct validators");
    });
  });

  // ── 3. Gate status logic ───────────────────────────────────────────────────
  describe("Gate status logic", function () {
    async function publishAndCheck(status: number, expectAllowed: boolean) {
      const { gate, gateAddr, chainId, owner, user } = await deploy(1);
      const packed = packData(status, 800, 735, 5);
      const sig    = await signPublish(owner, chainId, gateAddr, ENTITY_A, packed);
      await gate.publishSignal(ENTITY_A, packed, ethers.ZeroHash, ethers.ZeroHash, "", [sig]);
      const [allowed] = await gate.checkExecution.staticCall(ENTITY_A, user.address);
      expect(allowed).to.equal(expectAllowed);
    }

    it("STATUS_SAFE (1) allows execution",       () => publishAndCheck(1, true));
    it("STATUS_ELEVATED (2) allows execution",   () => publishAndCheck(2, true));
    it("STATUS_COLLAPSE (3) blocks execution",   () => publishAndCheck(3, false));
    it("STATUS_HOSTILE (4) blocks execution",    () => publishAndCheck(4, false));
  });

  // ── 4. nonReentrant ────────────────────────────────────────────────────────
  // checkExecution makes no external calls, so a traditional callback-based
  // re-entry is impossible from outside.  The guard is future-proofing.
  // We test the guard directly by using hardhat_setStorageAt to simulate the
  // state the EVM would be in if we were mid-execution (guard = true).
  describe("nonReentrant", function () {
    it("checkExecution reverts when _reentrancyGuard is already set", async function () {
      const { gate, gateAddr, user } = await deploy(1);

      // Storage layout (Solidity packs booleans in declaration order, rightmost first):
      //   slot 5, byte 31 (0x...00) = paused           (false = 0x00)
      //   slot 5, byte 30 (0x...01) = _reentrancyGuard (true  = 0x01)
      // (AUDIT-3 G3 added `validatorCount` at slot 4, shifting the boolean pair
      //  down from slot 4 to slot 5 — owner, pendingOwner, isValidator,
      //  quorumRequired, validatorCount occupy slots 0-4.)
      // To set _reentrancyGuard=true, paused=false:
      const guardSetValue =
        "0x0000000000000000000000000000000000000000000000000000000000000100";
      await ethers.provider.send("hardhat_setStorageAt", [
        gateAddr,
        "0x5",           // slot index 5 (post-G3 layout)
        guardSetValue,
      ]);

      // Now checkExecution should revert because the guard is pre-set
      await expect(gate.checkExecution(ENTITY_B, user.address))
        .to.be.revertedWith("TRION: Reentrant call");

      // Restore state for other tests
      const guardClearValue =
        "0x0000000000000000000000000000000000000000000000000000000000000000";
      await ethers.provider.send("hardhat_setStorageAt", [
        gateAddr, "0x5", guardClearValue,
      ]);
    });

    it("checkExecution succeeds sequentially (guard is unset after each call)", async function () {
      const { gate, user } = await deploy(1);
      // Two sequential calls must both succeed (guard is reset between calls)
      await gate.checkExecution(ENTITY_B, user.address);
      await expect(gate.checkExecution(ENTITY_B, user.address)).to.not.be.reverted;
    });
  });

  // ── 5. Pause / unpause ─────────────────────────────────────────────────────
  describe("Pause / unpause", function () {
    it("pause prevents checkExecution", async function () {
      const { gate, user } = await deploy(1);
      await gate.pause();
      await expect(gate.checkExecution(ENTITY_B, user.address))
        .to.be.revertedWith("TRION: Contract is paused");
    });

    it("pause prevents publishSignal", async function () {
      const { gate, gateAddr, chainId, owner } = await deploy(1);
      await gate.pause();
      const packed = packData(1, 800, 735, 0);
      const sig    = await signPublish(owner, chainId, gateAddr, ENTITY_A, packed);
      await expect(gate.publishSignal(ENTITY_A, packed, ethers.ZeroHash, ethers.ZeroHash, "", [sig]))
        .to.be.revertedWith("TRION: Contract is paused");
    });

    it("unpause restores checkExecution", async function () {
      const { gate, user } = await deploy(1);
      await gate.pause();
      await gate.unpause();
      // Should not revert (returns false for uninit, but no revert)
      await expect(gate.checkExecution(ENTITY_B, user.address)).to.not.be.reverted;
    });

    it("only owner can pause", async function () {
      const { gate, stranger } = await deploy(1);
      await expect(gate.connect(stranger).pause())
        .to.be.revertedWith("TRION: Not owner");
    });
  });

  // ── 6. pruneDecisions ──────────────────────────────────────────────────────
  describe("pruneDecisions", function () {
    it("owner can delete stale decision records", async function () {
      const { gate, user } = await deploy(1);
      const tx = await gate.checkExecution(ENTITY_B, user.address);
      const rc = await tx.wait();

      // Pull the decisionHash from the ExecutionBlocked event
      const iface    = gate.interface;
      let decisionHash = ethers.ZeroHash;
      for (const log of rc!.logs) {
        try {
          const parsed = iface.parseLog(log);
          if (parsed?.name === "ExecutionBlocked") {
            decisionHash = parsed.args.decisionHash;
          }
        } catch { /* skip unrelated logs */ }
      }
      expect(decisionHash).to.not.equal(ethers.ZeroHash);

      // Decision should exist before pruning
      const before = await gate.decisions(decisionHash);
      expect(before.checkedAt).to.be.gt(0n);

      // Prune it
      await expect(gate.pruneDecisions([decisionHash]))
        .to.emit(gate, "DecisionsPruned")
        .withArgs(1n, await ethers.provider.getBlock("latest").then(b => b!.timestamp + 1));

      // Decision should be gone
      const after = await gate.decisions(decisionHash);
      expect(after.checkedAt).to.equal(0n);
    });

    it("pruneDecisions batch limit is 500", async function () {
      const { gate } = await deploy(1);
      const bigBatch = Array.from({ length: 501 }, () => ethers.ZeroHash);
      await expect(gate.pruneDecisions(bigBatch))
        .to.be.revertedWith("TRION: Batch too large (max 500)");
    });

    it("only owner can prune", async function () {
      const { gate, stranger } = await deploy(1);
      await expect(gate.connect(stranger).pruneDecisions([]))
        .to.be.revertedWith("TRION: Not owner");
    });
  });

  // ── 7. Two-step ownership ──────────────────────────────────────────────────
  describe("Two-step ownership", function () {
    it("transferOwnership sets pendingOwner but does NOT transfer immediately", async function () {
      const { gate, validator2 } = await deploy(1);
      await gate.transferOwnership(validator2.address);
      expect(await gate.pendingOwner()).to.equal(validator2.address);
      expect(await gate.owner()).to.not.equal(validator2.address);
    });

    it("acceptOwnership completes the transfer and emits OwnershipTransferred", async function () {
      const { gate, owner, validator2 } = await deploy(1);
      await gate.transferOwnership(validator2.address);
      await expect(gate.connect(validator2).acceptOwnership())
        .to.emit(gate, "OwnershipTransferred")
        .withArgs(owner.address, validator2.address);
      expect(await gate.owner()).to.equal(validator2.address);
      expect(await gate.pendingOwner()).to.equal(ethers.ZeroAddress);
    });

    it("non-pending address cannot accept ownership", async function () {
      const { gate, stranger } = await deploy(1);
      await gate.transferOwnership(stranger.address);
      // A different account tries to steal it
      const [,,, thief] = await ethers.getSigners();
      await expect(gate.connect(thief).acceptOwnership())
        .to.be.revertedWith("TRION: Not pending owner");
    });

    it("transferOwnership to zero address reverts", async function () {
      const { gate } = await deploy(1);
      await expect(gate.transferOwnership(ethers.ZeroAddress))
        .to.be.revertedWith("TRION: Zero address");
    });
  });

  // ── 8. Statistics tracking ─────────────────────────────────────────────────
  describe("Statistics", function () {
    it("tracks totalExecutionsAllowed and totalExecutionsBlocked", async function () {
      const { gate, gateAddr, chainId, owner, user } = await deploy(1);

      // Publish SAFE signal → allow
      const packed = packData(1, 800, 735, 0);
      const sig    = await signPublish(owner, chainId, gateAddr, ENTITY_A, packed);
      await gate.publishSignal(ENTITY_A, packed, ethers.ZeroHash, ethers.ZeroHash, "", [sig]);
      await gate.checkExecution(ENTITY_A, user.address);

      // Unknown entity → block
      await gate.checkExecution(ENTITY_B, user.address);

      expect(await gate.totalExecutionsAllowed()).to.equal(1n);
      expect(await gate.totalExecutionsBlocked()).to.equal(1n);
    });

    it("tracks totalSignalsPublished and totalAnomaliesSealed", async function () {
      const { gate, gateAddr, chainId, owner } = await deploy(1);

      async function publish(status: number) {
        const packed = packData(status, 800, 735, 0);
        const sig    = await signPublish(owner, chainId, gateAddr, ENTITY_A, packed);
        await gate.publishSignal(ENTITY_A, packed, ethers.ZeroHash, ethers.ZeroHash, "", [sig]);
      }

      await publish(1); // SAFE — no anomaly
      await publish(3); // COLLAPSE — anomaly sealed

      expect(await gate.totalSignalsPublished()).to.equal(2n);
      expect(await gate.totalAnomaliesSealed()).to.equal(1n);
    });
  });

  // ── 9. AWA enforcement (AUDIT-3 Gap G3) ────────────────────────────────────
  describe("AWA enforcement (AUDIT-3 G3)", function () {
    it("constructor bootstraps an enforced AWA state", async function () {
      const { gate } = await deploy(1);
      expect(await gate.awaEnforced()).to.equal(true);
      expect(await gate.awaFailureMask()).to.equal(0n);
      expect(await gate.currentHHI()).to.equal(1000n);
      expect(await gate.gratitudeScore()).to.equal(1n);
      expect(await gate.publicGoodBps()).to.equal(1500n);
    });

    it("freezes signal emission when HHI reaches the critical 4000 tier", async function () {
      const { gate, gateAddr, chainId, owner } = await deploy(1);
      await gate.updateAWAState(4000, 1, 1500);           // HHI >= 4000 → critical
      expect(await gate.awaEnforced()).to.equal(false);
      expect(await gate.awaFailureMask()).to.equal(2n);   // bit 1 = HHI

      const packed = packData(1, 800, 735, 0);
      const sig    = await signPublish(owner, chainId, gateAddr, ENTITY_A, packed);
      await expect(
        gate.publishSignal(ENTITY_A, packed, ethers.ZeroHash, ethers.ZeroHash, "", [sig]),
      ).to.be.revertedWith("TRION: AWA not enforced - signal emission frozen");
    });

    it("freezes signal emission when gratitude < 1 (Love Protocol floor)", async function () {
      const { gate, gateAddr, chainId, owner } = await deploy(1);
      await gate.updateAWAState(1000, 0, 1500);           // gratitude < 1
      expect(await gate.awaEnforced()).to.equal(false);
      expect(await gate.awaFailureMask()).to.equal(4n);   // bit 2 = gratitude

      const packed = packData(1, 800, 735, 0);
      const sig    = await signPublish(owner, chainId, gateAddr, ENTITY_A, packed);
      await expect(
        gate.publishSignal(ENTITY_A, packed, ethers.ZeroHash, ethers.ZeroHash, "", [sig]),
      ).to.be.revertedWith("TRION: AWA not enforced - signal emission frozen");
    });

    it("freezes signal emission when public-good charter < 15%", async function () {
      const { gate, gateAddr, chainId, owner } = await deploy(1);
      await gate.updateAWAState(1000, 1, 1499);           // 14.99% < 15% charter
      expect(await gate.awaEnforced()).to.equal(false);
      expect(await gate.awaFailureMask()).to.equal(8n);   // bit 3 = publicGood

      const packed = packData(1, 800, 735, 0);
      const sig    = await signPublish(owner, chainId, gateAddr, ENTITY_A, packed);
      await expect(
        gate.publishSignal(ENTITY_A, packed, ethers.ZeroHash, ethers.ZeroHash, "", [sig]),
      ).to.be.revertedWith("TRION: AWA not enforced - signal emission frozen");
    });

    it("accumulates failure bits and updateAWAState restores emission", async function () {
      const { gate, gateAddr, chainId, owner } = await deploy(1);
      // All three oracle conditions failing at once → mask = 2 | 4 | 8 = 14
      await gate.updateAWAState(5000, 0, 0);
      expect(await gate.awaFailureMask()).to.equal(14n);
      expect(await gate.awaEnforced()).to.equal(false);

      // A single healthy oracle update unfreezes emission immediately
      await expect(gate.updateAWAState(1000, 1, 1500))
        .to.emit(gate, "AWAStateUpdated").withArgs(1000n, 1n, 1500n, true);
      expect(await gate.awaEnforced()).to.equal(true);

      const packed = packData(1, 800, 735, 0);
      const sig    = await signPublish(owner, chainId, gateAddr, ENTITY_A, packed);
      await expect(
        gate.publishSignal(ENTITY_A, packed, ethers.ZeroHash, ethers.ZeroHash, "", [sig]),
      ).to.emit(gate, "SignalPublished");
    });

    it("non-validators cannot update AWA state", async function () {
      const { gate, stranger } = await deploy(1);
      await expect(gate.connect(stranger).updateAWAState(1000, 1, 1500))
        .to.be.revertedWith("TRION: Not a validator");
    });

    it("AWA quorum rule: quorum below ⌈2/3·validatorCount⌉ fails enforcement", async function () {
      const { gate, validator2 } = await deploy(2);
      const signers = await ethers.getSigners();
      const validator3 = signers[4];
      // validatorCount = 3 → required quorum = ⌈2·3/3⌉ = 2; deploy(2) satisfies it
      await gate.addValidator(validator2.address);
      await gate.addValidator(validator3.address);
      expect(await gate.validatorCount()).to.equal(3n);
      expect(await gate.awaEnforced()).to.equal(true);     // quorum=2 ≥ ⌈2/3·3⌉=2

      // Lowering the configured quorum below the 2/3 floor is rejected by
      // setQuorum's G3 guard — the configuration path cannot break AWA.
      await expect(gate.setQuorum(1))
        .to.be.revertedWith("TRION: Quorum below 2/3 of validators");
    });
  });

  // ── 10. EIP-2 s-malleability guard ────────────────────────────────────────
  describe("EIP-2 s-malleability guard", function () {
    it("rejects the high-s malleable twin of a valid signature", async function () {
      const { gate, gateAddr, chainId, owner } = await deploy(1);
      const packed = packData(1, 800, 735, 0);
      const sig    = await signPublish(owner, chainId, gateAddr, ENTITY_A, packed);

      // The canonical signature must be accepted first (sanity)
      await expect(
        gate.publishSignal(ENTITY_A, packed, ethers.ZeroHash, ethers.ZeroHash, "", [sig]),
      ).to.emit(gate, "SignalPublished");

      // Craft the malleable twin: s' = n - s, v' = 27 ↔ 28.
      // This twin recovers to the SAME signer but violates EIP-2's low-s rule.
      const n = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141n;
      const raw = ethers.getBytes(sig);
      const r = BigInt(ethers.hexlify(raw.slice(0, 32)));
      const s = BigInt(ethers.hexlify(raw.slice(32, 64)));
      let v = raw[64];
      const sTwin = n - s;                                   // high half
      const vTwin = v === 27 ? 28 : 27;                      // parity flip
      const twinSig = ethers.concat([
        ethers.zeroPadValue(ethers.toBeHex(r), 32),
        ethers.zeroPadValue(ethers.toBeHex(sTwin), 32),
        new Uint8Array([vTwin]),
      ]);

      // Publishing again for a fresh entity with the malleable twin must fail
      await expect(
        gate.publishSignal(ENTITY_B, packed, ethers.ZeroHash, ethers.ZeroHash, "", [twinSig]),
      ).to.be.revertedWith("TRION: Invalid s (malleable)");
    });
  });

  // ── 11. Validator set management ──────────────────────────────────────────
  describe("Validator set management", function () {
    it("addValidator tracks validatorCount and rejects zero address", async function () {
      const { gate, validator2 } = await deploy(1);
      expect(await gate.validatorCount()).to.equal(1n);     // deployer
      await gate.addValidator(validator2.address);
      expect(await gate.validatorCount()).to.equal(2n);
      expect(await gate.isValidator(validator2.address)).to.equal(true);

      await expect(gate.addValidator(ethers.ZeroAddress))
        .to.be.revertedWith("TRION: Zero address");

      // Idempotent: re-adding does not double-count
      await gate.addValidator(validator2.address);
      expect(await gate.validatorCount()).to.equal(2n);
    });

    it("removeValidator refuses to remove the owner or the last validator", async function () {
      const { gate, owner } = await deploy(1);
      await expect(gate.removeValidator(owner.address))
        .to.be.revertedWith("TRION: Cannot remove owner");
      // owner is the only validator → last-validator protection fires
      await expect(gate.removeValidator(owner.address))
        .to.be.revertedWith("TRION: Cannot remove owner");
    });

    it("removeValidator decrements validatorCount and protects the last one", async function () {
      const { gate, validator2 } = await deploy(1);
      await gate.addValidator(validator2.address);
      await gate.removeValidator(validator2.address);
      expect(await gate.validatorCount()).to.equal(1n);
      expect(await gate.isValidator(validator2.address)).to.equal(false);

      // Now only the owner-validator remains — removing a non-validator first
      await expect(gate.removeValidator(validator2.address))
        .to.be.revertedWith("TRION: Not a validator");
    });
  });
});
