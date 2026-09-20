# TRION — Azure Validator Instances (3 regions: Africa, Europe, Asia)
# Uses Accelerated Networking (SR-IOV) for low-latency consensus.
# Eligible for Microsoft for Startups Founders Hub credits ($200 → $150k).

# ── Resource Group ────────────────────────────────────────────────────────────
resource "azurerm_resource_group" "trion_validators" {
  name     = "${var.project_name}-validators-rg"
  location = var.azure_region_primary
}

# ── VNet + Subnet ──────────────────────────────────────────────────────────────
resource "azurerm_virtual_network" "trion_vnet" {
  name                = "${var.project_name}-vnet"
  location            = azurerm_resource_group.trion_validators.location
  resource_group_name = azurerm_resource_group.trion_validators.name
  address_space       = ["10.0.0.0/16"]
}

resource "azurerm_subnet" "trion_subnet" {
  name                 = "${var.project_name}-subnet"
  resource_group_name  = azurerm_resource_group.trion_validators.name
  virtual_network_name = azurerm_virtual_network.trion_vnet.name
  address_prefixes     = ["10.0.1.0/24"]
}

# ── NSG: WireGuard + TRION ports ──────────────────────────────────────────────
resource "azurerm_network_security_group" "trion_validator_nsg" {
  name                = "${var.project_name}-validator-nsg"
  location            = azurerm_resource_group.trion_validators.location
  resource_group_name = azurerm_resource_group.trion_validators.name

  # WireGuard (UDP 51820)
  security_rule {
    name                       = "WireGuard"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Udp"
    source_port_range          = "*"
    destination_port_range     = var.wireguard_port
    source_address_prefix      = var.wireguard_cidr
    destination_address_prefix = "*"
  }

  # TRION internal ports
  security_rule {
    name                       = "TRION-Internal"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = ["5000", "8001", "7001", "7080"]
    source_address_prefix      = var.wireguard_cidr
    destination_address_prefix = "*"
  }

  # SSH
  security_rule {
    name                       = "SSH"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

# ── Public IPs for WireGuard endpoints ─────────────────────────────────────────
resource "azurerm_public_ip" "validator_pips" {
  for_each            = { v7 = "africa", v8 = "europe", v9 = "asia" }
  name                = "${var.project_name}-${each.value}-pip"
  location            = azurerm_resource_group.trion_validators.location
  resource_group_name = azurerm_resource_group.trion_validators.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

# ── Validator 7: Azure southafricanorth (Johannesburg, Africa) ────────────────
resource "azurerm_network_interface" "validator_v7_nic" {
  name                          = "${var.project_name}-v7-africa-nic"
  location                      = azurerm_resource_group.trion_validators.location
  resource_group_name           = azurerm_resource_group.trion_validators.name
  enable_accelerated_networking = true  # SR-IOV for low-latency consensus

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.trion_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.validator_pips["v7"].id
  }
}

resource "azurerm_linux_virtual_machine" "validator_v7_africa" {
  name                  = "${var.project_name}-v7-africa-azure"
  location              = azurerm_resource_group.trion_validators.location
  resource_group_name   = azurerm_resource_group.trion_validators.name
  size                  = var.azure_vm_size
  admin_username        = "trion"
  network_interface_ids = [azurerm_network_interface.validator_v7_nic.id]

  admin_ssh_key {
    username   = "trion"
    public_key = file("~/.ssh/trion_validator.pub")  # Generate beforehand
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
    disk_size_gb         = 500
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "24_04-lts-gen2"
    version   = "latest"
  }

  tags = {
    Continent    = "Africa"
    Jurisdiction = "South Africa"
    Cloud        = "Azure"
    WireGuardIP  = "10.66.0.7"
  }

  custom_data = base64encode(templatefile("${path.module}/../scripts/bootstrap_validator.sh.tftpl", {
    validator_id    = "validator-v7-africa-azure"
    validator_region = "NA-AF"
    wireguard_ip    = "10.66.0.7"
    wireguard_port  = var.wireguard_port
    trion_repo_url  = var.trion_repo_url
    trion_branch    = var.trion_branch
    trion_api_key   = var.trion_api_key
    faiss_api_key   = var.faiss_api_key
    timescaledb_url = var.timescaledb_url
    indexer_families = "pvm tron"
  }))
}
