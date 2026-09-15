# CYNTHERA — API Documentation (Researcher & Frontend Contracts)

This document specifies the public REST API endpoints provided by the CYNTHERA FastAPI service.

Base URL: `http://localhost:8000/api`

---

## 1. Evaluate Hypothesis

### `POST /api/analyze`

Executes the full 10-step epistemic reasoning pipeline across multi-database sources, applies empirical clinical opposition vetoes (Rule 2b), and returns the complete structured analysis response.

#### Request Body
```json
{
  "drug": "Azithromycin",
  "disease": "COVID-19",
  "policy": "STANDARD",
  "bypass_cache": false
}
```

| Field | Type | Description |
|---|---|---|
| `drug` | string | Common or canonical name of the drug compound (e.g. "Azithromycin", "Aspirin"). |
| `disease` | string | Target disease, indication, or MeSH term (e.g. "COVID-19", "Hypertension"). |
| `policy` | string | Retrieval depth: `STANDARD` (default), `FAST` (cached prior knowledge), or `COMPREHENSIVE` (deep retrieval). |
| `bypass_cache` | boolean | If `true`, bypasses stored evaluation cache and re-queries live APIs. Default `false`. |

#### Response (HTTP 200 OK)
```json
{
  "analysis_id": "338359ef-11f5-4696-8f5a-aa4b94f640c7",
  "hypothesis_id": "338359ef-11f5-4696-8f5a-aa4b94f640c7",
  "status": "completed",
  "duration_ms": 1420.5,
  "rule_set_version": "3.2",
  "drug": {
    "name": "Azithromycin",
    "chembl_id": "CHEMBL644",
    "canonical_smiles": "...",
    "synonyms": ["Zithromax"],
    "global_approval_phase": 4,
    "matched_indication_phase": 3
  },
  "disease": {
    "name": "COVID-19",
    "mesh_id": "D000086382",
    "mondo_id": "MONDO:0100096",
    "efo_id": null,
    "synonyms": []
  },
  "decision": {
    "verdict": "OPPOSE",
    "recommendation": "NOT_RECOMMENDED",
    "rationale": "Pair-specific negative clinical evidence contradicts efficacy.",
    "therapeutic_anchor": false,
    "mechanistic_evidence": "LOW",
    "therapeutic_evidence": "LOW",
    "opposition": "HIGH",
    "contradiction": "MODERATE",
    "safety_grade": "B",
    "safety_summary": "Risk level: MEDIUM"
  },
  "mechanism": {
    "score": 0.25,
    "level": "LOW",
    "primary_chain": ["Azithromycin", "50S Ribosome", "Bacterial translation"],
    "pathway_count": 1,
    "candidate_mechanisms": [...],
    "targets": [...],
    "evidence_status": "INSUFFICIENT_EVIDENCE",
    "literature_grounding_level": "NONE",
    "rationale": "Target not directly causative in viral pathophysiology."
  },
  "therapeutic_evidence": [
    {
      "id": "item-1",
      "evidence_type": "RCT",
      "source": "ClinicalTrials.gov",
      "citation_key": "NCT04885530",
      "title": "Evaluation of Azithromycin in Hospitalized COVID-19 Patients",
      "direction": "OPPOSES",
      "quality_tier": "HIGH",
      "pair_specificity": true,
      "independent_group": "study:NCT04885530",
      "extracted_claim": "Azithromycin did not improve clinical mortality.",
      "study_type": "INTERVENTIONAL",
      "outcome": "Terminated for futility",
      "why_stopped": "Lack of efficacy at interim analysis",
      "source_url": "https://clinicaltrials.gov/study/NCT04885530"
    }
  ],
  "opposition": {
    "score": 0.85,
    "level": "HIGH",
    "qualified_negative_claim_count": 2,
    "excluded_negative_claim_count": 0,
    "independent_group_count": 2,
    "key_claims": [...],
    "rationale": "Two pair-specific RCTs demonstrated no clinical benefit."
  },
  "contradictions": [
    {
      "id": "c-1",
      "conflict_type": "OUTCOME_DISCORDANCE",
      "severity": "MODERATE",
      "supporting_records": ["ChEMBL:25"],
      "opposing_records": ["NCT04885530"],
      "explanation": "In vitro antiviral claims contradicted by human clinical trial outcomes.",
      "resolution": "CLINICAL_OPPOSITION_DOMINATES"
    }
  ],
  "safety": {
    "risk_score": 0.65,
    "risk_level": "MEDIUM",
    "safety_grade": "B",
    "failed_trial_count": 2,
    "adverse_event_count": 1,
    "summary": "QT prolongation risk documented.",
    "signals": {}
  },
  "provenance": {
    "raw_record_count": 48,
    "deduplicated_record_count": 16,
    "independent_group_count": 8,
    "retrieval_timestamp": "2026-09-06T15:30:00Z",
    "sources": [
      {
        "name": "ClinicalTrials.gov",
        "status": "available",
        "retrieved_count": 17,
        "used_count": 4,
        "excluded_count": 13,
        "reason_for_exclusion": "Filtered by specificity or quality gate",
        "impact": "Evidence synthesized in reasoning chain"
      }
    ]
  },
  "sources": {
    "queried": ["ChEMBL", "PubMed", "ClinicalTrials.gov"],
    "failed": ["Semantic Scholar"],
    "breakdown": [...]
  },
  "limitations": [
    "Source 'Semantic Scholar' was unavailable during retrieval. Literature or pathway coverage may be incomplete."
  ],
  "audit_trace": {
    "evaluation_pathway": "PHASE_III_INVESTIGATION",
    "agent_verdicts": {
      "SupportAssessmentAgent": "LOW",
      "MechanisticExpertAgent": "LOW",
      "RiskAssessmentAgent": "HIGH",
      "OppositionAssessmentAgent": "HIGH"
    }
  }
}
```

---

## 2. Retrieve Stored Analysis

### `GET /api/analyze/{analysis_id}`
Retrieves a previously evaluated analysis result by its UUID.

---

## 3. Retrieve Evidence Ledger

### `GET /api/analyze/{analysis_id}/evidence`
Returns the array of individual `TherapeuticEvidenceItem` objects with provenance details, quality tiers, directions, and canonical external URLs.

---

## 4. Retrieve Structured Scientific Report

### `GET /api/analyze/{analysis_id}/report`
Returns the structured 15-section scientific report model (`ReportModelDTO`) ready for in-browser presentation, audit, and archiving.

---

## 5. Download Research-Grade PDF

### `GET /api/analyze/{analysis_id}/report/pdf`
Streams the server-side generated PDF binary (`application/pdf`) built with ReportLab, featuring:
- Executive Summary & Evaluated Hypothesis
- Three-Dimensional Score Table
- Reaction-Enriched Mechanistic Chains
- Therapeutic Opposition & Rule 2b Veto Breakdown
- Contradiction Conflict Registry
- Traceable Reasoning Path Flowchart
- Numbered Canonical References with verified hyperlinks
