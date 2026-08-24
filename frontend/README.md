# TRION Protocol — React Frontend

Next.js 16 + TypeScript + Tailwind CSS dashboard for the TRION Behavioral Truth Oracle.

## Quick Start

```bash
# 1. Install dependencies
npm install

# 2. Start Flask backend (port 5000)
cd .. && python3 serve.py

# 3. Start Next.js dev server (port 3000)
npm run dev
```

## Architecture

- **Frontend**: Next.js 16 (App Router) + TypeScript + Tailwind CSS + shadcn/ui
- **Backend**: Flask API on port 5000 (238 routes)
- **API Proxy**: `next.config.js` `rewrites()` — no proxy route files

### API proxying (next.config.js rewrites)

There are **no Next.js API route handlers for backend proxying**. All `/api/*`
and `/app/api/*` requests are transparently forwarded to the Flask backend by
`rewrites()` in `next.config.js`:

```js
async rewrites() {
  return [
    {
      source: '/api/:path*',
      destination: `${process.env.FLASK_URL || 'http://127.0.0.1:5000'}/api/:path*`,
    },
    {
      source: '/app/api/:path*',
      destination: `${process.env.FLASK_URL || 'http://127.0.0.1:5000'}/app/api/:path*`,
    },
  ];
}
```

Consequences:

- The browser calls relative paths (`/api/v1/...`) directly; Next.js dev/prod
  server rewrites them to Flask — no CORS handling needed anywhere.
- The Flask target is configured by `FLASK_URL` (default `http://127.0.0.1:5000`).
- Rewrites are applied in both `next dev` and the standalone production build
  (`output: 'standalone'`, Turbopack root pinned to this directory for flat
  Docker output).
- `next.config.js` also sets cache-control headers: `must-revalidate` for pages,
  `immutable` for `/_next/static/*`.

## Features

- 3-column layout: Sidebar + Main content + Right panel (blue gradient)
- Theme switcher: Light / Dark / System
- Fully responsive: mobile (collapsible sidebar), tablet, desktop, ultrawide
- Live data: Auto-refreshes every 10 seconds
- ~100 dashboard pages via `?page=` query routing (`src/views/`)

## Files

```
frontend/
├── src/app/
│   ├── page.tsx                    # Main dashboard (query-routed SPA shell)
│   ├── layout.tsx / globals.css    # Root layout + institutional design system
│   ├── error.tsx / not-found.tsx   # Error boundaries
│   ├── healthz/route.ts            # Health probe (Next.js route handler)
│   └── readyz/route.ts             # Readiness probe (Next.js route handler)
├── src/views/                      # ~100 dashboard views (?page= routing)
├── src/hooks/                      # useContracts.ts (canonical hooks)
│                                   # useBTCP.ts (BTCP/BEO extras, re-exports)
├── src/components/visualizations/  # Whitepaper math visualizations
├── next.config.js                  # rewrites() API proxy + cache headers
├── Caddyfile                       # Gateway config with API routing
└── README.md
```

Note: `healthz` and `readyz` are the only Next.js route handlers — they are
infrastructure probes, not backend proxies.
