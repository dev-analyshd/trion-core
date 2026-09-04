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
import struct
import hashlib
import urllib.request
import urllib.error
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any, Union
from enum import IntEnum


# ── Execution Result ──────────────────────────────────────────────────────────

@dataclass
class ExecutionResult:
    """Standardized result returned by every VM adapter's execute_* method.

    Both DRY_RUN and real execution paths populate this structure so that
    upstream callers (BTCPOrchestrator, CrossVMGateway) can treat all VMs
    uniformly.
    """
    route_id:           str
    vm_type:            str
    chain_id:           int
    action:             str                  # swap | transfer | liquidity
    dry_run:            bool
    status:             str                  # DRY_RUN | SIMULATED | BROADCAST | CONFIRMED | FAILED
    to_address:         str = ""             # target contract / program / module
    calldata:           str = ""             # hex-encoded payload (calldata / instruction data / BCS / JSON)
    value:              int = 0              # native value to send (wei / lamports / u64)
    gas_estimate:       Optional[Dict[str, Any]] = None
    tx_hash:            Optional[str] = None
    explorer_url:       Optional[str] = None
    error:              Optional[str] = None
    rpc_used:           Optional[str] = None
    metadata:           Dict[str, Any] = field(default_factory=dict)
    timestamp:          float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Public RPC URL Map (chain_id -> public RPC, no API keys) ──────────────────
# Verified public endpoints for each supported chain. Read-only friendly;
# broadcasting requires a signer (passed by caller via `sender_pk`).

CHAIN_RPC_URLS: Dict[int, str] = {
    # EVM mainnets
    1:            "https://eth.llamarpc.com",
    5:            "https://goerli.llamarpc.com",
    10:           "https://mainnet.optimism.io",
    56:           "https://bsc-dataseed.binance.org",
    100:          "https://rpc.gnosischain.com",
    137:          "https://polygon-rpc.com",
    250:          "https://rpcapi.fantom.network",
    42161:        "https://arb1.arbitrum.io/rpc",
    421614:       "https://sepolia-rollup.arbitrum.io/rpc",
    43114:        "https://api.avax.network/ext/bc/C/rpc",
    8453:         "https://mainnet.base.org",
    59144:        "https://rpc.linea.build",
    534352:       "https://rpc.scroll.io",
    324:          "https://mainnet.era.zksync.io",
    5000:         "https://rpc.mantle.xyz",
    81457:        "https://rpc.blast.io",
    169:          "https://pacific-rpc.manta.network/http",
    34443:        "https://mainnet.mode.network",
    167000:       "https://rpc.mainnet.taiko.xyz",
    252:          "https://rpc.frax.com",
    1088:         "https://andromeda.metis.io/?owner=1088",
    146:          "https://rpc.soniclabs.com",
    196:          "https://rpc.xlayer.tech",
    50:           "https://rpc.xinfin.network",
    1514:         "https://mainnet.storyrpc.io",
    80094:        "https://rpc.berachain.com",
    16661:        "https://evmrpc.0g.ai",
    177:          "https://mainnet.hsk.xyz",
    1101:         "https://zkevm-rpc.com",
    1313161554:   "https://mainnet.aurora.dev",
    1284:         "https://rpc.api.moonbeam.network",
    1285:         "https://rpc.api.moonriver.moonbeam.network",
    42220:        "https://forno.celo.org",
    7777777:      "https://rpc.zora.energy",
    11155111:     "https://ethereum-sepolia.publicnode.com",
    84532:        "https://sepolia.base.org",
    80002:        "https://rpc-amoy.polygon.technology",
    11155420:     "https://sepolia.optimism.io",
    # SVM
    900:          "https://api.mainnet-beta.solana.com",
    901:          "https://api.devnet.solana.com",
    # Cosmos
    10000:        "https://rpc.cosmos.directory/cosmoshub",
    10001:        "https://rpc.osmosis.zone",
    10002:        "https://rpc.juno.anatolianteam.com",
    10003:        "https://rpc.celestia.pops.one",
    10004:        "https://rpc-injective-ec1.diamondnodes.com",
    10005:        "https://rpc.sei.chainnodes.org",
    10006:        "https://dydx-rpc.publicnode.com",
    10007:        "https://rpc.kujira.interbloc.org",
    10008:        "https://rpc.stargaze.ezstaking.net",
    # Move VM (canonical: 20000 Aptos, 20001 Aptos testnet, 20100 Sui, 20101 Sui testnet)
    20000:        "https://fullnode.mainnet.aptoslabs.com/v1",
    20001:        "https://fullnode.testnet.aptoslabs.com/v1",
    20100:        "https://full.mainnet.sui.io",
    20101:        "https://full.testnet.sui.io",
    # OOA (object-centric — Fuel testnet; no canonical mainnet ID yet)
    20002:        "https://testnet.fuel.graphql.api.rsdev.org/v1/graphql",
}


# ── RPC Client (stdlib-only, no external deps) ────────────────────────────────

class _RPCClient:
    """Lightweight JSON-RPC / REST helper built on urllib.

    All execute_* methods use this for chain I/O so we never need a third-party
    HTTP or web3 library. Timeouts are short (10s) so failed RPCs degrade
    gracefully into `status="FAILED"` instead of blocking the BTCP orchestrator.
    """

    DEFAULT_TIMEOUT = 10.0
    DEFAULT_UA = "trion-btcp-adapter/2.1 (+https://trion.gg)"

    @staticmethod
    def _ctx() -> ssl.SSLContext:
        # Allow default verification but tolerate RPCs with stale certs in
        # sandboxed environments (read-only calls only).
        try:
            return ssl.create_default_context()
        except Exception:  # pragma: no cover
            return ssl._create_unverified_context()

    @staticmethod
    def post_json(url: str, payload: Any, headers: Optional[Dict[str, str]] = None,
                  timeout: Optional[float] = None) -> Dict[str, Any]:
        """POST JSON and return parsed JSON response."""
        data = json.dumps(payload).encode("utf-8")
        hdrs = {
            "Content-Type": "application/json",
            "User-Agent": _RPCClient.DEFAULT_UA,
            "Accept": "application/json",
        }
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
        tmo = timeout or _RPCClient.DEFAULT_TIMEOUT
        try:
            with urllib.request.urlopen(req, timeout=tmo, context=_RPCClient._ctx()) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code} from {url}: {body[:300]}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"URL error contacting {url}: {e.reason}") from None
        except Exception as e:
            raise RuntimeError(f"RPC {url} failed: {type(e).__name__}: {e}") from None

    @staticmethod
    def get_json(url: str, headers: Optional[Dict[str, str]] = None,
                 timeout: Optional[float] = None) -> Any:
        """GET JSON and return parsed JSON response."""
        hdrs = {
            "Accept": "application/json",
            "User-Agent": _RPCClient.DEFAULT_UA,
        }
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, headers=hdrs, method="GET")
        tmo = timeout or _RPCClient.DEFAULT_TIMEOUT
        try:
            with urllib.request.urlopen(req, timeout=tmo, context=_RPCClient._ctx()) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code} from {url}: {body[:300]}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"URL error contacting {url}: {e.reason}") from None
        except Exception as e:
            raise RuntimeError(f"GET {url} failed: {type(e).__name__}: {e}") from None

    @staticmethod
    def jsonrpc(url: str, method: str, params: Optional[List[Any]] = None,
                request_id: int = 1, timeout: Optional[float] = None) -> Any:
        """Single JSON-RPC 2.0 call. Returns the `result` field or raises."""
        payload = {"jsonrpc": "2.0", "method": method, "params": params or [], "id": request_id}
        resp = _RPCClient.post_json(url, payload, timeout=timeout)
        if isinstance(resp, dict):
            if "error" in resp and resp["error"] is not None:
                raise RuntimeError(f"JSON-RPC error: {resp['error']}")
            return resp.get("result")
        return resp


def _rpc_for_chain(chain_id: int, override: Optional[str] = None) -> Optional[str]:
    """Resolve a public RPC URL for a chain. Caller override takes precedence."""
    if override:
        return override
    return CHAIN_RPC_URLS.get(chain_id)


# ── EVM ABI helpers (minimal, no external dependency) ──────────────────────────

# Function selectors (keccak256 of signature, first 4 bytes) for Uniswap V2
# Router (https://uniswap.org/docs/v2/). The V2 router is deployed at the same
# address (0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D) on virtually every
# EVM L1/L2 thanks to CREATE2 deployment at genesis.
_UNISWAP_V2_ROUTER = "0x7a250d5630b4cf539739df2c5dacb4c659f2488d"

# Selectors derived from keccak256(signature)[:4]
#   swapExactTokensForTokens(uint256,uint256,address[],address,uint256) = 0x38ed1739
#   swapExactETHForTokens(uint256,address[],address,uint256)            = 0x7ff36ab5
#   swapExactTokensForETH(uint256,uint256,address[],address,uint256)    = 0x18cbafe5
#   transfer(address,uint256)                                           = 0xa9059cbb
#   addLiquidity(address,address,uint256,uint256,uint256,uint256,uint256)= 0xe8e33700
#   removeLiquidity(address,address,uint256,uint256,uint256,uint256)    = 0xbaa2abde
#   getAmountsOut(uint256,address[])                                     = 0xd06ca61f
_SEL_SWAP_TOKENS   = "38ed1739"
_SEL_SWAP_ETH      = "7ff36ab5"
_SEL_SWAP_TO_ETH   = "18cbafe5"
_SEL_TRANSFER      = "a9059cbb"
_SEL_ADD_LIQ       = "e8e33700"
_SEL_REMOVE_LIQ    = "baa2abde"
_SEL_GET_AMOUNTS   = "d06ca61f"


def _addr_padded(addr: str) -> str:
    """Normalize an EVM address to a 32-byte left-padded hex string (no 0x)."""
    a = addr.lower().removeprefix("0x")
    return a.rjust(64, "0")


def _uint_padded(n: int) -> str:
    """Encode an unsigned integer as a 32-byte big-endian hex string."""
    if n < 0:
        raise ValueError("negative uint not encodable as uint256")
    return format(n & ((1 << 256) - 1), "064x")


def _dyn_array(items: List[str]) -> str:
    """ABI-encode a dynamic array of 32-byte items: len || items."""
    out = _uint_padded(len(items))
    for it in items:
        out += it
    return out


def _evm_gas_for_action(action: str) -> int:
    """Approximate gas limit by action type."""
    return {
        "swap":      200_000,
        "transfer":   65_000,
        "liquidity": 350_000,
    }.get(action, 120_000)



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
    20001: VMType.MOVE,  # Aptos Testnet
    20100: VMType.MOVE,  # Sui Mainnet
    20101: VMType.MOVE,  # Sui Testnet
    20002: VMType.OOA,   # Fuel Testnet (OOA)
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

    @abstractmethod
    def execute_swap(self, route_id: str, amount: int, token_in: str,
                     token_out: str, recipient: str, chain_id: int = 0,
                     slippage_bps: int = 50, dry_run: bool = True,
                     rpc_url: Optional[str] = None,
                     sender_pk: Optional[str] = None,
                     sender_addr: Optional[str] = None,
                     **kwargs: Any) -> 'ExecutionResult':
        """Execute a DEX swap on this VM (dry_run=True by default).

        Returns an ExecutionResult populated with calldata, gas estimate, and
        (if dry_run=False) a real RPC-probed quote / signed envelope.
        """
        pass

    @abstractmethod
    def execute_transfer(self, route_id: str, amount: int, token: str,
                         recipient: str, chain_id: int = 0,
                         dry_run: bool = True, rpc_url: Optional[str] = None,
                         sender_pk: Optional[str] = None,
                         sender_addr: Optional[str] = None,
                         **kwargs: Any) -> 'ExecutionResult':
        """Execute a token transfer (native or token-standard) on this VM."""
        pass

    @abstractmethod
    def execute_liquidity(self, route_id: str, amount_a: int, amount_b: int,
                          token_a: str, token_b: str, recipient: str,
                          chain_id: int = 0, action: str = "ADD",
                          slippage_bps: int = 50, dry_run: bool = True,
                          rpc_url: Optional[str] = None,
                          sender_pk: Optional[str] = None,
                          sender_addr: Optional[str] = None,
                          **kwargs: Any) -> 'ExecutionResult':
        """Add or remove liquidity on this VM's AMM."""
        pass


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


    # ── EVM EXECUTE METHODS (Uniswap V2 router, ERC20, native) ──────────────

    def execute_swap(
        self,
        route_id: str,
        amount: int,
        token_in: str,
        token_out: str,
        recipient: str,
        chain_id: int = 1,
        slippage_bps: int = 50,
        deadline_sec: int = 1800,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute a DEX swap via the Uniswap V2 router on an EVM chain.

        DRY_RUN (default): builds the ABI calldata and a gas estimate without
        touching the chain.
        dry_run=False: probes the chain via `eth_blockNumber` (liveness) and
        `eth_call` against the router\'s `getAmountsOut` for a real quote,
        then returns the ready-to-broadcast signed-payload description. If
        `sender_pk` is provided, a raw transaction is constructed (signing
        still requires the caller to inject a web3 signer — we only build the
        unsigned envelope to keep this dependency-free).
        """
        rpc = _rpc_for_chain(chain_id, rpc_url)
        path = [_addr_padded(token_in), _addr_padded(token_out)]
        is_eth_in = token_in.lower() == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        is_eth_out = token_out.lower() == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        deadline_hex = _uint_padded(int(time.time()) + deadline_sec)
        amount_hex = _uint_padded(amount)
        min_out_hex = _uint_padded(int(amount * (10_000 - slippage_bps) / 10_000))

        # Build calldata for swapExactTokensForTokens (the general case)
        # Layout: selector || amountIn || amountOutMin || offset(path) || deadline || len(path) || path
        dyn_offset = _uint_padded(0x60)  # path is at offset 0x60
        encoded_path = _dyn_array(path)
        calldata = (
            "0x" + _SEL_SWAP_TOKENS
            + amount_hex + min_out_hex + dyn_offset + deadline_hex
            + encoded_path
        )
        # ETH in / ETH out use specialised selectors with the same layout but
        # the router interprets msg.value as amountIn for ETH-in paths.
        if is_eth_in:
            calldata = (
                "0x" + _SEL_SWAP_ETH
                + min_out_hex + dyn_offset + deadline_hex + encoded_path
            )
        elif is_eth_out:
            calldata = (
                "0x" + _SEL_SWAP_TO_ETH
                + amount_hex + min_out_hex + dyn_offset + deadline_hex + encoded_path
            )

        gas_est = self.estimate_gas(BTCPIntent(
            source_chain=chain_id, dest_chain=chain_id,
            source_address=sender_addr or recipient, dest_address=recipient,
            amount=amount, asset=token_in, intent_type="SWAP",
            deadline=int(time.time()) + deadline_sec,
        ))
        gas_dict = asdict(gas_est)
        # Override gas limit with action-specific estimate (more accurate).
        gas_dict["gas_limit"] = _evm_gas_for_action("swap")

        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="swap", dry_run=dry_run, status="DRY_RUN",
            to_address=_UNISWAP_V2_ROUTER, calldata=calldata,
            value=amount if is_eth_in else 0,
            gas_estimate=gas_dict, rpc_used=rpc,
            metadata={"token_in": token_in, "token_out": token_out,
                      "recipient": recipient, "slippage_bps": slippage_bps,
                      "path_size": len(path)},
        )

        if dry_run:
            return result

        # ── LIVE PATH: probe chain, fetch real quote, optionally broadcast ──
        if not rpc:
            result.status = "FAILED"
            result.error = f"No public RPC known for chain_id={chain_id}"
            return result

        try:
            # Liveness check (read-only)
            head_hex = _RPCClient.jsonrpc(rpc, "eth_blockNumber")
            block_num = int(head_hex, 16) if isinstance(head_hex, str) else int(head_hex or 0)
            result.metadata["current_block"] = block_num

            # Read-only quote via router.getAmountsOut(uint256, address[])
            quote_calldata = (
                "0x" + _SEL_GET_AMOUNTS
                + amount_hex + _uint_padded(0x40)  # offset to path array
                + _uint_padded(len(path)) + path[0] + path[1]
            )
            try:
                amounts = _RPCClient.jsonrpc(rpc, "eth_call", [
                    {"to": _UNISWAP_V2_ROUTER, "data": quote_calldata},
                    "latest",
                ])
                if isinstance(amounts, str) and amounts.startswith("0x"):
                    # Strip 0x + 32-byte len word + each 32-byte amount
                    raw = amounts[2:]
                    if len(raw) >= 64:
                        n = int(raw[0:64], 16)
                        out_vals = []
                        for i in range(n):
                            v = int(raw[64 + i * 64:64 + (i + 1) * 64], 16)
                            out_vals.append(v)
                        if out_vals:
                            result.metadata["quoted_amount_out"] = out_vals[-1]
                            result.metadata["price_impact_bps"] = (
                                abs(out_vals[-1] - amount) * 10_000 // max(amount, 1)
                            )
                    result.status = "SIMULATED"
                else:
                    result.status = "SIMULATED"
            except Exception as e:
                result.metadata["quote_error"] = str(e)[:200]
                result.status = "SIMULATED"  # still probed the chain

            # If a sender private key is supplied, build a raw-tx envelope
            # (we deliberately do NOT broadcast here — broadcast requires
            # full nonce management + chain_id signing which is delegated to
            # the relayer/ethers.js layer; we surface the ready envelope).
            if sender_pk:
                try:
                    chain_id_hex = _RPCClient.jsonrpc(rpc, "eth_chainId")
                    nonce_hex = _RPCClient.jsonrpc(rpc, "eth_getTransactionCount",
                                                   [sender_addr or recipient, "latest"])
                    gas_price_hex = _RPCClient.jsonrpc(rpc, "eth_gasPrice")
                    result.metadata["unsigned_tx"] = {
                        "to": _UNISWAP_V2_ROUTER,
                        "data": calldata,
                        "value": hex(result.value),
                        "chainId": int(chain_id_hex, 16) if isinstance(chain_id_hex, str) else int(chain_id_hex or 0),
                        "nonce": int(nonce_hex, 16) if isinstance(nonce_hex, str) else int(nonce_hex or 0),
                        "gas": hex(_evm_gas_for_action("swap")),
                        "gasPrice": gas_price_hex,
                        "from": sender_addr or recipient,
                    }
                    result.status = "BROADCAST_READY"
                except Exception as e:
                    result.metadata["envelope_error"] = str(e)[:200]
                    result.status = "SIMULATED"
        except Exception as e:
            result.status = "FAILED"
            result.error = f"EVM RPC failure: {e}"

        return result

    def execute_transfer(
        self,
        route_id: str,
        amount: int,
        token: str,
        recipient: str,
        chain_id: int = 1,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute an ERC20 or native ETH transfer.

        token == 0xEeee...eee or "" → native ETH transfer (value + empty calldata).
        Otherwise → ERC20 transfer(address,uint256) to recipient.
        """
        rpc = _rpc_for_chain(chain_id, rpc_url)
        sender = sender_addr or (recipient if not dry_run else "0x0000000000000000000000000000000000000001")

        is_native = (not token or
                     token.lower() in ("0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
                                       "eth", "native"))
        if is_native:
            to_addr = recipient
            calldata = "0x"
            value = amount
        else:
            to_addr = token
            calldata = "0x" + _SEL_TRANSFER + _addr_padded(recipient) + _uint_padded(amount)
            value = 0

        gas_est = self.estimate_gas(BTCPIntent(
            source_chain=chain_id, dest_chain=chain_id,
            source_address=sender, dest_address=recipient,
            amount=amount, asset=token, intent_type="TRANSFER",
            deadline=int(time.time()) + 600,
        ))
        gas_dict = asdict(gas_est)
        gas_dict["gas_limit"] = _evm_gas_for_action("transfer")

        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="transfer", dry_run=dry_run, status="DRY_RUN",
            to_address=to_addr, calldata=calldata, value=value,
            gas_estimate=gas_dict, rpc_used=rpc,
            metadata={"token": token, "recipient": recipient,
                      "native": is_native},
        )
        if dry_run:
            return result

        if not rpc:
            result.status = "FAILED"
            result.error = f"No public RPC known for chain_id={chain_id}"
            return result
        try:
            head_hex = _RPCClient.jsonrpc(rpc, "eth_blockNumber")
            block_num = int(head_hex, 16) if isinstance(head_hex, str) else int(head_hex or 0)
            result.metadata["current_block"] = block_num

            if not is_native:
                # Simulate ERC20 transfer via eth_call
                try:
                    sim = _RPCClient.jsonrpc(rpc, "eth_call", [
                        {"from": sender, "to": token, "data": calldata},
                        "latest",
                    ])
                    result.metadata["simulated"] = sim
                except Exception as e:
                    result.metadata["sim_error"] = str(e)[:200]
            result.status = "SIMULATED"

            if sender_pk:
                try:
                    nonce_hex = _RPCClient.jsonrpc(rpc, "eth_getTransactionCount",
                                                   [sender, "latest"])
                    gas_price_hex = _RPCClient.jsonrpc(rpc, "eth_gasPrice")
                    result.metadata["unsigned_tx"] = {
                        "to": to_addr, "data": calldata, "value": hex(value),
                        "from": sender,
                        "nonce": int(nonce_hex, 16) if isinstance(nonce_hex, str) else int(nonce_hex or 0),
                        "gas": hex(_evm_gas_for_action("transfer")),
                        "gasPrice": gas_price_hex,
                    }
                    result.status = "BROADCAST_READY"
                except Exception as e:
                    result.metadata["envelope_error"] = str(e)[:200]
        except Exception as e:
            result.status = "FAILED"
            result.error = f"EVM RPC failure: {e}"
        return result

    def execute_liquidity(
        self,
        route_id: str,
        amount_a: int,
        amount_b: int,
        token_a: str,
        token_b: str,
        recipient: str,
        chain_id: int = 1,
        action: str = "ADD",        # ADD | REMOVE
        slippage_bps: int = 50,
        deadline_sec: int = 1800,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Add or remove Uniswap V2 liquidity for a pair."""
        rpc = _rpc_for_chain(chain_id, rpc_url)
        deadline_hex = _uint_padded(int(time.time()) + deadline_sec)
        min_a = _uint_padded(int(amount_a * (10_000 - slippage_bps) / 10_000))
        min_b = _uint_padded(int(amount_b * (10_000 - slippage_bps) / 10_000))

        if action.upper() == "ADD":
            selector = _SEL_ADD_LIQ
            calldata = ("0x" + selector
                        + _addr_padded(token_a) + _addr_padded(token_b)
                        + _uint_padded(amount_a) + _uint_padded(amount_b)
                        + min_a + min_b + deadline_hex)
        elif action.upper() == "REMOVE":
            selector = _SEL_REMOVE_LIQ
            calldata = ("0x" + selector
                        + _addr_padded(token_a) + _addr_padded(token_b)
                        + _uint_padded(amount_a)   # liquidity amount
                        + min_a + min_b + deadline_hex)
        else:
            return ExecutionResult(
                route_id=route_id, vm_type=self.name, chain_id=chain_id,
                action="liquidity", dry_run=dry_run, status="FAILED",
                error=f"Unknown action: {action}",
            )

        gas_est = self.estimate_gas(BTCPIntent(
            source_chain=chain_id, dest_chain=chain_id,
            source_address=sender_addr or recipient, dest_address=recipient,
            amount=amount_a + amount_b, asset=token_a, intent_type="LIQUIDITY",
            deadline=int(time.time()) + deadline_sec,
        ))
        gas_dict = asdict(gas_est)
        gas_dict["gas_limit"] = _evm_gas_for_action("liquidity")

        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="liquidity", dry_run=dry_run, status="DRY_RUN",
            to_address=_UNISWAP_V2_ROUTER, calldata=calldata, value=0,
            gas_estimate=gas_dict, rpc_used=rpc,
            metadata={"token_a": token_a, "token_b": token_b,
                      "amount_a": amount_a, "amount_b": amount_b,
                      "action": action, "recipient": recipient},
        )
        if dry_run:
            return result

        if not rpc:
            result.status = "FAILED"
            result.error = f"No public RPC known for chain_id={chain_id}"
            return result
        try:
            head_hex = _RPCClient.jsonrpc(rpc, "eth_blockNumber")
            block_num = int(head_hex, 16) if isinstance(head_hex, str) else int(head_hex or 0)
            result.metadata["current_block"] = block_num
            result.status = "SIMULATED"
        except Exception as e:
            result.status = "FAILED"
            result.error = f"EVM RPC failure: {e}"
        return result

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


    # ── SVM EXECUTE METHODS (Jupiter aggregator + SPL Token) ───────────────

    JUPITER_QUOTE_API = "https://quote-api.jup.ag/v6/quote"
    JUPITER_SWAP_API   = "https://quote-api.jup.ag/v6/swap"
    # SPL Token program (same on Solana mainnet + devnet)
    SPL_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VZ5X"

    def execute_swap(
        self,
        route_id: str,
        amount: int,
        token_in: str,
        token_out: str,
        recipient: str,
        chain_id: int = 900,
        slippage_bps: int = 50,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute a Solana swap via the Jupiter V6 aggregator.

        DRY_RUN: returns the encoded SVM instruction (Borsh-style) + compute
        budget estimate. dry_run=False queries Jupiter for a real quote and
        returns a ready-to-sign serialized transaction envelope.
        """
        rpc = _rpc_for_chain(chain_id, rpc_url) or self.JUPITER_QUOTE_API
        intent_dummy = BTCPIntent(
            source_chain=chain_id, dest_chain=chain_id,
            source_address=sender_addr or recipient, dest_address=recipient,
            amount=amount, asset=token_in, intent_type="SWAP",
            deadline=int(time.time()) + 1800,
        )
        calldata = self.encode_intent(intent_dummy)
        gas_est = self.estimate_gas(intent_dummy)
        gas_dict = asdict(gas_est)

        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="swap", dry_run=dry_run, status="DRY_RUN",
            to_address="JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
            calldata=calldata, value=0,
            gas_estimate=gas_dict, rpc_used=rpc,
            metadata={"token_in": token_in, "token_out": token_out,
                      "recipient": recipient, "slippage_bps": slippage_bps},
        )
        if dry_run:
            return result

        try:
            # Live quote from Jupiter aggregator (public, no API key)
            quote_url = (
                f"{self.JUPITER_QUOTE_API}?inputMint={token_in}"
                f"&outputMint={token_out}&amount={amount}"
                f"&slippageBps={slippage_bps}"
            )
            quote = _RPCClient.get_json(quote_url, timeout=12.0)
            result.metadata["quote"] = {
                "input_amount": quote.get("inAmount"),
                "output_amount": quote.get("outAmount"),
                "price_impact_pct": quote.get("priceImpactPct"),
                "route_plan_len": len(quote.get("routePlan", [])),
            }
            result.status = "SIMULATED"

            # Optionally fetch unsigned swap tx from Jupiter
            if sender_addr:
                try:
                    swap_url = (
                        f"{self.JUPITER_QUOTE_API.replace('quote', 'swap')}"
                    )
                    swap_payload = {
                        "quoteResponse": quote,
                        "userPublicKey": sender_addr,
                        "wrapAndUnwrapSol": True,
                        "computeUnitPriceMicroLamports": "auto",
                    }
                    swap_resp = _RPCClient.post_json(
                        self.JUPITER_SWAP_API, swap_payload, timeout=12.0,
                    )
                    if swap_resp.get("swapTransaction"):
                        result.metadata["unsigned_tx_b64"] = swap_resp["swapTransaction"]
                        result.status = "BROADCAST_READY"
                except Exception as e:
                    result.metadata["swap_tx_error"] = str(e)[:200]
        except Exception as e:
            result.status = "FAILED"
            result.error = f"Jupiter/SVM RPC failure: {e}"
        return result

    def execute_transfer(
        self,
        route_id: str,
        amount: int,
        token: str,
        recipient: str,
        chain_id: int = 900,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute an SPL token transfer (or native SOL transfer).

        token == "native" or "SOL" → System Program transfer of lamports.
        Otherwise → SPL Token `transfer` instruction.
        """
        rpc = _rpc_for_chain(chain_id, rpc_url)
        is_native = token.lower() in ("native", "sol", "so11111111111111111111111111111111111111112")
        if is_native:
            to_prog = "11111111111111111111111111111111"  # System Program
            # System Program transfer instruction layout:
            #   4-byte instruction index (2) + u64 lamports + pubkey recipient
            instr = struct.pack("<I", 2) + struct.pack("<Q", amount)
            try:
                # recipient pubkey → 32 bytes
                import base58
                rec_bytes = base58.b58decode(recipient)
            except Exception:
                rec_bytes = bytes(32)
            instr += rec_bytes
            calldata = "0x" + instr.hex()
            target = recipient
            value = amount
        else:
            to_prog = self.SPL_TOKEN_PROGRAM
            # SPL Token Transfer instruction: index 3 + u64 amount
            instr = struct.pack("<I", 3) + struct.pack("<Q", amount)
            calldata = "0x" + instr.hex()
            target = to_prog
            value = 0

        gas_est = self.estimate_gas(BTCPIntent(
            source_chain=chain_id, dest_chain=chain_id,
            source_address=sender_addr or recipient, dest_address=recipient,
            amount=amount, asset=token, intent_type="TRANSFER",
            deadline=int(time.time()) + 600,
        ))
        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="transfer", dry_run=dry_run, status="DRY_RUN",
            to_address=target, calldata=calldata, value=value,
            gas_estimate=asdict(gas_est), rpc_used=rpc,
            metadata={"token": token, "recipient": recipient,
                      "native": is_native},
        )
        if dry_run:
            return result

        if not rpc:
            result.status = "FAILED"
            result.error = f"No public RPC known for chain_id={chain_id}"
            return result
        try:
            # Liveness: getLatestBlockhash via Solana JSON-RPC
            bh = _RPCClient.jsonrpc(rpc, "getLatestBlockhash", [{"commitment": "finalized"}])
            if isinstance(bh, dict):
                result.metadata["blockhash"] = bh.get("value", {}).get("blockhash")
            result.status = "SIMULATED"
        except Exception as e:
            result.status = "FAILED"
            result.error = f"Solana RPC failure: {e}"
        return result

    def execute_liquidity(
        self,
        route_id: str,
        amount_a: int,
        amount_b: int,
        token_a: str,
        token_b: str,
        recipient: str,
        chain_id: int = 900,
        action: str = "ADD",
        slippage_bps: int = 50,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Add or remove Raydium AMM liquidity on Solana.

        DRY_RUN: builds the encoded instruction + gas estimate.
        dry_run=False: probes the Raydium program ID via getAccountInfo.
        """
        rpc = _rpc_for_chain(chain_id, rpc_url)
        # Raydium AMM v4 program id (mainnet)
        raydium_program = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
        intent_dummy = BTCPIntent(
            source_chain=chain_id, dest_chain=chain_id,
            source_address=sender_addr or recipient, dest_address=recipient,
            amount=amount_a + amount_b, asset=token_a, intent_type="LIQUIDITY",
            deadline=int(time.time()) + 1800,
        )
        calldata = self.encode_intent(intent_dummy)
        gas_est = self.estimate_gas(intent_dummy)
        gas_dict = asdict(gas_est)
        gas_dict["gas_limit"] = 400_000  # Raydium LP ops are heavier

        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="liquidity", dry_run=dry_run, status="DRY_RUN",
            to_address=raydium_program, calldata=calldata, value=0,
            gas_estimate=gas_dict, rpc_used=rpc,
            metadata={"token_a": token_a, "token_b": token_b,
                      "amount_a": amount_a, "amount_b": amount_b,
                      "action": action, "recipient": recipient},
        )
        if dry_run:
            return result

        if not rpc:
            result.status = "FAILED"
            result.error = f"No public RPC known for chain_id={chain_id}"
            return result
        try:
            # Confirm Raydium program is live on this chain via getAccountInfo
            info = _RPCClient.jsonrpc(rpc, "getAccountInfo",
                                      [raydium_program, {"encoding": "base64"}])
            if isinstance(info, dict) and info.get("value"):
                result.metadata["raydium_program_live"] = True
                result.status = "SIMULATED"
            else:
                result.metadata["raydium_program_live"] = False
                result.status = "FAILED"
                result.error = "Raydium AMM program not found on this chain"
        except Exception as e:
            result.status = "FAILED"
            result.error = f"Solana RPC failure: {e}"
        return result

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


    # ── COSMOS EXECUTE METHODS (Osmosis pools + IBC + Bank) ─────────────────

    OSMOSIS_API = "https://lcd.osmosis.zone"

    def execute_swap(
        self,
        route_id: str,
        amount: int,
        token_in: str,
        token_out: str,
        recipient: str,
        chain_id: int = 10001,
        pool_id: int = 1,
        slippage_bps: int = 50,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute an Osmosis pool swap (MsgSwap).

        token_in / token_out are denoms (e.g. "uosmo", "uion", "ibc/...").
        DRY_RUN: builds the canonical MsgSwap JSON.
        dry_run=False: queries the Osmosis LCD for the live swap estimate.
        """
        rpc = _rpc_for_chain(chain_id, rpc_url)
        min_out = int(amount * (10_000 - slippage_bps) / 10_000)
        msg = {
            "@type": "/osmosis.poolmanager.v1beta1.MsgSwapExactAmountIn",
            "sender": sender_addr or recipient,
            "routes": [{"poolId": str(pool_id), "tokenOutDenom": token_out}],
            "tokenIn": {"denom": token_in, "amount": str(amount)},
            "tokenOutMinAmount": str(min_out),
        }
        calldata = "0x" + json.dumps(msg, separators=(",", ":")).encode().hex()

        gas_est = self.estimate_gas(BTCPIntent(
            source_chain=chain_id, dest_chain=chain_id,
            source_address=sender_addr or recipient, dest_address=recipient,
            amount=amount, asset=token_in, intent_type="SWAP",
            deadline=int(time.time()) + 1800,
        ))
        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="swap", dry_run=dry_run, status="DRY_RUN",
            to_address="osmosis-poolmanager", calldata=calldata, value=0,
            gas_estimate=asdict(gas_est), rpc_used=rpc,
            metadata={"pool_id": pool_id, "token_in": token_in,
                      "token_out": token_out, "recipient": recipient,
                      "min_out": min_out},
        )
        if dry_run:
            return result

        if not rpc:
            result.status = "FAILED"
            result.error = f"No public RPC known for chain_id={chain_id}"
            return result
        try:
            # Live swap estimate via Osmosis LCD
            lcd_url = (
                f"{self.OSMOSIS_API}/osmosis/poolmanager/v1beta1/{pool_id}/estimate/swap_exact_amount_in"
            )
            quote = _RPCClient.post_json(lcd_url, {
                "token_in": {"denom": token_in, "amount": str(amount)},
                "routes": [{"poolId": str(pool_id), "tokenOutDenom": token_out}],
            }, timeout=12.0)
            if isinstance(quote, dict):
                result.metadata["quote_out_amount"] = quote.get("token_out_amount")
            result.status = "SIMULATED"
        except Exception as e:
            result.status = "FAILED"
            result.error = f"Cosmos RPC failure: {e}"
        return result

    def execute_transfer(
        self,
        route_id: str,
        amount: int,
        token: str,
        recipient: str,
        chain_id: int = 10000,
        dest_chain_id: Optional[int] = None,
        ibc_channel: Optional[str] = None,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute a Cosmos Bank transfer or IBC transfer if dest_chain_id is set."""
        rpc = _rpc_for_chain(chain_id, rpc_url)
        sender = sender_addr or ("cosmos1" + "0" * 38)

        if dest_chain_id and ibc_channel:
            # IBC transfer (MsgTransfer)
            msg = {
                "@type": "/ibc.applications.transfer.v1.MsgTransfer",
                "source_port": "transfer",
                "source_channel": ibc_channel,
                "sender": sender,
                "receiver": recipient,
                "token": {"denom": token, "amount": str(amount)},
                "timeout_height": {"revision_height": "0"},
                "timeout_timestamp": str(int(time.time() * 1_000_000_000) + 600_000_000_000),
            }
            target = "ibc-channel"
        else:
            # Native bank send (same chain)
            msg = {
                "@type": "/cosmos.bank.v1beta1.MsgSend",
                "from_address": sender,
                "to_address": recipient,
                "amount": [{"denom": token, "amount": str(amount)}],
            }
            target = "cosmos-bank"

        calldata = "0x" + json.dumps(msg, separators=(",", ":")).encode().hex()
        gas_est = self.estimate_gas(BTCPIntent(
            source_chain=chain_id, dest_chain=dest_chain_id or chain_id,
            source_address=sender, dest_address=recipient,
            amount=amount, asset=token, intent_type="TRANSFER",
            deadline=int(time.time()) + 600,
        ))
        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="transfer", dry_run=dry_run, status="DRY_RUN",
            to_address=target, calldata=calldata, value=0,
            gas_estimate=asdict(gas_est), rpc_used=rpc,
            metadata={"token": token, "recipient": recipient,
                      "dest_chain_id": dest_chain_id,
                      "ibc_channel": ibc_channel},
        )
        if dry_run:
            return result

        if not rpc:
            result.status = "FAILED"
            result.error = f"No public RPC known for chain_id={chain_id}"
            return result
        try:
            # Tendermint /status liveness probe (works on every Cosmos RPC)
            status = _RPCClient.get_json(rpc.rstrip("/") + "/status", timeout=10.0)
            if isinstance(status, dict):
                result.metadata["latest_block_height"] = (
                    status.get("result", {}).get("sync_info", {}).get("latest_block_height")
                )
            result.status = "SIMULATED"
        except Exception as e:
            result.status = "FAILED"
            result.error = f"Cosmos RPC failure: {e}"
        return result

    def execute_liquidity(
        self,
        route_id: str,
        amount_a: int,
        amount_b: int,
        token_a: str,
        token_b: str,
        recipient: str,
        chain_id: int = 10001,
        pool_id: int = 1,
        action: str = "ADD",
        slippage_bps: int = 50,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Add or remove Osmosis GAMM liquidity (MsgJoinSwapExternAmountIn / MsgExitSwapShareAmountIn)."""
        rpc = _rpc_for_chain(chain_id, rpc_url)
        sender = sender_addr or ("osmo1" + "0" * 38)

        if action.upper() == "ADD":
            msg = {
                "@type": "/osmosis.gamm.v1beta1.MsgJoinSwapExternAmountIn",
                "sender": sender,
                "poolId": str(pool_id),
                "tokenIn": {"denom": token_a, "amount": str(amount_a)},
                "shareOutMinAmount": "1",
            }
        else:
            msg = {
                "@type": "/osmosis.gamm.v1beta1.MsgExitSwapShareAmountIn",
                "sender": sender,
                "poolId": str(pool_id),
                "tokenInDenom": token_a,
                "shareInAmount": str(amount_a),
                "tokenOutMinAmount": "1",
            }
        calldata = "0x" + json.dumps(msg, separators=(",", ":")).encode().hex()
        gas_est = self.estimate_gas(BTCPIntent(
            source_chain=chain_id, dest_chain=chain_id,
            source_address=sender, dest_address=recipient,
            amount=amount_a + amount_b, asset=token_a, intent_type="LIQUIDITY",
            deadline=int(time.time()) + 1800,
        ))
        gas_dict = asdict(gas_est)
        gas_dict["gas_limit"] = 500_000  # Osmosis LP ops are heavier
        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="liquidity", dry_run=dry_run, status="DRY_RUN",
            to_address="osmosis-gamm", calldata=calldata, value=0,
            gas_estimate=gas_dict, rpc_used=rpc,
            metadata={"pool_id": pool_id, "token_a": token_a, "token_b": token_b,
                      "amount_a": amount_a, "amount_b": amount_b,
                      "action": action, "recipient": recipient},
        )
        if dry_run:
            return result

        if not rpc:
            result.status = "FAILED"
            result.error = f"No public RPC known for chain_id={chain_id}"
            return result
        try:
            status = _RPCClient.get_json(rpc.rstrip("/") + "/status", timeout=10.0)
            if isinstance(status, dict):
                result.metadata["latest_block_height"] = (
                    status.get("result", {}).get("sync_info", {}).get("latest_block_height")
                )
            result.status = "SIMULATED"
        except Exception as e:
            result.status = "FAILED"
            result.error = f"Cosmos RPC failure: {e}"
        return result

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
        "sui": 20100,
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


    # ── MOVE EXECUTE METHODS (Aptos Liquidswap + aptos_account) ─────────────

    APTOS_API = "https://fullnode.mainnet.aptoslabs.com/v1"
    # Liquidswap (Pontem) mainnet resource account
    LIQUIDSWAP_MODULE = "0x190d442af2ab477c9480ae85006791d598a1b2d2c6539a4ad1f5e5f7e9b2a7d2"

    def execute_swap(
        self,
        route_id: str,
        amount: int,
        token_in: str,
        token_out: str,
        recipient: str,
        chain_id: int = 20000,
        slippage_bps: int = 50,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute an Aptos swap via the Liquidswap router.

        token_in / token_out are full CoinType addresses, e.g.
        "0x1::aptos_coin::AptosCoin".
        """
        rpc = _rpc_for_chain(chain_id, rpc_url) or self.APTOS_API
        min_out = str(int(amount * (10_000 - slippage_bps) / 10_000))
        sender = sender_addr or ("0x" + "00" * 31 + "01")

        # Move entry function payload:
        #   liquidswap::router::swap_exact_coin_for_coin<X,Y,L>(
        #       amount_in: u64, min_out: u64
        #   )
        payload = {
            "function": f"{self.LIQUIDSWAP_MODULE}::router::swap_exact_coin_for_coin",
            "type_arguments": [token_in, token_out,
                               "0x190d442af2ab477c9480ae85006791d598a1b2d2c6539a4ad1f5e5f7e9b2a7d2::curves::Uncorrelated"],
            "arguments": [str(amount), min_out],
            "type": "entry_function_payload",
        }
        calldata = "0x" + json.dumps(payload, separators=(",", ":")).encode().hex()

        gas_est = self.estimate_gas(BTCPIntent(
            source_chain=chain_id, dest_chain=chain_id,
            source_address=sender, dest_address=recipient,
            amount=amount, asset=token_in, intent_type="SWAP",
            deadline=int(time.time()) + 1800,
        ))
        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="swap", dry_run=dry_run, status="DRY_RUN",
            to_address=self.LIQUIDSWAP_MODULE, calldata=calldata, value=0,
            gas_estimate=asdict(gas_est), rpc_used=rpc,
            metadata={"token_in": token_in, "token_out": token_out,
                      "recipient": recipient, "min_out": min_out},
        )
        if dry_run:
            return result

        if not rpc:
            result.status = "FAILED"
            result.error = f"No public RPC known for chain_id={chain_id}"
            return result
        try:
            # Aptos REST: ledger/version liveness probe
            info = _RPCClient.get_json(rpc, timeout=10.0)
            if isinstance(info, dict):
                result.metadata["ledger_version"] = info.get("ledger_version")
                result.metadata["chain_id"] = info.get("chain_id")
            result.status = "SIMULATED"
        except Exception as e:
            result.status = "FAILED"
            result.error = f"Aptos RPC failure: {e}"
        return result

    def execute_transfer(
        self,
        route_id: str,
        amount: int,
        token: str,
        recipient: str,
        chain_id: int = 20000,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute an Aptos native Coin transfer (aptos_account::transfer)."""
        rpc = _rpc_for_chain(chain_id, rpc_url) or self.APTOS_API
        sender = sender_addr or ("0x" + "00" * 31 + "01")
        payload = {
            "function": "0x1::aptos_account::transfer",
            "type_arguments": [],
            "arguments": [recipient, str(amount)],
            "type": "entry_function_payload",
        }
        calldata = "0x" + json.dumps(payload, separators=(",", ":")).encode().hex()
        gas_est = self.estimate_gas(BTCPIntent(
            source_chain=chain_id, dest_chain=chain_id,
            source_address=sender, dest_address=recipient,
            amount=amount, asset=token, intent_type="TRANSFER",
            deadline=int(time.time()) + 600,
        ))
        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="transfer", dry_run=dry_run, status="DRY_RUN",
            to_address="0x1::aptos_account", calldata=calldata, value=0,
            gas_estimate=asdict(gas_est), rpc_used=rpc,
            metadata={"token": token, "recipient": recipient},
        )
        if dry_run:
            return result

        if not rpc:
            result.status = "FAILED"
            result.error = f"No public RPC known for chain_id={chain_id}"
            return result
        try:
            info = _RPCClient.get_json(rpc, timeout=10.0)
            if isinstance(info, dict):
                result.metadata["ledger_version"] = info.get("ledger_version")
            result.status = "SIMULATED"
        except Exception as e:
            result.status = "FAILED"
            result.error = f"Aptos RPC failure: {e}"
        return result

    def execute_liquidity(
        self,
        route_id: str,
        amount_a: int,
        amount_b: int,
        token_a: str,
        token_b: str,
        recipient: str,
        chain_id: int = 20000,
        action: str = "ADD",
        slippage_bps: int = 50,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Add or remove Liquidswap liquidity (mint or burn LP)."""
        rpc = _rpc_for_chain(chain_id, rpc_url) or self.APTOS_API
        sender = sender_addr or ("0x" + "00" * 31 + "01")
        if action.upper() == "ADD":
            func = f"{self.LIQUIDSWAP_MODULE}::router::add_liquidity"
            args = [str(amount_a), str(amount_b), "0", "0"]
        else:
            func = f"{self.LIQUIDSWAP_MODULE}::router::remove_liquidity"
            args = [str(amount_a), "0", "0"]  # amount_a = LP tokens to burn
        payload = {
            "function": func,
            "type_arguments": [token_a, token_b,
                               "0x190d442af2ab477c9480ae85006791d598a1b2d2c6539a4ad1f5e5f7e9b2a7d2::curves::Uncorrelated"],
            "arguments": args,
            "type": "entry_function_payload",
        }
        calldata = "0x" + json.dumps(payload, separators=(",", ":")).encode().hex()
        gas_est = self.estimate_gas(BTCPIntent(
            source_chain=chain_id, dest_chain=chain_id,
            source_address=sender, dest_address=recipient,
            amount=amount_a + amount_b, asset=token_a, intent_type="LIQUIDITY",
            deadline=int(time.time()) + 1800,
        ))
        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="liquidity", dry_run=dry_run, status="DRY_RUN",
            to_address=self.LIQUIDSWAP_MODULE, calldata=calldata, value=0,
            gas_estimate=asdict(gas_est), rpc_used=rpc,
            metadata={"token_a": token_a, "token_b": token_b,
                      "amount_a": amount_a, "amount_b": amount_b, "action": action},
        )
        if dry_run:
            return result
        try:
            info = _RPCClient.get_json(rpc, timeout=10.0)
            if isinstance(info, dict):
                result.metadata["ledger_version"] = info.get("ledger_version")
            result.status = "SIMULATED"
        except Exception as e:
            result.status = "FAILED"
            result.error = f"Aptos RPC failure: {e}"
        return result

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


    # ── COSMWASM EXECUTE METHODS (smart-contract ExecuteMsg + Bank) ─────────

    def execute_swap(
        self,
        route_id: str,
        amount: int,
        token_in: str,
        token_out: str,
        recipient: str,
        chain_id: int = 10002,
        dex_contract: Optional[str] = None,
        slippage_bps: int = 50,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute a CosmWasm swap by sending a Swap ExecuteMsg to a DEX contract
        (defaults to a generic Junoswap-style contract address provided by caller)."""
        rpc = _rpc_for_chain(chain_id, rpc_url)
        sender = sender_addr or ("juno1" + "0" * 38)
        contract = dex_contract or "juno1" + "0" * 38
        min_out = str(int(amount * (10_000 - slippage_bps) / 10_000))
        msg = {
            "swap": {
                "offer_asset": {"info": {"native_token": {"denom": token_in}},
                                "amount": str(amount)},
                "ask_asset":   {"info": {"native_token": {"denom": token_out}},
                                "amount": min_out},
                "belief_price": "1.0",
                "max_spread":   f"{slippage_bps / 10_000}",
                "to": recipient,
            }
        }
        # CosmWasm MsgExecuteContract
        full_msg = {
            "@type": "/cosmwasm.wasm.v1.MsgExecuteContract",
            "sender": sender,
            "contract": contract,
            "msg": msg,
            "funds": [{"denom": token_in, "amount": str(amount)}],
        }
        calldata = "0x" + json.dumps(full_msg, separators=(",", ":")).encode().hex()
        gas_est = self.estimate_gas(BTCPIntent(
            source_chain=chain_id, dest_chain=chain_id,
            source_address=sender, dest_address=recipient,
            amount=amount, asset=token_in, intent_type="SWAP",
            deadline=int(time.time()) + 1800,
        ))
        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="swap", dry_run=dry_run, status="DRY_RUN",
            to_address=contract, calldata=calldata, value=0,
            gas_estimate=asdict(gas_est), rpc_used=rpc,
            metadata={"dex_contract": contract, "token_in": token_in,
                      "token_out": token_out, "recipient": recipient},
        )
        if dry_run:
            return result

        if not rpc:
            result.status = "FAILED"
            result.error = f"No public RPC known for chain_id={chain_id}"
            return result
        try:
            status = _RPCClient.get_json(rpc.rstrip("/") + "/status", timeout=10.0)
            if isinstance(status, dict):
                result.metadata["latest_block_height"] = (
                    status.get("result", {}).get("sync_info", {}).get("latest_block_height")
                )
            result.status = "SIMULATED"
        except Exception as e:
            result.status = "FAILED"
            result.error = f"CosmWasm RPC failure: {e}"
        return result

    def execute_transfer(
        self,
        route_id: str,
        amount: int,
        token: str,
        recipient: str,
        chain_id: int = 10002,
        dest_chain_id: Optional[int] = None,
        ibc_channel: Optional[str] = None,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute a CosmWasm-chain bank send (or IBC if dest_chain_id given)."""
        rpc = _rpc_for_chain(chain_id, rpc_url)
        sender = sender_addr or ("juno1" + "0" * 38)
        if dest_chain_id and ibc_channel:
            msg = {
                "@type": "/ibc.applications.transfer.v1.MsgTransfer",
                "source_port": "transfer",
                "source_channel": ibc_channel,
                "sender": sender,
                "receiver": recipient,
                "token": {"denom": token, "amount": str(amount)},
                "timeout_height": {"revision_height": "0"},
                "timeout_timestamp": str(int(time.time() * 1_000_000_000) + 600_000_000_000),
            }
            target = "ibc-channel"
        else:
            msg = {
                "@type": "/cosmos.bank.v1beta1.MsgSend",
                "from_address": sender,
                "to_address": recipient,
                "amount": [{"denom": token, "amount": str(amount)}],
            }
            target = "cosmwasm-bank"
        calldata = "0x" + json.dumps(msg, separators=(",", ":")).encode().hex()
        gas_est = self.estimate_gas(BTCPIntent(
            source_chain=chain_id, dest_chain=dest_chain_id or chain_id,
            source_address=sender, dest_address=recipient,
            amount=amount, asset=token, intent_type="TRANSFER",
            deadline=int(time.time()) + 600,
        ))
        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="transfer", dry_run=dry_run, status="DRY_RUN",
            to_address=target, calldata=calldata, value=0,
            gas_estimate=asdict(gas_est), rpc_used=rpc,
            metadata={"token": token, "recipient": recipient,
                      "dest_chain_id": dest_chain_id, "ibc_channel": ibc_channel},
        )
        if dry_run:
            return result

        if not rpc:
            result.status = "FAILED"
            result.error = f"No public RPC known for chain_id={chain_id}"
            return result
        try:
            status = _RPCClient.get_json(rpc.rstrip("/") + "/status", timeout=10.0)
            if isinstance(status, dict):
                result.metadata["latest_block_height"] = (
                    status.get("result", {}).get("sync_info", {}).get("latest_block_height")
                )
            result.status = "SIMULATED"
        except Exception as e:
            result.status = "FAILED"
            result.error = f"CosmWasm RPC failure: {e}"
        return result

    def execute_liquidity(
        self,
        route_id: str,
        amount_a: int,
        amount_b: int,
        token_a: str,
        token_b: str,
        recipient: str,
        chain_id: int = 10002,
        pool_contract: Optional[str] = None,
        action: str = "ADD",
        slippage_bps: int = 50,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Add or remove CosmWasm LP via the pool contract\'s ExecuteMsg."""
        rpc = _rpc_for_chain(chain_id, rpc_url)
        sender = sender_addr or ("juno1" + "0" * 38)
        contract = pool_contract or "juno1" + "0" * 38
        if action.upper() == "ADD":
            inner = {
                "provide_liquidity": {
                    "assets": [
                        {"info": {"native_token": {"denom": token_a}}, "amount": str(amount_a)},
                        {"info": {"native_token": {"denom": token_b}}, "amount": str(amount_b)},
                    ],
                    "slippage_tolerance": f"{slippage_bps / 10_000}",
                }
            }
            funds = [{"denom": token_a, "amount": str(amount_a)},
                     {"denom": token_b, "amount": str(amount_b)}]
        else:
            inner = {
                "withdraw_liquidity": {
                    "amount": str(amount_a),
                }
            }
            funds = []
        full_msg = {
            "@type": "/cosmwasm.wasm.v1.MsgExecuteContract",
            "sender": sender,
            "contract": contract,
            "msg": inner,
            "funds": funds,
        }
        calldata = "0x" + json.dumps(full_msg, separators=(",", ":")).encode().hex()
        gas_est = self.estimate_gas(BTCPIntent(
            source_chain=chain_id, dest_chain=chain_id,
            source_address=sender, dest_address=recipient,
            amount=amount_a + amount_b, asset=token_a, intent_type="LIQUIDITY",
            deadline=int(time.time()) + 1800,
        ))
        gas_dict = asdict(gas_est)
        gas_dict["gas_limit"] = 500_000
        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="liquidity", dry_run=dry_run, status="DRY_RUN",
            to_address=contract, calldata=calldata, value=0,
            gas_estimate=gas_dict, rpc_used=rpc,
            metadata={"pool_contract": contract, "token_a": token_a, "token_b": token_b,
                      "amount_a": amount_a, "amount_b": amount_b, "action": action},
        )
        if dry_run:
            return result
        try:
            status = _RPCClient.get_json(rpc.rstrip("/") + "/status", timeout=10.0)
            if isinstance(status, dict):
                result.metadata["latest_block_height"] = (
                    status.get("result", {}).get("sync_info", {}).get("latest_block_height")
                )
            result.status = "SIMULATED"
        except Exception as e:
            result.status = "FAILED"
            result.error = f"CosmWasm RPC failure: {e}"
        return result

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


    # ── OOA EXECUTE METHODS (Sui DeepBook + pay::transfer) ──────────────────

    SUI_API = "https://full.mainnet.sui.io"

    def execute_swap(
        self,
        route_id: str,
        amount: int,
        token_in: str,
        token_out: str,
        recipient: str,
        chain_id: int = 20001,
        pool_id: Optional[str] = None,
        slippage_bps: int = 50,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute a Sui DeepBook pool swap.

        pool_id: DeepBook Pool object ID for the (token_in, token_out) pair.
        """
        rpc = _rpc_for_chain(chain_id, rpc_url) or self.SUI_API
        sender = sender_addr or ("0x" + "00" * 31 + "01")
        pool = pool_id or "0x" + "00" * 31 + "02"

        # Sui Move call: deepbook::pool::swap_exact_base_for_quote
        # (or swap_exact_quote_for_base) — args: pool, amount, min_out, deep
        payload = {
            "package": "0x2::sui",
            "module": "pay",
            "function": "split_join",
            "typeArguments": [],
            "arguments": [pool, str(amount), str(int(amount * (10_000 - slippage_bps) / 10_000))],
            "gasBudget": "100000000",
        }
        calldata = "0x" + json.dumps(payload, separators=(",", ":")).encode().hex()
        gas_est = self.estimate_gas(BTCPIntent(
            source_chain=chain_id, dest_chain=chain_id,
            source_address=sender, dest_address=recipient,
            amount=amount, asset=token_in, intent_type="SWAP",
            deadline=int(time.time()) + 1800,
        ))
        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="swap", dry_run=dry_run, status="DRY_RUN",
            to_address=pool, calldata=calldata, value=0,
            gas_estimate=asdict(gas_est), rpc_used=rpc,
            metadata={"token_in": token_in, "token_out": token_out,
                      "pool_id": pool, "recipient": recipient},
        )
        if dry_run:
            return result

        if not rpc:
            result.status = "FAILED"
            result.error = f"No public RPC known for chain_id={chain_id}"
            return result
        try:
            # Sui RPC: Sui_getLatestCheckpoint
            chk = _RPCClient.jsonrpc(rpc, "sui_getLatestCheckpoint")
            if isinstance(chk, dict):
                result.metadata["checkpoint"] = chk.get("checkpoint")
            elif isinstance(chk, str):
                result.metadata["checkpoint"] = chk
            result.status = "SIMULATED"
        except Exception as e:
            result.status = "FAILED"
            result.error = f"Sui RPC failure: {e}"
        return result

    def execute_transfer(
        self,
        route_id: str,
        amount: int,
        token: str,
        recipient: str,
        chain_id: int = 20001,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute a Sui pay::split / pay::join transfer (Coin object model)."""
        rpc = _rpc_for_chain(chain_id, rpc_url) or self.SUI_API
        sender = sender_addr or ("0x" + "00" * 31 + "01")
        payload = {
            "package": "0x2::sui",
            "module": "pay",
            "function": "transfer",
            "typeArguments": [],
            "arguments": [token, str(amount), recipient],
            "gasBudget": "100000000",
        }
        calldata = "0x" + json.dumps(payload, separators=(",", ":")).encode().hex()
        gas_est = self.estimate_gas(BTCPIntent(
            source_chain=chain_id, dest_chain=chain_id,
            source_address=sender, dest_address=recipient,
            amount=amount, asset=token, intent_type="TRANSFER",
            deadline=int(time.time()) + 600,
        ))
        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="transfer", dry_run=dry_run, status="DRY_RUN",
            to_address="0x2::pay", calldata=calldata, value=0,
            gas_estimate=asdict(gas_est), rpc_used=rpc,
            metadata={"token": token, "recipient": recipient},
        )
        if dry_run:
            return result

        if not rpc:
            result.status = "FAILED"
            result.error = f"No public RPC known for chain_id={chain_id}"
            return result
        try:
            chk = _RPCClient.jsonrpc(rpc, "sui_getLatestCheckpoint")
            if isinstance(chk, dict):
                result.metadata["checkpoint"] = chk.get("checkpoint")
            elif isinstance(chk, str):
                result.metadata["checkpoint"] = chk
            result.status = "SIMULATED"
        except Exception as e:
            result.status = "FAILED"
            result.error = f"Sui RPC failure: {e}"
        return result

    def execute_liquidity(
        self,
        route_id: str,
        amount_a: int,
        amount_b: int,
        token_a: str,
        token_b: str,
        recipient: str,
        chain_id: int = 20001,
        pool_id: Optional[str] = None,
        action: str = "ADD",
        slippage_bps: int = 50,
        dry_run: bool = True,
        rpc_url: Optional[str] = None,
        sender_pk: Optional[str] = None,
        sender_addr: Optional[str] = None,
    ) -> ExecutionResult:
        """Add or remove Sui DeepBook liquidity (deposit_base/withdraw)."""
        rpc = _rpc_for_chain(chain_id, rpc_url) or self.SUI_API
        sender = sender_addr or ("0x" + "00" * 31 + "01")
        pool = pool_id or "0x" + "00" * 31 + "02"
        if action.upper() == "ADD":
            payload = {
                "package": "0x2::deepbook",
                "module": "pool",
                "function": "deposit_base",
                "typeArguments": [token_a, token_b],
                "arguments": [pool, str(amount_a)],
                "gasBudget": "200000000",
            }
        else:
            payload = {
                "package": "0x2::deepbook",
                "module": "pool",
                "function": "withdraw_base",
                "typeArguments": [token_a, token_b],
                "arguments": [pool, str(amount_a)],
                "gasBudget": "200000000",
            }
        calldata = "0x" + json.dumps(payload, separators=(",", ":")).encode().hex()
        gas_est = self.estimate_gas(BTCPIntent(
            source_chain=chain_id, dest_chain=chain_id,
            source_address=sender, dest_address=recipient,
            amount=amount_a + amount_b, asset=token_a, intent_type="LIQUIDITY",
            deadline=int(time.time()) + 1800,
        ))
        result = ExecutionResult(
            route_id=route_id, vm_type=self.name, chain_id=chain_id,
            action="liquidity", dry_run=dry_run, status="DRY_RUN",
            to_address=pool, calldata=calldata, value=0,
            gas_estimate=asdict(gas_est), rpc_used=rpc,
            metadata={"pool_id": pool, "token_a": token_a, "token_b": token_b,
                      "amount_a": amount_a, "amount_b": amount_b, "action": action},
        )
        if dry_run:
            return result
        if not rpc:
            result.status = "FAILED"
            result.error = f"No public RPC known for chain_id={chain_id}"
            return result
        try:
            chk = _RPCClient.jsonrpc(rpc, "sui_getLatestCheckpoint")
            if isinstance(chk, dict):
                result.metadata["checkpoint"] = chk.get("checkpoint")
            elif isinstance(chk, str):
                result.metadata["checkpoint"] = chk
            result.status = "SIMULATED"
        except Exception as e:
            result.status = "FAILED"
            result.error = f"Sui RPC failure: {e}"
        return result

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
        """Get an adapter by chain ID.

        Unknown/unmapped chains resolve to the OOA (observation-only) adapter
        per BTCP spec §5.2 — non-integrated chains are anchored by observation
        at penalized confidence, NOT silently routed through the EVM adapter
        as if they were integrated EVM chains (the old default)."""
        cls._init_adapters()
        vm_type = CHAIN_VM_MAP.get(chain_id)
        if vm_type is None:
            return cls._adapters.get(VMType.OOA)
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
    'CHAIN_RPC_URLS',
    'BTCPIntent',
    'BTCPProof',
    'GasEstimate',
    'ExecutionResult',
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
