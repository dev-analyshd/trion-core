# TRION — Shared TimescaleDB (GCP-hosted, shared Akashic Index)
# The Akashic Index is the single source of truth — all 9 validators read/write here.
# Hosted on GCP (best networking + Web3 program credits).

# ── TimescaleDB Cloud connection (managed service) ────────────────────────────
# Note: TimescaleDB Cloud is a managed service. We don't provision the DB itself
# via Terraform — instead, we use the TimescaleDB Cloud API or manual setup.
# This file creates the firewall rules + network config to allow all 9 validators
# to connect to the shared TimescaleDB instance.

# ── GCP Cloud SQL (alternative: self-hosted TimescaleDB on a GCP VM) ──────────
# If using self-hosted TimescaleDB instead of TimescaleDB Cloud:
resource "google_compute_instance" "timescaledb" {
  count       = var.timescaledb_cloud == "gcp" ? 1 : 0
  name        = "${var.project_name}-timescaledb"
  machine_type = "n2-highmem-8"  # 8 vCPU, 64GB RAM (for large Akashic Index)
  zone        = "${var.timescaledb_region}-a"
  tags        = ["timescaledb", "trion-db"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2404-lts-amd64"
      size  = 2000  # 2TB for Akashic Index (grows ~1GB/day)
      type  = "pd-ssd"
    }
  }

  network_interface {
    network = google_compute_network.trion_validator_vpc.name
    access_config {}  # public IP for cross-cloud access (WireGuard-secured)
  }

  metadata = {
    Role = "TimescaleDB"
    Description = "Shared Akashic Index — all 9 validators read/write here"
  }

  # The startup script installs PostgreSQL 18 + TimescaleDB 2.30 + loads schema.sql
  metadata_startup_script = <<-EOT
    #!/bin/bash
    set -euo pipefail
    apt-get update -y
    apt-get install -y postgresql postgresql-contrib
    sh -c 'echo "deb https://packagecloud.io/timescale/timescaledb/ubuntu/ $(lsb_release -cs) main" > /etc/apt/sources.list.d/timescaledb.list'
    curl -L https://packagecloud.io/timescale/timescaledb/gpgkey | apt-key add -
    apt-get update -y
    apt-get install -y timescaledb-2-postgresql-18
    timescaledb-tune --yes
    systemctl restart postgresql
    # Create DB + user + load schema
    sudo -u postgres psql -c "CREATE DATABASE tsdb;"
    sudo -u postgres psql -c "CREATE USER tsdbadmin WITH PASSWORD 'CHANGE_ME';"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE tsdb TO tsdbadmin;"
    sudo -u postgres psql -d tsdb -c "CREATE EXTENSION timescaledb;"
    # Download + load schema.sql
    curl -L ${var.trion_repo_url}/raw/${var.trion_branch}/schema.sql -o /tmp/schema.sql
    sudo -u postgres psql -d tsdb -f /tmp/schema.sql
    # Allow external connections (WireGuard mesh only)
    echo "listen_addresses = '*'" >> /etc/postgresql/18/main/postgresql.conf
    echo "host all all 10.66.0.0/24 md5" >> /etc/postgresql/18/main/pg_hba.conf
    systemctl restart postgresql
  EOT
}

# ── Firewall rule: allow TimescaleDB access from WireGuard mesh ───────────────
resource "google_compute_firewall" "timescaledb_access" {
  name    = "${var.project_name}-timescaledb-access"
  network = google_compute_network.trion_validator_vpc.name

  allow {
    protocol = "tcp"
    ports    = ["5432"]
  }
  source_ranges = [var.wireguard_cidr]
  target_tags   = ["timescaledb"]
}
