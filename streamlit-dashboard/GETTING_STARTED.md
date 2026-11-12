# Getting Started Checklist

## ✅ Phase 1: Project Setup (5 minutes)

- [ ] Navigate to project directory:
  ```bash
  cd C:\Users\DHRUV HEGDE\Desktop\finaltest\streamlit-dashboard
  ```

- [ ] Create Python virtual environment (recommended):
  ```bash
  python -m venv venv
  venv\Scripts\activate  # Windows
  ```

- [ ] Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```

- [ ] Verify installation:
  ```bash
  python -c "import streamlit; print(streamlit.__version__)"
  ```

## ✅ Phase 2: Run Dashboard (2 minutes)

- [ ] Start Streamlit app:
  ```bash
  streamlit run app.py
  ```

- [ ] Open browser to: `http://localhost:8501`

- [ ] Verify dashboard loads with:
  - Header: "CI/CD Failure Predictor & Graph RCA"
  - Single input section for GitHub repo + commit SHA
  - Two workflow panels side-by-side
  - Sidebar with configuration

## ✅ Phase 3: Test UI (10 minutes)

- [ ] Test input validation:
  - Enter `owner/repo` in repository field
  - Enter full or short commit SHA (7+ chars)
  - Observe "✅ Ready" indicator
  - Try invalid inputs and observe warnings

- [ ] Test Workflow 1:
  - Click "🔍 Analyze Commit" button
  - Observe spinner (placeholder)
  - Click "🔄 Reset" button
  - Verify state resets

- [ ] Test Workflow 2:
  - Click "🔄 Fetch CI Runs" button
  - Observe status change
  - Check auto-refresh toggle
  - Click "🔄 Reset" button

- [ ] Test sidebar:
  - Review backend configuration
  - Adjust auto-refresh interval slider
  - Read documentation

## ⏳ Phase 4: API Integration (Planning)

### Option A: Quick Investigation (Recommended First)

**Check Log Pipeline API:**
```bash
# From a terminal, query existing endpoints
curl http://127.0.0.1:8000/api/demo/runs?limit=5

# Check if filtering works
curl "http://127.0.0.1:8000/api/demo/runs?repository=owner/repo&commit_sha=abc123"
```

**Check response structure** - Note which fields are available

### Option B: Deep Investigation

**Review Documentation:**
- [ ] Read `docs/API_REQUIREMENTS.md` - Lists all required endpoints
- [ ] Read `docs/ARCHITECTURE.md` - Understand system design
- [ ] Review Log Pipeline implementation at: `logpipeline/src/api/`

**Document Findings:**
- [ ] What Log Pipeline endpoints exist?
- [ ] Do they support filtering by repository + commit_sha?
- [ ] What is the exact response format?
- [ ] Is there analysis results endpoint for each run?

**Document ORC API:**
- [ ] Where is ORC located?
- [ ] What endpoints are available?
- [ ] How to submit commits?
- [ ] What format are responses?

## 📝 Phase 5: Implement Backend Integration (Future)

### Step 1: Create API Client Module
Create `src/api/client.py`:
```python
# Workflow 1: ORC Client
class ORCClient:
    def analyze_commit(self, repo, sha):
        # Call ORC API
        
    def get_results(self, analysis_id):
        # Poll for results

# Workflow 2: Log Pipeline Client
class LogPipelineClient:
    def get_runs(self, repo, sha):
        # Get CI runs for commit
        
    def get_run_analysis(self, run_id):
        # Get analysis results
```

### Step 2: Add Error Handling
Create `src/api/errors.py`:
```python
class APIConnectionError:
    pass

class AnalysisTimeoutError:
    pass

class RunNotFoundError:
    pass
```

### Step 3: Implement Backend Calls
- [ ] Replace placeholders in `src/ui/workflow1.py`
- [ ] Replace placeholders in `src/ui/workflow2.py`
- [ ] Add auto-refresh logic to session state
- [ ] Add comprehensive error handling

### Step 4: Test Integration
- [ ] Test with real commits
- [ ] Test error scenarios
- [ ] Test auto-refresh
- [ ] Test timeout handling

## 🐛 Debugging

### Dashboard Won't Start
```bash
# Check Python version
python --version  # Should be 3.8+

# Check dependencies
pip list | grep streamlit  # Should show 1.32.0+

# Run with debug
streamlit run app.py --logger.level=debug
```

### Components Not Displaying
```bash
# Clear Streamlit cache
rm -r ~/.streamlit/cache_*  # macOS/Linux
rmdir /s %USERPROFILE%\.streamlit\cache_*  # Windows

# Restart dashboard
streamlit run app.py
```

### Backend Connection Issues
```bash
# Test Log Pipeline
curl -v http://127.0.0.1:8000/api/health/system

# Test ORC (when available)
curl -v http://127.0.0.1:8001/api/status
```

## 📚 Documentation Quick Links

| Document | Purpose | When to Read |
|----------|---------|-------------|
| `README.md` | Setup, features, overview | First time setup |
| `ARCHITECTURE.md` | System design, data flow, diagrams | Before implementation |
| `API_REQUIREMENTS.md` | API spec, missing endpoints | Before API integration |
| `GETTING_STARTED.md` | This file - quick checklist | Right now! |

## 💡 Tips & Tricks

### Viewing Raw JSON Responses (Future)
```python
# In workflow files, add this to see API responses:
st.json(results)  # Shows raw JSON for debugging
```

### Running Multiple Instances
```bash
# Streamlit instance 1 (default port 8501)
streamlit run app.py

# Streamlit instance 2 (custom port)
streamlit run app.py --server.port 8502
```

### Clearing Session State
```python
# Reset button is in UI, but you can manually do:
for key in st.session_state:
    del st.session_state[key]
```

## 🎯 Success Criteria

### Phase 1: UI Complete ✅
- [ ] Dashboard loads without errors
- [ ] All components display correctly
- [ ] Input validation works
- [ ] All buttons respond to clicks
- [ ] Status indicators change appropriately

### Phase 2: API Integration 🚧
- [ ] Workflow 1 calls ORC and displays results
- [ ] Workflow 2 fetches runs from Log Pipeline
- [ ] Auto-refresh works for Workflow 2
- [ ] Error messages are clear and helpful
- [ ] Timeouts are handled gracefully

### Phase 3: Production Ready 🔜
- [ ] E2E tests pass
- [ ] Performance is acceptable
- [ ] Error scenarios handled
- [ ] Documentation is complete
- [ ] Team is trained on usage

## 🆘 Getting Help

1. **UI Issues**: Check component state in sidebar
2. **API Issues**: Review `docs/API_REQUIREMENTS.md`
3. **Architecture Questions**: See `docs/ARCHITECTURE.md`
4. **Setup Problems**: Follow Phase 1 checklist again

## 🎉 You're Ready!

The dashboard is installed and ready to go. Next steps:

1. Run the dashboard: `streamlit run app.py`
2. Explore the UI: Try all buttons and inputs
3. Review API documentation: `docs/API_REQUIREMENTS.md`
4. Plan backend integration: `docs/ARCHITECTURE.md`
5. Start implementing: Follow Phase 5 above

Happy analyzing! 🚀
