export const BASE = '';

export async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { next: { revalidate: 0 } });
  if (!res.ok) throw new Error(`${res.status} ${res.url}`);
  return res.json();
}

export const endpoints = {
  health: '/api/v1/health',
  stats: '/api/v1/stats',
  feed: '/api/v1/feed',
  chains: '/api/v1/chains',
  leaderboard: '/api/v1/leaderboard',
  archetypes: '/api/v1/akashic/archetypes',
  animaIntelligence: '/api/v1/anima/intelligence',
  signal: (id: string) => `/api/v1/signal/${encodeURIComponent(id)}`,
  deployments: '/deployments.json',
  security: '/api/v1/security/sec',
  zgIntegration: '/api/v1/zg/integration',
  zgChainStatus: '/api/v1/zg/chain/status',
};
