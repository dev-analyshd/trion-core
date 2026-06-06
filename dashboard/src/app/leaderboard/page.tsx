'use client';

import Topbar from '@/components/Topbar';
import LeaderboardTable from '@/components/LeaderboardTable';

export default function LeaderboardPage() {
  return (
    <>
      <Topbar title="Trust Leaderboard" />
      <div className="flex-1 overflow-hidden p-5">
        <LeaderboardTable limit={50} />
      </div>
    </>
  );
}
