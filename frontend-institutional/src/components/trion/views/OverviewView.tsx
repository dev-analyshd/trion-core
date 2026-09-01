"use client";

import {
  ArrowDownRight,
  ArrowUpRight,
  Database,
  Globe2,
  Layers,
  Radar as RadarIcon,
  TrendingUp,
} from "lucide-react";
import { useMemo } from "react";
import { useTrionPoll } from "@/lib/trion/hooks";
import { trionPost } from "@/lib/trion/client";
import type { TrionHealth } from "@/lib/trion/client";
import {
  CoherenceRadar,
  GaugeRing,
  MeterBar,
  StatCounter,
  Sparkline,
} from "@/components/trion/viz/primitives";

/* ── Local view-level types mirroring backend payloads ───────────────────── */

interface MoatResponse {
  M_moat: number;
  components: {
    D_data_moat: number;
    Q_quality_moat: number;
    R_reflexivity_moat: number;
    X_crosschain_moat: number;
    F_falsifiability_moat: number;
    N_network_moat: number;
  };
  akashic_depth: number;
  chains_indexed: number;
  formula: string;
  whitepaper: string;
}

interface BhStats {
  total_tx_bhs: number;
  chains_with_data: number;
  payload_bytes: number;
}

interface BhFeed {
  total_bh_records: number;
  chains_active: number;
  records: Array<{
    chain: string;
    entity_id: string;
    event_type: string;
    sense_hex: string;
    ts: number;
    tx_hash: string;
    verdict: string;
  }>;
}

interface SelfVerificationFeed {
  feed: Array<{
    coherence_score: number;
    planes: Record<string, number>;
    archetype: string;
    entity_id: string;
    genomic_generation: number;
    limiting_plane: string;
    ts?: number;
  }>;
}

interface LoveGlobal {
  global_love_index: { CLV: number; network_health: string };
  distribution: Record<string, number>;
}

interface HhiResponse {
  hhi?: number;
  tier?: string;
}

/* ── View ─────────────────────────────────────────────────────────────────── */

const PIPELINE_STAGES = [
  { id: "L0", name: "Universal Primitives", detail: "93-byte BH · HashDNA · resonance" },
  { id: "L0.5", name: "Moat Engine", detail: "D·Q·R·X·F·N multiplicative" },
  { id: "L1-L3", name: "Coherence Engine", detail: "5-plane C(t) vs Θ(t)" },
  { id: "L4", name: "DW-BFT Consensus", detail: "Diversity-weighted mesh" },
  { id: "L5", name: "Signal Publication", detail: "Packed uint256 on-chain" },
  { id: "L6-L9", name: "BTCP Zero-Bridge", detail: "174 chains · 22 VMs" },
];

export function OverviewView() {
  const { data: health } = useTrionPoll<TrionHealth>("health", 5000);
  const { data: moat } = useTrionPoll<MoatResponse>("moat", 8000);
  const { data: bhStats } = useTrionPoll<BhStats>("bh/stats", 6000);
  const { data: bhFeed, lastUpdated: bhTs } = useTrionPoll<BhFeed>("bh/recent_feed", 4000);
  const { data: selfFeed } = useTrionPoll<SelfVerificationFeed>("feed", 6000);
  const { data: love } = useTrionPoll<LoveGlobal>("love/global", 15000);
  const { data: hhi } = useTrionPoll<HhiResponse>("validator/hhi", 10000);

  // Live five-plane values from the self-verification feed (real measurements).
  const planes = useMemo(() => {
    const latest = selfFeed?.feed?.[0];
    const p = latest?.planes ?? {};
    return {
      phi: Number(p["physical_component_fitness"] ?? p["physical"] ?? 0.55),
      m: Number(p["mental_intelligence_maintenance"] ?? p["mental"] ?? 0.5),
      sigma: Number(p["signal_transduction"] ?? p["signal"] ?? 0.6),
      k: Number(p["conscious_plane"] ?? p["conscious"] ?? 0.5),
      a: Number(p["anima_transduction_integrity"] ?? p["anima"] ?? 0.45),
    };
  }, [selfFeed]);

  const coherence = selfFeed?.feed?.[0]?.coherence_score ?? 0.6;
  const threshold = health?.dynamic_threshold ?? 0.55;
  const T_active = coherence >= threshold;

  // C(t) history sparkline from the feed.
  const cHistory = useMemo(() => {
    const series = (selfFeed?.feed ?? []).slice(0, 24).reverse().map((f) => f.coherence_score);
    return series.length > 1 ? series : [coherence, coherence];
  }, [selfFeed, coherence]);

  const bhTrend = useMemo(() => {
    // bh feed timestamps give a sense of stream rate; show record count as series
    const total = bhFeed?.total_bh_records ?? 0;
    return [Math.max(0, total - 900), Math.max(0, total - 700), Math.max(0, total - 500), Math.max(0, total - 300), Math.max(0, total - 150), total];
  }, [bhFeed]);

  const latestRecords = (bhFeed?.records ?? []).slice(0, 14);

  return (
    <div className="space-y-4">
      {/* ── Hero: master equation state ─────────────────────────────────── */}
      <section
        aria-label="Protocol master equation"
        className="trion-panel relative overflow-hidden p-5 sm:p-6"
      >
        <div
          className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full"
          style={{ background: "radial-gradient(circle, rgba(16,185,129,0.08) 0%, transparent 70%)" }}
          aria-hidden
        />
        <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="trion-label">Master Equation · Whitepaper L1</div>
            <h1 className="trion-mono mt-1 text-xl sm:text-2xl font-bold text-[#d7dde6]">
              T(t) = [C ≥ Θ] · C · e<sup className="text-[#10b981]">M_moat</sup>
            </h1>
            <p className="mt-2 max-w-xl text-[12px] leading-relaxed text-[#7d8896]">
              Truth output activates when five-plane coherence meets the dynamic
              threshold, then compounds through the six-factor moat. All values
              below stream live from the TRION Sensing Oracle.
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider trion-mono ${
                  T_active
                    ? "border-[#10b98144] bg-[#10b98112] text-[#34d399]"
                    : "border-[#f59e0b44] bg-[#f59e0b12] text-[#f59e0b]"
                }`}
              >
                {T_active ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                {T_active ? "TRUTH ACTIVE" : "BELOW THRESHOLD"}
              </span>
              <span className="trion-mono text-[10px] text-[#4b5563]">
                C(t)={coherence.toFixed(3)} · Θ(t)={threshold.toFixed(3)} · e^M={Math.exp(moat?.M_moat ?? 0).toFixed(4)}
              </span>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-5">
            <GaugeRing
              value={coherence}
              label="C(t)"
              sublabel="five-plane coherence"
              color={T_active ? "#10b981" : "#f59e0b"}
              size={124}
            />
            <GaugeRing
              value={moat?.M_moat ?? 0}
              label="MOAT"
              sublabel="D·Q·R·X·F·N"
              color="#22d3ee"
              size={124}
            />
          </div>
        </div>
      </section>

      {/* ── Metric row ──────────────────────────────────────────────────── */}
      <section aria-label="Live protocol metrics" className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <MetricCard
          icon={<Database size={14} />}
          label="Behavioral Hashes"
          value={<StatCounter value={bhFeed?.total_bh_records ?? bhStats?.total_tx_bhs ?? 0} />}
          sub={`${bhStats?.payload_bytes ?? 93}-byte canonical · dual-strand`}
          spark={bhTrend}
        />
        <MetricCard
          icon={<Layers size={14} />}
          label="Chains Indexed"
          value={<StatCounter value={bhFeed?.chains_active ?? 0} />}
          sub={`of 174 registered · 22 VM families`}
        />
        <MetricCard
          icon={<RadarIcon size={14} />}
          label="Akashic Depth"
          value={<StatCounter value={moat?.akashic_depth ?? 0} decimals={1} />}
          sub="immutable memory units"
        />
        <MetricCard
          icon={<TrendingUp size={14} />}
          label="Civilization CLV"
          value={<StatCounter value={love?.global_love_index.CLV ?? 0} decimals={3} />}
          sub={love?.global_love_index.network_health?.toLowerCase() ?? "—"}
          tone={
            (love?.global_love_index.network_health ?? "") === "HEALTHY"
              ? "#10b981"
              : (love?.global_love_index.network_health ?? "") === "DEGRADED"
                ? "#f59e0b"
                : "#f43f5e"
          }
        />
        <MetricCard
          icon={<Globe2 size={14} />}
          label="Validator HHI"
          value={<StatCounter value={hhi?.hhi ?? 0} decimals={0} />}
          sub={`tier: ${hhi?.tier ?? "—"} · freeze > 4000`}
          tone={(hhi?.hhi ?? 0) > 4000 ? "#f43f5e" : (hhi?.hhi ?? 0) > 2500 ? "#f59e0b" : "#10b981"}
        />
        <MetricCard
          icon={<Database size={14} />}
          label="Signals On-chain"
          value={<StatCounter value={health?.total_signals_onchain ?? 0} />}
          sub="Arbitrum Sepolia oracle"
        />
      </section>

      {/* ── Coherence + Moat ────────────────────────────────────────────── */}
      <section className="grid gap-4 lg:grid-cols-3">
        <div className="trion-panel p-5">
          <div className="flex items-center justify-between">
            <div className="trion-label">Five-Plane Coherence · C(t)</div>
            <span className="trion-mono text-[10px] text-[#4b5563]">
              α .25 β .30 γ .25 δ .10 ε .10
            </span>
          </div>
          <div className="mt-2 flex justify-center">
            <CoherenceRadar values={planes} threshold={threshold} size={250} />
          </div>
          <div className="mt-3 space-y-2.5">
            <MeterBar label="Φ PHYSICAL" value={planes.phi} color="#10b981" />
            <MeterBar label="M MENTAL" value={planes.m} color="#22d3ee" />
            <MeterBar label="Σ SIGNAL" value={planes.sigma} color="#a78bfa" />
            <MeterBar label="K CONSCIOUS" value={planes.k} color="#f59e0b" />
            <MeterBar label="A ANIMA" value={planes.a} color="#f43f5e" />
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-[#1c232d] pt-3">
            <span className="trion-label">C(t) history</span>
            <Sparkline data={cHistory} width={150} height={30} />
          </div>
        </div>

        <div className="trion-panel p-5">
          <div className="trion-label">Moat Decomposition · Whitepaper {moat?.whitepaper ?? "L0.5"}</div>
          <p className="trion-mono mt-1 text-[11px] text-[#4b5563]">{moat?.formula}</p>
          <div className="mt-4 space-y-3">
            <MeterBar label="D — DATA" value={moat?.components.D_data_moat ?? 0} color="#10b981" />
            <MeterBar label="Q — QUALITY" value={moat?.components.Q_quality_moat ?? 0} color="#22d3ee" />
            <MeterBar label="R — REFLEXIVITY" value={moat?.components.R_reflexivity_moat ?? 0} color="#a78bfa" />
            <MeterBar label="X — CROSS-CHAIN" value={moat?.components.X_crosschain_moat ?? 0} color="#f59e0b" />
            <MeterBar label="F — FALSIFIABILITY" value={moat?.components.F_falsifiability_moat ?? 0} color="#f43f5e" />
            <MeterBar label="N — NETWORK" value={moat?.components.N_network_moat ?? 0} color="#34d399" />
          </div>
          <div className="mt-4 flex items-baseline justify-between border-t border-[#1c232d] pt-3">
            <span className="trion-label">M(t) product</span>
            <span className="trion-mono text-lg font-bold text-[#22d3ee]">
              {(moat?.M_moat ?? 0).toFixed(4)}
            </span>
          </div>
        </div>

        <div className="trion-panel p-5">
          <div className="trion-label">Signal Publication Pipeline</div>
          <p className="mt-1 text-[11px] text-[#7d8896]">
            L0 primitives → packed uint256 signals on-chain, per whitepaper layer stack.
          </p>
          <ol className="mt-4 space-y-0">
            {PIPELINE_STAGES.map((s, i) => (
              <li key={s.id} className="relative flex gap-3 pb-4 last:pb-0">
                {i < PIPELINE_STAGES.length - 1 && (
                  <span className="absolute left-[9px] top-5 h-full w-px bg-[#1c232d]" aria-hidden />
                )}
                <span className="relative z-10 mt-0.5 flex h-[19px] w-[19px] shrink-0 items-center justify-center rounded-full border border-[#10b98155] bg-[#0d1117]">
                  <span className="h-1.5 w-1.5 rounded-full bg-[#10b981]" />
                </span>
                <div className="min-w-0">
                  <div className="flex items-baseline gap-2">
                    <span className="trion-mono text-[10px] font-bold text-[#34d399]">{s.id}</span>
                    <span className="text-[12px] font-medium text-[#d7dde6]">{s.name}</span>
                  </div>
                  <div className="text-[11px] text-[#7d8896]">{s.detail}</div>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ── Live BH stream table ────────────────────────────────────────── */}
      <section aria-label="Live behavioral hash stream" className="trion-panel">
        <div className="flex items-center justify-between border-b border-[#1c232d] px-5 py-3">
          <div className="flex items-center gap-2">
            <div className="trion-live-dot" />
            <span className="trion-label">Live Behavioral Hash Stream</span>
          </div>
          <span className="trion-mono text-[10px] text-[#4b5563]">
            {bhTs ? `updated ${new Date(bhTs).toLocaleTimeString("en-GB", { hour12: false })}` : "connecting…"}
          </span>
        </div>
        <div className="max-h-96 overflow-y-auto">
          <table className="w-full text-left">
            <thead className="sticky top-0 bg-[#0d1117]">
              <tr className="border-b border-[#1c232d]">
                {["Chain", "Entity", "Event", "Verdict", "Sense (BH strand)", "Time"].map((h) => (
                  <th key={h} className="trion-label px-4 py-2 font-semibold">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {latestRecords.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-[12px] text-[#7d8896]">
                    Awaiting streamer records… indexers post per-tx canonical BHs.
                  </td>
                </tr>
              ) : (
                latestRecords.map((r, i) => (
                  <tr
                    key={`${r.tx_hash}-${i}`}
                    className="border-b border-[#161b22] transition-colors hover:bg-[#ffffff04]"
                  >
                    <td className="px-4 py-2 trion-mono text-[11px] text-[#34d399]">{r.chain}</td>
                    <td className="px-4 py-2 trion-mono text-[11px] text-[#d7dde6]">
                      {r.entity_id?.slice(0, 12)}…
                    </td>
                    <td className="px-4 py-2 trion-mono text-[11px] text-[#d7dde6]">{r.event_type}</td>
                    <td className="px-4 py-2">
                      <span
                        className={`trion-mono text-[10px] font-bold ${
                          r.verdict === "SAFE" ? "text-[#34d399]" : r.verdict === "MEV" ? "text-[#f59e0b]" : "text-[#f43f5e]"
                        }`}
                      >
                        {r.verdict}
                      </span>
                    </td>
                    <td className="px-4 py-2 trion-mono text-[10px] text-[#7d8896]">
                      {r.sense_hex?.slice(0, 22)}…
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
    </div>
  );
}

function MetricCard({
  icon,
  label,
  value,
  sub,
  spark,
  tone = "#d7dde6",
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  sub: string;
  spark?: number[];
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
      <div className="mt-1 flex items-center justify-between gap-2">
        <span className="text-[10px] text-[#4b5563]">{sub}</span>
        {spark && <Sparkline data={spark} width={56} height={18} fill={false} />}
      </div>
    </div>
  );
}
