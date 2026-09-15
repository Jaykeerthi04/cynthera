import React from 'react';
import { Download, Printer, ArrowLeft, ExternalLink, ShieldAlert, CheckCircle2, XCircle } from 'lucide-react';
import { ReportModel } from '../../types/analysis';
import { Badge } from '../common/Badge';
import { getPdfReportUrl } from '../../services/api';

export interface ReportViewerProps {
  report: ReportModel;
  onBack: () => void;
}

export const ReportViewer: React.FC<ReportViewerProps> = ({ report, onBack }) => {
  const pdfUrl = getPdfReportUrl(report.analysis_id);

  return (
    <div style={{ maxWidth: '960px', margin: '0 auto', padding: '2rem 1rem' }}>
      {/* Header Actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '0.75rem' }}>
        <button onClick={onBack} className="btn btn-secondary">
          <ArrowLeft size={16} /> Back to Analysis
        </button>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button onClick={() => window.print()} className="btn btn-secondary">
            <Printer size={16} /> Print Report
          </button>
          <a href={pdfUrl} target="_blank" rel="noopener noreferrer" className="btn btn-primary">
            <Download size={16} /> Export Detailed PDF
          </a>
        </div>
      </div>

      {/* Main Report Document */}
      <div style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border-color)',
        borderRadius: '8px',
        padding: '2.5rem',
        boxShadow: 'var(--shadow-sm)',
        fontSize: '0.9rem',
        lineHeight: 1.6
      }}>
        {/* Document Header */}
        <div style={{ borderBottom: '2px solid var(--primary-accent)', paddingBottom: '1.25rem', marginBottom: '2rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <span style={{ fontSize: '0.8rem', fontWeight: 700, letterSpacing: '0.05em', color: 'var(--primary-accent)', textTransform: 'uppercase' }}>
                CYNTHERA Evidence Synthesis
              </span>
              <h1 style={{ fontSize: '1.8rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.2rem' }}>
                Drug–Disease Hypothesis Evaluation Report
              </h1>
            </div>
            <div style={{ textAlign: 'right', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              <div>Generated: {new Date(report.generated_at).toUTCString()}</div>
              <div>Report Version: {report.report_version}</div>
              <div>ID: <code>{report.analysis_id.slice(0, 8)}</code></div>
            </div>
          </div>
        </div>

        {/* Section 1: Executive Summary */}
        <section style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, borderBottom: '1px solid var(--border-light)', paddingBottom: '0.4rem', marginBottom: '0.75rem' }}>
            1. Executive Summary
          </h2>
          <div style={{ display: 'flex', gap: '1rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
            <div><strong>Drug:</strong> {report.drug.name}</div>
            <div><strong>Disease:</strong> {report.disease.name}</div>
            <div><strong>Decision:</strong> <Badge variant={report.decision.verdict === 'SUPPORT' ? 'support' : (report.decision.verdict === 'OPPOSE' ? 'oppose' : 'uncertain')}>{report.decision.verdict}</Badge></div>
            <div><strong>Recommendation:</strong> <Badge variant="neutral">{report.decision.recommendation}</Badge></div>
            {report.decision.hypothesis_status && (
              <div><strong>Hypothesis Status:</strong> <Badge variant="support">{report.decision.hypothesis_status}</Badge></div>
            )}
            {report.decision.repurposing_novelty && (
              <div><strong>Repurposing Novelty:</strong> <Badge variant="neutral">{report.decision.repurposing_novelty}</Badge></div>
            )}
          </div>
          <p>{report.executive_summary}</p>
        </section>

        {/* Section 2: Evaluated Hypothesis */}
        <section style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, borderBottom: '1px solid var(--border-light)', paddingBottom: '0.4rem', marginBottom: '0.75rem' }}>
            2. Evaluated Hypothesis
          </h2>
          <p style={{ fontStyle: 'italic', padding: '0.75rem', backgroundColor: 'var(--bg-subtle)', borderRadius: '6px' }}>
            {report.evaluated_hypothesis}
          </p>
        </section>

        {/* Section 3: Evidence Overview */}
        <section style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, borderBottom: '1px solid var(--border-light)', paddingBottom: '0.4rem', marginBottom: '0.75rem' }}>
            3. Evidence Overview
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem', textAlign: 'center' }}>
            <div style={{ padding: '0.5rem', background: 'var(--bg-subtle)', borderRadius: '4px' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Supporting Records</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--support-color)' }}>{report.evidence_overview.supporting_count}</div>
            </div>
            <div style={{ padding: '0.5rem', background: 'var(--bg-subtle)', borderRadius: '4px' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Opposing Records</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--oppose-color)' }}>{report.evidence_overview.opposing_count}</div>
            </div>
            <div style={{ padding: '0.5rem', background: 'var(--bg-subtle)', borderRadius: '4px' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Non-Directional</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--uncertain-color)' }}>{report.evidence_overview.uncertain_count}</div>
            </div>
            <div style={{ padding: '0.5rem', background: 'var(--bg-subtle)', borderRadius: '4px' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Independent Study Groups</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700 }}>{report.evidence_overview.independent_groups}</div>
            </div>
          </div>
        </section>

        {/* Section 4: Entity Resolution */}
        <section style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, borderBottom: '1px solid var(--border-light)', paddingBottom: '0.4rem', marginBottom: '0.75rem' }}>
            4. Entity Resolution & Cross-Ontology Mapping
          </h2>
          <p>
            Drug <strong>{report.drug.name}</strong> mapped to ChEMBL ID: <code>{report.entity_resolution.drug_canonical_id}</code>.
            Disease <strong>{report.disease.name}</strong> mapped to MeSH ID: <code>{report.entity_resolution.disease_mesh_id}</code>.
          </p>
        </section>

        {/* Section 5: Regulatory Evidence */}
        <section style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, borderBottom: '1px solid var(--border-light)', paddingBottom: '0.4rem', marginBottom: '0.75rem' }}>
            5. Regulatory & Approval Indication Evidence
          </h2>
          <p>
            {report.regulatory_evidence.has_anchor
              ? `A matched regulatory indication was verified for this indication (Phase ${report.regulatory_evidence.matched_indication_phase}).`
              : 'No qualifying disease-matched regulatory therapeutic indication identified in ChEMBL / FDA data.'}
            {' '}Global molecule status: Phase {report.regulatory_evidence.global_approval_phase}.
          </p>
        </section>

        {/* Section 6: Mechanistic Evidence */}
        <section style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, borderBottom: '1px solid var(--border-light)', paddingBottom: '0.4rem', marginBottom: '0.75rem' }}>
            6. Mechanistic Path Evidence
          </h2>
          <p>
            Mechanistic Score: <strong>{report.mechanistic_evidence.score.toFixed(2)}</strong> ({report.mechanistic_evidence.level}).
            Biological grounding level: <strong>{report.mechanistic_evidence.literature_grounding_level}</strong>.
          </p>
          {report.mechanistic_evidence.primary_chain.length > 0 && (
            <p style={{ marginTop: '0.5rem' }}>
              Traced Path: <code>{report.mechanistic_evidence.primary_chain.join(' → ')}</code>
            </p>
          )}
        </section>

        {/* Section 7 & 8: Therapeutic and Opposing Evidence */}
        <section style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, borderBottom: '1px solid var(--border-light)', paddingBottom: '0.4rem', marginBottom: '0.75rem' }}>
            7 & 8. Clinical Trials & Opposing Evidence Analysis
          </h2>
          <p>
            Opposition Level: <strong>{report.opposing_evidence.level}</strong> ({report.opposing_evidence.score.toFixed(3)}).
            Qualified negative claims: <strong>{report.opposing_evidence.qualified_negative_claim_count}</strong>.
          </p>
          <div style={{ marginTop: '0.5rem', padding: '0.65rem 0.85rem', backgroundColor: 'var(--bg-subtle)', borderRadius: '6px', fontSize: '0.825rem', color: 'var(--text-secondary)' }}>
            <strong>Methodological Note:</strong> Registry records confirm trial existence; absence of an explicit recorded failure does not establish demonstrated therapeutic efficacy.
          </div>
          {report.opposing_evidence.rationale && (
            <p style={{ color: 'var(--oppose-color)', marginTop: '0.5rem', fontWeight: 500 }}>
              {report.opposing_evidence.rationale}
            </p>
          )}
        </section>

        {/* Section 9: Contradictions */}
        <section style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, borderBottom: '1px solid var(--border-light)', paddingBottom: '0.4rem', marginBottom: '0.75rem' }}>
            9. Contradiction & Discordance Registry
          </h2>
          {report.contradictions.length === 0 ? (
            <p>No discordant outcomes detected across supporting and opposing sources.</p>
          ) : (
            report.contradictions.map((c, i) => (
              <p key={i} style={{ marginBottom: '0.5rem' }}>
                • <strong>{c.conflict_type}:</strong> {c.explanation}
              </p>
            ))
          )}
        </section>

        {/* Section 10: Evidence Independence */}
        <section style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, borderBottom: '1px solid var(--border-light)', paddingBottom: '0.4rem', marginBottom: '0.75rem' }}>
            10. Evidence Independence Breakdown
          </h2>
          <p>
            Raw records retrieved: <strong>{report.evidence_independence.raw_records}</strong>.
            Deduplicated records: <strong>{report.evidence_independence.deduplicated_records}</strong>.
            Independent study groups: <strong>{report.evidence_independence.independent_groups}</strong>.
          </p>
        </section>

        {/* Section 11: Safety / Risk */}
        <section style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, borderBottom: '1px solid var(--border-light)', paddingBottom: '0.4rem', marginBottom: '0.75rem' }}>
            11. Safety & Clinical Risk Profile
          </h2>
          <p>
            Safety Signals: <strong>{report.safety_analysis.risk_score === 0.0 ? 'No qualifying safety signals detected in the retrieved evidence set.' : `Active signals (Risk score ${report.safety_analysis.risk_score.toFixed(3)})`}</strong>.
            Risk Level: <strong>{report.safety_analysis.risk_level}</strong> (Score {report.safety_analysis.risk_score.toFixed(3)}).
            Failed/Terminated trials: <strong>{report.safety_analysis.failed_trial_count}</strong>.
          </p>
        </section>

        {/* Section 12: Final Reasoning */}
        <section style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, borderBottom: '1px solid var(--border-light)', paddingBottom: '0.4rem', marginBottom: '0.75rem' }}>
            12. Final Epistemic Reasoning & Decision Rationale
          </h2>
          <div style={{ padding: '0.85rem', backgroundColor: 'var(--bg-subtle)', borderRadius: '6px', borderLeft: '3px solid var(--primary-accent)' }}>
            <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>
              Decision: {report.final_reasoning.decision} | Recommendation: {report.final_reasoning.recommendation}
            </div>
            <p>{report.final_reasoning.rationale}</p>
          </div>
        </section>

        {/* Section 13: Limitations */}
        <section style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, borderBottom: '1px solid var(--border-light)', paddingBottom: '0.4rem', marginBottom: '0.75rem' }}>
            13. Limitations & Source Availability Gaps
          </h2>
          {report.limitations.length === 0 ? (
            <p>No critical data gaps or source outages noted.</p>
          ) : (
            <ul>
              {report.limitations.map((lim, i) => (
                <li key={i} style={{ marginBottom: '0.35rem', marginLeft: '1.25rem' }}>{lim}</li>
              ))}
            </ul>
          )}
        </section>

        {/* Section 14: Evidence Ledger */}
        <section style={{ marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, borderBottom: '1px solid var(--border-light)', paddingBottom: '0.4rem', marginBottom: '0.75rem' }}>
            14. Full Evidence Ledger
          </h2>
          <div className="table-container">
            <table className="research-table">
              <thead>
                <tr>
                  <th>Citation Key</th>
                  <th>Type</th>
                  <th>Source</th>
                  <th>Direction</th>
                  <th>Quality</th>
                </tr>
              </thead>
              <tbody>
                {report.evidence_ledger.slice(0, 25).map((item) => (
                  <tr key={item.id}>
                    <td><code>{item.citation_key}</code></td>
                    <td>{item.evidence_type}</td>
                    <td>{item.source}</td>
                    <td>{item.direction}</td>
                    <td>{item.quality_tier}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Section 15: References */}
        <section style={{ marginBottom: '1rem' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, borderBottom: '1px solid var(--border-light)', paddingBottom: '0.4rem', marginBottom: '0.75rem' }}>
            15. Canonical References
          </h2>
          <ol style={{ paddingLeft: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {report.references.map((ref) => (
              <li key={ref.id}>
                <strong>{ref.citation_key}</strong> — {ref.title} [{ref.source}].{' '}
                {ref.url && ref.url !== 'Canonical link unavailable' ? (
                  <a href={ref.url} target="_blank" rel="noopener noreferrer">
                    [Open canonical record]
                  </a>
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>[Canonical link unavailable]</span>
                )}
              </li>
            ))}
          </ol>
        </section>
      </div>
    </div>
  );
};
