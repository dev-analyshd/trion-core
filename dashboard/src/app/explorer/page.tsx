'use client';

import { useState, useMemo, useRef } from 'react';
import useSWR from 'swr';
import { fetchJSON } from '@/lib/api';
import {
  Search, Grid3X3, List, ChevronDown, ExternalLink,
  Activity, Shield, Cpu, Database, Zap, Circle
} from 'lucide-react';
import clsx from 'clsx';

// ── Types ─────────────────────────────────────────────────────────────────────
interface ExplorerChain {
  id: string;
  name: string;
  vm: string;
  chain_id: number;
  status: 'live' | 'testnet' | 'indexed';
  color: string;
  indexer: string;
  note?: string;
  bh_proofs: number;
  faiss_vectors: number;
  last_block: number;
  last_indexed_ts: number;
}

interface ExplorerData {
  chains: ExplorerChain[];
  total: number;
  live: number;
  total_bh_proofs: number;
  vm_families: number;
  timestamp: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmt(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(0) + 'K';
  return n.toString();
}

function fmtBlock(n: number): string {
  if (n === 0) return '—';
  if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(2) + 'B';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(0) + 'K';
  return n.toString();
}

function timeAgo(ts: number): string {
  const diff = Math.floor(Date.now() / 1000) - ts;
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

// ── Chain color avatar ────────────────────────────────────────────────────────
function ChainAvatar({ name, color, size = 36 }: { name: string; color: string; size?: number }) {
  const initials = name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase().slice(0, 2);
  // Lighten very dark colors by adding opacity to background
  const isDark = color === '#000000' || color === '#121212' || color === '#3C3C3C' || color === '#333333';
  const bg = isDark ? '#374151' : color;
  return (
    <div
      className="rounded-xl flex items-center justify-center flex-shrink-0 font-bold text-white shadow-sm"
      style={{ width: size, height: size, background: bg, fontSize: size * 0.31 }}
    >
      {initials}
    </div>
  );
}

// ── Status badge ──────────────────────────────────────────────────────────────
const STATUS_CFG = {
  live:    { label: 'Live',    bg: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  testnet: { label: 'Testnet', bg: 'bg-amber-50 text-amber-700 border-amber-200' },
  indexed: { label: 'Indexed', bg: 'bg-blue-50 text-blue-600 border-blue-200' },
};

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CFG[status as keyof typeof STATUS_CFG] ?? STATUS_CFG.indexed;
  return (
    <span className={clsx('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border', cfg.bg)}>
      <Circle size={5} className="fill-current" />
      {cfg.label}
    </span>
  );
}

// ── VM badge ─────────────────────────────────────────────────────────────────
const VM_COLORS: Record<string, string> = {
  'EVM':        'bg-violet-50 text-violet-700 border-violet-200',
  'SVM':        'bg-indigo-50 text-indigo-700 border-indigo-200',
  'UTXO':       'bg-orange-50 text-orange-700 border-orange-200',
  'eUTXO':      'bg-amber-50 text-amber-700 border-amber-200',
  'Cosmos SDK': 'bg-blue-50 text-blue-700 border-blue-200',
  'Move VM':    'bg-teal-50 text-teal-700 border-teal-200',
  'Sui VM':     'bg-cyan-50 text-cyan-700 border-cyan-200',
  'Cairo VM':   'bg-yellow-50 text-yellow-700 border-yellow-200',
  'TVM':        'bg-sky-50 text-sky-700 border-sky-200',
  'PVM':        'bg-pink-50 text-pink-700 border-pink-200',
  'NEAR VM':    'bg-green-50 text-green-700 border-green-200',
  'Stellar':    'bg-purple-50 text-purple-700 border-purple-200',
  'XRP Ledger': 'bg-slate-50 text-slate-700 border-slate-200',
  'AVM':        'bg-stone-50 text-stone-700 border-stone-200',
  'HBAR VM':    'bg-zinc-50 text-zinc-700 border-zinc-200',
  'VET VM':     'bg-sky-50 text-sky-700 border-sky-200',
  'Chainweb':   'bg-rose-50 text-rose-700 border-rose-200',
  'Wasm':       'bg-violet-50 text-violet-700 border-violet-200',
  'LLVM':       'bg-teal-50 text-teal-700 border-teal-200',
  'Cadence VM': 'bg-emerald-50 text-emerald-700 border-emerald-200',
};

function VMBadge({ vm }: { vm: string }) {
  return (
    <span className={clsx('inline-block px-1.5 py-0.5 rounded text-[9px] font-semibold border uppercase tracking-wide',
      VM_COLORS[vm] ?? 'bg-gray-50 text-gray-600 border-gray-200')}>
      {vm}
    </span>
  );
}

// ── Chain card (grid view) ────────────────────────────────────────────────────
function ChainCard({ chain }: { chain: ExplorerChain }) {
  return (
    <div className="bg-white border border-[#E8EAF0] rounded-2xl p-4 hover:border-[#C5BFFF] hover:shadow-md transition-all duration-150 group cursor-pointer">
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-center gap-2.5">
          <ChainAvatar name={chain.name} color={chain.color} size={36} />
          <div>
            <p className="text-sm font-semibold text-[#0A0B14] leading-tight group-hover:text-[#5B48DC] transition-colors">
              {chain.name}
            </p>
            <p className="text-[10px] text-[#9CA3AF] font-mono mt-0.5">
              {chain.chain_id > 0 ? `Chain ${chain.chain_id}` : chain.vm}
            </p>
          </div>
        </div>
        <StatusBadge status={chain.status} />
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-2 py-3 border-t border-[#F3F4F6]">
        <div>
          <p className="text-[9px] uppercase tracking-wider text-[#9CA3AF] font-medium mb-0.5">BH Proofs</p>
          <p className="text-sm font-bold text-[#111827]">{fmt(chain.bh_proofs)}</p>
        </div>
        <div>
          <p className="text-[9px] uppercase tracking-wider text-[#9CA3AF] font-medium mb-0.5">FAISS Vectors</p>
          <p className="text-sm font-bold text-[#111827]">{fmt(chain.faiss_vectors)}</p>
        </div>
        <div>
          <p className="text-[9px] uppercase tracking-wider text-[#9CA3AF] font-medium mb-0.5">Last Block</p>
          <p className="text-sm font-mono text-[#374151]">{fmtBlock(chain.last_block)}</p>
        </div>
        <div>
          <p className="text-[9px] uppercase tracking-wider text-[#9CA3AF] font-medium mb-0.5">Updated</p>
          <p className="text-sm text-[#374151]">{timeAgo(chain.last_indexed_ts)}</p>
        </div>
      </div>

      <div className="flex items-center justify-between mt-1">
        <VMBadge vm={chain.vm} />
        <span className="text-[9px] text-[#9CA3AF] font-mono">{chain.indexer}</span>
      </div>
    </div>
  );
}

// ── Chain row (list view) ─────────────────────────────────────────────────────
function ChainRow({ chain, idx }: { chain: ExplorerChain; idx: number }) {
  return (
    <tr className="border-b border-[#F3F4F6] hover:bg-[#FAFBFF] transition-colors group cursor-pointer">
      <td className="py-3 pl-4 pr-2 text-[11px] text-[#9CA3AF] font-mono w-10">{idx + 1}</td>
      <td className="py-3 pr-4">
        <div className="flex items-center gap-2.5">
          <ChainAvatar name={chain.name} color={chain.color} size={28} />
          <div>
            <p className="text-[13px] font-semibold text-[#0A0B14] group-hover:text-[#5B48DC] transition-colors">{chain.name}</p>
            <p className="text-[10px] text-[#9CA3AF] font-mono">
              {chain.chain_id > 0 ? `Chain ${chain.chain_id}` : chain.id}
            </p>
          </div>
        </div>
      </td>
      <td className="py-3 pr-4"><VMBadge vm={chain.vm} /></td>
      <td className="py-3 pr-4 text-[12px] font-semibold text-[#111827]">{fmt(chain.bh_proofs)}</td>
      <td className="py-3 pr-4 text-[12px] text-[#374151]">{fmt(chain.faiss_vectors)}</td>
      <td className="py-3 pr-4 text-[12px] font-mono text-[#374151]">{fmtBlock(chain.last_block)}</td>
      <td className="py-3 pr-4 text-[11px] text-[#6B7280]">{timeAgo(chain.last_indexed_ts)}</td>
      <td className="py-3 pr-4"><StatusBadge status={chain.status} /></td>
      <td className="py-3 pr-4 text-[10px] text-[#9CA3AF] font-mono">{chain.indexer}</td>
    </tr>
  );
}

// ── Search suggestions ────────────────────────────────────────────────────────
const SUGGESTIONS = ['Entity', 'BH Hash', 'Proof ID', 'Block', 'Chain', 'Address'];

// ── VM filter tabs ────────────────────────────────────────────────────────────
const VM_FAMILIES = ['All', 'EVM', 'UTXO', 'Cosmos SDK', 'SVM', 'Move VM', 'TVM', 'Wasm', 'Other'];

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ExplorerPage() {
  const [query, setQuery] = useState('');
  const [vmFilter, setVmFilter] = useState('All');
  const [statusFilter, setStatusFilter] = useState('All');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [sortBy, setSortBy] = useState<'name' | 'bh_proofs' | 'faiss_vectors'>('bh_proofs');
  const inputRef = useRef<HTMLInputElement>(null);

  const { data, isLoading } = useSWR<ExplorerData>(
    '/api/v1/explorer/chains',
    fetchJSON,
    { refreshInterval: 30_000 }
  );

  const chains = useMemo(() => {
    if (!data?.chains) return [];
    return data.chains
      .filter(c => {
        const matchQuery = !query ||
          c.name.toLowerCase().includes(query.toLowerCase()) ||
          c.vm.toLowerCase().includes(query.toLowerCase()) ||
          String(c.chain_id).includes(query) ||
          c.id.toLowerCase().includes(query.toLowerCase());
        const matchVm = vmFilter === 'All'
          ? true
          : vmFilter === 'Other'
            ? !['EVM','UTXO','Cosmos SDK','SVM','Move VM','TVM','Wasm'].includes(c.vm)
            : c.vm === vmFilter;
        const matchStatus = statusFilter === 'All' || c.status === statusFilter;
        return matchQuery && matchVm && matchStatus;
      })
      .sort((a, b) => {
        if (sortBy === 'name') return a.name.localeCompare(b.name);
        return b[sortBy] - a[sortBy];
      });
  }, [data, query, vmFilter, statusFilter, sortBy]);

  const live = data?.live ?? 0;
  const total = data?.total ?? 0;
  const totalBH = data?.total_bh_proofs ?? 0;
  const vmFamilies = data?.vm_families ?? 0;

  return (
    <div className="flex-1 overflow-auto" style={{ background: '#F7F8FB', color: '#0A0B14' }}>
      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <div className="pt-14 pb-10 px-8" style={{ background: 'linear-gradient(180deg, #EDEDFF 0%, #F7F8FB 100%)' }}>
        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-[42px] font-bold tracking-tight leading-tight mb-3" style={{ color: '#0A0B14' }}>
            Multichain BH Explorer
          </h1>
          <p className="text-[22px] font-semibold mb-8" style={{ color: '#5B48DC' }}>
            Expand your behavioral intelligence
          </p>

          {/* CTA buttons */}
          <div className="flex items-center justify-center gap-3 mb-8">
            <button
              className="px-6 py-2.5 rounded-full text-sm font-semibold text-white transition-all"
              style={{ background: '#5B48DC' }}
              onClick={() => inputRef.current?.focus()}
            >
              Search on chain
            </button>
            <button className="px-6 py-2.5 rounded-full text-sm font-semibold border transition-all"
              style={{ borderColor: '#D1D5DB', color: '#374151', background: 'white' }}>
              Explore entities
            </button>
            <button className="flex items-center gap-1.5 px-5 py-2.5 rounded-full text-sm font-medium border transition-all"
              style={{ borderColor: '#C5BFFF', color: '#5B48DC', background: '#F5F3FF' }}>
              <Zap size={14} />
              ANIMA mode
            </button>
          </div>

          {/* Search bar */}
          <div className="relative max-w-2xl mx-auto">
            <Search
              size={18}
              className="absolute left-4 top-1/2 -translate-y-1/2"
              style={{ color: '#9CA3AF' }}
            />
            <input
              ref={inputRef}
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search by entity address / BH hash / chain / proof ID…"
              className="w-full pl-11 pr-5 py-4 rounded-2xl border-2 outline-none text-sm transition-all"
              style={{
                borderColor: query ? '#5B48DC' : '#E5E7EB',
                background: 'white',
                color: '#0A0B14',
                boxShadow: '0 2px 12px rgba(0,0,0,0.06)',
              }}
            />
          </div>

          {/* Suggestion chips */}
          <div className="flex items-center justify-center gap-2 mt-3 flex-wrap">
            <span className="text-xs" style={{ color: '#9CA3AF' }}>Try searching by:</span>
            {SUGGESTIONS.map(s => (
              <button
                key={s}
                onClick={() => setQuery('')}
                className="px-3 py-1 rounded-full text-xs border transition-all"
                style={{ borderColor: '#E5E7EB', color: '#6B7280', background: 'white' }}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Stats strip ───────────────────────────────────────────────────── */}
      <div className="max-w-7xl mx-auto px-8 -mt-6">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { icon: Activity,  label: 'Total Chains',    value: isLoading ? '…' : String(total),            sub: `${live} live` },
            { icon: Shield,    label: 'BH Proofs',       value: isLoading ? '…' : fmt(totalBH),             sub: 'across all chains' },
            { icon: Cpu,       label: 'VM Families',     value: isLoading ? '…' : String(vmFamilies),        sub: 'execution environments' },
            { icon: Database,  label: 'Indexers Active', value: '13',                                        sub: 'Rust + native relayers' },
          ].map(({ icon: Icon, label, value, sub }) => (
            <div key={label} className="bg-white border border-[#E8EAF0] rounded-2xl p-5 shadow-sm">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: '#F0EEFF' }}>
                  <Icon size={15} style={{ color: '#5B48DC' }} />
                </div>
                <span className="text-[11px] uppercase tracking-wider font-semibold" style={{ color: '#9CA3AF' }}>{label}</span>
              </div>
              <p className="text-3xl font-bold" style={{ color: '#0A0B14' }}>{value}</p>
              <p className="text-xs mt-1" style={{ color: '#9CA3AF' }}>{sub}</p>
            </div>
          ))}
        </div>
      </div>

      {/* ── Chain grid section ────────────────────────────────────────────── */}
      <div className="max-w-7xl mx-auto px-8 mt-8 pb-16">
        {/* Toolbar */}
        <div className="flex items-center justify-between gap-4 mb-5 flex-wrap">
          {/* VM family filter tabs */}
          <div className="flex items-center gap-1 flex-wrap">
            {VM_FAMILIES.map(f => (
              <button
                key={f}
                onClick={() => setVmFilter(f)}
                className="px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all border"
                style={vmFilter === f
                  ? { background: '#5B48DC', color: 'white', borderColor: '#5B48DC' }
                  : { background: 'white', color: '#6B7280', borderColor: '#E5E7EB' }
                }
              >
                {f}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            {/* Status filter */}
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
              className="text-xs border rounded-lg px-3 py-1.5 outline-none"
              style={{ borderColor: '#E5E7EB', background: 'white', color: '#374151' }}
            >
              <option value="All">All Status</option>
              <option value="live">Live</option>
              <option value="testnet">Testnet</option>
              <option value="indexed">Indexed</option>
            </select>

            {/* Sort */}
            <select
              value={sortBy}
              onChange={e => setSortBy(e.target.value as typeof sortBy)}
              className="text-xs border rounded-lg px-3 py-1.5 outline-none"
              style={{ borderColor: '#E5E7EB', background: 'white', color: '#374151' }}
            >
              <option value="bh_proofs">Sort: BH Proofs</option>
              <option value="faiss_vectors">Sort: FAISS Vectors</option>
              <option value="name">Sort: Name</option>
            </select>

            {/* View toggle */}
            <div className="flex items-center border rounded-lg overflow-hidden" style={{ borderColor: '#E5E7EB' }}>
              <button
                onClick={() => setViewMode('grid')}
                className="p-1.5 transition-colors"
                style={{ background: viewMode === 'grid' ? '#5B48DC' : 'white', color: viewMode === 'grid' ? 'white' : '#6B7280' }}
              >
                <Grid3X3 size={14} />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className="p-1.5 transition-colors"
                style={{ background: viewMode === 'list' ? '#5B48DC' : 'white', color: viewMode === 'list' ? 'white' : '#6B7280' }}
              >
                <List size={14} />
              </button>
            </div>

            <span className="text-xs" style={{ color: '#9CA3AF' }}>
              {chains.length} chain{chains.length !== 1 ? 's' : ''}
            </span>
          </div>
        </div>

        {/* Loading skeleton */}
        {isLoading && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {[...Array(20)].map((_, i) => (
              <div key={i} className="bg-white border border-[#E8EAF0] rounded-2xl p-4 h-48 animate-pulse">
                <div className="flex items-center gap-2.5 mb-3">
                  <div className="w-9 h-9 rounded-xl bg-gray-100" />
                  <div className="space-y-1.5">
                    <div className="h-3 w-20 bg-gray-100 rounded" />
                    <div className="h-2.5 w-14 bg-gray-100 rounded" />
                  </div>
                </div>
                <div className="space-y-2 pt-3 border-t border-gray-50">
                  {[...Array(4)].map((_, j) => <div key={j} className="h-2.5 bg-gray-100 rounded" />)}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Grid view */}
        {!isLoading && viewMode === 'grid' && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {chains.map(chain => (
              <ChainCard key={chain.id} chain={chain} />
            ))}
          </div>
        )}

        {/* List view */}
        {!isLoading && viewMode === 'list' && (
          <div className="bg-white border border-[#E8EAF0] rounded-2xl overflow-hidden shadow-sm">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[#F3F4F6]" style={{ background: '#FAFBFF' }}>
                  {['#', 'Chain', 'VM', 'BH Proofs', 'FAISS Vectors', 'Last Block', 'Updated', 'Status', 'Indexer'].map(h => (
                    <th key={h} className="py-3 pl-4 pr-2 text-left text-[10px] uppercase tracking-wider font-semibold"
                      style={{ color: '#9CA3AF' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {chains.map((chain, idx) => (
                  <ChainRow key={chain.id} chain={chain} idx={idx} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && chains.length === 0 && (
          <div className="text-center py-20">
            <Search size={40} className="mx-auto mb-4" style={{ color: '#D1D5DB' }} />
            <p className="text-lg font-semibold mb-1" style={{ color: '#374151' }}>No chains found</p>
            <p className="text-sm" style={{ color: '#9CA3AF' }}>
              Try a different search term or filter
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
