"""TRION Protocol — core.extended

Layers 6-9: Extended Intelligence Modules
- Level 6: Biological Rhythm Timer (BRT)
- Level 7: Natural Liquidity (NL)
- Level 8: Energy Participation (EP)
- Level 9: Biological Capital (BC), Cross-Species Liquidity (XSL), Sovereign Behavioral Assessment (SBA)
"""

from .biological_rhythm import (
    BiologicalRhythm, compute_brt, get_brt_dict, BRT,
    compute_brt_gas_correlation, BRTGasCorrelation,
    CIRCADIAN_SECONDS, ULTRADIAN_SECONDS, LUNAR_SECONDS, SEASONAL_SECONDS,
    RHYTHM_PERIODS, BRT_GAS_ALPHA,
)

from .natural_liquidity import (
    compute_ld, compute_lo, compute_lc, compute_ls, compute_nl,
    NL_ALERT_THRESHOLD,
)

from .energy_participation import (
    ProtocolEconomics, DeveloperData, EPResult,
    compute_vc, compute_pa, compute_dc, compute_ep,
    REFERENCE_TENURE_DAYS,
)

from .biological_capital import (
    EcosystemProfile, BiologicalCapitalResult,
    compute_flow, compute_resilience, compute_uniqueness,
    compute_interdependence, compute_bc, bc_to_ecosystem_health_signal,
    fetch_ecosystem_data, ecosystem_data_to_profile, clear_gbif_cache,
    NPP_MAX_REFERENCE, BIOMASS_MAX_REFERENCE,
)

from .cross_species import (
    SpeciesProfile, XSLResult,
    compute_territory_viability, compute_food_security,
    compute_reproduction_rate, compute_threat_pressure,
    compute_xsl, xsl_to_trion_signal,
    fetch_species_data, species_data_to_profile,
    iucn_threat_weight, IUCN_THREAT_WEIGHTS, clear_xsl_cache,
)

from .sovereign_behavioral import (
    SBAInputs, SBAResult,
    compute_pearson_corr, compute_economic_stability,
    compute_institutional_integrity, compute_social_cohesion,
    compute_governance_quality, compute_crypto_behavior, compute_sba,
    apply_economic_snapshot, fetch_and_apply_economic_snapshot,
    W_E, W_I, W_S, W_G, W_C,
)

from .xsl_engine import (
    CrossChainBehavior,
    compute_tv, compute_fs, compute_rr, compute_tp,
    # xsl_engine's scalar XSL formula (L9.1 cross-chain behavioural XSL).
    # The canonical `compute_xsl` export of this package is the L9
    # cross-species (GBIF/IUCN) compute_xsl from .cross_species above;
    # xsl_engine's homonymous function is aliased here so it stays importable
    # without shadowing it.
    compute_xsl as compute_xsl_engine, compute_xsl_full,
    XSL_KEYSTONE, XSL_BRIDGE,
)

__all__ = [
    # BRT (Level 6)
    'BiologicalRhythm', 'compute_brt', 'get_brt_dict', 'BRT',
    'compute_brt_gas_correlation', 'BRTGasCorrelation',
    'CIRCADIAN_SECONDS', 'ULTRADIAN_SECONDS', 'LUNAR_SECONDS', 'SEASONAL_SECONDS',
    'RHYTHM_PERIODS', 'BRT_GAS_ALPHA',
    # NL (Level 7)
    'compute_ld', 'compute_lo', 'compute_lc', 'compute_ls', 'compute_nl',
    'NL_ALERT_THRESHOLD',
    # EP (Level 8)
    'ProtocolEconomics', 'DeveloperData', 'EPResult',
    'compute_vc', 'compute_pa', 'compute_dc', 'compute_ep',
    'REFERENCE_TENURE_DAYS',
    # BC (Level 9) — GBIF-wired
    'EcosystemProfile', 'BiologicalCapitalResult',
    'compute_flow', 'compute_resilience', 'compute_uniqueness',
    'compute_interdependence', 'compute_bc', 'bc_to_ecosystem_health_signal',
    'fetch_ecosystem_data', 'ecosystem_data_to_profile', 'clear_gbif_cache',
    'NPP_MAX_REFERENCE', 'BIOMASS_MAX_REFERENCE',
    # XSL (Level 9) — GBIF + IUCN wired
    'SpeciesProfile', 'XSLResult',
    'compute_territory_viability', 'compute_food_security',
    'compute_reproduction_rate', 'compute_threat_pressure',
    'compute_xsl', 'xsl_to_trion_signal',
    'fetch_species_data', 'species_data_to_profile',
    'iucn_threat_weight', 'IUCN_THREAT_WEIGHTS', 'clear_xsl_cache',
    # SBA (Level 9) — IMF / World Bank wired
    'SBAInputs', 'SBAResult',
    'compute_pearson_corr', 'compute_economic_stability',
    'compute_institutional_integrity', 'compute_social_cohesion',
    'compute_governance_quality', 'compute_crypto_behavior', 'compute_sba',
    'apply_economic_snapshot', 'fetch_and_apply_economic_snapshot',
    'W_E', 'W_I', 'W_S', 'W_G', 'W_C',
    # XSL Engine (L9.1 — cross-chain behavioural XSL; its scalar
    # compute_xsl is exported as compute_xsl_engine to avoid shadowing
    # the canonical cross-species compute_xsl above)
    'CrossChainBehavior',
    'compute_tv', 'compute_fs', 'compute_rr', 'compute_tp',
    'compute_xsl_engine', 'compute_xsl_full',
    'XSL_KEYSTONE', 'XSL_BRIDGE',
]
