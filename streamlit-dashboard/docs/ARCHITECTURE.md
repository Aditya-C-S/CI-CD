# Dashboard Architecture Document

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     STREAMLIT DASHBOARD (Port 8501)                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │          SINGLE USER INPUT SECTION                           │   │
│  │  - GitHub Repository (owner/repo)                            │   │
│  │  - Commit SHA (full or short)                                │   │
│  │  - Input validation with visual feedback                     │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌──────────────────────────┐  ┌──────────────────────────────┐     │
│  │   WORKFLOW 1             │  │   WORKFLOW 2                 │     │
│  │   Metadata Prediction    │  │   CI Log Analysis            │     │
│  │   + Graph RCA            │  │   (Automatic)                │     │
│  │                          │  │                              │     │
│  │  [Analyze Commit Button] │  │  [Fetch CI Runs Button]      │     │
│  │         ↓                │  │         ↓                    │     │
│  │  Results Display:        │  │  Results Display:            │     │
│  │  - Failure Probability   │  │  - Multiple Runs             │     │
│  │  - SHAP Explanations     │  │  - Workflow Status           │     │
│  │  - Suspicious Files      │  │  - Log Classification        │     │
│  │  - Graph Relationships   │  │  - Error Analysis            │     │
│  │  - RCA Findings          │  │  - RCA Results               │     │
│  │                          │  │  - Remediation Suggestions   │     │
│  └──────────────────────────┘  └──────────────────────────────┘     │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                      SIDEBAR                                 │   │
│  │  - Backend Configuration                                     │   │
│  │  - Connection Status                                         │   │
│  │  - Auto-refresh Settings                                     │   │
│  │  - Documentation                                             │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
         ↓                              ↓
         │                              │
    [ORC API]                    [Log Pipeline API]
    (Port 8001)                  (Port 8000)
         ↓                              ↓
    ┌────────────────┐           ┌──────────────────┐
    │  Metadata-     │           │  Log Ingestion   │
    │  Pipeline      │           │  & Analysis      │
    │  + graph-doc-  │           │                  │
    │  gen           │           │  - Log Parser    │
    │                │           │  - Classifier    │
    │  - LightGBM    │           │  - RCA Engine    │
    │  - SHAP        │           │  - Remediation   │
    │  - Knowledge   │           │    Generator     │
    │    Graph       │           │                  │
    └────────────────┘           └──────────────────┘
         ↓                              ↓
    ┌────────────────┐           ┌──────────────────┐
    │  Neo4j Graph   │           │  GitHub Actions  │
    │  Database      │           │  (External)      │
    │  (graphdoc)    │           │                  │
    └────────────────┘           └──────────────────┘
```

## Data Flow

### Workflow 1: Metadata Prediction + Graph RCA

```
User Input
  ↓
Validation
  ↓
[Click "Analyze Commit"]
  ↓
Streamlit → ORC API
  ├─ Submit: repository + commit_sha
  └─ Poll: analysis_id
      ↓
  ORC Backend
    ├─ Invokes Metadata-Pipeline
    │  └─ Runs LightGBM model
    │  └─ Computes SHAP explanations
    │  └─ Identifies suspicious files
    ├─ Invokes graph-doc-gen
    │  └─ Builds code relationships
    │  └─ Calculates blast radius
    └─ Generates RCA report
      ↓
  Streamlit ← Results
    ├─ Display failure probability
    ├─ Display SHAP feature importance
    ├─ Display suspicious files
    ├─ Display graph relationships
    └─ Display RCA findings
```

### Workflow 2: Automatic CI Log Analysis

```
GitHub Actions Workflow (External)
  ↓
[Commit Pushed]
  ↓
GitHub Actions Runs
  ├─ Workflow 1: Python Tests
  ├─ Workflow 2: Integration Tests
  └─ Workflow 3: Security Scan
  ↓
[Logs Forwarded to Log Pipeline]
  ↓
User Input (Repository + Commit SHA)
  ↓
[Click "Fetch CI Runs"]
  ↓
Streamlit → Log Pipeline API
  ├─ Query: /api/demo/runs?repository=X&commit_sha=Y
  ├─ Get list of CI runs
  └─ For each run:
      ├─ Check if logs are collected
      ├─ Retrieve log analysis
      ├─ Get RCA results
      └─ Get remediation suggestions
      ↓
  Streamlit ← Results
    ├─ Display runs in tabs
    ├─ For each run show:
    │  ├─ Workflow name and status
    │  ├─ Log classification
    │  ├─ Error analysis
    │  ├─ RCA findings
    │  └─ Remediation suggestions
    └─ Auto-refresh periodically
```

## Session State Management

```
Session State (Streamlit)
├── User Input
│   ├── github_repo (string)
│   └── commit_sha (string)
│
├── Workflow 1
│   ├── wf1_status (idle|analyzing|completed|failed)
│   ├── wf1_results (dict or None)
│   ├── wf1_error (string or None)
│   └── wf1_last_analyzed (datetime)
│
├── Workflow 2
│   ├── wf2_status (idle|waiting|running|logs_received|analyzing|completed|failed|unavailable)
│   ├── wf2_runs (list of run objects)
│   ├── wf2_results (dict or None)
│   ├── wf2_error (string or None)
│   ├── wf2_last_refresh (datetime)
│   └── wf2_selected_run (run_id or None)
│
└── Configuration
    ├── auto_refresh_enabled (bool)
    └── auto_refresh_interval (int seconds)
```

## Component Hierarchy

```
src/
├── ui/
│   ├── layout.py
│   │   └── render_main_layout()
│   │       ├── render_sidebar()
│   │       ├── render_input_section()
│   │       ├── render_workflow1()
│   │       │   └── render_wf1_results()
│   │       ├── render_workflow2()
│   │       │   ├── render_wf2_runs()
│   │       │   └── render_run_details()
│   │       └── Footer
│   │
│   ├── input_section.py
│   │   └── render_input_section()
│   │       ├── GitHub Repository Input
│   │       ├── Commit SHA Input
│   │       └── Validation Indicator
│   │
│   ├── workflow1.py
│   │   ├── render_workflow1()
│   │   │   ├── Status Display
│   │   │   ├── [Analyze Commit] Button
│   │   │   └── Result Display (conditional)
│   │   └── render_wf1_results()
│   │       ├── Failure Probability Metric
│   │       ├── SHAP Explanations
│   │       ├── Suspicious Files
│   │       ├── Graph Relationships
│   │       └── RCA Findings
│   │
│   ├── workflow2.py
│   │   ├── render_workflow2()
│   │   │   ├── Status Display
│   │   │   ├── [Fetch CI Runs] Button
│   │   │   ├── Auto-refresh Toggle
│   │   │   └── Result Display (conditional)
│   │   ├── render_wf2_runs()
│   │   │   └── Multiple Run Tabs
│   │   └── render_run_details()
│   │       ├── Run Header (name, id, status)
│   │       ├── Logs Info (lines, errors)
│   │       ├── Error Explanation
│   │       ├── RCA Results
│   │       └── Remediation Suggestions
│   │
│   └── sidebar.py
│       └── render_sidebar()
│           ├── Backend Configuration
│           ├── Backend Status
│           ├── Auto-refresh Settings
│           └── Documentation
│
└── state/
    └── session.py
        ├── initialize_session_state()
        ├── get_wf1_status_display()
        ├── get_wf2_status_display()
        ├── reset_wf1_state()
        └── reset_wf2_state()
```

## State Diagram: Workflow 1

```
                    ┌─────────────────┐
                    │     IDLE        │
                    │ (No Input Valid)│
                    └────────┬────────┘
                             │
                             │ User enters valid input
                             ↓
                    ┌─────────────────┐
                    │  WAITING INPUT  │
                    │ (Ready to click) │
                    └────────┬────────┘
                             │
                             │ User clicks "Analyze Commit"
                             ↓
                    ┌─────────────────┐
                    │   ANALYZING     │
                    │  (ORC running)  │
                    └────────┬────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
           Success                   Error
                │                         │
                ↓                         ↓
        ┌──────────────┐         ┌──────────────┐
        │  COMPLETED   │         │    FAILED    │
        │ (Show results)         │ (Error msg)  │
        └──────┬───────┘         └──────┬───────┘
               │                        │
               │ User changes input     │ User clicks "Retry"
               │ or clicks "Reset"      │
               ↓                        ↓
        ┌─────────────────┐        ┌──────────────┐
        │ Back to IDLE    │        │   ANALYZING  │
        └─────────────────┘        └──────────────┘
```

## State Diagram: Workflow 2

```
                    ┌──────────────────┐
                    │      IDLE        │
                    │  (No CI runs)    │
                    └────────┬─────────┘
                             │
                   User clicks "Fetch CI Runs"
                             │
                             ↓
                    ┌──────────────────┐
                    │     WAITING      │
                    │  (No runs yet)   │
                    └────────┬─────────┘
                             │
                             │ GitHub Actions workflow detected
                             ↓
                    ┌──────────────────┐
                    │     RUNNING      │
                    │  (Workflow in    │
                    │   progress)      │
                    └────────┬─────────┘
                             │
                             │ Logs received by Log Pipeline
                             ↓
                    ┌──────────────────┐
                    │  LOGS_RECEIVED   │
                    │  (Processing)    │
                    └────────┬─────────┘
                             │
                             │ Analysis started
                             ↓
                    ┌──────────────────┐
                    │    ANALYZING     │
                    │  (Backend work)  │
                    └────────┬─────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
           Success                   Workflow Failed
                │                         │
                ↓                         ↓
        ┌──────────────┐         ┌──────────────┐
        │  COMPLETED   │         │    FAILED    │
        │(Show results)│         │ (Show reason)│
        └──────────────┘         └──────────────┘
                │                         │
                │ Auto-refresh every N sec│
                └────────────┬────────────┘
                             │
                             ↓
                    ┌──────────────────┐
                    │   UNAVAILABLE    │
                    │ (Backend down)   │
                    └──────────────────┘

Note: Auto-refresh mechanism continuously polls for updates
      while workflow is in WAITING, RUNNING, or ANALYZING states
```

## Key Design Principles

### 1. Single Input Section
- Both workflows use the same GitHub repository and commit SHA
- User enters this information once
- Both workflows operate on the same input data
- Input validation ensures both workflows have valid data

### 2. Complete Separation
- ORC project remains unchanged
- Metadata-Pipeline remains unchanged
- graph-doc-gen remains unchanged
- Log Pipeline remains unchanged
- Dashboard is a UI layer only

### 3. No Mock Data
- All results come from actual backend analysis
- No fabricated or test data in production
- Dashboard reads data, never writes to backends
- No modifications to GitHub Actions workflows

### 4. Professional UX
- Clear status indicators
- Structured result display
- Tab-based navigation for multiple runs
- Intuitive workflow layout
- Configurable auto-refresh

### 5. Robust Error Handling
- Graceful degradation
- Clear error messages
- Retry mechanisms
- Backend unavailability indicators
- Timeout handling

## Security Considerations

1. **Read-Only Access**
   - Dashboard only reads from backends
   - No credentials needed beyond what backends provide
   - No sensitive data stored in UI

2. **Input Validation**
   - Repository format validation (owner/repo)
   - SHA format validation (7+ characters)
   - Prevents injection attacks

3. **Backend Communication**
   - All calls through standard HTTPS/HTTP
   - Respects backend authentication if present
   - No sensitive data exposed in URLs

4. **Session State**
   - Stored locally in browser
   - Cleared when browser session ends
   - No data sent to third parties

## Performance Considerations

1. **Polling Strategy**
   - Workflow 1: Quick response expected (ORC handles analysis)
   - Workflow 2: Auto-refresh with configurable interval (5-60 seconds)

2. **Caching**
   - Results cached in session state
   - Prevents redundant API calls
   - Clear when inputs change

3. **UI Responsiveness**
   - Async operations with spinners
   - Status updates without full page reload
   - Efficient component rendering

## Future Enhancement Points

- Export results to PDF/JSON
- Commit comparison across multiple SHAs
- Workflow history and trends
- Team collaboration features
- Custom filtering and search
- Integration with issue/PR systems
- Advanced visualization (graphs, charts)
