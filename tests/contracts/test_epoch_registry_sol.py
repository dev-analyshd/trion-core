"""
TrionEpochRegistry — per-epoch canonical validator state on a real EVM
(Wave 2, Agent G — H-01 infrastructure).

Closes the H-01 ground layer: epoch sets with s_j/d_j weights, sequential
rotation, the grace window, H-03 threshold provenance storage and the L4.2
tier quorum view. Positive + adversarial pairs:

1. registration: valid set registers; views return the canonical values.
2. rotation: sequential epochs rotate the set; old epochs fall out of grace.
3. ADVERSARIAL registration: non-registrar, non-sequential epoch, duplicate/
   unsorted validators, bad ranges, CRITICAL HHI, tiny set — all revert.
4. epochActive: unknown epoch 0, future epoch, stale epoch (beyond grace)
   all inactive; current + within-grace active.
5. epochQuorum: count-attack shape (weights recomputed from the registry,
   never from the caller) and the tier boundary math.
6. init takeover: constructor-only ownership; non-owner cannot become
   registrar; no initialize() path exists (grep-verified in the report).

Run: python3 tests/contracts/test_epoch_registry_sol.py
"""

import os
import sys

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "tests.contracts.sol_helpers",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "sol_helpers.py"))
import sys as _sys
_sh = _ilu.module_from_spec(_spec)
_sys.modules[_spec.name] = _sh
_spec.loader.exec_module(_sh)
EvmHarness, make_validators, sort_numeric = (  # noqa: E402
    _sh.EvmHarness, _sh.make_validators, _sh.sort_numeric
)

PASSED = []
FAILED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"  {'OK' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))


def register(h, reg, epoch, vals, stakes, divs, d_cons, threshold, hhi,
             sender=None, expect_fail=False):
    fn = reg.functions.registerEpoch(epoch, [v["addr"] for v in vals], stakes, divs,
                                     d_cons, threshold, hhi)
    if expect_fail:
        return h.must_revert(fn, sender=sender)
    h.tx(fn, sender=sender)
    return True


def main():
    h = EvmHarness()
    reg = h.deploy(*h.compile([h.path("TrionEpochRegistry.sol")])["TrionEpochRegistry"])

    # 5 validators, stake 1.0 each, diversities 0.7/0.1/0.1/0.05/0.05
    # → w_j = [700k, 100k, 100k, 50k, 50k] ×1e6, total 1.0e6,
    #   D_consensus = 200k (tier 3), Θ = 550k.
    vals = make_validators(5)
    stakes = [1_000_000] * 5
    divs = [700_000, 100_000, 100_000, 50_000, 50_000]
    # numeric address order (string sort ≠ uint160 order — see sol_helpers)
    addrs = sort_numeric([v["addr"] for v in vals])
    by_addr = {v["addr"]: v for v in vals}
    vals_sorted = [by_addr[a] for a in addrs]
    stakes_sorted = [stakes[[v["addr"] for v in vals].index(a)] for a in addrs]
    divs_sorted = [divs[[v["addr"] for v in vals].index(a)] for a in addrs]
    div_by_addr = {a: d for a, d in zip(addrs, divs_sorted)}
    heavy_addr = max(div_by_addr, key=lambda a: div_by_addr[a])

    print("\n1) registration — canonical values land")
    check("latestEpoch starts 0", reg.functions.latestEpoch().call() == 0)
    register(h, reg, 1, vals_sorted, stakes_sorted, divs_sorted, 200_000, 550_000, 1_200)
    check("latestEpoch == 1", reg.functions.latestEpoch().call() == 1)
    check("epoch 1 registered", reg.functions.epochRegistered(1).call())
    check("epochActive(1) true", reg.functions.epochActive(1).call())
    check("total power == 1.0e6", reg.functions.epochTotalPower(1).call() == 1_000_000)
    check("validator count == 5", reg.functions.epochValidatorCount(1).call() == 5)
    check("d_consensus == 200k", reg.functions.epochDConsensus(1).call() == 200_000)
    check("epoch threshold == 550k (H-03 provenance)", reg.functions.epochThreshold(1).call() == 550_000)
    check("epoch hhi == 1200", reg.functions.epochHHI(1).call() == 1_200)
    # heavy validator's weight (by registered diversity, not address order)
    w0 = reg.functions.validatorWeight(1, heavy_addr).call()
    check("w_j = s_j·d_j/1e6 for the heavy validator", w0 == 700_000, str(w0))
    check("stake/diversity views return claims",
          reg.functions.validatorStake(1, heavy_addr).call() == 1_000_000
          and reg.functions.validatorDiversity(1, heavy_addr).call() == 700_000)
    check("non-member weight == 0",
          reg.functions.validatorWeight(1, h.other).call() == 0)

    print("\n2) sequential rotation + grace")
    # rotate to epoch 2 with the same set, then 3, 4 — epoch 1 falls out of grace (4-1=3 > 2)
    for ep in (2, 3, 4):
        register(h, reg, ep, vals_sorted, stakes_sorted, divs_sorted, 200_000, 550_000, 1_200)
    check("latestEpoch == 4", reg.functions.latestEpoch().call() == 4)
    check("epochActive(4) true (current)", reg.functions.epochActive(4).call())
    check("epochActive(3) true (within grace 2)", reg.functions.epochActive(3).call())
    check("epochActive(2) true (grace edge)", reg.functions.epochActive(2).call())
    check("epochActive(1) false (retired beyond grace)", not reg.functions.epochActive(1).call())

    print("\n3) adversarial registration")
    check("non-sequential epoch reverts",
          register(h, reg, 6, vals_sorted, stakes_sorted, divs_sorted, 200_000, 550_000, 1_200, expect_fail=True))
    check("re-registering an existing epoch reverts",
          register(h, reg, 4, vals_sorted, stakes_sorted, divs_sorted, 200_000, 550_000, 1_200, expect_fail=True))
    check("non-registrar cannot register",
          register(h, reg, 5, vals_sorted, stakes_sorted, divs_sorted, 200_000, 550_000, 1_200,
                   sender=h.other, expect_fail=True))
    # unsorted / duplicate validators
    check("unsorted validators revert",
          register(h, reg, 5, list(reversed(vals_sorted)), stakes_sorted, divs_sorted,
                   200_000, 550_000, 1_200, expect_fail=True))
    dup = [vals_sorted[0], vals_sorted[0], vals_sorted[1], vals_sorted[2], vals_sorted[3]]
    check("duplicate validators revert",
          register(h, reg, 5, dup, stakes_sorted, divs_sorted, 200_000, 550_000, 1_200, expect_fail=True))
    check("CRITICAL hhi (>4000) reverts",
          register(h, reg, 5, vals_sorted, stakes_sorted, divs_sorted, 200_000, 550_000, 4_001, expect_fail=True))
    check("tiny set (<3) reverts",
          register(h, reg, 5, vals_sorted[:2], stakes_sorted[:2], divs_sorted[:2],
                   200_000, 550_000, 1_200, expect_fail=True))
    check("diversity > 1e6 reverts",
          register(h, reg, 5, vals_sorted, stakes_sorted, [2_000_000] * 5,
                   200_000, 550_000, 1_200, expect_fail=True))
    check("threshold > 1e6 reverts",
          register(h, reg, 5, vals_sorted, stakes_sorted, divs_sorted, 200_000, 1_000_001, 1_200, expect_fail=True))

    print("\n4) epoch inactivity classes")
    check("epoch 0 never active", not reg.functions.epochActive(0).call())
    check("future epoch (99) not active", not reg.functions.epochActive(99).call())
    check("unregistered epoch views are zero",
          reg.functions.epochTotalPower(99).call() == 0
          and reg.functions.epochValidatorCount(99).call() == 0)

    print("\n5) epochQuorum — registry weights, never caller claims")
    div_by_addr = {a: d for a, d in zip(addrs, divs_sorted)}
    heavy_addr = max(div_by_addr, key=lambda a: div_by_addr[a])
    low_addrs = [a for a in addrs if a != heavy_addr]           # 100+100+50+50 = 300k
    # tier 3 set (D=0.2 < 0.4): 0.85 quorum → 850k needed of 1.0e6
    met, sp, tp, tier = reg.functions.epochQuorum(4, low_addrs).call()
    check("count-attack: 4 low-weight signers fail weight quorum",
          (not met) and sp == 300_000 and tp == 1_000_000 and tier == 3,
          f"met={met} sp={sp} tp={tp} tier={tier}")
    heavy4 = [heavy_addr] + [a for a in addrs if a != heavy_addr][:3]  # 700k + top-3 lows
    met, sp, tp, tier = reg.functions.epochQuorum(4, heavy4).call()
    check("heavy + 3 reaches tier-3 quorum (sp ≥ 850k)",
          met and sp >= 850_000 and sp <= 950_000 and tier == 3, f"sp={sp}")
    unknown = low_addrs + [h.other]
    met, sp, tp, tier = reg.functions.epochQuorum(4, unknown).call()
    check("unknown signers contribute zero power", sp == 300_000 and not met)

    print("\n6) init takeover — constructor-only ownership")
    check("owner is deployer", reg.functions.owner().call() == h.acct)
    check("registrar defaults to deployer", reg.functions.registrar().call() == h.acct)
    check("non-owner cannot set registrar",
          h.must_revert(reg.functions.setRegistrar(h.other), sender=h.other))
    check("non-owner cannot set grace",
          h.must_revert(reg.functions.setGrace(1), sender=h.other))
    check("zero registrar rejected",
          h.must_revert(reg.functions.setRegistrar("0x" + "00" * 20)))
    # rotate registrar and prove the old one loses power
    h.tx(reg.functions.setRegistrar(h.other))
    check("registrar rotated", reg.functions.registrar().call() == h.other)
    check("OLD registrar can no longer register",
          register(h, reg, 5, vals_sorted, stakes_sorted, divs_sorted, 200_000, 550_000, 1_200, expect_fail=True))
    check("NEW registrar can register (epoch 5)",
          register(h, reg, 5, vals_sorted, stakes_sorted, divs_sorted, 200_000, 550_000, 1_200, sender=h.other) or True)
    check("epoch 5 active after rotation", reg.functions.epochActive(5).call())
    check("epoch 2 retired after rotation (5-2=3 > grace)",
          not reg.functions.epochActive(2).call())

    print(f"\n═══ RESULT: {len(PASSED)} passed, {len(FAILED)} failed ═══")
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)
    print("TrionEpochRegistry: sequential rotation, grace, weights, takeover-guards verified.")


def test_full_battery_runs_clean():
    """pytest entry point (battery-integrity fix, follow-on-2 loop): the
    script battery must run clean whenever the pytest contracts battery
    runs — main() exits non-zero on any check() failure. Script-mode
    ("python3 tests/contracts/<file>.py") keeps working unchanged."""
    main()


if __name__ == "__main__":
    main()
