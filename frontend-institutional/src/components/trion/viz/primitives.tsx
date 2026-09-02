"use client";

import { useEffect, useRef, useState } from "react";

/** Eased live counter — animates numeric metric changes like a terminal. */
export function StatCounter({
  value,
  decimals = 0,
  prefix = "",
  suffix = "",
  className = "",
}: {
  value: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
}) {
  const [display, setDisplay] = useState(0);
  const from = useRef(0);

  useEffect(() => {
    const start = performance.now();
    const startVal = from.current;
    const delta = value - startVal;
    let raf = 0;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / 700);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(startVal + delta * eased);
      if (t < 1) raf = requestAnimationFrame(step);
      else from.current = value;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]);

  return (
    <span className={className}>
      {prefix}
      {display.toLocaleString(undefined, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}
      {suffix}
    </span>
  );
}

/** Five-plane coherence radar (Φ M Σ K A) rendered as pure SVG. */
export function CoherenceRadar({
  values,
  threshold,
  size = 260,
}: {
  values: { phi: number; m: number; sigma: number; k: number; a: number };
  threshold: number;
  size?: number;
}) {
  const planes = [
    { key: "phi", label: "Φ", name: "PHYSICAL" },
    { key: "m", label: "M", name: "MENTAL" },
    { key: "sigma", label: "Σ", name: "SIGNAL" },
    { key: "k", label: "K", name: "CONSCIOUS" },
    { key: "a", label: "A", name: "ANIMA" },
  ] as const;

  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 34;

  const point = (i: number, v: number) => {
    const angle = (Math.PI * 2 * i) / planes.length - Math.PI / 2;
    const rr = r * Math.max(0, Math.min(1, v));
    return [cx + rr * Math.cos(angle), cy + rr * Math.sin(angle)];
  };

  const poly = (fn: (i: number) => number) =>
    planes.map((_, i) => point(i, fn(i)).join(",")).join(" ");

  const valuePoly = poly((i) => values[planes[i].key]);
  const thresholdPoly = poly(() => threshold);

  return (
    <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} role="img" aria-label="Five-plane coherence radar">
      {[0.25, 0.5, 0.75, 1].map((ring) => (
        <polygon
          key={ring}
          points={poly(() => ring)}
          fill="none"
          stroke="#1c232d"
          strokeWidth={1}
        />
      ))}
      {planes.map((_, i) => {
        const [x, y] = point(i, 1);
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="#1c232d" strokeWidth={1} />;
      })}
      <polygon points={thresholdPoly} fill="rgba(245,158,11,0.04)" stroke="#f59e0b" strokeWidth={1} strokeDasharray="4 3" />
      <polygon points={valuePoly} fill="rgba(16,185,129,0.14)" stroke="#10b981" strokeWidth={1.5} />
      {planes.map((p, i) => {
        const [x, y] = point(i, values[p.key]);
        return <circle key={p.key} cx={x} cy={y} r={3} fill="#34d399" />;
      })}
      {planes.map((p, i) => {
        const [x, y] = point(i, 1.28);
        return (
          <text
            key={p.key}
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize={11}
            fontWeight={700}
            fill="#7d8896"
            className="trion-mono"
          >
            {p.label}
          </text>
        );
      })}
    </svg>
  );
}

/** Circular gauge for scores like C(t), BTCP score, MF. */
export function GaugeRing({
  value,
  max = 1,
  label,
  sublabel,
  color = "#10b981",
  size = 120,
  decimals = 3,
}: {
  value: number;
  max?: number;
  label: string;
  sublabel?: string;
  color?: string;
  size?: number;
  decimals?: number;
}) {
  const ratio = Math.max(0, Math.min(1, value / max));
  const r = size / 2 - 8;
  const circ = 2 * Math.PI * r;
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label} gauge`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1c232d" strokeWidth={6} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={6}
          strokeLinecap="round"
          strokeDasharray={`${circ * ratio} ${circ}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: "stroke-dasharray 0.8s cubic-bezier(0.4, 0, 0.2, 1)" }}
        />
        <text
          x={size / 2}
          y={size / 2 - 2}
          textAnchor="middle"
          fontSize={size * 0.17}
          fontWeight={700}
          fill="#d7dde6"
          className="trion-mono"
        >
          {value.toFixed(decimals)}
        </text>
        <text x={size / 2} y={size / 2 + size * 0.14} textAnchor="middle" fontSize={9} fill="#7d8896" letterSpacing="0.1em">
          {label}
        </text>
      </svg>
      {sublabel ? <span className="text-[10px] text-[#7d8896]">{sublabel}</span> : null}
    </div>
  );
}

/** Compact sparkline from a numeric series. */
export function Sparkline({
  data,
  color = "#10b981",
  width = 140,
  height = 34,
  fill = true,
}: {
  data: number[];
  color?: string;
  width?: number;
  height?: number;
  fill?: boolean;
}) {
  if (data.length < 2) return <div style={{ width, height }} />;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * (width - 2) + 1;
    const y = height - 2 - ((v - min) / span) * (height - 4);
    return `${x},${y}`;
  });
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden>
      {fill && (
        <polygon points={`1,${height - 1} ${pts.join(" ")} ${width - 1},${height - 1}`} fill={color} opacity={0.12} />
      )}
      <polyline points={pts.join(" ")} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  );
}

/** Horizontal meter bar with threshold marker. */
export function MeterBar({
  value,
  threshold,
  color = "#10b981",
  label,
}: {
  value: number;
  threshold?: number;
  color?: string;
  label?: string;
}) {
  const pct = Math.max(0, Math.min(100, value * 100));
  return (
    <div className="w-full">
      {label && (
        <div className="flex justify-between items-baseline mb-1">
          <span className="trion-label">{label}</span>
          <span className="trion-mono text-[11px] text-[#d7dde6]">{value.toFixed(3)}</span>
        </div>
      )}
      <div className="relative h-1.5 rounded-full bg-[#1c232d] overflow-visible">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: color }}
        />
        {threshold !== undefined && (
          <div
            className="absolute -top-0.5 w-0.5 h-2.5 bg-[#f59e0b]"
            style={{ left: `${Math.min(100, threshold * 100)}%` }}
            title={`Θ = ${threshold.toFixed(3)}`}
          />
        )}
      </div>
    </div>
  );
}
