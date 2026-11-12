# ⚡ QUICKSTART: Get Running in 10 Minutes

**Don't read the full README yet? Start here!**

---

## 🎯 What This Project Does (30 seconds)

This is an AI system that analyzes CI/CD pipeline failures by:
1. **Predicting** whether a GitHub commit will break the build
2. **Analyzing** logs from failed builds
3. **Finding root causes** (syntax errors, missing dependencies, etc.)
4. **Suggesting fixes** with copy-paste terminal commands

---

## ⏱️ 5-Minute Setup

### 1. Prerequisites (Check You Have These)
```bash
# Python 3.8 or higher
python --version

# Git
git --version

# You should have these folders:
# - streamlit-dashboard/
# - orc/
# - logpipeline/
# - Metadata-Pipeline-main/
# - graph-doc-gen-main/
```

### 2. Create Virtual Environment
```bash
cd streamlit-dashboard
python -m venv venv

# Activate it:
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Create .env File
Create `streamlit-dashboard/.env`:
```env
GITHUB_TOKEN=your_token_here
ORC_API_URL=http://localhost:8000
LOG_PIPELINE_API_URL=http://localhost:8001
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

**Need GitHub token?**
1. Go to https://github.com/settings/tokens
2. Click "Generate new token"
3. Copy it into `.env`

### 5. Start Dashboard
```bash
streamlit run app.py
```

✅ **Done!** Dashboard opens at http://localhost:8501

---

## 🏃 Running the Project

### Minimal Setup (Dashboard Only)
```bash
cd streamlit-dashboard
streamlit run app.py
```
Dashboard: http://localhost:8501

### Full Setup (All Services)

**Terminal 1: Neo4j Database**
```bash
docker run -d -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5.15
```

**Terminal 2: Log Pipeline API**
```bash
cd logpipeline
python -m uvicorn src.api.main:app --port 8001 --reload
```

**Terminal 3: Dashboard**
```bash
cd streamlit-dashboard
streamlit run app.py
```

Open: http://localhost:8501

---

## 💡 Using the Dashboard

### Workflow 1: Analyze a Commit
1. Go to dashboard
2. Enter: `owner/repository` (e.g., `torvalds/linux`)
3. Enter: Commit SHA (e.g., `abc1234def5678...`)
4. Click "Analyze Commit"
5. See: Risk score, SHAP explainers, suspicious files

### Workflow 2: Analyze CI Logs
1. Go to "Log Analysis" page
2. Enter same repo + SHA
3. System auto-detects GitHub Actions logs
4. See: Error patterns, RCA, suggested fixes

---

## 📁 Project Structure (Quick Overview)

```
streamlit-dashboard/        ← Main dashboard UI
├── app.py                  ← Start here
├── src/ui/                 ← Dashboard pages
└── requirements.txt        ← Python dependencies

orc/                        ← Commit analysis engine
├── src/adapters/           ← Neo4j integration
└── requirements.txt

logpipeline/                ← ML models + log analysis
├── src/models/             ← BiLSTM, SVM, Logistic Regression
├── src/api/                ← REST API
└── requirements.txt

graph-doc-gen-main/         ← Code graph parsing
├── code_parser/            ← AST parsing
└── database/               ← Neo4j integration

Metadata-Pipeline-main/     ← Commit metadata extraction
```

---

## 🔧 Troubleshooting (Most Common Issues)

### "ModuleNotFoundError: No module named 'streamlit'"
```bash
# Make sure you activated venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux

# Then reinstall
pip install -r requirements.txt
```

### "GITHUB_TOKEN not found"
```bash
# Create .env file in streamlit-dashboard/
# Add: GITHUB_TOKEN=your_token_here
# Get token from: https://github.com/settings/tokens
```

### "Neo4j connection refused"
```bash
# Start Neo4j
docker run -d -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5.15
```

### "Port 8501 already in use"
```bash
# Use different port
streamlit run app.py --server.port=8502
```

---

## 📊 What Happens Behind the Scenes

```
You Enter: owner/repo + commit SHA
           ↓
   Dashboard sends to ORC backend
           ↓
   ┌──────────────────────────────────┐
   │  ORC Analyzes Commit:            │
   │  - Extracts metadata             │
   │  - Runs 3 ML models              │
   │  - Generates SHAP explanations   │
   │  - Syncs Neo4j graph             │
   └──────────────────────────────────┘
           ↓
   ┌──────────────────────────────────┐
   │  Log Pipeline Analyzes Logs:     │
   │  - Fetches from GitHub Actions   │
   │  - Parses error patterns         │
   │  - Runs RCA                      │
   │  - Suggests fixes                │
   └──────────────────────────────────┘
           ↓
   Dashboard displays:
   - Risk score (0-100%)
   - Which features matter (SHAP)
   - Suspicious files
   - Root cause explanation
   - Suggested fixes
```

---

## 🎓 3 Models Explained Simply

| Model | What It Does | Speed | Accuracy |
|-------|---|---|---|
| **Logistic Regression** | Looks for keyword patterns (ERROR, FAILED, etc.) | ⚡ Fast | 70% |
| **SVM** | Looks for complex patterns in text | ⚡⚡ Medium | 80% |
| **BiLSTM** | Deep learning - understands sequence of events | ⚡⚡⚡ Slow | 90% |

**Result**: Average of all 3 = best prediction 🎯

---

## 🚀 Next Steps

1. **Run the dashboard** (see section above)
2. **Try Workflow 1**: Analyze a real GitHub commit
3. **Try Workflow 2**: Check CI logs
4. **Read the full README** for advanced features
5. **Check API docs** in `logpipeline/docs/`

---

## 📚 Quick Command Reference

```bash
# Setup
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt

# Start services
docker run -d -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5.15
python -m uvicorn logpipeline.src.api.main:app --port 8001
streamlit run app.py

# Testing
pytest tests/ -v

# Viewing logs
tail -f streamlit.log
curl http://localhost:8501/health
```

---

## ❓ FAQ

**Q: Do I need Neo4j?**
A: No, it's optional. Dashboard works without it, but graph features won't work.

**Q: Do I need Docker?**
A: Only if you want to run Neo4j. Otherwise, you can skip it.

**Q: Can I run this on Windows/Mac/Linux?**
A: Yes! Everything works on all platforms.

**Q: How long does analysis take?**
A: 2-10 seconds per commit, depending on repo size.

**Q: Does it need internet?**
A: Yes, to fetch GitHub data. Neo4j is optional and local.

---

## 📞 Need Help?

1. **Check Troubleshooting** section above
2. **Read the full README** (in finaltest folder)
3. **Check logs**: `tail -f streamlit.log`
4. **Verify services**: 
   ```bash
   curl http://localhost:8501/health
   curl http://localhost:8001/health
   ```

---

## 🎉 You're Ready!

```bash
# 1. Activate venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# 2. Start dashboard
streamlit run app.py

# 3. Open browser
open http://localhost:8501

# 4. Enter repo + SHA and click "Analyze"!
```

**Enjoy! 🚀**

---

**Last Updated**: November 2026  
**For Full Documentation**: See README.md
