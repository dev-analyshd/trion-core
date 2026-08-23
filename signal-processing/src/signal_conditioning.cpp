// TRION Signal Conditioning — pre-processing for FFT engine
// Filters and conditions raw sensor signals before spectral analysis
#include <vector>
#include <cmath>
#include <algorithm>

namespace trion {

// Moving average filter
std::vector<double> moving_average(const std::vector<double>& signal, int window) {
    std::vector<double> result(signal.size());
    for (size_t i = 0; i < signal.size(); ++i) {
        double sum = 0;
        int count = 0;
        for (int j = -window/2; j <= window/2; ++j) {
            int idx = static_cast<int>(i) + j;
            if (idx >= 0 && idx < static_cast<int>(signal.size())) {
                sum += signal[idx];
                ++count;
            }
        }
        result[i] = sum / std::max(count, 1);
    }
    return result;
}

// Hanning window
std::vector<double> hanning_window(int n) {
    std::vector<double> w(n);
    for (int i = 0; i < n; ++i) {
        w[i] = 0.5 * (1.0 - std::cos(2.0 * M_PI * i / (n - 1)));
    }
    return w;
}

} // namespace trion
