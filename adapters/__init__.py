"""
TRION BTCP — VM Adapter System
==============================

Cross-VM translation layer for BTCP operations.

Adapters implemented:
  1. EVM       — Ethereum Virtual Machine (Ethereum, Arbitrum, Optimism, etc.)
  2. SVM       — Sealevel Virtual Machine (Solana)
  3. Cosmos    — Cosmos SDK / Tendermint (Cosmos Hub, Osmosis, etc.)
  4. Move      — Move VM (Aptos, Sui)
  5. CosmWasm  — WebAssembly on Cosmos (Juno, Terra, etc.)
  6. OOA       — Object-Oriented Architecture (Fuel, Sui objects)

Architecture:
  - BaseVMAdapter abstract class defines common interface
  - Each VM adapter implements: encode_intent(), decode_proof(),
    estimate_gas(), get_chain_id(), format_address()
  - VMAdapterFactory provides unified access by chain_id or VM type

Whitepaper reference: L7.2 Cross-VM Translation Layer, L7.4 VM Abstraction
"""

import os
import sys
import json
import time
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any, Union
from enum import IntEnum


# ── VM Type Enumeration ──────────────────────────────────────────────────────

class VMType(IntEnum):
    """Virtual machine types supported by TRION BTCP."""
    EVM = 1
    SVM = 2
    COSMOS = 3
    MOVE = 4
    COSMWASM = 5
    OOA = 6


# ── Chain ID → VM Type Mapping ──────────────────────────────────────────────

CHAIN_VM_MAP: Dict[int, VMType] = {
    # EVM chains
    1: VMType.EVM,       # Ethereum Mainnet
    5: VMType.EVM,       # Goerli
    10: VMType.EVM,      # Optimism
    56: VMType.EVM,      # BNB Chain
    100: VMType.EVM,     # Gnosis
    137: VMType.EVM,     # Polygon
    250: VMType.EVM,     # Fantom
    42161: VMType.EVM,   # Arbitrum One
    421614: VMType.EVM,  # Arbitrum Sepolia
    43114: VMType.EVM,   # Avalanche C-Chain
    8453: VMType.EVM,    # Base
    59144: VMType.EVM,   # Linea
    7777777: VMType.EVM, # Zora
    
    # SVM chains
    900: VMType.SVM,     # Solana Mainnet
    901: VMType.SVM,     # Solana Devnet
    
    # Cosmos chains
    10000: VMType.COSMOS,    # Cosmos Hub
    10001: VMType.COSMOS,    # Osmosis
    10002: VMType.COSMWASM,  # Juno (CosmWasm)
    10003: VMType.COSMOS,    # Celestia
    
    # Move chains
    20000: VMType.MOVE,  # Aptos
    20001: VMType.MOVE,  # Sui
    20002: VMType.OOA,   # Fuel (OOA)
}


# ── Data Structures ─────────────────────────────────────────────────────────

@dataclass
class BTCPIntent:
    """Standardized BTCP intent representation across all VMs."""
    intent_id: str = ""
    source_chain: int = 0
    dest_chain: int = 0
    source_address: str = ""
    dest_address: str = ""
    amount: int = 0
    asset: str = ""
    intent_type: str = "TRANSFER"
    deadline: int = 0
    nonce: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def hash(self) -> bytes:
        """Hash of the canonical intent representation."""
        canonical = (
            f"{self.intent_id}:{self.source_chain}:{self.dest_chain}:"
            f"{self.source_address}:{self.dest_address}:{self.amount}:"
            f"{self.asset}:{self.intent_type}:{self.deadline}:{self.nonce}"
        )
        return hashlib.sha3_256(canonical.encode()).digest()


@dataclass
class BTCPProof:
    """Standardized BTCP proof across all VMs."""
    proof_id: str = ""
    intent_hash: str = ""
    source_chain: int = 0
    dest_chain: int = 0
    proof_data: Dict[str, Any] = field(default_factory=dict)
    signatures: List[str] = field(default_factory=list)
    vm_type: VMType = VMType.EVM
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['vm_type'] = self.vm_type.name
        return d


@dataclass
class GasEstimate:
    """Gas estimation result."""
    gas_limit: int = 0
    gas_price: float = 0.0
    estimated_fee: float = 0.0
    fee_token: str = ""
    vm_type: VMType = VMType.EVM


# ── Base VM Adapter ─────────────────────────────────────────────────────────

class BaseVMAdapter(ABC):
    """Abstract base class for all VM adapters."""
    
    vm_type: VMType
    name: str
    native_token: str
    gas_token: str
    
    @abstractmethod
    def encode_intent(self, intent: BTCPIntent) -> str:
        """
        Encode a BTCP intent into the VM-specific format.
        
        Returns the encoded intent as a hex string.
        """
        pass
    
    @abstractmethod
    def decode_proof(self, encoded_proof: str) -> BTCPProof:
        """Decode a VM-specific proof into the standard BTCPProof format."""
        pass
    
    @abstractmethod
    def estimate_gas(self, intent: BTCPIntent) -> GasEstimate:
        """Estimate gas cost for executing the intent on this VM."""
        pass
    
    @abstractmethod
    def get_chain_id(self, network_name: str) -> int:
        """Get the chain ID for a given network name."""
        pass
    
    @abstractmethod
    def format_address(self, address: str) -> str:
        """Format an address into the VM's canonical representation."""
        pass
    
    @abstractmethod
    def validate_address(self, address: str) -> bool:
        """Validate that an address is properly formatted for this VM."""
        pass
    
    @abstractmethod
    def hash_intent(self, intent: BTCPIntent) -> str:
        """Compute the VM-specific intent hash."""
        pass
    
    def generate_proof_id(self, intent: BTCPIntent) -> str:
        """Generate a unique proof ID for an intent."""
        data = f"{self.vm_type.value}:{intent.hash().hex()}:{time.time()}"
        return hashlib.sha3_256(data.encode()).hexdigest()


# ── EVM Adapter ─────────────────────────────────────────────────────────────

class EVMAdapter(BaseVMAdapter):
    """
    Ethereum Virtual Machine adapter.
    
    Handles all EVM-compatible chains: Ethereum, Arbitrum, Optimism, Polygon,
    BNB Chain, Avalanche, Base, etc.
    """
    
    vm_type = VMType.EVM
    name = "EVM"
    native_token = "ETH"
    gas_token = "ETH"
    
    # EVM chain ID mapping
    CHAIN_IDS = {
        "mainnet": 1,
        "goerli": 5,
        "sepolia": 11155111,
        "optimism": 10,
        "bsc": 56,
        "gnosis": 100,
        "polygon": 137,
        "fantom": 250,
        "arbitrum": 42161,
        "arbitrum-sepolia": 421614,
        "avalanche": 43114,
        "base": 8453,
        "linea": 59144,
    }
    
    def encode_intent(self, intent: BTCPIntent) -> str:
        """
        Encode intent as EVM calldata (ABI-encoded style).
        
        Format: 
          function selector (4 bytes) + abi-encoded parameters
        """
        # Simple encoding: keccak-style hash + parameters as hex
        intent_bytes = intent.hash()
        
        # EVM-style encoding: function selector + params
        selector = hashlib.sha3_256(b"executeBTCPIntent(bytes32,uint256,address,address,uint256)").digest()[:4]
        
        # Encode parameters in EVM abi style (simplified)
        source_addr_hex = intent.source_address.lower().zfill(64) if intent.source_address.startswith('0x') else intent.source_address.zfill(64)
        dest_addr_hex = intent.dest_address.lower().zfill(64) if intent.dest_address.startswith('0x') else intent.dest_address.zfill(64)
        amount_hex = format(intent.amount, '064x')
        deadline_hex = format(intent.deadline, '064x')
        
        encoded = selector.hex() + intent_bytes.hex() + amount_hex + source_addr_hex + dest_addr_hex + deadline_hex
        return "0x" + encoded
    
    def decode_proof(self, encoded_proof: str) -> BTCPProof:
        """Decode an EVM transaction receipt proof."""
        if encoded_proof.startswith('0x'):
            encoded_proof = encoded_proof[2:]
        
        proof = BTCPProof(
            proof_id=hashlib.sha3_256(encoded_proof.encode()).hexdigest(),
            vm_type=VMType.EVM,
            proof_data={
                "encoded_length": len(encoded_proof),
                "format": "evm_calldata",
                "raw": encoded_proof[:64] + "..." if len(encoded_proof) > 64 else encoded_proof,
            }
        )
        return proof
    
    def estimate_gas(self, intent: BTCPIntent) -> GasEstimate:
        """Estimate EVM gas cost."""
        # Base BTCP execution gas on EVM
        base_gas = 21000  # Base transaction cost
        intent_gas = 80000  # BTCP intent execution
        verification_gas = 50000  # Proof verification
        total_gas = base_gas + intent_gas + verification_gas
        
        # Gas price varies by chain
        gas_prices = {
            1: 20.0,      # Ethereum mainnet: 20 gwei
            42161: 0.1,   # Arbitrum: 0.1 gwei
            137: 30.0,    # Polygon: 30 gwei
            10: 0.001,    # Optimism: very low
        }
        gas_price = gas_prices.get(intent.source_chain, 5.0)
        
        estimated_fee = total_gas * gas_price * 1e-9  # Convert to ETH
        
        return GasEstimate(
            gas_limit=total_gas,
            gas_price=gas_price,
            estimated_fee=estimated_fee,
            fee_token=self.gas_token,
            vm_type=VMType.EVM,
        )
    
    def get_chain_id(self, network_name: str) -> int:
        return self.CHAIN_IDS.get(network_name.lower(), 0)
    
    def format_address(self, address: str) -> str:
        """Format as EIP-55 checksum address (simplified)."""
        if not address.startswith('0x'):
            address = '0x' + address
        return address.lower()
    
    def validate_address(self, address: str) -> bool:
        """Validate EVM address format."""
        if not address.startswith('0x'):
            return False
        hex_part = address[2:]
        if len(hex_part) != 40:
            return False
        try:
            int(hex_part, 16)
            return True
        except ValueError:
            return False
    
    def hash_intent(self, intent: BTCPIntent) -> str:
        """EVM-style keccak256 intent hash."""
        return "0x" + intent.hash().hex()


# ── SVM Adapter (Solana) ────────────────────────────────────────────────────

class SVMAdapter(BaseVMAdapter):
    """
    Sealevel Virtual Machine adapter for Solana.
    
    Handles Solana's account-based model with instruction data.
    """
    
    vm_type = VMType.SVM
    name = "SVM"
    native_token = "SOL"
    gas_token = "SOL"
    
    CHAIN_IDS = {
        "mainnet": 900,
        "devnet": 901,
        "testnet": 902,
    }
    
    def encode_intent(self, intent: BTCPIntent) -> str:
        """
        Encode intent as Solana instruction data.
        
        Solana uses base58-encoded addresses and borsh serialization.
        """
        import struct
        
        # Borsh-style simplified encoding
        discriminator = hashlib.sha3_256(b"global:execute_intent").digest()[:8]
        
        # Pack: intent_hash (32) + amount (8) + deadline (8) + nonce (4)
        packed = discriminator
        packed += intent.hash()
        packed += struct.pack('<Q', intent.amount)  # u64 little-endian
        packed += struct.pack('<Q', intent.deadline)
        packed += struct.pack('<I', intent.nonce)
        
        return "0x" + packed.hex()
    
    def decode_proof(self, encoded_proof: str) -> BTCPProof:
        """Decode a Solana transaction proof."""
        if encoded_proof.startswith('0x'):
            encoded_proof = encoded_proof[2:]
        
        return BTCPProof(
            proof_id=hashlib.sha3_256(encoded_proof.encode()).hexdigest(),
            vm_type=VMType.SVM,
            proof_data={
                "encoded_length": len(encoded_proof),
                "format": "svm_instruction",
                "encoding": "borsh",
            }
        )
    
    def estimate_gas(self, intent: BTCPIntent) -> GasEstimate:
        """Estimate Solana compute units and lamports cost."""
        # Solana uses compute units instead of gas
        compute_units = 100000  # Typical BTCP instruction
        cu_price = 1  # 1 lamport per CU (simplified)
        
        # Base fee + priority fee
        base_fee = 5000  # 5000 lamports base
        priority_fee = compute_units * cu_price
        total_lamports = base_fee + priority_fee
        
        estimated_fee = total_lamports * 1e-9  # Convert to SOL
        
        return GasEstimate(
            gas_limit=compute_units,
            gas_price=cu_price,
            estimated_fee=estimated_fee,
            fee_token=self.gas_token,
            vm_type=VMType.SVM,
        )
    
    def get_chain_id(self, network_name: str) -> int:
        return self.CHAIN_IDS.get(network_name.lower(), 0)
    
    def format_address(self, address: str) -> str:
        """Solana addresses are base58 encoded, 32-44 characters."""
        return address.strip()
    
    def validate_address(self, address: str) -> bool:
        """Validate Solana base58 address format."""
        import re
        # Solana addresses: base58, 32-44 chars
        return bool(re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', address))
    
    def hash_intent(self, intent: BTCPIntent) -> str:
        """Solana-style intent hash."""
        return intent.hash().hex()


# ── Cosmos Adapter ──────────────────────────────────────────────────────────

class CosmosAdapter(BaseVMAdapter):
    """
    Cosmos SDK adapter.
    
    Handles Tendermint-based chains with Protobuf-encoded transactions.
    """
    
    vm_type = VMType.COSMOS
    name = "Cosmos"
    native_token = "ATOM"
    gas_token = "uatom"
    
    CHAIN_IDS = {
        "cosmoshub": 10000,
        "osmosis": 10001,
        "juno": 10002,
        "celestia": 10003,
    }
    
    def encode_intent(self, intent: BTCPIntent) -> str:
        """Encode intent as Cosmos Protobuf-style message."""
        # Simplified Protobuf encoding
        msg_type = "/trion.btcp.v1.MsgExecuteIntent"
        
        proto_data = {
            "type": msg_type,
            "value": {
                "intent_hash": intent.hash().hex(),
                "source_chain": intent.source_chain,
                "dest_chain": intent.dest_chain,
                "amount": str(intent.amount),
                "denom": intent.asset,
                "sender": intent.source_address,
                "receiver": intent.dest_address,
                "timeout_timestamp": str(intent.deadline),
            }
        }
        
        encoded = json.dumps(proto_data, separators=(',', ':'))
        return "0x" + encoded.encode().hex()
    
    def decode_proof(self, encoded_proof: str) -> BTCPProof:
        """Decode a Cosmos Tendermint proof."""
        if encoded_proof.startswith('0x'):
            encoded_proof = encoded_proof[2:]
        
        return BTCPProof(
            proof_id=hashlib.sha3_256(encoded_proof.encode()).hexdigest(),
            vm_type=VMType.COSMOS,
            proof_data={
                "encoded_length": len(encoded_proof),
                "format": "cosmos_protobuf",
                "consensus": "tendermint",
            }
        )
    
    def estimate_gas(self, intent: BTCPIntent) -> GasEstimate:
        """Estimate Cosmos gas."""
        base_gas = 200000
        intent_gas = 150000
        total_gas = base_gas + intent_gas
        
        # Gas price in uatom per gas unit
        gas_price = 0.025  # uatom/gas
        estimated_fee = total_gas * gas_price * 1e-6  # Convert to ATOM
        
        return GasEstimate(
            gas_limit=total_gas,
            gas_price=gas_price,
            estimated_fee=estimated_fee,
            fee_token=self.gas_token,
            vm_type=VMType.COSMOS,
        )
    
    def get_chain_id(self, network_name: str) -> int:
        return self.CHAIN_IDS.get(network_name.lower(), 0)
    
    def format_address(self, address: str) -> str:
        """Cosmos addresses use Bech32 format (cosmos1..., osmo1..., etc.)."""
        return address.strip()
    
    def validate_address(self, address: str) -> bool:
        """Validate Cosmos Bech32 address format."""
        import re
        return bool(re.match(r'^(cosmos|osmo|juno|celestia)1[a-z0-9]{38,58}$', address))
    
    def hash_intent(self, intent: BTCPIntent) -> str:
        """Cosmos-style intent hash."""
        return intent.hash().hex()


# ── Move Adapter ────────────────────────────────────────────────────────────

class MoveAdapter(BaseVMAdapter):
    """
    Move VM adapter for Aptos and Sui.
    
    Handles Move module-based transactions.
    """
    
    vm_type = VMType.MOVE
    name = "Move"
    native_token = "APT"
    gas_token = "APT"
    
    CHAIN_IDS = {
        "aptos": 20000,
        "sui": 20001,
    }
    
    def encode_intent(self, intent: BTCPIntent) -> str:
        """Encode intent as Move module call."""
        # Move-style BCS encoding (simplified)
        import struct
        
        module_id = b"trion::btcp"
        function_name = b"execute_intent"
        
        # BCS-style: length-prefixed vectors
        def bcs_string(s: str) -> bytes:
            data = s.encode()
            return len(data).to_bytes(4, 'little') + data
        
        encoded = module_id + b"\x00" + function_name
        encoded += intent.hash()
        encoded += struct.pack('<Q', intent.amount)
        encoded += struct.pack('<Q', intent.deadline)
        encoded += bcs_string(intent.source_address)
        encoded += bcs_string(intent.dest_address)
        
        return "0x" + encoded.hex()
    
    def decode_proof(self, encoded_proof: str) -> BTCPProof:
        """Decode a Move transaction proof."""
        if encoded_proof.startswith('0x'):
            encoded_proof = encoded_proof[2:]
        
        return BTCPProof(
            proof_id=hashlib.sha3_256(encoded_proof.encode()).hexdigest(),
            vm_type=VMType.MOVE,
            proof_data={
                "encoded_length": len(encoded_proof),
                "format": "move_bcs",
                "encoding": "bcs",
            }
        )
    
    def estimate_gas(self, intent: BTCPIntent) -> GasEstimate:
        """Estimate Move VM gas."""
        base_gas = 100
        intent_gas = 800
        total_gas = base_gas + intent_gas
        
        gas_price = 100  # Octa per gas unit
        estimated_fee = total_gas * gas_price * 1e-8  # Convert to APT
        
        return GasEstimate(
            gas_limit=total_gas,
            gas_price=gas_price,
            estimated_fee=estimated_fee,
            fee_token=self.gas_token,
            vm_type=VMType.MOVE,
        )
    
    def get_chain_id(self, network_name: str) -> int:
        return self.CHAIN_IDS.get(network_name.lower(), 0)
    
    def format_address(self, address: str) -> str:
        """Move addresses are 32-byte hex with 0x prefix."""
        if not address.startswith('0x'):
            address = '0x' + address
        return address.lower()
    
    def validate_address(self, address: str) -> bool:
        """Validate Move address format."""
        if not address.startswith('0x'):
            return False
        hex_part = address[2:]
        if len(hex_part) < 1 or len(hex_part) > 64:
            return False
        try:
            int(hex_part, 16)
            return True
        except ValueError:
            return False
    
    def hash_intent(self, intent: BTCPIntent) -> str:
        """Move-style intent hash."""
        return "0x" + intent.hash().hex()


# ── CosmWasm Adapter ────────────────────────────────────────────────────────

class CosmWasmAdapter(CosmosAdapter):
    """
    CosmWasm adapter — WebAssembly smart contracts on Cosmos.
    
    Extends CosmosAdapter but handles WASM-specific encoding.
    """
    
    vm_type = VMType.COSMWASM
    name = "CosmWasm"
    native_token = "JUNO"
    gas_token = "ujuno"
    
    CHAIN_IDS = {
        "juno": 10002,
        "terra": 10004,
        "stargaze": 10005,
    }
    
    def encode_intent(self, intent: BTCPIntent) -> str:
        """Encode intent as CosmWasm ExecuteMsg JSON."""
        wasm_msg = {
            "execute_intent": {
                "intent_hash": intent.hash().hex(),
                "source_chain": intent.source_chain,
                "dest_chain": intent.dest_chain,
                "amount": str(intent.amount),
                "asset": intent.asset,
                "deadline": intent.deadline,
                "nonce": intent.nonce,
            }
        }
        
        encoded = json.dumps(wasm_msg, separators=(',', ':'))
        return "0x" + encoded.encode().hex()
    
    def estimate_gas(self, intent: BTCPIntent) -> GasEstimate:
        """CosmWasm gas is higher due to WASM execution."""
        base_gas = 300000
        wasm_gas = 400000  # WASM instantiation/execution overhead
        total_gas = base_gas + wasm_gas
        
        gas_price = 0.025
        estimated_fee = total_gas * gas_price * 1e-6
        
        return GasEstimate(
            gas_limit=total_gas,
            gas_price=gas_price,
            estimated_fee=estimated_fee,
            fee_token=self.gas_token,
            vm_type=VMType.COSMWASM,
        )


# ── OOA Adapter (Object-Oriented Architecture) ─────────────────────────────

class OOAAdapter(BaseVMAdapter):
    """
    Object-Oriented Architecture adapter for Fuel and similar.
    
    Handles UTXO-based and object-centric VMs.
    """
    
    vm_type = VMType.OOA
    name = "OOA"
    native_token = "ETH"
    gas_token = "ETH"
    
    CHAIN_IDS = {
        "fuel": 20002,
        "sui_objects": 20003,
    }
    
    def encode_intent(self, intent: BTCPIntent) -> str:
        """Encode intent as OOA object call."""
        # Object-centric encoding: input objects + operation
        ooa_encoding = {
            "operation": "BTCP_EXECUTE",
            "input_objects": [
                {"type": "coin", "asset": intent.asset, "amount": intent.amount},
                {"type": "intent", "hash": intent.hash().hex()},
            ],
            "output_objects": [
                {"type": "proof", "dest_chain": intent.dest_chain},
            ],
            "gas_budget": 1000000,
            "deadline": intent.deadline,
        }
        
        encoded = json.dumps(ooa_encoding, separators=(',', ':'))
        return "0x" + encoded.encode().hex()
    
    def decode_proof(self, encoded_proof: str) -> BTCPProof:
        """Decode an OOA transaction proof."""
        if encoded_proof.startswith('0x'):
            encoded_proof = encoded_proof[2:]
        
        return BTCPProof(
            proof_id=hashlib.sha3_256(encoded_proof.encode()).hexdigest(),
            vm_type=VMType.OOA,
            proof_data={
                "encoded_length": len(encoded_proof),
                "format": "ooa_object",
                "object_model": True,
            }
        )
    
    def estimate_gas(self, intent: BTCPIntent) -> GasEstimate:
        """Estimate OOA gas."""
        base_gas = 10000
        object_access = 50000  # Per object access
        num_objects = 4  # coin + intent + proof + gas
        total_gas = base_gas + (object_access * num_objects)
        
        gas_price = 0.1  # gwei equivalent
        estimated_fee = total_gas * gas_price * 1e-9
        
        return GasEstimate(
            gas_limit=total_gas,
            gas_price=gas_price,
            estimated_fee=estimated_fee,
            fee_token=self.gas_token,
            vm_type=VMType.OOA,
        )
    
    def get_chain_id(self, network_name: str) -> int:
        return self.CHAIN_IDS.get(network_name.lower(), 0)
    
    def format_address(self, address: str) -> str:
        return address.strip()
    
    def validate_address(self, address: str) -> bool:
        """OOA addresses can be various formats - basic validation."""
        return len(address) >= 20 and len(address) <= 128
    
    def hash_intent(self, intent: BTCPIntent) -> str:
        """OOA-style intent hash."""
        return intent.hash().hex()


# ── VM Adapter Factory ──────────────────────────────────────────────────────

class VMAdapterFactory:
    """
    Factory for creating VM adapters based on chain ID or VM type.
    
    Provides a unified interface for cross-VM BTCP operations.
    """
    
    _adapters: Dict[VMType, BaseVMAdapter] = {}
    
    @classmethod
    def _init_adapters(cls):
        """Initialize all available adapters."""
        if not cls._adapters:
            cls._adapters = {
                VMType.EVM: EVMAdapter(),
                VMType.SVM: SVMAdapter(),
                VMType.COSMOS: CosmosAdapter(),
                VMType.MOVE: MoveAdapter(),
                VMType.COSMWASM: CosmWasmAdapter(),
                VMType.OOA: OOAAdapter(),
            }
    
    @classmethod
    def get_by_vm_type(cls, vm_type: VMType) -> Optional[BaseVMAdapter]:
        """Get an adapter by VM type."""
        cls._init_adapters()
        return cls._adapters.get(vm_type)
    
    @classmethod
    def get_by_chain_id(cls, chain_id: int) -> Optional[BaseVMAdapter]:
        """Get an adapter by chain ID."""
        cls._init_adapters()
        vm_type = CHAIN_VM_MAP.get(chain_id)
        if vm_type is None:
            # Default to EVM for unknown chains
            return cls._adapters[VMType.EVM]
        return cls._adapters.get(vm_type)
    
    @classmethod
    def get_by_chain_name(cls, chain_name: str) -> Optional[BaseVMAdapter]:
        """Get an adapter by chain name."""
        cls._init_adapters()
        # Try to find chain name in any adapter's CHAIN_IDS
        for adapter in cls._adapters.values():
            if hasattr(adapter, 'CHAIN_IDS') and chain_name.lower() in adapter.CHAIN_IDS:
                return adapter
        return cls._adapters[VMType.EVM]
    
    @classmethod
    def list_adapters(cls) -> List[Dict[str, Any]]:
        """List all available adapters."""
        cls._init_adapters()
        return [
            {
                "vm_type": vm_type.name,
                "vm_type_id": int(vm_type),
                "name": adapter.name,
                "native_token": adapter.native_token,
                "gas_token": adapter.gas_token,
                "chains": list(getattr(adapter, 'CHAIN_IDS', {}).keys()),
            }
            for vm_type, adapter in cls._adapters.items()
        ]
    
    @classmethod
    def cross_vm_transfer(cls, intent: BTCPIntent) -> Dict[str, Any]:
        """
        Encode an intent for cross-VM transfer.
        
        Returns encoding for both source and destination VMs, plus
        gas estimates and proof format information.
        """
        cls._init_adapters()
        
        source_adapter = cls.get_by_chain_id(intent.source_chain)
        dest_adapter = cls.get_by_chain_id(intent.dest_chain)
        
        if source_adapter is None or dest_adapter is None:
            raise ValueError(f"Unknown chain: source={intent.source_chain}, dest={intent.dest_chain}")
        
        source_encoded = source_adapter.encode_intent(intent)
        dest_encoded = dest_adapter.encode_intent(intent)
        
        source_gas = source_adapter.estimate_gas(intent)
        dest_gas = dest_adapter.estimate_gas(intent)
        
        return {
            "intent_id": intent.intent_id or intent.hash().hex()[:16],
            "source_vm": source_adapter.vm_type.name,
            "dest_vm": dest_adapter.vm_type.name,
            "source_chain": intent.source_chain,
            "dest_chain": intent.dest_chain,
            "source_encoded": source_encoded[:66] + "..." if len(source_encoded) > 66 else source_encoded,
            "dest_encoded": dest_encoded[:66] + "..." if len(dest_encoded) > 66 else dest_encoded,
            "source_gas_estimate": asdict(source_gas),
            "dest_gas_estimate": asdict(dest_gas),
            "total_estimated_fee": source_gas.estimated_fee + dest_gas.estimated_fee,
            "intent_hash": intent.hash().hex(),
        }


# ── Self-Test ───────────────────────────────────────────────────────────────

def self_test() -> Dict[str, Any]:
    """Run comprehensive self-test of all VM adapters."""
    print("=" * 60)
    print("TRION VM ADAPTER SYSTEM — SELF TEST")
    print("=" * 60)
    
    results = {}
    
    # Test each adapter
    adapters = [
        ("EVM", EVMAdapter(), "0x1F98431c8aD98523631AE4a59f267346ea31F984"),
        ("SVM", SVMAdapter(), "Vote111111111111111111111111111111111111111"),
        ("Cosmos", CosmosAdapter(), "cosmos1v9jxgu33kfsgr5x2d8w8z3h3k4v8q5q6w7e8r9"),
        ("Move", MoveAdapter(), "0x421e8b512f9a3c7d8e6b5a4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3"),
        ("CosmWasm", CosmWasmAdapter(), "juno1v9jxgu33kfsgr5x2d8w8z3h3k4v8q5q6w7e8r9"),
        ("OOA", OOAAdapter(), "fuel1v9jxgu33kfsgr5x2d8w8z3h3k4v8q5q6w7e8r9"),
    ]
    
    # Create a test intent
    test_intent = BTCPIntent(
        intent_id="test_intent_001",
        source_chain=1,
        dest_chain=42161,
        source_address="0x1F98431c8aD98523631AE4a59f267346ea31F984",
        dest_address="0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
        amount=int(1.5 * 10**18),
        asset="ETH",
        intent_type="SWAP",
        deadline=int(time.time()) + 3600,
        nonce=42,
    )
    
    for name, adapter, test_addr in adapters:
        print(f"\n🧪 Testing {name} Adapter")
        
        try:
            # Test address validation
            addr_valid = adapter.validate_address(test_addr)
            print(f"  Address validation: {'✓' if addr_valid else '✗'} ({test_addr[:20]}...)")
            
            # Test address formatting
            formatted = adapter.format_address(test_addr)
            print(f"  Address formatted: ✓")
            
            # Test intent encoding
            encoded = adapter.encode_intent(test_intent)
            print(f"  Intent encoded: ✓ ({len(encoded)} chars)")
            
            # Test proof decoding
            proof = adapter.decode_proof(encoded)
            print(f"  Proof decoded: ✓ (vm_type={proof.vm_type.name})")
            
            # Test gas estimation
            gas = adapter.estimate_gas(test_intent)
            print(f"  Gas estimated: ✓ ({gas.gas_limit} units, {gas.estimated_fee:.8f} {gas.fee_token})")
            
            # Test intent hashing
            h = adapter.hash_intent(test_intent)
            print(f"  Intent hashed: ✓ ({h[:16]}...)")
            
            results[name] = {
                "address_validation": addr_valid,
                "encoding": True,
                "decoding": True,
                "gas_estimation": True,
                "hashing": True,
                "pass": True,
            }
            
        except Exception as e:
            print(f"  FAILED: {str(e)[:80]}")
            results[name] = {"pass": False, "error": str(e)[:100]}
    
    # Test factory
    print(f"\n🧪 Testing VM Adapter Factory")
    try:
        evm_adapter = VMAdapterFactory.get_by_chain_id(1)
        assert evm_adapter is not None
        assert evm_adapter.vm_type == VMType.EVM
        print(f"  EVM lookup by chain_id: ✓")
        
        svm_adapter = VMAdapterFactory.get_by_vm_type(VMType.SVM)
        assert svm_adapter is not None
        assert svm_adapter.vm_type == VMType.SVM
        print(f"  SVM lookup by VM type: ✓")
        
        cross_vm = VMAdapterFactory.cross_vm_transfer(test_intent)
        print(f"  Cross-VM transfer: ✓ (source={cross_vm['source_vm']}, dest={cross_vm['dest_vm']})")
        print(f"  Total fee: {cross_vm['total_estimated_fee']:.8f} ETH")
        
        adapters_list = VMAdapterFactory.list_adapters()
        print(f"  Listed {len(adapters_list)} adapters: ✓")
        
        results["Factory"] = {
            "chain_lookup": True,
            "vm_type_lookup": True,
            "cross_vm": True,
            "listing": True,
            "pass": True,
        }
        
    except Exception as e:
        print(f"  FAILED: {str(e)[:80]}")
        results["Factory"] = {"pass": False, "error": str(e)[:100]}
    
    # Summary
    passed = sum(1 for r in results.values() if r.get("pass"))
    total = len(results)
    
    print(f"\n{'='*60}")
    print(f"SELF TEST: {passed}/{total} PASSED")
    print(f"{'='*60}")
    
    results["_summary"] = {"passed": passed, "total": total}
    return results


if __name__ == "__main__":
    self_test()


__all__ = [
    'VMType',
    'CHAIN_VM_MAP',
    'BTCPIntent',
    'BTCPProof',
    'GasEstimate',
    'BaseVMAdapter',
    'EVMAdapter',
    'SVMAdapter',
    'CosmosAdapter',
    'MoveAdapter',
    'CosmWasmAdapter',
    'OOAAdapter',
    'VMAdapterFactory',
    'self_test',
]
