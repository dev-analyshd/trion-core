export const BEO_ATTESTATION_ABI = [
  {
    "type": "impl",
    "name": "BEOAttestationImpl",
    "interface_name": "trion_oracle::IBEOAttestation"
  },
  {
    "type": "enum",
    "name": "core::bool",
    "variants": [
      {
        "name": "False",
        "type": "()"
      },
      {
        "name": "True",
        "type": "()"
      }
    ]
  },
  {
    "type": "struct",
    "name": "trion_oracle::BEOIdentity",
    "members": [
      {
        "name": "beo_id",
        "type": "core::felt252"
      },
      {
        "name": "tier",
        "type": "core::integer::u8"
      },
      {
        "name": "genesis_confidence_bp",
        "type": "core::integer::u64"
      },
      {
        "name": "attested_at",
        "type": "core::integer::u64"
      },
      {
        "name": "active",
        "type": "core::bool"
      }
    ]
  },
  {
    "type": "interface",
    "name": "trion_oracle::IBEOAttestation",
    "items": [
      {
        "type": "function",
        "name": "attest",
        "inputs": [
          {
            "name": "wallet",
            "type": "core::starknet::contract_address::ContractAddress"
          },
          {
            "name": "beo_id",
            "type": "core::felt252"
          },
          {
            "name": "tier",
            "type": "core::integer::u8"
          },
          {
            "name": "genesis_confidence_bp",
            "type": "core::integer::u64"
          }
        ],
        "outputs": [],
        "state_mutability": "external"
      },
      {
        "type": "function",
        "name": "revoke",
        "inputs": [
          {
            "name": "wallet",
            "type": "core::starknet::contract_address::ContractAddress"
          }
        ],
        "outputs": [],
        "state_mutability": "external"
      },
      {
        "type": "function",
        "name": "get_beo",
        "inputs": [
          {
            "name": "wallet",
            "type": "core::starknet::contract_address::ContractAddress"
          }
        ],
        "outputs": [
          {
            "type": "trion_oracle::BEOIdentity"
          }
        ],
        "state_mutability": "view"
      },
      {
        "type": "function",
        "name": "get_wallet",
        "inputs": [
          {
            "name": "beo_id",
            "type": "core::felt252"
          }
        ],
        "outputs": [
          {
            "type": "core::starknet::contract_address::ContractAddress"
          }
        ],
        "state_mutability": "view"
      },
      {
        "type": "function",
        "name": "is_attested",
        "inputs": [
          {
            "name": "wallet",
            "type": "core::starknet::contract_address::ContractAddress"
          }
        ],
        "outputs": [
          {
            "type": "core::bool"
          }
        ],
        "state_mutability": "view"
      },
      {
        "type": "function",
        "name": "get_attester",
        "inputs": [],
        "outputs": [
          {
            "type": "core::starknet::contract_address::ContractAddress"
          }
        ],
        "state_mutability": "view"
      },
      {
        "type": "function",
        "name": "set_attester",
        "inputs": [
          {
            "name": "new_attester",
            "type": "core::starknet::contract_address::ContractAddress"
          }
        ],
        "outputs": [],
        "state_mutability": "external"
      },
      {
        "type": "function",
        "name": "total_attestations",
        "inputs": [],
        "outputs": [
          {
            "type": "core::integer::u64"
          }
        ],
        "state_mutability": "view"
      }
    ]
  },
  {
    "type": "constructor",
    "name": "constructor",
    "inputs": [
      {
        "name": "attester",
        "type": "core::starknet::contract_address::ContractAddress"
      }
    ]
  },
  {
    "type": "event",
    "name": "trion_oracle::BEOAttestation::Attested",
    "kind": "struct",
    "members": [
      {
        "name": "wallet",
        "type": "core::starknet::contract_address::ContractAddress",
        "kind": "key"
      },
      {
        "name": "beo_id",
        "type": "core::felt252",
        "kind": "key"
      },
      {
        "name": "tier",
        "type": "core::integer::u8",
        "kind": "data"
      },
      {
        "name": "genesis_confidence_bp",
        "type": "core::integer::u64",
        "kind": "data"
      },
      {
        "name": "timestamp",
        "type": "core::integer::u64",
        "kind": "data"
      }
    ]
  },
  {
    "type": "event",
    "name": "trion_oracle::BEOAttestation::Revoked",
    "kind": "struct",
    "members": [
      {
        "name": "wallet",
        "type": "core::starknet::contract_address::ContractAddress",
        "kind": "key"
      },
      {
        "name": "beo_id",
        "type": "core::felt252",
        "kind": "data"
      },
      {
        "name": "timestamp",
        "type": "core::integer::u64",
        "kind": "data"
      }
    ]
  },
  {
    "type": "event",
    "name": "trion_oracle::BEOAttestation::AttesterChanged",
    "kind": "struct",
    "members": [
      {
        "name": "old_attester",
        "type": "core::starknet::contract_address::ContractAddress",
        "kind": "data"
      },
      {
        "name": "new_attester",
        "type": "core::starknet::contract_address::ContractAddress",
        "kind": "data"
      }
    ]
  },
  {
    "type": "event",
    "name": "trion_oracle::BEOAttestation::Event",
    "kind": "enum",
    "variants": [
      {
        "name": "Attested",
        "type": "trion_oracle::BEOAttestation::Attested",
        "kind": "nested"
      },
      {
        "name": "Revoked",
        "type": "trion_oracle::BEOAttestation::Revoked",
        "kind": "nested"
      },
      {
        "name": "AttesterChanged",
        "type": "trion_oracle::BEOAttestation::AttesterChanged",
        "kind": "nested"
      }
    ]
  }
] as const;
