'use client';

import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { AlertsData, AlertEntry } from '@/lib/types';
import Topbar from '@/components/Topbar';
import { BellRing, AlertTriangle, CheckCircle, Clock, RefreshCw } from 'lucide-react';
import { formatDistanceToNow, parseISO } from 'date-fns';
import clsx from 'clsx';

const EVENT_META: Record<string, { label: string; color: string; bg: string }> = {
  'signal.collapse':    { label: 'Coherence Collapse', color: 'text-red-400',    bg: 'border-red-500/20 bg-red-500/5' },
  'signal.plane_shift': { label: 'Plane Shift',        color: 'text-amber-400',  bg: 'border-amber-500/20 bg-amber-500/5' },
  'signal.recovery':    { label: 'Recovery',           color: 'text-green-400',  bg: 'border-green-500/20 bg-green-500/5' },
  'attack.detected':    { label: 'Attack Detected',    color: 'text-red-500',    bg: 'border-red-500/30 bg-red-500/10' },
  'protocol.threat':    { label: 'Protocol Threat',    color: 'text-orange-400', bg: 'border-orange-500/20 bg-orange-500/5' },
};

function eventStyle(event: string) {
  return EVENT_META[event] ?? { label: event, color: 'text-cyan', bg: 'border-cyan/20 bg-cyan/5' };
}

function AlertCard({ alert }: { alert: AlertEntry }) {
  const meta = eventStyle(alert.event);
  let timeAgo = '';
  try { timeAgo = formatDistanceToNow(parseISO(alert.fired_at), { addSuffix: true }); } catch { /* noop */ }

  return (
    <div className={clsx('card p-4 border', meta.bg)}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2 min-w-0">
          <AlertTriangle size={13} className={clsx('flex-shrink-0 mt-0.5', meta.color)} />
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={clsx('text-[11px] font-bold', meta.color)}>{meta.label}</span>
              {alert.archetype && (
                <span className="text-[9px] px-1.5 py-0.5 rounded border border-cyan/20 bg-cyan/5 text-cyan">{alert.archetype}</span>
              )}
            </div>
            <p className="text-[11px] text-t2 mt-1 leading-relaxed">{alert.message}</p>
            <div className="flex items-center gap-3 mt-2 flex-wrap text-[10px] text-t3">
              <span className="mono">{alert.entity_label ?? alert.entity_id}</span>
              {alert.coherence !== undefined && (
                <span>C(t)={alert.coherence.toFixed(4)}</span>
              )}
              {alert.threshold !== undefined && (
                <span>Θ={alert.threshold.toFixed(4)}</span>
              )}
              {alert.limiting_plane && (
                <span className="text-amber-400">Limiting: {alert.limiting_plane}</span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1 text-[10px] text-t3 flex-shrink-0">
          <Clock size={10} />
          {timeAgo}
        </div>
      </div>
    </div>
  );
}

export default function AlertsPage() {
  const { data, isLoading, error, mutate } = useSWR<AlertsData>(
    endpoints.alerts, fetchJSON, { refreshInterval: 10000 }
  );

  const alerts = data?.alerts ?? [];
  const collapseCount = alerts.filter(a => a.event === 'signal.collapse').length;
  const planeShiftCount = alerts.filter(a => a.event === 'signal.plane_shift').length;
  const attackCount = alerts.filter(a => a.event?.includes('attack')).length;

  // Group by entity
  const byEntity: Record<string, AlertEntry[]> = {};
  for (const a of alerts) {
    const key = a.entity_label ?? a.entity_id;
    if (!byEntity[key]) byEntity[key] = [];
    byEntity[key].push(a);
  }

  return (
    <>
      <Topbar title="Attack Alerts" />
      <div className="flex-1 overflow-y-auto scrollable p-5 space-y-4">

        {/* Summary strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 flex-shrink-0">
          {[
            { label: 'Total Alerts',     value: alerts.length,    color: 'text-cyan'      },
            { label: 'Collapses',        value: collapseCount,    color: 'text-red-400'   },
            { label: 'Plane Shifts',     value: planeShiftCount,  color: 'text-amber-400' },
            { label: 'Attack Events',    value: attackCount,      color: 'text-orange-400'},
          ].map(({ label, value, color }) => (
            <div key={label} className="card p-3 text-center">
              <p className={clsx('text-2xl font-bold mono', color)}>{isLoading ? '—' : value}</p>
              <p className="text-[10px] text-t3 uppercase tracking-wide mt-0.5">{label}</p>
            </div>
          ))}
        </div>

        {/* Header + refresh */}
        <div className="flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-2">
            <BellRing size={13} className="text-cyan" />
            <span className="text-[12px] font-semibold text-t1">Live Alert Feed</span>
            <span className="text-[10px] text-t3">— refreshes every 10s</span>
          </div>
          <button
            onClick={() => mutate()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] text-t2 border border-border rounded hover:border-cyan/40 hover:text-cyan transition-colors"
          >
            <RefreshCw size={10} />
            Refresh
          </button>
        </div>

        {error && (
          <div className="card p-4 border-red-500/20 bg-red-500/5">
            <p className="text-red-400 text-[12px]">
              Cannot reach alert webhook service: {error.message}
            </p>
          </div>
        )}

        {isLoading && !error && (
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => <div key={i} className="card h-24 animate-pulse bg-border" />)}
          </div>
        )}

        {!isLoading && alerts.length === 0 && (
          <div className="card p-8 text-center">
            <CheckCircle size={32} className="text-green-400 mx-auto mb-3" />
            <p className="text-t1 text-[13px] mb-1">No active alerts</p>
            <p className="text-t3 text-[11px]">All monitored entities are operating within coherence bounds.</p>
          </div>
        )}

        {/* Alerts by entity */}
        {Object.entries(byEntity).map(([entity, entityAlerts]) => (
          <div key={entity} className="space-y-2">
            <p className="text-[10px] text-t3 font-semibold uppercase tracking-wide mono">
              {entity.length > 42 ? entity.slice(0, 20) + '…' + entity.slice(-6) : entity}
              <span className="ml-2 text-t3/60">({entityAlerts.length})</span>
            </p>
            {entityAlerts.map((a, i) => (
              <AlertCard key={`${a.event}-${a.fired_at}-${i}`} alert={a} />
            ))}
          </div>
        ))}
      </div>
    </>
  );
}
