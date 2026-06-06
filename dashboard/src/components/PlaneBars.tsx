import clsx from 'clsx';

interface PlaneBreakdown {
  physical: number;
  mental: number;
  spiritual: number;
  conscious: number;
  anima: number;
}

interface Props {
  planes: PlaneBreakdown;
  threshold?: number;
  compact?: boolean;
}

const PLANE_META = [
  { key: 'physical' as const, label: 'Φ Physical', weight: 'α=0.25', color: '#00c2ff' },
  { key: 'mental' as const, label: 'M Mental', weight: 'β=0.30', color: '#9f67f5' },
  { key: 'spiritual' as const, label: 'Σ Spiritual', weight: 'γ=0.25', color: '#22c55e' },
  { key: 'conscious' as const, label: 'K Conscious', weight: 'δ=0.10', color: '#f59e0b' },
  { key: 'anima' as const, label: 'A ANIMA', weight: 'ε=0.10', color: '#f97316' },
];

export default function PlaneBars({ planes, threshold = 0.55, compact = false }: Props) {
  return (
    <div className={clsx('flex flex-col', compact ? 'gap-1.5' : 'gap-2.5')}>
      {PLANE_META.map(({ key, label, weight, color }) => {
        const val = planes[key] ?? 0;
        const pct = Math.min(100, val * 100);
        const ok = val >= threshold;
        return (
          <div key={key} className="flex flex-col gap-0.5">
            {!compact && (
              <div className="flex justify-between items-center">
                <span className="text-[11px] text-t2 font-medium">{label}</span>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-t3 mono">{weight}</span>
                  <span
                    className="mono text-[11px] font-semibold"
                    style={{ color: ok ? '#22c55e' : '#ef4444' }}
                  >
                    {val.toFixed(4)}
                  </span>
                </div>
              </div>
            )}
            <div className="relative h-1.5 bg-border rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${pct}%`, background: color }}
              />
            </div>
            {compact && (
              <div className="flex justify-between">
                <span className="text-[9px] text-t3">{label}</span>
                <span className="text-[9px] mono" style={{ color: ok ? '#22c55e' : '#ef4444' }}>
                  {val.toFixed(3)}
                </span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
