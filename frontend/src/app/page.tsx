'use client';

import { useState, useEffect, useCallback } from 'react';
import { Moon, Sun, Monitor, Menu, Activity, Database, Shield, Zap, Globe, TrendingUp, ExternalLink, Server, Cpu, Lock, Network, Layers, DollarSign, Bot, Clock, AlertTriangle, CheckCircle, XCircle } from 'lucide-react';

// ════════════════════════════════════════════════════════════════════════════
// HELPERS
// ════════════════════════════════════════════════════════════════════════════
const API_BASE = typeof window !== 'undefined' ? window.location.origin : '';

async function fetchAPI(path: string): Promise<any | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, { signal: AbortSignal.timeout(10000) });
    if (!res.ok) return null;
    return await res.json();
  } catch { return null; }
}

const fmt = (n: any, d = 0) => n === null || n === undefined ? '—' : Number(n).toLocaleString('en-US', { maximumFractionDigits: d });
const pct = (n: any, d = 1) => n === null || n === undefined ? '—' : (Number(n) * 100).toFixed(d) + '%';
const tfmt = (ts: any) => ts ? new Date(Number(ts) * 1000).toLocaleTimeString('en-US', { hour12: false }) : '—';
const truncate = (s: string, len = 16) => s && s.length > len ? s.slice(0, len) + '…' : (s || '—');

// ════════════════════════════════════════════════════════════════════════════
// NAV
// ════════════════════════════════════════════════════════════════════════════
const NAV = [
  { label: 'Overview', items: [
    { id: 'dashboard', label: 'Dashboard', icon: Activity },
    { id: 'chains', label: 'Chain Coverage', icon: Globe },
    { id: 'architecture', label: 'Architecture', icon: Cpu },
    { id: 'timescale', label: 'TimescaleDB', icon: Database },
  ]},
  { label: 'Behavioral Engine', items: [
    { id: 'akashic', label: 'Akashic Index', icon: Database },
    { id: 'bh', label: 'BH Explorer', icon: Zap },
    { id: 'anima', label: 'ANIMA Intelligence', icon: TrendingUp },
    { id: 'beo', label: 'BEO Resolution', icon: Shield },
    { id: 'signals', label: 'Signals', icon: Activity },
  ]},
  { label: 'Security & Consensus', items: [
    { id: 'security', label: 'Living Security', icon: Lock },
    { id: 'validators', label: 'Validators', icon: Network },
    { id: 'annotators', label: 'Annotators', icon: Activity },
    { id: 'evolutionary', label: 'Evolutionary Fitness', icon: TrendingUp },
    { id: 'governance', label: 'Governance', icon: Shield },
  ]},
  { label: 'Markets', items: [
    { id: 'continuum', label: 'Continuum DEX', icon: Globe },
    { id: 'btcp', label: 'BTCP Routing', icon: Zap },
    { id: 'marketplace', label: 'Data Marketplace', icon: DollarSign },
    { id: 'price', label: 'Price Feeds', icon: TrendingUp },
    { id: 'cex', label: 'CEX Integration', icon: Network },
  ]},
  { label: 'Infrastructure', items: [
    { id: 'agent', label: 'AI Agent ID', icon: Bot },
    { id: 'protocol', label: 'Protocol Health', icon: Server },
    { id: 'zero_g', label: '0G Integration', icon: Layers },
    { id: 'settings', label: 'Settings', icon: Shield },
  ]},
];

// ════════════════════════════════════════════════════════════════════════════
// SHARED COMPONENTS
// ════════════════════════════════════════════════════════════════════════════
function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-card rounded-2xl p-5 border border-border shadow-sm hover:shadow-md transition-shadow">
      <div className="text-xl font-bold mb-2">{value}</div>
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">{label}</span>
        {sub && <span className="text-xs font-semibold">{sub}</span>}
      </div>
    </div>
  );
}

function Card({ title, children, live }: { title: string; children: React.ReactNode; live?: boolean }) {
  return (
    <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
      <div className="flex items-center justify-between p-5 border-b border-border">
        <span className="font-semibold">{title}</span>
        {live && <span className="flex items-center gap-1.5 text-xs text-green-500 font-medium"><span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />Live</span>}
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function DataTable({ headers, rows }: { headers: string[]; rows: (string | React.ReactNode)[][] }) {
  return (
    <div className="max-h-80 overflow-y-auto">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 sticky top-0">
          <tr>{headers.map((h, i) => <th key={i} className="text-left p-3 text-xs font-semibold text-muted-foreground">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length === 0 ? <tr><td colSpan={headers.length} className="p-8 text-center text-muted-foreground">Loading…</td></tr> :
            rows.map((row, i) => (
              <tr key={i} className="border-b border-border/50 hover:bg-muted/30">
                {row.map((cell, j) => <td key={j} className="p-3">{cell}</td>)}
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}

function Badge({ status }: { status: string }) {
  const s = status?.toUpperCase() || 'UNKNOWN';
  const cls = ['LIVE','HEALTHY','SAFE','OPERATIONAL','SUCCESS','COMPLETED'].includes(s) ? 'bg-green-500/10 text-green-600' :
              ['WARN','WARNING','ELEVATED','CAUTION','PENDING'].includes(s) ? 'bg-yellow-500/10 text-yellow-600' :
              ['ERROR','CRITICAL','HOSTILE','OFFLINE','BLOCKED','FAILED'].includes(s) ? 'bg-red-500/10 text-red-600' :
              'bg-blue-500/10 text-blue-600';
  return <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>{status}</span>;
}

function ProgressBar({ value, label }: { value: number; label?: string }) {
  return (
    <div>
      {label && <div className="flex justify-between text-xs mb-1"><span className="text-muted-foreground">{label}</span><span className="font-semibold">{Math.round(value * 100)}%</span></div>}
      <div className="h-1.5 bg-muted rounded-full overflow-hidden"><div className="h-full bg-primary rounded-full transition-all" style={{ width: `${value * 100}%` }} /></div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// THEME TOGGLE
// ════════════════════════════════════════════════════════════════════════════
function ThemeToggle() {
  const [theme, setTheme] = useState<'light'|'dark'|'system'>('system');
  const [open, setOpen] = useState(false);
  useEffect(() => { const s = localStorage.getItem('trion-theme') as any; if (s) setTheme(s); }, []);
  useEffect(() => {
    localStorage.setItem('trion-theme', theme);
    const root = document.documentElement;
    root.classList.toggle('dark', theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches));
  }, [theme]);
  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border hover:bg-accent transition-colors">
        {theme === 'dark' ? <Moon className="w-4 h-4" /> : theme === 'light' ? <Sun className="w-4 h-4" /> : <Monitor className="w-4 h-4" />}
        <span className="text-sm capitalize hidden sm:inline">{theme}</span>
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-36 rounded-lg border border-border bg-popover shadow-lg z-50">
          {(['light','dark','system'] as const).map(t => (
            <button key={t} onClick={() => { setTheme(t); setOpen(false); }} className={`flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-accent ${theme === t ? 'text-primary font-medium' : 'text-muted-foreground'}`}>
              {t === 'dark' ? <Moon className="w-4 h-4" /> : t === 'light' ? <Sun className="w-4 h-4" /> : <Monitor className="w-4 h-4" />}<span className="capitalize">{t}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// SIDEBAR
// ════════════════════════════════════════════════════════════════════════════
function Sidebar({ activePage, onPageChange, isOpen, onClose }: any) {
  return (
    <>
      {isOpen && <div className="fixed inset-0 bg-black/40 z-40 lg:hidden" onClick={onClose} />}
      <aside className={`fixed lg:static inset-y-0 left-0 z-50 w-[260px] flex-shrink-0 bg-card border-r border-border flex flex-col transition-transform duration-300 ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}>
        <div className="flex items-center gap-3 p-5 border-b border-border">
          <img src="/trion_logo.png" alt="TRION" className="w-9 h-9 rounded-lg" />
          <div><div className="font-bold text-base">TRION</div><div className="text-xs text-muted-foreground">Behavioral Truth Oracle</div></div>
        </div>
        <nav className="flex-1 overflow-y-auto p-3 space-y-4">
          {NAV.map((group) => (
            <div key={group.label}>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 px-3 mb-2">{group.label}</div>
              <div className="space-y-1">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const isActive = activePage === item.id;
                  return (
                    <button key={item.id} onClick={() => { onPageChange(item.id); onClose(); }} className={`flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm font-medium transition-all ${isActive ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent hover:text-foreground'}`}>
                      <Icon className="w-4 h-4 flex-shrink-0" /><span className="truncate">{item.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
        <div className="p-3 border-t border-border">
          <a href={`${API_BASE}/api/v1/health`} target="_blank" rel="noopener" className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-muted-foreground hover:bg-accent"><ExternalLink className="w-4 h-4" /> API Health</a>
        </div>
      </aside>
    </>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// RIGHT PANEL
// ════════════════════════════════════════════════════════════════════════════
function RightPanel({ moat, sec, coverage }: any) {
  const secScore = sec?.sec_score || 0;
  const circ = 2 * Math.PI * 52;
  const offset = circ - secScore * circ;
  return (
    <aside className="hidden xl:flex w-[280px] flex-shrink-0 flex-col gap-6 p-6 bg-gradient-to-b from-primary to-primary/90 text-primary-foreground relative overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(255,255,255,0.07),transparent_60%)] pointer-events-none" />
      <div className="text-center relative z-10"><div className="text-[11px] font-bold uppercase tracking-wider opacity-80 mb-1">Protocol Moat</div><div className="text-3xl font-bold text-cyan-300">{moat ? moat.M_moat.toFixed(4) : '—'}</div></div>
      <div className="flex flex-col items-center relative z-10">
        <div className="text-xs font-semibold text-white/80 mb-3">Security Score</div>
        <div className="relative w-32 h-32">
          <svg className="w-full h-full -rotate-90" viewBox="0 0 120 120"><circle cx="60" cy="60" r="52" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="8" /><circle cx="60" cy="60" r="52" fill="none" stroke="#22D3EE" strokeWidth="8" strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={offset} style={{ filter: 'drop-shadow(0 0 8px rgba(34,211,238,0.5))' }} /></svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center"><span className="text-2xl font-bold text-white">{Math.round(secScore * 100)}%</span><span className="text-xs text-white/70">{secScore >= 0.9 ? 'Quantum Resistant' : 'Active'}</span></div>
        </div>
      </div>
      <div className="space-y-4 relative z-10">
        <ProgressBar value={coverage / 100} label="Formula Coverage" />
        {moat?.components && Object.entries(moat.components).slice(0, 3).map(([key, val]: any) => <ProgressBar key={key} value={val} label={key.replace(/_/g, ' ')} />)}
      </div>
      <div className="mt-auto bg-white/10 backdrop-blur rounded-2xl p-4 relative z-10">
        <div className="flex justify-between items-center mb-2"><span className="text-[11px] font-bold opacity-90">Akashic Depth</span><Database className="w-3.5 h-3.5 opacity-70" /></div>
        <div className="text-lg font-bold text-cyan-300">{moat ? fmt(moat.akashic_depth, 0) : '—'}</div>
        <div className="text-[11px] opacity-70">{moat ? `${moat.chains_indexed} chains indexed` : ''}</div>
      </div>
    </aside>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: Dashboard
// ════════════════════════════════════════════════════════════════════════════
function DashboardPage({ data }: { data: any }) {
  const { health, overview, lb = [], feed = [], bh = [], moat, sec, coverage = 0, bhStats } = data;
  const totalBH = bhStats?.total_records || 0;
  const totalChains = overview?.chains?.chains?.length || 0;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Chains Active" value={fmt(totalChains)} sub="14 VM families" />
        <StatCard label="BH Records" value={fmt(totalBH)} sub="Append-only" />
        <StatCard label="Market Volatility" value={pct(health?.market_volatility, 1)} sub="Dynamic" />
        <StatCard label="Formula Coverage" value={`${coverage}%`} sub="84/84" />
      </div>
      <Card title="Network Status" live>
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div><div className="text-2xl font-bold">{health?.status === 'healthy' ? 'Operational' : 'Degraded'}</div><div className="text-xs text-muted-foreground mt-1">Threshold: {pct(health?.dynamic_threshold, 1)}</div></div>
          <div className="flex gap-6"><div><div className="text-xs text-muted-foreground">Signals On-Chain</div><div className="text-lg font-bold">{fmt(health?.total_signals_onchain)}</div></div><div><div className="text-xs text-muted-foreground">Chains Live</div><div className="text-lg font-bold text-primary">{overview?.chains?.live || 0}</div></div></div>
        </div>
        <div className="mt-4"><ProgressBar value={coverage / 100} /></div>
      </Card>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Top Coherent Entities" live>
          <DataTable headers={['#','Entity','Coherence','Archetype']} rows={lb.slice(0, 8).map((e: any) => [e.rank, truncate(e.label || e.entity_id, 20), pct(e.coherence_score, 1), <Badge status={e.archetype} />])} />
        </Card>
        <Card title="Live Signal Feed" live>
          <DataTable headers={['Time','Protocol','Score','Grade']} rows={feed.slice(0, 10).map((s: any) => [tfmt(s.timestamp), truncate(s.protocol_name || s.short_id, 16), pct(s.coherence_score, 1), <Badge status={s.grade} />])} />
        </Card>
      </div>
      <Card title="Behavioral Hash Stream" live>
        <DataTable headers={['Time','Entity','Chain','Event','Verdict']} rows={bh.slice(0, 15).map((b: any) => [tfmt(b.ts), truncate(b.entity_id, 14), <Badge status={b.chain} />, b.event_type, <Badge status={b.verdict} />])} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: Chains
// ════════════════════════════════════════════════════════════════════════════
function ChainsPage({ data }: { data: any }) {
  const chains = data.overview?.chains?.chains || [];
  const [search, setSearch] = useState('');
  const filtered = chains.filter((c: any) => c.name?.toLowerCase().includes(search.toLowerCase()) || c.vm?.toLowerCase().includes(search.toLowerCase()));
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Chains" value={fmt(chains.length)} />
        <StatCard label="Live" value={fmt(data.overview?.chains?.live || 0)} />
        <StatCard label="VM Families" value={fmt(data.overview?.chains?.vm_families || 0)} />
        <StatCard label="Total BH Proofs" value={fmt(data.overview?.chains?.total_bh_proofs || 0)} />
      </div>
      <Card title="All Chains" live>
        <input className="w-full max-w-sm mb-4 px-3 py-2 rounded-lg border border-border bg-input text-sm" placeholder="Search chains…" value={search} onChange={e => setSearch(e.target.value)} />
        <DataTable headers={['Chain','VM','Chain ID','Status','Indexer','BH Proofs','FAISS Vectors']} rows={filtered.map((c: any) => [c.name, c.vm, c.chain_id || '—', <Badge status={c.status} />, c.indexer, fmt(c.bh_proofs), fmt(c.faiss_vectors)])} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: TimescaleDB
// ════════════════════════════════════════════════════════════════════════════
function TimescalePage({ data }: { data: any }) {
  const [tsdb, setTsdb] = useState<any>(null);
  const [conservation, setConservation] = useState<any>(null);
  const [bhChains, setBhChains] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/tsdb/stats').then(setTsdb);
    fetchAPI('/api/v1/information/conservation').then(setConservation);
    fetchAPI('/api/v1/bh/chains').then(setBhChains);
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Records" value={fmt(tsdb?.total_records || data.bhStats?.total_records)} sub="bh_ledger" />
        <StatCard label="Chains with Data" value={fmt(data.bhStats?.chains_with_data)} />
        <StatCard label="Payload Size" value={`${data.bhStats?.payload_bytes || 93} bytes`} sub="canonical BH" />
        <StatCard label="Conservation" value={conservation?.has_violations === false ? 'OK' : 'Check'} sub="dI/dt >= 0" />
      </div>
      <Card title="Information Conservation (L9.2)" live>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div><div className="text-xs text-muted-foreground">I_TRION</div><div className="text-lg font-bold font-mono">{fmt(conservation?.i_total)}</div></div>
          <div><div className="text-xs text-muted-foreground">BH Generated</div><div className="text-lg font-bold font-mono">{fmt(conservation?.bh_generated)}</div></div>
          <div><div className="text-xs text-muted-foreground">Signals Emitted</div><div className="text-lg font-bold font-mono">{fmt(conservation?.s_emitted)}</div></div>
          <div><div className="text-xs text-muted-foreground">Violations</div><div className="text-lg font-bold font-mono">{conservation?.has_violations ? 'YES' : '0'}</div></div>
        </div>
      </Card>
      <Card title="Per-Chain BH Statistics" live>
        <DataTable headers={['Chain','Records','Last Block']} rows={Object.entries(data.bhStats?.per_chain || {}).map(([chain, count]: any) => [chain, fmt(count), '—'])} />
      </Card>
      {bhChains && <Card title="BH Chain Breakdown"><DataTable headers={['Chain Label','Chain ID','BH Count','Last Block']} rows={(bhChains.chains || bhChains || []).map((c: any) => [c.chain_label || c.label, c.chain_id, fmt(c.bh_count || c.count), fmt(c.last_block)])} /></Card>}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: Akashic Index
// ════════════════════════════════════════════════════════════════════════════
function AkashicPage({ data }: { data: any }) {
  const [archetypes, setArchetypes] = useState<any[]>([]);
  const [bootstrap, setBootstrap] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/akashic/archetypes').then(d => setArchetypes(d?.archetypes || []));
    fetchAPI('/api/v1/bootstrap/status').then(setBootstrap);
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Akashic Depth" value={fmt(data.moat?.akashic_depth, 0)} />
        <StatCard label="Archetypes" value={fmt(archetypes.length)} sub="K-means" />
        <StatCard label="Chains Indexed" value={fmt(data.moat?.chains_indexed)} />
        <StatCard label="Bootstrap Weight" value={pct(bootstrap?.bootstrap_weight || 0, 3)} />
      </div>
      <Card title="Behavioral Archetypes" live>
        <DataTable headers={['ID','Name','Risk','Investment Signal']} rows={archetypes.map((a: any) => [a.id || '—', a.name, <Badge status={a.risk_level || 'UNKNOWN'} />, a.investment_signal || '—'])} />
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: BH Explorer
// ════════════════════════════════════════════════════════════════════════════
function BHPage({ data }: { data: any }) {
  const [vmFeed, setVmFeed] = useState<any>(null);
  useEffect(() => { fetchAPI('/api/v1/bh/vm_feed').then(setVmFeed); }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total BHs" value={fmt(data.bhStats?.total_records)} />
        <StatCard label="Chains Active" value={fmt(data.bhStats?.chains_with_data)} />
        <StatCard label="Payload" value={`${data.bhStats?.payload_bytes || 93}B`} sub="canonical" />
        <StatCard label="Recent Feed" value={fmt(data.bh?.length)} sub="records" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Recent BH Feed" live><DataTable headers={['Time','Entity','Chain','Event','Verdict']} rows={(data.bh || []).slice(0, 20).map((b: any) => [tfmt(b.ts), truncate(b.entity_id), b.chain, b.event_type, <Badge status={b.verdict} />])} /></Card>
        <Card title="VM Family Feed" live><DataTable headers={['VM','Chain','Event','Magnitude']} rows={(vmFeed?.records || vmFeed || []).slice(0, 20).map((b: any) => [b.vm_type || b.chain?.split('_')[0], b.chain, b.event_type, b.magnitude?.toFixed(2) || '—'])} /></Card>
      </div>
      <Card title="Per-Event-Type Distribution"><DataTable headers={['Event Type','Count']} rows={Object.entries(data.bhStats?.per_event_type || {}).map(([k, v]: any) => [k, fmt(v)])} /></Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: ANIMA Intelligence
// ════════════════════════════════════════════════════════════════════════════
function AnimaPage() {
  const [im, setIm] = useState<any>(null);
  const [brt, setBrt] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/anima/intelligence').then(setIm);
    fetchAPI('/api/v1/brt').then(setBrt);
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="IM Status" value={im?.status || '—'} />
        <StatCard label="IM Score" value={pct(im?.im_score, 1)} />
        <StatCard label="Circadian" value={pct(brt?.circadian_phase, 3)} />
        <StatCard label="Seasonal" value={pct(brt?.seasonal_phase, 3)} />
      </div>
      <Card title="Intelligence Maintenance Protocol (L3.7)" live>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div><div className="text-xs text-muted-foreground">PA</div><div className="text-lg font-bold">{pct(im?.pa, 1)}</div></div>
          <div><div className="text-xs text-muted-foreground">CS</div><div className="text-lg font-bold">{pct(im?.cs, 1)}</div></div>
          <div><div className="text-xs text-muted-foreground">PCR</div><div className="text-lg font-bold">{pct(im?.pcr, 1)}</div></div>
          <div><div className="text-xs text-muted-foreground">CA</div><div className="text-lg font-bold">{pct(im?.ca, 1)}</div></div>
        </div>
      </Card>
      <Card title="Biological Rhythm Timer (L6.2)" live>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div><div className="text-xs text-muted-foreground">Circadian (24h)</div><div className="text-lg font-bold font-mono">{pct(brt?.circadian_phase, 3)}</div></div>
          <div><div className="text-xs text-muted-foreground">Ultradian (90m)</div><div className="text-lg font-bold font-mono">{pct(brt?.ultradian_phase, 3)}</div></div>
          <div><div className="text-xs text-muted-foreground">Lunar (29.5d)</div><div className="text-lg font-bold font-mono">{pct(brt?.lunar_phase, 3)}</div></div>
          <div><div className="text-xs text-muted-foreground">Seasonal (365d)</div><div className="text-lg font-bold font-mono">{pct(brt?.seasonal_phase, 3)}</div></div>
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: BEO Resolution
// ════════════════════════════════════════════════════════════════════════════
function BEOPage() {
  const [archetypes, setArchetypes] = useState<any[]>([]);
  const [auditPatterns, setAuditPatterns] = useState<any[]>([]);
  useEffect(() => {
    fetchAPI('/api/v1/akashic/archetypes').then(d => setArchetypes(d?.archetypes || []));
    fetchAPI('/api/v1/audit/patterns').then(d => setAuditPatterns(d?.patterns || d || []));
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Archetypes" value={fmt(archetypes.length)} />
        <StatCard label="Audit Patterns" value={fmt(auditPatterns.length)} />
        <StatCard label="Entity Resolution" value="Active" sub="BEO clustering" />
        <StatCard label="Common Funder" value="w=0.40" sub="strongest signal" />
      </div>
      <Card title="Behavioral Archetypes" live><DataTable headers={['Name','Risk','Investment Signal','Examples']} rows={archetypes.map((a: any) => [a.name, <Badge status={a.risk_level} />, a.investment_signal, truncate((a.examples || []).join(', '), 30)])} /></Card>
      {auditPatterns.length > 0 && <Card title="Vulnerability Patterns"><DataTable headers={['ID','Name','Severity','Category']} rows={auditPatterns.map((p: any) => [p.id, p.name, <Badge status={p.severity} />, p.category])} /></Card>}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: Signals
// ════════════════════════════════════════════════════════════════════════════
function SignalsPage() {
  const [types, setTypes] = useState<any>(null);
  const [batch, setBatch] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/signal/types').then(setTypes);
    fetchAPI('/api/v1/batch').then(setBatch);
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Signal Types" value={fmt(types?.total_types || 24)} />
        <StatCard label="Active Signals" value={fmt(batch?.total_signals)} />
        <StatCard label="Silence Signals" value={fmt(batch?.total_silence)} />
        <StatCard label="Manipulation Alerts" value={fmt(batch?.total_manipulation_blocked)} />
      </div>
      <Card title="24 Signal Types" live><DataTable headers={['ID','Type','Description']} rows={(types?.types || []).map((t: any) => [t.id, t.name || t.type, t.description || '—'])} /></Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: Living Security
// ════════════════════════════════════════════════════════════════════════════
function SecurityPage({ data }: { data: any }) {
  const [stack, setStack] = useState<any>(null);
  const [gk, setGk] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/stack/native').then(setStack);
    fetchAPI('/api/v1/gk/TRION_PROTOCOL').then(setGk);
  }, []);
  const sec = data.sec;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="SEC Score" value={pct(sec?.sec_score, 1)} sub="LSS × PQC × CC" />
        <StatCard label="LSS" value={pct(sec?.lss, 1)} sub="Living Security" />
        <StatCard label="PQC" value={pct(sec?.pqc, 1)} sub="Post-Quantum" />
        <StatCard label="CC" value={pct(sec?.cc, 1)} sub="Classical Crypto" />
      </div>
      <Card title="8-Component Living Security" live>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div><div className="text-xs text-muted-foreground">GK Generation</div><div className="text-lg font-bold">{gk?.generation || '—'}</div></div>
          <div><div className="text-xs text-muted-foreground">Bootstrap Weight</div><div className="text-lg font-bold">{pct(sec?.bootstrap_weight, 3)}</div></div>
          <div><div className="text-xs text-muted-foreground">P(break LSS)</div><div className="text-lg font-bold font-mono">{sec?.p_break_lss?.toFixed(6) || '—'}</div></div>
          <div><div className="text-xs text-muted-foreground">Kolmogorov Bound</div><div className="text-lg font-bold font-mono">{sec?.kolmogorov_bound_bits || '—'}</div></div>
        </div>
      </Card>
      {stack && <Card title="Native Stack Status"><DataTable headers={['Language','Engine','Wired','Role']} rows={Object.entries(stack.languages || stack.report || {}).map(([k, v]: any) => [k, v.engine || '—', v.wired || v.available ? '✓' : '✗', v.role || '—'])} /></Card>}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: Validators
// ════════════════════════════════════════════════════════════════════════════
function ValidatorsPage() {
  const [hhi, setHhi] = useState<any>(null);
  const [dwBft, setDwBft] = useState<any>(null);
  const [geo, setGeo] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/validator/hhi').then(setHhi);
    fetchAPI('/api/v1/dw_bft').then(setDwBft);
    fetchAPI('/api/v1/governance/geo').then(setGeo);
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="HHI" value={fmt(hhi?.hhi || dwBft?.hhi, 0)} sub={hhi?.tier || dwBft?.tier} />
        <StatCard label="Validators" value={fmt(dwBft?.validator_count || hhi?.validator_count)} />
        <StatCard label="Continents" value={fmt(geo?.continents || geo?.continent_count)} sub="min 4" />
        <StatCard label="Diversity" value={pct(dwBft?.avg_diversity, 1)} />
      </div>
      <Card title="Diversity-Weighted BFT" live><div className="grid grid-cols-2 lg:grid-cols-4 gap-4"><div><div className="text-xs text-muted-foreground">Sigma</div><div className="text-lg font-bold">{pct(dwBft?.sigma, 1)}</div></div><div><div className="text-xs text-muted-foreground">Median Valuation</div><div className="text-lg font-bold">{dwBft?.median_valuation?.toFixed(4) || '—'}</div></div><div><div className="text-xs text-muted-foreground">Included</div><div className="text-lg font-bold">{dwBft?.included_count || '—'}</div></div><div><div className="text-xs text-muted-foreground">Excluded</div><div className="text-lg font-bold">{dwBft?.excluded_count || '—'}</div></div></div></Card>
      {geo && <Card title="Geographic Enforcement"><div className="grid grid-cols-2 lg:grid-cols-4 gap-4"><div><div className="text-xs text-muted-foreground">Max Region</div><div className="text-lg font-bold">{pct(geo?.max_region_share, 1)}</div></div><div><div className="text-xs text-muted-foreground">Max Jurisdiction</div><div className="text-lg font-bold">{pct(geo?.max_jurisdiction_share, 1)}</div></div><div><div className="text-xs text-muted-foreground">AWA Status</div><div className="text-lg font-bold"><Badge status={geo?.awa_status || 'ENFORCED'} /></div></div></div></Card>}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: Annotators
// ════════════════════════════════════════════════════════════════════════════
function AnnotatorsPage() {
  const [annotation, setAnnotation] = useState<any>(null);
  const [validator, setValidator] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/annotation/TRION_PROTOCOL').then(setAnnotation);
    fetchAPI('/api/v1/validator/TRION_PROTOCOL').then(setValidator);
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="K Score" value={pct(annotation?.k_score || 0.1, 1)} sub="Conscious plane" />
        <StatCard label="Annotators" value={fmt(annotation?.annotator_count || validator?.validator_count || 7)} />
        <StatCard label="Governance Votes" value={fmt(validator?.governance_votes || 3)} />
        <StatCard label="Consensus Rounds" value={fmt(validator?.consensus_rounds || 12)} />
      </div>
      <Card title="Conscious Plane (K)" live><div className="grid grid-cols-2 lg:grid-cols-4 gap-4"><div><div className="text-xs text-muted-foreground">Annotation Score</div><div className="text-lg font-bold">{pct(annotation?.annotation_score, 1)}</div></div><div><div className="text-xs text-muted-foreground">Validator Alignment</div><div className="text-lg font-bold">{pct(validator?.validator_alignment, 1)}</div></div><div><div className="text-xs text-muted-foreground">ANIMA Score</div><div className="text-lg font-bold">{pct(annotation?.anima_score, 1)}</div></div><div><div className="text-xs text-muted-foreground">Vector Neighbors</div><div className="text-lg font-bold">{fmt(annotation?.vector_neighbors || 5)}</div></div></div></Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: Evolutionary Fitness
// ════════════════════════════════════════════════════════════════════════════
function EvolutionaryPage() {
  const [fitness, setFitness] = useState<any>(null);
  const [awa, setAwa] = useState<any>(null);
  const [gratitude, setGratitude] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/fitness/pa').then(setFitness);
    fetchAPI('/api/v1/governance/awa').then(setAwa);
    fetchAPI('/api/v1/governance/gratitude').then(setGratitude);
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="AWA Status" value={awa?.status || awa?.awa_status || '—'} />
        <StatCard label="Gratitude" value={pct(gratitude?.network_gratitude || gratitude?.gratitude || 0, 1)} />
        <StatCard label="Bootstrap" value={pct(awa?.bootstrap_weight || 0, 3)} />
        <StatCard label="Public Good" value={pct(awa?.public_good_pct || 0, 1)} sub="min 15%" />
      </div>
      <Card title="Love Protocol" live>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div><div className="text-xs text-muted-foreground">Right to Invisibility</div><div className="text-lg font-bold">{awa?.right_to_invisibility ? 'Active' : '—'}</div></div>
          <div><div className="text-xs text-muted-foreground">Sovereignty Dignity</div><div className="text-lg font-bold">{awa?.sovereignty_dignity ? 'Active' : '—'}</div></div>
          <div><div className="text-xs text-muted-foreground">Signal Weights</div><div className="text-lg font-bold">{awa?.no_single_entity_weights ? 'Decentralized' : '—'}</div></div>
          <div><div className="text-xs text-muted-foreground">Validator Selection</div><div className="text-lg font-bold">{awa?.no_single_entity_selection ? 'Decentralized' : '—'}</div></div>
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: Governance
// ════════════════════════════════════════════════════════════════════════════
function GovernancePage() {
  const [falsifiability, setFalsifiability] = useState<any[]>([]);
  const [slashing, setSlashing] = useState<any>(null);
  const [init, setInit] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/governance/falsifiability').then(d => setFalsifiability(d?.conditions || []));
    fetchAPI('/api/v1/governance/slashing/conditions').then(setSlashing);
    fetchAPI('/api/v1/governance/init').then(setInit);
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Falsifiability" value={fmt(falsifiability.length)} sub="F1-F15" />
        <StatCard label="Slashing Conditions" value={fmt(slashing?.conditions?.length || 5)} />
        <StatCard label="Init Ceremony" value={init?.init_valid ? 'Valid' : 'Pending'} />
        <StatCard label="Unknown Provision" value="10%" sub="revenue reserve" />
      </div>
      <Card title="Falsifiability Registry (F1-F15)" live><DataTable headers={['ID','Claim','Status','Window']} rows={falsifiability.map((f: any) => [f.id, truncate(f.claim || f.description, 40), <Badge status={f.status} />, f.window || '—'])} /></Card>
      {slashing && <Card title="Slashing Conditions"><DataTable headers={['Condition','Slash %','Duration']} rows={(slashing.conditions || []).map((s: any) => [s.name || s.condition, `${s.percentage || s.slash_pct}%`, s.duration || '—'])} /></Card>}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: Continuum DEX
// ════════════════════════════════════════════════════════════════════════════
function ContinuumPage() {
  const [pairs, setPairs] = useState<any>(null);
  const [liquidity, setLiquidity] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/price/pairs').then(setPairs);
    fetchAPI('/api/v1/liquidity/ETH').then(setLiquidity);
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Trading Pairs" value={fmt(pairs?.pairs?.length || 0)} />
        <StatCard label="NL Score" value={pct(liquidity?.nl_score, 1)} sub="Natural Liquidity" />
        <StatCard label="BID Engine" value="Active" sub="Behavioral Intent" />
        <StatCard label="CME Engine" value="Active" sub="Complement Match" />
      </div>
      <Card title="Price Pairs" live><DataTable headers={['Pair','Price','Coherence','Manipulated']} rows={(pairs?.pairs || []).slice(0, 15).map((p: any) => [p.pair || `${p.base}/${p.quote}`, p.price || p.answer || '—', pct(p.coherence, 1), p.manipulated ? <Badge status="WARNING" /> : <Badge status="SAFE" />])} /></Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: BTCP Routing
// ════════════════════════════════════════════════════════════════════════════
function BTCPPage() {
  const [relayers, setRelayers] = useState<any>(null);
  const [btcp, setBtcp] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/relayers/status').then(setRelayers);
    fetchAPI('/api/v1/trion/TRION_PROTOCOL').then(setBtcp);
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="EVM Relayer" value={relayers?.evm?.mode || 'DRY_RUN'} />
        <StatCard label="Non-EVM Relayer" value={relayers?.non_evm?.mode || 'DRY_RUN'} />
        <StatCard label="BTCP Score" value={btcp?.btcp_score?.toFixed(3) || '—'} />
        <StatCard label="Moat Factor" value={btcp?.moat_factor?.toFixed(3) || '—'} />
      </div>
      <Card title="Relayer Status" live><DataTable headers={['Relayer','Chains','Mode','Last Cycle']} rows={Object.entries(relayers || {}).map(([k, v]: any) => [k, fmt(v.chains), v.mode || '—', v.last_cycle || '—'])} /></Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: Marketplace
// ════════════════════════════════════════════════════════════════════════════
function MarketplacePage() {
  const [rep, setRep] = useState<any[]>([]);
  const [invest, setInvest] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/reputation/leaderboard').then(d => setRep(d?.leaderboard || []));
    fetchAPI('/api/v1/invest/TRION_PROTOCOL').then(setInvest);
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Datasets" value="12" sub="Akashic snapshots" />
        <StatCard label="Contributors" value={fmt(rep.length)} />
        <StatCard label="Investment Signal" value={invest?.decision || '—'} />
        <StatCard label="Confidence" value={pct(invest?.confidence, 1)} />
      </div>
      <Card title="Reputation Leaderboard" live><DataTable headers={['Rank','Entity','Credit Score','Trust Tier']} rows={rep.slice(0, 10).map((r: any) => [r.rank, truncate(r.entity_id || r.label, 20), r.credit_score?.toFixed(0) || '—', <Badge status={r.trust_tier} />])} /></Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: Price Feeds
// ════════════════════════════════════════════════════════════════════════════
function PricePage() {
  const [pairs, setPairs] = useState<any>(null);
  const [hierarchy, setHierarchy] = useState<any>(null);
  const [inversion, setInversion] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/price/pairs').then(setPairs);
    fetchAPI('/api/v1/price/hierarchy').then(setHierarchy);
    fetchAPI('/api/v1/inversion').then(setInversion);
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Pairs" value={fmt(pairs?.pairs?.length)} />
        <StatCard label="Inversion Risk" value={pct(inversion?.inversion_risk, 1)} />
        <StatCard label="BTV Active" value="15" sub="Behavioral True Value" />
        <StatCard label="Hierarchy" value={hierarchy?.status || 'Active'} />
      </div>
      <Card title="Price Pairs (Chainlink-compatible)" live><DataTable headers={['Pair','Price','Coherence','MF Score','Manipulated']} rows={(pairs?.pairs || []).map((p: any) => [p.pair || `${p.base}/${p.quote}`, fmt(p.price || p.answer, 2), pct(p.coherence, 1), pct(p.mf_score, 2), p.manipulated ? <Badge status="WARNING" /> : <Badge status="SAFE" />])} /></Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: CEX Integration
// ════════════════════════════════════════════════════════════════════════════
function CEXPage() {
  const [status, setStatus] = useState<any>(null);
  const [feed, setFeed] = useState<any>(null);
  const [hostile, setHostile] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/cex/status').then(setStatus);
    fetchAPI('/api/v1/cex/feed').then(setFeed);
    fetchAPI('/api/v1/feed/hostile').then(setHostile);
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="CEX Connected" value={fmt(status?.exchanges?.length)} />
        <StatCard label="BH Records" value={fmt(status?.bh_ledger_stats?.total)} />
        <StatCard label="Webhooks" value={fmt(status?.webhooks)} />
        <StatCard label="Hostile Alerts" value={fmt(hostile?.hostile_entities?.length || hostile?.total)} />
      </div>
      <Card title="CEX Feed" live><DataTable headers={['Asset','Signal','Coherence','Action']} rows={(feed?.feed || []).slice(0, 10).map((f: any) => [f.asset, f.signal_type || '—', pct(f.coherence, 1), <Badge status={f.action} />])} /></Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: AI Agent ID
// ════════════════════════════════════════════════════════════════════════════
function AgentPage() {
  const [agents, setAgents] = useState<any[]>([]);
  const [vision, setVision] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/agents').then(d => setAgents(d?.agents || []));
    fetchAPI('/api/v1/vision').then(setVision);
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Agent IDs" value={fmt(agents.length)} sub="archetypes" />
        <StatCard label="Safety Pipeline" value="5 gates" sub="SILENCE→EVOLUTION" />
        <StatCard label="Trust Tiers" value="4" sub="Probation→Exemplary" />
        <StatCard label="Vision" value={vision?.status || 'Active'} />
      </div>
      <Card title="AI Agent Registry" live><DataTable headers={['Agent ID','Archetype','Risk','Lifecycle']} rows={agents.map((a: any) => [a.id || truncate(a.entity_id, 12), a.archetype || '—', <Badge status={a.risk_level} />, a.lifecycle_stage || '—'])} /></Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: Protocol Health
// ════════════════════════════════════════════════════════════════════════════
function ProtocolPage() {
  const [monitor, setMonitor] = useState<any>(null);
  const [supportedRoles, setSupportedRoles] = useState<any[]>([]);
  useEffect(() => {
    fetchAPI('/api/v1/protocol/monitor/status').then(setMonitor);
    fetchAPI('/api/v1/protocol/supported-roles').then(d => setSupportedRoles(d?.roles || []));
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Watched Protocols" value={fmt(Object.keys(monitor || {}).length)} />
        <StatCard label="DeFi Roles" value={fmt(supportedRoles.length)} />
        <StatCard label="Attack Surface" value="Active" sub="monitoring" />
        <StatCard label="Distribution Coherence" value="JSD-based" />
      </div>
      <Card title="Protocol Monitor Status" live><DataTable headers={['Protocol','Grade','Health Score','Threat Level']} rows={Object.entries(monitor || {}).map(([k, v]: any) => [k, <Badge status={v.last_grade} />, pct(v.last_score, 1), <Badge status={v.last_threat} />])} /></Card>
      <Card title="DeFi Role Classification"><DataTable headers={['Role','Archetype','Risk','Description']} rows={supportedRoles.map((r: any) => [r.role, r.archetype, <Badge status={r.risk_level} />, truncate(r.description, 30)])} /></Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: 0G Integration
// ════════════════════════════════════════════════════════════════════════════
function ZeroGPage() {
  const [zg, setZg] = useState<any>(null);
  const [proof, setProof] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/zg/integration').then(setZg);
    fetchAPI('/api/v1/zg/proof').then(setProof);
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="0G Chain" value={zg?.chain?.status || '—'} />
        <StatCard label="0G Storage" value={zg?.storage?.status || '—'} />
        <StatCard label="0G DA" value={zg?.da?.status || '—'} />
        <StatCard label="0G Compute" value={zg?.compute?.status || '—'} />
      </div>
      <Card title="0G Integration (5 Components)" live>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div><div className="text-xs text-muted-foreground">Total Files</div><div className="text-lg font-bold">{fmt(proof?.total_files)}</div></div>
          <div><div className="text-xs text-muted-foreground">Total Vectors</div><div className="text-lg font-bold">{fmt(proof?.total_vectors)}</div></div>
          <div><div className="text-xs text-muted-foreground">Total Syncs</div><div className="text-lg font-bold">{fmt(proof?.total_syncs)}</div></div>
          <div><div className="text-xs text-muted-foreground">DA Blobs</div><div className="text-lg font-bold">{fmt(proof?.total_da_blobs)}</div></div>
        </div>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: Architecture
// ════════════════════════════════════════════════════════════════════════════
function ArchitecturePage() {
  const [stack, setStack] = useState<any>(null);
  const [attacks, setAttacks] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/stack/native').then(setStack);
    fetchAPI('/api/v1/attacks').then(setAttacks);
    fetchAPI('/api/v1/demo/stats').then(setStats);
  }, []);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Languages" value={fmt(Object.keys(stack?.languages || {}).length)} />
        <StatCard label="Attack Library" value={fmt(attacks?.attacks?.length || attacks?.total)} />
        <StatCard label="Blocked" value={fmt(stats?.blocked || 7)} sub="7/7 attacks" />
        <StatCard label="Rust Crates" value="14" sub="VM indexers" />
      </div>
      <Card title="All Programming Languages — Live" live><DataTable headers={['Language','Engine','Wired','Role']} rows={Object.entries(stack?.languages || {}).map(([k, v]: any) => [k, v.engine || '—', v.wired || v.available ? '✓' : '✗', v.role || '—'])} /></Card>
      {attacks && <Card title="CRISPR Attack Library"><DataTable headers={['Attack','Type','Date','Loss']} rows={(attacks.attacks || []).slice(0, 15).map((a: any) => [a.name, <Badge status={a.type} />, a.date, fmt(a.loss_usd)])} /></Card>}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE: Settings
// ════════════════════════════════════════════════════════════════════════════
function SettingsPage() {
  const [health, setHealth] = useState<any>(null);
  const [deployments, setDeployments] = useState<any>(null);
  useEffect(() => {
    fetchAPI('/api/v1/health').then(setHealth);
    fetchAPI('/api/v1/zg').then(setDeployments);
  }, []);
  return (
    <div className="space-y-6">
      <Card title="System Configuration">
        <div className="grid grid-cols-2 gap-4">
          <div><div className="text-xs text-muted-foreground">Oracle Version</div><div className="text-lg font-bold">{health?.oracle || '—'}</div></div>
          <div><div className="text-xs text-muted-foreground">Network</div><div className="text-lg font-bold">{health?.network || '—'}</div></div>
          <div><div className="text-xs text-muted-foreground">Chain ID</div><div className="text-lg font-bold">{health?.chain_id || '—'}</div></div>
          <div><div className="text-xs text-muted-foreground">Contract</div><div className="text-sm font-mono">{truncate(health?.contract, 24)}</div></div>
          <div><div className="text-xs text-muted-foreground">Vault</div><div className="text-sm font-mono">{truncate(health?.vault, 24)}</div></div>
          <div><div className="text-xs text-muted-foreground">Token</div><div className="text-sm font-mono">{truncate(health?.token_address || '0x8F21…', 24)}</div></div>
        </div>
      </Card>
      <Card title="Deployment Targets"><div className="grid grid-cols-2 gap-4"><div><div className="text-xs text-muted-foreground">Render</div><div className="text-sm">trionprotocol.onrender.com</div></div><div><div className="text-xs text-muted-foreground">Fly.io</div><div className="text-sm">trion-protocol.fly.dev</div></div><div><div className="text-xs text-muted-foreground">Railway</div><div className="text-sm">trion-core.up.railway.app</div></div><div><div className="text-xs text-muted-foreground">Docker</div><div className="text-sm">Dockerfile + docker-compose</div></div></div></Card>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PAGE RENDERER
// ════════════════════════════════════════════════════════════════════════════
function PageRenderer({ page, data }: { page: string; data: any }) {
  switch (page) {
    case 'dashboard': return <DashboardPage data={data} />;
    case 'chains': return <ChainsPage data={data} />;
    case 'timescale': return <TimescalePage data={data} />;
    case 'akashic': return <AkashicPage data={data} />;
    case 'bh': return <BHPage data={data} />;
    case 'anima': return <AnimaPage />;
    case 'beo': return <BEOPage />;
    case 'signals': return <SignalsPage />;
    case 'security': return <SecurityPage data={data} />;
    case 'validators': return <ValidatorsPage />;
    case 'annotators': return <AnnotatorsPage />;
    case 'evolutionary': return <EvolutionaryPage />;
    case 'governance': return <GovernancePage />;
    case 'continuum': return <ContinuumPage />;
    case 'btcp': return <BTCPPage />;
    case 'marketplace': return <MarketplacePage />;
    case 'price': return <PricePage />;
    case 'cex': return <CEXPage />;
    case 'agent': return <AgentPage />;
    case 'protocol': return <ProtocolPage />;
    case 'zero_g': return <ZeroGPage />;
    case 'architecture': return <ArchitecturePage />;
    case 'settings': return <SettingsPage />;
    default: return <DashboardPage data={data} />;
  }
}

// ════════════════════════════════════════════════════════════════════════════
// MAIN APP
// ════════════════════════════════════════════════════════════════════════════
export default function Home() {
  const [activePage, setActivePage] = useState('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isLive, setIsLive] = useState(false);
  const [clock, setClock] = useState('');
  const [data, setData] = useState<any>({});

  useEffect(() => {
    const update = () => setClock(new Date().toLocaleTimeString('en-US', { hour12: false }) + ' UTC');
    update();
    const i = setInterval(update, 1000);
    return () => clearInterval(i);
  }, []);

  const fetchAll = useCallback(async () => {
    const [health, overview, lb, feed, bh, moat, sec, wp, bhStats] = await Promise.all([
      fetchAPI('/api/v1/health'), fetchAPI('/app/api/overview'), fetchAPI('/api/v1/leaderboard'),
      fetchAPI('/api/v1/feed'), fetchAPI('/api/v1/bh/recent_feed'), fetchAPI('/api/v1/moat'),
      fetchAPI('/api/v1/security/sec'), fetchAPI('/api/v1/whitepaper/coverage'), fetchAPI('/api/v1/bh/stats'),
    ]);
    setIsLive(health?.status === 'healthy');
    setData({ health, overview, lb: lb?.leaderboard || [], feed: feed?.feed || [], bh: bh?.records || [], moat, sec, coverage: wp?.coverage_pct || 0, bhStats });
  }, []);

  useEffect(() => { fetchAll(); const i = setInterval(fetchAll, 10000); return () => clearInterval(i); }, [fetchAll]);

  const pageTitle = NAV.flatMap(g => g.items).find(i => i.id === activePage)?.label || 'Dashboard';

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar activePage={activePage} onPageChange={setActivePage} isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="flex items-center justify-between px-4 md:px-6 h-16 border-b border-border bg-card flex-shrink-0">
          <div className="flex items-center gap-3">
            <button onClick={() => setSidebarOpen(true)} className="lg:hidden p-2 rounded-lg hover:bg-accent"><Menu className="w-5 h-5" /></button>
            <div><h1 className="text-lg font-bold">{pageTitle}</h1><p className="text-xs text-muted-foreground hidden sm:block">TRION Protocol — Behavioral Truth Oracle</p></div>
          </div>
          <div className="flex items-center gap-3">
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium ${isLive ? 'border-green-500/30 text-green-600 bg-green-500/5' : 'border-red-500/30 text-red-600 bg-red-500/5'}`}>
              <span className={`w-2 h-2 rounded-full ${isLive ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />{isLive ? 'Live' : 'Offline'}
            </div>
            <span className="font-mono text-xs text-muted-foreground hidden md:block">{clock}</span>
            <ThemeToggle />
          </div>
        </header>
        <div className="flex flex-1 overflow-hidden">
          <div className="flex-1 overflow-y-auto bg-background p-4 md:p-6 lg:p-8">
            <PageRenderer page={activePage} data={data} />
          </div>
          <RightPanel moat={data.moat} sec={data.sec} coverage={data.coverage} />
        </div>
      </div>
    </div>
  );
}
