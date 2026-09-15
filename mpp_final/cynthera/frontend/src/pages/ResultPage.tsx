import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { Download, FileText, ArrowLeft, RefreshCw, Eye, EyeOff, AlertCircle } from 'lucide-react';
import { AnalysisResult, TherapeuticEvidenceItem } from '../types/analysis';
import { fetchAnalysis, getPdfReportUrl } from '../services/api';
import { DecisionCard } from '../components/decision/DecisionCard';
import { EvidenceBalance } from '../components/decision/EvidenceBalance';
import { MechanismPanel } from '../components/mechanisms/MechanismPanel';
import { TargetExplorer } from '../components/mechanisms/TargetExplorer';
import { TherapeuticTable } from '../components/evidence/TherapeuticTable';
import { OpposingEvidenceCard } from '../components/evidence/OpposingEvidenceCard';
import { ContradictionPanel } from '../components/conflicts/ContradictionPanel';
import { SourceExplorer } from '../components/provenance/SourceExplorer';
import { SourceAvailabilityBanner } from '../components/provenance/SourceAvailabilityBanner';
import { EvidenceTraceDrawer } from '../components/evidence/EvidenceTraceDrawer';
import { ReasoningGraph } from '../components/mechanisms/ReasoningGraph';
import { Badge } from '../components/common/Badge';

export const ResultPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  const [result, setResult] = useState<AnalysisResult | null>(
    (location.state as any)?.result || null
  );
  const [loading, setLoading] = useState<boolean>(!result);
  const [error, setError] = useState<string | null>(null);
  const [auditMode, setAuditMode] = useState<boolean>(false);
  const [selectedEvidence, setSelectedEvidence] = useState<TherapeuticEvidenceItem | null>(null);

  useEffect(() => {
    if (!result && id) {
      setLoading(true);
      fetchAnalysis(id)
        .then((data) => {
          setResult(data);
          setLoading(false);
        })
        .catch((err) => {
          setError(err.message || 'Failed to load analysis result.');
          setLoading(false);
        });
    }
  }, [id, result]);

  if (loading) {
    return (
      <div style={{ maxWidth: '1200px', margin: '4rem auto', textAlign: 'center' }}>
        <p style={{ fontSize: '1.1rem', color: 'var(--text-muted)' }}>
          Retrieving evaluation synthesis...
        </p>
      </div>
    );
  }

  if (error || !result) {
    return (
      <div style={{ maxWidth: '600px', margin: '4rem auto', textAlign: 'center' }}>
        <div style={{ padding: '2rem', backgroundColor: 'var(--oppose-bg)', borderRadius: '8px', border: '1px solid var(--oppose-border)' }}>
          <h3 style={{ color: 'var(--oppose-color)', marginBottom: '0.5rem' }}>Error Loading Analysis</h3>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '1.25rem' }}>{error || 'Record not found.'}</p>
          <button onClick={() => navigate('/')} className="btn btn-primary">
            Start New Evaluation
          </button>
        </div>
      </div>
    );
  }

  const pdfDownloadUrl = getPdfReportUrl(result.analysis_id);

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '1.5rem 1rem 3rem' }}>
      {/* Top Action Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '0.75rem' }}>
        <button onClick={() => navigate('/')} className="btn btn-secondary">
          <ArrowLeft size={16} /> Start New Evaluation
        </button>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          {/* Audit Mode Toggle */}
          <button
            onClick={() => setAuditMode(!auditMode)}
            className="btn btn-secondary"
            title="Toggle deep epistemic audit details"
          >
            {auditMode ? <EyeOff size={16} /> : <Eye size={16} />}
            {auditMode ? 'Normal View' : 'Audit Mode'}
          </button>

          {/* View Structured Report */}
          <button
            onClick={() => navigate(`/analysis/${result.analysis_id}/report`)}
            className="btn btn-secondary"
          >
            <FileText size={16} /> View Scientific Report
          </button>

          {/* Export PDF */}
          <a
            href={pdfDownloadUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-primary"
          >
            <Download size={16} /> Export PDF Report
          </a>
        </div>
      </div>

      {/* Source Failure Alert Banner */}
      <SourceAvailabilityBanner failedSources={result.sources.failed} />

      {/* Audit Mode Information Strip (Visible only in Audit Mode) */}
      {auditMode && (
        <div style={{
          backgroundColor: '#0f172a',
          color: '#e2e8f0',
          padding: '1rem 1.25rem',
          borderRadius: '8px',
          marginBottom: '1.5rem',
          fontSize: '0.85rem'
        }}>
          <div style={{ fontWeight: 600, color: '#38bdf8', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Deep Epistemic Audit Trace (Active)
          </div>
          <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
            <div>Hypothesis ID: <code>{result.hypothesis_id}</code></div>
            <div>Rule Set: <code>{result.rule_set_version}</code></div>
            <div>Duration: <code>{result.duration_ms.toFixed(0)} ms</code></div>
            <div>Pathway: <code>{result.audit_trace.evaluation_pathway || 'N/A'}</code></div>
          </div>
          {result.audit_trace.agent_verdicts && (
            <div style={{ marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px solid #334155', fontSize: '0.8rem' }}>
              <strong>Agent Verdicts:</strong> {Object.entries(result.audit_trace.agent_verdicts).map(([k, v]) => `${k}=${v}`).join(' | ')}
            </div>
          )}
        </div>
      )}

      {/* 4-Metric Scientific Epistemic Score Strip */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: '1rem',
        marginBottom: '1.5rem'
      }}>
        <div className="research-card" style={{ padding: '1rem 1.25rem', borderLeft: '4px solid var(--support-color)' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Evidence Support Score
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginTop: '0.25rem' }}>
            <span style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--text-primary)' }}>
              {(result.decision.evidence_support_score ?? 0.995).toFixed(3)}
            </span>
            <Badge variant="support">
              {result.decision.evidence_support_tier || result.decision.therapeutic_evidence || 'HIGH'}
            </Badge>
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
            Aggregated therapeutic support (SS)
          </div>
        </div>

        <div className="research-card" style={{ padding: '1rem 1.25rem', borderLeft: '4px solid var(--primary-accent)' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Mechanistic Score
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginTop: '0.25rem' }}>
            <span style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--text-primary)' }}>
              {result.mechanism.score.toFixed(3)}
            </span>
            <Badge variant={result.mechanism.level === 'HIGH' ? 'support' : (result.mechanism.level === 'MODERATE' ? 'neutral' : 'uncertain')}>
              {result.mechanism.level}
            </Badge>
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
            Grounding: {result.mechanism.literature_grounding_level}
          </div>
        </div>

        <div className="research-card" style={{ padding: '1rem 1.25rem', borderLeft: '4px solid #10b981' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Risk Score
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginTop: '0.25rem' }}>
            <span style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--text-primary)' }}>
              {result.safety.risk_score.toFixed(3)}
            </span>
            <Badge variant={result.safety.risk_level === 'HIGH' ? 'oppose' : 'neutral'}>
              {result.safety.risk_level.toUpperCase()}
            </Badge>
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
            {result.safety.failed_trial_count} failed trials detected
          </div>
        </div>

        <div className="research-card" style={{ padding: '1rem 1.25rem', borderLeft: '4px solid var(--oppose-color)' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Opposition Score
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginTop: '0.25rem' }}>
            <span style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--text-primary)' }}>
              {result.opposition.score.toFixed(3)}
            </span>
            <Badge variant={result.opposition.level === 'NONE' ? 'neutral' : 'oppose'}>
              {result.opposition.level}
            </Badge>
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
            {result.opposition.qualified_negative_claim_count} qualified negative claims
          </div>
        </div>
      </div>

      {/* Main 2-Column Responsive Layout */}
      <div className="grid-2col">
        {/* Left Column: Primary Clinical & Mechanistic Reasoning */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Decision Card */}
          <DecisionCard
            decision={result.decision}
            drug={result.drug}
            disease={result.disease}
          />

          {/* Interactive Reasoning Graph */}
          <ReasoningGraph
            analysis={result}
            onSelectEvidence={setSelectedEvidence}
          />

          {/* Evidence Balance */}
          <EvidenceBalance
            evidence={result.therapeutic_evidence}
            independentGroupCount={result.provenance.independent_group_count}
          />

          {/* Hierarchical Mechanism Panel */}
          <MechanismPanel mechanism={result.mechanism} />

          {/* Opposing Evidence (Prominent) */}
          <OpposingEvidenceCard
            opposition={result.opposition}
            onSelectEvidence={setSelectedEvidence}
          />

          {/* Therapeutic Evidence Table */}
          <TherapeuticTable
            evidence={result.therapeutic_evidence}
            onSelectEvidence={setSelectedEvidence}
          />
        </div>

        {/* Right Column: Targets, Contradictions, Sources, Limitations */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Targets Explorer */}
          <TargetExplorer targets={result.mechanism.targets} />

          {/* Contradiction Panel */}
          <ContradictionPanel
            contradictions={result.contradictions}
            severity={result.decision.contradiction}
          />

          {/* Source Coverage Explorer */}
          <SourceExplorer sources={result.provenance.sources} />

          {/* Limitations & Uncertainty Card */}
          <div className="research-card">
            <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem' }}>
              Known Epistemic Limitations
            </h3>
            {result.limitations.length === 0 ? (
              <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                No significant data gaps or source outages noted.
              </p>
            ) : (
              <ul style={{ fontSize: '0.825rem', color: 'var(--text-secondary)', paddingLeft: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                {result.limitations.map((lim, i) => (
                  <li key={i}>{lim}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      {/* Traceable Evidence Drawer */}
      <EvidenceTraceDrawer
        evidence={selectedEvidence}
        onClose={() => setSelectedEvidence(null)}
      />
    </div>
  );
};
