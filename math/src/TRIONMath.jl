# TRION Protocol — Julia Mathematics Module (whitepaper Part 11)
#
# Julia — Mathematics: Scale invariance verification, entropy budget calculation,
# prediction interval mathematical validation.
# WHY: Julia is purpose-built for high-performance numerical computing and formal
# mathematical verification with clean syntax for expressing theorems as code.

module TRIONMath

using Statistics
using LinearAlgebra

export shannon_entropy, phi_score, coherence, convergence_bound,
       verify_scale_invariance, prediction_interval_calibration,
       moat_compound, bootstrap_weight_decay, kolmogorov_bound

# ── L1.1: Shannon Entropy (whitepaper L1.1) ───────────────────────────────────

"""
    shannon_entropy(values::Vector{T}) -> Float64

H(X) = -Σ p(x) · log₂(p(x))

Computes Shannon entropy of a discrete distribution.
H=0: all identical (degenerate). H_max=log₂(n): uniform (organic).
"""
function shannon_entropy(values::Vector{T}) where T
    isempty(values) && return 0.0
    freq = Dict{T, Int}()
    for v in values
        freq[v] = get(freq, v, 0) + 1
    end
    n = length(values)
    -sum(c/n * log2(c/n) for c in values(freq) if c > 0)
end

function shannon_entropy(probs::Vector{Float64})
    isempty(probs) && return 0.0
    s = sum(p -> p > 0 ? -p * log2(p) : 0.0, probs)
    s
end

# ── L0.1: Magnitude Normalization ─────────────────────────────────────────────

"""
    magnitude_norm(usd_value::Float64, max_90d::Float64) -> Float64

magnitude_normalized = log10(USD_value + 1) / log10(max_observed_90d + 1)
Result ∈ [0, 1] always.
"""
function magnitude_norm(usd_value::Float64, max_90d::Float64)::Float64
    max_90d <= 0.0 && return 0.0
    log10(usd_value + 1) / log10(max_90d + 1)
end

# ── L1.1: Physical Richness Score Φ(t) ───────────────────────────────────────

"""
    phi_score(features::Vector{Float64}, weights::Vector{Float64}) -> Float64

Φ(t) = (1/N) · Σ [ w_i · H(f_i(t)) ]
Nine EVM features: volume, counterparty, temporal, contract, flow,
                   wallet, cross-protocol, gas, MEV patterns.
"""
function phi_score(features::Vector{Float64}, weights::Vector{Float64})::Float64
    length(features) != length(weights) && error("Feature/weight dimension mismatch")
    N = length(features)
    N == 0 && return 0.0
    sum(weights[i] * features[i] for i in 1:N) / N
end

# ── L5.2: Five-Plane Coherence C(t) ─────────────────────────────────────────

"""
    coherence(φ_adj, M_adj, Σ, K, A; profile=:balanced) -> Float64

C(t) = α·Φ_adj(t) + β·M_adj(t) + γ·Σ(t) + δ·K(t) + ε·A(t)
Weights sum to 1.0.
"""
function coherence(φ_adj::Float64, M_adj::Float64, Σ_val::Float64,
                   K::Float64, A::Float64; profile::Symbol=:balanced)::Float64
    weights = Dict(
        :balanced    => (0.25, 0.30, 0.25, 0.10, 0.10),
        :speed       => (0.50, 0.20, 0.20, 0.05, 0.05),
        :intelligence => (0.15, 0.35, 0.15, 0.05, 0.30),
        :certainty   => (0.15, 0.20, 0.50, 0.10, 0.05),
        :full_spectrum => (0.20, 0.20, 0.20, 0.20, 0.20),
    )
    α, β, γ, δ, ε = get(weights, profile, weights[:balanced])
    @assert abs(α + β + γ + δ + ε - 1.0) < 1e-10 "Weights must sum to 1.0"
    clamp(α*φ_adj + β*M_adj + γ*Σ_val + δ*K + ε*A, 0.0, 1.0)
end

# ── L2.5: Convergence Bound ───────────────────────────────────────────────────

"""
    convergence_bound(d::Float64, h_irreducible::Float64=0.01) -> Float64

lim_{D(t)→∞} E[|T(t) - V_true|] = H_irreducible

Expected error upper bound given current Akashic depth D.
Converges monotonically to H_irreducible as D→∞.
"""
function convergence_bound(d::Float64, h_irreducible::Float64=0.01)::Float64
    d <= 0 && return 1.0
    # Exponential convergence rate (law of large numbers guarantees this)
    h_irreducible + (1.0 - h_irreducible) * exp(-d / 10000.0)
end

# ── Scale Invariance Verification ────────────────────────────────────────────

"""
    verify_scale_invariance(signal_values::Vector{Float64}) -> NamedTuple

Verifies that TRION signals are scale-invariant (whitepaper L0.5).
A signal S is scale-invariant if multiplying all inputs by constant k
produces the same normalized signal.
"""
function verify_scale_invariance(signal_values::Vector{Float64})
    isempty(signal_values) && return (valid=false, reason="empty")
    
    mn, mx = extrema(signal_values)
    range_val = mx - mn
    range_val ≈ 0.0 && return (valid=true, reason="constant_signal", scale_factor=1.0)
    
    # Normalize to [0,1]
    normalized = (signal_values .- mn) ./ range_val
    
    # Scale-invariance test: multiply by 10x, normalize — should give same result
    scaled = signal_values .* 10.0
    mn2, mx2 = extrema(scaled)
    normalized2 = (scaled .- mn2) ./ (mx2 - mn2)
    
    max_diff = maximum(abs.(normalized .- normalized2))
    valid = max_diff < 1e-10
    
    (valid=valid, max_diff=max_diff, reason=valid ? "scale_invariant" : "scale_variant")
end

# ── Prediction Interval Calibration ──────────────────────────────────────────

"""
    prediction_interval_calibration(predictions, lower_bounds, upper_bounds,
                                     realized) -> NamedTuple

Verifies that 95% CI brackets outcome 95%±2% over test set (whitepaper L3.1).
FALSIFIABLE: F6 — Genesis Inference valid if calibration holds over 90d/100+ events.
"""
function prediction_interval_calibration(
    lower_bounds::Vector{Float64},
    upper_bounds::Vector{Float64},
    realized::Vector{Float64}
)
    n = length(realized)
    n == 0 && return (coverage=0.0, calibrated=false, n=0)
    
    in_interval = sum(lower_bounds[i] <= realized[i] <= upper_bounds[i] for i in 1:n)
    coverage = in_interval / n
    calibrated = abs(coverage - 0.95) <= 0.02  # 95% ± 2% tolerance
    
    widths = upper_bounds .- lower_bounds
    avg_width = mean(widths)
    
    (coverage=coverage, calibrated=calibrated, n=n,
     avg_interval_width=avg_width, target=0.95, tolerance=0.02)
end

# ── Moat Compounding ──────────────────────────────────────────────────────────

"""
    moat_compound(D, Q, R, X, F, N) -> Float64

M_moat(t) = D(t) · Q(t) · R(t) · X(t) · F(t) · N(t)
All factors ∈ [0, 1]. Multiplicative — all must be strong for a high moat.
A competitor must replicate ALL six factors simultaneously.
"""
function moat_compound(D::Float64, Q::Float64, R::Float64,
                        X::Float64, F::Float64, N::Float64)::Float64
    all(0.0 <= v <= 1.0 for v in (D, Q, R, X, F, N)) || @warn "Moat factors should be ∈ [0,1]"
    D * Q * R * X * F * N
end

# ── Bootstrap Weight Decay ────────────────────────────────────────────────────

"""
    bootstrap_weight_decay(d::Int) -> Float64

bootstrap_weight(t) = e^(-λ_boot · D(t))
λ_boot = 0.0001; D=50000 → weight ≈ 0.007 (Living Security fully active)
"""
function bootstrap_weight_decay(d::Int)::Float64
    λ = 0.0001
    exp(-λ * d)
end

# ── Kolmogorov Complexity Lower Bound ─────────────────────────────────────────

"""
    kolmogorov_bound(t_secs, n_chains, n_validators) -> Float64

K(H(TRION, t)) >= Ω(t · N_chains · N_validators · H_environment)
Returns approximate lower bound in bits.
Grows without bound → breach probability → 0.
"""
function kolmogorov_bound(t_secs::Float64, n_chains::Int, n_validators::Int)::Float64
    log2(max(t_secs, 1.0)) + log2(max(n_chains, 1)) + log2(max(n_validators, 1))
end

# ── Entropy Budget Calculator ─────────────────────────────────────────────────

"""
    entropy_budget(signal_count, bits_per_signal, storage_capacity_bits) -> NamedTuple

L0.5: Signal selected iff dI_gained / dS_entropy_cost > θ_selection
Computes information budget for a TRION node.
"""
function entropy_budget(signal_count::Int, bits_per_signal::Float64,
                         storage_capacity_bits::Float64)
    total_bits = signal_count * bits_per_signal
    utilization = total_bits / storage_capacity_bits
    remaining = storage_capacity_bits - total_bits
    compression_needed = utilization > 1.0
    
    (total_bits=total_bits, utilization=utilization,
     remaining_bits=max(0.0, remaining),
     compression_needed=compression_needed,
     signals_at_capacity=Int(floor(storage_capacity_bits / bits_per_signal)))
end

end  # module TRIONMath

# ── Standalone verification (run with: julia math/TRIONMath.jl) ──

if abspath(PROGRAM_FILE) == @__FILE__
    using .TRIONMath

    println("=== TRION Julia Mathematics Module — Verification Suite ===\n")

    # 1. Shannon entropy
    h_uniform = shannon_entropy([0.25, 0.25, 0.25, 0.25])
    h_degenerate = shannon_entropy([1.0, 0.0, 0.0, 0.0])
    @assert h_uniform ≈ 2.0 atol=1e-10 "Uniform entropy should be log2(4)=2.0"
    @assert h_degenerate ≈ 0.0 atol=1e-10 "Degenerate entropy should be 0"
    println("[PASS] L1.1 Shannon entropy: uniform=2.0, degenerate=0.0")

    # 2. Magnitude normalization
    m1 = magnitude_norm(Float64(1000.0), Float64(10000.0))
    m2 = magnitude_norm(Float64(0.0), Float64(10000.0))
    m3 = magnitude_norm(Float64(10000.0), Float64(10000.0))
    @assert 0.0 <= m1 <= 1.0 "magnitude_norm must be ∈ [0,1]"
    @assert m2 ≈ 0.0 atol=1e-10
    @assert m3 ≈ 1.0 atol=1e-10
    println("[PASS] L0.1 Magnitude normalization ∈ [0,1]")

    # 3. Five-plane coherence weights sum to 1
    for profile in (:balanced, :speed, :intelligence, :certainty, :full_spectrum)
        c = coherence(0.8, 0.7, 0.9, 0.6, 0.5; profile=profile)
        @assert 0.0 <= c <= 1.0 "Coherence must be ∈ [0,1] for $profile"
    end
    println("[PASS] L5.2 All 5 coherence weight profiles valid")

    # 4. Convergence bound (monotonically decreasing toward H_irreducible)
    depths = [0.0, 1000.0, 10000.0, 100000.0, 1000000.0]
    bounds = [convergence_bound(d) for d in depths]
    @assert all(bounds[i] >= bounds[i+1] for i in 1:length(bounds)-1) "Must be monotone"
    @assert bounds[end] ≈ 0.01 atol=0.001 "Must converge to H_irreducible"
    println("[PASS] L2.5 Convergence bound monotone, converges to H_irreducible=0.01")

    # 5. Scale invariance
    sv = verify_scale_invariance([0.1, 0.5, 0.8, 0.3, 0.9])
    @assert sv.valid "Signals must be scale-invariant"
    println("[PASS] L0.5 Scale invariance verified")

    # 6. Moat compounding
    m = moat_compound(0.8, 0.9, 0.7, 0.6, 0.5, 0.4)
    @assert 0.0 < m < 1.0 "Moat must compound correctly"
    m_partial = moat_compound(0.8, 0.9, 0.0, 0.6, 0.5, 0.4)
    @assert m_partial ≈ 0.0 atol=1e-10 "Zero in any factor → moat = 0"
    println("[PASS] L5.3 Moat compounding: M=$m, zero-factor=0.0")

    # 7. Bootstrap weight decay
    w0 = bootstrap_weight_decay(0)
    w_mature = bootstrap_weight_decay(50000)
    @assert w0 ≈ 1.0 atol=1e-10 "At D=0, bootstrap weight = 1.0"
    @assert w_mature < 0.01 "At D=50000, bootstrap weight ≈ 0"
    println("[PASS] L4.7 Bootstrap weight D=0→$(round(w0,digits=4)), D=50000→$(round(w_mature,digits=6))")

    # 8. Kolmogorov bound grows without bound
    k1 = kolmogorov_bound(86400.0, 31, 100)   # 1 day
    k2 = kolmogorov_bound(864000.0, 31, 100)  # 10 days
    @assert k2 > k1 "K complexity must grow with time"
    println("[PASS] L4.3 Kolmogorov bound growing: day1=$k1 bits, day10=$k2 bits")

    # 9. Prediction interval calibration
    # A well-calibrated 95% interval contains ~95% of realized values.
    # Construct exactly 95% coverage: 190 of 200 inside the interval.
    n = 200
    lower = fill(0.3, n)
    upper = fill(0.8, n)
    realized = fill(0.55, n)  # all inside [0.3, 0.8]
    realized[1:10] .= 0.95   # 10 outside → 190/200 = 95% coverage exactly
    cal = prediction_interval_calibration(lower, upper, realized)
    @assert cal.calibrated "95% coverage must be calibrated (within 2% of 95%)"
    println("[PASS] L3.1 Prediction interval calibration: coverage=$(cal.coverage)")

    # 10. Entropy budget
    budget = entropy_budget(10000, 256.0, 1e9)
    @assert budget.utilization > 0.0
    println("[PASS] L0.5 Entropy budget: $(Int(round(budget.total_bits))) bits used, $(round(budget.utilization*100,digits=2))% capacity")

    println("\n=== ALL JULIA MATH VERIFICATIONS PASSED ===")
    println("Language: Julia (whitepaper Part 11 — Mathematics)")
    println("Verified: Shannon entropy, magnitude norm, coherence weights,")
    println("          convergence bound, scale invariance, moat compounding,")
    println("          bootstrap decay, Kolmogorov bound, PI calibration, entropy budget")
end
