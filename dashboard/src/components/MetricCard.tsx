import clsx from 'clsx';
import type { ReactNode } from 'react';

interface Props {
  label: string;
  value: string | number | ReactNode;
  sub?: string;
  accent?: 'cyan' | 'green' | 'amber' | 'red' | 'violet';
  className?: string;
  loading?: boolean;
}

const ACCENT = {
  cyan: 'text-cyan',
  green: 'text-green-400',
  amber: 'text-amber-400',
  red: 'text-red-400',
  violet: 'text-violet-400',
};

export default function MetricCard({ label, value, sub, accent = 'cyan', className, loading }: Props) {
  return (
    <div className={clsx('card p-4 flex flex-col gap-1', className)}>
      <p className="text-[10px] font-semibold tracking-[0.1em] uppercase text-t3">{label}</p>
      {loading ? (
        <div className="h-7 w-24 bg-border2 rounded animate-pulse mt-1" />
      ) : (
        <p className={clsx('text-2xl font-bold tracking-tight', ACCENT[accent])}>
          {value}
        </p>
      )}
      {sub && <p className="text-[11px] text-t3 mt-0.5">{sub}</p>}
    </div>
  );
}
