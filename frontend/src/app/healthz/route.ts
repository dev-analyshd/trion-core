/**
 * /healthz — lightweight health check endpoint for container orchestration.
 *
 * Phase 8.4: Returns 200 if the Next.js process is alive and can reach the
 * Flask API. Render/Vercel-style health probes can hit this without
 * counting against the API rate limit.
 *
 * This is a Next.js Route Handler (App Router). It runs on the server.
 */
import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function GET() {
  const start = Date.now();
  let flaskOk = false;
  let flaskLatencyMs: number | null = null;

  // Probe the Flask backend
  try {
    const flaskUrl = process.env.FLASK_URL || 'http://127.0.0.1:5000';
    const t0 = Date.now();
    const res = await fetch(`${flaskUrl}/api/v1/health`, {
      signal: AbortSignal.timeout(3000),
    });
    flaskLatencyMs = Date.now() - t0;
    flaskOk = res.ok;
  } catch {
    // Flask unreachable — /healthz still returns 200 (Next.js is alive),
    // but flags flask_ok: false so monitoring can alert.
  }

  return NextResponse.json({
    status: 'ok',
    service: 'trion-frontend',
    timestamp: Math.floor(Date.now() / 1000),
    uptime_ms: process.uptime() * 1000,
    flask_ok: flaskOk,
    flask_latency_ms: flaskLatencyMs,
    response_ms: Date.now() - start,
  }, {
    status: 200,
    headers: {
      'Cache-Control': 'no-store, no-cache, must-revalidate',
    },
  });
}
