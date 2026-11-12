# 🚀 CI/CD Failure Predictor & Graph-Based RCA - Complete System

**A comprehensive AI-powered platform for analyzing, predicting, and diagnosing CI/CD pipeline failures using machine learning, knowledge graphs, and automated root cause analysis.**

![Status](https://img.shields.io/badge/status-production--ready-green)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-blue)

---

## 📋 Table of Contents

1. [Overview](#-overview)
2. [System Architecture](#-system-architecture)
3. [Prerequisites & Requirements](#-prerequisites--requirements)
4. [Installation](#-installation)
5. [Configuration](#-configuration)
6. [Running the Project](#-running-the-project)
7. [Project Structure](#-project-structure)
8. [How It Works](#-how-it-works)
9. [Features & Capabilities](#-features--capabilities)
10. [Troubleshooting](#-troubleshooting)

---

## 📌 Overview

This integrated system analyzes GitHub commits and CI/CD pipelines to:

✅ **Predict failures** using 3 independent ML models (Logistic Regression, SVM, BiLSTM)
✅ **Analyze logs** from GitHub Actions with automated pattern detection
✅ **Trace code impact** using Neo4j knowledge graphs and AST parsing
✅ **Provide RCA** (Root Cause Analysis) with actionable remediation suggestions
✅ **Visualize results** in an interactive Streamlit dashboard

### Key Components

| Component | Purpose | Technology |
|-----------|---------|-----------|
| **streamlit-dashboard** | Web UI for analysis | Streamlit, Plotly, Python |
| **ORC** | Commit analysis orchestration | Python, GitHub API |
| **logpipeline** | Log ingestion & ML prediction | FastAPI, TensorFlow, PyTorch |
| **Metadata-Pipeline-main** | Commit metadata extraction | Python, Git API |
| **graph-doc-gen-main** | Code parsing & Neo4j graph | AST parsing, Neo4j |

---

## 🏛️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  Streamlit Dashboard (Port 8501)                │
│                                                                 │
│  ┌──────────────────────┐         ┌──────────────────────┐     │
│  │   Workflow 1:        │         │   Workflow 2:        │     │
│  │ Metadata + Graph RCA │         │  Log Analysis        │     │
│  └──────────────────────┘         └──────────────────────┘     │
└──────────────┬──────────────────────────────────┬───────────────┘
               │                                  │
               v                                  v
    ┌──────────────────────┐           ┌──────────────────────┐
    │ ORC Backend          │           │ Log Pipeline API     │
    │ (Port 8000)          │           │ (Port 8000)          │
    │                      │           │                      │
    │ • Prediction         │           │ • Log Ingestion      │
    │ • SHAP Explainers    │           │ • Classification     │
    │ • Graph Sync         │           │ • RCA Analysis       │
    └──────────────────────┘           └──────────────────────┘
               │                                  │
       ┌───────┴──────┬──────────┐               │
       │              │          │               │
       v              v          v               v
   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
   │Metadata- │  │graph-doc-│  │LightGBM  │  │BiLSTM v2 │
   │Pipeline  │  │gen-main  │  │+SVM+LR   │  │(PyTorch) │
   │(Metadata)│  │(Neo4j)   │  │Models    │  │Models    │
   └──────────┘  └──────────┘  └──────────┘  └──────────┘
```

---

## 📦 Prerequisites & Requirements

### System Requirements
- **Python**: 3.8 or higher
- **Git**: For cloning repositories
- **npm/Node.js**: Optional (for graph visualization)
- **Neo4j**: Database for code graph storage (optional but recommended)

### Required APIs/Services
- **GitHub Token** (PAT): For accessing repository metadata via API
- **Neo4j Instance**: For graph database (local or cloud)
- **Docker** (optional): For running Neo4j in container

### Storage Space
- Minimum: 500MB for Python dependencies
- Recommended: 2GB for models, cache, and data
- Optional: 1-5GB for Neo4j database

---

## 🚀 Installation

### Step 1: Clone the Repository

```bash
# Navigate to your projects directory
cd /path/to/projects

# Clone/download all components (they should already be in finaltest)
# Ensure you have these directories:
# - streamlit-dashboard/
# - orc/
# - logpipeline/
# - Metadata-Pipeline-main/
# - graph-doc-gen-main/
```

### Step 2: Set Up Virtual Environment

```bash
# Navigate to streamlit-dashboard
cd streamlit-dashboard

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
# Install Streamlit dashboard dependencies
pip install -r requirements.txt

# Install ORC dependencies (from orc directory)
cd ../orc
pip install -r requirements.txt

# Install logpipeline dependencies (from logpipeline directory)
cd ../logpipeline
pip install -r requirements.txt

# Install graph-doc-gen dependencies (if using Neo4j features)
cd ../graph-doc-gen-main
pip install -r requirements.txt
```

### Step 4: Set Up Environment Variables

Create `.env` files in each component directory:

#### streamlit-dashboard/.env
```env
# GitHub Configuration
GITHUB_TOKEN=your_github_pat_token_here

# ORC Backend
ORC_API_URL=http://localhost:8000

# Log Pipeline Backend
LOG_PIPELINE_API_URL=http://localhost:8001

# Neo4j (optional)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=graphdoc
```

#### orc/.env
```env
GITHUB_TOKEN=your_github_pat_token_here
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=graphdoc
INVESTIGATION_THRESHOLD=0.50
MAX_RETRIES=3
RETRY_BACKOFF_SECONDS=2.0
```

#### logpipeline/.env
```env
GITHUB_TOKEN=your_github_pat_token_here
LOG_PIPELINE_DEBUG=false
ML_MODEL_PATH=models/
DATABASE_URL=sqlite:///./data/pipeline.db
```

### Step 5: Set Up Neo4j (Optional but Recommended)

**Option A: Docker**
```bash
docker run -d \
  -p 7687:7687 \
  -p 7474:7474 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5.15
```

**Option B: Local Installation**
Download from https://neo4j.com/download/ and follow installation guide

---

## ⚙️ Configuration

### GitHub Token Setup

1. Go to GitHub Settings → Developer settings → Personal access tokens
2. Create new token with scopes:
   - `repo` (Full control of private repositories)
   - `read:org` (Read organization data)
3. Copy token and add to `.env` files

### Streamlit Configuration

Edit `streamlit-dashboard/.streamlit/config.toml`:

```toml
[theme]
primaryColor = "#FF6B6B"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
textColor = "#262730"
font = "sans serif"

[server]
port = 8501
headless = true
runOnSave = true

[logger]
level = "info"
```

### Neo4j Connection

```cypher
# Test connection:
# In Neo4j Browser, run:
RETURN "Connected to Neo4j" as status;
```

---

## ▶️ Running the Project

### Quick Start (All Components)

```bash
# Terminal 1: Start Neo4j (if using Docker)
docker run -d -p 7687:7687 -p 7474:7474 -e NEO4J_AUTH=neo4j/password neo4j:5.15

# Terminal 2: Start Log Pipeline API
cd logpipeline
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8001 --reload

# Terminal 3: Start ORC Backend (optional, if needed)
cd orc
python -m uvicorn src.orchestrator:app --host 0.0.0.0 --port 8000 --reload

# Terminal 4: Start Streamlit Dashboard
cd streamlit-dashboard
streamlit run app.py
```

### Dashboard-Only (Minimal Setup)

```bash
# If backend APIs already running
cd streamlit-dashboard
streamlit run app.py
```

Dashboard will open at: **http://localhost:8501**

### Testing Individual Components

```bash
# Test streamlit-dashboard
cd streamlit-dashboard
pytest tests/

# Test ORC
cd orc
pytest tests/

# Test logpipeline
cd logpipeline
pytest tests/
```

---

## 📁 Project Structure

### Streamlit Dashboard

```
streamlit-dashboard/
├── app.py                          # Main entry point
├── requirements.txt                # Dependencies
├── .env                            # Configuration (create from .env.example)
├── .streamlit/
│   └── config.toml                # Streamlit settings
├── src/
│   ├── state/
│   │   └── session.py             # Session state management
│   ├── ui/
│   │   ├── input_section.py       # Repo + SHA input
│   │   ├── workflow1.py           # Metadata + Graph analysis
│   │   ├── workflow2.py           # Log analysis
│   │   ├── layout.py              # UI layout
│   │   └── sidebar.py             # Sidebar components
│   └── __init__.py
└── tests/
    ├── test_workflows.py
    └── test_integration.py
```

### ORC (Orchestration)

```
orc/
├── src/
│   ├── main.py                    # CLI entry
│   ├── orchestrator.py            # Main orchestration logic
│   ├── adapters/
│   │   ├── graph_adapter.py       # Neo4j integration
│   │   └── metadata_adapter.py    # Metadata extraction
│   ├── models/
│   │   └── prediction_result.py   # Data models
│   └── storage/
│       └── checkpoint_manager.py  # State persistence
├── requirements.txt
└── .env
```

### Log Pipeline

```
logpipeline/
├── src/
│   ├── api/
│   │   ├── main.py               # FastAPI app
│   │   └── routes/               # API endpoints
│   ├── models/
│   │   ├── bilstm_v2.py          # BiLSTM model
│   │   ├── svm_model.py          # SVM model
│   │   └── logistic_regression.py # LR model
│   ├── parser/
│   │   └── log_parser.py         # Log parsing logic
│   └── orchestrator/
│       └── runtime_tracker.py    # Model inference
├── requirements.txt
└── data/
    ├── models/                   # Trained model files
    ├── processed/                # Processed data
    └── demo_runs/                # Demo analysis results
```

### Graph Doc Gen

```
graph-doc-gen-main/
├── code_parser/
│   └── extractor.py              # AST parsing
├── database/
│   └── neo4j_client.py           # Neo4j interface
├── maintenance/
│   ├── diff_agent.py             # Git diff analysis
│   └── git_utils.py              # Git operations
└── requirements.txt
```

---

## 🔄 How It Works

### Workflow 1: Metadata + Graph RCA

1. **Input**: GitHub repo (owner/repo) + commit SHA
2. **Metadata Extraction**: Extracts commit metadata, file changes, blame history
3. **Prediction**: Runs 3 ML models on extracted features
4. **SHAP Analysis**: Explains which features contribute to failure prediction
5. **Graph Sync**: Parses code and syncs Neo4j knowledge graph
6. **RCA**: Analyzes changed files and their dependencies
7. **Output**: Risk score, SHAP drivers, suspicious files, remediation suggestions

**Time**: ~2-10 seconds depending on repo size

### Workflow 2: Log Analysis

1. **Input**: GitHub repo + commit SHA
2. **Auto-Detection**: Finds GitHub Actions workflows for commit
3. **Log Retrieval**: Fetches logs from GitHub Actions API
4. **Log Parsing**: Extracts errors, warnings, and patterns
5. **Classification**: Categorizes failure type (Syntax, Dependency, Test, Timeout)
6. **RCA**: Provides root cause explanation
7. **Remediation**: Suggests fixes and prevention strategies
8. **Output**: Error analysis, RCA findings, suggested commands

**Time**: Real-time as logs arrive, updates as build progresses

---

## ✨ Features & Capabilities

### Prediction Features
- ✅ Multi-model ensemble predictions (Logistic Regression, SVM, BiLSTM)
- ✅ Progressive inference at 25%, 50%, 75%, 100% log depth
- ✅ Real-time risk scoring and early warning system
- ✅ SHAP explainability for model predictions

### Analysis Features
- ✅ Automatic log ingestion from GitHub Actions
- ✅ Structured error pattern detection
- ✅ 5-category RCA (Syntax, Dependency, Test, Timeout, Fallback)
- ✅ Neo4j knowledge graph with blast radius analysis
- ✅ Commit provenance tracking

### Remediation Features
- ✅ Copyable terminal commands for fixes
- ✅ Configuration suggestions with explanations
- ✅ Best practices and prevention strategies
- ✅ Links to documentation and resources

### Visualization Features
- ✅ Interactive risk meters and gauges
- ✅ Dependency graphs and topology visualization
- ✅ SHAP waterfall plots
- ✅ Timeline and progression indicators
- ✅ Downloadable analysis reports

---

## 🐛 Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'streamlit'"

**Solution**:
```bash
# Ensure virtual environment is activated
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Issue: "GitHub token not found"

**Solution**:
```bash
# Create GitHub personal access token at:
# https://github.com/settings/tokens

# Add to .env file:
echo "GITHUB_TOKEN=ghp_xxxxxxxxxxxx" >> .env
```

### Issue: "Neo4j connection refused"

**Solution**:
```bash
# Start Neo4j (Docker)
docker run -d -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5.15

# Or check if local Neo4j service is running
# macOS: brew services start neo4j
# Linux: sudo systemctl start neo4j
# Windows: net start Neo4j
```

### Issue: "API Port Already in Use"

**Solution**:
```bash
# Change port in command:
streamlit run app.py --server.port=8502

# Or kill existing process:
# Windows: netstat -ano | findstr :8501 → taskkill /PID xxxxx
# macOS/Linux: lsof -i :8501 → kill -9 xxxxx
```

### Issue: "Log Pipeline API Connection Timeout"

**Solution**:
```bash
# Ensure Log Pipeline is running:
cd logpipeline
python -m uvicorn src.api.main:app --port 8001

# Check if service is responsive:
curl http://localhost:8001/health
```

---

## 📞 Support & Contact

For issues, questions, or suggestions:

1. Check the **Troubleshooting** section above
2. Review existing GitHub Issues
3. Create a new Issue with:
   - Steps to reproduce
   - Error messages/logs
   - System information (OS, Python version)
   - Expected vs. actual behavior

---

## 📄 License

This project is part of the CI/CD Failure Predictor capstone project. All code is provided as-is for educational and research purposes.

---

## 🎯 Quick Reference

| Task | Command |
|------|---------|
| Setup | `pip install -r requirements.txt` |
| Start Dashboard | `streamlit run app.py` |
| Start Log Pipeline | `python -m uvicorn src.api.main:app --port 8001` |
| Run Tests | `pytest tests/ -v` |
| View Logs | `tail -f streamlit.log` |
| Format Code | `black src/` |
| Check Health | `curl http://localhost:8501/health` |

---

## 📌 Version History

- **v1.0.0** (Current) - Production release with full integration
- **v0.9.0** - Beta testing with core features
- **v0.5.0** - Alpha release with basic workflows

---

**Last Updated**: November 2026  
**Maintainers**: Dhruv Hegde, Team  
**Status**: ✅ Production Ready
