"use client";

import { useMemo, useState } from "react";
import { useTrionPoll } from "@/lib/trion/hooks";
import { CoherenceRadar, MeterBar, Sparkline } from "@/components/trion/viz/primitives";
import type { TrionHealth } from "@/lib/trion/client";

interface ProfilesResponse {
  formula: string;
  asset_type_profiles: Record<
    string,
    { alpha: number; beta: number; gamma: number; delta: number; epsilon: number; description?: string }
  >;
  named_profiles: Record<
    string,
    { phi: number; m: number; sigma: number; k: number; anima: number; description?: string }
  >;
  whitepaper?: string;
}

interface SelfVerificationFeed {
  feed: Array<{ coherence_score: number; planes: Record<string, number> }>;
}

const PLANE_KEYS: Record<string, string> = {
  phi: "physical_component_fitness",
  m: "mental_intelligence_maintenance",
  sigma: "signal_transduction",
  k: "conscious_plane",
  a: "anima_transduction_integrity",
};

export function CoherenceView() {
  const { data: profiles } = useTrionPoll<ProfilesResponse>("coherence/profiles", 20000);
  const { data: selfFeed } = useTrionPoll<SelfVerificationFeed>("feed", 6000);
  const { data: health } = useTrionPoll<TrionHealth>("health", 5000);

  const [selectedProfile, setSelectedProfile] = useState<string>("BALANCED");

  const livePlanes = useMemo(() => {
    const p = selfFeed?.feed?.[0]?.planes ?? {};
    return {
      phi: Number(p[PLANE_KEYS.phi] ?? 0.55),
      m: Number(p[PLANE_KEYS.m] ?? 0.5),
      sigma: Number(p[PLANE_KEYS.sigma] ?? 0.6),
      k: Number(p[PLANE_KEYS.k] ?? 0.5),
      a: Number(p[PLANE_KEYS.a] ?? 0.45),
    };
  }, [selfFeed]);

  const profile = profiles?.named_profiles?.[selectedProfile];
  const weights = profile
    ? { alpha: profile.phi, beta: profile.m, gamma: profile.sigma, delta: profile.k, epsilon: profile.anima }
    : { alpha: 0.25, beta: 0.3, gamma: 0.25, delta: 0.1, epsilon: 0.1 };

  // C(t) computed live under the selected weight profile.
  const C = weights.alpha * livePlanes.phi + weights.beta * livePlanes.m + weights.gamma * livePlanes.sigma + weights.delta * livePlanes.k + weights.epsilon * livePlanes.a;
  const theta = health?.dynamic_threshold ?? 0.55;

  const cHistory = useMemo(
    () => (selfFeed?.feed ?? []).slice(0, 24).reverse().map((f) => f.coherence_score),
    [selfFeed]
  );

  const namedEntries = Object.entries(profiles?.named_profiles ?? {});
  const assetEntries = Object.entries(profiles?.asset_type_profiles ?? {});

  return (
    <div className="space-y-4">
      <section className="grid gap-4 lg:grid-cols-3">
        <div className="trion-panel p-5 lg:col-span-1">
          <div className="flex items-center justify-between">
            <span className="trion-label">Live Radar · Self-Verification Planes</span>
          </div>
          <div className="mt-2 flex justify-center">
            <CoherenceRadar values={livePlanes} threshold={theta} size={240} />
          </div>
          <div className="mt-2 space-y-2">
            <MeterBar label="Φ" value={livePlanes.phi} color="#10b981" threshold={theta} />
            <MeterBar label="M" value={livePlanes.m} color="#22d3ee" threshold={theta} />
            <MeterBar label="Σ" value={livePlanes.sigma} color="#a78bfa" threshold={theta} />
            <MeterBar label="K" value={livePlanes.k} color="#f59e0b" threshold={theta} />
            <MeterBar label="A" value={livePlanes.a} color="#f43f5e" threshold={theta} />
          </div>
        </div>

        <div className="trion-panel p-5 lg:col-span-2">
          <div className="trion-label">C(t) Under Selected Weight Profile</div>
          <p className="trion-mono mt-1 text-[11px] text-[#4b5563]">{profiles?.formula}</p>

          <div className="mt-4 rounded-lg border border-[#1c232d] bg-[#0a0d12] p-4">
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2">
              <span className="trion-mono text-lg font-bold text-[#34d399]">
                C(t) = {C.toFixed(4)}
              </span>
              <span className="trion-mono text-[12px] text-[#f59e0b]">Θ(t) = {theta.toFixed(4)}</span>
              <span
                className={`trion-mono rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${
                  C >= theta
                    ? "border-[#10b98144] bg-[#10b98112] text-[#34d399]"
                    : "border-[#f43f5e44] bg-[#f43f5e12] text-[#f43f5e]"
                }`}
              >
                {C >= theta ? "coherent" : "incoherent"}
              </span>
              <span className="ml-auto">
                <Sparkline data={cHistory.length > 1 ? cHistory : [C, C]} width={160} height={32} color="#34d399" />
              </span>
            </div>
            <div className="trion-mono mt-3 grid grid-cols-1 gap-1 text-[11px] text-[#7d8896] sm:grid-cols-2">
              <span>α·Φ = {weights.alpha.toFixed(2)} × {livePlanes.phi.toFixed(3)} = {(weights.alpha * livePlanes.phi).toFixed(4)}</span>
              <span>β·M = {weights.beta.toFixed(2)} × {livePlanes.m.toFixed(3)} = {(weights.beta * livePlanes.m).toFixed(4)}</span>
              <span>γ·Σ = {weights.gamma.toFixed(2)} × {livePlanes.sigma.toFixed(3)} = {(weights.gamma * livePlanes.sigma).toFixed(4)}</span>
              <span>δ·K = {weights.delta.toFixed(2)} × {livePlanes.k.toFixed(3)} = {(weights.delta * livePlanes.k).toFixed(4)}</span>
              <span className="sm:col-span-2">ε·A = {weights.epsilon.toFixed(2)} × {livePlanes.a.toFixed(3)} = {(weights.epsilon * livePlanes.a).toFixed(4)}</span>
            </div>
          </div>

          <div className="mt-4">
            <span className="trion-label">Select Weight Profile</span>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {namedEntries.map(([name]) => (
                <button
                  key={name}
                  onClick={() => setSelectedProfile(name)}
                  className={`trion-mono rounded border px-2.5 py-1 text-[10px] font-semibold transition-colors ${
                    selectedProfile === name
                      ? "border-[#10b98166] bg-[#10b98112] text-[#34d399]"
                      : "border-[#1c232d] bg-[#0d1117] text-[#7d8896] hover:border-[#2a3441] hover:text-[#d7dde6]"
                  }`}
                >
                  {name}
                </button>
              ))}
            </div>
            {profile?.description && (
              <p className="mt-2 text-[11px] text-[#7d8896]">{profile.description}</p>
            )}
          </div>
        </div>
      </section>

      {/* Named profiles table */}
      <section aria-label="Named coherence profiles" className="trion-panel">
        <div className="border-b border-[#1c232d] px-5 py-3">
          <span className="trion-label">Named Weight Profiles (α β γ δ ε)</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-[#1c232d]">
                {["Profile", "α · Φ", "β · M", "γ · Σ", "δ · K", "ε · A", "Σ weights", "Description"].map((h) => (
                  <th key={h} className="trion-label px-4 py-2">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {namedEntries.map(([name, p]) => {
                const sum = p.phi + p.m + p.sigma + p.k + p.anima;
                return (
                  <tr
                    key={name}
                    onClick={() => setSelectedProfile(name)}
                    className={`cursor-pointer border-b border-[#161b22] hover:bg-[#ffffff04] ${
                      selectedProfile === name ? "bg-[#10b9810a]" : ""
                    }`}
                  >
                    <td className="px-4 py-2 trion-mono text-[11px] font-bold text-[#34d399]">{name}</td>
                    <td className="px-4 py-2 trion-mono text-[11px] text-[#d7dde6]">{p.phi.toFixed(2)}</td>
                    <td className="px-4 py-2 trion-mono text-[11px] text-[#d7dde6]">{p.m.toFixed(2)}</td>
                    <td className="px-4 py-2 trion-mono text-[11px] text-[#d7dde6]">{p.sigma.toFixed(2)}</td>
                    <td className="px-4 py-2 trion-mono text-[11px] text-[#d7dde6]">{p.k.toFixed(2)}</td>
                    <td className="px-4 py-2 trion-mono text-[11px] text-[#d7dde6]">{p.anima.toFixed(2)}</td>
                    <td className="px-4 py-2 trion-mono text-[11px]" style={{ color: Math.abs(sum - 1) < 0.001 ? "#34d399" : "#f59e0b" }}>
                      {sum.toFixed(2)}
                    </td>
                    <td className="px-4 py-2 text-[11px] text-[#7d8896]">{p.description ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Asset-type profiles */}
      <section aria-label="Asset type profiles" className="trion-panel">
        <div className="border-b border-[#1c232d] px-5 py-3">
          <span className="trion-label">Asset-Type Profiles</span>
        </div>
        <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3">
          {assetEntries.map(([name, p]) => (
            <div key={name} className="rounded-md border border-[#1c232d] bg-[#0a0d12] p-3">
              <div className="trion-mono text-[11px] font-bold text-[#34d399]">{name}</div>
              <p className="mt-1 text-[10px] text-[#7d8896]">{p.description ?? ""}</p>
              <div className="mt-2 space-y-1.5">
                <MeterBar label="α" value={p.alpha} color="#10b981" />
                <MeterBar label="β" value={p.beta} color="#22d3ee" />
                <MeterBar label="γ" value={p.gamma} color="#a78bfa" />
                <MeterBar label="δ" value={p.delta} color="#f59e0b" />
                <MeterBar label="ε" value={p.epsilon} color="#f43f5e" />
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
