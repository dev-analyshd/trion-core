# TRION Protocol — Julia math module test suite
#
# Audit fix (TEST-1): this file was a trivial placeholder (`1 + 1 == 2`) that
# never imported TRIONMath — the module's real functions were untested.
# This suite exercises every exported function against whitepaper-specified
# values and mathematical invariants.
#
# Run: julia --project=.. math/test/runtests.jl   (or `julia test/runtests.jl` from math/)

using Test
using Statistics
using LinearAlgebra

# ── Import the actual module (audit TEST-1: previously never imported) ──────
const TRION_SRC = joinpath(@__DIR__, "..", "src")
include(joinpath(TRION_SRC, "TRIONMath.jl"))
using .TRIONMath
import .TRIONMath: magnitude_norm, entropy_budget  # internal, not exported

@testset "TRIONMath — whitepaper formula verification" begin

    # ── L1.1 Shannon Entropy ────────────────────────────────────────────────
    @testset "shannon_entropy" begin
        # Uniform distribution over n symbols → log2(n) bits
        @test shannon_entropy([0.25, 0.25, 0.25, 0.25]) ≈ 2.0 atol=1e-12
        @test shannon_entropy([0.5, 0.5]) ≈ 1.0 atol=1e-12
        # Certain distribution → 0 bits
        @test shannon_entropy([1.0, 0.0, 0.0]) ≈ 0.0 atol=1e-12
        # Empty input → 0
        @test shannon_entropy(Float64[]) == 0.0
        # Frequency-based method agrees with probability method
        @test shannon_entropy([:a, :a, :b, :c]) ≈ shannon_entropy([0.5, 0.25, 0.25]) atol=1e-12
        # Entropy is maximized by uniformity (1/8 uniform → 3 bits)
        @test shannon_entropy(fill(0.125, 8)) ≈ 3.0 atol=1e-12
    end

    # ── L0.1 Magnitude Normalization ───────────────────────────────────────
    @testset "magnitude_norm" begin
        # log10(USD+1) / log10(max90d+1) — whitepaper L0.1
        @test magnitude_norm(999.0, 999.0) ≈ 1.0 atol=1e-12
        @test magnitude_norm(0.0, 1e6) ≈ 0.0 atol=1e-12
        @test magnitude_norm(1e6, 1e6) ≈ 1.0 atol=1e-12
        # Mid-range value strictly inside (0, 1)
        mid = magnitude_norm(1000.0, 1e6)
        @test 0.0 < mid < 1.0
        # Degenerate max_90d → 0 (safe fallback)
        @test magnitude_norm(100.0, 0.0) == 0.0
        # Monotonicity in usd_value
        @test magnitude_norm(10.0, 1e6) < magnitude_norm(100.0, 1e6) < magnitude_norm(1000.0, 1e6)
    end

    # ── L1.1 Physical Richness Φ(t) ─────────────────────────────────────────
    @testset "phi_score" begin
        # Φ = (1/N) Σ w_i·H(f_i): uniform weights over 9 features
        feats = collect(0.1:0.1:0.9)
        w     = fill(0.2, 9)
        expected = sum(w[i] * feats[i] for i in 1:9) / 9
        @test phi_score(feats, w) ≈ expected atol=1e-12
        # Dimension mismatch raises
        @test_throws ErrorException phi_score([0.5, 0.5], [1.0])
        # Empty → 0
        @test phi_score(Float64[], Float64[]) == 0.0
    end

    # ── L5.2 Five-Plane Coherence C(t) ──────────────────────────────────────
    @testset "coherence" begin
        # Balanced profile: α=.25 β=.30 γ=.25 δ=.10 ε=.10
        vals = (0.8, 0.6, 0.5, 0.4, 0.2)
        expected_balanced = 0.25*0.8 + 0.30*0.6 + 0.25*0.5 + 0.10*0.4 + 0.10*0.2
        @test coherence(vals..., profile=:balanced) ≈ expected_balanced atol=1e-12
        # Clamped to [0, 1]
        @test coherence(1.5, 1.5, 1.5, 1.5, 1.5) == 1.0
        @test coherence(-1.0, -1.0, -1.0, -1.0, -1.0) == 0.0
        # All-weight profiles — equal planes under full_spectrum = mean
        @test coherence(0.5, 0.5, 0.5, 0.5, 0.5, profile=:full_spectrum) ≈ 0.5 atol=1e-12
        # Certainty profile weights Σ (spiritual) heaviest: raising Σ raises C
        @test coherence(0.1, 0.1, 0.9, 0.1, 0.1, profile=:certainty) >
              coherence(0.9, 0.1, 0.1, 0.1, 0.1, profile=:certainty)
    end

    # ── L2.5 Convergence Bound ──────────────────────────────────────────────
    @testset "convergence_bound" begin
        h = 0.01
        # D → ∞ converges to H_irreducible
        @test convergence_bound(1e9, h) ≈ h atol=1e-4
        # D = 0 → maximal error (1.0)
        @test convergence_bound(0.0, h) == 1.0
        # Negative depth → 1.0 (safe)
        @test convergence_bound(-5.0, h) == 1.0
        # Monotone decreasing in depth
        @test convergence_bound(100.0, h) > convergence_bound(10000.0, h) >
              convergence_bound(1000000.0, h)
    end

    # ── L0.5 Scale Invariance ───────────────────────────────────────────────
    @testset "verify_scale_invariance" begin
        r = verify_scale_invariance([0.1, 0.5, 0.8, 0.3, 0.9])
        @test r isa NamedTuple
        @test haskey(r, :valid)
        # Empty input explicitly reported invalid
        @test verify_scale_invariance(Float64[]).valid == false
    end

    # ── L9 Moat Compounding ─────────────────────────────────────────────────
    @testset "moat_compound" begin
        # M_moat = D·Q·R·X·F·N — pure product of six factors
        @test moat_compound(0.5, 0.5, 0.5, 0.5, 0.5, 0.5) ≈ 0.5^6 atol=1e-12
        @test moat_compound(1.0, 1.0, 1.0, 1.0, 1.0, 1.0) ≈ 1.0 atol=1e-12
        @test moat_compound(0.0, 1.0, 1.0, 1.0, 1.0, 1.0) ≈ 0.0 atol=1e-12
    end

    # ── L4.7 Bootstrap Weight Decay ─────────────────────────────────────────
    @testset "bootstrap_weight_decay" begin
        # w(t) = e^(-λ·D), λ = 1e-4; D = 50_000 → ≈ 0.0067 (Living Security active)
        @test bootstrap_weight_decay(50_000) ≈ exp(-5.0) atol=1e-12
        @test bootstrap_weight_decay(0) == 1.0
        @test 0.0 < bootstrap_weight_decay(50_000) < 0.01
        # Monotone decay
        @test bootstrap_weight_decay(1000) > bootstrap_weight_decay(10000)
    end

    # ── L4.4 Kolmogorov Complexity Lower Bound ──────────────────────────────
    @testset "kolmogorov_bound" begin
        # K ≥ log2(t) + log2(chains) + log2(validators)
        @test kolmogorov_bound(1e6, 16, 64) ≈ 20.0 + 4.0 + 6.0 atol=1e-9
        # Grows with each factor
        @test kolmogorov_bound(1e6, 32, 64) > kolmogorov_bound(1e6, 16, 64)
        @test kolmogorov_bound(1e7, 16, 64) > kolmogorov_bound(1e6, 16, 64)
        # Degenerate inputs are clamped to 1 (log2(max(x,1)))
        @test kolmogorov_bound(0.5, 0, 0) ≈ 0.0 atol=1e-12
    end

    # ── L0.5 Entropy Budget ─────────────────────────────────────────────────
    @testset "entropy_budget" begin
        r = entropy_budget(100, 256.0, 1e6)
        @test r.total_bits == 25_600.0
        @test r.utilization ≈ 0.0256 atol=1e-12
        @test r.remaining_bits ≈ 974_400.0 atol=1e-6
        @test r.compression_needed == false
        @test r.signals_at_capacity == Int(floor(1e6 / 256.0))
        # Over capacity → compression flagged, remaining clamped at 0
        over = entropy_budget(10_000, 256.0, 1e6)
        @test over.compression_needed == true
        @test over.remaining_bits == 0.0
    end
end

println("TRION Math — all testsets executed against the real module")
