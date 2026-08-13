import { NextRequest, NextResponse } from 'next/server';

const BACKEND = 'http://127.0.0.1:5000';

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const url = `${BACKEND}/app/api/${path.join('/')}`;
  const search = req.nextUrl.search;
  try {
    const res = await fetch(`${url}${search}`, { signal: AbortSignal.timeout(10000) });
    const data = await res.text();
    return NextResponse.json(JSON.parse(data), { status: res.status });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 502 });
  }
}
