import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DecisionCard } from '../components/decision/DecisionCard';
import { SourceAvailabilityBanner } from '../components/provenance/SourceAvailabilityBanner';
import { OpposingEvidenceCard } from '../components/evidence/OpposingEvidenceCard';
import { ContradictionPanel } from '../components/conflicts/ContradictionPanel';
import { EvidenceTraceDrawer } from '../components/evidence/EvidenceTraceDrawer';
import { ReportViewer } from '../components/reports/ReportViewer';
import { resolveCanonicalUrl, getPubMedUrl, getClinicalTrialsUrl, getChEMBLCompoundUrl } from '../utils/sourceLinks';
import { DecisionData, DrugInfo, DiseaseInfo, TherapeuticEvidenceItem, OppositionData, ReportModel } from '../types/analysis';

describe('CYNTHERA Frontend Validation Suite', () => {
  const dummyDrug: DrugInfo = {
    name: 'Azithromycin',
    chembl_id: 'CHEMBL644',
    canonical_smiles: 'CCC...',
    synonyms: ['Zithromax'],
    global_approval_phase: 4,
    matched_indication_phase: 3,
  };

  const dummyDisease: DiseaseInfo = {
    name: 'COVID-19',
    mesh_id: 'D000086382',
    mondo_id: 'MONDO:0100096',
    efo_id: null,
    synonyms: ['SARS-CoV-2 Infection'],
  };

  // 1. SUPPORT renders correctly
  it('renders SUPPORT decision correctly', () => {
    const decision: DecisionData = {
      verdict: 'SUPPORT',
      recommendation: 'PROMISING',
      rationale: 'Established indication confirmed.',
      therapeutic_anchor: true,
      mechanistic_evidence: 'HIGH',
      therapeutic_evidence: 'HIGH',
      opposition: 'NONE',
      contradiction: 'NONE',
      safety_grade: 'A',
      safety_summary: 'Well-tolerated safety profile.',
    };
    render(<DecisionCard decision={decision} drug={dummyDrug} disease={dummyDisease} />);
    expect(screen.getByText('SUPPORT')).toBeDefined();
    expect(screen.getByText('PROMISING')).toBeDefined();
    expect(screen.getByText('Established indication confirmed.')).toBeDefined();
  });

  // 2. OPPOSE renders correctly
  it('renders OPPOSE decision correctly', () => {
    const decision: DecisionData = {
      verdict: 'OPPOSE',
      recommendation: 'NOT_RECOMMENDED',
      rationale: 'Pair-specific negative clinical trial evidence.',
      therapeutic_anchor: false,
      mechanistic_evidence: 'LOW',
      therapeutic_evidence: 'LOW',
      opposition: 'HIGH',
      contradiction: 'NONE',
      safety_grade: 'HIGH_RISK',
      safety_summary: 'Significant safety signals.',
    };
    render(<DecisionCard decision={decision} drug={dummyDrug} disease={dummyDisease} />);
    expect(screen.getByText('OPPOSE')).toBeDefined();
    expect(screen.getByText('NOT RECOMMENDED')).toBeDefined();
    expect(screen.getByText('Pair-specific negative clinical trial evidence.')).toBeDefined();
  });

  // 3. UNCERTAIN renders correctly
  it('renders UNCERTAIN decision correctly', () => {
    const decision: DecisionData = {
      verdict: 'UNCERTAIN',
      recommendation: 'UNCERTAIN',
      rationale: 'Insufficient data to confirm therapeutic benefit.',
      therapeutic_anchor: false,
      mechanistic_evidence: 'LOW',
      therapeutic_evidence: 'LOW',
      opposition: 'NONE',
      contradiction: 'NONE',
      safety_grade: 'B',
      safety_summary: 'Standard profile.',
    };
    render(<DecisionCard decision={decision} drug={dummyDrug} disease={dummyDisease} />);
    expect(screen.getAllByText('UNCERTAIN').length).toBeGreaterThan(0);
    expect(screen.getByText('Insufficient data to confirm therapeutic benefit.')).toBeDefined();
  });

  // 4. Recommendation is independent from prediction (not inferred in frontend)
  it('displays independent recommendation without overriding prediction', () => {
    const decision: DecisionData = {
      verdict: 'SUPPORT',
      recommendation: 'UNCERTAIN', // Intentionally discordant to test independence
      rationale: 'Mechanistically plausible but clinical data pending.',
      therapeutic_anchor: false,
      mechanistic_evidence: 'HIGH',
      therapeutic_evidence: 'LOW',
      opposition: 'NONE',
      contradiction: 'NONE',
      safety_grade: 'A',
      safety_summary: '',
    };
    render(<DecisionCard decision={decision} drug={dummyDrug} disease={dummyDisease} />);
    expect(screen.getByText('SUPPORT')).toBeDefined();
    expect(screen.getByText('UNCERTAIN')).toBeDefined();
  });

  // 5. UNKNOWN is not rendered as NEGATIVE
  it('ensures UNKNOWN or sparse evidence is not displayed as NEGATIVE or 0 evidence', () => {
    const decision: DecisionData = {
      verdict: 'UNCERTAIN',
      recommendation: 'UNCERTAIN',
      rationale: 'Sparse evidence.',
      therapeutic_anchor: false,
      mechanistic_evidence: 'NONE',
      therapeutic_evidence: 'LOW',
      opposition: 'NONE',
      contradiction: 'NONE',
      safety_grade: 'B',
      safety_summary: '',
    };
    render(<DecisionCard decision={decision} drug={dummyDrug} disease={dummyDisease} />);
    expect(screen.getByText('No qualifying anchor identified')).toBeDefined();
    expect(screen.queryByText('0 evidence')).toBeNull();
  });

  // 6. Missing source is shown as unavailable, not silent absence
  it('shows missing source as unavailable rather than implying no evidence exists', () => {
    render(<SourceAvailabilityBanner failedSources={['Semantic Scholar', 'Europe PMC']} />);
    expect(screen.getByText(/Limited Source Availability/i)).toBeDefined();
    expect(screen.getByText(/Semantic Scholar, Europe PMC/i)).toBeDefined();
    expect(screen.getByText(/This is NOT equivalent to "no evidence exists in these sources"/i)).toBeDefined();
  });

  // 7 & 8. Source links use canonical URLs and reject fabricated URLs
  it('builds canonical source URLs and rejects invalid identifiers without fabricating links', () => {
    expect(getPubMedUrl('33887462')).toBe('https://pubmed.ncbi.nlm.nih.gov/33887462/');
    expect(getPubMedUrl('invalid-pmid')).toBeNull();

    expect(getClinicalTrialsUrl('NCT04885530')).toBe('https://clinicaltrials.gov/study/NCT04885530');
    expect(getClinicalTrialsUrl('random_trial_id')).toBeNull();

    expect(getChEMBLCompoundUrl('CHEMBL25')).toBe('https://www.ebi.ac.uk/chembl/compound_report_card/CHEMBL25/');
    expect(getChEMBLCompoundUrl('fake_chembl')).toBeNull();

    expect(resolveCanonicalUrl('NCT04885530', 'ClinicalTrials.gov')).toBe('https://clinicaltrials.gov/study/NCT04885530');
    expect(resolveCanonicalUrl('unsupported_key', 'unknown_source')).toBeNull();
  });

  // 9 & 10. Evidence detail opens correctly and provenance fields remain intact
  it('renders EvidenceTraceDrawer with intact provenance and claim text', () => {
    const item: TherapeuticEvidenceItem = {
      id: 'item-1',
      evidence_type: 'RCT',
      source: 'ClinicalTrials.gov',
      citation_key: 'NCT04885530',
      title: 'Evaluation of Azithromycin in Hospitalized COVID-19 Patients',
      abstract: 'Randomized controlled trial demonstrating lack of efficacy.',
      direction: 'OPPOSES',
      quality_tier: 'HIGH',
      pair_specificity: true,
      independent_group: 'study:NCT04885530',
      extracted_claim: 'Azithromycin did not improve 28-day clinical mortality.',
      study_type: 'INTERVENTIONAL',
      outcome: 'Terminated for futility',
      why_stopped: 'Lack of efficacy at interim analysis',
      target: null,
      pathway: null,
      source_url: 'https://clinicaltrials.gov/study/NCT04885530',
      provenance_id: 'prov-001',
      retrieved_at: '2026-09-06T12:00:00Z',
    };

    const handleClose = vi.fn();
    render(<EvidenceTraceDrawer evidence={item} onClose={handleClose} />);

    expect(screen.getByText('Evidence Trace & Provenance')).toBeDefined();
    expect(screen.getByText('NCT04885530')).toBeDefined();
    expect(screen.getByText(/Termination Reason: Lack of efficacy at interim analysis/i)).toBeDefined();
    expect(screen.getByText(/"Azithromycin did not improve 28-day clinical mortality."/i)).toBeDefined();
    expect(screen.getByText('study:NCT04885530')).toBeDefined();

    // Close button
    const closeBtn = screen.getByLabelText('Close drawer');
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  // 11. Opposition evidence is visible
  it('renders OpposingEvidenceCard prominently when opposition exists', () => {
    const oppItem: TherapeuticEvidenceItem = {
      id: 'opp-1',
      evidence_type: 'RCT',
      source: 'ClinicalTrials.gov',
      citation_key: 'NCT04885530',
      title: 'Negative Trial',
      abstract: 'Terminated',
      direction: 'OPPOSES',
      quality_tier: 'HIGH',
      pair_specificity: true,
      independent_group: 'study:NCT04885530',
      extracted_claim: 'Failed to meet primary endpoint',
      study_type: 'RCT',
      outcome: 'FAILED',
      why_stopped: 'Futility',
      target: null,
      pathway: null,
      source_url: null,
      provenance_id: null,
      retrieved_at: null,
    };
    const opp: OppositionData = {
      score: 0.85,
      level: 'HIGH',
      qualified_negative_claim_count: 1,
      excluded_negative_claim_count: 0,
      independent_group_count: 1,
      key_claims: [oppItem],
      rationale: 'Published RCT outcome shows no clinical benefit.',
    };

    render(<OpposingEvidenceCard opposition={opp} onSelectEvidence={vi.fn()} />);
    expect(screen.getByText(/Opposing Evidence & Clinical Trial Failures/i)).toBeDefined();
    expect(screen.getByText('Opposition: HIGH (0.85)')).toBeDefined();
    expect(screen.getByText(/Termination Reason: Futility/i)).toBeDefined();
  });

  // 12. Contradiction evidence is visible
  it('renders ContradictionPanel with visual conflict schematic and explanations', () => {
    render(
      <ContradictionPanel
        contradictions={[
          {
            id: 'c-1',
            conflict_type: 'OUTCOME_DISCORDANCE',
            severity: 'MODERATE',
            supporting_records: ['ChEMBL:25'],
            opposing_records: ['NCT04885530'],
            explanation: 'Historical in vitro activity contradicted by human clinical trials.',
            resolution: 'CLINICAL_OPPOSITION_DOMINATES',
          },
        ]}
        severity="MODERATE"
      />
    );
    expect(screen.getByText(/Evidence Contradiction & Discordance/i)).toBeDefined();
    expect(screen.getByText('Severity: MODERATE')).toBeDefined();
    expect(screen.getByText('SUPPORTING CLAIMS')).toBeDefined();
    expect(screen.getByText('OPPOSING OUTCOMES')).toBeDefined();
    expect(screen.getByText(/Historical in vitro activity contradicted by human clinical trials./i)).toBeDefined();
  });

  // 14, 15, 16, 17. Report contains references, links, limitations, and traceability
  it('renders full ReportViewer with 15 sections, canonical links, and limitations', () => {
    const dummyReport: ReportModel = {
      report_version: '1.0',
      generated_at: '2026-09-06T12:00:00Z',
      analysis_id: '338359ef-11f5-4696-8f5a-aa4b94f640c7',
      drug: dummyDrug,
      disease: dummyDisease,
      evaluated_hypothesis: 'Evaluated hypothesis: Azithromycin may have utility for COVID-19.',
      executive_summary: 'Evidence analysis indicates empirical opposition dominating hypothesis.',
      decision: {
        verdict: 'OPPOSE',
        recommendation: 'NOT_RECOMMENDED',
        rationale: 'Clinical trial termination veto.',
        therapeutic_anchor: false,
        mechanistic_evidence: 'LOW',
        therapeutic_evidence: 'LOW',
        opposition: 'HIGH',
        contradiction: 'MODERATE',
        safety_grade: 'B',
        safety_summary: 'Trial failure observed.',
      },
      evidence_overview: {
        supporting_count: 2,
        opposing_count: 2,
        uncertain_count: 1,
        independent_groups: 3,
      },
      entity_resolution: {
        drug_canonical_id: 'CHEMBL644',
        drug_synonyms: ['Zithromax'],
        disease_mesh_id: 'D000086382',
        disease_mondo_id: 'MONDO:0100096',
      },
      regulatory_evidence: {
        has_anchor: false,
        matched_indication_phase: 0,
        global_approval_phase: 4,
      },
      mechanistic_evidence: {
        score: 0.25,
        level: 'LOW',
        primary_chain: ['Azithromycin', '50S Ribosome', 'Bacterial translation'],
        pathway_count: 1,
        candidate_mechanisms: [],
        targets: [],
        evidence_status: 'INSUFFICIENT_EVIDENCE',
        literature_grounding_level: 'NONE',
        rationale: 'Target not directly causative in viral pathophysiology.',
      },
      therapeutic_evidence: [],
      opposing_evidence: {
        score: 0.85,
        level: 'HIGH',
        qualified_negative_claim_count: 2,
        excluded_negative_claim_count: 0,
        independent_group_count: 2,
        key_claims: [],
        rationale: 'Negative trials documented.',
      },
      contradictions: [],
      evidence_independence: {
        raw_records: 12,
        deduplicated_records: 6,
        independent_groups: 3,
      },
      safety_analysis: {
        risk_score: 0.65,
        risk_level: 'MEDIUM',
        safety_grade: 'B',
        failed_trial_count: 2,
        adverse_event_count: 1,
        summary: 'QT prolongation risk.',
        signals: {},
      },
      final_reasoning: {
        decision: 'OPPOSE',
        recommendation: 'NOT_RECOMMENDED',
        rationale: 'Empirical opposition veto Rule 2b applied.',
        positive_factors: ['Preclinical in vitro paper'],
        negative_factors: ['Published randomized controlled trial failure'],
      },
      limitations: [
        'Semantic Scholar unavailable during analysis.',
        'No active regulatory indication for evaluated disease.',
      ],
      evidence_ledger: [],
      references: [
        {
          id: '1',
          citation_key: 'NCT04885530',
          title: 'Trial of Azithromycin',
          source: 'ClinicalTrials.gov',
          url: 'https://clinicaltrials.gov/study/NCT04885530',
        },
      ],
    };

    render(<ReportViewer report={dummyReport} onBack={vi.fn()} />);

    expect(screen.getByText('1. Executive Summary')).toBeDefined();
    expect(screen.getByText('2. Evaluated Hypothesis')).toBeDefined();
    expect(screen.getByText('13. Limitations & Source Availability Gaps')).toBeDefined();
    expect(screen.getByText(/Semantic Scholar unavailable during analysis/i)).toBeDefined();
    expect(screen.getByText('15. Canonical References')).toBeDefined();
    expect(screen.getByText('NCT04885530')).toBeDefined();
    expect(screen.getByText('[Open canonical record]')).toBeDefined();
  });
});
