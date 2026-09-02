"use client";

import {
  Boxes,
  Database,
  Layers,
  Loader2,
  Radar,
  Search,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useTrionPoll } from "@/lib/trion/hooks";
import { trionGet } from "@/lib/trion/client";
import { StatCounter } from "@/components/trion/viz/primitives";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/* ── Local view-level types mirroring backend payloads ───────────────────── */

interface BhRecord {
  chain: string;
  entity_id: string;
  event_type: string;
  sense_hex: string;
  antisense_hex?: string;
  ts: number;
  tx_hash: string;
  verdict: string;
}

interface BhStats {
  total_tx_bhs: number;
  chains_with_data: number;
  payload_bytes: number;
  per_chain: Record<string, number>;
  per_event_type: Record<string, number>;
  formula?: string;
  whitepaper?: string;
}

interface BhFeed {
  total_bh_records: number;
  chains_active: number;
  mev_captures: number;
  payload_bytes: number;
  records: BhRecord[];
  formula?: string;
  whitepaper?: string;
}

interface VmGroup {
  label: string;
  chains: string[];
  total: number;
}

interface VmFeed {
  total_bh_records: number;
  vm_groups: Record<string, VmGroup>;
}

interface BhDetail {
  entity_id: string;
  bh: {
    sense_hex: string;
    antisense_hex: string;
    valid: boolean;
    payload_bytes: number;
    canonical_order: string;
  };
  event: {
    type: string;
    type_id: number;
    magnitude_normalized: number;
    context_hex: string;
    chain_id: number;
    block_number: number;
    timestamp: number;
  };
  formula: string;
  magnitude_formula: string;
  whitepaper: string;
}

interface EntityAgg {
  id: string;
  count: number;
  chains: Set<string>;
  events: Map<string, number>;
  lastTs: number;
}

const VERDICT_TONE: Record<string, string> = {
  SAFE: "#34d399",
  MEV: "#f59e0b",
  INTERCEPT: "#f59e0b",
  HOSTILE: "#f43f5e",
  WATCH: "#a78bfa",
  ELEVATED: "#f59e0b",
};

function verdictColor(v: string): string {
  return VERDICT_TONE[v] ?? "#7d8896";
}

/* ── View ─────────────────────────────────────────────────────────────────── */

export function ExplorerView() {
  const { data: stats, lastUpdated: statsTs } = useTrionPoll<BhStats>("bh/stats", 6000);
  const { data: feed, lastUpdated: feedTs } = useTrionPoll<BhFeed>("bh/recent_feed", 3000);
  const { data: vmFeed } = useTrionPoll<VmFeed>("bh/vm_feed", 12000);

  const [search, setSearch] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selected, setSelected] = useState<BhRecord | null>(null);
  const [detail, setDetail] = useState<BhDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const records = feed?.records ?? [];

  /* A. Client-side search across chain / entity / event / tx / verdict. */
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return records;
    return records.filter((r) =>
      [r.chain, r.entity_id, r.event_type, r.tx_hash, r.verdict].some((f) =>
        (f ?? "").toLowerCase().includes(q)
      )
    );
  }, [records, search]);

  /* B. Entity resolution — group filtered records by entity_id. */
  const entities = useMemo(() => {
    const map = new Map<string, EntityAgg>();
    for (const r of filtered) {
      const id = r.entity_id || "—";
      let agg = map.get(id);
      if (!agg) {
        agg = { id, count: 0, chains: new Set(), events: new Map(), lastTs: 0 };
        map.set(id, agg);
      }
      agg.count += 1;
      agg.chains.add(r.chain);
      agg.events.set(r.event_type, (agg.events.get(r.event_type) ?? 0) + 1);
      if (r.ts > agg.lastTs) agg.lastTs = r.ts;
    }
    return [...map.values()].sort((a, b) => b.count - a.count || b.lastTs - a.lastTs);
  }, [filtered]);

  /* D. Per-chain distribution (top 20, desc). */
  const chainEntries = useMemo(
    () =>
      Object.entries(stats?.per_chain ?? {})
        .sort((a, b) => b[1] - a[1])
        .slice(0, 20),
    [stats]
  );
  const maxChain = chainEntries.length > 0 ? chainEntries[0][1] : 0;

  /* E. Event type distribution. */
  const eventEntries = useMemo(
    () => Object.entries(stats?.per_event_type ?? {}).sort((a, b) => b[1] - a[1]),
    [stats]
  );
  const eventTotal = eventEntries.reduce((s, [, n]) => s + n, 0);

  /* VM families strip. */
  const vmGroups = useMemo(() => Object.entries(vmFeed?.vm_groups ?? {}), [vmFeed]);

  /* C. Row click → fetch per-BH detail from the oracle. */
  const openDetail = async (r: BhRecord) => {
    setSelected(r);
    setDialogOpen(true);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const d = await trionGet<BhDetail>(`bh/${r.tx_hash.replace(/^0x/, "")}`);
      setDetail(d);
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : "detail fetch failed");
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* ── Metric row ───────────────────────────────────────────────────── */}
      <section aria-label="Ledger metrics" className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard
          icon={<Database size={14} />}
          label="Total BH Records"
          value={<StatCounter value={feed?.total_bh_records ?? stats?.total_tx_bhs ?? 0} />}
          sub={`${feed?.payload_bytes ?? stats?.payload_bytes ?? 93}-byte canonical dual-strand`}
        />
        <MetricCard
          icon={<Layers size={14} />}
          label="Chains With Data"
          value={<StatCounter value={stats?.chains_with_data ?? 0} />}
          sub={`of 174 registered · ${feed?.chains_active ?? 0} active in window`}
        />
        <MetricCard
          icon={<Radar size={14} />}
          label="Entities In View"
          value={<StatCounter value={entities.length} />}
          sub={`resolved from ${filtered.length} matching records`}
        />
        <MetricCard
          icon={<Boxes size={14} />}
          label="MEV Captures"
          value={<StatCounter value={feed?.mev_captures ?? 0} />}
          sub="INTERCEPT-class events across ledger"
          tone="#f59e0b"
        />
      </section>

      {/* ── A. Search bar + C. Results table ─────────────────────────────── */}
      <section aria-label="Behavioral hash ledger search" className="trion-panel">
        <div className="flex flex-wrap items-center gap-3 border-b border-[#1c232d] px-5 py-3">
          <div className="relative min-w-[200px] flex-1">
            <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[#4b5563]" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search tx hash, entity, chain, event type, verdict…"
              aria-label="Search behavioral hash records"
              className="trion-mono h-8 rounded border-[#1c232d] bg-[#0a0d12] pl-8 pr-8 text-[11px] text-[#d7dde6] placeholder:text-[#4b5563] focus-visible:border-[#10b981] focus-visible:ring-0"
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                aria-label="Clear search"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-[#4b5563] transition-colors hover:text-[#d7dde6]"
              >
                <X size={13} />
              </button>
            )}
          </div>
          <span className="trion-mono text-[10px] text-[#4b5563]">
            {filtered.length}/{records.length} records
          </span>
          <span className="trion-mono text-[10px] text-[#4b5563]">
            {feedTs
              ? `live · updated ${new Date(feedTs).toLocaleTimeString("en-GB", { hour12: false })}`
              : statsTs
                ? `stats · ${new Date(statsTs).toLocaleTimeString("en-GB", { hour12: false })}`
                : "connecting…"}
          </span>
        </div>

        <div className="max-h-96 overflow-y-auto">
          <table className="w-full text-left">
            <thead className="sticky top-0 z-10 bg-[#0d1117]">
              <tr className="border-b border-[#1c232d]">
                {["Tx Hash", "Chain", "Entity", "Event", "Verdict", "Sense Strand", "Antisense", "Time"].map((h) => (
                  <th key={h} className="trion-label px-4 py-2 font-semibold">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {records.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-[12px] text-[#7d8896]">
                    Awaiting ledger records… indexers post per-tx canonical BHs.
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-[12px] text-[#7d8896]">
                    No records match “{search}”.
                  </td>
                </tr>
              ) : (
                filtered.map((r, i) => (
                  <tr
                    key={`${r.tx_hash}-${i}`}
                    onClick={() => openDetail(r)}
                    className="cursor-pointer border-b border-[#161b22] transition-colors hover:bg-[#ffffff04]"
                    aria-label={`Open detail for ${r.tx_hash}`}
                  >
                    <td className="px-4 py-2 trion-mono text-[10px] text-[#7d8896]" title={r.tx_hash}>
                      {r.tx_hash?.replace(/^0x/, "").slice(0, 10)}…
                    </td>
                    <td className="px-4 py-2 trion-mono text-[11px] text-[#34d399]">{r.chain}</td>
                    <td className="px-4 py-2 trion-mono text-[10px] text-[#d7dde6]" title={r.entity_id}>
                      {r.entity_id?.slice(0, 12)}…
                    </td>
                    <td className="px-4 py-2 trion-mono text-[11px] text-[#d7dde6]">{r.event_type}</td>
                    <td className="px-4 py-2">
                      <span
                        className="trion-mono text-[10px] font-bold"
                        style={{ color: verdictColor(r.verdict) }}
                      >
                        {r.verdict}
                      </span>
                    </td>
                    <td className="px-4 py-2 trion-mono text-[10px] text-[#7d8896]" title={r.sense_hex}>
                      {r.sense_hex?.slice(0, 16)}…
                    </td>
                    <td className="px-4 py-2 trion-mono text-[10px] text-[#4b5563]" title="full strand in row detail">
                      {r.antisense_hex?.slice(0, 14) ?? "—"}
                    </td>
                    <td className="px-4 py-2 trion-mono text-[10px] text-[#4b5563]">
                      {r.ts ? new Date(r.ts * 1000).toLocaleTimeString("en-GB", { hour12: false }) : "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* ── B. Entity resolution + D. per-chain distribution ─────────────── */}
      <section className="grid gap-4 lg:grid-cols-2">
        <div className="trion-panel">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#1c232d] px-5 py-3">
            <div className="flex items-center gap-2">
              <Radar size={13} className="text-[#a78bfa]" />
              <span className="trion-label">BEO Entity Resolution</span>
            </div>
            <span className="trion-mono text-[10px] text-[#4b5563]">
              {entities.length} entities · click to filter
            </span>
          </div>
          <div className="border-b border-[#1c232d] bg-[#0a0d12] px-5 py-2">
            <p className="trion-mono text-[10px] leading-relaxed text-[#7d8896]">
              Entities resolved via BEO (Behavioral Entity Object) —
              <span className="text-[#a78bfa]"> CF 0.40 + ST 0.25 + SC 0.25 + BP 0.10 &gt; 0.75</span>
            </p>
          </div>
          <div className="max-h-96 overflow-y-auto divide-y divide-[#161b22]">
            {entities.length === 0 ? (
              <div className="px-5 py-6 text-center text-[12px] text-[#7d8896]">
                No entities in the current result set.
              </div>
            ) : (
              entities.map((e) => {
                const chains = [...e.chains].sort();
                const dominant = [...e.events.entries()].sort((a, b) => b[1] - a[1])[0];
                return (
                  <button
                    key={e.id}
                    onClick={() => setSearch(e.id)}
                    className="block w-full px-5 py-2.5 text-left transition-colors hover:bg-[#ffffff04]"
                    aria-label={`Filter records for entity ${e.id}`}
                  >
                    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <span className="trion-mono text-[11px] font-semibold text-[#d7dde6]" title={e.id}>
                        {e.id?.slice(0, 16)}…
                      </span>
                      <span className="trion-mono rounded-full border border-[#1c232d] bg-[#0a0d12] px-2 py-0.5 text-[9px] font-bold text-[#34d399]">
                        {e.count} BH{e.count === 1 ? "" : "s"}
                      </span>
                      <span className="trion-mono ml-auto text-[9px] text-[#4b5563]">
                        last {e.lastTs ? new Date(e.lastTs * 1000).toLocaleTimeString("en-GB", { hour12: false }) : "—"}
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5">
                      <span className="trion-mono text-[9px] text-[#22d3ee]">
                        {chains.length} chain{chains.length === 1 ? "" : "s"}: {chains.slice(0, 4).join(", ")}
                        {chains.length > 4 ? ` +${chains.length - 4}` : ""}
                      </span>
                      {dominant && (
                        <span className="trion-mono text-[9px] text-[#7d8896]">
                          dominant {dominant[0]} ×{dominant[1]}
                        </span>
                      )}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        <div className="trion-panel">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#1c232d] px-5 py-3">
            <div className="flex items-center gap-2">
              <Layers size={13} className="text-[#22d3ee]" />
              <span className="trion-label">Per-Chain BH Distribution</span>
            </div>
            <span className="trion-mono text-[10px] text-[#4b5563]">top 20 · desc</span>
          </div>
          <div className="max-h-96 overflow-y-auto p-4">
            <div className="space-y-1.5">
              {chainEntries.length === 0 ? (
                <div className="py-6 text-center text-[12px] text-[#7d8896]">
                  Loading chain distribution from ledger stats…
                </div>
              ) : (
                chainEntries.map(([chain, count], i) => (
                  <div key={chain} className="flex items-center gap-2.5">
                    <span className="trion-mono w-[92px] shrink-0 truncate text-[10px] text-[#d7dde6]">
                      {chain}
                    </span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[#1c232d]">
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{
                          width: `${maxChain > 0 ? (count / maxChain) * 100 : 0}%`,
                          background: i < 3 ? "#22d3ee" : "#10b981",
                        }}
                      />
                    </div>
                    <span className="trion-mono w-14 shrink-0 text-right text-[10px] tabular-nums text-[#7d8896]">
                      {count.toLocaleString()}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ── E. Event type distribution + VM families ─────────────────────── */}
      <section className="grid gap-4 lg:grid-cols-3">
        <div className="trion-panel p-5 lg:col-span-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Database size={13} className="text-[#34d399]" />
              <span className="trion-label">Event Type Distribution</span>
            </div>
            <span className="trion-mono text-[10px] text-[#4b5563]">
              {eventEntries.length} type{eventEntries.length === 1 ? "" : "s"} observed
            </span>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
            {eventEntries.length === 0 ? (
              <div className="col-span-full py-6 text-center text-[12px] text-[#7d8896]">
                Loading event type distribution…
              </div>
            ) : (
              eventEntries.map(([type, count]) => (
                <div
                  key={type}
                  className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-3 transition-colors hover:border-[#2a3441]"
                >
                  <div className="trion-mono truncate text-[10px] font-bold text-[#34d399]">{type}</div>
                  <div className="trion-mono mt-1 text-lg font-bold tabular-nums text-[#d7dde6]">
                    {count.toLocaleString()}
                  </div>
                  <div className="trion-mono text-[9px] text-[#4b5563]">
                    {eventTotal > 0 ? `${((count / eventTotal) * 100).toFixed(1)}% of ledger` : "—"}
                  </div>
                </div>
              ))
            )}
          </div>
          <div className="trion-mono mt-3 border-t border-[#1c232d] pt-2.5 text-[10px] text-[#4b5563]">
            {stats?.whitepaper ?? "L0.1"} · {stats?.formula ?? "sense=SHA3-256(93-byte||0x00); antisense=SHA3-256(93-byte||0xFF)⊕NOT(sense)"}
          </div>
        </div>

        <div className="trion-panel p-5">
          <div className="flex items-center gap-2">
            <Boxes size={13} className="text-[#f59e0b]" />
            <span className="trion-label">VM Family Coverage</span>
          </div>
          <div className="mt-3 space-y-2">
            {vmGroups.length === 0 ? (
              <div className="py-6 text-center text-[12px] text-[#7d8896]">
                Loading VM families…
              </div>
            ) : (
              vmGroups.map(([key, g]) => (
                <div
                  key={key}
                  className="flex items-center justify-between gap-3 rounded-md border border-[#1c232d] bg-[#0a0d12] px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="trion-mono text-[11px] font-bold text-[#d7dde6]">{g.label}</div>
                    <div className="trion-mono truncate text-[9px] text-[#4b5563]">
                      {g.chains.slice(0, 6).join(" · ")}
                      {g.chains.length > 6 ? ` +${g.chains.length - 6}` : ""}
                    </div>
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="trion-mono text-[11px] font-bold tabular-nums text-[#f59e0b]">
                      {g.total.toLocaleString()}
                    </div>
                    <div className="trion-mono text-[9px] text-[#4b5563]">
                      {g.chains.length} chain{g.chains.length === 1 ? "" : "s"}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
          <div className="trion-mono mt-3 border-t border-[#1c232d] pt-2.5 text-[10px] text-[#4b5563]">
            multi-VM live feed · 22 VM families registered
          </div>
        </div>
      </section>

      {/* ── C. Record detail dialog ──────────────────────────────────────── */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto border-[#1c232d] bg-[#0d1117] p-0 text-[#d7dde6]">
          <DialogHeader className="border-b border-[#1c232d] px-5 py-3">
            <DialogTitle className="trion-mono text-[13px] text-[#d7dde6]">
              Behavioral Hash Record
            </DialogTitle>
            <DialogDescription className="trion-mono text-[10px] text-[#4b5563]">
              {selected?.tx_hash ?? ""}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 p-5">
            {detailLoading && (
              <div className="flex items-center gap-2 py-4">
                <Loader2 size={14} className="animate-spin text-[#10b981]" />
                <span className="trion-mono text-[11px] text-[#7d8896]">
                  resolving dual-strand detail from oracle…
                </span>
              </div>
            )}
            {detailError && (
              <div className="rounded-md border border-[#f43f5e44] bg-[#f43f5e0f] p-3">
                <span className="trion-mono text-[11px] text-[#f43f5e]">{detailError}</span>
              </div>
            )}
            {detail && (
              <>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <KV label="Sense Strand (full)" value={detail.bh.sense_hex} tone="#34d399" />
                  <KV label="Antisense Strand (full)" value={detail.bh.antisense_hex} tone="#22d3ee" />
                  <KV label="Payload" value={`${detail.bh.payload_bytes} bytes`} />
                  <KV label="Valid" value={detail.bh.valid ? "true — complement verified" : "false"} />
                  <KV label="Event" value={`${detail.event.type} (#${detail.event.type_id})`} />
                  <KV label="Magnitude Norm" value={detail.event.magnitude_normalized.toFixed(6)} />
                  <KV label="Chain ID" value={String(detail.event.chain_id)} />
                  <KV label="Block" value={detail.event.block_number.toLocaleString()} />
                </div>
                <div className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-3">
                  <div className="trion-label">Canonical Order</div>
                  <div className="trion-mono mt-1 text-[10px] leading-relaxed text-[#7d8896]">
                    {detail.bh.canonical_order}
                  </div>
                  <div className="trion-mono mt-1.5 text-[10px] leading-relaxed text-[#4b5563]">
                    {detail.formula} · {detail.magnitude_formula}
                  </div>
                </div>
              </>
            )}
            {selected && (
              <div className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-3">
                <div className="trion-label">Raw Ledger Record (recent_feed)</div>
                <pre className="trion-mono mt-1.5 overflow-x-auto text-[10px] leading-relaxed text-[#7d8896]">
                  {JSON.stringify(selected, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* ── Local building blocks ────────────────────────────────────────────────── */

function MetricCard({
  icon,
  label,
  value,
  sub,
  tone = "#d7dde6",
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  sub: string;
  tone?: string;
}) {
  return (
    <div className="trion-panel p-4 transition-colors hover:border-[#2a3441]">
      <div className="flex items-center justify-between">
        <span className="trion-label">{label}</span>
        <span className="text-[#4b5563]">{icon}</span>
      </div>
      <div className="trion-mono mt-1.5 text-xl font-bold tabular-nums" style={{ color: tone }}>
        {value}
      </div>
      <div className="mt-1 text-[10px] text-[#4b5563]">{sub}</div>
    </div>
  );
}

function KV({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-2.5">
      <div className="trion-label">{label}</div>
      <div className="trion-mono mt-0.5 break-all text-[10px] leading-relaxed" style={{ color: tone ?? "#d7dde6" }}>
        {value}
      </div>
    </div>
  );
}
