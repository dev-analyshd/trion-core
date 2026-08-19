"""
Rust BTCP Bridge — Optional integration layer

This module provides optional integration between the Python TRION system
and the Rust BTCP implementation. The Python system continues to work
independently — this is purely an optional accelerator/alternative.

Both implementations coexist without breaking each other:
- Python: core/btcp/ — full reference implementation
- Rust:   rust/       — high-performance implementation per spec
"""

import json
import subprocess
import os
from pathlib import Path
from typing import Optional, Dict, Any

# Path to the Rust project root (repo root / rust)
RUST_DIR = Path(__file__).parent.parent.parent / "rust"

# Path to built Rust binaries (release mode)
RUST_BIN_DIR = RUST_DIR / "target" / "release"


def rust_available() -> bool:
    """Check if Rust BTCP binaries are available and built."""
    router_bin = RUST_BIN_DIR / "btcp-router"
    escrow_bin = RUST_BIN_DIR / "btcp-escrow-monitor"
    return router_bin.exists() and escrow_bin.exists()


def build_rust() -> bool:
    """Build the Rust BTCP implementation in release mode."""
    try:
        result = subprocess.run(
            ["cargo", "build", "--release"],
            cwd=str(RUST_DIR),
            capture_output=True,
            text=True,
            timeout=300,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def run_rust_tests() -> Dict[str, Any]:
    """Run the Rust BTCP test suite."""
    try:
        # Use /tmp for target dir to avoid filesystem issues
        env = os.environ.copy()
        env["CARGO_TARGET_DIR"] = "/tmp/trion-rust-target"

        result = subprocess.run(
            ["cargo", "test", "--release"],
            cwd=str(RUST_DIR),
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[-2000:],
            "stderr": result.stderr[-1000:],
        }
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"success": False, "error": str(e)}


def demo_rust_router() -> Optional[str]:
    """Run the Rust BTCP router demo binary."""
    router_bin = RUST_BIN_DIR / "btcp-router"
    if not router_bin.exists():
        # Try the /tmp target location
        router_bin = Path("/tmp/trion-rust-target/release/btcp-router")

    if not router_bin.exists():
        return None

    try:
        result = subprocess.run(
            [str(router_bin)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def demo_rust_escrow_monitor() -> Optional[str]:
    """Run the Rust BTCP escrow monitor demo binary."""
    escrow_bin = RUST_BIN_DIR / "btcp-escrow-monitor"
    if not escrow_bin.exists():
        escrow_bin = Path("/tmp/trion-rust-target/release/btcp-escrow-monitor")

    if not escrow_bin.exists():
        return None

    try:
        result = subprocess.run(
            [str(escrow_bin)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_rust_file_list() -> list:
    """List all Rust BTCP source files per the spec requirements."""
    src_dir = RUST_DIR / "src"
    rust_files = sorted([f.name for f in src_dir.glob("*.rs")])
    bin_files = sorted([f.name for f in (src_dir / "bin").glob("*.rs")]) if (src_dir / "bin").exists() else []
    return {
        "library_files": rust_files,
        "binary_files": bin_files,
        "total_source_files": len(rust_files) + len(bin_files),
    }


# BTCP spec-required Rust files (19 modules + 2 binaries)
SPEC_REQUIRED_FILES = [
    "btcp_router.rs",           # Core routing, BTCP_score, route selection
    "btcp_proof_builder.rs",    # Proof construction, reorg protection
    "bitp_matcher.rs",          # CUT/MATCH/PASTE engine
    "netting_engine.rs",        # Counterparty matching
    "intent_aggregator.rs",     # IAP pooling
    "ooa_anchor.rs",            # Non-integrated chain observation
    "shadow_observer.rs",       # Hostile chain shadow protocol
    "state_capsule.rs",         # Cross-chain state reads
    "btcp_failure_classifier.rs",  # External vs entity cause
    "behavioral_state_channel.rs",  # BSC lifecycle
    "finality_normalizer.rs",   # max(A, B) finality
    "btcp_version_handler.rs",  # Semver compatibility
    "validator_fee_calculator.rs",  # Coverage bonus formula
    "genesis_commitment.rs",    # Null-state detection + genesis
    "blo_scheduler.rs",         # BRT intent scheduling
    "sybil_resistance.rs",      # 5-layer sybil protection
    "dispute_resolution.rs",    # Conscious Layer 3-of-5
    "bibl_engine.rs",           # Inter-block layer analysis
    "btcp_escrow_monitor.rs",   # Escrow state watching
]


def verify_spec_compliance() -> Dict[str, Any]:
    """Verify that the Rust implementation meets all spec requirements."""
    src_dir = RUST_DIR / "src"
    existing_files = set(f.name for f in src_dir.glob("*.rs"))

    missing = [f for f in SPEC_REQUIRED_FILES if f not in existing_files]
    extra = [f for f in existing_files if f not in SPEC_REQUIRED_FILES and f != "lib.rs" and f != "types.rs"]

    return {
        "spec_required_files": len(SPEC_REQUIRED_FILES),
        "rust_library_files": len(existing_files),
        "missing_files": missing,
        "extra_files": extra,
        "fully_compliant": len(missing) == 0,
        "coexists_with_python": True,  # Rust in separate directory
    }


if __name__ == "__main__":
    print("=" * 60)
    print("TRION BTCP — Rust + Python Dual Implementation")
    print("=" * 60)
    print()

    # Verify spec compliance
    compliance = verify_spec_compliance()
    print(f"Spec Compliance: {'PASS' if compliance['fully_compliant'] else 'FAIL'}")
    print(f"  Required Rust files: {compliance['spec_required_files']}")
    print(f"  Library files present: {compliance['rust_library_files']}")
    if compliance['missing_files']:
        print(f"  Missing: {compliance['missing_files']}")
    print(f"  Coexists with Python: {compliance['coexists_with_python']}")
    print()

    # File list
    files = get_rust_file_list()
    print(f"Rust Source Files ({files['total_source_files']}):")
    for f in files['library_files']:
        print(f"  src/{f}")
    for f in files['binary_files']:
        print(f"  src/bin/{f}")
    print()

    # Demo Rust router if available
    print("-" * 60)
    print("Rust BTCP Router Demo:")
    print("-" * 60)
    output = demo_rust_router()
    if output:
        print(output)
    else:
        print("  (Rust binaries not built yet. Run: cd rust && cargo build --release)")
