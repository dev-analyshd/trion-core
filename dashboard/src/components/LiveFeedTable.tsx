'use client';

import { useLiveFeed } from '@/hooks/useLiveFeed';
import type { FeedEntry } from '@/lib/types';
import CoherenceMeter from './CoherenceMeter';
import clsx from 'clsx';
import { formatDistanceToNow } from 'date-fns';
import { Activity, Wifi, WifiOff, RefreshCw, Building2, TrendingDown, TrendingUp, Minus } from 'lucide-react';

const ARCH_COLORS: Record<string, string> = {
  Hero: 'text-cyan border-cyan/30 bg-cyan/5',
  Sage: 'text-violet-400 border-violet-400/30 bg-violet-400/5',
  Outlaw: 'text-red-400 border-red-400/30 bg-red-400/5',
  Jester: 'text-amber-400 border-amber-400/30 bg-amber-400/5',
  Innocent: 'text-green-400 border-green-400/30 bg-green-400/5',
  Lover: 'text-pink-400 border-pink-400/30 bg-pink-400/5',
  Regular: 'text-t2 border-border bg-card2',
};

const GRADE_COLORS: Record<string, string> = {
  A: 'text-green-400 border-green-400/30 bg-green-400/5',
  B: 'text-cyan border-cyan/30 bg-cyan/5',
  C: 'text-amber-400 border-amber-400/30 bg-amber-400/5',
  D: 'text-orange-400 border-orange-400/30 bg-orange-400/5',
  F: 'text-red-400 border-red-400/30 bg-red-400/5',
};

const THREAT_COLORS: Record<string, string> = {
  LOW: 'text-green-400',
  MEDIUM: 'text-amber-400',
  HIGH: 'text-orange-400',
  CRITICAL: 'text-red-400',
};

function ArchBadge({ arch }: { arch: string }) {
  return (
    <span className={clsx('px-1.5 py-0.5 rounded border text-[9px] font-semibold tracking-wide uppercase', ARCH_COLORS[arch] ?? ARCH_COLORS.Regular)}>
      {arch}
    </span>
  );
}

function GradeBadge({ grade }: { grade: string }) {
  return (
    <span className={clsx('px-1.5 py-0.5 rounded border text-[9px] font-bold tracking-widest uppercase', GRADE_COLORS[grade] ?? GRADE_COLORS.F)}>
      {grade}
    </span>
  );
}

function SignalBadge({ coherent }: { coherent: boolean }) {
  if (coherent) {
    return <span className="px-1.5 py-0.5 rounded border border-green-500/30 bg-green-500/5 text-green-400 text-[9px] font-semibold uppercase">EMIT</span>;
  }
  return <span className="px-1.5 py-0.5 rounded border border-t3/30 bg-card2 text-t3 text-[9px] font-semibold uppercase">SILENCE</span>;
}

function ProtocolSignalBadge({ grade, threatLevel }: { grade?: string; threatLevel?: string }) {
  if (threatLevel === 'CRITICAL' || threatLevel === 'HIGH') {
    return (
      <span className={clsx(
        'px-1.5 py-0.5 rounded border text-[9px] font-semibold uppercase',
        threatLevel === 'CRITICAL' ? 'text-red-400 border-red-400/30 bg-red-400/5' : 'text-orange-400 border-orange-400/30 bg-orange-400/5'
      )}>
        {threatLevel}
      </span>
    );
  }
  return <span className="px-1.5 py-0.5 rounded border border-cyan/20 bg-cyan/5 text-cyan text-[9px] font-semibold uppercase">H(t)</span>;
}

function TrendIcon({ prev, current }: { prev?: number; current: number }) {
  if (prev == null) return <Minus size={10} className="text-t3" />;
  if (current > prev + 0.02) return <TrendingUp size={10} className="text-green-400" />;
  if (current < prev - 0.02) return <TrendingDown size={10} className="text-red-400" />;
  return <Minus size={10} className="text-t3" />;
}

function ConnIndicator({ state }: { state: 'connecting' | 'live' | 'error' | 'polling' }) {
  if (state === 'live') {
    return (
      <div className="flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-blink" />
        <Wifi size={10} className="text-green-400" />
        <span className="text-[10px] text-green-400 font-medium">LIVE</span>
      </div>
    );
  }
  if (state === 'connecting') {
    return (
      <div className="flex items-center gap-1.5">
        <RefreshCw size={10} className="text-amber-400 animate-spin" />
        <span className="text-[10px] text-amber-400 font-medium">CONNECTING</span>
      </div>
    );
  }
  if (state === 'error') {
    return (
      <div className="flex items-center gap-1.5">
        <WifiOff size={10} className="text-red-400" />
        <span className="text-[10px] text-red-400 font-medium">RECONNECTING</span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-1.5">
      <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-blink" />
      <span className="text-[10px] text-amber-400 font-medium">POLLING</span>
    </div>
  );
}

function ProtocolRow({ e, isNew, compact }: { e: FeedEntry; isNew: boolean; compact: boolean }) {
  const isAttack = e.threat_level === 'CRITICAL' || e.threat_level === 'HIGH';
  return (
    <tr className={clsx(
      'border-b border-border/50 hover:bg-card2 transition-colors',
      isAttack ? 'bg-red-950/20' : 'bg-blue-950/10',
      isNew && 'animate-flash-in'
    )}>
      <td className="px-4 py-2.5">
        <div className="flex items-center gap-1.5">
          <Building2 size={11} className={clsx('flex-shrink-0', isAttack ? 'text-red-400' : 'text-cyan')} />
          <div className="flex flex-col min-w-0">
            <span className="text-[11px] text-t1 font-medium truncate">
              {e.protocol_name ?? e.short_id}
            </span>
            {e.change_reason && (
              <span className="text-[9px] text-t3 truncate">{e.change_reason.replace(/_/g, ' ')}</span>
            )}
          </div>
        </div>
      </td>
      <td className="px-3 py-2.5">
        {e.grade ? <GradeBadge grade={e.grade} /> : <ArchBadge arch={e.archetype} />}
      </td>
      {!compact && (
        <td className="px-3 py-2.5">
          <span className={clsx('text-[11px]', THREAT_COLORS[e.threat_level ?? ''] ?? 'text-t2')}>
            {e.threat_level ?? e.limiting_plane}
          </span>
        </td>
      )}
      <td className="px-3 py-2.5 min-w-[120px]">
        <div className="flex items-center gap-1.5">
          <CoherenceMeter score={e.coherence_score} threshold={e.threshold} size="sm" />
          <TrendIcon prev={e.prev_score} current={e.coherence_score} />
        </div>
      </td>
      <td className="px-3 py-2.5 hidden md:table-cell">
        <ProtocolSignalBadge grade={e.grade} threatLevel={e.threat_level} />
      </td>
      {!compact && (
        <td className="px-4 py-2.5 text-right text-[10px] text-t3 hidden lg:table-cell">
          {formatDistanceToNow(new Date(e.timestamp * 1000), { addSuffix: true })}
        </td>
      )}
    </tr>
  );
}

function WalletRow({ e, isNew, compact }: { e: FeedEntry; isNew: boolean; compact: boolean }) {
  return (
    <tr className={clsx(
      'border-b border-border/50 hover:bg-card2 transition-colors',
      isNew && 'animate-flash-in'
    )}>
      <td className="px-4 py-2.5">
        <span className="mono text-[11px] text-t1 truncate block max-w-[140px]" title={e.entity_id}>
          {e.short_id || e.entity_id}
        </span>
      </td>
      <td className="px-3 py-2.5">
        <ArchBadge arch={e.archetype} />
      </td>
      {!compact && (
        <td className="px-3 py-2.5 text-[11px] text-t2">{e.limiting_plane}</td>
      )}
      <td className="px-3 py-2.5 min-w-[120px]">
        <CoherenceMeter score={e.coherence_score} threshold={e.threshold} size="sm" />
      </td>
      <td className="px-3 py-2.5 hidden md:table-cell">
        <SignalBadge coherent={e.coherent} />
      </td>
      {!compact && (
        <td className="px-4 py-2.5 text-right text-[10px] text-t3 hidden lg:table-cell">
          {formatDistanceToNow(new Date(e.timestamp * 1000), { addSuffix: true })}
        </td>
      )}
    </tr>
  );
}

interface Props {
  limit?: number;
  compact?: boolean;
}

export default function LiveFeedTable({ limit = 50, compact = false }: Props) {
  const { entries, connState, newCount } = useLiveFeed(limit);
  const isLoading = entries.length === 0;

  const protocolCount = entries.filter(e => e.kind === 'PROTOCOL_HEALTH').length;

  return (
    <div className="card flex flex-col overflow-hidden h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <Activity size={13} className="text-cyan" />
          <span className="text-[12px] font-semibold text-t1">Live Signal Feed</span>
          {newCount > 0 && (
            <span className="px-1.5 py-0.5 rounded bg-cyan/10 border border-cyan/20 text-cyan text-[9px] font-semibold mono">
              +{newCount}
            </span>
          )}
          {protocolCount > 0 && (
            <span className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-blue-500/10 border border-blue-500/20 text-blue-400 text-[9px] font-semibold">
              <Building2 size={9} />
              {protocolCount} protocol
            </span>
          )}
        </div>
        <ConnIndicator state={connState} />
      </div>

      <div className="overflow-y-auto scrollable flex-1">
        {isLoading ? (
          <div className="p-4 space-y-2">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-10 bg-border rounded animate-pulse" />
            ))}
          </div>
        ) : (
          <table className="w-full">
            <thead className="sticky top-0 bg-card z-10">
              <tr className="border-b border-border">
                <th className="text-left px-4 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">Entity</th>
                <th className="text-left px-3 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">Type</th>
                {!compact && <th className="text-left px-3 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">Plane / Threat</th>}
                <th className="text-left px-3 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">C(t) / H(t)</th>
                <th className="text-left px-3 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase hidden md:table-cell">Signal</th>
                {!compact && <th className="text-right px-4 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase hidden lg:table-cell">Age</th>}
              </tr>
            </thead>
            <tbody>
              {entries.map((e: FeedEntry, i) => (
                e.kind === 'PROTOCOL_HEALTH'
                  ? <ProtocolRow key={`${e.entity_id}-${e.timestamp}-${i}`} e={e} isNew={i === 0 && connState === 'live'} compact={compact} />
                  : <WalletRow key={`${e.entity_id}-${e.timestamp}-${i}`} e={e} isNew={i === 0 && connState === 'live'} compact={compact} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
