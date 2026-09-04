# TRION + BTCP — Autonomous Master Worklog

Standing record of the autonomous canonical-reconstruction / security / architecture
loop. One section per wave. Never rewritten — append only.

Hierarchy of truth (fixed, per master command):
1. Authoritative TRION whitepaper/specification
2. Authoritative BTCP specification
3. Canonical math definitions and protocol invariants
4. Canonical security requirements derived from the specs
5. Existing implementation
6. Tests
7. Documentation/comments
8. Engineering judgment

Authoritative specification set (established at freeze, HEAD af09ab3, 2026-09-04):

| Document | Role | Status |
|---|---|---|
| spec/WHITEPAPER_MD.txt | Canonical whitepaper (Feb 2026, updated Mar 2026) — protocol semantics | AUTHORITATIVE (newest, wins semantic conflicts) |
| spec/WHITEPAPER_V2.txt | Complete implementation specification — every formula/component (Feb 2026, "all gaps filled", Parts 1–13 incl. Part 12 team roles) | AUTHORITATIVE (implementation detail; V2 wins where MD is silent) |
| spec/BTCP_SPEC.txt | BTCP master implementation spec (§4.1 intent, 6-step sequence, §5.x modules, §14 build order) | AUTHORITATIVE for BTCP |
| spec/L0–L9 layer docs | Layer-level definitions (universal primitives → cross-species) | AUTHORITATIVE (layer scope) |
| spec/DD_REPORT.txt | Due-diligence report (S1–S10, C1–C10) | AUDIT INPUT (not a spec) |
| spec/signal_types, novel_primitives, falsifiability_registry, communication_channels | Supporting normative tables | AUTHORITATIVE (their domain) |

Conflict rule: MD > V2 on protocol semantics (newer); V2 > MD on implementation
detail where MD is silent; BTCP_SPEC governs BTCP absolutely; DD_REPORT never
overrides a spec.

Baseline at Wave 1 open:
- HEAD af09ab3, working tree clean, origin/main synced, author dev-analyshd
- 691 unit tests + 9 skipped; tests/btcp 39; bitp 33; adversarial 120/121
  (1 failure = PQC libs absent — environmental, proven pre-existing)
- Task 20 (23 commits) + Task 21 (23 commits) landed and lead-verified; all
  open items from those waves closed; remaining items are external-toolchain
  (cargo, go, PQC libs, funded keys, live RPCs, validator fleet, TimescaleDB)
- External toolchain policy in force: static verification + deterministic tests
  + documented unverified boundaries; no fabricated verification

Wave plan (roles per master command §3–§21):
- W1: A (spec matrix), B (canonical BH + golden vectors), E (canonical
  certificate), F (invariants + BTCP state machine)
- W2: G (EVM/Solidity), H (Solana), I (Move), J (TON), K (Cairo), L (Vyper)
- W3: C (chain registry/indexers), D (Akashic/BEO/math), M (API/relayer/SDK),
  N (storage), O (deployment)
- W4: P (red team), Q (dead code), R (docs conformance)
- W5: S (final integration + fresh adversarial review + FINAL report)

---

## WAVE 1 — Foundation: canonical specifications, BH, certificate, invariants

Status: OPEN
Agents: A, B, E, F (parallel, disjoint file ownership)
Lead: freeze performed above; this worklog opened.

(Agents append per-wave results via the lead after integration; per-agent
detailed logs live in the shared engineering worklog outside the repo and in
each agent's final report to the lead.)
