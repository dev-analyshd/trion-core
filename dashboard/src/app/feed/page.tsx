'use client';

import Topbar from '@/components/Topbar';
import LiveFeedTable from '@/components/LiveFeedTable';
import ThreatPanel from '@/components/ThreatPanel';

export default function FeedPage() {
  return (
    <>
      <Topbar title="Live Feed" />
      <div className="flex-1 overflow-hidden p-5 flex gap-4">
        <div className="flex-1 overflow-hidden">
          <LiveFeedTable limit={50} />
        </div>
        <div className="w-64 flex-shrink-0">
          <ThreatPanel />
        </div>
      </div>
    </>
  );
}
