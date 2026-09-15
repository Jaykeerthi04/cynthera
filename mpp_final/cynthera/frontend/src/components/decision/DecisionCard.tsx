import React from 'react';
import { CheckCircle2, XCircle, AlertTriangle, Shield, Activity, GitBranch } from 'lucide-react';
import { DecisionData, DrugInfo, DiseaseInfo } from '../../types/analysis';
import { Badge } from '../common/Badge';

export interface DecisionCardProps {
  decision: DecisionData;
  drug: DrugInfo;
  disease: DiseaseInfo;
}

export const DecisionCard: React.FC<DecisionCardProps> = ({ decision, drug, disease }) => {
  const getVerdictBadge = () => {
    switch (decision.verdict) {
      case 'SUPPORT':
        return (
          <Badge variant="support" icon={<CheckCircle2 size={16} />}>
            SUPPORT
          </Badge>
        );
      case 'OPPOSE':
        return (
          <Badge variant="oppose" icon={<XCircle size={16} />}>
            OPPOSE
          </Badge>
        );
      case 'UNCERTAIN':
      default:
        return (
          <Badge variant="uncertain" icon={<AlertTriangle size={16} />}>
            UNCERTAIN
          </Badge>
        );
    }
  };

  const getRecommendationBadge = () => {
    switch (decision.recommendation) {
      case 'PROMISING':
        return (
          <Badge variant="support">
            PROMISING
          </Badge>
        );
      case 'NOT_RECOMMENDED':
        return (
          <Badge variant="oppose">
            NOT RECOMMENDED
          </Badge>
        );
      case 'UNCERTAIN':
      default:
        return (
          <Badge variant="uncertain">
            UNCERTAIN
          </Badge>
        );
    }
  };

  return (
    <div className="research-card" style={{ borderLeft: `5px solid ${
      decision.verdict === 'SUPPORT' ? 'var(--support-color)' :
      decision.verdict === 'OPPOSE' ? 'var(--oppose-color)' : 'var(--uncertain-color)'
    }` }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Evaluated Pair
            </span>
            {decision.hypothesis_status && (
              <span className={`badge ${decision.hypothesis_status.includes('ESTABLISHED') ? 'badge-support' : 'badge-neutral'}`} style={{ fontSize: '0.7rem' }}>
                {decision.hypothesis_status}
              </span>
            )}
          </div>
          <h2 style={{ fontSize: '1.65rem', fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>
            {drug.name} <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>×</span> {disease.name}
          </h2>
          {drug.chembl_id && (
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
              Drug ID: <code>{drug.chembl_id}</code>
              {disease.mesh_id && <span> • MeSH: <code>{disease.mesh_id}</code></span>}
              {drug.global_approval_phase > 0 && <span> • Global Phase: Phase {drug.global_approval_phase}</span>}
              {decision.repurposing_novelty && <span> • Novelty: {decision.repurposing_novelty}</span>}
            </p>
          )}
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.2rem' }}>Decision</div>
            {getVerdictBadge()}
          </div>
          <div style={{ textAlign: 'right', borderLeft: '1px solid var(--border-light)', paddingLeft: '0.75rem' }}>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.2rem' }}>Recommendation</div>
            {getRecommendationBadge()}
          </div>
        </div>
      </div>

      {/* Rationale Statement */}
      <div style={{
        marginTop: '1.25rem',
        padding: '1rem',
        backgroundColor: 'var(--bg-subtle)',
        borderRadius: '6px',
        borderLeft: '3px solid var(--primary-accent)',
        fontSize: '0.925rem',
        lineHeight: 1.6
      }}>
        <div style={{ fontWeight: 600, fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.25rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          Primary Scientific Conclusion
        </div>
        <p style={{ color: 'var(--text-primary)' }}>{decision.rationale}</p>
      </div>

      {/* Structured "Why did CYNTHERA reach this conclusion?" (UX Principle #13) */}
      {decision.structured_why && decision.structured_why.length > 0 && (
        <div style={{
          marginTop: '1rem',
          padding: '0.85rem 1rem',
          backgroundColor: 'var(--bg-surface)',
          borderRadius: '6px',
          border: '1px solid var(--border-light)'
        }}>
          <div style={{ fontWeight: 700, fontSize: '0.8rem', color: 'var(--text-secondary)', textTransform: 'uppercase', marginBottom: '0.5rem', letterSpacing: '0.04em' }}>
            Evidence Basis — Step-by-Step Rationale
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.65rem' }}>
            {decision.structured_why.map((item, idx) => {
              const isPos = item.status === 'POSITIVE';
              const isNeg = item.status === 'NEGATIVE';
              return (
                <div
                  key={idx}
                  style={{
                    padding: '0.6rem 0.75rem',
                    backgroundColor: isPos ? 'var(--support-bg)' : (isNeg ? 'var(--oppose-bg)' : 'var(--bg-subtle)'),
                    border: `1px solid ${isPos ? 'var(--support-border)' : (isNeg ? 'var(--oppose-border)' : 'var(--border-light)')}`,
                    borderRadius: '4px',
                    fontSize: '0.8rem'
                  }}
                >
                  <div style={{ fontWeight: 700, color: isPos ? 'var(--support-color)' : (isNeg ? 'var(--oppose-color)' : 'var(--text-secondary)'), marginBottom: '0.15rem' }}>
                    {item.step}
                  </div>
                  <div style={{ color: 'var(--text-primary)' }}>{item.detail}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Structured Evidence State Grid */}
      <div style={{
        marginTop: '1.5rem',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: '1rem',
        paddingTop: '1.25rem',
        borderTop: '1px solid var(--border-light)'
      }}>
        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>
            Therapeutic Anchor
          </span>
          <span style={{ fontWeight: 600, fontSize: '0.9rem', color: decision.therapeutic_anchor ? 'var(--support-color)' : 'var(--text-secondary)' }}>
            {decision.therapeutic_anchor ? 'YES (Identified)' : 'No qualifying anchor identified'}
          </span>
        </div>

        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>
            Mechanistic Evidence
          </span>
          <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>
            {decision.mechanistic_evidence}
          </span>
        </div>

        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>
            Therapeutic Evidence
          </span>
          <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>
            {decision.therapeutic_evidence}
          </span>
        </div>

        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>
            Opposition Level
          </span>
          <span style={{
            fontWeight: 600,
            fontSize: '0.9rem',
            color: decision.opposition === 'HIGH' || decision.opposition === 'MODERATE' ? 'var(--oppose-color)' : 'var(--text-primary)'
          }}>
            {decision.opposition}
          </span>
        </div>

        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>
            Contradiction Conflict
          </span>
          <span style={{
            fontWeight: 600,
            fontSize: '0.9rem',
            color: decision.contradiction === 'STRONG' ? 'var(--oppose-color)' : 'var(--text-primary)'
          }}>
            {decision.contradiction}
          </span>
        </div>

        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.25rem' }}>
            Safety Grade
          </span>
          <span style={{
            fontWeight: 600,
            fontSize: '0.9rem',
            color: decision.safety_grade === 'HIGH_RISK' ? 'var(--oppose-color)' : 'var(--text-primary)'
          }}>
            Grade {decision.safety_grade}
          </span>
        </div>
      </div>
    </div>
  );
};
