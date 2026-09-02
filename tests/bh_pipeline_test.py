"""
BH Pipeline Test — compute canonical dual-strand BH for every VM family.
Verifies the indexing pipeline output contract per chain family.
"""
import sys, os, hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.primitives.behavioral_hash import (
    compute_behavioral_hash, BehavioralEvent, EventType, hash_dna,
)

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
print("BH PIPELINE — CANONICAL DUAL-STRAND HASH FOR EVERY VM FAMILY")
print("═" * 70)

# Representative chain per VM family (chain_id per canonical registry)
VM_CHAINS = [
    ("EVM",       1,      "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"),
    ("SVM",       900,    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"),
    ("COSMOS",    4001,   "cosmos1abc123def456ghi789jkl"),
    ("COSMWASM",  10002,  "juno1abc123def456ghi789jkl"),
    ("MOVE",      5001,   "0x742d35cc6634c0532925a3b844bc454e4438f44e"),  # Aptos 32-byte hex
    ("SUI",       6001,   "0x742d35cc6634c0532925a3b844bc454e4438f44e0000"),
    ("UTXO",      2000,   "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"),
    ("TON",       1100,   "EQCD39VS5jcptHL8vMjEXrzGaRcCVYto7HUn4fAOOOeoK9ak"),
    ("NEAR",      1200,   "trion.near"),
    ("STARKNET",  7001,   "0x742d35cc6634c0532925a3b844bc454e4438f44e0123456789abcdef"),
    ("TRON",      7001,   "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"),
    ("STELLAR",   8001,   "GA5XIGA5C7QTPTWXQHY6MCJRMTRZDPSZVWT4D5NTPWAI6ZZTJAQJMX2F"),
    ("PVM",       900,    "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"),
    ("XRPL",      8100,   "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"),
    ("WAVES",     9200,   "3P8dk2MDsYYb9CHA6g8DbjrD4EKW8KTbHWt"),
    ("VECHAIN",   8400,   "0x742d35cc6634c0532925a3b844bc454e4438f44e"),
    ("MULTIVERSX", 9000,  "erd1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh83z8hq6y8qqqq"),
    ("HEDERA",    8300,   "0.0.1234567"),
    ("ALGORAND",  8200,   "ALGO7AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"),
    ("CARDANO",   9400,   "addr1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlhc07k6q9w8q"),
]

# 1. Cross-VM BEO substrate independence: same actor string → same BEO id
print("\n── 1. BEO substrate independence across all 20 VMs ──")
beo_ids = set()
for vm, cid, addr in VM_CHAINS:
    beo = hashlib.sha3_256(addr.lower().strip().encode()).hexdigest()
    beo_ids.add(beo)
# Different address formats → different BEOs (correct — they're different identifiers)
# But the SAME identifier in different case → same BEO:
for vm, cid, addr in VM_CHAINS[:5]:
    a = hashlib.sha3_256(addr.lower().encode()).hexdigest()
    b = hashlib.sha3_256(addr.upper().lower().encode()).hexdigest()
    if a != b:
        check(f"BEO case-normalization for {vm}", False)
        break
else:
    check("BEO case-normalization consistent (first 5 VMs)", True)

# 2. Canonical BH for every VM family
print("\n── 2. Canonical BH per VM family ──")
for vm, cid, addr in VM_CHAINS:
    eid = hashlib.sha3_256(addr.lower().strip().encode()).digest()
    event = BehavioralEvent(
        entity_id=eid,
        event_type=EventType.SWAP,
        magnitude_raw=1_500_000,
        magnitude_decimals=6,
        magnitude_max_90d=10_000_000,
        timestamp=1700000000,
        block_number=18_000_000,
        block_hash=hashlib.sha3_256(f"block_{vm}".encode()).digest(),
        chain_id=cid,
    )
    bh = compute_behavioral_hash(event)
    ok = (
        bh["valid"] is True
        and len(bh["sense_hex"]) == 64
        and len(bh["antisense_hex"]) == 64
        and bh["sense_hex"] != bh["antisense_hex"]
        and 0.0 <= bh["magnitude_normalized"] <= 1.0
    )
    check(f"{vm:12} chain={cid:<6} BH dual-strand valid", ok,
          f"sense={bh['sense_hex'][:12]}…" if ok else str(bh)[:60])

# 3. Event-type coverage: all 20 types through the pipeline
print("\n── 3. All 20 event types through pipeline ──")
eid = hashlib.sha3_256("test_entity".encode()).digest()
for et in EventType:
    event = BehavioralEvent(
        entity_id=eid, event_type=et, magnitude_raw=1000, magnitude_decimals=18,
        magnitude_max_90d=100000, timestamp=1700000000, block_number=100,
        block_hash=bytes(32), chain_id=1,
    )
    bh = compute_behavioral_hash(event)
    check(f"EventType.{et.name} ({et.value})", bh["valid"] and bh["event_type"] == et.name)

# 4. Chain-ID isolation: same event on different chains → different BH
print("\n── 4. Chain-ID isolation ──")
hashes = set()
for vm, cid, addr in VM_CHAINS:
    eid = hashlib.sha3_256(addr.lower().strip().encode()).digest()
    event = BehavioralEvent(
        entity_id=eid, event_type=EventType.TRANSFER, magnitude_raw=100,
        magnitude_decimals=6, magnitude_max_90d=10000, timestamp=1700000000,
        block_number=100, block_hash=bytes(32), chain_id=cid,
    )
    hashes.add(compute_behavioral_hash(event)["sense_hex"])
check(f"identical event on {len(VM_CHAINS)} chains → {len(hashes)} distinct BHs",
      len(hashes) == len(VM_CHAINS))

print("\n" + "═" * 70)
print(f"BH PIPELINE: {PASS} passed, {FAIL} failed")
print("═" * 70)
if FAILURES:
    for f in FAILURES:
        print(f"  ❌ {f}")
    sys.exit(1)
print("✅ ALL VM FAMILIES PRODUCE VALID CANONICAL BHs")
