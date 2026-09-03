# Deep Read: `frontend/` + `frontend-institutional/` + `sdk/` (agent 2-e)

**Scope:** every tracked file under the three directories — 75 files total
(frontend 30, frontend-institutional 35, sdk 10). All source files read in full;
`package-lock.json`/`tsconfig.tsbuildinfo`/`trion_logo.png`/`signal_processor.wasm`/`src/package-lock.json`
characterized in one line each; the WASM binary was additionally **instantiated and
its exports enumerated empirically** (Node `WebAssembly.instantiate`), and the
`/api/v1/chains` registry was executed in-process to verify chain counts.
Cross-checks against `api/app.py`, `api/btcp_continuum_routes.py`,
`api/chains_registry.py` are cited where relevant (endpoints genuinely exist or
not). Line numbers refer to current `main`.

---

## Overview

Three deliverables, three generations of the same product:

| App | Stack | Routing | Data source | Verdict |
|---|---|---|---|---|
| `frontend/` | Next.js 16 + React 19 + Tailwind 4 + wagmi/viem | **1 page**, `?page=` query switch over a 134-entry `PAGE_MAP` | Flask via `next.config.js` rewrites (`/api/*`, `/app/api/*`) | Older "everything dashboard": 134 page components in 13 view files, real polling hooks, but a thick layer of hardcoded stats, fabricated fallbacks, static marketing pages, broken links, and zero live contract wiring (all `CONTRACTS` are `null`) |
| `frontend-institutional/` | Next.js 16 + React 19 + Tailwind 4 + Radix (shadcn-style) + recharts | **1 page**, hash routing (`#/overview` … `#/explorer`), 9 views | same-origin catch-all proxy `src/app/api/trion/[...path]/route.ts` → Flask `/api/v1/*` | Newer "institutional terminal". Genuinely live: every view polls real endpoints (all verified to exist in Flask). Honest "static protocol reference" labels on static panels. Main defects: hardcoded **174-chain** marketing number contradicting the 160-chain registry its own view fetches, UTC-mislabeled local clock, TS build errors ignored, leftover Tailwind v3 config importing a package that isn't installed |
| `sdk/` | TypeScript ×4 parallel copies + Python + WASM | n/a | direct `fetch`/`requests` to a user-supplied base URL | Conceptually the nicest code (typed signal taxonomy, 256-bit packing, SILENCE≠VALUATION type safety) but **the WASM layer is broken end-to-end** (calls exports that don't exist, wrong default path), 3 of the TS files are byte-duplicates/drift copies, several endpoints don't exist (`/api/btcp/sanctions`, `/api/btcp/bitp/clipboard`, GET route-by-hash, `/health`), the auth header name mismatches the backend, and the Python SDK reads the wrong ledger key |

Money quote for the merged report: the institutional README's claim
("wired **live** to the TRION Sensing Oracle — no mock data, no placeholders") is
**substantially true for the 9 views' data panels** — but "no placeholders" is
falsified by silent numeric fallbacks (planes `0.55/0.5/0.6/0.5/0.45`,
`C(t)=0.6`, `Θ=0.55`, BALANCED weights, tier `"—"`) that render plausible values
while the backend is unreachable, and by the "174 chains / 22 VMs" number
hardcoded in four places while the live registry returns **160 chains / 22 VMs
(94 live, 23 testnet, 43 indexed)** — verified by executing
`api.chains_registry.get_all_chains()`.

---

## Per-app findings

### A. `frontend/` — legacy 134-page dashboard

**Config & entry**

- `package.json` (30 ln) — `next ^16`, `react ^19`, `wagmi ^2.12`, `viem ^2.21`,
  `@tanstack/react-query`, `lucide-react`; Tailwind 4 via `@tailwindcss/postcss`.
  `start` uses `${PORT:-10000}` (Render convention). No lockfile drift: lockfile
  (292 KB) present and consistent with package.json name/version.
- `next.config.js` (47 ln) — `output: 'standalone'`, Turbopack root pinned to the
  dir (Docker flat output); cache headers (HTML `must-revalidate`, static
  `immutable`); **API proxying is done here** via `rewrites()` `/api/*` and
  `/app/api/*` → `$FLASK_URL` (default `127.0.0.1:5000`). Matches the README's
  "no proxy route files" note.
- `README.md` (84 ln) — accurate about the rewrite architecture; says "~100
  dashboard pages" (actual: 134 `PAGE_MAP` entries); claims "Live data: refreshes
  every 10 seconds" (real intervals range 2–60 s).
- `.env.example` (23 ln) — `FLASK_URL`, `NEXT_PUBLIC_API_BASE` (empty →
  same-origin), optional `NEXT_PUBLIC_WS_URL`, commented-out WalletConnect ID,
  optional analytics. WalletConnect is never actually wired (no projectId code
  path) — the hint is vestigial.
- `tsconfig.json` — `strict: false` **but** `strictNullChecks: true` (unusual
  half-strict combo); paths `@/*` defined but barely used (imports are relative).
- `postcss.config.mjs` / `next-env.d.ts` / `.gitignore` (1 line: tsbuildinfo) —
  boilerplate.
- `tsconfig.tsbuildinfo` (548 KB) — build artifact; gitignored in
  frontend-institutional but *committed* here (hygiene issue, matches
  `.gitignore` naming it and yet it's tracked).
- `public/trion_logo.png` — 384×404 8-bit RGB PNG, 168 KB; used as icon/OG image.
- `Caddyfile` (37 ln) — port 81: `XTransformPort` query-based reverse proxy
  (Replit convention), `/api/*` + `/app/api/*` → Flask:5000, everything else →
  Next:3000. Redundant with the Next rewrites (both layers proxy; harmless but
  duplicated).

**`src/app/`**

- `layout.tsx` (115 ln) — Inter + JetBrains Mono, FOUC-avoiding inline theme
  script reading `trion-theme`, JSON-LD `SoftwareApplication`, full OG/Twitter
  metadata. **Marketing numbers baked into metadata**: "128 chains and 18 VM
  families" (backend registry says 160/22; other repo docs say 96/124/56…).
  ErrorBoundary + Web3Provider wrap the tree.
- `page.tsx` (739 ln) — the entire SPA. `PAGE_MAP` **134 pages** mapped from 13
  view modules; `PAGE_TITLES` mirrors it; `?page=` routing with `useSearchParams`
  inside `Suspense`; keyboard shortcuts (`?`, ⌘B); default page is
  `RedesignedDashboard` — hero (health/faiss/streamer/bh stats), PipelineFlow,
  CoherenceEngine, MasterEquation, MoatFactors, SignalPublication, live feed
  (15 items), whitepaper formula cards (L5.2/L5.3/L0.5/L1.1/L4.1), footer
  "128 chains · 18 VM families". Clean component decomposition (MetricCard,
  FormulaBlock).
- `error.tsx` / `not-found.tsx` — friendly 500/404 with link home.
- `healthz/route.ts` — probes Flask `/api/v1/health` with 3 s abort; always 200
  with `flask_ok` flag (process-alive semantics). Correct pattern.
- `readyz/route.ts` — 503 until Flask `/readyz` 200; gates routing. Correct.
- `globals.css` (188 ln) — "Institutional Design System v3.0", dual light/dark
  token sets, thin scrollbars, WCAG focus ring, `stream-flow`/`pulse-ring`/
  `ticker`/`shimmer` animations, grid-pattern hero, glass panels, responsive
  font scale (14.5px→17.5px), print styles, `prefers-reduced-motion` respected.
  High quality CSS.

**`src/lib/`, `src/hooks/`, `src/providers/`, `src/config/`**

- `lib/api.ts` (200 ln) — `fetchAPI` discriminated union
  (`{ok,data,status} | {ok,error,type}`) with timeout/invalid-JSON/abort
  classification; `postAPI` auto-attaches `X-API-Key` from localStorage
  (matches backend `api/app.py:155`); formatting helpers (`fmt`, `pct`, `hex`,
  `compact`…); `statusColor` vocabulary; `cleanText` Greek/formula scrubber —
  **but the scrubber's symbol table produces visibly duplicated labels** (see
  bugs #20/§Bugs).
- `lib/config.ts` (18 ln) — env single source of truth.
- `lib/hooks.ts` (321 ln) — `useAPI` (poll, refresh, tick), `useMultiAPI`,
  `useStream` (100-item deduped buffer with identity keys; comment documents the
  duplicate-accumulation bug it fixed), `useCounter` (eased rAF), `useTheme`,
  `useWebSocket` (exponential backoff 1→30 s, 100-msg buffer, polling fallback).
  `useWebSocket` is **never imported by any view** (dead export); its doc comment
  says "Default interval: 50ms (20 Hz)" while the actual default is 2000 ms.
- `providers/Web3Provider.tsx` (17 ln) — WagmiProvider + QueryClientProvider.
- `config/wagmi.ts` (94 ln) — 10 wagmi chains + custom BOT Chain (id 677,
  rpc.botchain.ai); connectors metamask/coinbase/injected; **`CONTRACTS` map is
  100% `null` on every chain for all 8 contracts** (btcpEscrow/Intent/Route,
  pmoRegistry, beoIdentity, coherenceVault, oracleV3, bhLedger) — i.e., the
  wallet can connect but every on-chain feature is structurally disabled
  ("Contracts deploying soon").
- `hooks/useContracts.ts` (375 ln) — minimal hand-rolled ABIs (lockEscrow 6-arg,
  releaseEscrow, revertEmergency, getEscrow, emergencyEscape, registerIntent
  11-arg, registerBEO, coherenceWrap/Unwrap, ExecutionGate view fns,
  publishBehavioralTruth); hooks gate on contract presence. `useTRIONExecutionGate`
  hardcodes a 0G-chain (16661) address `0xA85B49…` — contradicts the
  Arbitrum-Sepolia story told elsewhere and is dead code while `CONTRACTS` are null.
- `hooks/useBTCP.ts` (72 ln) — thin re-export façade over useContracts (documents
  the July 2026 audit that consolidated drifted duplicates) + unique
  `BEO_IDENTITY_ABI` (`getBEO`, `beoExists`) and `useUserBEOAttestation`.

**`src/components/`**

- `ui.tsx` (812 ln) — shared kit: Card, StatCard (responsive clamp sizing),
  ProgressBar, Badge, DataTable (sort cycle, CSV/JSON export, copyable cells,
  aria-sort), CodeBlock, KVList, EntityInput (sample quick-fill), Spinner,
  EmptyState, Skeleton/SkeletonCard, ErrorState (typed network/timeout/server),
  StreamView (latency + Hz row, honest tooltip "API round-trip latency (not BH
  computation speed)"), `ArchitectureFlow` (hand-authored SVG diagram — contains
  hardcoded marketing: "16 crates", "128 chains", "18 VM families", "531K+
  vectors", "472 tests passing", "All systems operational"), PlaneGauge
  (SVG ring), LiveClock (**bug**: local time labeled "UTC").
- `Sidebar.tsx` (418 ln) — 17 groups / ~130 items, search filter, collapsible
  groups, recently-visited (localStorage), mobile drawer. Comment says "18 page
  groups / 70+ pages" (stale). `dw_bft` appears in **two** groups (Governance and
  Validators). "Novel Primitives" group was removed ("backend-only") but its 10
  pages remain in `PAGE_MAP` — URL-only orphans.
- `CommandPalette.tsx` (293 ln) — ⌘K fuzzy palette with scoring, recent-first,
  keyboard nav, scroll-into-view, localStorage recents. Well built.
- `ErrorBoundary.tsx` (97 ln) — class boundary, structured console logging,
  reset + reload actions, `<details>` stack.
- `SettingsModal.tsx` (170 ln) — API key store → `X-API-Key` on POSTs (matches
  backend), read-only/write-enabled indicator.
- `ShortcutHelpDialog.tsx` (135 ln) — accessible dialog replacing an old
  `alert()`; documents ⌘K/⌘B/?/Esc.
- `wallet/WalletButton.tsx` (327 ln) — full connector: wrong-chain detection,
  chain switcher (11 chains), balance, explorer link, copy address, aria attrs,
  click-outside/Escape. Good; but everything downstream is dead because
  `CONTRACTS` are null.
- `visualizations/` (5 files, ~700 ln) — whitepaper-aligned live widgets:
  `CoherenceEngine` (radar chart, weights fetched from
  `/api/v1/coherence/profiles` with BALANCED fallback and live/indicator label),
  `MasterEquation` (T(t)=[C≥Θ]·C·e^M breakdown), `MoatFactors` (D·Q·R·X·F·N with
  bootstrap fallback 0.5 per factor), `PipelineFlow` (8 stages fed by streamer/
  faiss/health), `SignalPublication` (Oracle address
  `0xb819c63c…58b3`, chain 421614 Arbitrum Sepolia, 256-bit packing legend).
  All fetch real endpoints; several silent fallbacks.

**`src/views/` (13 files, ~5,500 ln, 134 pages)**

- `overview.tsx` (547) — DashboardPage (10 endpoints), ArchitecturePage
  (dependency graph, relayers, backfill + **hardcoded 8×'OK' "Pipeline
  Connectivity Check"**), Vision, Phases, PhaseTransition, OrderParameter,
  Convergence. `DashboardPage` "Master Equation" card computes C from
  `dynamic_threshold` (mislabel); "Security Posture" hardcodes LSS=100%,
  PQC=90%.
- `behavioral.tsx` (461) — BH Explorer (entity lookup + `/api/v1/bh/<id>`,
  vm_feed, recent_feed), BH v2 Extended (POST demo with fixed sample payload),
  BH Stats, Akashic/Archetypes, BEO (signal + akashic match), FAISS, Signals +
  aliases. Mostly live; `vmFeed` fallbacks `total_vm_families||14`,
  `total_chains||57`.
- `planes.tsx` (405) — Physical/Mental/Spiritual/Conscious/ANIMA plane pages +
  profiles. **Physical plane fabricates F1–F9 as `0.1 + i*0.08` when API omits
  features** (line 74) — displayed as live values.
- `security.tsx` (460) — SEC, Living Security, Chameleon, CRISPR, PQC (static
  "verified" round-trips), MF Detector (static formula table), MEV, Immune,
  Attacks (polls `/api/v1/demo/simulate_attack` via GET every 30 s —
  side-effectful GET).
- `governance.tsx` (725) — Governance, AWA ("4 Conditions" — inconsistent with
  institutional view's 8), Gratitude, Love, Falsifiability, Slashing,
  UnknownProvision, AdaptiveConsensus/RightToInvisibility/ElderWisdom (purely
  static), DWBFT (nice math explanation; **HHI fallback 1482**, hardcoded
  sybil-sim 75.8% vs 0%).
- `akashic.tsx` (281) — 10 per-entity KV pages (epigenetics, fork, resurrection,
  trajectory, dormancy, genesis, convergence, manifestation gap, negative space,
  emergence). Thin but live.
- `markets.tsx` (279) — BTCP/BIBL/BITP/Continuum pages are **pure static text**;
  BTCP "Routes Published" is an honest empty table ("Connect BTCPRoute
  contract"); SBA/price/liquidity/stablecoin/hierarchy live.
- `primitives.tsx` (322) — BIRP (phases + genomic endpoint), DNA_Code (static),
  UBL, BC, XSL, Transduction, Inversion, PredictiveLimit, Information,
  PhaseSignal. Live KV pages for "backend-only" primitives (sidebar removed).
- `btcp_continuum.tsx` (374) — pipeline status, hash_dna demo (POST), 7-plane,
  MF fingerprints (static), BTCP modules ("18" hardcoded), escrow FSM, private
  BIBL, continuum engines (**5 headers but 4 cells per row** — 'Formula' column
  empty/misaligned).
- `spec_pages.tsx` (598) — BTCP/Continuum/BOT Chain "spec" pages with large
  embedded `BTCP_DATA`/`CONTINUUM_DATA`/`BOTCHAIN_DATA` constants. **BOT Chain
  contract addresses are malformed hex** (44/34/38 chars — not valid 20-byte
  addresses) with fabricated metrics (28,800 BH/day, 1,247 BEOs, $1,247.50 gas
  saved, "Aug 12, 2026" future dates, deployer balance). CTAs link to
  `/continuum`, `/btcp` — routes that don't exist in this SPA (404s).
- `ui_assessment.tsx` (615) — BEO Lookup Toolbox (parallel fetch signal + bh
  ledger), Live Event Stream (merges BH + signal + oracle events with ages),
  TimeSeries (client-side history sparklines — "simulated from live data" is
  literally in the section comment), BTCP/Continuum visualization pages
  (duplicate data constants from spec_pages; BIBL snapshot is live).
- `wallet_pages.tsx` (494) — WalletBTCP route simulator now calls **real**
  `POST /api/v1/btcp/route` (K1 resolution; comment documents replacing a
  `Math.random()` version) with editable from/to/amount; input dicts (NL/gas/CC/
  MF/finality/validators) are hardcoded sample values. WalletContinuum page:
  static engines + live FAISS/streamer cards; CCP donut (SVG) 40/40/12/8.
- `core_principles.tsx` (513) — Home (signal + feed + health + moat), Zero-Bridge
  (chain selects incl. Solana=900, TON, NEAR; real POST `/api/v1/btcp/route`),
  Witness, BEO Dashboard (planes/all, gk, reputation), Action Economy, Digital
  Self ("The Honest Claim" section is genuinely well written).
- `infrastructure.tsx` (795) — validators (sigma/hhi/dw_bft), annotators
  (static), bootstrap, reputation, 7×0G pages (zg/full_stack…zg/vm-families),
  chains/timescale/kv/backfill/relayers/depgraph/sdk-spec/token/revenue, agent
  pages (AgentsPage and AgentValidatePage are aliases of AgentPage — lazy),
  protocol monitor/roles/self, 4 CEX pages, leaderboard/feed/audit/demo.
  ChainsPage hardcodes "VM Families: 14" while fetching the real registry.

### B. `frontend-institutional/` — the 9-view terminal

**Config**

- `README.md` (69 ln) — architecture diagram (browser → same-origin `/api/trion/*`
  → proxy → Flask), view table with data sources (accurate — all endpoints
  verified to exist), "no mock data, no placeholders" claim, `TRION_BACKEND_URL`
  env, formula list. One internal contradiction: views table says "chains (160
  unique · 22 VMs)" while the footer/metadata say 174.
- `package.json` (36 ln) — `next ^16.1.1`, react 19, Radix primitives
  (dialog/select/slider/slot/tabs), `cva`, `clsx`+`tailwind-merge`, `recharts`,
  `lucide-react`. **No lockfile committed** (README says bun/npm/pnpm install).
  `eslint src` script exists but no eslint config file is committed.
- `next.config.ts` (12 ln) — `output: "standalone"`, **`typescript:
  { ignoreBuildErrors: true }`**, `reactStrictMode: false`. Type errors are
  deliberately silenced.
- `tailwind.config.ts` (64 ln) — Tailwind **v3-style** config (hsl(var(--…)))
  importing `tailwindcss-animate` — **a package that is not in package.json**
  (devDeps have `tw-animate-css`). Under Tailwind v4 (CSS-first via
  `@theme inline` in globals.css) this file is dead weight that would crash any
  tooling that loads it. Leftover from the shadcn scaffold.
- `components.json` — shadcn "new-york" style manifest.
- `tsconfig.json` — `strict: true` but `noImplicitAny: false` (weakened).
- `.env.example` (3 ln) — `TRION_BACKEND_URL=http://127.0.0.1:5000`.
- `.gitignore` — node_modules/.next/out/build/env/logs/tsbuildinfo/next-env.d.ts.
- `postcss.config.mjs` — `@tailwindcss/postcss` only (consistent with Tailwind 4).

**Proxy route — `src/app/api/trion/[...path]/route.ts` (67 ln)**

Catch-all GET/POST proxy: splits `req.url` on `/api/trion/`, forwards to
`$TRION_BACKEND_URL/api/v1/<path>`, 15 s abort, `cache: 'no-store'`, forwards
POST body verbatim, relays status + content-type, 502 JSON with backend origin
on failure. The comment "Never allow the browser to reach private metadata
endpoints" is **aspirational — no allowlist is implemented** (any `/api/v1/*`
path is proxied, including e.g. `app/debug`-style paths if they existed; the
only protection is the `/api/v1/` prefix). Query strings survive (split keeps
`?…`). This is the "same-origin proxy" the task brief highlighted: it exists,
it's minimal, and it works.

**App shell**

- `src/app/layout.tsx` (57 ln) — Geist/Geist Mono; metadata description claims
  "174 chains across 22 VM families"; **favicon is an external ChatGLM CDN
  URL** (`https://z-cdn.chatglm.cn/z-ai/static/logo.svg`) — a non-TRION asset
  (and a build-time external dependency for the tab icon).
- `src/app/page.tsx` (131 ln) — hash-router (`#/btcp` etc., hashchange listener,
  deep-linkable), VIEW_MAP of the 9 views, top-level `useTrionPoll("health",
  5000)` feeding TopBar; sticky footer status ticker (duplicated strip for
  seamless scroll) with live health values + marketing lines ("174 CHAINS · 22
  VM FAMILIES", "BIBL 3-TIER · <200MS").
- `shell/Sidebar.tsx` (145 ln) — 9 views in 4 groups (PROTOCOL/CROSS-CHAIN/TRUTH
  ENGINE/CIVILIZATION) with hover state, active rail, mobile drawer, footer
  badges ("174 CHAINS · 22 VMs", "CC0 · v2.0.0 · ORACLE LIVE").
- `shell/TopBar.tsx` (99 ln) — view label, oracle identity, network, Θ, wifi
  on/off status (aria-live), **clock labeled "UTC" that renders local time**
  (`toLocaleTimeString("en-GB", {hour12:false})` without `timeZone: "UTC"`).

**Data layer**

- `lib/trion/client.ts` (141 ln) — typed interfaces (TrionHealth, BhStats,
  BhRecord, MoatFactors, PlaneProfile, DwBft incl. `coordination_attack_simulation`,
  HhiStatus, ChainEntry, BtcpRouteResult, FeedItem) + `trionGet`/`trionPost`
  (relative `/api/trion/*`, `cache: 'no-store'`, throws with HTTP status and
  200-char error body).
- `lib/trion/hooks.ts` (59 ln) — `useTrionPoll`: setTimeout self-chaining loop
  (not setInterval — avoids overlap), `alive` ref guard, `lastUpdated`,
  loading/error state; `deps` spread into the effect (array-size lint hazard).
- `lib/utils.ts` — `cn()` (clsx + tailwind-merge).

**The 9 views (special attention)**

1. **Command Center — `OverviewView.tsx` (411 ln).** Polls health(5s),
   moat(8s), bh/stats(6s), bh/recent_feed(4s), feed(6s), love/global(15s),
   validator/hhi(10s). Hero = master equation with TRUTH ACTIVE / BELOW
   THRESHOLD badge, C(t) & MOAT GaugeRings; 6-metric strip (BHs, chains indexed
   — "of 174 registered", Akashic depth, CLV, HHI with freeze>4000 tone,
   signals on-chain); five-plane radar + per-plane meters + C(t) history
   sparkline (from `feed` — live series); moat decomposition (6 meters + M(t));
   L0→L6 pipeline timeline; live BH stream table (verdict color-coding).
   Fallback constants: planes `0.55/0.5/0.6/0.5/0.45`, `coherence ?? 0.6`,
   `threshold ?? 0.55`; `bhTrend` sparkline is a **synthetic ramp**
   (`total−900…total−600…total` — fabricated trend, not history). Dead import
   `trionPost` (line 14).
2. **Signal Feed — `SignalsView.tsx` (197 ln).** bh/recent_feed(3s) + feed(6s);
   chain & event-type dropdowns built from observed data; verdict counting;
   80-row stream table with sense/antisense strands; "Protocol
   Self-Verification" strip (genomic generation, archetype, limiting plane).
   Fully live.
3. **BTCP Zero-Bridge — `BtcpView.tsx` (948 ln).** The K1 route simulator:
   per-chain sliders for NL & MF, gas inputs, intent value, 3 presets (HIGH /
   STRESSED / ADVERSARIAL — the adversarial preset demonstrates fail-closed),
   `POST btcp/route` with full body (all fields match the Flask handler at
   `api/btcp_continuum_routes.py:180`); result card: resolved route badge,
   anchor→execution flow diagram (animated CSS arrows), 4 minimum-viable-route
   gates (client-side mirror of `route_is_valid`), finality/BEO/CC meters, K1
   ladder (NETTING…SPLIT); fail-closed banner with reason & score; BIBL 3-tier
   latency budget (T1 continuous / T2 <50ms / T3 <150ms, <200ms total — static
   but labeled "D3 Resolution"); escrow state machine **honestly labeled
   "static protocol reference"** (HOLDING → PENDING_AKASHIC → RELEASED +
   REVERTED / EMERGENCY_ESCAPE dashed terminals + revert reasons); streamer
   control panel (poll status 5s, **Start Streamer button POSTs
   `btcp/streamer/start`** — exists at `api/btcp_continuum_routes.py:697`);
   5 protocol fact cards. Caveat: `CC_COHERENCE`/`FINALITY_DIST`/
   `VALIDATOR_COUNTS`/`GAS_REFERENCE` are client constants, not fetched from the
   BIBL snapshot — the simulator's inputs are partially synthetic even though
   the scoring is real.
4. **Chain Coverage — `ChainsView.tsx` (576 ln).** chains(30s) + bh/vm_feed(5s).
   Counts live/testnet/indexed from the registry itself; proportional stacked
   VM-family bar (emerald→cyan hex blend); top-12 live BH coverage bars;
   searchable/filterable table (VM + status selects) with per-row Dialog
   (registry record + raw JSON). **Metric labels and the table footer still say
   "174 chains" while `chains.length` is 160** — the view contradicts its own
   hardcoded copy.
5. **Five-Plane Coherence — `CoherenceView.tsx` (209 ln).** coherence/profiles
   (20s) + feed(6s) + health(5s). Live radar; **C(t) computed client-side under
   a selectable named weight profile** with per-term α·Φ…ε·A arithmetic shown;
   named profiles table with weight-sum validation (green when Σ=1); asset-type
   profile cards with 5 meters each. Falls back to BALANCED
   `0.25/0.30/0.25/0.10/0.10` when profiles are missing.
6. **Security & Consensus — `SecurityView.tsx` (847 ln).** dw_bft(6s) +
   validator/hhi(10s) + feed(8s). DW-BFT panel: safety-proof quote
   (d_j = 1 − corr(M_j, M̄)), byzantine effective weight/δ-drift/total stake/
   safety margin chips, v̄ gauge with adaptive scale, Σ(t) ring; **coordination
   attack simulation as a Recharts LineChart** (from live
   `dw.coordination_attack_simulation` — real backend data); HHI concentration
   monitor: 0–5000 segmented meter with LOW/MODERATE/CRITICAL markers, current
   reading + registry validators/continents/F8/F9/pause/emergency flags;
   manipulation firewall table (7 patterns — static, labeled "static protocol
   constants"); 5 sybil-resistance layer cards (L1 log-depth…L5 star-pattern);
   crypto stack 2×2 (PQC, Genomic Key with live generation & fingerprint, 5 ZK
   circuit names, Living Security with live GEN/archetype). Highest-quality view.
7. **Governance & AWA — `GovernanceView.tsx` (737 ln).** governance/awa(8s) +
   love/global(15s) + falsifiability(30s). AWA verdict banner (ARMED/DEGRADED,
   armed iff all conditions met or `enforced`), 8-condition checklist with
   value≥threshold rendering + pending-telemetry chips; bootstrap weight /
   akashic depth / gratitude counters; Love protocol gauge (CLV), grade
   distribution stacked bar (EXEMPLARY→HOSTILE_COLLAPSE) + per-grade rows +
   trust-web stats + unlock badges; civilization leaderboard (grade+LV sort);
   falsifiability registry table (status colors, N, test metric, window,
   disclosure, live-evidence note); 4 "Institutional Rights" cards (static,
   labeled). Note: 8 AWA conditions here vs **4** in the legacy frontend —
   cross-app inconsistency.
8. **HashDNA Primitives — `PrimitivesView.tsx` (955 ln).** bh/stats(10s) +
   feed(8s). 93-byte payload byte-map (proportional SVG memory map + offsets +
   big-endian note); dual-strand construction formulas; **Hash Lab** with two
   tabs: HashDNA (POST `btcp/hash_dna` — 11 editable fields, request JSON shown
   verbatim, response hash/domain/currency/magnitude) and Extended v2 BH (POST
   `bh/v2/extended` — event-type dropdown of the 20 types, CSPRNG nonce hint);
   magnitude normalization lab (client-side log10 formula with live math);
   Genomic Key card (live generation + 8 G1–G8 DNA components); thermodynamic
   deletion card (dI/dS > θ selection mini-lab); resonance weights (top-6 bars +
   20-type chips) + 256-bit packed signal bit-field map with shift layout. All
   POSTs verified live (btcp_continuum_routes.py:42 / app.py bh/v2/extended).
   Sample defaults are clearly "pre-filled" with a hint line.
9. **Entity Explorer — `ExplorerView.tsx` (612 ln).** bh/stats(6s) +
   bh/recent_feed(3s) + bh/vm_feed(12s). Client-side search over the ~100-record
   feed window; **"BEO Entity Resolution" panel groups the feed by entity_id
   client-side** (presentation implies resolution; it's an aggregation of the
   last 100 records); per-chain top-20 distribution; event-type distribution
   cards; VM family strip; row click → Dialog that fetches **`GET bh/{tx_hash}`**
   (dual-strand detail with valid flag, canonical order, formulas) + raw record
   JSON. Verdict vocabulary widened (SAFE/MEV/INTERCEPT/HOSTILE/WATCH/ELEVATED).

**UI kit** — `components/ui/` (7 files, 635 ln): shadcn-style badge/button
(cva variants), input, slider (Radix), dialog (overlay + close + sr-only),
select (portaled, popper, scroll buttons), table (8 subcomponents). All
conventional, correctly typed. `viz/primitives.tsx` (253 ln): StatCounter (eased
rAF), CoherenceRadar (threshold polygon + value polygon), GaugeRing,
Sparkline, MeterBar (threshold tick). `globals.css` (236 ln): shadcn oklch token
sets + "INSTITUTIONAL TERMINAL THEME v4.0" (`.trion-app` palette, grid bg,
panel, label, mono, live dot, shimmer, 42 s ticker, thin scrollbars, focus
visibility, reduced-motion). Dark-terminal aesthetic, coherent, reduced-motion
respected. Accessibility is above average (aria-labels everywhere, roles on
meters/dialogs, `aria-sort` in legacy app).

### C. `sdk/` — TypeScript ×4 + Python + WASM

- `TrionSDK.ts` (730 ln, sdk root) — static helper class: `fetchSignal` /
  `checkHealth` (`/api/v1/signal/{id}`, `/api/v1/health`); classification
  helpers (isSafe/isSilence/isManipulationAlert/isGenesis, coherenceMargin,
  limitingPlane, summarize); **256-bit pack/unpack** (status[0:8],
  coherence×1e6[8:40], threshold×1e6[40:72], block[72:136], ts[136:200] —
  consistent with the frontends' packing legend); `signalToPacked` with a
  15-entry signal-type→status map; biological rhythm dominance;
  `normalizeEntityId` (padEnd 42 — questionable for non-address IDs);
  `supportedChains()` (8 chains — contradicts every other chain list);
  BTCP helpers (`btcpScoreTier`, `minValidators` C1, `coverageMultiplier` C2,
  `checkBITPTolerance` 2%, `mfScoreLevel`); **fetchBTCPRoute /
  fetchBITPClipboard / checkSanctions** (see Bugs — endpoints don't exist;
  checkSanctions **fails open**: `sanctioned:false, confidence:1` on any
  error); WASM loader + `verifyCoherenceWasm` + `computeEntropyWasm`
  (**broken**, see below).
- `src/index.ts` (620 ln) — **byte-identical to TrionSDK.ts minus the entire
  WASM section** (diff: 621–730 deleted). Drift-prone duplicate.
- `src/trion-sdk.ts` (308 ln) — **byte-identical to `src/client.ts`** (verified
  by diff).
- `src/client.ts` (308 ln) — `TRIONClient` class: 19-signal taxonomy
  (VALUATION…BOOTSTRAP incl. FORK_DIVERGENCE, SYSTEMIC_RISK, MEV_EXPOSURE…),
  `ValuationSignal`/`SilenceSignal` discriminated subtypes (nice type-level
  SILENCE≠VALUATION enforcement), trading-signal layer types, `getSignal?
  profile=`, `getAllPlanes/getPhysicalPlane`, `preExecCheck`
  (POST `/api/v1/security/check`), `getNLScore` (`/api/v1/liquidity/{addr}`),
  `getBTCPScore` (POST `/api/v1/btcp/score`), `health()` → **`/health` (no such
  Flask route)**, `getBootstrapStatus`/`getFalsifiability` →
  `/api/v1/system/bootstrap|falsifiability`, `getVMStatus` →
  `/api/v1/index/vm-status`, trading signal/agent decide/patterns/scanChain.
  Default base `https://trion-protocol.onrender.com`. `TRION_MODIFIER` solidity
  snippet export (references `verifyExecution(txId)` — matches the ABI
  disagreement agent 2-g flagged in SUBMISSION).
- `src/trion.ts` (297 ln) — a *third* client variant: config-object
  constructor (baseUrl/apiKey/timeoutMs/retryCount), retry with backoff (only
  retries ≥500), **`X-TRION-API-Key` header (backend expects `X-API-Key`)**,
  plane getters ×5, security check (POST `/api/v1/security/check` with
  `{tx_data}` — different body shape than client.ts's `preExecCheck`!),
  `getMFScore`, `getCRISPRLibrary`, NL, BTCP score, system
  status/bootstrap/falsifiability, `/health`, `getSignalHistory`
  (`/api/v1/signal/{id}/history`), `batchSignals` (POST `/api/v1/signal/batch`
  — exists), `isSafeToExecute` composite (SILENCE or MF≥0.70 → unsafe). Example
  URL `trion-protocol.replit.app` (stale).
- `src/package.json` — `@trion-protocol/sdk` v1.0.0, main `dist/trion.js`,
  build `tsc`, test `jest` (no jest config, no tests, no dist, no tsconfig in
  src/ — `tsc` would compile with defaults). `src/package-lock.json` — empty
  lockfile v3 (zero deps).
- `src/wasm/signal_processor.wat` (169 ln) + `.wasm` (768 bytes) — hand-written
  WAT: 24 signal-type globals, Θ constants (0.55/0.92), BRT moduli; exports
  `compute_threshold` (Θ=0.55+0.37·clamp(V) — **matches Flask
  `dynamic_threshold = 0.55 + 0.37*vol` exactly**, a rare cross-layer
  consistency), `signal_emits`, `is_silence_type`/`is_valuation_type`,
  `apply_mf_correction` (Φ(1−MF)), `compute_pc_limit`, 4 `brt_*` phase
  functions, `signal_type_count`(24), `is_extended_signal`(19–23). Own memory
  `(memory 1)`, **not exported**. **Empirically instantiated**: 12 exports, no
  `compute_coherence`, no `shannon_entropy`, no `memory` export. Header claims
  "Companion TypeScript SDK (chains/*/execute.ts) imports these exports" — no
  such consumer exists in `chains/`.
- `trion_sdk.py` (536 ln) — the best-behaved SDK: typed dataclasses
  (TRIONSignal w/ CI fallback, PlaneBreakdown, BehavioralHash **with local
  `verify()`** checking the XOR complement invariant against a stored
  `complement_invariant_hex`, LivingIndex), requests-based `_HTTP` (raises on
  non-2xx), methods hitting endpoints that **all exist** (signal, trion/<id>,
  signal/type/<type>/<id>, signal/batch (50 cap), bh GET/POST, bh/ledger, 5
  planes, security mf/gk/immune/chameleon, living_index, emergence,
  universal_asset, manifestation_gap, awa, falsifiability, phases, whitepaper
  coverage, moat, coherence profiles, convergence), `subscribe` polling loop,
  `verify_signal` (requires `genomic_signature` len==128 — signals that lack
  it fail; strictness is honest but makes it near-unusable against current
  payloads), `connect()` factory. `get_bh_ledger` reads `data.get("entries")`
  but Flask returns **`bh_records`** → always `[]`.

---

## API wiring map

**frontend/ (legacy)** — browser → Next rewrites → Flask `/api/*` (agent 2-f's
inventory is the reference). Distinct endpoints observed across the 13 view
files (GET unless noted):

- Core: `/api/v1/health`, `/api/v1/stats`, `/api/v1/moat`,
  `/api/v1/security/sec`, `/api/v1/whitepaper/coverage`,
  `/api/v1/leaderboard`, `/api/v1/faiss`, `/api/v1/bh/stats`,
  `/api/v1/bh/recent_feed`, `/api/v1/feed`, `/api/v1/bh/{id}`,
  `/api/v1/bh/vm_feed`, `/api/v1/bh/v2/extended` (POST),
  `/api/v1/bh/ledger/{id}`, `/api/v1/signal/{id}`,
  `/api/v1/akashic/match/{id}`, `/api/v1/signal/types`,
  `/api/v1/coherence/profiles`, `/api/v1/planes/{id}/{physical|mental|spiritual|conscious|anima|all}`,
  `/api/v1/thermodynamics/{id}`, `/api/v1/silence/{id}`,
  `/api/v1/predictive_limit`, `/api/v1/sigma/{id}`, `/api/v1/validator/hhi`,
  `/api/v1/validator_hhi` (alias), `/api/v1/validators` (alias),
  `/api/v1/dw_bft`, `/api/v1/annotation/{id}`, `/api/v1/bootstrap/status`,
  `/api/v1/anima/intelligence`, `/api/v1/anima/{id}`,
  `/api/v1/security/{id}/mf`, `/api/v1/security/{id}/genomic`,
  `/api/v1/immune/{id}`, `/api/v1/living_index/{id}`, `/api/v1/mev/{id}`,
  `/api/v1/attacks`, `/api/v1/demo/simulate_attack`, `/api/v1/demo/stats`,
  `/api/v1/audit/patterns`, `/api/v1/governance/{init|awa|geo|ceremony|gratitude|slashing/conditions|unknown_provision}`,
  `/api/v1/love/global`, `/api/v1/falsifiability`, `/api/v1/vision`,
  `/api/v1/trion/vision`, `/api/v1/phases`, `/api/v1/phase_transition`,
  `/api/v1/order_parameter`, `/api/v1/convergence`, `/api/v1/akashic/epigenetics/{id}`,
  `/api/v1/fork_resolution/{id}`, `/api/v1/resurrection/{id}`,
  `/api/v1/trajectory{,_anomaly}/{id}`, `/api/v1/dormancy/{id}`,
  `/api/v1/genesis{,/fingerprint}/{id}`, `/api/v1/manifestation_gap/{id}`,
  `/api/v1/negative_space/{id}`, `/api/v1/emergence/{id}`,
  `/api/v1/price/{pairs,hierarchy}`, `/api/v1/inverted_price_feed`,
  `/api/v1/liquidity/{asset}`, `/api/v1/stablecoin_health/{asset}`,
  `/api/v1/sba/{nation}`, `/api/v1/ubl/schema`, `/api/v1/bc/evm`,
  `/api/v1/xsl/{id}`, `/api/v1/transduction/sensor_1`, `/api/v1/inversion`,
  `/api/v1/information/conservation`, `/api/v1/phase_signal`,
  `/api/v1/btcp/{pipeline_status,modules,escrow_states,integration_status,streamer/status,bibl/snapshot,mainnet_bootstrap}`,
  `/api/v1/btcp/route` (POST ×3 pages), `/api/v1/btcp/hash_dna` (POST),
  `/api/v1/continuum/engines`, `/api/v1/zg/{full_stack,storage/root,da/status,compute/status,chain/status,proof,vm-families}`,
  `/api/v1/chains`, `/api/v1/tsdb/stats`, `/api/v1/kv/status`,
  `/api/v1/backfill/status`, `/api/v1/relayers/status`,
  `/api/v1/dependency_graph`, `/api/v1/sdk/spec`,
  `/api/v1/token/{utility,distribution}`, `/api/v1/trion/revenue`,
  `/api/v1/agents`, `/api/v1/agent_id/{id}`, `/api/v1/invest/{id}`,
  `/api/v1/intelligence_maintenance`, `/api/v1/protocol/monitor/status`,
  `/api/v1/protocol/supported-roles`, `/api/v1/self`,
  `/api/v1/reputation{,/leaderboard}`, `/api/v1/cex/{status,feed,alerts,stats}`,
  `/api/v1/gk/{id}`. On-chain: none live (CONTRACTS null).
- Health probes: `healthz`/`readyz` route handlers hit Flask `/api/v1/health`
  and `/readyz` server-side.

**frontend-institutional/** — browser → `/api/trion/*` (same-origin) → proxy →
Flask `/api/v1/*`:

- Overview: `health`, `moat`, `bh/stats`, `bh/recent_feed`, `feed`,
  `love/global`, `validator/hhi`
- Signals: `bh/recent_feed`, `feed`
- BTCP: `btcp/route` (POST), `btcp/streamer/status`,
  `btcp/streamer/start` (POST)
- Chains: `chains`, `bh/vm_feed`
- Coherence: `coherence/profiles`, `feed`, `health`
- Security: `dw_bft`, `validator/hhi`, `feed`
- Governance: `governance/awa`, `love/global`, `falsifiability`
- Primitives: `btcp/hash_dna` (POST), `bh/v2/extended` (POST), `bh/stats`, `feed`
- Explorer: `bh/recent_feed`, `bh/stats`, `bh/vm_feed`, `bh/{tx_hash}`
- Shell: `health` (5s)

All 20 distinct paths verified to exist in `api/app.py` /
`api/btcp_continuum_routes.py` (btcp blueprint). This is the cleanest API
surface in the repo — no orphan endpoints, no spelling drift (the legacy app's
`validator_hhi` alias problem doesn't arise).

**sdk/** — direct fetch to user base URL:

- TrionSDK.ts: `/api/v1/signal/{id}`, `/api/v1/health`, **`/api/btcp/route/{hash}` (GET —
  only the POST `/api/v1/btcp/route` exists)**, **`/api/btcp/bitp/clipboard` (does not
  exist)**, **`/api/btcp/sanctions/{addr}` (does not exist)**
- client.ts: `/api/v1/signal/{id}?profile=`, `/api/v1/planes/{id}/all|physical`,
  `/api/v1/security/check` (POST), `/api/v1/liquidity/{addr}`,
  `/api/v1/btcp/score` (POST), **`/health` (does not exist)**,
  `/api/v1/system/{bootstrap,falsifiability}`, `/api/v1/index/vm-status`,
  `/api/v1/trading/{signal/{id},agent/decide,patterns,scan/{chain}}`
- trion.ts: signal + `/api/v1/signal/{id}/history` + `/api/v1/signal/batch`
  (POST), 6 plane getters, `/api/v1/security/check` (POST, different body),
  `/api/v1/security/{id}/mf`, `/api/v1/security/crispr/library`,
  `/api/v1/liquidity/{addr}`, `/api/v1/btcp/score` (POST),
  `/api/v1/system/{status,bootstrap,falsifiability}`, **`/health` (does not
  exist)**
- trion_sdk.py: 25+ methods, all verified to exist (including `/api/v1/bh`
  POST, `/api/v1/signal/type/{t}/{id}`, `/api/v1/trion/{id}`,
  `/api/v1/living_index/{id}`, `/api/v1/universal_asset/{chain}/{addr}`)
  except the response-key mismatch on `bh/ledger`.

---

## UI/code quality assessment

**frontend/ (legacy)** — 6.5/10. Genuinely good React craftsmanship in the
shell (command palette, error boundaries, dedup' stream hook, accessible
dialogs, theme FOUC guard, responsive typography), but the 134-page content
layer is a mix of live KV pages, static marketing pages, fabricated fallbacks
(F1–F9 ramp, HHI 1482, LSS 100%), duplicated embedded data constants
(BTCP_DATA defined 3×, CONTINUUM_DATA 3×), symbol-scrubbing artifacts visible
in titles ("Economic Moat Economic Moat"), dead wallet integration, and broken
internal links. TypeScript is loose (`any` everywhere in views; strict off).
No tests, no storybook, one ErrorBoundary. The July-2026-audit comments
scattered through the code (dedup fix, alert→dialog, Math.random→real router,
hook consolidation) show real iteration on quality debt.

**frontend-institutional/** — 8/10 as a UI, 6.5/10 as engineering. The visual
system is the best in the repo (terminal palette, consistent spacing, animated
flow diagrams, radar/gauge/meter/sparkline primitives, honest "static
reference" badges, reduced-motion support, aria coverage). The data layer is
clean (one proxy, one typed client, one polling hook — no scattered fetches).
Engineering debt: `ignoreBuildErrors: true`, dead v3 tailwind config importing
an absent package, duplicated MetricCard/KV helpers per view (copy-paste ×5),
external CDN favicon, hardcoded 174-chain marketing, UTC-mislabeled clock, no
error boundaries, no tests, no CI. The BTCP simulator + Hash Lab +
Explorer row-detail are legitimately interactive products, not mockups.

**sdk/** — 7/10 concept, 4/10 execution. The type design (discriminated
SILENCE/VALUATION, packed-signal BigInt, local BH verify) is thoughtful; the
Python client is genuinely usable; but the TS side ships four overlapping
files (two byte-identical, one drifted), a WASM integration that cannot work,
three non-existent endpoints, a fail-open sanctions check, an auth header that
doesn't match the backend, and inconsistent default hosts (onrender.com vs
replit.app vs localhost). No package.json at sdk/ root; no dist; no tests
despite a jest script.

---

## Bugs / issues / inconsistencies (file:line)

### frontend/

1. **Invalid contract addresses** — `src/views/spec_pages.tsx:170-172`:
   `0x714Ea58861F3e4221f83f9e0a3e682Ba4be682Ba4b` (44 hex), `0xf4420893A27a5B6F9e8D7c3E5b9A6Dc6D4` (34),
   `0xdbd3C2f67A9eD118F9c8e7aE4B4c4a446D00E` (38). None is a valid 20-byte
   address; the whole "BOT Chain LIVE contracts" card is fabricated (incl.
   metrics at :174-178 and future dates "Aug 12, 2026" at :180-186).
2. **Broken in-app links** — `spec_pages.tsx:357,469,592` (`href="/continuum"`,
   `/btcp`) and `overview.tsx:220` (`/explorer?entity=…`): the SPA only serves
   `/?page=…`; these CTAs 404.
3. **Mislabeled Master Equation** — `overview.tsx:140-149`:
   `const C = health?.dynamic_threshold || 0.5` — threshold used as coherence in
   the T(t) display (and "Coherence" row at :149 shows the threshold).
4. **Fabricated plane features** — `planes.tsx:74`: `|| (0.1 + i * 0.08)`
   fallback renders synthetic F1–F9 values as if measured.
5. **Hardcoded "verified" crypto** — `security.tsx:38-45,258-261`: LSS 100%,
   PQC 90%, "Kyber/Dilithium/SPHINCS+ round-trip: verified" are static strings,
   not API data.
6. **Hardcoded pipeline health** — `overview.tsx:353-361`: 8 stages all
   `status:'OK'` (no API), rendered with green checks under "Verified live data
   flows".
7. **Hardcoded HHI fallback & sybil sim** — `governance.tsx:508`
   (`hhi?.hhi ?? 1482`), `:515-516` (75.8% / 0.0% constants presented as a
   simulation).
8. **Local time labeled UTC** — `components/ui.tsx:810` (LiveClock), same class
   of bug as institutional TopBar.
9. **Dynamic Tailwind class** — `security.tsx:301`: `` text-${t.color}-500 ``
   is never emitted by Tailwind's JIT → color silently missing.
10. **Header/cell mismatch** — `btcp_continuum.tsx:344-352`: 5 headers
    (incl. 'Formula') vs 4-cell rows in ContinuumEnginesPage table.
11. **Hardcoded marketing stats** — `btcp_continuum.tsx:25-26` ("6/6", "18",
    "100%"), `infrastructure.tsx:318` ("VM Families 14"),
    `behavioral.tsx:32-33` (fallbacks 14/57), `layout.tsx:28,46,54` +
    `page.tsx:691` ("128 chains · 18 VM families" vs backend 160/22 vs
    institutional 174/22) — at least four mutually inconsistent chain counts
    across the two frontends.
12. **All on-chain contracts null** — `config/wagmi.ts:29-55`: every CONTRACTS
    entry null; wallet writes (`useContracts.ts`) can never execute;
    `useTRIONExecutionGate` (`useContracts.ts:181-183`) hardcodes 0G chain
    16661 gate address — inconsistent with the Arbitrum-Sepolia narrative.
13. **Dead export** — `lib/hooks.ts:205` `useWebSocket` never imported; its
    doc comment ("Default interval: 50ms") contradicts the code (2000 ms at
    `:76`).
14. **Side-effectful GET polling** — `infrastructure.tsx:413,783` poll
    `/api/v1/demo/simulate_attack` (a simulator endpoint) every 30 s via GET.
15. **`dw_bft` double-listed** — `Sidebar.tsx:88,153` (Governance + Validators
    groups both navigate to the same page); 10 primitives pages are
    PAGE_MAP-only orphans (comment at `Sidebar.tsx:144-147`).
16. **`cleanText` produces duplicated labels** — `lib/api.ts:166-199` replaces
    Greek with English but callers pre-concatenated both, e.g.
    `overview.tsx:124` "Market Volatility Market Volatility",
    `overview.tsx:243` "Economic Moat Economic Moat = D - Q - R - X - F - N",
    `planes.tsx:275` "Akashic Depth Behavioral Depth",
    `security.tsx:31` "SECoherence = LSS - PQC - CC",
    `ui_assessment.tsx:296,322` "Oracle Coherence Coherence" /
    "Information Information Flow", `infrastructure.tsx:125` (also mixed ·/−).
17. **tsbuildinfo committed** — `frontend/tsconfig.tsbuildinfo` (548 KB) is
    tracked while frontend-institutional's `.gitignore` excludes it.
18. **AWA condition count mismatch** — legacy `governance.tsx:24` counts
    "/4", institutional `GovernanceView.tsx:92-106` lists 8 conditions.
19. **useMultiAPI deps** — `lib/hooks.ts:68` uses `JSON.stringify(paths)` as
    effect dep (identity churn; harmless but lint-flaggable).

### frontend-institutional/

20. **174 vs 160 chains** — hardcoded in `src/app/page.tsx:100,116` (footer
    ticker), `shell/Sidebar.tsx:131` (footer badge) & `:29` (blurb),
    `src/app/layout.tsx:18,36` (metadata), `views/OverviewView.tsx:92,207`,
    `views/ChainsView.tsx:469`, `views/ExplorerView.tsx:210`; while
    `ChainsView` itself renders `chains.length` = **160** (executed
    `api.chains_registry.get_all_chains()` → 160 chains, 22 VMs, 94 live, 23
    testnet, 43 indexed) and the README's own view table says "160 unique ·
    22 VMs".
21. **UTC clock bug** — `shell/TopBar.tsx:92-94`: `toLocaleTimeString("en-GB",
    { hour12: false })` with no `timeZone` → local time labeled "UTC" (same in
    every view's "updated" stamps).
22. **Silent numeric placeholders contradict "no placeholders"** —
    `views/OverviewView.tsx:109-118` (planes `0.55/0.5/0.6/0.5/0.45`,
    `coherence ?? 0.6`, `threshold ?? 0.55`), `views/CoherenceView.tsx:43-54`
    (same + BALANCED weight fallback) — when Flask is down the views render
    plausible-looking numbers with no "offline" marker on the affected widgets
    (only the TopBar shows "backend offline").
23. **Synthetic sparkline** — `views/OverviewView.tsx:127-131`: `bhTrend`
    fabricates `[total-900, total-700, …, total]` — a fake upward ramp labeled
    as a trend.
24. **Dead import** — `views/OverviewView.tsx:14` (`trionPost` imported, never
    used).
25. **External favicon** — `src/app/layout.tsx:31`: icon =
    `https://z-cdn.chatglm.cn/z-ai/static/logo.svg` (ChatGLM CDN), not the
    TRION logo.
26. **Type errors suppressed** — `next.config.ts:7-8`
    (`typescript.ignoreBuildErrors: true`) + `reactStrictMode: false`;
    `tsconfig.json` `noImplicitAny: false`.
27. **Broken tailwind config** — `tailwind.config.ts:2` imports
    `tailwindcss-animate` (not in package.json; the actual dep is
    `tw-animate-css`); v3-style config unused under Tailwind v4 — would throw
    if any tooling loads it.
28. **Proxy has no allowlist** — `src/app/api/trion/[...path]/route.ts:23`
    comment promises blocking "private metadata endpoints" but no filtering
    exists; any `/api/v1/*` path is forwarded.
29. **Copypasta helpers** — `MetricCard`/`KV`/`Stat` redefined in
    OverviewView/ChainsView/ExplorerView/SignalsView (drift risk).
30. **"BEO Entity Resolution" overstated** — `views/ExplorerView.tsx:141-157`:
    client-side `groupBy(entity_id)` over the last ~100 feed records is
    presented as BEO resolution (CF/ST/SC/BP formula banner at :339-342).
31. **BTCP simulator inputs partly static** — `views/BtcpView.tsx:75-77`:
    CC/finality/validator counts are constants, not from `btcp/bibl/snapshot`
    (which the legacy app does use).
32. **useTrionPoll deps spread** — `lib/trion/hooks.ts:55` spreads a variadic
    `deps` array into the effect dep list (unstable length).

### sdk/

33. **WASM API mismatch (verified empirically)** — `TrionSDK.ts:691,713` call
    `wasm.exports.compute_coherence` and `wasm.exports.shannon_entropy`;
    instantiating `src/wasm/signal_processor.wasm` shows exports are
    `compute_threshold, signal_emits, is_silence_type, is_valuation_type,
    apply_mf_correction, compute_pc_limit, brt_*, signal_type_count,
    is_extended_signal` — **neither function exists**, and the module does not
    export `memory` (`.wat:58` `(memory 1)` unexported), so `computeEntropyWasm`
    (`:706`) would also fail. `verifyCoherenceWasm`/`computeEntropyWasm` throw
    TypeError at runtime.
34. **WASM default path wrong** — `TrionSDK.ts:650-652` resolves
    `./wasm/signal_processor.wasm` relative to sdk root (file lives at
    `sdk/src/wasm/`); `src/index.ts` (where the relative path would be correct)
    had its WASM section deleted. 404 by default either way.
35. **Nonexistent endpoints** — `TrionSDK.ts:442` GET
    `/api/btcp/route/{intentHash}` (backend only has POST `/api/v1/btcp/route`),
    `:460` `/api/btcp/bitp/clipboard`, `:477` `/api/btcp/sanctions/{addr}`
    (none exist in api/); `client.ts:264` and `trion.ts:255` call `/health`
    (Flask has `/api/v1/health` + `/readyz` only).
36. **Fail-open sanctions check** — `TrionSDK.ts:479-483`: on error returns
    `{sanctioned:false, confidence:1}` — a compliance check that silently
    passes when unreachable.
37. **Auth header mismatch** — `trion.ts:133` sends `X-TRION-API-Key`; backend
    (`api/app.py:155`) requires `X-API-Key` (which the legacy frontend
    correctly uses).
38. **Wrong response key** — `trion_sdk.py:357` reads `data.get("entries")`
    from `/api/v1/bh/ledger/{id}`; the endpoint returns `bh_records` → always
    `[]`. (Legacy `ui_assessment.tsx:113` reads `.records` — also wrong.)
39. **Byte-duplicated files** — `src/trion-sdk.ts` == `src/client.ts`
    (verified diff); `src/index.ts` == `TrionSDK.ts` minus WASM (verified
    diff) — three parallel "the SDK" with different endpoints/taxonomies:
    19 signal types (client.ts) vs 14+11 BTCP (TrionSDK.ts) vs 24 (wasm) vs 19
    (trion_sdk.py).
40. **Unbuildable package** — `src/package.json` main `dist/trion.js` with no
    dist, no tsconfig, `test: jest` with no jest config/tests; no package.json
   at `sdk/` root for `TrionSDK.ts`.
41. **`security/check` body shape conflict** — `client.ts:232-239` posts
    `{entity_id, asset_address, amount, is_flash_loan}` while `trion.ts:210-214`
    posts `{tx_data}` to the same URL — at most one matches the handler.
42. **verify_signal strictness** — `trion_sdk.py:504-505` requires
    `genomic_signature` of exactly 128 hex chars; current signal payloads
    generally lack this field → verification returns False for valid signals.
43. **Stale hosts** — `client.ts:180`
    (`https://trion-protocol.onrender.com`), `trion.ts:7`
    (`trion-protocol.replit.app`) — neither is the documented deployment.
44. **normalizeEntityId pads with zeros** — `TrionSDK.ts:336-339`: `padEnd(42,
    '0')` silently corrupts short/non-address entity IDs (e.g. "uniswap"
    → "0xuniswap000…").

Cross-cutting consistency note (positive): the WASM Θ formula
(`0.55 + 0.37·V`) matches Flask's `dynamic_threshold` computation exactly, and
the 20-event-type list matches `PrimitivesView.EVENT_WEIGHTS` — the layers that
*do* line up line up precisely.

---

## Claims vs reality

| Claim (where) | Reality (evidence) |
|---|---|
| "wired live … no mock data, no placeholders" (frontend-institutional/README:5) | **Mostly true**: all 9 views poll 20 real Flask endpoints (all verified present); interactive POSTs (btcp/route, btcp/hash_dna, bh/v2/extended, streamer/start) hit real handlers; static panels are honestly labeled "static protocol reference". **But**: silent numeric fallbacks (planes 0.55/0.5/0.6/0.5/0.45, C 0.6, Θ 0.55) render when backend is down (OverviewView:109-118, CoherenceView:43-54), a synthetic BH "trend" sparkline (OverviewView:127-131), and BTCP simulator CC/finality/validator inputs are constants (BtcpView:75-77). "No placeholders" is overstated; "no mock data" holds for anything fetched. |
| "9 hash-routed views … all live" | TRUE — overview/signals/btcp/chains/coherence/security/governance/primitives/explorer all exist, all data panels poll real endpoints; nothing in VIEW_MAP is a stub. |
| "174 chains · 22 VM families" (footer, sidebar, metadata, README:29,46) | **FALSE** — `/api/v1/chains` (executed locally) returns **160 chains / 22 VMs** (94 live, 23 testnet, 43 indexed); the ChainsView's own live counter shows 160 next to hardcoded "174" copy. |
| "Backend runs on :5000 with 271 routes" (README:10) vs "238 routes" (frontend/README:21) | Inconsistent route-count claims (agent 2-f counted 180 @app.route + 86 blueprint); neither 238 nor 271 matches a single inventory. |
| legacy layout metadata "128 chains and 18 VM families" | Contradicted by backend registry (160/22), by the same app's hardcoded "VM Families 14" (infrastructure.tsx:318) and vm_feed fallbacks (14/57), and by the institutional app (174/22). |
| "BOT Chain … 3 Core Contracts LIVE" (spec_pages.tsx:504) | Fabricated: contract addresses are invalid hex (44/34/38 chars), metrics hardcoded, dates in the future (Aug 2026). No on-chain wiring exists anywhere in the frontend (CONTRACTS all null). |
| "Pipeline Connectivity Check … Verified live data flows" (overview.tsx:351) | 8 hardcoded `OK` badges, no API behind them. |
| PQC "round-trip verified" (security.tsx:258-261) | Static strings; agent 2-a found the PQC self-test suite actually fails 1/105 without optional deps — the UI asserts more than the backend proves. |
| SDK "Complete TypeScript client for all TRION API endpoints" (client.ts:3) | 3 of its endpoints don't exist (`/health`, and TrionSDK's btcp GET/sanctions/clipboard); auth header mismatches; `/api/v1/index/vm-status` + `/api/v1/system/*` + trading layer unverified in my scope (agent 2-f's inventory is authoritative). |
| WASM "browser-side signal processing … companion SDK (chains/*/execute.ts) imports these exports" (signal_processor.wat:5,13) | No consumer anywhere; and the TS WASM wrapper calls exports that don't exist — the integration has never run. |
| "Live data: Auto-refreshes every 10 seconds" (frontend/README:61) | Intervals actually range 2 s–60 s across views (3–5 s typical for streams). |
| healthz "Returns 200 if … can reach the Flask API" | Correct behavior as implemented (always 200 + flask_ok flag) — honest. |
| institutional "BTCP Zero-Bridge K1 route simulator" | **Real**: POST `/api/v1/btcp/route` with editable per-chain NL/MF/gas and 3 presets; backend computes the score and can fail closed (adversarial preset). The route *inputs* partially reference constants, but the K1 scoring is genuinely server-side. |

---

## Next actions (for the main agent)

1. Fold the **chain-count matrix** into the master claims audit: 160 (live
   registry) vs 174 (institutional UI copy) vs 128/18 (legacy metadata) vs
   14/57 (legacy fallbacks) vs 96/124/56/35/31 (docs, per 2-b/2-g/2-i).
2. Treat the SDK as **non-functional for its two flagship features**: WASM
   verification (missing exports + wrong path) and BTCP/sanctions fetchers
   (nonexistent endpoints, fail-open sanctions). If the SDK is a claimed
   deliverable, this is a gap; if it's aspirational, the READMEs
   over-promise.
3. frontend-institutional is the credible UI: recommend the merged report use
   it (not the legacy app) when describing "the frontend", while noting the
   174-chain hardcode and the ignoreBuildErrors config.
4. Cross-check with 2-f: the ~60 synthetic Flask endpoints (leaderboard,
   attacks, demo) are exactly the endpoints the legacy views display with
   "live" badges — the frontends are honest *transport-wise* but inherit the
   backend's synthetic data (not a frontend bug per se).
5. If anyone intends to run the institutional app: `bun install`, `python3
   serve.py`, set `TRION_BACKEND_URL`; note the proxy has no path allowlist
   despite its comment.
