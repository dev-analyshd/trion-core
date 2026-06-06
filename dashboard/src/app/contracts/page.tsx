'use client';

import Topbar from '@/components/Topbar';
import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { HealthData } from '@/lib/types';
import { Shield, ExternalLink } from 'lucide-react';
import clsx from 'clsx';

interface ContractInfo {
  name: string;
  chain: string;
  chainId: number;
  address: string;
  purpose: string;
  status: 'live' | 'testnet' | 'pending';
  explorer?: string;
}

const CONTRACTS: ContractInfo[] = [
  {
    name: 'TRIONExecutionGate',
    chain: '0G Mainnet',
    chainId: 16661,
    address: '0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b',
    purpose: 'Pre-trade firewall — checkExecution(addr)',
    status: 'live',
    explorer: 'https://chainscan.0g.ai/address/0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b',
  },
  {
    name: 'AkashicProof',
    chain: '0G Mainnet',
    chainId: 16661,
    address: '0x33c793fed5bf5fcB043D8c6c74256e7B4b38156D',
    purpose: 'BEO Merkle root storage',
    status: 'live',
    explorer: 'https://chainscan.0g.ai/address/0x33c793fed5bf5fcB043D8c6c74256e7B4b38156D',
  },
  {
    name: 'TRIONOracleV3',
    chain: '0G Galileo Testnet',
    chainId: 16602,
    address: '0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C',
    purpose: 'Behavioral truth oracle v3',
    status: 'testnet',
  },
  {
    name: 'LiquidityOcean',
    chain: '0G Galileo Testnet',
    chainId: 16602,
    address: '0x105c7F6c16d2c92FEad10336C2b6A047F999a5A7',
    purpose: 'Liquidity health scoring',
    status: 'testnet',
  },
  {
    name: 'TravelRuleCompliance',
    chain: '0G Galileo Testnet',
    chainId: 16602,
    address: '0x5e7DBE6cc90d6260be2781dc312812834715EBaB',
    purpose: 'Travel rule enforcement layer',
    status: 'testnet',
  },
  {
    name: 'BTCPSimpleEscrow',
    chain: '0G Galileo Testnet',
    chainId: 16602,
    address: '0x388f98831c749D7Acad2046329c9CeC94A8b248d',
    purpose: 'BTCP cross-chain escrow',
    status: 'testnet',
  },
  {
    name: 'TRIONExecutionGate',
    chain: '0G Galileo Testnet',
    chainId: 16602,
    address: '0xDB5910Dc6CfD219D00F64be1F23DA0289901356d',
    purpose: 'Galileo testnet execution gate',
    status: 'testnet',
  },
  {
    name: 'TRIONSensingOracle',
    chain: 'Arbitrum Sepolia',
    chainId: 421614,
    address: '0xb819c63c02Ed5aB49017C0f3f2568A14624658b3',
    purpose: 'EVM testnet oracle signal emitter',
    status: 'testnet',
    explorer: 'https://sepolia.arbiscan.io/address/0xb819c63c02Ed5aB49017C0f3f2568A14624658b3',
  },
  {
    name: 'Oracle',
    chain: 'HashKey Mainnet',
    chainId: 177,
    address: '0x708193f93Fb897fbeA72e7e7D19237770F19E969',
    purpose: 'HashKey chain behavioral oracle',
    status: 'live',
  },
  {
    name: 'Oracle',
    chain: 'Ethereum Sepolia',
    chainId: 11155111,
    address: '0xB07AD89a10f94B6D3bF2ab0B3a37988b1F37Db39',
    purpose: 'Ethereum testnet oracle',
    status: 'testnet',
  },
  {
    name: 'Oracle',
    chain: 'Base Sepolia',
    chainId: 84532,
    address: '0x7ADF5B7273883C50EFc005BA7EdD3F379Af9680C',
    purpose: 'Base testnet oracle',
    status: 'testnet',
  },
  {
    name: 'Oracle',
    chain: 'Optimism Sepolia',
    chainId: 11155420,
    address: '0x708193f93Fb897fbeA72e7e7D19237770F19E969',
    purpose: 'OP testnet oracle',
    status: 'testnet',
  },
];

const STATUS_STYLE: Record<string, string> = {
  live: 'text-green-400 border-green-400/30 bg-green-400/5',
  testnet: 'text-amber-400 border-amber-400/30 bg-amber-400/5',
  pending: 'text-t3 border-border bg-card2',
};

export default function ContractsPage() {
  const { data: health } = useSWR<HealthData>(endpoints.health, fetchJSON, { refreshInterval: 5000 });

  const liveCount = CONTRACTS.filter(c => c.status === 'live').length;
  const testnetCount = CONTRACTS.filter(c => c.status === 'testnet').length;

  return (
    <>
      <Topbar title="Smart Contract Monitor" />
      <div className="flex-1 overflow-hidden p-5 flex flex-col gap-4">
        {/* Summary */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 flex-shrink-0">
          {[
            { label: 'Contracts', value: CONTRACTS.length, color: 'text-cyan' },
            { label: 'Mainnet Live', value: liveCount, color: 'text-green-400' },
            { label: 'Testnets', value: testnetCount, color: 'text-amber-400' },
            { label: 'Active Block', value: health?.block_number?.toLocaleString() ?? '—', color: 'text-violet-400' },
          ].map(({ label, value, color }) => (
            <div key={label} className="card p-3 text-center">
              <p className={`text-xl font-bold mono ${color}`}>{value}</p>
              <p className="text-[10px] text-t3 uppercase tracking-wide mt-0.5">{label}</p>
            </div>
          ))}
        </div>

        {/* Contract table */}
        <div className="card flex flex-col overflow-hidden flex-1">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-border flex-shrink-0">
            <Shield size={13} className="text-cyan" />
            <span className="text-[12px] font-semibold text-t1">Deployed Contracts</span>
          </div>
          <div className="overflow-y-auto scrollable flex-1">
            <table className="w-full">
              <thead className="sticky top-0 bg-card z-10">
                <tr className="border-b border-border">
                  {['Contract', 'Chain', 'Address', 'Purpose', 'Status', ''].map((h, i) => (
                    <th key={i} className="text-left px-4 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {CONTRACTS.map((c, i) => (
                  <tr key={i} className="border-b border-border/50 hover:bg-card2 transition-colors">
                    <td className="px-4 py-3">
                      <p className="text-[11px] font-semibold text-t1">{c.name}</p>
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-[11px] text-t2">{c.chain}</p>
                      <p className="text-[10px] mono text-t3">Chain {c.chainId}</p>
                    </td>
                    <td className="px-4 py-3">
                      <p className="mono text-[10px] text-cyan tracking-tight">
                        {c.address.slice(0, 10)}…{c.address.slice(-6)}
                      </p>
                    </td>
                    <td className="px-4 py-3 max-w-[200px]">
                      <p className="text-[11px] text-t2">{c.purpose}</p>
                    </td>
                    <td className="px-4 py-3">
                      <span className={clsx('px-1.5 py-0.5 rounded border text-[9px] font-semibold uppercase', STATUS_STYLE[c.status])}>
                        {c.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {c.explorer && (
                        <a
                          href={c.explorer}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-t3 hover:text-cyan transition-colors"
                        >
                          <ExternalLink size={12} />
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
