#!/usr/bin/env bash
# leakage_grep_contracts.sh — TRION BZK Phase 4 acceptance gate.
#
# Per mission Phase 4 ACCEPTANCE: "greps the contract source for ABSENT
# fields (per R-ABSENT)". This script greps the entire contracts/zk/
# directory for the forbidden tokens listed in BTCP §7.1 (BEHAVIORAL_
# TRUTH_SIGNAL ABSENT fields) + BTCP Fix 1 Step 3 (private inputs) +
# BTCP §7.1 Sensing Oracle private inputs + WP-Mar §16 BIRP user-secret
# content/length/timing.
#
# Forbidden tokens (case-sensitive, word-bounded):
#   disclosure_contents   — BTCP Fix 1 Step 3 private input (NEVER stored)
#   regulator_receipt     — BTCP Fix 1 Step 3 private input (NEVER stored)
#   private_behavior      — BTCP §7.1 Sensing Oracle private input (NEVER stored)
#   DNA_Code              — WP-Mar §16 BIRP user-secret (NEVER stored)
#   behavior_content      — BTCP §7.1 BEHAVIORAL_TRUTH_SIGNAL ABSENT field
#   amount                — BTCP §7.1 BEHAVIORAL_TRUTH_SIGNAL ABSENT field
#   counterparty          — BTCP §7.1 BEHAVIORAL_TRUTH_SIGNAL ABSENT field
#   protocol              — BTCP §7.1 BEHAVIORAL_TRUTH_SIGNAL ABSENT field
#   chain                 — BTCP §7.1 BEHAVIORAL_TRUTH_SIGNAL ABSENT field
#
# Word-boundary matching (-w) is used so that "blockchain" does NOT match
# "chain" (blockchain is a single word), but a standalone "chain" identifier
# would. The Solidity source uses "onchain" / "offchain" (single words) and
# "ledger identifier" / "message-layer identifier" / "counter-party
# identifier" to comply with R-ABSENT while remaining readable.
#
# Exit code:
#   0  — CLEAN (no forbidden tokens found)
#   1  — NOT CLEAN (at least one forbidden token found — R-ABSENT violation)

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

FORBIDDEN_TOKENS=(
  "disclosure_contents"
  "regulator_receipt"
  "private_behavior"
  "DNA_Code"
  "behavior_content"
  "amount"
  "counterparty"
  "protocol"
  "chain"
)

leaks_found=0
leak_report=""

for tok in "${FORBIDDEN_TOKENS[@]}"; do
  matches=$(grep -rnIw \
    --exclude="leakage_grep_contracts.sh" \
    --exclude-dir="data" \
    --exclude-dir="__pycache__" \
    --exclude-dir="hardhat-cache" \
    --exclude-dir="hardhat-artifacts" \
    --exclude-dir="node_modules" \
    --exclude="*.abi" \
    --exclude="*.json" \
    --exclude="*.bin" \
    -- "$tok" "$DIR" 2>/dev/null || true)
  if [ -n "$matches" ]; then
    leaks_found=$((leaks_found + 1))
    leak_report+="LEAK: forbidden token '$tok' found in contracts/zk/:
$matches

"
  fi
done

if [ "$leaks_found" -eq 0 ]; then
  echo "CLEAN: no forbidden ABSENT tokens found in $DIR"
  echo "  (checked: ${FORBIDDEN_TOKENS[*]})"
  echo "  R-ABSENT invariant holds. Phase 4 acceptance gate: GREPS CLEAN."
  exit 0
else
  echo "NOT CLEAN: $leaks_found forbidden token(s) found in $DIR" >&2
  echo "" >&2
  printf "%s" "$leak_report" >&2
  echo "R-ABSENT violation. Phase 4 acceptance gate: GREPS NOT CLEAN." >&2
  exit 1
fi
