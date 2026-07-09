#!/usr/bin/env bash
# TRION Protocol — WebAssembly Build Script
# Compiles signal_processor.wat → signal_processor.wasm
#
# Requirements:
#   wat2wasm  (part of WABT — WebAssembly Binary Toolkit)
#   wasm-opt  (from Binaryen — optional, for size optimization)
#
# Install on NixOS/Replit:
#   nix-env -iA nixpkgs.wabt nixpkgs.binaryen
#
# Usage:
#   bash wasm/build.sh [--optimize] [--validate]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WAT_FILE="$SCRIPT_DIR/signal_processor.wat"
WASM_OUT="$SCRIPT_DIR/signal_processor.wasm"
WASM_OPT_OUT="$SCRIPT_DIR/signal_processor.opt.wasm"

echo "TRION WebAssembly Build"
echo "─────────────────────────────────────────────"

# ── Step 1: Validate WAT syntax ───────────────────────────────────────────────
if command -v wat2wasm &>/dev/null; then
  echo "  [1/3] Compiling WAT → WASM ..."
  wat2wasm "$WAT_FILE" -o "$WASM_OUT" --enable-all
  echo "        Output: $WASM_OUT ($(wc -c < "$WASM_OUT") bytes)"
else
  echo "  [1/3] wat2wasm not found — trying Node.js wabt JS API fallback ..."
  if command -v node &>/dev/null && node -e "require('wabt')" 2>/dev/null; then
    node -e "
const wabt = require('wabt');
const fs   = require('fs');
wabt().then(w => {
  const src = fs.readFileSync('$WAT_FILE', 'utf8');
  const mod = w.parseWat('signal_processor.wat', src, { mutable_globals: true });
  const { buffer } = mod.toBinary({ log: false, write_debug_names: false });
  fs.writeFileSync('$WASM_OUT', Buffer.from(buffer));
  console.log('        Output: $WASM_OUT (' + buffer.length + ' bytes) via wabt npm');
  mod.destroy();
}).catch(e => { console.error('wabt JS API failed:', e.message); process.exit(1); });
"
  else
    echo "  [1/3] ERROR — no WASM compiler found."
    echo "         Install WABT (preferred): nix-env -iA nixpkgs.wabt"
    echo "                                   brew install wabt  (macOS)"
    echo "                                   sudo apt-get install wabt  (Debian/Ubuntu)"
    echo "         OR install wabt npm package: npm install wabt"
    # Fail hard if no valid artifact is already present — a zero-byte placeholder
    # from a prior failed build is not a usable .wasm.
    if [ ! -f "$WASM_OUT" ] || [ ! -s "$WASM_OUT" ]; then
      echo "  No pre-compiled wasm/signal_processor.wasm found — aborting."
      exit 1
    fi
    echo "        Pre-compiled wasm/signal_processor.wasm already present ($(wc -c < "$WASM_OUT") bytes) — using it."
  fi
fi

# ── Step 2: Optimize (optional) ───────────────────────────────────────────────
if [[ "${1:-}" == "--optimize" ]] && command -v wasm-opt &>/dev/null; then
  echo "  [2/3] Optimizing with wasm-opt -O3 ..."
  wasm-opt "$WASM_OUT" -O3 -o "$WASM_OPT_OUT"
  echo "        Optimized: $WASM_OPT_OUT ($(wc -c < "$WASM_OPT_OUT") bytes)"
else
  echo "  [2/3] SKIP — wasm-opt not available or --optimize not specified"
fi

# ── Step 3: Validate ──────────────────────────────────────────────────────────
if [[ "${1:-}" == "--validate" ]] || [[ "${2:-}" == "--validate" ]]; then
  if command -v wasm-validate &>/dev/null; then
    echo "  [3/3] Validating WASM module ..."
    wasm-validate "$WASM_OUT"
    echo "        VALID"
  else
    echo "  [3/3] SKIP — wasm-validate not available"
  fi
else
  echo "  [3/3] SKIP — pass --validate to run validation"
fi

echo "─────────────────────────────────────────────"

# ── TypeScript usage snippet ───────────────────────────────────────────────────
cat <<'EOF'
  TypeScript SDK usage (chains/*/execute.ts):

    import wasmPath from './signal_processor.wasm';
    const mod = await WebAssembly.instantiateStreaming(fetch(wasmPath));
    const {
      compute_threshold, signal_emits, apply_mf_correction,
      compute_pc_limit, brt_circadian, is_silence_type,
      signal_type_count,
    } = mod.instance.exports as any;

    // Compute threshold locally — no Oracle API round-trip
    const theta = compute_threshold(marketVolatility);        // → f64
    const emits = signal_emits(coherenceC, theta) === 1;      // → bool
    const phiAdj = apply_mf_correction(phiRaw, mfScore);      // → f64
    const pcLim  = compute_pc_limit(hIrreducible, hFuture);   // → f64

    // BRT phases from block timestamp
    const circadian = brt_circadian(blockTimestamp);           // → f64 ∈ [0,1]

    // Type safety — never treat SILENCE as VALUATION
    if (is_silence_type(signal.signal_type_id)) {
      // handle structured silence — do NOT treat as price signal
    }

    // Total registered signal types (24)
    const count = signal_type_count();  // → 24
EOF

echo ""
echo "Build complete — signal_processor.wasm ready for TRION SDK."
