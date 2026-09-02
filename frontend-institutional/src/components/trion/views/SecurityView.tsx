"use client";

import {
  Dna,
  FileKey2,
  Flame,
  Lock,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Users,
} from "lucide-react";
import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useTrionPoll } from "@/lib/trion/hooks";
import { GaugeRing, StatCounter } from "@/components/trion/viz/primitives";

/* ── Local view-level types mirroring backend payloads ───────────────────── */

interface CoordinationAttackRow {
  byzantine_effective_weight: number;
  byzantine_power_fraction: number;
  coordination_level: number;
  total_effective_stake: number;
  safety_holds?: boolean;
  sigma?: number;
}

interface DwBftResponse {
  consensus_value?: number;
  byzantine_effective_weight?: number;
  consensus_window_delta?: number;
  bft_safety_proof?: string;
  self_defeating_proof?: string;
  coordination_attack_simulation?: CoordinationAttackRow[];
  sigma?: number;
  total_effective_stake?: number;
  honest_effective_stake?: number;
  safety_margin?: number;
  safety_holds?: boolean;
  validator_count?: number;
  validators_in_consensus?: number;
  whitepaper?: string;
  timestamp?: number;
}

interface HhiResponse {
  hhi?: number;
  tier?: string;
  validator_count?: number;
  continent_count?: number;
  continents?: string[];
  auto_response?: string;
  consensus_paused?: boolean;
  f8_violation?: boolean;
  f9_violation?: boolean;
  governance_emergency?: boolean;
  geographic_violations?: string[];
  formula?: string;
  whitepaper?: string;
}

interface SelfVerificationFeed {
  feed?: Array<{
    archetype?: string;
    genomic_generation?: number;
    genomic_key?: string;
    status?: string;
  }>;
}

/* ── Static protocol constants (clearly labeled, not live) ────────────────── */

interface FirewallPattern {
  pattern: string;
  mf: string;
  trigger: string;
  response: string;
  dominant?: boolean;
}

const FIREWALL_PATTERNS: FirewallPattern[] = [
  {
    pattern: "ORACLE_ATTACK",
    mf: "1.0 (fixed)",
    trigger: "oracle feed compromise detected",
    response: "IMMEDIATE SILENCE",
    dominant: true,
  },
  {
    pattern: "WASH_TRADING",
    mf: "0.70 × wash_ratio",
    trigger: "ratio > 0.60 ∧ counterparties < 5",
    response: "behavioral discount",
  },
  {
    pattern: "SYBIL",
    mf: "0.60 × concentration",
    trigger: "concentration > 0.80 ∧ BEO < 20",
    response: "weight suppression",
  },
  {
    pattern: "GOV_CAPTURE",
    mf: "0.50 × (HHI − 2500) / 7500",
    trigger: "HHI > 4000 ∧ capture age < 48h",
    response: "governance freeze",
  },
  {
    pattern: "MEV",
    mf: "0.40 × (rate − 0.005) / 0.045",
    trigger: "MEV extraction rate > 0.005",
    response: "extraction penalty",
  },
  {
    pattern: "PUMP",
    mf: "0.85 × sync",
    trigger: "≥ 3 synchronized moves @ 0.80",
    response: "synchronization decay",
  },
  {
    pattern: "FAKE_VOLUME",
    mf: "0.80 × entropy_deficit",
    trigger: "entropy below volume-implied baseline",
    response: "volume discount",
  },
];

const SYBIL_LAYERS = [
  {
    layer: "L1",
    name: "Log-Depth Cap",
    formula: "cred ≤ 10 · log₁₀(1 + depth)",
    detail:
      "Credibility grows only logarithmically with behavioral depth — minting a credible history is exponentially costly.",
  },
  {
    layer: "L2",
    name: "Scrutiny Escalation",
    formula: "scrutiny = 1 + 0.5n",
    detail:
      "Each anomaly flag n raises future scrutiny by 50%, compounding the cost of repeated borderline behavior.",
  },
  {
    layer: "L3",
    name: "Cosine Similarity",
    formula: "cos(v_i, v_j) ≥ 0.85 → ALERT",
    detail:
      "Near-duplicate behavioral vectors are flagged as coordinated identities before they can accumulate weight.",
  },
  {
    layer: "L4",
    name: "Temporal Spacing",
    formula: "Δt ≥ 7n² days",
    detail:
      "Identity-affecting events must be spaced quadratically — rapid identity churn is structurally penalized.",
  },
  {
    layer: "L5",
    name: "Star-Pattern Detection",
    formula: "fan-out > 20 → FLAG",
    detail:
      "Hub-and-spoke interaction topology marks coordination hubs and severs their influence path.",
  },
];

const ZK_CIRCUITS = [
  "zk_travel_rule",
  "zk_iap_share_proof",
  "zk_behavioral_credential",
  "zk_intent_commitment",
  "zk_complementarity_proof",
];

const HHI_SCALE_MAX = 5000;
const HHI_SEGMENTS = [
  { from: 0, to: 1500, color: "rgba(16,185,129,0.45)" },
  { from: 1500, to: 2500, color: "rgba(245,158,11,0.40)" },
  { from: 2500, to: 4000, color: "rgba(244,63,94,0.30)" },
  { from: 4000, to: 5000, color: "rgba(244,63,94,0.65)" },
];
const HHI_MARKERS = [
  { value: 1500, label: "LOW" },
  { value: 2500, label: "MODERATE" },
  { value: 4000, label: "CRITICAL" },
];

/* ── Helpers ─────────────────────────────────────────────────────────────── */

function tierColor(tier?: string): string {
  switch ((tier ?? "").toUpperCase()) {
    case "HEALTHY":
      return "#34d399";
    case "WARNING":
      return "#f59e0b";
    case "DANGER":
    case "CRITICAL":
      return "#f43f5e";
    default:
      return "#7d8896";
  }
}

function fmt(n: number | undefined, d = 2): string {
  return (n ?? 0).toLocaleString("en-US", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  });
}

function MonoTag({ children }: { children: React.ReactNode }) {
  return (
    <span className="trion-mono rounded border border-[#1c232d] bg-[#0d1117] px-2 py-0.5 text-[10px] text-[#7d8896]">
      {children}
    </span>
  );
}

function StatChip({
  label,
  value,
  sub,
  tone = "#d7dde6",
}: {
  label: string;
  value: React.ReactNode;
  sub: string;
  tone?: string;
}) {
  return (
    <div className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-3">
      <div className="trion-label">{label}</div>
      <div className="trion-mono mt-0.5 text-[15px] font-bold tabular-nums" style={{ color: tone }}>
        {value}
      </div>
      <div className="mt-0.5 text-[9px] text-[#4b5563]">{sub}</div>
    </div>
  );
}

/* ── Recharts tooltip (dark) for the coordination attack simulation ──────── */

function AttackTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: CoordinationAttackRow }>;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const row = payload[0].payload;
  return (
    <div className="trion-mono rounded-lg border border-[#2a3441] bg-[#0a0d12] px-3 py-2 text-[10px] leading-relaxed shadow-xl">
      <div className="text-[#7d8896]">coordination level ρ = {row.coordination_level.toFixed(2)}</div>
      <div className="text-[#34d399]">
        byzantine eff. weight {fmt(row.byzantine_effective_weight, 0)}
      </div>
      <div className="text-[#d7dde6]">
        power fraction {(row.byzantine_power_fraction * 100).toFixed(2)}%
      </div>
      <div className="text-[#7d8896]">
        total eff. stake {fmt(row.total_effective_stake, 0)}
      </div>
    </div>
  );
}

/* ── View ─────────────────────────────────────────────────────────────────── */

export function SecurityView() {
  const { data: dw, lastUpdated: dwTs } = useTrionPoll<DwBftResponse>("dw_bft", 6000);
  const { data: hhi } = useTrionPoll<HhiResponse>("validator/hhi", 10000);
  const { data: selfFeed } = useTrionPoll<SelfVerificationFeed>("feed", 8000);

  const consensus = dw?.consensus_value ?? 0;
  const sigma = dw?.sigma ?? 0;
  const byzWeight = dw?.byzantine_effective_weight ?? 0;
  const totalStake = dw?.total_effective_stake ?? 0;
  const byzShare = totalStake > 0 ? byzWeight / totalStake : 0;
  const windowDelta = dw?.consensus_window_delta ?? 0;
  const safetyHolds = dw?.safety_holds ?? true;

  // Gauge scale adapts if the weighted mean moves outside the 0–2000 band.
  const vScale = Math.max(2000, Math.ceil(consensus / 500) * 500);

  const attackSeries = useMemo(
    () =>
      [...(dw?.coordination_attack_simulation ?? [])].sort(
        (a, b) => a.byzantine_power_fraction - b.byzantine_power_fraction
      ),
    [dw]
  );

  const living = selfFeed?.feed?.[0];

  const hhiVal = hhi?.hhi ?? 0;
  const hhiTier = hhi?.tier ?? "—";
  const hhiPos = Math.min(100, Math.max(0, (hhiVal / HHI_SCALE_MAX) * 100));
  const liveColor = tierColor(hhi?.tier);

  return (
    <div className="space-y-4">
      {/* ── A. DW-BFT consensus panel ────────────────────────────────────── */}
      <section
        aria-label="Diversity-weighted BFT consensus state"
        className="trion-panel relative overflow-hidden p-5 sm:p-6"
      >
        <div
          className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full"
          style={{ background: "radial-gradient(circle, rgba(16,185,129,0.08) 0%, transparent 70%)" }}
          aria-hidden
        />
        <div className="relative flex flex-col gap-6 xl:flex-row xl:items-center xl:justify-between">
          <div className="min-w-0 max-w-2xl">
            <div className="flex items-center gap-2">
              <div className="trion-live-dot" />
              <span className="trion-label">
                DW-BFT Consensus · {dw?.whitepaper ?? "L4"} · {dw?.validator_count ?? 0} validators
              </span>
            </div>

            <blockquote className="mt-3 rounded-lg border border-[#1c232d] border-l-2 border-l-[#10b981] bg-[#0a0d12] p-4">
              <div className="trion-label">BFT Safety Proof</div>
              <p className="trion-mono mt-1 text-base font-bold text-[#d7dde6]">
                d_j = 1 − corr(M_j, M̄)
              </p>
              <p className="mt-2 text-[11px] leading-relaxed text-[#7d8896]">
                Coordination increases corr(M_j, M̄) → d_j → 0 → effective Byzantine
                weight → 0. A coordinated attack is structurally self-defeating.
              </p>
              {dw?.bft_safety_proof && (
                <p className="trion-mono mt-2 border-t border-[#1c232d] pt-2 text-[10px] leading-relaxed text-[#4b5563]">
                  {dw.bft_safety_proof}
                </p>
              )}
            </blockquote>

            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatChip
                label="Byzantine Eff. Weight"
                value={<StatCounter value={byzWeight} decimals={0} />}
                sub={`${(byzShare * 100).toFixed(1)}% of eff. stake`}
                tone="#f43f5e"
              />
              <StatChip
                label="Window δ Drift"
                value={
                  <StatCounter
                    value={Math.abs(windowDelta)}
                    prefix={windowDelta >= 0 ? "+" : "−"}
                    decimals={3}
                  />
                }
                sub="consensus window delta"
                tone="#22d3ee"
              />
              <StatChip
                label="Total Eff. Stake"
                value={<StatCounter value={totalStake} decimals={0} />}
                sub="Σ s_j · d_j"
              />
              <StatChip
                label="Safety Margin"
                value={<StatCounter value={dw?.safety_margin ?? 0} decimals={0} />}
                sub={safetyHolds ? "honest > ⅔ total" : "below ⅔ floor"}
                tone={safetyHolds ? "#34d399" : "#f43f5e"}
              />
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span
                className={`trion-mono inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider ${
                  safetyHolds
                    ? "border-[#10b98144] bg-[#10b98112] text-[#34d399]"
                    : "border-[#f43f5e44] bg-[#f43f5e12] text-[#f43f5e]"
                }`}
              >
                {safetyHolds ? <ShieldCheck size={12} /> : <ShieldAlert size={12} />}
                {safetyHolds ? "SAFETY HOLDS" : "SAFETY AT RISK"}
              </span>
              <span className="trion-mono text-[10px] text-[#4b5563]">
                {dw?.validators_in_consensus ?? 0}/{dw?.validator_count ?? 0} within window ·{" "}
                {dwTs
                  ? `updated ${new Date(dwTs).toLocaleTimeString("en-GB", { hour12: false })}`
                  : "connecting…"}
              </span>
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap items-center justify-center gap-4">
            <GaugeRing
              value={consensus}
              max={vScale}
              label="v̄"
              sublabel={`consensus value · scale 0–${fmt(vScale, 0)}`}
              color="#34d399"
              size={124}
              decimals={2}
            />
            <GaugeRing
              value={sigma}
              max={1}
              label="Σ(t)"
              sublabel="consensus level"
              color="#22d3ee"
              size={124}
            />
          </div>
        </div>
      </section>

      {/* ── B. Coordination attack simulation (recharts line) ─────────────── */}
      <section aria-label="Coordination attack simulation" className="trion-panel">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#1c232d] px-5 py-3">
          <div className="flex items-center gap-2">
            <div className="trion-live-dot" />
            <span className="trion-label">Coordination Attack Simulation</span>
          </div>
          <span className="trion-mono text-[10px] text-[#4b5563]">
            byzantine_effective_weight vs byzantine_power_fraction
          </span>
        </div>
        <div className="p-4 sm:p-5">
          <div className="h-[260px] w-full">
            {attackSeries.length > 1 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={attackSeries} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
                  <CartesianGrid stroke="#1c232d" strokeDasharray="3 3" />
                  <XAxis
                    type="number"
                    dataKey="byzantine_power_fraction"
                    domain={[0, "dataMax"]}
                    stroke="#1c232d"
                    tick={{ fill: "#7d8896", fontSize: 10 }}
                    tickLine={false}
                    axisLine={{ stroke: "#1c232d" }}
                    tickFormatter={(v: number) => `${(v * 100).toFixed(1)}%`}
                  />
                  <YAxis
                    domain={[0, "dataMax"]}
                    width={56}
                    stroke="#1c232d"
                    tick={{ fill: "#7d8896", fontSize: 10 }}
                    tickLine={false}
                    axisLine={{ stroke: "#1c232d" }}
                    tickFormatter={(v: number) =>
                      v >= 1000 ? `${Math.round(v / 1000)}k` : `${Math.round(v)}`
                    }
                  />
                  <Tooltip content={<AttackTooltip />} cursor={{ stroke: "#2a3441", strokeDasharray: "4 4" }} />
                  <Line
                    type="monotone"
                    dataKey="byzantine_effective_weight"
                    stroke="#10b981"
                    strokeWidth={2}
                    dot={{ r: 3, fill: "#0d1117", stroke: "#34d399", strokeWidth: 1.5 }}
                    activeDot={{ r: 4, fill: "#34d399", stroke: "#0d1117", strokeWidth: 1 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-[12px] text-[#7d8896]">
                Awaiting coordination simulation rows…
              </div>
            )}
          </div>
          <div className="mt-1 flex flex-wrap justify-between gap-2">
            <span className="trion-mono text-[9px] text-[#4b5563]">
              x · byzantine power fraction (effective share of stake)
            </span>
            <span className="trion-mono text-[9px] text-[#4b5563]">
              y · byzantine effective weight (Σ s_j·d_j)
            </span>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            {(dw?.coordination_attack_simulation ?? []).map((row) => (
              <div
                key={row.coordination_level}
                className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-2.5"
              >
                <div className="trion-label">coord ρ = {row.coordination_level.toFixed(2)}</div>
                <div className="trion-mono mt-0.5 text-[13px] font-bold tabular-nums text-[#d7dde6]">
                  {fmt(row.byzantine_effective_weight, 0)}
                </div>
                <div className="trion-mono text-[10px] text-[#7d8896]">
                  {(row.byzantine_power_fraction * 100).toFixed(1)}% power
                </div>
              </div>
            ))}
          </div>
          {dw?.self_defeating_proof && (
            <p className="trion-mono mt-3 border-t border-[#1c232d] pt-3 text-[10px] leading-relaxed text-[#4b5563]">
              {dw.self_defeating_proof}
            </p>
          )}
        </div>
      </section>

      {/* ── C. HHI concentration monitor ─────────────────────────────────── */}
      <section aria-label="HHI concentration monitor" className="trion-panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="trion-live-dot" />
            <span className="trion-label">
              Validator HHI · Concentration Monitor · {hhi?.whitepaper ?? "L4.8"}
            </span>
          </div>
          <span
            className="trion-mono inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider"
            style={{
              borderColor: `${liveColor}44`,
              background: `${liveColor}12`,
              color: liveColor,
            }}
          >
            {hhiTier}
          </span>
        </div>

        <div className="mt-4 grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            {/* Horizontal 0→5000 scale with tier markers */}
            <div className="relative pt-7">
              <div
                className="absolute top-0 z-10 -translate-x-1/2"
                style={{ left: `${hhiPos}%` }}
                aria-hidden
              >
                <span
                  className="trion-mono whitespace-nowrap rounded border border-[#2a3441] bg-[#0a0d12] px-1.5 py-0.5 text-[10px] font-bold tabular-nums"
                  style={{ color: liveColor }}
                >
                  {fmt(hhiVal, 0)}
                </span>
                <span
                  className="mx-auto block h-2 w-0.5"
                  style={{ background: liveColor }}
                />
              </div>
              <div
                role="meter"
                aria-valuemin={0}
                aria-valuemax={HHI_SCALE_MAX}
                aria-valuenow={Math.round(hhiVal)}
                aria-valuetext={`HHI ${fmt(hhiVal, 0)}, tier ${hhiTier}`}
                className="relative h-2.5 overflow-hidden rounded-full border border-[#1c232d] bg-[#0a0d12]"
              >
                {HHI_SEGMENTS.map((s) => (
                  <div
                    key={s.from}
                    className="absolute inset-y-0"
                    style={{
                      left: `${(s.from / HHI_SCALE_MAX) * 100}%`,
                      width: `${((s.to - s.from) / HHI_SCALE_MAX) * 100}%`,
                      background: s.color,
                    }}
                  />
                ))}
              </div>
              <div className="relative mt-1 h-7">
                <span className="trion-mono absolute left-0 text-[9px] text-[#4b5563]">0</span>
                {HHI_MARKERS.map((m) => (
                  <div
                    key={m.value}
                    className="absolute -translate-x-1/2 text-center"
                    style={{ left: `${(m.value / HHI_SCALE_MAX) * 100}%` }}
                  >
                    <div className="mx-auto h-1.5 w-px bg-[#4b5563]" />
                    <span className="trion-mono text-[9px] text-[#4b5563]">
                      {m.value} {m.label}
                    </span>
                  </div>
                ))}
                <span className="trion-mono absolute right-0 text-[9px] text-[#4b5563]">5000</span>
              </div>
            </div>

            <blockquote className="mt-4 rounded-lg border border-[#1c232d] border-l-2 border-l-[#22d3ee] bg-[#0a0d12] p-3.5">
              <p className="trion-mono text-[13px] font-bold text-[#d7dde6]">
                HHI = Σ(s_j/Σs)² · 10000
              </p>
              <p className="mt-1.5 text-[11px] leading-relaxed text-[#7d8896]">
                Concentration of effective stake on a 0–10,000 scale. Above 4,000 the
                protocol enters CRITICAL: signal publication freezes and the AWA
                disarms. Below 1,500 the validator mesh is considered diverse.
              </p>
            </blockquote>
            <p className="trion-mono mt-2 text-[10px] text-[#4b5563]">
              CRITICAL &gt; 4000 → freeze signals · AWA off · emergency rotation
            </p>
          </div>

          <div className="rounded-lg border border-[#1c232d] bg-[#0a0d12] p-4">
            <div className="trion-label">Current Reading</div>
            <div
              className="trion-mono mt-1 text-3xl font-bold tabular-nums"
              style={{ color: liveColor }}
            >
              <StatCounter value={hhiVal} decimals={0} />
            </div>
            <div className="trion-mono mt-3 space-y-1.5 text-[10px] text-[#7d8896]">
              <div className="flex justify-between gap-2">
                <span>registry validators</span>
                <span className="tabular-nums text-[#d7dde6]">{hhi?.validator_count ?? "—"}</span>
              </div>
              <div className="flex justify-between gap-2">
                <span>continents</span>
                <span className="tabular-nums text-[#d7dde6]">
                  {hhi?.continent_count ?? "—"}
                  {hhi?.continents?.length ? ` · ${hhi.continents.join(" ")}` : ""}
                </span>
              </div>
              <div className="flex justify-between gap-2">
                <span>auto response</span>
                <span className="trion-mono text-[#d7dde6]">{hhi?.auto_response ?? "—"}</span>
              </div>
              <div className="flex justify-between gap-2">
                <span>F8 weight-cap violation</span>
                <span style={{ color: hhi?.f8_violation ? "#f43f5e" : "#34d399" }}>
                  {hhi?.f8_violation ? "YES" : "no"}
                </span>
              </div>
              <div className="flex justify-between gap-2">
                <span>F9 geographic violation</span>
                <span style={{ color: hhi?.f9_violation ? "#f43f5e" : "#34d399" }}>
                  {hhi?.f9_violation ? "YES" : "no"}
                </span>
              </div>
              <div className="flex justify-between gap-2">
                <span>consensus paused</span>
                <span style={{ color: hhi?.consensus_paused ? "#f43f5e" : "#34d399" }}>
                  {hhi?.consensus_paused ? "YES" : "no"}
                </span>
              </div>
              <div className="flex justify-between gap-2">
                <span>governance emergency</span>
                <span style={{ color: hhi?.governance_emergency ? "#f43f5e" : "#34d399" }}>
                  {hhi?.governance_emergency ? "YES" : "no"}
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── D. Manipulation firewall (static protocol constants) ─────────── */}
      <section aria-label="Manipulation firewall patterns" className="trion-panel">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#1c232d] px-5 py-3">
          <div className="flex items-center gap-2">
            <Flame size={13} className="text-[#f59e0b]" />
            <span className="trion-label">Manipulation Firewall · 7 Attack Patterns</span>
          </div>
          <span className="trion-mono rounded-full border border-[#a78bfa44] bg-[#a78bfa12] px-2.5 py-1 text-[9px] font-bold uppercase tracking-wider text-[#a78bfa]">
            static reference · protocol constants
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-[#1c232d]">
                {["Pattern", "Manipulation factor", "Trigger condition", "Response"].map((h) => (
                  <th key={h} scope="col" className="trion-label px-4 py-2">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {FIREWALL_PATTERNS.map((p) => (
                <tr
                  key={p.pattern}
                  className={`border-b border-[#161b22] transition-colors hover:bg-[#ffffff04] ${
                    p.dominant ? "bg-[#f43f5e08]" : ""
                  }`}
                >
                  <td
                    className="px-4 py-2.5 trion-mono text-[11px] font-bold"
                    style={{ color: p.dominant ? "#f43f5e" : "#34d399" }}
                  >
                    {p.pattern}
                  </td>
                  <td className="px-4 py-2.5 trion-mono text-[11px] text-[#d7dde6]">{p.mf}</td>
                  <td className="px-4 py-2.5 trion-mono text-[10px] text-[#7d8896]">{p.trigger}</td>
                  <td
                    className="px-4 py-2.5 trion-mono text-[10px] font-bold"
                    style={{ color: p.dominant ? "#f43f5e" : "#7d8896" }}
                  >
                    {p.response}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex flex-col gap-2 border-t border-[#1c232d] px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="trion-mono text-[10px] text-[#7d8896]">
            MF_agg = max(MF_i) · ORACLE_ATTACK dominates at 1.0
          </p>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="trion-mono text-[9px] uppercase tracking-wider text-[#4b5563]">
              firewall gates
            </span>
            <span className="trion-mono rounded border border-[#f59e0b44] bg-[#f59e0b12] px-2 py-0.5 text-[10px] font-bold text-[#f59e0b]">
              NL ≥ 0.30
            </span>
            <span className="trion-mono rounded border border-[#10b98144] bg-[#10b98112] px-2 py-0.5 text-[10px] font-bold text-[#34d399]">
              MF ≤ 0.70
            </span>
          </div>
        </div>
      </section>

      {/* ── E. Sybil resistance layers ───────────────────────────────────── */}
      <section
        aria-label="Sybil resistance layers"
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5"
      >
        {SYBIL_LAYERS.map((l) => (
          <div
            key={l.layer}
            className="trion-panel p-4 transition-colors hover:border-[#2a3441]"
          >
            <div className="flex items-center justify-between">
              <span className="trion-mono rounded border border-[#22d3ee44] bg-[#22d3ee12] px-1.5 py-0.5 text-[9px] font-bold text-[#22d3ee]">
                {l.layer}
              </span>
              <Users size={13} className="text-[#4b5563]" />
            </div>
            <div className="mt-2 text-[12px] font-semibold text-[#d7dde6]">{l.name}</div>
            <div className="trion-mono mt-1.5 rounded border border-[#1c232d] bg-[#0a0d12] px-2 py-1.5 text-[10px] text-[#34d399]">
              {l.formula}
            </div>
            <p className="mt-2 text-[10px] leading-relaxed text-[#7d8896]">{l.detail}</p>
          </div>
        ))}
      </section>

      {/* ── F. Cryptography stack (2×2) ──────────────────────────────────── */}
      <section aria-label="Cryptography stack" className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="trion-panel p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Lock size={14} className="text-[#34d399]" />
              <span className="trion-label">Post-Quantum Cryptography</span>
            </div>
            <span className="trion-mono text-[9px] text-[#4b5563]">L4.6</span>
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-[#7d8896]">
            NIST-standard lattice and hash-signature schemes execute real
            round-trips — live KEM encapsulate/decapsulate and sign/verify, not
            algorithm stubs.
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <MonoTag>ML-KEM-768</MonoTag>
            <MonoTag>ML-DSA-65</MonoTag>
            <MonoTag>SLH-DSA</MonoTag>
          </div>
          <div className="trion-mono mt-3 border-t border-[#1c232d] pt-2 text-[10px] text-[#4b5563]">
            round-trip verified per session · harvest-now-decrypt-later resistant
          </div>
        </div>

        <div className="trion-panel p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Dna size={14} className="text-[#22d3ee]" />
              <span className="trion-label">Genomic Key</span>
            </div>
            <span className="trion-mono text-[9px] text-[#4b5563]">L4.4</span>
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-[#7d8896]">
            Entity keys are grown from 8 DNA components (G1–G8) on dual
            sense/antisense strands; the 93-byte canonical behavioral hash is the
            binding substrate.
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <MonoTag>8 DNA components · G1–G8</MonoTag>
            <MonoTag>dual-strand</MonoTag>
            <MonoTag>93-byte BH</MonoTag>
          </div>
          {living?.genomic_key && (
            <div className="trion-mono mt-3 border-t border-[#1c232d] pt-2 text-[10px] text-[#4b5563]">
              live fingerprint {living.genomic_key}
            </div>
          )}
        </div>

        <div className="trion-panel p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileKey2 size={14} className="text-[#a78bfa]" />
              <span className="trion-label">ZK Circuits</span>
            </div>
            <span className="trion-mono text-[9px] text-[#4b5563]">5 SNARKs</span>
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-[#7d8896]">
            Circom / Poseidon SNARKs prove compliance without disclosing the
            underlying behavior — 477–1319 constraints per circuit.
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {ZK_CIRCUITS.map((c) => (
              <MonoTag key={c}>{c}</MonoTag>
            ))}
          </div>
          <div className="trion-mono mt-3 border-t border-[#1c232d] pt-2 text-[10px] text-[#4b5563]">
            Groth16 · Poseidon hashes · 477–1319 constraints
          </div>
        </div>

        <div className="trion-panel p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <RefreshCw size={14} className="text-[#f59e0b]" />
              <span className="trion-label">Living Security</span>
            </div>
            <span className="trion-mono text-[9px] text-[#4b5563]">self-rewriting</span>
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-[#7d8896]">
            Detection patterns and key material rewrite themselves each genomic
            generation — attackers face a moving target that learns from every
            probe.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded border border-[#1c232d] bg-[#0a0d12] px-2.5 py-2">
            <div className="trion-live-dot" />
            <span className="trion-mono text-[10px] font-bold text-[#34d399]">
              GEN {living?.genomic_generation ?? "—"}
            </span>
            <span className="trion-mono text-[10px] text-[#7d8896]">
              archetype {living?.archetype ?? "—"}
            </span>
            <span className="trion-mono text-[10px] text-[#7d8896]">
              {living?.status ?? "—"}
            </span>
          </div>
        </div>
      </section>
    </div>
  );
}
