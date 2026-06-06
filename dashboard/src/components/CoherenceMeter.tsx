import clsx from 'clsx';

interface Props {
  score: number;
  threshold: number;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
}

function getColor(score: number, threshold: number) {
  if (score >= threshold) return '#22c55e';
  if (score >= threshold * 0.8) return '#f59e0b';
  return '#ef4444';
}

export default function CoherenceMeter({ score, threshold, size = 'md', showLabel = true }: Props) {
  const pct = Math.min(100, (score / 1) * 100);
  const color = getColor(score, threshold);
  const threshPct = Math.min(100, threshold * 100);

  const heights = { sm: 'h-1', md: 'h-1.5', lg: 'h-2' };

  return (
    <div className="flex flex-col gap-1 w-full">
      {showLabel && (
        <div className="flex justify-between items-center">
          <span style={{ color }} className="mono text-[11px] font-medium">
            {score.toFixed(4)}
          </span>
          <span className="text-[10px] text-t3">Θ {threshold.toFixed(3)}</span>
        </div>
      )}
      <div className={clsx('relative w-full bg-border rounded-full overflow-hidden', heights[size])}>
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: color }}
        />
        {/* threshold marker */}
        <div
          className="absolute top-0 bottom-0 w-px bg-white/30"
          style={{ left: `${threshPct}%` }}
        />
      </div>
    </div>
  );
}
