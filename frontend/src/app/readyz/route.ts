/**
 * /readyz — readiness probe for Railway/Compose.
 *
 * Returns 503 until BOTH:
 *   - Next.js is serving
 *   - Flask /readyz returns 200 (Flask → FAISS chain healthy)
 *
 * Distinct from /healthz which always returns 200 when Next.js is up
 * (process-alive signal). /readyz gates routing.
 */
import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function GET() {
  const flaskUrl = process.env.FLASK_URL || 'http://127.0.0.1:5000';
  try {
    const res = await fetch(`${flaskUrl}/readyz`, {
      signal: AbortSignal.timeout(2000),
    });
    if (!res.ok) {
      return NextResponse.json(
        { status: 'not_ready', reason: 'flask_not_ready', flask_url: flaskUrl },
        { status: 503, headers: { 'Cache-Control': 'no-store' } },
      );
    }
    const body = await res.json();
    return NextResponse.json(
      { status: 'ready', ...body },
      { status: 200, headers: { 'Cache-Control': 'no-store' } },
    );
  } catch {
    return NextResponse.json(
      { status: 'not_ready', reason: 'flask_unreachable', flask_url: flaskUrl },
      { status: 503, headers: { 'Cache-Control': 'no-store' } },
    );
  }
}
