import React from 'react';
import { Info } from 'lucide-react';
import { TherapeuticEvidenceItem } from '../../types/analysis';

export interface EvidenceBalanceProps {
  evidence: TherapeuticEvidenceItem[];
  independentGroupCount: number;
}

export const EvidenceBalance: React.FC<EvidenceBalanceProps> = ({
  evidence,
  independentGroupCount,
}) => {
  const supporting = evidence.filter((e) => e.direction === 'SUPPORTS');
  const opposing = evidence.filter((e) => e.direction === 'OPPOSES');
  const nonDirectional = evidence.filter(
    (e) => e.direction === 'UNCERTAIN' || e.direction === 'UNKNOWN'
  );

  const total = evidence.length || 1;
  const suppPct = Math.round((supporting.length / total) * 100);
  const oppPct = Math.round((opposing.length / total) * 100);
  const nonDirPct = 100 - suppPct - oppPct;

  const supportingGroups = new Set(supporting.map((e) => e.independent_group)).size;
  const opposingGroups = new Set(opposing.map((e) => e.independent_group)).size;

  return (
    <div className="research-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Evidence Balance & Independence</h3>
        <span
          title="Record count includes multiple database representations and is not equivalent to independent studies."
          style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.75rem', color: 'var(--text-muted)', cursor: 'help' }}
        >
          <Info size={14} /> Multi-database citation metric
        </span>
      </div>

      {/* Proportional Bar */}
      <div style={{
        height: '24px',
        borderRadius: '4px',
        overflow: 'hidden',
        display: 'flex',
        backgroundColor: 'var(--bg-muted)',
        marginBottom: '1rem'
      }}>
        {supporting.length > 0 && (
          <div
            style={{ width: `${suppPct}%`, backgroundColor: 'var(--support-color)', height: '100%' }}
            title={`Supporting: ${supporting.length} records (${suppPct}%)`}
          />
        )}
        {opposing.length > 0 && (
          <div
            style={{ width: `${oppPct}%`, backgroundColor: 'var(--oppose-color)', height: '100%' }}
            title={`Opposing: ${opposing.length} records (${oppPct}%)`}
          />
        )}
        {nonDirectional.length > 0 && (
          <div
            style={{ width: `${nonDirPct}%`, backgroundColor: 'var(--uncertain-color)', height: '100%' }}
            title={`Non-Directional: ${nonDirectional.length} records (${nonDirPct}%)`}
          />
        )}
      </div>

      {/* Breakdown Metrics Table */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem', textAlign: 'center' }}>
        <div style={{ padding: '0.75rem', backgroundColor: 'var(--support-bg)', borderRadius: '6px', border: '1px solid var(--support-border)' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--support-color)', textTransform: 'uppercase' }}>
            Supporting
          </div>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--support-color)', margin: '0.25rem 0' }}>
            {supporting.length} <span style={{ fontSize: '0.75rem', fontWeight: 400 }}>records</span>
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            {supportingGroups} independent {supportingGroups === 1 ? 'group' : 'groups'}
          </div>
        </div>

        <div style={{ padding: '0.75rem', backgroundColor: 'var(--oppose-bg)', borderRadius: '6px', border: '1px solid var(--oppose-border)' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--oppose-color)', textTransform: 'uppercase' }}>
            Opposing
          </div>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--oppose-color)', margin: '0.25rem 0' }}>
            {opposing.length} <span style={{ fontSize: '0.75rem', fontWeight: 400 }}>records</span>
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            {opposingGroups} independent {opposingGroups === 1 ? 'group' : 'groups'}
          </div>
        </div>

        <div style={{ padding: '0.75rem', backgroundColor: 'var(--uncertain-bg)', borderRadius: '6px', border: '1px solid var(--uncertain-border)' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--uncertain-color)', textTransform: 'uppercase' }}>
            Non-Directional
          </div>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--uncertain-color)', margin: '0.25rem 0' }}>
            {nonDirectional.length} <span style={{ fontSize: '0.75rem', fontWeight: 400 }}>records</span>
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
            Biochemical / structural
          </div>
        </div>
      </div>

      <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.75rem', fontStyle: 'italic' }}>
        * Record count reflects multiple database citations (PubMed, Europe PMC, ChEMBL, ClinicalTrials.gov) and is not equivalent to independent replicate studies.
      </p>
    </div>
  );
};
