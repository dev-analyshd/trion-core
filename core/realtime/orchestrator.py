#!/usr/bin/env python3
"""
TRION Unified Indexer Orchestrator
====================================
Supervises all indexer processes — restarts on crash, centralizes logging,
aggregates health checks.

Per spec Phase 2 Step 2.3 + 2.4:
  - Starts each indexer with appropriate env vars
  - Restarts on crash with exponential backoff
  - Centralized logging with chain labels
  - Health check endpoint aggregation
  - RPC endpoint health monitor (pings every 60s)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import IntEnum


class IndexerStatus(IntEnum):
    STOPPED = 0
    RUNNING = 1
    CRASHED = 2
    RESTARTING = 3


@dataclass
class IndexerProcess:
    name: str
    command: List[str]
    env: Dict[str, str] = field(default_factory=dict)
    process: Optional[subprocess.Popen] = None
    status: IndexerStatus = IndexerStatus.STOPPED
    last_start: float = 0.0
    restart_count: int = 0
    last_health: float = 0.0
    health_ok: bool = False


class IndexerOrchestrator:
    """
    Manages all TRION indexer processes.

    In production, this runs as a supervisor process that:
    1. Starts the Python BH streamer (all 55 EVM chains)
    2. Starts the FAISS service
    3. Starts the Flask Oracle API
    4. Starts the Node.js relayer
    5. Monitors all processes and restarts on crash
    """

    def __init__(self):
        self._processes: Dict[str, IndexerProcess] = {}
        self._stop = threading.Event()
        self._rpc_health: Dict[int, Dict] = {}

    def register(self, name: str, command: List[str], env: Optional[Dict] = None):
        """Register an indexer process."""
        self._processes[name] = IndexerProcess(
            name=name, command=command, env=env or {}
        )

    def start_all(self):
        """Start all registered processes."""
        for name, proc in self._processes.items():
            self._start_one(name)
        # Start RPC health monitor
        threading.Thread(target=self._rpc_health_monitor, daemon=True).start()
        # Start process supervisor
        threading.Thread(target=self._supervisor, daemon=True).start()

    def _start_one(self, name: str):
        """Start a single process."""
        proc = self._processes[name]
        env = {**os.environ, **proc.env}
        try:
            proc.process = subprocess.Popen(
                proc.command,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            proc.status = IndexerStatus.RUNNING
            proc.last_start = time.time()
            print(f"[orchestrator] Started {name} (pid={proc.process.pid})")
        except Exception as e:
            proc.status = IndexerStatus.CRASHED
            print(f"[orchestrator] Failed to start {name}: {e}")

    def _supervisor(self):
        """Monitor processes and restart on crash."""
        while not self._stop.is_set():
            for name, proc in self._processes.items():
                if proc.process and proc.process.poll() is not None:
                    # Process crashed
                    proc.status = IndexerStatus.CRASHED
                    proc.restart_count += 1
                    backoff = min(60, 2 ** min(proc.restart_count, 6))
                    print(f"[orchestrator] {name} crashed (exit={proc.process.returncode}), restarting in {backoff}s")
                    time.sleep(backoff)
                    self._start_one(name)
            time.sleep(5)

    def _rpc_health_monitor(self):
        """Ping every RPC endpoint every 60 seconds."""
        from core.realtime.bh_streamer import CHAIN_RPCS
        while not self._stop.is_set():
            for chain_id, config in CHAIN_RPCS.items():
                try:
                    start = time.time()
                    req = urllib.request.Request(
                        config["rpc"],
                        data=json.dumps({"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}).encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = json.loads(resp.read())
                        latency = (time.time() - start) * 1000
                        self._rpc_health[chain_id] = {
                            "status": "ok",
                            "latency_ms": round(latency, 1),
                            "chain": config["name"],
                            "last_check": time.time(),
                        }
                except Exception as e:
                    self._rpc_health[chain_id] = {
                        "status": "error",
                        "error": str(e)[:100],
                        "chain": config["name"],
                        "last_check": time.time(),
                    }
            time.sleep(60)

    def get_status(self) -> Dict:
        """Get status of all processes and RPC endpoints."""
        return {
            "processes": {
                name: {
                    "status": p.status.name,
                    "pid": p.process.pid if p.process else None,
                    "restart_count": p.restart_count,
                    "uptime": time.time() - p.last_start if p.status == IndexerStatus.RUNNING else 0,
                }
                for name, p in self._processes.items()
            },
            "rpc_health": {
                str(k): v for k, v in self._rpc_health.items()
            },
            "total_chains_monitored": len(self._rpc_health),
            "healthy_chains": sum(1 for v in self._rpc_health.values() if v["status"] == "ok"),
            "timestamp": time.time(),
        }

    def stop_all(self):
        """Stop all processes."""
        self._stop.set()
        for name, proc in self._processes.items():
            if proc.process:
                proc.process.terminate()
                proc.status = IndexerStatus.STOPPED
                print(f"[orchestrator] Stopped {name}")


# ── Default process configurations ────────────────────────────────────────────

def default_processes() -> Dict[str, IndexerProcess]:
    """Return the default set of TRION processes."""
    return {
        "bh_streamer": IndexerProcess(
            name="bh_streamer",
            command=[sys.executable, "-m", "core.realtime.bh_streamer"],
            env={"PYTHONPATH": "/home/z/my-project/repos/trion-core"},
        ),
        "flask_api": IndexerProcess(
            name="flask_api",
            command=[sys.executable, "-m", "gunicorn", "--workers", "2", "--bind", "127.0.0.1:5000",
                     "--timeout", "120", "--threads", "8", "api.app:app"],
            env={"PYTHONPATH": "/home/z/my-project/repos/trion-core:/home/z/my-project/repos/trion-core/api"},
        ),
    }


if __name__ == "__main__":
    print("=== TRION Unified Indexer Orchestrator ===\n")
    orch = IndexerOrchestrator()

    # Register processes
    for name, proc in default_processes().items():
        orch.register(name, proc.command, proc.env)

    # Start everything
    orch.start_all()

    # Run for 60 seconds and print status
    for i in range(6):
        time.sleep(10)
        status = orch.get_status()
        print(f"\n--- Status at {i*10+10}s ---")
        print(f"  Processes: {len(status['processes'])}")
        for name, s in status["processes"].items():
            print(f"    {name}: {s['status']} (restarts={s['restart_count']})")
        print(f"  RPC health: {status['healthy_chains']}/{status['total_chains_monitored']} chains healthy")

    orch.stop_all()
    print("\nOrchestrator stopped.")
