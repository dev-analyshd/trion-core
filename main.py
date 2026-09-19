"""
TRION Sensing Oracle — entry point for gunicorn / deployment.
Serves the Oracle API + static frontend on port 5000.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api"))
from app import app  # noqa: F401 — imported for gunicorn


def _log_pqc_availability() -> None:
    """Probe PQC library availability at startup.

    The L4.6 SEC(t) endpoint (SEC = LSS · PQC · CC) returns SEC=0.0 when
    kyber-py / dilithium-py / pyspx are not installed, because the real
    ML-KEM / ML-DSA / SLH-DSA round-trips cannot run.  This probe logs the
    install state of each library at startup so operators can immediately
    see which primitive is missing instead of debugging SEC=0.0 from the
    client side.  Required packages: `pip install kyber-py dilithium-py pyspx`.
    """
    probes = [
        ("kyber-py (ML-KEM / FIPS 203)", "kyber_py.ml_kem"),
        ("dilithium-py (ML-DSA / FIPS 204)", "dilithium_py.ml_dsa"),
        ("pyspx (SLH-DSA / SPHINCS+ / FIPS 205)", "pyspx.shake_128s"),
    ]
    print("TRION PQC availability probe:", flush=True)
    for label, modname in probes:
        try:
            __import__(modname)
            print(f"  [OK]   {label} -> {modname}", flush=True)
        except Exception as exc:  # noqa: BLE001 — startup probe must not crash
            print(f"  [MISS] {label} -> {modname}: {exc}", flush=True)
            print(f"         fix: /home/z/.venv/bin/python3 -m pip install "
                  f"kyber-py dilithium-py pyspx", flush=True)


if __name__ == "__main__":
    _log_pqc_availability()
    port = int(os.environ.get("PORT", 5000))
    print(f"TRION Oracle + Frontend serving on http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False)
