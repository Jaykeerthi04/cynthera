import React from 'react';
import { Link, Outlet } from 'react-router-dom';
import { Dna, ShieldCheck, FileText } from 'lucide-react';

export const MainLayout: React.FC = () => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {/* Top Navigation */}
      <header className="app-header">
        <div className="app-container header-content">
          <Link to="/" className="logo-link">
            <Dna size={22} style={{ color: 'var(--primary-accent)' }} />
            <span>CYNTHERA</span>
            <span className="logo-badge">Research Grade</span>
          </Link>

          <nav style={{ display: 'flex', gap: '1.25rem', alignItems: 'center', fontSize: '0.875rem' }}>
            <Link to="/" style={{ color: 'var(--text-secondary)', fontWeight: 500 }}>
              New Evaluation
            </Link>
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: 'var(--text-muted)' }}
            >
              Documentation
            </a>
          </nav>
        </div>
      </header>

      {/* Main Content Body */}
      <main style={{ flex: 1 }}>
        <Outlet />
      </main>

      {/* Footer */}
      <footer style={{ borderTop: '1px solid var(--border-color)', backgroundColor: 'var(--bg-surface)', padding: '1.5rem 0' }}>
        <div className="app-container" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          <div>
            CYNTHERA — Contradiction-Aware Mechanistic Reasoning Engine for Drug Repurposing
          </div>
          <div>
            Built with strict empirical opposition vetoes & canonical biomedical traceability
          </div>
        </div>
      </footer>
    </div>
  );
};
