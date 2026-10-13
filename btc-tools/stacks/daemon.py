#!/usr/bin/env python3
"""
daemon.py — True double-fork daemon to run the 50-tx test.
Survives parent shell termination by reparenting to init.
"""
import os
import sys
import time
import subprocess
import signal

SCRIPT = "/home/z/my-project/trion-core/btc-tools/stacks/run-50tx-tests.mjs"
LOG = "/tmp/run-50tx.log"
PIDFILE = "/tmp/run-50tx-daemon.pid"
RESULTS = "/home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/v3-50tx-results.json"
WORKDIR = "/home/z/my-project/trion-core/btc-tools/stacks"


def is_complete():
    try:
        import json
        d = json.load(open(RESULTS))
        return d.get("summary", {}).get("completed", 0) >= 50
    except Exception:
        return False


def main():
    # First fork — detach from parent
    if os.fork() != 0:
        # Parent: write pidfile + exit immediately
        time.sleep(0.5)
        return 0

    # Decouple from parent environment
    os.setsid()
    os.umask(0)

    # Second fork — prevent re-acquiring a controlling terminal
    if os.fork() != 0:
        os._exit(0)

    # Redirect stdin/stdout/stderr
    sys.stdin.flush()
    sys.stdout.flush()
    sys.stderr.flush()
    with open("/dev/null", "rb") as f:
        os.dup2(f.fileno(), 0)
    log_fd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(log_fd, 1)
    os.dup2(log_fd, 2)

    # Write pidfile
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))

    # Loop forever — restart the test if it dies
    while not is_complete():
        ts = time.strftime("%H:%M:%S")
        os.write(2, f"[{ts}] starting run-50tx-tests.mjs\n".encode())
        proc = subprocess.run(
            ["node", SCRIPT],
            cwd=WORKDIR,
            stdout=None,
            stderr=None,
            timeout=10800,  # 3 hours max per run
        )
        ts = time.strftime("%H:%M:%S")
        os.write(2, f"[{ts}] run-50tx-tests.mjs exited with code {proc.returncode}\n".encode())
        if is_complete():
            break
        time.sleep(10)

    ts = time.strftime("%H:%M:%S")
    os.write(2, f"[{ts}] all 50 tests complete. exiting daemon.\n".encode())
    os.unlink(PIDFILE)


if __name__ == "__main__":
    main()
