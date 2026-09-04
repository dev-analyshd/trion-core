"""
test_pvm_oracle.py — C-05 PVM leg closure test (static audit + py mirror).

contracts/pvm/legacy_oracle.rs is an owner-write route store with no
signatures/quorum/epoch (audit C-05, MEDIUM — no funded escrow consumer).
The Wave 2 remediation for the PVM leg is HONEST LABELING, not a rewrite:

  1. STATIC HONESTY LABELS — the source (and its byte-identical relayer-side
     copy chains/pvm/contract/lib.rs) must carry: the RESEARCH/NON-PRODUCTION
     header, the PRODUCTION_STATUS const, the is_oracle_of_record() ->
     false honesty-flag message, the C-05 warning on publish_btcp_route,
     and the canonical-uprade-path documentation (what ink! can/can't do
     for the CANONICAL_CERTIFICATE families).
  2. NO CONSENSUS MACHINERY — code lines (comments stripped) contain no
     signature verification, no quorum computation, no validator epoch:
     the contract cannot be mistaken (or abused) as an oracle of record,
     and its stored route struct carries no consensus-claim field.
  3. PY MIRROR of the authorization + data semantics:
       - non-owner / non-validator cannot write (Unauthorized)
       - owner CAN write (that is exactly the documented weakness)
       - owner-added validators CAN write (max 20, owner-only management)
       - score bounds (> 1e6 rejected), missing route, inactive route
       - verify_execution() merely restates coherence >= threshold for the
         row the caller wrote — it is a DATA READ, not consensus evidence
  4. ATTACK: "owner forges a validator consensus claim" — there is NO API
     path (method or storage field) that mints a consensus/quorum/epoch
     claim; the mirror's full message set is enumerated and pinned.
  5. DOC PIN — CANONICAL_INVARIANTS.md registers the PVM tier as a
     research/partial (non-production) tier.

No cargo toolchain exists in this environment (external-toolchain policy):
the Rust crate is verified statically + via this mirror; `cargo test` on
contracts/pvm is the documented unverified boundary.

Run: python3 tests/contracts/test_pvm_oracle.py
"""

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ORACLE_RS = os.path.join(REPO, "contracts/pvm/legacy_oracle.rs")
ORACLE_RS_RELAYER_COPY = os.path.join(REPO, "chains/pvm/contract/lib.rs")
INVARIANTS_MD = os.path.join(REPO, "docs/security/CANONICAL_INVARIANTS.md")

PASSED = []
FAILED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"  {'OK' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))


# ── source helpers ───────────────────────────────────────────────────────────

def strip_rust_comments(src: str) -> str:
    """Remove // and //! and /// line comments; keep code (doc comments are
    where the honesty labels live, code is where machinery would live)."""
    out = []
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("//"):
            continue
        out.append(line)
    return "\n".join(out)


# ── py mirror of the ink! contract semantics ────────────────────────────────

class Error(Exception):
    pass


class PVMOracleMirror:
    """Python mirror of contracts/pvm/legacy_oracle.rs (TRIONPVMOracle).

    Mirrors the exact message surface, authorization model and stored
    BtcpRoute fields of the ink! contract so the static source audit can be
    cross-checked against executed semantics.
    """

    MESSAGES = {
        "new", "publish_btcp_route", "verify_execution", "get_route",
        "add_validator", "remove_validator", "owner", "route_count",
        "version", "is_validator", "is_oracle_of_record",
    }
    ROUTE_FIELDS = {
        "route_id", "anchor_bh", "execution_bh", "coherence_score",
        "threshold_score", "published_at", "publisher", "is_active",
    }
    MAX_VALIDATORS = 20

    def __init__(self, owner):
        self.owner = owner
        self.validators = []
        self.routes = {}
        self.route_count = 0
        self.version = 3
        self.production_status = "RESEARCH_NON_PRODUCTION"

    def publish_btcp_route(self, caller, route_id, anchor_bh, execution_bh,
                           coherence_score, threshold_score, now=1_000):
        if coherence_score > 1_000_000 or threshold_score > 1_000_000:
            raise Error("InvalidScore")
        if caller != self.owner and caller not in self.validators:
            raise Error("Unauthorized")
        route = {
            "route_id": route_id, "anchor_bh": anchor_bh,
            "execution_bh": execution_bh,
            "coherence_score": coherence_score,
            "threshold_score": threshold_score,
            "published_at": now, "publisher": caller, "is_active": True,
        }
        assert set(route) == self.ROUTE_FIELDS  # mirror pins the field set
        self.routes[route_id] = route
        self.route_count += 1
        return None

    def verify_execution(self, route_id):
        route = self.routes.get(route_id)
        if route is None:
            raise Error("RouteNotFound")
        if not route["is_active"]:
            raise Error("RouteInactive")
        is_safe = route["coherence_score"] >= route["threshold_score"]
        return (is_safe, route["coherence_score"], route["threshold_score"])

    def get_route(self, route_id):
        return self.routes.get(route_id)

    def add_validator(self, caller, validator):
        if caller != self.owner:
            raise Error("Unauthorized")
        if len(self.validators) >= self.MAX_VALIDATORS:
            raise Error("TooManyValidators")
        if validator not in self.validators:
            self.validators.append(validator)
        return None

    def remove_validator(self, caller, validator):
        if caller != self.owner:
            raise Error("Unauthorized")
        self.validators = [v for v in self.validators if v != validator]
        return None

    def is_validator(self, account):
        return account in self.validators

    def is_oracle_of_record(self):
        # HONESTY FLAG — always False in the research stub.
        return False


# ── test sections ────────────────────────────────────────────────────────────

def test_static_honesty_labels():
    print("\n1) static honesty labels (source + relayer-side copy)")
    src = open(ORACLE_RS).read()
    for label, needle in [
        ("RESEARCH/NON-PRODUCTION header", "RESEARCH / NON-PRODUCTION — NOT AN ORACLE OF RECORD"),
        ("C-05 finding named", "audit finding C-05, PVM leg"),
        ("PRODUCTION_STATUS const", 'PRODUCTION_STATUS: &str = "RESEARCH_NON_PRODUCTION"'),
        ("is_oracle_of_record() honesty flag message", "pub fn is_oracle_of_record(&self) -> bool { false }"),
        ("C-05 warning on publish_btcp_route", "C-05 (RESEARCH STUB): this is an OWNER-VALIDATOR data write"),
        ("no funded consumer disclosed", "No funded escrow consumer exists in this repo"),
        ("canonical upgrade path documented (signatures)", "ink_env::crypto::verify_signature"),
        ("canonical upgrade path documented (hashing limits)", "SHA3-256, which ink! does NOT provide natively"),
        ("canonical upgrade path documented (epoch registry)", "ink::storage::Mapping` supports the per-epoch"),
    ]:
        check(f"label present: {label}", needle in src)

    # the misrepresentation is GONE: the old header claimed to be "the
    # Polkadot equivalent of TRIONOracleV3.sol" as fact, not warning
    check("old 'Polkadot equivalent of TRIONOracleV3.sol' claim removed",
          "Polkadot equivalent of TRIONOracleV3.sol.\n" not in src)

    # relayer-side copy stays byte-identical (same artifact, no drift)
    try:
        mirror = open(ORACLE_RS_RELAYER_COPY).read()
        check("chains/pvm/contract/lib.rs is byte-identical to contracts/pvm/legacy_oracle.rs",
              mirror == src)
    except FileNotFoundError:
        check("chains/pvm/contract/lib.rs is byte-identical to contracts/pvm/legacy_oracle.rs",
              False, "relayer-side copy missing")


def test_no_consensus_machinery():
    print("\n2) no consensus machinery in code (comments stripped)")
    src = open(ORACLE_RS).read()
    code = strip_rust_comments(src)
    forbidden = [
        (r"verify_signature", "signature verification"),
        (r"\becdsa\b(?!_)", "ecdsa verification"),
        (r"\bed25519\b", "ed25519 verification"),
        (r"\bsr25519\b", "sr25519 verification"),
        (r"quorum", "quorum computation"),
        (r"\bepoch\b", "validator epoch"),
        (r"minRouteAttestations", "dynamic quorum view"),
        (r"total_effective_power", "canonical power field"),
        (r"certificate_hash", "canonical certificate hash"),
    ]
    for pattern, what in forbidden:
        hits = re.findall(pattern, code, flags=re.IGNORECASE)
        check(f"no {what} in code", not hits, f"found: {hits[:3]}")

    # the storage struct has exactly the legacy 5 fields — no epoch/weights
    m = re.search(r"pub struct TRIONPVMOracle \{(.*?)\}", code, flags=re.DOTALL)
    check("TRIONPVMOracle storage struct found", m is not None)
    if m:
        fields = re.findall(r"^\s*(\w+)\s*:", m.group(1), flags=re.MULTILINE)
        check("storage fields are exactly the legacy set (owner/validators/routes/route_count/version)",
              set(fields) == {"owner", "validators", "routes", "route_count", "version"},
              str(fields))

    # the stored BtcpRoute has no consensus-claim field
    m2 = re.search(r"pub struct BtcpRoute \{(.*?)\}", code, flags=re.DOTALL)
    check("BtcpRoute struct found", m2 is not None)
    if m2:
        fields2 = re.findall(r"pub (\w+)\s*:", m2.group(1))
        check("BtcpRoute fields carry no consensus/quorum/epoch claim",
              set(fields2) == {"route_id", "anchor_bh", "execution_bh",
                               "coherence_score", "threshold_score",
                               "published_at", "publisher", "is_active"},
              str(fields2))


def test_authorization_mirror():
    print("\n3) py mirror — authorization + data semantics")
    OWNER, ATTACKER, V1, V2 = "owner-key", "attacker-key", "validator-1", "validator-2"
    o = PVMOracleMirror(OWNER)
    rid, anchor, execbh = b"\x01" * 32, b"\x02" * 32, b"\x03" * 32

    # ATTACK: non-owner/non-validator cannot write
    try:
        o.publish_btcp_route(ATTACKER, rid, anchor, execbh, 800_000, 700_000)
        check("non-owner cannot publish (Unauthorized)", False, "write succeeded")
    except Error as e:
        check("non-owner cannot publish (Unauthorized)", str(e) == "Unauthorized")

    # owner CAN write — this is the documented C-05 weakness, disclosed
    o.publish_btcp_route(OWNER, rid, anchor, execbh, 800_000, 700_000)
    check("owner CAN publish (the documented owner-write weakness)",
          o.route_count == 1 and o.routes[rid]["publisher"] == OWNER)

    # owner-added validators can write; management is owner-only, max 20
    try:
        o.add_validator(ATTACKER, V1)
        check("add_validator is owner-only", False, "attacker added a validator")
    except Error as e:
        check("add_validator is owner-only", str(e) == "Unauthorized")
    o.add_validator(OWNER, V1)
    check("owner adds validator", o.is_validator(V1))
    o.publish_btcp_route(V1, b"\x11" * 32, anchor, execbh, 900_000, 700_000)
    check("registered validator can publish", o.route_count == 2)
    for i in range(25):
        try:
            o.add_validator(OWNER, f"v-{i}")
        except Error:
            break
    check("validator cap at 20 enforced",
          len(o.validators) == PVMOracleMirror.MAX_VALIDATORS)

    # score bounds / missing route / inactive route
    try:
        o.publish_btcp_route(OWNER, b"\x21" * 32, anchor, execbh, 1_100_000, 700_000)
        check("score > 1e6 rejected", False)
    except Error as e:
        check("score > 1e6 rejected", str(e) == "InvalidScore")
    try:
        o.verify_execution(b"\x99" * 32)
        check("missing route rejected", False)
    except Error as e:
        check("missing route rejected", str(e) == "RouteNotFound")
    inactive = b"\x31" * 32
    o.publish_btcp_route(OWNER, inactive, anchor, execbh, 800_000, 700_000)
    o.routes[inactive]["is_active"] = False
    try:
        o.verify_execution(inactive)
        check("inactive route rejected", False)
    except Error as e:
        check("inactive route rejected", str(e) == "RouteInactive")

    # verify_execution is a data restatement, not a consensus verdict
    safe, coh, thr = o.verify_execution(rid)
    check("verify_execution restates coherence >= threshold (data read)",
          safe is True and coh == 800_000 and thr == 700_000)
    o.publish_btcp_route(OWNER, b"\x41" * 32, anchor, execbh, 600_000, 700_000)
    unsafe, _, _ = o.verify_execution(b"\x41" * 32)
    check("verify_execution is False when coherence < threshold",
          unsafe is False)


def test_consensus_forgery_impossible():
    print("\n4) ATTACK — owner cannot forge a validator-consensus claim")
    o = PVMOracleMirror("owner-key")

    # There is NO method and NO stored field anywhere in the mirror's
    # surface that mints a consensus/quorum/epoch claim: the only write is
    # publish_btcp_route (a data row), and the row schema is pinned.
    consensus_words = ("consensus", "quorum", "attest", "epoch", "signature",
                       "verified", "finalized")
    method_names = {m for m in dir(o) if not m.startswith("_") and callable(getattr(o, m))}
    # ink! messages map onto py: new→__init__ (constructor, not a method),
    # owner/route_count/version→attribute reads; the rest are callables.
    MIRROR_METHODS = {
        "publish_btcp_route", "verify_execution", "get_route",
        "add_validator", "remove_validator", "is_validator",
        "is_oracle_of_record",
    }
    attribute_accessors = {"owner", "route_count", "version"}
    check("mirror message set pinned (no consensus-minting method added)",
          method_names == MIRROR_METHODS
          and all(hasattr(o, a) for a in attribute_accessors), str(method_names))
    surface = method_names | attribute_accessors | {"new"}
    check("mirror surface is exactly the ink! message set",
          surface == PVMOracleMirror.MESSAGES, str(surface ^ PVMOracleMirror.MESSAGES))
    minter = [m for m in surface if any(w in m.lower() for w in consensus_words)]
    check("no method name hints at consensus authority", not minter, str(minter))

    # The honesty flag stays false no matter what the owner writes.
    o.publish_btcp_route("owner-key", b"\x01" * 32, b"\x02" * 32, b"\x03" * 32,
                         1_000_000, 0)  # "perfect" verdict row
    check("is_oracle_of_record() stays false after an owner write",
          o.is_oracle_of_record() is False)
    check("PRODUCTION_STATUS stays RESEARCH_NON_PRODUCTION",
          o.production_status == "RESEARCH_NON_PRODUCTION")

    # The stored row carries no claim field even for the owner.
    row = o.get_route(b"\x01" * 32)
    claim_fields = [k for k in row if any(w in k.lower() for w in consensus_words)]
    check("stored route row has no consensus-claim field (owner can't forge one)",
          not claim_fields, str(claim_fields))

    # Static side: the ink! message list in source matches the mirror set.
    src = open(ORACLE_RS).read()
    code = strip_rust_comments(src)
    fns = set(re.findall(r"pub fn (\w+)\(", code))
    expected = {
        "new", "publish_btcp_route", "verify_execution", "get_route",
        "add_validator", "remove_validator", "owner", "route_count",
        "version", "is_validator", "is_oracle_of_record",
    }
    check("ink! public message set in source == mirror set",
          fns == expected, str(fns ^ expected))


def test_doc_pin():
    print("\n5) documentation pins")
    inv = open(INVARIANTS_MD).read()
    check("CANONICAL_INVARIANTS.md registers the PVM research tier",
          "PVM (ink!" in inv and "research" in inv.lower())


def main():
    test_static_honesty_labels()
    test_no_consensus_machinery()
    test_authorization_mirror()
    test_consensus_forgery_impossible()
    test_doc_pin()

    print(f"\n═══ RESULT: {len(PASSED)} passed, {len(FAILED)} failed ═══")
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)
    print("C-05 PVM leg CLOSED: legacy_oracle.rs is honestly labeled "
          "RESEARCH/NON-PRODUCTION, carries the misuse-obvious flag, "
          "contains no consensus machinery, and is not an oracle of record.")


if __name__ == "__main__":
    main()
