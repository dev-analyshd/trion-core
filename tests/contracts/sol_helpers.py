"""Shared real-EVM harness for the Solidity-tier canonical-certificate tests.

Compiles the REAL contracts under contracts/solidity (via py-solcx + eth_tester
/ py-evm — no network, real EVM semantics including the ecrecover precompile)
and provides:

- validator key generation + EIP-191 message signing over the canonical digest
- a Python-side mirror of the Solidity ``CanonicalCertificate.Cert`` struct
  (built on the Wave-1 reference encoder ``core/consensus/certificate.py`` so
  the py↔sol payloads are byte-identical by construction)
- cert → web3 struct-dict conversion, signature-batch assembly (sorted
  ascending by recovered signer, per the V3 batch discipline)

Run: python3 tests/contracts/<test file>.py
"""

import os
import sys

from web3 import Web3
from web3.providers.eth_tester import EthereumTesterProvider
from eth_tester import EthereumTester
from eth_account import Account
from eth_account.messages import encode_defunct
import solcx

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOLC_VERSION = "0.8.24"

# Load the reference encoder by file path — no sys.path mutation (the repo's
# import-hygiene policy, tests/unit/test_no_sys_path_hacks.py). Works both
# under pytest (tests/conftest.py provides the root for other imports) and
# when this file is executed directly.
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "core.consensus.certificate", os.path.join(REPO, "core", "consensus", "certificate.py"))
import sys as _sys
_mod = _ilu.module_from_spec(_spec)
_sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
PyCanonicalCertificate = _mod.CanonicalCertificate

SOLIDITY = os.path.join(REPO, "contracts", "solidity")

# Cert field order MUST match contracts/solidity/libraries/CanonicalCertificate.sol
CERT_FIELDS = [
    "certificateKind", "protocolVersion", "validatorEpoch", "certificateNonce",
    "escrowId", "routeId", "intentHash", "entityId", "sourceChain", "destChain",
    "destination", "amount", "anchorBh", "executionBh",
    "coherence", "threshold", "hhiAtEmission", "totalEffectivePower",
    "validatorCount", "awaEnforced", "issuedAt", "ttl",
]


class EvmHarness:
    """One eth_tester chain + a compile cache for the real contract files."""

    # The canonical dest-chain binding (P-EVM-01 fix) compares the
    # certificate's dest_chain against block.chainid. eth_tester's default
    # artificial id (131277322940537) exceeds the u32 registry space, so the
    # harness pins the EVM-level chain id to 1 — a realistic registry id.
    TEST_CHAIN_ID = 1

    def __init__(self):
        self.t = EthereumTester()
        # Patch the closure-local chain class (MainnetTesterPosChain) so the
        # CHAINID opcode reports TEST_CHAIN_ID to contracts.
        _backend = self.t.backend
        type(_backend.chain).chain_id = self.TEST_CHAIN_ID
        self.w3 = Web3(EthereumTesterProvider(self.t))
        self.acct = self.w3.eth.accounts[0]      # owner / relayer / registrar
        self.other = self.w3.eth.accounts[1]     # attacker / non-owner
        self.dest = self.w3.eth.accounts[2]      # escrow destination
        self._cache = {}
        solcx.install_solc(SOLC_VERSION)

    # ── compilation / deployment ───────────────────────────────────────────
    def compile(self, paths, names=None, via_ir=True):
        """Compile real repo files; returns {(path, name): (abi, bin)}."""
        key = tuple(paths)
        if key in self._cache:
            outs = self._cache[key]
        else:
            outs = solcx.compile_files(
                paths, output_values=["abi", "bin"], optimize=True,
                solc_version=SOLC_VERSION, via_ir=via_ir)
            self._cache[key] = outs
        picked = {}
        for k, v in outs.items():
            name = k.split(":")[-1]
            if names is None or name in names:
                picked[name] = (v["abi"], v["bin"])
        return picked

    def deploy(self, abi, bin_, from_=None, args=(), gas=8_000_000):
        from_ = from_ or self.acct
        c = self.w3.eth.contract(abi=abi, bytecode=bin_)
        tx = c.constructor(*args).transact({"from": from_, "gas": gas})
        rcpt = self.w3.eth.wait_for_transaction_receipt(tx)
        return self.w3.eth.contract(address=rcpt.contractAddress, abi=abi)

    def path(self, *rel):
        return os.path.join(SOLIDITY, *rel)

    # ── time / chain ───────────────────────────────────────────────────────
    def now(self):
        return self.w3.eth.get_block("latest")["timestamp"]

    def mine(self, seconds=1):
        self.t.mine_blocks(1) if seconds == 0 else self.t.time_travel(seconds)

    def balance(self, addr):
        return self.w3.eth.get_balance(addr)

    def must_revert(self, fn_call, sender=None, gas=3_000_000):
        sender = sender or self.acct
        try:
            txh = fn_call.transact({"from": sender, "gas": gas})
        except Exception:
            return True  # web3 pre-flight revert (eth_tester raises)
        rcpt = self.w3.eth.wait_for_transaction_receipt(txh)
        return rcpt["status"] == 0

    def tx(self, fn_call, sender=None, gas=5_000_000):
        sender = sender or self.acct
        txh = fn_call.transact({"from": sender, "gas": gas})
        rcpt = self.w3.eth.wait_for_transaction_receipt(txh)
        assert rcpt["status"] == 1, f"tx reverted: {rcpt}"
        return rcpt


# ── validator keys ──────────────────────────────────────────────────────────

def addr_key(a: str) -> int:
    """Numeric sort key for checksummed address strings (string sort is NOT
    numeric order — '0xC4...' < '0xa0...' as strings)."""
    return int(a, 16)


def sort_numeric(addrs):
    return sorted(addrs, key=addr_key)


def make_validators(n, seed_start=0xCE57_0AAA_0000_0000_0000_0000_0000_0001):
    """Deterministic validator keypairs: address + private key.

    Keys are deliberately far away from eth_tester's default accounts (which
    are derived from private keys 1..10) so validator addresses never collide
    with the harness owner/attacker/destination accounts.
    """
    out = []
    for i in range(n):
        key = (seed_start + i).to_bytes(32, "big")
        acct = Account.from_key(key)
        out.append({"key": key, "addr": acct.address, "acct": acct})
    return out


# ── certificate construction (py reference = ground truth bytes) ────────────

def make_cert(**kw) -> PyCanonicalCertificate:
    """Build a py reference certificate (defaults chosen to pass §6)."""
    from core.consensus.certificate import pack_version  # local import
    defaults = dict(
        certificate_kind=1,
        protocol_version=pack_version(1, 2, 3),
        validator_epoch=1,
        certificate_nonce=1,
        escrow_id=Web3.keccak(text="escrow-1"),
        route_id=Web3.keccak(text="route-1"),
        intent_hash=Web3.keccak(text="intent-1"),
        entity_id=Web3.keccak(text="entity-1"),
        source_chain=1,
        dest_chain=1,
        destination=b"\x00" * 12 + b"\x11" * 20,
        amount=10**18,
        anchor_bh=Web3.keccak(text="anchor-1"),
        execution_bh=Web3.keccak(text="exec-1"),
        coherence=900_000,
        threshold=550_000,
        hhi_at_emission=1_200,
        total_effective_power=2_100_000,
        validator_count=3,
        awa_enforced=True,
        issued_at=0,       # caller sets
        ttl=3_600,
    )
    defaults.update(kw)
    return PyCanonicalCertificate(**defaults)


def cert_to_sol(cert: PyCanonicalCertificate) -> dict:
    """py reference certificate → web3 struct dict (Solidity field names)."""
    return {
        "certificateKind": cert.certificate_kind,
        "protocolVersion": cert.protocol_version,
        "validatorEpoch": cert.validator_epoch,
        "certificateNonce": cert.certificate_nonce,
        "escrowId": cert.escrow_id,
        "routeId": cert.route_id,
        "intentHash": cert.intent_hash,
        "entityId": cert.entity_id,
        "sourceChain": cert.source_chain,
        "destChain": cert.dest_chain,
        "destination": cert.destination,
        "amount": cert.amount,
        "anchorBh": cert.anchor_bh,
        "executionBh": cert.execution_bh,
        "coherence": cert.coherence,
        "threshold": cert.threshold,
        "hhiAtEmission": cert.hhi_at_emission,
        "totalEffectivePower": cert.total_effective_power,
        "validatorCount": cert.validator_count,
        "awaEnforced": cert.awa_enforced,
        "issuedAt": cert.issued_at,
        "ttl": cert.ttl,
    }


# ── signing ─────────────────────────────────────────────────────────────────

# SEC-21: the EVM escrow verifies release certificates over the
# deployment-BOUND digest — the Python twin of
# CanonicalCertificate.escrowBoundEthDigestOf. A certificate signed for one
# escrow deployment recovers garbage signers on any other deployment.
ESCROW_BINDING_DOMAIN = Web3.keccak(text="TRION-ESCROW-BOUND-V1")


def escrow_binding_inner(harness: EvmHarness, escrow_address, inner: bytes) -> bytes:
    """keccak(ESCROW_BINDING_DOMAIN ‖ escrow ‖ inner) — the deployment-bound
    inner digest the EVM-family validators sign for a SPECIFIC escrow
    (CanonicalCertificate.escrowBoundEthDigestOf, SEC-21 fix)."""
    escrow = bytes.fromhex(
        escrow_address.removeprefix("0x")
        if isinstance(escrow_address, str) else escrow_address.hex())
    return harness.w3.keccak(ESCROW_BINDING_DOMAIN + escrow + inner)


def eip191_signed_hash(harness: EvmHarness, inner: bytes) -> bytes:
    """keccak(b"\\x19Ethereum Signed Message:\\n32" ‖ inner) — the value the
    EVM-family validators sign (CanonicalCertificate.ethSignedDigest)."""
    return harness.w3.keccak(b"\x19Ethereum Signed Message:\n32" + inner)


def sign_cert(harness: EvmHarness, cert: PyCanonicalCertificate, signers,
              escrow_address=None):
    """Sign the canonical payload with `signers` (list of validator dicts).

    With `escrow_address` the signatures are made over the deployment-bound
    digest (CanonicalCertificate.escrowBoundEthDigestOf) — what the EVM
    escrow verifies on releaseEscrowCanonical (SEC-21: the quorum signs for
    ONE escrow deployment). Without it the plain EIP-191 wrap of keccak256(P)
    is signed (the oracle observability path, submitCertificateAttestation).

    Returns (signatures, stakeWeights, diversityWeights, signersSorted) —
    sorted ascending by signer address (the V3 batch discipline).
    """
    inner = harness.w3.keccak(cert.encode_payload())   # keccak256(P)
    if escrow_address is not None:
        inner = escrow_binding_inner(harness, escrow_address, inner)
    msg = encode_defunct(primitive=inner)              # EIP-191 wrap of inner
    entries = []
    for v in signers:
        signed = v["acct"].sign_message(msg)
        vbyte = signed.v if signed.v in (27, 28) else signed.v + 27
        sig = signed.r.to_bytes(32, "big") + signed.s.to_bytes(32, "big") + bytes([vbyte])
        entries.append((v["addr"], sig))
    entries.sort(key=lambda e: int(e[0], 16))
    return (
        [e[1] for e in entries],
        None,   # weights filled by caller from the epoch set
        None,
        [e[0] for e in entries],
    )


def sign_cert_with_weights(harness, cert, signers, stake, diversity,
                           escrow_address=None):
    """Sign + attach the envelope weight CLAIMS (§4) in signer-sorted order.

    `stake`/`diversity` may be either an index-aligned list (matching
    `signers`) or an address-keyed mapping ({addr: value}); returns the fully
    assembled (signatures, stakeWeights, diversityWeights, sorted_addrs) call
    arguments. `escrow_address` selects the deployment-bound digest (see
    sign_cert — the escrow release path); the default signs the plain
    payload digest (the oracle path).
    """
    sigs, _, _, sorted_addrs = sign_cert(harness, cert, signers, escrow_address)
    by_addr = {v["addr"]: i for i, v in enumerate(signers)}

    def _pick(weights, addr):
        if isinstance(weights, dict):
            return weights[addr]
        return weights[by_addr[addr]]

    stakes = [_pick(stake, a) for a in sorted_addrs]
    divs = [_pick(diversity, a) for a in sorted_addrs]
    return sigs, stakes, divs, sorted_addrs


# ── receipt event decoding (web3 v7 receipts carry raw logs) ────────────────

_TOPIC_CACHE = {}


def event_names(contract, rcpt):
    """Decode a tx receipt's logs into event names (topic0 → name)."""
    abi = contract.abi
    key = id(abi)
    if key not in _TOPIC_CACHE:
        m = {}
        for item in abi:
            if item.get("type") == "event" and not item.get("anonymous", False):
                sig = item["name"] + "(" + ",".join(
                    i["type"] for i in item.get("inputs", [])) + ")"
                m[Web3.keccak(text=sig)] = item["name"]
        _TOPIC_CACHE[key] = m
    names = []
    for log in rcpt["logs"]:
        names.append(_TOPIC_CACHE[key].get(log["topics"][0], "<unknown>"))
    return names
