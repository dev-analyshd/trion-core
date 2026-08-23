/*!
 * TRION FFT Engine unit tests (linked against the engine sources, no main conflict).
 * Build: g++ -std=c++17 -O2 -I../src ../src/fft_engine.cpp test_fft.cpp -o test_fft
 * (fft_engine.cpp's main() is compiled out via TRION_FFT_NO_MAIN)
 */
#define TRION_FFT_NO_MAIN
#include "../src/fft_engine.cpp"
#include <cassert>
#include <cstdio>
#include <cstdint>

int main() {
    printf("TRION FFT Engine — unit tests\n");

    // 1. Entropy of broadband noise > entropy of pure tone.
    std::vector<double> noise;
    {
        uint64_t s = 0xDEADBEEFCAFEBABEULL;
        for (int i = 0; i < 128; ++i) {
            s ^= s << 13; s ^= s >> 7; s ^= s << 17;
            noise.push_back(((double)(s >> 11) / 9007199254740992.0) - 0.5);
        }
    }
    std::vector<double> tone;
    for (int i = 0; i < 128; ++i)
        tone.push_back(std::sin(2.0 * M_PI * i / 16.0));

    double h_noise = compute_entropy_fft(noise);
    double h_tone  = compute_entropy_fft(tone);
    assert(h_noise > h_tone);
    printf("  broadband entropy %.4f > tone entropy %.4f: PASS\n", h_noise, h_tone);

    // 2. Periodic anomaly fires on strict cycle.
    std::vector<double> wash;
    for (int i = 0; i < 64; ++i)
        wash.push_back(1.0 + 0.95 * std::sin(2.0 * M_PI * i / 8.0));
    assert(detect_periodic_anomaly(wash, 0.15));
    printf("  wash-trade cycle detected: PASS\n");

    // 3. Broadband noise does NOT fire anomaly detector.
    assert(!detect_periodic_anomaly(noise, 0.15));
    printf("  broadband not flagged: PASS\n");

    // 4. Autocorrelation lag-0 == 1.
    auto acf = autocorrelation(noise, 8);
    assert(acf[0] > 0.9999);
    printf("  ACF(0)=1: PASS\n");

    // 5. FFT round-trip: inverse(forward(x)) == x.
    std::vector<std::complex<double>> sig = {
        {0.5, 0}, {-0.2, 0}, {0.8, 0}, {0.1, 0},
        {-0.6, 0}, {0.3, 0}, {0.9, 0}, {-0.4, 0}
    };
    auto reference = sig;
    fft_inplace(sig, false);
    fft_inplace(sig, true);
    for (size_t i = 0; i < reference.size(); ++i)
        assert(std::abs(sig[i] - reference[i]) < 1e-9);
    printf("  FFT round-trip identity: PASS\n");

    printf("ALL FFT UNIT TESTS PASS\n");
    return 0;
}
