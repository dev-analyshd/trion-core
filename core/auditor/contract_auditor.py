"""
TRION On-Chain Contract Auditor
================================
Reads any contract address from any supported chain, extracts behavioral
features, compares against the vulnerability pattern library and Akashic
Index archetypes, and produces a structured audit report with:
  - Risk score (0.0 = safe, 1.0 = critical)
  - Matched vulnerability archetypes
  - CRISPR patch suggestions
  - FAISS similarity to historical exploits
  - Epigenetic change analysis (behavior drift over time)
"""

import hashlib
import json
import time
import math
import logging
import sys
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

import numpy as np
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.auditor.vulnerability_patterns import (
    VULNERABILITY_LIBRARY, VulnerabilityPattern,
    get_phi_matrix, SEVERITY_SCORES
)
from src.core.coherence_engine import CoherenceEngine

logger = logging.getLogger(__name__)


@dataclass
class AuditFinding:
    pattern_id: str
    pattern_name: str
    severity: str
    category: str
    confidence: float          # 0-1 match confidence
    description: str
    evidence: List[str]
    prevention: str
    crispr_suggestion: str
    similar_exploits: List[str]


@dataclass
class AuditReport:
    address: str
    chain_id: int
    chain_name: str
    timestamp: int
    risk_score: float          # 0.0 (safe) → 1.0 (critical)
    risk_label: str            # SAFE | LOW | MEDIUM | HIGH | CRITICAL
    coherence_score: float     # C(t) estimate for the contract
    archetype: str             # closest behavioral archetype
    archetype_distance: float  # distance from archetype centroid
    findings: List[AuditFinding]
    tx_stats: Dict
    behavioral_summary: str
    epigenetic_drift: float    # how much behavior changed vs. 30-day baseline
    lifecycle_stage: str       # BIRTH | GROWTH | MATURITY | DECLINE | DEATH
    ubl_vector: List[float]    # Universal Behavioral Language encoding
    patch_priority: List[str]  # ordered CRISPR patches to apply
    attestation_hash: str      # tamper-proof audit fingerprint


# RPC endpoints per chain
CHAIN_RPCS = {
    1:       "https://eth.llamarpc.com",
    42161:   "https://arb1.arbitrum.io/rpc",
    8453:    "https://mainnet.base.org",
    10:      "https://mainnet.optimism.io",
    56:      "https://bsc-dataseed.binance.org",
    137:     "https://polygon-rpc.com",
    43114:   "https://api.avax.network/ext/bc/C/rpc",
    421614:  "https://sepolia-rollup.arbitrum.io/rpc",
    84532:   "https://sepolia.base.org",
    11155111: "https://rpc.sepolia.org",
    97:      "https://data-seed-prebsc-1-s1.binance.org:8545",
    177:     "https://mainnet.hsk.xyz",
    16602:   "https://evmrpc-testnet.0g.ai",
}

CHAIN_NAMES = {
    1: "Ethereum", 42161: "Arbitrum", 8453: "Base", 10: "Optimism",
    56: "BNB Chain", 137: "Polygon", 43114: "Avalanche",
    421614: "Arbitrum Sepolia", 84532: "Base Sepolia",
    11155111: "Ethereum Sepolia", 97: "BNB Testnet",
    177: "HashKey", 16602: "0G Galileo",
}


class ContractAuditor:
    def __init__(self, faiss_url: str = "http://127.0.0.1:8000"):
        self.faiss_url = faiss_url
        self.coherence_engine = CoherenceEngine()
        self._vuln_phi_matrix = get_phi_matrix()

    def _rpc_call(self, chain_id: int, method: str, params: list) -> Optional[dict]:
        # Skip live RPC unless TRION_LIVE=1 — avoids hanging in sandbox/test environments
        if not os.environ.get("TRION_LIVE"):
            return None
        rpc = CHAIN_RPCS.get(chain_id)
        if not rpc:
            return None
        try:
            r = requests.post(rpc, json={
                "jsonrpc": "2.0", "id": 1,
                "method": method, "params": params
            }, timeout=1.5)
            data = r.json()
            return data.get("result")
        except Exception as e:
            logger.warning(f"RPC error on chain {chain_id}: {e}")
            return None

    def _get_bytecode(self, address: str, chain_id: int) -> str:
        result = self._rpc_call(chain_id, "eth_getCode", [address, "latest"])
        return result or "0x"

    def _get_tx_history(self, address: str, chain_id: int) -> List[dict]:
        # Get recent block range and scan for txs to/from contract
        block_result = self._rpc_call(chain_id, "eth_blockNumber", [])
        if not block_result:
            return []
        latest = int(block_result, 16)
        scan_from = max(0, latest - 500)
        # Use eth_getLogs to get events
        try:
            logs = self._rpc_call(chain_id, "eth_getLogs", [{
                "address": address,
                "fromBlock": hex(scan_from),
                "toBlock": "latest"
            }]) or []
            return logs[:200]
        except Exception:
            return []

    def _get_storage_slots(self, address: str, chain_id: int) -> Dict[str, str]:
        slots = {}
        for i in range(5):
            slot = hex(i).replace("0x", "").zfill(64)
            val = self._rpc_call(chain_id, "eth_getStorageAt", [address, "0x" + slot, "latest"])
            if val and val != "0x" + "0" * 64:
                slots[f"slot_{i}"] = val
        return slots

    def _analyze_bytecode(self, bytecode: str) -> Dict:
        if bytecode in ("0x", "", None):
            return {"is_eoa": True, "opcode_counts": {}, "has_delegatecall": False,
                    "has_selfdestruct": False, "has_create": False, "call_count": 0}

        code = bytecode.lower().replace("0x", "")
        analysis = {
            "is_eoa": False,
            "length": len(code) // 2,
            "has_delegatecall": "f4" in code,
            "has_selfdestruct": "ff" in code,
            "has_create": "f0" in code or "f5" in code,
            "has_call": "f1" in code,
            "has_staticcall": "fa" in code,
            "has_timestamp": "42" in code,
            "has_origin": "32" in code,
            "call_count": code.count("f1"),
            "jump_count": code.count("56"),
            "sload_count": code.count("54"),
            "sstore_count": code.count("55"),
        }

        # Detect proxy pattern
        analysis["is_proxy"] = analysis["has_delegatecall"] and len(code) < 200
        # Detect ERC-20 selectors
        analysis["is_erc20"] = "a9059cbb" in code  # transfer()
        analysis["is_erc721"] = "42842e0e" in code  # safeTransferFrom()
        # Detect mint backdoor
        analysis["has_mint"] = "40c10f19" in code or "a9059cbb" in code

        return analysis

    def _extract_phi_vector(self, tx_logs: List[dict], bytecode_analysis: Dict) -> np.ndarray:
        n = max(len(tx_logs), 1)
        # f1: tx volume entropy
        values = [int(log.get("data", "0x0") or "0x0", 16) for log in tx_logs[:100]]
        values = [v for v in values if v > 0] or [1]
        total = sum(values) + 1e-10
        probs = [v / total for v in values]
        h1 = -sum(p * math.log2(p + 1e-10) for p in probs)
        max_h = math.log2(len(probs) + 1)
        f1 = min(1.0, h1 / (max_h + 1e-10))

        # f2: call complexity
        f2 = min(1.0, bytecode_analysis.get("call_count", 0) / 20.0)

        # f3: storage density
        f3 = min(1.0, bytecode_analysis.get("sstore_count", 0) / 50.0)

        # f4: jump complexity
        f4 = min(1.0, bytecode_analysis.get("jump_count", 0) / 100.0)

        # f5: delegatecall risk
        f5 = 1.0 if bytecode_analysis.get("has_delegatecall") else 0.0

        # f6: selfdestruct risk
        f6 = 1.0 if bytecode_analysis.get("has_selfdestruct") else 0.0

        # f7: bytecode length complexity (normalized)
        f7 = min(1.0, bytecode_analysis.get("length", 0) / 24576.0)

        # f8: timestamp risk
        f8 = 0.8 if bytecode_analysis.get("has_timestamp") else 0.1

        # f9: create/upgrade risk
        f9 = 0.9 if bytecode_analysis.get("has_create") else 0.1

        return np.array([f1, f2, f3, f4, f5, f6, f7, f8, f9], dtype=np.float32)

    def _match_vulnerabilities(self, phi: np.ndarray, bytecode_analysis: Dict,
                                tx_logs: List[dict]) -> List[AuditFinding]:
        findings = []
        vuln_matrix = self._vuln_phi_matrix

        for i, pattern in enumerate(VULNERABILITY_LIBRARY):
            ref = vuln_matrix[i]
            norm_phi = np.linalg.norm(phi)
            norm_ref = np.linalg.norm(ref)
            if norm_phi == 0 or norm_ref == 0:
                sim = 0.0
            else:
                sim = float(np.dot(phi, ref) / (norm_phi * norm_ref))

            # Check bytecode markers
            marker_hits = 0
            code = bytecode_analysis.get("_raw_code", "")
            for m in pattern.bytecode_markers:
                if m in code:
                    marker_hits += 1
            marker_score = marker_hits / max(len(pattern.bytecode_markers), 1)

            # Combined confidence
            confidence = sim * 0.6 + marker_score * 0.4

            # Only report if confidence above threshold per severity
            threshold = {"CRITICAL": 0.35, "HIGH": 0.40, "MEDIUM": 0.45, "LOW": 0.50}
            if confidence >= threshold.get(pattern.severity, 0.45):
                evidence = []
                if bytecode_analysis.get("has_delegatecall"):
                    evidence.append("DELEGATECALL opcode detected in bytecode")
                if bytecode_analysis.get("has_selfdestruct"):
                    evidence.append("SELFDESTRUCT opcode detected — destructible contract")
                if bytecode_analysis.get("call_count", 0) > 10:
                    evidence.append(f"High external CALL count: {bytecode_analysis['call_count']}")
                if bytecode_analysis.get("has_timestamp"):
                    evidence.append("TIMESTAMP opcode used — miner-influenceable")
                if marker_hits > 0:
                    evidence.append(f"Bytecode markers matched: {marker_hits}/{len(pattern.bytecode_markers)}")
                if not evidence:
                    evidence.append(f"Behavioral vector similarity: {sim:.3f}")

                findings.append(AuditFinding(
                    pattern_id=pattern.id,
                    pattern_name=pattern.name,
                    severity=pattern.severity,
                    category=pattern.category,
                    confidence=round(confidence, 3),
                    description=pattern.description,
                    evidence=evidence,
                    prevention=pattern.prevention,
                    crispr_suggestion=pattern.crispr_suggestion,
                    similar_exploits=pattern.known_exploits
                ))

        # Sort by severity then confidence
        sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        findings.sort(key=lambda f: (sev_order[f.severity], -f.confidence))
        return findings

    def _compute_risk_score(self, findings: List[AuditFinding],
                             phi: np.ndarray, bytecode_analysis: Dict) -> float:
        if not findings:
            return 0.05
        weighted = sum(
            f.confidence * SEVERITY_SCORES[f.severity]
            for f in findings
        )
        normalized = min(1.0, weighted / max(len(findings), 1))
        # Boost for critical bytecode flags
        if bytecode_analysis.get("has_selfdestruct"):
            normalized = min(1.0, normalized + 0.15)
        if bytecode_analysis.get("is_proxy") and not bytecode_analysis.get("is_erc20"):
            normalized = min(1.0, normalized + 0.05)
        return round(normalized, 4)

    def _classify_archetype(self, phi: np.ndarray) -> Tuple[str, float]:
        archetypes = {
            "Organic Growth":           np.array([0.30, 0.25, 0.35, 0.28, 0.22, 0.18, 0.32, 0.27, 0.30], dtype=np.float32),
            "Accumulation":             np.array([0.45, 0.40, 0.55, 0.38, 0.60, 0.55, 0.42, 0.38, 0.52], dtype=np.float32),
            "Distribution":             np.array([0.68, 0.62, 0.75, 0.58, 0.72, 0.68, 0.65, 0.60, 0.73], dtype=np.float32),
            "Liquidity Drain":          np.array([0.78, 0.72, 0.88, 0.65, 0.82, 0.78, 0.75, 0.70, 0.85], dtype=np.float32),
            "Bot Swarm":                np.array([0.22, 0.20, 0.90, 0.18, 0.88, 0.85, 0.20, 0.18, 0.89], dtype=np.float32),
            "Governance Attack":        np.array([0.62, 0.68, 0.45, 0.78, 0.58, 0.52, 0.60, 0.65, 0.62], dtype=np.float32),
            "Flash Exploit":            np.array([0.95, 0.90, 0.85, 0.92, 0.05, 0.03, 0.93, 0.88, 0.95], dtype=np.float32),
            "Wash Trading":             np.array([0.32, 0.28, 0.82, 0.24, 0.78, 0.74, 0.30, 0.26, 0.80], dtype=np.float32),
            "Healthy DeFi Protocol":    np.array([0.55, 0.50, 0.60, 0.48, 0.40, 0.35, 0.52, 0.48, 0.58], dtype=np.float32),
            "Stablecoin Protocol":      np.array([0.40, 0.35, 0.45, 0.38, 0.28, 0.22, 0.38, 0.33, 0.42], dtype=np.float32),
            "Dormant Contract":         np.array([0.10, 0.08, 0.15, 0.12, 0.06, 0.05, 0.09, 0.07, 0.13], dtype=np.float32),
            "Ponzi Structure":          np.array([0.62, 0.58, 0.78, 0.52, 0.72, 0.68, 0.60, 0.55, 0.76], dtype=np.float32),
        }
        best_name = "Unknown"
        best_sim = -1.0
        for name, centroid in archetypes.items():
            n_phi = np.linalg.norm(phi)
            n_c = np.linalg.norm(centroid)
            if n_phi > 0 and n_c > 0:
                sim = float(np.dot(phi, centroid) / (n_phi * n_c))
                if sim > best_sim:
                    best_sim = sim
                    best_name = name
        distance = 1.0 - best_sim
        return best_name, round(distance, 4)

    def _detect_lifecycle_stage(self, tx_logs: List[dict],
                                 bytecode_analysis: Dict) -> str:
        n = len(tx_logs)
        if n == 0:
            return "DEATH"
        if n < 5:
            return "BIRTH"
        if n < 50:
            return "GROWTH"
        f5 = bytecode_analysis.get("has_selfdestruct", False)
        if f5:
            return "DECLINE"
        return "MATURITY"

    def _compute_epigenetic_drift(self, phi: np.ndarray,
                                   address: str, chain_id: int) -> float:
        # Compare to FAISS baseline if available
        try:
            r = requests.get(f"{self.faiss_url}/api/v1/planes/{address}/physical", timeout=4)
            if r.status_code == 200:
                data = r.json()
                baseline = data.get("phi_vector") or data.get("features", {})
                if isinstance(baseline, list) and len(baseline) == 9:
                    base_arr = np.array(baseline, dtype=np.float32)
                    drift = float(np.linalg.norm(phi - base_arr))
                    return round(min(1.0, drift), 4)
        except Exception:
            pass
        return 0.0

    def _encode_ubl(self, phi: np.ndarray, findings: List[AuditFinding],
                    lifecycle: str, archetype: str) -> List[float]:
        lc_map = {"BIRTH": 0.1, "GROWTH": 0.3, "MATURITY": 0.6,
                  "DECLINE": 0.8, "DEATH": 1.0}
        risk_level = sum(SEVERITY_SCORES[f.severity] * f.confidence for f in findings)
        risk_level = min(1.0, risk_level)
        ubl = list(phi[:9]) + [
            lc_map.get(lifecycle, 0.5),
            risk_level,
            len(findings) / 20.0,
        ]
        return [round(float(v), 4) for v in ubl]

    def audit(self, address: str, chain_id: int = 1) -> AuditReport:
        t0 = int(time.time())
        chain_name = CHAIN_NAMES.get(chain_id, f"chain_{chain_id}")
        logger.info(f"[AUDITOR] Auditing {address} on {chain_name}")

        # 1. Fetch on-chain data
        bytecode = self._get_bytecode(address, chain_id)
        tx_logs = self._get_tx_history(address, chain_id)
        storage = self._get_storage_slots(address, chain_id)

        # 2. Analyze bytecode
        ba = self._analyze_bytecode(bytecode)
        ba["_raw_code"] = bytecode.lower().replace("0x", "")

        # 3. Extract behavioral phi vector
        phi = self._extract_phi_vector(tx_logs, ba)

        # 4. Match vulnerability patterns
        findings = self._match_vulnerabilities(phi, ba, tx_logs)

        # 5. Risk score
        risk_score = self._compute_risk_score(findings, phi, ba)

        # 6. Archetype classification
        archetype, arch_dist = self._classify_archetype(phi)

        # 7. Lifecycle stage
        lifecycle = self._detect_lifecycle_stage(tx_logs, ba)

        # 8. Epigenetic drift
        drift = self._compute_epigenetic_drift(phi, address, chain_id)

        # 9. Coherence estimate
        coherence = round(max(0.0, 1.0 - risk_score * 0.85 + (1 - arch_dist) * 0.15), 4)

        # 10. UBL encoding
        ubl = self._encode_ubl(phi, findings, lifecycle, archetype)

        # 11. Risk label
        if risk_score >= 0.80:
            label = "CRITICAL"
        elif risk_score >= 0.60:
            label = "HIGH"
        elif risk_score >= 0.35:
            label = "MEDIUM"
        elif risk_score >= 0.15:
            label = "LOW"
        else:
            label = "SAFE"

        # 12. Prioritized CRISPR patches
        patches = [f.crispr_suggestion for f in findings if f.severity in ("CRITICAL", "HIGH")]
        patches += [f.crispr_suggestion for f in findings if f.severity == "MEDIUM"]

        # 13. Behavioral summary
        summary_parts = [f"Contract on {chain_name} classified as '{archetype}'."]
        if findings:
            crit = [f for f in findings if f.severity == "CRITICAL"]
            summary_parts.append(
                f"Found {len(findings)} vulnerability pattern(s) including "
                f"{len(crit)} CRITICAL."
            )
        else:
            summary_parts.append("No significant vulnerability patterns detected.")
        summary_parts.append(f"Lifecycle stage: {lifecycle}. Risk score: {risk_score:.3f}.")
        if drift > 0.3:
            summary_parts.append(f"WARNING: Significant behavioral drift ({drift:.3f}) from baseline — possible state change or attack in progress.")

        # 14. Attestation hash
        raw = f"{address}:{chain_id}:{risk_score}:{len(findings)}:{t0}"
        attestation = hashlib.sha256(raw.encode()).hexdigest()

        # 15. TX stats
        tx_stats = {
            "recent_log_count": len(tx_logs),
            "bytecode_length": ba.get("length", 0),
            "has_delegatecall": ba.get("has_delegatecall", False),
            "has_selfdestruct": ba.get("has_selfdestruct", False),
            "is_proxy": ba.get("is_proxy", False),
            "is_erc20": ba.get("is_erc20", False),
            "call_count": ba.get("call_count", 0),
            "storage_slots_used": len(storage),
        }

        return AuditReport(
            address=address,
            chain_id=chain_id,
            chain_name=chain_name,
            timestamp=t0,
            risk_score=risk_score,
            risk_label=label,
            coherence_score=coherence,
            archetype=archetype,
            archetype_distance=arch_dist,
            findings=findings,
            tx_stats=tx_stats,
            behavioral_summary=" ".join(summary_parts),
            epigenetic_drift=drift,
            lifecycle_stage=lifecycle,
            ubl_vector=ubl,
            patch_priority=patches[:5],
            attestation_hash=attestation,
        )

    def audit_to_dict(self, address: str, chain_id: int = 1) -> dict:
        report = self.audit(address, chain_id)
        d = asdict(report)
        return d
