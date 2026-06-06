export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const ORACLE_URL = 'http://127.0.0.1:5001';
const POLL_MS = 3000;
const MAX_SEEN = 600;
const TRIM_TO = 400;

function sleep(ms: number) {
  return new Promise<void>(r => setTimeout(r, ms));
}

export async function GET() {
  let cancelled = false;
  const seen = new Set<string>();
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      const enqueue = (obj: object) => {
        try {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(obj)}\n\n`));
        } catch {
          cancelled = true;
        }
      };

      enqueue({ type: 'connected', ts: Date.now() });

      while (!cancelled) {
        try {
          const res = await fetch(`${ORACLE_URL}/api/v1/feed`, {
            signal: AbortSignal.timeout(4000),
            cache: 'no-store',
          });

          if (res.ok) {
            const json = await res.json();
            const entries: Record<string, unknown>[] = json.feed ?? [];
            let pushed = 0;

            for (const e of entries) {
              const key = `${e.entity_id}-${e.timestamp}`;
              if (!seen.has(key)) {
                seen.add(key);
                enqueue({ type: 'signal', data: e });
                pushed++;
              }
            }

            if (seen.size > MAX_SEEN) {
              const arr = [...seen];
              arr.slice(0, seen.size - TRIM_TO).forEach(k => seen.delete(k));
            }

            if (pushed > 0) {
              enqueue({ type: 'batch_end', count: pushed, ts: Date.now() });
            }
          }
        } catch {
          // network blip — keep looping
        }

        if (!cancelled) await sleep(POLL_MS);
      }

      try { controller.close(); } catch { /* already closed */ }
    },

    cancel() {
      cancelled = true;
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}
