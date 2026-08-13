'use client';

/**
 * TRION Contract Interaction Hooks
 *
 * Phase 5.2: Comprehensive wagmi/viem hooks for on-chain contract reads/writes.
 * Each hook auto-detects whether the contract is deployed on the current chain
 * and gracefully returns null/undefined when not deployed.
 *
 * Contracts covered:
 *   - TRIONExecutionGate   — totalSignalsPublished, totalExecutionsAllowed/Blocked, quorum
 *   - TRIONSensingOracle   — publishBehavioralTruth, read events
 *   - BTCPEscrow           — lockFunds, revertEmergency, escrows, MAX_LOCK_DURATION
 *   - BTCPIntent           — registerIntent, getIntent
 *   - BEOIdentityRegistry  — getBEO, beoExists
 *   - BehavioralHashLedger — recordBH, getBH
 */
import {
  useAccount, useChainId, useReadContract, useWriteContract,
  useWaitForTransactionReceipt, useBalance,
} from 'wagmi';
import { CONTRACTS, getContract, isBTCPDeployed } from '../config/wagmi';

// ── ABIs (minimal — only the functions we actually call) ───────────────────

export const BEO_IDENTITY_ABI = [
  { name: 'getBEO', type: 'function', stateMutability: 'view',
    inputs: [{ name: 'account', type: 'address' }],
    outputs: [
      { name: 'beoId', type: 'bytes32' },
      { name: 'depth', type: 'uint256' },
      { name: 'archetype', type: 'uint8' },
      { name: 'coherence', type: 'uint256' },
    ],
  },
  { name: 'beoExists', type: 'function', stateMutability: 'view',
    inputs: [{ name: 'account', type: 'address' }],
    outputs: [{ name: '', type: 'bool' }],
  },
] as const;

export const BTCP_ESCROW_ABI = [
  { name: 'lockFunds', type: 'function', stateMutability: 'payable',
    inputs: [
      { name: 'token', type: 'address' },
      { name: 'amount', type: 'uint256' },
      { name: 'intentHash', type: 'bytes32' },
    ],
    outputs: [],
  },
  { name: 'revertEmergency', type: 'function', stateMutability: 'nonpayable',
    inputs: [{ name: 'escrowId', type: 'uint256' }],
    outputs: [],
  },
  { name: 'release', type: 'function', stateMutability: 'nonpayable',
    inputs: [{ name: 'escrowId', type: 'uint256' }, { name: 'routeSignal', type: 'bytes32' }],
    outputs: [],
  },
  { name: 'escrows', type: 'function', stateMutability: 'view',
    inputs: [{ name: 'escrowId', type: 'uint256' }],
    outputs: [
      { name: 'sender', type: 'address' },
      { name: 'token', type: 'address' },
      { name: 'amount', type: 'uint256' },
      { name: 'lockBlock', type: 'uint256' },
      { name: 'status', type: 'uint8' },
    ],
  },
  { name: 'MAX_LOCK_DURATION', type: 'function', stateMutability: 'view',
    inputs: [],
    outputs: [{ name: '', type: 'uint256' }],
  },
] as const;

export const BTCP_INTENT_ABI = [
  { name: 'registerIntent', type: 'function', stateMutability: 'nonpayable',
    inputs: [
      { name: 'fromAsset', type: 'address' },
      { name: 'toAsset', type: 'address' },
      { name: 'amount', type: 'uint256' },
      { name: 'targetChain', type: 'uint256' },
    ],
    outputs: [{ name: 'intentId', type: 'bytes32' }],
  },
  { name: 'getIntent', type: 'function', stateMutability: 'view',
    inputs: [{ name: 'intentId', type: 'bytes32' }],
    outputs: [
      { name: 'sender', type: 'address' },
      { name: 'status', type: 'uint8' },
    ],
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

export const BH_LEDGER_ABI = [
  { name: 'recordBH', type: 'function', stateMutability: 'nonpayable',
    inputs: [
      { name: 'sense', type: 'bytes32' },
      { name: 'antisense', type: 'bytes32' },
      { name: 'entityId', type: 'bytes32' },
      { name: 'eventType', type: 'uint8' },
    ],
    outputs: [],
  },
  { name: 'getBH', type: 'function', stateMutability: 'view',
    inputs: [{ name: 'index', type: 'uint256' }],
    outputs: [
      { name: 'sense', type: 'bytes32' },
      { name: 'antisense', type: 'bytes32' },
      { name: 'entityId', type: 'bytes32' },
      { name: 'timestamp', type: 'uint256' },
    ],
  },
  { name: 'totalBHs', type: 'function', stateMutability: 'view',
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

/** Read the connected user's BEO identity (if BEOIdentityRegistry is deployed). */
export function useUserBEO() {
  const { address, isConnected } = useAccount();
  const chainId = useChainId();
  const beoAddress = getContract(CONTRACTS.beoIdentity, chainId);
  return useReadContract({
    address: beoAddress as `0x${string}`,
    abi: BEO_IDENTITY_ABI,
    functionName: 'getBEO',
    args: [address!],
    query: { enabled: isConnected && !!address && !!beoAddress },
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

/** Lock funds in BTCP escrow (write). Returns { lockFunds, hash, isPending, receipt }. */
export function useLockFunds() {
  const { writeContract, data: hash, isPending } = useWriteContract();
  const receipt = useWaitForTransactionReceipt({ hash });
  const chainId = useChainId();

  const lockFunds = async (tokenAddress: string, amount: bigint, intentHash: `0x${string}`) => {
    const escrowAddr = getContract(CONTRACTS.btcpEscrow, chainId);
    if (!escrowAddr) throw new Error('BTCP Escrow not deployed on this chain');
    writeContract({
      address: escrowAddr as `0x${string}`,
      abi: BTCP_ESCROW_ABI,
      functionName: 'lockFunds',
      args: [tokenAddress as `0x${string}`, amount, intentHash],
    });
  };

  return { lockFunds, hash, isPending, receipt };
}

/** Register a BTCP intent (write). */
export function useRegisterIntent() {
  const { writeContract, data: hash, isPending } = useWriteContract();
  const receipt = useWaitForTransactionReceipt({ hash });
  const chainId = useChainId();

  const registerIntent = async (
    fromAsset: string,
    toAsset: string,
    amount: bigint,
    targetChain: bigint,
  ) => {
    const intentAddr = getContract(CONTRACTS.btcpIntent, chainId);
    if (!intentAddr) throw new Error('BTCP Intent not deployed on this chain');
    writeContract({
      address: intentAddr as `0x${string}`,
      abi: BTCP_INTENT_ABI,
      functionName: 'registerIntent',
      args: [
        fromAsset as `0x${string}`,
        toAsset as `0x${string}`,
        amount,
        targetChain,
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

  const revertEmergency = async (escrowId: bigint) => {
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

/** Read the MAX_LOCK_DURATION from BTCP escrow (should be 7 days in blocks). */
export function useMaxLockDuration() {
  const chainId = useChainId();
  const escrowAddr = getContract(CONTRACTS.btcpEscrow, chainId);
  return useReadContract({
    address: escrowAddr as `0x${string}`,
    abi: BTCP_ESCROW_ABI,
    functionName: 'MAX_LOCK_DURATION',
    query: { enabled: !!escrowAddr },
  });
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
