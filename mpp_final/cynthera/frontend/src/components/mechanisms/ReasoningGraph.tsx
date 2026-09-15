import React from 'react';
import { ChevronRight, ArrowDown, Database, ExternalLink, ShieldCheck, AlertCircle } from 'lucide-react';
import { AnalysisResult, TherapeuticEvidenceItem } from '../../types/analysis';
import { Badge } from '../common/Badge';

export interface ReasoningGraphProps {
  analysis: AnalysisResult;
  onSelectEvidence: (item: TherapeuticEvidenceItem) => void;
}

export const ReasoningGraph: React.FC<ReasoningGraphProps> = ({
  analysis,
  onSelectEvidence,
}) => {
  const { drug, disease, decision, mechanism, opposition, therapeutic_evidence } = analysis;

  const targetName = mechanism.targets[0]?.symbol || 'Target';
  const targetUniprot = mechanism.targets[0]?.uniprot_id || 'P43220';
  const pathwayName = mechanism.candidate_mechanisms[0]?.pathway || 'Metabolic / Signalling Pathway';
  const predicate = mechanism.candidate_mechanisms[0]?.hops[0]?.predicate || 'AGONIST / INHIBITOR';

  const regEvidence = therapeutic_evidence.find((e) => e.evidence_type === 'REGULATORY_INDICATION');
  const clinicalEvidence = therapeutic_evidence.find((e) => e.evidence_type === 'RCT' || e.evidence_type === 'CLINICAL_TRIAL');

  return (
    <div className="research-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <div>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 600 }}>Interactive Reasoning Graph</h3>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Traceable chain of evidence connecting intervention to final epistemic decision
          </p>
        </div>
        <Badge variant="accent">Click any edge to inspect provenance</Badge>
      </div>

      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '0.5rem',
        padding: '1.5rem',
        backgroundColor: 'var(--bg-subtle)',
        borderRadius: '8px',
        border: '1px solid var(--border-light)'
      }}>
        {/* Node 1: Drug */}
        <div style={{
          width: '100%',
          maxWidth: '440px',
          padding: '0.75rem 1rem',
          backgroundColor: 'var(--bg-surface)',
          borderRadius: '6px',
          border: '2px solid var(--primary-accent)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          boxShadow: 'var(--shadow-sm)'
        }}>
          <div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Intervention</div>
            <div style={{ fontWeight: 700, fontSize: '1rem' }}>{drug.name}</div>
          </div>
          {drug.chembl_id && <code>{drug.chembl_id}</code>}
        </div>

        {/* Edge 1: Drug -> Target */}
        <div
          onClick={() => {
            const ev = therapeutic_evidence.find((e) => e.source.toLowerCase().includes('chembl')) || therapeutic_evidence[0];
            if (ev) onSelectEvidence(ev);
          }}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            cursor: 'pointer',
            padding: '0.2rem 0.5rem',
            borderRadius: '4px',
            transition: 'background 0.15s'
          }}
          title="Click to view drug-target interaction record"
        >
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--primary-accent)' }}>
            ↓ {predicate} (ChEMBL / BindingDB)
          </span>
          <ArrowDown size={16} style={{ color: 'var(--primary-accent)' }} />
        </div>

        {/* Node 2: Target */}
        <div style={{
          width: '100%',
          maxWidth: '440px',
          padding: '0.75rem 1rem',
          backgroundColor: 'var(--bg-surface)',
          borderRadius: '6px',
          border: '1px solid var(--border-color)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          boxShadow: 'var(--shadow-sm)'
        }}>
          <div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Primary Target Protein</div>
            <div style={{ fontWeight: 700, fontSize: '0.95rem' }}>{targetName}</div>
          </div>
          <code style={{ color: 'var(--text-secondary)' }}>{targetUniprot}</code>
        </div>

        {/* Edge 2: Target -> Pathway */}
        <div
          onClick={() => {
            const ev = therapeutic_evidence.find((e) => e.source.toLowerCase().includes('reactome')) || therapeutic_evidence[0];
            if (ev) onSelectEvidence(ev);
          }}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            cursor: 'pointer',
            padding: '0.2rem 0.5rem',
            borderRadius: '4px'
          }}
          title="Click to inspect pathway reaction participation"
        >
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
            ↓ Reaction Participation (Reactome)
          </span>
          <ArrowDown size={16} style={{ color: 'var(--text-secondary)' }} />
        </div>

        {/* Node 3: Biological Mechanism / Pathway */}
        <div style={{
          width: '100%',
          maxWidth: '440px',
          padding: '0.75rem 1rem',
          backgroundColor: 'var(--bg-surface)',
          borderRadius: '6px',
          border: '1px solid var(--border-color)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          boxShadow: 'var(--shadow-sm)'
        }}>
          <div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Biological Pathway Cascade</div>
            <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>{pathwayName}</div>
          </div>
          <Badge variant="neutral">Curated Path</Badge>
        </div>

        {/* Edge 3: Pathway -> Disease */}
        <div
          onClick={() => {
            const ev = therapeutic_evidence.find((e) => e.source.toLowerCase().includes('opentargets')) || therapeutic_evidence[0];
            if (ev) onSelectEvidence(ev);
          }}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            cursor: 'pointer',
            padding: '0.2rem 0.5rem',
            borderRadius: '4px'
          }}
          title="Click to view disease association score"
        >
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
            ↓ Disease Association & Direction of Effect (Open Targets)
          </span>
          <ArrowDown size={16} style={{ color: 'var(--text-secondary)' }} />
        </div>

        {/* Node 4: Disease Indication */}
        <div style={{
          width: '100%',
          maxWidth: '440px',
          padding: '0.75rem 1rem',
          backgroundColor: 'var(--bg-surface)',
          borderRadius: '6px',
          border: '2px solid #0f172a',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          boxShadow: 'var(--shadow-sm)'
        }}>
          <div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Target Disease / Pathology</div>
            <div style={{ fontWeight: 700, fontSize: '1rem' }}>{disease.name}</div>
          </div>
          {disease.mesh_id && <code>{disease.mesh_id}</code>}
        </div>

        {/* Edge 4: Disease -> Final Decision (incorporating clinical trials & opposition veto) */}
        <div
          onClick={() => {
            if (regEvidence) onSelectEvidence(regEvidence);
            else if (clinicalEvidence) onSelectEvidence(clinicalEvidence);
          }}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            cursor: 'pointer',
            padding: '0.2rem 0.5rem',
            borderRadius: '4px'
          }}
          title="Click to view regulatory & clinical trial support"
        >
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: decision.verdict === 'OPPOSE' ? 'var(--oppose-color)' : 'var(--support-color)' }}>
            ↓ Clinical Outcome & Opposition Screening: {opposition.level === 'NONE' ? 'Veto Clean' : `Active Veto (${opposition.level})`}
          </span>
          <ArrowDown size={16} style={{ color: decision.verdict === 'OPPOSE' ? 'var(--oppose-color)' : 'var(--support-color)' }} />
        </div>

        {/* Node 5: Final Epistemic Decision */}
        <div style={{
          width: '100%',
          maxWidth: '440px',
          padding: '0.85rem 1.25rem',
          backgroundColor: decision.verdict === 'SUPPORT' ? 'var(--support-bg)' : (decision.verdict === 'OPPOSE' ? 'var(--oppose-bg)' : 'var(--uncertain-bg)'),
          borderRadius: '6px',
          border: `2px solid ${decision.verdict === 'SUPPORT' ? 'var(--support-color)' : (decision.verdict === 'OPPOSE' ? 'var(--oppose-color)' : 'var(--uncertain-color)')}`,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          boxShadow: 'var(--shadow-md)'
        }}>
          <div>
            <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', fontWeight: 600 }}>Final Conclusion</div>
            <div style={{ fontWeight: 800, fontSize: '1.1rem' }}>
              {decision.verdict} — {decision.recommendation}
            </div>
          </div>
          <Badge variant={decision.verdict === 'SUPPORT' ? 'support' : (decision.verdict === 'OPPOSE' ? 'oppose' : 'uncertain')}>
            {decision.hypothesis_status || 'EVALUATED'}
          </Badge>
        </div>
      </div>
    </div>
  );
};
