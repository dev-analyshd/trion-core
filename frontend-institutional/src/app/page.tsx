"use client";

import { useCallback, useEffect, useState } from "react";
import { Sidebar, TRION_VIEWS } from "@/components/trion/shell/Sidebar";
import { TopBar } from "@/components/trion/shell/TopBar";
import { useTrionPoll } from "@/lib/trion/hooks";
import type { TrionHealth } from "@/lib/trion/client";

import { OverviewView } from "@/components/trion/views/OverviewView";
import { SignalsView } from "@/components/trion/views/SignalsView";
import { BtcpView } from "@/components/trion/views/BtcpView";
import { ChainsView } from "@/components/trion/views/ChainsView";
import { CoherenceView } from "@/components/trion/views/CoherenceView";
import { SecurityView } from "@/components/trion/views/SecurityView";
import { GovernanceView } from "@/components/trion/views/GovernanceView";
import { PrimitivesView } from "@/components/trion/views/PrimitivesView";
import { ExplorerView } from "@/components/trion/views/ExplorerView";

const VIEW_MAP: Record<string, React.ComponentType> = {
  overview: OverviewView,
  signals: SignalsView,
  btcp: BtcpView,
  chains: ChainsView,
  coherence: CoherenceView,
  security: SecurityView,
  governance: GovernanceView,
  primitives: PrimitivesView,
  explorer: ExplorerView,
};

export default function Home() {
  const [active, setActive] = useState<string>("overview");
  const [mobileOpen, setMobileOpen] = useState(false);

  // Hash-synced view routing (#/btcp etc.) — deep-linkable views.
  useEffect(() => {
    const fromHash = () => {
      const id = window.location.hash.replace(/^#\/?/, "");
      if (id && VIEW_MAP[id]) setActive(id);
    };
    fromHash();
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
  }, []);

  const selectView = useCallback((id: string) => {
    setActive(id);
    window.location.hash = `/${id}`;
  }, []);

  const { data: health, error: healthError } = useTrionPoll<TrionHealth>("health", 5000);

  const ActiveView = VIEW_MAP[active] ?? OverviewView;
  const meta = TRION_VIEWS.find((v) => v.id === active);

  return (
    <div className="trion-app min-h-screen flex flex-col">
      <div className="flex flex-1 min-h-0">
        <div className="flex w-full min-w-0">
          <Sidebar
            active={active}
            onSelect={selectView}
            mobileOpen={mobileOpen}
            onCloseMobile={() => setMobileOpen(false)}
          />
          <div className="flex min-w-0 flex-1 flex-col">
            <TopBar
              health={health}
              healthError={healthError ?? null}
              onMenu={() => setMobileOpen(true)}
              viewLabel={meta?.label ?? "Command Center"}
            />
            <main className="relative flex-1 overflow-y-auto min-w-0">
              <div className="trion-grid-bg pointer-events-none absolute inset-0" aria-hidden />
              <div className="relative p-3 sm:p-5 pb-10">
                <ActiveView />
              </div>
            </main>
          </div>
        </div>
      </div>

      {/* Sticky institutional status footer */}
      <footer className="mt-auto shrink-0 border-t border-[#1c232d] bg-[#0a0d12]">
        <div className="flex items-center gap-4 px-4 h-9 overflow-hidden">
          <div className="flex shrink-0 items-center gap-2">
            <div className="trion-live-dot" />
            <span className="trion-label hidden sm:inline">Live</span>
          </div>
          <div className="min-w-0 flex-1 overflow-hidden" aria-hidden>
            <div className="trion-ticker trion-mono text-[10px] text-[#7d8896]">
              {[
                `ORACLE ${health?.oracle ?? "TRION Protocol v2.0.0"}`,
                `NETWORK ${health?.network ?? "arbitrum-sepolia"}`,
                `Θ ${health ? (health.dynamic_threshold ?? 0).toFixed(3) : "—"}`,
                `VOLATILITY V ${health ? (health.market_volatility ?? 0).toFixed(3) : "—"}`,
                `CHAIN_ID ${health?.chain_id ?? "—"}`,
                `VAULT ${health?.vault ?? "—"}`,
                `BTCP ZERO-BRIDGE · BIBL 3-TIER · <200MS`,
                `174 CHAINS · 22 VM FAMILIES`,
                `C(t)=α·Φ+β·M+γ·Σ+δ·K+ε·A`,
                `T(t)=[C≥Θ]·C·e^M`,
                `MOAT=D·Q·R·X·F·N`,
                `DW-BFT · d_j=1−corr(M_j,M̄)`,
                `HASHDNA · 93-BYTE CANONICAL BH`,
                `CC0 PUBLIC DOMAIN · TRION PROTOCOL`,
              ].join("   ·   ")}
              {[
                `ORACLE ${health?.oracle ?? "TRION Protocol v2.0.0"}`,
                `NETWORK ${health?.network ?? "arbitrum-sepolia"}`,
                `Θ ${health ? (health.dynamic_threshold ?? 0).toFixed(3) : "—"}`,
                `VOLATILITY V ${health ? (health.market_volatility ?? 0).toFixed(3) : "—"}`,
                `CHAIN_ID ${health?.chain_id ?? "—"}`,
                `VAULT ${health?.vault ?? "—"}`,
                `BTCP ZERO-BRIDGE · BIBL 3-TIER · <200MS`,
                `174 CHAINS · 22 VM FAMILIES`,
                `C(t)=α·Φ+β·M+γ·Σ+δ·K+ε·A`,
                `T(t)=[C≥Θ]·C·e^M`,
                `MOAT=D·Q·R·X·F·N`,
                `DW-BFT · d_j=1−corr(M_j,M̄)`,
                `HASHDNA · 93-BYTE CANONICAL BH`,
                `CC0 PUBLIC DOMAIN · TRION PROTOCOL`,
              ].join("   ·   ")}
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
