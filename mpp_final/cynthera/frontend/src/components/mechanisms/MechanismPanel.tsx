import React, { useState } from 'react';
import { ChevronRight, ExternalLink, Activity, GitCommit, Layers } from 'lucide-react';
import { MechanismData, CandidateMechanism, MechanismHop } from '../../types/analysis';
import { Badge } from '../common/Badge';

export interface MechanismPanelProps {
  mechanism: MechanismData;
}

export const MechanismPanel: React.FC<MechanismPanelProps> = ({ mechanism }) => {
  const [selectedCandidate, setSelectedCandidate] = useState<number>(0);

  const candidates = mechanism.candidate_mechanisms || [];
  const activeCandidate: CandidateMechanism | undefined = candidates[selectedCandidate];

  const getCausalBadgeVariant = (grounding: string) => {
    switch (grounding) {
      case 'DIRECT':
      case 'CAUSAL':
        return 'support';
      case 'CURATED':
        return 'accent';
      case 'INFERRED':
        return 'uncertain';
      case 'STRUCTURAL':
      default:
        return 'neutral';
    }
  };

  return (
    <div className="research-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
        <div>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 600 }}>Mechanistic Pathway Analysis</h3>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Traced biological chain connecting intervention to disease pathology
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <Badge variant="neutral">
            Score: {mechanism.score.toFixed(2)} [{mechanism.level}]
          </Badge>
          <Badge variant="neutral">
            Grounding: {mechanism.literature_grounding_level}
          </Badge>
        </div>
      </div>

      {/* Primary Trace Summary */}
      {mechanism.primary_chain && mechanism.primary_chain.length > 0 && (
        <div style={{
          backgroundColor: 'var(--bg-subtle)',
          padding: '0.75rem 1rem',
          borderRadius: '6px',
          marginBottom: '1.25rem',
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '0.5rem',
          fontSize: '0.85rem'
        }}>
          <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>Primary Trace:</span>
          {mechanism.primary_chain.map((node, i) => (
            <React.Fragment key={i}>
              <span style={{
                background: 'var(--bg-surface)',
                padding: '0.2rem 0.6rem',
                borderRadius: '4px',
                border: '1px solid var(--border-color)',
                fontWeight: 500
              }}>
                {node}
              </span>
              {i < mechanism.primary_chain.length - 1 && (
                <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
              )}
            </React.Fragment>
          ))}
        </div>
      )}

      {/* Candidate Mechanism Selector Tabs */}
      {candidates.length > 1 && (
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.25rem', overflowX: 'auto', paddingBottom: '0.25rem' }}>
          {candidates.map((cand, idx) => (
            <button
              key={cand.candidate_id || idx}
              onClick={() => setSelectedCandidate(idx)}
              className="btn btn-secondary"
              style={{
                padding: '0.4rem 0.8rem',
                fontSize: '0.8rem',
                backgroundColor: selectedCandidate === idx ? 'var(--primary-accent-subtle)' : 'var(--bg-surface)',
                borderColor: selectedCandidate === idx ? 'var(--primary-accent)' : 'var(--border-color)',
                color: selectedCandidate === idx ? 'var(--primary-accent)' : 'var(--text-primary)',
                fontWeight: selectedCandidate === idx ? 600 : 500,
              }}
            >
              Candidate {idx + 1}: {cand.target} → {cand.pathway.slice(0, 20)}...
            </button>
          ))}
        </div>
      )}

      {/* Active Candidate Hops Flow */}
      {activeCandidate ? (
        <div>
          <div style={{ marginBottom: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
              Chain: {activeCandidate.target} ➔ {activeCandidate.pathway}
            </span>
            <Badge variant={activeCandidate.support_level.includes('SUPPORTED') ? 'support' : 'neutral'}>
              {activeCandidate.support_level}
            </Badge>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {activeCandidate.hops.map((hop: MechanismHop, hopIdx: number) => (
              <div
                key={hopIdx}
                style={{
                  padding: '1rem',
                  borderRadius: '6px',
                  border: '1px solid var(--border-color)',
                  backgroundColor: 'var(--bg-surface)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.5rem'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem', fontWeight: 600 }}>
                    <span>{hop.from_node}</span>
                    <span style={{
                      fontSize: '0.75rem',
                      color: 'var(--primary-accent)',
                      background: 'var(--primary-accent-subtle)',
                      padding: '0.15rem 0.45rem',
                      borderRadius: '4px',
                      textTransform: 'uppercase'
                    }}>
                      {hop.predicate}
                    </span>
                    <span>{hop.to_node}</span>
                  </div>

                  <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                    <Badge variant={getCausalBadgeVariant(hop.causal_grounding)}>
                      {hop.causal_grounding}
                    </Badge>
                    <Badge variant="neutral">
                      {hop.source_database}
                    </Badge>
                    {hop.polarity !== 'UNKNOWN' && (
                      <Badge variant="neutral">
                        Polarity: {hop.polarity}
                      </Badge>
                    )}
                  </div>
                </div>

                {hop.provenance_note && (
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    {hop.provenance_note}
                  </p>
                )}

                {hop.source_url && (
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.25rem' }}>
                    <a
                      href={hop.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.25rem' }}
                    >
                      Canonical DB Record <ExternalLink size={12} />
                    </a>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
          No qualifying multi-hop mechanistic pathways identified under current retrieval scope.
        </div>
      )}
    </div>
  );
};
