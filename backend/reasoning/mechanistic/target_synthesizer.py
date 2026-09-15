"""Target ranking and multi-target synthesis (Phase 5.5).

Hierarchy for ranking/preferred targets:
1. Explicit drug mechanism annotation (ChEMBL mechanism text with actionable action)
2. Curated mechanism target (e.g. DrugMechDB or literature-grounded)
3. Mechanistic candidate evidence quality (STRONGLY_SUPPORTED > MODERATELY_SUPPORTED)
4. Target binding affinity / retrieval order as tie-breaker

Rules:
- One drug may have primary, secondary, or promiscuous binding targets.
- Weak secondary targets cannot overwhelm high-quality targets merely through candidate or row count.
- The raw Mechanistic Score formula is preserved: MS remains the raw confidence of the best candidate
  from the top-ranked target.
- Target-level evidence breakdown is exposed in score_components for full auditability.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Sequence

from backend.core.domain.candidate_mechanism import CandidateMechanism
from backend.core.domain.retrieval_package import RetrievalPackage

_ACTIONABLE_MECHANISMS = {
    "INHIBITOR", "INHIBITS", "ANTAGONIST", "BLOCKER",
    "AGONIST", "ACTIVATOR", "ACTIVATES", "OPENER",
    "POSITIVE_ALLOSTERIC_MODULATOR", "NEGATIVE_ALLOSTERIC_MODULATOR",
    "UPREGULATES", "DOWNREGULATES",
}

_SUPPORT_LEVEL_RANKS = {
    "STRONGLY_SUPPORTED": 4,
    "MODERATELY_SUPPORTED": 3,
    "WEAK_SPECULATIVE": 2,
    "CANDIDATE_STRUCTURAL": 2,
    "UNSUPPORTED": 1,
    "CONTRADICTED": 0,
}


def extract_target_identifier(candidate: CandidateMechanism) -> str:
    """Extract canonical target identifier from a candidate mechanism."""
    if candidate.hops:
        hop0 = candidate.hops[0]
        # hop 0 canonical_to_id or to_node
        if hop0.canonical_to_id:
            return hop0.canonical_to_id.strip().upper()
        to_n = hop0.to_node
        if ":" in to_n:
            return to_n.split(":", 1)[1].strip().upper()
        return to_n.strip().upper()
    if len(candidate.summary_chain) > 1:
        node1 = candidate.summary_chain[1]
        if ":" in node1:
            return node1.split(":", 1)[1].strip().upper()
        return node1.strip().upper()
    return "UNKNOWN_TARGET"


def rank_targets_and_synthesize_candidates(
    package: RetrievalPackage,
    candidates: Sequence[CandidateMechanism],
) -> tuple[list[CandidateMechanism], dict[str, Any]]:
    """Rank drug targets and synthesize candidate mechanisms.

    Args:
        package: Sealed RetrievalPackage.
        candidates: Discovered and validated CandidateMechanism objects.

    Returns:
        tuple of:
          - Sorted candidates list (top-ranked target candidates first, highest confidence first)
          - Target synthesis audit dictionary for score_components
    """
    if not candidates:
        fallback_target = ""
        target_source = "none"
        if getattr(package, "targets", None):
            t0 = package.targets[0]
            fallback_target = (
                getattr(t0, "gene_symbol", None)
                or getattr(t0, "protein_uniprot", None)
                or getattr(t0, "name", None)
                or ""
            ).strip().upper()
            if fallback_target:
                target_source = "fallback_no_mechanistic_path"
        return [], {
            "ranked_target": fallback_target,
            "target_source": target_source,
            "target_count": len(getattr(package, "targets", [])),
            "target_ranking_summary": [],
        }

    # Group candidates by target
    candidates_by_target: dict[str, list[CandidateMechanism]] = defaultdict(list)
    for cand in candidates:
        tid = extract_target_identifier(cand)
        candidates_by_target[tid].append(cand)

    # Build target metadata map from package.targets
    target_meta: dict[str, dict[str, Any]] = {}
    for t in getattr(package, "targets", []):
        t_uni = (getattr(t, "protein_uniprot", None) or "").strip().upper()
        t_name = (getattr(t, "name", None) or "").strip().upper()
        mech = (getattr(t, "mechanism", None) or "").strip().upper()
        aff_raw = getattr(t, "affinity_nm", None)
        aff = aff_raw if isinstance(aff_raw, (int, float)) and aff_raw > 0 else 999999.0

        meta = {
            "mechanism": mech,
            "has_explicit_mechanism": mech in _ACTIONABLE_MECHANISMS or any(m in mech for m in _ACTIONABLE_MECHANISMS),
            "affinity_nm": aff,
        }
        if t_uni:
            target_meta[t_uni] = meta
        if t_name:
            target_meta[t_name] = meta

    # Cross-reference protein gene symbols from package.proteins
    for p in getattr(package, "proteins", []):
        p_acc = (getattr(p, "uniprot_accession", None) or "").strip().upper()
        p_sym = (getattr(p, "gene_symbol", None) or "").strip().upper()
        if p_acc and p_acc in target_meta and p_sym:
            target_meta[p_sym] = target_meta[p_acc]

    # Check DrugMechDB curated target validation
    drugmech_targets: set[str] = set()
    for dm in getattr(package, "drugmechdb_evidence", []):
        if dm.target_uniprot:
            drugmech_targets.add(dm.target_uniprot.strip().upper())

    # Score each target
    scored_targets: list[dict[str, Any]] = []
    for tid, target_cands in candidates_by_target.items():
        # Match target meta
        meta = target_meta.get(tid, {})
        if not meta:
            # Try sub-string or pattern match
            for k, v in target_meta.items():
                if k in tid or tid in k:
                    meta = v
                    break

        has_explicit = meta.get("has_explicit_mechanism", False)
        mech_str = meta.get("mechanism", "UNKNOWN")
        aff = meta.get("affinity_nm", 999999.0)
        is_drugmech = any(dm_t in tid for dm_t in drugmech_targets)

        # Best candidate for this target
        best_cand = max(target_cands, key=lambda c: c.confidence_score)
        best_support = best_cand.support_level
        best_support_rank = _SUPPORT_LEVEL_RANKS.get(best_support, 1)
        best_conf = best_cand.confidence_score

        # Ranking score calculation:
        # Tier 1: Explicit drug mechanism (+100)
        # Tier 2: Curated in DrugMechDB (+50)
        # Tier 3: Candidate evidence quality (STRONGLY=40, MODERATELY=30, WEAK=20, UNSUPPORTED=10)
        # Tier 4: Best candidate confidence score (+0.0 to 1.0)
        # Tier 5: Binding affinity tie-breaker (subtract log affinity or tiny bonus)
        rank_score = (
            (100.0 if has_explicit else 0.0)
            + (50.0 if is_drugmech else 0.0)
            + (best_support_rank * 10.0)
            + best_conf
            + (1.0 / (1.0 + aff / 100.0))  # Small tie-breaker: nanomolar affinity
        )

        scored_targets.append({
            "target_id": tid,
            "rank_score": rank_score,
            "has_explicit_mechanism": has_explicit,
            "mechanism": mech_str,
            "is_drugmech_validated": is_drugmech,
            "best_support_level": best_support,
            "best_confidence": round(best_conf, 4),
            "candidate_count": len(target_cands),
            "candidates": sorted(target_cands, key=lambda c: c.confidence_score, reverse=True),
        })

    # Sort targets by rank_score descending with target_id as deterministic tie-breaker
    scored_targets.sort(
        key=lambda item: (round(item["rank_score"], 6), item["target_id"]),
        reverse=True,
    )

    # Flatten candidates with top-ranked target first
    synthesized_candidates: list[CandidateMechanism] = []
    for t_info in scored_targets:
        synthesized_candidates.extend(t_info["candidates"])

    top_target = scored_targets[0]
    # NOTE: 'ranked_target' represents the preferred target for this reasoning run
    # based on explicit annotation, curated validation, and candidate support level;
    # it must NOT be represented as absolute biological ground truth.
    summary = {
        "ranked_target": top_target["target_id"],
        "target_source": "mechanistic_path",
        "ranked_target_mechanism": top_target["mechanism"],
        "ranked_target_support_level": top_target["best_support_level"],
        "ranked_target_confidence": top_target["best_confidence"],
        "target_count": len(scored_targets),
        "target_ranking_summary": [
            {
                "target_id": t["target_id"],
                "rank_score": round(t["rank_score"], 2),
                "support_level": t["best_support_level"],
                "confidence": t["best_confidence"],
                "candidate_count": t["candidate_count"],
            }
            for t in scored_targets
        ],
    }

    return synthesized_candidates, summary
