# CYNTHERA — Research-Grade Biomedical Frontend

This directory contains the researcher-facing React + TypeScript + Vite web application for the CYNTHERA Drug Repurposing Reasoning Engine.

---

## Features

- **Authoritative 3-Class Decision Card**: Directly presents authoritative backend decisions (`SUPPORT`, `OPPOSE`, `UNCERTAIN`) and recommendations (`PROMISING`, `NOT_RECOMMENDED`, `UNCERTAIN`) with explicit structured evidence states (Therapeutic Anchor, Mechanistic Level, Therapeutic Evidence, Opposition, Contradiction, Safety Grade).
- **Evidence Balance & Independence**: Distinguishes between multi-database raw citation counts and independent clinical study groups.
- **Hierarchical Mechanism Panel**: Visualizes the traced chain `Drug → Target → Reaction → Pathway → Disease`, with causal grounding badges (`DIRECT`, `CURATED`, `INFERRED`, `STRUCTURAL`). Structural interactions are explicitly never conflated with causal proof.
- **Opposing Evidence & Trial Failures**: Prominently displays clinical trial failures, futility terminations, safety terminations, and pair-specific negative claims (Rule 2b veto).
- **Contradiction Registry**: Visual `Supporting ↕ Conflict ↕ Opposing` conflict representations with plain-language explanations.
- **Traceable Evidence Drawer**: Granular record inspection with verified PMIDs, NCT IDs, ChEMBL IDs, DOIs, and canonical external hyperlinks without link fabrication.
- **Source Availability & Coverage**: Explicitly exposes missing or unavailable sources (e.g. rate-limited services) so users never mistake retrieval outages for lack of evidence.
- **Comprehensive 15-Section Scientific Report**: Interactive in-browser report viewer and one-click export to server-generated PDF via ReportLab.
- **Audit Mode**: Quick toggle between concise researcher presentation and deep epistemic audit traces (agent verdicts, raw identifiers, decision traces).

---

## Quick Start

### 1. Start the FastAPI Backend
From the repository root (`cynthera/`):
```bash
uvicorn backend.api.main:create_app --factory --reload --port 8000
```
API docs available at `http://localhost:8000/docs`.

### 2. Start the Frontend Dev Server
From the `frontend/` directory:
```bash
npm install
npm run dev
```
Open `http://localhost:3000` in your web browser.

### 3. Run Tests
```bash
npm test
```

### 4. Build for Production
```bash
npm run build
```
Production assets are output to `frontend/dist/`.
