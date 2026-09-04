"use client";

import {
  Activity,
  Boxes,
  Cpu,
  Database,
  FlaskConical,
  Search,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useTrionPoll } from "@/lib/trion/hooks";
import { CHAIN_COUNT, VM_FAMILY_COUNT } from "@/lib/trion/client";
import { StatCounter } from "@/components/trion/viz/primitives";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

/* ── Local view-level types mirroring backend payloads ───────────────────── */

interface ChainRow {
  id: string;
  name: string;
  chain_id: number;
  vm: string;
  status: string;
  indexer: string;
  color?: string;
  note?: string;
  bh_label?: string;
}

interface ChainsResponse {
  chains: ChainRow[];
  total?: number;
  live?: number;
  indexed?: number;
  vm_families?: number;
  timestamp?: number;
}

interface VmFeedResponse {
  per_chain?: Record<string, number>;
}

/* ── Helpers ──────────────────────────────────────────────────────────────── */

const STATUS_TONES: Record<string, { color: string; bg: string; border: string }> = {
  live: { color: "#34d399", bg: "#10b98112", border: "#10b98144" },
  testnet: { color: "#f59e0b", bg: "#f59e0b12", border: "#f59e0b44" },
  indexed: { color: "#22d3ee", bg: "#22d3ee12", border: "#22d3ee44" },
};

function statusTone(status: string) {
  return STATUS_TONES[status.toLowerCase()] ?? { color: "#7d8896", bg: "#ffffff08", border: "#1c232d" };
}

/** Linear hex blend — emerald → cyan gradient scale by family size. */
function mixHex(a: string, b: string, t: number): string {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  const pc = pa.map((v, i) => Math.round(v + (pb[i] - v) * Math.max(0, Math.min(1, t))));
  return `#${pc.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

/* ── View ─────────────────────────────────────────────────────────────────── */

export function ChainsView() {
  const { data: chainsResp, lastUpdated: chainsTs } = useTrionPoll<ChainsResponse>("chains", 30000);
  const { data: vmFeed, lastUpdated: vmTs } = useTrionPoll<VmFeedResponse>("bh/vm_feed", 5000);

  const chains = useMemo(() => chainsResp?.chains ?? [], [chainsResp]);

  /* A. Summary metrics */
  const statusCounts = useMemo(() => {
    let live = 0;
    let testnet = 0;
    let indexed = 0;
    for (const c of chains) {
      const s = c.status.toLowerCase();
      if (s === "live") live++;
      else if (s === "testnet") testnet++;
      else if (s === "indexed") indexed++;
    }
    return { live, testnet, indexed };
  }, [chains]);

  /* B. VM family breakdown — sorted desc by chain count */
  const vmFamilies = useMemo(() => {
    const m = new Map<string, number>();
    for (const c of chains) m.set(c.vm, (m.get(c.vm) ?? 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }, [chains]);
  const vmMax = vmFamilies.length > 0 ? Math.max(1, vmFamilies[0][1]) : 1;
  const totalChains = chains.length;

  /* C. Live BH coverage — top 12 chains by BH count */
  const topBh = useMemo(() => {
    const entries = Object.entries(vmFeed?.per_chain ?? {}).map(([name, count]) => ({
      name,
      count: Number(count) || 0,
    }));
    entries.sort((a, b) => b.count - a.count);
    return entries.slice(0, 12);
  }, [vmFeed]);
  const bhMax = topBh.length > 0 ? Math.max(1, topBh[0].count) : 1;

  /* D. Chain explorer filters */
  const [search, setSearch] = useState("");
  const [vmFilter, setVmFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selected, setSelected] = useState<ChainRow | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return chains.filter((c) => {
      if (vmFilter !== "all" && c.vm !== vmFilter) return false;
      if (statusFilter !== "all" && c.status.toLowerCase() !== statusFilter) return false;
      if (!q) return true;
      return (
        c.name.toLowerCase().includes(q) ||
        c.id.toLowerCase().includes(q) ||
        String(c.chain_id).includes(q) ||
        (c.indexer ?? "").toLowerCase().includes(q) ||
        (c.note ?? "").toLowerCase().includes(q)
      );
    });
  }, [chains, search, vmFilter, statusFilter]);

  const openChain = (c: ChainRow) => {
    setSelected(c);
    setDialogOpen(true);
  };

  const selectedTone = selected ? statusTone(selected.status) : null;

  return (
    <div className="space-y-4">
      {/* ── A. Summary strip ────────────────────────────────────────────── */}
      <section
        aria-label="Chain registry summary"
        className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5"
      >
        <MetricCard
          icon={<Boxes size={14} />}
          label="Total Chains"
          value={<StatCounter value={totalChains} />}
          sub="registered in BTCP registry"
        />
        <MetricCard
          icon={<Activity size={14} />}
          label="Live"
          value={<StatCounter value={statusCounts.live} />}
          sub="per-tx BH streaming"
          tone="#34d399"
        />
        <MetricCard
          icon={<FlaskConical size={14} />}
          label="Testnet"
          value={<StatCounter value={statusCounts.testnet} />}
          sub="staging environments"
          tone="#f59e0b"
        />
        <MetricCard
          icon={<Database size={14} />}
          label="Indexed"
          value={<StatCounter value={statusCounts.indexed} />}
          sub="registry-only · awaiting indexer"
          tone="#22d3ee"
        />
        <MetricCard
          icon={<Cpu size={14} />}
          label="VM Families"
          value={<StatCounter value={vmFamilies.length} />}
          sub="execution environments"
          tone="#a78bfa"
        />
      </section>

      {/* ── B. VM families + C. Live BH coverage ────────────────────────── */}
      <section className="grid gap-4 lg:grid-cols-2" aria-label="VM family distribution and live coverage">
        {/* B. VM family breakdown — proportional bars */}
        <div className="trion-panel p-5">
          <div className="flex items-center justify-between">
            <span className="trion-label">VM Family Breakdown</span>
            <span className="trion-mono text-[10px] text-[#4b5563]">
              {vmFamilies.length} families · {totalChains} chains
            </span>
          </div>

          {/* Proportional stacked bar — segment widths ∝ chain counts */}
          <div
            className="mt-3 flex h-3 w-full overflow-hidden rounded-full"
            role="img"
            aria-label="Proportional VM family distribution across all chains"
          >
            {vmFamilies.map(([vm, count], i) => (
              <div
                key={vm}
                className="h-full min-w-[2px] transition-all duration-700"
                style={{
                  width: `${totalChains > 0 ? (count / totalChains) * 100 : 0}%`,
                  background: mixHex("#10b981", "#22d3ee", vmFamilies.length > 1 ? i / (vmFamilies.length - 1) : 0),
                }}
                title={`${vm} — ${count} chains`}
              />
            ))}
          </div>

          {/* Per-family rows, sorted desc */}
          <div className="mt-4 max-h-96 overflow-y-auto pr-1">
            <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
              {vmFamilies.length === 0 ? (
                <span className="trion-mono text-[11px] text-[#7d8896]">loading registry…</span>
              ) : (
                vmFamilies.map(([vm, count], i) => {
                  const color = mixHex(
                    "#10b981",
                    "#22d3ee",
                    vmFamilies.length > 1 ? i / (vmFamilies.length - 1) : 0
                  );
                  return (
                    <div key={vm} className="flex items-center gap-2">
                      <span
                        className="w-24 shrink-0 truncate text-[10px] text-[#d7dde6]"
                        title={vm}
                      >
                        {vm}
                      </span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[#1c232d]">
                        <div
                          className="h-full rounded-full transition-all duration-700"
                          style={{ width: `${(count / vmMax) * 100}%`, background: color }}
                        />
                      </div>
                      <span className="trion-mono w-8 shrink-0 text-right text-[10px] tabular-nums text-[#7d8896]">
                        {count}
                      </span>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          <div className="trion-mono mt-3 border-t border-[#1c232d] pt-2.5 text-[10px] text-[#4b5563]">
            {chainsTs
              ? `registry poll 30s · updated ${new Date(chainsTs).toLocaleTimeString("en-GB", { hour12: false })}`
              : "connecting…"}
          </div>
        </div>

        {/* C. Live BH coverage — top 12 by count */}
        <div className="trion-panel">
          <div className="flex items-center justify-between border-b border-[#1c232d] px-5 py-3">
            <div className="flex items-center gap-2">
              <span className="trion-live-dot" aria-hidden />
              <span className="trion-label">Live BH Coverage · Top 12</span>
            </div>
            <span className="trion-mono text-[10px] text-[#4b5563]">
              {vmTs ? `poll 5s · ${new Date(vmTs).toLocaleTimeString("en-GB", { hour12: false })}` : "connecting…"}
            </span>
          </div>
          <div className="space-y-2.5 p-5">
            {topBh.length === 0 ? (
              <span className="trion-mono text-[11px] text-[#7d8896]">awaiting streamer BH counts…</span>
            ) : (
              topBh.map((c, i) => (
                <div key={c.name} className="flex items-center gap-2">
                  <span
                    className="trion-mono w-28 shrink-0 truncate text-[10px] text-[#d7dde6]"
                    title={c.name}
                  >
                    {c.name}
                  </span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-[#1c232d]">
                    <div
                      className="h-full rounded-full transition-all duration-700"
                      style={{
                        width: `${(c.count / bhMax) * 100}%`,
                        background: mixHex("#10b981", "#22d3ee", topBh.length > 1 ? i / (topBh.length - 1) : 0),
                      }}
                    />
                  </div>
                  <span className="trion-mono w-14 shrink-0 text-right text-[10px] tabular-nums text-[#34d399]">
                    {c.count.toLocaleString()}
                  </span>
                </div>
              ))
            )}
            <div className="trion-mono border-t border-[#1c232d] pt-2.5 text-[10px] text-[#4b5563]">
              behavioral hashes indexed per chain · multi-VM live feed
            </div>
          </div>
        </div>
      </section>

      {/* ── D. Chain explorer table ─────────────────────────────────────── */}
      <section aria-label="Chain explorer" className="trion-panel">
        <div className="flex flex-wrap items-center gap-3 border-b border-[#1c232d] px-5 py-3">
          <div className="relative min-w-[200px] flex-1">
            <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[#4b5563]" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search chain name, id, note, indexer…"
              aria-label="Search chains"
              className="trion-mono h-8 rounded border-[#1c232d] bg-[#0a0d12] pl-8 pr-8 text-[11px] text-[#d7dde6] placeholder:text-[#4b5563] focus-visible:border-[#10b981] focus-visible:ring-0"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                aria-label="Clear chain search"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-[#4b5563] transition-colors hover:text-[#d7dde6]"
              >
                <X size={13} />
              </button>
            )}
          </div>

          <Select value={vmFilter} onValueChange={setVmFilter}>
            <SelectTrigger
              size="sm"
              aria-label="Filter by VM family"
              className="trion-mono h-8 w-[170px] rounded border-[#1c232d] bg-[#0a0d12] text-[11px] text-[#d7dde6] focus-visible:border-[#10b981] focus-visible:ring-0"
            >
              <SelectValue placeholder="All VMs" />
            </SelectTrigger>
            <SelectContent className="max-h-72 border-[#1c232d] bg-[#0d1117] text-[#d7dde6]">
              <SelectItem
                value="all"
                className="trion-mono text-[11px] focus:bg-[#10b9811a] focus:text-[#34d399]"
              >
                All VMs
              </SelectItem>
              {vmFamilies.map(([vm, count]) => (
                <SelectItem
                  key={vm}
                  value={vm}
                  className="trion-mono text-[11px] focus:bg-[#10b9811a] focus:text-[#34d399]"
                >
                  {vm} · {count}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger
              size="sm"
              aria-label="Filter by chain status"
              className="trion-mono h-8 w-[140px] rounded border-[#1c232d] bg-[#0a0d12] text-[11px] text-[#d7dde6] focus-visible:border-[#10b981] focus-visible:ring-0"
            >
              <SelectValue placeholder="All statuses" />
            </SelectTrigger>
            <SelectContent className="border-[#1c232d] bg-[#0d1117] text-[#d7dde6]">
              <SelectItem
                value="all"
                className="trion-mono text-[11px] focus:bg-[#10b9811a] focus:text-[#34d399]"
              >
                All statuses
              </SelectItem>
              {(["live", "testnet", "indexed"] as const).map((s) => (
                <SelectItem
                  key={s}
                  value={s}
                  className="trion-mono text-[11px] focus:bg-[#10b9811a] focus:text-[#34d399]"
                >
                  {s} · {statusCounts[s]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <span className="trion-mono text-[10px] text-[#4b5563]">
            {filtered.length}/{chains.length} chains
          </span>
        </div>

        <div className="max-h-96 overflow-y-auto">
          <Table className="w-full">
            <TableHeader className="sticky top-0 z-10 bg-[#0d1117]">
              <TableRow className="border-b border-[#1c232d] hover:bg-transparent">
                {["Chain", "Chain ID", "VM", "Status", "Indexer", "Note"].map((h) => (
                  <TableHead key={h} className="trion-label px-4 py-2 font-semibold">
                    {h}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 ? (
                <TableRow className="hover:bg-transparent">
                  <TableCell colSpan={6} className="px-4 py-6 text-center text-[12px] text-[#7d8896]">
                    {chains.length === 0 ? "Loading chain registry…" : "No chains match the current filters."}
                  </TableCell>
                </TableRow>
              ) : (
                filtered.map((c) => {
                  const tone = statusTone(c.status);
                  return (
                    <TableRow
                      key={`${c.id}-${c.chain_id}`}
                      onClick={() => openChain(c)}
                      className="cursor-pointer border-b border-[#161b22] hover:bg-[#ffffff04]"
                      aria-label={`Open details for ${c.name}`}
                    >
                      <TableCell className="px-4 py-2">
                        <div className="flex items-center gap-2">
                          <span
                            className="h-2 w-2 shrink-0 rounded-full"
                            style={{ background: c.color ?? "#4b5563" }}
                            aria-hidden
                          />
                          <span className="text-[12px] font-medium text-[#d7dde6]">{c.name}</span>
                        </div>
                      </TableCell>
                      <TableCell className="px-4 py-2 trion-mono text-[11px] tabular-nums text-[#7d8896]">
                        {c.chain_id}
                      </TableCell>
                      <TableCell className="px-4 py-2 trion-mono text-[11px] text-[#a78bfa]">{c.vm}</TableCell>
                      <TableCell className="px-4 py-2">
                        <Badge
                          variant="outline"
                          className="trion-mono rounded-full px-2 py-0 text-[9px] font-bold uppercase tracking-wider"
                          style={{ color: tone.color, borderColor: tone.border, background: tone.bg }}
                        >
                          {c.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="px-4 py-2 trion-mono text-[10px] text-[#7d8896]">
                        {c.indexer}
                      </TableCell>
                      <TableCell className="max-w-[280px] truncate px-4 py-2 text-[11px] text-[#7d8896]">
                        {c.note ?? "—"}
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </div>

        <div className="trion-mono border-t border-[#1c232d] px-5 py-2.5 text-[10px] text-[#4b5563]">
          click a row for the full registry record · {CHAIN_COUNT} chains · {VM_FAMILY_COUNT} VM families · zero-bridge candidate set
        </div>
      </section>

      {/* ── Chain detail dialog ─────────────────────────────────────────── */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto border-[#1c232d] bg-[#0d1117] p-0 text-[#d7dde6]">
          <DialogHeader className="border-b border-[#1c232d] px-5 py-3">
            <DialogTitle className="trion-mono flex items-center gap-2 text-[13px] text-[#d7dde6]">
              {selected && (
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: selected.color ?? "#4b5563" }}
                  aria-hidden
                />
              )}
              {selected?.name ?? "Chain"}
            </DialogTitle>
            <DialogDescription className="trion-mono text-[10px] text-[#4b5563]">
              {selected ? `id ${selected.id} · BTCP chain registry record` : ""}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 p-5">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <KV label="Registry ID" value={selected?.id ?? "—"} />
              <KV label="Name" value={selected?.name ?? "—"} />
              <KV label="Chain ID" value={selected ? String(selected.chain_id) : "—"} />
              <KV label="VM" value={selected?.vm ?? "—"} tone="#a78bfa" />
              <KV label="Status" value={selected?.status ?? "—"} tone={selectedTone?.color} />
              <KV label="Indexer" value={selected?.indexer ?? "—"} tone="#34d399" />
              <KV label="BH Label" value={selected?.bh_label ?? "—"} tone="#22d3ee" />
              <div className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-2.5">
                <div className="trion-label">Color</div>
                <div className="mt-0.5 flex items-center gap-2">
                  <span
                    className="h-3 w-3 shrink-0 rounded-full border border-[#2a3441]"
                    style={{ background: selected?.color ?? "#4b5563" }}
                    aria-hidden
                  />
                  <span className="trion-mono text-[10px] text-[#d7dde6]">{selected?.color ?? "—"}</span>
                </div>
              </div>
            </div>

            <div className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-3">
              <div className="trion-label">Note (full)</div>
              <div className="mt-1 break-words text-[11px] leading-relaxed text-[#7d8896]">
                {selected?.note || "—"}
              </div>
            </div>

            <div className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-3">
              <div className="trion-label">Raw Registry Record</div>
              <pre className="trion-mono mt-1.5 overflow-x-auto text-[10px] leading-relaxed text-[#7d8896]">
                {selected ? JSON.stringify(selected, null, 2) : ""}
              </pre>
            </div>
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
      <div
        className="trion-mono mt-0.5 break-all text-[10px] leading-relaxed"
        style={{ color: tone ?? "#d7dde6" }}
      >
        {value}
      </div>
    </div>
  );
}
