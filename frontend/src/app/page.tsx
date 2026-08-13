'use client';

import { useState, useEffect, useCallback } from 'react';
import { Moon, Sun, Monitor, Menu, Activity, Database, Shield, Zap, Globe, TrendingUp, ExternalLink } from 'lucide-react';

// ════════════════════════════════════════════════════════════════════════════
// TYPES & HELPERS
// ════════════════════════════════════════════════════════════════════════════
const API_BASE = typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:5000';

async function fetchAPI(path: string): Promise<any | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, { signal: AbortSignal.timeout(10000) });
    if (!res.ok) return null;
    return await res.json();
  } catch { return null; }
}

const fmt = (n: any, d = 0) => n === null || n === undefined ? '—' : Number(n).toLocaleString('en-US', { maximumFractionDigits: d });
const pct = (n: any, d = 1) => n === null || n === undefined ? '—' : (Number(n) * 100).toFixed(d) + '%';
const time = (ts: any) => ts ? new Date(Number(ts) * 1000).toLocaleTimeString('en-US', { hour12: false }) : '—';

const NAV_GROUPS = [
  { label: 'Overview', items: [
    { id: 'dashboard', label: 'Dashboard', icon: Activity },
    { id: 'chains', label: 'Chain Coverage', icon: Globe },
    { id: 'architecture', label: 'Architecture', icon: Database },
  ]},
  { label: 'Behavioral Engine', items: [
    { id: 'akashic', label: 'Akashic Index', icon: Database },
    { id: 'bh-explorer', label: 'BH Explorer', icon: Zap },
    { id: 'anima', label: 'ANIMA Intelligence', icon: TrendingUp },
    { id: 'beo', label: 'BEO Resolution', icon: Shield },
  ]},
  { label: 'Security & Consensus', items: [
    { id: 'living-security', label: 'Living Security', icon: Shield },
    { id: 'validators', label: 'Validators', icon: Globe },
    { id: 'annotators', label: 'Annotators', icon: Activity },
    { id: 'evolutionary', label: 'Evolutionary Fitness', icon: TrendingUp },
  ]},
  { label: 'Markets', items: [
    { id: 'continuum', label: 'Continuum DEX', icon: Globe },
    { id: 'btcp', label: 'BTCP Routing', icon: Zap },
    { id: 'marketplace', label: 'Data Marketplace', icon: TrendingUp },
  ]},
  { label: 'Infrastructure', items: [
    { id: 'agent-id', label: 'AI Agent ID', icon: Activity },
    { id: 'timescale', label: 'TimescaleDB', icon: Database },
    { id: 'settings', label: 'Settings', icon: Shield },
  ]},
];

// ════════════════════════════════════════════════════════════════════════════
// THEME TOGGLE
// ════════════════════════════════════════════════════════════════════════════
function ThemeToggle() {
  const [theme, setTheme] = useState<'light' | 'dark' | 'system'>('system');
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const s = localStorage.getItem('trion-theme') as any;
    if (s) setTheme(s);
  }, []);
  useEffect(() => {
    localStorage.setItem('trion-theme', theme);
    const root = document.documentElement;
    const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    root.classList.toggle('dark', isDark);
  }, [theme]);
  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border hover:bg-accent transition-colors" aria-label="Theme">
        {theme === 'dark' ? <Moon className="w-4 h-4" /> : theme === 'light' ? <Sun className="w-4 h-4" /> : <Monitor className="w-4 h-4" />}
        <span className="text-sm capitalize hidden sm:inline">{theme}</span>
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-36 rounded-lg border border-border bg-popover shadow-lg z-50">
          {(['light', 'dark', 'system'] as const).map(t => (
            <button key={t} onClick={() => { setTheme(t); setOpen(false); }}
              className={`flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-accent transition-colors ${theme === t ? 'text-primary font-medium' : 'text-muted-foreground'}`}>
              {t === 'dark' ? <Moon className="w-4 h-4" /> : t === 'light' ? <Sun className="w-4 h-4" /> : <Monitor className="w-4 h-4" />}
              <span className="capitalize">{t}</span>
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
          <div>
            <div className="font-bold text-base">TRION</div>
            <div className="text-xs text-muted-foreground">Behavioral Truth Oracle</div>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto p-3 space-y-6">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 px-3 mb-2">{group.label}</div>
              <div className="space-y-1">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const isActive = activePage === item.id || (activePage === 'main' && item.id === 'dashboard');
                  return (
                    <button key={item.id} onClick={() => { onPageChange(item.id); onClose(); }}
                      className={`flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm font-medium transition-all ${isActive ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent hover:text-foreground'}`}>
                      <Icon className="w-4 h-4 flex-shrink-0" />
                      <span className="truncate">{item.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
        <div className="p-3 border-t border-border">
          <a href={`${API_BASE}/api/v1/health`} target="_blank" rel="noopener" className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-muted-foreground hover:bg-accent transition-colors">
            <ExternalLink className="w-4 h-4" /> API Health
          </a>
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
  const circumference = 2 * Math.PI * 52;
  const offset = circumference - (secScore * 100 / 100) * circumference;
  return (
    <aside className="hidden xl:flex w-[280px] flex-shrink-0 flex-col gap-6 p-6 bg-gradient-to-b from-primary to-primary/90 text-primary-foreground relative overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(255,255,255,0.07),transparent_60%)] pointer-events-none" />
      <div className="text-center relative z-10">
        <div className="text-[11px] font-bold uppercase tracking-wider opacity-80 mb-1">Protocol Moat</div>
        <div className="text-3xl font-bold text-cyan-300">{moat ? moat.M_moat.toFixed(4) : '—'}</div>
      </div>
      <div className="flex flex-col items-center relative z-10">
        <div className="text-xs font-semibold text-white/80 mb-3">Security Score</div>
        <div className="relative w-32 h-32">
          <svg className="w-full h-full -rotate-90" viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="52" fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="8" />
            <circle cx="60" cy="60" r="52" fill="none" stroke="#22D3EE" strokeWidth="8" strokeLinecap="round"
              strokeDasharray={circumference} strokeDashoffset={offset}
              style={{ filter: 'drop-shadow(0 0 8px rgba(34,211,238,0.5))' }} />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-2xl font-bold text-white">{Math.round(secScore * 100)}%</span>
            <span className="text-xs text-white/70">{secScore >= 0.9 ? 'Quantum Resistant' : 'Active'}</span>
          </div>
        </div>
      </div>
      <div className="space-y-4 relative z-10">
        <div>
          <div className="flex justify-between text-[11px] font-semibold mb-1.5"><span>Formula Coverage</span><span>{coverage}%</span></div>
          <div className="h-1 bg-white/20 rounded-full overflow-hidden"><div className="h-full bg-cyan-400 rounded-full" style={{ width: `${coverage}%` }} /></div>
        </div>
        {moat?.components && Object.entries(moat.components).slice(0, 3).map(([key, val]: any) => (
          <div key={key}>
            <div className="flex justify-between text-[11px] font-semibold mb-1.5"><span className="capitalize">{key.replace(/_/g, ' ')}</span><span>{Math.round(val * 100)}%</span></div>
            <div className="h-1 bg-white/20 rounded-full overflow-hidden"><div className="h-full bg-cyan-400 rounded-full" style={{ width: `${val * 100}%` }} /></div>
          </div>
        ))}
      </div>
      <div className="mt-auto bg-white/10 backdrop-blur rounded-2xl p-4 relative z-10">
        <div className="flex justify-between items-center mb-2"><span className="text-[11px] font-bold opacity-90">Akashic Depth</span><Database className="w-3.5 h-3.5 opacity-70" /></div>
        <div className="text-lg font-bold text-cyan-300 mb-1">{moat ? fmt(moat.akashic_depth, 0) : '—'}</div>
        <div className="text-[11px] opacity-70">{moat ? `${moat.chains_indexed} chains indexed` : ''}</div>
      </div>
    </aside>
  );
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
      fetchAPI('/api/v1/health'),
      fetchAPI('/app/api/overview'),
      fetchAPI('/api/v1/leaderboard'),
      fetchAPI('/api/v1/feed'),
      fetchAPI('/api/v1/bh/recent_feed'),
      fetchAPI('/api/v1/moat'),
      fetchAPI('/api/v1/security/sec'),
      fetchAPI('/api/v1/whitepaper/coverage'),
      fetchAPI('/api/v1/bh/stats'),
    ]);
    setIsLive(health?.status === 'healthy');
    setData({ health, overview, lb: lb?.leaderboard || [], feed: feed?.feed || [], bh: bh?.records || [], moat, sec, coverage: wp?.coverage_pct || 0, bhStats });
  }, []);

  useEffect(() => { fetchAll(); const i = setInterval(fetchAll, 10000); return () => clearInterval(i); }, [fetchAll]);

  const { health, overview, lb = [], feed = [], bh = [], moat, sec, coverage = 0, bhStats } = data;
  const totalBH = bhStats?.total_records || 0;
  const totalVec = health?.total_signals_onchain || 0;
  const totalChains = overview?.chains?.chains?.length || overview?.chains?.total || 0;
  const volatility = health?.market_volatility || 0;
  const pageTitle = NAV_GROUPS.flatMap(g => g.items).find(i => i.id === activePage)?.label || 'Dashboard';

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar activePage={activePage} onPageChange={setActivePage} isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Topbar */}
        <header className="flex items-center justify-between px-4 md:px-6 h-16 border-b border-border bg-card flex-shrink-0">
          <div className="flex items-center gap-3">
            <button onClick={() => setSidebarOpen(true)} className="lg:hidden p-2 rounded-lg hover:bg-accent"><Menu className="w-5 h-5" /></button>
            <div>
              <h1 className="text-lg font-bold">{pageTitle}</h1>
              <p className="text-xs text-muted-foreground hidden sm:block">Real-time behavioral truth oracle — five-plane coherence across 100+ chains</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium ${isLive ? 'border-green-500/30 text-green-600 bg-green-500/5' : 'border-red-500/30 text-red-600 bg-red-500/5'}`}>
              <span className={`w-2 h-2 rounded-full ${isLive ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
              {isLive ? 'Live' : 'Offline'}
            </div>
            <span className="font-mono text-xs text-muted-foreground hidden md:block">{clock}</span>
            <ThemeToggle />
          </div>
        </header>

        {/* Content + Right Panel */}
        <div className="flex flex-1 overflow-hidden">
          <div className="flex-1 overflow-y-auto bg-background p-4 md:p-6 lg:p-8 space-y-6">
            {/* Stat cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              {[
                { label: 'FAISS Vectors', value: fmt(totalVec), sub: 'ANIMA Engine' },
                { label: 'BH Records', value: fmt(totalBH), sub: 'Append-only ledger' },
                { label: 'Chains Active', value: fmt(totalChains), sub: '14 VM families' },
                { label: 'Market Volatility', value: pct(volatility, 1), sub: 'Dynamic threshold' },
              ].map((s, i) => (
                <div key={i} className="bg-card rounded-2xl p-5 border border-border shadow-sm hover:shadow-md transition-shadow">
                  <div className="text-xl font-bold mb-2">{s.value}</div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">{s.label}</span>
                    {s.sub && <span className="text-xs font-semibold">{s.sub}</span>}
                  </div>
                </div>
              ))}
            </div>

            {/* Network status card */}
            <div className="bg-card rounded-2xl p-6 border border-border shadow-sm">
              <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-4">Network Status</div>
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                <div>
                  <div className="text-2xl font-bold">{health?.status === 'healthy' ? 'Operational' : 'Degraded'}</div>
                  <div className="text-xs text-muted-foreground mt-1">Dynamic Threshold: {pct(health?.dynamic_threshold, 1)}</div>
                </div>
                <div className="flex gap-6">
                  <div><div className="text-xs text-muted-foreground">Signals On-Chain</div><div className="text-lg font-bold">{fmt(health?.total_signals_onchain)}</div></div>
                  <div><div className="text-xs text-muted-foreground">Formula Coverage</div><div className="text-lg font-bold text-primary">{coverage}%</div></div>
                </div>
              </div>
              <div className="mt-4 h-1.5 bg-muted rounded-full overflow-hidden"><div className="h-full bg-primary rounded-full transition-all" style={{ width: `${coverage}%` }} /></div>
            </div>

            {/* Leaderboard + Feed */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
                <div className="flex items-center justify-between p-5 border-b border-border">
                  <span className="font-semibold">Top Coherent Entities</span>
                  <span className="flex items-center gap-1.5 text-xs text-green-500 font-medium"><span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />Live</span>
                </div>
                <div className="max-h-80 overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 sticky top-0"><tr><th className="text-left p-3 text-xs font-semibold text-muted-foreground">#</th><th className="text-left p-3 text-xs font-semibold text-muted-foreground">Entity</th><th className="text-right p-3 text-xs font-semibold text-muted-foreground">Coherence</th><th className="text-left p-3 text-xs font-semibold text-muted-foreground">Archetype</th></tr></thead>
                    <tbody>
                      {lb.length === 0 ? <tr><td colSpan={4} className="p-8 text-center text-muted-foreground">Loading…</td></tr> :
                        lb.slice(0, 8).map((e: any) => (
                          <tr key={e.rank} className="border-b border-border/50 hover:bg-muted/30"><td className="p-3 font-mono text-muted-foreground">{e.rank}</td><td className="p-3 truncate max-w-[160px]" title={e.entity_id}>{e.label || e.entity_id?.slice(0, 16) + '…'}</td><td className="p-3 text-right font-mono">{pct(e.coherence_score, 1)}</td><td className="p-3"><span className="px-2 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary">{e.archetype}</span></td></tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
                <div className="flex items-center justify-between p-5 border-b border-border">
                  <span className="font-semibold">Live Signal Feed</span>
                  <span className="flex items-center gap-1.5 text-xs text-green-500 font-medium"><span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />Auto-refresh</span>
                </div>
                <div className="max-h-80 overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 sticky top-0"><tr><th className="text-left p-3 text-xs font-semibold text-muted-foreground">Time</th><th className="text-left p-3 text-xs font-semibold text-muted-foreground">Protocol</th><th className="text-right p-3 text-xs font-semibold text-muted-foreground">Score</th><th className="text-left p-3 text-xs font-semibold text-muted-foreground">Grade</th></tr></thead>
                    <tbody>
                      {feed.length === 0 ? <tr><td colSpan={4} className="p-8 text-center text-muted-foreground">Loading…</td></tr> :
                        feed.slice(0, 10).map((s: any, i: number) => (
                          <tr key={i} className="border-b border-border/50 hover:bg-muted/30"><td className="p-3 font-mono text-xs text-muted-foreground">{time(s.timestamp)}</td><td className="p-3 truncate max-w-[140px]">{s.protocol_name || s.short_id || '—'}</td><td className="p-3 text-right font-mono">{pct(s.coherence_score, 1)}</td><td className="p-3"><span className={`px-2 py-0.5 rounded-full text-xs font-medium ${s.grade === 'A' ? 'bg-green-500/10 text-green-600' : s.grade === 'B' ? 'bg-blue-500/10 text-blue-600' : s.grade === 'C' ? 'bg-yellow-500/10 text-yellow-600' : 'bg-red-500/10 text-red-600'}`}>{s.grade}</span></td></tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* BH Stream */}
            <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
              <div className="flex items-center justify-between p-5 border-b border-border">
                <span className="font-semibold">Behavioral Hash Stream</span>
                <span className="flex items-center gap-1.5 text-xs text-green-500 font-medium"><span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />Streaming</span>
              </div>
              <div className="max-h-64 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 sticky top-0"><tr><th className="text-left p-3 text-xs font-semibold text-muted-foreground">Time</th><th className="text-left p-3 text-xs font-semibold text-muted-foreground">Entity</th><th className="text-left p-3 text-xs font-semibold text-muted-foreground">Chain</th><th className="text-left p-3 text-xs font-semibold text-muted-foreground">Event</th><th className="text-left p-3 text-xs font-semibold text-muted-foreground">Verdict</th></tr></thead>
                  <tbody>
                    {bh.length === 0 ? <tr><td colSpan={5} className="p-8 text-center text-muted-foreground">Loading…</td></tr> :
                      bh.slice(0, 15).map((b: any, i: number) => (
                        <tr key={i} className="border-b border-border/50 hover:bg-muted/30"><td className="p-3 font-mono text-xs text-muted-foreground">{time(b.ts)}</td><td className="p-3 font-mono text-xs truncate max-w-[120px]">{b.entity_id?.slice(0, 14)}…</td><td className="p-3"><span className="px-2 py-0.5 rounded text-xs font-medium bg-muted text-muted-foreground">{b.chain}</span></td><td className="p-3 text-xs">{b.event_type}</td><td className="p-3"><span className={`px-2 py-0.5 rounded-full text-xs font-medium ${b.verdict === 'SAFE' ? 'bg-green-500/10 text-green-600' : 'bg-red-500/10 text-red-600'}`}>{b.verdict}</span></td></tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <RightPanel moat={moat} sec={sec} coverage={coverage} />
        </div>
      </div>
    </div>
  );
}
