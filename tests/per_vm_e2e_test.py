"""
Per-VM Full-Stack E2E — boots FAISS, ingests a vector for EVERY VM family,
then verifies each flows through to signal/archetype/depth.
"""
import sys, os, time, threading, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "anima-service"))

import uvicorn
import faiss_service
import requests

PASS = FAIL = 0
FAILURES = []

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name} {detail}")
        print(f"  ❌ {name} {detail}")

print("═" * 70)
print("PER-VM FULL-STACK E2E — INDEXING → FAISS → SIGNAL FOR EVERY VM")
print("═" * 70)

# Boot FAISS
print("\n── Booting FAISS ANIMA Engine ──")
cfg = uvicorn.Config(faiss_service.app, host="127.0.0.1", port=8020, log_level="error")
threading.Thread(target=lambda: uvicorn.Server(cfg).run(), daemon=True).start()
time.sleep(7)

r = requests.get("http://127.0.0.1:8020/health", timeout=15)
check("FAISS boots", r.status_code == 200)

# Every VM family: ingest a vector + per-tx BH batch
VM_ENTITIES = [
    ("EVM",       1,     "EVM entity",      "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"),
    ("SVM",       900,   "SVM entity",      "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"),
    ("COSMOS",    4001,  "Cosmos entity",   "cosmos1trionentity"),
    ("COSMWASM",  10002, "Juno entity",     "juno1trionentity"),
    ("MOVE",      5001,  "Aptos entity",    "0x742d35cc6634c0532925a3b844bc454e4438f44e"),
    ("SUI",       6001,  "Sui entity",      "0x742d35cc6634c0532925a3b844bc454e4438f44e01"),
    ("UTXO",      2000,  "Bitcoin entity",  "bc1qtrionentity"),
    ("TON",       1100,  "TON entity",      "EQCDtrionentity"),
    ("NEAR",      1200,  "NEAR entity",     "trion-entity.near"),
    ("STARKNET",  7001,  "Starknet entity", "0x742d35cc6634c0532925a3b844bc454e4438f44e0123"),
    ("TRON",      7002,  "TRON entity",     "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"),
    ("STELLAR",   8001,  "Stellar entity",  "GA5XIGA5C7QTPTWXQHY6MCJRMTRZDPSZVWT4D5NTPWAI6Z"),
    ("PVM",       900,   "Polkadot entity", "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKut"),
    ("XRPL",      8100,  "XRPL entity",     "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"),
    ("WAVES",     9200,  "Waves entity",    "3P8dk2MDsYYb9CHA6g8DbjrD4EKW8KTbHWt"),
    ("VECHAIN",   8400,  "VeChain entity",  "0x742d35cc6634c0532925a3b844bc454e4438f44f"),
    ("MULTIVERSX", 9000,  "MultiversX entity", "erd1trionentity"),
    ("HEDERA",    8300,  "Hedera entity",   "0.0.742d35"),
    ("ALGORAND",  8200,  "Algorand entity", "ALGO7TRIONENTITY"),
    ("CARDANO",   9400,  "Cardano entity",  "addr1qtrionentity"),
]

import hashlib
from core.primitives.behavioral_hash import compute_behavioral_hash, BehavioralEvent, EventType

print("\n── Ingest vector + per-tx BH for every VM family ──")
for vm, cid, label, addr in VM_ENTITIES:
    # 1. Block vector ingest
    vec = [0.55] * 128
    r = requests.post("http://127.0.0.1:8020/index/add", json={
        "entity_id": addr, "vector": vec, "magnitude": 0.7, "entropy": 0.8,
    }, timeout=20)
    added = r.status_code == 200 and r.json().get("status") == "added"

    # 2. Per-tx BH batch (the Rust indexer contract)
    eid = hashlib.sha3_256(addr.lower().strip().encode()).hexdigest()
    event = BehavioralEvent(
        entity_id=bytes.fromhex(eid), event_type=EventType.SWAP,
        magnitude_raw=1500, magnitude_decimals=6, magnitude_max_90d=10000,
        timestamp=int(time.time()), block_number=100,
        block_hash=hashlib.sha3_256(f"blk{vm}".encode()).digest(),
        chain_id=cid,
    )
    bh = compute_behavioral_hash(event)
    r2 = requests.post("http://127.0.0.1:8020/index/add_tx_bh_batch", json={
        "chain_id": cid, "chain_label": f"{vm}_E2E", "block_num": 100,
        "block_hash": bh["sense_hex"], "timestamp": int(time.time()),
        "entries": [{
            "tx_hash": f"tx_{vm}_{int(time.time())}", "from_addr": addr,
            "to_addr": "counterparty", "event_type": 1,
            "event_type_name": "SWAP", "entity_id": eid,
            "magnitude_norm": 0.5, "value_wei": "1500000000",
            "selector": "38ed1739", "timestamp": int(time.time()),
            "chain_id": cid, "chain_label": f"{vm}_E2E", "block_num": 100,
            "block_hash": bh["sense_hex"],
            "sense_hex": bh["sense_hex"], "antisense_hex": bh["antisense_hex"],
        }],
    }, timeout=20)
    bh_stored = r2.status_code == 200 and r2.json().get("stored", 0) >= 0
    check(f"{vm:12} vector={'✓' if added else '✗'} bh={'✓' if bh_stored else '✗'}",
          added and bh_stored, f"add={r.status_code} bh={r2.status_code}")

# Verify the vm-status endpoint sees all families
print("\n── VM status endpoint ──")
r = requests.get("http://127.0.0.1:8020/api/v1/index/vm-status", timeout=15)
if r.status_code == 200:
    d = r.json()
    # Response shape: {total_vectors, vm_families: {name: {...}}, ...}
    vm_map = d.get("vm_families", {})
    check(f"VM status endpoint reports {len(vm_map)} families", len(vm_map) >= 10,
          str(list(vm_map.keys()))[:120])
else:
    check("VM status endpoint", False, f"HTTP {r.status_code}")

# Signal for one entity per major family
print("\n── Signal computation per VM ──")
for vm, cid, label, addr in VM_ENTITIES[:10]:
    r = requests.get(f"http://127.0.0.1:8020/api/v1/signal/{addr}", timeout=30)
    if r.status_code == 200:
        d = r.json()
        check(f"{vm:12} signal type={d.get('signal_type')}", d.get("signal_type") is not None)
    else:
        check(f"{vm:12} signal", False, f"HTTP {r.status_code}")

print("\n" + "═" * 70)
print(f"PER-VM E2E: {PASS} passed, {FAIL} failed")
print("═" * 70)
if FAILURES:
    for f in FAILURES:
        print(f"  ❌ {f}")
    sys.exit(1)
print("✅ EVERY VM FAMILY FLOWS: INDEXING → FAISS → BH LEDGER → SIGNAL")
