'use client';

/**
 * TRION Settings Modal — API key management.
 *
 * Phase 5.4: Opens from the header settings icon. Stores an API key in
 * localStorage. The fetchAPI client automatically adds the X-API-Key header
 * to POST requests when a key is present.
 *
 * Usage:
 *   <SettingsModal open={open} onClose={() => setOpen(false)} />
 */
import { useState, useEffect } from 'react';
import * as Icons from 'lucide-react';

const STORAGE_KEY = 'trion-api-key';

export function SettingsModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [apiKey, setApiKey] = useState('');
  const [saved, setSaved] = useState(false);
  const [showKey, setShowKey] = useState(false);

  useEffect(() => {
    if (open) {
      const k = localStorage.getItem(STORAGE_KEY) || '';
      setApiKey(k);
      setSaved(false);
    }
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const save = () => {
    if (apiKey.trim()) {
      localStorage.setItem(STORAGE_KEY, apiKey.trim());
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
    setSaved(true);
    setTimeout(() => {
      setSaved(false);
      onClose();
    }, 800);
  };

  const clear = () => {
    localStorage.removeItem(STORAGE_KEY);
    setApiKey('');
    setSaved(true);
    setTimeout(() => setSaved(false), 800);
  };

  const hasKey = !!localStorage.getItem(STORAGE_KEY);

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center px-4"
      role="dialog"
      aria-modal="true"
      aria-label="Settings"
    >
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative w-full max-w-md bg-card border border-border rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Icons.Settings className="w-5 h-5 text-muted-foreground" />
            <h2 className="font-semibold">Settings</h2>
          </div>
          <button
            onClick={onClose}
            aria-label="Close settings"
            className="p-1 rounded hover:bg-accent text-muted-foreground"
          >
            <Icons.X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4">
          <div>
            <label className="text-xs text-muted-foreground font-mono uppercase tracking-wider mb-2 block">
              API Key (write operations)
            </label>
            <div className="flex gap-2">
              <div className="flex-1 relative">
                <input
                  type={showKey ? 'text' : 'password'}
                  value={apiKey}
                  onChange={e => { setApiKey(e.target.value); setSaved(false); }}
                  placeholder="Paste your TRION API key…"
                  className="w-full px-3 py-2 pr-10 rounded-lg border border-border bg-input text-sm font-mono"
                  aria-label="API key"
                />
                <button
                  type="button"
                  onClick={() => setShowKey(v => !v)}
                  aria-label={showKey ? 'Hide key' : 'Show key'}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground"
                >
                  {showKey ? <Icons.EyeOff className="w-4 h-4" /> : <Icons.Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              Stored in your browser&apos;s localStorage. Added as <code className="font-mono px-1 py-0.5 rounded bg-muted">X-API-Key</code> header to all POST requests.
            </p>
          </div>

          <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/50">
            <div className={`w-2 h-2 rounded-full ${hasKey ? 'bg-green-500' : 'bg-muted-foreground'}`} />
            <span className="text-xs">
              {hasKey ? 'Write operations enabled' : 'Read-only mode (no key set)'}
            </span>
          </div>

          {saved && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-green-500/10 border border-green-500/30 text-green-600 text-sm">
              <Icons.CheckCircle className="w-4 h-4" />
              Saved
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-between gap-2 px-5 py-4 border-t border-border">
          <button
            onClick={clear}
            className="text-xs text-muted-foreground hover:text-red-500 transition-colors"
          >
            Clear key
          </button>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={save}
              className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:opacity-90 transition-opacity"
            >
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
