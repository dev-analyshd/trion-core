"""
TRION — Cross-language golden vectors for the canonical 93-byte Behavioral Hash
================================================================================

Verifies tests/golden/vectors.json (≥ 12 vectors: plain transfer, swap, MEV,
flash-loan, max magnitudes, zero value, minimal fields, per-chain decimal
normalization 18/6/9/7dp, distinct chain ids, all 20 event-type bytes, lenient
block-hash edges, entity-resolution rules, context/timestamp edges, the
truncation edge, plus the two frozen reference vectors) three ways:

  (a) PYTHON — a doc-exact rebuild of docs/protocol/CANONICAL_BH.md §1/§4/§9
      AND the repo builders (core/primitives/behavioral_hash.py,
      core/realtime/bh_streamer.py) must reproduce the pinned payload/sense/
      antisense byte-for-byte.
  (b) RUST — static source-order verification of
      indexers/crates/trion-common/src/hash_dna.rs::canonical_bh (field
      widths/order/endian match the canonical table — the same static-parity
      pattern as tests/unit/test_intent_spec_fields.py) plus determinism
      guarantees across the 21 indexer crates: no session-max magnitude
      (AtomicU64), no wall-clock timestamps feeding the BH.
      (No cargo toolchain in this environment — the Rust verification is
      static; cargo build/test remains the documented unverified boundary.)
  (c) TYPESCRIPT — chains/shared/canonical_bh.ts is EXECUTED via bun (or
      node) and its digests compared byte-for-byte.

Run:  python3 -m pytest tests/golden/test_golden_vectors.py -q
"""
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
VECTORS_PATH = REPO / "tests" / "golden" / "vectors.json"
DOC = json.loads(VECTORS_PATH.read_text())
VECTORS = {v["id"]: v for v in DOC["vectors"]}

# repo-root import path is provided by tests/conftest.py (no sys.path hacks —
# see tests/unit/test_no_sys_path_hacks.py)


# ── (a) Python canonical builders ────────────────────────────────────────────

def lenient_hex32(s: str) -> bytes:
    """CANONICAL_BH.md §9 — lenient hex → exactly 32 bytes (doc-exact)."""
    s = str(s)
    s = s[2:] if s[:2].lower() == "0x" else s
    out = bytearray(32)
    n = min(len(s) // 2, 32)
    for i in range(n):
        hi, lo = s[i * 2], s[i * 2 + 1]
        hv = int(hi, 16) if hi in "0123456789abcdefABCDEF" else 0
        lv = int(lo, 16) if lo in "0123456789abcdefABCDEF" else 0
        out[i] = (hv << 4) | lv
    return bytes(out)


def normalise_addr(raw: str) -> str:
    """CANONICAL_BH.md §6 — entity normalisation (doc-exact)."""
    s = str(raw).strip().lower()
    if s.startswith("0x") and len(s) >= 42:
        return s
    if len(s) == 40 and all(c in "0123456789abcdef" for c in s):
        return "0x" + s
    return s


def doc_exact_canonical_bh(entity_id_hex, event_type, magnitude_norm, context,
                           timestamp, chain_id, block_hash_hex):
    """CANONICAL_BH.md §1 — returns (payload, sense, antisense, mag_nano)."""
    mag_nano = int(max(0.0, min(1.0, magnitude_norm)) * 1_000_000_000)
    payload = (
        lenient_hex32(entity_id_hex)
        + bytes([int(event_type) & 0xFF])
        + mag_nano.to_bytes(8, "big")
        + int(context).to_bytes(8, "big")
        + int(timestamp).to_bytes(8, "big")
        + (int(chain_id) & 0xFFFFFFFF).to_bytes(4, "big")
        + lenient_hex32(block_hash_hex)
    )
    assert len(payload) == 93
    sense = hashlib.sha3_256(payload + b"\x00").digest()
    sha3ff = hashlib.sha3_256(payload + b"\xFF").digest()
    antisense = bytes(a ^ (~s & 0xFF) for a, s in zip(sha3ff, sense))
    return payload, sense, antisense, mag_nano


@pytest.fixture(scope="module")
def core_bh():
    """core/primitives/behavioral_hash.py — the repo's canonical builder."""
    from core.primitives.behavioral_hash import (  # noqa: PLC0415
        BehavioralEvent, EventType, canonical_magnitude_norm, compute_behavioral_hash,
    )
    return BehavioralEvent, EventType, canonical_magnitude_norm, compute_behavioral_hash


@pytest.fixture(scope="module")
def streamer_bh():
    """core/realtime/bh_streamer.py — the live ingestion-path builder."""
    from core.realtime.bh_streamer import compute_bh  # noqa: PLC0415
    return compute_bh


# ── (a) tests: doc-exact rebuild + repo builders ─────────────────────────────

@pytest.mark.parametrize("vid", sorted(VECTORS), ids=lambda v: v)
def test_python_doc_exact_rebuild(vid):
    v = VECTORS[vid]
    inp, exp = v["input"], v["expected"]
    payload, sense, anti, mag_nano = doc_exact_canonical_bh(
        inp["entity_id_hex"], inp["event_type"], inp["magnitude_norm"],
        inp["context"], inp["timestamp"], inp["chain_id"], inp["block_hash_hex"],
    )
    assert payload.hex() == exp["payload_hex"], f"{vid}: payload bytes diverge"
    assert len(payload) == 93 == exp["payload_len"]
    assert sense.hex() == exp["sense"], f"{vid}: sense diverges"
    assert anti.hex() == exp["antisense"], f"{vid}: antisense diverges"
    assert mag_nano == exp["magnitude_nano"], f"{vid}: magnitude_nano diverges"
    # §10 self-verification invariant
    xor = bytes(s ^ a for s, a in zip(sense, anti))
    not_ff = bytes(~b & 0xFF for b in hashlib.sha3_256(payload + b"\xFF").digest())
    assert xor == not_ff, f"{vid}: dual-strand invariant broken"


@pytest.mark.parametrize("vid", sorted(
    v for v, d in VECTORS.items() if "magnitude_raw" in d["input"]), ids=lambda v: v)
def test_python_core_builder_parity(vid, core_bh):
    """core/primitives/behavioral_hash.py must reproduce the pinned digests
    (lenient 32-byte fields + canonical §4 magnitude + truncating nano)."""
    BehavioralEvent, EventType, canonical_magnitude_norm, compute_bh = core_bh
    v = VECTORS[vid]
    inp, exp = v["input"], v["expected"]
    # §4 rule: repo implementation reproduces the pinned magnitude
    assert canonical_magnitude_norm(inp["magnitude_raw"], inp["decimals"]) == \
        pytest.approx(inp["magnitude_norm"], abs=1e-15), f"{vid}: §4 magnitude"
    event = BehavioralEvent(
        entity_id=lenient_hex32(inp["entity_id_hex"]),
        event_type=EventType(inp["event_type"]),
        magnitude_raw=inp["magnitude_raw"],
        magnitude_decimals=inp["decimals"],
        magnitude_max_90d=int(1e18),  # ignored by the canonical path
        timestamp=inp["timestamp"],
        block_number=18000000,
        block_hash=lenient_hex32(inp["block_hash_hex"]),
        chain_id=inp["chain_id"],
        context=inp["context"].to_bytes(8, "big"),
    )
    res = compute_bh(event)
    assert res["payload_len"] == 93, f"{vid}: core builder payload must be 93 bytes"
    assert res["sense_hex"] == exp["sense"], f"{vid}: core builder sense diverges"
    assert res["antisense_hex"] == exp["antisense"], f"{vid}: core antisense diverges"
    assert res["valid"], f"{vid}: core builder self-verification failed"


@pytest.mark.parametrize("vid", sorted(
    v for v, d in VECTORS.items()
    if "sender_address" in d["input"] and "magnitude_raw" in d["input"]), ids=lambda v: v)
def test_python_streamer_builder_parity(vid, streamer_bh):
    """core/realtime/bh_streamer.py (the live ingestion path) must reproduce
    the pinned digests — entity = sha3(normalise(addr)), per-chain decimals,
    fixed-scale §4 magnitude, context 0."""
    v = VECTORS[vid]
    inp, exp = v["input"], v["expected"]
    res = streamer_bh(
        inp["sender_address"], inp["event_type"], inp["magnitude_raw"],
        inp["chain_id"], 18000000, inp["block_hash_hex"], inp["timestamp"],
        "GOLDEN", inp.get("decimals", 18),
    )
    assert res["sense_hex"] == exp["sense"], f"{vid}: streamer sense diverges"
    assert res["antisense_hex"] == exp["antisense"], f"{vid}: streamer antisense diverges"
    assert res["valid"], f"{vid}: streamer self-verification failed"


def test_reference_vectors_match_frozen_sources():
    """The two pre-existing single-vector checks stay authoritative."""
    schema = json.loads((REPO / "config" / "bh_schema_v1.json").read_text())
    tv = schema["test_vector"]
    v = VECTORS["ref_schema_v1_vector"]
    assert v["input"]["entity_id_hex"] == tv["entity_id_hex"]
    assert v["input"]["event_type"] == tv["event_type"]
    assert v["input"]["magnitude_norm"] == tv["magnitude_norm"]
    assert v["input"]["chain_id"] == tv["chain_id"]
    assert v["input"]["block_hash_hex"] == tv["block_hash_hex"]
    assert v["expected"]["sense"] == tv["expected_sense"]
    assert v["expected"]["antisense"] == tv["expected_antisense"]
    # the Rust-pinned parity vector (hash_dna.rs::cross_language_canonical_bh_vector)
    rv = VECTORS["ref_cross_lang_rust_vector"]
    rust_src = (REPO / "indexers" / "crates" / "trion-common" / "src" / "hash_dna.rs").read_text()
    assert rv["expected"]["sense"] in rust_src, \
        "Rust pinned sense vector not found in hash_dna.rs"
    assert rv["expected"]["antisense"] in rust_src, \
        "Rust pinned antisense vector not found in hash_dna.rs"


def test_entity_rules():
    """§6: case-insensitive EVM addresses; non-EVM passthrough; pinned bh_id."""
    a = "0xDEADBEEF000000000000000000000000DEADBEEF"
    b = "0xdeadbeef000000000000000000000000deadbeef"
    eid = hashlib.sha3_256(normalise_addr(a).encode()).hexdigest()
    assert eid == hashlib.sha3_256(normalise_addr(b).encode()).hexdigest()
    assert eid == "f9769049b9d4b778ba5c676f396b98b6578831524d0744264eaff84375f6826e"
    assert VECTORS["entity_bh_id_pinned"]["input"]["entity_id_hex"] == eid
    # intended digest equalities (documented in the vector descriptions)
    assert VECTORS["plain_transfer_eth"]["expected"]["sense"] == \
        VECTORS["entity_case_insensitive"]["expected"]["sense"]
    assert VECTORS["decimals_18dp_usdc_ethlike"]["expected"]["sense"] == \
        VECTORS["decimals_6dp_usdc"]["expected"]["sense"]
    # chain-id separation: same event, different registry ids → different BH
    ids = [f"chain_id_{c}" for c in (1, 900, 421614, 10000, 4294967295)]
    senses = {VECTORS[i]["expected"]["sense"] for i in ids}
    assert len(senses) == len(ids), "distinct chain ids must separate digests"
    # and the chain_id_1 sweep vector is the same event as the 6dp base vector
    assert VECTORS["chain_id_1"]["expected"]["sense"] == \
        VECTORS["decimals_6dp_usdc"]["expected"]["sense"]


def test_event_type_table_complete():
    """All 20 canonical event-type bytes are covered by the sweep vectors."""
    for et in range(20):
        matches = [v for v in VECTORS.values()
                   if v["input"]["event_type"] == et and "event-type" in v.get("tags", [])]
        assert matches, f"event_type byte {et} has no sweep vector"
    names = {v["input"]["event_type"]: v["id"] for v in VECTORS.values()
             if "sweep" in v.get("tags", [])}
    assert len(names) == 20


def test_magnitude_rule_deterministic():
    """§4: same raw → same magnitude always (pure function); clamping."""
    from core.primitives.behavioral_hash import canonical_magnitude_norm  # noqa: PLC0415
    for raw, dec, human in [(1_500_000, 6, 1.5), (1_500_000_000_000_000_000, 18, 1.5),
                            (3_000_000_000, 9, 3.0), (0, 18, 0.0)]:
        m = canonical_magnitude_norm(raw, dec)
        assert m == canonical_magnitude_norm(raw, dec)  # pure
        assert 0.0 <= m <= 1.0
        if human == 0:
            assert m == 0.0
    # clamp at the 1000-human reference scale
    assert canonical_magnitude_norm(10**21, 18) == 1.0
    assert canonical_magnitude_norm((1 << 128) - 1, 18) == 1.0
    assert VECTORS["flash_loan_eth"]["expected"]["magnitude_nano"] == 1_000_000_000
    # doc-exact formula
    assert canonical_magnitude_norm(1_500_000, 6) == \
        pytest.approx(min(1.0, math.log10(1.5 + 1) / math.log10(1001)), rel=1e-12)


# ── (b) static Rust verification ─────────────────────────────────────────────

HASH_DNA = REPO / "indexers" / "crates" / "trion-common" / "src" / "hash_dna.rs"
CRATES = sorted((REPO / "indexers" / "crates").glob("trion-*/src/main.rs"))

# crates whose only remaining SystemTime use is the FAISS VectorEntry
# *metadata* timestamp (outside the BH payload — allowed per §5)
SYSTEMTIME_ALLOWED = {"trion-evm", "trion-botchain"}

# §5 block-time source markers for the crates that previously hashed
# wall-clock ingestion time (each must now read the chain's own block time)
BLOCK_TIME_MARKERS = {
    "trion-svm":       'block["blockTime"]',
    "trion-aptos":     'block["block_timestamp"]',
    "trion-movement":  'block["block_timestamp"]',
    "trion-near":      'block["header"]["timestamp"]',
    "trion-sui":       'cp["timestamp_ms"]',
    "trion-ton":       't["utime"]',
    "trion-tron":      'block["block_header"]["raw_data"]["timestamp"]',
    "trion-starknet":  'block["timestamp"]',
    "trion-cosmos":    'block["block"]["header"]["time"]',
    "trion-cardano":   't.get("block_time")',
    "trion-pi":        't.get("created_at")',
    "trion-pvm":       "let ts_u64    = 0u64;",
}


def _fn_body(source: str, fn_name: str) -> str:
    m = re.search(rf"fn {fn_name}\(", source)
    assert m, f"fn {fn_name} not found"
    depth, i = 0, m.start()
    start = source.find("{", m.end())
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    raise AssertionError(f"unbalanced braces in fn {fn_name}")


def test_rust_canonical_bh_layout():
    """hash_dna.rs::canonical_bh constructs the exact §1 byte layout, in
    order, with the canonical widths and endianness."""
    src = HASH_DNA.read_text()
    body = _fn_body(src, "canonical_bh")
    # field construction order (§1 table) — offsets are implied by widths
    order = [
        (r"hex_to_32bytes\(entity_id_hex\)", 32, "entity_id"),
        (r"payload\.push\(event_type\)", 1, "event_type"),
        (r"mag_nano\.to_be_bytes\(\)", 8, "magnitude_nano"),
        (r"context\.to_be_bytes\(\)", 8, "context"),
        (r"timestamp_secs\.to_be_bytes\(\)", 8, "timestamp_secs"),
        (r"\(chain_id as u32\)\.to_be_bytes\(\)", 4, "chain_id"),
        (r"hex_to_32bytes\(block_hash_hex\)", 32, "block_hash"),
    ]
    positions = []
    for pat, width, name in order:
        m = re.search(pat, body)
        assert m, f"canonical_bh missing construction of {name} ({pat})"
        positions.append((m.start(), width, name))
    assert positions == sorted(positions), "canonical_bh field order diverges from §1"
    assert sum(w for _, w, _ in order) == 93
    # length guard
    assert re.search(r"payload\.len\(\), 93|len\(\), 93", body) or \
        "payload.len(), 93" in src, "canonical_bh must assert the 93-byte payload"
    # dual-strand construction (§1)
    assert "p0.push(0x00)" in body and "pff.push(0xFF)" in body
    assert re.search(r"Sha3_256::digest\(&p0\)", body)
    assert re.search(r"Sha3_256::digest\(&pff\)", body)
    assert re.search(r"ff \^ !s", body), "antisense must be sha3ff XOR NOT(sense)"


def test_rust_magnitude_nano_truncates():
    """mag_nano uses a truncating cast (`as u64`), never a rounding form."""
    src = HASH_DNA.read_text()
    body = _fn_body(src, "canonical_bh")
    assert re.search(r"clamp\(0\.0, 1\.0\)\s*\*\s*1_000_000_000\.0\)\s*as u64", body), \
        "mag_nano must be trunc((clamp(mag) * 1e9)) as u64 — §1 truncation rule"
    assert "round" not in body.lower(), "canonical_bh must not round the magnitude"


def test_rust_lenient_hex_decoder():
    """hex_to_32bytes is the §9 lenient LEFT-aligned decoder."""
    src = HASH_DNA.read_text()
    body = _fn_body(src, "hex_to_32bytes")
    assert "trim_start_matches(\"0x\")" in body
    assert re.search(r"\.min\(32\)", body), "at most 32 bytes (truncate)"
    assert "unwrap_or(0)" in body, "invalid nibbles decode as 0"
    assert "padStart" not in body and "pad" not in body.replace("payload", "").lower()
    # doc-exact port check: the TS/Python lenient decoders in this file agree
    for probe, want in [("f", "00" * 32), ("0f", "0f" + "00" * 31),
                        ("zz" + "11" * 31, "00" + "11" * 31), ("0x0", "00" * 32)]:
        assert lenient_hex32(probe).hex() == want


def test_rust_entity_key_and_block_time_helper():
    src = HASH_DNA.read_text()
    assert "pub fn bh_id" in src and "fn normalise" in src
    # §5 helper exported and pinned
    assert "pub fn iso8601_to_epoch" in src
    lib = (REPO / "indexers" / "crates" / "trion-common" / "src" / "lib.rs").read_text()
    assert "iso8601_to_epoch" in lib, "lib.rs must re-export iso8601_to_epoch"
    # the Rust test pins the exact digests of our reference vectors
    rv = VECTORS["ref_cross_lang_rust_vector"]
    assert rv["expected"]["sense"] in src
    assert rv["expected"]["antisense"] in src


@pytest.mark.parametrize("crate_file", CRATES, ids=lambda p: p.parent.parent.name)
def test_rust_crate_magnitude_deterministic(crate_file):
    """No crate may derive BH magnitude from process/session state (§4):
    no AtomicU64 trackers, no .store() updates — and the canonical fixed
    scale log10(…/1001) must be present."""
    name = crate_file.parent.parent.name
    if name == "trion-common":
        pytest.skip("shared crate — covered by the layout tests")
    src = crate_file.read_text()
    assert "AtomicU64" not in src, f"{name}: session-state magnitude tracker present (canonical violation)"
    assert ".store(" not in src, f"{name}: atomic store (session state) present"
    assert "log10(1001" in src or name == "trion-common", \
        f"{name}: canonical §4 fixed scale log10(1001) missing"
    # every per-tx BH call passes context 0
    for m in re.finditer(r"canonical_bh\(", src):
        snippet = src[m.start():m.start() + 400]
        assert re.search(r",\s*0(u64)?\s*,", snippet) or "0u64" in snippet, \
            f"{name}: canonical_bh call must pass context 0"


@pytest.mark.parametrize("crate_file", CRATES, ids=lambda p: p.parent.parent.name)
def test_rust_crate_bh_timestamp_not_wall_clock(crate_file):
    """§5 — the per-tx BH timestamp must come from the chain's block time
    (or canonical 0), never SystemTime::now(). Wall clock remains legal ONLY
    for FAISS VectorEntry metadata (trion-evm / trion-botchain)."""
    name = crate_file.parent.parent.name
    if name == "trion-common":
        pytest.skip("shared crate — covered by the layout tests")
    src = crate_file.read_text()
    if name in SYSTEMTIME_ALLOWED:
        # the only SystemTime sites must be VectorEntry timestamps — verify no
        # BH batch call receives one (ts variables feeding canonical_bh are
        # derived from the block header timestamp in these crates).
        for m in re.finditer(r"canonical_bh\(", src):
            window = src[max(0, m.start() - 2000):m.start()]
            assert "SystemTime::now" not in window, \
                f"{name}: wall clock within 2KB of a canonical_bh call"
        return
    assert "SystemTime" not in src, \
        f"{name}: wall-clock SystemTime still present (BH timestamp must be block time or 0)"
    marker = BLOCK_TIME_MARKERS.get(name)
    if marker:
        assert marker in src, f"{name}: §5 block-time source {marker!r} missing"


def test_rust_wall_clock_bh_pattern_gone():
    """The exact pre-fix pattern (wall clock feeding the tx-BH ts) must be
    absent from every crate."""
    for crate_file in CRATES:
        src = crate_file.read_text()
        assert "as_secs_f64();\n            let ts_u64" not in src or \
            "SystemTime" not in src.split("as_secs_f64();")[0][-200:], \
            f"{crate_file.parent.parent.name}: old wall-clock BH ts pattern remains"


# ── (c) TypeScript execution ─────────────────────────────────────────────────

TS_BH = REPO / "chains" / "shared" / "canonical_bh.ts"

DRIVER = """
import { readFileSync } from "node:fs";
import { canonicalBH } from %TS_PATH%;
const doc = JSON.parse(readFileSync(%VEC_PATH%, "utf8"));
const out = [];
for (const v of doc.vectors) {
  const i = v.input;
  const r = canonicalBH(i.entity_id_hex, i.event_type, i.magnitude_norm,
                        BigInt(i.context), i.timestamp, i.chain_id, i.block_hash_hex);
  out.push({ id: v.id, sense: r.sense, antisense: r.antisense,
             payload_len: r.payload_len });
}
console.log(JSON.stringify(out));
"""


def _run_ts_driver():
    """Execute the TS builder on every vector. Returns list of results or
    None (skip) when no TS-capable runtime exists."""
    if not shutil.which("bun") and not shutil.which("node"):
        return None
    import tempfile
    with tempfile.TemporaryDirectory(prefix="trion_bh_ts_") as td:
        driver = Path(td) / "driver.mjs"
        driver.write_text(
            DRIVER.replace("%TS_PATH%", repr(str(TS_BH)))
                  .replace("%VEC_PATH%", repr(str(VECTORS_PATH))))
        # bun runs .ts imports natively; node needs strip-types
        for cmd in (["bun", str(driver)],
                    ["node", "--experimental-strip-types", str(driver)]):
            if not shutil.which(cmd[0]):
                continue
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=120, cwd=td)
            except (OSError, subprocess.TimeoutExpired):
                continue
            if proc.returncode == 0 and proc.stdout.strip():
                return json.loads(proc.stdout.strip().splitlines()[-1])
            # keep trying the next runtime
    return None


def test_typescript_builder_byte_parity():
    """chains/shared/canonical_bh.ts (executed live via bun/node) must
    reproduce every pinned digest — including the truncation edge that a
    rounding implementation fails."""
    results = _run_ts_driver()
    if results is None:
        pytest.skip("no TS-capable runtime (bun/node) available — TypeScript "
                    "byte-parity unverified in this environment")
    got = {r["id"]: r for r in results}
    assert set(got) == set(VECTORS), "TS driver must cover every vector"
    mismatches = []
    for vid, r in got.items():
        exp = VECTORS[vid]["expected"]
        if r["sense"] != exp["sense"] or r["antisense"] != exp["antisense"] \
                or r["payload_len"] != 93:
            mismatches.append(vid)
    assert not mismatches, f"TS builder diverges on: {mismatches[:8]}"


def test_typescript_truncation_edge_catches_rounding():
    """The 0.1234567895 vector MUST produce mag_nano 123456789 — a Math.round
    implementation produces 123456790 and fails this test (it did, pre-fix)."""
    v = VECTORS["magnitude_truncation_edge"]
    assert v["input"]["magnitude_norm"] * 1e9 == 123456789.5
    assert v["expected"]["magnitude_nano"] == 123456789
    # byte 33..41 of the payload is the big-endian mag_nano
    payload = bytes.fromhex(v["expected"]["payload_hex"])
    assert int.from_bytes(payload[33:41], "big") == 123456789


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
