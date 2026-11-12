# Phase 5: Quick Start Guide

Get Phase 5 (GitHub Actions Log Forwarding) running in 5 minutes.

## 1. Add GitHub Secrets (2 min)

In your GitHub repo:
1. **Settings → Secrets and variables → Actions**
2. Add two secrets:
   - `LOG_API_URL`: `https://localhost:8000` (or your API URL)
   - `LOG_API_KEY`: `demo_key_phase5` (or your API key)

## 2. Update Your Workflow (2 min)

Add log forwarding to any job:

```yaml
jobs:
  my_job:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      # NEW: Install requests library
      - run: pip install requests
      
      # CHANGE: Wrap your command with log forwarder
      - name: Run with Log Forwarding
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
          python scripts/gh_run_with_logs.py YOUR_COMMAND_HERE
```

Replace `YOUR_COMMAND_HERE` with your actual command, e.g.:
- `pytest tests/ -v`
- `python build.py`
- `npm run test`
- `make deploy`

## 3. Trigger Workflow (1 min)

```bash
gh workflow run <your_workflow.yml>
```

Or use GitHub web UI: **Actions → Your Workflow → Run workflow**

## 4. Verify Logs (1 min)

Open Log Pipeline UI:
```
https://localhost:8000  (or your API URL)
```

Look for your repo in the **Runs** section.

## ✅ Done!

Your workflow now forwards logs to the Log Pipeline API. Logs are:
- Captured in real-time
- Buffered for efficiency
- Secrets redacted automatically
- Forwarded progressively
- Used for Phase 4 predictions

## 🔧 Configuration

### Environment Variables

**Required:**
- `GH_LOG_API_URL`: API endpoint
- `GH_LOG_API_KEY`: API authentication key
- `GITHUB_*`: GitHub context (auto-filled above)

**Optional:**
- `GH_LOG_STRICT`: `true` (fail job on API error) or `false` (continue)

### Buffering (Advanced)

To customize buffering, edit `scripts/gh_run_with_logs.py`:

```python
# Around line 80-85
buffer = LogBuffer(
    max_lines=100,        # Lines per chunk (default)
    max_bytes=50000,      # Bytes per chunk (default)
    max_seconds=5.0       # Seconds before flush (default)
)
```

Smaller values = more frequent forwarding. Larger values = fewer API calls.

## 🐛 Troubleshooting

### Workflow shows "Failed"
- Check `GH_LOG_STRICT` mode (default: `true` fails the job)
- Use `GH_LOG_STRICT: "false"` to allow failure

### "Connection refused" error
- Verify `LOG_API_URL` is correct and API is running
- For local dev: use ngrok tunnel (see PHASE5_CONFIGURATION.md)

### Logs not appearing in UI
- Check secrets are set correctly
- Verify API URL is accessible
- Look for errors in workflow output

## 📚 Full Documentation

- **Setup & Configuration**: See `docs/PHASE5_CONFIGURATION.md`
- **Full Demo**: See `docs/PHASE5_E2E_DEMO.md`
- **Known Limits**: See `docs/PHASE5_LIMITATIONS.md`

## 🧪 Test the Implementation

```bash
# Run test suite (verify everything works)
cd /path/to/logpipeline
python -m pytest tests/test_phase5_log_forwarder.py -v

# Expected: 20 tests pass
```

## 📝 Example Workflows

Pre-made example workflows are included:

- `.github/workflows/phase5_success.yml` - Success scenario
- `.github/workflows/phase5_failure.yml` - Failure scenario

Copy and adapt these to your needs.

## 🚀 Next Steps

1. **Local Testing**: Follow PHASE5_E2E_DEMO.md for hands-on walkthrough
2. **Production Setup**: Update Log Pipeline API URL and key for production
3. **Monitor**: Check log forwarding success rate and latency
4. **Iterate**: Adjust buffer sizes based on your log volumes

---

**Need help?** Check the full docs or run the test suite to verify your setup.
