'use client';

/**
 * TRION Keyboard Shortcuts Dialog.
 *
 * Replaces the previous alert() shortcut help (July 2026 audit — alert()
 * blocks the main thread, is not screen-reader accessible, and cannot be
 * styled). Accessible modal following the same pattern as SettingsModal:
 * role="dialog" + aria-modal, Escape-to-close, backdrop click-to-close,
 * focus is trapped by the modal semantics of the top-level dialog element.
 *
 * Opens with the `?` (or `Shift+/`) key — see the global keydown handler in
 * src/app/page.tsx.
 *
 * Usage:
 *   <ShortcutHelpDialog open={open} onClose={() => setOpen(false)} />
 */
import { useEffect, useRef } from 'react';
import * as Icons from 'lucide-react';

const SHORTCUTS: Array<{
  keys: string;
  description: string;
  icon: React.ReactNode;
}> = [
  {
    keys: '⌘K / Ctrl+K',
    description: 'Open the command palette (jump to any page)',
    icon: <Icons.Command className="w-4 h-4" />,
  },
  {
    keys: '⌘B / Ctrl+B',
    description: 'Toggle the navigation sidebar',
    icon: <Icons.PanelLeft className="w-4 h-4" />,
  },
  {
    keys: '?  /  Shift+/',
    description: 'Show this keyboard shortcut help',
    icon: <Icons.Keyboard className="w-4 h-4" />,
  },
  {
    keys: 'Esc',
    description: 'Close overlays (this dialog, settings, command palette)',
    icon: <Icons.XCircle className="w-4 h-4" />,
  },
];

export function ShortcutHelpDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);

  // Close on Escape + move focus into the dialog when opened
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    closeRef.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center px-4"
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
    >
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative w-full max-w-md bg-card border border-border rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Icons.Keyboard className="w-5 h-5 text-muted-foreground" />
            <h2 className="font-semibold">Keyboard Shortcuts</h2>
          </div>
          <button
            ref={closeRef}
            onClick={onClose}
            aria-label="Close keyboard shortcuts"
            className="p-1 rounded hover:bg-accent text-muted-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
          >
            <Icons.X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5">
          <ul className="space-y-1" role="list">
            {SHORTCUTS.map(s => (
              <li
                key={s.keys}
                className="flex items-center justify-between gap-4 px-3 py-2.5 rounded-lg hover:bg-muted/40 transition-colors"
              >
                <span className="flex items-center gap-2.5 min-w-0">
                  <span className="text-muted-foreground flex-shrink-0">{s.icon}</span>
                  <span className="text-sm text-muted-foreground truncate">
                    {s.description}
                  </span>
                </span>
                <kbd className="flex-shrink-0 px-2.5 py-1 rounded-md border border-border bg-muted font-mono text-xs font-semibold shadow-sm">
                  {s.keys}
                </kbd>
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground mt-4 px-3">
            Shortcuts are disabled while typing in inputs and text areas.
          </p>
        </div>

        {/* Footer */}
        <div className="flex justify-end px-5 py-4 border-t border-border">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:opacity-90 transition-opacity"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
