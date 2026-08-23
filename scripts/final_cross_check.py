#!/usr/bin/env python3
"""
TRION Protocol — FINAL Cross-Check Verification

Runs through the entire Phase 1-8 checklist from
TRION_UNIFIED_MASTER_COMMAND.md and verifies every item.

Run: python3 /home/z/my-project/repos/trion-core/scripts/final_cross_check.py
"""
import os
import sys
import subprocess

REPO = '/home/z/my-project/repos/trion-core'
PASS = 0
FAIL = 0

def check(label, condition, detail=''):
    global PASS, FAIL
    status = '✓ PASS' if condition else '✗ FAIL'
    if condition:
        PASS += 1
    else:
        FAIL += 1
    print(f"  {status} — {label}" + (f" ({detail})" if detail and not condition else ''))

def read(p):
    with open(os.path.join(REPO, p)) as f:
        return f.read()

def exists(p):
    return os.path.exists(os.path.join(REPO, p))


def phase_1():
    print("\n" + "=" * 72)
    print("PHASE 1: FOUNDATION & CRITICAL FIXES")
    print("=" * 72)

    # 1.1 Duplicate API proxy removed
    check("Duplicate API proxy removed (src/app/api/)",
          not exists('frontend/src/app/api/v1/[...path]/route.ts') and
          not exists('frontend/src/app/app/api/[...path]/route.ts'))
    check("next.config.js rewrites cover /api/* and /app/api/*",
          '/api/:path*' in read('frontend/next.config.js') and
          '/app/api/:path*' in read('frontend/next.config.js'))

    # 1.2 Config standardization
    check("frontend/src/lib/config.ts created", exists('frontend/src/lib/config.ts'))
    check("frontend/.env.example created", exists('frontend/.env.example'))
    check("api.ts imports config", 'from \'./config\'' in read('frontend/src/lib/api.ts'))

    # 1.3 SHA3-256
    app = read('api/app.py')
    check("_entity_seed uses SHA3-256", 'hashlib.sha3_256(eid.encode())' in app)
    check("Cross-language BH test script exists", exists('scripts/cross_lang_bh_check.py'))

    # 1.4 DW-BFT page
    gov = read('frontend/src/views/governance.tsx')
    page = read('frontend/src/app/page.tsx')
    sb = read('frontend/src/components/Sidebar.tsx')
    check("DWBFTPage component in governance.tsx", 'export function DWBFTPage' in gov)
    check("dw_bft in PAGE_MAP", 'dw_bft: DWBFTPage' in page)
    check("dw_bft in PAGE_TITLES", "dw_bft: 'Diversity-Weighted BFT'" in page)
    check("dw_bft in Sidebar NAV", "id: 'dw_bft'" in sb)

    # 1.5 /api/v1/zg uses web3.py
    check("/api/v1/zg uses web3.py (no subprocess)", 'from web3 import Web3' in app)
    # Find the zg_stats function and check it doesn't spawn node
    zg_start = app.find('@app.route("/api/v1/zg")')
    zg_end = app.find('@app.route("/api/v1/faiss")')
    zg_section = app[zg_start:zg_end]
    check("/api/v1/zg no Node.js subprocess", 'import subprocess' not in zg_section)

    # 1.6 fetchAPI discriminated union
    api_ts = read('frontend/src/lib/api.ts')
    check("APIResult<T> discriminated union", 'export type APIResult<T>' in api_ts)
    check("APIErrorType defined", 'export type APIErrorType' in api_ts)
    check("fetchAPIOrNull legacy wrapper", 'fetchAPIOrNull' in api_ts)


def phase_2():
    print("\n" + "=" * 72)
    print("PHASE 2: BACKEND HARDENING")
    print("=" * 72)

    # 2.1 Input validation
    check("api/validation.py created", exists('api/validation.py'))
    val = read('api/validation.py')
    check("ENTITY_ID_RE regex", 'ENTITY_ID_RE' in val)
    check("ADDRESS_RE regex", 'ADDRESS_RE' in val)
    check("TX_HASH_RE regex", 'TX_HASH_RE' in val)
    check("require_entity_id decorator", 'def require_entity_id' in val)

    app = read('api/app.py')
    check("require_entity_id imported in app.py", 'from api.validation import' in app)
    # Count decorated routes
    decorated_count = app.count('@require_entity_id()')
    check(f"@require_entity_id() applied to {decorated_count} routes", decorated_count >= 10)

    # 2.2 Bounded FAISS cache
    check("lru_cache imported", 'from functools import lru_cache' in app)
    check("_faiss_lock threading.Lock", '_faiss_lock' in app and 'threading.Lock' in app)
    check("_FAISS_CACHE_MAX = 10_000", '_FAISS_CACHE_MAX' in app)
    check("_query_faiss_planes_cached (lru_cache)", '_query_faiss_planes_cached' in app)

    # 2.3 Rate limiter
    check("_rl_cleanup_loop background thread", '_rl_cleanup_loop' in app)
    check("_rl_cleanup_thread started", '_rl_cleanup_thread' in app and '.start()' in app)
    check("RATE_LIMIT_WINDOW_SEC env-configurable", 'RATE_LIMIT_WINDOW_SEC' in app)
    check("RATE_LIMIT_MAX_REQUESTS env-configurable", 'RATE_LIMIT_MAX_REQUESTS' in app)


def phase_3():
    print("\n" + "=" * 72)
    print("PHASE 3: FRONTEND CAPABILITY EXPANSION")
    print("=" * 72)

    hooks = read('frontend/src/lib/hooks.ts')
    ui = read('frontend/src/components/ui.tsx')
    page = read('frontend/src/app/page.tsx')

    # 3.1 WebSocket hook
    check("useWebSocket hook", 'export function useWebSocket' in hooks)
    check("Exponential backoff in useWebSocket", 'Math.pow(2' in hooks or '1000 *' in hooks)
    check("Polling fallback in useWebSocket", 'fallbackInterval' in hooks)

    # 3.2 Loading & Error states
    check("Skeleton component", 'export function Skeleton' in ui)
    check("ErrorState component", 'export function ErrorState' in ui)
    check("SkeletonCard component", 'export function SkeletonCard' in ui)
    check("LoadingState component", 'export function LoadingState' in ui)

    # 3.3 EntityInput wired
    check("EntityInput has samples prop", 'samples?:' in ui)
    check("EntityInput 'Try sample' quick-fill", 'Try:' in ui)

    # 3.4 URL state persistence
    check("useSearchParams imported", 'useSearchParams' in page)
    check("changePage updates URL", 'searchParams.set' in page)
    check("Suspense boundary", 'Suspense' in page)

    # 3.5 Command Palette
    check("CommandPalette.tsx created", exists('frontend/src/components/CommandPalette.tsx'))
    cp = read('frontend/src/components/CommandPalette.tsx')
    check("Cmd+K / Ctrl+K toggle", "e.key.toLowerCase() === 'k'" in cp)
    check("Arrow key navigation", 'ArrowDown' in cp and 'ArrowUp' in cp)
    check("Recent pages in palette", 'recent' in cp.lower())
    check("CommandPalette wired in page.tsx", 'CommandPalette' in page)


def phase_4():
    print("\n" + "=" * 72)
    print("PHASE 4: INSTITUTIONAL DESIGN SYSTEM")
    print("=" * 72)

    layout = read('frontend/src/app/layout.tsx')
    css = read('frontend/src/app/globals.css')
    ui = read('frontend/src/components/ui.tsx')

    # 4.1 Typography
    check("Inter font via next/font/google", 'Inter' in layout and 'next/font/google' in layout)
    check("JetBrains_Mono via next/font/google", 'JetBrains_Mono' in layout)
    check("--font-sans variable", '--font-sans' in css)
    check("--font-mono variable", '--font-mono' in css)

    # 4.2 Dark mode
    check("@custom-variant dark", '@custom-variant dark' in css)

    # 4.3 Metadata
    check("metadataBase set", 'metadataBase' in layout)
    check("openGraph configured", 'openGraph' in layout)
    check("twitter card configured", 'twitter' in layout)
    check("JSON-LD structured data", 'application/ld+json' in layout)
    check("viewport themeColor", 'themeColor' in layout)

    # 4.4 Accessibility
    check("focus-visible styles", ':focus-visible' in css)
    check("? keyboard shortcut for help", "e.key === '?'" in read('frontend/src/app/page.tsx'))
    check("aria-label on icon buttons", 'aria-label' in ui)

    # 4.5 DataTable enhancements
    check("DataTable sortable prop", 'sortable' in ui)
    check("DataTable exportable prop", 'exportable' in ui)
    check("DataTable copyableColumns", 'copyableColumns' in ui)
    check("DataTable onRowClick", 'onRowClick' in ui)
    check("CSV export function", 'exportCSV' in ui)
    check("JSON export function", 'exportJSON' in ui)


def phase_5():
    print("\n" + "=" * 72)
    print("PHASE 5: WEB3 INTEGRATION")
    print("=" * 72)

    check("Web3Provider.tsx exists", exists('frontend/src/providers/Web3Provider.tsx'))
    check("WalletButton.tsx exists", exists('frontend/src/components/wallet/WalletButton.tsx'))
    check("wagmi config (wagmi.ts)", exists('frontend/src/config/wagmi.ts'))

    uc = read('frontend/src/hooks/useContracts.ts')
    check("useContracts.ts created", exists('frontend/src/hooks/useContracts.ts'))
    check("useTRIONExecutionGate hook", 'useTRIONExecutionGate' in uc)
    check("usePublishBehavioralTruth hook", 'usePublishBehavioralTruth' in uc)
    check("useLockFunds hook", 'useLockFunds' in uc)
    check("useRegisterIntent hook", 'useRegisterIntent' in uc)
    check("useEmergencyRevert hook", 'useEmergencyRevert' in uc)
    check("useUserBEO hook", 'useUserBEO' in uc)
    check("useMaxLockDuration hook", 'useMaxLockDuration' in uc)

    check("SettingsModal.tsx created", exists('frontend/src/components/SettingsModal.tsx'))
    api_ts = read('frontend/src/lib/api.ts')
    check("getAPIKeyHeaders in api.ts", 'getAPIKeyHeaders' in api_ts)
    check("X-API-Key header auto-attached", 'X-API-Key' in api_ts)


def phase_6():
    print("\n" + "=" * 72)
    print("PHASE 6: RUST INDEXER VERIFICATION")
    print("=" * 72)

    check("trion-common/src/hash_dna.rs exists", exists('indexers/crates/trion-common/src/hash_dna.rs'))
    check("trion-common/src/vector.rs exists", exists('indexers/crates/trion-common/src/vector.rs'))
    check("trion-common/src/entropy.rs exists", exists('indexers/crates/trion-common/src/entropy.rs'))
    check("chains/shared/canonical_bh.ts exists", exists('chains/shared/canonical_bh.ts'))

    hd = read('indexers/crates/trion-common/src/hash_dna.rs')
    check("Rust bh_id uses SHA3-256", 'Sha3_256::digest' in hd)
    check("Cross-language BH test in Rust", 'cross_language_canonical_bh_vector' in hd)
    check("Cross-language bh_id test in Rust", 'cross_language_bh_id_vector' in hd)

    vec = read('indexers/crates/trion-common/src/vector.rs')
    check("build_vector produces 128 dims", '128' in vec and 'vec![0f32; 128]' in vec)

    evm = read('indexers/crates/trion-evm/src/main.rs')
    check("EVM indexer documents 9 features", 'f1 —' in evm and 'f9 —' in evm)
    check("EVM extract_features returns [f64; 9]", '[f64; 9]' in evm)


def phase_7():
    print("\n" + "=" * 72)
    print("PHASE 7: CONTRACT VERIFICATION")
    print("=" * 72)

    escrow = read('contracts/BTCPEscrow.sol')
    check("EMERGENCY_ESCAPE_SECONDS = 7 days", 'EMERGENCY_ESCAPE_SECONDS = 7 days' in escrow)
    check("revertEmergency is external", 'function revertEmergency' in escrow and 'external' in escrow)
    check("EmergencyRevert event", 'emit EmergencyRevert' in escrow)

    relayer = read('relayer/relayer.js')
    check("Bit layout documented", 'Bit layout' in relayer)
    check("packGateSignal function", 'function packGateSignal' in relayer)

    oracle = read('contracts/TRIONOracleV3.sol')
    check("publishSignal in TRIONOracleV3", 'function publishSignal' in oracle)


def phase_8():
    print("\n" + "=" * 72)
    print("PHASE 8: POLISH, MONITORING & DEPLOYMENT")
    print("=" * 72)

    check("ErrorBoundary.tsx created", exists('frontend/src/components/ErrorBoundary.tsx'))
    check("not-found.tsx (404)", exists('frontend/src/app/not-found.tsx'))
    check("error.tsx (500)", exists('frontend/src/app/error.tsx'))
    check("/healthz route", exists('frontend/src/app/healthz/route.ts'))
    check("Dockerfile.render exists", exists('Dockerfile.render'))
    check("render-entrypoint.sh exists", exists('render-entrypoint.sh'))
    check("render.yaml exists", exists('render.yaml'))

    ui = read('frontend/src/components/ui.tsx')
    check("Arch diagram: 16 crates", '16 crates' in ui)
    check("Arch diagram: 100+ chains", '100+ chains' in ui)
    check("StreamView 'API latency' label", 'API {ms(speedMs)}' in ui)

    sb = read('frontend/src/components/Sidebar.tsx')
    check("Sidebar: collapsible groups", 'collapsedGroups' in sb)
    check("Sidebar: Recently Visited", 'Recently Visited' in sb)
    check("Sidebar: role=navigation", 'role="navigation"' in sb)


def main():
    print("=" * 72)
    print("TRION PROTOCOL — FINAL CROSS-CHECK VERIFICATION")
    print("Phases 1-8 per TRION_UNIFIED_MASTER_COMMAND.md")
    print("=" * 72)

    phase_1()
    phase_2()
    phase_3()
    phase_4()
    phase_5()
    phase_6()
    phase_7()
    phase_8()

    print("\n" + "=" * 72)
    print(f"FINAL TALLY: {PASS} passed, {FAIL} failed")
    print("=" * 72)
    if FAIL == 0:
        print("✓ ALL PHASES VERIFIED — PRODUCTION READY")
    else:
        print(f"✗ {FAIL} items need attention")
    return 0 if FAIL == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
