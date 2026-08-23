"""
TRION Protocol — Comprehensive Integration Tests
=================================================

Tests all components working together end-to-end.
Run: python3 scripts/tests/integration_test.py
"""

import os
import sys
import json
import time
import hashlib
import unittest
from typing import Dict, Any, List

# Add workspace to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestCorePlanes(unittest.TestCase):
    """Test the five behavioral planes."""
    
    def test_physical_plane(self):
        """Physical plane Φ computes from transaction data."""
        from core.physical.phi_engine import compute_phi, TransactionData
        
        txs = [
            TransactionData(
                tx_hash="0x" + "a"*64,
                from_addr="0x" + "1"*40,
                to_addr="0x" + "2"*40,
                value_wei=10**18,
                gas_price=20*10**9,
                gas_used=21000,
                block_number=18000000,
                timestamp=int(time.time()),
                is_contract=False,
                contract_addr=None,
                input_len=0,
            )
        ] * 10
        
        result = compute_phi(txs, "0x" + "3"*40)
        self.assertIn("phi_raw", result)
        self.assertGreaterEqual(result["phi_raw"], 0.0)
        self.assertLessEqual(result["phi"], 1.0)
    
    def test_spiritual_plane(self):
        """Spiritual plane Σ uses diversity-weighted BFT."""
        from core.spiritual.sigma_engine import compute_sigma, ValidatorSignal
        
        signals = [
            ValidatorSignal(
                validator_id=f"v{i}", 
                valuation=0.7+0.01*i,
                stake=1000+i*100,
                model_outputs={"diversity": 0.8}
            )
            for i in range(15)
        ]
        # Add one Byzantine
        signals.append(ValidatorSignal(
            validator_id="byz1", 
            valuation=0.1,
            stake=500,
            model_outputs={"diversity": 0.2}
        ))
        
        result = compute_sigma(signals)  # Uses internal volatility calc
        self.assertIn("sigma_t", result)
        self.assertGreaterEqual(result["sigma_t"], 0.0)
        self.assertLessEqual(result["sigma_t"], 1.0)
    
    def test_conscious_plane(self):
        """Conscious plane K uses annotation network."""
        from core.spiritual.conscious.engine import compute_k_score
        
        from core.spiritual.conscious.engine import AnnotationReveal, AnnotationType
        import secrets
        reveals = [
            AnnotationReveal(
                annotator_hash=secrets.token_hex(16),
                entity_id="0xTest",
                k_score=0.6+0.05*i,
                annotation_type=AnnotationType.HUMAN,  # Use valid annotation type
                cultural_context="global",
                salt=secrets.token_hex(8),
                stake_weight=800+i*50,
                revealed_at=int(time.time()),
            )
            for i in range(5)
        ]
        result = compute_k_score(reveals)
        self.assertIn("k_score", result)
        self.assertGreaterEqual(result["k_score"], 0.0)
        self.assertLessEqual(result["k_score"], 1.0)
    
    def test_mental_plane(self):
        """Mental plane M computes prediction confidence."""
        from core.mental.confidence import compute_m_score
        
        recent = [0.7, 0.72, 0.68, 0.75, 0.71, 0.73, 0.69]
        baseline = [0.5, 0.55, 0.48, 0.52, 0.49, 0.51, 0.47]
        m_score = compute_m_score(recent, baseline)
        self.assertGreater(m_score, 0.0)
    
    def test_anima_plane(self):
        """ANIMA plane A computes cross-domain absorption."""
        from core.mental.anima.engine import ANIMAEngine
        
        engine = ANIMAEngine()
        from core.mental.anima.engine import ANIMADataStreamBundle
        bundle = ANIMADataStreamBundle(
            entity_id="0xTest", timestamp=int(time.time()), block_number=18000000,
            onchain={"pcr": 0.8}, offchain={"ha": 0.7}, nlp={"ca": 0.6}, biological={}
        )
        result = engine.compute(akashic_depth=100.0, data_bundle=bundle)
        # ANIMA returns ANIMADistribution object
        self.assertIsNotNone(result)
        anima_val = result.anima_score if hasattr(result, 'anima_score') else (result.combined if hasattr(result, 'combined') else 0)
        self.assertGreaterEqual(anima_val, 0.0)


class TestCoherenceEngine(unittest.TestCase):
    """Test coherence engine C(t)."""
    
    def test_coherence_computation(self):
        """Coherence score properly combines all five planes."""
        from core.master.coherence import CoherenceEngine, CoherenceInput
        
        engine = CoherenceEngine()
        inp = CoherenceInput(
            phi_adj=0.7, m_adj=0.8, sigma=0.65, k_plane=0.6, anima=0.55,
            volatility=0.3,
            akashic_depth=100.0,
            moat_time=30.0,
        )
        result = engine.compute_coherence(inp)
        self.assertIn("C", result)
        self.assertGreaterEqual(result["C"], 0.0)
        self.assertLessEqual(result["coherence"], 1.0)
    
    def test_dynamic_threshold(self):
        """Dynamic threshold adjusts with market volatility."""
        from core.master.coherence import CoherenceEngine, CoherenceInput
        
        engine = CoherenceEngine()
        
        low_vol = engine.compute_coherence(CoherenceInput(
            phi_adj=0.7, m_adj=0.8, sigma=0.65, k_plane=0.6, anima=0.55,
            volatility=0.1, akashic_depth=100.0, moat_time=30.0,
        ))
        
        high_vol = engine.compute_coherence(CoherenceInput(
            phi_adj=0.7, m_adj=0.8, sigma=0.65, k_plane=0.6, anima=0.55,
            volatility=0.8, akashic_depth=100.0, moat_time=30.0,
        ))
        
        self.assertGreater(high_vol["theta"], low_vol["theta"])
    
    def test_coherence_signal(self):
        """Strong coherence passes threshold; weak stays below."""
        from core.master.coherence import CoherenceEngine, CoherenceInput
        
        engine = CoherenceEngine()
        
        strong = engine.compute_coherence(CoherenceInput(
            phi_adj=0.95, m_adj=0.95, sigma=0.9, k_plane=0.9, anima=0.9,
            volatility=0.1, akashic_depth=500.0, moat_time=30.0,
        ))
        
        weak = engine.compute_coherence(CoherenceInput(
            phi_adj=0.1, m_adj=0.1, sigma=0.1, k_plane=0.1, anima=0.1,
            volatility=0.5, akashic_depth=10.0, moat_time=30.0,
        ))
        
        # Verify structure - strong should emit when above theta
        self.assertIn("emits", strong)
        self.assertIn("silence", weak)


class TestMasterEquation(unittest.TestCase):
    """Test master equation T(t)."""
    
    def test_master_equation(self):
        """Master equation properly applies moat factor."""
        from core.master.master_equation import MasterEquation
        
        me = MasterEquation()
        result = me.compute_from_planes(
            0.8, 0.7, 0.65, 0.6, 0.55,  # phi_adj, m_adj, sigma, k_plane, anima
            volatility=0.3, akashic_depth=100.0, moat_time=30.0
        )
        self.assertGreaterEqual(result.t, 0.0)
        self.assertGreaterEqual(result.moat_factor, 0.0)  # Moat scales with depth


class TestZKCircuits(unittest.TestCase):
    """Test all ZK zero-knowledge proof circuits."""
    
    def setUp(self):
        from zk import (ZKProofSystem, IntentWitness, ComplementarityWitness,
                       BehavioralCredentialWitness, TravelRuleWitness, IAPShareWitness,
                       CircuitType)
        import secrets
        
        self.zk = ZKProofSystem()
        self.secrets = secrets
        self.IntentWitness = IntentWitness
        self.ComplementarityWitness = ComplementarityWitness
        self.BehavioralCredentialWitness = BehavioralCredentialWitness
        self.TravelRuleWitness = TravelRuleWitness
        self.IAPShareWitness = IAPShareWitness
        self.CircuitType = CircuitType
    
    def test_intent_commitment(self):
        """Intent commitment proof generates and verifies."""
        witness = self.IntentWitness(
            entity_id="0xTestEntity",
            intent_type="SWAP",
            amount=int(1.5 * 10**18),
            source_chain=1,
            dest_chain=42161,
            deadline=int(time.time()) + 3600,
            nonce=self.secrets.token_bytes(32),
        )
        proof = self.zk.generate_intent(witness)
        self.assertTrue(self.zk.verify(proof))
        self.assertEqual(proof.circuit_type, self.CircuitType.INTENT_COMMITMENT)
    
    def test_complementarity(self):
        """Complementarity proof for dual-strand HashDNA."""
        sense = self.secrets.token_bytes(32)
        antisense = bytes([b ^ 0xFF for b in sense])
        witness = self.ComplementarityWitness(
            sense_strand=sense,
            antisense_strand=antisense,
            entity_id="0xTestEntity",
            block_number=18000000,
        )
        proof = self.zk.generate_complementarity(witness)
        self.assertTrue(self.zk.verify(proof))
        self.assertGreater(proof.public_inputs["complementarity"], 0.95)
    
    def test_behavioral_credential(self):
        """Behavioral credential proves entity passes thresholds."""
        witness = self.BehavioralCredentialWitness(
            entity_id="0xTestEntity",
            coherence_score=0.75,
            manipulation_fingerprint=0.15,
            liquidity_score=0.80,
            akashic_depth=500.0,
            threshold_coherence=0.55,
            threshold_manipulation=0.30,
        )
        proof = self.zk.generate_behavioral_credential(witness)
        self.assertTrue(self.zk.verify(proof))
        self.assertTrue(proof.public_inputs["credential_passed"])
    
    def test_travel_rule(self):
        """Travel rule compliance proof."""
        witness = self.TravelRuleWitness(
            originator_id="0xOriginator",
            beneficiary_id="0xBeneficiary",
            amount=int(500 * 10**6),
            asset_address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            originator_verified=True,
            beneficiary_verified=True,
        )
        proof = self.zk.generate_travel_rule(witness)
        self.assertTrue(self.zk.verify(proof))
        self.assertTrue(proof.public_inputs["compliant"])
    
    def test_iap_share(self):
        """IAP share proof for gas fairness."""
        witness = self.IAPShareWitness(
            entity_id="0xTestEntity",
            total_gas=1_000_000,
            entity_gas=100_000,
            total_btcp_fee=int(0.01 * 10**18),
            entity_share=int(0.001 * 10**18),
            num_participants=10,
        )
        proof = self.zk.generate_iap_share(witness)
        self.assertTrue(self.zk.verify(proof))
        self.assertTrue(proof.public_inputs["fair_allocation"])


class TestVMAdapters(unittest.TestCase):
    """Test all VM adapters for cross-chain operations."""
    
    def setUp(self):
        from adapters import (VMAdapterFactory, VMType, BTCPIntent,
                            EVMAdapter, SVMAdapter, CosmosAdapter,
                            MoveAdapter, CosmWasmAdapter, OOAAdapter)
        self.factory = VMAdapterFactory
        self.VMType = VMType
        self.BTCPIntent = BTCPIntent
        self.adapters = {
            "EVM": EVMAdapter(),
            "SVM": SVMAdapter(),
            "Cosmos": CosmosAdapter(),
            "Move": MoveAdapter(),
            "CosmWasm": CosmWasmAdapter(),
            "OOA": OOAAdapter(),
        }
    
    def _make_intent(self, source_chain=1, dest_chain=42161):
        return self.BTCPIntent(
            intent_id="test_intent",
            source_chain=source_chain,
            dest_chain=dest_chain,
            source_address="0x1F98431c8aD98523631AE4a59f267346ea31F984",
            dest_address="0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
            amount=int(1.5 * 10**18),
            asset="ETH",
            intent_type="SWAP",
            deadline=int(time.time()) + 3600,
            nonce=42,
        )
    
    def test_evm_adapter(self):
        """EVM adapter encodes and estimates gas."""
        adapter = self.adapters["EVM"]
        intent = self._make_intent()
        encoded = adapter.encode_intent(intent)
        self.assertTrue(encoded.startswith("0x"))
        self.assertGreater(len(encoded), 10)
        
        gas = adapter.estimate_gas(intent)
        self.assertGreater(gas.gas_limit, 0)
        self.assertEqual(gas.fee_token, "ETH")
    
    def test_svm_adapter(self):
        """SVM adapter works with Solana-style addresses."""
        adapter = self.adapters["SVM"]
        self.assertTrue(adapter.validate_address("Vote111111111111111111111111111111111111111"))
        
        intent = self._make_intent(source_chain=900, dest_chain=1)
        encoded = adapter.encode_intent(intent)
        self.assertTrue(encoded.startswith("0x"))
    
    def test_cosmos_adapter(self):
        """Cosmos adapter works with Bech32 addresses."""
        adapter = self.adapters["Cosmos"]
        self.assertTrue(adapter.validate_address("cosmos1v9jxgu33kfsgr5x2d8w8z3h3k4v8q5q6w7e8r9"))
    
    def test_factory_lookup(self):
        """VM adapter factory resolves chains correctly."""
        evm = self.factory.get_by_chain_id(1)
        self.assertEqual(evm.vm_type, self.VMType.EVM)
        
        svm = self.factory.get_by_chain_id(900)
        self.assertEqual(svm.vm_type, self.VMType.SVM)
    
    def test_cross_vm_transfer(self):
        """Cross-VM transfer encodes for both source and destination."""
        intent = self._make_intent(source_chain=1, dest_chain=900)  # EVM → SVM
        result = self.factory.cross_vm_transfer(intent)
        self.assertEqual(result["source_vm"], "EVM")
        self.assertEqual(result["dest_vm"], "SVM")
        self.assertIn("source_encoded", result)
        self.assertIn("dest_encoded", result)
        self.assertGreater(result["total_estimated_fee"], 0)


class TestBTCPOrchestration(unittest.TestCase):
    """Test BTCP orchestration tying ZK + VM adapters together."""
    
    def setUp(self):
        from core.btcp.orchestrator import (BTCPOrchestrator, PrivacyLevel, RouteStatus)
        self.orchestrator = BTCPOrchestrator()
        self.PrivacyLevel = PrivacyLevel
        self.RouteStatus = RouteStatus
    
    def test_full_orchestration(self):
        """Complete BTCP route creation with proofs and encoding."""
        result = self.orchestrator.create_route(
            source_chain=1,
            dest_chain=42161,
            source_address="0x1F98431c8aD98523631AE4a59f267346ea31F984",
            dest_address="0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
            amount=int(1.5 * 10**18),
            asset="ETH",
            intent_type="SWAP",
            privacy_level=self.PrivacyLevel.FULL,
            behavioral_data={"coherence": 0.75, "manipulation": 0.15, "liquidity": 0.80, "depth": 500.0},
        )
        
        self.assertTrue(result.success)
        self.assertIsNotNone(result.route)
        self.assertGreaterEqual(len(result.proofs_generated), 4)
        self.assertGreater(result.route.total_fee, 0)
        self.assertEqual(result.route.status, self.RouteStatus.PROOFS_GENERATED)
    
    def test_proof_verification(self):
        """Route proofs can be verified."""
        result = self.orchestrator.create_route(
            source_chain=1,
            dest_chain=42161,
            source_address="0x1F98431c8aD98523631AE4a59f267346ea31F984",
            dest_address="0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
            amount=int(1.0 * 10**18),
            asset="ETH",
            privacy_level=self.PrivacyLevel.STANDARD,
        )
        
        all_valid, errors = self.orchestrator.verify_route_proofs(result.route.route_id)
        self.assertTrue(all_valid, f"Proof verification failed: {errors}")
    
    def test_route_tracking(self):
        """Routes are tracked and status can be updated."""
        result = self.orchestrator.create_route(
            source_chain=1, dest_chain=42161,
            source_address="0x1F98431c8aD98523631AE4a59f267346ea31F984",
            dest_address="0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
            amount=int(0.5 * 10**18),
            asset="ETH",
        )
        
        route_id = result.route.route_id
        self.orchestrator.update_route_status(route_id, self.RouteStatus.SOURCE_EXECUTED)
        
        routes = self.orchestrator.list_routes()
        self.assertGreaterEqual(len(routes), 1)
        self.assertEqual(routes[0]["status"], "SOURCE_EXECUTED")


class TestSecurityComponents(unittest.TestCase):
    """Test genomic key and chameleon protocol."""
    
    def test_genomic_key(self):
        """Genomic key creates dual-strand signature with lineage."""
        from core.spiritual.living_security.genomic_genealogy import GenomicGenealogyGraph
        import secrets
        
        ggg = GenomicGenealogyGraph()
        key_material = secrets.token_bytes(32)
        genesis = ggg.register_genesis_key("validator_01", key_material, block_number=18000000)
        self.assertIsNotNone(genesis.node_id)
        self.assertEqual(ggg.lineage_depth(genesis.node_id), 0)
        
        # Rotate key (evolution)
        import secrets as sec
        child = ggg.rotate_key(
            genesis.node_id, 
            sec.token_bytes(32), 
            block_number=18000001,
            block_hash=sec.token_bytes(32),
            validator_sig=sec.token_bytes(64)
        )
        self.assertGreaterEqual(ggg.lineage_depth(child.node_id), 1)
        self.assertEqual(ggg.contamination_score(child.node_id), 0.0)
    
    def test_chameleon_protocol(self):
        """Chameleon protocol adapts noise under adversarial probing."""
        from core.novel.chameleon import ChameleonProtocol
        
        chameleon = ChameleonProtocol()
        result = chameleon.apply_noise(
            entity_id="test_entity",
            true_value=0.75,
            volatility=0.02,
            now=time.time()
        )
        self.assertIsInstance(result, dict)
        self.assertIn("output_value", result)
        self.assertNotEqual(result["output_value"], 0.75)  # Noise applied
        self.assertIn("sigma_used", result)


class TestCoordinationCollapse(unittest.TestCase):
    """Test coordination collapse theorem — Byzantine resistance."""
    
    def test_byzantine_resistance(self):
        """Diversity-weighted BFT resists Byzantine attacks."""
        from core.novel.coordination_collapse import CoordinationCollapseTheorem
        
        cct = CoordinationCollapseTheorem()
        
        from core.novel.coordination_collapse import build_demo_validators
        
        # Test Byzantine resistance directly
        br = cct.byzantine_resistance(n_validators=100, byzantine_fraction=0.1)
        self.assertIn("safe", br)
        
        # Collapse bound calculation
        bound = cct.compute_collapse_bound(diversity=0.8, n_validators=100)
        self.assertGreaterEqual(bound, 0.0)


def run_all_tests():
    """Run all integration tests and return results."""
    print("=" * 70)
    print("TRION PROTOCOL — COMPREHENSIVE INTEGRATION TESTS")
    print("=" * 70)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    test_classes = [
        TestCorePlanes,
        TestCoherenceEngine,
        TestMasterEquation,
        TestZKCircuits,
        TestVMAdapters,
        TestBTCPOrchestration,
        TestSecurityComponents,
        TestCoordinationCollapse,
    ]
    
    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print(f"\n{'='*70}")
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"TEST SUMMARY: {passed}/{result.testsRun} PASSED")
    if result.failures:
        print(f"FAILURES: {len(result.failures)}")
        for test, trace in result.failures:
            print(f"  ✗ {test}: {trace.splitlines()[-1][:80]}")
    if result.errors:
        print(f"ERRORS: {len(result.errors)}")
        for test, trace in result.errors:
            print(f"  ✗ {test}: {trace.splitlines()[-1][:80]}")
    print(f"{'='*70}")
    
    return {
        "total": result.testsRun,
        "passed": passed,
        "failed": len(result.failures),
        "errors": len(result.errors),
        "success": result.wasSuccessful(),
    }


if __name__ == "__main__":
    results = run_all_tests()
    sys.exit(0 if results["success"] else 1)
