# TRION Institutional Dashboard

The institutional-grade terminal frontend for the TRION Protocol and BTCP
Zero-Bridge. Built with Next.js 16 (App Router) + TypeScript + Tailwind CSS 4,
wired **live** to the TRION Sensing Oracle — no mock data, no placeholders.

## Quick start

```bash
# 1. Start the backend (repo root) — serves on :5000 with 271 routes
cd ..
pip install -r api/requirements.txt
python3 serve.py

# 2. Start this dashboard — serves on :3000
cd frontend-institutional
bun install        # or: npm install / pnpm install
bun run dev        # or: npm run dev
```

Open http://localhost:3000 — every metric streams from the Oracle.

## Architecture

```
Browser ──same-origin /api/trion/*──> Next.js route handlers (proxy)
                                          │
                                          └──server-side──> Flask Sensing Oracle (:5000)
                                                            core/  ·  api/  ·  akashic/
```

- `src/app/api/trion/[...path]/route.ts` — catch-all GET/POST proxy to the
  Flask backend (`TRION_BACKEND_URL`, default `http://127.0.0.1:5000`).
  The browser only ever issues same-origin relative requests.
- `src/lib/trion/client.ts` — typed API client (`trionGet` / `trionPost`)
- `src/lib/trion/hooks.ts` — `useTrionPoll` interval-polling hook
- `src/components/trion/` — shell, 9 views, visualization primitives

## Views

| View | Route | Data sources |
|------|-------|--------------|
| Command Center | `#/overview` | health, moat, bh/stats, bh/recent_feed, feed, love/global, validator/hhi |
| Signal Feed | `#/signals` | bh/recent_feed, feed |
| BTCP Zero-Bridge | `#/btcp` | POST btcp/route (K1 simulator), btcp/streamer/status |
| Chain Coverage | `#/chains` | chains (129 registered · 18 VMs), bh/vm_feed |
| Five-Plane Coherence | `#/coherence` | coherence/profiles (11 named + asset types), feed, health |
| Security & Consensus | `#/security` | dw_bft, validator/hhi, feed |
| Governance & AWA | `#/governance` | governance/awa, love/global, falsifiability |
| HashDNA Primitives | `#/primitives` | POST btcp/hash_dna, POST bh/v2/extended, bh/stats |
| Entity Explorer | `#/explorer` | bh/recent_feed, bh/stats, GET bh/{tx_hash} |

## Configuration

Environment (optional):

```
TRION_BACKEND_URL=http://127.0.0.1:5000   # Oracle location for the proxy
```

## Key formulas rendered live

- `C(t) = α·Φ + β·M + γ·Σ + δ·K + ε·A` — five-plane coherence
- `T(t) = [C ≥ Θ] · C · e^M_moat` — master equation
- `Moat = D · Q · R · X · F · N` — multiplicative moat
- `BTCP = (0.25·NL + 0.20·gas + 0.20·finality + 0.15·CC + 0.20·BEO)·(1−MF)` — K1 route score
- `d_j = 1 − corr(M_j, M̄)` — DW-BFT diversity weighting

CC0 Public Domain — TRION Protocol by Hudu Yusuf (Analys).
