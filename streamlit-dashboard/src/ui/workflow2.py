"""
Workflow 2: Automatic CI Log Analysis with Polling
Automatically discovers and monitors Log Pipeline runs based on repository and commit SHA.
Displays comprehensive log analysis results including predictions, RCA, and remediation.
"""

import streamlit as st
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime
from src.state.session import get_wf2_status_display, reset_wf2_state
from src.backend.logpipeline_handler import LogPipelineHandler
from src.ui.live_progress import render_live_progress_section

logger = logging.getLogger(__name__)

# Polling configuration
POLLING_INTERVAL = 5  # seconds (for run discovery)
LIVE_POLL_INTERVAL = 2  # seconds (for active run monitoring)
MAX_RETRY_WITHOUT_RUN = 60  # seconds (give up trying to find a run after 60s)


def render_workflow2():
    """Render Workflow 2 UI - Log Analysis with automatic discovery and polling."""
    
    # Check if inputs are valid
    is_valid = (
        st.session_state.github_repo.strip() != "" and
        "/" in st.session_state.github_repo and
        st.session_state.commit_sha.strip() != "" and
        len(st.session_state.commit_sha.strip()) >= 7
    )
    
    # Detect input changes and reset state if repo/SHA changed
    _detect_input_change(is_valid)
    
    # Status indicator
    st.markdown(f"**Status:** {get_wf2_status_display(st.session_state.wf2_status)}")
    
    # Control buttons (Fetch and Reset only)
    col1, col2 = st.columns([2, 1], gap="small")
    
    with col1:
        if st.button(
            "🔄 Retry Discovery",
            disabled=not is_valid or st.session_state.wf2_status in ["analyzing"],
            use_container_width=True,
            key="btn_retry_discovery",
            help="Manually retry discovering runs (normally done automatically)"
        ):
            _fetch_log_runs_manual()
    
    with col2:
        if st.button(
            "🔄 Reset",
            use_container_width=True,
            key="btn_wf2_reset"
        ):
            reset_wf2_state()
            st.rerun()
    
    st.divider()
    
    # Attempt automatic discovery and polling
    if is_valid:
        _handle_automatic_discovery_and_polling()
    
    # Display content based on status
    if st.session_state.wf2_status == "idle" and not st.session_state.wf2_runs:
        st.info(
            "👆 Enter repository and commit SHA above, then this page will automatically discover matching runs",
            icon="ℹ️"
        )
    
    elif st.session_state.wf2_status == "discovering":
        st.info("🔍 Discovering runs from Log Pipeline...", icon="ℹ️")
    
    elif st.session_state.wf2_status == "waiting":
        st.info("⏳ Waiting for matching CI run...", icon="ℹ️")
        st.markdown("This will retry periodically. The run status will update automatically when matching executions are found.")
    
    elif st.session_state.wf2_status == "running":
        st.warning("🔄 Log Pipeline is processing...", icon="⚠️")
        st.markdown("Monitoring for updates... (polling every 2-3 seconds)")
    
    elif st.session_state.wf2_status == "analyzing":
        st.warning("🔍 Analysis in progress...", icon="⚠️")
    
    elif st.session_state.wf2_status == "failed":
        st.error(
            f"Failed to retrieve runs: {st.session_state.wf2_error}",
            icon="❌"
        )
    
    elif st.session_state.wf2_status == "unavailable":
        st.error(
            "⚠️ Log Pipeline backend is unavailable. Make sure the Log Pipeline API is running on port 8000.",
            icon="❌"
        )
    
    elif st.session_state.wf2_status == "completed" and st.session_state.wf2_runs:
        render_wf2_runs(st.session_state.wf2_runs)
    
    # Last refresh indicator
    if st.session_state.wf2_last_refresh:
        st.caption(f"Last refresh: {st.session_state.wf2_last_refresh}")


def _detect_input_change(is_valid: bool) -> None:
    """Detect if repository or commit SHA changed and reset state accordingly."""
    repo_changed = (st.session_state.wf2_last_discovery_repo != st.session_state.github_repo)
    sha_changed = (st.session_state.wf2_last_discovery_sha != st.session_state.commit_sha)
    
    if repo_changed or sha_changed:
        # Input changed - reset discovery state but keep UI responsive
        if st.session_state.wf2_runs:  # Only reset if we had previous results
            st.session_state.wf2_runs = []
            st.session_state.wf2_selected_run_id = None
            st.session_state.wf2_polling_active = False
            st.session_state.wf2_status = "idle"
            logger.info(f"Input changed - resetting discovery state")


def _handle_automatic_discovery_and_polling() -> None:
    """
    Handle automatic discovery and polling of Log Pipeline runs.
    
    Logic:
    1. On first load: Start discovery
    2. If no run found: Retry discovery periodically
    3. If run found and processing: Poll for updates
    4. If run completed/failed: Stop polling, show results
    """
    repo_id = st.session_state.github_repo
    commit_sha = st.session_state.commit_sha.strip()
    
    # Initialize on first call with valid inputs
    if st.session_state.wf2_status == "idle" and st.session_state.wf2_last_discovery_repo is None:
        st.session_state.wf2_status = "discovering"
        st.session_state.wf2_last_discovery_repo = repo_id
        st.session_state.wf2_last_discovery_sha = commit_sha
        st.session_state.wf2_last_discovery_time = time.time()
        _fetch_log_runs()
        return
    
    # Update tracking
    st.session_state.wf2_last_discovery_repo = repo_id
    st.session_state.wf2_last_discovery_sha = commit_sha
    
    # Check if we should retry discovery (if no run found yet)
    if st.session_state.wf2_status in ["idle", "waiting", "discovering"]:
        now = time.time()
        last_attempt = st.session_state.wf2_last_discovery_time or now
        time_since_last = now - last_attempt
        
        # Retry discovery if enough time has passed
        if time_since_last >= POLLING_INTERVAL:
            st.session_state.wf2_status = "discovering"
            st.session_state.wf2_last_discovery_time = now
            _fetch_log_runs()
    
    # Poll if run is active
    elif st.session_state.wf2_status in ["running", "analyzing"]:
        now = time.time()
        last_attempt = st.session_state.wf2_last_discovery_time or now
        time_since_last = now - last_attempt
        
        if time_since_last >= POLLING_INTERVAL:
            st.session_state.wf2_last_discovery_time = now
            _fetch_log_runs()


def _handle_live_progress_polling(run_id: str) -> Optional[Dict[str, Any]]:
    """
    Poll for live progress updates on a specific run.
    
    This is separate from run discovery - it polls an already-discovered run
    to get real-time updates on:
    - Current stage
    - Log ingestion progress
    - Runtime predictions
    - Early warnings
    - Parser and RCA status
    
    Args:
        run_id: The run ID to monitor
    
    Returns:
        Updated run data if available, None if error
    """
    now = time.time()
    last_poll = st.session_state.wf2_live_last_poll_time or 0
    time_since_last = now - last_poll
    
    # Check if enough time has passed for another poll
    if time_since_last < LIVE_POLL_INTERVAL:
        # Use cached data
        return st.session_state.wf2_live_run_data
    
    # Poll the backend for live updates
    try:
        handler = LogPipelineHandler()
        run_data, error = handler.get_live_run_data(run_id)
        
        if error:
            logger.warning(f"Error polling live data for {run_id}: {error}")
            return st.session_state.wf2_live_run_data  # Return cached data on error
        
        if run_data:
            # Update cached live data
            st.session_state.wf2_live_run_data = run_data
            st.session_state.wf2_live_last_poll_time = now
            
            # Check if run has reached terminal state
            status = run_data.get("status", "")
            if status in ("completed", "failed"):
                # Stop live polling, workflow will show final results
                st.session_state.wf2_live_polling_active = False
                logger.info(f"Run {run_id} reached terminal state: {status}")
            
            return run_data
    
    except Exception as e:
        logger.error(f"Exception during live progress polling: {e}")
        return st.session_state.wf2_live_run_data  # Return cached data on exception
    
    return None


def _fetch_log_runs() -> None:
    """Fetch runs from Log Pipeline backend for the selected repository and commit."""
    try:
        handler = LogPipelineHandler()
        
        # Check API health
        is_healthy, health_error = handler.check_api_health()
        if not is_healthy:
            st.session_state.wf2_status = "unavailable"
            st.session_state.wf2_error = health_error
            logger.error(f"Log Pipeline API health check failed: {health_error}")
            return
        
        # Find runs matching repository and commit
        repo_id = st.session_state.github_repo
        commit_sha = st.session_state.commit_sha.strip()
        
        runs, error = handler.find_runs_by_commit(repo_id, commit_sha)
        
        if error:
            st.session_state.wf2_status = "failed"
            st.session_state.wf2_error = error
            logger.error(f"Error finding runs: {error}")
            return
        
        if not runs:
            # No runs found yet - keep waiting/discovering
            st.session_state.wf2_status = "waiting"
            st.session_state.wf2_runs = []
            st.session_state.wf2_last_refresh = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"No runs found yet for {repo_id} @ {commit_sha}")
            return
        
        # Fetch full details for each run
        detailed_runs = []
        for run in runs:
            run_id = run.get("run_id")
            run_detail, _ = handler.get_run(run_id)
            
            if run_detail:
                detailed_runs.append(run_detail)
        
        st.session_state.wf2_runs = detailed_runs
        st.session_state.wf2_status = "completed"
        st.session_state.wf2_last_refresh = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Successfully retrieved {len(detailed_runs)} run(s)")
        
        # If user hasn't selected a run yet, auto-select the first one
        if not st.session_state.wf2_selected_run_id and detailed_runs:
            st.session_state.wf2_selected_run_id = detailed_runs[0].get("run_id")
        
    except Exception as e:
        st.session_state.wf2_status = "failed"
        st.session_state.wf2_error = str(e)
        logger.exception(f"Unexpected error fetching runs: {e}")


def _fetch_log_runs_manual() -> None:
    """Manual retry of run discovery (triggered by button)."""
    st.session_state.wf2_last_discovery_time = 0  # Force immediate retry
    _fetch_log_runs()
    st.rerun()


def render_wf2_runs(runs: list):
    """Render list of CI runs and their analysis results."""
    
    if not runs:
        st.info("No CI runs found for this repository and commit", icon="ℹ️")
        return
    
    st.markdown(f"#### ✅ Found {len(runs)} Run(s)")
    
    # Create tabs for each run (limit to first 10 to avoid UI clutter)
    run_tabs = runs[:10]
    tab_labels = []
    for i, run in enumerate(run_tabs):
        run_id = run.get("run_id", f"Run {i+1}")[:16]
        status = run.get("status", "unknown")
        status_icon = "✅" if status == "completed" else "🔄" if status == "running" else "❌"
        tab_labels.append(f"{status_icon} {run_id}")
    
    tabs = st.tabs(tab_labels)
    
    for idx, (tab, run) in enumerate(zip(tabs, run_tabs)):
        with tab:
            render_run_details(run)


def render_run_details(run: dict):
    """Render comprehensive log analysis for a single run."""
    
    # Check if run is still processing - if so, show live progress
    run_status = run.get("status", "unknown")
    if run_status == "running":
        # Trigger live polling and display progress
        run_id = run.get("run_id")
        if run_id:
            try:
                live_data = _handle_live_progress_polling(run_id)
                if live_data and live_data.get("status") == "running":
                    try:
                        render_live_progress_section(live_data)
                        st.markdown("---")
                        st.markdown("## 📊 Final Results (when complete)")
                    except Exception as e:
                        logger.error(f"Error rendering live progress section: {e}")
                        st.warning(f"Could not display live progress: {str(e)}", icon="⚠️")
            except Exception as e:
                logger.error(f"Error during live progress polling: {e}")
    
    # =========================================================================
    # A. CI Run Overview
    # =========================================================================
    with st.expander("📋 CI Run Overview", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"**Repository:** `{run.get('commit_info', {}).get('repo_id', 'N/A')}`")
            st.markdown(f"**Commit SHA:** `{run.get('commit_info', {}).get('commit_sha', 'N/A')}`")
            st.markdown(f"**Branch:** {run.get('commit_info', {}).get('branch', 'N/A')}")
            st.markdown(f"**Run ID:** `{run.get('run_id', 'N/A')}`")
        
        with col2:
            status = run.get('status', 'pending')
            status_icon = "✅" if status == "completed" else "🔄" if status == "running" else "❌"
            st.markdown(f"**Status:** {status_icon} {status.upper()}")
            
            actual_outcome = run.get('actual_outcome', 'pending')
            outcome_icon = "✅" if actual_outcome == "success" else "❌" if actual_outcome == "failure" else "⏳"
            st.markdown(f"**Outcome:** {outcome_icon} {actual_outcome.upper()}")
            
            ci_exec = run.get('ci_execution', {})
            if ci_exec.get('ci_run_id'):
                st.markdown(f"**CI Run ID:** `{ci_exec.get('ci_run_id')}`")
            
            if ci_exec.get('started_at'):
                st.markdown(f"**Started:** {ci_exec.get('started_at')}")
        
        # Checkpoint progress (based on actual predictions at 25%, 50%, 75%, 100%)
        runtime_predictions = run.get('runtime_predictions', [])
        actual_checkpoints = [p for p in runtime_predictions if p.get('prediction_type') == 'ACTUAL']
        
        logger.debug(f"Runtime predictions count: {len(runtime_predictions)}, actual: {len(actual_checkpoints)}")
        if actual_checkpoints:
            logger.debug(f"Actual checkpoints: {[p.get('checkpoint', p.get('depth_percentage')) for p in actual_checkpoints]}")
        
        if actual_checkpoints:
            # Show which checkpoints have been reached
            checkpoint_levels = {25: False, 50: False, 75: False, 100: False}
            for pred in actual_checkpoints:
                depth = pred.get('checkpoint', pred.get('depth_percentage'))
                if depth and depth in checkpoint_levels:
                    checkpoint_levels[depth] = True
                    logger.debug(f"Marking checkpoint {depth} as completed")
            
            completed_checkpoints = sum(1 for v in checkpoint_levels.values() if v)
            total_checkpoints = len(checkpoint_levels)
            
            # Show progress
            progress_text = f"Log Checkpoints: {completed_checkpoints}/{total_checkpoints}"
            reached_checkpoints = [str(k) + "%" for k, v in checkpoint_levels.items() if v]
            if reached_checkpoints:
                progress_text += f" ({', '.join(reached_checkpoints)})"
            
            st.progress(
                completed_checkpoints / total_checkpoints if total_checkpoints > 0 else 0,
                text=progress_text
            )
        else:
            # Fall back to stages if no predictions yet
            stages = run.get('stages', {})
            completed_stages = sum(1 for s in stages.values() if s.get('status') == 'completed')
            total_stages = len(stages)
            st.progress(completed_stages / total_stages if total_stages > 0 else 0, 
                       text=f"Processing Stages: {completed_stages}/{total_stages}")
    
    # =========================================================================
    # B. Runtime Failure Prediction
    # =========================================================================
    current_pred = run.get('current_runtime_prediction', {})
    if current_pred:
        with st.expander("⚡ Runtime Failure Prediction", expanded=True):
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                failure_prob = current_pred.get('failure_probability_pct', 0)
                st.metric(
                    "Failure Probability",
                    f"{failure_prob:.1f}%"
                )
            
            with col2:
                pred_label = current_pred.get('predicted_label', 'unknown').upper()
                st.metric(
                    "Predicted Label",
                    pred_label
                )
            
            with col3:
                risk_tier = current_pred.get('risk_tier', 'UNKNOWN')
                st.metric(
                    "Risk Tier",
                    risk_tier
                )
            
            with col4:
                evidence = current_pred.get('evidence_strength_label', 'UNKNOWN')
                st.metric(
                    "Evidence Strength",
                    evidence
                )
            
            # Additional metrics
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Runtime Model:** {run.get('runtime_model', 'N/A')}")
                log_lines = current_pred.get('total_lines', 0)
                st.markdown(f"**Log Lines Analyzed:** {log_lines:,}")
            
            with col2:
                depth = current_pred.get('depth_percentage', 0)
                st.markdown(f"**Pipeline Depth:** {depth}%")
                timestamp = current_pred.get('timestamp', '')
                if timestamp:
                    st.markdown(f"**Timestamp:** {timestamp}")
    
    # =========================================================================
    # C. Checkpoint Progression
    # =========================================================================
    pred_history = run.get('runtime_predictions', [])
    checkpoint_projections = run.get('checkpoint_projections', {})
    
    if pred_history or checkpoint_projections:
        with st.expander("📈 Checkpoint Progression"):
            # Organize by checkpoint depth
            checkpoints_by_depth = {}
            for pred in pred_history:
                depth = pred.get('depth_percentage')
                if depth:
                    checkpoints_by_depth[depth] = pred
            
            # Display actual predictions
            st.markdown("**ACTUAL Predictions (verified from logs):**")
            actual_found = False
            for depth in [25, 50, 75, 100]:
                if depth in checkpoints_by_depth:
                    pred = checkpoints_by_depth[depth]
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric(f"{depth}% Checkpoint", 
                                f"{pred.get('failure_probability_pct', 0):.1f}%")
                    with col2:
                        st.markdown(f"**Label:** {pred.get('predicted_label', 'N/A').upper()}")
                    with col3:
                        st.markdown(f"**Risk:** {pred.get('risk_tier', 'N/A')}")
                    actual_found = True
            
            if not actual_found:
                st.info("No actual predictions available yet - waiting for log ingestion", icon="ℹ️")
            
            # Display projections separately
            if checkpoint_projections:
                st.markdown("**PROJECTED Predictions (based on available evidence):**")
                for depth, proj_val in checkpoint_projections.items():
                    if int(depth) not in checkpoints_by_depth:
                        # Safely format proj_val as float
                        try:
                            proj_float = float(proj_val) if proj_val is not None else 0
                            st.caption(f"📊 {depth}%: {proj_float:.1f}% (PROJECTED - NOT CONFIRMED)")
                        except (ValueError, TypeError):
                            st.caption(f"📊 {depth}%: {proj_val} (PROJECTED - NOT CONFIRMED)")
    
    # =========================================================================
    # D. Model Comparison
    # =========================================================================
    _render_model_comparison(run)
    
    # =========================================================================
    # E. Early Warnings
    # =========================================================================
    early_warning = run.get('early_warning')
    warning_history = run.get('warning_history', [])
    
    with st.expander("⚠️ Early Warnings"):
        if early_warning or warning_history:
            threshold = run.get('early_warning_threshold', 0.70)
            st.markdown(f"**Active Threshold:** {threshold * 100:.0f}%")
            
            if warning_history:
                st.markdown(f"**Total Warnings Generated:** {len(warning_history)}")
                
                for idx, warning in enumerate(warning_history[:5], 1):
                    with st.expander(f"Warning {idx}: {warning.get('timestamp', 'N/A')}", expanded=False):
                        st.markdown(f"**Level:** {warning.get('level', 'N/A')}")
                        st.markdown(f"**Probability:** {warning.get('failure_probability_pct', 0):.1f}%")
                        st.markdown(f"**Message:** {warning.get('message', '')}")
                
                if len(warning_history) > 5:
                    st.caption(f"... and {len(warning_history) - 5} more warnings")
            else:
                st.info("No early warnings were generated for this run", icon="ℹ️")
        else:
            st.info("No early warning data available", icon="ℹ️")
    
    # =========================================================================
    # F. Log RCA (Root Cause Analysis)
    # =========================================================================
    rca_result = run.get('rca_result')
    
    with st.expander("🔍 Root Cause Analysis"):
        if rca_result:
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown(f"**Primary Category:** {rca_result.get('primary_category', 'UNKNOWN')}")
                st.markdown(f"**Detected Error:** {rca_result.get('detected_error', 'N/A')}")
                st.markdown(f"**Classification:** {rca_result.get('classification_method', 'N/A')}")
            
            with col2:
                st.markdown(f"**Evidence Strength:** {rca_result.get('evidence_strength', 'UNKNOWN')}")
                confidence = rca_result.get('rca_confidence', 0)
                st.markdown(f"**RCA Confidence:** {confidence * 100:.0f}%")
                st.markdown(f"**Status:** {rca_result.get('status', 'UNKNOWN')}")
            
            # Confidence rationale
            if rca_result.get('confidence_rationale'):
                st.info(f"💭 {rca_result.get('confidence_rationale')}", icon="ℹ️")
            
            # Root causes
            root_causes = rca_result.get('root_causes', [])
            if root_causes:
                st.markdown("**Root Causes Identified:**")
                for idx, rc in enumerate(root_causes, 1):
                    with st.expander(f"Cause {idx}: {rc.get('category', 'Unknown')}", expanded=False):
                        st.markdown(f"**What Failed:** {rc.get('what_failed', 'N/A')}")
                        st.markdown(f"**Where Failed:** {rc.get('where_failed', 'N/A')}")
                        st.markdown(f"**Why Failed:** {rc.get('why_failed', 'N/A')}")
                        st.markdown(f"**Confirmed:** {'✅ Yes' if rc.get('is_confirmed') else '❌ Suspected'}")
                        st.markdown(f"**Evidence Strength:** {rc.get('evidence_strength', 'N/A')}")
                        st.markdown(f"**Confidence:** {rc.get('confidence', 0) * 100:.0f}%")
            else:
                st.warning("⚠️ No root causes identified - insufficient evidence or analysis incomplete", icon="⚠️")
            
            # Evidence items
            evidence_items = rca_result.get('evidence_items', [])
            if evidence_items:
                with st.expander("📎 Supporting Evidence", expanded=False):
                    for idx, ev in enumerate(evidence_items[:10], 1):
                        st.markdown(f"**Evidence {idx}:**")
                        st.caption(f"Type: {ev.get('source_type', 'N/A')} | "
                                 f"Stage: {ev.get('stage_name', 'N/A')} | "
                                 f"Lines: {ev.get('line_start', 'N/A')}-{ev.get('line_end', 'N/A')}")
                        st.caption(f"'{ev.get('error_text', 'N/A')}'")
                    
                    if len(evidence_items) > 10:
                        st.caption(f"... and {len(evidence_items) - 10} more evidence items")
        else:
            st.info("RCA not yet available - waiting for log analysis to complete", icon="ℹ️")
    
    # =========================================================================
    # G. Remediation
    # =========================================================================
    remediation_result = run.get('remediation_result')
    
    with st.expander("💡 Remediation Guidance"):
        if remediation_result:
            rem = remediation_result
            
            if rem.get('primary_action'):
                st.info(f"🎯 **Primary Action:** {rem.get('primary_action')}", icon="ℹ️")
            
            # Confirmed fixes
            confirmed_fixes = rem.get('confirmed_fixes', [])
            if confirmed_fixes:
                st.markdown("**Confirmed Fixes:**")
                for fix in confirmed_fixes[:5]:
                    st.markdown(f"- {fix.get('action', fix.get('description', 'N/A'))}")
            
            # Troubleshooting steps
            troubleshooting = rem.get('troubleshooting', [])
            if troubleshooting:
                st.markdown("**Troubleshooting Steps:**")
                for i, step in enumerate(troubleshooting[:5], 1):
                    st.markdown(f"{i}. {step.get('description', step)}")
            
            # Terminal commands
            commands = rem.get('terminal_commands', [])
            if commands:
                with st.expander("🖥️ Terminal Commands", expanded=False):
                    for cmd in commands[:10]:
                        if cmd:
                            st.code(cmd, language="bash")
        else:
            st.info("Remediation not yet available - waiting for analysis to complete", icon="ℹ️")
    
    # =========================================================================
    # H. Final Assessment
    # =========================================================================
    summary = run.get('summary')
    
    with st.expander("📊 Final Assessment"):
        if summary:
            col1, col2 = st.columns(2)
            
            with col1:
                actual_outcome = run.get('actual_outcome', 'pending')
                pipeline_passed = actual_outcome == "success"
                st.markdown(f"**Pipeline Passed:** {'✅ Yes' if pipeline_passed else '❌ No'}")
                
                warnings_gen = len(warning_history) > 0
                st.markdown(f"**Warnings Generated:** {'✅ Yes' if warnings_gen else '❌ No'}")
            
            with col2:
                rca_found = (rca_result and len(rca_result.get('root_causes', [])) > 0)
                st.markdown(f"**RCA Identified Cause:** {'✅ Yes' if rca_found else '❌ No'}")
                
                ev_sufficient = (rca_result and rca_result.get('evidence_strength') == 'STRONG')
                st.markdown(f"**Evidence Sufficient:** {'✅ Yes' if ev_sufficient else '❌ No'}")
            
            if summary.get('narrative'):
                st.markdown("**Summary Narrative:**")
                st.markdown(f"> {summary.get('narrative')}")
        else:
            st.caption("Summary will be available after analysis completes")
    
    # =========================================================================
    # I. Raw Log Information (if available)
    # =========================================================================
    accumulated_log = run.get('accumulated_log', '')
    log_lines_count = run.get('log_lines_count', 0)
    log_chunks_count = run.get('log_chunks_count', 0)
    
    if accumulated_log or log_lines_count > 0:
        with st.expander("📄 Raw Logs"):
            st.markdown(f"**Log Statistics:**")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Log Lines", f"{log_lines_count:,}")
            with col2:
                st.metric("Log Chunks", f"{log_chunks_count:,}")
            
            if accumulated_log:
                # Show first 5000 characters with scroll
                log_preview = accumulated_log[:5000]
                st.text_area(
                    "Log Content (first 5000 characters):",
                    value=log_preview,
                    height=300,
                    disabled=True,
                    key=f"log_display_{run.get('run_id')}"
                )
                
                if len(accumulated_log) > 5000:
                    st.caption(f"... {len(accumulated_log) - 5000} more characters")
            else:
                st.info("Logs not yet collected", icon="ℹ️")


def _render_model_comparison(run: dict) -> None:
    """
    Render model comparison section.
    
    Fetches and displays comparison of BiLSTM, TF-IDF + SVM, and TF-IDF + Logistic Regression
    models evaluated on the same log evidence.
    """
    with st.expander("🤖 Model Comparison"):
        run_id = run.get('run_id')
        
        if not run_id:
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
            
            logger.debug(f"Model comparison response type: {type(comparison)}")
            logger.debug(f"Model comparison response keys: {list(comparison.keys()) if isinstance(comparison, dict) else 'N/A'}")
            
            # Extract models from response
            models = {}
            
            if isinstance(comparison, dict):
                # Check for predictions array with model data
                if "predictions" in comparison:
                    predictions = comparison.get("predictions")
                    logger.debug(f"Predictions type: {type(predictions)}, value: {predictions}")
                    
                    if isinstance(predictions, list):
                        # Predictions is an array of ModelComparisonEntry objects
                        logger.debug(f"Found {len(predictions)} predictions in array")
                        for pred_item in predictions:
                            if isinstance(pred_item, dict):
                                model_id = pred_item.get('model_id')
                                if model_id:
                                    models[model_id] = pred_item
                                    logger.debug(f"Added model: {model_id}")
                    elif isinstance(predictions, dict):
                        # Predictions is a dict with model keys
                        model_keys = {"bilstm2", "svm", "logistic_regression"}
                        predictions_models = {k: v for k, v in predictions.items() if k in model_keys}
                        if predictions_models:
                            models = predictions_models
                
                # Try other common structures
                if not models:
                    if "models" in comparison:
                        models = comparison.get("models", {})
                    elif "model_results" in comparison:
                        models = comparison.get("model_results", {})
                    elif "bilstm2" in comparison or "svm" in comparison or "logistic_regression" in comparison:
                        # Direct model keys in response
                        models = {k: v for k, v in comparison.items() if k in ["bilstm2", "svm", "logistic_regression"]}
                
                if not models:
                    st.info(f"Model comparison data not yet available. Response has: {', '.join(comparison.keys())}", icon="ℹ️")
                    logger.info(f"Full comparison response: {comparison}")
                    return
                
                # Display each model's results in columns
                st.markdown("**Model Predictions:**")
                
                # Create columns for each model (up to 3)
                model_items = list(models.items())
                cols = st.columns(min(3, len(model_items)))
                
                for idx, (col, (model_key, model_data)) in enumerate(zip(cols, model_items)):
                    with col:
                        # Display model name (use from data or prettify the key)
                        model_name = model_data.get('model', model_key.replace("_", " ").title())
                        st.markdown(f"### {model_name}")
                        
                        # Display key metrics
                        if isinstance(model_data, dict):
                            # Handle various probability field names
                            failure_prob = (
                                model_data.get('failure_probability_pct') or
                                model_data.get('failure_probability') or 
                                0
                            )
                            # Ensure it's in percentage format
                            if isinstance(failure_prob, float) and failure_prob < 1.0:
                                failure_prob = failure_prob * 100
                            
                            st.metric("Failure Probability", f"{failure_prob:.1f}%")
                            
                            # Predicted label
                            pred_label = model_data.get('predicted_label', 'N/A')
                            st.markdown(f"**Prediction:** {pred_label.upper()}")
                            
                            # Risk tier
                            risk_tier = model_data.get('risk_tier', 'N/A')
                            st.markdown(f"**Risk Tier:** {risk_tier}")
                            
                            # Prediction type
                            pred_type = model_data.get('prediction_type', '')
                            if pred_type:
                                st.markdown(f"**Type:** {pred_type}")
                            
                            # Status
                            status = model_data.get('status', '')
                            if status:
                                st.markdown(f"**Status:** {status}")
                            
                            # Confidence
                            confidence = model_data.get('confidence')
                            if confidence is not None:
                                st.markdown(f"**Confidence:** {confidence:.2f}")
                            
                            # Inference latency
                            latency = model_data.get('inference_latency_ms')
                            if latency:
                                st.markdown(f"**Latency:** {latency}ms")
                            
                            # Evidence strength
                            evidence = model_data.get('evidence_strength')
                            if evidence:
                                st.markdown(f"**Evidence:** {evidence}")
                            
                            # Error message if present
                            error = model_data.get('error_message')
                            if error:
                                st.error(f"Error: {error}")
                        else:
                            st.write(model_data)
            else:
                st.write(comparison)
        
        except Exception as e:
            st.warning(f"Error rendering model comparison: {str(e)}", icon="⚠️")
            logger.error(f"Model comparison render error: {e}")

