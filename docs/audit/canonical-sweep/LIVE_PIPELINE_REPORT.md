# LIVE PIPELINE REPORT (§29 — Master Sweep 2026-09-04)

Boot (one bash invocation, in-sandbox): faiss_service :8000 + serve.py :5000 +
bh_streamer (8-chain limit → 44 workers) for 80 seconds.

## Evidence (real numbers, LIVE-2)

- **Streamer:** 5,195 BHs / 69.2 BH/s / **0 write errors**; 5,760 FAISS
  vectors; 3,990 entities.
- **External RPCs LIVE:** ETH 25,906,540 (RPC tip …542), Solana slot
  444,343,783, BTC 965,523.
- **POST /api/v1/bh:** valid 93-byte dual-strand BH; **independent recompute
  of the strands matched the API output exactly.**
- **API battery:** 30/30 GET + 6/6 POST respond; 28/30 with FAISS
  intentionally down (the 2 = documented FAISS gates).
- **WebSocket:** live connect on /feed — health + signal push received
  (werkzeug WS-upgrade 400 → documented polling fallback).
- **Loop closure (after fix b4a64fa):** entity write key == read key —
  history lookups now reach streamed vectors (94.5% were unreachable before).

## CHAIN → TRION → BIBL → BTCP → EXECUTION → TRION

| Stage | Locally live? | Evidence |
|---|---|---|
| CHAIN → TRION | ✅ | 69 BH/s over real public RPCs |
| TRION → AKASHIC | ✅ | vectors + ledger growth, loop closed |
| AKASHIC → SIGNAL/ORACLE | ✅ | coherence 0.9966, AWA gate, WS push |
| BIBL reads TRION | ✅ | beo_lookup → real ledger rows |
| BTCP escrow + cert | ✅ local (py-evm real execution) | 16/16 attack matrix |
| EXECUTION on live chains | ❌ EXTERNAL | funded relayer wallet + deployed contracts |
| TRION feedback | ✅ mechanism (executed tx → new BH); live close needs the external leg | |

0G: API routes 200 with honest errors; CLI toolchain-blocked (ethers deps);
Galileo testnet was live in prior full-run (698 signals, 474 anomalies
sealed) — re-verification of on-chain state needs the CLI deps (external).
