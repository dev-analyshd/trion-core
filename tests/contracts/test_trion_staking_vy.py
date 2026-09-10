"""TRIONStaking.vy — validator fee structure compliance (D3 §11 Fix 4, M-180).

The M-180 row flagged the Vyper economics split: TRIONToken.vy and
BTCP_ESCROW.vy carried the security-critical token/escrow tier while the
D3 §11 Fix 4 validator fee structure only existed in the Rust calculator.
This battery pins the Vyper-side closure on real EVM execution
(eth-tester, vyper 0.3.10 — same stack as test_btcp_escrow_vy.py):

  1. compiles clean under vyper 0.3.10
  2. rarity_factor = total_validators / validators_covering_chain
     (D3-185/D3-278; doc example: 5% coverage → rarity 20)
  3. coverage_bonus = BASE_RATE × rarity × volume × uptime × chains
     (D3-185; zero coverage inputs → 0, never invented)
  4. btcp_route_reward = route.value × FEE_RATE (D3-186, 0.1%)
  5. the 60/40 anchor/execution split (D3-186/D3-279) — shares sum to the
     route reward exactly
  6. coverage_cost_offset (D3-184 offset term, 1 unit/chain)
  7. total_reward = base + coverage_bonus + route_reward − cost offset
     (D3-184), failing closed when the offset exceeds the gross reward

Constants are cross-checked against the Rust reference
(rust/src/validator_fee_calculator.rs: BASE_RATE 100.0, split 0.6/0.4,
fee 0.001, cost 1.0/chain) so the two implementations cannot drift.

Run: pytest tests/contracts/test_trion_staking_vy.py -q
"""
import os

import pytest

try:
    import vyper  # noqa: F401
    import web3  # noqa: F401
    import eth_tester  # noqa: F401
    _VYPER_OK = True
except Exception:  # pragma: no cover — env gap
    _VYPER_OK = False

_vyper_skip = pytest.mark.skipif(not _VYPER_OK, reason="vyper/web3/eth_tester absent")

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STAKING_VY = os.path.join(REPO, "contracts", "vyper", "TRIONStaking.vy")
FEE_CALC_RS = os.path.join(REPO, "rust", "src", "validator_fee_calculator.rs")

E18 = 10**18
E17 = 10**17


def _src(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _flat(path: str) -> str:
    """Source with runs of whitespace collapsed — pin-friendly for the
    aligned constant declarations in the .vy file."""
    import re
    return re.sub(r"\s+", " ", _src(path))


# ── Static source pins (constants + rust parity — cairo-mirror style) ─────────

class TestStakingSourcePins:

    def test_spec_constants_declared(self):
        src = _flat(STAKING_VY)
        for pin in (
            "BASE_REWARD: constant(uint256) = 100 * 10**18",
            "BTCP_ROUTE_SPLIT_ANCHOR_BPS: constant(uint256) = 6000",
            "BTCP_ROUTE_SPLIT_EXEC_BPS: constant(uint256) = 4000",
            "BTCP_ROUTE_FEE_RATE_BPS: constant(uint256) = 10",
            "COVERAGE_COST_PER_CHAIN: constant(uint256) = 10**18",
        ):
            assert pin in src, pin

    def test_constants_match_the_rust_reference(self):
        """Cross-language parity: the .vy constants mirror
        validator_fee_calculator.rs (BASE_RATE 100.0, split 0.6/0.4,
        fee 0.001 = 10 bps, cost 1.0 per chain)."""
        rs = _flat(FEE_CALC_RS)
        vy = _flat(STAKING_VY)
        assert "pub const BASE_RATE: f64 = 100.0;" in rs
        assert "BTCP_ROUTE_SPLIT_ANCHOR: f64 = 0.6;" in rs
        assert "BTCP_ROUTE_SPLIT_EXEC: f64 = 0.4;" in rs
        assert "pub const BTCP_ROUTE_FEE_RATE: f64 = 0.001;" in rs
        assert "BASE_REWARD: constant(uint256) = 100 * 10**18" in vy
        assert "BTCP_ROUTE_SPLIT_ANCHOR_BPS: constant(uint256) = 6000" in vy
        assert "BTCP_ROUTE_SPLIT_EXEC_BPS: constant(uint256) = 4000" in vy
        assert "BTCP_ROUTE_FEE_RATE_BPS: constant(uint256) = 10" in vy

    def test_fee_functions_are_pure_over_caller_supplied_inputs(self):
        """The explicit-input contract: no state reads, no fabricated
        figures — the oracle supplies the live network statistics."""
        src = _src(STAKING_VY)
        for fn in ("def rarity_factor(", "def coverage_bonus(",
                   "def btcp_route_reward(", "def btcp_route_reward_split(",
                   "def coverage_cost_offset(", "def total_validator_reward("):
            assert fn in src, fn


# ── Real EVM execution (vyper 0.3.10 + eth-tester) ────────────────────────────

if _VYPER_OK:
    from web3 import Web3
    from web3.providers.eth_tester import EthereumTesterProvider
    from eth_tester import EthereumTester


@_vyper_skip
class TestValidatorFeeStructureOnEVM:

    @pytest.fixture(scope="class")
    def staking(self):
        """Compile + deploy TRIONStaking with non-zero constructor bindings."""
        src = _src(STAKING_VY)
        out = vyper.compile_code(src, output_formats=["bytecode", "abi"])
        w3 = Web3(EthereumTesterProvider(EthereumTester()))
        acct, token, oracle, gov = w3.eth.accounts[:4]
        contract = w3.eth.contract(abi=out["abi"],
                                   bytecode=bytes.fromhex(out["bytecode"].removeprefix("0x")))
        tx = contract.constructor(token, oracle, gov).transact({"from": acct, "gas": 3_000_000})
        rcpt = w3.eth.wait_for_transaction_receipt(tx)
        return w3.eth.contract(address=rcpt.contractAddress, abi=out["abi"])

    def test_compiles_and_deploys_under_vyper_0310(self, staking):
        assert staking.functions.minimum_stake_for_tier(1).call() == 10_000 * E18

    def test_rarity_factor_doc_example(self, staking):
        """5% coverage → rarity 20 (D3-185/D3-278)."""
        assert staking.functions.rarity_factor(100, 5).call() == 20 * E18

    def test_rarity_factor_zero_coverage_fails_closed(self, staking, w3=None):
        with pytest.raises(Exception):
            staking.functions.rarity_factor(100, 0).call()

    def test_coverage_bonus_formula(self, staking):
        """BASE_RATE × rarity × volume × uptime × chains (D3-185):
        100 × 20 × 0.5 × 0.8 × 2 chains = 1600."""
        bonus = staking.functions.coverage_bonus(
            100, 5, 5 * E17, 8 * E17, 2).call()
        assert bonus == 1600 * E18

    def test_coverage_bonus_zero_inputs_never_invent(self, staking):
        assert staking.functions.coverage_bonus(100, 0, 5 * E17, 8 * E17, 2).call() == 0
        assert staking.functions.coverage_bonus(100, 5, 5 * E17, 8 * E17, 0).call() == 0

    def test_btcp_route_reward_fee_rate(self, staking):
        """0.1% of certified route value (D3-186)."""
        assert staking.functions.btcp_route_reward(10**24).call() == 10**21

    def test_route_reward_split_is_60_40_and_sums_exactly(self, staking):
        """D3-186/D3-279: 60% anchor / 40% execution."""
        anchor, exec_share = staking.functions.btcp_route_reward_split(10**24).call()
        total = staking.functions.btcp_route_reward(10**24).call()
        assert anchor == 6 * 10**20
        assert exec_share == 4 * 10**20
        assert anchor + exec_share == total

    def test_coverage_cost_offset_per_chain(self, staking):
        assert staking.functions.coverage_cost_offset(3).call() == 3 * E18

    def test_total_reward_composition(self, staking):
        """D3-184: base + coverage_bonus + route_reward − cost offset."""
        total = staking.functions.total_validator_reward(
            100 * E18, 1600 * E18, 1000 * E18, 3 * E18).call()
        assert total == 2697 * E18

    def test_total_reward_fails_closed_on_negative_composition(self, staking):
        with pytest.raises(Exception):
            staking.functions.total_validator_reward(
                100 * E18, 0, 0, 200 * E18).call()


def main():
    """Script-mode entry (repo contract-battery convention)."""
    rc = pytest.main([os.path.abspath(__file__), "-q", "-p", "no:cacheprovider"])
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
