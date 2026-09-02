"use client";

import { useEffect, useState } from "react";
import { Menu, Wifi, WifiOff } from "lucide-react";
import type { TrionHealth } from "@/lib/trion/client";

export function TopBar({
  health,
  healthError,
  onMenu,
  viewLabel,
}: {
  health: TrionHealth | null;
  healthError: string | null;
  onMenu: () => void;
  viewLabel: string;
}) {
  const [clock, setClock] = useState<string>(() =>
    new Date().toLocaleTimeString("en-GB", { hour12: false })
  );

  useEffect(() => {
    const t = setInterval(
      () => setClock(new Date().toLocaleTimeString("en-GB", { hour12: false })),
      1000
    );
    return () => clearInterval(t);
  }, []);

  const status = health?.status;
  const online = !healthError && !!health;

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-[#1c232d] bg-[#0a0d12]/95 px-3 backdrop-blur sm:px-5">
      <button
        onClick={onMenu}
        className="flex h-9 w-9 items-center justify-center rounded-md text-[#7d8896] hover:bg-[#ffffff08] lg:hidden"
        aria-label="Open navigation"
      >
        <Menu size={18} />
      </button>

      <div className="min-w-0">
        <div className="trion-label hidden sm:block">Current View</div>
        <div className="truncate text-[13px] font-semibold text-[#d7dde6]">{viewLabel}</div>
      </div>

      <div className="ml-auto flex items-center gap-4 sm:gap-6">
        {/* Oracle identity */}
        <div className="hidden md:block text-right leading-tight">
          <div className="trion-label">Sensing Oracle</div>
          <div className="trion-mono text-[11px] text-[#34d399]">
            {health?.oracle ?? "TRION v2"}
          </div>
        </div>

        {/* Network */}
        <div className="hidden sm:block text-right leading-tight">
          <div className="trion-label">Network</div>
          <div className="trion-mono text-[11px] text-[#d7dde6]">
            {health?.network ?? "—"}
          </div>
        </div>

        {/* Threshold */}
        <div className="hidden lg:block text-right leading-tight">
          <div className="trion-label">Θ Dynamic</div>
          <div className="trion-mono text-[11px] text-[#f59e0b]">
            {(health?.dynamic_threshold ?? 0).toFixed(3)}
          </div>
        </div>

        {/* Connection state */}
        <div className="flex items-center gap-2" role="status" aria-live="polite">
          {online ? (
            <>
              <Wifi size={14} className="text-[#10b981]" />
              <span className="trion-mono text-[10px] uppercase tracking-wider text-[#34d399] hidden sm:inline">
                {status ?? "online"}
              </span>
            </>
          ) : (
            <>
              <WifiOff size={14} className="text-[#f43f5e]" />
              <span className="trion-mono text-[10px] uppercase tracking-wider text-[#f43f5e] hidden sm:inline">
                backend offline
              </span>
            </>
          )}
        </div>

        <div className="trion-mono text-[12px] tabular-nums text-[#d7dde6] border border-[#1c232d] rounded px-2 py-1">
          {clock} UTC
        </div>
      </div>
    </header>
  );
}
