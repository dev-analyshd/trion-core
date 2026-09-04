"use client";

import { useState } from "react";
import {
  Activity,
  Boxes,
  BrainCircuit,
  Cpu,
  Gauge,
  Globe2,
  HeartHandshake,
  Radar,
  ShieldCheck,
  Waves,
} from "lucide-react";
import { CHAIN_COUNT, VM_FAMILY_COUNT } from "@/lib/trion/client";

export interface TrionViewMeta {
  id: string;
  label: string;
  icon: React.ComponentType<{ size?: number | string; className?: string }>;
  group: string;
  blurb: string;
}

export const TRION_VIEWS: TrionViewMeta[] = [
  { id: "overview", label: "Command Center", icon: Gauge, group: "PROTOCOL", blurb: "T(t) master equation, live pipeline state, signal publication" },
  { id: "signals", label: "Signal Feed", icon: Activity, group: "PROTOCOL", blurb: "Live behavioral signals and truth stream" },
  { id: "btcp", label: "BTCP Zero-Bridge", icon: Waves, group: "CROSS-CHAIN", blurb: "Route selection, BIBL engine, escrow state channels" },
  { id: "chains", label: "Chain Coverage", icon: Globe2, group: "CROSS-CHAIN", blurb: `${CHAIN_COUNT} networks · ${VM_FAMILY_COUNT} VM families · indexer status` },
  { id: "coherence", label: "Five-Plane Coherence", icon: BrainCircuit, group: "TRUTH ENGINE", blurb: "C(t)=α·Φ+β·M+γ·Σ+δ·K+ε·A with 11 asset profiles" },
  { id: "security", label: "Security & Consensus", icon: ShieldCheck, group: "TRUTH ENGINE", blurb: "DW-BFT, HHI monitor, manipulation firewall, sybil resistance" },
  { id: "governance", label: "Governance & AWA", icon: HeartHandshake, group: "CIVILIZATION", blurb: "AWA enforcement, Love Protocol, Akashic memory" },
  { id: "primitives", label: "HashDNA Primitives", icon: Cpu, group: "CIVILIZATION", blurb: "Behavioral hashing, genomic keys, thermodynamic deletion" },
  { id: "explorer", label: "Entity Explorer", icon: Radar, group: "CIVILIZATION", blurb: "Behavioral hash ledger search and entity resolution" },
];

export function Sidebar({
  active,
  onSelect,
  mobileOpen,
  onCloseMobile,
}: {
  active: string;
  onSelect: (id: string) => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  const groups = [...new Set(TRION_VIEWS.map((v) => v.group))];
  const [hovered, setHovered] = useState<string | null>(null);

  return (
    <>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={onCloseMobile}
          aria-hidden
        />
      )}
      <nav
        aria-label="TRION primary navigation"
        className={`
          fixed inset-y-0 left-0 z-50 flex w-60 flex-col border-r border-[#1c232d] bg-[#0a0d12]
          transition-transform duration-200 lg:static lg:translate-x-0
          ${mobileOpen ? "translate-x-0" : "-translate-x-full"}
        `}
      >
        {/* Brand */}
        <div className="flex h-14 items-center gap-2.5 border-b border-[#1c232d] px-4">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-[#10b981] to-[#059669]">
            <span className="trion-mono text-[13px] font-bold text-[#07130d]">T</span>
          </div>
          <div className="leading-tight">
            <div className="trion-mono text-[13px] font-bold tracking-wider text-[#d7dde6]">
              TRION<span className="text-[#10b981]">·</span>CORE
            </div>
            <div className="text-[9px] uppercase tracking-[0.18em] text-[#4b5563]">
              Behavioral Truth Infra
            </div>
          </div>
        </div>

        {/* Nav groups */}
        <div className="flex-1 overflow-y-auto px-2 py-3 space-y-4">
          {groups.map((group) => (
            <div key={group}>
              <div className="px-3 pb-1.5 trion-label">{group}</div>
              <div className="space-y-0.5">
                {TRION_VIEWS.filter((v) => v.group === group).map((v) => {
                  const Icon = v.icon;
                  const isActive = active === v.id;
                  const isHovered = hovered === v.id;
                  return (
                    <button
                      key={v.id}
                      onClick={() => {
                        onSelect(v.id);
                        onCloseMobile();
                      }}
                      onMouseEnter={() => setHovered(v.id)}
                      onMouseLeave={() => setHovered(null)}
                      aria-current={isActive ? "page" : undefined}
                      className={`
                        group relative flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left
                        transition-colors duration-100
                        ${isActive
                          ? "bg-[#10b98112] text-[#34d399]"
                          : isHovered
                            ? "bg-[#ffffff06] text-[#d7dde6]"
                            : "text-[#7d8896]"}
                      `}
                    >
                      {isActive && (
                        <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r bg-[#10b981]" />
                      )}
                      <Icon size={15} />
                      <span className="text-[12.5px] font-medium">{v.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {/* Footer badges */}
        <div className="border-t border-[#1c232d] p-3 space-y-2">
          <div className="flex items-center gap-2">
            <Boxes size={12} className="text-[#4b5563]" />
            <span className="trion-mono text-[10px] text-[#4b5563]">
              {`${CHAIN_COUNT} CHAINS · ${VM_FAMILY_COUNT} VMs`}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="trion-live-dot" />
            <span className="trion-mono text-[10px] text-[#4b5563]">
              CC0 · v2.0.0 · ORACLE LIVE
            </span>
          </div>
        </div>
      </nav>
    </>
  );
}
