/**
 * TRION UI - Shared components for the dashboard.
 */
'use client';

import React, { useState, useEffect, useRef } from 'react';
import { fetchAPI, fmt, pct, tfmt, dtfmt, truncate, hex, compact, statusColor, ms } from '../lib/api';

// ════════════════════════════════════════════════════════════════════════════
// PRIMITIVES
// ════════════════════════════════════════════════════════════════════════════

export function Card({
  title,
  subtitle,
  children,
  live,
  right,
  collapsible,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  live?: boolean;
  right?: React.ReactNode;
  collapsible?: boolean;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden transition-all hover:shadow-md">
      <div className="flex items-center justify-between p-4 md:p-5 border-b border-border">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <div className="min-w-0">
            <div className="font-semibold text-sm md:text-base truncate">{title}</div>
            {subtitle && <div className="text-xs text-muted-foreground mt-0.5 truncate">{subtitle}</div>}
          </div>
          {live && (
            <span className="flex items-center gap-1.5 text-xs text-green-500 font-medium ml-2 flex-shrink-0">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
              LIVE
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {right}
          {collapsible && (
            <button onClick={() => setOpen(!open)} className="text-muted-foreground hover:text-foreground p-1">
              {open ? '-' : '+'}
            </button>
          )}
        </div>
      </div>
      {open && <div className="p-4 md:p-5">{children}</div>}
    </div>
  );
}

export function StatCard({
  label,
  value,
  sub,
  trend,
  color = 'default',
  icon,
}: {
  label: string;
  value: string | number | React.ReactNode;
  sub?: string;
  trend?: 'up' | 'down' | 'flat';
  color?: 'default' | 'green' | 'amber' | 'red' | 'blue' | 'purple';
  icon?: React.ReactNode;
}) {
  const colors = {
    default: 'border-border',
    green: 'border-green-500/30 bg-green-500/5',
    amber: 'border-amber-500/30 bg-amber-500/5',
    red: 'border-red-500/30 bg-red-500/5',
    blue: 'border-blue-500/30 bg-blue-500/5',
    purple: 'border-purple-500/30 bg-purple-500/5',
  };
  const trendIcon = trend === 'up' ? 'up' : trend === 'down' ? 'down' : '';
  return (
    <div className={`bg-card rounded-2xl p-4 md:p-5 border ${colors[color]} shadow-sm hover:shadow-md transition-all overflow-hidden`}>
      {icon && <div className="mb-2 text-muted-foreground">{icon}</div>}
      <div 
        className="font-bold mb-1.5 ticker break-all"
        style={{
          fontSize: typeof value === 'string' && value.length > 12 
            ? 'clamp(0.75rem, 1.5vw, 1rem)' 
            : typeof value === 'string' && value.length > 8
              ? 'clamp(0.9rem, 1.8vw, 1.25rem)'
              : 'clamp(1.1rem, 2.2vw, 1.5rem)',
          lineHeight: 1.2,
          wordBreak: 'break-all',
          overflowWrap: 'anywhere',
        }}
        title={typeof value === 'string' || typeof value === 'number' ? String(value) : undefined}
      >{value}</div>
      <div className="flex items-center justify-between gap-2 min-w-0">
        <span className="text-xs text-muted-foreground truncate min-w-0 flex-1" style={{fontSize: "clamp(0.65rem, 1.1vw, 0.75rem)"}}>{label}</span>
        {sub && <span className="text-xs font-semibold flex items-center gap-1 flex-shrink-0 truncate max-w-[50%]">{trendIcon}{sub}</span>}
      </div>
    </div>
  );
}

export function ProgressBar({
  value,
  max = 1,
  color = 'primary',
  height = 8,
  label,
  showValue = false,
}: {
  value: number;
  max?: number;
  color?: 'primary' | 'green' | 'amber' | 'red' | 'blue' | 'purple';
  height?: number;
  label?: string;
  showValue?: boolean;
}) {
  const v = Math.max(0, Math.min(1, value / max));
  const colors = {
    primary: 'bg-blue-500',
    green: 'bg-green-500',
    amber: 'bg-amber-500',
    red: 'bg-red-500',
    blue: 'bg-blue-500',
    purple: 'bg-purple-500',
  };
  return (
    <div>
      {label && (
        <div className="flex justify-between mb-1 text-xs gap-2 min-w-0">
          <span className="text-muted-foreground truncate min-w-0">{label}</span>
          {showValue && <span className="font-mono flex-shrink-0">{(v * 100).toFixed(1)}%</span>}
        </div>
      )}
      <div className="bg-muted rounded-full overflow-hidden" style={{ height }}>
        <div
          className={`${colors[color]} rounded-full transition-all duration-500`}
          style={{ width: `${v * 100}%`, height: '100%' }}
        />
      </div>
    </div>
  );
}

export function Badge({ status, label }: { status?: any; label?: string }) {
  const color = statusColor(status || label);
  const colors: Record<string, string> = {
    green: 'bg-green-500/10 text-green-600 border-green-500/30',
    amber: 'bg-amber-500/10 text-amber-600 border-amber-500/30',
    red: 'bg-red-500/10 text-red-600 border-red-500/30',
    blue: 'bg-blue-500/10 text-blue-600 border-blue-500/30',
    gray: 'bg-gray-500/10 text-gray-500 border-gray-500/30',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border max-w-[200px] truncate ${colors[color]}`} title={label || String(status || '')}>
      <span className="truncate">{label || String(status || 'N/A')}</span>
    </span>
  );
}

export function DataTable({
  headers,
  rows,
  maxHeight = 320,
  emptyMessage = 'Loading...',
  sortable = false,
  exportable = false,
  exportName = 'trion_export',
  onRowClick,
  copyableColumns,
}: {
  headers: string[];
  rows: (string | React.ReactNode)[][];
  maxHeight?: number;
  emptyMessage?: string;
  sortable?: boolean;
  exportable?: boolean;
  exportName?: string;
  onRowClick?: (rowIdx: number) => void;
  copyableColumns?: number[]; // column indices that should show a copy button
}) {
  const [sortCol, setSortCol] = useState<number | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc' | null>(null);

  // Apply sort
  let displayRows = rows;
  if (sortable && sortCol !== null && sortDir !== null) {
    displayRows = [...rows].sort((a, b) => {
      const av = a[sortCol];
      const bv = b[sortCol];
      // Try numeric compare first
      const an = typeof av === 'string' ? parseFloat(av.replace(/[^0-9.-]/g, '')) : NaN;
      const bn = typeof bv === 'string' ? parseFloat(bv.replace(/[^0-9.-]/g, '')) : NaN;
      if (!isNaN(an) && !isNaN(bn)) {
        return sortDir === 'asc' ? an - bn : bn - an;
      }
      const as = String(av ?? '');
      const bs = String(bv ?? '');
      return sortDir === 'asc' ? as.localeCompare(bs) : bs.localeCompare(as);
    });
  }

  const handleSort = (colIdx: number) => {
    if (!sortable) return;
    if (sortCol === colIdx) {
      // Cycle: asc {'->'} desc {'->'} null
      if (sortDir === 'asc') setSortDir('desc');
      else if (sortDir === 'desc') { setSortCol(null); setSortDir(null); }
    } else {
      setSortCol(colIdx);
      setSortDir('asc');
    }
  };

  const exportCSV = () => {
    const csv = [
      headers.join(','),
      ...rows.map(r => r.map(c => {
        const s = typeof c === 'string' ? c : String(c ?? '');
        return `"${s.replace(/"/g, '""')}"`;
      }).join(',')),
    ].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${exportName}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportJSON = () => {
    const data = rows.map(r => {
      const obj: Record<string, any> = {};
      headers.forEach((h, i) => { obj[h] = r[i]; });
      return obj;
    });
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${exportName}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyCell = (val: React.ReactNode) => {
    const s = typeof val === 'string' ? val : String(val ?? '');
    navigator.clipboard?.writeText(s).catch(() => {});
  };

  return (
    <div>
      {exportable && rows.length > 0 && (
        <div className="flex justify-end gap-2 mb-2">
          <button
            onClick={exportCSV}
            className="text-xs px-2 py-1 rounded border border-border hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Export as CSV"
          >
            down CSV
          </button>
          <button
            onClick={exportJSON}
            className="text-xs px-2 py-1 rounded border border-border hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Export as JSON"
          >
            down JSON
          </button>
        </div>
      )}
      <div className="overflow-auto" style={{ maxHeight }}>
        <table className="w-full text-sm">
          <thead className="bg-muted/50 sticky top-0 backdrop-blur">
            <tr>
              {headers.map((h, i) => (
                <th
                  key={i}
                  onClick={() => handleSort(i)}
                  className={`text-left p-2 md:p-3 text-xs font-semibold text-muted-foreground whitespace-nowrap ${
                    sortable ? 'cursor-pointer hover:text-foreground select-none' : ''
                  }`}
                  aria-sort={sortCol === i ? (sortDir === 'asc' ? 'ascending' : sortDir === 'desc' ? 'descending' : 'none') : undefined}
                >
                  {h}
                  {sortable && sortCol === i && (
                    <span className="ml-1" aria-hidden>
                      {sortDir === 'asc' ? 'up' : sortDir === 'desc' ? 'down' : ''}
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayRows.length === 0 ? (
              <tr>
                <td colSpan={headers.length} className="p-8 text-center text-muted-foreground">
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              displayRows.map((row, i) => (
                <tr
                  key={i}
                  className={`border-b border-border/50 hover:bg-muted/30 transition-colors ${
                    onRowClick ? 'cursor-pointer' : ''
                  }`}
                  onClick={onRowClick ? () => onRowClick(i) : undefined}
                >
                  {row.map((cell, j) => (
                    <td key={j} className="p-2 md:p-3 whitespace-nowrap max-w-[240px]">
                      <div className="flex items-center gap-1.5 overflow-hidden">
                        <span className="truncate">{cell}</span>
                        {copyableColumns?.includes(j) && cell && (
                          <button
                            onClick={(e) => { e.stopPropagation(); copyCell(cell); }}
                            className="text-[10px] opacity-30 hover:opacity-100 transition-opacity text-muted-foreground"
                            title="Copy to clipboard"
                            aria-label="Copy value"
                          >
                            ⧉
                          </button>
                        )}
                      </div>
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function CodeBlock({ code, label }: { code: string; label?: string }) {
  return (
    <div>
      {label && <div className="text-xs text-muted-foreground mb-1">{label}</div>}
      <pre className="bg-muted/50 rounded-lg p-3 text-xs font-mono overflow-auto max-h-60 border border-border">
        {code}
      </pre>
    </div>
  );
}

export function KVList({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {items.map(([k, v]) => (
        <div key={k} className="flex flex-col min-w-0 overflow-hidden">
          <span className="text-xs text-muted-foreground truncate">{k}</span>
          <span className="font-mono text-sm font-semibold break-all">{v}</span>
        </div>
      ))}
    </div>
  );
}

export function EntityInput({
  onSubmit,
  placeholder = 'Entity ID or address...',
  defaultValue,
  samples,
}: {
  onSubmit: (id: string) => void;
  placeholder?: string;
  defaultValue?: string;
  samples?: string[]; // quick-fill sample entity IDs
}) {
  const [val, setVal] = useState(defaultValue || '');
  return (
    <div className="space-y-2">
      <form
        onSubmit={e => { e.preventDefault(); onSubmit(val); }}
        className="flex gap-2"
      >
        <input
          type="text"
          value={val}
          onChange={e => setVal(e.target.value)}
          placeholder={placeholder}
          aria-label="Entity ID or address"
          className="flex-1 px-3 py-2 rounded-lg border border-border bg-input text-sm font-mono"
        />
        <button
          type="submit"
          className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90"
        >
          Load
        </button>
      </form>
      {samples && samples.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Try:</span>
          {samples.map((s, i) => (
            <button
              key={i}
              onClick={() => { setVal(s); onSubmit(s); }}
              className="px-2 py-1 rounded text-xs font-mono bg-muted hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
              title={s}
            >
              {s.slice(0, 10)}...{s.slice(-4)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <div
      className="border-2 border-muted border-t-primary rounded-full animate-spin"
      style={{ width: size, height: size }}
    />
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
      <div className="text-4xl mb-2 opacity-30">N/A</div>
      <div className="text-sm">{message}</div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// Phase 3.2: Loading & Error States
// ════════════════════════════════════════════════════════════════════════════

export function Skeleton({ className = '', count = 1 }: { className?: string; count?: number }) {
  // Render `count` skeleton bars stacked vertically - useful for lists/tables
  if (count > 1) {
    return (
      <div className="space-y-2">
        {Array.from({ length: count }).map((_, i) => (
          <div key={i} className={`animate-pulse bg-muted rounded ${className || 'h-4 w-full'}`} />
        ))}
      </div>
    );
  }
  return <div className={`animate-pulse bg-muted rounded ${className || 'h-4 w-full'}`} />;
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  // A full Card skeleton for dashboard loading states
  return (
    <div className="bg-card rounded-2xl border border-border shadow-sm p-5">
      <div className="flex items-center justify-between mb-4">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-3 w-12" />
      </div>
      <div className="space-y-3">
        {Array.from({ length: lines }).map((_, i) => (
          <Skeleton key={i} className={`h-4 ${i === 0 ? 'w-full' : i === 1 ? 'w-5/6' : 'w-4/6'}`} />
        ))}
      </div>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
  type,
}: {
  message: string;
  onRetry?: () => void;
  type?: 'network' | 'timeout' | 'invalid_json' | 'server' | 'aborted';
}) {
  const icon = type === 'timeout' ? '⏱' : type === 'server' ? '⚠' : type === 'network' ? '📡' : '⚠';
  const label = type
    ? `${type.toUpperCase()} ERROR`
    : 'ERROR';
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center py-12 px-4 text-center"
    >
      <div className="text-4xl mb-3 opacity-50" aria-hidden>{icon}</div>
      <div className="text-xs font-mono uppercase tracking-wider text-red-500 mb-2">{label}</div>
      <div className="text-sm text-muted-foreground mb-4 max-w-md break-words">{message}</div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:opacity-90 transition-opacity"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function LoadingState({ message = 'Loading...' }: { message?: string }) {
  return (
    <div className="flex items-center justify-center py-12 text-muted-foreground">
      <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin mr-3" />
      <span className="text-sm">{message}</span>
    </div>
  );
}

export function Tag({ children, color = 'default' }: { children: React.ReactNode; color?: 'default' | 'green' | 'amber' | 'red' | 'blue' }) {
  const colors = {
    default: 'bg-muted text-muted-foreground',
    green: 'bg-green-500/10 text-green-600',
    amber: 'bg-amber-500/10 text-amber-600',
    red: 'bg-red-500/10 text-red-600',
    blue: 'bg-blue-500/10 text-blue-600',
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-mono ${colors[color]}`}>
      {children}
    </span>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// STREAMING - BH/signal live stream visualization
// ════════════════════════════════════════════════════════════════════════════

export function StreamView({
  items,
  speedMs,
  columns,
  title = 'Live Stream',
}: {
  items: any[];
  speedMs: number;
  columns: { key: string; label: string; render?: (v: any, row: any) => React.ReactNode }[];
  title?: string;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-3 text-xs">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
          </span>
          <span className="text-muted-foreground">{items.length} records buffered</span>
        </div>
        <div className="flex items-center gap-3 font-mono">
          <span className="text-green-500" title="API round-trip latency (not BH computation speed)">⚡ API {ms(speedMs)}</span>
          <span className="text-muted-foreground">{(1000 / Math.max(speedMs, 1)).toFixed(0)} Hz</span>
        </div>
      </div>
      <div className="stream-line h-0.5 bg-border rounded mb-2" />
      <div className="overflow-auto max-h-80">
        <table className="w-full text-xs">
          <thead className="bg-muted/50 sticky top-0">
            <tr>
              {columns.map(c => (
                <th key={c.key} className="text-left p-2 font-semibold text-muted-foreground whitespace-nowrap">
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={columns.length} className="p-6 text-center text-muted-foreground">Awaiting data...</td></tr>
            ) : (
              items.map((row, i) => (
                <tr key={i} className="border-b border-border/30 hover:bg-muted/30">
                  {columns.map(c => (
                    <td key={c.key} className="p-2 whitespace-nowrap max-w-[200px]">
                      <span className="truncate inline-block max-w-full">
                        {c.render ? c.render(row[c.key], row) : String(row[c.key] ?? 'N/A')}
                      </span>
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// ARCHITECTURE FLOW DIAGRAM (SVG)
// ════════════════════════════════════════════════════════════════════════════

export function ArchitectureFlow({ compact: compactMode }: { compact?: boolean }) {
  const height = compactMode ? 360 : 520;
  return (
    <svg viewBox="0 0 900 520" className="w-full h-auto" style={{ maxHeight: height }}>
      <defs>
        <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.2" />
          <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0.2" />
        </linearGradient>
        <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
          <path d="M0,0 L0,6 L9,3 z" fill="currentColor" />
        </marker>
        <filter id="glow">
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Chain sources */}
      <text x="60" y="30" className="fill-muted-foreground text-[10px] font-semibold">CHAIN SOURCES (100+)</text>
      {['EVM', 'SVM', 'Cosmos', 'Move', 'Substrate', 'UTXO'].map((vm, i) => (
        <g key={vm}>
          <rect x="20" y={50 + i * 30} width="100" height="22" rx="4" fill="url(#grad1)" stroke="#3b82f6" strokeOpacity="0.4" />
          <text x="70" y={65 + i * 30} textAnchor="middle" className="fill-foreground text-[10px] font-mono">{vm}</text>
        </g>
      ))}

      {/* Rust Indexers */}
      <g>
        <rect x="160" y="100" width="120" height="100" rx="8" fill="url(#grad1)" stroke="#3b82f6" strokeOpacity="0.6" filter="url(#glow)" />
        <text x="220" y="125" textAnchor="middle" className="fill-foreground text-[11px] font-semibold">RUST INDEXERS</text>
        <text x="220" y="145" textAnchor="middle" className="fill-muted-foreground text-[9px]">16 crates</text>
        <text x="220" y="160" textAnchor="middle" className="fill-muted-foreground text-[9px]">128 chains</text>
        <text x="220" y="175" textAnchor="middle" className="fill-muted-foreground text-[9px]">18 VM families</text>
        <text x="220" y="190" textAnchor="middle" className="fill-green-500 text-[9px] font-mono">LIVE</text>
      </g>

      {/* Arrow chain -> indexer */}
      <line x1="120" y1="150" x2="160" y2="150" stroke="currentColor" strokeWidth="1.5" markerEnd="url(#arrow)" className="text-muted-foreground" />

      {/* BH Primitive */}
      <g>
        <rect x="310" y="100" width="120" height="100" rx="8" fill="url(#grad1)" stroke="#8b5cf6" strokeOpacity="0.6" filter="url(#glow)" />
        <text x="370" y="125" textAnchor="middle" className="fill-foreground text-[11px] font-semibold">BH L0.1</text>
        <text x="370" y="145" textAnchor="middle" className="fill-muted-foreground text-[9px]">93-byte payload</text>
        <text x="370" y="160" textAnchor="middle" className="fill-muted-foreground text-[9px]">SHA3-256 dual-strand</text>
        <text x="370" y="175" textAnchor="middle" className="fill-muted-foreground text-[9px]">XOR invariant</text>
        <text x="370" y="190" textAnchor="middle" className="fill-green-500 text-[9px] font-mono">0.006ms</text>
      </g>

      <line x1="280" y1="150" x2="310" y2="150" stroke="currentColor" strokeWidth="1.5" markerEnd="url(#arrow)" className="text-muted-foreground" />

      {/* Five Planes */}
      <text x="540" y="30" textAnchor="middle" className="fill-muted-foreground text-[10px] font-semibold">FIVE-PLANE COHERENCE Coherence</text>
      {[
        { name: 'Phi Physical', color: '#ef4444', y: 50 },
        { name: 'M Mental', color: '#f59e0b', y: 95 },
        { name: 'Sigma Spiritual', color: '#10b981', y: 140 },
        { name: 'K Conscious', color: '#3b82f6', y: 185 },
        { name: 'A ANIMA', color: '#8b5cf6', y: 230 },
      ].map(plane => (
        <g key={plane.name}>
          <rect x="470" y={plane.y} width="140" height="32" rx="6" fill={plane.color} fillOpacity="0.15" stroke={plane.color} strokeOpacity="0.5" />
          <text x="540" y={plane.y + 20} textAnchor="middle" className="fill-foreground text-[10px] font-mono">{plane.name}</text>
        </g>
      ))}

      <line x1="430" y1="150" x2="470" y2="150" stroke="currentColor" strokeWidth="1.5" markerEnd="url(#arrow)" className="text-muted-foreground" />

      {/* Coherence Engine */}
      <g>
        <rect x="650" y="80" width="140" height="60" rx="8" fill="url(#grad1)" stroke="#3b82f6" strokeOpacity="0.6" filter="url(#glow)" />
        <text x="720" y="105" textAnchor="middle" className="fill-foreground text-[11px] font-semibold">COHERENCE Coherence</text>
        <text x="720" y="125" textAnchor="middle" className="fill-muted-foreground text-[9px]">11 weight profiles</text>
      </g>

      <line x1="610" y1="150" x2="650" y2="110" stroke="currentColor" strokeWidth="1.5" markerEnd="url(#arrow)" className="text-muted-foreground" />

      {/* Master Equation Master Signal */}
      <g>
        <rect x="810" y="80" width="80" height="60" rx="8" fill="#3b82f6" fillOpacity="0.3" stroke="#3b82f6" filter="url(#glow)" />
        <text x="850" y="105" textAnchor="middle" className="fill-foreground text-[10px] font-bold">Master Signal</text>
        <text x="850" y="120" textAnchor="middle" className="fill-muted-foreground text-[8px]">Master Eq.</text>
        <text x="850" y="132" textAnchor="middle" className="fill-muted-foreground text-[8px]">C-e^M_moat</text>
      </g>

      <line x1="790" y1="110" x2="810" y2="110" stroke="currentColor" strokeWidth="1.5" markerEnd="url(#arrow)" className="text-muted-foreground" />

      {/* Signal Factory */}
      <g>
        <rect x="650" y="170" width="140" height="60" rx="8" fill="url(#grad1)" stroke="#8b5cf6" strokeOpacity="0.6" filter="url(#glow)" />
        <text x="720" y="195" textAnchor="middle" className="fill-foreground text-[11px] font-semibold">SIGNAL FACTORY</text>
        <text x="720" y="215" textAnchor="middle" className="fill-muted-foreground text-[9px]">24 signal types</text>
      </g>

      <line x1="610" y1="200" x2="650" y2="200" stroke="currentColor" strokeWidth="1.5" markerEnd="url(#arrow)" className="text-muted-foreground" />

      {/* Relayer */}
      <g>
        <rect x="810" y="170" width="80" height="60" rx="8" fill="url(#grad1)" stroke="#10b981" strokeOpacity="0.6" filter="url(#glow)" />
        <text x="850" y="195" textAnchor="middle" className="fill-foreground text-[10px] font-semibold">RELAYER</text>
        <text x="850" y="215" textAnchor="middle" className="fill-muted-foreground text-[8px]">KMS-backed</text>
      </g>

      <line x1="790" y1="200" x2="810" y2="200" stroke="currentColor" strokeWidth="1.5" markerEnd="url(#arrow)" className="text-muted-foreground" />

      {/* On-chain */}
      <g>
        <rect x="650" y="260" width="240" height="60" rx="8" fill="#10b981" fillOpacity="0.2" stroke="#10b981" strokeOpacity="0.6" filter="url(#glow)" />
        <text x="770" y="285" textAnchor="middle" className="fill-foreground text-[11px] font-semibold">ON-CHAIN (0G + 100+ CHAINS)</text>
        <text x="770" y="305" textAnchor="middle" className="fill-muted-foreground text-[9px]">TRIONExecutionGate - TRIONOracleV3 - BTCPRoute</text>
      </g>

      <line x1="850" y1="230" x2="850" y2="260" stroke="currentColor" strokeWidth="1.5" markerEnd="url(#arrow)" className="text-muted-foreground" />

      {/* Akashic Records (bottom) */}
      <g>
        <rect x="160" y="280" width="430" height="80" rx="8" fill="url(#grad1)" stroke="#8b5cf6" strokeOpacity="0.4" />
        <text x="375" y="305" textAnchor="middle" className="fill-foreground text-[11px] font-semibold">AKASHIC RECORDS (L2)</text>
        <text x="375" y="325" textAnchor="middle" className="fill-muted-foreground text-[9px]">Append-only BH ledger - FAISS 128-dim - 531K+ vectors - BEO entity resolution</text>
        <text x="375" y="345" textAnchor="middle" className="fill-green-500 text-[9px] font-mono">TimescaleDB + SQLite fallback</text>
      </g>

      <line x1="370" y1="200" x2="370" y2="280" stroke="currentColor" strokeWidth="1.5" markerEnd="url(#arrow)" className="text-muted-foreground" />
      <line x1="220" y1="200" x2="220" y2="280" stroke="currentColor" strokeWidth="1.5" markerEnd="url(#arrow)" className="text-muted-foreground" />

      {/* Governance row */}
      <g>
        <rect x="20" y="380" width="860" height="120" rx="8" fill="url(#grad1)" stroke="#f59e0b" strokeOpacity="0.3" />
        <text x="450" y="405" textAnchor="middle" className="fill-foreground text-[11px] font-semibold">GOVERNANCE & NOVEL PRIMITIVES (L4-L9)</text>

        {['BIRP', 'BIBL', 'BTCP', 'SBA', 'Gratitude', 'Love F', 'ACP*6', 'Falsifiability*15', 'Slashing*5', 'Adaptive Consensus'].map((g, i) => (
          <g key={g}>
            <rect x={40 + i * 85} y="420" width="75" height="22" rx="4" fill="#f59e0b" fillOpacity="0.15" stroke="#f59e0b" strokeOpacity="0.4" />
            <text x={77 + i * 85} y="435" textAnchor="middle" className="fill-foreground text-[9px] font-mono">{g}</text>
          </g>
        ))}

        <text x="450" y="465" textAnchor="middle" className="fill-muted-foreground text-[9px]">
          AWA Ceremony - Right to Invisibility - Elder Wisdom - Unknown-Unknown Provision - Public Good Charter
        </text>
        <text x="450" y="485" textAnchor="middle" className="fill-green-500 text-[9px] font-mono">
          All systems operational - 472 tests passing
        </text>
      </g>
    </svg>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// PLANE VISUALIZATION - Five-plane coherence chart
// ════════════════════════════════════════════════════════════════════════════

export function PlaneGauge({
  label,
  value,
  threshold,
  color,
  icon,
}: {
  label: string;
  value: number;
  threshold: number;
  color: string;
  icon?: string;
}) {
  const pct = Math.max(0, Math.min(1, value));
  const passes = value >= threshold;
  const circumference = 2 * Math.PI * 36;
  const offset = circumference * (1 - pct);

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-24 h-24">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 80 80">
          <circle cx="40" cy="40" r="36" fill="none" stroke="currentColor" strokeWidth="4" className="text-muted" />
          <circle
            cx="40" cy="40" r="36" fill="none" stroke={color} strokeWidth="4"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            className="transition-all duration-700"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className="text-lg font-bold">{(pct * 100).toFixed(0)}%</div>
          {icon && <div className="text-xs">{icon}</div>}
        </div>
      </div>
      <div className="text-xs font-semibold mt-2 truncate max-w-[120px] text-center">{label}</div>
      <div className={`text-xs ${passes ? 'text-green-500' : 'text-red-500'}`}>
        threshold={threshold.toFixed(2)} {passes ? 'pass' : 'fail'}
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// LIVE CLOCK
// ════════════════════════════════════════════════════════════════════════════

export function LiveClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const i = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(i);
  }, []);
  return <span className="font-mono text-xs">{now.toLocaleTimeString('en-US', { hour12: false })} UTC</span>;
}
