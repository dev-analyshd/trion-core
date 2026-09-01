import { NextRequest, NextResponse } from "next/server";

/**
 * TRION Core API gateway.
 *
 * Proxies all requests from the Next.js frontend (port 3000) to the
 * TRION Sensing Oracle Flask backend (port 5000) server-side, so the
 * browser only ever issues same-origin relative requests.
 *
 * GET  /api/trion/<path>  -> http://127.0.0.1:5000/api/v1/<path>
 * POST /api/trion/<path>  -> http://127.0.0.1:5000/api/v1/<path> (JSON body forwarded)
 */

const BACKEND_ORIGIN = process.env.TRION_BACKEND_URL || "http://127.0.0.1:5000";
const BACKLOG_TIMEOUT_MS = 15_000;

async function proxy(req: NextRequest, method: "GET" | "POST") {
  const path = req.url.split("/api/trion/")[1] ?? "";
  if (!path) {
    return NextResponse.json({ error: "missing path" }, { status: 400 });
  }

  // Never allow the browser to reach private metadata endpoints.
  const target = `${BACKEND_ORIGIN}/api/v1/${path}`;

  const init: RequestInit = {
    method,
    headers: {
      Accept: "application/json",
      "X-Requested-With": "trion-dashboard",
    },
    signal: AbortSignal.timeout(BACKLOG_TIMEOUT_MS),
    cache: "no-store",
  };

  if (method === "POST") {
    init.headers = { ...init.headers, "Content-Type": "application/json" };
    init.body = await req.text();
  }

  try {
    const upstream = await fetch(target, init);
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "backend unreachable";
    return NextResponse.json(
      { error: `TRION backend unreachable: ${message}`, backend: BACKEND_ORIGIN },
      { status: 502 }
    );
  }
}

export async function GET(req: NextRequest) {
  return proxy(req, "GET");
}

export async function POST(req: NextRequest) {
  return proxy(req, "POST");
}
