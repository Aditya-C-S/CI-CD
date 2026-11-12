# CI/CD Failure Predictor & Graph-Based RCA Dashboard

A professional Streamlit dashboard for analyzing CI/CD failures using integrated LightGBM predictions, SHAP explanations, knowledge graph analysis, and automatic CI log ingestion.

## Project Overview

This dashboard provides a unified interface for two complementary analysis workflows:

### Workflow 1: Metadata Prediction + Graph RCA
- **Input:** GitHub repository and commit SHA (single input section)
- **Action:** Click "Analyze Commit" button
- **Backend:** ORC → Metadata-Pipeline + graph-doc-gen
- **Output:**
  - LightGBM failure probability with risk level
  - SHAP feature importance explanations
  - Suspicious files identified by the model
  - Knowledge graph relationships and blast radius
  - Root cause analysis findings with remediation suggestions

### Workflow 2: Automatic CI Log Analysis
- **Input:** Repository and commit SHA (shared input section, no additional input)
- **Trigger:** Automatic - GitHub Actions workflows are detected via Log Pipeline API
- **Backend:** Log Pipeline API (no user uploads needed)
- **Output:**
  - GitHub Actions workflow status and logs
  - Log classification and error detection
  - Root cause analysis from logs
  - Remediation suggestions
  - Support for multiple workflow attempts per commit

## Architecture

```
Streamlit Dashboard (Port 8501)
    ↓
    ├─→ Workflow 1: ORC Backend → Metadata-Pipeline + graph-doc-gen
    │   (Metadata prediction and graph-based RCA)
    │
    └─→ Workflow 2: Log Pipeline API (Port 8000)
        (Automatic CI log analysis from GitHub Actions)
```

### Key Principles

✅ **Separation of Concerns**
- ORC, Metadata-Pipeline, graph-doc-gen, and Log Pipeline remain independent
- Dashboard is a UI layer only - no modifications to backend implementations
- No mock data or fabricated results

✅ **User Experience**
- SINGLE input section for both workflows (repository + commit SHA)
- No input fields for Workflow 2 - fully automatic
- Professional, presentation-friendly design
- Clear status indicators for all states

✅ **Architecture Compliance**
- Workflow 2 uses existing Log Pipeline API endpoints
- GitHub Actions log forwarding is unchanged
- Results are real, from actual backend analysis

## Project Structure

```
streamlit-dashboard/
├── app.py                          # Main Streamlit application
├── requirements.txt                # Python dependencies
├── README.md                       # This file
├── .gitignore                      # Git ignore rules
├── .streamlit/
│   └── config.toml                # Streamlit configuration
└── src/
    ├── __init__.py
    ├── state/
    │   ├── __init__.py
    │   └── session.py              # Session state management
    └── ui/
        ├── __init__.py
        ├── layout.py               # Main layout orchestration
        ├── input_section.py        # User input (shared by both workflows)
        ├── workflow1.py            # Metadata prediction + graph RCA
        ├── workflow2.py            # Automatic CI log analysis
        └── sidebar.py              # Configuration and info sidebar
```

## Setup Instructions

### Prerequisites
- Python 3.8+
- pip

### Installation

1. **Navigate to project directory:**
   ```bash
   cd C:\Users\DHRUV HEGDE\Desktop\finaltest\streamlit-dashboard
   ```

2. **Create virtual environment (optional but recommended):**
   ```bash
   python -m venv venv
   venv\Scripts\activate  # On Windows
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

### Running the Dashboard

```bash
streamlit run app.py
```

The dashboard will start at `http://localhost:8501`

### Configuration

Edit `.streamlit/config.toml` to customize:
- Theme colors and fonts
- Server port
- Other Streamlit settings

## UI States

### Workflow 1 States
- ⏹️ **Waiting for input** - Ready for user to click "Analyze Commit"
- 🔄 **Analyzing commit** - ORC and backends are processing
- ✅ **Analysis completed** - Results are displayed
- ❌ **Analysis failed** - Error message with retry option

### Workflow 2 States
- ⏹️ **Ready to fetch runs** - Initial state, waiting for "Fetch CI Runs"
- ⏳ **Waiting for CI run** - No GitHub Actions workflow found yet
- 🔄 **Workflow running** - GitHub Actions is executing
- 📋 **Logs received, processing** - Log Pipeline received logs
- 🔍 **Analysis in progress** - Backend is analyzing logs
- ✅ **Analysis completed** - Results are displayed
- ❌ **Workflow failed** - GitHub Actions failed
- ⚠️ **Backend unavailable** - Log Pipeline API unreachable

## Backend Integration

### Workflow 1 Integration Points

The dashboard will call ORC API to:
1. Submit commit for analysis
2. Get failure probability from Metadata-Pipeline
3. Fetch SHAP explanations
4. Retrieve suspicious files
5. Get graph relationships and blast radius
6. Retrieve RCA findings

**Status:** Implementation pending

### Workflow 2 Integration Points

The dashboard will query Log Pipeline API to:
1. Get list of CI runs for repository + commit SHA
2. Check if logs have been ingested
3. Get log classification and error analysis
4. Retrieve RCA results from logs
5. Get remediation suggestions

**Status:** Implementation pending - Need to verify Log Pipeline API endpoints for:
- Retrieving runs by repository and commit SHA
- Filtering by workflow status
- Retrieving log analysis results

## Current Implementation Status

✅ **Complete**
- UI layout and components
- Session state management
- Input validation
- Professional styling
- All status indicators
- Placeholder sections for results

❌ **Pending**
- Backend API integration for Workflow 1
- Backend API integration for Workflow 2
- Auto-refresh logic for Workflow 2
- Error handling and retry logic

## API Requirements Investigation

### Workflow 2 - Log Pipeline API Endpoints Needed

Please verify the Log Pipeline API (http://127.0.0.1:8000) provides endpoints for:

1. **Get runs by repository and commit SHA**
   ```
   GET /api/runs?repository=owner/repo&commit_sha=abc123&limit=10
   ```
   Expected response: List of runs with workflow_id, run_id, status, timestamp

2. **Get run details and analysis**
   ```
   GET /api/runs/{run_id}/analysis
   ```
   Expected response: Logs, classification, RCA results, remediation suggestions

3. **Check if logs are available**
   ```
   GET /api/runs/{run_id}/status
   ```
   Expected response: status (waiting, received, analyzing, completed), progress

If these endpoints don't exist, we need to:
- Check what endpoints ARE available
- Design new endpoints if needed
- Update this documentation accordingly

## Development Notes

- Dashboard does not modify any backend implementations
- All analysis results come from actual backend computations
- GitHub Actions workflow forwarding to Log Pipeline continues unchanged
- Multiple workflow attempts per commit are fully supported
- Auto-refresh is configurable (5-60 seconds)

## Future Enhancements

- Export results to PDF/JSON
- Commit comparison across multiple SHAs
- Workflow history visualization
- Custom dashboard themes
- Team collaboration features
- Integration with issue/PR tracking

## License

Part of the CI/CD Failure Predictor & RCA Project

## Support

For issues or questions about the dashboard architecture, see the development notes section above.
