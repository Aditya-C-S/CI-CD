# Phase 5: Real GitHub Actions Log Forwarding - Configuration Guide

## Overview

Phase 5 enables real GitHub Actions workflows to forward logs to the Log Pipeline API for real-time threshold detection and failure prediction. This document explains how to set up and use the log forwarder.

## Architecture

```
GitHub Actions Job
  ↓
gh_run_with_logs.py (wrapper)
  ↓
CommandExecutor (captures stdout/stderr)
  ↓
LogBuffer (buffers by lines/bytes/time)
  ↓
SecretRedactor (redacts sensitive data)
  ↓
APIClient (HTTP forwarding with retries)
  ↓
Log Pipeline API (/api/demo/runs/{run_id}/logs)
  ↓
Phase 4 Threshold Detection
```

## Environment Variables

The log forwarder is controlled via environment variables. Set these in your GitHub Actions workflow:

### Required

- **`GH_LOG_API_URL`**: Base URL of the Log Pipeline API
  - Example: `https://localhost:8000` (local dev)
  - Example: `https://api.logpipeline.example.com` (production)

- **`GH_LOG_API_KEY`**: API authentication key
  - Retrieved from `${{ secrets.LOG_API_KEY }}` in GitHub Actions
  - Forwarded as `X-API-Key` header to the API

### Optional

- **`GH_LOG_STRICT`**: Error handling mode (default: `true`)
  - `true`: Fail the job if log forwarding fails (strict mode)
  - `false`: Continue job even if log forwarding fails (best-effort mode)

### GitHub Context (Auto-Populated)

These are automatically injected by GitHub Actions but must be explicitly set in the workflow:

```yaml
env:
  GITHUB_REPOSITORY: ${{ github.repository }}
  GITHUB_SHA: ${{ github.sha }}
  GITHUB_RUN_ID: ${{ github.run_id }}
  GITHUB_RUN_ATTEMPT: ${{ github.run_attempt }}
  GITHUB_REF_NAME: ${{ github.ref_name }}
  GITHUB_JOB: ${{ github.job }}
  GITHUB_EVENT_NAME: ${{ github.event_name }}
```

## Setup Instructions

### 1. Add API Secret to GitHub Repository

1. Navigate to: **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Name: `LOG_API_KEY`
4. Value: (obtained from your Log Pipeline administrator)
5. Click **Add secret**

### 2. Update Your Workflow

Replace your command invocation with the log forwarder wrapper:

**Before (without forwarding):**
```yaml
- name: Run Tests
  run: pytest tests/ -v
```

**After (with forwarding):**
```yaml
- name: Run Tests with Log Forwarding
  env:
    GH_LOG_API_URL: ${{ secrets.LOG_API_URL }}
    GH_LOG_API_KEY: ${{ secrets.LOG_API_KEY }}
    GH_LOG_STRICT: "false"
    GITHUB_REPOSITORY: ${{ github.repository }}
    GITHUB_SHA: ${{ github.sha }}
    GITHUB_RUN_ID: ${{ github.run_id }}
    GITHUB_RUN_ATTEMPT: ${{ github.run_attempt }}
    GITHUB_REF_NAME: ${{ github.ref_name }}
    GITHUB_JOB: ${{ github.job }}
    GITHUB_EVENT_NAME: ${{ github.event_name }}
  run: |
    python scripts/gh_run_with_logs.py \
      pytest tests/ -v
```

### 3. Install Dependencies

Ensure `requests` is installed (required by log forwarder):

```yaml
- name: Install Dependencies
  run: |
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    pip install requests  # Required by log forwarder
```

## Buffering Configuration

The log forwarder buffers output to avoid spamming the API. Chunks are flushed when ANY limit is reached:

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `max_lines` | 100 | Flush after this many lines |
| `max_bytes` | 50000 | Flush after this many bytes |
| `max_seconds` | 5.0 | Flush after this many seconds |

Example with custom buffering:

```python
buffer = LogBuffer(
    max_lines=200,      # More lines per chunk
    max_bytes=100000,   # Larger byte size
    max_seconds=10.0    # More time before flush
)
```

## Secret Redaction

The log forwarder automatically redacts:

- **AWS Keys**: `AKIA*` patterns, `aws_secret_access_key`, `aws_access_key_id`
- **GitHub Tokens**: `ghp_*`, `ghu_*`, `ghs_*`, `ghr_*`
- **API Keys**: `api_key=`, `apikey=`, `api-key=` patterns
- **Passwords**: `password=`, `passwd=` patterns

Redacted values are replaced with `[REDACTED]`.

Example redaction:
```
Before: export AWS_KEY=AKIAIOSFODNN7EXAMPLE
After:  export AWS_KEY=[REDACTED]
```

## API Contract

### Create Run

**Endpoint:** `POST /api/demo/runs`

**Request:**
```json
{
  "repo_id": "owner/repo",
  "commit_sha": "abc123...",
  "branch": "main",
  "is_pr": false,
  "runtime_model": "logistic_regression",
  "auto_advance": false
}
```

**Response:**
```json
{
  "run_id": "run_xyz"
}
```

### Ingest Chunk

**Endpoint:** `POST /api/demo/runs/{run_id}/logs`

**Headers:**
```
X-API-Key: your-api-key
Content-Type: application/json
```

**Request:**
```json
{
  "log_chunk": "Build step output here...",
  "event_id": "evt_abc123",
  "step_name": "pytest",
  "stage": "execution",
  "ci_run_id": "gha_123456",
  "commit_sha": "abc123...",
  "step_outcome": "success|failure",
  "workflow_outcome": "success|failure",
  "exit_code": 0,
  "is_final": false,
  "timestamp": "2026-11-07T12:00:00Z"
}
```

**Response:**
```json
{
  "status": "ok",
  "log_id": "log_xyz"
}
```

### Finalize Run

**Request (special case of ingest with is_final=true):**
```json
{
  "log_chunk": "",
  "event_id": "final_xyz",
  "stage": "finalization",
  "workflow_outcome": "success|failure",
  "is_final": true,
  "timestamp": "2026-11-07T12:00:00Z"
}
```

## Local Development Setup

### Option 1: Using ngrok (Fast)

1. Install ngrok: https://ngrok.com/download
2. Start your Log Pipeline API locally:
   ```bash
   python -m src.api.main
   ```
3. In a new terminal, expose it:
   ```bash
   ngrok http 8000
   ```
4. Use the ngrok URL in your workflow:
   ```yaml
   GH_LOG_API_URL: https://xxxx-xx-xxx-xxx-xx.ngrok.io
   ```

### Option 2: Using localtunnel

1. Install: `npm install -g localtunnel`
2. Start your API locally
3. Expose it:
   ```bash
   lt --port 8000 --subdomain myapi
   ```
4. Use: `https://myapi.loca.lt`

## Example Workflows

### Simple Success Scenario

```yaml
name: Phase 5 Success Example

on: workflow_dispatch

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - run: pip install requests
      
      - name: Run with Log Forwarding
        env:
          GH_LOG_API_URL: ${{ secrets.LOG_API_URL }}
          GH_LOG_API_KEY: ${{ secrets.LOG_API_KEY }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          GITHUB_SHA: ${{ github.sha }}
          GITHUB_RUN_ID: ${{ github.run_id }}
          GITHUB_RUN_ATTEMPT: ${{ github.run_attempt }}
          GITHUB_REF_NAME: ${{ github.ref_name }}
          GITHUB_JOB: ${{ github.job }}
          GITHUB_EVENT_NAME: ${{ github.event_name }}
        run: |
          python scripts/gh_run_with_logs.py python -c "print('Success')"
```

### Failure Scenario with Best-Effort Mode

```yaml
- name: Run (may fail, logs still forwarded)
  env:
    GH_LOG_API_URL: ${{ secrets.LOG_API_URL }}
    GH_LOG_API_KEY: ${{ secrets.LOG_API_KEY }}
    GH_LOG_STRICT: "false"  # Don't fail the job if API is down
    GITHUB_REPOSITORY: ${{ github.repository }}
    GITHUB_SHA: ${{ github.sha }}
    GITHUB_RUN_ID: ${{ github.run_id }}
    GITHUB_RUN_ATTEMPT: ${{ github.run_attempt }}
    GITHUB_REF_NAME: ${{ github.ref_name }}
    GITHUB_JOB: ${{ github.job }}
    GITHUB_EVENT_NAME: ${{ github.event_name }}
  run: |
    python scripts/gh_run_with_logs.py pytest tests/ -v
  continue-on-error: true
```

## Retry Behavior

The log forwarder automatically retries failed API calls with exponential backoff:

- **Max Retries:** 3 (configurable)
- **Initial Delay:** 1 second
- **Backoff Formula:** `delay = initial_delay * (2 ^ attempt_number)`

Example retry timeline:
- Attempt 1 fails → wait 1s
- Attempt 2 fails → wait 2s
- Attempt 3 fails → wait 4s
- Attempt 4 (final) fails → raise error or log warning

## Error Handling

### Strict Mode (default: `GH_LOG_STRICT=true`)

If log forwarding fails:
- The entire job fails with a RuntimeError
- Useful when logs are critical for your pipeline

### Best-Effort Mode (`GH_LOG_STRICT=false`)

If log forwarding fails:
- Job continues normally
- Errors are logged but not fatal
- Useful for optional telemetry

## Monitoring & Verification

### Check Logs Forwarded

1. Access the Log Pipeline UI at your `GH_LOG_API_URL`
2. Navigate to the Runs section
3. Look for entries with:
   - Your repo name
   - Latest commit SHA
   - Today's date
4. Click on a run to see forwarded log chunks

### Verify Threshold Detection

After logs are forwarded:

1. Go to Phase 4 predictions page
2. Filter by your commit SHA
3. Check if threshold-based predictions were triggered
4. Review prediction confidence scores

### Debugging

Enable debug logging in your workflow:

```yaml
- name: Run with Debug Logging
  env:
    GH_LOG_API_URL: ${{ secrets.LOG_API_URL }}
    GH_LOG_API_KEY: ${{ secrets.LOG_API_KEY }}
    PYTHONUNBUFFERED: "1"  # Real-time Python output
  run: |
    python -u scripts/gh_run_with_logs.py your-command
```

## Limitations & Known Issues

1. **SSL Verification**: Local dev with self-signed certs requires `verify_ssl=false` (handled by wrapper)
2. **Large Logs**: Chunks are buffered in memory; very large outputs (>1GB) may cause memory pressure
3. **Network Dependency**: Job only fails if `GH_LOG_STRICT=true` and API is unreachable
4. **Secret Redaction**: Regex-based; edge cases may slip through (manual audit recommended)

## Troubleshooting

### API Key Invalid

**Error:** `403 Forbidden`

**Solution:** Verify the API key in GitHub Secrets matches your Log Pipeline API key.

### API Unreachable

**Error:** `Connection refused` or `Timeout`

**Solution:**
1. Check the API URL: `curl $GH_LOG_API_URL/api/demo/runs`
2. Ensure API is running
3. For local dev, use ngrok or localtunnel
4. Use `GH_LOG_STRICT=false` to prevent job failure

### Logs Not Appearing

**Debug steps:**
1. Check workflow output for log forwarder errors
2. Verify run was created: `GET /api/demo/runs`
3. Confirm chunks are ingested: `POST /api/demo/runs/{run_id}/logs` response
4. Check secret redaction isn't hiding output

### High Memory Usage

**Solution:** Reduce buffer sizes in log forwarder:

```python
# In scripts/gh_run_with_logs.py
buffer = LogBuffer(
    max_lines=50,       # Smaller chunks
    max_bytes=10000,    # Smaller byte size
    max_seconds=2.0     # Flush more often
)
```

## Next Steps

1. Set up API secret in GitHub: `LOG_API_KEY` and `LOG_API_URL`
2. Update your workflows to use `scripts/gh_run_with_logs.py`
3. Trigger a test workflow manually
4. Monitor logs in the Log Pipeline UI
5. Verify predictions are triggered by Phase 4
6. Document any custom buffering or redaction needs

## Support

For issues or questions:
- Check Log Pipeline API logs: `docker logs logpipeline-api`
- Review Phase 4 threshold detection: `docs/phase4_integration.md`
- Run local tests: `python -m pytest tests/test_phase5_log_forwarder.py -v`
