"""Disease Relation Classification and Indication/Trial Matching Policies.

This module provides a single, shared disease relation classification engine used by:
1. Rule -1 (Approved Indication Anchor): strictly requires DiseaseRelation.SAME.
2. ClinicalTrials.gov (Trial Attribution Condition Matching): accepts DiseaseRelation.SAME
   and DiseaseRelation.PARENT_CHILD.

References:
- ClinicalTrials.gov Forensic Audit Root-Cause Analysis
- Safe Implementation Specification Section 2-8
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any


class DiseaseRelation(Enum):
    SAME = "SAME"
    PARENT_CHILD = "PARENT_CHILD"
    SIBLING_EXCLUDED = "SIBLING_EXCLUDED"
    UNRELATED = "UNRELATED"


# Curated explicit parent-child ontology for trial recall without approval leakage
_PARENT_CHILD: dict[str, frozenset[str]] = {
    "traumatic brain injury": frozenset({
        "subdural hematoma",
        "epidural hematoma",
        "intracranial hemorrhage",
        "concussion",
        "diffuse axonal injury",
        "cerebral contusion",
    }),
    "cardiovascular disease": frozenset({
        "coronary artery disease",
        "myocardial infarction",
        "heart failure",
        "atherosclerosis",
        "peripheral artery disease",
        "stroke",
    }),
    "stroke": frozenset({
        "ischemic stroke",
        "cerebral infarction",
    }),
    "brain neoplasms": frozenset({
        "glioblastoma",
        "gbm",
        "glioma",
        "astrocytoma",
    }),
    "brain cancer": frozenset({
        "glioblastoma",
        "gbm",
        "glioma",
        "astrocytoma",
    }),
    "alzheimer's disease": frozenset({
        "mild cognitive impairment due to alzheimer's disease",
        "mild cognitive impairment",
        "prodromal alzheimer's disease",
    }),
}

# Explicit sibling exclusions: SIBLING_EXCLUDED always wins over parent/child or substring
_SIBLING_EXCLUSIONS: dict[str, frozenset[str]] = {
    "ischemic stroke": frozenset({"hemorrhagic stroke"}),
    "hemorrhagic stroke": frozenset({"ischemic stroke", "stroke"}),
    "stroke": frozenset({"hemorrhagic stroke"}),
}

# Curated synonym and canonical normalization map
_CANONICAL_SYNONYMS: dict[str, str] = {
    "tbi": "traumatic brain injury",
    "traumatic brain injuries": "traumatic brain injury",
    "brain injury, traumatic": "traumatic brain injury",
    "brain injuries, traumatic": "traumatic brain injury",
    "cvd": "cardiovascular disease",
    "cardiovascular diseases": "cardiovascular disease",
    "secondary prevention of cardiovascular disease": "cardiovascular disease",
    "secondary prevention of stroke": "stroke",
    "subdural hematoma, chronic": "subdural hematoma",
    "subdural hematoma, acute": "subdural hematoma",
    "subdural hematomas": "subdural hematoma",
    "hematoma, subdural, chronic": "subdural hematoma",
    "hematoma, subdural": "subdural hematoma",
    "chronic subdural hematoma": "subdural hematoma",
    "acute subdural hematoma": "subdural hematoma",
    "epidural hematoma": "epidural hematoma",
    "hematoma, epidural": "epidural hematoma",
    "intracranial hemorrhage": "intracranial hemorrhage",
    "intracranial hemorrhages": "intracranial hemorrhage",
    "hemorrhage, intracranial": "intracranial hemorrhage",
    "brain concussion": "concussion",
    "concussions": "concussion",
    "diffuse axonal injury": "diffuse axonal injury",
    "axonal injury, diffuse": "diffuse axonal injury",
    "cerebral contusion": "cerebral contusion",
    "contusion, cerebral": "cerebral contusion",
    "ischemic stroke": "ischemic stroke",
    "stroke, ischemic": "ischemic stroke",
    "hemorrhagic stroke": "hemorrhagic stroke",
    "stroke, hemorrhagic": "hemorrhagic stroke",
    "cerebral infarction": "cerebral infarction",
    "infarction, cerebral": "cerebral infarction",
    "coronary artery disease": "coronary artery disease",
    "coronary disease": "coronary artery disease",
    "myocardial infarction": "myocardial infarction",
    "infarction, myocardial": "myocardial infarction",
    "heart failure": "heart failure",
    "cardiac failure": "heart failure",
    "atherosclerosis": "atherosclerosis",
    "arteriosclerosis": "atherosclerosis",
    "peripheral artery disease": "peripheral artery disease",
    "peripheral arterial disease": "peripheral artery disease",
    "gbm": "glioblastoma",
    "glioblastoma multiforme": "glioblastoma",
    "alzheimer's disease": "alzheimer's disease",
    "alzheimer disease": "alzheimer's disease",
    "type 2 diabetes mellitus": "type 2 diabetes",
    "diabetes mellitus, type 2": "type 2 diabetes",
    "type 2 diabetes": "type 2 diabetes",
    "type 1 diabetes mellitus": "type 1 diabetes",
    "diabetes mellitus, type 1": "type 1 diabetes",
    "type 1 diabetes": "type 1 diabetes",
    "breast carcinoma": "breast cancer",
    "breast neoplasms": "breast cancer",
    "breast cancer": "breast cancer",
    "brain neoplasm": "brain neoplasms",
    "brain neoplasms": "brain neoplasms",
    "brain tumor": "brain cancer",
    "brain tumors": "brain cancer",
    "mild cognitive impairment due to alzheimer disease": "mild cognitive impairment due to alzheimer's disease",
    "mild cognitive impairment due to alzheimer's disease": "mild cognitive impairment due to alzheimer's disease",
    "amd": "age-related macular degeneration",
    "wet amd": "age-related macular degeneration",
    "wet macular degeneration": "age-related macular degeneration",
    "wet age-related macular degeneration": "age-related macular degeneration",
    "neovascular age-related macular degeneration": "age-related macular degeneration",
}


def normalize_disease_term(term: str) -> str:
    """Canonical normalization function for disease terms.

    Rules:
    - strip whitespace
    - lowercase
    - collapse whitespace
    - normalize punctuation and possessives
    - resolve curated clinical abbreviations, inverted MeSH terms, and canonical forms
    - do NOT perform aggressive stemming
    - do NOT silently drop clinically meaningful qualifiers
    """
    if not term:
        return ""
    text = term.strip().lower()
    # Normalize possessives (e.g. Alzheimer's -> alzheimer's)
    text = re.sub(r"['’]s\b", "'s", text)
    # Collapse multiple whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Direct canonical synonym lookup
    if text in _CANONICAL_SYNONYMS:
        return _CANONICAL_SYNONYMS[text]

    # Handle MeSH comma-inversion if present: e.g. "hematoma, subdural, chronic"
    if "," in text:
        parts = [p.strip() for p in text.split(",") if p.strip()]
        # Check reverse join: e.g. ["hematoma", "subdural"] -> "subdural hematoma"
        reversed_text = " ".join(reversed(parts))
        if reversed_text in _CANONICAL_SYNONYMS:
            return _CANONICAL_SYNONYMS[reversed_text]
        # Check if first two reversed: e.g. ["hematoma", "subdural", "chronic"]
        if len(parts) >= 2:
            base_rev = f"{parts[1]} {parts[0]}"
            if base_rev in _CANONICAL_SYNONYMS:
                return _CANONICAL_SYNONYMS[base_rev]
        if reversed_text:
            text = reversed_text

    # Strip safe non-alphanumeric trailing/leading punctuation
    text = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", text)

    # Check canonical synonyms again after basic normalization
    if text in _CANONICAL_SYNONYMS:
        return _CANONICAL_SYNONYMS[text]

    # Safe stripping of severity/stage prefixes (excluding subtype distinctions like ischemic/hemorrhagic)
    prefix_stripped = re.sub(
        r"^(?:advanced|metastatic|refractory|relapsed|recurrent|chronic|acute|severe|mild|moderate|early[- ]?stage|late[- ]?stage)\s+",
        "",
        text,
    ).strip()
    if prefix_stripped in _CANONICAL_SYNONYMS:
        return _CANONICAL_SYNONYMS[prefix_stripped]

    return text


def classify_disease_relation(term_a: str, term_b: str) -> DiseaseRelation:
    """Classify the relationship between two disease terms.

    Evaluation order (strict):
    1. Normalize both terms.
    2. If normalized terms are equal:
       => SAME
    3. Explicit sibling exclusion:
       => SIBLING_EXCLUDED (always wins over parent/child or substring containment)
    4. Direct curated parent-child relation:
       => PARENT_CHILD
    5. Otherwise:
       => UNRELATED
    """
    norm_a = normalize_disease_term(term_a)
    norm_b = normalize_disease_term(term_b)

    if not norm_a or not norm_b:
        return DiseaseRelation.UNRELATED

    # Step 2: Exact equality after canonical normalization
    if norm_a == norm_b:
        return DiseaseRelation.SAME

    # Step 3: Explicit sibling exclusions (bidirectional check)
    if (
        norm_b in _SIBLING_EXCLUSIONS.get(norm_a, frozenset())
        or norm_a in _SIBLING_EXCLUSIONS.get(norm_b, frozenset())
    ):
        return DiseaseRelation.SIBLING_EXCLUDED

    # Step 4: Direct curated parent-child relation
    if (
        norm_b in _PARENT_CHILD.get(norm_a, frozenset())
        or norm_a in _PARENT_CHILD.get(norm_b, frozenset())
    ):
        return DiseaseRelation.PARENT_CHILD

    return DiseaseRelation.UNRELATED


def matches_for_trial_attribution(queried_disease: str, trial_condition: str) -> bool:
    """Trial Evidence Matching Policy:
    Allows SAME and PARENT_CHILD relations so clinically recognized subtypes
    are discoverable for the broader hypothesis in clinical trials.
    Rejects SIBLING_EXCLUDED and UNRELATED.
    """
    rel = classify_disease_relation(queried_disease, trial_condition)
    return rel in (DiseaseRelation.SAME, DiseaseRelation.PARENT_CHILD)


def matches_for_approval_anchor(queried_disease: str, chembl_indication: str) -> bool:
    """Rule -1 Approved Indication Matching Policy:
    STRICT: Only DiseaseRelation.SAME creates an approved indication anchor.
    PARENT_CHILD, SIBLING_EXCLUDED, and UNRELATED are strictly rejected to prevent
    broad approval leakage into child indications (e.g. stroke -> hemorrhagic stroke).
    """
    rel = classify_disease_relation(queried_disease, chembl_indication)
    return rel is DiseaseRelation.SAME


@dataclass(frozen=True)
class DiseaseMatchTelemetry:
    """Trace telemetry record for disease relation matching decisions."""
    query_disease: str
    candidate_term: str
    relation: str
    policy: str
    matched: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_disease": self.query_disease,
            "candidate_term": self.candidate_term,
            "relation": self.relation,
            "policy": self.policy,
            "matched": self.matched,
        }


def evaluate_approval_anchor_match(
    queried_disease: str,
    chembl_indication: str,
) -> tuple[bool, DiseaseMatchTelemetry]:
    """Evaluate approval anchor matching with auditable telemetry."""
    rel = classify_disease_relation(queried_disease, chembl_indication)
    matched = (rel is DiseaseRelation.SAME)
    telemetry = DiseaseMatchTelemetry(
        query_disease=queried_disease,
        candidate_term=chembl_indication,
        relation=rel.value,
        policy="APPROVAL_ANCHOR",
        matched=matched,
    )
    return matched, telemetry


def evaluate_trial_attribution_match(
    queried_disease: str,
    trial_condition: str,
) -> tuple[bool, DiseaseMatchTelemetry]:
    """Evaluate trial condition matching with auditable telemetry."""
    rel = classify_disease_relation(queried_disease, trial_condition)
    matched = rel in (DiseaseRelation.SAME, DiseaseRelation.PARENT_CHILD)
    telemetry = DiseaseMatchTelemetry(
        query_disease=queried_disease,
        candidate_term=trial_condition,
        relation=rel.value,
        policy="TRIAL_ATTRIBUTION",
        matched=matched,
    )
    return matched, telemetry
