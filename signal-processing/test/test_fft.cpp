// TRION FFT Engine Tests
#include "../src/fft_engine.cpp"
#include <cassert>
#include <iostream>

int main() {
    // Test 1: Organic signal has high entropy
    std::vector<double> organic(64);
    for (size_t i = 0; i < organic.size(); ++i) {
        organic[i] = 0.5 + 0.3 * std::sin(i * 0.5) + 0.2 * std::cos(i * 1.3);
    }
    double organic_entropy = compute_entropy_fft(organic);
    assert(organic_entropy > 0.5);
    std::cout << "Test 1 PASS: organic entropy = " << organic_entropy << std::endl;

    // Test 2: Wash-trade signal has low entropy
    std::vector<double> wash(64);
    for (size_t i = 0; i < wash.size(); ++i) {
        wash[i] = (i % 10 == 0) ? 1.0 : 0.0;  // Periodic spikes
    }
    double wash_entropy = compute_entropy_fft(wash);
    assert(wash_entropy < organic_entropy);
    std::cout << "Test 2 PASS: wash entropy = " << wash_entropy << std::endl;

    std::cout << "All FFT tests passed" << std::endl;
    return 0;
}
