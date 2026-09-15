import React from 'react';
import { AlertOctagon, ExternalLink, XCircle, FileWarning } from 'lucide-react';
import { OppositionData, TherapeuticEvidenceItem } from '../../types/analysis';
import { Badge } from '../common/Badge';
import { resolveCanonicalUrl } from '../../utils/sourceLinks';

export interface OpposingEvidenceCardProps {
  opposition: OppositionData;
  onSelectEvidence: (item: TherapeuticEvidenceItem) => void;
}

export const OpposingEvidenceCard: React.FC<OpposingEvidenceCardProps> = ({
  opposition,
  onSelectEvidence,
}) => {
  const hasOpposition = opposition.score > 0 || opposition.level !== 'NONE' || opposition.key_claims.length > 0;

  if (!hasOpposition) {
    return (
      <div className="research-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Opposing / Negative Evidence</h3>
          <Badge variant="neutral">Level: NONE</Badge>
        </div>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          No qualifying pair-specific negative therapeutic claims or failed trials identified under current retrieval scope.
        </p>
      </div>
    );
  }

  return (
    <div
      className="research-card"
      style={{
        border: '1px solid var(--oppose-border)',
        backgroundColor: 'var(--bg-surface)',
        borderLeft: '5px solid var(--oppose-color)'
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <AlertOctagon size={22} style={{ color: 'var(--oppose-color)' }} />
          <div>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--oppose-color)' }}>
              Opposing Evidence & Clinical Trial Failures
            </h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              Explicit clinical evidence opposing therapeutic efficacy (Rule 2b veto)
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <Badge variant="oppose">
            Opposition: {opposition.level} ({opposition.score.toFixed(2)})
          </Badge>
          <Badge variant="neutral">
            {opposition.independent_group_count} Independent {opposition.independent_group_count === 1 ? 'Group' : 'Groups'}
          </Badge>
        </div>
      </div>

      {opposition.rationale && (
        <div style={{
          padding: '0.85rem',
          backgroundColor: 'var(--oppose-bg)',
          borderRadius: '6px',
          border: '1px solid var(--oppose-border)',
          fontSize: '0.875rem',
          marginBottom: '1rem',
          color: 'var(--text-primary)'
        }}>
          <strong>Basis:</strong> {opposition.rationale}
        </div>
      )}

      {/* Opposing Studies List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {opposition.key_claims.map((claim) => {
          const canonicalUrl = claim.source_url || resolveCanonicalUrl(claim.citation_key, claim.source);
          return (
            <div
              key={claim.id}
              onClick={() => onSelectEvidence(claim)}
              style={{
                padding: '0.85rem 1rem',
                borderRadius: '6px',
                border: '1px solid var(--border-light)',
                backgroundColor: 'var(--bg-surface)',
                cursor: 'pointer',
                transition: 'border-color 0.15s ease'
              }}
              onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--oppose-color)')}
              onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--border-light)')}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.35rem' }}>
                <div>
                  <span style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)' }}>
                    <code>{claim.citation_key}</code>
                  </span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>
                    Source: {claim.source}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: '0.35rem' }}>
                  <Badge variant="oppose">OPPOSES</Badge>
                  <Badge variant={claim.quality_tier === 'HIGH' ? 'support' : 'neutral'}>
                    {claim.quality_tier} Quality
                  </Badge>
                </div>
              </div>

              {claim.title && (
                <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.25rem' }}>
                  {claim.title}
                </div>
              )}

              {claim.why_stopped && (
                <div style={{ fontSize: '0.8rem', color: 'var(--oppose-color)', fontWeight: 600, marginBottom: '0.25rem' }}>
                  Termination Reason: {claim.why_stopped}
                </div>
              )}

              {claim.outcome && (
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  <strong>Reported Outcome:</strong> {claim.outcome}
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px solid var(--border-light)' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Pair Specific: {claim.pair_specificity ? 'YES' : 'NO'} • Group: {claim.independent_group}
                </span>

                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                  {canonicalUrl && (
                    <a
                      href={canonicalUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      style={{ fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.25rem' }}
                    >
                      Canonical Source <ExternalLink size={12} />
                    </a>
                  )}
                  <span style={{ fontSize: '0.75rem', color: 'var(--primary-accent)', fontWeight: 500 }}>
                    Trace Record →
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
