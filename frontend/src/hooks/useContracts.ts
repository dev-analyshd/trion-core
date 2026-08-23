'use client';

/**
 * TRION Contract Interaction Hooks
 *
 * Phase 5.2: Comprehensive wagmi/viem hooks for on-chain contract reads/writes.
 * Each hook auto-detects whether the contract is deployed on the current chain
 * and gracefully returns null/undefined when not deployed.
 *
 * Contracts covered (ABIs aligned with the actual Solidity sources in
 * contracts/solidity/ — regenerated after the security-hardening pass):
 *   - TRIONExecutionGate   — totalSignalsPublished, totalExecutionsAllowed/Blocked, quorum
 *   - TRIONSensingOracle   — publishBehavioralTruth, read events
 *   - BTCPEscrow           — lockEscrow, releaseEscrow, revertEmergency, getEscrow
 *   - BTCPIntent           — registerIntent (11-arg), getIntent
 *   - ConfidentialCoherenceVault — registerBEO, coherenceWrap/Unwrap
 */
import {
  useAccount, useChainId, useReadContract, useWriteContract,
  useWaitForTransactionReceipt, useBalance,
} from 'wagmi';
import { CONTRACTS, getContract, isBTCPDeployed } from '../config/wagmi';

// ── ABIs (minimal — only the functions we actually call) ───────────────────

export const BTCP_ESCROW_ABI = [
  // 7-arg overload with parentEscrowId omitted — use the 6-arg path
  { name: 'lockEscrow', type: 'function', stateMutability: 'payable',
    inputs: [
      { name: 'escrowId', type: 'bytes32' },
      { name: 'routeId', type: 'bytes32' },
      { name: 'entityId', type: 'bytes32' },
      { name: 'destination', type: 'address' },
      { name: 'minCoherence', type: 'uint256' },
      { name: 'timeoutBlocks', type: 'uint256' },
    ],
    outputs: [{ name: '', type: 'bool' }],
  },
  { name: 'releaseEscrow', type: 'function', stateMutability: 'nonpayable',
    inputs: [
      { name: 'escrowId', type: 'bytes32' },
      { name: 'executionBH', type: 'bytes32' },
      { name: 'coherence', type: 'uint256' },
    ],
    outputs: [{ name: '', type: 'bool' }],
  },
  { name: 'revertEmergency', type: 'function', stateMutability: 'nonpayable',
    inputs: [{ name: 'escrowId', type: 'bytes32' }],
    outputs: [{ name: '', type: 'bool' }],
  },
  { name: 'getEscrow', type: 'function', stateMutability: 'view',
    inputs: [{ name: 'escrowId', type: 'bytes32' }],
    outputs: [{ name: '', type: 'tuple' }],
  },
  { name: 'emergencyEscapeAvailable', type: 'function', stateMutability: 'view',
    inputs: [{ name: 'escrowId', type: 'bytes32' }],
    outputs: [{ name: '', type: 'bool' }],
  },
  { name: 'EMERGENCY_ESCAPE_SECONDS', type: 'function', stateMutability: 'view',
    inputs: [], outputs: [{ name: '', type: 'uint256' }],
  },
  { name: 'totalLockedBalance', type: 'function', stateMutability: 'view',
    inputs: [], outputs: [{ name: '', type: 'uint256' }],
  },
] as const;

export const BTCP_INTENT_ABI = [
  { name: 'registerIntent', type: 'function', stateMutability: 'nonpayable',
    inputs: [
      { name: 'intentHash', type: 'bytes32' },
      { name: 'entityId', type: 'bytes32' },
      { name: 'action', type: 'uint8' },
      { name: 'assetIn', type: 'bytes32' },
      { name: 'assetOut', type: 'bytes32' },
      { name: 'magnitude', type: 'uint256' },
      { name: 'deadline', type: 'uint64' },
      { name: 'maxTotalGas', type: 'uint128' },
      { name: 'minFinality', type: 'uint8' },
      { name: 'minNLScore', type: 'uint16' },
      { name: 'privacy', type: 'uint8' },
    ],
    outputs: [{ name: '', type: 'bool' }],
  },
  { name: 'getIntent', type: 'function', stateMutability: 'view',
    inputs: [{ name: 'intentHash', type: 'bytes32' }],
    outputs: [{ name: '', type: 'tuple' }],
  },
  { name: 'intentCount', type: 'function', stateMutability: 'view',
    inputs: [], outputs: [{ name: '', type: 'uint256' }],
  },
] as const;

export const COHERENCE_VAULT_ABI = [
  { name: 'registerBEO', type: 'function', stateMutability: 'nonpayable',
    inputs: [{ name: 'entityId', type: 'bytes32' }],
    outputs: [],
  },
  { name: 'registeredBEO', type: 'function', stateMutability: 'view',
    inputs: [{ name: 'user', type: 'address' }],
    outputs: [{ name: '', type: 'bytes32' }],
  },
  { name: 'coherenceWrap', type: 'function', stateMutability: 'nonpayable',
    inputs: [
      { name: 'amount', type: 'uint256' },
      { name: 'entityId', type: 'bytes32' },
    ],
    outputs: [],
  },
  { name: 'coherenceUnwrap', type: 'function', stateMutability: 'nonpayable',
    inputs: [
      { name: 'amount', type: 'uint256' },
      { name: 'entityId', type: 'bytes32' },
    ],
    outputs: [],
  },
] as const;

export const TRION_EXECUTION_GATE_ABI = [
  { name: 'totalSignalsPublished',  type: 'function', stateMutability: 'view',
    inputs: [], outputs: [{ name: '', type: 'uint256' }] },
  { name: 'totalExecutionsAllowed', type: 'function', stateMutability: 'view',
    inputs: [], outputs: [{ name: '', type: 'uint256' }] },
  { name: 'totalExecutionsBlocked', type: 'function', stateMutability: 'view',
    inputs: [], outputs: [{ name: '', type: 'uint256' }] },
  { name: 'totalAnomaliesSealed',   type: 'function', stateMutability: 'view',
    inputs: [], outputs: [{ name: '', type: 'uint256' }] },
  { name: 'quorumRequired',         type: 'function', stateMutability: 'view',
    inputs: [], outputs: [{ name: '', type: 'uint256' }] },
  { name: 'lastStorageSyncBlock',   type: 'function', stateMutability: 'view',
    inputs: [], outputs: [{ name: '', type: 'uint256' }] },
  { name: 'beoVectorStorageRoot',   type: 'function', stateMutability: 'view',
    inputs: [], outputs: [{ name: '', type: 'string' }] },
] as const;

export const TRION_SENSING_ORACLE_ABI = [
  { name: 'publishBehavioralTruth', type: 'function', stateMutability: 'nonpayable',
    inputs: [
      { name: 'entityId', type: 'bytes32' },
      { name: 'coherence', type: 'uint8' },
      { name: 'mfScore', type: 'uint8' },
      { name: 'packedPlanes', type: 'bytes32' },
    ],
    outputs: [],
  },
  { name: 'totalSignals', type: 'function', stateMutability: 'view',
    inputs: [], outputs: [{ name: '', type: 'uint256' }] },
] as const;

// ── Hooks ───────────────────────────────────────────────────────────────────

/** Check if BTCP contracts are deployed on the current chain. */
export function useBTCPStatus() {
  const chainId = useChainId();
  return {
    isDeployed: isBTCPDeployed(chainId),
    escrowAddress: getContract(CONTRACTS.btcpEscrow, chainId),
    intentAddress: getContract(CONTRACTS.btcpIntent, chainId),
    routeAddress: getContract(CONTRACTS.btcpRoute, chainId),
    chainId,
  };
}

/** Read the connected user's registered BEO identity from the Coherence Vault. */
export function useUserBEO() {
  const { address, isConnected } = useAccount();
  const chainId = useChainId();
  const vaultAddress = getContract(CONTRACTS.coherenceVault, chainId);
  return useReadContract({
    address: vaultAddress as `0x${string}`,
    abi: COHERENCE_VAULT_ABI,
    functionName: 'registeredBEO',
    args: [address!],
    query: { enabled: isConnected && !!address && !!vaultAddress },
  });
}

/** Read TRIONExecutionGate stats (signals published, executions allowed/blocked, etc.). */
export function useTRIONExecutionGate(chainId?: number) {
  const effectiveChainId = chainId ?? useChainId();
  // ExecutionGate doesn't have a per-chain entry in CONTRACTS yet — use the 0G mainnet default
  const gateAddress = effectiveChainId === 16661
    ? '0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b'
    : null;
  return useReadContract({
    address: gateAddress as `0x${string}`,
    abi: TRION_EXECUTION_GATE_ABI,
    functionName: 'totalSignalsPublished',
    query: { enabled: !!gateAddress },
  });
}

/**
 * Lock native value in the BTCP escrow (write).
 * Mirrors BTCPEscrow.lockEscrow(escrowId, routeId, entityId, destination,
 * minCoherence, timeoutBlocks) — payable with the locked amount as msg.value.
 */
export function useLockEscrow() {
  const { writeContract, data: hash, isPending } = useWriteContract();
  const receipt = useWaitForTransactionReceipt({ hash });
  const chainId = useChainId();

  const lockEscrow = async (params: {
    escrowId: `0x${string}`;
    routeId: `0x${string}`;
    entityId: `0x${string}`;
    destination: `0x${string}`;
    minCoherence: bigint;     // ×1e6
    timeoutBlocks: bigint;
    value: bigint;            // native amount to lock
  }) => {
    const escrowAddr = getContract(CONTRACTS.btcpEscrow, chainId);
    if (!escrowAddr) throw new Error('BTCP Escrow not deployed on this chain');
    writeContract({
      address: escrowAddr as `0x${string}`,
      abi: BTCP_ESCROW_ABI,
      functionName: 'lockEscrow',
      args: [
        params.escrowId,
        params.routeId,
        params.entityId,
        params.destination,
        params.minCoherence,
        params.timeoutBlocks,
      ],
      value: params.value,
    });
  };

  return { lockEscrow, hash, isPending, receipt };
}

/**
 * Register a BTCP intent (write).
 * Mirrors BTCPIntent.registerIntent(intentHash, entityId, action, assetIn,
 * assetOut, magnitude, deadline, maxTotalGas, minFinality, minNLScore, privacy).
 */
export function useRegisterIntent() {
  const { writeContract, data: hash, isPending } = useWriteContract();
  const receipt = useWaitForTransactionReceipt({ hash });
  const chainId = useChainId();

  const registerIntent = async (params: {
    intentHash: `0x${string}`;
    entityId: `0x${string}`;
    action: number;           // enum: 0=TRANSFER 1=SWAP 2=LIQUIDITY 3=STAKE 4=BORROW
    assetIn: `0x${string}`;
    assetOut: `0x${string}`;
    magnitude: bigint;
    deadline: bigint;
    maxTotalGas: bigint;
    minFinality: number;      // 0=FAST 1=STANDARD 2=SECURE
    minNLScore: number;       // ×1000 (default 300 = 0.30)
    privacy: number;          // 0=PUBLIC 1=ZK_CREDENTIAL 2=INVISIBLE
  }) => {
    const intentAddr = getContract(CONTRACTS.btcpIntent, chainId);
    if (!intentAddr) throw new Error('BTCP Intent not deployed on this chain');
    writeContract({
      address: intentAddr as `0x${string}`,
      abi: BTCP_INTENT_ABI,
      functionName: 'registerIntent',
      args: [
        params.intentHash,
        params.entityId,
        params.action,        // uint8
        params.assetIn,
        params.assetOut,
        params.magnitude,     // uint256
        params.deadline,      // uint64
        params.maxTotalGas,   // uint128
        params.minFinality,   // uint8
        params.minNLScore,    // uint16
        params.privacy,       // uint8
      ],
    });
  };

  return { registerIntent, hash, isPending, receipt };
}

/** Trigger emergency revert on a BTCP escrow (write, callable by ANYONE). */
export function useEmergencyRevert() {
  const { writeContract, data: hash, isPending } = useWriteContract();
  const receipt = useWaitForTransactionReceipt({ hash });
  const chainId = useChainId();

  const revertEmergency = async (escrowId: `0x${string}`) => {
    const escrowAddr = getContract(CONTRACTS.btcpEscrow, chainId);
    if (!escrowAddr) throw new Error('BTCP Escrow not deployed on this chain');
    writeContract({
      address: escrowAddr as `0x${string}`,
      abi: BTCP_ESCROW_ABI,
      functionName: 'revertEmergency',
      args: [escrowId],
    });
  };

  return { revertEmergency, hash, isPending, receipt };
}

/** Read whether the 7-day emergency escape is available for an escrow. */
export function useEmergencyEscapeAvailable(escrowId?: `0x${string}`) {
  const chainId = useChainId();
  const escrowAddr = getContract(CONTRACTS.btcpEscrow, chainId);
  return useReadContract({
    address: escrowAddr as `0x${string}`,
    abi: BTCP_ESCROW_ABI,
    functionName: 'emergencyEscapeAvailable',
    args: escrowId ? [escrowId] : undefined,
    query: { enabled: !!escrowAddr && !!escrowId },
  });
}

/** Read total value locked in active escrows (security view). */
export function useTotalLockedBalance() {
  const chainId = useChainId();
  const escrowAddr = getContract(CONTRACTS.btcpEscrow, chainId);
  return useReadContract({
    address: escrowAddr as `0x${string}`,
    abi: BTCP_ESCROW_ABI,
    functionName: 'totalLockedBalance',
    query: { enabled: !!escrowAddr },
  });
}

/** Register the connected user's BEO identity on the Coherence Vault (write). */
export function useRegisterBEO() {
  const { writeContract, data: hash, isPending } = useWriteContract();
  const receipt = useWaitForTransactionReceipt({ hash });
  const chainId = useChainId();

  const registerBEO = async (entityId: `0x${string}`) => {
    const vaultAddr = getContract(CONTRACTS.coherenceVault, chainId);
    if (!vaultAddr) throw new Error('Coherence Vault not deployed on this chain');
    writeContract({
      address: vaultAddr as `0x${string}`,
      abi: COHERENCE_VAULT_ABI,
      functionName: 'registerBEO',
      args: [entityId],
    });
  };

  return { registerBEO, hash, isPending, receipt };
}

/** Publish a behavioral truth signal via TRIONSensingOracle (write). */
export function usePublishBehavioralTruth() {
  const { writeContract, data: hash, isPending } = useWriteContract();
  const receipt = useWaitForTransactionReceipt({ hash });
  const chainId = useChainId();
  // SensingOracle uses the same address map as oracleV3
  const oracleAddr = CONTRACTS.oracleV3?.[chainId];

  const publishBehavioralTruth = async (
    entityId: `0x${string}`,
    coherence: number,    // 0-255
    mfScore: number,      // 0-255
    packedPlanes: `0x${string}`,
  ) => {
    if (!oracleAddr) throw new Error('TRION Sensing Oracle not deployed on this chain');
    writeContract({
      address: oracleAddr as `0x${string}`,
      abi: TRION_SENSING_ORACLE_ABI,
      functionName: 'publishBehavioralTruth',
      args: [entityId, coherence, mfScore, packedPlanes],
    });
  };

  return { publishBehavioralTruth, hash, isPending, receipt };
}

/** Convenience: native balance of the connected address. */
export function useNativeBalance() {
  const { address } = useAccount();
  return useBalance({ address });
}
