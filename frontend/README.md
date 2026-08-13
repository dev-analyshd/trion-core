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
- **API Proxy**: Next.js catch-all routes forward `/api/v1/*` and `/app/api/*` to Flask

## Features

- 3-column layout: Sidebar + Main content + Right panel (blue gradient)
- Theme switcher: Light / Dark / System
- Fully responsive: mobile (collapsible sidebar), tablet, desktop, ultrawide
- Live data: Auto-refreshes every 10 seconds
- 17 dashboard pages accessible via sidebar navigation

## Files

```
frontend/
├── src/app/
│   ├── page.tsx                    # Main dashboard (350 lines)
│   ├── api/v1/[...path]/route.ts   # API proxy → Flask:5000
│   └── app/api/[...path]/route.ts  # Dashboard API proxy → Flask:5000
├── public/
│   └── trion_logo.png              # TRION sacred geometry logo
├── Caddyfile                       # Gateway config with API routing
└── README.md
```
