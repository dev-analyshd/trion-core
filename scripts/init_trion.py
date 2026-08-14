#!/usr/bin/env python3
"""
TRION Protocol — Full Engine Initialization
============================================

This script initializes and connects all TRION components:
  1. Core primitives (HashDNA, Resonance, Evolutionary Fitness)
  2. Five Planes (Physical Φ, Mental M, Spiritual Σ, Conscious K, ANIMA A)
  3. Coherence Engine C(t)
  4. Master Equation T(t)
  5. Akashic Index & BIBL Engine
  6. Security (Living Security, GK, Chameleon, PQC)
  7. BTCP Router
  8. Thermodynamic Engine
  9. Coordination Collapse Theorem

Usage:
  python3 scripts/init_trion.py [--test] [--verbose]
"""

import os
import sys
import time
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

# Add workspace to path
WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKSPACE)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("trion-init")


@dataclass
class ComponentStatus:
    name: str
    status: str = "PENDING"  # PENDING / LOADED / FAILED
    module: str = ""
    exports: List[str] = field(default_factory=list)
    error: Optional[str] = None
    load_time_ms: float = 0.0


class TRIONEngine:
    """
    Master TRION engine that initializes and connects all components.
    
    This is the single entry point for bringing the TRION protocol to life.
    It ensures every component is properly loaded, wired, and ready for use.
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.components: Dict[str, ComponentStatus] = {}
        self._engines: Dict[str, Any] = {}
        
    def load_component(self, name: str, module_path: str, required_exports: List[str]) -> bool:
        """Load a single component and verify its exports."""
        status = ComponentStatus(name=name, module=module_path)
        start = time.perf_counter()
        
        try:
            mod = __import__(module_path, fromlist=required_exports)
            
            # Verify exports exist
            for exp in required_exports:
                if not hasattr(mod, exp):
                    raise ImportError(f"Missing export: {exp}")
                status.exports.append(exp)
            
            status.status = "LOADED"
            status.load_time_ms = (time.perf_counter() - start) * 1000
            
            if self.verbose:
                logger.info(f"  ✓ {name}: loaded in {status.load_time_ms:.1f}ms")
                
        except Exception as e:
            status.status = "FAILED"
            status.error = str(e)
            status.load_time_ms = (time.perf_counter() - start) * 1000
            logger.error(f"  ✗ {name}: FAILED - {e}")
            
        self.components[name] = status
        return status.status == "LOADED"
    
    def initialize_all(self) -> Dict[str, Any]:
        """Initialize all TRION components in dependency order."""
        logger.info("=" * 60)
        logger.info("TRION PROTOCOL — FULL ENGINE INITIALIZATION")
        logger.info("=" * 60)
        
        results = {
            "loaded": 0,
            "failed": 0,
            "components": {},
            "total_time_ms": 0.0,
        }
        
        start_total = time.perf_counter()
        
        # ── Layer 1: Core Primitives ──────────────────────────────
        logger.info("\n📦 Layer 1: Core Primitives")
        self.load_component("HashDNA", "core.primitives.hash_dna", 
                          ["hash_dna", "hash_dna_hex", "HashDNAEvent", "build_event"])
        self.load_component("Resonance", "core.primitives.resonance",
                          ["compute_resonance_frequencies", "compute_channel_resonance", 
                           "can_communicate", "ResonanceResult"])
        self.load_component("Evolutionary Fitness", "core.primitives.evolutionary_fitness",
                          ["compute_fitness", "compute_pa", "compute_ice", "compute_love", 
                           "compute_adaptation_speed", "FitnessComponents"])
        self.load_component("Entity Resolution", "core.primitives.entity_resolution",
                          ["resolve_entity"])
        
        # ── Layer 2: Five Planes ─────────────────────────────────
        logger.info("\n🌌 Layer 2: Five Planes")
        self.load_component("Physical Plane Φ", "core.physical.phi_engine",
                          ["compute_phi", "TransactionData", "PHI_WEIGHTS"])
        self.load_component("Mental Plane M", "core.mental.confidence",
                          ["compute_m_score", "compute_prediction_interval", 
                           "compute_observer_effect", "compute_m_adj"])
        self.load_component("Spiritual Plane Σ", "core.spiritual.sigma_engine",
                          ["compute_sigma", "ValidatorSignal", "SIGMA_BOOTSTRAP"])
        self.load_component("Conscious Plane K", "core.spiritual.conscious.engine",
                          ["compute_k_score", "AnnotationReveal", "K_BOOTSTRAP",
                           "get_anti_capture_protections"])
        self.load_component("ANIMA Plane A", "core.mental.anima.engine",
                          ["ANIMAEngine", "compute_anima", "ANIMADistribution",
                           "HATracker", "SourceCredibility"])
        
        # ── Layer 3: Coherence & Master Equation ─────────────────
        logger.info("\n🎯 Layer 3: Coherence Engine")
        self.load_component("Coherence Engine C(t)", "core.master.coherence",
                          ["CoherenceEngine", "CoherenceInput", "AssetProfile"])
        self.load_component("Master Equation T(t)", "core.master.master_equation",
                          ["MasterEquation", "MasterEquationResult"])
        self.load_component("Economic Moat", "core.master.moat",
                          ["MoatEngine", "MoatInput"])
        # Dynamic threshold computed inside CoherenceEngine.compute_coherence()
        
        # ── Layer 4: Akashic Index ───────────────────────────────
        logger.info("\n📚 Layer 4: Akashic Index")
        self.load_component("Akashic Depth", "core.akashic.depth",
                          ["compute_akashic_depth", "bootstrap_weight", 
                           "is_bootstrap_phase", "depth_to_confidence"])
        self.load_component("BIBL Engine", "core.akashic.bibl",
                          ["BIBLEngine", "BIBLState", "BIBLOutput",
                           "classify_mempool_archetype"])
        self.load_component("Genesis Inference", "core.akashic.genesis",
                          ["genesis_confidence", "infer_genesis_value",
                           "Archetype", "GenesisFingerprint"])
        self.load_component("Resurrection", "core.akashic.resurrection",
                          ["compute_resurrection", "classify_dormancy", "ResurrectionScore", "DormancyProfile"])
        
        # ── Layer 5: Security ────────────────────────────────────
        logger.info("\n🔒 Layer 5: Security")
        self.load_component("Living Security", "core.spiritual.living_security.genomic_genealogy",
                          ["GenomicGenealogyGraph", "GenomicKeyNode"])
        self.load_component("PQC Layer", "core.spiritual.living_security.pqc_layer",
                          ["compute_sec", "compute_pqc_score", "compute_lss",
                           "PQCStatus", "SecurityScoreResult"])
        self.load_component("Chameleon Protocol", "core.novel.chameleon",
                          ["ChameleonProtocol", "ChameleonExpression", "ThreatLevel"])
        self.load_component("Coordination Collapse", "core.novel.coordination_collapse",
                          ["CoordinationCollapseTheorem", "compute_diversity_weights",
                           "compute_dw_bft_consensus"])
        
        # ── Layer 6: BTCP & Cross-Chain ─────────────────────────
        logger.info("\n🔀 Layer 6: BTCP Cross-Chain")
        self.load_component("BTCP Router", "core.btcp.router",
                          ["RouteType", "Route", "BIBLState", "btcp_score_final",
                           "select_optimal_route", "route_is_valid"])
        self.load_component("BTCP Integration", "core.btcp.integration",
                          ["BTCPIntegrationHub", "PrivateBIBLProtocol"])
        self.load_component("BTCP Escrow Monitor", "core.btcp.escrow_monitor",
                          ["EscrowMonitor"])
        
        # ── Layer 7: Thermodynamics ──────────────────────────────
        logger.info("\n🔥 Layer 7: Thermodynamic Engine")
        self.load_component("Thermodynamic Engine", "core.thermodynamics.thermo_engine",
                          ["ThermoEngine", "ThermoState", "get_thermo_engine"])
        self.load_component("Entropy Engine", "core.thermodynamics.entropy_engine",
                          ["BehavioralEntropyEngine", "get_entropy_engine", "shannon_entropy", "EntropyState"])
        
        # ── Layer 8: Temporal & Signal ───────────────────────────
        logger.info("\n⏱️  Layer 8: Temporal & Signal")
        self.load_component("Temporal Coherence", "core.physical.temporal_coherence",
                          ["compute_temporal_coherence", "SensorCalibration",
                           "TransductionIntegrityResult"])
        # Transduction integrity exported from core.physical.temporal_coherence
        self.load_component("Signal Factory", "core.master.signal_factory",
                          ["SignalType", "build_signal", "build_silence", "compute_brt", "build_manipulation_alert"])
        
        # ── Summary ──────────────────────────────────────────────
        total_time = (time.perf_counter() - start_total) * 1000
        loaded = sum(1 for c in self.components.values() if c.status == "LOADED")
        failed = sum(1 for c in self.components.values() if c.status == "FAILED")
        
        results["loaded"] = loaded
        results["failed"] = failed
        results["total_time_ms"] = total_time
        results["components"] = {
            name: {
                "status": c.status,
                "module": c.module,
                "exports": c.exports,
                "error": c.error,
                "load_time_ms": round(c.load_time_ms, 2),
            }
            for name, c in self.components.items()
        }
        
        logger.info("\n" + "=" * 60)
        logger.info(f"INITIALIZATION COMPLETE: {loaded} loaded, {failed} failed")
        logger.info(f"Total time: {total_time:.1f}ms")
        logger.info("=" * 60)
        
        if failed > 0:
            logger.warning("\nFailed components:")
            for name, c in self.components.items():
                if c.status == "FAILED":
                    logger.warning(f"  ✗ {name}: {c.error}")
        
        return results
    
    def run_self_test(self) -> Dict[str, Any]:
        """Run a comprehensive self-test of the entire engine."""
        logger.info("\n" + "=" * 60)
        logger.info("TRION ENGINE — SELF TEST")
        logger.info("=" * 60)
        
        test_results = {}
        
        try:
            import numpy as np
            
            # Test 1: Five planes → Coherence → Master Equation pipeline
            logger.info("\n🧪 Test 1: Full pipeline (Planes → C(t) → T(t))")
            from core.master.coherence import CoherenceEngine, CoherenceInput, AssetProfile
            from core.master.master_equation import MasterEquation
            
            engine = CoherenceEngine()
            me = MasterEquation()
            
            # Strong signal case
            coh_input = CoherenceInput(
                phi_adj=0.88, m_adj=0.82, sigma=0.75, k_plane=0.70, anima=0.78,
                volatility=0.15, akashic_depth=50000, moat_time=1e7,
                profile=AssetProfile.MATURE,
            )
            coh = engine.compute_coherence(coh_input)
            t_result = me.compute(coh)
            
            test_results["pipeline_strong"] = {
                "C": round(coh["C"], 4),
                "theta": round(coh["theta"], 4),
                "emits": coh["emits"],
                "T": round(t_result.t, 4),
                "moat": round(coh.get("moat_factor", 0), 4),
                "pass": coh["emits"] and t_result.t > 0,
            }
            logger.info(f"  Strong: C={coh['C']:.4f} Θ={coh['theta']:.4f} emits={coh['emits']} T={t_result.t:.4f}")
            
            # Weak signal case (should SILENCE)
            weak_input = CoherenceInput(
                phi_adj=0.15, m_adj=0.30, sigma=0.25, k_plane=0.10, anima=0.10,
                volatility=0.85, akashic_depth=50, moat_time=1e4,
                profile=AssetProfile.MATURE,
            )
            weak_coh = engine.compute_coherence(weak_input)
            weak_t = me.compute(weak_coh)
            
            test_results["pipeline_weak"] = {
                "C": round(weak_coh["C"], 4),
                "silence": weak_coh["silence"],
                "T": round(weak_t.t, 4),
                "pass": weak_coh["silence"] and weak_t.t == 0,
            }
            logger.info(f"  Weak:   C={weak_coh['C']:.4f} SILENCE={weak_coh['silence']} T={weak_t.t:.4f}")
            
            # Test 2: HashDNA dual-strand complementarity
            logger.info("\n🧪 Test 2: HashDNA dual-strand")
            from core.primitives.hash_dna import hash_dna, build_event
            
            event = build_event(
                entity_id="0xTestEntity123",
                event_type_id=1,  # TRANSFER
                raw_amount=int(1e18),
                asset_decimals=18,
                asset_chain_id=1,
                asset_address="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                asset_symbol="WETH",
                timestamp=int(time.time()),
                block_number=18000000,
                block_hash="0x" + "a" * 64,
                chain_id=1,
                contract_address="0x" + "b" * 40,
            )
            hd = hash_dna(event)
            sense = hd[:32]
            antisense = hd[32:64]
            
            # Verify complementarity: each bit position should be opposite
            xor_sum = sum(bin(s ^ a).count('1') for s, a in zip(sense, antisense))
            expected_xor = 32 * 8  # All bits should differ
            
            test_results["hashdna"] = {
                "sense_hex": sense.hex()[:16] + "...",
                "antisense_hex": antisense.hex()[:16] + "...",
                "complementary_bits": xor_sum,
                "expected_bits": expected_xor,
                "pass": xor_sum >= expected_xor * 0.95,
            }
            logger.info(f"  HashDNA: {xor_sum}/{expected_xor} complementary bits")
            
            # Test 3: Spiritual plane - Coordination Collapse
            logger.info("\n🧪 Test 3: Coordination Collapse Theorem")
            from core.novel.coordination_collapse import CoordinationCollapseTheorem
            
            bound = CoordinationCollapseTheorem.compute_collapse_bound(100, 0.33, 0.5)
            resistance = CoordinationCollapseTheorem.byzantine_resistance(1000.0, 330.0, 0.9)
            
            test_results["coordination_collapse"] = {
                "collapse_bound": round(bound, 6),
                "byzantine_safe": resistance["safe"],
                "effective_weight": round(resistance["effective_byzantine_weight"], 1),
                "pass": bound < 0.1 and resistance["safe"],
            }
            logger.info(f"  Collapse bound: {bound:.6f} (should be near 0)")
            logger.info(f"  Byzantine resistance: safe={resistance['safe']}")
            
            # Test 4: Living Security - Genomic Genealogy
            logger.info("\n🧪 Test 4: Genomic Genealogy")
            from core.spiritual.living_security.genomic_genealogy import GenomicGenealogyGraph
            import hashlib
            
            g = GenomicGenealogyGraph()
            genesis = g.register_genesis_key(
                "validator_alpha", 
                hashlib.sha3_256(b"genesis_key_alpha").digest(),
                block_number=0
            )
            
            depth = g.lineage_depth("validator_alpha")
            current = g.current_node("validator_alpha")
            
            test_results["genomic_genealogy"] = {
                "genesis_registered": genesis is not None,
                "lineage_depth": depth,
                "current_node_exists": current is not None,
                "pass": genesis is not None and current is not None,
            }
            logger.info(f"  Genesis key registered: depth={depth}, node={current is not None}")
            
            # Test 5: BIBL Engine
            logger.info("\n🧪 Test 5: BIBL Engine")
            from core.akashic.bibl import BIBLEngine, BIBLState
            
            bibl = BIBLEngine()
            state = BIBLState(
                current_block=18000000,
                block_time_ms=12000,
                mempool_size=150,
                mempool_fee_p50=10.0,
                mempool_fee_p95=50.0,
                volatility=0.25,
                nl_scores={"42161": 0.85, "1": 0.70},
                mev_rate_30d=0.05,
            )
            output = bibl.run_cycle(state, chain_id="42161")
            
            test_results["bibl"] = {
                "signal_type": output.signal_type,
                "archetype": output.archetype_code,
                "pass": output.signal_type is not None,
            }
            logger.info(f"  BIBL: signal={output.signal_type} archetype={output.archetype_code}")
            
            # Test 6: Evolutionary Fitness
            logger.info("\n🧪 Test 6: Evolutionary Fitness")
            from core.primitives.evolutionary_fitness import compute_fitness, compute_pa, compute_ice
            
            pa = compute_pa([0.7, 0.8, 0.75], [0.72, 0.78, 0.76])
            ice = compute_ice(0.05, 0.01)
            fitness = compute_fitness("trion_core", pa, ice, adaptation_speed=0.8, love=0.9)
            
            test_results["evolutionary_fitness"] = {
                "pa": round(pa, 4),
                "ice": round(ice, 4),
                "pass": 0 <= pa <= 1 and ice > 0,
            }
            logger.info(f"  PA={pa:.4f} ICE={ice:.4f}")
            
            # Overall pass rate
            all_passed = sum(1 for t in test_results.values() if t.get("pass", False))
            total_tests = len(test_results)
            test_results["_summary"] = {
                "passed": all_passed,
                "total": total_tests,
                "pass_rate": f"{all_passed}/{total_tests}",
            }
            
            logger.info(f"\n{'='*60}")
            logger.info(f"SELF TEST: {all_passed}/{total_tests} PASSED")
            logger.info(f"{'='*60}")
            
        except Exception as e:
            logger.error(f"Self test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            test_results["_error"] = str(e)
        
        return test_results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TRION Protocol Engine Initialization")
    parser.add_argument("--test", action="store_true", help="Run self-test after initialization")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()
    
    engine = TRIONEngine(verbose=args.verbose)
    init_results = engine.initialize_all()
    
    if args.test:
        test_results = engine.run_self_test()
        init_results["self_test"] = test_results
    
    if args.json:
        print(json.dumps(init_results, indent=2, default=str))
    
    return 0 if init_results["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
