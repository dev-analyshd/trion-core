'use client';

/**
 * TRION BTCP/BEO hooks — thin façade over useContracts.ts
 *
 * History: this file previously duplicated `useBTCPStatus` and `useUserBEO`
 * from `useContracts.ts` with divergent implementations (different contract
 * targets and ABIs), which silently drifted apart. Per the July 2026 audit
 * the canonical implementations live in `useContracts.ts`; this module now
 * RE-EXPORTS them and keeps only the parts that are genuinely unique here:
 * the BEOAttestation identity ABI (`BEO_IDENTITY_ABI`) and its reader hook.
 *
 * Import from either module — they are the same hooks:
 *   import { useBTCPStatus, useUserBEO } from '@/hooks/useContracts';
 *   import { useBTCPStatus, useUserBEO } from '@/hooks/useBTCP'; // re-export
 */
import { useAccount, useChainId, useReadContract } from 'wagmi';
import { CONTRACTS, getContract } from '../config/wagmi';

// ── Canonical hooks (single source of truth: useContracts.ts) ────────────────
export {
  /** BTCP deployment status + contract addresses for the current chain. */
  useBTCPStatus,
  /** Connected user's registered BEO id (Coherence Vault `registeredBEO`). */
  useUserBEO,
  /** Lock native value in the BTCP escrow (write). */
  useLockEscrow,
  /** Register a BTCP intent (write). */
  useRegisterIntent,
  /** Trigger emergency revert on a BTCP escrow (write). */
  useEmergencyRevert,
  /** Whether the 7-day emergency escape is available for an escrow. */
  useEmergencyEscapeAvailable,
  /** Total value locked in active escrows. */
  useTotalLockedBalance,
  /** Register the connected user's BEO identity (write). */
  useRegisterBEO,
  /** Publish a behavioral truth signal (write). */
  usePublishBehavioralTruth,
  /** Native balance of the connected address. */
  useNativeBalance,
} from './useContracts';

// ── Unique part: BEOAttestation identity reads ───────────────────────────────

/**
 * Minimal ABI for the BEOAttestation contract (contracts/solidity/BEOAttestation.sol).
 * `getBEO` returns the wallet's behavioral identity (BEO id, akashic depth,
 * archetype, coherence); `beoExists` is the existence guard.
 */
export const BEO_IDENTITY_ABI = [
  { name: 'getBEO', type: 'function', stateMutability: 'view', inputs: [{ name: 'account', type: 'address' }], outputs: [{ name: 'beoId', type: 'bytes32' }, { name: 'depth', type: 'uint256' }, { name: 'archetype', type: 'uint8' }, { name: 'coherence', type: 'uint256' }] },
  { name: 'beoExists', type: 'function', stateMutability: 'view', inputs: [{ name: 'account', type: 'address' }], outputs: [{ name: '', type: 'bool' }] },
] as const;

/**
 * Read the connected user's FULL BEO attestation (id, depth, archetype,
 * coherence) from the BEOAttestation contract — distinct from
 * `useUserBEO` (Coherence Vault registeredBEO id only).
 */
export function useUserBEOAttestation() {
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
