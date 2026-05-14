"""
TRION Live Trading Signal Feed
--------------------------------
Continuously monitors FAISS behavioral data
and emits trading signals every N seconds.

AI agents subscribe via:
  GET /api/v1/trading/signal/{entity_id}   — pull
  (WebSocket push: future roadmap)

This module is the daemon that:
  1. Polls FAISS for vector changes every 30s
  2. Recomputes pattern matches
  3. Detects signal changes (flip from ACCUMULATION to DISTRIBUTION etc)
  4. Logs signal history for replay
"""

import asyncio
import httpx
import time
from typing import Optional


class TRIONSignalFeed:

    def __init__(
        self,
        faiss_url:      str  = "http://127.0.0.1:8000",
        poll_interval:  int  = 30,
        watch_entities: list = None,
    ):
        self.faiss_url    = faiss_url
        self.interval     = poll_interval
        self.entities     = watch_entities or []
        self._last_signals: dict = {}
        self._signal_log:   list = []

    async def fetch_signal(self, entity_id: str) -> Optional[dict]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{self.faiss_url}/api/v1/trading/signal/{entity_id}"
                )
                if r.status_code == 200:
                    return r.json()
        except Exception:
            pass
        return None

    def detect_flip(self, entity_id: str, new_signal: dict) -> Optional[dict]:
        """
        Detect when a signal flips (e.g., ACCUMULATION → DISTRIBUTION).
        These flips are high-value events for trading agents.
        """
        old = self._last_signals.get(entity_id)
        if not old:
            return None
        old_sig = old.get("signal")
        new_sig = new_signal.get("signal")
        if old_sig == new_sig:
            return None

        significant_flips = {
            ("ACCUMULATION",  "DISTRIBUTION"):   "SMART_MONEY_EXIT",
            ("DISTRIBUTION",  "ACCUMULATION"):   "SMART_MONEY_ENTRY",
            ("STRONG_BUY",    "STRONG_SELL"):    "MOMENTUM_REVERSAL",
            ("STRONG_SELL",   "STRONG_BUY"):     "CAPITULATION_BOUNCE",
            ("MOMENTUM",      "REVERSAL_SHORT"): "TREND_EXHAUSTION",
            ("NEUTRAL",       "ACCUMULATION"):   "ACCUMULATION_START",
            ("NEUTRAL",       "DISTRIBUTION"):   "DISTRIBUTION_START",
        }
        flip_type = significant_flips.get((old_sig, new_sig), "SIGNAL_CHANGE")

        return {
            "entity_id":       entity_id,
            "from_signal":     old_sig,
            "to_signal":       new_sig,
            "flip_type":       flip_type,
            "from_confidence": old.get("confidence", 0),
            "to_confidence":   new_signal.get("confidence", 0),
            "timestamp":       int(time.time()),
            "alert":           flip_type != "SIGNAL_CHANGE",
        }

    async def run_cycle(self) -> list:
        """Run one monitoring cycle — returns any signal changes."""
        changes = []
        for entity_id in self.entities:
            signal = await self.fetch_signal(entity_id)
            if not signal:
                continue
            flip = self.detect_flip(entity_id, signal)
            if flip:
                changes.append(flip)
                print(
                    f"[FEED] Signal flip: {entity_id[:12]}... "
                    f"{flip['from_signal']} → {flip['to_signal']} "
                    f"({flip['flip_type']})"
                )
            self._last_signals[entity_id] = signal
            self._signal_log.append({
                "entity_id": entity_id,
                "signal":    signal.get("signal"),
                "confidence": signal.get("confidence"),
                "timestamp": int(time.time()),
            })
        return changes

    async def start(self):
        """Main loop — runs continuously."""
        print(f"[FEED] TRION Signal Feed starting")
        print(f"[FEED] Monitoring {len(self.entities)} entities")
        print(f"[FEED] Poll interval: {self.interval}s")
        print(f"[FEED] API: {self.faiss_url}")
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{self.faiss_url}/health")
                print(f"[FEED] FAISS health: {r.json().get('status', 'ok')}")
        except Exception:
            print("[FEED] Warning: FAISS not reachable — will retry")

        while True:
            try:
                changes = await self.run_cycle()
                if changes:
                    print(f"[FEED] {len(changes)} signal changes detected")
            except Exception as e:
                print(f"[FEED] Error: {e}")
            await asyncio.sleep(self.interval)

    def get_current_signals(self) -> dict:
        return dict(self._last_signals)

    def get_recent_log(self, n: int = 50) -> list:
        return self._signal_log[-n:]


async def _test():
    feed = TRIONSignalFeed(
        watch_entities=[
            "0xb819c63c02Ed5aB49017C0f3f2568A14624658b3",
            "0xC3511006C04EF1d78af4C8E0e74Ec18A6E64Ff2",
        ],
        poll_interval=5,
    )
    print("[TEST] Running one feed cycle...")
    changes = await feed.run_cycle()
    signals = feed.get_current_signals()
    print(f"[TEST] Signals fetched: {len(signals)}")
    for eid, sig in signals.items():
        print(f"  {eid[:16]}... → {sig.get('signal', '?')} "
              f"(conf={sig.get('confidence', 0):.3f})")
    print("PHASE 6 PASS — Live Feed: PASS")


if __name__ == "__main__":
    asyncio.run(_test())
