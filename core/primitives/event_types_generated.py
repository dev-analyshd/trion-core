"""TRION Protocol — Canonical Event Types (auto-generated).

DO NOT EDIT MANUALLY. Run scripts/generate_enums.py to regenerate.
Source: config/bh_schema_v1.json
"""

from enum import IntEnum


class EventType(IntEnum):
    TRANSFER = 0  # 0
    SWAP = 1  # 1
    LIQUIDITY = 2  # 2
    STAKE = 3  # 3
    UNSTAKE = 4  # 4
    GOVERNANCE = 5  # 5
    PROPOSAL = 6  # 6
    BORROW = 7  # 7
    REPAY = 8  # 8
    LIQUIDATE = 9  # 9
    BRIDGE = 10  # 10
    DEPLOY = 11  # 11
    UPGRADE = 12  # 12
    MINT = 13  # 13
    BURN = 14  # 14
    ORACLE_UPDATE = 15  # 15
    MEV_CAPTURE = 16  # 16
    FLASH_LOAN = 17  # 17
    AIRDROP = 18  # 18
    CLAIM = 19  # 19


EVENT_TYPE_NAMES = {e.value: e.name for e in EventType}
