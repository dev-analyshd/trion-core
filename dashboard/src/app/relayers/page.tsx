'use client';

import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { RelayersStatus, RelayerChainStatus, RelayerVmStatus } from '@/lib/types';
import Topbar from '@/components/Topbar';
import { Radio, CheckCircle, XCircle, Activity } from 'lucide-react';
import clsx from 'clsx';

function ModeBadge({ mode }: { mode: string }) {
  const live = mode === 'LIVE';
  return (
    <span className={clsx(
      'px-2 py-0.5 rounded border text-[10px] font-bold uppercase tracking-wide',
      live
        ? 'border-green-500/40 bg-green-500/5 text-green-400'
        : 'border-amber-500/40 bg-amber-500/5 text-amber-400'
    )}>
      {mode}
    </span>
  );
}

function ChainRow({ item }: { item: RelayerChainStatus | RelayerVmStatus }) {
  const label = 'chain' in item ? item.chain : item.vm;
  const live = item.live;
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-border/40 last:border-0">
      <div className="flex items-center gap-2">
        {live
          ? <CheckCircle size={11} className="text-green-400 flex-shrink-0" />
          : <XCircle size={11} className="text-t3 flex-shrink-0" />}
        <span className={clsx('text-[11px] mono', live ? 'text-t1' : 'text-t3')}>{label}</span>
      </div>
      <span className={clsx('text-[10px] font-semibold', live ? 'text-green-400' : 'text-t3')}>
        {live ? 'LIVE' : 'DRY'}
      </span>
    </div>
  );
}

function RelayerCard({
  title, mode, sub, children, liveCount, totalCount,
}: {
  title: string; mode: string; sub: string; children: React.ReactNode;
  liveCount?: number; totalCount?: number;
}) {
  return (
    <div className="card flex flex-col overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <Radio size={13} className={mode === 'LIVE' ? 'text-green-400' : 'text-amber-400'} />
          <span className="text-[12px] font-semibold text-t1">{title}</span>
          {liveCount !== undefined && totalCount !== undefined && (
            <span className="text-[10px] text-t3 ml-1">{liveCount}/{totalCount} active</span>
          )}
        </div>
        <ModeBadge mode={mode} />
      </div>
      <p className="px-4 py-2 text-[10px] text-t3 border-b border-border/50">{sub}</p>
      <div className="overflow-y-auto scrollable flex-1 px-4 py-2">
        {children}
      </div>
    </div>
  );
}

export default function RelayersPage() {
  const { data, isLoading, error } = useSWR<RelayersStatus>(
    endpoints.relayersStatus, fetchJSON, { refreshInterval: 15000 }
  );

  const loading = isLoading || !data;

  return (
    <>
      <Topbar title="Relayer Status" />
      <div className="flex-1 overflow-y-auto scrollable p-5 space-y-4">

        {/* Summary strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 flex-shrink-0">
          {[
            {
              label: 'TRION EVM',
              value: data?.trion_evm?.mode ?? '—',
              color: data?.trion_evm?.live ? 'text-green-400' : 'text-amber-400',
              sub: `${data?.trion_evm?.chains ?? 53} EVM chains`,
            },
            {
              label: '0G Gate',
              value: data?.zg_gate?.mode ?? '—',
              color: data?.zg_gate?.live ? 'text-green-400' : 'text-amber-400',
              sub: 'ExecutionGate',
            },
            {
              label: 'Extended Chains',
              value: `${data?.extended?.live_chains ?? 0}/${data?.extended?.total_chains ?? 36}`,
              color: (data?.extended?.live_chains ?? 0) > 0 ? 'text-green-400' : 'text-amber-400',
              sub: 'UTXO · Cosmos · Move · etc.',
            },
            {
              label: 'Native VMs',
              value: `${data?.native?.live_vms ?? 0}/${data?.native?.total_vms ?? 5}`,
              color: (data?.native?.live_vms ?? 0) > 0 ? 'text-green-400' : 'text-amber-400',
              sub: 'SVM · NEAR · TON · PVM · STK',
            },
          ].map(({ label, value, color, sub }) => (
            <div key={label} className="card p-3 text-center">
              <p className={clsx('text-xl font-bold mono', color)}>{loading ? '—' : value}</p>
              <p className="text-[10px] text-t3 uppercase tracking-wide mt-0.5">{label}</p>
              <p className="text-[9px] text-t3 mt-0.5">{sub}</p>
            </div>
          ))}
        </div>

        {error && (
          <div className="card p-4 border-red-500/20 bg-red-500/5">
            <p className="text-red-400 text-[12px]">Failed to load relayer status: {error.message}</p>
          </div>
        )}

        {loading && !error && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {[...Array(4)].map((_, i) => <div key={i} className="card h-64 animate-pulse bg-border" />)}
          </div>
        )}

        {data && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* TRION EVM Relayer */}
            <RelayerCard
              title="TRION EVM Relayer"
              mode={data.trion_evm.mode}
              sub={data.trion_evm.description}
            >
              <div className="py-2 space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-[11px] text-t2">Signing key</span>
                  <span className={clsx('text-[11px] font-semibold', data.trion_evm.live ? 'text-green-400' : 'text-amber-400')}>
                    {data.trion_evm.live ? 'SET' : 'NOT SET'}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[11px] text-t2">Target chains</span>
                  <span className="text-[11px] mono text-cyan">{data.trion_evm.chains}</span>
                </div>
                <div className="mt-3 p-3 rounded bg-card2 border border-border">
                  <p className="text-[10px] text-t3 mb-1">Publishing to</p>
                  <p className="text-[10px] text-t2 leading-relaxed">
                    ETH · ARB · BASE · OP · BNB · POLYGON · MANTLE · LINEA · SCROLL · ZKSYNC · BERACHAIN · SONIC · XLAYER · BLAST · MANTA · MODE · TAIKO · FRAXTAL · METIS · CELO · GNOSIS · MOONBEAM · KAIA · CORE · BITLAYER · BOB · ROOTSTOCK · CRONOS · AURORA · IOTEX · CONFLUX · MONAD · FILECOIN · HYPERLIQUID · ABSTRACT · ZORA + testnets
                  </p>
                </div>
              </div>
            </RelayerCard>

            {/* 0G Gate Relayer */}
            <RelayerCard
              title="0G ExecutionGate Relayer"
              mode={data.zg_gate.mode}
              sub={data.zg_gate.description}
            >
              <div className="py-2 space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-[11px] text-t2">Signing key</span>
                  <span className={clsx('text-[11px] font-semibold', data.zg_gate.live ? 'text-green-400' : 'text-amber-400')}>
                    {data.zg_gate.live ? 'SET' : 'NOT SET'}
                  </span>
                </div>
                <div className="mt-3 p-3 rounded bg-card2 border border-border">
                  <p className="text-[10px] text-t3 mb-1">Gate contract</p>
                  <p className="mono text-[10px] text-cyan break-all">0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b</p>
                  <p className="text-[10px] text-t3 mt-1">0G Mainnet · Chain 16661</p>
                </div>
              </div>
            </RelayerCard>

            {/* Extended Chain Relayer */}
            <RelayerCard
              title="Extended Chain Relayer"
              mode={data.extended.mode}
              sub="38 non-EVM chains: UTXO · Cosmos · Move · SUI · TRON · and more"
              liveCount={data.extended.live_chains}
              totalCount={data.extended.total_chains}
            >
              <div className="grid grid-cols-2 gap-x-4">
                <div>
                  <p className="text-[9px] text-t3 uppercase tracking-wide mb-1 mt-2">UTXO</p>
                  {data.extended.utxo.map(c => <ChainRow key={c.chain} item={c} />)}
                  <p className="text-[9px] text-t3 uppercase tracking-wide mb-1 mt-3">Move / SUI</p>
                  {data.extended.move_sui.map(c => <ChainRow key={c.chain} item={c} />)}
                </div>
                <div>
                  <p className="text-[9px] text-t3 uppercase tracking-wide mb-1 mt-2">Cosmos</p>
                  {data.extended.cosmos.map(c => <ChainRow key={c.chain} item={c} />)}
                </div>
              </div>
              {data.extended.other.length > 0 && (
                <div className="mt-3">
                  <p className="text-[9px] text-t3 uppercase tracking-wide mb-1">Other</p>
                  <div className="grid grid-cols-2 gap-x-4">
                    {data.extended.other.map(c => <ChainRow key={c.chain} item={c} />)}
                  </div>
                </div>
              )}
            </RelayerCard>

            {/* Native VM Relayer */}
            <RelayerCard
              title="Native VM Relayer"
              mode={data.native.mode}
              sub="SVM · NEAR · TON · Polkadot · StarkNet — real signed transactions per cycle"
              liveCount={data.native.live_vms}
              totalCount={data.native.total_vms}
            >
              <div className="py-1">
                {data.native.vms.map(v => <ChainRow key={v.vm} item={v} />)}
              </div>
              <div className="mt-3 p-3 rounded bg-card2 border border-border">
                <p className="text-[10px] text-t3">Cycle interval: 10 min · Per-VM stagger: 30s</p>
              </div>
            </RelayerCard>
          </div>
        )}
      </div>
    </>
  );
}
