"use client";

import {
  BookOpen,
  CheckCircle2,
  EyeOff,
  FlaskConical,
  Flame,
  Heart,
  Landmark,
  ShieldAlert,
  ShieldCheck,
  Trophy,
  XCircle,
} from "lucide-react";
import { useMemo } from "react";
import { useTrionPoll } from "@/lib/trion/hooks";
import { GaugeRing, StatCounter } from "@/components/trion/viz/primitives";

/* ── Local view-level types mirroring backend payloads ───────────────────── */

interface AwaCondition {
  met?: boolean;
  threshold?: number;
  value?: number;
}

interface AwaResponse {
  conditions?: Record<string, AwaCondition>;
  akashic_depth?: number;
  bootstrap_weight?: number;
  disclosure?: string;
  enforced?: boolean;
  status?: string;
  failing_conditions?: string[];
  gratitude_events_30d?: number;
  timestamp?: number;
}

interface LoveGlobal {
  global_love_index?: {
    CLV?: number;
    network_health?: string;
    description?: string;
    formula?: string;
  };
  distribution?: Record<string, number>;
  leaderboard?: Array<{
    entity: string;
    grade: string;
    lv: number;
    cs: number;
    pg: number;
    longevity_yrs: number;
  }>;
  trust_web_stats?: Record<string, string>;
  unlock?: Record<string, boolean>;
  storage_layer?: string;
}

interface FalsifiabilityCondition {
  id: string;
  claim: string;
  plane?: string;
  status: string;
  sample_size?: number;
  test_metric?: string;
  threshold?: string;
  window?: string;
  notes?: string;
  last_check?: number;
}

interface FalsifiabilityResponse {
  conditions?: FalsifiabilityCondition[];
  summary?: {
    passing?: number;
    monitoring?: number;
    conjecture?: number;
    failing?: number;
    total?: number;
    integrity?: boolean;
  };
  disclosure?: string;
  whitepaper_ref?: string;
  live_evidence?: { note?: string };
  timestamp?: number;
}

/* ── Static presentation metadata ────────────────────────────────────────── */

const AWA_CONDITIONS: Array<{
  key: string;
  label: string;
  hint: string;
  comparison?: "le" | "ge";
}> = [
  { key: "validator_hhi", label: "Validator HHI", hint: "mesh concentration below hard ceiling", comparison: "le" },
  { key: "gratitude_score", label: "Gratitude Score", hint: "network gratitude above floor", comparison: "ge" },
  { key: "public_good_pct", label: "Public-Good Share", hint: "signal weight routed to public goods", comparison: "ge" },
  { key: "consensus_quorum", label: "Consensus Quorum", hint: "effective stake within agreement window", comparison: "ge" },
  { key: "no_single_entity_controls_validators", label: "No Entity Controls Validators", hint: "validator-set share cap", comparison: "le" },
  { key: "no_single_entity_controls_weights", label: "No Entity Controls Weights", hint: "weight-share cap", comparison: "le" },
  { key: "right_to_invisibility", label: "Right to Invisibility", hint: "opt-out honored protocol-wide" },
  { key: "sovereignty_dignity_protocol", label: "Sovereignty & Dignity Protocol", hint: "SDP privileges and obligations enforced" },
];

const GRADE_ORDER = ["EXEMPLARY", "TRUSTED", "BUILDING", "HOSTILE_COLLAPSE"];
const GRADE_COLORS: Record<string, string> = {
  EXEMPLARY: "#34d399",
  TRUSTED: "#22d3ee",
  BUILDING: "#f59e0b",
  HOSTILE_COLLAPSE: "#f43f5e",
};

const FALS_STATUS_COLORS: Record<string, string> = {
  PASSING: "#34d399",
  MONITORING: "#f59e0b",
  CONJECTURE: "#a78bfa",
  FAILING: "#f43f5e",
};

const RIGHTS_CARDS = [
  {
    icon: <EyeOff size={15} className="text-[#22d3ee]" />,
    title: "Right to Invisibility",
    tag: "AWA condition",
    detail:
      "Any entity may exit observation entirely — no shadow profiles, no residual inference. Opt-out is honored at the sensing layer, before storage, not merely after it.",
  },
  {
    icon: <Landmark size={15} className="text-[#34d399]" />,
    title: "Sovereignty & Dignity Protocol",
    tag: "L8 · SBA",
    detail:
      "Privileges P1–P5 and obligations O1–O5 bind observer behavior. Sovereign observer weight is capped at 0.20 so no watcher can dominate the entity it watches.",
  },
  {
    icon: <Flame size={15} className="text-[#f59e0b]" />,
    title: "Thermodynamic Deletion",
    tag: "Entropy engine",
    detail:
      "Deletion is made physically costly: erasing history must burn real work against the entropy engine, which keeps the akashic ledger append-only in practice.",
  },
  {
    icon: <BookOpen size={15} className="text-[#a78bfa]" />,
    title: "Elder Wisdom",
    tag: "Governance",
    detail:
      "Entities with verified coherent longevity earn mentoring weight in governance — wisdom compounds through survived time rather than purchased stake.",
  },
];

/* ── Helpers ─────────────────────────────────────────────────────────────── */

function fmt(n: number | undefined, d = 2): string {
  return (n ?? 0).toLocaleString("en-US", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  });
}

/** Adaptive decimals for mixed-magnitude governance values. */
function govDecimals(v: number): number {
  if (Math.abs(v) >= 100) return 0;
  if (Math.abs(v) >= 1) return 2;
  return 4;
}

function GradeBadge({ grade }: { grade: string }) {
  const color = GRADE_COLORS[grade] ?? "#7d8896";
  return (
    <span
      className="trion-mono inline-flex rounded-full border px-2 py-0.5 text-[9px] font-bold tracking-wider"
      style={{ borderColor: `${color}44`, background: `${color}12`, color }}
    >
      {grade}
    </span>
  );
}

/* ── View ─────────────────────────────────────────────────────────────────── */

export function GovernanceView() {
  const { data: awa } = useTrionPoll<AwaResponse>("governance/awa", 8000);
  const { data: love } = useTrionPoll<LoveGlobal>("love/global", 15000);
  const { data: fals } = useTrionPoll<FalsifiabilityResponse>("falsifiability", 30000);

  const allMet =
    awa?.conditions !== undefined &&
    AWA_CONDITIONS.every((m) => awa.conditions?.[m.key]?.met === true);
  const armed = allMet || (awa?.enforced ?? false);
  const verdictColor = armed ? "#34d399" : "#f43f5e";

  const CLV = love?.global_love_index?.CLV ?? 0;
  const networkHealth = love?.global_love_index?.network_health ?? "—";
  const healthColor =
    networkHealth.toUpperCase() === "HEALTHY"
      ? "#34d399"
      : networkHealth.toUpperCase() === "DEGRADED"
        ? "#f59e0b"
        : "#f43f5e";

  const dist = love?.distribution ?? {};
  const totalEntities =
    dist.total_entities ?? GRADE_ORDER.reduce((s, g) => s + (dist[g] ?? 0), 0);

  const board = useMemo(() => {
    const rows = love?.leaderboard ?? [];
    return [...rows].sort((a, b) => {
      const ga = GRADE_ORDER.indexOf(a.grade);
      const gb = GRADE_ORDER.indexOf(b.grade);
      if (ga !== gb) return ga - gb;
      return b.lv - a.lv;
    });
  }, [love]);

  const falsRows = fals?.conditions ?? [];
  const falsSummary = fals?.summary ?? {};

  return (
    <div className="space-y-4">
      {/* ── A. AWA conditions + verdict banner ───────────────────────────── */}
      <section
        aria-label="AWA enforcement status"
        className="trion-panel relative overflow-hidden p-5 sm:p-6"
      >
        <div
          className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full"
          style={{
            background: `radial-gradient(circle, ${armed ? "rgba(16,185,129,0.10)" : "rgba(244,63,94,0.10)"} 0%, transparent 70%)`,
          }}
          aria-hidden
        />
        <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="trion-label">
              Autonomous Wisdom Architecture · L8 · Governance Conditions
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-3">
              {armed ? (
                <ShieldCheck size={28} className="text-[#34d399]" />
              ) : (
                <ShieldAlert size={28} className="text-[#f43f5e]" />
              )}
              <h1
                className="trion-mono text-xl font-bold sm:text-2xl"
                style={{ color: verdictColor }}
              >
                {armed ? "AWA ARMED" : "AWA DEGRADED"}
              </h1>
              <span
                className="trion-mono rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider"
                style={{
                  borderColor: `${verdictColor}44`,
                  background: `${verdictColor}12`,
                  color: verdictColor,
                }}
              >
                {awa?.status ?? "—"}
              </span>
            </div>
            <p className="mt-2 max-w-xl text-[12px] leading-relaxed text-[#7d8896]">
              {awa?.disclosure ??
                "AWA gates signal publication on eight live governance conditions. All must hold before wisdom authority is armed."}
            </p>
            {(awa?.failing_conditions ?? []).length > 0 && (
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                <span className="trion-mono text-[9px] uppercase tracking-wider text-[#4b5563]">
                  pending telemetry
                </span>
                {(awa?.failing_conditions ?? []).map((f) => {
                  const [name, val] = f.split("=");
                  return (
                    <span
                      key={f}
                      className="trion-mono rounded border border-[#f59e0b33] bg-[#f59e0b0d] px-1.5 py-0.5 text-[9px] text-[#f59e0b]"
                    >
                      {name.replaceAll("_", " ")} · {val ?? "pending"}
                    </span>
                  );
                })}
              </div>
            )}
          </div>
          <div className="grid shrink-0 grid-cols-3 gap-3">
            <div className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-3">
              <div className="trion-label">Bootstrap Weight</div>
              <div className="trion-mono mt-0.5 text-lg font-bold tabular-nums text-[#22d3ee]">
                <StatCounter value={awa?.bootstrap_weight ?? 0} decimals={4} />
              </div>
              <div className="text-[9px] text-[#4b5563]">decentralization transition</div>
            </div>
            <div className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-3">
              <div className="trion-label">Akashic Depth</div>
              <div className="trion-mono mt-0.5 text-lg font-bold tabular-nums text-[#a78bfa]">
                <StatCounter value={awa?.akashic_depth ?? 0} decimals={1} />
              </div>
              <div className="text-[9px] text-[#4b5563]">immutable memory units</div>
            </div>
            <div className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-3">
              <div className="trion-label">Gratitude 30d</div>
              <div className="trion-mono mt-0.5 text-lg font-bold tabular-nums text-[#34d399]">
                <StatCounter value={awa?.gratitude_events_30d ?? 0} decimals={0} />
              </div>
              <div className="text-[9px] text-[#4b5563]">gratitude events</div>
            </div>
          </div>
        </div>

        {/* Conditions checklist */}
        <ul className="relative mt-5 grid grid-cols-1 gap-x-8 border-t border-[#1c232d] pt-2 xl:grid-cols-2">
          {AWA_CONDITIONS.map((m) => {
            const cond = awa?.conditions?.[m.key];
            const met = cond?.met ?? false;
            const hasValue = cond?.value !== undefined;
            const hasThreshold = cond?.threshold !== undefined;
            const sym = m.comparison === "ge" ? "≥" : m.comparison === "le" ? "≤" : "·";
            return (
              <li
                key={m.key}
                aria-label={`AWA condition ${m.label}: ${met ? "met" : "not met"}`}
                className="flex items-center gap-3 border-b border-[#161b22] py-2.5"
              >
                {met ? (
                  <CheckCircle2 size={16} className="shrink-0 text-[#34d399]" />
                ) : (
                  <XCircle size={16} className="shrink-0 text-[#f43f5e]" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="text-[12px] font-medium text-[#d7dde6]">{m.label}</div>
                  <div className="text-[10px] text-[#4b5563]">{m.hint}</div>
                </div>
                <div className="trion-mono shrink-0 text-right text-[11px] tabular-nums">
                  {hasValue ? (
                    <span className="text-[#d7dde6]">
                      {fmt(cond?.value, govDecimals(cond?.value ?? 0))}
                    </span>
                  ) : null}
                  {hasValue && hasThreshold ? (
                    <span className="text-[#7d8896]"> {sym} </span>
                  ) : null}
                  {hasThreshold ? (
                    <span className="text-[#7d8896]">
                      {fmt(cond?.threshold, govDecimals(cond?.threshold ?? 0))}
                    </span>
                  ) : null}
                  {!hasValue && !hasThreshold ? (
                    <span className="text-[#7d8896]">enforced</span>
                  ) : null}
                </div>
                <span
                  className="trion-mono shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase"
                  style={{
                    borderColor: met ? "#10b98144" : "#f43f5e44",
                    background: met ? "#10b98112" : "#f43f5e12",
                    color: met ? "#34d399" : "#f43f5e",
                  }}
                >
                  {met ? "MET" : "FAIL"}
                </span>
              </li>
            );
          })}
        </ul>
      </section>

      {/* ── B. Love protocol ─────────────────────────────────────────────── */}
      <section aria-label="Love protocol global index" className="grid gap-4 lg:grid-cols-3">
        <div className="trion-panel p-5">
          <div className="flex items-center gap-2">
            <Heart size={13} className="text-[#f43f5e]" />
            <span className="trion-label">Love Protocol · Civilization CLV</span>
          </div>
          <div className="mt-3 flex justify-center">
            <GaugeRing
              value={CLV}
              max={1}
              label="CLV"
              sublabel="civilization-level value"
              color={healthColor}
              size={140}
            />
          </div>
          <div className="mt-2 flex justify-center">
            <span
              className="trion-mono rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider"
              style={{
                borderColor: `${healthColor}44`,
                background: `${healthColor}12`,
                color: healthColor,
              }}
            >
              network {networkHealth.toLowerCase()}
            </span>
          </div>
          <blockquote className="mt-4 rounded-lg border border-[#1c232d] border-l-2 border-l-[#f43f5e] bg-[#0a0d12] p-3">
            <p className="trion-mono text-[12px] font-bold text-[#d7dde6]">
              CLV = Σ(LV_i · weight_i) / N_entities
            </p>
            <p className="mt-1.5 text-[10px] leading-relaxed text-[#7d8896]">
              {love?.global_love_index?.description ??
                "Civilization-level behavioral health across all indexed chains."}
            </p>
          </blockquote>
        </div>

        <div className="trion-panel p-5 lg:col-span-2">
          <div className="flex items-center justify-between">
            <span className="trion-label">Entity Grade Distribution</span>
            <span className="trion-mono text-[10px] text-[#4b5563]">
              {totalEntities} entities indexed
            </span>
          </div>

          <div
            className="mt-4 flex h-3 overflow-hidden rounded-full border border-[#1c232d] bg-[#0a0d12]"
            role="img"
            aria-label={`Grade distribution: ${GRADE_ORDER.map(
              (g) => `${g} ${dist[g] ?? 0}`
            ).join(", ")}`}
          >
            {GRADE_ORDER.map((g) => {
              const count = dist[g] ?? 0;
              const pct = totalEntities > 0 ? (count / totalEntities) * 100 : 0;
              return (
                <div
                  key={g}
                  title={`${g} · ${count} (${pct.toFixed(1)}%)`}
                  style={{
                    width: `${pct}%`,
                    background: GRADE_COLORS[g],
                    opacity: 0.75,
                  }}
                />
              );
            })}
          </div>

          <div className="mt-4 space-y-3">
            {GRADE_ORDER.map((g) => {
              const count = dist[g] ?? 0;
              const pct = totalEntities > 0 ? count / totalEntities : 0;
              return (
                <div key={g} className="flex items-center gap-3" aria-label={`${g}: ${count} entities`}>
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ background: GRADE_COLORS[g] }}
                    aria-hidden
                  />
                  <span className="trion-label w-36 shrink-0">{g.replaceAll("_", " ")}</span>
                  <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-[#1c232d]">
                    <div
                      className="h-full rounded-full transition-all duration-700"
                      style={{ width: `${pct * 100}%`, background: GRADE_COLORS[g] }}
                    />
                  </div>
                  <span className="trion-mono w-24 shrink-0 text-right text-[11px] tabular-nums text-[#d7dde6]">
                    {count} · {(pct * 100).toFixed(1)}%
                  </span>
                </div>
              );
            })}
          </div>

          <div className="mt-4 grid grid-cols-2 gap-2 border-t border-[#1c232d] pt-3 sm:grid-cols-4">
            {[
              { label: "altruistic events", value: love?.trust_web_stats?.altruistic_events },
              { label: "trust edges", value: love?.trust_web_stats?.total_edges },
              { label: "cross-chain edges", value: love?.trust_web_stats?.cross_chain_edges },
              { label: "public goods USD", value: love?.trust_web_stats?.public_goods_volume_usd },
            ].map((s) => (
              <div key={s.label} className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-2.5">
                <div className="trion-label">{s.label}</div>
                <div className="trion-mono mt-0.5 text-[12px] font-bold tabular-nums text-[#d7dde6]">
                  {s.value ?? "—"}
                </div>
              </div>
            ))}
          </div>

          {(love?.unlock ? Object.keys(love.unlock) : []).length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              <span className="trion-mono text-[9px] uppercase tracking-wider text-[#4b5563]">
                unlocked
              </span>
              {Object.keys(love?.unlock ?? {}).map((u) => (
                <span
                  key={u}
                  className="trion-mono rounded border border-[#10b98133] bg-[#10b9810d] px-1.5 py-0.5 text-[9px] text-[#34d399]"
                >
                  {u.replaceAll("_", " ")}
                </span>
              ))}
            </div>
          )}
          {love?.storage_layer && (
            <p className="trion-mono mt-3 text-[10px] text-[#4b5563]">{love.storage_layer}</p>
          )}
        </div>
      </section>

      {/* ── C. Civilization leaderboard ──────────────────────────────────── */}
      <section aria-label="Civilization leaderboard" className="trion-panel">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#1c232d] px-5 py-3">
          <div className="flex items-center gap-2">
            <Trophy size={13} className="text-[#f59e0b]" />
            <span className="trion-label">Civilization Leaderboard</span>
          </div>
          <span className="trion-mono text-[10px] text-[#4b5563]">
            ranked by grade, then behavioral love value
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <caption className="sr-only">
              Civilization leaderboard of entities ranked by grade and love value
            </caption>
            <thead>
              <tr className="border-b border-[#1c232d]">
                <th scope="col" className="trion-label px-4 py-2">
                  Entity
                </th>
                <th scope="col" aria-sort="descending" className="trion-label px-4 py-2">
                  Grade
                </th>
                <th scope="col" className="trion-label px-4 py-2 text-right">
                  LV
                </th>
                <th scope="col" className="trion-label px-4 py-2 text-right">
                  CS
                </th>
                <th scope="col" className="trion-label px-4 py-2 text-right">
                  PG
                </th>
                <th scope="col" className="trion-label px-4 py-2 text-right">
                  Longevity (yrs)
                </th>
              </tr>
            </thead>
            <tbody>
              {board.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-[12px] text-[#7d8896]">
                    Awaiting leaderboard telemetry…
                  </td>
                </tr>
              ) : (
                board.map((e, i) => (
                  <tr
                    key={e.entity}
                    className="border-b border-[#161b22] transition-colors hover:bg-[#ffffff04]"
                  >
                    <td className="px-4 py-2.5">
                      <span className="trion-mono mr-2 text-[10px] text-[#4b5563]">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span className="trion-mono text-[11px] text-[#d7dde6]">{e.entity}</span>
                    </td>
                    <td className="px-4 py-2.5">
                      <GradeBadge grade={e.grade} />
                    </td>
                    <td className="px-4 py-2.5 text-right trion-mono text-[11px] tabular-nums text-[#34d399]">
                      {e.lv.toFixed(3)}
                    </td>
                    <td className="px-4 py-2.5 text-right trion-mono text-[11px] tabular-nums text-[#22d3ee]">
                      {e.cs.toFixed(3)}
                    </td>
                    <td className="px-4 py-2.5 text-right trion-mono text-[11px] tabular-nums text-[#a78bfa]">
                      {e.pg.toFixed(3)}
                    </td>
                    <td className="px-4 py-2.5 text-right trion-mono text-[11px] tabular-nums text-[#7d8896]">
                      {e.longevity_yrs.toFixed(1)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* ── D. Falsifiability registry ───────────────────────────────────── */}
      <section aria-label="Falsifiability registry" className="trion-panel">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#1c232d] px-5 py-3">
          <div className="flex items-center gap-2">
            <FlaskConical size={13} className="text-[#a78bfa]" />
            <span className="trion-label">
              Falsifiability Registry · {fals?.whitepaper_ref ?? "Chapter 14.2"}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {(
              [
                ["passing", falsSummary.passing, "#34d399"],
                ["monitoring", falsSummary.monitoring, "#f59e0b"],
                ["conjecture", falsSummary.conjecture, "#a78bfa"],
                ["failing", falsSummary.failing, "#f43f5e"],
              ] as Array<[string, number | undefined, string]>
            ).map(([label, value, color]) => (
              <span
                key={label}
                className="trion-mono rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase tabular-nums"
                style={{
                  borderColor: `${color}44`,
                  background: `${color}12`,
                  color,
                }}
              >
                {value ?? 0} {label}
              </span>
            ))}
            {falsSummary.integrity && (
              <span className="trion-mono rounded border border-[#10b98144] bg-[#10b98112] px-1.5 py-0.5 text-[9px] font-bold uppercase text-[#34d399]">
                registry integrity
              </span>
            )}
          </div>
        </div>
        <div className="max-h-96 overflow-y-auto overflow-x-auto">
          <table className="w-full text-left">
            <caption className="sr-only">
              Falsifiability registry of claims with live status
            </caption>
            <thead className="sticky top-0 bg-[#0d1117]">
              <tr className="border-b border-[#1c232d]">
                {["ID", "Claim", "Plane", "Status", "N", "Falsification test", "Window"].map((h) => (
                  <th key={h} scope="col" className="trion-label px-4 py-2">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {falsRows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-6 text-center text-[12px] text-[#7d8896]">
                    Awaiting falsifiability registry…
                  </td>
                </tr>
              ) : (
                falsRows.map((c) => {
                  const sc = FALS_STATUS_COLORS[c.status] ?? "#7d8896";
                  return (
                    <tr
                      key={c.id}
                      title={c.notes}
                      className="border-b border-[#161b22] align-top transition-colors hover:bg-[#ffffff04]"
                    >
                      <td className="px-4 py-2.5">
                        <div className="trion-mono text-[11px] font-bold text-[#34d399]">{c.id}</div>
                        <div className="trion-mono text-[9px] text-[#4b5563]">
                          {c.last_check
                            ? new Date(c.last_check * 1000).toLocaleTimeString("en-GB", {
                                hour12: false,
                              })
                            : "—"}
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-[11px] text-[#d7dde6]">{c.claim}</td>
                      <td className="px-4 py-2.5 trion-mono text-[10px] text-[#7d8896]">
                        {c.plane ?? "—"}
                      </td>
                      <td className="px-4 py-2.5">
                        <span
                          className="trion-mono rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase"
                          style={{ borderColor: `${sc}44`, background: `${sc}12`, color: sc }}
                        >
                          {c.status}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 trion-mono text-[10px] tabular-nums text-[#d7dde6]">
                        {c.sample_size ?? 0}
                      </td>
                      <td className="max-w-sm px-4 py-2.5">
                        <div className="text-[10px] leading-relaxed text-[#7d8896]">
                          {c.test_metric ?? "—"}
                        </div>
                        {c.threshold && (
                          <div className="trion-mono mt-0.5 text-[9px] text-[#4b5563]">
                            gate · {c.threshold}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-2.5 trion-mono text-[10px] text-[#7d8896]">
                        {c.window ?? "—"}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        <div className="border-t border-[#1c232d] px-5 py-3">
          <p className="text-[11px] leading-relaxed text-[#7d8896]">
            {fals?.disclosure ??
              "Explicit conditions under which the model would be wrong. FAILING conditions indicate model invalidation."}
          </p>
          {fals?.live_evidence?.note && (
            <p className="mt-1 text-[10px] leading-relaxed text-[#4b5563]">
              {fals.live_evidence.note}
            </p>
          )}
        </div>
      </section>

      {/* ── E. Institutional rights ──────────────────────────────────────── */}
      <section aria-label="Institutional rights" className="trion-panel">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#1c232d] px-5 py-3">
          <span className="trion-label">Institutional Rights · Protocol Guarantees</span>
          <span className="trion-mono rounded-full border border-[#a78bfa44] bg-[#a78bfa12] px-2.5 py-1 text-[9px] font-bold uppercase tracking-wider text-[#a78bfa]">
            static reference · protocol constants
          </span>
        </div>
        <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-4">
          {RIGHTS_CARDS.map((r) => (
            <div
              key={r.title}
              className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-4 transition-colors hover:border-[#2a3441]"
            >
              <div className="flex items-center justify-between">
                {r.icon}
                <span className="trion-mono rounded border border-[#1c232d] bg-[#0d1117] px-1.5 py-0.5 text-[9px] text-[#7d8896]">
                  {r.tag}
                </span>
              </div>
              <div className="mt-2.5 text-[12px] font-semibold text-[#d7dde6]">{r.title}</div>
              <p className="mt-1.5 text-[10px] leading-relaxed text-[#7d8896]">{r.detail}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
