#!/usr/bin/env bash
# leakage_grep.sh — TRION BZK Phase 2 acceptance gate.
#
# Per mission Phase 2 ACCEPTANCE: "roots publish; greps clean."
# Per R-ABSENT: NEVER store disclosure payload, regulator receipt, private
# behavior, user-secret content/length/timing, behavior content, value,
# counterparty, protocol, or chain identifier as PERSISTED FIELDS anywhere
# in the commitment layer.
#
# This script greps the entire zk-circuits/commitments/ directory for the
# forbidden tokens listed in BTCP §7.1 (BEHAVIORAL_TRUTH_SIGNAL ABSENT
# fields) + BTCP Fix 1 Step 3 (private inputs) + BTCP §7.1 (private inputs)
# + WP-Mar §16 (BIRP user-secret content/length/timing).
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
# Exit code:
#   0  — CLEAN (no forbidden tokens found)
#   1  — NOT CLEAN (at least one forbidden token found — R-ABSENT violation)
#
# Word-boundary matching (-w) is used so that "blockchain" does NOT match
# "chain" (because `blockchain` is a single word), but a standalone "chain"
# identifier would. Case-sensitive matching is used so "hash_dna_code" does
# NOT match "DNA_Code".
#
# This script excludes itself from the grep (the script's own documentation
# block above must list the forbidden tokens, so we cannot let it self-match).
# It also excludes the SQLite data/ directory (binary files).

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Forbidden tokens — exactly as listed in BTCP §7.1 + Fix 1 Step 3 + WP-Mar §16.
# Stored here in an array; the script greps for each one.
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
  # -rI : recursive, skip binary files
  # -n  : line numbers
  # -w  : word-bounded match (so "blockchain" does NOT match "chain")
  # --exclude=this script itself (the script's docstring lists the tokens)
  # --exclude-dir=data : skip the SQLite DB files
  matches=$(grep -rnIw \
    --exclude="leakage_grep.sh" \
    --exclude-dir="data" \
    --exclude-dir="__pycache__" \
    --exclude="*.db" \
    --exclude="*.pyc" \
    -- "$tok" "$DIR" 2>/dev/null || true)
  if [ -n "$matches" ]; then
    leaks_found=$((leaks_found + 1))
    leak_report+="LEAK: forbidden token '$tok' found in commitments/ layer:
$matches

"
  fi
done

if [ "$leaks_found" -eq 0 ]; then
  echo "CLEAN: no forbidden ABSENT tokens found in $DIR"
  echo "  (checked: ${FORBIDDEN_TOKENS[*]})"
  echo "  R-ABSENT invariant holds. Phase 2 acceptance gate: GREPS CLEAN."
  exit 0
else
  echo "NOT CLEAN: $leaks_found forbidden token(s) found in $DIR" >&2
  echo "" >&2
  printf "%s" "$leak_report" >&2
  echo "R-ABSENT violation. Phase 2 acceptance gate: GREPS NOT CLEAN." >&2
  exit 1
fi
