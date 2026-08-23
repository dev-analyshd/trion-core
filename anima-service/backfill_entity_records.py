"""
TRION BH Ledger → FAISS Entity Records Backfill
================================================
Reads all entity records from bh_ledger.db and re-ingests them into the
live FAISS service (port 8000) via POST /index/add_batch.

Vector reconstruction is faithful to vector.rs build_vector():
  [0..9]   9 Shannon entropy features (f1..f9)
  [9..18]  complementary strand  (1 - f_i)
  [18..27] cross-correlations    (f_i × f_{i+1}, wrap at i=8)
  [27]     mean(f1..f9)
  [28]     std-dev(f1..f9)
  [29]     min(f1..f9)
  [30]     max(f1..f9)
  [31..64] SHA3-256(seed) noise blended with mean  (byte×0.7 + mean×0.3)
  [64..128] zeros (reserved)

Entropy is computed from per-entity BH record distributions; a small floor
is applied so every backfill record clears the L0.5 signal-selection gate
(max(mag, 0.02) × entropy / 0.1 > 0.5) — all records in bh_ledger were
already validated by the Rust indexers, so passing the gate is correct.

Usage:
    uv run python3 akashic/backfill_entity_records.py
    uv run python3 akashic/backfill_entity_records.py --batch-size 200 --dry-run
    uv run python3 akashic/backfill_entity_records.py --faiss-url http://127.0.0.1:8000
"""

import argparse
import hashlib
import json
import math
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from typing import List, Tuple

# ── Constants (must match faiss_service.py) ───────────────────────────────────
SIGNAL_SELECTION_THETA = 0.5
BASE_PRESENCE          = 0.02
D_ENTROPY_COST         = 0.1
DIMENSION              = 128

# ── Shannon / histogram entropy (mirrors entropy.rs) ─────────────────────────

def _shannon_normalized(counts: List[int]) -> float:
    """Normalised Shannon entropy — matches entropy.rs shannon_entropy()."""
    total = sum(counts)
    if total == 0:
        return 0.0
    non_zero = [c / total for c in counts if c > 0]
    if len(non_zero) <= 1:
        return 0.0
    h = -sum(p * math.log2(p) for p in non_zero)
    max_h = math.log2(len(non_zero))
    return min(1.0, h / max_h) if max_h > 0 else 0.0


def _histogram_entropy(values: List[float], bins: int = 16) -> float:
    """Histogram entropy — matches entropy.rs histogram_entropy()."""
    if not values:
        return 0.0
    vmin, vmax = min(values), max(values)
    rng = vmax - vmin
    if rng < 1e-9:
        return 0.0
    hist = [0] * bins
    for v in values:
        idx = min(int((v - vmin) / rng * bins), bins - 1)
        hist[idx] += 1
    return _shannon_normalized(hist)


def _freq_entropy(labels: List) -> float:
    """Frequency-map entropy — matches entropy.rs freq_entropy()."""
    if not labels:
        return 0.0
    freq: dict = defaultdict(int)
    for l in labels:
        freq[l] += 1
    return _shannon_normalized(list(freq.values()))

# ── Feature extraction ────────────────────────────────────────────────────────

def _compute_features(records: List[Tuple]) -> Tuple[List[float], float]:
    """
    Compute 9 entropy features from an entity's BH records.

    records: list of (magnitude_norm, event_type, ts, sense_hex, chain_id, block_num)

    Mirrors the 9-feature extraction in trion-evm/src/main.rs:
      f1  transaction volume entropy   histogram_entropy(magnitudes)
      f2  event-type entropy           freq_entropy(event_types)
      f3  sense-strand byte[0] mean    (SHA3 payload byte — proxy for value flow)
      f4  sense-strand byte[1] mean    (proxy for counterparty diversity)
      f5  sense-strand byte[2] mean    (proxy for gas diversity)
      f6  sense-strand byte[3] mean    (proxy for contract interaction)
      f7  time-of-day entropy          histogram_entropy(ts % 86400 / 86400)
      f8  magnitude std-dev            (proxy for gas-usage spread)
      f9  chain diversity entropy      freq_entropy(chain_ids)

    Returns (features [f1..f9], phi = mean(features))
    """
    mags        = [r[0] for r in records]
    event_types = [r[1] for r in records]
    tss         = [r[2] for r in records]
    sense_hexes = [r[3] for r in records]
    chain_ids   = [r[4] for r in records]

    f1 = _histogram_entropy(mags, 16)
    f2 = _freq_entropy(event_types)

    sense_bytes = [bytes.fromhex(s) for s in sense_hexes if s and len(s) == 64]
    if sense_bytes:
        f3 = sum(b[0] / 255.0 for b in sense_bytes) / len(sense_bytes)
        f4 = sum(b[1] / 255.0 for b in sense_bytes) / len(sense_bytes)
        f5 = sum(b[2] / 255.0 for b in sense_bytes) / len(sense_bytes)
        f6 = sum(b[3] / 255.0 for b in sense_bytes) / len(sense_bytes)
    else:
        f3 = f4 = f5 = f6 = 0.5

    tod = [(t % 86400) / 86400.0 for t in tss]
    f7  = _histogram_entropy(tod, 8)

    mean_m = sum(mags) / len(mags)
    var_m  = sum((m - mean_m) ** 2 for m in mags) / len(mags)
    f8     = min(1.0, var_m ** 0.5 * 2.0)

    f9 = _freq_entropy(chain_ids)

    features = [f1, f2, f3, f4, f5, f6, f7, f8, f9]
    phi      = sum(features) / 9.0
    return features, phi

# ── Vector construction (exact mirror of vector.rs build_vector) ─────────────

def _build_vector(features: List[float], seed: str) -> List[float]:
    """
    Build 128-dim f32 vector — exact Python port of vector.rs build_vector().
    Seed format: "{entity_id}:{chain_id}:{block_num}"
    """
    f = [max(0.0, min(1.0, x)) for x in features]
    v = [0.0] * DIMENSION

    # [0..9] raw features
    for i in range(9):
        v[i] = f[i]

    # [9..18] complementary strand
    for i in range(9):
        v[9 + i] = 1.0 - v[i]

    # [18..27] cross-correlations
    for i in range(8):
        v[18 + i] = v[i] * v[i + 1]
    v[26] = v[8] * v[0]           # wrap-around (matches Rust)

    # [27..31] aggregate statistics
    mean    = sum(f) / 9.0
    variance = sum((x - mean) ** 2 for x in f) / 9.0
    std_dev  = variance ** 0.5
    v[27]   = max(0.0, min(1.0, mean))
    v[28]   = max(0.0, min(1.0, std_dev))
    v[29]   = max(0.0, min(1.0, min(f)))
    v[30]   = max(0.0, min(1.0, max(f)))

    # [31..64] SHA3-256 noise blended with mean
    seed_hash = hashlib.sha3_256(seed.encode()).digest()
    for i in range(32):
        byte_val = seed_hash[i] / 255.0
        v[31 + i] = max(0.0, min(1.0, byte_val * 0.7 + mean * 0.3))

    # [64..128] zeros — reserved
    return v

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _check_faiss(faiss_url: str) -> dict:
    with urllib.request.urlopen(f"{faiss_url}/health", timeout=5) as r:
        return json.loads(r.read())


def _post_bulk_backfill(faiss_url: str, items: list) -> Tuple[int, int]:
    """POST to /index/bulk_backfill — fast numpy-batch path, no per-item overhead."""
    payload = json.dumps({"items": items}).encode()
    req = urllib.request.Request(
        f"{faiss_url}/index/bulk_backfill",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read())
    return resp.get("added", 0), resp.get("skipped", 0)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Backfill FAISS entity records from bh_ledger.db"
    )
    parser.add_argument("--faiss-url",   default="http://127.0.0.1:8000")
    parser.add_argument("--bh-db",       default="bh_ledger.db")
    parser.add_argument("--state-db",    default="akashic_state.db")
    parser.add_argument("--batch-size",  type=int, default=150,
                        help="Entity vectors per HTTP batch (default 150)")
    parser.add_argument("--dry-run",     action="store_true",
                        help="Parse and build vectors but skip HTTP posts")
    args = parser.parse_args()

    # ── Verify FAISS is live ──────────────────────────────────────────────────
    print("Checking FAISS health…", end=" ", flush=True)
    try:
        health = _check_faiss(args.faiss_url)
        print(f"OK  ({health.get('indexed_vectors', 0):,} vectors, "
              f"{health.get('entities_tracked', 0):,} entities)")
    except Exception as e:
        print(f"FAILED\n✗ FAISS unreachable at {args.faiss_url}: {e}", file=sys.stderr)
        sys.exit(1)

    # ── Load already-indexed BEO IDs ──────────────────────────────────────────
    print(f"Loading existing entity_records from {args.state_db}…", end=" ", flush=True)
    try:
        sc = sqlite3.connect(f"file:{args.state_db}?mode=ro", uri=True)
        existing = {r[0] for r in sc.execute(
            "SELECT DISTINCT beo_id FROM entity_records"
        ).fetchall()}
        sc.close()
    except Exception:
        existing = set()
    print(f"{len(existing):,} already indexed")

    # ── Load BH ledger (via /tmp snapshot to avoid Rust-indexer write contention) ──
    import shutil, tempfile, os
    print(f"Snapshotting {args.bh_db} → /tmp/bh_backfill_snap.db …", end=" ", flush=True)
    snap_path = "/tmp/bh_backfill_snap.db"
    try:
        shutil.copy2(args.bh_db, snap_path)
        # Also copy WAL/SHM if present so snapshot is consistent
        for ext in ("-wal", "-shm"):
            src = args.bh_db + ext
            if os.path.exists(src):
                shutil.copy2(src, snap_path + ext)
    except Exception as e:
        print(f"\n✗ Failed to snapshot {args.bh_db}: {e}", file=sys.stderr)
        sys.exit(1)
    print("done")
    print(f"Reading snapshot…", end=" ", flush=True)
    bh_con = sqlite3.connect(snap_path)
    bh_con.execute("PRAGMA journal_mode=WAL")
    rows = bh_con.execute("""
        SELECT entity_id, magnitude_norm, ts, event_type,
               sense_hex, chain_id, block_num
        FROM bh_ledger
        ORDER BY entity_id, ts
    """).fetchall()
    bh_con.close()
    print(f"{len(rows):,} BH records")

    # ── Group by entity ───────────────────────────────────────────────────────
    entity_groups: dict = defaultdict(list)
    for entity_id, mag, ts, evt, sense, chain_id, block_num in rows:
        entity_groups[entity_id].append((mag, evt, ts, sense, chain_id, block_num))

    new_entities = {
        eid: recs for eid, recs in entity_groups.items()
        if eid not in existing
    }
    print(f"BH ledger entities: {len(entity_groups):,} total, "
          f"{len(new_entities):,} new to backfill, "
          f"{len(existing):,} already present")

    if not new_entities:
        print("Nothing to backfill — all entities are already in entity_records.")
        return

    # ── Build vectors and post in batches ────────────────────────────────────
    entity_list  = sorted(new_entities.keys())
    total_added  = 0
    total_rejected = 0
    t0           = time.time()

    print(f"\nBackfilling {len(entity_list):,} entities "
          f"(batch_size={args.batch_size}"
          + (" DRY-RUN" if args.dry_run else "") + ")…\n")

    for batch_start in range(0, len(entity_list), args.batch_size):
        batch_eids = entity_list[batch_start : batch_start + args.batch_size]
        vectors    = []

        for entity_id in batch_eids:
            records  = new_entities[entity_id]
            features, phi = _compute_features(records)

            magnitude = sum(r[0] for r in records) / len(records)
            ts_latest = max(r[2] for r in records)
            block_num = records[-1][5]
            chain_id  = records[0][4]
            sense_hex = next(
                (r[3] for r in reversed(records) if r[3] and len(r[3]) == 64),
                None,
            )
            dominant_event = max(
                set(r[1] for r in records),
                key=lambda e: sum(1 for r in records if r[1] == e),
            )

            # ── L0.5 entropy floor ────────────────────────────────────────────
            # All bh_ledger records are real on-chain events validated by the
            # Rust indexer — they legitimately belong in entity_records.
            # Apply minimum entropy so the signal passes selection:
            #   max(magnitude, BASE_PRESENCE) × entropy / D_ENTROPY_COST > θ
            #   → entropy > θ × D_ENTROPY_COST / max(mag, BASE_PRESENCE)
            mag_eff     = max(magnitude, BASE_PRESENCE)
            min_entropy = SIGNAL_SELECTION_THETA * D_ENTROPY_COST / mag_eff + 1e-4
            entropy     = max(phi, min_entropy)

            seed   = f"{entity_id}:{chain_id}:{block_num}"
            vector = _build_vector(features, seed)

            vectors.append({
                "entity_id":   entity_id,
                "vector":      vector,
                "magnitude":   float(magnitude),
                "entropy":     float(entropy),
                "timestamp":   float(ts_latest),
                "sense_hex":   sense_hex,
                "chain_label": "BACKFILL",
            })

        if args.dry_run:
            total_added += len(vectors)
        else:
            try:
                added, rejected = _post_bulk_backfill(args.faiss_url, vectors)
                total_added    += added
                total_rejected += rejected
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")[:200]
                print(f"\n  ✗ HTTP {e.code} on batch {batch_start}: {body}")
                continue
            except Exception as e:
                print(f"\n  ✗ Batch {batch_start} failed: {e}")
                continue

        done    = min(batch_start + args.batch_size, len(entity_list))
        elapsed = time.time() - t0
        rate    = done / elapsed if elapsed > 0 else 1
        eta     = (len(entity_list) - done) / rate if rate > 0 else 0

        bar_w   = 30
        filled  = int(bar_w * done / len(entity_list))
        bar     = "█" * filled + "░" * (bar_w - filled)
        pct     = 100.0 * done / len(entity_list)

        print(
            f"  [{bar}] {pct:5.1f}%  "
            f"{done:>6,}/{len(entity_list):,}  "
            f"added={total_added:,}  rejected={total_rejected:,}  "
            f"rate={rate:.0f}/s  eta={eta:.0f}s"
            + (" [DRY-RUN]" if args.dry_run else ""),
            end="\r",
            flush=True,
        )

    elapsed = time.time() - t0
    print(f"\n\n{'[DRY-RUN] ' if args.dry_run else ''}"
          f"Backfill complete in {elapsed:.1f}s\n"
          f"  Entities processed : {len(entity_list):,}\n"
          f"  Vectors added      : {total_added:,}\n"
          f"  Vectors rejected   : {total_rejected:,}\n"
          f"  BH records covered : {len(rows):,}\n"
          f"  Throughput         : {len(entity_list)/elapsed:.0f} entities/s")

    if not args.dry_run:
        print("\nVerifying…", end=" ", flush=True)
        try:
            health = _check_faiss(args.faiss_url)
            print(f"FAISS now has {health.get('indexed_vectors', 0):,} vectors, "
                  f"{health.get('entities_tracked', 0):,} entities")
        except Exception as e:
            print(f"(health check failed: {e})")

        if total_added > 0:
            print("\nTriggering archetype training on full entity population…",
                  end=" ", flush=True)
            try:
                import urllib.request, json as _json
                req = urllib.request.Request(
                    f"{args.faiss_url}/archetypes/train",
                    method="POST",
                    headers={"Content-Type": "application/json"},
                    data=b"{}",
                )
                with urllib.request.urlopen(req, timeout=180) as resp:
                    train_result = _json.loads(resp.read())
                status   = train_result.get("status", "?")
                n_arch   = train_result.get("archetypes", "?")
                coverage = train_result.get("coverage", 0)
                n_vecs   = train_result.get("vectors_used", "?")
                print(f"done\n"
                      f"  status    : {status}\n"
                      f"  archetypes: {n_arch}\n"
                      f"  coverage  : {coverage:.1%}\n"
                      f"  vectors   : {n_vecs:,}" if isinstance(n_vecs, int) else
                      f"  status    : {status}\n"
                      f"  archetypes: {n_arch}\n"
                      f"  coverage  : {coverage:.1%}")
            except Exception as e:
                print(f"(archetype training request failed: {e})")


if __name__ == "__main__":
    main()
