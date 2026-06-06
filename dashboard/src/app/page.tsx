'use client';

import useSWR from 'swr';
import { endpoints, fetchJSON } from '@/lib/api';
import type { HealthData, StatsData } from '@/lib/types';
import Topbar from '@/components/Topbar';
import MetricCard from '@/components/MetricCard';
import LiveFeedTable from '@/components/LiveFeedTable';
import SystemStatus from '@/components/SystemStatus';
import ThreatPanel from '@/components/ThreatPanel';
import LeaderboardTable from '@/components/LeaderboardTable';
import AnimaStats from '@/components/AnimaStats';

function fmt(n: number | undefined): string {
  if (!n) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

export default function OverviewPage() {
  const { data: health, isLoading: hLoad } = useSWR<HealthData>(endpoints.health, fetchJSON, { refreshInterval: 5000 });
  const { data: stats, isLoading: sLoad } = useSWR<StatsData>(endpoints.stats, fetchJSON, { refreshInterval: 10000 });

  const loading = hLoad || sLoad;

  return (
    <>
      <Topbar title="Overview" />

      <div className="flex-1 overflow-y-auto scrollable p-5 space-y-4">
        {/* Top metric strip */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          <MetricCard
            label="Chains Monitored"
            value="37"
            sub="37 chains · 11 VM families"
            accent="cyan"
            loading={loading}
          />
          <MetricCard
            label="Behavioral Records"
            value={fmt(stats?.indexed_vectors)}
            sub="FAISS vector index"
            accent="violet"
            loading={loading}
          />
          <MetricCard
            label="Entities Tracked"
            value={fmt(stats?.indexed_vectors)}
            sub="In Akashic Index"
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
            value={stats?.total_signals_onchain ?? '0'}
            sub="Published to blockchain"
            accent="cyan"
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
