# ✅ Setup Checklist & Configuration Guide

Use this checklist to ensure everything is properly configured before running the project.

---

## 🔍 Pre-Installation Checklist

- [ ] **Python 3.8+** installed
  ```bash
  python --version  # Should show 3.8 or higher
  ```

- [ ] **Git** installed
  ```bash
  git --version
  ```

- [ ] **All project directories present**
  ```
  ✓ streamlit-dashboard/
  ✓ orc/
  ✓ logpipeline/
  ✓ Metadata-Pipeline-main/
  ✓ graph-doc-gen-main/
  ```

- [ ] **GitHub account and internet access**

- [ ] **~500MB free disk space** (minimum)

---

## 📋 Installation Checklist

### Step 1: Virtual Environment

- [ ] Navigate to streamlit-dashboard directory
  ```bash
  cd streamlit-dashboard
  ```

- [ ] Created virtual environment
  ```bash
  python -m venv venv
  ```

- [ ] Virtual environment activated
  ```bash
  # Windows:
  venv\Scripts\activate
  # macOS/Linux:
  source venv/bin/activate
  ```

- [ ] Confirmed activation (prompt shows `(venv)`)

### Step 2: Dependencies

- [ ] Installed streamlit-dashboard requirements
  ```bash
  pip install -r requirements.txt
  ```

- [ ] Installed ORC requirements
  ```bash
  cd ../orc
  pip install -r requirements.txt
  ```

- [ ] Installed logpipeline requirements
  ```bash
  cd ../logpipeline
  pip install -r requirements.txt
  ```

- [ ] Installed graph-doc-gen requirements (optional)
  ```bash
  cd ../graph-doc-gen-main
  pip install -r requirements.txt
  ```

- [ ] **Verified no installation errors** (no red ERROR messages)

### Step 3: GitHub Token

- [ ] Created GitHub Personal Access Token
  - [ ] Visited https://github.com/settings/tokens
  - [ ] Clicked "Generate new token"
  - [ ] Selected scopes: `repo`, `read:org`
  - [ ] Copied token (40+ character string starting with `ghp_`)

- [ ] **Saved token securely** (don't share or commit!)

### Step 4: Environment Files

- [ ] Created `streamlit-dashboard/.env`
  ```env
  GITHUB_TOKEN=ghp_xxxxxxxxxxxx
  ORC_API_URL=http://localhost:8000
  LOG_PIPELINE_API_URL=http://localhost:8001
  NEO4J_URI=bolt://localhost:7687
  NEO4J_USER=neo4j
  NEO4J_PASSWORD=password
  ```

- [ ] Created `orc/.env`
  ```env
  GITHUB_TOKEN=ghp_xxxxxxxxxxxx
  NEO4J_URI=bolt://localhost:7687
  NEO4J_USER=neo4j
  NEO4J_PASSWORD=password
  ```

- [ ] Created `logpipeline/.env` (if needed)
  ```env
  GITHUB_TOKEN=ghp_xxxxxxxxxxxx
  ```

- [ ] **Verified no typos in tokens**

- [ ] **Added .env files to .gitignore** (never commit credentials!)

---

## 🗄️ Database Setup (Optional but Recommended)

### Option A: Docker

- [ ] **Docker installed**
  ```bash
  docker --version  # Should show version
  ```

- [ ] **Started Neo4j container**
  ```bash
  docker run -d \
    -p 7687:7687 \
    -p 7474:7474 \
    -e NEO4J_AUTH=neo4j/password \
    neo4j:5.15
  ```

- [ ] **Neo4j accessible**
  ```bash
  curl http://localhost:7474  # Should return HTML
  ```

- [ ] **Updated .env with Neo4j credentials**
  ```env
  NEO4J_URI=bolt://localhost:7687
  NEO4J_USER=neo4j
  NEO4J_PASSWORD=password
  ```

### Option B: Local Neo4j Installation

- [ ] **Downloaded Neo4j** from https://neo4j.com/download/
- [ ] **Installed** according to platform instructions
- [ ] **Started Neo4j service**
  - [ ] macOS: `brew services start neo4j`
  - [ ] Linux: `sudo systemctl start neo4j`
  - [ ] Windows: `net start Neo4j`
- [ ] **Accessed Neo4j Browser** at http://localhost:7474
- [ ] **Updated .env** with correct URI and credentials

### Skip Option (No Neo4j)

- [ ] Acknowledged that graph features won't work
- [ ] Dashboard and log analysis will still work
- [ ] Can add Neo4j later

---

## ▶️ Running the Project Checklist

### Minimal Setup (Dashboard Only)

- [ ] Opened terminal in `streamlit-dashboard/`
- [ ] Activated virtual environment
  ```bash
  venv\Scripts\activate  # Windows
  source venv/bin/activate  # macOS/Linux
  ```
- [ ] Confirmed `(venv)` in prompt
- [ ] Started dashboard
  ```bash
  streamlit run app.py
  ```
- [ ] Browser opened to http://localhost:8501
- [ ] Dashboard shows input fields for repo + SHA

### Full Setup (All Services)

#### Terminal 1: Neo4j
- [ ] Started Neo4j
  ```bash
  docker run -d -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5.15
  # OR local installation
  ```
- [ ] Verified running: `curl http://localhost:7474`

#### Terminal 2: Log Pipeline
- [ ] Navigated to `logpipeline/`
- [ ] Activated virtual environment
- [ ] Started API
  ```bash
  python -m uvicorn src.api.main:app --port 8001 --reload
  ```
- [ ] Verified running: `curl http://localhost:8001/health`

#### Terminal 3: ORC (Optional)
- [ ] Navigated to `orc/`
- [ ] Activated virtual environment
- [ ] Started backend
  ```bash
  python -m orchestrator.py
  ```

#### Terminal 4: Dashboard
- [ ] Navigated to `streamlit-dashboard/`
- [ ] Activated virtual environment
- [ ] Started dashboard
  ```bash
  streamlit run app.py
  ```
- [ ] Confirmed all services running:
  ```
  ✓ Streamlit: http://localhost:8501
  ✓ Log Pipeline: http://localhost:8001
  ✓ ORC: http://localhost:8000
  ✓ Neo4j: http://localhost:7474
  ```

---

## 🧪 Functionality Testing Checklist

### Dashboard Loads

- [ ] Dashboard accessible at http://localhost:8501
- [ ] Page title shows "🚀 CI/CD Failure Predictor & RCA"
- [ ] Input fields visible for repo + SHA
- [ ] Sidebar shows workflow options

### Input Validation

- [ ] **Invalid repo format rejected**
  - [ ] Tried: `invalid-repo` (no slash)
  - [ ] Got: warning message
  
- [ ] **Invalid SHA rejected**
  - [ ] Tried: `abc` (too short)
  - [ ] Got: warning message

- [ ] **Valid input accepted**
  - [ ] Entered: `owner/repo` + `abc1234567890`
  - [ ] Got: green checkmark

### Workflow 1: Metadata + Graph

- [ ] [ ] Can navigate to "Metadata + Graph RCA" page
- [ ] [ ] "Analyze Commit" button visible
- [ ] [ ] Button clickable (not disabled)
- [ ] [ ] **Note**: Backend implementation may be pending

### Workflow 2: Log Analysis

- [ ] Can navigate to "Log Analysis" page
- [ ] "Fetch CI Runs" button visible
- [ ] Status indicator shows initial state
- [ ] **Note**: Backend implementation may be pending

---

## 🔧 Configuration Verification Checklist

### Environment Variables

- [ ] `GITHUB_TOKEN` is set and valid
  ```bash
  # Test: should return user info (not 401 Unauthorized)
  curl -H "Authorization: token $GITHUB_TOKEN" \
       https://api.github.com/user
  ```

- [ ] `ORC_API_URL` points to correct host:port
  ```bash
  curl http://localhost:8000/health  # if running
  ```

- [ ] `LOG_PIPELINE_API_URL` points to correct host:port
  ```bash
  curl http://localhost:8001/health  # if running
  ```

- [ ] `NEO4J_URI` format is correct
  ```
  ✓ bolt://localhost:7687  (correct)
  ✗ http://localhost:7474  (wrong port)
  ```

### API Health

- [ ] Neo4j responding
  ```bash
  curl http://localhost:7474 -u neo4j:password
  ```

- [ ] Log Pipeline responding
  ```bash
  curl http://localhost:8001/health
  ```

- [ ] ORC responding (if running)
  ```bash
  curl http://localhost:8000/health
  ```

---

## 🚨 Troubleshooting Checklist

### Issue: "ModuleNotFoundError: No module named 'streamlit'"

- [ ] Virtual environment activated? (check `(venv)` in prompt)
- [ ] Dependencies installed? (`pip list | grep streamlit`)
- [ ] Installed in correct directory? (inside `streamlit-dashboard/`)
- [ ] **Fix**: 
  ```bash
  source venv/bin/activate
  pip install -r requirements.txt
  ```

### Issue: "FileNotFoundError: .env file not found"

- [ ] `.env` file exists in `streamlit-dashboard/`?
- [ ] File named exactly `.env` (not `.env.example` or `.env.txt`)?
- [ ] File contains `GITHUB_TOKEN=`?
- [ ] **Fix**:
  ```bash
  cp .env.example .env
  # Edit .env and add real token
  ```

### Issue: "GITHUB_TOKEN not found or invalid"

- [ ] Token exists in `.env`?
- [ ] Token starts with `ghp_` (GitHub personal token)?
- [ ] Token hasn't expired?
- [ ] **Fix**:
  ```bash
  # Generate new token: https://github.com/settings/tokens
  # Add to .env: GITHUB_TOKEN=ghp_xxxxxxxxxxxx
  ```

### Issue: "Connection refused: localhost:8001"

- [ ] Log Pipeline service running?
- [ ] Correct port in `.env` (8001)?
- [ ] No firewall blocking port?
- [ ] **Fix**:
  ```bash
  cd logpipeline
  python -m uvicorn src.api.main:app --port 8001 --reload
  ```

### Issue: "Port 8501 already in use"

- [ ] Check what's using port 8501
  ```bash
  # Windows:
  netstat -ano | findstr :8501
  # macOS/Linux:
  lsof -i :8501
  ```
- [ ] Use different port
  ```bash
  streamlit run app.py --server.port=8502
  ```

### Issue: "Neo4j connection refused"

- [ ] Neo4j running?
  ```bash
  docker ps | grep neo4j
  ```
- [ ] Correct port in `.env` (7687)?
- [ ] Correct credentials (default: neo4j/password)?
- [ ] **Fix**:
  ```bash
  docker run -d -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5.15
  ```

---

## 📊 Final Verification Checklist

Before declaring setup complete:

- [ ] **All dependencies installed** (no errors)
  ```bash
  pip list | head -20
  ```

- [ ] **All .env files created** with valid tokens

- [ ] **Dashboard starts without errors**
  ```bash
  streamlit run app.py
  # Should show: You can now view your Streamlit app...
  ```

- [ ] **Dashboard accessible in browser**
  ```
  http://localhost:8501
  ```

- [ ] **Input fields functional** (can type in them)

- [ ] **Navigation between workflows works**

- [ ] **All required services running** (if doing full setup)
  ```bash
  curl http://localhost:8501  # Dashboard
  curl http://localhost:8001  # Log Pipeline
  curl http://localhost:7474  # Neo4j (optional)
  ```

---

## 🎉 Setup Complete!

If all checkboxes are checked ✅, your project is ready!

### Next Steps:

1. **Try analyzing a real commit**:
   - Enter: `torvalds/linux`
   - Enter: Any recent commit SHA
   - Click "Analyze Commit"

2. **Test log analysis**:
   - Enter: Your own repo (with GitHub Actions)
   - Enter: A recent commit SHA
   - Click "Fetch CI Runs"

3. **Read full documentation**:
   - See `README.md` in artifacts
   - Explore API docs in each component

---

## 📝 Notes for Future Reference

- **GitHub Token expires after**: 1 year (regenerate annually)
- **Docker Neo4j default password**: `password` (change in production)
- **Database size**: Grows with each repo analyzed (~50KB per repo)
- **Cache location**: `.graph_cache/` (in ORC directory)
- **Logs location**: Check terminal output (configurable)

---

**Setup Last Completed**: _______________  
**Completed By**: _______________  
**Date**: _______________

---

**Questions?** Check README.md or run `streamlit run app.py --help`
