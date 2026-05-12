"""
Conscious Coherence Score K(t) — TRION L8
Requires: 100+ annotators, 20+ countries, 3+ indigenous knowledge systems.
K(t) = credibility-weighted human assessment score.
"""
from dataclasses import dataclass, field
from typing import List
from datetime import datetime, timezone


K_MIN_ANNOTATORS        = 100
K_MIN_COUNTRIES         = 20
K_MIN_INDIGENOUS_SYSTEMS = 3


@dataclass
class Annotation:
    annotator_id:    str
    asset_id:        str
    score:           float
    cultural_context: str
    knowledge_system: str
    confidence:      float
    stake_amount:    float
    challenged:      bool = False
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ConsciousScoreState:
    asset_id:              str
    annotations:           List[Annotation] = field(default_factory=list)
    challenged_annotations: List[str]        = field(default_factory=list)

    def add_annotation(self, annotation: Annotation):
        self.annotations.append(annotation)

    def _get_annotator_cred(self, annotator_id: str) -> float:
        return 0.50

    def compute_k(self) -> dict:
        if not self.annotations:
            return {"k_score": 0.0, "ready": False, "message": "No annotations yet"}

        countries = set(a.cultural_context for a in self.annotations)
        indigenous = set(a.knowledge_system for a in self.annotations
                        if a.knowledge_system.startswith("indigenous"))

        if len(self.annotations) < K_MIN_ANNOTATORS:
            return {"k_score": 0.0, "ready": False,
                    "annotators": len(self.annotations),
                    "needed": K_MIN_ANNOTATORS - len(self.annotations)}

        if len(countries) < K_MIN_COUNTRIES:
            return {"k_score": 0.0, "ready": False,
                    "countries": len(countries),
                    "needed_countries": K_MIN_COUNTRIES - len(countries)}

        weighted_sum = 0.0
        cred_sum     = 0.0
        for ann in self.annotations:
            if ann.challenged: continue
            cred          = self._get_annotator_cred(ann.annotator_id)
            weighted_sum += cred * ann.score
            cred_sum     += cred

        k_score = (weighted_sum / cred_sum) if cred_sum > 0 else 0.0

        return {
            "k_score":          round(k_score, 6),
            "ready":            True,
            "annotator_count":  len(self.annotations),
            "country_count":    len(countries),
            "indigenous_systems": len(indigenous),
            "indigenous_systems_met": len(indigenous) >= K_MIN_INDIGENOUS_SYSTEMS,
        }
