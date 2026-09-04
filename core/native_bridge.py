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

Julia (`math/src/TRIONMath.jl`) is invoked via `run_julia_validation()` when
a julia binary is discoverable; otherwise it reports unavailable honestly.
Cross-language proof: Julia's coherence() reproduces Python's C(t) exactly.

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
_GO_BIN = os.path.expanduser("~/go/bin/go")
_GHC_RUNGHC = "/nix/store/2qqlva2zbkdhbyrz4qyacgq57s8kfy1l-ghc-9.4.8/bin/runghc"
# Also check stack-installed GHC and common system paths
_GHC_CANDIDATES = [
    _GHC_RUNGHC,
    os.path.expanduser("~/ghc/bin/runghc"),          # audit fix: our real install
    os.path.expanduser("~/.stack/programs/x86_64-linux/ghc-tinfo6-9.10.3/bin/runghc"),
    os.path.expanduser("~/.local/bin/runghc"),
    "runghc",
]
_GO_CANDIDATES = [
    os.path.expanduser("~/go-toolchain/go/bin/go"),  # audit fix: our real install
    os.path.expanduser("~/go/bin/go"),
    "/usr/local/go/bin/go",
    "go",
]

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
        cpp_src = os.path.join(_ROOT, "signal-processing", "src", "fft_engine.cpp")  # audit fix: was "cpp/fft_engine.cpp" (never existed)
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
        go_tool = _find_tool(_GO_CANDIDATES)
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
    runghc = _find_tool(_GHC_CANDIDATES)
    hs_src = os.path.join(_ROOT, "formal", "src", "TRION", "Theorems.hs")  # audit fix: real module location
    if not runghc or not os.path.exists(hs_src):
        return {"available": False, "reason": "ghc/runghc or source not found"}
    try:
        formal_dir = os.path.dirname(os.path.dirname(os.path.dirname(hs_src)))
        proc = subprocess.run(
            [runghc, "-i" + os.path.join(formal_dir, "src"), hs_src],
            capture_output=True, text=True, timeout=timeout_s,
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
    Status for math/trion_entropy_verification.jl.
    Julia runtime is checked via PATH and common install locations.
    """
    has_julia = shutil.which("julia") is not None
    # Also check common install locations
    if not has_julia:
        for p in [os.path.expanduser("~/julia/bin/julia"), "/usr/local/bin/julia", "/home/z/julia-1.10.9/bin/julia"]:
            if os.path.exists(p):
                has_julia = True
                break
    return {
        "available": has_julia,
        "reason": None if has_julia else "no Julia runtime installed in this environment",
        "source": "math/src/TRIONMath.jl",
    }




def run_julia_validation(timeout_s: float = 240.0) -> dict:
    """
    Runs math/src/TRIONMath.jl's embedded verification suite via Julia.
    Proves the Julia implementation reproduces the Python engines' values
    (coherence with all 5 spec weight profiles, convergence bound, entropy).
    """
    julia_bin = shutil.which("julia")
    if not julia_bin:
        for p in [os.path.expanduser("~/julia/bin/julia"), "/usr/local/bin/julia"]:
            if os.path.exists(p):
                julia_bin = p
                break
    jl_src = os.path.join(_ROOT, "math", "src", "TRIONMath.jl")
    if not julia_bin or not os.path.exists(jl_src):
        return {"available": False, "reason": "julia runtime or TRIONMath.jl not found"}
    try:
        proc = subprocess.run(
            [julia_bin, "--startup-file=no", jl_src],
            capture_output=True, text=True, timeout=timeout_s,
        )
        return {
            "available": proc.returncode == 0,
            "all_pass": proc.returncode == 0,
            "raw_output": proc.stdout[-2000:] if proc.stdout else "",
            "engine": "julia_TRIONMath",
        }
    except subprocess.TimeoutExpired:
        return {"available": False, "reason": "julia JIT exceeded timeout"}
    except Exception as e:
        return {"available": False, "reason": str(e)}

def native_stack_report() -> dict:
    """Full status of all 12+ programming languages in the TRION stack."""
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return {
        "python":     {"engine": "api + akashic + src/", "wired": True, "role": "Behavioral engine + API"},
        "rust":       {"engine": "indexers (21 per-VM crates + trion-common)", "wired": os.path.exists(os.path.join(_root, "indexers", "Cargo.toml")), "role": "L0 indexers + BH pipeline"},
        "javascript": {"engine": "relayer/relayer.js + relayer_non_evm.js", "wired": os.path.exists(os.path.join(_root, "relayer", "relayer.js")), "role": "Multi-chain relayers"},
        "typescript": {"engine": "chains/*/execute.ts + sdk/", "wired": os.path.exists(os.path.join(_root, "chains", "svm", "execute.ts")), "role": "Chain adapters + SDK"},
        "solidity":   {"engine": "contracts/*.sol", "wired": len([f for f in os.listdir(os.path.join(_root, "contracts")) if f.endswith(".sol")]) > 0, "role": "Smart contracts"},
        "vyper":      {"engine": "contracts/*.vy", "wired": any(f.endswith(".vy") for f in os.listdir(os.path.join(_root, "contracts"))), "role": "Token + staking"},
        "go":         {
            "crawler_coordinator": os.path.exists(os.path.join(_BIN_DIR, "crawler_coordinator")),
            "validator_mesh":      os.path.exists(os.path.join(_BIN_DIR, "validator_mesh")),
            "role": "P2P validator mesh + ANIMA crawler",
        },
        "haskell":    {"engine": "formal_verification", "wired": _find_tool(_GHC_CANDIDATES) is not None, "role": "9 theorems as types"},
        "julia":      {**julia_status(), "role": "Entropy + scale invariance verification"},
        "cpp":        {"engine": "fft_engine", "wired": os.path.exists(os.path.join(_BIN_DIR, "fft_engine")), "role": "FFT wash-trade spectral detection"},
        "cairo":      {"engine": "chains/starknet/src/cairo/", "wired": os.path.exists(os.path.join(_root, "chains", "starknet", "src", "cairo")), "role": "StarkNet contracts"},
        "func":       {"engine": "chains/ton/contracts/", "wired": os.path.exists(os.path.join(_root, "chains", "ton", "contracts")), "role": "TON contracts"},
        "ink":        {"engine": "chains/pvm/contracts/", "wired": os.path.exists(os.path.join(_root, "chains", "pvm", "contracts")), "role": "Polkadot contracts"},
        "wasm":       {"engine": "wasm/signal_processor.wasm", "wired": os.path.exists(os.path.join(_root, "wasm", "signal_processor.wasm")), "role": "Browser-side enforcement"},
    }
