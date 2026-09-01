"use client";

import {
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  CornerDownRight,
  Cpu,
  Crosshair,
  DoorOpen,
  GitBranch,
  Hourglass,
  Landmark,
  Loader2,
  Lock,
  Play,
  Radar,
  Repeat,
  Route as RouteIcon,
  Scale,
  ShieldAlert,
  Timer,
  Undo2,
  Users,
  XCircle,
  Zap,
} from "lucide-react";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { useTrionPoll } from "@/lib/trion/hooks";
import { trionPost } from "@/lib/trion/client";
import { GaugeRing, MeterBar, StatCounter } from "@/components/trion/viz/primitives";
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

/* ── Local view-level types mirroring backend payloads ───────────────────── */

interface RouteSimResponse {
  route: {
    route_id: string;
    route_type: string;
    anchor_chain: number;
    execution_chain: number;
    gas_total: number;
    finality_confidence: number;
    beo_continuity: number;
    cc_coherence: number;
  } | null;
  btcp_score: number;
  reason?: string;
  whitepaper?: string;
}

interface StreamerStatus {
  status?: string;
  message?: string;
  total_bhs?: number;
  bhs_per_second?: number;
  chains_active?: number;
  running?: boolean;
}

/* ── Protocol constants (K1 / D3 resolution reference values) ─────────────── */

const CANDIDATE_CHAINS = [
  { id: 1, name: "Ethereum", tag: "L1" },
  { id: 137, name: "Polygon", tag: "PoS" },
  { id: 8453, name: "Base", tag: "L2" },
];

const CHAIN_TONES: Record<number, string> = { 1: "#34d399", 137: "#a78bfa", 8453: "#22d3ee" };

const GAS_REFERENCE = 31.0;
const CC_COHERENCE: Record<number, number> = { 1: 0.9, 137: 0.85, 8453: 0.87 };
const FINALITY_DIST: Record<number, number> = { 1: 12.0, 137: 3.0, 8453: 5.0 };
const VALIDATOR_COUNTS: Record<number, number> = { 1: 50, 137: 30, 8453: 20 };

type PresetId = "high" | "stressed" | "adversarial";

interface Preset {
  label: string;
  hint: string;
  intent: number;
  nl: Record<number, number>;
  gas: Record<number, number>;
  mf: Record<number, number>;
}

const PRESETS: Record<PresetId, Preset> = {
  high: {
    label: "HIGH LIQUIDITY",
    hint: "deep liquidity · minimal manipulation fingerprint — the healthy-network baseline",
    intent: 15000,
    nl: { 1: 0.85, 137: 0.78, 8453: 0.81 },
    gas: { 1: 31.0, 137: 0.5, 8453: 2.0 },
    mf: { 1: 0.02, 137: 0.05, 8453: 0.03 },
  },
  stressed: {
    label: "STRESSED",
    hint: "thin liquidity (NL 0.40/0.35/0.40) with elevated manipulation (MF 0.15/0.20/0.18)",
    intent: 15000,
    nl: { 1: 0.4, 137: 0.35, 8453: 0.4 },
    gas: { 1: 31.0, 137: 0.5, 8453: 2.0 },
    mf: { 1: 0.15, 137: 0.2, 8453: 0.18 },
  },
  adversarial: {
    label: "ADVERSARIAL",
    hint: "attack concentrated on chain 137 — MF 0.55/0.60/0.62 crushes the route score (fail-closed territory)",
    intent: 15000,
    nl: { 1: 0.85, 137: 0.78, 8453: 0.81 },
    gas: { 1: 31.0, 137: 0.5, 8453: 2.0 },
    mf: { 1: 0.55, 137: 0.6, 8453: 0.62 },
  },
};

/** K1 priority ladder (display order) — backend enum names normalized. */
const ROUTE_LADDER = ["NETTING", "SINGLE_CHAIN", "MULTIHOP", "PARALLEL", "BITP", "DEFERRED", "SPLIT"];

/** BIBL three-tier latency budget (D3 Resolution). */
const BIBL_TIERS = [
  {
    tier: "T1",
    icon: <Radar size={13} />,
    name: "Per-Block Scanning",
    target: "continuous",
    fraction: 1,
    color: "#a78bfa",
    desc: "BIBL state cache refreshed every block on every chain — always-on pre-computation, outside the intent-critical budget.",
  },
  {
    tier: "T2",
    icon: <Cpu size={13} />,
    name: "Candidate Evaluation",
    target: "<50ms",
    fraction: 0.25,
    color: "#10b981",
    desc: "Up to N×7 = 600 candidate routes scored per intent against the cached BIBL state.",
  },
  {
    tier: "T3",
    icon: <Zap size={13} />,
    name: "Execution Verification",
    target: "<150ms",
    fraction: 0.75,
    color: "#22d3ee",
    desc: "Single execution RPC check — escrow opens only after final on-chain verification.",
  },
];

/** View-scoped animation CSS (arrow dash flow + latency-bar sweep). */
const BTCP_LOCAL_CSS = `
@keyframes btcp-dash { to { background-position-x: 20px; } }
@keyframes btcp-sweep { 0% { transform: translateX(-120%); } 100% { transform: translateX(320%); } }
.btcp-arrow-track {
  height: 2px; width: 44px; border-radius: 9999px;
  background-image: repeating-linear-gradient(90deg, rgba(52,211,153,0.85) 0 5px, transparent 5px 20px);
  background-size: 20px 2px;
  animation: btcp-dash 0.7s linear infinite;
}
.btcp-sweep {
  position: absolute; inset: 0; border-radius: 9999px;
  background: linear-gradient(90deg, transparent, rgba(215,221,230,0.30), transparent);
  animation: btcp-sweep 2.6s linear infinite;
}`;

/* ── View ─────────────────────────────────────────────────────────────────── */

export function BtcpView() {
  /* D. Streamer (polled every 5s) */
  const { data: streamer, lastUpdated: streamerTs } = useTrionPoll<StreamerStatus>(
    "btcp/streamer/status",
    5000
  );
  const isRunning =
    streamer?.status === "RUNNING" || streamer?.status === "STARTED" || streamer?.running === true;
  const [starting, setStarting] = useState(false);
  const [startNote, setStartNote] = useState<string | null>(null);

  const startStreamer = async () => {
    setStarting(true);
    setStartNote(null);
    try {
      await trionPost<Record<string, unknown>>("btcp/streamer/start", {});
      setStartNote("start issued — 5s poll will confirm");
    } catch (e) {
      setStartNote(e instanceof Error ? e.message : "streamer start failed");
    } finally {
      setStarting(false);
    }
  };

  /* A. Route simulator state */
  const [activePreset, setActivePreset] = useState<PresetId | null>("high");
  const [intentValue, setIntentValue] = useState(PRESETS.high.intent);
  const [nl, setNl] = useState<Record<number, number>>({ ...PRESETS.high.nl });
  const [gas, setGas] = useState<Record<number, number>>({ ...PRESETS.high.gas });
  const [mf, setMf] = useState<Record<number, number>>({ ...PRESETS.high.mf });
  const [result, setResult] = useState<RouteSimResponse | null>(null);
  const [simulating, setSimulating] = useState(false);
  const [simError, setSimError] = useState<string | null>(null);

  const applyPreset = (p: PresetId) => {
    setActivePreset(p);
    setIntentValue(PRESETS[p].intent);
    setNl({ ...PRESETS[p].nl });
    setGas({ ...PRESETS[p].gas });
    setMf({ ...PRESETS[p].mf });
  };

  const updateParam = (field: "nl" | "gas" | "mf", chainId: number, value: number) => {
    setActivePreset(null);
    if (field === "nl") setNl((s) => ({ ...s, [chainId]: value }));
    else if (field === "gas") setGas((s) => ({ ...s, [chainId]: value }));
    else setMf((s) => ({ ...s, [chainId]: value }));
  };

  const simulate = async () => {
    setSimulating(true);
    setSimError(null);
    try {
      const body = {
        intent_value: intentValue,
        nl_scores: nl,
        gas_forecasts: gas,
        gas_reference: GAS_REFERENCE,
        cc_coherence: CC_COHERENCE,
        mf_scores: mf,
        finality_dist: FINALITY_DIST,
        candidate_chains: CANDIDATE_CHAINS.map((c) => c.id),
        validator_counts: VALIDATOR_COUNTS,
      };
      const r = await trionPost<RouteSimResponse>("btcp/route", body);
      setResult(r);
    } catch (e) {
      setSimError(e instanceof Error ? e.message : "route simulation failed");
    } finally {
      setSimulating(false);
    }
  };

  /* Resolve the baseline HIGH LIQUIDITY route once on mount. */
  const bootstrapped = useRef(false);
  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    void simulate();
  }, []);

  /* Result derivation */
  const route = result?.route ?? null;
  const score = result?.btcp_score ?? 0;
  const scoreColor = score > 0.5 ? "#10b981" : score > 0.3 ? "#f59e0b" : "#f43f5e";
  const selectedType = route ? route.route_type.toUpperCase().replace(/_/g, "") : null;
  const execName = (id: number) => CANDIDATE_CHAINS.find((c) => c.id === id)?.name ?? `chain ${id}`;

  /* Minimum viable route gates (client-side mirror of route_is_valid) */
  const validity = useMemo(() => {
    if (!route) return null;
    const exec = route.execution_chain;
    const nlExec = nl[exec] ?? 0;
    const vCount = VALIDATOR_COUNTS[exec] ?? 0;
    return [
      { label: "NL > 0.05", pass: nlExec > 0.05, detail: `NL${exec} = ${nlExec.toFixed(2)}` },
      { label: "score > 0.10", pass: score > 0.1, detail: `BTCP = ${score.toFixed(3)}` },
      {
        label: "finality > 0.80",
        pass: route.finality_confidence > 0.8,
        detail: `conf = ${route.finality_confidence.toFixed(3)}`,
      },
      { label: "validators ≥ 3", pass: vCount >= 3, detail: `${vCount} validators` },
    ];
  }, [route, nl, score]);

  const gasNorm = route ? Math.max(0, 1 - route.gas_total / GAS_REFERENCE) : 0;

  return (
    <div className="space-y-4">
      <style>{BTCP_LOCAL_CSS}</style>

      {/* ── A. Route Simulator ──────────────────────────────────────────── */}
      <section aria-label="BTCP route simulator" className="trion-panel p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <RouteIcon size={15} className="text-[#34d399]" />
            <span className="trion-label">BTCP Zero-Bridge · Route Simulator</span>
          </div>
          <span className="trion-mono text-[10px] text-[#4b5563]">
            K1 Resolution · tier-2 intent scoring · POST btcp/route
          </span>
        </div>

        {/* Formula strip — the K1 scoring function, front and center */}
        <div className="mt-3 rounded-lg border border-[#10b98133] bg-[#0a0d12] p-3.5">
          <div className="trion-mono text-[13px] font-bold leading-relaxed text-[#34d399] sm:text-[14px]">
            BTCP = (0.25·NL + 0.20·gas + 0.20·finality + 0.15·CC + 0.20·BEO) · (1 − MF)
          </div>
          <div className="trion-mono mt-1 text-[10px] leading-relaxed text-[#4b5563]">
            W_NL .25 · W_GAS .20 · W_FIN .20 · W_COH .15 · W_BEO .20 — gas normalized (1 − g/g_ref), g_ref = $
            {GAS_REFERENCE.toFixed(2)} rolling 30-day P99
          </div>
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {/* Controls */}
          <div>
            <div className="flex flex-wrap items-center gap-1.5">
              {(Object.keys(PRESETS) as PresetId[]).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => applyPreset(p)}
                  aria-pressed={activePreset === p}
                  className={`trion-mono rounded border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider transition-colors ${
                    activePreset === p
                      ? "border-[#10b98166] bg-[#10b98112] text-[#34d399]"
                      : "border-[#1c232d] bg-[#0d1117] text-[#7d8896] hover:border-[#2a3441] hover:text-[#d7dde6]"
                  }`}
                >
                  {PRESETS[p].label}
                </button>
              ))}
            </div>
            <p className="mt-1.5 text-[10px] leading-relaxed text-[#4b5563]">
              {activePreset ? PRESETS[activePreset].hint : "custom parameters — drag sliders to explore the decision surface"}
            </p>

            {/* Intent + simulate */}
            <div className="mt-3 flex flex-wrap items-end gap-3">
              <label className="min-w-[150px] flex-1">
                <span className="trion-label">Intent value (USD)</span>
                <Input
                  type="number"
                  min={0}
                  step={500}
                  value={intentValue}
                  onChange={(e) => {
                    setActivePreset(null);
                    setIntentValue(Math.max(0, Number(e.target.value)));
                  }}
                  aria-label="Intent value in USD"
                  className="trion-mono mt-1 h-8 rounded border-[#1c232d] bg-[#0a0d12] px-2.5 text-[11px] tabular-nums text-[#d7dde6] focus-visible:border-[#10b981] focus-visible:ring-0"
                />
              </label>
              <Button
                type="button"
                onClick={() => void simulate()}
                disabled={simulating}
                aria-label="Simulate BTCP route"
                className="h-8 gap-1.5 rounded bg-[#10b981] px-4 trion-mono text-[11px] font-bold uppercase tracking-wider text-[#06231a] hover:bg-[#34d399]"
              >
                {simulating ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
                Simulate Route
              </Button>
            </div>

            {/* Per-chain parameters */}
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              {CANDIDATE_CHAINS.map((c) => (
                <div
                  key={c.id}
                  role="group"
                  aria-label={`${c.name} routing parameters`}
                  className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-3"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <span
                        className="h-2 w-2 shrink-0 rounded-full"
                        style={{ background: CHAIN_TONES[c.id] }}
                        aria-hidden
                      />
                      <span className="truncate text-[12px] font-semibold text-[#d7dde6]">{c.name}</span>
                      <span className="trion-mono text-[9px] text-[#4b5563]">{c.tag}</span>
                    </div>
                    <span className="trion-mono text-[10px] tabular-nums text-[#4b5563]">id {c.id}</span>
                  </div>

                  <div className="mt-3 space-y-3">
                    <div>
                      <div className="flex items-baseline justify-between">
                        <span className="trion-label">NL score</span>
                        <span className="trion-mono text-[10px] tabular-nums text-[#34d399]">
                          {(nl[c.id] ?? 0).toFixed(2)}
                        </span>
                      </div>
                      <Slider
                        value={[nl[c.id] ?? 0]}
                        min={0}
                        max={1}
                        step={0.01}
                        onValueChange={(v) => updateParam("nl", c.id, v[0] ?? 0)}
                        aria-label={`Net liquidity score for ${c.name}`}
                        className="mt-1.5 [&_[data-slot=slider-range]]:bg-[#10b981] [&_[data-slot=slider-thumb]]:border-[#10b981] [&_[data-slot=slider-thumb]]:bg-[#0a0d12] [&_[data-slot=slider-track]]:bg-[#1c232d]"
                      />
                    </div>

                    <div>
                      <div className="flex items-baseline justify-between">
                        <span className="trion-label">MF score</span>
                        <span className="trion-mono text-[10px] tabular-nums text-[#f43f5e]">
                          {(mf[c.id] ?? 0).toFixed(2)}
                        </span>
                      </div>
                      <Slider
                        value={[mf[c.id] ?? 0]}
                        min={0}
                        max={1}
                        step={0.01}
                        onValueChange={(v) => updateParam("mf", c.id, v[0] ?? 0)}
                        aria-label={`Manipulation fingerprint score for ${c.name}`}
                        className="mt-1.5 [&_[data-slot=slider-range]]:bg-[#f43f5e] [&_[data-slot=slider-thumb]]:border-[#f43f5e] [&_[data-slot=slider-thumb]]:bg-[#0a0d12] [&_[data-slot=slider-track]]:bg-[#1c232d]"
                      />
                    </div>

                    <div>
                      <span className="trion-label">Gas forecast (USD)</span>
                      <Input
                        type="number"
                        min={0}
                        step={0.5}
                        value={gas[c.id] ?? 0}
                        onChange={(e) => updateParam("gas", c.id, Math.max(0, Number(e.target.value)))}
                        aria-label={`Gas forecast in USD for ${c.name}`}
                        className="trion-mono mt-1 h-7 rounded border-[#1c232d] bg-[#0d1117] px-2 text-[11px] tabular-nums text-[#d7dde6] focus-visible:border-[#10b981] focus-visible:ring-0"
                      />
                    </div>
                  </div>

                  <div className="trion-mono mt-2.5 border-t border-[#161b22] pt-2 text-[9px] leading-relaxed text-[#4b5563]">
                    CC {(CC_COHERENCE[c.id] ?? 0).toFixed(2)} · finality {FINALITY_DIST[c.id] ?? 0}s · validators{" "}
                    {VALIDATOR_COUNTS[c.id] ?? 0}
                  </div>
                </div>
              ))}
            </div>

            <div className="trion-mono mt-3 border-t border-[#161b22] pt-2.5 text-[9px] leading-relaxed text-[#4b5563]">
              POST btcp/route · intent ${intentValue.toLocaleString()} · NL{" "}
              {CANDIDATE_CHAINS.map((c) => (nl[c.id] ?? 0).toFixed(2)).join("/")} · MF{" "}
              {CANDIDATE_CHAINS.map((c) => (mf[c.id] ?? 0).toFixed(2)).join("/")} · gas{" "}
              {CANDIDATE_CHAINS.map((c) => `$${(gas[c.id] ?? 0).toFixed(2)}`).join("/")}
            </div>
          </div>

          {/* Result card */}
          <div
            className="rounded-lg border border-[#1c232d] bg-[#0a0d12] p-4"
            aria-live="polite"
            aria-label="Route simulation result"
          >
            {simError && (
              <div className="rounded-md border border-[#f43f5e44] bg-[#f43f5e0f] p-3">
                <span className="trion-mono text-[11px] text-[#f43f5e]">{simError}</span>
              </div>
            )}

            {!result && !simError && (
              <div className="flex h-full min-h-[220px] items-center justify-center">
                <span className="trion-mono text-[11px] text-[#7d8896]">
                  {simulating ? "scoring candidate routes…" : "run a simulation to resolve a route"}
                </span>
              </div>
            )}

            {result && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <span className="trion-label">Resolved Route</span>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2">
                      <Badge
                        variant="outline"
                        className="trion-mono rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider"
                        style={{
                          color: route ? "#34d399" : "#f43f5e",
                          borderColor: route ? "#10b98144" : "#f43f5e44",
                          background: route ? "#10b98112" : "#f43f5e12",
                        }}
                      >
                        {route ? route.route_type : "no route"}
                      </Badge>
                      {route && (
                        <span className="trion-mono text-[10px] text-[#4b5563]">{route.route_id}</span>
                      )}
                      {result.whitepaper && (
                        <span className="trion-mono text-[10px] text-[#4b5563]">· {result.whitepaper}</span>
                      )}
                    </div>
                    <div className="trion-mono mt-1.5 text-[10px] tabular-nums text-[#7d8896]">
                      intent ${intentValue.toLocaleString()} · exec {execName(route?.execution_chain ?? 0)}
                    </div>
                  </div>
                  <GaugeRing
                    value={score}
                    label="BTCP"
                    sublabel="route score · K1"
                    color={scoreColor}
                    size={108}
                  />
                </div>

                {route ? (
                  <>
                    {/* Anchor → execution flow */}
                    <div className="rounded-md border border-[#1c232d] bg-[#0d1117] p-3">
                      <div className="flex flex-col items-stretch gap-1.5 sm:flex-row sm:items-center">
                        <ChainBox id={route.anchor_chain} role="Anchor" />
                        <FlowArrow />
                        <ChainBox id={route.execution_chain} role="Execution" accent />
                      </div>
                      <div className="trion-mono mt-2.5 text-[10px] leading-relaxed text-[#4b5563]">
                        gas total ${route.gas_total.toFixed(2)} → norm {gasNorm.toFixed(2)} · BEO{" "}
                        {route.beo_continuity.toFixed(2)} · CC {route.cc_coherence.toFixed(2)}
                      </div>
                    </div>

                    {/* Minimum viable route gates */}
                    {validity && (
                      <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                        {validity.map((v) => (
                          <div
                            key={v.label}
                            className="flex items-center gap-2 rounded-md border border-[#1c232d] bg-[#0d1117] px-2.5 py-1.5"
                          >
                            {v.pass ? (
                              <CheckCircle2 size={13} className="shrink-0 text-[#34d399]" />
                            ) : (
                              <XCircle size={13} className="shrink-0 text-[#f43f5e]" />
                            )}
                            <span className="trion-mono text-[10px] font-bold text-[#d7dde6]">{v.label}</span>
                            <span className="trion-mono ml-auto text-[10px] tabular-nums text-[#4b5563]">
                              {v.detail}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Route component meters */}
                    <div className="space-y-2.5">
                      <MeterBar
                        label="FINALITY CONF"
                        value={route.finality_confidence}
                        threshold={0.8}
                        color="#10b981"
                      />
                      <MeterBar label="BEO CONTINUITY" value={route.beo_continuity} color="#22d3ee" />
                      <MeterBar label="CC COHERENCE" value={route.cc_coherence} color="#a78bfa" />
                    </div>
                  </>
                ) : (
                  <FailClosedBanner reason={result.reason ?? "no_valid_route"} score={score} />
                )}

                {/* K1 priority ladder */}
                <div>
                  <span className="trion-label">Route Type Ladder · K1 preference</span>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1">
                    {ROUTE_LADDER.map((rt, i) => {
                      const active = selectedType === rt;
                      return (
                        <Fragment key={rt}>
                          {i > 0 && <ChevronRight size={10} className="text-[#2a3441]" aria-hidden />}
                          <span
                            aria-current={active ? "true" : undefined}
                            className={`trion-mono rounded border px-2 py-0.5 text-[9px] font-bold tracking-wider transition-colors ${
                              active
                                ? "border-[#10b98166] bg-[#10b98112] text-[#34d399]"
                                : "border-[#1c232d] bg-[#0d1117] text-[#4b5563]"
                            }`}
                          >
                            {rt}
                          </span>
                        </Fragment>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ── B. BIBL Engine + C. Escrow state machine ─────────────────────── */}
      <section className="grid gap-4 lg:grid-cols-2" aria-label="BIBL engine and escrow state machine">
        {/* B. BIBL three-tier latency budget */}
        <div className="trion-panel p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="trion-label">BIBL Engine · Three-Tier Latency</span>
            </div>
            <span className="trion-mono text-[10px] text-[#4b5563]">D3 Resolution</span>
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-[#7d8896]">
            Behavioral Intent Bridge Layer — per-block pre-computation keeps the intent-critical path under 200ms.
          </p>

          <div className="mt-4 space-y-3.5">
            {BIBL_TIERS.map((t) => (
              <div key={t.tier}>
                <div className="flex flex-wrap items-baseline justify-between gap-x-2">
                  <span className="flex items-center gap-1.5">
                    <span style={{ color: t.color }}>{t.icon}</span>
                    <span className="trion-mono text-[10px] font-bold text-[#d7dde6]">
                      {t.tier} · {t.name.toUpperCase()}
                    </span>
                  </span>
                  <span className="trion-mono text-[10px] tabular-nums font-bold" style={{ color: t.color }}>
                    {t.target}
                    {t.fraction < 1 ? ` · ${Math.round(t.fraction * 100)}% budget` : ""}
                  </span>
                </div>
                <div className="relative mt-1.5 h-2 overflow-hidden rounded-full bg-[#1c232d]">
                  <div
                    className="relative h-full overflow-hidden rounded-full transition-all duration-700"
                    style={{ width: `${t.fraction * 100}%`, background: t.color }}
                  >
                    <span className="btcp-sweep" aria-hidden />
                  </div>
                </div>
                <div className="mt-1 text-[10px] leading-relaxed text-[#7d8896]">{t.desc}</div>
              </div>
            ))}
          </div>

          <div className="mt-4 border-t border-[#1c232d] pt-3">
            <div className="flex items-baseline justify-between">
              <span className="flex items-center gap-1.5">
                <Timer size={13} className="text-[#f59e0b]" />
                <span className="trion-mono text-[10px] font-bold text-[#d7dde6]">
                  END-TO-END · INTENT-CRITICAL BUDGET
                </span>
              </span>
              <span className="trion-mono text-[10px] font-bold tabular-nums text-[#f59e0b]">&lt;200ms</span>
            </div>
            <div className="relative mt-1.5 h-2 overflow-hidden rounded-full bg-[#1c232d]">
              <div className="flex h-full w-full">
                <div
                  className="relative h-full overflow-hidden"
                  style={{ width: "25%", background: "#10b981" }}
                >
                  <span className="btcp-sweep" aria-hidden />
                </div>
                <div
                  className="relative h-full overflow-hidden rounded-r-full"
                  style={{ width: "75%", background: "#22d3ee" }}
                >
                  <span className="btcp-sweep" aria-hidden />
                </div>
              </div>
            </div>
            <div className="trion-mono mt-1 flex justify-between text-[9px] text-[#4b5563]">
              <span>0ms</span>
              <span>T2 50ms</span>
              <span>200ms cap</span>
            </div>
          </div>
        </div>

        {/* C. Escrow state machine — static protocol reference */}
        <div className="trion-panel p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Landmark size={14} className="text-[#34d399]" />
              <span className="trion-label">Escrow State Machine</span>
            </div>
            <span className="trion-mono rounded border border-[#1c232d] bg-[#0d1117] px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-[#4b5563]">
              static protocol reference
            </span>
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-[#7d8896]">
            Two-phase execution confirmation (G1) — every escrowed transfer resolves or reverts; funds are never
            stuck.
          </p>

          <div className="mt-4 flex flex-col items-stretch gap-2 sm:flex-row sm:items-center">
            <EscrowNode
              name="HOLDING"
              tone="#d7dde6"
              icon={<Lock size={12} />}
              desc="intent assets locked · two-phase execution confirm (G1)"
            />
            <FlowArrow />
            <EscrowNode
              name="PENDING_AKASHIC"
              tone="#22d3ee"
              icon={<Hourglass size={12} />}
              desc="24h Akashic recovery window — E1 availability guarantee"
            />
            <FlowArrow />
            <EscrowNode
              name="RELEASED"
              tone="#34d399"
              icon={<CheckCircle2 size={12} />}
              desc="destination finality confirmed · escrow closed"
            />
          </div>

          <div className="mt-4 border-t border-dashed border-[#2a3441] pt-3">
            <div className="flex items-center gap-2">
              <CornerDownRight size={13} className="text-[#4b5563]" aria-hidden />
              <span className="trion-label">exceptional terminals — funds are never stuck</span>
            </div>
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
              <EscrowNode
                dashed
                name="REVERTED"
                tone="#f43f5e"
                icon={<Undo2 size={12} />}
                desc="multi-hop cascade revert (Gap 9) — funds return to source on route failure"
              />
              <EscrowNode
                dashed
                name="EMERGENCY_ESCAPE"
                tone="#f59e0b"
                icon={<DoorOpen size={12} />}
                desc="7-day hatch — triggerable by anyone · absolute max lock (Gap 8)"
              />
            </div>
          </div>

          <div className="trion-mono mt-3 border-t border-[#161b22] pt-2.5 text-[9px] leading-relaxed text-[#4b5563]">
            revert reasons: TIMEOUT · COHERENCE_FAILURE · ROUTE_INVALID · MANUAL · AKASHIC_OUTAGE_24H ·
            CASCADE_REVERT · EMERGENCY_ESCAPE
          </div>
        </div>
      </section>

      {/* ── D. Streamer control ──────────────────────────────────────────── */}
      <section aria-label="Real-time BH streamer control" className="trion-panel p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              {isRunning && <span className="trion-live-dot" aria-hidden />}
              <span className="trion-label">Real-Time BH Streamer · BIBL Tier-1 Feed</span>
            </div>
            <p className="mt-1 text-[11px] leading-relaxed text-[#7d8896]">
              {isRunning
                ? "Streaming per-block behavioral hashes across live chains — feeding the BIBL state cache."
                : (streamer?.message ?? "Streamer idle — start it to feed the BIBL state cache.")}
            </p>
            <div className="trion-mono mt-1 text-[10px] text-[#4b5563]">
              {streamerTs
                ? `poll 5s · updated ${new Date(streamerTs).toLocaleTimeString("en-GB", { hour12: false })}`
                : "connecting…"}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-4">
              <div className="min-w-[86px]">
                <span className="trion-label">Total BHs</span>
                <div className="trion-mono text-lg font-bold tabular-nums text-[#d7dde6]">
                  <StatCounter value={streamer?.total_bhs ?? 0} />
                </div>
              </div>
              <div className="min-w-[86px]">
                <span className="trion-label">BH/s</span>
                <div className="trion-mono text-lg font-bold tabular-nums text-[#34d399]">
                  {(streamer?.bhs_per_second ?? 0).toFixed(1)}
                </div>
              </div>
              <div className="min-w-[86px]">
                <span className="trion-label">Chains</span>
                <div className="trion-mono text-lg font-bold tabular-nums text-[#22d3ee]">
                  {streamer?.chains_active ?? 0}
                </div>
              </div>
            </div>

            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 trion-mono text-[10px] font-bold uppercase tracking-wider ${
                isRunning
                  ? "border-[#10b98144] bg-[#10b98112] text-[#34d399]"
                  : "border-[#f59e0b44] bg-[#f59e0b12] text-[#f59e0b]"
              }`}
              role="status"
            >
              {isRunning ? (streamer?.status ?? "STARTED") : (streamer?.status ?? "STOPPED")}
            </span>

            {streamer && !isRunning && (
              <Button
                type="button"
                onClick={() => void startStreamer()}
                disabled={starting}
                aria-label="Start the real-time BH streamer"
                className="h-9 gap-1.5 rounded bg-[#10b981] px-4 trion-mono text-[11px] font-bold uppercase tracking-wider text-[#06231a] hover:bg-[#34d399]"
              >
                {starting ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                Start Streamer
              </Button>
            )}
            {startNote && !isRunning && (
              <span className="trion-mono text-[10px] text-[#f59e0b]">{startNote}</span>
            )}
          </div>
        </div>
      </section>

      {/* ── E. Protocol facts strip ───────────────────────────────────────── */}
      <section
        aria-label="BTCP protocol facts"
        className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5"
      >
        <FactCard
          icon={<Crosshair size={14} />}
          label="OOA Confidence"
          formula="conf = 0.85·(1−e^(−0.001·depth))"
          detail="off-order-activity model — detected OOA applies a ×1.5 confidence penalty"
        />
        <FactCard
          icon={<Users size={14} />}
          label="Validator Fees"
          formula="60 / 40 split"
          detail="anchor / execution validator fee split, plus coverage bonus for continuous BIBL feed"
        />
        <FactCard
          icon={<Scale size={14} />}
          label="Dispute Resolution"
          formula="3-of-5 · 72h"
          detail="annotator-majority resolution window · 500 bps challenge bond posted by disputant"
        />
        <FactCard
          icon={<Repeat size={14} />}
          label="Netting"
          formula="N(N−1)/2 pairs"
          detail="bilateral settlement pairs eliminated — 4,950 pairs avoided at 100 chains"
        />
        <FactCard
          icon={<GitBranch size={14} />}
          label="Fork Protocol"
          formula="67% weighted"
          detail="30-day suspension on forked chains · canonical = 50% validator + 30% TVL + 20% dev activity"
        />
      </section>
    </div>
  );
}

/* ── Local building blocks ────────────────────────────────────────────────── */

function ChainBox({ id, role, accent }: { id: number; role: string; accent?: boolean }) {
  const meta = CANDIDATE_CHAINS.find((c) => c.id === id);
  return (
    <div
      className={`flex-1 rounded-md border px-3 py-2 ${
        accent ? "border-[#10b98155] bg-[#10b9810a]" : "border-[#1c232d] bg-[#0a0d12]"
      }`}
    >
      <div className="trion-label">{role} chain</div>
      <div className="mt-0.5 flex items-baseline gap-2">
        <span
          className="trion-mono text-[13px] font-bold"
          style={{ color: accent ? "#34d399" : "#d7dde6" }}
        >
          {meta?.name ?? `chain ${id}`}
        </span>
        <span className="trion-mono text-[10px] tabular-nums text-[#4b5563]">id {id}</span>
      </div>
    </div>
  );
}

function FlowArrow() {
  return (
    <div className="flex items-center justify-center py-1 sm:px-1" aria-hidden>
      <div className="flex rotate-90 items-center gap-0.5 sm:rotate-0">
        <span className="btcp-arrow-track" />
        <ArrowRight size={12} className="text-[#34d399]" />
      </div>
    </div>
  );
}

function EscrowNode({
  name,
  desc,
  tone,
  icon,
  dashed,
}: {
  name: string;
  desc: string;
  tone: string;
  icon: React.ReactNode;
  dashed?: boolean;
}) {
  return (
    <div
      className={`flex-1 rounded-md border bg-[#0a0d12] px-3 py-2.5 ${dashed ? "border-dashed" : ""}`}
      style={{ borderColor: `${tone}55` }}
    >
      <div className="flex items-center gap-1.5">
        <span style={{ color: tone }}>{icon}</span>
        <span className="trion-mono text-[11px] font-bold" style={{ color: tone }}>
          {name}
        </span>
      </div>
      <div className="mt-1 text-[10px] leading-relaxed text-[#7d8896]">{desc}</div>
    </div>
  );
}

function FailClosedBanner({ reason, score }: { reason: string; score: number }) {
  return (
    <div className="rounded-md border border-[#f43f5e44] bg-[#f43f5e0d] p-4" role="alert">
      <div className="flex items-center gap-2">
        <ShieldAlert size={16} className="text-[#f43f5e]" />
        <span className="trion-mono text-[12px] font-bold uppercase tracking-wider text-[#f43f5e]">
          fail-closed — bridge refused
        </span>
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-[#7d8896]">
        reason <span className="trion-mono font-bold text-[#f43f5e]">{reason}</span> · score{" "}
        <span className="trion-mono tabular-nums text-[#f43f5e]">{score.toFixed(3)}</span> — every candidate was
        rejected by the minimum viable route gates (NL ≤ 0.05 · BTCP ≤ 0.10 · finality ≤ 0.80 · validators &lt; 3).
        No escrow opens; no bridge execution is attempted.
      </p>
    </div>
  );
}

function FactCard({
  icon,
  label,
  formula,
  detail,
}: {
  icon: React.ReactNode;
  label: string;
  formula: string;
  detail: string;
}) {
  return (
    <div className="trion-panel p-4 transition-colors hover:border-[#2a3441]">
      <div className="flex items-center justify-between">
        <span className="trion-label">{label}</span>
        <span className="text-[#4b5563]">{icon}</span>
      </div>
      <div className="trion-mono mt-1.5 text-[12px] font-bold leading-relaxed text-[#34d399]">{formula}</div>
      <div className="mt-1 text-[10px] leading-relaxed text-[#7d8896]">{detail}</div>
    </div>
  );
}
