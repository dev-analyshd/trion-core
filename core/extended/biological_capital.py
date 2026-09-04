"""
TRION Protocol — L6.1 Biological Capital Index (BC)

BC(ecosystem, t) = Flow · Resilience · Uniqueness · Interdependence

Flow          = net primary productivity rate × biomass density
                Measures energy/material flow through the ecosystem.
                High flow = productive, active ecosystem.

Resilience    = recovery_speed_after_disturbance / disturbance_magnitude
                How fast the ecosystem recovers relative to the size of the shock.
                Healthy ecosystems recover quickly. Brittle ones do not.

Uniqueness    = endemic_species_count / (comparable_ecosystem_baseline + 1)
                Irreplaceable ecological value.
                Uniqueness = 0 if species are globally common.
                Uniqueness → high if species exist ONLY here.

Interdependence = keystone_species_presence_weighted_connectivity
                Network of species dependencies — how connected is the web?
                Loss of keystone species → cascade collapse.

BC maps to financial protocol health:
    Flow          = value throughput and velocity
    Resilience    = protocol resilience to stress events
    Uniqueness    = protocol's unique value proposition (non-substitutability)
    Interdependence = composability and ecosystem integration depth

XSL(species, t) = TerritoryViability · FoodSecurity · ReproductionRate / (1 + ThreatPressure)
→ see xsl.py

Falsification: F9 (BC scores must not systematically diverge from
peer-reviewed ecosystem valuations over 12-month rolling window)

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# GBIF ecosystem data fetcher (real data feed for the "flow" component)
# ─────────────────────────────────────────────────────────────────────────────

_GBIF_CACHE: Dict[str, Dict[str, Any]] = {}
_GBIF_CACHE_TTL = 300.0   # 5 minutes
_GBIF_LOCK = __import__("threading").Lock()


def _gbif_get_cached(key: str) -> Optional[Any]:
    import time
    with _GBIF_LOCK:
        entry = _GBIF_CACHE.get(key)
        if entry is None:
            return None
        if time.time() - entry["ts"] > _GBIF_CACHE_TTL:
            _GBIF_CACHE.pop(key, None)
            return None
        return entry["data"]


def _gbif_set_cached(key: str, data: Any) -> None:
    import time
    with _GBIF_LOCK:
        _GBIF_CACHE[key] = {"ts": time.time(), "data": data}


def clear_gbif_cache() -> None:
    """Clear the GBIF ecosystem-data cache. Used by tests / refresh on demand."""
    with _GBIF_LOCK:
        _GBIF_CACHE.clear()


def fetch_ecosystem_data(
    species_query: str = "coral reef",
    limit: int = 50,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """
    Fetch real ecosystem data from the GBIF public Occurrence API.

    GBIF (Global Biodiversity Information Facility) returns species occurrence
    records including scientific name, taxon key, IUCN Red List category
    (when available), country code, decimal latitude / longitude, and year.

    This data feeds the BC ``flow`` component — species occurrence density
    is a proxy for net primary productivity and biomass density at the
    ecosystem level (more occurrences = more biomass = higher flow).

    Returns a structured dict::

        {
          "source":           "gbif",
          "query":            species_query,
          "occurrence_count": int,
          "species_count":    int,                 # unique species
          "endemic_count":    int,                 # species seen only here
          "iucn_threats":     {category: count},   # CR/EN/VU/LC/...
          "flow_proxy":       float,               # [0, 1] — BC flow input
          "diversity_score":  float,               # [0, 1] — Shannon-like
          "occurrences":      List[dict],          # raw records (truncated)
          "fetched_at":       float,               # unix ts
        }

    On any network / parse error returns an empty-result dict (count=0)
    so callers can fall back to default EcosystemProfile values without
    try/except. Never raises.
    """
    import json
    import time
    import urllib.parse
    import urllib.request
    import urllib.error

    cache_key = f"gbif_eco:{species_query}:{limit}"
    if use_cache:
        cached = _gbif_get_cached(cache_key)
        if cached is not None:
            return cached

    params = urllib.parse.urlencode({
        "q": species_query,
        "limit": limit,
        "hasCoordinate": "true",
    })
    url = f"https://api.gbif.org/v1/occurrence/search?{params}"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "TRION-Protocol/2.0 (+biological-capital)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except (urllib.error.URLError, urllib.error.HTTPError,
            json.JSONDecodeError, OSError, TimeoutError):
        return {
            "source":           "gbif",
            "query":            species_query,
            "occurrence_count": 0,
            "species_count":    0,
            "endemic_count":    0,
            "iucn_threats":     {},
            "flow_proxy":       0.0,
            "diversity_score":  0.0,
            "occurrences":      [],
            "fetched_at":       time.time(),
            "error":            "network_or_parse_failure",
        }

    results = payload.get("results", []) if isinstance(payload, dict) else []
    occurrences: List[Dict[str, Any]] = []
    species_set = set()
    country_set = set()
    iucn_threats: Dict[str, int] = {}

    for occ in results:
        if not isinstance(occ, dict):
            continue
        species = occ.get("species") or occ.get("scientificName") or "unknown"
        species_set.add(species)
        country = occ.get("countryCode") or occ.get("country") or ""
        if country:
            country_set.add(country)
        iucn = occ.get("iucnRedListCategory") or "UNKNOWN"
        iucn_threats[iucn] = iucn_threats.get(iucn, 0) + 1
        occurrences.append({
            "species":   species,
            "country":   country,
            "year":      occ.get("year"),
            "latitude":  occ.get("decimalLatitude"),
            "longitude": occ.get("decimalLongitude"),
            "iucn":      iucn,
            "taxon_key": occ.get("taxonKey"),
        })

    occurrence_count = len(occurrences)
    species_count = len(species_set)

    # Flow proxy: occurrence density (more occurrences = higher productivity)
    # capped at 1.0 — 50+ occurrences in a single GBIF search ≈ productive
    # ecosystem (proxy for NPP × biomass).
    flow_proxy = min(1.0, occurrence_count / 50.0)

    # Diversity score: Shannon-like evenness proxy over species count
    # capped at 1.0 — 15+ unique species in a single search ≈ diverse ecosystem.
    diversity_score = min(1.0, species_count / 15.0)

    result = {
        "source":           "gbif",
        "query":            species_query,
        "occurrence_count": occurrence_count,
        "species_count":    species_count,
        "endemic_count":    species_count,   # endemic proxy: unique species seen here
        "iucn_threats":     iucn_threats,
        "countries":        sorted(country_set),
        "flow_proxy":       flow_proxy,
        "diversity_score":  diversity_score,
        "occurrences":      occurrences[:20],   # truncate for downstream serde
        "fetched_at":       time.time(),
    }

    if use_cache:
        _gbif_set_cached(cache_key, result)
    return result


def ecosystem_data_to_profile(
    ecosystem_id: str,
    eco_data: Dict[str, Any],
) -> Tuple["EcosystemProfile", bool]:
    """
    Convert raw GBIF ecosystem data into an ``EcosystemProfile`` for BC.

    Returns ``(profile, used_real_data)`` where ``used_real_data`` is True
    when ``eco_data`` contained GBIF occurrence records. When the GBIF fetch
    failed (count=0), the profile is built from conservative defaults
    (mid-range values) and ``used_real_data`` is False — callers can fall
    back to a hand-authored profile if they prefer.

    The mapping follows the whitepaper's BC formula:
      - flow_proxy           → NPP×biomass proxy (mapped via NPP_MAX_REFERENCE)
      - diversity_score      → resilience proxy (diverse = resilient)
      - species_count       → endemic_species_count
      - iucn threatened      → disturbance_magnitude (more threats = more disturbance)
    """
    if not eco_data or not isinstance(eco_data, dict):
        eco_data = {}

    occurrence_count = int(eco_data.get("occurrence_count", 0) or 0)
    flow_proxy = float(eco_data.get("flow_proxy", 0.0) or 0.0)
    diversity = float(eco_data.get("diversity_score", 0.0) or 0.0)
    species_count = int(eco_data.get("species_count", 0) or 0)
    iucn = eco_data.get("iucn_threats", {}) or {}

    threatened = sum(
        n for k, n in iucn.items()
        if k in ("CRITICALLY_ENDANGERED", "ENDANGERED", "VULNERABLE")
    )
    total_iucn = max(1, sum(iucn.values()))
    threat_ratio = min(1.0, threatened / total_iucn)

    used_real_data = occurrence_count > 0

    profile = EcosystemProfile(
        ecosystem_id                 = ecosystem_id,
        # Flow: flow_proxy is already normalized to [0, 1] → scale to NPP_MAX
        net_primary_productivity     = flow_proxy * NPP_MAX_REFERENCE,
        biomass_density              = flow_proxy * BIOMASS_MAX_REFERENCE,
        # Resilience: diversity is a proxy — diverse ecosystems recover faster
        recovery_speed               = max(0.1, min(1.0, diversity)),
        disturbance_magnitude       = max(0.05, threat_ratio),
        # Uniqueness: species_count as endemic proxy
        endemic_species_count       = max(0, species_count),
        comparable_baseline_count    = 5,   # conservative baseline
        # Interdependence: keystone = any threatened flagship species seen
        keystone_species_present     = threatened > 0,
        network_connectivity        = max(0.1, min(1.0, diversity)),
        trophic_levels              = 3 if species_count > 5 else 2,
    )
    return profile, used_real_data


@dataclass
class EcosystemProfile:
    """
    Input data for Biological Capital computation.
    Sourced from: IUCN Red List, GBIF, peer-reviewed ecological databases.
    Calibrated by computational biologists (critical non-obvious hire).
    """
    ecosystem_id:                 str
    # Flow components
    net_primary_productivity:     float   # gC/m²/year — carbon fixed by photosynthesis
    biomass_density:              float   # tonnes/hectare
    # Resilience components
    recovery_speed:               float   # [0, 1] — fraction recovered per year post-disturbance
    disturbance_magnitude:        float   # [0, 1] — size of reference disturbance
    # Uniqueness components
    endemic_species_count:        int
    comparable_baseline_count:    int     # Same type ecosystem elsewhere
    # Interdependence components
    keystone_species_present:     bool
    network_connectivity:         float   # [0, 1] — ecological network connectivity
    trophic_levels:               int     # Number of trophic levels


@dataclass
class BiologicalCapitalResult:
    """
    BC(ecosystem, t) = Flow · Resilience · Uniqueness · Interdependence
    """
    ecosystem_id:      str
    bc:                float     # [0, 1] — biological capital score
    flow:              float     # Net primary productivity × biomass (normalized)
    resilience:        float     # Recovery speed / disturbance magnitude
    uniqueness:        float     # Endemic / comparable baseline
    interdependence:   float     # Keystone × connectivity
    label:             str       # THRIVING / HEALTHY / STRESSED / CRITICAL / COLLAPSED
    warning:           Optional[str]


# Calibration constants (from peer-reviewed ecology literature)
# These must be validated against real ecological data by computational biologists
NPP_MAX_REFERENCE     = 2500.0   # gC/m²/year — tropical rainforest reference
BIOMASS_MAX_REFERENCE = 300.0    # tonnes/hectare — old-growth forest reference


def compute_flow(
    net_primary_productivity: float,
    biomass_density:          float,
) -> float:
    """
    Flow = (NPP / NPP_reference) × (biomass / biomass_reference)
    Normalized to [0, 1] using reference maxima.
    """
    npp_norm     = min(1.0, net_primary_productivity / NPP_MAX_REFERENCE)
    biomass_norm = min(1.0, biomass_density / BIOMASS_MAX_REFERENCE)
    return npp_norm * biomass_norm


def compute_resilience(
    recovery_speed:      float,
    disturbance_magnitude: float,
) -> float:
    """
    Resilience = recovery_speed / disturbance_magnitude

    If disturbance is near zero, resilience is defined by recovery speed alone.
    Normalized to [0, 1].
    """
    if disturbance_magnitude <= 0:
        return min(1.0, recovery_speed)
    raw = recovery_speed / max(disturbance_magnitude, 0.001)
    return min(1.0, max(0.0, raw))


def compute_uniqueness(
    endemic_species_count:     int,
    comparable_baseline_count: int,
) -> float:
    """
    Uniqueness = endemic_species_count / (comparable_baseline_count + 1)

    +1 prevents division by zero.
    High endemic count relative to baseline = highly unique = high conservation value.
    Normalized to [0, 1] with logistic capping.
    """
    raw = endemic_species_count / (comparable_baseline_count + 1)
    # Logistic normalization: caps high values smoothly
    import math
    return 1.0 - math.exp(-raw)


def compute_interdependence(
    keystone_species_present: bool,
    network_connectivity:     float,
    trophic_levels:           int,
) -> float:
    """
    Interdependence = keystone_presence_weight × connectivity × trophic_complexity

    Keystone species: if absent, interdependence is halved regardless of connectivity.
    Trophic levels: more levels = more complex web = higher interdependence.
    """
    keystone_weight   = 1.0 if keystone_species_present else 0.5
    trophic_factor    = min(1.0, trophic_levels / 6.0)  # Normalize 6 trophic levels = 1.0
    raw               = keystone_weight * network_connectivity * trophic_factor
    return min(1.0, max(0.0, raw))


def compute_bc(
    profile: EcosystemProfile,
    eco_data: Optional[Dict[str, Any]] = None,
    fetch_live: bool = False,
    species_query: Optional[str] = None,
) -> BiologicalCapitalResult:
    """
    BC(ecosystem, t) = Flow · Resilience · Uniqueness · Interdependence

    Parameters
    ----------
    profile : EcosystemProfile
        Hand-authored profile (the original contract — preserved for
        backwards compatibility).
    eco_data : Optional[Dict], default None
        Pre-fetched GBIF ecosystem data dict from :func:`fetch_ecosystem_data`.
        When provided, the ``flow`` component is recalibrated against the
        real GBIF occurrence density proxy.
    fetch_live : bool, default False
        When True, fetch a fresh GBIF snapshot for ``species_query`` (or
        ``profile.ecosystem_id`` if not specified) and apply it to the
        ``flow`` component. Network failures degrade gracefully — the
        hand-authored profile is used.
    species_query : Optional[str], default None
        Search query forwarded to GBIF when ``fetch_live=True``. Defaults
        to ``profile.ecosystem_id``.
    """
    if fetch_live and eco_data is None:
        try:
            eco_data = fetch_ecosystem_data(
                species_query=species_query or profile.ecosystem_id,
                use_cache=True,
            )
        except Exception:
            eco_data = None

    if eco_data:
        # Recalibrate the flow component against real GBIF data.
        # flow_proxy ∈ [0, 1] is the GBIF occurrence density → we use it
        # directly as the BC flow component, scaled into the NPP/biomass
        # normalization via the existing ``compute_flow`` formula.
        flow_proxy = float(eco_data.get("flow_proxy", 0.0) or 0.0)
        # Override the profile's NPP and biomass with GBIF-derived values
        # so the original compute_flow formula yields the GBIF-derived flow.
        profile.net_primary_productivity = flow_proxy * NPP_MAX_REFERENCE
        profile.biomass_density          = flow_proxy * BIOMASS_MAX_REFERENCE

    flow   = compute_flow(profile.net_primary_productivity, profile.biomass_density)
    resil  = compute_resilience(profile.recovery_speed, profile.disturbance_magnitude)
    unique = compute_uniqueness(profile.endemic_species_count, profile.comparable_baseline_count)
    inter  = compute_interdependence(
        profile.keystone_species_present, profile.network_connectivity, profile.trophic_levels
    )

    bc = flow * resil * unique * inter

    if bc >= 0.70:
        label = "THRIVING"
    elif bc >= 0.50:
        label = "HEALTHY"
    elif bc >= 0.30:
        label = "STRESSED"
    elif bc >= 0.10:
        label = "CRITICAL"
    else:
        label = "COLLAPSED"

    warning = None
    if bc < 0.10:
        warning = (
            f"ECOSYSTEM COLLAPSE: BC={bc:.4f}. "
            "XSL(species) signals will show systemic extinction risk. "
            "Correlated asset (ECOSYSTEM_HEALTH signal) affected."
        )
    elif bc < 0.30:
        warning = f"CRITICAL ecosystem: BC={bc:.4f}. Stress signals active."

    return BiologicalCapitalResult(
        ecosystem_id  = profile.ecosystem_id,
        bc            = bc,
        flow          = flow,
        resilience    = resil,
        uniqueness    = unique,
        interdependence = inter,
        label         = label,
        warning       = warning,
    )


def bc_to_ecosystem_health_signal(bc_result: BiologicalCapitalResult) -> dict:
    """
    Build ECOSYSTEM_HEALTH signal from BC computation.
    BC and EP components included per whitepaper signal specification.
    """
    return {
        "signal_type":    "ECOSYSTEM_HEALTH",
        "ecosystem_id":   bc_result.ecosystem_id,
        "bc_score":       bc_result.bc,
        "bc_components": {
            "flow":           bc_result.flow,
            "resilience":     bc_result.resilience,
            "uniqueness":     bc_result.uniqueness,
            "interdependence": bc_result.interdependence,
        },
        "label":          bc_result.label,
        "warning":        bc_result.warning,
        "data_sources":   [
            "IUCN Red List", "GBIF", "peer-reviewed ecological databases",
        ],
        "calibration_note": (
            "HONEST DISCLOSURE: BC calibration requires computational biologist validation "
            "against peer-reviewed ecosystem valuations (F9 falsification condition). "
            "Current values are initial estimates pending expert calibration."
        ),
    }


if __name__ == "__main__":
    # Amazon rainforest approximation
    amazon = EcosystemProfile(
        ecosystem_id                 = "amazon_basin",
        net_primary_productivity     = 2100.0,
        biomass_density              = 250.0,
        recovery_speed               = 0.60,
        disturbance_magnitude        = 0.30,
        endemic_species_count        = 40000,
        comparable_baseline_count    = 5000,
        keystone_species_present     = True,
        network_connectivity         = 0.88,
        trophic_levels               = 5,
    )

    result = compute_bc(amazon)
    print(f"Amazon BC: {result.bc:.4f} [{result.label}]")
    print(f"  Flow={result.flow:.4f} Resilience={result.resilience:.4f} "
          f"Uniqueness={result.uniqueness:.4f} Interdependence={result.interdependence:.4f}")
    assert result.bc > 0.30  # Amazon should be healthy

    # Degraded ecosystem
    degraded = EcosystemProfile(
        ecosystem_id                 = "degraded_monoculture",
        net_primary_productivity     = 300.0,
        biomass_density              = 20.0,
        recovery_speed               = 0.10,
        disturbance_magnitude        = 0.80,
        endemic_species_count        = 5,
        comparable_baseline_count    = 1000,
        keystone_species_present     = False,
        network_connectivity         = 0.15,
        trophic_levels               = 2,
    )
    result_d = compute_bc(degraded)
    print(f"Degraded BC: {result_d.bc:.4f} [{result_d.label}]")
    assert result_d.bc < 0.30

    print("L6.1 Biological Capital Index: PASS")
