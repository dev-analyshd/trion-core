'use client';
import { useAccount, useChainId, useReadContract } from 'wagmi';
import { CONTRACTS, getContract, isBTCPDeployed } from '../config/wagmi';

export const BEO_IDENTITY_ABI = [
  { name: 'getBEO', type: 'function', stateMutability: 'view', inputs: [{ name: 'account', type: 'address' }], outputs: [{ name: 'beoId', type: 'bytes32' }, { name: 'depth', type: 'uint256' }, { name: 'archetype', type: 'uint8' }, { name: 'coherence', type: 'uint256' }] },
  { name: 'beoExists', type: 'function', stateMutability: 'view', inputs: [{ name: 'account', type: 'address' }], outputs: [{ name: '', type: 'bool' }] },
] as const;

export function useBTCPStatus() {
  const chainId = useChainId();
  return {
    isDeployed: isBTCPDeployed(chainId),
    escrowAddress: getContract(CONTRACTS.btcpEscrow, chainId),
    intentAddress: getContract(CONTRACTS.btcpIntent, chainId),
    chainId,
  };
}

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
