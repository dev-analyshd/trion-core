#!/usr/bin/env python3
"""daemon-30tx.py — Double-fork daemon to run the 37-tx BTC-Stacks test.
Survives parent shell termination by reparenting to init.
Restarts on crash (the test script is resumable — skips completed tests).
"""
import os
import sys
import time
import subprocess

SCRIPT = "/home/z/my-project/trion-core/btc-tools/stacks/run-btc-stacks-30tx.mjs"
LOG = "/tmp/btc-stacks-30tx.log"
PIDFILE = "/tmp/btc-stacks-30tx-daemon.pid"
RESULTS = "/home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/v4-btc-stacks-30tx-results.json"
WORKDIR = "/home/z/my-project/trion-core/btc-tools/stacks"


def is_complete():
    try:
        import json
        d = json.load(open(RESULTS))
        return len(d.get("tests", [])) >= 37
    except Exception:
        return False


def main():
    if os.fork() != 0:
        time.sleep(0.5)
        return 0

    os.setsid()
    os.umask(0)

    if os.fork() != 0:
        os._exit(0)

    sys.stdin.flush()
    sys.stdout.flush()
    sys.stderr.flush()
    with open("/dev/null", "rb") as f:
        os.dup2(f.fileno(), 0)
    log_fd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(log_fd, 1)
    os.dup2(log_fd, 2)

    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))

    while not is_complete():
        ts = time.strftime("%H:%M:%S")
        os.write(2, f"[{ts}] starting run-btc-stacks-30tx.mjs\n".encode())
        proc = subprocess.run(
            ["node", SCRIPT],
            cwd=WORKDIR,
            stdout=None,
            stderr=None,
            timeout=3600,
        )
        ts = time.strftime("%H:%M:%S")
        os.write(2, f"[{ts}] run-btc-stacks-30tx.mjs exited with code {proc.returncode}\n".encode())
        if is_complete():
            break
        time.sleep(10)

    ts = time.strftime("%H:%M:%S")
    os.write(2, f"[{ts}] all 37 tests complete. exiting daemon.\n".encode())
    os.unlink(PIDFILE)


if __name__ == "__main__":
    main()
