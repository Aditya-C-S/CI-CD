# Phase 5: End-to-End Demonstration Guide

This guide walks through a complete demonstration of Phase 5 (Real GitHub Actions Log Forwarding) with both success and failure scenarios.

## Prerequisites

- Python 3.11+
- Git & GitHub CLI (`gh`)
- Log Pipeline API running locally or accessible
- ngrok or localtunnel (for GHA → local API)
- Fork or clone of this repo

## Part 1: Local API Setup (5 minutes)

### Step 1: Start the Log Pipeline API

```bash
cd ~/projects/logpipeline

# Terminal 1: API Server
python -m src.api.main --port 8000

# Expected output:
# Uvicorn running on http://127.0.0.1:8000
# API ready at http://127.0.0.1:8000/docs
```

### Step 2: Expose API to Internet (for GitHub Actions)

```bash
# Terminal 2: Tunnel to GHA
ngrok http 8000

# Expected output:
# Forwarding  https://abcd-12-345-6789.ngrok.io -> http://127.0.0.1:8000
```

**Copy the ngrok URL for later use** (e.g., `https://abcd-12-345-6789.ngrok.io`)

### Step 3: Verify API Health

```bash
curl -s https://abcd-12-345-6789.ngrok.io/api/demo/runs | head -20

# Expected output:
# {
#   "status": "ok",
#   "runs": []
# }
```

## Part 2: GitHub Setup (5 minutes)

### Step 1: Add API Key Secret

1. Go to GitHub repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. **Name:** `LOG_API_KEY`
4. **Value:** `demo_key_phase5_testing` (or actual key from your API)
5. Click **Add secret**

### Step 2: Add API URL Secret

1. Click **New repository secret** again
2. **Name:** `LOG_API_URL`
3. **Value:** `https://abcd-12-345-6789.ngrok.io` (your ngrok URL from Part 1)
4. Click **Add secret**

### Step 3: Verify Secrets

Navigate to the same Secrets page and confirm both secrets appear (values hidden).

## Part 3: Run Success Scenario (10 minutes)

### Step 1: Trigger Success Workflow

```bash
# Option A: Via gh CLI
gh workflow run phase5_success.yml \
  --ref main \
  -f log_api_url="https://abcd-12-345-6789.ngrok.io"

# Option B: Via GitHub Web UI
# Go to Actions → Phase 5 Success → Run workflow → Run workflow
```

### Step 2: Monitor GitHub Actions

1. Go to **Actions** tab
2. Click on the **Phase 5 Success** workflow run
3. Click **phase5-success** job
4. Watch the output scroll in real-time

**Expected output:**
```
[*] Checking API connectivity...
[✓] Run created: run_xyz123
[✓] Forwarding logs: 45 bytes in chunk 1
[✓] Forwarding logs: 56 bytes in chunk 2
[✓] Finalized run: success
✅ Phase 5 Success: Logs forwarded to pipeline API
```

### Step 3: Verify in API

```bash
# Terminal 3: Query the API
curl -s https://abcd-12-345-6789.ngrok.io/api/demo/runs | jq '.runs[0]'

# Expected output:
# {
#   "run_id": "run_xyz123",
#   "status": "success",
#   "logs_ingested": 2,
#   "repo_id": "owner/repo",
#   "commit_sha": "abc123...",
#   "created_at": "2026-11-07T12:00:00Z"
# }
```

### Step 4: Check Phase 4 Predictions

```bash
# Query for predictions triggered by the logs
curl -s https://abcd-12-345-6789.ngrok.io/api/demo/runs/run_xyz123/predictions \
  | jq '.predictions'

# Expected output:
# [
#   {
#     "prediction_id": "pred_abc",
#     "trigger": "threshold_crossed",
#     "failure_probability": 0.12,
#     "timestamp": "2026-11-07T12:00:30Z"
#   }
# ]
```

## Part 4: Run Failure Scenario (10 minutes)

### Step 1: Trigger Failure Workflow

```bash
# Option A: Via gh CLI
gh workflow run phase5_failure.yml \
  --ref main \
  -f failure_type="exit_code_1" \
  -f log_api_url="https://abcd-12-345-6789.ngrok.io"

# Option B: Via GitHub Web UI
# Go to Actions → Phase 5 Failure → Run workflow
# Select failure_type: "exit_code_1"
# Run workflow
```

### Step 2: Monitor GitHub Actions

1. Go to **Actions** tab
2. Click on the **Phase 5 Failure** workflow run
3. Watch the job output

**Expected output:**
```
[*] Running: python -c "print('Phase 5 Failure Test'); import sys; sys.exit(1)"
Phase 5 Failure Test

[!] Command exited with code 1
[✓] Forwarding failure logs to API
[✓] Run finalized with outcome: failure
✅ Phase 5 Failure Test: Logs forwarded even with command failure
```

**Note:** The workflow shows orange (warning) status because `continue-on-error: true` is set.

### Step 3: Verify Failure Logs

```bash
# Query runs with failure outcome
curl -s https://abcd-12-345-6789.ngrok.io/api/demo/runs \
  | jq '.runs[] | select(.status == "failure")'

# Expected output:
# {
#   "run_id": "run_xyz456",
#   "status": "failure",
#   "logs_ingested": 3,
#   "workflow_outcome": "failure",
#   "exit_code": 1,
#   "repo_id": "owner/repo"
# }
```

### Step 4: Check Predictions for Failure

```bash
# Predictions should have high failure probability
curl -s https://abcd-12-345-6789.ngrok.io/api/demo/runs/run_xyz456/predictions \
  | jq '.predictions[]'

# Expected output shows:
# {
#   "failure_probability": 0.87,  # High confidence in failure
#   "trigger": "threshold_crossed",
#   "stage": "finalization"
# }
```

## Part 5: Multi-Run Comparison (10 minutes)

### Step 1: View All Runs

```bash
# List all forwarded runs
curl -s https://abcd-12-345-6789.ngrok.io/api/demo/runs | jq '.runs[] | {run_id, status, logs_ingested, created_at}' | head -40

# Expected output:
# {
#   "run_id": "run_xyz456",
#   "status": "failure",
#   "logs_ingested": 3,
#   "created_at": "2026-11-07T12:15:00Z"
# }
# {
#   "run_id": "run_xyz123",
#   "status": "success",
#   "logs_ingested": 2,
#   "created_at": "2026-11-07T12:10:00Z"
# }
```

### Step 2: Compare Predictions

```bash
# Success run: low failure probability
curl -s https://abcd-12-345-6789.ngrok.io/api/demo/runs/run_xyz123/predictions \
  | jq '.predictions[0].failure_probability'
# Output: 0.12

# Failure run: high failure probability
curl -s https://abcd-12-345-6789.ngrok.io/api/demo/runs/run_xyz456/predictions \
  | jq '.predictions[0].failure_probability'
# Output: 0.87
```

## Part 6: Isolation & Multi-Job Testing (15 minutes)

### Step 1: Run Multiple Workflows Simultaneously

```bash
# Trigger 3 success workflows in parallel
for i in {1..3}; do
  gh workflow run phase5_success.yml \
    --ref main \
    -f log_api_url="https://abcd-12-345-6789.ngrok.io" &
done
wait

# Trigger 2 failure workflows in parallel
for i in {1..2}; do
  gh workflow run phase5_failure.yml \
    --ref main \
    -f failure_type="exit_code_1" \
    -f log_api_url="https://abcd-12-345-6789.ngrok.io" &
done
wait
```

### Step 2: Verify Job Isolation

```bash
# Query runs - each should have unique run_id and isolated predictions
curl -s https://abcd-12-345-6789.ngrok.io/api/demo/runs \
  | jq '.runs | length'
# Expected output: 5

# Verify no cross-contamination of logs
curl -s https://abcd-12-345-6789.ngrok.io/api/demo/runs \
  | jq '.runs[] | {run_id, logs_ingested, status}'
# All runs should have independent log counts
```

## Part 7: Secret Redaction Verification (5 minutes)

### Step 1: Create Test with Secrets

Create a temporary test file:

```bash
cat > test_secret.py << 'EOF'
import os

# These should be redacted in logs
print("AWS_SECRET=AKIAIOSFODNN7EXAMPLE")
print("GITHUB_TOKEN=ghp_1234567890abcdefg")
print("API_KEY=sk_live_1234567890abcdef")
print("password=super_secret_password")
print("All secrets should be [REDACTED]")
EOF
```

### Step 2: Run with Forwarding

```bash
python scripts/gh_run_with_logs.py python test_secret.py 2>&1 | grep -E 'SECRET|TOKEN|API_KEY|password'

# Expected output:
# AWS_SECRET=[REDACTED]
# GITHUB_TOKEN=[REDACTED]
# API_KEY=[REDACTED]
# password=[REDACTED]
```

### Step 3: Verify in API Logs

```bash
# Get the run and check ingested logs for redaction
curl -s https://abcd-12-345-6789.ngrok.io/api/demo/runs | jq '.runs[0].logs_sample' | grep REDACTED

# All sensitive data should show as [REDACTED]
```

## Part 8: Deduplication & Idempotency (5 minutes)

### Step 1: Submit Duplicate Events

```bash
# From the log forwarder code, event_ids are unique per chunk
# Re-running the same command should generate new event_ids

# Run same workflow twice
gh workflow run phase5_success.yml --ref main -f log_api_url="https://abcd-12-345-6789.ngrok.io"
gh workflow run phase5_success.yml --ref main -f log_api_url="https://abcd-12-345-6789.ngrok.io"

# Wait for both to complete
sleep 30

# Query logs
curl -s https://abcd-12-345-6789.ngrok.io/api/demo/runs | jq '.runs | length'
# Should show 2 separate runs (not merged)
```

### Step 2: Verify No Duplicate Chunks

```bash
# Get both runs
curl -s https://abcd-12-345-6789.ngrok.io/api/demo/runs \
  | jq '.runs[] | {run_id, logs_ingested, created_at}' | tail -10

# Each run should have independent chunk count (no merge)
```

## Part 9: Error Recovery & Retry (10 minutes)

### Step 1: Simulate API Downtime

```bash
# Stop ngrok tunnel (or API server temporarily)
# Terminal 2: Press Ctrl+C to stop ngrok
```

### Step 2: Trigger Workflow During Downtime

```bash
# This will trigger while API is down
gh workflow run phase5_failure.yml --ref main -f log_api_url="https://abcd-12-345-6789.ngrok.io"
```

### Step 3: Verify Retry Behavior

Monitor the workflow output. You should see:
```
[!] API unreachable, retrying (attempt 1/3)...
[!] API unreachable, retrying (attempt 2/3)...
[!] Logs not forwarded (API down), but job continuing (GH_LOG_STRICT=false)
```

### Step 4: Bring API Back Online

```bash
# Terminal 2: Re-start ngrok
ngrok http 8000
```

### Step 5: Manual Retry

```bash
# Trigger again - should now succeed
gh workflow run phase5_success.yml --ref main -f log_api_url="https://abcd-12-345-6789.ngrok.io"
```

## Verification Checklist

- [ ] **API Running**: `curl https://abcd-12-345-6789.ngrok.io/api/demo/runs`
- [ ] **Success Workflow**: Completes with logs forwarded
- [ ] **Failure Workflow**: Completes and forwards failure logs
- [ ] **Predictions Triggered**: `/api/demo/runs/{run_id}/predictions` shows Phase 4 predictions
- [ ] **Secret Redaction**: Logs show `[REDACTED]` for sensitive data
- [ ] **Multi-Run Isolation**: Each run has unique run_id and logs
- [ ] **Job Isolation**: No cross-contamination between concurrent runs
- [ ] **Retry Behavior**: Handles API downtime with exponential backoff
- [ ] **Deduplication**: Same event_id not submitted twice

## Cleanup

### Option A: Keep Running (for continued testing)

```bash
# API and ngrok keep running
# Workflows queue in GitHub for manual execution
```

### Option B: Stop Services

```bash
# Terminal 2: Stop ngrok
# Press Ctrl+C

# Terminal 1: Stop API
# Press Ctrl+C

# Verify API down
curl https://abcd-12-345-6789.ngrok.io/api/demo/runs
# Expected: Connection refused
```

## Performance Observations

During the demo, you should observe:

1. **Latency**: ~100-500ms per chunk forwarded (depends on network)
2. **Throughput**: 50KB chunks typically forward in <1s
3. **Buffering**: With default settings (100 lines, 50KB, 5s):
   - Small commands flush immediately
   - Large logs may buffer for 5s max
4. **Memory**: ~10-50MB for typical GHA jobs
5. **Prediction Trigger**: Predictions appear within 1-2s of threshold crossing

## Troubleshooting

### Workflow Shows "Failed"

Check if `GH_LOG_STRICT=true` (strict mode):
- If yes, API failure → job failure
- Use `GH_LOG_STRICT=false` for best-effort mode

### No Logs Appearing in API

1. Check ngrok is running: `curl https://xxxx.ngrok.io/ping`
2. Check API has the run: `curl https://xxxx.ngrok.io/api/demo/runs`
3. Check GitHub Actions output for forwarder errors
4. Verify API key matches

### Predictions Not Triggered

1. Verify Phase 4 API is running separately
2. Check threshold values in Phase 4 config
3. Query predictions endpoint: `/api/demo/runs/{run_id}/predictions`
4. Review Phase 4 logs for errors

## Next Steps

After successful E2E demo:

1. **Production Setup**: Replace ngrok with permanent DNS
2. **ORC Integration**: Integrate with orchestration system
3. **Monitoring**: Set up metrics for log forwarding success rate
4. **CI/CD Rollout**: Update all workflows to use phase5 forwarder
5. **Documentation**: Add team-specific setup instructions

## Additional Resources

- Configuration Guide: `docs/PHASE5_CONFIGURATION.md`
- API Reference: `docs/phase4_integration.md`
- Log Forwarder Code: `src/integration/github_actions/log_forwarder.py`
- Wrapper Script: `scripts/gh_run_with_logs.py`
- Example Workflows: `.github/workflows/phase5_*.yml`
- Test Suite: `tests/test_phase5_log_forwarder.py`
