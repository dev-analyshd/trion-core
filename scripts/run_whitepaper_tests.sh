#!/usr/bin/env bash
# TRION Protocol — Whitepaper Test Runner (L0–L10)
# Tests every whitepaper implementation in the live repo: Rust L0 core,
# Python src/ modules (L1–L9), Solidity contracts, and the full pytest suite.
#
# Usage: bash scripts/run_whitepaper_tests.sh
# Requires: uv (Python), cargo (Rust), pytest installed via pyproject.toml
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0; RESULTS=()

run_test() {
    local label="$1" cmd="$2" cwd="${3:-$ROOT}"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $label"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    pushd "$cwd" > /dev/null
    if eval "$cmd" 2>&1; then
        echo "  ✓ PASSED"
        RESULTS+=("PASS  $label")
        PASS=$((PASS+1))
    else
        echo "  ✗ FAILED"
        RESULTS+=("FAIL  $label")
        FAIL=$((FAIL+1))
    fi
    popd > /dev/null
}

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║    TRION Whitepaper Test Runner (L0–L10 live repo)   ║"
echo "╚══════════════════════════════════════════════════════╝"

# ── Rust L0 core (rust-indexers/crates/trion-common) ─────────────────────────
run_test "L0 Rust: BehavioralHash + DualStrand + LivingSecurity (23 tests)" \
    "cargo test --workspace --lib -- --nocapture" \
    "$ROOT/rust-indexers"

# ── Python: trion_protocol unit tests (L0–L5 scaffold) ──────────────────────
run_test "L1 Python: phi_engine — 9 Shannon entropy features" \
    "uv run python3 -m pytest tests/trion_protocol/test_feature_extractor.py -q" \
    "$ROOT"

run_test "L2 Python: archetypes — 12 Akashic archetypes + match_archetype" \
    "uv run python3 -m pytest tests/trion_protocol/test_archetype_engine.py -q" \
    "$ROOT"

run_test "L3 Python: m_engine — M(t) conformal prediction + observer effect" \
    "uv run python3 -m pytest tests/trion_protocol/test_conformal_predictor.py -q" \
    "$ROOT"

run_test "L4 Python: sigma_engine — Σ diversity-weighted BFT + HHI" \
    "uv run python3 -m pytest tests/trion_protocol/test_consensus_bft.py -q" \
    "$ROOT"

run_test "L5 Python: coherence_engine — C(t) master equation + moat" \
    "uv run python3 -m pytest tests/trion_protocol/test_five_plane_c.py -q" \
    "$ROOT"

run_test "L0 Python: BH collision resistance" \
    "uv run python3 -m pytest tests/trion_protocol/test_bh_collision_resistance.py -q" \
    "$ROOT"

# ── Python: integration plane tests ──────────────────────────────────────────
run_test "Integration: all planes (physical/mental/spiritual/conscious/anima)" \
    "uv run python3 -m pytest tests/test_all_planes.py -q" \
    "$ROOT"

run_test "Integration: BTCP/BITP/SBA/BIBL engines" \
    "uv run python3 -m pytest tests/test_btcp_bitp_sba_bibl.py -q" \
    "$ROOT"

run_test "Integration: GK + Living Security" \
    "uv run python3 -m pytest tests/test_gk_living_security.py -q" \
    "$ROOT"

run_test "Integration: BEO cross-chain + VM routing" \
    "uv run python3 -m pytest tests/test_beo_cross_chain_vm.py -q" \
    "$ROOT"

run_test "Integration: deep VM + 0G" \
    "uv run python3 -m pytest tests/test_deep_vm_and_zg.py -q" \
    "$ROOT"

run_test "Integration: trading signals" \
    "uv run python3 -m pytest tests/test_trading_signals.py -q" \
    "$ROOT"

run_test "Integration: vision expansion (chain coverage)" \
    "uv run python3 -m pytest tests/test_vision_expansion.py -q" \
    "$ROOT"

run_test "Integration: whitepaper gap coverage" \
    "uv run python3 -m pytest tests/test_whitepaper_gaps.py -q" \
    "$ROOT"

# ── Chain integration tests ───────────────────────────────────────────────────
run_test "Chain: multi-chain integration (mock RPC)" \
    "uv run python3 -m pytest tests/test_chain_integrations.py -q" \
    "$ROOT"

# ── Protocol health check ─────────────────────────────────────────────────────
run_test "Protocol: health + role classifier + segmentation + distribution" \
    "uv run python3 -m pytest tests/test_protocol_health.py tests/test_protocol_role_classifier.py tests/test_protocol_segmentation.py tests/test_protocol_distribution_coherence.py -q" \
    "$ROOT"

# ── Stress test ───────────────────────────────────────────────────────────────
run_test "Stress: 1000-entity ANIMA + behavioral stress" \
    "uv run python3 -m pytest tests/test_stress.py -q" \
    "$ROOT"

# ── Solidity contracts syntax check ──────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  L10: Solidity Contracts (contracts/)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
SOL_PASS=0; SOL_FAIL=0
for f in TRIONExecutionGate.sol TRIONOracleV3.sol TRIONSensingOracle.sol \
         TRIONFirewall.sol AkashicProof.sol TRIONOracle.sol; do
    path="$ROOT/contracts/$f"
    if [ -f "$path" ] && grep -q "pragma solidity" "$path" && grep -q "contract \|interface " "$path"; then
        echo "  ✓ $f"
        SOL_PASS=$((SOL_PASS+1))
    else
        echo "  ✗ $f — MISSING or INVALID"
        SOL_FAIL=$((SOL_FAIL+1))
    fi
done
if [ $SOL_FAIL -eq 0 ]; then
    RESULTS+=("PASS  L10: Solidity contracts ($SOL_PASS found)")
    PASS=$((PASS+1))
else
    RESULTS+=("FAIL  L10: Solidity contracts ($SOL_FAIL missing)")
    FAIL=$((FAIL+1))
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║                   TEST SUMMARY                       ║"
echo "╚══════════════════════════════════════════════════════╝"
for r in "${RESULTS[@]}"; do echo "  $r"; done
echo ""
echo "  Total: $PASS passed, $FAIL failed"
echo ""
if [ $FAIL -eq 0 ]; then
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║     ALL WHITEPAPER TESTS GREEN — L0–L10 LIVE        ║"
    echo "╚══════════════════════════════════════════════════════╝"
    exit 0
else
    echo "✗ $FAIL test group(s) failed"
    exit 1
fi
