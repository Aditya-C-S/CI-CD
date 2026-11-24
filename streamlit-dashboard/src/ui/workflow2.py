"""
Workflow 2: Automatic CI Log Analysis with Polling
Automatically discovers and monitors Log Pipeline runs based on repository and commit SHA.
Displays comprehensive log analysis results including predictions, RCA, and remediation.
"""

import streamlit as st
import logging
import time
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
from src.state.session import get_wf2_status_display, reset_wf2_state
from src.backend.logpipeline_handler import LogPipelineHandler
from src.ui.live_progress import render_live_progress_section

logger = logging.getLogger(__name__)

# Polling configuration
POLLING_INTERVAL = 5  # seconds (for run discovery)
LIVE_POLL_INTERVAL = 2  # seconds (for active run monitoring)
MAX_RETRY_WITHOUT_RUN = 60  # seconds (give up trying to find a run after 60s)


def _parse_run_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        s = str(dt_str).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def is_run_stale(r: Optional[Dict[str, Any]], threshold_seconds: int = 900) -> bool:
    """
    Check if a running run is abandoned/stale.
    If status == 'running':
    - Checks updated_at or created_at activity timestamps.
    - If activity timestamps are missing, empty, or unparseable, the run cannot prove
      active telemetry and is safely marked as stale (True) to prevent indefinite active classification.
    """
    if not r or not isinstance(r, dict):
        return False
    if r.get("status") != "running":
        return False
    last_dt = _parse_run_datetime(r.get("updated_at") or r.get("created_at"))
    if not last_dt:
        # Missing activity timestamps safely treated as stale (fail-closed staleness)
        return True
    now = datetime.now(timezone.utc)
    elapsed = (now - last_dt).total_seconds()
    return elapsed > threshold_seconds


def is_run_terminal(run: Optional[Dict[str, Any]]) -> bool:
    """
    Authoritative terminal-status check for a run.
    A run is terminal if:
    - status is in ('completed', 'failed', 'cancelled')
    - ci_execution.workflow_outcome or actual_outcome is in ('success', 'failure')
    - ci_execution.status is in ('completed', 'failed', 'cancelled')
    - stages.rca_remediation.status is 'completed'
    - is_run_stale(run) is True
    """
    if not isinstance(run, dict):
        return True
    
    status = str(run.get("status") or "").strip().lower()
    if status in ("completed", "failed", "cancelled"):
        return True
    
    ci_exec = run.get("ci_execution") if isinstance(run.get("ci_execution"), dict) else {}
    workflow_outcome = str(ci_exec.get("workflow_outcome") or "").strip().lower()
    if workflow_outcome in ("success", "failure"):
        return True
    
    actual_outcome = str(run.get("actual_outcome") or "").strip().lower()
    if actual_outcome in ("success", "failure"):
        return True
        
    ci_status = str(ci_exec.get("status") or "").strip().lower()
    if ci_status in ("completed", "failed", "cancelled"):
        return True
        
    stages = run.get("stages") if isinstance(run.get("stages"), dict) else {}
    rca_stage = stages.get("rca_remediation") if isinstance(stages.get("rca_remediation"), dict) else {}
    if rca_stage.get("status") == "completed":
        return True

    if is_run_stale(run):
        return True

    return False


def classify_run_provenance(run: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify a run's provenance using authentic runner telemetry, GitHub Actions run IDs,
    and verified source records.
    
    Returns:
        dict with:
            - category: 'AUTHENTIC GITHUB ACTIONS' | 'LOCAL DEMO / SYNTHETIC' | 'UNKNOWN / UNVERIFIED'
            - badge: formatted string with icon
            - is_authentic: bool
            - reason: human-readable explanation
    """
    ci_exec = run.get('ci_execution') or {}
    ci_id = str(ci_exec.get('ci_run_id') or '').strip().lower()
    acc_log = run.get('accumulated_log', '') or ''
    exec_source = (run.get('execution_source') or '').upper()
    log_lines = run.get('log_lines_count', 0)
    if not log_lines and acc_log:
        log_lines = len(acc_log.splitlines())

    # 0. Check for explicit local / simulation / synthetic execution source
    if any(pfx in exec_source for pfx in ("LOCAL", "SIMULATION", "MOCK", "TEST")):
        return {
            "category": "LOCAL DEMO / SYNTHETIC",
            "badge": "🟠 LOCAL DEMO / SYNTHETIC",
            "is_authentic": False,
            "reason": f"Local simulation / runner test ({log_lines} log lines, source: {exec_source}).",
        }

    # 1. Check for GitHub API fallback / post-run source
    if "API FALLBACK" in exec_source or "POST-RUN" in exec_source:
        return {
            "category": "PUBLIC GITHUB REPO (API Fallback)",
            "badge": "🔵 PUBLIC GITHUB REPO (API Fallback)",
            "is_authentic": True,
            "reason": f"Discovered via GitHub REST API ({log_lines} log lines). Post-run log analysis.",
        }

    # 2. Check for explicit local / synthetic identifiers
    if any(ci_id.startswith(pfx) for pfx in ("local", "sim", "mock", "test_run", "demo")):
        return {
            "category": "LOCAL DEMO / SYNTHETIC",
            "badge": "🟠 LOCAL DEMO / SYNTHETIC",
            "is_authentic": False,
            "reason": f"Local test runner identifier '{ci_exec.get('ci_run_id')}' with synthetic mock data ({log_lines} lines).",
        }

    # 2. Check for synthetic mock demo log patterns
    if "Step 1: Installing dependencies" in acc_log and log_lines < 20:
        return {
            "category": "LOCAL DEMO / SYNTHETIC",
            "badge": "🟠 LOCAL DEMO / SYNTHETIC",
            "is_authentic": False,
            "reason": f"Synthetic demo script log ({log_lines} lines). Not authentic runner console telemetry.",
        }

    # 3. Check for genuine authentic GitHub Actions runner telemetry in log stream
    runner_signatures = [
        "Current runner version:",
        "Runner Image Provisioner",
        "Hosted Compute Agent",
        "GITHUB_TOKEN Permissions",
        "actions/checkout@",
        "actions/setup-python@",
        "Image: ubuntu-",
        "Image Release: https://github.com/actions/runner-images",
    ]
    matched_signatures = [sig for sig in runner_signatures if sig in acc_log]
    if matched_signatures and log_lines > 20:
        return {
            "category": "AUTHENTIC GITHUB ACTIONS",
            "badge": "🟢 AUTHENTIC GITHUB ACTIONS",
            "is_authentic": True,
            "reason": f"Verified authentic GitHub Actions runner telemetry ({log_lines} log lines with '{matched_signatures[0]}').",
        }

    # 4. Genuine GitHub Actions run ID (numeric 6+ digits from GitHub API)
    if ci_id.isdigit() and len(ci_id) >= 6 and log_lines > 10:
        return {
            "category": "AUTHENTIC GITHUB ACTIONS",
            "badge": "🟢 AUTHENTIC GITHUB ACTIONS",
            "is_authentic": True,
            "reason": f"Authentic GitHub Actions workflow run #{ci_id} ({log_lines} log lines).",
        }

    # 5. Fallback check on log volume and source
    if not acc_log.strip():
        return {
            "category": "UNKNOWN / UNVERIFIED",
            "badge": "⚪ UNKNOWN / UNVERIFIED",
            "is_authentic": False,
            "reason": "No log stream available for this run.",
        }

    if "AUTHENTIC" in exec_source and log_lines > 50:
        return {
            "category": "AUTHENTIC GITHUB ACTIONS",
            "badge": "🟢 AUTHENTIC GITHUB ACTIONS",
            "is_authentic": True,
            "reason": f"Verified live telemetry stream ({log_lines} lines).",
        }

    return {
        "category": "LOCAL DEMO / SYNTHETIC",
        "badge": "🟠 LOCAL DEMO / SYNTHETIC",
        "is_authentic": False,
        "reason": f"Local simulation / benchmark replay ({log_lines} lines).",
    }


def render_workflow2():
    """Render Workflow 2 UI - Generic CI Log Analysis & Live Monitoring."""
    monitored_repo = st.session_state.get("monitored_repo") or st.session_state.get("github_repo") or "Aditya-C-S/demo-order-service"
    is_valid = bool(monitored_repo.strip() != "" and "/" in monitored_repo)
    
    # Detect input changes and reset state if repo changed
    _detect_input_change(is_valid)
    
    # Top Header: Monitored Repository & Status
    with st.container():
        hcol1, hcol2, hcol3 = st.columns([3, 2, 2])
        with hcol1:
            st.markdown(f"**Target Repository:** `{monitored_repo}`")
            repo_lower = monitored_repo.lower()
            has_auth_run = any(
                (r.get("repo_id") or "").lower() == repo_lower and r.get("data_source") == "AUTHENTIC GITHUB ACTIONS"
                for r in st.session_state.get("wf2_runs", [])
            )
            if "demo-order-service" in repo_lower or has_auth_run:
                mode_badge = "🟢 Live Streaming (Verified Runner)"
            elif "flask" in repo_lower and "pallets" not in repo_lower:
                mode_badge = "🟡 Integration Configured (Awaiting Live Run)"
            else:
                mode_badge = "🔵 Post-Run API Fallback Only"
            st.caption(f"Mode: {mode_badge}")
        with hcol2:
            st.markdown(f"**Pipeline Status:** {get_wf2_status_display(st.session_state.wf2_status)}")
            if st.session_state.wf2_last_refresh:
                st.caption(f"Last checked: {st.session_state.wf2_last_refresh}")
        with hcol3:
            btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1])
            with btn_col1:
                if st.button("🔄 Refresh", use_container_width=True, key="btn_retry_discovery"):
                    _fetch_log_runs_manual()
            with btn_col2:
                if st.button("🔄 Reset", use_container_width=True, key="btn_wf2_reset"):
                    reset_wf2_state()
                    st.rerun()
            with btn_col3:
                auto_refresh = st.checkbox("Auto", value=st.session_state.get("auto_refresh_enabled", True), key="chk_auto_refresh_top", help="Auto-refresh periodically (2s for active live runs, 5s for discovery)")
                st.session_state["auto_refresh_enabled"] = auto_refresh
    
    st.divider()
    
    # Attempt automatic discovery and polling
    if is_valid:
        _handle_automatic_discovery_and_polling()
    
    # Display content based on status
    if st.session_state.wf2_status == "idle" and not st.session_state.wf2_runs:
        st.info(
            f"👆 Waiting for CI/CD pipeline executions on `{monitored_repo}`. When a workflow starts, incoming logs will stream automatically.",
            icon="ℹ️"
        )
    
    elif st.session_state.wf2_status == "discovering":
        st.info(f"🔍 Checking for active runs on `{monitored_repo}`...", icon="ℹ️")
    
    elif st.session_state.wf2_status == "waiting":
        st.info(f"⏳ Waiting for live CI run on `{monitored_repo}`...", icon="ℹ️")
        st.markdown("Automatic listener is active. The dashboard will automatically detect and stream when a runner connects.")
    
    elif st.session_state.wf2_status == "running":
        st.warning(f"🔄 CI/CD Pipeline execution active on `{monitored_repo}`!", icon="⚠️")
        st.markdown("Streaming incoming log chunks and running ML predictions every 2-3 seconds...")
    
    elif st.session_state.wf2_status == "analyzing":
        st.warning("🔍 Analysis in progress...", icon="⚠️")
    
    elif st.session_state.wf2_status == "failed":
        st.error(
            f"Failed to retrieve runs: {st.session_state.wf2_error}",
            icon="❌"
        )
    
    elif st.session_state.wf2_status == "unavailable":
        st.error(
            "⚠️ Log Pipeline backend is unavailable. Make sure the Unified Backend API is running on port 8000.",
            icon="❌"
        )
    
    if st.session_state.wf2_runs:
        render_wf2_runs(st.session_state.wf2_runs)
    
    # Check whether an active live run is genuinely in-flight
    active_in_flight = False
    if st.session_state.wf2_runs:
        for r in st.session_state.wf2_runs:
            if isinstance(r, dict) and r.get("status") == "running" and not is_run_stale(r) and not is_run_terminal(r):
                active_in_flight = True
                break

    auto_refresh_enabled = st.session_state.get("auto_refresh_enabled", True)

    # Polling & Rerun scheduler:
    # ONLY trigger rapid periodic reruns (2s) when an active pipeline is genuinely streaming.
    # When all runs are terminal/completed, DO NOT call st.rerun() in an infinite loop!
    # Halting reruns on completed runs eliminates full-page buffering, screen fading, and flickering.
    if auto_refresh_enabled and is_valid and active_in_flight:
        time.sleep(LIVE_POLL_INTERVAL)
        st.rerun()

    # Background Discovery Poller (st.fragment):
    # When no active run is in flight, this isolated fragment quietly checks for newly triggered
    # CI/CD workflows every 5s without causing full-page reruns, buffering overlays, or screen flickering.
    # It triggers an app-level rerun (st.rerun) ONLY when a new workflow, active run, or status change is detected.
    if auto_refresh_enabled and is_valid and not active_in_flight:
        _discovery_poller_fragment(monitored_repo, is_valid)


def _detect_input_change(is_valid: bool) -> None:
    """Detect if monitored repository changed and reset state accordingly."""
    current_repo = st.session_state.get("monitored_repo") or st.session_state.get("github_repo") or "Aditya-C-S/demo-order-service"
    last_repo = st.session_state.get("wf2_last_discovery_repo") if hasattr(st.session_state, "get") else getattr(st.session_state, "wf2_last_discovery_repo", None)
    repo_changed = (last_repo != current_repo)
    
    if repo_changed:
        if st.session_state.get("wf2_runs"):
            st.session_state.wf2_runs = []
            st.session_state.wf2_selected_run_id = None
            st.session_state.wf2_user_locked_run_id = None
            st.session_state.wf2_polling_active = False
            st.session_state.wf2_status = "idle"
            if hasattr(st.session_state, "_cached_terminal_runs"):
                st.session_state._cached_terminal_runs = {}
            logger.info(f"Monitored repo changed to {current_repo} - resetting discovery state")


def _handle_automatic_discovery_and_polling() -> None:
    """
    Handle automatic discovery and polling of Log Pipeline runs.
    Continuously discovers newly started or completed CI/CD runs on the monitored repository.
    """
    repo_id = st.session_state.get("monitored_repo") if hasattr(st.session_state, "get") else getattr(st.session_state, "monitored_repo", "Aditya-C-S/demo-order-service")
    if not repo_id:
        repo_id = "Aditya-C-S/demo-order-service"
    
    wf2_status = st.session_state.get("wf2_status") if hasattr(st.session_state, "get") else getattr(st.session_state, "wf2_status", "idle")
    last_repo = st.session_state.get("wf2_last_discovery_repo") if hasattr(st.session_state, "get") else getattr(st.session_state, "wf2_last_discovery_repo", None)
    last_time = st.session_state.get("wf2_last_discovery_time") if hasattr(st.session_state, "get") else getattr(st.session_state, "wf2_last_discovery_time", None)
    
    # Initialize on first call with valid inputs
    if wf2_status == "idle" and last_repo is None:
        if hasattr(st.session_state, "__setitem__"):
            st.session_state["wf2_status"] = "discovering"
            st.session_state["wf2_last_discovery_repo"] = repo_id
            st.session_state["wf2_last_discovery_time"] = time.time()
        else:
            setattr(st.session_state, "wf2_status", "discovering")
            setattr(st.session_state, "wf2_last_discovery_repo", repo_id)
            setattr(st.session_state, "wf2_last_discovery_time", time.time())
        _fetch_log_runs()
        return
    
    # Update tracking
    if hasattr(st.session_state, "__setitem__"):
        st.session_state["wf2_last_discovery_repo"] = repo_id
    else:
        setattr(st.session_state, "wf2_last_discovery_repo", repo_id)
        
    now = time.time()
    last_attempt = last_time or 0
    time_since_last = now - last_attempt
    
    # Determine appropriate poll interval based on whether an active stream is in progress:
    # 2s when active running runs are in flight; 5s when resting or completed.
    is_active = (wf2_status in ["running", "analyzing"])
    interval = LIVE_POLL_INTERVAL if is_active else POLLING_INTERVAL
    
    if time_since_last >= interval:
        if hasattr(st.session_state, "__setitem__"):
            st.session_state["wf2_last_discovery_time"] = now
        else:
            setattr(st.session_state, "wf2_last_discovery_time", now)
        _fetch_log_runs()


def _safe_fragment(run_every=None):
    """Decorator helper that safely applies st.fragment if supported in the environment."""
    if hasattr(st, "fragment"):
        try:
            return st.fragment(run_every=run_every)
        except Exception:
            pass
    def _noop(fn):
        return fn
    return _noop


def _check_and_poll_for_new_runs(repo_id: str, is_valid: bool) -> bool:
    """
    Lightweight background discovery check for new CI/CD runs.
    Inspects backend runs without triggering unnecessary full-page redraws.
    Returns True if a new run, active in-flight run, or run status transition was discovered
    and an app-level rerun is required.
    """
    auto_refresh = st.session_state.get("auto_refresh_enabled", True) if hasattr(st.session_state, "get") else getattr(st.session_state, "auto_refresh_enabled", True)
    if not auto_refresh or not is_valid:
        return False
    
    current_runs = st.session_state.get("wf2_runs", []) if hasattr(st.session_state, "get") else getattr(st.session_state, "wf2_runs", [])
    has_active_in_flight = any(
        isinstance(r, dict) and r.get("status") == "running" and not is_run_stale(r) and not is_run_terminal(r)
        for r in current_runs
    )
    if has_active_in_flight:
        return False
    
    try:
        handler = LogPipelineHandler()
        is_healthy, _ = handler.check_api_health()
        if not is_healthy:
            return False
        
        runs, error = handler.find_runs_by_repo(repo_id)
        if error or not runs:
            return False
        
        known_ids = {r.get("run_id") for r in current_runs if isinstance(r, dict) and r.get("run_id")}
        
        # 1. New run ID detected
        has_new_run = any(r.get("run_id") not in known_ids for r in runs if isinstance(r, dict) and r.get("run_id"))
        
        # 2. An active running run is newly detected
        has_new_active = any(
            r.get("status") == "running" and not is_run_stale(r)
            for r in runs if isinstance(r, dict)
        )
        
        # 3. Status transition in any known run
        status_map = {r.get("run_id"): r.get("status") for r in current_runs if isinstance(r, dict)}
        has_status_change = any(
            r.get("run_id") in status_map and r.get("status") != status_map.get(r.get("run_id"))
            for r in runs if isinstance(r, dict)
        )
        
        if has_new_run or has_new_active or has_status_change:
            logger.info(
                f"Discovery poller detected pipeline update (new_run={has_new_run}, "
                f"new_active={has_new_active}, status_change={has_status_change}) on {repo_id}"
            )
            _fetch_log_runs()
            return True
            
    except Exception as e:
        logger.debug(f"Discovery check error: {e}")
        
    return False


@_safe_fragment(run_every=POLLING_INTERVAL)
def _discovery_poller_fragment(repo_id: str, is_valid: bool) -> None:
    """
    Isolated background fragment for periodic workflow discovery.
    Runs silently every POLLING_INTERVAL (5s) while the dashboard is idle or displaying completed runs.
    Because it is an st.fragment, its 5s re-evaluations do NOT cause full-page reruns, screen flickering,
    or gray buffering overlays.
    Calls st.rerun(scope='app') ONLY when a new run, active in-flight run, or status transition is detected.
    """
    should_rerun = _check_and_poll_for_new_runs(repo_id, is_valid)
    if should_rerun:
        st.rerun(scope="app")


def _handle_live_progress_polling(run_id: str) -> Optional[Dict[str, Any]]:
    """
    Poll for live progress updates on a specific run.
    """
    now = time.time()
    # Support both attribute and dictionary access for session_state
    if hasattr(st.session_state, "get"):
        last_poll = st.session_state.get("wf2_live_last_poll_time") or 0
        cached_data = st.session_state.get("wf2_live_run_data")
    else:
        last_poll = getattr(st.session_state, "wf2_live_last_poll_time", 0) or 0
        cached_data = getattr(st.session_state, "wf2_live_run_data", None)

    time_since_last = now - (last_poll or 0)
    
    cached_run_id = cached_data.get("run_id") if isinstance(cached_data, dict) else None
    is_other_run = bool(cached_run_id and cached_run_id != run_id)

    # Return cached data only if it doesn't belong to a different run and interval has not passed
    if cached_data and not is_other_run and time_since_last < LIVE_POLL_INTERVAL:
        return cached_data
    
    try:
        handler = LogPipelineHandler()
        run_data, error = handler.get_live_run_data(run_id)
        
        if error:
            logger.warning(f"Error polling live data for {run_id}: {error}")
            return cached_data if (cached_data and not is_other_run) else None
        
        if run_data:
            if hasattr(st.session_state, "__setitem__"):
                st.session_state["wf2_live_run_data"] = run_data
                st.session_state["wf2_live_last_poll_time"] = now
            else:
                setattr(st.session_state, "wf2_live_run_data", run_data)
                setattr(st.session_state, "wf2_live_last_poll_time", now)
            
            # Synchronize detailed run record in st.session_state.wf2_runs
            wf2_runs = st.session_state.get("wf2_runs") if hasattr(st.session_state, "get") else getattr(st.session_state, "wf2_runs", [])
            if wf2_runs:
                for r in wf2_runs:
                    if r.get("run_id") == run_id:
                        r.update(run_data)
                        acc_log = run_data.get("accumulated_log") or ""
                        if acc_log:
                            r["log_lines_count"] = len(acc_log.splitlines())
                        break

            if is_run_terminal(run_data):
                if hasattr(st.session_state, "__setitem__"):
                    st.session_state["wf2_live_polling_active"] = False
                    st.session_state["wf2_live_run_data"] = None
                else:
                    setattr(st.session_state, "wf2_live_polling_active", False)
                    setattr(st.session_state, "wf2_live_run_data", None)
                logger.info(f"Run {run_id} reached terminal state")
            
            return run_data
    
    except Exception as e:
        logger.error(f"Exception during live progress polling: {e}")
        return cached_data if (cached_data and not is_other_run) else None
    
    return None


def _fetch_log_runs() -> None:
    """Fetch runs from Log Pipeline backend for the monitored repository."""
    try:
        handler = LogPipelineHandler()
        
        # Check API health
        is_healthy, health_error = handler.check_api_health()
        if not is_healthy:
            st.session_state.wf2_status = "unavailable"
            st.session_state.wf2_error = health_error
            logger.error(f"Log Pipeline API health check failed: {health_error}")
            return
        
        repo_id = st.session_state.get("monitored_repo") or st.session_state.get("github_repo") or "Aditya-C-S/demo-order-service"
        commit_sha = (st.session_state.get("commit_sha") or "").strip()
        
        # Generic Repository Support: query by repo without requiring commit SHA
        if commit_sha and len(commit_sha) >= 7 and st.session_state.get("selected_workflow_page") == "Metadata + Graph RCA":
            runs, error = handler.find_runs_by_commit(repo_id, commit_sha)
        else:
            runs, error = handler.find_runs_by_repo(repo_id)
        
        if error:
            st.session_state.wf2_status = "failed"
            st.session_state.wf2_error = error
            logger.error(f"Error finding runs: {error}")
            return
        
        if not runs:
            st.session_state.wf2_status = "waiting"
            st.session_state.wf2_runs = []
            st.session_state.wf2_last_refresh = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"No runs found yet for {repo_id}")
            return
        
        # Fetch full details for each run and augment with verified provenance
        # Optimization: Reuse already-fetched details for terminal completed/failed runs to minimize polling latency
        existing_cached = {}
        if hasattr(st.session_state, "get"):
            for r in st.session_state.get("wf2_runs", []):
                if isinstance(r, dict) and r.get("status") in ("completed", "failed") and r.get("run_id"):
                    existing_cached[r["run_id"]] = r

        detailed_runs = []
        for run in runs:
            run_id = run.get("run_id")
            if not run_id:
                continue
            if run_id in existing_cached:
                detailed_runs.append(existing_cached[run_id])
            else:
                run_detail, _ = handler.get_run(run_id)
                if run_detail:
                    run_detail["provenance_info"] = classify_run_provenance(run_detail)
                    acc_log = run_detail.get("accumulated_log") or ""
                    if acc_log:
                        run_detail["log_lines_count"] = len(acc_log.splitlines())
                    detailed_runs.append(run_detail)
        
        # Sort runs: genuine active in-flight running first, then authentic completed runs,
        # then synthetic completed runs, and finally stale abandoned runs at the very bottom.
        # Within each category, sort newest to oldest.
        def _sort_key(r: dict) -> Tuple[int, int, int, str]:
            if not isinstance(r, dict):
                return (0, 0, 0, "")
            stale = is_run_stale(r)
            is_active_running = 1 if (r.get("status") == "running" and not stale) else 0
            prov = r.get("provenance_info") or {}
            is_auth = 1 if (prov.get("is_authentic") and not stale) else 0
            not_stale = 0 if stale else 1
            created = str(r.get("created_at") or "")
            return (is_active_running, is_auth, not_stale, created)
            
        detailed_runs.sort(key=_sort_key, reverse=True)
        
        st.session_state.wf2_runs = detailed_runs
        st.session_state.wf2_last_refresh = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Successfully retrieved {len(detailed_runs)} run(s)")
        
        # Auto-selection logic without unexpectedly overwriting user-selected run:
        active_running_runs = [r for r in detailed_runs if r.get("status") == "running" and not is_run_stale(r)]
        if active_running_runs:
            st.session_state.wf2_status = "running"
        else:
            st.session_state.wf2_status = "completed"

        run_ids = [r.get("run_id") for r in detailed_runs if r.get("run_id")]
        current_selected = st.session_state.wf2_selected_run_id
        user_locked = st.session_state.get("wf2_user_locked_run_id")
        auto_select_live = st.session_state.get("wf2_auto_select_live", True)
        
        # Check if currently selected run is stale
        current_run_dict = next((r for r in detailed_runs if r.get("run_id") == current_selected), None)
        current_is_stale = is_run_stale(current_run_dict) if current_run_dict else False

        top_run_id = detailed_runs[0].get("run_id") if detailed_runs else None
        top_created = (detailed_runs[0].get("created_at") or "") if detailed_runs else ""
        cur_created = (current_run_dict.get("created_at") or "") if current_run_dict else ""

        if active_running_runs and auto_select_live and (not user_locked or user_locked not in run_ids):
            # 1. An actively streaming live run takes priority when Auto-Select is enabled
            new_sel = active_running_runs[0].get("run_id")
            st.session_state.wf2_selected_run_id = new_sel
            if hasattr(st.session_state, "__setitem__"):
                st.session_state["wf2_run_selector_dropdown"] = new_sel
            else:
                setattr(st.session_state, "wf2_run_selector_dropdown", new_sel)
        elif not user_locked and auto_select_live and top_run_id and (
            not current_selected
            or current_selected not in run_ids
            or current_is_stale
            or top_created > cur_created
        ):
            # 2. When Auto-Select is enabled and user has not locked a selection, automatically surface the newest run
            st.session_state.wf2_selected_run_id = top_run_id
            if hasattr(st.session_state, "__setitem__"):
                st.session_state["wf2_run_selector_dropdown"] = top_run_id
            else:
                setattr(st.session_state, "wf2_run_selector_dropdown", top_run_id)
        elif not current_selected or current_selected not in run_ids or (current_is_stale and not user_locked):
            # 3. Fallback to top run if current selection is invalid or stale
            st.session_state.wf2_selected_run_id = top_run_id
            if hasattr(st.session_state, "__setitem__"):
                st.session_state["wf2_run_selector_dropdown"] = top_run_id
            else:
                setattr(st.session_state, "wf2_run_selector_dropdown", top_run_id)

        # Invalidate live streaming state if all retrieved runs are terminal
        if detailed_runs and all(is_run_terminal(r) for r in detailed_runs):
            if hasattr(st.session_state, "__setitem__"):
                st.session_state["wf2_live_run_data"] = None
                st.session_state["wf2_live_polling_active"] = False
            else:
                setattr(st.session_state, "wf2_live_run_data", None)
                setattr(st.session_state, "wf2_live_polling_active", False)
        
    except Exception as e:
        # Do NOT permanently block discovery: preserve existing runs so the UI stays
        # responsive and the auto-refresh rerun loop can retry on the next poll tick.
        # Only switch to "failed" status if we have no runs to show.
        logger.exception(f"Unexpected error fetching runs: {e}")
        if not st.session_state.get("wf2_runs"):
            st.session_state.wf2_status = "failed"
            st.session_state.wf2_error = str(e)
        # else: keep existing runs and status so the dashboard stays usable


def _fetch_log_runs_manual() -> None:
    """Manual retry of run discovery (triggered by button)."""
    st.session_state.wf2_last_discovery_time = 0  # Force immediate retry
    _fetch_log_runs()
    st.rerun()


def render_wf2_runs(runs: List[Dict[str, Any]]) -> None:
    """Render list of CI runs with enhanced filtering, provenance identification, and details."""
    
    if not runs:
        st.info("No CI runs found for this repository and commit", icon="ℹ️")
        return
    
    # Calculate counts
    auth_runs = [r for r in runs if isinstance(r, dict) and (r.get("provenance_info") or {}).get("is_authentic")]
    synth_runs = [r for r in runs if isinstance(r, dict) and not (r.get("provenance_info") or {}).get("is_authentic")]
    fail_runs = [r for r in runs if isinstance(r, dict) and (((r.get("ci_execution") or {}).get("workflow_outcome") or r.get("actual_outcome")) == "failure")]
    succ_runs = [r for r in runs if isinstance(r, dict) and (((r.get("ci_execution") or {}).get("workflow_outcome") or r.get("actual_outcome")) == "success")]

    st.markdown(f"### 🧪 CI Run Discovery ({len(runs)} Available)")
    
    # Check for genuine in-flight running runs and notify if viewing another run
    running_runs = [r for r in runs if isinstance(r, dict) and r.get("status") == "running" and not is_run_stale(r)]
    cur_sel_id = st.session_state.get("wf2_selected_run_id") if hasattr(st.session_state, "get") else getattr(st.session_state, "wf2_selected_run_id", None)
    if running_runs and cur_sel_id != running_runs[0].get("run_id"):
        active_r = running_runs[0]
        active_ci = (active_r.get("ci_execution") or {}).get("ci_run_id") or "In-Flight"
        act_repo = (active_r.get("commit_info") or {}).get("repo_id") or active_r.get("repo_id") or (st.session_state.get("monitored_repo") if hasattr(st.session_state, "get") else getattr(st.session_state, "monitored_repo", "N/A"))
        act_lines = active_r.get("log_lines_count", 0)
        try:
            act_lines = int(act_lines)
        except (TypeError, ValueError):
            act_lines = 0
        act_pred = active_r.get("current_runtime_prediction") or {}
        act_prob = _safe_prob_pct(act_pred)
        act_prob_str = f"{act_prob:.1f}%" if act_prob is not None else "Analyzing..."
        act_tier = act_pred.get("risk_tier", "MONITORING")
        
        with st.container():
            st.markdown(
                f"<div style='background-color: #1e293b; border-left: 4px solid #3b82f6; padding: 12px 16px; border-radius: 6px; margin-bottom: 12px;'>"
                f"<div style='display: flex; justify-content: space-between; align-items: center;'>"
                f"<span style='font-size: 14px; font-weight: bold; color: #60a5fa;'>🔴 ACTIVE LIVE PIPELINE IN PROGRESS</span>"
                f"<span style='background-color: #2563eb; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;'>MONITORING ACTIVE</span>"
                f"</div>"
                f"<div style='font-size: 13px; color: #e2e8f0; margin-top: 6px;'>"
                f"<b>Repository:</b> <code>{act_repo}</code> &nbsp;|&nbsp; "
                f"<b>GitHub Actions Run ID:</b> <code>#{active_ci}</code> &nbsp;|&nbsp; "
                f"<b>Backend Run ID:</b> <code>{active_r.get('run_id')}</code>"
                f"</div>"
                f"<div style='font-size: 12px; color: #94a3b8; margin-top: 4px;'>"
                f"Status: <span style='color: #fbbf24; font-weight: bold;'>RUNNING</span> &nbsp;•&nbsp; "
                f"Telemetry: <b>{act_lines:,} lines</b> &nbsp;•&nbsp; "
                f"In-Flight Risk: <b>{act_prob_str}</b> ({act_tier})"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True
            )
            col_b1, col_b2 = st.columns([5, 1])
            with col_b2:
                if st.button("🔴 View Live Run", key="btn_switch_to_active_live", use_container_width=True):
                    live_id = active_r.get("run_id")
                    if hasattr(st.session_state, "__setitem__"):
                        st.session_state["wf2_selected_run_id"] = live_id
                        st.session_state["wf2_run_selector_dropdown"] = live_id
                        st.session_state["wf2_user_locked_run_id"] = None
                        st.session_state["wf2_live_run_data"] = None
                    else:
                        setattr(st.session_state, "wf2_selected_run_id", live_id)
                        setattr(st.session_state, "wf2_run_selector_dropdown", live_id)
                        setattr(st.session_state, "wf2_user_locked_run_id", None)
                        setattr(st.session_state, "wf2_live_run_data", None)
                    st.rerun()

    # Header summary badges
    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
    with mcol1:
        st.metric("Total Runs", len(runs))
    with mcol2:
        st.metric("Authentic Runs", len(auth_runs))
    with mcol3:
        st.metric("Failed Runs", len(fail_runs))
    with mcol4:
        st.metric("Successful Runs", len(succ_runs))

    # Provenance and outcome filters
    fcol1, fcol2 = st.columns(2)
    with fcol1:
        prov_filter = st.selectbox(
            "Filter Data Source:",
            options=["All Sources", "🟢 Authentic GitHub Actions Only", "🔵 Public GitHub Repo (API Fallback)", "🟠 Local Demo / Synthetic Only"],
            key="wf2_prov_filter"
        )
    with fcol2:
        outcome_filter = st.selectbox(
            "Filter CI Outcome:",
            options=["All Outcomes", "❌ Failures Only", "✅ Successes Only"],
            key="wf2_outcome_filter"
        )

    # Apply filters
    filtered_runs = []
    for r in runs:
        if not isinstance(r, dict):
            continue
        prov = r.get("provenance_info") or {}
        outcome = ((r.get("ci_execution") or {}).get("workflow_outcome") or r.get("actual_outcome") or "pending").lower()
        cat = str(prov.get("category") or "")
        
        if prov_filter == "🟢 Authentic GitHub Actions Only" and (not prov.get("is_authentic") or "API FALLBACK" in cat):
            continue
        if prov_filter == "🔵 Public GitHub Repo (API Fallback)" and "API FALLBACK" not in cat:
            continue
        if prov_filter == "🟠 Local Demo / Synthetic Only" and prov.get("is_authentic"):
            continue
            
        if outcome_filter == "❌ Failures Only" and outcome != "failure":
            continue
        if outcome_filter == "✅ Successes Only" and outcome != "success":
            continue
            
        filtered_runs.append(r)

    if not filtered_runs:
        st.warning("⚠️ No runs match the selected filters. Please adjust the filters above.", icon="⚠️")
        return

    # Prominent notification if only synthetic runs are available
    if not auth_runs:
        st.info(
            "ℹ️ Notice: No authentic GitHub Actions runs found for this repository. Displaying local demo / synthetic executions.",
            icon="ℹ️"
        )

    # Format run selection options
    def _format_run_label(r: Dict[str, Any]) -> str:
        if not isinstance(r, dict):
            return "Invalid Run"
        prov = r.get("provenance_info") or {}
        cat = str(prov.get("category") or "")
        if "API FALLBACK" in cat:
            prov_tag = "🔵 API FALLBACK"
        elif prov.get("is_authentic"):
            prov_tag = "🟢 LIVE STREAM"
        else:
            prov_tag = "🟠 SYNTHETIC"
        
        status = str(r.get("status") or "")
        ci_exec = r.get("ci_execution") or {}
        outcome = str(ci_exec.get("workflow_outcome") or r.get("actual_outcome") or "pending").upper()
        
        if is_run_stale(r):
            outcome_tag = "⚠️ STALE / ABANDONED"
        elif status == "running":
            outcome_tag = "🔄 LIVE RUNNING"
        elif outcome == "SUCCESS":
            outcome_tag = "✅ SUCCESS"
        elif outcome == "FAILURE":
            outcome_tag = "❌ FAILURE"
        else:
            outcome_tag = "⏳ PENDING"

        lines_val = r.get("log_lines_count") or 0
        try:
            lines = int(lines_val)
        except (TypeError, ValueError):
            lines = 0
        rid = str(r.get("run_id") or "")
        short_id = rid[-6:] if len(rid) >= 6 else rid
        ci_id = ci_exec.get("ci_run_id")
        ci_tag = f"CI #{ci_id}" if ci_id else "Replayed Logs"
        created = str(r.get("created_at") or "")[:19].replace("T", " ")
        model = str(r.get("runtime_model") or "bilstm")
        return f"[{prov_tag}] [{outcome_tag}] Run ...{short_id} ({lines:,} lines | {ci_tag} | {model} | {created})"

    run_options = {r["run_id"]: _format_run_label(r) for r in filtered_runs if isinstance(r, dict) and r.get("run_id")}
    run_ids = list(run_options.keys())

    # Ensure selected run is valid
    cur_sel_id = st.session_state.get("wf2_selected_run_id") if hasattr(st.session_state, "get") else getattr(st.session_state, "wf2_selected_run_id", None)
    if cur_sel_id not in run_ids:
        cur_sel_id = run_ids[0]
        if hasattr(st.session_state, "__setitem__"):
            st.session_state["wf2_selected_run_id"] = cur_sel_id
            st.session_state["wf2_run_selector_dropdown"] = cur_sel_id
        else:
            setattr(st.session_state, "wf2_selected_run_id", cur_sel_id)
            setattr(st.session_state, "wf2_run_selector_dropdown", cur_sel_id)
    elif hasattr(st.session_state, "get") and st.session_state.get("wf2_run_selector_dropdown") != cur_sel_id:
        if hasattr(st.session_state, "__setitem__"):
            st.session_state["wf2_run_selector_dropdown"] = cur_sel_id
        else:
            setattr(st.session_state, "wf2_run_selector_dropdown", cur_sel_id)

    selected_index = run_ids.index(cur_sel_id)

    def _on_run_selector_change():
        chosen = st.session_state.get("wf2_run_selector_dropdown")
        if chosen:
            if hasattr(st.session_state, "__setitem__"):
                st.session_state["wf2_selected_run_id"] = chosen
                st.session_state["wf2_user_locked_run_id"] = chosen
                st.session_state["wf2_live_run_data"] = None
            else:
                setattr(st.session_state, "wf2_selected_run_id", chosen)
                setattr(st.session_state, "wf2_user_locked_run_id", chosen)
                setattr(st.session_state, "wf2_live_run_data", None)

    selected_run_id = st.selectbox(
        "Select Run for Analysis:",
        options=run_ids,
        index=selected_index,
        format_func=lambda x: run_options[x],
        key="wf2_run_selector_dropdown",
        on_change=_on_run_selector_change
    )
    if selected_run_id != cur_sel_id:
        if hasattr(st.session_state, "__setitem__"):
            st.session_state["wf2_selected_run_id"] = selected_run_id
            st.session_state["wf2_user_locked_run_id"] = selected_run_id
            st.session_state["wf2_live_run_data"] = None
        else:
            setattr(st.session_state, "wf2_selected_run_id", selected_run_id)
            setattr(st.session_state, "wf2_user_locked_run_id", selected_run_id)
            setattr(st.session_state, "wf2_live_run_data", None)

    # Single source of truth: selected_run strictly derives from the chosen run ID
    effective_run_id = selected_run_id or cur_sel_id
    selected_run = next((r for r in filtered_runs if isinstance(r, dict) and r.get("run_id") == effective_run_id), filtered_runs[0])

    # Public Repository Fallback: GitHub REST API Discovery Expander
    with st.expander("🌐 Public Repository GitHub API Discovery (Zero-Install Post-Run Fallback)", expanded=False, key="wf2_exp_github_api_discovery"):
        mon_repo = st.session_state.get("monitored_repo") or "Aditya-C-S/CI-CD-Failure-Predictor-"
        st.markdown(f"Discover and import runs from **`{mon_repo}`** directly via GitHub REST API without installing runner scripts.")
        dcol1, dcol2 = st.columns([3, 1])
        with dcol1:
            api_repo_input = st.text_input("Repository (owner/repo):", value=mon_repo, key="gha_api_repo_input")
        with dcol2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            fetch_api_btn = st.button("🔍 Discover Runs", key="btn_fetch_github_api", use_container_width=True)

        if fetch_api_btn:
            handler = LogPipelineHandler()
            with st.spinner(f"Querying GitHub Actions API for {api_repo_input}..."):
                gh_runs, gh_err = handler.discover_github_runs(api_repo_input, limit=10)
                if gh_err:
                    st.error(f"Failed to query GitHub API: {gh_err}")
                else:
                    st.session_state.wf2_github_discovered_runs = gh_runs or []

        discovered = st.session_state.get("wf2_github_discovered_runs", [])
        if discovered and isinstance(discovered, list):
            st.markdown(f"Found **{len(discovered)}** recent GitHub Actions runs on `{api_repo_input}`:")
            for gr in discovered:
                if not isinstance(gr, dict):
                    continue
                gcol1, gcol2, gcol3, gcol4 = st.columns([2, 3, 2, 2])
                with gcol1:
                    st.markdown(f"**Run #{gr.get('id', '?')}**")
                    st.caption(f"{gr.get('event', 'push')} on `{gr.get('head_branch', 'main')}`")
                with gcol2:
                    st.markdown(f"*{gr.get('name', 'Workflow')}*")
                    st.caption(f"SHA: `{str(gr.get('head_sha') or '')[:7]}`")
                with gcol3:
                    concl = str(gr.get('conclusion') or gr.get('status') or 'unknown').upper()
                    c_icon = "✅" if concl == "SUCCESS" else "❌" if concl == "FAILURE" else "🔄"
                    st.markdown(f"{c_icon} `{concl}`")
                    st.caption(f"{str(gr.get('created_at') or '')[:19].replace('T', ' ')}")
                with gcol4:
                    if st.button("📥 Import Run", key=f"btn_import_gh_{gr.get('id', 'x')}", use_container_width=True):
                        handler = LogPipelineHandler()
                        with st.spinner(f"Importing run #{gr.get('id')} from GitHub API..."):
                            imported, imp_err = handler.import_github_run(api_repo_input, gr.get('id', ''))
                            if imp_err:
                                st.error(f"Failed to import: {imp_err}")
                            else:
                                st.success(f"Successfully imported run #{gr.get('id')}!")
                                st.session_state.monitored_repo = api_repo_input
                                if isinstance(imported, dict) and imported.get("run_id"):
                                    st.session_state.wf2_selected_run_id = imported.get("run_id")
                                    st.session_state.wf2_user_locked_run_id = imported.get("run_id")
                                _fetch_log_runs_manual()

    st.markdown("---")
    # Wrap render_run_details in a top-level guard so that any rendering exception
    # (TypeError, AttributeError, etc.) shows an inline error instead of crashing the
    # entire Streamlit script and halting the auto-refresh rerun loop.
    try:
        render_run_details(selected_run)
    except Exception as _detail_exc:
        logger.exception(f"render_run_details crashed for run {selected_run.get('run_id') if isinstance(selected_run, dict) else '?'}: {_detail_exc}")
        st.error(
            f"⚠️ **Rendering error for run `{selected_run.get('run_id', '?') if isinstance(selected_run, dict) else '?'}`:** {_detail_exc}\n\n"
            "The dashboard remains active and will continue polling for new runs.",
            icon="❌",
        )


def _safe_prob_pct(d_pred: Any) -> Optional[float]:
    """
    Safely extract failure probability percentage from a prediction dictionary,
    numeric value, or string. Never raises an exception.
    
    Rules:
      - Returns None if input is None, unparseable, or missing both prob fields.
      - Never silently turns a genuinely missing probability into 0.0%.
      - Distinguishes fractions (<=1.0 -> multiplied by 100) from percentages (>1.0 -> pass-through).
      - Handles strings like '91.21' or '91.21%'.
      - Bounds valid output to [0.0, 100.0].
    """
    if d_pred is None:
        return None
    if isinstance(d_pred, (int, float)):
        v = float(d_pred)
        res = v * 100.0 if v <= 1.0 else v
        return max(0.0, min(100.0, res))
    if isinstance(d_pred, str):
        try:
            s = d_pred.replace("%", "").strip()
            v = float(s)
            res = v * 100.0 if v <= 1.0 else v
            return max(0.0, min(100.0, res))
        except (TypeError, ValueError):
            return None
    if not isinstance(d_pred, dict):
        return None

    pct = d_pred.get("failure_probability_pct")
    if pct is not None:
        try:
            s = str(pct).replace("%", "").strip()
            v = float(s)
            return max(0.0, min(100.0, v))
        except (TypeError, ValueError):
            pass

    raw = d_pred.get("failure_probability")
    if raw is None:
        return None
    try:
        s = str(raw).replace("%", "").strip()
        v = float(s)
        res = v * 100.0 if v <= 1.0 else v
        return max(0.0, min(100.0, res))
    except (TypeError, ValueError):
        return None


def _resolve_checkpoint_data(run: dict) -> Tuple[Dict[int, Dict[str, Any]], int, List[int], Optional[int]]:
    """
    Resolve checkpoint statuses across 25%, 50%, 75%, 100% with rigorous semantics:
    - Only genuinely executed and confirmed milestones count as verified.
    - A projected checkpoint must never be counted as an actual checkpoint.
    - A checkpoint after an early pipeline failure must be labelled SKIPPED or NOT REACHED, not CONFIRMED.
    - Missing probability must display N/A.
    - Returns (checkpoints_data, completed_count, confirmed_depths, failure_depth).
    """
    if not isinstance(run, dict):
        empty_data = {
            d: {
                "depth": d, "type": "NONE", "prob_pct": None, "raw_prob_pct": None,
                "label": "N/A", "risk": "N/A", "confirmed": False, "status_text": "⚪ Not reached", "basis": None
            } for d in [25, 50, 75, 100]
        }
        return empty_data, 0, [], None

    ci_exec = run.get("ci_execution") or {}
    actual_outcome = str(ci_exec.get("workflow_outcome") or run.get("actual_outcome") or "pending").lower()
    is_failed_run = (actual_outcome == "failure")
    run_status = str(run.get("status") or "pending").lower()
    
    prov = classify_run_provenance(run)
    is_synthetic = prov.get("is_synthetic", False)

    pred_history = (run.get('runtime_predictions') or []) if isinstance(run.get('runtime_predictions'), list) else []
    raw_projections = run.get('checkpoint_projections')
    
    projections_by_depth: Dict[int, Dict[str, Any]] = {}
    if isinstance(raw_projections, dict):
        for k, v in raw_projections.items():
            try:
                k_int = int(float(k))
                if k_int in [25, 50, 75, 100] and isinstance(v, dict):
                    projections_by_depth[k_int] = v
            except (TypeError, ValueError):
                pass
    elif isinstance(raw_projections, list):
        for p in raw_projections:
            if isinstance(p, dict):
                raw_dp = p.get('depth_percentage')
                try:
                    dp = int(float(raw_dp)) if raw_dp is not None else None
                    if dp in [25, 50, 75, 100]:
                        projections_by_depth[dp] = p
                except (TypeError, ValueError):
                    pass

    actuals_by_depth: Dict[int, Dict[str, Any]] = {}
    for p in pred_history:
        if not isinstance(p, dict):
            continue
        raw_dp = p.get('checkpoint', p.get('depth_percentage'))
        try:
            dp = int(float(raw_dp)) if raw_dp is not None else None
        except (TypeError, ValueError):
            dp = None
        if dp in [25, 50, 75, 100]:
            is_proj = p.get('is_projected', False) or p.get('prediction_type') == 'PROJECTED'
            if is_proj:
                continue
            prob = _safe_prob_pct(p)
            if prob is not None:
                actuals_by_depth[dp] = p
            elif is_synthetic and run_status == "completed" and actual_outcome == "success":
                actuals_by_depth[dp] = p

    failure_depth: Optional[int] = None
    if is_failed_run:
        curr_pred = run.get('current_runtime_prediction')
        if isinstance(curr_pred, dict):
            raw_cd = curr_pred.get('depth_percentage') or curr_pred.get('checkpoint')
            try:
                cd_int = int(float(raw_cd)) if raw_cd is not None else None
                if cd_int in [25, 50, 75, 100]:
                    failure_depth = cd_int
            except (TypeError, ValueError):
                pass
        if failure_depth is None:
            actual_depths_with_prob = [d for d in [25, 50, 75, 100] if d in actuals_by_depth]
            failure_depth = max(actual_depths_with_prob) if actual_depths_with_prob else 25

    checkpoints_data: Dict[int, Dict[str, Any]] = {}
    for d in [25, 50, 75, 100]:
        if is_failed_run and failure_depth is not None and d > failure_depth:
            proj_entry = projections_by_depth.get(d)
            if proj_entry and isinstance(proj_entry, dict):
                prob_val = _safe_prob_pct(proj_entry)
                basis_raw = proj_entry.get("projection_basis_pct")
                try:
                    basis_val = float(basis_raw) if basis_raw is not None else None
                except (TypeError, ValueError):
                    basis_val = None
                basis_text = f" (from {basis_val:.0f}%)" if basis_val is not None else ""
                checkpoints_data[d] = {
                    "depth": d,
                    "type": "PROJECTED",
                    "prob_pct": prob_val,
                    "raw_prob_pct": None,
                    "label": (
                        "FAILURE (Projected)" if (prob_val is not None and prob_val >= 50)
                        else ("SUCCESS (Projected)" if prob_val is not None else "N/A")
                    ),
                    "risk": proj_entry.get("risk_tier", "HIGH RISK" if (prob_val is not None and prob_val >= 50) else "LOW RISK"),
                    "confirmed": False,
                    "status_text": f"⚠️ Projected{basis_text} (Run failed at {failure_depth}% — not executed)",
                    "basis": basis_val,
                }
            else:
                checkpoints_data[d] = {
                    "depth": d,
                    "type": "SKIPPED",
                    "prob_pct": None,
                    "raw_prob_pct": None,
                    "label": "NOT REACHED",
                    "risk": "N/A",
                    "confirmed": False,
                    "status_text": f"⏭️ Skipped (Pipeline failed at {failure_depth}%)",
                    "basis": None,
                }
        elif d in actuals_by_depth:
            act = actuals_by_depth[d]
            raw_prob = act.get("raw_failure_probability")
            try:
                raw_pct = (float(raw_prob) * 100.0) if raw_prob is not None else None
            except (TypeError, ValueError):
                raw_pct = None
            prob_pct = _safe_prob_pct(act)
            checkpoints_data[d] = {
                "depth": d,
                "type": "EVALUATED",
                "prob_pct": prob_pct,
                "raw_prob_pct": raw_pct,
                "label": act.get("predicted_label", "unknown").upper() if prob_pct is not None else "N/A",
                "risk": act.get("risk_tier", "LOW RISK" if (prob_pct is not None and prob_pct < 40) else "HIGH RISK"),
                "confirmed": True,
                "status_text": "✅ Model inference on available log slice",
                "basis": None,
            }
        elif d in projections_by_depth:
            proj_entry = projections_by_depth[d]
            p_type = proj_entry.get("type", "PROJECTED")
            prob_val = _safe_prob_pct(proj_entry)
            is_proj = proj_entry.get("is_projected", True)
            if p_type in ("ACTUAL", "EVALUATED") and not is_proj:
                checkpoints_data[d] = {
                    "depth": d,
                    "type": "EVALUATED",
                    "prob_pct": prob_val,
                    "raw_prob_pct": None,
                    "label": proj_entry.get("predicted_label", "unknown").upper() if prob_val is not None else "N/A",
                    "risk": proj_entry.get("risk_tier", "LOW RISK"),
                    "confirmed": True,
                    "status_text": "✅ Model inference on available log slice",
                    "basis": None,
                }
            else:
                basis_raw = proj_entry.get("projection_basis_pct")
                try:
                    basis_val = float(basis_raw) if basis_raw is not None else None
                except (TypeError, ValueError):
                    basis_val = None
                basis_text = f" (from {basis_val:.0f}%)" if basis_val is not None else ""
                checkpoints_data[d] = {
                    "depth": d,
                    "type": "PROJECTED",
                    "prob_pct": prob_val,
                    "raw_prob_pct": None,
                    "label": (
                        "FAILURE (Projected)" if (prob_val is not None and prob_val >= 50)
                        else ("SUCCESS (Projected)" if prob_val is not None else "N/A")
                    ),
                    "risk": proj_entry.get("risk_tier", "LOW RISK"),
                    "confirmed": False,
                    "status_text": f"⚠️ Projected{basis_text}",
                    "basis": basis_val,
                }
        else:
            status_text = f"⏳ Awaiting log data for {d}% depth" if run_status == "running" else "⚪ Not reached"
            checkpoints_data[d] = {
                "depth": d,
                "type": "NONE",
                "prob_pct": None,
                "raw_prob_pct": None,
                "label": "Awaiting Log Data" if run_status == "running" else "NOT REACHED",
                "risk": "N/A",
                "confirmed": False,
                "status_text": status_text,
                "basis": None,
            }

    confirmed_depths = [d for d in [25, 50, 75, 100] if checkpoints_data[d]["confirmed"]]
    completed_checkpoints = len(confirmed_depths)
    
    return checkpoints_data, completed_checkpoints, confirmed_depths, failure_depth


def render_run_details(run: dict) -> None:
    """Render comprehensive log analysis for a single run."""
    if not isinstance(run, dict):
        st.warning("Invalid run details record.", icon="⚠️")
        return

    run_id = run.get("run_id") or "N/A"
    
    # Authoritative terminal status determination
    terminal = is_run_terminal(run)
    
    # If currently considered running, poll live progress
    if not terminal and run_id and run_id != "N/A":
        try:
            live_data = _handle_live_progress_polling(run_id)
            if isinstance(live_data, dict) and live_data.get("run_id") == run_id:
                if is_run_terminal(live_data):
                    run.update(live_data)
                    terminal = True
                    if hasattr(st.session_state, "__setitem__"):
                        st.session_state["wf2_live_polling_active"] = False
                        st.session_state["wf2_live_run_data"] = None
                    else:
                        setattr(st.session_state, "wf2_live_polling_active", False)
                        setattr(st.session_state, "wf2_live_run_data", None)
                    wf2_runs = st.session_state.get("wf2_runs") if hasattr(st.session_state, "get") else getattr(st.session_state, "wf2_runs", [])
                    if wf2_runs:
                        for r in wf2_runs:
                            if r.get("run_id") == run_id:
                                r.update(live_data)
                                break
                else:
                    run = live_data
        except Exception as e:
            logger.error(f"Error during live progress polling: {e}")

    # If the run is terminal, invalidate active live polling state so stale streaming predictions cannot leak
    if terminal:
        if hasattr(st.session_state, "__setitem__"):
            st.session_state["wf2_live_run_data"] = None
            st.session_state["wf2_live_polling_active"] = False
        else:
            setattr(st.session_state, "wf2_live_run_data", None)
            setattr(st.session_state, "wf2_live_polling_active", False)

    run_status = str(run.get("status") or "unknown").lower()
    run_is_stale = is_run_stale(run)
    
    commit_info = run.get("commit_info") or {}
    ci_exec = run.get("ci_execution") or {}
    repo_name = commit_info.get("repo_id") or run.get("repo_id") or st.session_state.get("monitored_repo", "N/A")
    ci_run_id_val = ci_exec.get("ci_run_id") or "N/A (Replayed Authentic Telemetry)"
    
    prov = run.get("provenance_info") or classify_run_provenance(run)
    log_lines_count = run.get("log_lines_count")
    try:
        log_lines_count = int(log_lines_count) if log_lines_count is not None else 0
    except (TypeError, ValueError):
        log_lines_count = 0
    acc_log_content = run.get("accumulated_log") or ""
    if acc_log_content and isinstance(acc_log_content, str):
        actual_lines = len(acc_log_content.splitlines())
        if actual_lines > log_lines_count or log_lines_count == 0:
            log_lines_count = actual_lines

    # =========================================================================
    # CASE 1: ACTIVELY RUNNING LIVE PIPELINE (LIVE MONITORING VIEW)
    # Only rendered when run is actively in-flight and NOT terminal!
    # =========================================================================
    if not terminal:
        st.markdown(
            f"<div style='background-color: #1e293b; border-left: 4px solid #ef4444; padding: 14px 18px; border-radius: 6px; margin-bottom: 14px;'>"
            f"<div style='display: flex; justify-content: space-between; align-items: center;'>"
            f"<span style='font-size: 15px; font-weight: bold; color: #f87171;'>🔴 LIVE CI/CD PIPELINE MONITOR</span>"
            f"<span style='background-color: #ef4444; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;'>STREAMING</span>"
            f"</div>"
            f"<div style='font-size: 13px; color: #f1f5f9; margin-top: 6px;'>"
            f"<b>Repository:</b> <code>{repo_name}</code> &nbsp;|&nbsp; "
            f"<b>GitHub Actions Run ID:</b> <code>#{ci_run_id_val}</code> &nbsp;|&nbsp; "
            f"<b>Backend Run ID:</b> <code>{run_id}</code>"
            f"</div>"
            f"<div style='font-size: 12px; color: #94a3b8; margin-top: 4px;'>"
            f"<b>Branch:</b> <code>{commit_info.get('branch', 'main')}</code> &nbsp;•&nbsp; "
            f"<b>SHA:</b> <code>{str(commit_info.get('commit_sha', 'N/A'))[:7]}</code> &nbsp;•&nbsp; "
            f"<b>Source:</b> {prov.get('badge', 'UNKNOWN')} &nbsp;•&nbsp; "
            f"<b>Received Logs:</b> <b>{log_lines_count:,} lines</b>"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True
        )

        try:
            render_live_progress_section(run)
        except Exception as e:
            logger.error(f"Error rendering live progress section: {e}")
            st.warning(f"Could not display live progress: {str(e)}", icon="⚠️")

        # Live Real-Time Logs Viewer
        with st.expander(f"📄 Real-Time Streaming Logs ({log_lines_count:,} Lines Received)", expanded=True, key=f"wf2_exp_live_stream_{run_id}"):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.caption("Live streaming logs from runner telemetry.")
            with col2:
                st.metric("Lines Received", f"{log_lines_count:,}")
            if acc_log_content:
                lines = acc_log_content.splitlines()
                preview_lines = lines[-100:] if len(lines) > 100 else lines
                st.text_area(
                    f"Live Log Stream (most recent {len(preview_lines)} of {len(lines):,} lines):",
                    value="\n".join(preview_lines),
                    height=280,
                    disabled=True,
                    key=f"live_stream_view_{run_id}"
                )
            else:
                st.info("Awaiting initial log chunk from runner...", icon="⏳")

        # Clear pending notice explaining why terminal results are not shown yet
        st.info(
            "⏳ **Pipeline Execution in Progress:** Live predictions, intermediate checkpoints, and log streams update automatically every 2 seconds. "
            "Final results, verified checkpoint comparison, Root Cause Analysis (RCA), and remediation guidance will appear here automatically once the pipeline concludes.",
            icon="ℹ️"
        )
        return  # CRITICAL: Stop rendering here! Do NOT render terminal sections for an active run!

    # =========================================================================
    # CASE 2: TERMINAL RUN (COMPLETED / FAILED / CANCELLED / STALE)
    # =========================================================================
    if run_status == "running" and run_is_stale:
        st.warning(
            "⚠️ **Run Inactive / Abandoned:** This execution stopped receiving log chunks more than 15 minutes ago without sending a completion signal. Displaying last captured state.",
            icon="⚠️"
        )

    # Resolve checkpoints and metadata
    checkpoints_data, completed_checkpoints, confirmed_depths, failure_depth = _resolve_checkpoint_data(run)
    actual_outcome = str(ci_exec.get("workflow_outcome") or run.get("actual_outcome") or "pending").lower()

    # =========================================================================
    # A. CI Run Overview (Complete 10-Field Metadata)
    # =========================================================================
    with st.expander("📋 CI Run Overview", expanded=True, key=f"wf2_exp_overview_{run_id}"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"**Repository:** `{commit_info.get('repo_id', 'N/A')}`")
            st.markdown(f"**Commit SHA:** `{commit_info.get('commit_sha', 'N/A')}`")
            st.markdown(f"**Run ID:** `{run.get('run_id', 'N/A')}`")
            ci_run_id_val = ci_exec.get("ci_run_id") or "N/A (Replayed Authentic Telemetry)"
            st.markdown(f"**GitHub Actions Run ID:** `{ci_run_id_val}`")
            st.markdown(f"**Branch:** `{commit_info.get('branch', 'main')}`")
        
        with col2:
            status = str(run.get('status') or 'pending')
            status_icon = "✅" if status == "completed" else "🔄" if status == "running" else "❌"
            st.markdown(f"**Execution Status:** {status_icon} `{status.upper()}`")
            
            outcome_icon = "✅" if actual_outcome == "success" else "❌" if actual_outcome == "failure" else "⏳"
            st.markdown(f"**Actual CI Outcome:** {outcome_icon} `{actual_outcome.upper()}`")
            
            started_val = ci_exec.get("started_at") or run.get("created_at") or "N/A"
            st.markdown(f"**Start Time:** `{started_val}`")
            st.markdown(f"**Log Line Count:** **{log_lines_count:,} lines**")
            
            st.markdown(f"**Data Source:** **{prov.get('badge', 'UNKNOWN')}**")
            st.caption(f"ℹ️ *{prov.get('reason', '')}*")
        
        # Checkpoint progress bar
        if failure_depth is not None and completed_checkpoints < 4:
            progress_text = f"Log Checkpoints Verified: {completed_checkpoints}/4 ({', '.join([str(k) + '%' for k in confirmed_depths]) or 'None'}) — Pipeline halted at {failure_depth}%"
        else:
            progress_text = f"Log Checkpoints Verified: {completed_checkpoints}/4 ({', '.join([str(k) + '%' for k in confirmed_depths]) or 'None'})"
        st.progress(completed_checkpoints / 4.0, text=progress_text)
    
    # =========================================================================
    # B. Runtime Failure Prediction (Final Verified Prediction)
    # =========================================================================
    current_pred = run.get('current_runtime_prediction')
    pred_history = (run.get('runtime_predictions') or []) if isinstance(run.get('runtime_predictions'), list) else []
    final_pred = None
    for p in reversed(pred_history):
        if isinstance(p, dict) and p.get("prediction_type") in ("ACTUAL", "FINAL_ACTUAL") and not p.get("is_projected"):
            final_pred = p
            break
    if not final_pred and isinstance(current_pred, dict):
        final_pred = current_pred
        
    if isinstance(final_pred, dict) and final_pred:
        with st.expander("⚡ Runtime Failure Prediction", expanded=True, key=f"wf2_exp_pred_{run_id}"):
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                prob_val = _safe_prob_pct(final_pred)
                prob_disp = f"{prob_val:.1f}%" if prob_val is not None else "N/A"
                st.metric("Failure Probability", prob_disp)
            
            with col2:
                pred_label = str(final_pred.get('predicted_label') or 'unknown').upper()
                st.metric("Predicted Label", pred_label)
            
            with col3:
                risk_tier = str(final_pred.get('risk_tier') or 'UNKNOWN')
                st.metric("Risk Tier", risk_tier)
            
            with col4:
                evidence = str(final_pred.get('evidence_strength_label') or final_pred.get('evidence_strength') or 'UNKNOWN')
                st.metric("Evidence Strength", evidence)
            
            col1, col2 = st.columns(2)
            with col1:
                model_name = (
                    final_pred.get('model_name')
                    or final_pred.get('model')
                    or final_pred.get('model_id')
                    or run.get('runtime_model')
                    or 'bilstm2'
                )
                st.markdown(f"**Runtime Model:** `{model_name}`")
                log_lines = final_pred.get('total_lines') or final_pred.get('log_lines_count') or log_lines_count
                try:
                    log_lines_safe = int(log_lines) if log_lines is not None else 0
                except (TypeError, ValueError):
                    log_lines_safe = 0
                st.markdown(f"**Log Lines Analyzed:** {log_lines_safe:,}")
            
            with col2:
                depth_raw = final_pred.get('depth_percentage')
                try:
                    depth = int(float(depth_raw)) if depth_raw is not None else 100
                except (TypeError, ValueError):
                    depth = 100
                st.markdown(f"**Pipeline Depth:** {depth}%")
                timestamp = final_pred.get('timestamp', '')
                if timestamp:
                    st.markdown(f"**Timestamp:** `{timestamp}`")
    
    # =========================================================================
    # C. Checkpoint Progression (Proper UI for 25%, 50%, 75%, 100%)
    # =========================================================================
    with st.expander("📈 Checkpoint Progression (Multi-Stage Log Visibility)", expanded=True, key=f"wf2_exp_checkpoints_{run_id}"):
        # Render 4 side-by-side checkpoint cards
        c_cols = st.columns(4)
        for idx, d in enumerate([25, 50, 75, 100]):
            with c_cols[idx]:
                cd = checkpoints_data[d]
                if cd["type"] in ("ACTUAL", "EVALUATED"):
                    st.markdown(f"#### 🟢 {d}% Checkpoint")
                    prob_pct_val = cd['prob_pct']
                    prob_display = f"{float(prob_pct_val):.1f}%" if prob_pct_val is not None else "N/A"
                    st.metric("Failure Risk", prob_display)
                    raw_pct = cd.get("raw_prob_pct")
                    if raw_pct is not None and prob_pct_val is not None:
                        try:
                            if abs(float(raw_pct) - float(prob_pct_val)) > 0.5:
                                st.caption(f"🧠 In-Flight ML: {float(raw_pct):.1f}%")
                        except (TypeError, ValueError):
                            pass
                    st.markdown(f"**Label:** `{cd['label']}`")
                    st.markdown(f"**Risk Tier:** `{cd['risk']}`")
                    st.markdown(f"**Type:** `EVALUATED`")
                    st.markdown(f"**Status:** {cd.get('status_text', '✅ Model inference on available log slice')}")
                elif cd["type"] == "PROJECTED":
                    st.markdown(f"#### 🟠 {d}% Checkpoint")
                    proj_pct_val = cd['prob_pct']
                    proj_display = f"{float(proj_pct_val):.1f}%" if proj_pct_val is not None else "N/A"
                    st.metric("Projected Risk", proj_display)
                    st.markdown(f"**Label:** `{cd['label']}`")
                    st.markdown(f"**Risk Tier:** `{cd['risk']}`")
                    st.markdown(f"**Type:** `PROJECTED`")
                    st.markdown(f"**Status:** {cd.get('status_text', '⚠️ Projected')}")
                else:
                    st.markdown(f"#### ⚪ {d}% Checkpoint")
                    st.metric("Risk", "N/A")
                    st.markdown(f"**Label:** `{cd['label']}`")
                    st.markdown(f"**Status:** {cd.get('status_text', '⚪ Not reached')}")

        st.markdown("---")
        # Render clean structured comparison table
        table_rows = []
        for d in [25, 50, 75, 100]:
            cd = checkpoints_data[d]
            prob_str = f"{float(cd['prob_pct']):.1f}%" if cd['prob_pct'] is not None else "N/A"
            type_badge = (
                "🟢 EVALUATED" if cd["type"] in ("ACTUAL", "EVALUATED")
                else "🟠 PROJECTED" if cd["type"] == "PROJECTED"
                else "⚪ SKIPPED" if cd["type"] == "SKIPPED"
                else "⚪ NONE"
            )
            table_rows.append({
                "Checkpoint Visibility": f"{d}% Depth",
                "Prediction Type": type_badge,
                "Failure Risk": prob_str,
                "Predicted Label": cd["label"],
                "Risk Tier": cd["risk"],
                "Confirmation Status": cd.get("status_text", "N/A"),
            })
        st.dataframe(table_rows, use_container_width=True, hide_index=True)
        st.caption(
            "ℹ️ **Prediction Distinction:** **EVALUATED** checkpoints represent verified ML model inferences executed on real log data received up to that depth checkpoint. "
            "**PROJECTED** checkpoints provide forward-looking predictive trajectory estimations for checkpoints not yet reached. "
            "Neither implies the final CI outcome has occurred — the final outcome is confirmed only by GitHub Actions."
        )

    # =========================================================================
    # D. Model Comparison
    # =========================================================================
    _render_model_comparison(run)
    
    # =========================================================================
    # E. Early Warnings
    # =========================================================================
    early_warning = run.get('early_warning')
    raw_warnings = run.get('warning_history')
    warning_history = raw_warnings if isinstance(raw_warnings, list) else []
    
    with st.expander("⚠️ Early Warnings", key=f"wf2_exp_warnings_{run_id}"):
        if early_warning or warning_history:
            threshold_raw = run.get('early_warning_threshold')
            try:
                threshold = float(threshold_raw) if threshold_raw is not None else 0.70
            except (TypeError, ValueError):
                threshold = 0.70
            st.markdown(f"**Active Threshold:** `{threshold * 100:.0f}%`")
            
            if warning_history:
                st.markdown(f"**Total Warnings Generated:** `{len(warning_history)}`")
                for idx, warning in enumerate(warning_history[:5], 1):
                    if not isinstance(warning, dict):
                        continue
                    with st.expander(f"Warning {idx}: {warning.get('timestamp', 'N/A')}", expanded=False, key=f"wf2_exp_warn_{run_id}_{idx}"):
                        st.markdown(f"**Level:** {warning.get('level', 'WARNING')}")
                        prob_raw = warning.get('failure_probability_pct')
                        try:
                            prob_val = f"{float(prob_raw):.1f}%" if prob_raw is not None else "N/A"
                        except (TypeError, ValueError):
                            prob_val = "N/A"
                        st.markdown(f"**Probability:** {prob_val}")
                        st.markdown(f"**Message:** {warning.get('message', '')}")
                if len(warning_history) > 5:
                    st.caption(f"... and {len(warning_history) - 5} more warnings")
            else:
                st.info("No early warnings were generated for this run (failure risk remained below threshold).", icon="ℹ️")
        else:
            st.info("No early warning data available for this run.", icon="ℹ️")
    
    # =========================================================================
    # F. Root Cause Analysis (RCA)
    # =========================================================================
    raw_rca = run.get('rca_result')
    rca_result = raw_rca if isinstance(raw_rca, dict) else None
    is_success = (actual_outcome == "success")
    
    with st.expander("🔍 Root Cause Analysis (RCA)", expanded=True, key=f"wf2_exp_rca_{run_id}"):
        if is_success:
            st.success("✅ Nominal Execution: Pipeline completed all steps with 0 errors. No failure root cause detected.", icon="✅")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Primary Category:** `CLEAN_RUN / NOMINAL`")
                st.markdown("**Detected Error:** `No failure detected (Clean execution)`")
                st.markdown("**Classification:** `NOMINAL_EXECUTION_VERIFIED`")
            with col2:
                st.markdown("**Evidence Strength:** `NOMINAL`")
                st.markdown("**RCA Confidence:** `10% Baseline Prior (No failure signatures found)`")
                st.markdown("**Status:** `CONFIRMED CLEAN RUN`")
            st.caption("ℹ️ For successful runs, RCA engine confirms nominal pass without fabricating root causes or assigning false failure confidence.")
        
        elif rca_result:
            col1, col2 = st.columns(2)
            with col1:
                category = rca_result.get('primary_category', 'UNKNOWN')
                st.markdown(f"**Primary Category:** `{category}`")
                st.markdown(f"**Detected Error:** `{rca_result.get('detected_error', 'N/A')}`")
                st.markdown(f"**Classification Method:** `{rca_result.get('classification_method', 'N/A')}`")
            
            with col2:
                st.markdown(f"**Evidence Strength:** `{rca_result.get('evidence_strength', 'UNKNOWN')}`")
                confidence_raw = rca_result.get('rca_confidence')
                try:
                    confidence_val = f"{float(confidence_raw) * 100:.0f}%" if confidence_raw is not None else "N/A"
                except (TypeError, ValueError):
                    confidence_val = "N/A"
                st.markdown(f"**RCA Confidence:** **{confidence_val}**")
                rca_status = "CONFIRMED" if category not in ["UNKNOWN", "INSUFFICIENT_EVIDENCE"] else "PARTIAL"
                st.markdown(f"**Status:** `{rca_status}`")
            
            if rca_result.get('confidence_rationale'):
                st.info(f"💭 **Diagnostic Rationale:** {rca_result.get('confidence_rationale')}", icon="ℹ️")
            
            root_causes = rca_result.get('root_causes')
            root_causes_list = root_causes if isinstance(root_causes, list) else []
            if root_causes_list:
                st.markdown("#### 🎯 Identified Root Causes:")
                for idx, rc in enumerate(root_causes_list, 1):
                    if not isinstance(rc, dict):
                        continue
                    is_conf = rc.get('is_confirmed', False)
                    badge = "✅ CONFIRMED" if is_conf else "⚠️ SUSPECTED"
                    rc_conf_raw = rc.get('confidence')
                    try:
                        rc_conf_str = f"{float(rc_conf_raw) * 100:.0f}%" if rc_conf_raw is not None else "N/A"
                    except (TypeError, ValueError):
                        rc_conf_str = "N/A"
                    with st.expander(f"Root Cause {idx}: {rc.get('category', 'Failure')} [{badge}]", expanded=True, key=f"wf2_exp_rc_{run_id}_{idx}"):
                        st.markdown(f"**What Failed:** {rc.get('what_failed', 'N/A')}")
                        st.markdown(f"**Where Failed:** `{rc.get('where_failed', 'N/A')}`")
                        st.markdown(f"**Why Failed:** {rc.get('why_failed', 'N/A')}")
                        st.markdown(f"**Evidence Strength:** `{rc.get('evidence_strength', 'N/A')}` | **Confidence:** `{rc_conf_str}`")
            else:
                st.warning("⚠️ No specific root causes isolated from available log chunks. Status is PARTIAL.", icon="⚠️")
            
            evidence_items = rca_result.get('evidence_items')
            evidence_list = evidence_items if isinstance(evidence_items, list) else []
            if evidence_list:
                with st.expander(f"📎 Supporting Log Evidence ({len(evidence_list)} Items)", expanded=False, key=f"wf2_exp_ev_{run_id}"):
                    for idx, ev in enumerate(evidence_list[:10], 1):
                        if not isinstance(ev, dict):
                            continue
                        st.markdown(f"**Evidence {idx}:**")
                        st.caption(
                            f"Source: `{ev.get('source_type', 'N/A')}` | "
                            f"Stage: `{ev.get('stage_name', 'N/A')}` | "
                            f"Lines: {ev.get('line_start', 'N/A')}-{ev.get('line_end', 'N/A')}"
                        )
                        st.code(ev.get('error_text', 'N/A'), language="text")
                    if len(evidence_list) > 10:
                        st.caption(f"... and {len(evidence_list) - 10} more evidence items.")
        else:
            st.info("RCA not yet available for this run.", icon="ℹ️")
    
    # =========================================================================
    # G. Remediation Guidance
    # =========================================================================
    raw_rem = run.get('remediation_result')
    remediation_result = raw_rem if isinstance(raw_rem, dict) else None
    
    with st.expander("💡 Remediation Guidance", expanded=True, key=f"wf2_exp_remediation_{run_id}"):
        if is_success:
            st.success("✅ **Pipeline Passed — No Remediation Required**")
            st.markdown("All steps in the build, dependency, and test pipeline finished cleanly with exit code 0.")
        elif remediation_result:
            rem = remediation_result
            if rem.get('primary_action'):
                st.info(f"🎯 **Primary Action:** {rem.get('primary_action')}", icon="ℹ️")
            
            confirmed_fixes = rem.get('confirmed_fixes')
            fixes_list = confirmed_fixes if isinstance(confirmed_fixes, list) else []
            if fixes_list:
                st.markdown("**Confirmed Fixes:**")
                for fix in fixes_list[:5]:
                    act = fix.get('action') if isinstance(fix, dict) else str(fix)
                    st.markdown(f"- {act}")
            
            troubleshooting = rem.get('troubleshooting')
            trouble_list = troubleshooting if isinstance(troubleshooting, list) else []
            if trouble_list:
                st.markdown("**Troubleshooting Steps:**")
                for i, step in enumerate(trouble_list[:5], 1):
                    desc = step.get('description', step.get('action', step)) if isinstance(step, dict) else str(step)
                    st.markdown(f"{i}. {desc}")
            
            commands = rem.get('terminal_commands')
            cmd_list = commands if isinstance(commands, list) else []
            if cmd_list:
                st.markdown("**Recommended Terminal Commands:**")
                for cmd in cmd_list[:5]:
                    if cmd and isinstance(cmd, str):
                        st.code(cmd, language="bash")
        else:
            st.info("No failure remediation required or available.", icon="ℹ️")
    
    # =========================================================================
    # H. Final Assessment
    # =========================================================================
    raw_summary = run.get('summary')
    summary = raw_summary if isinstance(raw_summary, dict) else {}
    with st.expander("📊 Final Assessment", key=f"wf2_exp_final_{run_id}"):
        if summary:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Pipeline Passed:** {'✅ Yes' if is_success else '❌ No'}")
                st.markdown(f"**Warnings Generated:** {'✅ Yes' if len(warning_history) > 0 else '❌ No'}")
            with col2:
                rca_found = bool(rca_result and len(rca_result.get('root_causes') or []) > 0)
                st.markdown(f"**RCA Identified Cause:** {'✅ Yes' if rca_found else '❌ No'}")
                ev_sufficient = bool(rca_result and rca_result.get('evidence_strength') == 'STRONG')
                st.markdown(f"**Evidence Sufficient:** {'✅ Yes' if ev_sufficient else '❌ No'}")
            
            if summary.get('narrative'):
                st.markdown(f"> **Summary Narrative:** {summary.get('narrative')}")
        else:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Pipeline Passed:** {'✅ Yes' if is_success else '❌ No'}")
            with col2:
                rca_found = bool(rca_result and len(rca_result.get('root_causes') or []) > 0)
                st.markdown(f"**RCA Identified Cause:** {'✅ Yes' if rca_found else '❌ No'}")
    
    # =========================================================================
    # I. Raw Log Information (Complete & Transparent Log Viewer)
    # =========================================================================
    accumulated_log = run.get('accumulated_log') or ""
    log_chunks_raw = run.get('log_chunks_count')
    try:
        log_chunks_count = int(log_chunks_raw) if log_chunks_raw is not None else 0
    except (TypeError, ValueError):
        log_chunks_count = 0
    
    with st.expander(f"📄 Raw CI Execution Logs ({log_lines_count:,} Lines)", expanded=False, key=f"wf2_exp_raw_logs_{run_id}"):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Lines", f"{log_lines_count:,}")
        with col2:
            st.metric("Log Chunks", f"{log_chunks_count:,}")
        with col3:
            st.metric("Log Size", f"{len(accumulated_log):,} bytes")
        
        if accumulated_log:
            # Download complete log button
            st.download_button(
                label=f"📥 Download Complete Log ({log_lines_count:,} lines)",
                data=accumulated_log,
                file_name=f"{run.get('run_id')}_full.log",
                mime="text/plain",
                use_container_width=True,
                key=f"btn_dl_{run.get('run_id')}"
            )
            
            view_mode = st.radio(
                "Display Mode:",
                options=["Preview (First 150 lines)", f"Full Log (All {log_lines_count:,} lines)"],
                horizontal=True,
                key=f"view_mode_{run.get('run_id')}"
            )
            
            if view_mode.startswith("Preview") and log_lines_count > 150:
                lines = accumulated_log.splitlines()
                preview_text = "\n".join(lines[:150])
                st.text_area(
                    f"Showing first 150 of {log_lines_count:,} lines:",
                    value=preview_text,
                    height=350,
                    disabled=True,
                    key=f"log_preview_{run.get('run_id')}"
                )
                st.caption(f"ℹ️ Remaining {log_lines_count - 150:,} lines not shown in preview. Select 'Full Log' or click Download to view all content.")
            else:
                st.text_area(
                    f"Full Log Content ({log_lines_count:,} lines):",
                    value=accumulated_log,
                    height=500,
                    disabled=True,
                    key=f"log_full_{run.get('run_id')}"
                )
        else:
            st.info("No log text available for this run.", icon="ℹ️")


def _render_model_comparison(run: dict) -> None:
    """
    Render model comparison section.
    Compares BiLSTM, TF-IDF + SVM, and TF-IDF + Logistic Regression models evaluated on the same log evidence.
    """
    run_id = run.get('run_id') or "N/A"
    with st.expander("🤖 Model Comparison (Multi-Model Log Inference)", key=f"wf2_exp_models_{run_id}"):
        if not run.get('run_id'):
            st.info("Run ID not available", icon="ℹ️")
            return
        
        try:
            handler = LogPipelineHandler()
            comparison, error = handler.get_run_model_comparison(run_id)
            
            if error:
                st.warning(f"Could not retrieve model comparison: {error}", icon="⚠️")
                return
            
            if not comparison:
                st.info("Model comparison not yet available", icon="ℹ️")
                return
            
            models = {}
            if isinstance(comparison, dict):
                if "predictions" in comparison:
                    predictions = comparison.get("predictions")
                    if isinstance(predictions, list):
                        for pred_item in predictions:
                            if isinstance(pred_item, dict):
                                model_id = pred_item.get('model_id')
                                if model_id:
                                    models[model_id] = pred_item
                    elif isinstance(predictions, dict):
                        model_keys = {"bilstm2", "svm", "logistic_regression"}
                        models = {k: v for k, v in predictions.items() if k in model_keys}
                
                if not models:
                    if "models" in comparison:
                        models = comparison.get("models", {})
                    elif "model_results" in comparison:
                        models = comparison.get("model_results", {})
                    elif any(k in comparison for k in ["bilstm2", "svm", "logistic_regression"]):
                        models = {k: v for k, v in comparison.items() if k in ["bilstm2", "svm", "logistic_regression"]}
                
                if not models:
                    st.info("Model comparison results pending log processing.", icon="ℹ️")
                    return
                
                st.markdown("#### Fair Side-by-Side Model Inference Comparison:")
                model_items = list(models.items())
                cols = st.columns(min(3, len(model_items)))
                
                for idx, (col, (model_key, model_data)) in enumerate(zip(cols, model_items)):
                    with col:
                        model_name = model_data.get('model', model_key.replace("_", " ").title())
                        st.markdown(f"**{model_name}**")
                        
                        if isinstance(model_data, dict):
                            prob_val = _safe_prob_pct(model_data)
                            prob_str = f"{prob_val:.1f}%" if prob_val is not None else "N/A"
                            st.metric("Failure Risk", prob_str)
                            pred_label = model_data.get('predicted_label', 'N/A')
                            st.markdown(f"**Prediction:** `{pred_label.upper()}`")
                            risk_tier = model_data.get('risk_tier', 'N/A')
                            st.markdown(f"**Risk Tier:** `{risk_tier}`")
                            
                            latency = model_data.get('inference_latency_ms')
                            if latency:
                                st.caption(f"Latency: {latency:.1f}ms")
                        else:
                            st.write(model_data)
            else:
                st.write(comparison)
        
        except Exception as e:
            st.warning(f"Error rendering model comparison: {str(e)}", icon="⚠️")
            logger.error(f"Model comparison render error: {e}")
