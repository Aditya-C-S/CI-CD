# Dashboard Startup Instructions

## Quick Start

1. **Ensure no previous Uvicorn processes are running:**
   ```powershell
   # Kill any existing Python processes on port 8000
   Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { 
       Stop-Process -Id $_.OwningProcess -Force 
   }
   Start-Sleep -Seconds 2
   ```

2. **Start Uvicorn (no --reload flag):**
   ```powershell
   cd c:\Users\DHRUV HEGDE\Desktop\finaltest\logpipeline
   python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
   ```

3. **Open the dashboard:**
   - Navigate to `http://127.0.0.1:8000/` in your browser
   - You should see "System Status: **HEALTHY**" with Neo4j "ONLINE"

## Why --reload is NOT recommended

Using `python -m uvicorn src.api.main:app --reload` can cause issues because:
- When changes are detected, Uvicorn restarts the process
- During restart, a previous instance might still be bound to the port
- This causes socket binding errors that interrupt startup
- The application shuts down prematurely before fully initializing
- Result: Neo4j shows as OFFLINE with misleading error messages

## Troubleshooting

### If Neo4j shows OFFLINE:

1. **Check that no stale processes are using port 8000:**
   ```powershell
   Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
   ```

2. **If something is using port 8000, kill it:**
   ```powershell
   Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { 
       Stop-Process -Id $_.OwningProcess -Force 
   }
   ```

3. **Verify .env files exist with proper credentials:**
   - `c:\Users\DHRUV HEGDE\Desktop\graph-doc-gen-main\.env` (source)
   - `c:\Users\DHRUV HEGDE\Desktop\finaltest\logpipeline\.env` (local)

4. **Run the diagnostic script:**
   ```powershell
   cd c:\Users\DHRUV HEGDE\Desktop\finaltest\logpipeline
   python diagnose_offline.py
   ```
   This will verify:
   - Environment variables are loaded correctly
   - Neo4j database is accessible
   - Connection works end-to-end

## Environment Loading Order

The application loads credentials in this order:
1. `graph-doc-gen-main/.env` (contains `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`)
2. `logpipeline/.env` (can override other settings, but not Neo4j credentials)

This ensures the real Neo4j database credentials take precedence over any local test values.

## Architecture Overview

```
Frontend (http://127.0.0.1:8000/) 
    ↓
    → /api/metadata/graph/status (graph statistics)
    → /api/health/system (system diagnostics)
    ↓
FastAPI Backend (Uvicorn)
    ↓
Neo4j Database (bolt://localhost:7687)
    ↓
Knowledge graph with 237 nodes, 636 edges
```

All subsystems should show HEALTHY when properly started.
