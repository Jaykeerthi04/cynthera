"""Evidence and Weighting Panel component for CYNTHERA frontend."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from typing import Any

from backend.evaluation.evidence_weights import (
    CALIBRATION_METADATA,
    CALIBRATION_SELECTED_CONFIG,
    WEIGHT_CONFIGS,
)


def render_evidence_panel(result: Any, package: Any | None = None) -> None:
    """Render the Evidence Family breakdown and frozen Evidence Weighting metadata.

    Displays:
    - Evidence family counts (GENETIC, CLINICAL_TRIAL, etc.)
    - Frozen calibration configuration (CONFIG_A)
    - Epistemic grounding tier weights (read-only)
    """
    st.markdown("### 📚 Evidence Breakdown & Frozen Calibration")

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### Evidence Sources Breakdown")
        family_summary = {}

        # Safe extraction from audit report or therapeutic alignment
        if hasattr(result, "audit_report") and result.audit_report:
            ta = getattr(result.audit_report, "therapeutic_alignment", {}) or {}
            target_aligns = ta.get("target_alignments", [])
            for t in target_aligns:
                for eg in t.get("evidence_groups", []):
                    fam = str(eg.get("evidence_family", "UNKNOWN"))
                    family_summary[fam] = family_summary.get(fam, 0) + 1

        if not family_summary and package is not None:
            # Fallback to package counts
            if hasattr(package, "opentargets_doe_evidence"):
                family_summary["GENETIC (OpenTargets)"] = len(package.opentargets_doe_evidence)
            if hasattr(package, "datts_evidence"):
                family_summary["CURATED_REFERENCE (DATTs)"] = len(package.datts_evidence)
            if hasattr(package, "drugmechdb_evidence"):
                family_summary["MECHANISTIC_DB (DrugMechDB)"] = len(package.drugmechdb_evidence)
            if hasattr(package, "literature_evidence"):
                family_summary["LITERATURE (PubMed/PMC)"] = len(package.literature_evidence)
            if hasattr(package, "reactome_reaction_evidence"):
                family_summary["STRUCTURAL (Reactome)"] = len(package.reactome_reaction_evidence)

        if family_summary:
            df_fam = pd.DataFrame(
                [{"Evidence Family": k, "Independent Groups": v} for k, v in sorted(family_summary.items())]
            )
            st.dataframe(df_fam, hide_index=True, use_container_width=True)
        else:
            st.info("No evidence family records mapped for this evaluation.")

    with col_right:
        st.markdown("#### Evidence Weighting (Production Calibration)")
        
        cfg = WEIGHT_CONFIGS.get(CALIBRATION_SELECTED_CONFIG, WEIGHT_CONFIGS["DEFAULT_HEURISTIC"])
        
        weights_data = [
            {"Grounding Tier": "DIRECT (Clinical / LoF-protect)", "Weight": f"{cfg.direct:.1f}"},
            {"Grounding Tier": "CURATED (Expert databases / DrugMechDB)", "Weight": f"{cfg.curated:.1f}"},
            {"Grounding Tier": "INFERRED (Inferred literature claims)", "Weight": f"{cfg.inferred:.1f}"},
            {"Grounding Tier": "STRUCTURAL (Pathway topology / Reactome)", "Weight": f"{cfg.structural:.1f} (Strict Zero)"},
            {"Grounding Tier": "NONE (Uncharacterized)", "Weight": f"{cfg.none:.1f} (Strict Zero)"},
        ]
        
        st.dataframe(pd.DataFrame(weights_data), hide_index=True, use_container_width=True)
        
        st.info(
            f"⚙️ **Configuration: `{CALIBRATION_SELECTED_CONFIG}`** | **Status: `{CALIBRATION_METADATA.status}`**\n\n"
            "Evidence weighting is calibrated strictly on the DEVELOPMENT split and frozen for evaluation. "
            "Structural evidence strictly carries 0.0 directional weight to prevent topology from fabricating causality."
        )
