# TRION Multi-Cloud Validator Grid — Main Orchestrator
# =======================================================
# Provisions 9 TRION validators across AWS + GCP + Azure simultaneously,
# connected by a P2P WireGuard mesh, sharing a TimescaleDB Akashic Index.
#
# Whitepaper compliance:
# - 6 continents (Africa ×3, N. America ×1, Europe ×2, Asia ×2, S. America ×1)
# - 7 jurisdictions (no single >30%)
# - 3 cloud vendors (diversity-weighted by construction)
# - DW-BFT quorum needs ≥2/3 of 9 = 6 validators to sign

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
  # Backend: store state in GCS (free with GCP credits)
  backend "gcs" {
    bucket = "trion-terraform-state"
    prefix = "multi-cloud-validator-grid"
  }
}

# ── Provider configurations ──────────────────────────────────────────────────
# Each provider authenticates via its cloud's CLI (aws-cli, gcloud, az-cli)

provider "aws" {
  region = var.aws_region_primary
  alias  = "primary"
}

provider "aws" {
  region = var.aws_region_secondary
  alias  = "secondary"
}

provider "aws" {
  region = var.aws_region_tertiary
  alias  = "tertiary"
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region_primary
}

provider "azurerm" {
  features {}
}

# ── WireGuard keypair generation ──────────────────────────────────────────────
# Generate a WireGuard private key for each validator
resource "tls_private_key" "wireguard_keys" {
  for_each = local.validator_matrix
  algorithm = "ED25519"
}

# ── Generate WireGuard public keys ────────────────────────────────────────────
locals {
  wireguard_public_keys = {
    for k, v in local.validator_matrix : k => tls_private_key.wireguard_keys[k].public_key_openssh
  }
}

# ── WireGuard mesh config generation ──────────────────────────────────────────
resource "local_file" "wireguard_mesh_config" {
  for_each = local.validator_matrix
  filename = "${path.module}/../wireguard/generated/${each.key}.conf"
  content  = templatefile("${path.module}/../wireguard/peer_template.conf.tftpl", {
    validator_name    = each.key
    private_key       = tls_private_key.wireguard_keys[each.key].private_key_pem
    wireguard_ip      = each.value.wireguard_ip
    wireguard_cidr    = var.wireguard_cidr
    wireguard_port    = var.wireguard_port
    peers = [
      for k, v in local.validator_matrix : {
        name        = k
        public_key  = tls_private_key.wireguard_keys[k].public_key_openssh
        endpoint    = ""  # filled in after instances are created
        allowed_ips = "${v.wireguard_ip}/32"
      }
      if k != each.key
    ]
  })
}

# ── Module calls ──────────────────────────────────────────────────────────────
# Each cloud's validators are provisioned in their respective .tf files

# Output the mesh topology
output "validator_mesh_topology" {
  description = "Complete validator mesh topology (9 validators, 3 clouds, 6 continents)"
  value = {
    for k, v in local.validator_matrix : k => {
      cloud       = v.cloud
      region      = v.region
      continent   = v.continent
      jurisdiction = v.jurisdiction
      wireguard_ip = v.wireguard_ip
    }
  }
}

output "wireguard_port" {
  description = "WireGuard UDP port for P2P mesh"
  value       = var.wireguard_port
}

output "total_validators" {
  description = "Total validator count (must be ≥4 for BFT, ≥9 recommended)"
  value       = var.aws_instance_count + var.gcp_instance_count + var.azure_instance_count
}
