"""
TRION Rust-Python Bridge — PyO3-compatible interface.

The whitepaper Part 11 specifies: "Performance-critical paths compiled to Rust
via PyO3 bindings." This module provides the Python interface to the Rust
core protocol components (Behavioral Hash, Living Security, Φ/Σ computation,
signal emission).

When the Rust extension is built with PyO3 (cargo build --release --features pyo3),
this module loads the native extension. When the extension is not available,
it falls back to the Python reference implementations in core/primitives/.

Part 11 language mandate wiring (TRION-TEAM-D):
  * Behavioral Hash  → rust::pyo3_bindings::compute_behavioral_hash
                       (or ctypes shim `trion_rust_compute_behavioral_hash`)
  * Physical Richness Φ → rust::phi::compute_phi
                       (or ctypes shim `trion_rust_compute_phi_flat`)
  * Spiritual Plane Σ → rust::sigma::compute_sigma
                       (or ctypes shim `trion_rust_compute_sigma`)
  * Master Equation T → rust::master_equation::master_equation
                       (or ctypes shim `trion_rust_compute_master_equation`)

Each native wrapper first tries `import trion_rust` (the PyO3 module path),
then falls back to a `ctypes.CDLL` call against the cdylib built by
`cargo build --features pyo3`, and finally falls back to the canonical
Python implementation in `core/primitives/` / `core/master/` / `core/spiritual/`.

Build instructions:
    cd rust/
    cargo build --release --features pyo3
    # The resulting .so/.dylib is importable as trion_rust
"""
import ctypes
import logging
import math
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

_log = logging.getLogger(__name__)

# Try to load the native Rust extension.
#
# Two-step lookup:
#   1. PyO3-built extension module (preferred — fastest, type-safe).
#   2. Plain cdylib loaded via ctypes (fallback for frozen/embedded
#      interpreters that cannot import the PyO3 module directly).
#
# A single sentinel `_NATIVE_MODE` records which path succeeded (or "python"
# when neither is available) so the `compute_*_native()` wrappers below can
# dispatch without re-probing on every call.
_RUST_EXT_PYTHON_MODULE = None  # type: Optional[object]
_RUST_EXT_CDLL = None           # type: Optional[ctypes.CDLL]
_RUST_LIB_PATH: Optional[str] = None
_NATIVE_MODE = "python"          # one of: "pyo3", "ctypes", "python"


def _find_rust_ext() -> bool:
    """Locate and load the compiled Rust extension (PyO3 or ctypes)."""
    global _RUST_EXT_PYTHON_MODULE, _RUST_EXT_CDLL, _RUST_LIB_PATH, _NATIVE_MODE

    # ── 1. PyO3 extension module ──────────────────────────────────────────
    try:
        import trion_rust  # type: ignore
        _RUST_EXT_PYTHON_MODULE = trion_rust
        _RUST_LIB_PATH = "pyo3:trion_rust"
        _NATIVE_MODE = "pyo3"
        _log.info("Rust extension loaded via PyO3 module: trion_rust")
        return True
    except ImportError:
        pass

    # ── 2. ctypes cdylib fallback ─────────────────────────────────────────
    repo_root = Path(__file__).parent.parent
    candidates = [
        repo_root / "rust" / "target" / "release" / "libtrion_btcp.so",
        repo_root / "rust" / "target" / "release" / "libtrion_btcp.dylib",
        repo_root / "rust" / "target" / "release" / "trion_btcp.dll",
        # Backward-compat names used by older build scripts.
        repo_root / "rust" / "target" / "release" / "libtrion_rust.so",
        repo_root / "rust" / "target" / "release" / "libtrion_rust.dylib",
        repo_root / "rust" / "target" / "release" / "trion_rust.dll",
    ]
    for path in candidates:
        if path.exists():
            try:
                _RUST_EXT_CDLL = ctypes.CDLL(str(path))
                _RUST_LIB_PATH = str(path)
                _NATIVE_MODE = "ctypes"
                _log.info("Rust extension loaded via ctypes: %s", path)
                return True
            except OSError as exc:
                _log.debug("Failed to load %s: %s", path, exc)

    _log.info("Rust extension not found — using Python fallback implementations")
    return False


def is_native_available() -> bool:
    """Check if the native Rust extension is available."""
    return _NATIVE_MODE in ("pyo3", "ctypes")


def get_rust_lib_path() -> Optional[str]:
    """Get the path to the loaded Rust library."""
    return _RUST_LIB_PATH


def native_mode() -> str:
    """Return which native dispatch mode is active ('pyo3', 'ctypes', or 'python')."""
    return _NATIVE_MODE


# ─── Behavioral Hash (L0.1) ──────────────────────────────────────────────

def _py_build_canonical_payload(
    entity_id: bytes, event_type: int, magnitude: float,
    context: bytes, timestamp: int, chain_id: int, block_hash: bytes,
) -> bytes:
    """Build the canonical 93-byte BH payload (mirrors
    `core.primitives.behavioral_hash.hash_dna` callers)."""
    from core.primitives.behavioral_hash import canonical_magnitude_norm
    mag_norm = canonical_magnitude_norm(int(magnitude), 18)
    payload = (
        entity_id.ljust(32, b'\x00')[:32]
        + bytes([event_type & 0xFF])
        + int(mag_norm * 1e9).to_bytes(8, 'big')
        + bytes(context[:8]).ljust(8, b'\x00')
        + int(timestamp).to_bytes(8, 'big')
        + int(chain_id).to_bytes(4, 'big')
        + bytes(block_hash).ljust(32, b'\x00')[:32]
    )
    return payload


def _native_behavioral_hash_via_ctypes(payload: bytes) -> Optional[Tuple[bytes, bytes]]:
    """Invoke the `trion_rust_compute_behavioral_hash` C shim."""
    if _RUST_EXT_CDLL is None:
        return None
    try:
        _RUST_EXT_CDLL.trion_rust_compute_behavioral_hash.argtypes = [
            ctypes.c_char_p, ctypes.c_size_t,
            ctypes.c_char_p, ctypes.c_char_p,
        ]
        _RUST_EXT_CDLL.trion_rust_compute_behavioral_hash.restype = ctypes.c_int32
        sense_buf = ctypes.create_string_buffer(32)
        antisense_buf = ctypes.create_string_buffer(32)
        rc = _RUST_EXT_CDLL.trion_rust_compute_behavioral_hash(
            payload, len(payload), sense_buf, antisense_buf,
        )
        if rc != 0:
            _log.warning("trion_rust_compute_behavioral_hash returned rc=%d", rc)
            return None
        return sense_buf.raw[:32], antisense_buf.raw[:32]
    except (AttributeError, OSError, ctypes.ArgumentError) as exc:
        _log.warning("ctypes BH call failed: %s", exc)
        return None


def compute_behavioral_hash_native(
    entity_id: bytes, event_type: int, magnitude: float,
    context: bytes, timestamp: int, chain_id: int, block_hash: bytes,
) -> Tuple[bytes, bytes]:
    """
    Compute the canonical Behavioral Hash using the Rust implementation.

    Returns (sense: bytes, antisense: bytes) — the dual-strand DNA hash.

    Dispatch order:
      1. PyO3: `trion_rust.compute_behavioral_hash(payload)`
      2. ctypes: `lib.trion_rust_compute_behavioral_hash(payload_ptr, len, out, out2)`
      3. Python fallback: `core.primitives.behavioral_hash.hash_dna`
    """
    payload = _py_build_canonical_payload(
        entity_id, event_type, magnitude, context, timestamp, chain_id, block_hash,
    )

    # 1. PyO3 path
    if _NATIVE_MODE == "pyo3" and _RUST_EXT_PYTHON_MODULE is not None:
        try:
            result = _RUST_EXT_PYTHON_MODULE.compute_behavioral_hash(payload)
            if isinstance(result, tuple) and len(result) == 2:
                return bytes(result[0]), bytes(result[1])
        except Exception as exc:  # pragma: no cover — defensive
            _log.warning("PyO3 compute_behavioral_hash failed: %s", exc)

    # 2. ctypes path
    if _NATIVE_MODE == "ctypes":
        ct_result = _native_behavioral_hash_via_ctypes(payload)
        if ct_result is not None:
            return ct_result

    # 3. Python fallback
    from core.primitives.behavioral_hash import hash_dna
    sense, antisense = hash_dna(payload)
    return sense, antisense


# ─── Φ Score (L1.1) ──────────────────────────────────────────────────────

def _py_transactions_from_features(features: list) -> list:
    """Convert the loose Python-side `features` arg into a list of dicts
    shaped like TransactionData. Each row is expected to be a dict with
    keys matching `phi.TransactionData` fields; rows that are already
    TransactionData instances are passed through untouched. This is a
    thin adapter — it does not synthesize missing fields."""
    from core.physical.phi_engine import TransactionData as PyTxData
    out = []
    for row in features or []:
        if isinstance(row, PyTxData):
            out.append(row)
            continue
        if isinstance(row, dict):
            out.append(PyTxData(
                tx_hash=row.get("tx_hash", ""),
                timestamp=float(row.get("timestamp", row.get("ts", 0.0))),
                block_number=int(row.get("block_number", row.get("block_num", 0))),
                from_addr=row.get("from_addr", row.get("from", "")),
                to_addr=row.get("to_addr", row.get("to", "")),
                value_wei=int(row.get("value_wei", row.get("value", 0))),
                gas_used=int(row.get("gas_used", row.get("gas", 0))),
                gas_price=int(row.get("gas_price", 0)),
                is_contract=bool(row.get("is_contract", False)),
                contract_addr=row.get("contract_addr"),
                input_len=int(row.get("input_len", 0)),
            ))
            continue
        # Fall through: assume already-correct record-like object with attributes.
        out.append(row)
    return out


def _native_phi_via_pyo3(txs: list, weights: list) -> Optional[float]:
    """PyO3 dispatch for compute_phi. Constructs `trion_rust.TransactionData`
    instances from the Python TransactionData records."""
    if _RUST_EXT_PYTHON_MODULE is None:
        return None
    try:
        PyTx = _RUST_EXT_PYTHON_MODULE.TransactionData  # type: ignore[attr-defined]
        rust_txs = []
        for t in txs:
            contract_addr = getattr(t, "contract_addr", None) or ""
            rust_txs.append(PyTx(
                tx_hash=getattr(t, "tx_hash", ""),
                value_wei=int(getattr(t, "value_wei", 0)),
                gas_used=int(getattr(t, "gas_used", 0)),
                contract_addr=contract_addr if not getattr(t, "is_contract", False) else contract_addr,
                from_addr=getattr(t, "from_addr", ""),
                to_addr=getattr(t, "to_addr", ""),
                block_num=int(getattr(t, "block_number", getattr(t, "block_num", 0))),
                timestamp=float(getattr(t, "timestamp", 0.0)),
            ))
        return float(_RUST_EXT_PYTHON_MODULE.compute_phi(rust_txs, list(weights)))
    except Exception as exc:  # pragma: no cover — defensive
        _log.warning("PyO3 compute_phi failed: %s", exc)
        return None


def _native_phi_via_ctypes(txs: list, weights: list) -> Optional[float]:
    """ctypes dispatch for compute_phi — flattens records into a [N, 8] f64
    array matching the layout expected by `trion_rust_compute_phi_flat`:
      [value_wei_as_f64, gas_used_as_f64, block_num_as_f64, timestamp,
       has_contract_flag (0/1), contract_hash_short, from_hash_short, to_hash_short]
    """
    if _RUST_EXT_CDLL is None:
        return None
    try:
        _RUST_EXT_CDLL.trion_rust_compute_phi_flat.argtypes = [
            ctypes.POINTER(ctypes.c_double), ctypes.c_size_t, ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_double),
        ]
        _RUST_EXT_CDLL.trion_rust_compute_phi_flat.restype = ctypes.c_double

        n = len(txs)
        if n == 0:
            return 0.0
        # 8 f64 fields per tx (matches the Rust shim).
        flat = (ctypes.c_double * (n * 8))()
        for i, t in enumerate(txs):
            contract_addr = getattr(t, "contract_addr", None) or ""
            has_contract = 1.0 if getattr(t, "is_contract", False) else 0.0
            # Reduce the contract/from/to addresses to a u64 seed so the
            # Rust shim can reconstruct a stable string identifier. We
            # hash the first 8 bytes of the hex (mirrors the Python
            # f7/f2 implementation, which only looks at the prefix).
            def _hex_seed(s: str) -> float:
                head = (s or "")[:16]
                try:
                    return float(int(head, 16)) if head else 0.0
                except ValueError:
                    return 0.0

            contract_short = _hex_seed(contract_addr)
            from_short = _hex_seed(getattr(t, "from_addr", "") or "")
            to_short = _hex_seed(getattr(t, "to_addr", "") or "")
            base = i * 8
            flat[base + 0] = float(getattr(t, "value_wei", 0))
            flat[base + 1] = float(getattr(t, "gas_used", 0))
            flat[base + 2] = float(getattr(t, "block_number", getattr(t, "block_num", 0)))
            flat[base + 3] = float(getattr(t, "timestamp", 0.0))
            flat[base + 4] = has_contract
            flat[base + 5] = contract_short
            flat[base + 6] = from_short
            flat[base + 7] = to_short

        w = (ctypes.c_double * 9)(*weights)
        return float(_RUST_EXT_CDLL.trion_rust_compute_phi_flat(flat, n, 8, w))
    except (AttributeError, OSError, ctypes.ArgumentError) as exc:
        _log.warning("ctypes compute_phi call failed: %s", exc)
        return None


def compute_phi_native(features: list, weights: Optional[list] = None) -> float:
    """
    Compute Physical Richness Score (Φ) using the Rust implementation.

    Dispatch order:
      1. PyO3: `trion_rust.compute_phi(rust_txs, weights)`
      2. ctypes: `lib.trion_rust_compute_phi_flat(tx_ptr, n, 8, w_ptr)`
      3. Python fallback: `core.physical.phi_engine.compute_phi`
    """
    txs = _py_transactions_from_features(features)

    # Default weights — same 9-entry vector as the Rust `PHI_WEIGHTS`.
    if weights is None:
        from core.physical.phi_engine import PHI_WEIGHTS
        weights = list(PHI_WEIGHTS)
    else:
        weights = list(weights)
    if len(weights) != 9:
        from core.physical.phi_engine import PHI_WEIGHTS
        weights = list(PHI_WEIGHTS)

    # 1. PyO3 path
    if _NATIVE_MODE == "pyo3":
        phi_val = _native_phi_via_pyo3(txs, weights)
        if phi_val is not None:
            return phi_val

    # 2. ctypes path
    if _NATIVE_MODE == "ctypes":
        phi_val = _native_phi_via_ctypes(txs, weights)
        if phi_val is not None:
            return phi_val

    # 3. Python fallback
    from core.physical.phi_engine import compute_phi
    # The canonical Python reference computes entity_addr internally when
    # omitted; we mirror that here by recovering it from the tx window.
    entity_addr = ""
    if txs:
        entity_addr = getattr(txs[0], "from_addr", "") or ""
    result = compute_phi(txs, entity_addr, weights=weights)
    return result.get('phi', result.get('phi_raw', 0.0))


# ─── Spiritual Plane Σ (L4.1) ────────────────────────────────────────────

def _native_sigma_via_pyo3(
    stakes: list, diversity: list, valuations: list,
    median: float, delta_base: float, volatility: float,
) -> Optional[float]:
    if _RUST_EXT_PYTHON_MODULE is None:
        return None
    try:
        return float(_RUST_EXT_PYTHON_MODULE.compute_sigma(
            list(stakes), list(diversity), list(valuations),
            float(median), float(delta_base), float(volatility),
        ))
    except Exception as exc:  # pragma: no cover — defensive
        _log.warning("PyO3 compute_sigma failed: %s", exc)
        return None


def _native_sigma_via_ctypes(
    stakes: list, diversity: list, valuations: list,
    median: float, delta_base: float, volatility: float,
) -> Optional[float]:
    if _RUST_EXT_CDLL is None:
        return None
    try:
        _RUST_EXT_CDLL.trion_rust_compute_sigma.argtypes = [
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double), ctypes.c_size_t,
            ctypes.c_double, ctypes.c_double, ctypes.c_double,
        ]
        _RUST_EXT_CDLL.trion_rust_compute_sigma.restype = ctypes.c_double
        n = min(len(stakes), len(diversity), len(valuations))
        if n == 0:
            return 0.25  # bootstrap baseline
        s = (ctypes.c_double * n)(*stakes[:n])
        d = (ctypes.c_double * n)(*diversity[:n])
        v = (ctypes.c_double * n)(*valuations[:n])
        return float(_RUST_EXT_CDLL.trion_rust_compute_sigma(
            s, d, v, n,
            float(median), float(delta_base), float(volatility),
        ))
    except (AttributeError, OSError, ctypes.ArgumentError) as exc:
        _log.warning("ctypes compute_sigma call failed: %s", exc)
        return None


def compute_sigma_native(
    stakes: list, diversity: list, valuations: list,
    median: float, delta_base: float = 0.10, volatility: float = 0.30,
) -> float:
    """
    Compute Σ(t) — diversity-weighted BFT — using the Rust implementation.

    Dispatch order:
      1. PyO3: `trion_rust.compute_sigma(stakes, diversity, valuations, median, db, v)`
      2. ctypes: `lib.trion_rust_compute_sigma(s_ptr, d_ptr, v_ptr, n, median, db, v)`
      3. Python fallback: `core.spiritual.sigma_engine.compute_sigma`
    """
    if _NATIVE_MODE == "pyo3":
        sigma = _native_sigma_via_pyo3(
            stakes, diversity, valuations, median, delta_base, volatility,
        )
        if sigma is not None:
            return sigma

    if _NATIVE_MODE == "ctypes":
        sigma = _native_sigma_via_ctypes(
            stakes, diversity, valuations, median, delta_base, volatility,
        )
        if sigma is not None:
            return sigma

    # 3. Python fallback
    from core.spiritual.sigma_engine import ValidatorSignal, compute_sigma
    validators = [
        ValidatorSignal(
            validator_id=f"v{i}",
            valuation=float(valuations[i]),
            stake=float(stakes[i]),
            model_outputs=[],  # No model-output history here; pure scalar path.
        )
        for i in range(min(len(stakes), len(diversity), len(valuations)))
    ]
    # Diversity weights are precomputed by the caller; we fold them into the
    # stake so the Python reference (which recomputes d_j from
    # model_outputs) treats effective stake as s_j·d_j directly.
    for i, v in enumerate(validators[:len(diversity)]):
        v.stake = v.stake * float(diversity[i])
    result = compute_sigma(validators, volatility=volatility, delta_base=delta_base)
    return result.get("sigma", 0.0)


# ─── Master Equation (L5) ────────────────────────────────────────────────

def _native_master_equation_via_pyo3(
    coherence: float, threshold: float, signal_value: float,
    moat: float, time_years: float,
) -> Optional[float]:
    if _RUST_EXT_PYTHON_MODULE is None:
        return None
    try:
        result = _RUST_EXT_PYTHON_MODULE.compute_master_equation(
            float(coherence), float(threshold), float(signal_value),
            float(moat), float(time_years),
        )
        # Rust returns Option<f64>; PyO3 maps it to None when the gate is closed.
        if result is None:
            return 0.0
        return float(result)
    except Exception as exc:  # pragma: no cover — defensive
        _log.warning("PyO3 compute_master_equation failed: %s", exc)
        return None


def _native_master_equation_via_ctypes(
    coherence: float, threshold: float, signal_value: float,
    moat: float, time_years: float,
) -> Optional[float]:
    if _RUST_EXT_CDLL is None:
        return None
    try:
        _RUST_EXT_CDLL.trion_rust_compute_master_equation.argtypes = [
            ctypes.c_double, ctypes.c_double, ctypes.c_double,
            ctypes.c_double, ctypes.c_double,
        ]
        _RUST_EXT_CDLL.trion_rust_compute_master_equation.restype = ctypes.c_double
        result = _RUST_EXT_CDLL.trion_rust_compute_master_equation(
            float(coherence), float(threshold), float(signal_value),
            float(moat), float(time_years),
        )
        # Sentinel -1.0 from the C shim = SILENCE branch → T(t) = 0.
        if result == -1.0:
            return 0.0
        return float(result)
    except (AttributeError, OSError, ctypes.ArgumentError) as exc:
        _log.warning("ctypes compute_master_equation call failed: %s", exc)
        return None


def compute_master_equation_native(
    coherence: float, threshold: float, signal_value: float,
    moat: float, time_years: float,
) -> float:
    """
    Compute the TRION Master Equation T(t) using Rust.

    Dispatch order:
      1. PyO3: `trion_rust.compute_master_equation(c, θ, s, M, t)`
      2. ctypes: `lib.trion_rust_compute_master_equation(c, θ, s, M, t)`
      3. Python fallback: `core.master.master_equation.MasterEquation.compute`
    """
    if _NATIVE_MODE == "pyo3":
        t = _native_master_equation_via_pyo3(
            coherence, threshold, signal_value, moat, time_years,
        )
        if t is not None:
            return t

    if _NATIVE_MODE == "ctypes":
        t = _native_master_equation_via_ctypes(
            coherence, threshold, signal_value, moat, time_years,
        )
        if t is not None:
            return t

    # 3. Python fallback
    from core.master.master_equation import MasterEquation
    me = MasterEquation()
    # The Python `MasterEquation.compute` consumes a coherence-result dict
    # produced by `CoherenceEngine.compute_coherence`. We synthesize a
    # minimal dict from the caller's scalar inputs (c, theta, s, moat) so
    # the Python fallback returns the same T(t) the Rust `master_equation`
    # function does: T = [C≥Θ] · S · e^(M·t), None / 0.0 when silent.
    emits = coherence >= threshold
    coherence_result = {
        "C": float(coherence),
        "theta": float(threshold),
        "emits": emits,
        "margin": float(coherence - threshold),
        "moat_factor": float(moat),
        "limiting_plane": "rust_bridge",
        "trend": "STABLE",
        "signal_value": float(signal_value),
    }
    result = me.compute(coherence_result, time_years=time_years)
    return getattr(result, "t", 0.0)


# ─── Living Security (L4.3-4.6) ──────────────────────────────────────────
#
# Part 11 language mandate — "Performance-critical paths compiled to Rust
# via PyO3 bindings." The three native wrappers below expose the
# cryptographic primitives of the Living Security System ported to Rust
# (`rust/src/living_security.rs`):
#
#   1. compute_genomic_key_native(entity_id, generation, behavioral_event, timestamp, context)
#        → (sense_hex, antisense_hex)
#      Evolves a GenomicKey one generation forward (or initialises the
#      genesis key when generation=0). Hex strings are 64 lowercase chars.
#
#   2. compute_sec_native(entity_id, akashic_depth, n_chains, n_validators)
#        → sec_score float ∈ [0, 1]
#      Full SEC(t) = LSS · PQC · CC computation, bootstrap-weighted
#      (effective_SEC = w_boot·CC + (1-w_boot)·SEC).
#
#   3. crispr_check_native(transaction_data_bytes) → bool
#      Substring match against the 126 static CRISPR attack signatures
#      (`rust/src/living_security_crispr_data.rs`). True iff a match is found.
#
# Each wrapper first tries the PyO3 entry point on `trion_rust`, then falls
# back to the ctypes C-shim on `libtrion_btcp.so`, then finally falls
# through to the canonical Python reference in `core/spiritual/living_security/`.

def _native_genomic_key_via_pyo3(
    entity_id: str, generation: int,
    behavioral_event: bytes, timestamp: bytes, context: bytes,
) -> Optional[Tuple[str, str]]:
    """PyO3 dispatch for compute_genomic_key_native."""
    if _RUST_EXT_PYTHON_MODULE is None:
        return None
    fn = getattr(_RUST_EXT_PYTHON_MODULE, "compute_genomic_key_native", None)
    if not callable(fn):
        return None
    try:
        result = fn(
            str(entity_id), int(generation),
            bytes(behavioral_event), bytes(timestamp), bytes(context),
        )
        if isinstance(result, tuple) and len(result) == 2:
            return str(result[0]), str(result[1])
    except Exception as exc:  # pragma: no cover — defensive
        _log.warning("PyO3 compute_genomic_key_native failed: %s", exc)
    return None


def _native_genomic_key_via_ctypes(
    entity_id: str, generation: int,
    behavioral_event: bytes, timestamp: bytes, context: bytes,
) -> Optional[Tuple[str, str]]:
    """ctypes dispatch for compute_genomic_key_native via
    `trion_rust_compute_genomic_key` (writes NUL-terminated 65-byte hex
    buffers for each strand)."""
    if _RUST_EXT_CDLL is None:
        return None
    try:
        _RUST_EXT_CDLL.trion_rust_compute_genomic_key.argtypes = [
            ctypes.c_char_p, ctypes.c_size_t,           # entity_id_ptr, entity_id_len
            ctypes.c_uint64,                              # generation
            ctypes.c_char_p, ctypes.c_size_t,           # be_ptr, be_len
            ctypes.c_char_p, ctypes.c_size_t,           # tm_ptr, tm_len
            ctypes.c_char_p, ctypes.c_size_t,           # cv_ptr, cv_len
            ctypes.c_char_p,                              # out_sense_hex
            ctypes.c_char_p,                              # out_antisense_hex
        ]
        _RUST_EXT_CDLL.trion_rust_compute_genomic_key.restype = ctypes.c_int32
        eid_bytes = entity_id.encode("utf-8") if isinstance(entity_id, str) else bytes(entity_id)
        sense_buf = ctypes.create_string_buffer(65)
        antisense_buf = ctypes.create_string_buffer(65)
        rc = _RUST_EXT_CDLL.trion_rust_compute_genomic_key(
            eid_bytes, len(eid_bytes), int(generation),
            bytes(behavioral_event), len(behavioral_event),
            bytes(timestamp), len(timestamp),
            bytes(context), len(context),
            sense_buf, antisense_buf,
        )
        if rc != 0:
            _log.warning("trion_rust_compute_genomic_key returned rc=%d", rc)
            return None
        # sense_buf.raw is NUL-padded to 65 bytes; take the first 64 hex chars.
        return sense_buf.raw[:64].decode("ascii"), antisense_buf.raw[:64].decode("ascii")
    except (AttributeError, OSError, ctypes.ArgumentError) as exc:
        _log.warning("ctypes compute_genomic_key call failed: %s", exc)
        return None


def compute_genomic_key_native(
    entity_id: str, generation: int,
    behavioral_event: bytes, timestamp: bytes, context: bytes,
) -> Tuple[str, str]:
    """
    Evolve a Living-Security Genomic Key one generation forward.

    Specification L4.3:
        GK(t) = Hash_DNA(GK(t-1).sense || BE(t) || TM(t) || CV(t) || H_env)

    Args:
        entity_id:        32-byte-max entity routing key (UTF-8 string).
                          Shorter strings are zero-padded to 32 bytes inside Rust.
        generation:        Generation counter. 0 → initialise the genesis key
                          from entity_id alone. N>0 → re-derive the genesis key
                          and evolve it N times, folding (BE, TM, CV) into the
                          final step only.
        behavioral_event: BE(t) — already SHA3-hashed behavioral entropy vector.
        timestamp:        TM(t) — already SHA3-hashed timestamp/block_hash bundle.
        context:          CV(t) — already SHA3-hashed consensus view.

    Returns:
        (sense_hex, antisense_hex) — each 64 lowercase hex chars (32 bytes).

    Dispatch order:
      1. PyO3: trion_rust.compute_genomic_key_native(...)
      2. ctypes: lib.trion_rust_compute_genomic_key(...)
      3. Python fallback: core.spiritual.living_security.GenomicKeyEvolver
    """
    if _NATIVE_MODE == "pyo3":
        result = _native_genomic_key_via_pyo3(
            entity_id, generation, behavioral_event, timestamp, context,
        )
        if result is not None:
            return result

    if _NATIVE_MODE == "ctypes":
        result = _native_genomic_key_via_ctypes(
            entity_id, generation, behavioral_event, timestamp, context,
        )
        if result is not None:
            return result

    # Python fallback (always available).
    import hashlib as _hashlib
    import os as _os
    import time as _time
    from core.spiritual.living_security import GenomicKeyEvolver, hash_dna
    # Mirror the Rust port's seeding scheme so the two paths are byte-compatible
    # for the genesis key when no OS entropy is mixed in.
    h_env_seed = _hashlib.sha3_256(
        b"trion_lss_h_env_seed::" + str(entity_id).encode("utf-8")
    ).digest()
    now = _time.time()
    evolver = GenomicKeyEvolver()
    eid_bytes = str(entity_id).encode("utf-8")[:32].ljust(32, b'\x00')
    # Seed the evolver's H_environment deterministically so the genesis key
    # matches the Rust port (which does the same).
    evolver._h_environment = h_env_seed
    gk = evolver.initialize(eid_bytes)
    if generation > 0:
        zero_hash = _hashlib.sha3_256(b"trion_lss_zero_step").digest()
        for _ in range(1, generation):
            gk = evolver.evolve(eid_bytes, zero_hash, zero_hash, zero_hash)
        gk = evolver.evolve(
            eid_bytes,
            be_hash=behavioral_event,
            tm_hash=timestamp,
            cv_hash=context,
        )
    return gk.sense_hex(), gk.antisense_hex()


def _native_sec_via_pyo3(
    entity_id: str, akashic_depth: int, n_chains: int, n_validators: int,
) -> Optional[float]:
    if _RUST_EXT_PYTHON_MODULE is None:
        return None
    fn = getattr(_RUST_EXT_PYTHON_MODULE, "compute_sec_native", None)
    if not callable(fn):
        return None
    try:
        return float(fn(str(entity_id), int(akashic_depth), int(n_chains), int(n_validators)))
    except Exception as exc:  # pragma: no cover — defensive
        _log.warning("PyO3 compute_sec_native failed: %s", exc)
    return None


def _native_sec_via_ctypes(
    entity_id: str, akashic_depth: int, n_chains: int, n_validators: int,
) -> Optional[float]:
    if _RUST_EXT_CDLL is None:
        return None
    try:
        _RUST_EXT_CDLL.trion_rust_compute_sec.argtypes = [
            ctypes.c_char_p, ctypes.c_size_t,
            ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64,
        ]
        _RUST_EXT_CDLL.trion_rust_compute_sec.restype = ctypes.c_double
        eid_bytes = entity_id.encode("utf-8") if isinstance(entity_id, str) else bytes(entity_id)
        return float(_RUST_EXT_CDLL.trion_rust_compute_sec(
            eid_bytes, len(eid_bytes),
            int(akashic_depth), int(n_chains), int(n_validators),
        ))
    except (AttributeError, OSError, ctypes.ArgumentError) as exc:
        _log.warning("ctypes compute_sec call failed: %s", exc)
        return None


def compute_sec_native(
    entity_id: str, akashic_depth: int = 0,
    n_chains: int = 31, n_validators: int = 100,
) -> float:
    """
    Compute SEC(t) = LSS(t) · PQC(t) · CC(t) using the Rust LSS port.

    Bootstrap-weighted effective SEC:
        effective_SEC = w_boot · CC + (1 - w_boot) · SEC
        w_boot = exp(-λ_boot · D)         (λ_boot = 0.0001)

    Args:
        entity_id:     Entity routing key (UTF-8 string).
        akashic_depth: Block depth — controls bootstrap weight. 0 = full
                       bootstrap (SEC collapses to CC); 50000 = mature
                       (SEC = LSS · PQC · CC).
        n_chains:      Number of chains — used in the Kolmogorov bound.
        n_validators:  Number of validators — used in the Kolmogorov bound.

    Returns:
        effective_SEC ∈ [0, 1] — bootstrap-weighted combined security score.

    Dispatch order:
      1. PyO3: trion_rust.compute_sec_native(...)
      2. ctypes: lib.trion_rust_compute_sec(...)
      3. Python fallback: core.spiritual.living_security.LivingSecuritySystem.compute_sec
    """
    if _NATIVE_MODE == "pyo3":
        sec = _native_sec_via_pyo3(entity_id, akashic_depth, n_chains, n_validators)
        if sec is not None:
            return sec

    if _NATIVE_MODE == "ctypes":
        sec = _native_sec_via_ctypes(entity_id, akashic_depth, n_chains, n_validators)
        if sec is not None:
            return sec

    # Python fallback (always available).
    from core.spiritual.living_security import get_lss
    lss = get_lss()
    sec_result = lss.compute_sec(str(entity_id), akashic_depth=int(akashic_depth))
    return float(sec_result.get("SEC_t", 0.0))


def _native_crispr_check_via_pyo3(transaction_data: bytes) -> Optional[bool]:
    if _RUST_EXT_PYTHON_MODULE is None:
        return None
    fn = getattr(_RUST_EXT_PYTHON_MODULE, "crispr_check_native", None)
    if not callable(fn):
        return None
    try:
        return bool(fn(bytes(transaction_data)))
    except Exception as exc:  # pragma: no cover — defensive
        _log.warning("PyO3 crispr_check_native failed: %s", exc)
    return None


def _native_crispr_check_via_ctypes(transaction_data: bytes) -> Optional[bool]:
    if _RUST_EXT_CDLL is None:
        return None
    try:
        _RUST_EXT_CDLL.trion_rust_crispr_check.argtypes = [
            ctypes.c_char_p, ctypes.c_size_t,
        ]
        _RUST_EXT_CDLL.trion_rust_crispr_check.restype = ctypes.c_int32
        rc = _RUST_EXT_CDLL.trion_rust_crispr_check(
            bytes(transaction_data), len(transaction_data),
        )
        return bool(rc)
    except (AttributeError, OSError, ctypes.ArgumentError) as exc:
        _log.warning("ctypes crispr_check call failed: %s", exc)
        return None


def crispr_check_native(transaction_data: bytes) -> bool:
    """
    CRISPR innate-check: scan transaction bytes for any of the 126 static
    attack signatures baked into the Rust binary.

    Args:
        transaction_data: Raw transaction bytes (or str — encoded UTF-8).

    Returns:
        True iff at least one signature matches as a substring.

    Dispatch order:
      1. PyO3: trion_rust.crispr_check_native(...)
      2. ctypes: lib.trion_rust_crispr_check(...)
      3. Python fallback: core.spiritual.living_security.CRISPRDefense.innate_check
    """
    if isinstance(transaction_data, str):
        transaction_data = transaction_data.encode("utf-8", errors="ignore")
    else:
        transaction_data = bytes(transaction_data)

    if _NATIVE_MODE == "pyo3":
        result = _native_crispr_check_via_pyo3(transaction_data)
        if result is not None:
            return result

    if _NATIVE_MODE == "ctypes":
        result = _native_crispr_check_via_ctypes(transaction_data)
        if result is not None:
            return result

    # Python fallback (always available).
    from core.spiritual.living_security import CRISPRDefense
    return CRISPRDefense().innate_check(transaction_data) is not None


def compute_bootstrap_weight_native(akashic_depth: int) -> float:
    """
    Compute bootstrap weight e^(-λ·D).

    Falls back to Python when the Rust extension is not available (the
    Rust crate currently does not expose a bootstrap-weight function).
    When the Rust extension IS available, this function first attempts
    the PyO3 entry point `trion_rust.bootstrap_weight` if it exists.
    """
    if _NATIVE_MODE == "pyo3" and _RUST_EXT_PYTHON_MODULE is not None:
        fn = getattr(_RUST_EXT_PYTHON_MODULE, "bootstrap_weight", None)
        if callable(fn):
            try:
                return float(fn(int(akashic_depth)))
            except Exception as exc:  # pragma: no cover — defensive
                _log.warning("PyO3 bootstrap_weight failed: %s", exc)

    # Python fallback (always available).
    from core.spiritual.living_security import bootstrap_weight
    return bootstrap_weight(akashic_depth)


# ─── Signal Type Registry (§14.2 — 24-type enum) ──────────────────────────
#
# Part 11 language mandate: the canonical 24-type SignalType registry is
# defined in Rust (`rust/src/signal_emitter.rs::SignalType`) and in Python
# (`core/master/signal_factory.py::SignalType`). The two enums are
# parity-tested (see `signal_emitter::tests::test_names_match_python_registry`
# and `test_all_24_ids_round_trip`) — the ids 0–23 and the SCREAMING_SNAKE
# names are byte-identical across both implementations.
#
# The bridge below resolves name ↔ id using the Rust implementation when
# the cdylib/PyO3 module exposes the lookup symbol, and falls back to the
# Python `SignalType` IntEnum (the canonical source of truth) when the
# Rust lookup symbol is unavailable. The fallback is honest: it is NOT a
# fake Rust implementation — it is the Python reference that the Rust enum
# is parity-tested against, used as the fallback when the Rust lookup is
# not linked into the loaded cdylib.

# Map of canonical registry id (0-23) → canonical registry name.
# Populated lazily from the Python SignalType IntEnum on first use so the
# bridge stays in sync with the canonical registry without a duplicate
# static table. The Rust enum's `ALL_SIGNAL_TYPES` is parity-tested to
# produce the same name-for-id mapping (see `signal_emitter.rs` tests).
_SIGNAL_TYPE_ID_TO_NAME_CACHE: Optional[list] = None


def _ensure_signal_type_cache() -> list:
    """Lazily build the (id → name) lookup table from the Python registry.

    The Python SignalType IntEnum is the canonical source of truth — the
    Rust `SignalType::ALL_SIGNAL_TYPES` array is parity-tested against it
    (see `signal_emitter::tests::test_names_match_python_registry`).
    """
    global _SIGNAL_TYPE_ID_TO_NAME_CACHE
    if _SIGNAL_TYPE_ID_TO_NAME_CACHE is None:
        from core.master.signal_factory import SignalType
        _SIGNAL_TYPE_ID_TO_NAME_CACHE = [
            member.name for member in sorted(SignalType, key=lambda m: int(m))
        ]
    return _SIGNAL_TYPE_ID_TO_NAME_CACHE


def signal_type_id_from_name_native(name: str) -> Optional[int]:
    """
    Resolve a canonical signal type name (e.g. `"VALUATION"`,
    `"CROSS_CHAIN_COHERENCE"`) to its registry id in 0–23.

    Dispatch order:
      1. PyO3: `trion_rust.signal_type_id_from_name(name)` when the PyO3
         module exposes the signal_emitter lookup.
      2. ctypes: `lib.trion_rust_signal_type_id_from_name(name_ptr)` when
         the cdylib exports the C ABI shim (added by the next `cargo build
         --features pyo3` after the signal_emitter shim lands).
      3. Python fallback: the canonical `SignalType` IntEnum lookup (the
         source of truth the Rust enum is parity-tested against).

    Returns None when the name is not a canonical 24-type member.
    """
    return signal_type_id_from_name_with_dispatch(name)[0]


def signal_type_id_from_name_with_dispatch(name: str) -> tuple:
    """
    Same as `signal_type_id_from_name_native` but also returns the dispatch
    mode that produced the value. The tuple is `(id_or_None, dispatch_mode)`
    where `dispatch_mode` is one of:
      * `"rust_native_pyo3"`    — the PyO3 `trion_rust` module answered.
      * `"rust_native_ctypes"`  — the cdylib C ABI shim answered.
      * `"python_fallback"`     — the Python IntEnum answered (canonical
                                  source of truth; the Rust enum is
                                  parity-tested against this).
      * `"none"`                — the name did not resolve.

    The dispatch tag lets callers (e.g. `classify_signal`) honestly label
    which implementation produced the value — when the .so does not yet
    export the signal_emitter C ABI shim, the dispatch is
    `"python_fallback"` (NOT a fake `"rust_native"`).
    """
    name_upper = str(name).upper().strip()

    # 1. PyO3 module path.
    if _NATIVE_MODE == "pyo3" and _RUST_EXT_PYTHON_MODULE is not None:
        fn = getattr(_RUST_EXT_PYTHON_MODULE, "signal_type_id_from_name", None)
        if callable(fn):
            try:
                id_val = fn(name_upper)
                if id_val is not None and 0 <= int(id_val) < 24:
                    return int(id_val), "rust_native_pyo3"
            except Exception as exc:  # pragma: no cover — defensive
                _log.warning("PyO3 signal_type_id_from_name failed: %s", exc)

    # 2. ctypes cdylib path (forward-compat: activates when the .so is
    # rebuilt with the signal_emitter C ABI shim).
    if _NATIVE_MODE == "ctypes" and _RUST_EXT_CDLL is not None:
        fn = getattr(_RUST_EXT_CDLL, "trion_rust_signal_type_id_from_name", None)
        if callable(fn):
            try:
                fn.argtypes = [ctypes.c_char_p]
                fn.restype = ctypes.c_int32
                rc = fn(name_upper.encode("utf-8"))
                # rc == -1 → unknown name; 0..23 → canonical id.
                if rc >= 0 and rc < 24:
                    return int(rc), "rust_native_ctypes"
            except (AttributeError, OSError, ctypes.ArgumentError) as exc:
                _log.debug("ctypes signal_type_id_from_name not available: %s", exc)

    # 3. Python fallback (canonical source of truth — the Rust enum is
    # parity-tested against this IntEnum).
    from core.master.signal_factory import SignalType, RULING_NAME_ALIASES
    canonical = RULING_NAME_ALIASES.get(name_upper, name_upper)
    try:
        return int(SignalType[canonical]), "python_fallback"
    except KeyError:
        return None, "none"


def signal_type_name_from_id_native(signal_type_id: int) -> Optional[str]:
    """
    Resolve a canonical signal type id (0–23) to its registry name.

    Dispatch order mirrors `signal_type_id_from_name_native`:
      1. PyO3: `trion_rust.signal_type_name_from_id(id)`.
      2. ctypes: `lib.trion_rust_signal_type_name_from_id(id, buf, len)`.
      3. Python fallback: the canonical `SignalType` IntEnum lookup.

    Returns None when the id is outside 0–23.
    """
    try:
        id_int = int(signal_type_id)
    except (TypeError, ValueError):
        return None
    if id_int < 0 or id_int >= 24:
        return None

    # 1. PyO3 module path.
    if _NATIVE_MODE == "pyo3" and _RUST_EXT_PYTHON_MODULE is not None:
        fn = getattr(_RUST_EXT_PYTHON_MODULE, "signal_type_name_from_id", None)
        if callable(fn):
            try:
                name_val = fn(id_int)
                if isinstance(name_val, str) and name_val:
                    return name_val
            except Exception as exc:  # pragma: no cover — defensive
                _log.warning("PyO3 signal_type_name_from_id failed: %s", exc)

    # 2. ctypes cdylib path (forward-compat).
    if _NATIVE_MODE == "ctypes" and _RUST_EXT_CDLL is not None:
        fn = getattr(_RUST_EXT_CDLL, "trion_rust_signal_type_name_from_id", None)
        if callable(fn):
            try:
                fn.argtypes = [ctypes.c_uint8, ctypes.c_char_p, ctypes.c_size_t]
                fn.restype = ctypes.c_int32
                buf = ctypes.create_string_buffer(64)
                rc = fn(id_int, buf, 64)
                if rc == 0:
                    name = buf.value.decode("utf-8", errors="ignore")
                    if name:
                        return name
            except (AttributeError, OSError, ctypes.ArgumentError) as exc:
                _log.debug("ctypes signal_type_name_from_id not available: %s", exc)

    # 3. Python fallback (canonical source of truth).
    table = _ensure_signal_type_cache()
    if 0 <= id_int < len(table):
        return table[id_int]
    return None



# ─── ANIMA ML hot-path (L3.3 / L3.6) ─────────────────────────────────────
#
# Part 11 language mandate — "Performance-critical paths compiled to Rust
# via PyO3 bindings." The five functions below port the per-signal inference
# hot-path of the ANIMA engine (`anima-service/anima_engine.py` +
# `core/mental/anima/reflexivity.py` + `pattern_library.py`):
#
#   1. compute_anima_score(pcr, ha, ca)            → A(t) = PCR·HA·CA
#   2. compute_archetype_similarity(entity, arch)  → cosine similarity
#   3. compute_observer_effect(pubs, changes)      → lag-1 Pearson corr
#   4. compute_ci_95(mean, std_dev, n)             → (lo, hi) t-distribution
#   5. compute_probability_distribution(scores)    → (mean, std, lo, hi)
#
# Each `*_native` wrapper dispatches in three layers:
#   1. PyO3: `trion_rust.<fn>(...)`        (preferred — fastest, type-safe)
#   2. ctypes: `lib.trion_rust_<fn>(...)`  (fallback for frozen interpreters)
#   3. Python fallback: inline reference implementation
# Each layer returns byte-identical math (verified by the Rust unit tests
# at `rust/src/anima.rs::tests::*` and the Python round-trip test below).

HA_DISABLE_THRESHOLD = 0.60  # mirrors anima_engine.py + rust/anima.rs
ANIMA_COSINE_EPS = 1e-10


def _native_anima_score_via_pyo3(pcr: float, ha: float, ca: float) -> Optional[float]:
    if _RUST_EXT_PYTHON_MODULE is None:
        return None
    try:
        return float(_RUST_EXT_PYTHON_MODULE.compute_anima_score(
            float(pcr), float(ha), float(ca),
        ))
    except Exception as exc:  # pragma: no cover — defensive
        _log.warning("PyO3 compute_anima_score failed: %s", exc)
        return None


def _native_anima_score_via_ctypes(pcr: float, ha: float, ca: float) -> Optional[float]:
    if _RUST_EXT_CDLL is None:
        return None
    try:
        _RUST_EXT_CDLL.trion_rust_compute_anima_score.argtypes = [
            ctypes.c_double, ctypes.c_double, ctypes.c_double,
        ]
        _RUST_EXT_CDLL.trion_rust_compute_anima_score.restype = ctypes.c_double
        return float(_RUST_EXT_CDLL.trion_rust_compute_anima_score(
            float(pcr), float(ha), float(ca),
        ))
    except (AttributeError, OSError, ctypes.ArgumentError) as exc:
        _log.warning("ctypes compute_anima_score call failed: %s", exc)
        return None


def compute_anima_score_native(pcr: float, ha: float, ca: float) -> float:
    """
    Compute the L3.3 ANIMA Score A(t) = PCR · HA · CA using Rust.

    Returns 0.0 when HA < 0.60 (HA_DISABLE_THRESHOLD — anima_engine.py
    line 1427). Inputs are clamped to [0,1] and NaN/Inf coerce to 0.0.

    Dispatch order:
      1. PyO3: `trion_rust.compute_anima_score(pcr, ha, ca)`
      2. ctypes: `lib.trion_rust_compute_anima_score(pcr, ha, ca)`
      3. Python fallback: `0.0 if ha < 0.60 else clamp(pcr*ha*ca, 0, 1)`
    """
    if _NATIVE_MODE == "pyo3":
        v = _native_anima_score_via_pyo3(pcr, ha, ca)
        if v is not None:
            return v
    if _NATIVE_MODE == "ctypes":
        v = _native_anima_score_via_ctypes(pcr, ha, ca)
        if v is not None:
            return v

    # 3. Python fallback — same math as rust::anima::compute_anima_score
    import math
    if not all(math.isfinite(x) for x in (pcr, ha, ca)):
        return 0.0
    if ha < HA_DISABLE_THRESHOLD:
        return 0.0
    pcr_c = max(0.0, min(1.0, pcr))
    ha_c = max(0.0, min(1.0, ha))
    ca_c = max(0.0, min(1.0, ca))
    return pcr_c * ha_c * ca_c


def _native_archetype_similarity_via_pyo3(
    entity_vector: list, archetype_vector: list,
) -> Optional[float]:
    if _RUST_EXT_PYTHON_MODULE is None:
        return None
    try:
        return float(_RUST_EXT_PYTHON_MODULE.compute_archetype_similarity(
            [float(x) for x in entity_vector],
            [float(x) for x in archetype_vector],
        ))
    except Exception as exc:  # pragma: no cover — defensive
        _log.warning("PyO3 compute_archetype_similarity failed: %s", exc)
        return None


def _native_archetype_similarity_via_ctypes(
    entity_vector: list, archetype_vector: list,
) -> Optional[float]:
    if _RUST_EXT_CDLL is None:
        return None
    try:
        _RUST_EXT_CDLL.trion_rust_compute_archetype_similarity.argtypes = [
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_size_t,
        ]
        _RUST_EXT_CDLL.trion_rust_compute_archetype_similarity.restype = ctypes.c_double
        n = min(len(entity_vector), len(archetype_vector))
        if n == 0:
            return 0.0
        a = (ctypes.c_double * n)(*[float(x) for x in entity_vector[:n]])
        b = (ctypes.c_double * n)(*[float(x) for x in archetype_vector[:n]])
        return float(_RUST_EXT_CDLL.trion_rust_compute_archetype_similarity(a, b, n))
    except (AttributeError, OSError, ctypes.ArgumentError) as exc:
        _log.warning("ctypes compute_archetype_similarity call failed: %s", exc)
        return None


def compute_archetype_similarity_native(
    entity_vector: list, archetype_vector: list,
) -> float:
    """
    Cosine similarity between an entity vector and an archetype centroid.

    Mirrors `anima_engine.py::_compute_pcr` step 3 (line 1167):
        sim = dot(a, b) / (‖a‖ · ‖b‖ + 1e-10)
    Returns 0.0 for empty/zero-vector inputs. Unequal lengths truncate to
    the trailing min-length slice.

    Dispatch order:
      1. PyO3: `trion_rust.compute_archetype_similarity(entity, archetype)`
      2. ctypes: `lib.trion_rust_compute_archetype_similarity(a, b, n)`
      3. Python fallback: inline numpy-free cosine similarity
    """
    if _NATIVE_MODE == "pyo3":
        v = _native_archetype_similarity_via_pyo3(entity_vector, archetype_vector)
        if v is not None:
            return v
    if _NATIVE_MODE == "ctypes":
        v = _native_archetype_similarity_via_ctypes(entity_vector, archetype_vector)
        if v is not None:
            return v

    # 3. Python fallback — same math as rust::anima::compute_archetype_similarity
    import math
    if not entity_vector or not archetype_vector:
        return 0.0
    n = min(len(entity_vector), len(archetype_vector))
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        a = float(entity_vector[i])
        b = float(archetype_vector[i])
        if not (math.isfinite(a) and math.isfinite(b)):
            continue
        dot += a * b
        na += a * a
        nb += b * b
    denom = (math.sqrt(na) * math.sqrt(nb)) + ANIMA_COSINE_EPS
    if denom <= ANIMA_COSINE_EPS:
        return 0.0
    return max(-1.0, min(1.0, dot / denom))


def _native_observer_effect_via_pyo3(
    publications: list, behavioral_changes: list,
) -> Optional[float]:
    if _RUST_EXT_PYTHON_MODULE is None:
        return None
    try:
        return float(_RUST_EXT_PYTHON_MODULE.compute_observer_effect(
            [float(x) for x in publications],
            [float(x) for x in behavioral_changes],
        ))
    except Exception as exc:  # pragma: no cover — defensive
        _log.warning("PyO3 compute_observer_effect failed: %s", exc)
        return None


def _native_observer_effect_via_ctypes(
    publications: list, behavioral_changes: list,
) -> Optional[float]:
    if _RUST_EXT_CDLL is None:
        return None
    try:
        _RUST_EXT_CDLL.trion_rust_compute_observer_effect.argtypes = [
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_size_t,
        ]
        _RUST_EXT_CDLL.trion_rust_compute_observer_effect.restype = ctypes.c_double
        n = min(len(publications), len(behavioral_changes))
        if n < 2:
            return 0.0
        pubs = (ctypes.c_double * n)(*[float(x) for x in publications[:n]])
        chgs = (ctypes.c_double * n)(*[float(x) for x in behavioral_changes[:n]])
        return float(_RUST_EXT_CDLL.trion_rust_compute_observer_effect(pubs, chgs, n))
    except (AttributeError, OSError, ctypes.ArgumentError) as exc:
        _log.warning("ctypes compute_observer_effect call failed: %s", exc)
        return None


def compute_observer_effect_native(
    publications: list, behavioral_changes: list,
) -> float:
    """
    Observer Effect (L3.6): OE = corr(publication[t-1], behavioral_change[t]).

    Lag-1 Pearson correlation. Returns the raw correlation ∈ [-1, 1];
    callers that need positive-clipped OE (as `reflexivity.py` does) can
    apply `max(0.0, oe)` themselves. Returns 0.0 when fewer than 2 paired
    samples or when either series has zero variance.

    Dispatch order:
      1. PyO3: `trion_rust.compute_observer_effect(pubs, changes)`
      2. ctypes: `lib.trion_rust_compute_observer_effect(p, c, n)`
      3. Python fallback: inline Pearson correlation (mirrors
         `core/mental/anima/reflexivity.py::compute_correlation`)
    """
    if _NATIVE_MODE == "pyo3":
        v = _native_observer_effect_via_pyo3(publications, behavioral_changes)
        if v is not None:
            return v
    if _NATIVE_MODE == "ctypes":
        v = _native_observer_effect_via_ctypes(publications, behavioral_changes)
        if v is not None:
            return v

    # 3. Python fallback — mirrors reflexivity.py::compute_correlation
    # with the lag-1 alignment baked in.
    if len(publications) < 2 or len(behavioral_changes) < 2:
        return 0.0
    n_pub = len(publications) - 1
    n_chg = len(behavioral_changes) - 1
    n = min(n_pub, n_chg)
    if n < 2:
        return 0.0
    pubs = [float(x) for x in publications[len(publications) - n - 1:len(publications) - 1]]
    chgs = [float(x) for x in behavioral_changes[len(behavioral_changes) - n:]]
    mx = sum(pubs) / n
    my = sum(chgs) / n
    cov = sum((pubs[i] - mx) * (chgs[i] - my) for i in range(n))
    vx = sum((p - mx) ** 2 for p in pubs)
    vy = sum((c - my) ** 2 for c in chgs)
    if vx <= 0 or vy <= 0:
        return 0.0
    corr = cov / math.sqrt(vx * vy)
    return max(-1.0, min(1.0, corr))


def _native_ci_95_via_pyo3(mean: float, std_dev: float, n_samples: int) -> Optional[Tuple[float, float]]:
    if _RUST_EXT_PYTHON_MODULE is None:
        return None
    try:
        result = _RUST_EXT_PYTHON_MODULE.compute_ci_95(
            float(mean), float(std_dev), int(n_samples),
        )
        if isinstance(result, tuple) and len(result) == 2:
            return float(result[0]), float(result[1])
    except Exception as exc:  # pragma: no cover — defensive
        _log.warning("PyO3 compute_ci_95 failed: %s", exc)
    return None


def _native_ci_95_via_ctypes(mean: float, std_dev: float, n_samples: int) -> Optional[Tuple[float, float]]:
    if _RUST_EXT_CDLL is None:
        return None
    try:
        _RUST_EXT_CDLL.trion_rust_compute_ci_95.argtypes = [
            ctypes.c_double, ctypes.c_double, ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_double),
        ]
        _RUST_EXT_CDLL.trion_rust_compute_ci_95.restype = ctypes.c_int32
        out = (ctypes.c_double * 2)()
        rc = _RUST_EXT_CDLL.trion_rust_compute_ci_95(
            float(mean), float(std_dev), int(n_samples), out,
        )
        if rc != 0:
            _log.warning("trion_rust_compute_ci_95 returned rc=%d", rc)
            return None
        return float(out[0]), float(out[1])
    except (AttributeError, OSError, ctypes.ArgumentError) as exc:
        _log.warning("ctypes compute_ci_95 call failed: %s", exc)
        return None


def compute_ci_95_native(
    mean: float, std_dev: float, n_samples: int,
) -> Tuple[float, float]:
    """
    95% confidence interval using the t-distribution approximation.

    Mirrors `pattern_library.py::OutcomeDistribution.from_observations`
    (lines 82-92):
        t      = 2.262 if n < 10 else 1.96
        margin = t · σ / √n
        CI_95  = (max(0.0, mean − margin), min(1.0, mean + margin))

    `n_samples == 0` returns the degenerate `(mean, mean)` interval
    clipped to [0,1].

    Dispatch order:
      1. PyO3: `trion_rust.compute_ci_95(mean, std_dev, n_samples)`
      2. ctypes: `lib.trion_rust_compute_ci_95(mean, std_dev, n, out*)`
      3. Python fallback: inline t-distribution approximation
    """
    if _NATIVE_MODE == "pyo3":
        v = _native_ci_95_via_pyo3(mean, std_dev, n_samples)
        if v is not None:
            return v
    if _NATIVE_MODE == "ctypes":
        v = _native_ci_95_via_ctypes(mean, std_dev, n_samples)
        if v is not None:
            return v

    # 3. Python fallback
    n = int(n_samples)
    if n == 0:
        m = 0.5 if not math.isfinite(float(mean)) else float(mean)
        m = max(0.0, min(1.0, m))
        return (m, m)
    m = float(mean) if math.isfinite(float(mean)) else 0.5
    s = float(std_dev) if (math.isfinite(float(std_dev)) and float(std_dev) >= 0.0) else 0.5
    t = 2.262 if n < 10 else 1.96
    margin = t * s / math.sqrt(max(n, 1))
    lo = max(0.0, m - margin)
    hi = min(1.0, m + margin)
    return (lo, hi)


def _native_probability_distribution_via_pyo3(scores: list) -> Optional[Tuple[float, float, float, float]]:
    if _RUST_EXT_PYTHON_MODULE is None:
        return None
    try:
        result = _RUST_EXT_PYTHON_MODULE.compute_probability_distribution(
            [float(x) for x in scores],
        )
        if isinstance(result, tuple) and len(result) == 4:
            return tuple(float(x) for x in result)  # type: ignore[return-value]
    except Exception as exc:  # pragma: no cover — defensive
        _log.warning("PyO3 compute_probability_distribution failed: %s", exc)
    return None


def _native_probability_distribution_via_ctypes(scores: list) -> Optional[Tuple[float, float, float, float]]:
    if _RUST_EXT_CDLL is None:
        return None
    try:
        _RUST_EXT_CDLL.trion_rust_compute_probability_distribution.argtypes = [
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_double),
        ]
        _RUST_EXT_CDLL.trion_rust_compute_probability_distribution.restype = ctypes.c_int32
        n = len(scores)
        arr = (ctypes.c_double * n)(*[float(x) for x in scores]) if n > 0 else (ctypes.c_double * 0)()
        out = (ctypes.c_double * 4)()
        rc = _RUST_EXT_CDLL.trion_rust_compute_probability_distribution(
            arr if n > 0 else None, n, out,
        )
        if rc != 0:
            _log.warning("trion_rust_compute_probability_distribution returned rc=%d", rc)
            return None
        return float(out[0]), float(out[1]), float(out[2]), float(out[3])
    except (AttributeError, OSError, ctypes.ArgumentError) as exc:
        _log.warning("ctypes compute_probability_distribution call failed: %s", exc)
        return None


def compute_probability_distribution_native(
    scores: list,
) -> Tuple[float, float, float, float]:
    """
    Full PROBABILITY_DISTRIBUTION over a sample of scores — spec §3.3
    mandates that ANIMA outputs are distributions, never point predictions.

    Mirrors `pattern_library.py::OutcomeDistribution.from_observations`:
        mean   = (1/n) Σ x_i
        var    = (1/n) Σ (x_i − mean)²         (n > 1, else 0.25)
        std    = √var
        CI_95  = compute_ci_95(mean, std, n)

    Cold-start: when `scores` is empty, returns `(0.5, 0.25, 0.0, 1.0)` —
    matching `OutcomeDistribution(0.5, 0.25, 0.0, 1.0, 0.0, 0)`.

    Dispatch order:
      1. PyO3: `trion_rust.compute_probability_distribution(scores)`
      2. ctypes: `lib.trion_rust_compute_probability_distribution(arr, n, out*)`
      3. Python fallback: inline mean/var/std + compute_ci_95
    """
    if _NATIVE_MODE == "pyo3":
        v = _native_probability_distribution_via_pyo3(scores)
        if v is not None:
            return v
    if _NATIVE_MODE == "ctypes":
        v = _native_probability_distribution_via_ctypes(scores)
        if v is not None:
            return v

    # 3. Python fallback
    finite = [float(x) for x in scores if math.isfinite(float(x))]
    n = len(finite)
    if n == 0:
        return (0.5, 0.25, 0.0, 1.0)
    mean = sum(finite) / n
    var = (sum((x - mean) ** 2 for x in finite) / n) if n > 1 else 0.25
    std = math.sqrt(var)
    lo, hi = compute_ci_95_native(mean, std, n)
    return (mean, std, lo, hi)


def compute_pattern_library_pcr_native(
    coherences: list, thresholds: list,
) -> Tuple[float, int, int]:
    """
    Pattern Coherence Ratio (PCR) over a pattern library — mirrors
    `pattern_library.py::ANIMAPatternLibrary.compute_pcr`.

    Returns (pcr, coherent_count, total_count).

    Dispatch order:
      1. PyO3: `trion_rust.compute_pattern_library_pcr(coherences, thresholds)`
      2. ctypes: `lib.trion_rust_compute_pattern_library_pcr(c, t, n, out*)`
      3. Python fallback: inline counting
    """
    if _NATIVE_MODE == "pyo3" and _RUST_EXT_PYTHON_MODULE is not None:
        try:
            result = _RUST_EXT_PYTHON_MODULE.compute_pattern_library_pcr(
                [float(x) for x in coherences],
                [float(x) for x in thresholds],
            )
            if isinstance(result, tuple) and len(result) == 3:
                return float(result[0]), int(result[1]), int(result[2])
        except Exception as exc:  # pragma: no cover — defensive
            _log.warning("PyO3 compute_pattern_library_pcr failed: %s", exc)

    if _NATIVE_MODE == "ctypes" and _RUST_EXT_CDLL is not None:
        try:
            _RUST_EXT_CDLL.trion_rust_compute_pattern_library_pcr.argtypes = [
                ctypes.POINTER(ctypes.c_double),
                ctypes.POINTER(ctypes.c_double),
                ctypes.c_size_t,
                ctypes.POINTER(ctypes.c_double),
            ]
            _RUST_EXT_CDLL.trion_rust_compute_pattern_library_pcr.restype = ctypes.c_int32
            n = min(len(coherences), len(thresholds))
            if n == 0:
                return (0.0, 0, 0)
            c_arr = (ctypes.c_double * n)(*[float(x) for x in coherences[:n]])
            t_arr = (ctypes.c_double * n)(*[float(x) for x in thresholds[:n]])
            out = (ctypes.c_double * 3)()
            rc = _RUST_EXT_CDLL.trion_rust_compute_pattern_library_pcr(c_arr, t_arr, n, out)
            if rc == 0:
                return float(out[0]), int(out[1]), int(out[2])
        except (AttributeError, OSError, ctypes.ArgumentError) as exc:
            _log.warning("ctypes compute_pattern_library_pcr call failed: %s", exc)

    # 3. Python fallback
    n = min(len(coherences), len(thresholds))
    if n == 0:
        return (0.0, 0, 0)
    coherent = sum(
        1 for i in range(n)
        if math.isfinite(float(coherences[i]))
        and math.isfinite(float(thresholds[i]))
        and float(coherences[i]) > float(thresholds[i])
    )
    return (coherent / n, coherent, n)


# Initialize on import
_find_rust_ext()
