'use client';

/**
 * TRION Command Palette (⌘K / Ctrl+K)
 *
 * Phase 3.5: Fuzzy-search across all 80+ pages. Shows recently visited at top.
 * Arrow keys navigate, Enter selects, Esc closes.
 *
 * Usage:
 *   <CommandPalette
 *     pages={[{id, label, group}, ...]}
 *     onSelect={(id) => router.push(`/?page=${id}`)}
 *   />
 *
 * The palette auto-mounts a global keydown listener. Toggle with ⌘K / Ctrl+K.
 */
import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import * as Icons from 'lucide-react';

export interface CommandPalettePage {
  id: string;
  label: string;
  group: string;
}

export function CommandPalette({
  pages,
  onSelect,
}: {
  pages: CommandPalettePage[];
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIdx, setActiveIdx] = useState(0);
  const [recent, setRecent] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Load recent from localStorage
  useEffect(() => {
    try {
      const r = JSON.parse(localStorage.getItem('trion-recent-pages') || '[]');
      if (Array.isArray(r)) setRecent(r.slice(0, 5));
    } catch {
      // ignore
    }
  }, []);

  // Global keydown listener
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // ⌘K (Mac) or Ctrl+K (others)
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen(v => !v);
        return;
      }
      if (e.key === 'Escape' && open) {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  // Focus input when opened
  useEffect(() => {
    if (open) {
      setQuery('');
      setActiveIdx(0);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  // Filtered + scored results
  const results = useMemo(() => {
    if (!query.trim()) {
      // Show recent first when no query
      const recentPages = recent
        .map(id => pages.find(p => p.id === id))
        .filter((p): p is CommandPalettePage => !!p);
      const rest = pages.filter(p => !recent.includes(p.id));
      return [...recentPages, ...rest].slice(0, 50);
    }
    const q = query.toLowerCase();
    // Simple fuzzy: score by (a) exact prefix match, (b) substring match, (c) token match
    const scored = pages
      .map(p => {
        const label = p.label.toLowerCase();
        const id = p.id.toLowerCase();
        const group = p.group.toLowerCase();
        let score = 0;
        if (label.startsWith(q)) score += 100;
        if (label.includes(q)) score += 50;
        if (id.includes(q)) score += 30;
        if (group.includes(q)) score += 20;
        // Token match: query words appear in label
        const qTokens = q.split(/\s+/).filter(Boolean);
        const labelTokens = label.split(/\s+/);
        for (const qt of qTokens) {
          if (labelTokens.some(lt => lt.startsWith(qt))) score += 10;
        }
        return { page: p, score };
      })
      .filter(r => r.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 50)
      .map(r => r.page);
    return scored;
  }, [query, pages, recent]);

  // Reset active idx when results change
  useEffect(() => {
    setActiveIdx(0);
  }, [query]);

  // Scroll active item into view
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-idx="${activeIdx}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [activeIdx]);

  const select = useCallback((id: string) => {
    // Update recent
    setRecent(prev => {
      const next = [id, ...prev.filter(r => r !== id)].slice(0, 5);
      try { localStorage.setItem('trion-recent-pages', JSON.stringify(next)); } catch {}
      return next;
    });
    onSelect(id);
    setOpen(false);
  }, [onSelect]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[10vh] px-4"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={() => setOpen(false)}
      />

      {/* Palette */}
      <div className="relative w-full max-w-xl bg-card border border-border rounded-2xl shadow-2xl overflow-hidden">
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
          <Icons.Search className="w-5 h-5 text-muted-foreground flex-shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'ArrowDown') {
                e.preventDefault();
                setActiveIdx(i => Math.min(i + 1, results.length - 1));
              } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setActiveIdx(i => Math.max(i - 1, 0));
              } else if (e.key === 'Enter') {
                e.preventDefault();
                if (results[activeIdx]) select(results[activeIdx].id);
              }
            }}
            placeholder="Search pages... (⌘K to close)"
            className="flex-1 bg-transparent outline-none text-sm placeholder:text-muted-foreground"
          />
          <kbd className="text-xs text-muted-foreground font-mono px-2 py-1 rounded border border-border">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div ref={listRef} className="max-h-[60vh] overflow-y-auto py-2">
          {!query.trim() && recent.length > 0 && (
            <div className="px-2 pb-2">
              <div className="text-xs text-muted-foreground font-mono uppercase tracking-wider px-3 py-1">
                Recently Visited
              </div>
              {results.slice(0, recent.length).map((p, i) => (
                <PaletteItem
                  key={p.id}
                  page={p}
                  active={i === activeIdx}
                  onClick={() => select(p.id)}
                  idx={i}
                  isRecent
                />
              ))}
              <div className="text-xs text-muted-foreground font-mono uppercase tracking-wider px-3 py-1 mt-2">
                All Pages
              </div>
              {results.slice(recent.length).map((p, i) => (
                <PaletteItem
                  key={p.id}
                  page={p}
                  active={i + recent.length === activeIdx}
                  onClick={() => select(p.id)}
                  idx={i + recent.length}
                />
              ))}
            </div>
          )}
          {(query.trim() || recent.length === 0) && (
            <>
              {results.length === 0 ? (
                <div className="px-4 py-8 text-center text-sm text-muted-foreground">
                  No pages match &quot;{query}&quot;
                </div>
              ) : (
                results.map((p, i) => (
                  <PaletteItem
                    key={p.id}
                    page={p}
                    active={i === activeIdx}
                    onClick={() => select(p.id)}
                    idx={i}
                  />
                ))
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-2 border-t border-border text-xs text-muted-foreground">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <kbd className="font-mono px-1.5 py-0.5 rounded border border-border">updown</kbd>
              navigate
            </span>
            <span className="flex items-center gap-1">
              <kbd className="font-mono px-1.5 py-0.5 rounded border border-border">Enter</kbd>
              select
            </span>
            <span className="flex items-center gap-1">
              <kbd className="font-mono px-1.5 py-0.5 rounded border border-border">esc</kbd>
              close
            </span>
          </div>
          <span>{results.length} results</span>
        </div>
      </div>
    </div>
  );
}

function PaletteItem({
  page,
  active,
  onClick,
  idx,
  isRecent,
}: {
  page: CommandPalettePage;
  active: boolean;
  onClick: () => void;
  idx: number;
  isRecent?: boolean;
}) {
  return (
    <button
      data-idx={idx}
      onClick={onClick}
      onMouseEnter={() => {
        // Don't change activeIdx on hover - let keyboard nav own it
      }}
      className={`w-full flex items-center gap-3 px-3 py-2 text-left transition-colors ${
        active ? 'bg-accent text-accent-foreground' : 'hover:bg-muted/50'
      }`}
    >
      {isRecent ? (
        <Icons.Clock className="w-4 h-4 text-muted-foreground flex-shrink-0" />
      ) : (
        <Icons.FileText className="w-4 h-4 text-muted-foreground flex-shrink-0" />
      )}
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{page.label}</div>
        <div className="text-xs text-muted-foreground truncate">{page.group}</div>
      </div>
      {active && (
        <Icons.ChevronRight className="w-4 h-4 text-muted-foreground flex-shrink-0" />
      )}
    </button>
  );
}
