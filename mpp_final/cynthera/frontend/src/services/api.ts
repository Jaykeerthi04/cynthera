import { AnalysisResult, ReportModel, TherapeuticEvidenceItem } from '../types/analysis';

const API_BASE = '/api';

export interface AnalyzeParams {
  drug: string;
  disease: string;
  policy?: 'STANDARD' | 'FAST' | 'COMPREHENSIVE';
  bypass_cache?: boolean;
}

export async function submitAnalysis(params: AnalyzeParams): Promise<AnalysisResult> {
  const response = await fetch(`${API_BASE}/analyze`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      drug: params.drug.trim(),
      disease: params.disease.trim(),
      policy: params.policy || 'STANDARD',
      bypass_cache: Boolean(params.bypass_cache),
    }),
  });

  if (!response.ok) {
    let errMessage = `HTTP error ${response.status}`;
    try {
      const errData = await response.json();
      if (errData.detail) {
        errMessage = typeof errData.detail === 'string' ? errData.detail : JSON.stringify(errData.detail);
      }
    } catch {
      // ignore
    }
    throw new Error(errMessage);
  }

  return response.json();
}

export async function fetchAnalysis(analysisId: string): Promise<AnalysisResult> {
  const response = await fetch(`${API_BASE}/analyze/${encodeURIComponent(analysisId)}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch analysis (${response.status})`);
  }
  return response.json();
}

export async function fetchEvidenceLedger(analysisId: string): Promise<TherapeuticEvidenceItem[]> {
  const response = await fetch(`${API_BASE}/analyze/${encodeURIComponent(analysisId)}/evidence`);
  if (!response.ok) {
    throw new Error(`Failed to fetch evidence ledger (${response.status})`);
  }
  return response.json();
}

export async function fetchReport(analysisId: string): Promise<ReportModel> {
  const response = await fetch(`${API_BASE}/analyze/${encodeURIComponent(analysisId)}/report`);
  if (!response.ok) {
    throw new Error(`Failed to fetch scientific report (${response.status})`);
  }
  return response.json();
}

export function getPdfReportUrl(analysisId: string): string {
  return `${API_BASE}/analyze/${encodeURIComponent(analysisId)}/report/pdf`;
}
