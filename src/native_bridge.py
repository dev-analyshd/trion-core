"""
TRION Protocol — Native Stack Bridge
=====================================
Closes TRION_AUDIT_REPORT.md finding S5 / P3-14: Go, Haskell, and C++ source
files implement real spec logic (P2P validator mesh diversity weighting,
formal invariant proofs, FFT-based periodic-anomaly detection) but were
previously disconnected from the running services — no build step or call
boundary existed. This module is that call boundary: it compiles the native
sources once (idempotent) and exposes thin subprocess wrappers so the live
Python pipeline can actually invoke them.

Julia (`math/trion_entropy_verification.jl`) has no available Julia runtime
in this environment (no Nix module exists for it here), so it remains
un-wired; `julia_status()` reports this honestly rather than faking a call.

Each wrapper is defensive: if a binary is missing or a build fails, the
function returns a dict with "available": False and a reason, and callers
must treat native results as an optional cross-check/enrichment — never a
hard dependency of the core Python-computed signal path.
"""

import os
import json
import shutil
import subprocess
import threading
from typing import List, Optional

logger = __import__("logging").getLogger(__name__)

_ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BIN_DIR   = os.path.join(_ROOT, "bin")
_GO_BIN    = "/nix/store/a90l6nxkqdlqxzgz5j958rz5gwygbamc-go-1.21.13/bin/go"
_GHC_RUNGHC = "/nix/store/2qqlva2zbkdhbyrz4qyacgq57s8kfy1l-ghc-9.4.8/bin/runghc"

_build_lock = threading.Lock()
_build_done = False


def _find_tool(candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if os.path.exists(c):
            return c
        found = shutil.which(c)
        if found:
            return found
    return None


def ensure_native_stack_built(timeout_s: int = 90) -> dict:
    """
    Idempotent build of the C++ FFT engine and Go binaries into bin/.
    Safe to call repeatedly / concurrently — only builds once per process.
    """
    global _build_done
    with _build_lock:
        if _build_done:
            return {"already_built": True}
        os.makedirs(_BIN_DIR, exist_ok=True)
        results = {}

        # ── C++ FFT engine ───────────────────────────────────────────────
        cpp_src = os.path.join(_ROOT, "cpp", "fft_engine.cpp")
        cpp_bin = os.path.join(_BIN_DIR, "fft_engine")
        gpp = _find_tool(["g++", "/nix/store"])
        if os.path.exists(cpp_src) and shutil.which("g++"):
            try:
                subprocess.run(
                    ["g++", "-O2", "-std=c++17", "-o", cpp_bin, cpp_src],
                    check=True, timeout=timeout_s, capture_output=True,
                )
                results["cpp"] = "built"
            except Exception as e:
                results["cpp"] = f"build_failed: {e}"
        else:
            results["cpp"] = "g++ not found"

        # ── Go binaries ──────────────────────────────────────────────────
        go_tool = _find_tool([_GO_BIN, "go"])
        if go_tool and os.path.isdir(os.path.join(_ROOT, "go")):
            env = dict(os.environ, GOFLAGS="-mod=mod", GOCACHE="/tmp/gocache")
            for name in ("crawler_coordinator", "validator_mesh"):
                src = os.path.join(_ROOT, "go", f"{name}.go")
                out = os.path.join(_BIN_DIR, name)
                if not os.path.exists(src):
                    continue
                try:
                    subprocess.run(
                        [go_tool, "build", "-o", out, src],
                        check=True, timeout=timeout_s, capture_output=True,
                        cwd=os.path.join(_ROOT, "go"), env=env,
                    )
                    results[name] = "built"
                except Exception as e:
                    results[name] = f"build_failed: {e}"
        else:
            results["go"] = "go toolchain not found"

        _build_done = True
        logger.info("[native_bridge] stack build results: %s", results)
        return results


def compute_fft_features(signal: List[float], timeout_s: float = 5.0) -> dict:
    """
    Real Cooley-Tukey FFT entropy + periodic-anomaly detection via the
    compiled C++ engine (cpp/fft_engine.cpp), invoked as a subprocess.
    Returns {"available": False, "reason": ...} if the binary is missing.
    """
    ensure_native_stack_built()
    binp = os.path.join(_BIN_DIR, "fft_engine")
    if not os.path.exists(binp) or not signal:
        return {"available": False, "reason": "binary missing or empty signal"}
    try:
        proc = subprocess.run(
            [binp, "--stdin"],
            input=json.dumps(signal), capture_output=True, text=True,
            timeout=timeout_s,
        )
        out = json.loads(proc.stdout.strip() or "{}")
        out["available"] = "error" not in out
        out["engine"] = "cpp_fft_engine"
        return out
    except Exception as e:
        return {"available": False, "reason": str(e)}


def run_formal_verification(timeout_s: float = 30.0) -> dict:
    """
    Runs the Haskell formal-verification module (math/formal_verification.hs)
    via `runghc`, which type-checks and executes theorems T1-T8 as a real
    interpreter pass rather than documentation claims. Parses PASS/FAIL
    output into a structured result.
    """
    runghc = _find_tool([_GHC_RUNGHC, "runghc"])
    hs_src = os.path.join(_ROOT, "math", "formal_verification.hs")
    if not runghc or not os.path.exists(hs_src):
        return {"available": False, "reason": "ghc/runghc or source not found"}
    try:
        proc = subprocess.run(
            [runghc, hs_src], capture_output=True, text=True, timeout=timeout_s,
        )
        lines = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
        theorems = {}
        for l in lines:
            if ":" in l and ("True" in l or "False" in l):
                name, val = l.rsplit(":", 1)
                theorems[name.strip()] = "True" in val
        all_pass = proc.returncode == 0 and bool(theorems) and all(theorems.values())
        return {
            "available": True,
            "all_pass": all_pass,
            "theorems": theorems,
            "raw_output": proc.stdout,
            "engine": "haskell_formal_verification",
        }
    except Exception as e:
        return {"available": False, "reason": str(e)}


def run_go_crawler_coordinator_selftest(timeout_s: float = 15.0) -> dict:
    """Runs the compiled Go ANIMA crawler coordinator self-test binary."""
    ensure_native_stack_built()
    binp = os.path.join(_BIN_DIR, "crawler_coordinator")
    if not os.path.exists(binp):
        return {"available": False, "reason": "binary not built"}
    try:
        proc = subprocess.run([binp], capture_output=True, text=True, timeout=timeout_s)
        return {
            "available": proc.returncode == 0,
            "raw_output": proc.stdout,
            "engine": "go_crawler_coordinator",
        }
    except Exception as e:
        return {"available": False, "reason": str(e)}


def run_go_validator_mesh_selftest(timeout_s: float = 15.0) -> dict:
    """Runs the compiled Go P2P validator mesh self-test binary."""
    ensure_native_stack_built()
    binp = os.path.join(_BIN_DIR, "validator_mesh")
    if not os.path.exists(binp):
        return {"available": False, "reason": "binary not built"}
    try:
        proc = subprocess.run([binp], capture_output=True, text=True, timeout=timeout_s)
        return {
            "available": proc.returncode == 0,
            "raw_output": proc.stdout,
            "engine": "go_validator_mesh",
        }
    except Exception as e:
        return {"available": False, "reason": str(e)}


def julia_status() -> dict:
    """
    Honest status for math/trion_entropy_verification.jl — no Julia runtime
    module is available in this Replit environment, so it cannot be wired
    the way Go/Haskell/C++ were. Reported explicitly rather than silently
    dropped or faked.
    """
    has_julia = shutil.which("julia") is not None
    return {
        "available": has_julia,
        "reason": None if has_julia else "no Julia runtime installed in this environment",
        "source": "math/trion_entropy_verification.jl",
    }


def native_stack_report() -> dict:
    """Full status of all four previously-disconnected stack languages."""
    return {
        "cpp":     {"engine": "fft_engine", "wired": os.path.exists(os.path.join(_BIN_DIR, "fft_engine"))},
        "go":      {
            "crawler_coordinator": os.path.exists(os.path.join(_BIN_DIR, "crawler_coordinator")),
            "validator_mesh":      os.path.exists(os.path.join(_BIN_DIR, "validator_mesh")),
        },
        "haskell": {"engine": "formal_verification", "wired": _find_tool([_GHC_RUNGHC, "runghc"]) is not None},
        "julia":   julia_status(),
    }
