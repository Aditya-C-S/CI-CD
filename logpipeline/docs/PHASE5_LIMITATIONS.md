# Phase 5: Known Limitations & Design Constraints

## Overview

This document outlines known limitations, design constraints, and future improvements for Phase 5 (Real GitHub Actions Log Forwarding).

## Scope Limitations

### Out of Scope (Intentional)

**Phase 5 does NOT:**
- Modify BiLSTM model or tokenization
- Change Phase 3 log size estimator
- Alter Phase 4 threshold detection logic
- Rebuild ingestion API from Phase 4
- Support real-time model retraining
- Provide SLA guarantees on log delivery
- Transform or pre-process logs (beyond secret redaction)
- Handle log compression or encryption

**Why:** Phase 5 is designed as a thin forwarding layer that captures real GHA output and pushes it through Phase 4's existing pipeline without architectural changes.

## Current Implementation Limitations

### 1. In-Memory Buffering

**Limitation:** Logs are buffered in process memory; very large outputs may cause memory pressure.

**Current Design:**
- Default buffer: 50KB or 100 lines, whichever comes first
- Flushed every 5 seconds or on command completion
- No disk-based spilling

**Impact:**
- Jobs with >100MB logs may use significant memory
- Long-running commands with continuous output may accumulate buffered data

**Workaround:**
- Reduce `max_bytes` or `max_lines` in buffer config
- Flush more frequently (`max_seconds=2.0`)
- Limit output verbosity in commands

**Future:** Could implement disk-based queue if needed.

### 2. Single-Process Execution

**Limitation:** The wrapper runs commands in a single subprocess; multi-process jobs aren't specially handled.

**Current Design:**
```
gh_run_with_logs.py
  └─ subprocess.Popen()
     └─ bash -c "your-command"
        ├─ pytest (single process)
        └─ python app.py (single process)
```

**Impact:**
- Child processes' output is captured but not isolated
- Multi-job workflows each get separate forwarding (correct)
- Cannot attribute logs to specific worker threads

**Workaround:**
- Use one wrapper per job in workflow
- Separate logs manually if process spawning is critical

**Future:** Could add per-PID logging if multi-worker isolation is needed.

### 3. Regex-Based Secret Redaction

**Limitation:** Secret redaction uses regex patterns, not cryptographic scanning.

**Current Redaction Patterns:**
- `AKIA[0-9A-Z]{16}` (AWS keys)
- `ghp_[a-zA-Z0-9_]{36,255}` (GitHub PAT)
- `api[_-]?key\s*=\s*[^\s]+` (generic API keys)
- `password\s*=\s*[^\s]+` (passwords)

**Impact:**
- Sophisticated secret formats may slip through
- Custom secret patterns not recognized
- Regex false positives possible (e.g., if log contains `api_key=abc def` with space)

**Workaround:**
- Manually audit logs before forwarding sensitive jobs
- Use GitHub's secret masking: `echo "::add-mask::secret_value"`
- Disable secret redaction if false positives occur

**Future:** Could integrate with GitGuardian or similar services.

### 4. HTTP-Only Transport (No Compression)

**Limitation:** Log chunks sent as plain JSON; no compression or binary encoding.

**Current Design:**
```
POST /api/demo/runs/{run_id}/logs
Content-Type: application/json
{
  "log_chunk": "plain text here...",
  ...
}
```

**Impact:**
- 50KB chunks → ~55KB JSON payload (10% overhead)
- Network bandwidth increases with log verbosity
- No streaming or chunked transfer encoding

**Workaround:**
- Reduce verbosity of commands (`-q` flags, less debug output)
- Filter logs locally before forwarding (not yet implemented)
- Increase buffer size to fewer but larger chunks

**Future:** Could add gzip compression (`Content-Encoding: gzip`).

### 5. No Log Persistence in Forwarder

**Limitation:** If API ingestion fails and retries exhaust, logs are discarded.

**Current Design:**
- Retry up to 3 times with exponential backoff
- No fallback disk queue
- Best-effort mode just logs warnings

**Impact:**
- Network partition → lost logs
- API overload → lost logs
- No audit trail of forwarded chunks

**Workaround:**
- Use strict mode to fail fast (easier to debug)
- Monitor API health before triggering workflows
- Implement external logging (e.g., CloudWatch integration)

**Future:** Could add optional disk queue for critical environments.

### 6. Stateless Event ID Generation

**Limitation:** Event IDs are UUIDs; no deterministic replay mechanism.

**Current Design:**
```python
event_id = f"evt_{uuid.uuid4().hex[:8]}"  # Random
```

**Impact:**
- Cannot replay exact same logs with same event_id
- Duplicate detection is single-session only
- No idempotency across workflow retries

**Workaround:**
- Design workflows to re-run cleanly (no data corruption)
- Use `GITHUB_RUN_ATTEMPT` as part of event ID if determinism needed

**Future:** Could use hash of (run_id + chunk_index) for deterministic IDs.

### 7. No Cross-Job Log Aggregation

**Limitation:** Each GHA job is a separate run; no parent-child relationships.

**Current Design:**
```
Workflow (gha_123)
  ├─ Job 1 → Run 1 (forwarded)
  ├─ Job 2 → Run 2 (forwarded)
  └─ Job 3 → Run 3 (forwarded)
```

**Impact:**
- Cannot view all logs for a workflow in one place
- Predictions per-job, not per-workflow
- No causal relationships between jobs

**Workaround:**
- Use `GITHUB_RUN_ID` to manually correlate jobs
- Add workflow_id to event_id
- Build aggregation layer in Phase 4

**Future:** Could add workflow-level run tracking.

## API Contract Limitations

### 1. Authentication

**Limitation:** Uses simple API key; no OAuth, JWT, or mTLS.

**Current Design:**
```
X-API-Key: your-api-key
```

**Impact:**
- Key exposure = full API access
- No rate limiting per user
- No audit trail of which key made request

**Workaround:**
- Rotate keys regularly
- Use GitHub Secrets (not version control)
- Restrict API to trusted networks (firewall)

**Future:** Could add JWT or mTLS for mutual authentication.

### 2. No Idempotency Tokens

**Limitation:** API doesn't accept idempotency keys; duplicate detection is client-side only.

**Current Design:**
```python
# Client side
submitted_event_ids.add(event_id)  # Prevents re-submission in same process
```

**Impact:**
- Network retry of same request → duplicate chunk
- API may ingest duplicates from different workflow runs
- Phase 4 must handle duplicate chunks

**Workaround:**
- Phase 4 deduplicates by event_id
- Client retries only on exception (not 200 response)

**Future:** API could accept `Idempotency-Key` header.

### 3. Synchronous Responses Only

**Limitation:** API doesn't support async callbacks or webhooks.

**Current Design:**
```
Client: POST /api/demo/runs/{run_id}/logs
Server: return 200 OK immediately
Client: continues to next chunk
```

**Impact:**
- If API processes slowly, logs pile up in workflow
- No backpressure or flow control
- Workflow can't wait for processing confirmation

**Workaround:**
- API must process chunks quickly (<1s)
- Monitor API performance

**Future:** Could add async processing with webhooks.

## Scaling Limitations

### 1. Single-Threaded Forwarding

**Limitation:** Each chunk forwarded sequentially; no concurrent uploads.

**Current Design:**
```python
for chunk in buffer.flush():
    api.ingest_chunk(chunk)  # Sequential
```

**Impact:**
- Large number of chunks → slow overall time
- Network latency multiplied by chunk count
- Single API connection reused

**Workaround:**
- Increase buffer size to reduce chunk count
- Run API locally or co-located (reduce latency)

**Future:** Could use thread pool for concurrent uploads.

### 2. No Load Balancing

**Limitation:** Forwarder connects to single API endpoint; no failover.

**Current Design:**
```
GHA Workflow → API_URL (single endpoint)
```

**Impact:**
- API single point of failure
- Cannot distribute load
- No graceful degradation

**Workaround:**
- Use load balancer in front of API
- Run multiple API replicas behind LB

**Future:** Could support API_URL_FAILOVER env var.

### 3. Memory Per Workflow

**Limitation:** Each workflow run has its own LogBuffer; no shared memory across jobs.

**Impact:**
- 100 concurrent jobs → 100 buffers × 50KB = 5MB baseline
- Very large buffers (100MB+) multiply this cost
- No optimization across jobs

**Workaround:**
- Use reasonable buffer sizes
- Monitor GHA memory limits

## Workflow Integration Limitations

### 1. No Job Ordering

**Limitation:** Logs from concurrent jobs may forward out of order.

**Current Design:**
- Job 1 may complete and finalize before Job 2 starts
- Phase 4 receives chunks in arrival order, not execution order

**Impact:**
- Temporal ordering of logs is workflow-dependent, not guaranteed
- Multi-job workflows may have interleaved logs

**Workaround:**
- Use sequential jobs if ordering is critical
- Phase 4 can re-order by timestamp

**Future:** Could add workflow_timestamp to all events.

### 2. No Signal Forwarding

**Limitation:** SIGTERM, SIGINT not forwarded to subprocess; only exit code.

**Current Design:**
```python
process = subprocess.Popen(...)  # Captures exit code only
```

**Impact:**
- Cannot detect if job was cancelled (signal) vs failed (exit code)
- Workflow outcome may not accurately reflect signal termination

**Workaround:**
- Use non-zero exit codes on termination
- Monitor GitHub Actions cancellation status separately

**Future:** Could add signal detection to workflow_outcome.

### 3. No Conditional Forwarding

**Limitation:** All jobs forward logs; no skip/condition logic.

**Current Design:**
```bash
python scripts/gh_run_with_logs.py your-command  # Always forwards
```

**Impact:**
- Cannot selectively disable forwarding per job
- No cost optimization

**Workaround:**
- Manual if-statement around forwarder invocation
- Use `GH_LOG_STRICT=false` to make it non-breaking

## Security Limitations

### 1. No Encryption in Transit

**Limitation:** Logs sent over HTTPS but not encrypted at rest.

**Current Design:**
```
Client → HTTPS → API (stores plain text in DB)
```

**Impact:**
- Requires HTTPS; no fallback to HTTP (good)
- API database not encrypted
- Logs visible to anyone with API access

**Workaround:**
- Use TLS 1.3+ only
- Enable API authentication (not yet implemented)
- Restrict API network access

**Future:** Could add E2E encryption or field-level encryption.

### 2. Secret Redaction Not Cryptographic

**Limitation:** Regex-based redaction can be bypassed.

**Current Design:**
```
Before: AWS_SECRET=AKIAIOSFODNN7EXAMPLE
After:  AWS_SECRET=[REDACTED]
```

**Impact:**
- Sophisticated secret formats may not match regex
- False negatives possible
- Cannot guarantee all secrets removed

**Workaround:**
- Manually audit critical logs
- Use GitHub Secrets masking in addition
- Rotate secrets if exposed

**Future:** Could integrate with secret scanning services.

### 3. API Key in Environment Variable

**Limitation:** API key passed as env var; visible in GitHub Actions logs if not careful.

**Current Design:**
```yaml
env:
  GH_LOG_API_KEY: ${{ secrets.LOG_API_KEY }}  # GitHub masks this
```

**Impact:**
- Requires GitHub to properly mask secrets
- Logs shouldn't show key, but possible if redaction fails

**Workaround:**
- Verify GitHub masks the value in logs
- Use GitHub's secret scanning on repo
- Rotate key if exposed

## Observability Limitations

### 1. No Built-in Metrics

**Limitation:** No metrics collection for forwarding success rate, latency, etc.

**Current Design:**
```python
logger.info(...)  # Just logging, no metrics
```

**Impact:**
- Hard to detect widespread failures
- No SLA visibility
- Cannot debug performance issues

**Workaround:**
- Parse logs for custom metrics
- Implement wrapper metrics collection
- Query API for run statistics

**Future:** Could emit CloudWatch/Prometheus metrics.

### 2. No Tracing

**Limitation:** No correlation IDs or distributed tracing.

**Current Design:**
- Each request independent
- No trace ID across client→API→Phase 4

**Impact:**
- Hard to follow a log chunk through the system
- Debugging slow predictions requires manual correlation

**Workaround:**
- Use event_id as manual trace ID
- Add manual logging to trace flow

**Future:** Could add OpenTelemetry support.

## Data Retention Limitations

### 1. No TTL or Archival

**Limitation:** API stores all logs indefinitely (depends on Phase 4 backend).

**Impact:**
- Database grows unbounded
- Old logs may affect query performance
- No cleanup mechanism

**Workaround:**
- Implement Phase 4 archival policy
- Monitor database size

**Future:** Could add log TTL or cold storage.

## Documentation Limitations

### 1. No Real Examples in Workflows

**Limitation:** Example workflows use simple test commands.

**Current Design:**
```yaml
python -c "print('test')"
```

**Impact:**
- Doesn't demonstrate real build/test scenarios
- Users may not know how to integrate with existing workflows

**Workaround:**
- Reference existing workflows in repo
- Add more complex examples

## Future Improvements (Backlog)

**Prioritized by impact:**

1. **P0: Disk-based queue** (data safety)
2. **P1: Concurrent uploads** (performance)
3. **P1: Gzip compression** (bandwidth)
4. **P2: Metrics collection** (observability)
5. **P2: JWT authentication** (security)
6. **P3: Workflow-level aggregation** (usability)
7. **P3: OpenTelemetry** (tracing)
8. **P4: Custom redaction patterns** (extensibility)

## Support & Escalation

For issues related to these limitations:

1. Check PHASE5_CONFIGURATION.md for workarounds
2. Review PHASE5_E2E_DEMO.md for examples
3. Run test suite: `pytest tests/test_phase5_log_forwarder.py -v`
4. Enable debug logging: `PYTHONUNBUFFERED=1`
5. File issue with limitation name and reproduction steps

## Conclusion

Phase 5 is designed as a pragmatic forwarding layer, not a comprehensive logging system. It prioritizes:
- **Simplicity**: Easy to integrate and understand
- **Reliability**: Retries and deduplication built-in
- **Minimal overhead**: Thin wrapper around subprocess

Limitations are documented and have workarounds. Future improvements are planned based on user feedback and scaling requirements.
