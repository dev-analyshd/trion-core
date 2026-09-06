// TRION Protocol — C++ FFT Engine
// Whitepaper Section 21 Tech Stack:
// "C++ — FFT computation, hardware interface drivers, physical sensor nodes"
//
// This module implements the Shannon entropy computation over behavioral
// transaction flows using a Fast Fourier Transform (FFT) approach.
// Used by the Physical plane (Φ) to detect frequency-domain manipulation
// signatures — wash trading shows up as periodic spikes in the FFT spectrum
// that are invisible to time-domain analysis, thats not random.
//
// Interface:
//   compute_entropy_fft(signal, n)  → double  (Shannon entropy from FFT magnitudes)
//   detect_periodic_anomaly(signal, n) → bool  (FFT-based wash trading detector)
//   power_spectral_entropy(signal, n) → double (power spectral density entropy)
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0

#include <cmath>
#include <complex>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <vector>
#include <algorithm>
#include <numeric>
#include <string>
#include <iostream>
#include <cstdint>

using Complex = std::complex<double>;
using namespace std;


// ── Cooley-Tukey FFT (in-place, radix-2, DIT) ─────────────────────────────────

static void fft_inplace(vector<Complex>& a, bool inverse) {
    int n = static_cast<int>(a.size());
    // Bit-reversal permutation
    for (int i = 1, j = 0; i < n; ++i) {
        int bit = n >> 1;
        for (; j & bit; bit >>= 1)
            j ^= bit;
        j ^= bit;
        if (i < j) swap(a[i], a[j]);
    }
    // FFT butterfly stages
    for (int len = 2; len <= n; len <<= 1) {
        double ang = 2.0 * M_PI / len * (inverse ? -1 : 1);
        Complex wlen(cos(ang), sin(ang));
        for (int i = 0; i < n; i += len) {
            Complex w(1.0, 0.0);
            for (int j = 0; j < len / 2; ++j) {
                Complex u = a[i + j];
                Complex v = a[i + j + len / 2] * w;
                a[i + j]           = u + v;
                a[i + j + len / 2] = u - v;
                w *= wlen;
            }
        }
    }
    if (inverse) {
        for (auto& x : a)
            x /= static_cast<double>(n);
    }
}


// ── Shannon Entropy from FFT Magnitude Spectrum ────────────────────────────────
//
// Behavioral flows exhibit low spectral entropy when natural (organic activity
// has irregular, broadband frequency distribution). Manipulation (wash trading,
// MEV bots) produces periodic patterns — narrow peaks in the FFT spectrum —
// yielding low spectral entropy.
//
// Formula: H_fft = -Σ p_k · log2(p_k)  where p_k = |X_k|² / Σ|X_j|²
//
// This is the Power Spectral Density (PSD) entropy — equivalent to the
// Shannon entropy applied to the normalized power spectrum.

double compute_entropy_fft(const vector<double>& signal) {
    int n = static_cast<int>(signal.size());
    if (n == 0) return 0.0;

    // Zero-pad to next power of 2
    int m = 1;
    while (m < n) m <<= 1;

    vector<Complex> a(m, {0.0, 0.0});
    for (int i = 0; i < n; ++i)
        a[i] = Complex(signal[i], 0.0);

    fft_inplace(a, false);

    // Compute power spectrum |X_k|² for k = 0..m/2 (one-sided)
    int half = m / 2 + 1;
    vector<double> power(half);
    for (int k = 0; k < half; ++k)
        power[k] = norm(a[k]);  // |X_k|²

    double total_power = accumulate(power.begin(), power.end(), 0.0);
    if (total_power <= 0.0) return 0.0;

    // Normalize to probability distribution
    double entropy = 0.0;
    for (int k = 0; k < half; ++k) {
        double p = power[k] / total_power;
        if (p > 1e-15)
            entropy -= p * log2(p);
    }

    // Normalize to [0, 1] by dividing by max possible entropy log2(half)
    double max_entropy = log2(static_cast<double>(half));
    if (max_entropy > 0.0)
        entropy /= max_entropy;

    return min(1.0, max(0.0, entropy));
}


// ── Periodic Anomaly Detector ─────────────────────────────────────────────────
//
// Wash trading and MEV bots operate on fixed schedules (every N blocks, every
// M seconds). This function detects unusually dominant frequency components —
// a signal of synthetic, clock-driven activity.
//
// Anomaly condition: any spectral peak has PSD concentration > threshold.
// threshold = 0.15 means any single frequency holds >15% of total power.

bool detect_periodic_anomaly(const vector<double>& signal, double threshold = 0.15) {
    int n = static_cast<int>(signal.size());
    if (n < 4) return false;

    int m = 1;
    while (m < n) m <<= 1;

    vector<Complex> a(m, {0.0, 0.0});
    for (int i = 0; i < n; ++i)
        a[i] = Complex(signal[i], 0.0);
    fft_inplace(a, false);

    int half = m / 2 + 1;
    double total = 0.0;
    vector<double> power(half);
    for (int k = 1; k < half; ++k) {  // skip DC component (k=0)
        power[k] = norm(a[k]);
        total += power[k];
    }
    if (total <= 0.0) return false;

    for (int k = 1; k < half; ++k) {
        if (power[k] / total > threshold)
            return true;  // dominant frequency detected — manipulation fingerprint
    }
    return false;
}


// ── Power Spectral Density Entropy (normalized) ────────────────────────────────
//
// Returns the entropy of the power spectral density normalized to [0, 1].
// Used as a feature for the Φ (Physical) plane entropy vector.
// Organic flows: high PSD entropy (broadband).
// Bot/manipulation: low PSD entropy (narrowband, periodic).

double power_spectral_entropy(const vector<double>& signal) {
    return compute_entropy_fft(signal);
}


// ── Behavioral Autocorrelation ─────────────────────────────────────────────────
//
// Computes the normalized autocorrelation of a behavioral signal at lag τ.
// R(τ) = Σ x(t)·x(t+τ) / Σ x(t)²
// High R(τ) at small τ = momentum (organic growth).
// Periodic spikes in R(τ) = wash trading (manipulated rhythm).

vector<double> autocorrelation(const vector<double>& signal, int max_lag = -1) {
    int n = static_cast<int>(signal.size());
    if (max_lag < 0 || max_lag > n / 2)
        max_lag = n / 2;

    double mean = accumulate(signal.begin(), signal.end(), 0.0) / n;
    double variance = 0.0;
    for (double x : signal)
        variance += (x - mean) * (x - mean);

    vector<double> result(max_lag + 1, 0.0);
    if (variance <= 0.0) return result;

    for (int lag = 0; lag <= max_lag; ++lag) {
        double sum = 0.0;
        for (int i = 0; i < n - lag; ++i)
            sum += (signal[i] - mean) * (signal[i + lag] - mean);
        result[lag] = sum / variance;
    }
    return result;
}


// ── CLI bridge mode ───────────────────────────────────────────────────────────
//
// `fft_engine --stdin` reads a JSON array of doubles from stdin (one line) and
// prints `{"entropy_fft":...,"periodic_anomaly":...,"psd_entropy":...}` to
// stdout. This is the call boundary used by src/native_bridge.py to invoke
// this engine from the live Python physical-plane pipeline (see
// TRION_AUDIT_REPORT.md finding S5 / P3-14 — wiring existing native code into
// the running services instead of leaving it disconnected).
static int run_stdin_bridge() {
    std::string line, all;
    while (std::getline(std::cin, line)) all += line;

    vector<double> signal;
    double val = 0.0;
    bool in_num = false;
    std::string num_buf;
    for (char c : all) {
        if ((c >= '0' && c <= '9') || c == '.' || c == '-' || c == 'e' || c == 'E' || c == '+') {
            num_buf += c;
            in_num = true;
        } else if (in_num) {
            signal.push_back(atof(num_buf.c_str()));
            num_buf.clear();
            in_num = false;
        }
    }
    if (in_num) signal.push_back(atof(num_buf.c_str()));

    if (signal.empty()) {
        printf("{\"error\":\"empty signal\"}\n");
        return 1;
    }

    double h        = compute_entropy_fft(signal);
    bool anomaly    = detect_periodic_anomaly(signal, 0.15);
    double psd_h    = power_spectral_entropy(signal);
    printf("{\"entropy_fft\":%.6f,\"periodic_anomaly\":%s,\"psd_entropy\":%.6f,\"n\":%d}\n",
           h, anomaly ? "true" : "false", psd_h, static_cast<int>(signal.size()));
    return 0;
}


// ── Self-test ─────────────────────────────────────────────────────────────────

#ifndef TRION_FFT_NO_MAIN
int main(int argc, char** argv) {
    if (argc > 1 && std::string(argv[1]) == "--stdin") {
        return run_stdin_bridge();
    }
    printf("TRION Protocol — C++ FFT Engine self-test\n");
    printf("─────────────────────────────────────────\n");

    // Test 1: Organic signal — high entropy (broadband pseudo-random noise).
    // NOTE: a pure sinusoid mix is itself narrowband and trips the periodicity
    // detector; real organic traffic is broadband. Use a deterministic
    // xorshift PRNG so the test is reproducible without <random> overhead.
    vector<double> organic;
    {
        uint64_t rng_state = 0x9E3779B97F4A7C15ULL;  // fixed seed
        for (int i = 0; i < 64; ++i) {
            rng_state ^= rng_state << 13;
            rng_state ^= rng_state >> 7;
            rng_state ^= rng_state << 17;
            organic.push_back(0.5 + 0.35 * ((double)(rng_state >> 11) / 9007199254740992.0) * 2.0 - 0.35);
        }
    }
    double h_organic = compute_entropy_fft(organic);
    printf("  Organic signal entropy:   %.4f\n", h_organic);

    // Test 2: Wash trading signal — periodic, low entropy (dominant frequency)
    vector<double> wash_trade;
    for (int i = 0; i < 64; ++i)
        wash_trade.push_back(1.0 + 0.95 * sin(2.0 * M_PI * i / 8.0));  // strict 8-block cycle
    double h_wash = compute_entropy_fft(wash_trade);
    printf("  Wash-trade entropy:       %.4f\n", h_wash);

    // Test 3: Periodic anomaly detection
    bool organic_ok  = !detect_periodic_anomaly(organic, 0.15);
    bool wash_ok     =  detect_periodic_anomaly(wash_trade, 0.15);
    printf("  Organic anomaly=false:    %s\n", organic_ok  ? "PASS" : "FAIL");
    printf("  Wash-trade anomaly=true:  %s\n", wash_ok     ? "PASS" : "FAIL");

    // Test 4: High entropy > low entropy (organic > wash trade)
    bool entropy_order = h_organic > h_wash;
    printf("  Entropy order (org>wash): %s\n", entropy_order ? "PASS" : "FAIL");

    // Test 5: Autocorrelation at lag 0 = 1.0 always
    auto acf = autocorrelation(organic, 5);
    bool acf_ok = (acf[0] > 0.999);
    printf("  Autocorrelation R(0)=1:   %s\n", acf_ok ? "PASS" : "FAIL");

    printf("─────────────────────────────────────────\n");
    bool all_pass = organic_ok && wash_ok && entropy_order && acf_ok;
    printf("TRION C++ FFT Engine: %s\n", all_pass ? "ALL PASS" : "FAILURES DETECTED");
    return all_pass ? 0 : 1;
}
#endif  // TRION_FFT_NO_MAIN
