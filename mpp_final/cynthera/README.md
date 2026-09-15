# 🧬 CYNTHERA — Evidence-Traceable, Mechanism-Grounded & Directional AI Research Assistant for Drug Repurposing

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Unit Tests](https://img.shields.io/badge/tests-487%20passing-brightgreen.svg)](tests/)
[![Architecture](https://img.shields.io/badge/architecture-sealed%20two--tier-purple.svg)](#-architecture)

[![Data](https://img.shields.io/badge/data-100%25%20free%20open%20biomedical-orange.svg)](#-data-sources-100-free--open)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](#-license--disclaimer)

**CYNTHERA** investigates a **Drug + Disease** hypothesis and produces a scientifically defensible, multi-dimensional assessment of **Mechanistic Plausibility** and **Therapeutic Directional Consistency**, backed by multi-hop biological reasoning and traceable to primary sources (PMIDs, DOIs, clinical trial IDs, and curated database records).

Unlike naive LLM wrappers that hallucinate causal mechanisms or treat structural associations as therapeutic efficacy, CYNTHERA enforces **biological rigor**:
1. **Mechanism-first reasoning:** Biological chains (`Drug → Target → Reaction → Pathway → Disease Gene → Disease`) are constructed from retrieved database records (ChEMBL, Reactome, UniProt, Open Targets, DisGeNET), not invented by a language model.
2. **Strict Semantic Separation:** Mechanistic plausibility, molecular polarity, therapeutic direction, and directional mechanism consistency are computed and maintained as orthogonal dimensions.
3. **Traceability:** Every conclusion is linked to underlying evidence records with direct access links.
4. **Honest Failure & Non-Conflation:** Missing data is never silently converted into biological implausibility. `INSUFFICIENT EVIDENCE`, `CONTRADICTORY EVIDENCE`, `UNSUPPORTED`, and `PLAUSIBLE` are strictly partitioned states.

---

## 🔬 Scientific Core: The Four Reasoning Dimensions

A common failure mode of biomedical AI is collapsing different scientific questions into a single scalar confidence score. CYNTHERA strictly separates four dimensions:

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                               CYNTHERA REASONING DIMENSIONS                              │
├──────────────────────────────┬──────────────────────────────┬─────────────────────────────┤
│ Dimension                    │ Scientific Question          │ Values / Spectrum           │
├──────────────────────────────┼──────────────────────────────┼─────────────────────────────┤
│ 1. Mechanistic Plausibility  │ Is there an evidence-backed  │ Score: [0.0, 1.0]           │
│    (MS)                      │ multi-hop path from drug     │ Level: HIGH / MEDIUM /      │
│                              │ target to the disease?       │        LOW / NONE           │
├──────────────────────────────┼──────────────────────────────┼─────────────────────────────┤
│ 2. Molecular Polarity        │ What is the sign of an       │ POSITIVE (+) / NEGATIVE (-) │
│                              │ individual molecular edge?   │ / UNKNOWN (?)               │
├──────────────────────────────┼──────────────────────────────┼─────────────────────────────┤
│ 3. Therapeutic Direction     │ Does drug action match the   │ SUPPORTS / OPPOSES /        │
│    Alignment                 │ required disease target      │ INSUFFICIENT                │
│                              │ direction of effect?         │                             │
├──────────────────────────────┼──────────────────────────────┼─────────────────────────────┤
│ 4. Directional Mechanism     │ Does the multi-hop pathway   │ CONSISTENT / CONTRADICTORY  │
│    Consistency               │ preserve or contradict the   │ / PARTIAL / UNKNOWN         │
│                              │ target therapeutic action?   │                             │
└──────────────────────────────┴──────────────────────────────┴─────────────────────────────┘
```

### The Reactome Invariant
Reactome participation roles (`CATALYST`, `INPUT`, `OUTPUT`, `PARTICIPANT`, `COMPLEX_COMPONENT`, `ENTITY_SET_MEMBER`) represent **structural physical connectivity**, not causal regulation. CYNTHERA enforces a non-negotiable invariant:
- Structural Reactome participation strictly receives `MolecularPolarity.UNKNOWN` and `CausalGrounding.STRUCTURAL`.
- Only explicit regulatory annotations (`POSITIVE_REGULATOR`, `NEGATIVE_REGULATOR`) or curated literature claims carry non-zero sign.
- **Low mechanistic score $\neq$ therapeutic opposition.**
- **Missing reaction evidence $\neq$ mechanistic score of 0.**
- **High mechanistic plausibility $\neq$ therapeutic support** (e.g., *Testosterone* has high mechanistic connectivity to *Prostate Cancer*, but directionally **OPPOSES** treatment because it activates the androgen receptor).

---

## ✨ Features & Capabilities

### 1. Multi-Hop Evidence Graph & Path Finding
- Dynamically constructs a typed biological `EvidenceGraph` with `DRUG`, `TARGET`, `PATHWAY`, `REACTION`, `GENE`, and `DISEASE` nodes.
- Performs depth-first search (DFS) pathfinding to discover 2-hop to 5-hop reaction-enriched biological cascades:
  - **4-Hop Direct Pathway:** `Drug → Target → Pathway → Disease Gene → Disease`
  - **5-Hop Reaction-Enriched:** `Drug → Target → Reaction → Pathway → Disease Gene → Disease`
- **Zero-Crowding Pathway Ranking:** Discovers relevant pathways by filtering to confirmed target participants and prioritizing confirmed disease-gene overlap before slicing.
- **Infectious Disease Primary Target Support:** Seamlessly supports pathogen-encoded targets (e.g., viral Neuraminidase for *Oseltamivir → Influenza*).

### 2. Multi-Dimensional Candidate Mechanism Validation
- Validates discovered candidate mechanisms against 7 transparent dimensions:
  1. `edge_validity` (affinity confidence, interaction type, database provenance)
  2. `directionality` (molecular polarity consistency)
  3. `disease_relevance` (disease-gene association score from Open Targets / DisGeNET)
  4. `curated_database_support` (ChEMBL + Reactome curation tiers)
  5. `literature_support` (PubMed / Europe PMC claim grounding)
  6. `evidence_independence` (study replication across distinct sources)
  7. `contradictory_evidence` (explicit negative or conflicting claims penalty)
- Synthesizes candidate support ratings: `STRONGLY_SUPPORTED`, `MODERATELY_SUPPORTED`, `WEAK_SPECULATIVE`, `CONTRADICTED`, and `UNSUPPORTED`.

### 3. Directional Evidence & Therapeutic Alignment Engine
- **Drug Action Normalization:** Normalizes bioactivity classifications from ChEMBL (e.g., `INHIBITOR`, `AGONIST`, `ANTAGONIST`, `POSITIVE_ALLOSTERIC_MODULATOR`).
- **Disease Target Requirement:** Retrieves target directionality from Open Targets Direction-of-Effect (DoE) and DisGeNET Actionable Target Trajectories (DATTs).
- **Contradiction-Aware Alignment:** Employs independent evidence grouping with conservative aggregation to resolve alignment verdicts (`SUPPORTS`, `OPPOSES`, `INSUFFICIENT`).
- **Directional Mechanism Evaluator:** Evaluates candidate paths for intermediate regulatory contradictions (e.g., drug inhibition acting on a negative regulator of a disease mediator).

### 4. Contextual Clinical Trial Analysis
- Connects directly to ClinicalTrials.gov API.
- Deeply inspects `whyStopped` logs using NLP pattern matching to distinguish true clinical safety/efficacy failures from administrative/operational friction (e.g., low recruitment, funding withdrawal, COVID-19 logistical disruptions).

### 5. Benchmark Grounding & Statistical Calibration
- **24 Curated Evaluation Cases:** Partitioned into `TEST` (13 cases) and `DEVELOPMENT` (11 cases) splits to prevent evaluation contamination.
- **True Contradiction Controls:** Includes verified opposing pairs (*Testosterone → Prostate Cancer*, *Digoxin → WPW*, *Salbutamol → HCM*, *Verapamil → HFrEF*, *Finasteride → ER+ Breast Cancer*).
- **Real Component Ablation:** Measures performance across `FULL_4D`, `NO_OPEN_TARGETS`, `NO_DATTS`, and `UNWEIGHTED_BASELINE`.
- **Statistical Calibration:** Computes non-parametric bootstrap confidence intervals (1,000 resamples, seed=42) for Accuracy, Precision, Recall, Specificity, F1, and MCC.

### 6. Traceability & Source URLs
- Every claim is linked: `Conclusion → Claim ID → Evidence IDs → PMID / DOI / DB Accession → Source URL`.
- Directly opens authoritative database entries: ChEMBL assays, UniProt accessions, Reactome reaction/pathway diagrams, Open Targets disease associations, and PubMed/Europe PMC articles.

---

## 🏗️ Architecture

CYNTHERA uses a **sealed two-tier architecture**: a deterministic engineering retrieval layer feeds a structured `RetrievalPackage` into an agentic + rule-based reasoning layer.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                          ENGINEERING RETRIEVAL LAYER (Deterministic)                   │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Master Orchestrator                                                                    │
│   ├── Biological Identifier Normalizer (ChEMBL, UniProt, MeSH, MONDO, Ensembl, HGNC)   │
│   ├── Async Parallel Connectors:                                                       │
│   │     • ChEMBL (bioactivity, targets, mechanism of action)                           │
│   │     • UniProt (canonical accessions, human proteome verification)                  │
│   │     • Reactome (pathway hierarchies, reaction events, molecular roles)             │
│   │     • Open Targets Platform (disease associations, Direction-of-Effect)            │
│   │     • DisGeNET (curated gene-disease scores, actionable target trajectories)       │
│   │     • Europe PMC & PubMed (literature citations, abstracts)                        │
│   │     • ClinicalTrials.gov (recruitment status, whyStopped termination logs)         │
│   │     • Semantic Scholar & OpenAlex (citation-weighted literature metadata)          │
│   └── Tiered SQLite Raw-Response Cache Layer (`data/cynthera.db`)                      │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                               Sealed `RetrievalPackage`
                                            │
┌───────────────────────────────────────────▼────────────────────────────────────────────┐
│                             REASONING & ASSESSMENT LAYER                               │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. Claim Extraction Agent (Groq / Gemini LLM with deterministic rule fallback)         │
│ 2. Evidence Graph Builder (Typed multi-relational graph construction)                  │
│ 3. Multi-Hop Reasoner (DFS pathfinder discovering 2-hop to 5-hop reaction paths)       │
│ 4. Mechanism Validator (7-dimensional candidate mechanism validation)                  │
│ 5. Directional Mechanism Evaluator (Path-level regulatory polarity & contradictions)   │
│ 6. Therapeutic Alignment Engine (DoE / DATT target-level directional consensus)        │
│ 7. Clinical Safety Agent (Trial outcome classification & adverse event profiling)      │
│ 8. Deterministic Decision Engine & Scientific Context Builder                          │
│ 9. Scientific Audit Report & Evaluation Exporters (Streamlit, REST API, PDF)          │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🌐 Data Sources (100% Free & Open)

| Data Source | Domain / Biological Coverage | Direct Resource Link |
| :--- | :--- | :--- |
| **ChEMBL** | Drug bioactivities, primary targets, action mechanisms | [ebi.ac.uk/chembl](https://www.ebi.ac.uk/chembl/) |
| **UniProt** | Human protein accessions, canonical sequence mapping | [uniprot.org](https://www.uniprot.org/) |
| **Reactome** | Pathways, reaction events, molecular participant roles | [reactome.org](https://reactome.org/) |
| **Open Targets** | Disease–gene associations, Direction-of-Effect (DoE) | [platform.opentargets.org](https://platform.opentargets.org/) |
| **DisGeNET** | Gene–disease evidence scores, actionable trajectories | [disgenet.org](https://www.disgenet.org/) |
| **PubMed** | MEDLINE citations, biomedical literature abstracts | [pubmed.ncbi.nlm.nih.gov](https://pubmed.ncbi.nlm.nih.gov/) |
| **Europe PMC** | Open-access articles, full text, external links | [europepmc.org](https://europepmc.org/) |
| **ClinicalTrials.gov** | Clinical trial protocols, status, whyStopped logs | [clinicaltrials.gov](https://clinicaltrials.gov/) |
| **Semantic Scholar** | Citation-weighted scientific literature metadata | [semanticscholar.org](https://www.semanticscholar.org/) |
| **OpenAlex** | Global scholarly bibliographic catalog | [openalex.org](https://openalex.org/) |

---

## 🚀 Quick Start

### 1. Installation

```bash
# 1. Clone repository
git clone https://github.com/sameekshaa19/cynthera.git
cd cynthera

# 2. Create virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration

Copy `.env.example` to `.env`:
```bash
cp .env.example .env    # Linux/macOS
copy .env.example .env  # Windows
```

Configure your LLM provider and optional API keys in `.env`:
```env
# LLM Extraction Provider (Groq or Gemini)
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: Higher rate-limit keys
NCBI_API_KEY=your_ncbi_api_key_here
SEMANTIC_SCHOLAR_API_KEY=your_semantic_scholar_key_here
```
*(Note: CYNTHERA operates seamlessly with automatic rule-based extractors even if LLM keys are omitted).*

---

## 💻 Usage

### Command-Line Interface (CLI)

Evaluate a drug-disease hypothesis directly:
```bash
python main.py --drug "Sildenafil" --disease "Pulmonary Arterial Hypertension"
```

Bypass local cache for live real-time API retrieval:
```bash
python main.py --drug "Lisinopril" --disease "Hypertension" --no-cache
```

Export detailed scientific assessment to JSON:
```bash
python main.py --drug "Testosterone" --disease "Prostate Cancer" --output report.json
```

### Interactive Streamlit Web Dashboard

Launch the full visual dashboard featuring interactive multi-hop chain cards, reaction event viewers, directional alignment badges, and PDF export:
```bash
streamlit run frontend/app.py
```
Open `http://localhost:8501` in your browser.

### FastAPI REST Service

Launch the high-performance async REST API:
```bash
python -m uvicorn backend.api.main:app --reload --port 8000
```
- Interactive OpenAPI documentation: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/v1/health`

---

## 📊 Benchmark & Evaluation Framework

CYNTHERA includes a standardized benchmark dataset grounded in clinical literature and pharmacological databases ([`backend/evaluation/benchmark_dataset.py`](backend/evaluation/benchmark_dataset.py)):

### Benchmark Composition (24 Curated Cases)
- **TEST Split (13 Cases):** Held-out evaluation set for clinical indications, negative controls, and contradiction cases.
- **DEVELOPMENT Split (11 Cases):** Calibration set for directional weighting and statistical verification.
- **Contradiction Controls (Verified Opposing Pairs):**
  - *Testosterone $\rightarrow$ Prostate Cancer* (`OPPOSES` — androgen receptor agonist promotes prostate tumor proliferation)
  - *Digoxin $\rightarrow$ Wolff-Parkinson-White Syndrome* (`OPPOSES` — AV nodal blockade promotes lethal ventricular arrhythmias)
  - *Salbutamol $\rightarrow$ Hypertrophic Cardiomyopathy* (`OPPOSES` — beta-2 agonist exacerbates left ventricular outflow obstruction)
  - *Verapamil $\rightarrow$ Heart Failure with Reduced Ejection Fraction* (`OPPOSES` — negative inotrope worsens systolic failure)
  - *Finasteride $\rightarrow$ ER+ Breast Cancer* (`OPPOSES` — 5-alpha reductase inhibitor increases estrogen receptor stimulation)

### Running the Live Benchmark
```bash
# Run the 13-case test benchmark
python scratch/run_phase4e_live_benchmark.py

# Run component ablations (FULL_4D, NO_OPEN_TARGETS, NO_DATTS, UNWEIGHTED)
python scratch/run_phase4e_ablation_study.py
```

### Diagnostic Audit Script
Audit mechanistic score dataflow and directional mechanisms across test pairs:
```bash
python scratch/audit_mechanistic_score.py
```

---

## 📁 Project Structure

```
cynthera/
├── backend/
│   ├── api/                          # FastAPI REST API routes & models
│   ├── core/
│   │   ├── domain/                   # Domain entities (CandidateMechanism, RetrievalPackage,
│   │   │                             #   DirectionalMechanismAssessment, Claim, Evidence...)
│   │   ├── enums/                    # Enums (MolecularPolarity, CausalGrounding, RecommendationStatus...)
│   │   └── value_objects/            # Value objects (ERW, ProvenanceReference, SourceURLBuilder...)
│   ├── engineering/
│   │   ├── identity/                 # Biological identifier canonicalization (ChEMBL, UniProt, MeSH)
│   │   ├── orchestrator/             # MasterOrchestrator pipeline coordinator
│   │   └── retrieval/                # Deterministic API connectors (ChEMBL, Reactome, Open Targets...)
│   ├── evaluation/                   # Benchmark dataset (24 cases), metrics, runner, evidence weights
│   ├── infrastructure/               # SQLite cache layer, logging, knowledge store
│   ├── reasoning/
│   │   ├── agents/                   # Clinical safety agent, prior knowledge agent
│   │   ├── conflict/                 # Advanced conflict resolver & contradiction detector
│   │   ├── context/                  # Scientific context builder
│   │   ├── directional/              # Directional mechanism evaluator & Reactome polarity mappers
│   │   ├── extraction/               # Claim extraction agent (LLM + rule-based fallback)
│   │   ├── mechanistic/              # Evidence graph builder, multi-hop reasoner, validator
│   │   ├── normalization/            # Biological identifier resolver
│   │   └── orchestrator/             # Reasoning orchestrator & 3D scoring coordinator
│   └── reporting/                    # PDF report generator & evaluation PDF exporter
├── frontend/
│   └── app.py                        # Streamlit interactive user interface
├── tests/
│   └── unit/                         # 345 unit tests covering all modules & invariants
├── scratch/                          # Audit scripts, ablation runners, live benchmarks
├── data/                             # SQLite persistent cache & database
├── main.py                           # CLI entry point
├── requirements.txt                  # Python dependencies
└── README.md                         # Project documentation
```

---

## 🧪 Running Tests

CYNTHERA maintains an extensive regression test suite guaranteeing dataflow correctness, directional invariants, and edge case resilience:

```bash
# Run all 345 unit tests
python -m pytest tests/unit/ -v

# Run the directional mechanism suite
python -m pytest tests/unit/test_directional_mechanism.py -v

# Run benchmark integrity & calibration tests
python -m pytest tests/unit/test_phase4e_benchmark.py -v
```

---

## 📝 License & Disclaimer

This project is licensed under the **MIT License**.

**Disclaimer:** CYNTHERA is designed exclusively for biological research, hypothesis generation, and educational analysis. It does not provide clinical diagnoses, medical recommendations, or treatment plans. All computational hypotheses, mechanistic chains, and scores must be evaluated and verified by qualified domain experts before any laboratory or clinical application.
