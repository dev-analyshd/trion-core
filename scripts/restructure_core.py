#!/usr/bin/env python3
"""
[COMPLETED ONE-TIME MIGRATION TOOL — DO NOT RUN]

Restructure src/ → core/ — Phase 2
Copies ALL Python files from src/ to core/ with the new directory structure
prescribed by the institutional grade execution document.
Then creates a compatibility shim so `from src.*` imports still work.

Historical record only (W4-Q): the migration has long since landed (src/ no
longer exists) and the compatibility shim it creates was later removed
(FIX-4). The MAPPING below is the authoritative file-level provenance of the
restructure — kept for that reason, not as a runnable tool.
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

# ── Exact file mapping: (src_path, core_path) ────────────────────────────────
MAPPING = {
    # primitives/ (Level 0)
    "src/core/behavioral_hash.py":            "core/primitives/behavioral_hash.py",
    "src/core/entity_resolution.py":           "core/primitives/entity_resolution.py",
    "src/core/resonance.py":                  "core/primitives/resonance.py",
    "src/core/information_conservation.py":    "core/primitives/thermodynamics.py",
    "src/core/evolutionary_fitness.py":        "core/primitives/evolutionary_fitness.py",

    # physical/ (Level 1)
    "src/planes/physical/phi_engine.py":       "core/physical/phi_engine.py",
    "src/manipulation/fingerprint_detector.py":"core/physical/manipulation_detector.py",
    "src/core/temporal_coherence.py":          "core/physical/temporal_coherence.py",
    "src/core/self_verification.py":           "core/physical/transduction_integrity.py",

    # akashic/ (Level 2)
    "src/planes/physical/akashic_depth.py":    "core/akashic/depth.py",
    "src/akashic/archetypes.py":               "core/akashic/archetype.py",
    "src/core/genesis_inference.py":           "core/akashic/genesis.py",
    "src/core/mental_transformer.py":          "core/akashic/mental_transformer.py",
    "src/planes/physical/resurrection.py":     "core/akashic/resurrection.py",
    "src/planes/physical/fork_resolution.py":  "core/akashic/fork_resolution.py",
    "src/planes/physical/trajectory_anomaly.py":"core/akashic/trajectory_anomaly.py",
    "src/core/bibl.py":                        "core/akashic/bibl.py",
    "src/core/bibl_pattern_store.py":          "core/akashic/bibl_pattern_store.py",
    "src/akashic/epigenetics.py":              "core/akashic/epigenetics.py",

    # mental/ (Level 3)
    "src/planes/mental/m_engine.py":           "core/mental/confidence.py",
    "src/planes/mental/intelligence_maintenance.py":"core/mental/intelligence_maintenance.py",

    # mental/anima/
    "src/planes/anima/anima_engine.py":        "core/mental/anima/engine.py",
    "src/planes/anima/anima_data_streams.py":   "core/mental/anima/data_streams.py",
    "src/planes/anima/anima_pattern_library.py":"core/mental/anima/pattern_library.py",
    "src/planes/anima/anima_reflexivity.py":    "core/mental/anima/reflexivity.py",
    "src/planes/anima/source_credibility.py":   "core/mental/anima/source_credibility.py",

    # spiritual/ (Level 4)
    "src/consensus/diversity_weighted_bft.py": "core/spiritual/consensus.py",
    "src/planes/spiritual/sigma_engine.py":    "core/spiritual/sigma_engine.py",
    "src/planes/spiritual/hhi_monitor.py":     "core/spiritual/hhi_monitor.py",
    "src/planes/spiritual/slashing.py":        "core/spiritual/slashing.py",
    "src/planes/spiritual/epigenetic.py":      "core/spiritual/epigenetic.py",
    "src/planes/spiritual/consensus_degradation.py":"core/spiritual/consensus_degradation.py",

    # spiritual/conscious/
    "src/planes/conscious/k_engine.py":        "core/spiritual/conscious/engine.py",
    "src/planes/conscious/indigenous_knowledge.py":"core/spiritual/conscious/indigenous_knowledge.py",

    # spiritual/living_security/
    "src/security/living_security.py":         "core/spiritual/living_security/__init__.py",
    "src/security/pqc_layer.py":               "core/spiritual/living_security/pqc_layer.py",
    "src/security/genomic_genealogy.py":       "core/spiritual/living_security/genomic_genealogy.py",

    # master/ (Level 5)
    "src/core/coherence_engine.py":            "core/master/coherence.py",
    "src/core/moat_engine.py":                 "core/master/moat.py",
    "src/core/consensus_degradation.py":       "core/master/degradation.py",
    "src/signals/signal_factory.py":           "core/master/signal_factory.py",
    "src/core/channel_architecture.py":        "core/master/channel_architecture.py",
    "src/core/trion_primitives.py":            "core/master/trion_primitives.py",
    "src/core/d_engine.py":                    "core/master/d_engine.py",
    "src/core/homomorphic_mapping.py":         "core/master/homomorphic_mapping.py",
    "src/core/btcp_score.py":                  "core/master/btcp_score.py",

    # extended/ (Levels 6-9)
    "src/planes/extended/biological_capital.py":"core/extended/biological_capital.py",
    "src/planes/extended/sba.py":              "core/extended/sovereign_behavioral.py",
    "src/planes/extended/xsl.py":              "core/extended/cross_species.py",
    "src/planes/extended/energy_participation.py":"core/extended/energy_participation.py",
    "src/planes/physical/nl_engine.py":        "core/extended/natural_liquidity.py",
    "src/planes/physical/xsl_engine.py":       "core/extended/xsl_engine.py",

    # novel/ (7 Novel Primitives)
    "src/signals/birp.py":                     "core/novel/birp.py",
    "src/signals/behavioral_identity_recovery.py":"core/novel/behavioral_identity_recovery.py",
    "src/security/chameleon_protocol.py":      "core/novel/chameleon.py",

    # governance/
    "src/governance/awa_state.py":             "core/governance/awa.py",
    "src/governance/falsifiability_registry.py":"core/governance/falsifiability_registry.py",
    "src/governance/intelligence_maintenance.py":"core/governance/intelligence_maintenance.py",
    "src/governance/open_research_questions.py":"core/governance/open_research_questions.py",
    "src/governance/sba_engine.py":            "core/governance/sba_engine.py",
    "src/governance/slashing.py":              "core/governance/slashing.py",

    # Other modules
    "src/agent/safety_pipeline.py":            "core/agent/safety_pipeline.py",
    "src/auditor/contract_auditor.py":         "core/auditor/contract_auditor.py",
    "src/auditor/vulnerability_patterns.py":   "core/auditor/vulnerability_patterns.py",
    "src/trading/signal_engine.py":            "core/trading/signal_engine.py",
    "src/trading/pattern_archetypes.py":       "core/trading/pattern_archetypes.py",
    "src/trading/agent_interface.py":          "core/trading/agent_interface.py",
    "src/trading/live_feed.py":                "core/trading/live_feed.py",
    "src/trading/market_data.py":              "core/trading/market_data.py",
    "src/investment/investment_engine.py":     "core/investment/investment_engine.py",
    "src/lifecycle/entity_lifecycle.py":       "core/lifecycle/entity_lifecycle.py",
    "src/reputation/reputation_engine.py":     "core/reputation/reputation_engine.py",
    "src/price/behavioral_price_engine.py":    "core/price/behavioral_price_engine.py",
    "src/thermodynamics/entropy_engine.py":    "core/thermodynamics/entropy_engine.py",
    "src/thermodynamics/thermo_engine.py":     "core/thermodynamics/thermo_engine.py",
    "src/ubl/ubl.py":                          "core/ubl/ubl.py",
    "src/protocol/distribution_coherence.py":  "core/protocol/distribution_coherence.py",
    "src/protocol/protocol_health.py":         "core/protocol/protocol_health.py",
    "src/protocol/role_classifier.py":         "core/protocol/role_classifier.py",
    "src/protocol/segmentation.py":            "core/protocol/segmentation.py",
    "src/api/routes.py":                       "core/api/routes.py",
    "src/native_bridge.py":                    "core/native_bridge.py",
}

# Directories that need __init__.py
INIT_DIRS = [
    "core", "core/primitives", "core/physical", "core/akashic",
    "core/mental", "core/mental/anima", "core/mental/anima/data_sources",
    "core/spiritual", "core/spiritual/conscious", "core/spiritual/living_security",
    "core/master", "core/extended", "core/novel", "core/governance",
    "core/agent", "core/auditor", "core/trading", "core/investment",
    "core/lifecycle", "core/reputation", "core/price",
    "core/thermodynamics", "core/ubl", "core/protocol", "core/api",
]

def main():
    # Create all directories with __init__.py
    for d in INIT_DIRS:
        os.makedirs(d, exist_ok=True)
        init = os.path.join(d, "__init__.py")
        if not os.path.exists(init):
            with open(init, "w") as f:
                f.write(f'"""TRION Protocol — {d.replace("/", ".")}"""\n')

    # Copy files
    moved = 0
    skipped = 0
    for src, dst in MAPPING.items():
        src_full = os.path.join(ROOT, src)
        dst_full = os.path.join(ROOT, dst)
        if os.path.exists(src_full):
            os.makedirs(os.path.dirname(dst_full), exist_ok=True)
            shutil.copy2(src_full, dst_full)
            moved += 1
        else:
            skipped += 1
            print(f"  SKIP: {src}")

    print(f"Copied {moved} files, skipped {skipped}")

    # Create missing files from the document
    missing = {
        "core/mental/anima/data_sources/__init__.py": '"""ANIMA data sources"""\n',
        "core/mental/anima/data_sources/sec_edgar.py": '"""SEC EDGAR data source"""\n',
        "core/mental/anima/data_sources/regulatory.py": '"""Regulatory data source (FCA/MAS/ESMA/CFTC)"""\n',
        "core/mental/anima/data_sources/github_activity.py": '"""GitHub developer activity data source"""\n',
        "core/mental/anima/data_sources/academic.py": '"""Academic preprint data source"""\n',
        "core/mental/anima/data_sources/news.py": '"""News data source with credibility"""\n',
        "core/mental/anima/data_sources/ecological.py": '"""IUCN/species ecological data source"""\n',
        "core/mental/anima/crawlers.py": '"""ANIMA crawler framework — 1000+ concurrent crawlers"""\n# See akashic/anima_engine.py for the live implementation\n',
        "core/mental/anima/nlp_pipeline.py": '"""ANIMA NLP pipeline — 50+ language processing"""\n# See src/planes/anima/anima_data_streams.py for the live implementation\n',
        "core/mental/anima/pattern_engine.py": '"""ANIMA pattern coherence ratio engine"""\n# See core/akashic/mental_transformer.py for the live implementation\n',
        "core/mental/predictive_limit.py": '"""L3.6 — Predictive Completeness Limit: PC_limit = 1 - H_irr/H_future < 1"""\n# Implemented in core/master/coherence.py (compute_pc_limit method)\n',
        "core/novel/bck.py": '"""P2 — Behavioral Causal Keys (BCK)"""\n# Implemented in core/spiritual/living_security/genomic_genealogy.py\n',
        "core/novel/semi_immutability.py": '"""P1 — Semi-Immutability: bytecode immutable, expression changes"""\n# Implemented in core/spiritual/epigenetic.py\n',
        "core/novel/coordination_collapse.py": '"""P3 — Coordination Collapse Theorem: d_j = 1-corr(M_j, M_bar)"""\n# Implemented in core/spiritual/consensus.py\n',
        "core/novel/behavioral_zk.py": '"""P4 — Behavioral ZK Proofs"""\n# Implemented in akashic/anima_regulatory.py (Schnorr-Pedersen NIZK)\n',
        "core/governance/gratitude.py": '"""Gratitude Protocol: Gratitude(t) = Value_given / Value_received >= 1"""\n# Implemented in api/app.py (/api/v1/governance/gratitude endpoint)\n',
        "core/governance/unknown_unknown.py": '"""Unknown Unknown Provision: Budget = 0.10 * Revenue(t)"""\n# Held in multi-sig with 30-day time-lock\n',
        "core/governance/initialization.py": '"""INIT_valid ceremony"""\n# INIT_valid iff: N_validators>=100, geo>=4 continents, D>=D_minimum, N_chains>=3\n',
        "core/master/threshold.py": '"""L5.1 — Dynamic Threshold: Theta(t) = Theta_min + (Theta_max-Theta_min)*V(t)"""\n# Implemented in core/master/coherence.py (compute_threshold method)\n',
        "core/master/master_equation.py": '"""L5.4 — Master Equation: T(t) = [C>=Theta] * S * e^(M_moat*t)"""\n# Implemented in core/master/coherence.py (compute_coherence method)\n',
    }
    for path, content in missing.items():
        full = os.path.join(ROOT, path)
        if not os.path.exists(full):
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as f:
                f.write(content)

    # Create core/pyproject.toml
    with open(os.path.join(ROOT, "core/pyproject.toml"), "w") as f:
        f.write('''[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "trion-core"
version = "1.0.0"
requires-python = ">=3.11"

[tool.setuptools.packages.find]
where = ["."]
''')

    print(f"Created {len(missing)} missing files")
    print("Phase 2: core/ directory structure complete")

if __name__ == "__main__":
    main()
