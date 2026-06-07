'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import { Building2, Search, Shield, AlertTriangle, Users, Activity, BarChart3, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';
import clsx from 'clsx';
import { formatDistanceToNow } from 'date-fns';

const PRESET_PROTOCOLS = [
  { label: 'Uniswap V3', address: 'uniswap' },
  { label: 'Aave V3', address: 'aave' },
  { label: 'Compound III', address: 'compound' },
  { label: '0G ExecutionGate', address: '0xa85b49c73b5710d9ddb1cb5a94c52d0f33c4199b' },
];

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

const RISK_COLORS: Record<string, string> = {
  LOW: 'text-green-400 bg-green-400/10 border-green-400/20',
  MEDIUM: 'text-amber-400 bg-amber-400/10 border-amber-400/20',
  HIGH: 'text-red-400 bg-red-400/10 border-red-400/20',
  UNKNOWN: 'text-t3 bg-card2 border-border',
};

const ROLE_COLORS: Record<string, string> = {
  LIQUIDITY_PROVIDER: '#22c55e',
  BORROWER: '#818cf8',
  LIQUIDATOR: '#f97316',
  MEV_BOT: '#ef4444',
  ARBITRAGEUR: '#00c2ff',
  GOVERNANCE_ACTOR: '#a78bfa',
  TRADER: '#94a3b8',
  UNKNOWN: '#334155',
};

function ScoreBar({ label, value, weight }: { label: string; value: number; weight: number }) {
  const pct = Math.round(value * 100);
  const color = value >= 0.7 ? '#22c55e' : value >= 0.5 ? '#f59e0b' : '#ef4444';
  return (
    <div className="flex items-center gap-3">
      <span className="text-[11px] text-t2 w-40 flex-shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-border rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="text-[11px] mono text-t1 w-10 text-right">{value.toFixed(3)}</span>
      <span className="text-[10px] text-t3 w-10 text-right">{(weight * 100).toFixed(0)}%</span>
    </div>
  );
}

function RoleDonut({ distribution }: { distribution: Record<string, number> }) {
  const entries = Object.entries(distribution).filter(([, v]) => v > 0).sort(([, a], [, b]) => b - a);
  return (
    <div className="space-y-2">
      {entries.map(([role, share]) => (
        <div key={role} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: ROLE_COLORS[role] ?? '#94a3b8' }} />
          <span className="text-[11px] text-t1 flex-1">{role.replace(/_/g, ' ')}</span>
          <div className="w-24 h-1.5 bg-border rounded-full overflow-hidden">
            <div className="h-full rounded-full" style={{ width: `${Math.round(share * 100)}%`, backgroundColor: ROLE_COLORS[role] ?? '#94a3b8' }} />
          </div>
          <span className="text-[11px] mono text-t2 w-10 text-right">{(share * 100).toFixed(1)}%</span>
        </div>
      ))}
    </div>
  );
}

function AnomalyEvent({ event }: { event: { event: string; current_ratio: number; baseline_ratio: number; spike_factor: number } }) {
  return (
    <div className="flex items-center justify-between px-3 py-2 bg-red-500/5 border border-red-500/20 rounded">
      <div className="flex items-center gap-2">
        <AlertTriangle size={11} className="text-red-400 flex-shrink-0" />
        <span className="text-[11px] text-red-400 font-semibold">{event.event}</span>
      </div>
      <div className="flex items-center gap-4 text-[10px] mono">
        <span className="text-t3">baseline: {(event.baseline_ratio * 100).toFixed(1)}%</span>
        <span className="text-red-400">now: {(event.current_ratio * 100).toFixed(1)}%</span>
        <span className="text-amber-400 font-semibold">{event.spike_factor}× spike</span>
      </div>
    </div>
  );
}

function UserRow({ user, expanded, onToggle }: { user: Record<string, unknown>; expanded: boolean; onToggle: () => void }) {
  return (
    <>
      <tr
        className="border-b border-border/50 hover:bg-card2 transition-colors cursor-pointer"
        onClick={onToggle}
      >
        <td className="px-4 py-2.5">
          <span className="mono text-[11px] text-t1 truncate block max-w-[150px]" title={user.caller as string}>
            {(user.caller as string)?.slice(0, 18) ?? '—'}…
          </span>
        </td>
        <td className="px-3 py-2.5">
          <span className="text-[10px] font-semibold" style={{ color: ROLE_COLORS[(user.role as string)] ?? '#94a3b8' }}>
            {(user.role as string)?.replace(/_/g, ' ')}
          </span>
        </td>
        <td className="px-3 py-2.5">
          <span className={clsx('px-1.5 py-0.5 rounded border text-[9px] font-semibold', RISK_COLORS[(user.risk_level as string)] ?? RISK_COLORS.UNKNOWN)}>
            {user.risk_level as string}
          </span>
        </td>
        <td className="px-3 py-2.5">
          <div className="flex items-center gap-1.5">
            <div className="w-16 h-1 bg-border rounded-full overflow-hidden">
              <div className="h-full bg-cyan rounded-full" style={{ width: `${Math.round((user.confidence as number) * 100)}%` }} />
            </div>
            <span className="text-[10px] mono text-t2">{((user.confidence as number) * 100).toFixed(0)}%</span>
          </div>
        </td>
        <td className="px-3 py-2.5 text-right">
          <span className="text-[11px] mono text-t2">{user.tx_count as number}</span>
        </td>
        <td className="px-3 py-2.5 text-right">
          {expanded ? <ChevronUp size={11} className="text-t3 ml-auto" /> : <ChevronDown size={11} className="text-t3 ml-auto" />}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-card2 border-b border-border">
          <td colSpan={6} className="px-4 py-3">
            <div className="grid grid-cols-2 gap-4 text-[11px]">
              <div>
                <p className="text-t3 text-[10px] mb-1 uppercase tracking-wide">Event breakdown</p>
                <div className="space-y-1">
                  {Object.entries(user.event_type_counts as Record<string, number>).sort(([, a], [, b]) => b - a).slice(0, 6).map(([evt, cnt]) => (
                    <div key={evt} className="flex justify-between">
                      <span className="text-t2">{evt}</span>
                      <span className="mono text-t1">{cnt}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-t3 text-[10px] mb-1 uppercase tracking-wide">Magnitude</p>
                <div className="space-y-1">
                  <div className="flex justify-between"><span className="text-t2">Mean</span><span className="mono text-t1">{((user.magnitude_mean as number) ?? 0).toFixed(4)}</span></div>
                  <div className="flex justify-between"><span className="text-t2">P95</span><span className="mono text-t1">{((user.magnitude_p95 as number) ?? 0).toFixed(4)}</span></div>
                  <div className="flex justify-between"><span className="text-t2">Chains</span><span className="mono text-t1">{(user.chains as string[])?.join(', ') || '—'}</span></div>
                  <div className="flex justify-between"><span className="text-t2">Last seen</span><span className="mono text-t1">{user.last_seen ? formatDistanceToNow(new Date((user.last_seen as number) * 1000), { addSuffix: true }) : '—'}</span></div>
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function ProtocolPage() {
  const [input, setInput] = useState('');
  const [address, setAddress] = useState('');
  const [expandedUser, setExpandedUser] = useState<string | null>(null);

  const active = address || null;

  const { data: health, isLoading: loadingHealth } = useSWR(
    active ? endpoints.protocolHealth(active) : null,
    fetchJSON<Record<string, unknown>>,
    { refreshInterval: 30000 }
  );
  const { data: users } = useSWR(
    active ? endpoints.protocolUsers(active) + '?limit=30' : null,
    fetchJSON<Record<string, unknown>>,
    { refreshInterval: 30000 }
  );
  const { data: attackSurface } = useSWR(
    active ? endpoints.protocolAttackSurface(active) : null,
    fetchJSON<Record<string, unknown>>,
    { refreshInterval: 30000 }
  );
  const { data: distribution } = useSWR(
    active ? endpoints.protocolDistribution(active) : null,
    fetchJSON<Record<string, unknown>>,
    { refreshInterval: 30000 }
  );

  const handleSearch = () => {
    const val = input.trim();
    if (val) setAddress(val);
  };

  const components = (health?.components as Record<string, number>) ?? {};
  const weights = (components as Record<string, unknown>)?.weights as Record<string, number> ?? {};
  const roleDistribution = (health?.role_distribution as Record<string, number>) ?? {};
  const recommendations = (health?.recommendations as string[]) ?? [];
  const anomalous = (attackSurface?.anomalous_events as Record<string, unknown>[]) ?? [];
  const highRiskCallers = (attackSurface?.high_risk_callers as Record<string, unknown>[]) ?? [];
  const userList = (users?.users as Record<string, unknown>[]) ?? [];
  const curDist = (distribution?.current_distribution as Record<string, number>) ?? {};
  const baseDist = (distribution?.baseline_distribution as Record<string, number>) ?? {};

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Building2 size={16} className="text-cyan" />
          <h1 className="text-[15px] font-semibold text-t1">Protocol Intel</h1>
          <span className="text-[11px] text-t3 ml-2">Sub-entity segmentation · Role classification · Distribution coherence</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollable p-6 space-y-5">

        {/* Search */}
        <div className="card p-4">
          <p className="text-[11px] text-t3 mb-3 uppercase tracking-wide font-semibold">Analyse Protocol Contract</p>
          <div className="flex gap-2 mb-3">
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              placeholder="0x... contract address or name (e.g. uniswap, aave)"
              className="flex-1 bg-bg border border-border rounded px-3 py-2 text-[12px] text-t1 placeholder-t3 focus:outline-none focus:border-cyan/50"
            />
            <button
              onClick={handleSearch}
              className="px-4 py-2 bg-cyan/10 border border-cyan/20 text-cyan rounded text-[12px] font-medium hover:bg-cyan/20 transition-colors flex items-center gap-1.5"
            >
              <Search size={12} /> Analyse
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {PRESET_PROTOCOLS.map(p => (
              <button
                key={p.address}
                onClick={() => { setInput(p.address); setAddress(p.address); }}
                className={clsx(
                  'px-2.5 py-1 rounded border text-[10px] font-medium transition-colors',
                  address === p.address
                    ? 'bg-cyan/10 border-cyan/30 text-cyan'
                    : 'bg-card2 border-border text-t2 hover:border-cyan/20 hover:text-t1'
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {!active && (
          <div className="card p-8 text-center">
            <Building2 size={32} className="text-t3 mx-auto mb-3" />
            <p className="text-t2 text-[13px] mb-1">Enter a protocol contract address above</p>
            <p className="text-t3 text-[11px]">
              TRION decomposes protocol activity into (contract, caller) pairs — each with
              their own DeFi role, risk level, and behavioural coherence score.
            </p>
          </div>
        )}

        {active && loadingHealth && (
          <div className="space-y-3">
            {[...Array(4)].map((_, i) => <div key={i} className="card h-24 animate-pulse" />)}
          </div>
        )}

        {active && health && (
          <>
            {/* Health score row */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="card p-4 col-span-2 lg:col-span-1 flex flex-col items-center justify-center py-6">
                <p className="text-[10px] text-t3 uppercase tracking-wide mb-2">Health Score H(t)</p>
                <div className="flex items-baseline gap-2">
                  <span className="text-[42px] font-bold mono text-t1 leading-none">
                    {((health.health_score as number) * 100).toFixed(1)}
                  </span>
                  <span className="text-[16px] text-t3">%</span>
                </div>
                <span className={clsx('mt-2 px-3 py-0.5 rounded border text-[13px] font-bold', GRADE_COLORS[health.grade as string])}>
                  Grade {health.grade as string}
                </span>
              </div>

              <div className="card p-4">
                <p className="text-[10px] text-t3 uppercase tracking-wide mb-1">Sub-entities</p>
                <p className="text-[28px] font-bold mono text-cyan">{health.sub_entity_count as number}</p>
                <p className="text-[10px] text-t3 mt-1">(contract, caller) pairs sampled</p>
              </div>

              <div className="card p-4">
                <p className="text-[10px] text-t3 uppercase tracking-wide mb-1">Threat Level</p>
                <p className={clsx('text-[20px] font-bold', THREAT_COLORS[(attackSurface?.threat_level as string)] ?? 'text-t2')}>
                  {(attackSurface?.threat_level as string) ?? '—'}
                </p>
                <p className="text-[10px] text-t3 mt-1">
                  Attack prob: {(((attackSurface?.attack_probability as number) ?? 0) * 100).toFixed(1)}%
                </p>
              </div>

              <div className="card p-4">
                <p className="text-[10px] text-t3 uppercase tracking-wide mb-1">Distribution Coherence</p>
                <p className="text-[28px] font-bold mono text-t1">
                  {(((health.dc_summary as Record<string, unknown>)?.distribution_coherence as number) * 100).toFixed(1)}%
                </p>
                <p className="text-[10px] text-t3 mt-1 truncate">
                  {((health.dc_summary as Record<string, unknown>)?.interpretation as string)?.split('—')[0]}
                </p>
              </div>
            </div>

            {/* H(t) components + Role distribution */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="card p-4">
                <p className="text-[11px] text-t2 font-semibold mb-3 flex items-center gap-1.5">
                  <BarChart3 size={12} className="text-cyan" /> H(t) Component Breakdown
                </p>
                <div className="space-y-3">
                  <ScoreBar label="Distribution Coherence" value={components.distribution_coherence ?? 0} weight={weights.w_dc ?? 0.35} />
                  <ScoreBar label="User Quality" value={components.user_quality ?? 0} weight={weights.w_user_quality ?? 0.30} />
                  <ScoreBar label="Role Coherence" value={components.role_coherence ?? 0} weight={weights.w_role_coherence ?? 0.20} />
                  <ScoreBar label="Attack Surface" value={components.attack_surface ?? 0} weight={weights.w_attack_surface ?? 0.15} />
                </div>
                <div className="mt-4 pt-3 border-t border-border text-[10px] text-t3">
                  H(t) = 0.35·DC + 0.20·RoleCoh + 0.30·UserQual + 0.15·AttackSurf
                </div>
              </div>

              <div className="card p-4">
                <p className="text-[11px] text-t2 font-semibold mb-3 flex items-center gap-1.5">
                  <Users size={12} className="text-violet-400" /> Role Distribution
                </p>
                {Object.keys(roleDistribution).length > 0 ? (
                  <RoleDonut distribution={roleDistribution} />
                ) : (
                  <p className="text-t3 text-[11px]">No role data — contract may not be in bh_ledger yet</p>
                )}
              </div>
            </div>

            {/* Anomaly events + Distribution comparison */}
            {(anomalous.length > 0 || Object.keys(curDist).length > 0) && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="card p-4">
                  <p className="text-[11px] text-t2 font-semibold mb-3 flex items-center gap-1.5">
                    <AlertTriangle size={12} className="text-amber-400" /> Anomalous Event Spikes
                  </p>
                  {anomalous.length > 0 ? (
                    <div className="space-y-2">
                      {anomalous.map((e, i) => (
                        <AnomalyEvent key={i} event={e as { event: string; current_ratio: number; baseline_ratio: number; spike_factor: number }} />
                      ))}
                    </div>
                  ) : (
                    <p className="text-t3 text-[11px]">No anomalous event spikes detected in current window</p>
                  )}
                </div>

                <div className="card p-4">
                  <p className="text-[11px] text-t2 font-semibold mb-3 flex items-center gap-1.5">
                    <Activity size={12} className="text-cyan" /> Event Distribution vs Baseline
                  </p>
                  <div className="space-y-1.5">
                    {Object.entries(curDist).sort(([, a], [, b]) => (b as number) - (a as number)).slice(0, 8).map(([evt, val]) => {
                      const base = baseDist[evt] ?? 0;
                      const ratio = base > 0 ? (val as number) / base : 1;
                      const isSpike = ratio > 2 && (val as number) > 0.03;
                      return (
                        <div key={evt} className="flex items-center gap-2">
                          <span className={clsx('text-[10px] w-28 flex-shrink-0', isSpike ? 'text-red-400 font-semibold' : 'text-t2')}>{evt}</span>
                          <div className="flex-1 h-1 bg-border rounded-full overflow-hidden">
                            <div className="h-full rounded-full" style={{ width: `${Math.min(Math.round((val as number) * 100), 100)}%`, backgroundColor: isSpike ? '#ef4444' : '#00c2ff' }} />
                          </div>
                          <span className={clsx('text-[10px] mono w-10 text-right', isSpike ? 'text-red-400' : 'text-t2')}>{((val as number) * 100).toFixed(1)}%</span>
                        </div>
                      );
                    })}
                  </div>
                  <div className="mt-2 pt-2 border-t border-border text-[10px] text-t3">
                    JSD: {((distribution?.jsd as number) ?? 0).toFixed(4)} | {distribution?.interpretation as string}
                  </div>
                </div>
              </div>
            )}

            {/* High-risk callers */}
            {highRiskCallers.length > 0 && (
              <div className="card p-4">
                <p className="text-[11px] text-t2 font-semibold mb-3 flex items-center gap-1.5">
                  <Shield size={12} className="text-red-400" /> High-Risk Callers
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {highRiskCallers.map((caller, i) => (
                    <div key={i} className="flex items-center justify-between px-3 py-2 bg-red-500/5 border border-red-500/15 rounded">
                      <div>
                        <span className="mono text-[11px] text-red-400">{(caller.caller as string)?.slice(0, 20)}…</span>
                        <span className="ml-2 text-[10px] text-t3">{(caller.role as string)?.replace(/_/g, ' ')}</span>
                      </div>
                      <span className="text-[10px] text-t3">
                        {caller.tx_count as number} tx · {((caller.confidence as number) * 100).toFixed(0)}% conf
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Recommendations */}
            {recommendations.length > 0 && (
              <div className="card p-4">
                <p className="text-[11px] text-t2 font-semibold mb-3">Recommendations</p>
                <div className="space-y-2">
                  {recommendations.map((rec, i) => {
                    const isUrgent = rec.startsWith('URGENT') || rec.startsWith('ALERT');
                    return (
                      <div key={i} className={clsx('flex items-start gap-2 px-3 py-2 rounded border text-[11px]',
                        isUrgent ? 'border-red-500/20 bg-red-500/5 text-red-300' : 'border-border bg-card2 text-t2'
                      )}>
                        {isUrgent && <AlertTriangle size={11} className="text-red-400 flex-shrink-0 mt-0.5" />}
                        {rec}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Sub-entity user table */}
            {userList.length > 0 && (
              <div className="card overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                  <p className="text-[11px] text-t2 font-semibold flex items-center gap-1.5">
                    <Users size={12} className="text-cyan" /> Caller Sub-entities
                  </p>
                  <span className="text-[10px] text-t3">{userList.length} shown</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-card">
                      <tr className="border-b border-border">
                        <th className="text-left px-4 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">Caller</th>
                        <th className="text-left px-3 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">Role</th>
                        <th className="text-left px-3 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">Risk</th>
                        <th className="text-left px-3 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">Confidence</th>
                        <th className="text-right px-3 py-2 text-[10px] font-semibold tracking-wide text-t3 uppercase">Txs</th>
                        <th className="px-3 py-2 w-8" />
                      </tr>
                    </thead>
                    <tbody>
                      {userList.map((user, i) => (
                        <UserRow
                          key={i}
                          user={user}
                          expanded={expandedUser === `${user.caller}-${i}`}
                          onToggle={() => setExpandedUser(expandedUser === `${user.caller}-${i}` ? null : `${user.caller}-${i}`)}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
