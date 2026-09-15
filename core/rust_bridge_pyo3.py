"""
TRION Rust-Python Bridge — PyO3-compatible interface.

The whitepaper Part 11 specifies: "Performance-critical paths compiled to Rust
via PyO3 bindings." This module provides the Python interface to the Rust
core protocol components (Behavioral Hash, Living Security, Φ/Σ computation,
signal emission).

When the Rust extension is built with PyO3 (cargo build --features pyo3),
this module loads the native extension. When the extension is not available,
it falls back to the Python reference implementations in core/primitives/.

Build instructions:
    cd rust/
    cargo build --release --features pyo3
    # The resulting .so/.dylib is importable as trion_rust_ext
"""
import os
import sys
import ctypes
import logging
from pathlib import Path
from typing import Optional

_log = logging.getLogger(__name__)

# Try to load the native Rust extension
_RUST_EXT = None
_RUST_LIB_PATH = None

def _find_rust_ext():
    """Find the compiled Rust extension library."""
    global _RUST_EXT, _RUST_LIB_PATH
    
    # Check common locations
    repo_root = Path(__file__).parent.parent
    candidates = [
        repo_root / "rust" / "target" / "release" / "libtrion_rust.so",
        repo_root / "rust" / "target" / "release" / "libtrion_rust.dylib",
        repo_root / "rust" / "target" / "release" / "trion_rust.dll",
        repo_root / "rust" / "target" / "release" / "libtrion_rust_ext.so",
        repo_root / "rust" / "target" / "release" / "libtrion_rust_ext.dylib",
    ]
    
    for path in candidates:
        if path.exists():
            try:
                _RUST_EXT = ctypes.CDLL(str(path))
                _RUST_LIB_PATH = str(path)
                _log.info(f"Loaded Rust extension: {path}")
                return True
            except Exception as e:
                _log.debug(f"Failed to load {path}: {e}")
    
    # Try importing as a Python extension module (if built with pyo3 + maturin)
    try:
        import trion_rust_ext
        _RUST_EXT = trion_rust_ext
        _RUST_LIB_PATH = "python_module"
        _log.info("Loaded Rust extension via Python module")
        return True
    except ImportError:
        pass
    
    _log.info("Rust extension not found — using Python fallback implementations")
    return False


def is_native_available() -> bool:
    """Check if the native Rust extension is available."""
    return _RUST_EXT is not None


def get_rust_lib_path() -> Optional[str]:
    """Get the path to the loaded Rust library."""
    return _RUST_LIB_PATH


# --- Behavioral Hash (L0.1) ---

def compute_behavioral_hash_native(entity_id: bytes, event_type: int,
                                    magnitude: float, context: bytes,
                                    timestamp: int, chain_id: int,
                                    block_hash: bytes) -> tuple:
    """
    Compute the canonical Behavioral Hash using the Rust implementation.
    
    Returns (sense: bytes, antisense: bytes) — the dual-strand DNA hash.
    
    Falls back to Python implementation if Rust extension is not available.
    """
    if _RUST_EXT is None:
        # Fallback to Python
        from core.primitives.behavioral_hash import hash_dna, canonical_magnitude_norm
        from core.primitives.behavioral_hash import EventType
        mag_norm = canonical_magnitude_norm(int(magnitude), 18)
        payload = (
            entity_id +
            bytes([event_type]) +
            int(mag_norm * 1e9).to_bytes(8, 'big') +
            context[:8].ljust(8, b'\x00') +
            timestamp.to_bytes(8, 'big') +
            chain_id.to_bytes(4, 'big') +
            block_hash
        )
        sense, antisense = hash_dna(payload)
        return sense, antisense
    
    # Native path (when Rust extension is built)
    # The Rust function signature would be:
    # extern "C" fn compute_bh(entity_id: *const u8, entity_id_len: usize, ...) -> *mut BHResult
    # For now, we document the interface; actual FFI calls require the Rust
    # crate to export C-compatible functions.
    raise NotImplementedError(
        "Native Rust FFI not yet implemented. Build with: cd rust/ && cargo build --release --features pyo3"
    )


# --- Φ Score (L1.1) ---

def compute_phi_native(features: list) -> float:
    """
    Compute Physical Richness Score (Φ) using the Rust implementation.
    
    Falls back to Python if Rust extension is not available.
    """
    if _RUST_EXT is None:
        from core.physical.phi_engine import compute_phi
        result = compute_phi(features)
        return result.get('phi', 0.0)
    
    raise NotImplementedError("Native Φ computation requires Rust FFI")


# --- Living Security (L4.3-4.6) ---

def compute_genomic_key_native(prev_key: bytes, behavioral_events: bytes,
                                threat_map: bytes, consensus_state: bytes) -> tuple:
    """
    Evolve a Genomic Key using the Rust implementation.
    
    Falls back to Python if Rust extension is not available.
    """
    if _RUST_EXT is None:
        from core.spiritual.living_security import GenomicKeyEvolver, GenomicKeyState
        evolver = GenomicKeyEvolver()
        state = GenomicKeyState(
            sense=prev_key[:32],
            antisense=prev_key[32:],
            generation=0,
            rotation_trigger="manual",
            h_environment=b'\x00' * 32,
            last_rotation=0,
        )
        new_state = evolver.evolve(state, behavioral_events, threat_map, consensus_state)
        return new_state.sense, new_state.antisense
    
    raise NotImplementedError("Native Genomic Key requires Rust FFI")


def compute_bootstrap_weight_native(akashic_depth: int) -> float:
    """
    Compute bootstrap weight e^(-λ·D) using Rust.
    
    Falls back to Python if Rust extension is not available.
    """
    if _RUST_EXT is None:
        from core.spiritual.living_security import bootstrap_weight
        return bootstrap_weight(akashic_depth)
    
    raise NotImplementedError("Native bootstrap weight requires Rust FFI")


# --- Signal Emission (L5.4) ---

def compute_master_equation_native(coherence: float, threshold: float,
                                    signal_value: float, moat: float,
                                    time_years: float) -> float:
    """
    Compute the TRION Master Equation T(t) using Rust.
    
    Falls back to Python if Rust extension is not available.
    """
    if _RUST_EXT is None:
        from core.master.master_equation import MasterEquation
        me = MasterEquation()
        result = me.compute(coherence, threshold, signal_value, moat, time_years)
        return result.get('T', 0.0)
    
    raise NotImplementedError("Native Master Equation requires Rust FFI")


# Initialize on import
_find_rust_ext()
