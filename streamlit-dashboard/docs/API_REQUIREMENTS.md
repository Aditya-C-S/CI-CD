# Dashboard API Requirements & Investigation Report

## Overview

This document specifies the API endpoints required to integrate the Streamlit dashboard with backend services. The dashboard is designed as a **read-only UI layer** that does not modify backend implementations.

## Workflow 1: ORC + Metadata Prediction + Graph RCA

### Required Endpoints

#### 1. Submit Commit for Analysis
```
POST /api/commits/{repository}/analyze
Content-Type: application/json

{
  "commit_sha": "abc123def456...",
  "visibility": 100  // Optional: 25, 50, 75, 100
}

Response:
{
  "analysis_id": "uuid",
  "status": "submitted",
  "repository": "owner/repo",
  "commit_sha": "abc123...",
  "submitted_at": "2024-01-15T10:30:00Z"
}
```

#### 2. Get Analysis Results
```
GET /api/commits/{repository}/analysis/{commit_sha}?analysis_id={analysis_id}

Response:
{
  "status": "completed",
  "failure_probability": 0.72,
  "risk_level": "HIGH",
  "probability_change": "+5%",
  
  "shap_explanations": [
    {
      "name": "test_coverage_percentage",
      "contribution": 0.25,
      "direction": "positive",
      "value": 45
    },
    ...
  ],
  
  "suspicious_files": [
    {
      "path": "src/payment_service.py",
      "score": 0.89,
      "type": "Python",
      "lines_changed": 127,
      "reason": "High risk patterns detected in transaction handling"
    },
    ...
  ],
  
  "graph_relationships": {
    "total_nodes": 237,
    "total_edges": 636,
    "blast_radius": 45,
    "critical_paths": [...]
  },
  
  "rca_findings": {
    "primary_cause": "Race condition in concurrent payment processing",
    "contributing_factors": [
      "Missing mutex lock in transaction handler",
      "Inadequate test coverage for concurrent scenarios",
      "Insufficient error handling for timeout cases"
    ],
    "remediation": "Add mutex synchronization and improve concurrent test suite"
  },
  
  "analyzed_at": "2024-01-15T10:35:22Z"
}
```

### Status: Investigation Needed

**Questions for ORC/Metadata-Pipeline team:**

1. What is the current API endpoint format for submitting commits?
2. How are analysis results retrieved? (polling vs. callback)
3. What format are SHAP explanations in?
4. How is the graph-doc-gen integrated into the API response?
5. What is the typical analysis duration?
6. Are there rate limits or concurrent analysis limits?

---

## Workflow 2: Automatic CI Log Analysis

### Required Endpoints

#### 1. Get CI Runs by Repository and Commit SHA
```
GET /api/demo/runs?repository=owner/repo&commit_sha=abc123&limit=20

Response:
{
  "total": 3,
  "runs": [
    {
      "run_id": "12345",
      "workflow_name": "CI - Python Tests",
      "workflow_id": "build.yml",
      "status": "failure",
      "attempt_number": 2,
      "triggered_at": "2024-01-15T10:30:00Z",
      "duration": "5m 23s",
      "logs_collected": true,
      "analysis_status": "completed"
    },
    {
      "run_id": "12344",
      "workflow_name": "CI - Integration Tests",
      "workflow_id": "integration.yml",
      "status": "success",
      "attempt_number": 1,
      "triggered_at": "2024-01-15T09:45:00Z",
      "duration": "12m 15s",
      "logs_collected": true,
      "analysis_status": "completed"
    },
    {
      "run_id": "12343",
      "workflow_name": "CI - Security Scan",
      "workflow_id": "security.yml",
      "status": "running",
      "attempt_number": 1,
      "triggered_at": "2024-01-15T10:15:00Z",
      "duration": null,
      "logs_collected": false,
      "analysis_status": "waiting"
    }
  ]
}
```

**Current Status:** Endpoint exists at `/api/demo/runs?limit=N` but may not support filtering by `repository` and `commit_sha`. **Need to verify.**

#### 2. Get Run Status and Logs Info
```
GET /api/demo/runs/{run_id}/status

Response:
{
  "run_id": "12345",
  "status": "completed",
  "logs_collected": true,
  "logs_info": {
    "total_lines": 1524,
    "error_lines": 47,
    "warning_lines": 89,
    "classification": "Database Connection Failure",
    "ingestion_timestamp": "2024-01-15T10:35:00Z"
  },
  "analysis_progress": {
    "stage": "completed",
    "percentage": 100,
    "message": "Analysis complete"
  }
}
```

**Current Status:** May not exist or may return different structure. **Need to verify.**

#### 3. Get Run Analysis Results
```
GET /api/demo/runs/{run_id}/analysis

Response:
{
  "run_id": "12345",
  "status": "completed",
  
  "error_explanation": {
    "summary": "PostgreSQL connection timeout after 30 seconds",
    "error_patterns": [
      "FATAL: connection timeout",
      "Unable to connect to database server",
      "Retried 3 times without success"
    ],
    "failure_type": "infrastructure",
    "root_indicators": ["network", "database", "configuration"]
  },
  
  "rca_results": {
    "root_cause": "Database server down for maintenance during deployment",
    "contributing_factors": [
      "No health check before running integration tests",
      "Retry logic expired after 30 seconds",
      "No circuit breaker pattern implemented"
    ],
    "affected_services": ["database", "api_gateway"],
    "timeline": [
      {
        "time": "2024-01-15T10:30:00Z",
        "event": "DB maintenance started (unscheduled)"
      },
      {
        "time": "2024-01-15T10:31:15Z",
        "event": "CI workflow triggered"
      },
      {
        "time": "2024-01-15T10:31:20Z",
        "event": "First connection attempt failed"
      }
    ]
  },
  
  "remediation_suggestions": [
    {
      "title": "Implement health checks before running tests",
      "priority": "HIGH",
      "description": "Add a pre-test health check that verifies database connectivity",
      "steps": [
        "Create a health_check.py script",
        "Run it before integration tests",
        "Skip tests if health check fails"
      ],
      "estimated_time": "2 hours"
    },
    {
      "title": "Implement exponential backoff with jitter",
      "priority": "MEDIUM",
      "description": "Improve retry mechanism to handle temporary outages",
      "steps": [
        "Install retry library: pip install tenacity",
        "Update database connection function",
        "Add exponential backoff decorator"
      ],
      "estimated_time": "1 hour"
    },
    {
      "title": "Coordinate deployment schedules",
      "priority": "MEDIUM",
      "description": "Ensure CI workflows don't run during maintenance windows",
      "steps": [
        "Document maintenance windows",
        "Disable CI during maintenance",
        "Add automated alerts"
      ],
      "estimated_time": "1 hour"
    }
  ],
  
  "analyzed_at": "2024-01-15T10:36:00Z"
}
```

**Current Status:** Unknown if this endpoint exists. **Need to verify.**

#### 4. Poll for New Results (Optional)
```
GET /api/demo/runs/{run_id}/analysis?include_progress=true

Response: Same as above but with added:
{
  "analysis_progress": {
    "stage": "analyzing",
    "percentage": 65,
    "message": "Processing error patterns..."
  }
}
```

**Current Status:** Unknown. **Need to verify.**

---

## Current Log Pipeline Endpoints

### Verified Working

#### Get All Runs (with Limit)
```
GET /api/demo/runs?limit=15
Response: List of recent runs with details
```

✅ **Status: WORKING** (Used in dashboard)

#### Get Run Details
```
GET /api/demo/runs/{run_id}
Response: Detailed run information
```

✅ **Status: WORKING**

#### Get Run Summary
```
GET /api/summaries?limit=10
Response: Recent summaries
```

✅ **Status: WORKING**

---

## API Integration Gaps

### Gap 1: Filter Runs by Repository and Commit SHA

**Current Limitation:**
- `/api/demo/runs?limit=N` returns all recent runs
- No filtering by repository or commit_sha
- Dashboard must iterate through all runs to find matches (inefficient)

**Needed:**
- `/api/demo/runs?repository=owner/repo&commit_sha=abc123&limit=20`
- Or modify existing endpoint to accept these filters

**Priority:** HIGH

---

### Gap 2: Run Analysis Results Endpoint

**Current Limitation:**
- Analysis results may only be available in demo summaries
- No dedicated endpoint for detailed analysis per run_id

**Needed:**
- `/api/demo/runs/{run_id}/analysis` endpoint
- Or verify where analysis results are stored and how to access them

**Priority:** HIGH

---

### Gap 3: Run Status and Progress

**Current Limitation:**
- Unknown if dashboard can detect when logs are being collected vs. analyzed
- Unknown how to implement auto-refresh for Workflow 2

**Needed:**
- Clear status values: "waiting", "running", "logs_received", "analyzing", "completed", "failed"
- Progress indicator for long-running analysis
- Timestamp for when logs were ingested

**Priority:** MEDIUM

---

## Workflow 1 API Integration Gaps

### Gap 1: ORC Endpoint Availability

**Question:** What is the ORC API base URL and endpoint format?

**Expected Format:**
```
POST /api/analyze-commit
POST /api/commits/analyze
POST /api/orc/analyze
```

**Needed:** Documentation of ORC API endpoints

**Priority:** CRITICAL

---

### Gap 2: Metadata-Pipeline Integration

**Question:** How are Metadata-Pipeline results exposed via ORC API?

**Current Implementation:** Direct Python imports in existing backends

**Needed:** ORC should expose endpoints that return:
- Failure probability (0-1)
- Feature importance (SHAP values)
- Risk classification (HIGH, MEDIUM, LOW)

**Priority:** CRITICAL

---

### Gap 3: Graph-doc-gen Integration

**Question:** How are graph relationships included in analysis?

**Expected:** Blast radius, relationship counts, critical paths

**Priority:** CRITICAL

---

## Implementation Recommendation

### Phase 1: Investigate Current State
1. Query `/api/demo/runs?limit=100` and inspect structure
2. Query `/api/demo/runs/{run_id}` for a specific run
3. Check if run object contains analysis results
4. Verify ORC API documentation and endpoints
5. Verify if graph-doc-gen is exposed via ORC

### Phase 2: Design Missing Endpoints
If gaps exist:
1. Design `/api/demo/runs?repository=X&commit_sha=Y` endpoint
2. Design `/api/demo/runs/{run_id}/analysis` endpoint
3. Verify ORC API structure for Workflow 1
4. Get timeline for ORC/Metadata-Pipeline integration

### Phase 3: Implement Dashboard Integration
Once endpoints are verified:
1. Implement Workflow 2 backend calls
2. Implement Workflow 1 backend calls
3. Add error handling and retry logic
4. Implement auto-refresh mechanism
5. Add comprehensive testing

---

## Notes

- This dashboard uses **existing APIs only** - no modifications to backend implementations
- GitHub Actions log forwarding is unchanged
- All results must come from real backend analysis
- No mock data or fabricated results
- Dashboard is a read-only UI layer
