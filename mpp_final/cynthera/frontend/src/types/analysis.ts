export type DecisionVerdict = 'SUPPORT' | 'OPPOSE' | 'UNCERTAIN';
export type RecommendationStatus = 'PROMISING' | 'NOT_RECOMMENDED' | 'UNCERTAIN';

export type EvidenceLevel = 'HIGH' | 'MODERATE' | 'LOW' | 'NONE';
export type ContradictionSeverity = 'NONE' | 'MINOR' | 'MODERATE' | 'STRONG';
export type EvidenceDirection = 'SUPPORTS' | 'OPPOSES' | 'UNCERTAIN' | 'UNKNOWN';
export type EvidenceQualityTier = 'HIGH' | 'MODERATE' | 'LOW' | 'UNVERIFIED';

export interface DrugInfo {
  name: string;
  chembl_id: string | null;
  canonical_smiles: string | null;
  synonyms: string[];
  global_approval_phase: number;
  matched_indication_phase: number;
}

export interface DiseaseInfo {
  name: string;
  mesh_id: string | null;
  mondo_id: string | null;
  efo_id: string | null;
  synonyms: string[];
}

export interface DecisionData {
  verdict: DecisionVerdict;
  recommendation: RecommendationStatus;
  hypothesis_status?: string;
  repurposing_novelty?: string;
  evidence_support_score?: number;
  evidence_support_tier?: string;
  risk_score?: number;
  opposition_score?: number;
  rationale: string;
  therapeutic_anchor: boolean;
  mechanistic_evidence: EvidenceLevel;
  therapeutic_evidence: 'HIGH' | 'MODERATE' | 'LOW';
  opposition: EvidenceLevel;
  contradiction: ContradictionSeverity;
  safety_grade: string;
  safety_summary: string;
  structured_why?: Array<{ step: string; detail: string; status: string }>;
}

export interface TargetInfo {
  symbol: string;
  uniprot_id: string;
  name: string;
  chembl_id: string | null;
  mechanism_count: number;
  disease_relevance: number;
  evidence_count: number;
  affinity_nm: number | null;
  source: string;
  source_url: string | null;
}

export interface MechanismHop {
  from_node: string;
  to_node: string;
  predicate: string;
  status: string;
  evidence_strength: number;
  source_database: string;
  provenance_note: string;
  polarity: 'POSITIVE' | 'NEGATIVE' | 'UNKNOWN';
  causal_grounding: 'DIRECT' | 'CURATED' | 'INFERRED' | 'STRUCTURAL' | 'NONE';
  evidence_type: 'DIRECT' | 'CURATED' | 'STRUCTURAL' | 'LITERATURE';
  source_url: string | null;
}

export interface CandidateMechanism {
  candidate_id: string;
  target: string;
  pathway: string;
  biological_process: string;
  hops: MechanismHop[];
  support_level: string;
  overall_confidence: number;
  rationale: string;
}

export interface MechanismData {
  score: number;
  level: EvidenceLevel;
  primary_chain: string[];
  pathway_count: number;
  candidate_mechanisms: CandidateMechanism[];
  targets: TargetInfo[];
  evidence_status: string;
  literature_grounding_level: string;
  rationale: string;
}

export interface TherapeuticEvidenceItem {
  id: string;
  evidence_type: string;
  source: string;
  citation_key: string;
  title: string | null;
  abstract: string | null;
  direction: EvidenceDirection;
  quality_tier: EvidenceQualityTier;
  pair_specificity: boolean;
  independent_group: string;
  extracted_claim: string | null;
  study_type: string | null;
  outcome: string | null;
  why_stopped: string | null;
  target: string | null;
  pathway: string | null;
  source_url: string | null;
  provenance_id: string | null;
  retrieved_at: string | null;
  drug_name?: string | null;
  disease_name?: string | null;
}

export interface OppositionData {
  score: number;
  level: EvidenceLevel;
  qualified_negative_claim_count: number;
  excluded_negative_claim_count: number;
  independent_group_count: number;
  key_claims: TherapeuticEvidenceItem[];
  rationale: string;
}

export interface ContradictionItem {
  id: string;
  conflict_type: string;
  severity: ContradictionSeverity;
  supporting_records: string[];
  opposing_records: string[];
  explanation: string;
  resolution: string;
}

export interface SafetyData {
  risk_score: number;
  risk_level: string;
  safety_grade: string;
  failed_trial_count: number;
  adverse_event_count: number;
  summary: string;
  signals: Record<string, unknown>;
}

export interface SourceStatus {
  name: string;
  status: 'available' | 'unavailable' | 'partial';
  retrieved_count: number;
  used_count: number;
  excluded_count: number;
  reason_for_exclusion: string | null;
  impact: string | null;
  canonical_portal_url: string | null;
}

export interface ProvenanceData {
  raw_record_count: number;
  deduplicated_record_count: number;
  independent_group_count: number;
  retrieval_timestamp: string;
  sources: SourceStatus[];
}

export interface AnalysisResult {
  analysis_id: string;
  hypothesis_id: string;
  status: 'completed' | 'partial' | 'failed';
  duration_ms: number;
  rule_set_version: string;
  drug: DrugInfo;
  disease: DiseaseInfo;
  decision: DecisionData;
  mechanism: MechanismData;
  therapeutic_evidence: TherapeuticEvidenceItem[];
  opposition: OppositionData;
  contradictions: ContradictionItem[];
  safety: SafetyData;
  provenance: ProvenanceData;
  sources: {
    queried: string[];
    failed: string[];
    breakdown: SourceStatus[];
  };
  limitations: string[];
  audit_trace: {
    agent_verdicts?: Record<string, string>;
    top_citations?: string[];
    positive_factors?: string[];
    negative_factors?: string[];
    evaluation_pathway?: string;
  };
}

export interface ReportReference {
  id: string;
  citation_key: string;
  title: string;
  source: string;
  url: string;
}

export interface ReportModel {
  report_version: string;
  generated_at: string;
  analysis_id: string;
  drug: DrugInfo;
  disease: DiseaseInfo;
  evaluated_hypothesis: string;
  executive_summary: string;
  decision: DecisionData;
  evidence_overview: {
    supporting_count: number;
    opposing_count: number;
    uncertain_count: number;
    independent_groups: number;
  };
  entity_resolution: {
    drug_canonical_id: string;
    drug_synonyms: string[];
    disease_mesh_id: string;
    disease_mondo_id: string;
  };
  regulatory_evidence: {
    has_anchor: boolean;
    matched_indication_phase: number;
    global_approval_phase: number;
  };
  mechanistic_evidence: MechanismData;
  therapeutic_evidence: TherapeuticEvidenceItem[];
  opposing_evidence: OppositionData;
  contradictions: ContradictionItem[];
  evidence_independence: {
    raw_records: number;
    deduplicated_records: number;
    independent_groups: number;
  };
  safety_analysis: SafetyData;
  final_reasoning: {
    decision: DecisionVerdict;
    recommendation: RecommendationStatus;
    rationale: string;
    positive_factors: string[];
    negative_factors: string[];
  };
  limitations: string[];
  evidence_ledger: TherapeuticEvidenceItem[];
  references: ReportReference[];
}
