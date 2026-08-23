/**
 * TRION frontend configuration — single source of truth for env-driven settings.
 *
 * - apiBase:    client-side base URL (empty string => same-origin via Next.js rewrites)
 * - flaskUrl:   server-side Flask URL (used by next.config.js rewrites, NOT exposed to browser)
 * - wsUrl:      optional WebSocket URL for real-time streaming
 * - environment: 'development' | 'production' | 'test'
 */
export const config = {
  apiBase: process.env.NEXT_PUBLIC_API_BASE || '',
  flaskUrl: process.env.FLASK_URL || 'http://127.0.0.1:5000',
  wsUrl: process.env.NEXT_PUBLIC_WS_URL || '',
  environment: process.env.NODE_ENV || 'development',
  isProd: (process.env.NODE_ENV || 'development') === 'production',
  isDev: (process.env.NODE_ENV || 'development') === 'development',
} as const;

export type TRIONConfig = typeof config;
