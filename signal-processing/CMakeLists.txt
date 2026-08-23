cmake_minimum_required(VERSION 3.16)
project(trion_cpp VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Optimization flags — needed for FFT performance
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -ffast-math")

# ── Sources live in src/ ─────────────────────────────────────────────────────
add_executable(trion_fft_engine src/fft_engine.cpp)
target_compile_options(trion_fft_engine PRIVATE -Wall -Wextra)

add_executable(trion_sensor_interface src/sensor_interface.cpp)
target_compile_options(trion_sensor_interface PRIVATE -Wall -Wextra)

# Signal conditioning utility (header-only style compilation, no main)
add_library(signal_conditioning STATIC src/signal_conditioning.cpp)
target_compile_options(signal_conditioning PRIVATE -Wall -Wextra)

# ── Tests ─────────────────────────────────────────────────────────────────────
enable_testing()
add_test(NAME fft_engine_self_test       COMMAND trion_fft_engine)
add_test(NAME sensor_interface_self_test COMMAND trion_sensor_interface)

# ── Build instructions ────────────────────────────────────────────────────────
# mkdir -p build && cd build
# cmake .. -DCMAKE_BUILD_TYPE=Release
# cmake --build . -j$(nproc)
# ctest --output-on-failure
