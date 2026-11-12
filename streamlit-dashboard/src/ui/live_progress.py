"""
Live Progress Monitoring Display for Log Analysis Workflow.

Displays real-time progress updates during workflow execution:
- Current processing stage
- Log ingestion progress
- Intermediate predictions
- Early warnings
- Parser and RCA status
"""

import streamlit as st
import time
from typing import Dict, Any, Optional, Set
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.logpipeline_handler import LogPipelineHandler


def get_stage_display_name(stage_key: str) -> str:
    """Convert stage key to human-readable display name."""
    stage_names = {
        "commit_metadata": "📋 Commit Metadata",
        "metadata_prediction": "🤖 Pre-Build Prediction",
        "neo4j_blast_radius": "🔗 Code Graph Analysis",
        "ci_execution": "🏃 CI Pipeline Execution",
        "live_log_ingestion": "📥 Log Ingestion & Predictions",
        "parser_v2": "📖 Evidence Parser",
        "rca_remediation": "🔎 Root Cause & Remediation"
    }
    return stage_names.get(stage_key, stage_key)


def get_stage_icon(status: str) -> str:
    """Get icon for stage status."""
    icons = {
        "pending": "⏳",
        "in_progress": "🔄",
        "completed": "✅",
        "failed": "❌"
    }
    return icons.get(status, "◯")


def render_stage_progress(stages: Dict[str, Dict[str, Any]], current_stage: str) -> None:
    """Render current processing stage indicator."""
    with st.container():
        cols = st.columns([3, 1])
        
        with cols[0]:
            # Display current stage
            if current_stage in stages:
                stage_info = stages[current_stage]
                status = stage_info.get("status", "pending")
                icon = get_stage_icon(status)
                display_name = get_stage_display_name(current_stage)
                st.markdown(f"### {icon} {display_name}")
            else:
                st.markdown("### 🤔 Processing...")
        
        with cols[1]:
            # Stage status badge
            status_colors = {
                "pending": "#FFB84D",      # Orange
                "in_progress": "#4A90E2",  # Blue
                "completed": "#50C878",    # Green
                "failed": "#E74C3C"        # Red
            }
            if current_stage in stages:
                status = stages[current_stage].get("status", "pending")
                color = status_colors.get(status, "#777777")
                badge_text = status.replace("_", " ").upper()
                st.markdown(
                    f"<div style='background-color: {color}; color: white; padding: 8px 12px; "
                    f"border-radius: 4px; text-align: center; font-weight: bold;'>{badge_text}</div>",
                    unsafe_allow_html=True
                )


def render_stage_timeline(stages: Dict[str, Dict[str, Any]]) -> None:
    """Render timeline of log analysis stages only (exclude metadata stages)."""
    st.subheader("📊 Processing Timeline")
    
    timeline_html = "<div style='display: flex; gap: 8px; flex-wrap: wrap; margin: 10px 0;'>"
    
    # Only show log analysis related stages, exclude metadata stages
    stage_displays = {
        "ci_execution": "Execution",
        "live_log_ingestion": "Predictions",
        "parser_v2": "Parser",
        "rca_remediation": "Remediation"
    }
    
    for stage_key, display_name in stage_displays.items():
        if stage_key not in stages:
            continue
            
        status = stages[stage_key].get("status", "pending")
        icon = get_stage_icon(status)
        colors = {
            "pending": "#e0e0e0",
            "in_progress": "#4A90E2",
            "completed": "#50C878",
            "failed": "#E74C3C"
        }
        color = colors.get(status, "#777777")
        
        timeline_html += f"""
            <div style='background-color: {color}; color: white; padding: 6px 10px; 
                        border-radius: 4px; font-size: 12px; white-space: nowrap; font-weight: bold;'>
                {icon} {display_name}
            </div>
        """
    
    timeline_html += "</div>"
    st.markdown(timeline_html, unsafe_allow_html=True)


def render_log_ingestion_progress(
    log_lines_count: int,
    estimated_log_size: Optional[int],
    log_chunks_count: int
) -> None:
    """Render log ingestion progress."""
    st.subheader("📥 Log Ingestion Progress")
    
    cols = st.columns([2, 1, 1])
    
    with cols[0]:
        if estimated_log_size and estimated_log_size > 0:
            progress = min(100, int((log_lines_count / estimated_log_size) * 100))
            st.progress(progress / 100.0, text=f"{progress}% ({log_lines_count}/{estimated_log_size} lines)")
        else:
            st.metric("Log Lines", f"{log_lines_count} lines")
    
    with cols[1]:
        st.metric("Chunks Received", log_chunks_count)
    
    with cols[2]:
        if estimated_log_size:
            st.metric("Total Expected", f"{estimated_log_size} lines")


def render_live_predictions(
    runtime_predictions: list,
    current_runtime_prediction: Optional[Dict[str, Any]],
    seen_predictions: Set[str]
) -> None:
    """Render live runtime predictions."""
    st.subheader("🧠 Live Predictions")
    
    if not runtime_predictions:
        st.info("⏳ Waiting for first prediction...", icon="ℹ️")
        return
    
    # Show current prediction prominently
    if current_runtime_prediction:
        pred = current_runtime_prediction
        checkpoint = pred.get("checkpoint", pred.get("depth_percentage", "?"))
        prob_pct = pred.get("failure_probability_pct", 0)
        risk_tier = pred.get("risk_tier", "UNKNOWN")
        pred_type = pred.get("prediction_type", "UNKNOWN")
        model = pred.get("model", "Unknown Model")
        evidence_strength = pred.get("evidence_strength", "UNKNOWN")
        
        # Color based on risk tier
        risk_colors = {
            "LOW": "#50C878",
            "MODERATE": "#FFB84D",
            "HIGH": "#FF6B6B",
            "CRITICAL": "#E74C3C"
        }
        color = risk_colors.get(risk_tier, "#777777")
        
        cols = st.columns([2, 1, 1, 1])
        
        with cols[0]:
            st.metric(
                f"📊 Checkpoint {checkpoint}%",
                f"{prob_pct:.1f}%",
                delta=None
            )
        
        with cols[1]:
            st.markdown(f"<div style='background-color: {color}; color: white; padding: 8px; "
                       f"border-radius: 4px; text-align: center; font-weight: bold;'>{risk_tier}</div>",
                       unsafe_allow_html=True)
        
        with cols[2]:
            type_icon = "✅" if pred_type == "ACTUAL" else "📊" if pred_type == "PROJECTED" else "⏳"
            st.markdown(f"**{type_icon} {pred_type}**")
        
        with cols[3]:
            st.markdown(f"**{evidence_strength}** evidence")
        
        st.caption(f"Model: {model} • Lines analyzed: {pred.get('log_lines_count', '?')}")
        
        # Mark as seen
        pred_id = f"{checkpoint}_{prob_pct}"
        seen_predictions.add(pred_id)
    
    # Show history of checkpoints
    if len(runtime_predictions) > 1:
        st.markdown("**Checkpoint History:**")
        
        checkpoint_rows = []
        for pred in runtime_predictions:
            if pred.get("prediction_type") == "ACTUAL":
                cp = pred.get("checkpoint", pred.get("depth_percentage"))
                prob = pred.get("failure_probability_pct", 0)
                tier = pred.get("risk_tier", "?")
                timestamp = pred.get("timestamp", "")
                checkpoint_rows.append({
                    "Checkpoint": f"{cp}%",
                    "Probability": f"{prob:.1f}%",
                    "Risk Tier": tier,
                    "Time": timestamp[-8:] if timestamp else ""  # HH:MM:SS
                })
        
        if checkpoint_rows:
            # Display as compact table
            for row in checkpoint_rows[-4:]:  # Last 4 checkpoints
                cols = st.columns([1, 1, 1, 1])
                with cols[0]:
                    st.caption(row["Checkpoint"])
                with cols[1]:
                    st.caption(row["Probability"])
                with cols[2]:
                    st.caption(row["Risk Tier"])
                with cols[3]:
                    st.caption(row["Time"])


def render_early_warnings(
    early_warning: Optional[Dict[str, Any]],
    warning_history: list,
    seen_warnings: Set[str]
) -> None:
    """Render early warning alerts."""
    if not early_warning and not warning_history:
        return
    
    st.subheader("⚠️ Early Warnings")
    
    # Show current active warning prominently
    if early_warning:
        warning = early_warning
        event_id = warning.get("event_id", "")
        prob_pct = warning.get("failure_probability_pct", 0)
        threshold_pct = warning.get("threshold_pct", 70)
        risk_tier = warning.get("risk_tier", "HIGH RISK")
        checkpoint = warning.get("checkpoint", "?")
        
        if event_id not in seen_warnings:
            seen_warnings.add(event_id)
            # New warning - show it prominently
            st.error(
                f"🚨 **{risk_tier}** at {checkpoint}% checkpoint!\n\n"
                f"Failure probability: **{prob_pct:.1f}%** (Threshold: {threshold_pct:.1f}%)\n\n"
                f"{warning.get('message', '')}"
            )
        else:
            # Already shown - display as info
            st.warning(
                f"⚠️ **{risk_tier}** at {checkpoint}% checkpoint\n"
                f"Failure probability: {prob_pct:.1f}% (Threshold: {threshold_pct:.1f}%)"
            )
    
    # Show warning history
    if warning_history and len(warning_history) > 1:
        with st.expander(f"📋 Warning History ({len(warning_history)})"):
            for warning in warning_history[-5:]:  # Last 5 warnings
                cp = warning.get("checkpoint", "?")
                prob = warning.get("failure_probability_pct", 0)
                tier = warning.get("risk_tier", "?")
                st.caption(f"Checkpoint {cp}%: {prob:.1f}% ({tier})")


def render_parser_status(parser_v2_result: Optional[Dict[str, Any]]) -> None:
    """Render parser V2 status."""
    if not parser_v2_result:
        return
    
    status = parser_v2_result.get("status", "pending")
    
    if status == "pending":
        st.info("⏳ Parser V2: Waiting to process logs...", icon="ℹ️")
    elif status == "processing":
        st.info("🔍 Parser V2: Processing and extracting evidence...", icon="ℹ️")
    elif status == "completed":
        extracted = parser_v2_result.get("extracted_evidence", [])
        failures = parser_v2_result.get("failure_indicators", [])
        st.success(f"✅ Parser V2: Completed - {len(extracted)} evidence items, {len(failures)} failure indicators", icon="✅")
    elif status == "error":
        error_msg = parser_v2_result.get("error_summary", "Unknown error")
        st.error(f"❌ Parser V2: {error_msg}", icon="❌")


def render_rca_status(rca_result: Optional[Dict[str, Any]], remediation_result: Optional[Dict[str, Any]]) -> None:
    """Render RCA and remediation status."""
    if not rca_result and not remediation_result:
        return
    
    st.subheader("🔎 Root Cause Analysis")
    
    cols = st.columns(2)
    
    with cols[0]:
        if rca_result:
            status = rca_result.get("status", "pending")
            if status == "pending":
                st.info("⏳ RCA: Pending", icon="ℹ️")
            elif status == "in_progress":
                st.info("🔍 RCA: Analyzing...", icon="ℹ️")
            elif status == "completed":
                root_causes = rca_result.get("root_causes", [])
                st.success(f"✅ RCA: Found {len(root_causes)} root cause(s)", icon="✅")
            elif status == "no_failure_detected":
                st.success("✅ RCA: No failure detected", icon="✅")
            elif status == "insufficient_evidence":
                st.warning("⚠️ RCA: Insufficient evidence", icon="⚠️")
    
    with cols[1]:
        if remediation_result:
            status = remediation_result.get("status", "pending")
            if status == "pending":
                st.info("⏳ Remediation: Pending", icon="ℹ️")
            elif status == "generated":
                recommendations = remediation_result.get("recommendations", [])
                st.success(f"✅ Remediation: {len(recommendations)} recommendations", icon="✅")
            elif status == "not_applicable":
                st.info("ℹ️ Remediation: Not applicable", icon="ℹ️")


def render_live_progress_section(run_data: Dict[str, Any]) -> None:
    """
    Render complete live progress monitoring section.
    
    Shows real-time updates during workflow execution:
    - Current stage
    - Live predictions
    - Early warnings
    - Parser and RCA status
    """
    st.markdown("---")
    st.markdown("## 🔴 LIVE MONITORING")
    
    # Current status and stage
    status = run_data.get("status", "unknown")
    current_stage = run_data.get("current_stage", "unknown")
    stages = run_data.get("stages", {})
    
    # Show LIVE indicator if still running
    if status == "running":
        st.markdown(
            "<div style='background-color: #ff4444; color: white; padding: 4px 8px; "
            "border-radius: 3px; display: inline-block; font-weight: bold; margin-bottom: 10px;'>"
            "🔴 LIVE</div>",
            unsafe_allow_html=True
        )
    
    # Render stage progress
    render_stage_progress(stages, current_stage)
    render_stage_timeline(stages)
    
    st.divider()
    
    # Live predictions
    runtime_predictions = run_data.get("runtime_predictions", [])
    current_runtime_prediction = run_data.get("current_runtime_prediction")
    
    if runtime_predictions or current_runtime_prediction:
        if "wf2_live_predictions_seen" not in st.session_state:
            st.session_state.wf2_live_predictions_seen = set()
        
        render_live_predictions(
            runtime_predictions,
            current_runtime_prediction,
            st.session_state.wf2_live_predictions_seen
        )
        st.divider()
    
    # Early warnings
    early_warning = run_data.get("early_warning")
    warning_history = run_data.get("warning_history", [])
    
    if early_warning or warning_history:
        if "wf2_live_warnings_seen" not in st.session_state:
            st.session_state.wf2_live_warnings_seen = set()
        
        render_early_warnings(
            early_warning,
            warning_history,
            st.session_state.wf2_live_warnings_seen
        )
        st.divider()
    
    # Parser status
    parser_v2_result = run_data.get("parser_v2_result")
    render_parser_status(parser_v2_result)
    
    # RCA and remediation status
    rca_result = run_data.get("rca_result")
    remediation_result = run_data.get("remediation_result")
    render_rca_status(rca_result, remediation_result)
    
    st.markdown("---")
