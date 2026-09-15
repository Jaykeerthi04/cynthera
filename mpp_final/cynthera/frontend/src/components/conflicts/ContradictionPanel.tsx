import React from 'react';
import { ArrowUpDown, AlertTriangle, ShieldCheck } from 'lucide-react';
import { ContradictionItem, ContradictionSeverity } from '../../types/analysis';
import { Badge } from '../common/Badge';

export interface ContradictionPanelProps {
  contradictions: ContradictionItem[];
  severity: ContradictionSeverity;
}

export const ContradictionPanel: React.FC<ContradictionPanelProps> = ({
  contradictions,
  severity,
}) => {
  if (severity === 'NONE' || contradictions.length === 0) {
    return (
      <div className="research-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Contradiction Analysis</h3>
          <Badge variant="neutral">Status: CONCORDANT / NONE</Badge>
        </div>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          No direct empirical or mechanistic discordance identified across the retrieved evidence set.
        </p>
      </div>
    );
  }

  return (
    <div className="research-card" style={{ borderLeft: '4px solid var(--uncertain-color)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <ArrowUpDown size={20} style={{ color: 'var(--uncertain-color)' }} />
          <div>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600 }}>
              Evidence Contradiction & Discordance
            </h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Directional conflict between retrieved supporting and opposing records
            </p>
          </div>
        </div>

        <Badge variant={severity === 'STRONG' ? 'oppose' : 'uncertain'}>
          Severity: {severity}
        </Badge>
      </div>

      {/* Visual Conflict Schematic */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr auto 1fr',
        gap: '0.75rem',
        alignItems: 'center',
        padding: '0.85rem 1rem',
        backgroundColor: 'var(--bg-subtle)',
        borderRadius: '6px',
        marginBottom: '1rem',
        textAlign: 'center'
      }}>
        <div style={{ padding: '0.5rem', background: 'var(--support-bg)', border: '1px solid var(--support-border)', borderRadius: '4px' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--support-color)' }}>SUPPORTING CLAIMS</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>Plausibility / Indication</div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', color: 'var(--uncertain-color)' }}>
          <AlertTriangle size={18} />
          <span style={{ fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', marginTop: '0.15rem' }}>CONFLICT</span>
        </div>

        <div style={{ padding: '0.5rem', background: 'var(--oppose-bg)', border: '1px solid var(--oppose-border)', borderRadius: '4px' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--oppose-color)' }}>OPPOSING OUTCOMES</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>Trial Efficacy Failures</div>
        </div>
      </div>

      {/* Contradiction Items Explanations */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {contradictions.map((c, idx) => (
          <div
            key={c.id || idx}
            style={{
              padding: '0.85rem',
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-light)',
              borderRadius: '6px'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                Conflict Classification: {c.conflict_type.replace(/_/g, ' ')}
              </span>
              <Badge variant="neutral">Resolution: {c.resolution}</Badge>
            </div>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-primary)', lineHeight: 1.5 }}>
              {c.explanation}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
};
