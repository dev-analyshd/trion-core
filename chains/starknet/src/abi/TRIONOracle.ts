export const TRION_ORACLE_ABI = [
  {
    "type": "impl",
    "name": "TRIONOracleImpl",
    "interface_name": "trion_oracle::ITRIONOracle"
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
    "name": "trion_oracle::BEOScore",
    "members": [
      {
        "name": "anima_score",
        "type": "core::integer::u64"
      },
      {
        "name": "genesis_confidence",
        "type": "core::integer::u64"
      },
      {
        "name": "trajectory_alert",
        "type": "core::integer::u8"
      },
      {
        "name": "archetype_id",
        "type": "core::integer::u8"
      },
      {
        "name": "akashic_depth",
        "type": "core::integer::u64"
      },
      {
        "name": "is_resurrection",
        "type": "core::bool"
      },
      {
        "name": "dormancy_type",
        "type": "core::felt252"
      },
      {
        "name": "last_updated",
        "type": "core::integer::u64"
      },
      {
        "name": "update_count",
        "type": "core::integer::u64"
      }
    ]
  },
  {
    "type": "interface",
    "name": "trion_oracle::ITRIONOracle",
    "items": [
      {
        "type": "function",
        "name": "update_score",
        "inputs": [
          {
            "name": "beo_id",
            "type": "core::felt252"
          },
          {
            "name": "anima_score",
            "type": "core::integer::u64"
          },
          {
            "name": "genesis_confidence",
            "type": "core::integer::u64"
          },
          {
            "name": "trajectory_alert",
            "type": "core::integer::u8"
          },
          {
            "name": "archetype_id",
            "type": "core::integer::u8"
          },
          {
            "name": "akashic_depth",
            "type": "core::integer::u64"
          },
          {
            "name": "is_resurrection",
            "type": "core::bool"
          },
          {
            "name": "dormancy_type",
            "type": "core::felt252"
          }
        ],
        "outputs": [],
        "state_mutability": "external"
      },
      {
        "type": "function",
        "name": "get_score",
        "inputs": [
          {
            "name": "beo_id",
            "type": "core::felt252"
          }
        ],
        "outputs": [
          {
            "type": "trion_oracle::BEOScore"
          }
        ],
        "state_mutability": "view"
      },
      {
        "type": "function",
        "name": "get_owner",
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
        "name": "transfer_ownership",
        "inputs": [
          {
            "name": "new_owner",
            "type": "core::starknet::contract_address::ContractAddress"
          }
        ],
        "outputs": [],
        "state_mutability": "external"
      },
      {
        "type": "function",
        "name": "get_score_count",
        "inputs": [],
        "outputs": [
          {
            "type": "core::integer::u64"
          }
        ],
        "state_mutability": "view"
      },
      {
        "type": "function",
        "name": "get_last_updated",
        "inputs": [
          {
            "name": "beo_id",
            "type": "core::felt252"
          }
        ],
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
        "name": "owner",
        "type": "core::starknet::contract_address::ContractAddress"
      }
    ]
  },
  {
    "type": "event",
    "name": "trion_oracle::TRIONOracle::ScoreUpdated",
    "kind": "struct",
    "members": [
      {
        "name": "beo_id",
        "type": "core::felt252",
        "kind": "key"
      },
      {
        "name": "anima_score",
        "type": "core::integer::u64",
        "kind": "data"
      },
      {
        "name": "trajectory_alert",
        "type": "core::integer::u8",
        "kind": "data"
      },
      {
        "name": "archetype_id",
        "type": "core::integer::u8",
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
    "name": "trion_oracle::TRIONOracle::OwnershipTransferred",
    "kind": "struct",
    "members": [
      {
        "name": "previous_owner",
        "type": "core::starknet::contract_address::ContractAddress",
        "kind": "data"
      },
      {
        "name": "new_owner",
        "type": "core::starknet::contract_address::ContractAddress",
        "kind": "data"
      }
    ]
  },
  {
    "type": "event",
    "name": "trion_oracle::TRIONOracle::Event",
    "kind": "enum",
    "variants": [
      {
        "name": "ScoreUpdated",
        "type": "trion_oracle::TRIONOracle::ScoreUpdated",
        "kind": "nested"
      },
      {
        "name": "OwnershipTransferred",
        "type": "trion_oracle::TRIONOracle::OwnershipTransferred",
        "kind": "nested"
      }
    ]
  }
] as const;
