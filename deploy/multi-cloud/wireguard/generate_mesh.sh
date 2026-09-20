#!/usr/bin/env bash
# =============================================================================
# TRION WireGuard Mesh Generator
# =============================================================================
# Generates a full P2P WireGuard mesh configuration for all 9 validators.
# Each validator peers directly with every other validator — no centralized
# VPN gateway, no single point of failure.
#
# Usage:
#   ./generate_mesh.sh  # generates configs in generated/*.conf
#   ./generate_mesh.sh --verify  # tests mesh connectivity
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GENERATED_DIR="${SCRIPT_DIR}/generated"
mkdir -p "${GENERATED_DIR}"

# ── 9 validators, each gets a unique WireGuard keypair + IP ────────────────────
VALIDATORS=(
  "validator-v1-africa-aws:10.66.0.1"
  "validator-v2-namerica-aws:10.66.0.2"
  "validator-v3-europe-aws:10.66.0.3"
  "validator-v4-africa-gcp:10.66.0.4"
  "validator-v5-asia-gcp:10.66.0.5"
  "validator-v6-samerica-gcp:10.66.0.6"
  "validator-v7-africa-azure:10.66.0.7"
  "validator-v8-europe-azure:10.66.0.8"
  "validator-v9-asia-azure:10.66.0.9"
)

WG_PORT="${WG_PORT:-51820}"
WG_CIDR="${WG_CIDR:-10.66.0.0/24}"

echo "═══════════════════════════════════════════════════════════════════"
echo "  TRION WireGuard Mesh Generator — 9 validators, P2P topology"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# ── Check WireGuard is installed ────────────────────────────────────────────────
if ! command -v wg &>/dev/null; then
  echo "❌ WireGuard not installed. Install with:"
  echo "   apt install wireguard wireguard-tools  # Debian/Ubuntu"
  echo "   brew install wireguard-tools            # macOS"
  exit 1
fi
echo "✅ WireGuard installed: $(wg --version)"

# ── Generate keypairs for each validator ────────────────────────────────────────
echo ""
echo "── Generating WireGuard keypairs ──"
declare -A PRIVATE_KEYS
declare -A PUBLIC_KEYS
declare -A WG_IPS

for entry in "${VALIDATORS[@]}"; do
  name="${entry%%:*}"
  ip="${entry##*:}"
  WG_IPS["$name"]="$ip"

  # Generate keypair
  private_key=$(wg genkey)
  public_key=$(echo "$private_key" | wg pubkey)

  PRIVATE_KEYS["$name"]="$private_key"
  PUBLIC_KEYS["$name"]="$public_key"

  echo "  ✅ $name: $ip (pubkey: ${public_key:0:16}...)"
done

# ── Generate config for each validator ─────────────────────────────────────────
echo ""
echo "── Generating per-validator WireGuard configs ──"
for entry in "${VALIDATORS[@]}"; do
  name="${entry%%:*}"
  ip="${entry##*:}"

  config_file="${GENERATED_DIR}/${name}.conf"

  cat > "$config_file" << EOF
# =============================================================================
# TRION Validator WireGuard Configuration — ${name}
# =============================================================================
# P2P mesh: each validator peers directly with every other validator.
# No centralized VPN gateway — if any single validator goes down, the mesh
# self-heals (remaining validators continue peering).
#
# Install on the validator:
#   sudo cp ${name}.conf /etc/wireguard/wg0.conf
#   sudo wg-quick up wg0
#   sudo systemctl enable wg-quick@wg0
# =============================================================================

[Interface]
PrivateKey = ${PRIVATE_KEYS[$name]}
Address = ${ip}/24
ListenPort = ${WG_PORT}
# PersistentKeepalive ensures the peer relationship survives NAT timeouts
# (25s = standard for NAT traversal; 0 = disable if both peers have public IPs)
Table = off  # Don't override default routing — WireGuard is for mesh traffic only

# ── Peer validators (8 peers — full mesh) ───────────────────────────────────
EOF

  # Add all other validators as peers
  for peer_entry in "${VALIDATORS[@]}"; do
    peer_name="${peer_entry%%:*}"
    peer_ip="${peer_entry##*:}"

    if [ "$peer_name" = "$name" ]; then
      continue
    fi

    # The endpoint IP is filled in after Terraform creates the instances.
    # For now, use a placeholder — the deploy_all.sh script will patch these
    # with the real public IPs from Terraform outputs.
    cat >> "$config_file" << EOF

# Peer: ${peer_name} (${peer_ip})
[Peer]
PublicKey = ${PUBLIC_KEYS[$peer_name]}
AllowedIPs = ${peer_ip}/32
# Endpoint will be patched by deploy_all.sh after instance creation
# Endpoint = <PUBLIC_IP>:${WG_PORT}
PersistentKeepalive = 25
EOF
  done

  chmod 600 "$config_file"
  echo "  ✅ Generated: ${config_file}"
done

# ── Generate mesh topology summary ────────────────────────────────────────────
echo ""
echo "── Mesh Topology Summary ──"
topology_file="${GENERATED_DIR}/mesh_topology.txt"
cat > "$topology_file" << 'EOF'
TRION Validator WireGuard Mesh — 9-node P2P Topology
=====================================================

Mesh: 10.66.0.0/24 (254 validator capacity)
Port: UDP 51820

  V1 AWS Africa  (10.66.0.1) ──────────────── V2 AWS N.America (10.66.0.2)
       │                                        │
       │                                        │
  V4 GCP Africa  (10.66.0.4)              V3 AWS Europe (10.66.0.3)
       │                                        │
       │                                        │
  V7 Azure Africa (10.66.0.7)           V8 Azure Europe (10.66.0.8)
       │                                        │
       │                                        │
  V5 GCP Asia (10.66.0.5)              V6 GCP S.America (10.66.0.6)
       │                                        │
       └────────────────────────────────────────┘
                           │
                    V9 Azure Asia (10.66.0.9)

Diversity: 3 clouds × 3 regions = 9 validators across 6 continents
Quorum: 2/3 of 9 = 6 validators needed for certificate signing
Failover: mesh survives loss of any 3 validators (33% Byzantine tolerance)
EOF
echo "$topology_file" > /dev/null  # touch
echo "  ✅ Topology: ${topology_file}"

# ── Verify mode ────────────────────────────────────────────────────────────────
if [ "${1:-}" = "--verify" ]; then
  echo ""
  echo "── Mesh Connectivity Test ──"
  for entry in "${VALIDATORS[@]}"; do
    name="${entry%%:*}"
    ip="${entry##*:}"
    echo -n "  ${name} (${ip}): "
    if ping -c 1 -W 2 "$ip" &>/dev/null; then
      echo "✅ reachable"
    else
      echo "❌ unreachable (WireGuard may not be up yet)"
    fi
  done
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "  ✅ WireGuard mesh configs generated in ${GENERATED_DIR}/"
echo "  Next: run deploy_all.sh to create instances + patch endpoints"
echo "═══════════════════════════════════════════════════════════════════"
