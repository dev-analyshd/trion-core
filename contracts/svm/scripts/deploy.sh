#!/usr/bin/env bash
# =============================================================================
# TRION BTCP Solana Programs — Deployment Script
# =============================================================================
# Deploys all three BTCP Anchor programs to Solana devnet.
#
# Prerequisites:
#   - Solana CLI:  solana --version
#   - Anchor CLI:   anchor --version  (or cargo-build-sbf + solana program deploy)
#   - Wallet:       ~/.config/solana/id.json  (or SOLANA_KEYPAIR env var)
#   - Devnet SOL:   solana airdrop 2  (or use your key with existing balance)
#
# Usage:
#   ./deploy.sh                    # Deploy to devnet with default wallet
#   SOLANA_KEYPAIR=./my.json ./deploy.sh   # Use specific wallet
#   CLUSTER=mainnet ./deploy.sh    # Deploy to mainnet (CAUTION!)
# =============================================================================
set -euo pipefail

CLUSTER="${CLUSTER:-devnet}"
KEYPAIR="${SOLANA_KEYPAIR:-$HOME/.config/solana/id.json}"
WORKSPACE_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "═══════════════════════════════════════════════════════════════════"
echo "  TRION BTCP Solana Programs — Deployment"
echo "  Cluster: $CLUSTER"
echo "  Wallet:  $KEYPAIR"
echo "═══════════════════════════════════════════════════════════════════"
echo

# ── Pre-flight checks ────────────────────────────────────────────────────────
echo "📋 Pre-flight checks..."

if ! command -v solana &>/dev/null; then
    echo "❌ solana CLI not found. Install: https://docs.solana.com/cli/install-solana-cli-tools"
    exit 1
fi

if ! command -v cargo-build-sbf &>/dev/null; then
    echo "⚠️  cargo-build-sbf not found. Trying anchor..."
    if ! command -v anchor &>/dev/null; then
        echo "❌ Neither cargo-build-sbf nor anchor found."
        echo "   Install Anchor: https://www.anchor-lang.com/docs/installation"
        exit 1
    fi
    USE_ANCHOR=true
else
    USE_ANCHOR=false
fi

if [ ! -f "$KEYPAIR" ]; then
    echo "❌ Keypair not found: $KEYPAIR"
    echo "   Generate one: solana-keygen new -o $KEYPAIR"
    exit 1
fi

# Set Solana config
solana config set --url "$CLUSTER" --keypair "$KEYPAIR" &>/dev/null

WALLET_ADDR=$(solana address -k "$KEYPAIR")
WALLET_BAL=$(solana balance -k "$KEYPAIR" | cut -d' ' -f1)
echo "   Wallet: $WALLET_ADDR"
echo "   Balance: $WALLET_BAL SOL"

if (( $(echo "$WALLET_BAL < 1.0" | bc -l) )); then
    echo "⚠️  Low balance. Requesting airdrop..."
    solana airdrop 2 -k "$KEYPAIR" --url "$CLUSTER" 2>/dev/null || true
fi

echo

# ── Generate program keypairs if needed ──────────────────────────────────────
cd "$WORKSPACE_DIR"

PROGRAMS=("btcp_escrow" "btcp_intent" "btcp_route")
declare -A PROGRAM_IDS

for prog in "${PROGRAMS[@]}"; do
    KEY_FILE="target/deploy/${prog}-keypair.json"
    mkdir -p target/deploy

    if [ ! -f "$KEY_FILE" ]; then
        echo "🔑 Generating keypair for $prog..."
        solana-keygen new -o "$KEY_FILE" --no-bip39-passphrase --silent
    fi

    PUBKEY=$(solana-keygen pubkey "$KEY_FILE")
    PROGRAM_IDS[$prog]="$PUBKEY"
    echo "   $prog: $PUBKEY"
done

echo

# ── Update declare_id!() in each program ────────────────────────────────────
echo "📝 Updating declare_id!() in source files..."

update_declare_id() {
    local prog="$1"
    local new_id="$2"
    local file="programs/$prog/src/lib.rs"
    # Replace the placeholder declare_id
    sed -i "s/^declare_id!(\"[^\"]*\");/declare_id!(\"$new_id\");/" "$file"
    echo "   $prog → $new_id"
}

update_declare_id "btcp_escrow" "${PROGRAM_IDS[btcp_escrow]}"
update_declare_id "btcp_intent" "${PROGRAM_IDS[btcp_intent]}"
update_declare_id "btcp_route"  "${PROGRAM_IDS[btcp_route]}"

echo

# ── Build programs ───────────────────────────────────────────────────────────
echo "🔨 Building programs for SBF target..."

if [ "$USE_ANCHOR" = true ]; then
    anchor build --arch sbf
else
    for prog in "${PROGRAMS[@]}"; do
        echo "   Building $prog..."
        cargo-build-sbf --manifest-path "programs/$prog/Cargo.toml" --sbf-out-dir target/deploy
    done
fi

echo "✅ Build complete"
echo

# ── Deploy programs ─────────────────────────────────────────────────────────
echo "🚀 Deploying to $CLUSTER..."

DEPLOYED_IDS=()
for prog in "${PROGRAMS[@]}"; do
    SO_FILE="target/deploy/${prog}.so"
    if [ ! -f "$SO_FILE" ]; then
        # cargo-build-sbf names output differently
        SO_FILE="target/deploy/$(echo $prog | tr '_' '-').so"
    fi

    echo "   Deploying $prog..."
    DEPLOY_OUTPUT=$(solana program deploy "$SO_FILE" \
        --keypair "$KEYPAIR" \
        --program-id "target/deploy/${prog}-keypair.json" \
        --url "$CLUSTER" \
        --commitment finalized 2>&1)

    echo "$DEPLOY_OUTPUT"

    # Extract deployed program ID
    DEPLOYED_ID=$(echo "$DEPLOY_OUTPUT" | grep "Program Id:" | awk '{print $NF}')
    DEPLOYED_IDS+=("$DEPLOYED_ID")
    echo "   → Deployed: $DEPLOYED_ID"
    echo
done

# ── Initialize each program's config account ────────────────────────────────
echo "⚙️  Initializing program config accounts..."

# We need to call the `initialize` instruction on each program.
# This requires a small Rust helper or using Anchor's ts client.
# For now, output the instructions for manual initialization.

echo
echo "═══════════════════════════════════════════════════════════════════"
echo "  📋 NEXT STEPS — Initialize Config Accounts"
echo "═══════════════════════════════════════════════════════════════════"
echo
echo "Each program needs its config account initialized once. This sets"
echo "the owner and relayer to your wallet address."
echo
echo "Using the deployed program IDs:"
for i in "${!PROGRAMS[@]}"; do
    echo "  ${PROGRAMS[$i]}: ${DEPLOYED_IDS[$i]}"
done
echo
echo "To initialize via a TypeScript script (recommended):"
echo "  1. cd $WORKSPACE_DIR"
echo "  2. npm install @solana/web3.js @project-serum/anchor"
echo "  3. Run the init script: node scripts/initialize_programs.ts"
echo
echo "Or via the Rust test helper:"
echo "  cargo test --test initialize_configs -- --nocapture"
echo

# ── Save deployment addresses ───────────────────────────────────────────────
OUTPUT_FILE="target/deploy/deployment_${CLUSTER}_$(date +%Y%m%d_%H%M%S).json"
cat > "$OUTPUT_FILE" << EOF
{
  "cluster": "$CLUSTER",
  "deployer": "$WALLET_ADDR",
  "deployed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "programs": {
    "btcp_escrow": "${DEPLOYED_IDS[0]}",
    "btcp_intent": "${DEPLOYED_IDS[1]}",
    "btcp_route":  "${DEPLOYED_IDS[2]}"
  },
  "keypairs": {
    "btcp_escrow": "target/deploy/btcp_escrow-keypair.json",
    "btcp_intent": "target/deploy/btcp_intent-keypair.json",
    "btcp_route":  "target/deploy/btcp_route-keypair.json"
  },
  "pda_seeds": {
    "config": "config",
    "escrow": "escrow + escrow_id",
    "intent": "intent + intent_hash",
    "route":  "route + route_id",
    "vault":  "vault + escrow_id"
  },
  "note": "After deployment, run initialize on each program to create the config PDA."
}
EOF

echo "💾 Deployment info saved to: $OUTPUT_FILE"
cat "$OUTPUT_FILE" | python3 -m json.tool 2>/dev/null || cat "$OUTPUT_FILE"

echo
echo "✅ Deployment complete!"
