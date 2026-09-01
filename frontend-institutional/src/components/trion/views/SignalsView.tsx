"use client";

import { useMemo, useState } from "react";
import { Filter, Radio } from "lucide-react";
import { useTrionPoll } from "@/lib/trion/hooks";

interface BhFeed {
  total_bh_records: number;
  chains_active: number;
  records: Array<{
    chain: string;
    entity_id: string;
    event_type: string;
    sense_hex: string;
    antisense_hex?: string;
    ts: number;
    tx_hash: string;
    verdict: string;
  }>;
}

interface SelfVerificationFeed {
  feed: Array<{
    entity_id: string;
    coherence_score: number;
    archetype: string;
    genomic_generation: number;
    genomic_key?: string;
    limiting_plane: string;
    planes: Record<string, number>;
    ts?: number;
  }>;
}

const VERDICT_TONE: Record<string, string> = {
  SAFE: "#34d399",
  MEV: "#f59e0b",
  SUSPICIOUS: "#f43f5e",
};

export function SignalsView() {
  const { data: bhFeed, lastUpdated } = useTrionPoll<BhFeed>("bh/recent_feed", 3000);
  const { data: selfFeed } = useTrionPoll<SelfVerificationFeed>("feed", 6000);
  const [chainFilter, setChainFilter] = useState<string>("all");
  const [eventFilter, setEventFilter] = useState<string>("all");

  const records = bhFeed?.records ?? [];
  const chains = useMemo(() => [...new Set(records.map((r) => r.chain))].sort(), [records]);
  const events = useMemo(() => [...new Set(records.map((r) => r.event_type))].sort(), [records]);

  const filtered = records.filter(
    (r) =>
      (chainFilter === "all" || r.chain === chainFilter) &&
      (eventFilter === "all" || r.event_type === eventFilter)
  );

  const verdictCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of records) counts[r.verdict] = (counts[r.verdict] ?? 0) + 1;
    return counts;
  }, [records]);

  return (
    <div className="space-y-4">
      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Total BH Records" value={bhFeed?.total_bh_records ?? 0} tone="#34d399" />
        <Stat label="Active Chains" value={bhFeed?.chains_active ?? 0} tone="#22d3ee" />
        <Stat
          label="Safe Verdicts"
          value={verdictCounts["SAFE"] ?? 0}
          tone="#34d399"
          sub={`${records.length ? Math.round(((verdictCounts["SAFE"] ?? 0) / records.length) * 100) : 0}% of window`}
        />
        <Stat
          label="Flagged (MEV/SUSP)"
          value={(verdictCounts["MEV"] ?? 0) + (verdictCounts["SUSPICIOUS"] ?? 0)}
          tone="#f59e0b"
        />
      </section>

      <section aria-label="Behavioral signal stream" className="trion-panel">
        <div className="flex flex-wrap items-center gap-3 border-b border-[#1c232d] px-4 py-3">
          <div className="flex items-center gap-2">
            <Radio size={13} className="text-[#10b981]" />
            <span className="trion-label">Behavioral Signal Stream</span>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Filter size={12} className="text-[#4b5563]" />
            <select
              value={chainFilter}
              onChange={(e) => setChainFilter(e.target.value)}
              className="trion-mono rounded border border-[#1c232d] bg-[#0d1117] px-2 py-1 text-[10px] text-[#d7dde6] focus:border-[#10b981]"
              aria-label="Filter by chain"
            >
              <option value="all">ALL CHAINS</option>
              {chains.map((c) => (
                <option key={c} value={c}>{c.toUpperCase()}</option>
              ))}
            </select>
            <select
              value={eventFilter}
              onChange={(e) => setEventFilter(e.target.value)}
              className="trion-mono rounded border border-[#1c232d] bg-[#0d1117] px-2 py-1 text-[10px] text-[#d7dde6] focus:border-[#10b981]"
              aria-label="Filter by event type"
            >
              <option value="all">ALL EVENTS</option>
              {events.map((e) => (
                <option key={e} value={e}>{e}</option>
              ))}
            </select>
            <span className="trion-mono text-[10px] text-[#4b5563] hidden sm:inline">
              {lastUpdated ? new Date(lastUpdated).toLocaleTimeString("en-GB", { hour12: false }) : "—"}
            </span>
          </div>
        </div>
        <div className="max-h-[480px] overflow-y-auto">
          <table className="w-full text-left">
            <thead className="sticky top-0 bg-[#0d1117] z-10">
              <tr className="border-b border-[#1c232d]">
                {["Tx Hash", "Chain", "Entity", "Event", "Verdict", "Sense Strand", "Antisense Strand", "Time"].map((h) => (
                  <th key={h} className="trion-label px-3 py-2">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-[12px] text-[#7d8896]">
                    No records match the current filter.
                  </td>
                </tr>
              ) : (
                filtered.slice(0, 80).map((r, i) => (
                  <tr key={`${r.tx_hash}-${i}`} className="border-b border-[#161b22] hover:bg-[#ffffff04]">
                    <td className="px-3 py-2 trion-mono text-[10px] text-[#7d8896]" title={r.tx_hash}>
                      {r.tx_hash?.replace(/^0x/, "")?.slice(0, 10)}…
                    </td>
                    <td className="px-3 py-2 trion-mono text-[11px] text-[#34d399]">{r.chain}</td>
                    <td className="px-3 py-2 trion-mono text-[10px] text-[#d7dde6]">{r.entity_id?.slice(0, 10)}…</td>
                    <td className="px-3 py-2 trion-mono text-[11px] text-[#d7dde6]">{r.event_type}</td>
                    <td className="px-3 py-2">
                      <span className="trion-mono text-[10px] font-bold" style={{ color: VERDICT_TONE[r.verdict] ?? "#7d8896" }}>
                        {r.verdict}
                      </span>
                    </td>
                    <td className="px-3 py-2 trion-mono text-[10px] text-[#7d8896]">{r.sense_hex?.slice(0, 14)}…</td>
                    <td className="px-3 py-2 trion-mono text-[10px] text-[#4b5563]">{r.antisense_hex?.slice(0, 14) ?? "—"}</td>
                    <td className="px-3 py-2 trion-mono text-[10px] text-[#4b5563]">
                      {r.ts ? new Date(r.ts * 1000).toLocaleTimeString("en-GB", { hour12: false }) : "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Protocol self-verification stream */}
      <section aria-label="Protocol self-verification" className="trion-panel">
        <div className="border-b border-[#1c232d] px-4 py-3">
          <span className="trion-label">Protocol Self-Verification · TRION_PROTOCOL as Measured Entity</span>
        </div>
        <div className="divide-y divide-[#161b22]">
          {(selfFeed?.feed ?? []).slice(0, 6).map((f, i) => (
            <div key={i} className="flex flex-wrap items-center gap-x-6 gap-y-1 px-4 py-3">
              <span className="trion-mono text-[11px] font-bold text-[#34d399]">
                C(t) {f.coherence_score.toFixed(3)}
              </span>
              <span className="trion-mono text-[10px] text-[#7d8896]">gen {f.genomic_generation}</span>
              <span className="trion-mono text-[10px] text-[#a78bfa]">{f.archetype}</span>
              <span className="trion-mono text-[10px] text-[#4b5563]">
                limiting: {f.limiting_plane}
              </span>
              <span className="trion-mono text-[10px] text-[#4b5563] ml-auto hidden lg:inline">
                {f.ts ? new Date(f.ts * 1000).toISOString().slice(11, 19) + "Z" : "—"}
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Stat({ label, value, tone, sub }: { label: string; value: number; tone: string; sub?: string }) {
  return (
    <div className="trion-panel p-4">
      <div className="trion-label">{label}</div>
      <div className="trion-mono mt-1 text-xl font-bold tabular-nums" style={{ color: tone }}>
        {value.toLocaleString()}
      </div>
      {sub && <div className="text-[10px] text-[#4b5563]">{sub}</div>}
    </div>
  );
}
