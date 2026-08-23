"""
TRION Protocol — Signal Packing for On-Chain Publication

Implements the 256-bit thermodynamic signal encoding specified in the whitepaper:

  bits [0..7]    status       (1=NOMINAL, 2=WARN, 3=COLLAPSE, 4=HOSTILE)
  bits [8..39]   coherence    (C(t) × 1e6, 32 bits)
  bits [40..71]  threshold    (Θ(t) × 1e6, 32 bits)
  bits [72..135] blockNumber  (64 bits)
  bits [136..199] timestamp    (64 bits)
  bits [200..255] plane_code   (limiting plane + flags, 56 bits)

Also provides helpers for the rich BehavioralSignal publication format.
"""

import time
import hashlib
from typing import Dict, Optional, Tuple

# Signal status codes
STATUS_NOMINAL = 1
STATUS_WARN = 2
STATUS_COLLAPSE = 3
STATUS_HOSTILE = 4

# Plane indices (matching contract and ChainRelay)
PLANE_PHYSICAL = 0
PLANE_MENTAL = 1
PLANE_SPIRITUAL = 2
PLANE_CONSCIOUS = 3
PLANE_ANIMA = 4

PLANE_NAMES = {
    PLANE_PHYSICAL: "Physical",
    PLANE_MENTAL: "Mental",
    PLANE_SPIRITUAL: "Spiritual",
    PLANE_CONSCIOUS: "Conscious",
    PLANE_ANIMA: "ANIMA",
}

# Scaling factor for fixed-point encoding (× 1e6)
SCALE = 1_000_000


def to_fixed(value: float, scale: int = SCALE) -> int:
    """Convert float to fixed-point integer."""
    return int(round(value * scale))


def from_fixed(value: int, scale: int = SCALE) -> float:
    """Convert fixed-point integer back to float."""
    return value / scale


def pack_signal(
    coherence: float,
    threshold: float,
    block_number: int,
    timestamp: Optional[int] = None,
    status: Optional[int] = None,
    limiting_plane: int = PLANE_PHYSICAL,
) -> int:
    """
    Pack a thermodynamic signal into a single uint256 per whitepaper spec.

    Args:
        coherence: C(t) coherence score [0, 1]
        threshold: Θ(t) dynamic threshold [0, 1]
        block_number: Ethereum block number
        timestamp: Unix timestamp (defaults to now)
        status: Signal status (1=NOMINAL, etc. — auto-detected if None)
        limiting_plane: Which plane limits coherence (0-4)

    Returns:
        uint256 packed integer
    """
    if timestamp is None:
        timestamp = int(time.time())

    # Auto-determine status from coherence vs threshold
    if status is None:
        if coherence >= threshold:
            status = STATUS_NOMINAL
        elif coherence >= threshold * 0.8:
            status = STATUS_WARN
        elif coherence >= threshold * 0.5:
            status = STATUS_COLLAPSE
        else:
            status = STATUS_HOSTILE

    c_fixed = to_fixed(coherence) & 0xFFFFFFFF  # 32 bits
    t_fixed = to_fixed(threshold) & 0xFFFFFFFF  # 32 bits
    blk = int(block_number) & 0xFFFFFFFFFFFFFFFF  # 64 bits
    ts = int(timestamp) & 0xFFFFFFFFFFFFFFFF     # 64 bits

    # Plane code: 8 bits plane + 48 bits reserved
    plane_code = (limiting_plane & 0xFF)

    packed = (
        (status & 0xFF)
        | (c_fixed << 8)
        | (t_fixed << 40)
        | (blk << 72)
        | (ts << 136)
        | (plane_code << 200)
    )

    return packed


def unpack_signal(packed: int) -> Dict:
    """
    Unpack a uint256 thermodynamic signal into its components.

    Returns:
        Dict with keys: status, coherence, threshold, block_number,
                        timestamp, limiting_plane
    """
    status = packed & 0xFF
    coherence = from_fixed((packed >> 8) & 0xFFFFFFFF)
    threshold = from_fixed((packed >> 40) & 0xFFFFFFFF)
    block_number = (packed >> 72) & 0xFFFFFFFFFFFFFFFF
    timestamp = (packed >> 136) & 0xFFFFFFFFFFFFFFFF
    limiting_plane = (packed >> 200) & 0xFF

    return {
        "status": status,
        "coherence": coherence,
        "threshold": threshold,
        "block_number": block_number,
        "timestamp": timestamp,
        "limiting_plane": limiting_plane,
        "limiting_plane_name": PLANE_NAMES.get(limiting_plane, f"Unknown({limiting_plane})"),
    }


def public_commitment(entity_id: str, coherence: float, timestamp: int) -> bytes:
    """
    Generate a public commitment hash for on-chain publication.
    Does NOT leak behavioral content — only proves the signal existed.
    """
    # Quantize timestamp to 5-minute windows for privacy
    quantized_ts = timestamp // 300
    payload = f"{entity_id}:{coherence:.6f}:{quantized_ts}".encode()
    return hashlib.sha256(payload).digest()


def entity_to_bytes32(entity_id: str) -> bytes:
    """Convert entity_id string to bytes32 for Solidity."""
    raw = entity_id.encode()
    if len(raw) <= 32:
        return raw + b'\x00' * (32 - len(raw))
    return hashlib.sha256(raw).digest()


def determine_limiting_plane(
    phi: float, mental: float, sigma: float, conscious: float, anima: float
) -> Tuple[int, str]:
    """
    Determine which plane is the limiting factor (lowest score).
    Returns (plane_index, plane_name).
    """
    planes = [
        (PLANE_PHYSICAL, phi, "Physical"),
        (PLANE_MENTAL, mental, "Mental"),
        (PLANE_SPIRITUAL, sigma, "Spiritual"),
        (PLANE_CONSCIOUS, conscious, "Conscious"),
        (PLANE_ANIMA, anima, "ANIMA"),
    ]
    planes.sort(key=lambda x: x[1])
    return planes[0][0], planes[0][2]


def prepare_behavioral_signal(
    entity_id: str,
    coherence: float,
    threshold: float,
    moat_factor: float,
    phi: float,
    mental: float,
    sigma: float,
    conscious: float,
    anima: float,
    block_number: Optional[int] = None,
    timestamp: Optional[int] = None,
) -> Dict:
    """
    Prepare a full behavioral signal for on-chain publication via
    publishBehavioralSignal().

    Returns dict ready for contract call parameters.
    """
    if timestamp is None:
        timestamp = int(time.time())

    coherent = coherence >= threshold
    limiting_plane_idx, limiting_plane_name = determine_limiting_plane(
        phi, mental, sigma, conscious, anima
    )
    commitment = public_commitment(entity_id, coherence, timestamp)
    entity_b32 = entity_to_bytes32(entity_id)

    return {
        "entity_id": entity_id,
        "entity_id_bytes32": entity_b32,
        "public_commitment": commitment,
        "coherence_score": to_fixed(coherence),
        "threshold": to_fixed(threshold),
        "moat_factor": to_fixed(moat_factor),
        "coherent": coherent,
        "limiting_plane": limiting_plane_idx,
        "limiting_plane_name": limiting_plane_name,
        "phi_plane": to_fixed(phi) & 0xFFFFFFFFFFFFFFFF,
        "mental_plane": to_fixed(mental) & 0xFFFFFFFFFFFFFFFF,
        "sigma_plane": to_fixed(sigma) & 0xFFFFFFFFFFFFFFFF,
        "conscious_plane": to_fixed(conscious) & 0xFFFFFFFFFFFFFFFF,
        "anima_plane": to_fixed(anima) & 0xFFFFFFFFFFFFFFFF,
        "block_number": block_number,
        "timestamp": timestamp,
        "packed_legacy": pack_signal(
            coherence=coherence,
            threshold=threshold,
            block_number=block_number or 0,
            timestamp=timestamp,
            limiting_plane=limiting_plane_idx,
        ),
    }
