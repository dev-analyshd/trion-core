# TRION — GCP Validator Instances (3 regions: Africa, Asia, S. America)
# Uses Andromeda networking with Tier_1 for low-latency consensus.
# Eligible for Google Cloud Web3 program credits ($2k Start, $200k Scale).

# ── VPC + Firewall ────────────────────────────────────────────────────────────
resource "google_compute_network" "trion_validator_vpc" {
  name                    = "${var.project_name}-validator-vpc"
  auto_create_subnetworks = true
}

resource "google_compute_firewall" "trion_validator_fw" {
  name    = "${var.project_name}-validator-firewall"
  network = google_compute_network.trion_validator_vpc.name

  # WireGuard P2P mesh (UDP 51820)
  allow {
    protocol = "udp"
    ports    = [var.wireguard_port]
  }
  source_ranges = [var.wireguard_cidr]

  # TRION internal ports (Oracle 5000, FAISS 8001, Go 7001-7080)
  allow {
    protocol = "tcp"
    ports    = ["5000", "8001", "7001", "7080"]
  }
  source_ranges = [var.wireguard_cidr]

  # SSH
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  source_ranges = ["0.0.0.0/0"]
}

# ── Validator 4: GCP africa-south1 (Johannesburg, Africa) ─────────────────────
resource "google_compute_instance" "validator_v4_africa" {
  name         = "${var.project_name}-v4-africa-gcp"
  machine_type = var.gcp_machine_type
  zone         = "${var.gcp_region_primary}-a"
  tags         = ["trion-validator", "africa", "gcp"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2404-lts-amd64"
      size  = 500
      type  = "pd-ssd"
    }
  }

  # SR-IOV / Andromeda networking is enabled by default on n2 instances
  network_interface {
    network = google_compute_network.trion_validator_vpc.name
    access_config {}  # ephemeral public IP (for WireGuard endpoint)
  }

  metadata = {
    Continent   = "Africa"
    Jurisdiction = "South Africa"
    Cloud       = "GCP"
    WireGuardIP = "10.66.0.4"
  }

  metadata_startup_script = templatefile("${path.module}/../scripts/bootstrap_validator.sh.tftpl", {
    validator_id   = "validator-v4-africa-gcp"
    validator_region = "NA-AF"
    wireguard_ip   = "10.66.0.4"
    wireguard_port = var.wireguard_port
    trion_repo_url = var.trion_repo_url
    trion_branch   = var.trion_branch
    trion_api_key  = var.trion_api_key
    faiss_api_key  = var.faiss_api_key
    timescaledb_url = var.timescaledb_url
    indexer_families = "near ton"
  })
}

# ── Validator 5: GCP asia-northeast1 (Tokyo, Asia) ──────────────────────────
resource "google_compute_instance" "validator_v5_asia" {
  name         = "${var.project_name}-v5-asia-gcp"
  machine_type = var.gcp_machine_type
  zone         = "${var.gcp_region_secondary}-a"
  tags         = ["trion-validator", "asia", "gcp"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2404-lts-amd64"
      size  = 500
      type  = "pd-ssd"
    }
  }

  network_interface {
    network = google_compute_network.trion_validator_vpc.name
    access_config {}
  }

  metadata = {
    Continent   = "Asia"
    Jurisdiction = "Japan"
    Cloud       = "GCP"
    WireGuardIP = "10.66.0.5"
  }

  metadata_startup_script = templatefile("${path.module}/../scripts/bootstrap_validator.sh.tftpl", {
    validator_id   = "validator-v5-asia-gcp"
    validator_region = "AP-JP"
    wireguard_ip   = "10.66.0.5"
    wireguard_port = var.wireguard_port
    trion_repo_url = var.trion_repo_url
    trion_branch   = var.trion_branch
    trion_api_key  = var.trion_api_key
    faiss_api_key  = var.faiss_api_key
    timescaledb_url = var.timescaledb_url
    indexer_families = "sui aptos"
  })
}

# ── Validator 6: GCP southamerica-east1 (São Paulo, S. America) ──────────────
resource "google_compute_instance" "validator_v6_samerica" {
  name         = "${var.project_name}-v6-samerica-gcp"
  machine_type = var.gcp_machine_type
  zone         = "${var.gcp_region_tertiary}-a"
  tags         = ["trion-validator", "south-america", "gcp"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2404-lts-amd64"
      size  = 500
      type  = "pd-ssd"
    }
  }

  network_interface {
    network = google_compute_network.trion_validator_vpc.name
    access_config {}
  }

  metadata = {
    Continent   = "South America"
    Jurisdiction = "Brazil"
    Cloud       = "GCP"
    WireGuardIP = "10.66.0.6"
  }

  metadata_startup_script = templatefile("${path.module}/../scripts/bootstrap_validator.sh.tftpl", {
    validator_id   = "validator-v6-samerica-gcp"
    validator_region = "SA-BR"
    wireguard_ip   = "10.66.0.6"
    wireguard_port = var.wireguard_port
    trion_repo_url = var.trion_repo_url
    trion_branch   = var.trion_branch
    trion_api_key  = var.trion_api_key
    faiss_api_key  = var.faiss_api_key
    timescaledb_url = var.timescaledb_url
    indexer_families = "stacks stellar"
  })
}
