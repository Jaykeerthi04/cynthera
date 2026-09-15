import React from 'react';
import { ExternalLink, ShieldCheck, FileText, Database, AlertCircle } from 'lucide-react';
import { TherapeuticEvidenceItem } from '../../types/analysis';
import { Drawer } from '../common/Drawer';
import { Badge } from '../common/Badge';
import { resolveCanonicalUrl } from '../../utils/sourceLinks';

export interface EvidenceTraceDrawerProps {
  evidence: TherapeuticEvidenceItem | null;
  onClose: () => void;
}

export const EvidenceTraceDrawer: React.FC<EvidenceTraceDrawerProps> = ({
  evidence,
  onClose,
}) => {
  if (!evidence) return null;

  const canonicalUrl = evidence.source_url || resolveCanonicalUrl(evidence.citation_key, evidence.source);

  const getDirectionBadge = () => {
    switch (evidence.direction) {
      case 'SUPPORTS':
        return <Badge variant="support">SUPPORTS</Badge>;
      case 'OPPOSES':
        return <Badge variant="oppose">OPPOSES</Badge>;
      case 'UNCERTAIN':
      case 'UNKNOWN':
      default:
        return <Badge variant="uncertain">{evidence.direction}</Badge>;
    }
  };

  return (
    <Drawer
      isOpen={Boolean(evidence)}
      onClose={onClose}
      title="Evidence Trace & Provenance"
      subtitle={`Citation Key: ${evidence.citation_key}`}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', fontSize: '0.875rem' }}>
        {/* Direction and Type Badges */}
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {getDirectionBadge()}
          <Badge variant="neutral">{evidence.evidence_type}</Badge>
          <Badge variant={evidence.quality_tier === 'HIGH' ? 'support' : 'neutral'}>
            Quality: {evidence.quality_tier}
          </Badge>
          <Badge variant={evidence.pair_specificity ? 'accent' : 'neutral'}>
            {evidence.pair_specificity ? 'Pair-Specific: YES' : 'Pair-Specific: NO'}
          </Badge>
        </div>

        {/* Title */}
        {evidence.title && (
          <div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase' }}>
              Study / Record Title
            </span>
            <div style={{ fontWeight: 600, fontSize: '0.95rem', color: 'var(--text-primary)', marginTop: '0.2rem' }}>
              {evidence.title}
            </div>
          </div>
        )}

        {/* Extracted Claim Text */}
        {evidence.extracted_claim && (
          <div style={{
            padding: '0.85rem',
            backgroundColor: 'var(--bg-subtle)',
            borderRadius: '6px',
            borderLeft: '3px solid var(--primary-accent)'
          }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', textTransform: 'uppercase', marginBottom: '0.25rem' }}>
              Exact Extracted Claim
            </span>
            <p style={{ fontStyle: 'italic', color: 'var(--text-primary)' }}>
              "{evidence.extracted_claim}"
            </p>
          </div>
        )}

        {/* Study outcome / Why stopped if trial */}
        {(evidence.outcome || evidence.why_stopped) && (
          <div style={{
            padding: '0.85rem',
            backgroundColor: evidence.direction === 'OPPOSES' ? 'var(--oppose-bg)' : 'var(--bg-subtle)',
            borderRadius: '6px',
            border: `1px solid ${evidence.direction === 'OPPOSES' ? 'var(--oppose-border)' : 'var(--border-light)'}`
          }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: evidence.direction === 'OPPOSES' ? 'var(--oppose-color)' : 'var(--text-secondary)', display: 'block', textTransform: 'uppercase' }}>
              Trial Outcome / Status
            </span>
            {evidence.outcome && (
              <div style={{ fontWeight: 600, marginTop: '0.2rem' }}>
                Outcome: {evidence.outcome}
              </div>
            )}
            {evidence.why_stopped && (
              <div style={{ color: 'var(--oppose-color)', marginTop: '0.35rem', fontWeight: 500 }}>
                Termination Reason: {evidence.why_stopped}
              </div>
            )}
          </div>
        )}

        {/* Abstract / Summary */}
        {evidence.abstract && (
          <div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase', marginBottom: '0.25rem' }}>
              Record Summary / Abstract Text
            </span>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.825rem', lineHeight: 1.6, maxHeight: '200px', overflowY: 'auto' }}>
              {evidence.abstract}
            </p>
          </div>
        )}

        {/* Provenance Metadata Details */}
        <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-muted)' }}>Source Database</span>
            <span style={{ fontWeight: 600 }}>{evidence.source}</span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-muted)' }}>Citation Identifier</span>
            <code>{evidence.citation_key}</code>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-muted)' }}>Independent Evidence Group</span>
            <code>{evidence.independent_group}</code>
          </div>

          {evidence.study_type && (
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-muted)' }}>Study Design</span>
              <span>{evidence.study_type}</span>
            </div>
          )}

          {evidence.retrieved_at && (
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-muted)' }}>Retrieved Timestamp</span>
              <span>{evidence.retrieved_at.slice(0, 10)}</span>
            </div>
          )}
        </div>

        {/* Canonical Link Button */}
        <div style={{ marginTop: '1.25rem', paddingTop: '1rem', borderTop: '1px solid var(--border-light)' }}>
          {canonicalUrl ? (
            <a
              href={canonicalUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-primary"
              style={{ width: '100%' }}
            >
              Open Canonical Source Record <ExternalLink size={16} />
            </a>
          ) : (
            <div style={{
              padding: '0.75rem',
              backgroundColor: 'var(--bg-subtle)',
              borderRadius: '6px',
              textAlign: 'center',
              color: 'var(--text-muted)',
              fontSize: '0.8rem'
            }}>
              Canonical external link unavailable for this identifier format.
            </div>
          )}
        </div>
      </div>
    </Drawer>
  );
};
