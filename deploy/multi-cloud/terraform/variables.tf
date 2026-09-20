# TRION Multi-Cloud Validator Grid — Variables

# ── General ──────────────────────────────────────────────────────────────────
variable "project_name" {
  description = "Project prefix for all resources"
  type        = string
  default     = "trion-validator-grid"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "mainnet"
}

# ── AWS Configuration ────────────────────────────────────────────────────────
variable "aws_region_primary" {
  description = "AWS primary region (Africa)"
  type        = string
  default     = "af-south-1"  # Cape Town
}

variable "aws_region_secondary" {
  description = "AWS secondary region (N. America)"
  type        = string
  default     = "us-east-1"   # Virginia
}

variable "aws_region_tertiary" {
  description = "AWS tertiary region (Europe)"
  type        = string
  default     = "eu-central-1" # Frankfurt
}

variable "aws_instance_type" {
  description = "EC2 instance type for validators (m5.2xlarge = 8 vCPU, 32GB, 25 Gbps)"
  type        = string
  default     = "m5.2xlarge"  # $0.384/hr on-demand, covered by credits
}

variable "aws_instance_count" {
  description = "Number of AWS validators"
  type        = number
  default     = 3
}

# ── GCP Configuration ────────────────────────────────────────────────────────
variable "gcp_project_id" {
  description = "GCP project ID"
  type        = string
  default     = "trion-validator-grid"
}

variable "gcp_region_primary" {
  description = "GCP primary region (Africa)"
  type        = string
  default     = "africa-south1"  # Johannesburg
}

variable "gcp_region_secondary" {
  description = "GCP secondary region (Asia)"
  type        = string
  default     = "asia-northeast1"  # Tokyo
}

variable "gcp_region_tertiary" {
  description = "GCP tertiary region (S. America)"
  type        = string
  default     = "southamerica-east1"  # São Paulo
}

variable "gcp_machine_type" {
  description = "GCP machine type (n2-standard-8 = 8 vCPU, 32GB, 16 Gbps)"
  type        = string
  default     = "n2-standard-8"
}

variable "gcp_instance_count" {
  description = "Number of GCP validators"
  type        = number
  default     = 3
}

# ── Azure Configuration ──────────────────────────────────────────────────────
variable "azure_region_primary" {
  description = "Azure primary region (Africa)"
  type        = string
  default     = "southafricanorth"  # Johannesburg
}

variable "azure_region_secondary" {
  description = "Azure secondary region (Europe)"
  type        = string
  default     = "northeurope"  # Dublin
}

variable "azure_region_tertiary" {
  description = "Azure tertiary region (Asia)"
  type        = string
  default     = "southeastasia"  # Singapore
}

variable "azure_vm_size" {
  description = "Azure VM size (Standard_D8s_v5 = 8 vCPU, 32GB, 12.5 Gbps)"
  type        = string
  default     = "Standard_D8s_v5"
}

variable "azure_instance_count" {
  description = "Number of Azure validators"
  type        = number
  default     = 3
}

# ── TimescaleDB Configuration ────────────────────────────────────────────────
variable "timescaledb_cloud" {
  description = "Which cloud hosts the shared TimescaleDB (GCP recommended — best networking)"
  type        = string
  default     = "gcp"
}

variable "timescaledb_region" {
  description = "TimescaleDB region (should match the primary indexer region)"
  type        = string
  default     = "africa-south1"
}

variable "timescaledb_tier" {
  description = "TimescaleDB Cloud tier (essential-1-7-4 = 8 vCPU, 32GB, 500GB)"
  type        = string
  default     = "essential-1-7-4"
}

# ── WireGuard Mesh ───────────────────────────────────────────────────────────
variable "wireguard_port" {
  description = "WireGuard UDP port (same on all validators)"
  type        = number
  default     = 51820
}

variable "wireguard_cidr" {
  description = "WireGuard mesh network CIDR"
  type        = string
  default     = "10.66.0.0/24"  # 254 validators max
}

# ── TRION Configuration ──────────────────────────────────────────────────────
variable "trion_repo_url" {
  description = "TRION Protocol repository URL"
  type        = string
  default     = "https://github.com/dev-analyshd/trion-core.git"
}

variable "trion_branch" {
  description = "TRION repository branch"
  type        = string
  default     = "main"
}

variable "trion_api_key" {
  description = "TRION Oracle API key (generate a unique 32-byte hex key)"
  type        = string
  sensitive   = true
  default     = ""  # Set via TF_VAR_trion_api_key
}

variable "faiss_api_key" {
  description = "ANIMA FAISS API key (generate a unique 32-byte hex key)"
  type        = string
  sensitive   = true
  default     = ""  # Set via TF_VAR_faiss_api_key
}

variable "relayer_private_key" {
  description = "EVM private key for relayer (software keys, no HSM)"
  type        = string
  sensitive   = true
  default     = ""  # Set via TF_VAR_relayer_private_key
}

variable "timescaledb_url" {
  description = "Shared TimescaleDB connection URL"
  type        = string
  sensitive   = true
  default     = ""  # Set via TF_VAR_timescaledb_url
}

# ── Validator Regions Matrix ──────────────────────────────────────────────────
locals {
  validator_matrix = {
    # 9 validators across 3 clouds, 6 continents, 7 jurisdictions
    aws_v1 = {
      cloud = "aws", region = var.aws_region_primary, continent = "Africa",
      jurisdiction = "South Africa", wireguard_ip = "10.66.0.1"
    }
    aws_v2 = {
      cloud = "aws", region = var.aws_region_secondary, continent = "North America",
      jurisdiction = "USA", wireguard_ip = "10.66.0.2"
    }
    aws_v3 = {
      cloud = "aws", region = var.aws_region_tertiary, continent = "Europe",
      jurisdiction = "Germany", wireguard_ip = "10.66.0.3"
    }
    gcp_v4 = {
      cloud = "gcp", region = var.gcp_region_primary, continent = "Africa",
      jurisdiction = "South Africa", wireguard_ip = "10.66.0.4"
    }
    gcp_v5 = {
      cloud = "gcp", region = var.gcp_region_secondary, continent = "Asia",
      jurisdiction = "Japan", wireguard_ip = "10.66.0.5"
    }
    gcp_v6 = {
      cloud = "gcp", region = var.gcp_region_tertiary, continent = "South America",
      jurisdiction = "Brazil", wireguard_ip = "10.66.0.6"
    }
    azure_v7 = {
      cloud = "azure", region = var.azure_region_primary, continent = "Africa",
      jurisdiction = "South Africa", wireguard_ip = "10.66.0.7"
    }
    azure_v8 = {
      cloud = "azure", region = var.azure_region_secondary, continent = "Europe",
      jurisdiction = "Ireland", wireguard_ip = "10.66.0.8"
    }
    azure_v9 = {
      cloud = "azure", region = var.azure_region_tertiary, continent = "Asia",
      jurisdiction = "Singapore", wireguard_ip = "10.66.0.9"
    }
  }
}
