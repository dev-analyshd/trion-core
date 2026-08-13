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
)
