'use client';

import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { HealthData, StatsData, ChainsData, AlertsData } from '@/lib/types';
import Topbar from '@/components/Topbar';
import MetricCard from '@/components/MetricCard';
import LiveFeedTable from '@/components/LiveFeedTable';
import SystemStatus from '@/components/SystemStatus';
import ThreatPanel from '@/components/ThreatPanel';
import LeaderboardTable from '@/components/LeaderboardTable';
import AnimaStats from '@/components/AnimaStats';
import BiologicalTime from '@/components/BiologicalTime';

function fmt(n: number | undefined): string {
  if (n == null) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

export default function OverviewPage() {
  const { data: health, isLoading: hLoad } = useSWR<HealthData>(endpoints.health, fetchJSON, { refreshInterval: 5000 });
  const { data: stats, isLoading: sLoad } = useSWR<StatsData>(endpoints.stats, fetchJSON, { refreshInterval: 10000 });
  const { data: chains } = useSWR<ChainsData>(endpoints.chains, fetchJSON, { refreshInterval: 30000 });
  const { data: alerts } = useSWR<AlertsData>(endpoints.alerts, fetchJSON, { refreshInterval: 15000 });

  const loading = hLoad || sLoad;
  const chainCount = chains?.chains?.length ?? 0;
  const liveChains = chains?.chains?.filter(c => c.status === 'live').length ?? 0;
  const alertCount = alerts?.alerts?.length ?? 0;
  const criticalAlerts = alerts?.alerts?.filter(a =>
    a.event === 'signal.collapse' || a.event?.includes('attack')
  ).length ?? 0;

  return (
    <>
      <Topbar title="Overview" />

      <div className="flex-1 overflow-y-auto scrollable p-5 space-y-4">
        {/* Top metric strip */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          <MetricCard
            label="Chains Monitored"
            value={chainCount > 0 ? String(chainCount) : '—'}
            sub={`${liveChains} live · multi-VM`}
            accent="cyan"
            loading={loading}
          />
          <MetricCard
            label="Indexed Vectors"
            value={fmt(stats?.indexed_vectors)}
            sub="FAISS behavioral index"
            accent="violet"
            loading={loading}
          />
          <MetricCard
            label="Market Volatility"
            value={health?.market_volatility !== undefined ? `${(health.market_volatility * 100).toFixed(1)}%` : '—'}
            sub={`Gate threshold: ${health?.dynamic_threshold?.toFixed(3) ?? '—'}`}
            accent={
              (health?.market_volatility ?? 0) > 0.6 ? 'red'
              : (health?.market_volatility ?? 0) > 0.4 ? 'amber'
              : 'green'
            }
            loading={loading}
          />
          <MetricCard
            label="Signals On-Chain"
            value={fmt(stats?.total_signals_onchain)}
            sub="Published to blockchain"
            accent="cyan"
            loading={loading}
          />
          <MetricCard
            label="Active Alerts"
            value={alertCount > 0 ? String(alertCount) : '0'}
            sub={criticalAlerts > 0 ? `${criticalAlerts} critical` : 'All clear'}
            accent={criticalAlerts > 0 ? 'red' : 'green'}
            loading={loading}
          />
        </div>

        {/* Main content grid */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4" style={{ height: 'calc(100vh - 320px)', minHeight: '460px' }}>
          {/* Live Feed — takes 2 cols */}
          <div className="xl:col-span-2 overflow-hidden">
            <LiveFeedTable limit={25} />
          </div>

          {/* Right sidebar */}
          <div className="flex flex-col gap-4 overflow-hidden">
            <SystemStatus />
            <BiologicalTime />
            <ThreatPanel />
          </div>
        </div>

        {/* Bottom row */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4" style={{ height: '340px' }}>
          <div className="xl:col-span-2 overflow-hidden">
            <LeaderboardTable compact limit={8} />
          </div>
          <div className="overflow-hidden">
            <AnimaStats />
          </div>
        </div>
      </div>
    </>
  );
}
