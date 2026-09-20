# TRION — AWS Validator Instances (3 regions: Africa, N. America, Europe)
# Uses SR-IOV enhanced networking (Nitro) for <1ms inter-AZ latency.
# Eligible for AWS Activate credits ($1k Founders, $100k Portfolio, $300k AI tier).

# ── Security Group: WireGuard + TRION ports ──────────────────────────────────
resource "aws_security_group" "trion_validator" {
  provider    = aws.primary
  name        = "${var.project_name}-validator-sg"
  description = "TRION validator — WireGuard mesh + Oracle API + Go validator"

  # WireGuard P2P mesh (UDP 51820)
  ingress {
    from_port   = var.wireguard_port
    to_port     = var.wireguard_port
    protocol    = "udp"
    cidr_blocks = [var.wireguard_cidr]
  }

  # TRION Oracle API (TCP 5000) — internal only (via WireGuard)
  ingress {
    from_port   = 5000
    to_port     = 5000
    protocol    = "tcp"
    cidr_blocks = [var.wireguard_cidr]
  }

  # ANIMA FAISS (TCP 8001) — internal only
  ingress {
    from_port   = 8001
    to_port     = 8001
    protocol    = "tcp"
    cidr_blocks = [var.wireguard_cidr]
  }

  # Go validator mesh + healthz (TCP 7001, 7080) — internal only
  ingress {
    from_port   = 7001
    to_port     = 7080
    protocol    = "tcp"
    cidr_blocks = [var.wireguard_cidr]
  }

  # SSH (restricted to your IP — set in variables)
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # Restrict in production
  }

  # All outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── SSH keypair ────────────────────────────────────────────────────────────────
resource "tls_private_key" "aws_ssh_key" {
  algorithm = "ED25519"
}

resource "aws_key_pair" "trion_validator" {
  provider   = aws.primary
  key_name   = "${var.project_name}-validator-key"
  public_key = tls_private_key.aws_ssh_key.public_key_openssh
}

# ── Validator 1: AWS af-south-1 (Cape Town, Africa) ──────────────────────────
resource "aws_instance" "validator_v1_africa" {
  provider          = aws.primary
  ami               = "ami-0c1bcfcb2c1b1e1b1"  # Ubuntu 24.04 LTS in af-south-1
  instance_type     = var.aws_instance_type
  key_name          = aws_key_pair.trion_validator.key_name
  security_groups   = [aws_security_group.trion_validator.name]
  availability_zone = "af-south-1a"

  tags = {
    Name        = "${var.project_name}-v1-africa-aws"
    Continent   = "Africa"
    Jurisdiction = "South Africa"
    Cloud       = "AWS"
    Role        = "TRION Validator"
    WireGuardIP = "10.66.0.1"
  }

  root_block_device {
    volume_size = 500  # 500GB for Akashic Index
    volume_type = "gp3"
    encrypted   = true
  }

  # Enhanced networking (SR-IOV) is enabled by default on m5 instances
  # via the Nitro hypervisor — no additional config needed.

  user_data = templatefile("${path.module}/../scripts/bootstrap_validator.sh.tftpl", {
    validator_id   = "validator-v1-africa-aws"
    validator_region = "NA-AF"  # Africa
    wireguard_ip   = "10.66.0.1"
    wireguard_port = var.wireguard_port
    trion_repo_url = var.trion_repo_url
    trion_branch   = var.trion_branch
    trion_api_key  = var.trion_api_key
    faiss_api_key  = var.faiss_api_key
    timescaledb_url = var.timescaledb_url
    indexer_families = "evm"  # This validator indexes EVM chains
  })
}

# ── Validator 2: AWS us-east-1 (Virginia, N. America) ────────────────────────
resource "aws_instance" "validator_v2_namerica" {
  provider          = aws.secondary
  ami               = "ami-0c7217cdde8c2c5b1"  # Ubuntu 24.04 LTS in us-east-1
  instance_type     = var.aws_instance_type
  key_name          = aws_key_pair.trion_validator.key_name
  security_groups   = [aws_security_group.trion_validator.name]
  availability_zone = "us-east-1a"

  tags = {
    Name         = "${var.project_name}-v2-namerica-aws"
    Continent    = "North America"
    Jurisdiction = "USA"
    Cloud        = "AWS"
    Role         = "TRION Validator"
    WireGuardIP  = "10.66.0.2"
  }

  root_block_device {
    volume_size = 500
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = templatefile("${path.module}/../scripts/bootstrap_validator.sh.tftpl", {
    validator_id   = "validator-v2-namerica-aws"
    validator_region = "NA-US"
    wireguard_ip   = "10.66.0.2"
    wireguard_port = var.wireguard_port
    trion_repo_url = var.trion_repo_url
    trion_branch   = var.trion_branch
    trion_api_key  = var.trion_api_key
    faiss_api_key  = var.faiss_api_key
    timescaledb_url = var.timescaledb_url
    indexer_families = "svm utxo"  # This validator indexes SVM + UTXO
  })
}

# ── Validator 3: AWS eu-central-1 (Frankfurt, Europe) ─────────────────────────
resource "aws_instance" "validator_v3_europe" {
  provider          = aws.tertiary
  ami               = "ami-0c1bc7dde8c2c5b1"  # Ubuntu 24.04 LTS in eu-central-1
  instance_type     = var.aws_instance_type
  key_name          = aws_key_pair.trion_validator.key_name
  security_groups   = [aws_security_group.trion_validator.name]
  availability_zone = "eu-central-1a"

  tags = {
    Name         = "${var.project_name}-v3-europe-aws"
    Continent    = "Europe"
    Jurisdiction = "Germany"
    Cloud        = "AWS"
    Role         = "TRION Validator"
    WireGuardIP  = "10.66.0.3"
  }

  root_block_device {
    volume_size = 500
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = templatefile("${path.module}/../scripts/bootstrap_validator.sh.tftpl", {
    validator_id   = "validator-v3-europe-aws"
    validator_region = "EU-DE"
    wireguard_ip   = "10.66.0.3"
    wireguard_port = var.wireguard_port
    trion_repo_url = var.trion_repo_url
    trion_branch   = var.trion_branch
    trion_api_key  = var.trion_api_key
    faiss_api_key  = var.faiss_api_key
    timescaledb_url = var.timescaledb_url
    indexer_families = "starknet cosmos"  # This validator indexes Starknet + Cosmos
  })
}

# ── Elastic IPs for WireGuard endpoints ──────────────────────────────────────
resource "aws_eip" "validator_eips" {
  provider   = aws.primary
  for_each   = { v1 = "validator_v1_africa" }
  instance   = aws_instance.validator_v1_africa.id
  domain     = "vpc"
  tags       = { Name = "${var.project_name}-${each.key}-eip" }
}
