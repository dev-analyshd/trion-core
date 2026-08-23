#!/usr/bin/env python3
"""
Generate src/ compatibility shim that re-exports from core/.
This allows existing `from src.core.coherence_engine import X` to work
after the move to `core/master/coherence.py`.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Mapping: old src path → new core path (module-level)
SHIM_MAP = {
    # src/core/ → various core/ subdirs
    "src/core/behavioral_hash":           "core/primitives/behavioral_hash",
    "src/core/entity_resolution":         "core/primitives/entity_resolution",
    "src/core/resonance":                 "core/primitives/resonance",
    "src/core/information_conservation":  "core/primitives/thermodynamics",
    "src/core/evolutionary_fitness":      "core/primitives/evolutionary_fitness",
    "src/core/temporal_coherence":        "core/physical/temporal_coherence",
    "src/core/self_verification":         "core/physical/transduction_integrity",
    "src/core/coherence_engine":         "core/master/coherence",
    "src/core/moat_engine":              "core/master/moat",
    "src/core/consensus_degradation":    "core/master/degradation",
    "src/core/channel_architecture":     "core/master/channel_architecture",
    "src/core/trion_primitives":         "core/master/trion_primitives",
    "src/core/d_engine":                 "core/master/d_engine",
    "src/core/homomorphic_mapping":      "core/master/homomorphic_mapping",
    "src/core/btcp_score":               "core/master/btcp_score",
    "src/core/bibl":                     "core/akashic/bibl",
    "src/core/bibl_pattern_store":       "core/akashic/bibl_pattern_store",
    "src/core/genesis_inference":        "core/akashic/genesis",
    "src/core/mental_transformer":       "core/akashic/mental_transformer",

    # src/planes/physical/ → core/physical/ + core/akashic/ + core/extended/
    "src/planes/physical/phi_engine":     "core/physical/phi_engine",
    "src/planes/physical/akashic_depth":  "core/akashic/depth",
    "src/planes/physical/resurrection":   "core/akashic/resurrection",
    "src/planes/physical/fork_resolution":"core/akashic/fork_resolution",
    "src/planes/physical/trajectory_anomaly":"core/akashic/trajectory_anomaly",
    "src/planes/physical/nl_engine":      "core/extended/natural_liquidity",
    "src/planes/physical/xsl_engine":     "core/extended/xsl_engine",

    # src/planes/mental/ → core/mental/
    "src/planes/mental/m_engine":         "core/mental/confidence",
    "src/planes/mental/intelligence_maintenance":"core/mental/intelligence_maintenance",

    # src/planes/anima/ → core/mental/anima/
    "src/planes/anima/anima_engine":      "core/mental/anima/engine",
    "src/planes/anima/anima_data_streams": "core/mental/anima/data_streams",
    "src/planes/anima/anima_pattern_library":"core/mental/anima/pattern_library",
    "src/planes/anima/anima_reflexivity":  "core/mental/anima/reflexivity",
    "src/planes/anima/source_credibility": "core/mental/anima/source_credibility",

    # src/planes/conscious/ → core/spiritual/conscious/
    "src/planes/conscious/k_engine":      "core/spiritual/conscious/engine",
    "src/planes/conscious/indigenous_knowledge":"core/spiritual/conscious/indigenous_knowledge",

    # src/planes/spiritual/ → core/spiritual/
    "src/planes/spiritual/sigma_engine":  "core/spiritual/sigma_engine",
    "src/planes/spiritual/hhi_monitor":   "core/spiritual/hhi_monitor",
    "src/planes/spiritual/slashing":      "core/spiritual/slashing",
    "src/planes/spiritual/epigenetic":    "core/spiritual/epigenetic",
    "src/planes/spiritual/consensus_degradation":"core/spiritual/consensus_degradation",

    # src/planes/extended/ → core/extended/
    "src/planes/extended/biological_capital":"core/extended/biological_capital",
    "src/planes/extended/sba":            "core/extended/sovereign_behavioral",
    "src/planes/extended/xsl":            "core/extended/cross_species",
    "src/planes/extended/energy_participation":"core/extended/energy_participation",

    # src/manipulation/ → core/physical/
    "src/manipulation/fingerprint_detector":"core/physical/manipulation_detector",

    # src/signals/ → core/master/ + core/novel/
    "src/signals/signal_factory":         "core/master/signal_factory",
    "src/signals/birp":                   "core/novel/birp",
    "src/signals/behavioral_identity_recovery":"core/novel/behavioral_identity_recovery",

    # src/security/ → core/spiritual/living_security/ + core/novel/
    "src/security/living_security":       "core/spiritual/living_security",
    "src/security/pqc_layer":             "core/spiritual/living_security/pqc_layer",
    "src/security/genomic_genealogy":     "core/spiritual/living_security/genomic_genealogy",
    "src/security/chameleon_protocol":    "core/novel/chameleon",

    # src/governance/ → core/governance/
    "src/governance/awa_state":           "core/governance/awa",
    "src/governance/falsifiability_registry":"core/governance/falsifiability_registry",
    "src/governance/intelligence_maintenance":"core/governance/intelligence_maintenance",
    "src/governance/open_research_questions":"core/governance/open_research_questions",
    "src/governance/sba_engine":          "core/governance/sba_engine",
    "src/governance/slashing":            "core/governance/slashing",

    # src/consensus/ → core/spiritual/
    "src/consensus/diversity_weighted_bft":"core/spiritual/consensus",

    # src/akashic/ → core/akashic/
    "src/akashic/archetypes":             "core/akashic/archetype",
    "src/akashic/epigenetics":            "core/akashic/epigenetics",

    # Other modules — same path in core/
    "src/agent/safety_pipeline":          "core/agent/safety_pipeline",
    "src/auditor/contract_auditor":       "core/auditor/contract_auditor",
    "src/auditor/vulnerability_patterns": "core/auditor/vulnerability_patterns",
    "src/trading/signal_engine":          "core/trading/signal_engine",
    "src/trading/pattern_archetypes":     "core/trading/pattern_archetypes",
    "src/trading/agent_interface":        "core/trading/agent_interface",
    "src/trading/live_feed":              "core/trading/live_feed",
    "src/trading/market_data":            "core/trading/market_data",
    "src/investment/investment_engine":   "core/investment/investment_engine",
    "src/lifecycle/entity_lifecycle":     "core/lifecycle/entity_lifecycle",
    "src/reputation/reputation_engine":   "core/reputation/reputation_engine",
    "src/price/behavioral_price_engine":  "core/price/behavioral_price_engine",
    "src/thermodynamics/entropy_engine":  "core/thermodynamics/entropy_engine",
    "src/thermodynamics/thermo_engine":   "core/thermodynamics/thermo_engine",
    "src/ubl/ubl":                        "core/ubl/ubl",
    "src/protocol/distribution_coherence":"core/protocol/distribution_coherence",
    "src/protocol/protocol_health":       "core/protocol/protocol_health",
    "src/protocol/role_classifier":       "core/protocol/role_classifier",
    "src/protocol/segmentation":          "core/protocol/segmentation",
    "src/api/routes":                     "core/api/routes",
    "src/native_bridge":                  "core/native_bridge",
}

def main():
    os.chdir(ROOT)
    count = 0
    for old_path, new_path in SHIM_MAP.items():
        # Convert module path to file path
        old_file = old_path.replace(".", "/") + ".py"
        new_file = new_path.replace(".", "/") + ".py"

        # The shim file re-exports everything from the new location
        new_module = new_path.replace("/", ".")
        shim_content = f'''"""Compatibility shim — re-exports from {new_module}."""
# This file exists so `from {old_path.replace("/", ".")} import X` still works
# after the restructuring to core/. The canonical location is {new_module}.
from {new_module} import *  # noqa: F401,F403
'''

        # But wait — the old path uses dots, not slashes. E.g., "src.core.coherence_engine"
        # The file is at src/core/coherence_engine.py
        old_file_full = os.path.join(ROOT, old_file)
        if os.path.exists(old_file_full):
            # Overwrite with shim
            with open(old_file_full, "w") as f:
                f.write(shim_content)
            count += 1

    print(f"Created {count} compatibility shims in src/")

if __name__ == "__main__":
    main()
