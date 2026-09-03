;; TRION Protocol — WebAssembly Browser Signal Processor
;; Whitepaper Section 21 Tech Stack / Layer 7 — Type System (Channel 18):
;; "WebAssembly — browser-side signal processing, type-system enforcement"
;;
;; This WASM module enables browser clients to:
;;   1. Verify TRIONSignal type integrity (SILENCE ≠ VALUATION at runtime)
;;   2. Compute threshold Θ(t) = 0.55 + 0.37·V(t) locally (no server round-trip)
;;   3. Apply MF correction: Φ_adj = Φ_raw × (1 - MF)
;;   4. Compute PC_limit: 1 - H_irr / H_future
;;   5. Decode BRT phases from a unix timestamp
;;
;; Gas-optimized for browser execution — no external dependencies, pure WASM.
;; Companion TypeScript SDK (chains/*/execute.ts) imports these exports.
;;
;; Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
;; License: CC0

(module
  ;; ── Constants ────────────────────────────────────────────────────────────────
  ;; Signal type IDs matching SignalType enum in signal_factory.py
  (global $ST_VALUATION          i32 (i32.const 0))
  (global $ST_SILENCE            i32 (i32.const 1))
  (global $ST_MANIPULATION_ALERT i32 (i32.const 2))
  (global $ST_GENESIS            i32 (i32.const 3))
  (global $ST_RESURRECTION       i32 (i32.const 4))
  (global $ST_FORK_DIVERGENCE    i32 (i32.const 5))
  (global $ST_TRAJECTORY         i32 (i32.const 6))
  (global $ST_NEGATIVE_SPACE     i32 (i32.const 7))
  (global $ST_PHASE_TRANSITION   i32 (i32.const 8))
  (global $ST_SYSTEMIC_RISK      i32 (i32.const 9))
  (global $ST_LIQUIDITY_HEALTH   i32 (i32.const 10))
  (global $ST_GOVERNANCE         i32 (i32.const 11))
  (global $ST_CROSS_CHAIN        i32 (i32.const 12))
  (global $ST_STABLECOIN         i32 (i32.const 13))
  (global $ST_MEV_EXPOSURE       i32 (i32.const 14))
  (global $ST_INSTITUTIONAL      i32 (i32.const 15))
  (global $ST_REGULATORY         i32 (i32.const 16))
  (global $ST_ECOSYSTEM          i32 (i32.const 17))
  (global $ST_BOOTSTRAP          i32 (i32.const 18))
  (global $ST_SOVEREIGN          i32 (i32.const 19))
  (global $ST_ENERGY_PART        i32 (i32.const 20))
  (global $ST_BIO_CAPITAL        i32 (i32.const 21))
  (global $ST_BTCP_ROUTE         i32 (i32.const 22))
  (global $ST_CONSENSUS_ADAPT    i32 (i32.const 23))

  ;; Threshold constants
  (global $THETA_MIN  f64 (f64.const 0.55))
  (global $THETA_MAX  f64 (f64.const 0.92))

  ;; BRT moduli (seconds)
  (global $BRT_CIRCADIAN   f64 (f64.const 86400.0))    ;; 24 hours
  (global $BRT_ULTRADIAN   f64 (f64.const 5400.0))     ;; 90 minutes
  (global $BRT_LUNAR       f64 (f64.const 2551442.0))  ;; 29.53 days
  (global $BRT_SEASONAL    f64 (f64.const 31557600.0)) ;; 365.25 days


  ;; ── Memory ──────────────────────────────────────────────────────────────────
  (memory 1)  ;; 64 KiB page — sufficient for signal processing buffers


  ;; ── Exported functions ───────────────────────────────────────────────────────

  ;; compute_threshold(volatility: f64) → f64
  ;; Θ(t) = Θ_min + (Θ_max - Θ_min) × clamp(V(t), 0, 1)
  ;; Runs entirely client-side — no network round-trip.
  (func $compute_threshold (export "compute_threshold") (param $v f64) (result f64)
    (local $v_clamped f64)
    ;; clamp v to [0.0, 1.0]
    (local.set $v_clamped
      (f64.min
        (f64.const 1.0)
        (f64.max (f64.const 0.0) (local.get $v))))
    ;; Θ = 0.55 + (0.92 - 0.55) × v_clamped  =  0.55 + 0.37 × v
    (f64.add
      (global.get $THETA_MIN)
      (f64.mul
        (f64.sub (global.get $THETA_MAX) (global.get $THETA_MIN))
        (local.get $v_clamped))))

  ;; signal_emits(coherence: f64, threshold: f64) → i32 (bool: 1=true, 0=false)
  ;; Returns 1 if C(t) ≥ Θ(t) — VALUATION; 0 — SILENCE
  (func $signal_emits (export "signal_emits") (param $C f64) (param $theta f64) (result i32)
    (f64.ge (local.get $C) (local.get $theta)))

  ;; is_silence_type(signal_type_id: i32) → i32 (bool)
  ;; Type-system enforcement: SILENCE = type 1 only.
  ;; Browser consumers use this to guard against treating SILENCE as VALUATION.
  (func $is_silence_type (export "is_silence_type") (param $type_id i32) (result i32)
    (i32.eq (local.get $type_id) (global.get $ST_SILENCE)))

  ;; is_valuation_type(signal_type_id: i32) → i32 (bool)
  (func $is_valuation_type (export "is_valuation_type") (param $type_id i32) (result i32)
    (i32.eq (local.get $type_id) (global.get $ST_VALUATION)))

  ;; apply_mf_correction(phi_raw: f64, mf_score: f64) → f64
  ;; Φ_adj(t) = Φ_raw(t) × (1 - clamp(MF, 0, 1))
  (func $apply_mf_correction (export "apply_mf_correction") (param $phi f64) (param $mf f64) (result f64)
    (local $mf_clamped f64)
    (local.set $mf_clamped
      (f64.min (f64.const 1.0) (f64.max (f64.const 0.0) (local.get $mf))))
    (f64.mul
      (local.get $phi)
      (f64.sub (f64.const 1.0) (local.get $mf_clamped))))

  ;; compute_pc_limit(h_irr: f64, h_future: f64) → f64
  ;; PC_limit(t) = 1 - H_irr / H_future  (clamped to [0, 0.9999])
  (func $compute_pc_limit (export "compute_pc_limit") (param $h_irr f64) (param $h_future f64) (result f64)
    (local $pc f64)
    ;; guard: h_future <= 0 → return 0.0
    (if (f64.le (local.get $h_future) (f64.const 0.0))
      (then (return (f64.const 0.0))))
    ;; guard: h_irr <= 0 → return 1.0 (no irreducible uncertainty)
    (if (f64.le (local.get $h_irr) (f64.const 0.0))
      (then (return (f64.const 1.0))))
    (local.set $pc
      (f64.sub
        (f64.const 1.0)
        (f64.div (local.get $h_irr) (local.get $h_future))))
    ;; clamp to [0.0, 0.9999]
    (f64.min
      (f64.const 0.9999)
      (f64.max (f64.const 0.0) (local.get $pc))))

  ;; brt_circadian(unix_ts: f64) → f64  — phase ∈ [0, 1]
  (func $brt_circadian (export "brt_circadian") (param $ts f64) (result f64)
    (f64.div
      (f64.sub (local.get $ts)
        (f64.mul
          (global.get $BRT_CIRCADIAN)
          (f64.trunc (f64.div (local.get $ts) (global.get $BRT_CIRCADIAN)))))
      (global.get $BRT_CIRCADIAN)))

  ;; brt_ultradian(unix_ts: f64) → f64
  (func $brt_ultradian (export "brt_ultradian") (param $ts f64) (result f64)
    (f64.div
      (f64.sub (local.get $ts)
        (f64.mul
          (global.get $BRT_ULTRADIAN)
          (f64.trunc (f64.div (local.get $ts) (global.get $BRT_ULTRADIAN)))))
      (global.get $BRT_ULTRADIAN)))

  ;; brt_lunar(unix_ts: f64) → f64
  (func $brt_lunar (export "brt_lunar") (param $ts f64) (result f64)
    (f64.div
      (f64.sub (local.get $ts)
        (f64.mul
          (global.get $BRT_LUNAR)
          (f64.trunc (f64.div (local.get $ts) (global.get $BRT_LUNAR)))))
      (global.get $BRT_LUNAR)))

  ;; brt_seasonal(unix_ts: f64) → f64
  (func $brt_seasonal (export "brt_seasonal") (param $ts f64) (result f64)
    (f64.div
      (f64.sub (local.get $ts)
        (f64.mul
          (global.get $BRT_SEASONAL)
          (f64.trunc (f64.div (local.get $ts) (global.get $BRT_SEASONAL)))))
      (global.get $BRT_SEASONAL)))

  ;; signal_type_count() → i32  — total registered signal types (24)
  (func $signal_type_count (export "signal_type_count") (result i32)
    (i32.const 24))

  ;; is_extended_signal(type_id: i32) → i32  — types 19-23 are extended
  (func $is_extended_signal (export "is_extended_signal") (param $type_id i32) (result i32)
    (i32.and
      (i32.ge_s (local.get $type_id) (i32.const 19))
      (i32.le_s (local.get $type_id) (i32.const 23))))

  ;; ── SDK P0 fix: coherence verification + entropy (TrionSDK.ts depends on these) ──

  ;; log2(x) for x > 0 — implemented without the f64.log2 opcode so the
  ;; module builds with every wat2wasm (incl. wabt/wasmtime builds that
  ;; reject transcendental opcodes in text form).
  ;; Method: normalize x = m·2^e with m ∈ [0.5,1), then
  ;;   log2(m) = (2/ln2)·artanh(y), y = (m-1)/(m+1), y ∈ [-1/3, 0)
  ;;   artanh(y) = Σ_{k=0}^{13} y^(2k+1)/(2k+1)
  ;; 14 terms bound the remainder by ~|y|^29/29 ≈ 1e-15 for |y| ≤ 1/3.
  (func $log2 (param $x f64) (result f64)
    (local $m f64) (local $e i32) (local $y f64)
    (local $term f64) (local $sum f64) (local $k i32)
    (local $y2 f64)
    (local.set $m (local.get $x))
    ;; normalize m into [0.5, 1)
    (loop $norm_lo
      (if (f64.lt (local.get $m) (f64.const 0.5))
        (then
          (local.set $m (f64.mul (local.get $m) (f64.const 2.0)))
          (local.set $e (i32.sub (local.get $e) (i32.const 1)))
          (br $norm_lo))))
    (loop $norm_hi
      (if (f64.ge (local.get $m) (f64.const 1.0))
        (then
          (local.set $m (f64.div (local.get $m) (f64.const 2.0)))
          (local.set $e (i32.add (local.get $e) (i32.const 1)))
          (br $norm_hi))))
    ;; y = (m-1)/(m+1)
    (local.set $y
      (f64.div
        (f64.sub (local.get $m) (f64.const 1.0))
        (f64.add (local.get $m) (f64.const 1.0))))
    (local.set $y2 (f64.mul (local.get $y) (local.get $y)))
    ;; series: sum = Σ y^(2k+1)/(2k+1), k = 0..13
    (local.set $term (local.get $y))
    (local.set $k (i32.const 0))
    (loop $series
      (if (i32.lt_s (local.get $k) (i32.const 14))
        (then
          (local.set $sum
            (f64.add (local.get $sum)
              (f64.div (local.get $term)
                (f64.convert_i32_s
                  (i32.add (i32.mul (local.get $k) (i32.const 2)) (i32.const 1))))))
          (local.set $term (f64.mul (local.get $term) (local.get $y2)))
          (local.set $k (i32.add (local.get $k) (i32.const 1)))
          (br $series))))
    ;; log2(x) = 2.885390081777927 · sum + e
    (f64.add
      (f64.mul (f64.const 2.885390081777927) (local.get $sum))
      (f64.convert_i32_s (local.get $e))))

  ;; compute_coherence(phi, mental, sigma, conscious, anima) → f64
  ;; C(t) = 0.25·Φ + 0.30·M + 0.25·Σ + 0.10·K + 0.10·A   (DEFAULT_BALANCED profile)
  ;; Matches core/master/coherence.py (canonical five-plane weighted sum),
  ;; clamped to [0, 1]. Used by TrionSDK.verifyCoherenceWasm() for
  ;; client-side tamper detection of server-reported coherence.
  (func $compute_coherence (export "compute_coherence")
      (param $phi f64) (param $mental f64) (param $sigma f64)
      (param $conscious f64) (param $anima f64)
      (result f64)
    (local $c f64)
    (local.set $c
      (f64.add
        (f64.add
          (f64.add
            (f64.mul (f64.const 0.25) (local.get $phi))
            (f64.mul (f64.const 0.30) (local.get $mental)))
          (f64.add
            (f64.mul (f64.const 0.25) (local.get $sigma))
            (f64.mul (f64.const 0.10) (local.get $conscious))))
        (f64.mul (f64.const 0.10) (local.get $anima))))
    ;; clamp to [0, 1]
    (f64.min (f64.const 1.0)
      (f64.max (f64.const 0.0) (local.get $c))))

  ;; shannon_entropy(ptr: i32, len: i32) → f64
  ;; H = -Σ p·log2(p) where p = v_i / Σv (positive values only).
  ;; Mirrors core/physical/phi_engine.py shannon_entropy(). Values are read
  ;; from linear memory as f64 at 8-byte stride starting at `ptr`.
  (func $shannon_entropy (export "shannon_entropy") (param $ptr i32) (param $len i32) (result f64)
    (local $i i32)
    (local $total f64)
    (local $h f64)
    (local $v f64)
    (local $p f64)
    ;; Pass 1: total = Σ (v > 0)
    (local.set $i (i32.const 0))
    (loop $sum_loop
      (if (i32.lt_u (local.get $i) (local.get $len))
        (then
          (local.set $v
            (f64.load
              (i32.add
                (local.get $ptr)
                (i32.mul (local.get $i) (i32.const 8)))))
          (if (f64.gt (local.get $v) (f64.const 0.0))
            (then
              (local.set $total (f64.add (local.get $total) (local.get $v)))))
          (local.set $i (i32.add (local.get $i) (i32.const 1)))
          (br $sum_loop))))
    ;; guard: empty or all-zero input → 0.0
    (if (f64.le (local.get $total) (f64.const 0.0))
      (then (return (f64.const 0.0))))
    ;; Pass 2: H = -Σ p·log2(p)
    (local.set $i (i32.const 0))
    (loop $ent_loop
      (if (i32.lt_u (local.get $i) (local.get $len))
        (then
          (local.set $v
            (f64.load
              (i32.add
                (local.get $ptr)
                (i32.mul (local.get $i) (i32.const 8)))))
          (if (f64.gt (local.get $v) (f64.const 0.0))
            (then
              (local.set $p (f64.div (local.get $v) (local.get $total)))
              (local.set $h
                (f64.add (local.get $h)
                  (f64.mul (local.get $p) (call $log2 (local.get $p)))))))
          (local.set $i (i32.add (local.get $i) (i32.const 1)))
          (br $ent_loop))))
    ;; negate: H = -H (H accumulated as Σ p·log2(p) ≤ 0)
    (f64.neg (local.get $h)))

  ;; Export linear memory so the SDK can write input arrays for
  ;; shannon_entropy and read back results.
  (export "memory" (memory 0))
)
