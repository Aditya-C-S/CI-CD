"""
Session state management for Streamlit dashboard.
Maintains user input and workflow states across page reruns.
"""

import streamlit as st
from datetime import datetime


def initialize_session_state():
    """Initialize session state variables."""
    
    # User Input
    if "github_repo" not in st.session_state:
        st.session_state.github_repo = ""
    
    if "commit_sha" not in st.session_state:
        st.session_state.commit_sha = ""
    
    # Workflow 1: Metadata Prediction + Graph RCA
    if "wf1_status" not in st.session_state:
        st.session_state.wf1_status = "idle"  # idle, analyzing, completed, failed
    
    if "wf1_results" not in st.session_state:
        st.session_state.wf1_results = None
    
    if "wf1_error" not in st.session_state:
        st.session_state.wf1_error = None
    
    if "wf1_last_analyzed" not in st.session_state:
        st.session_state.wf1_last_analyzed = None
    
    # Workflow 2: CI Log Analysis
    if "wf2_status" not in st.session_state:
        st.session_state.wf2_status = "idle"
    
    if "wf2_runs" not in st.session_state:
        st.session_state.wf2_runs = []
    
    if "wf2_results" not in st.session_state:
        st.session_state.wf2_results = None
    
    if "wf2_error" not in st.session_state:
        st.session_state.wf2_error = None
    
    if "wf2_last_refresh" not in st.session_state:
        st.session_state.wf2_last_refresh = None
    
    if "wf2_selected_run" not in st.session_state:
        st.session_state.wf2_selected_run = None
    
    # Polling state tracking
    if "wf2_last_discovery_repo" not in st.session_state:
        st.session_state.wf2_last_discovery_repo = None
    
    if "wf2_last_discovery_sha" not in st.session_state:
        st.session_state.wf2_last_discovery_sha = None
    
    if "wf2_last_discovery_time" not in st.session_state:
        st.session_state.wf2_last_discovery_time = None
    
    if "wf2_polling_active" not in st.session_state:
        st.session_state.wf2_polling_active = False
    
    if "wf2_selected_run_id" not in st.session_state:
        st.session_state.wf2_selected_run_id = None
    
    # Graph Viewer state
    if "show_graph_viewer" not in st.session_state:
        st.session_state.show_graph_viewer = False
    
    # Auto-refresh configuration
    if "auto_refresh_enabled" not in st.session_state:
        st.session_state.auto_refresh_enabled = True
    
    if "auto_refresh_interval" not in st.session_state:
        st.session_state.auto_refresh_interval = 5  # seconds (changed from 10 to 5)
    
    # Live Progress Monitoring (Workflow 2)
    if "wf2_live_run_data" not in st.session_state:
        st.session_state.wf2_live_run_data = None
    
    if "wf2_live_polling_active" not in st.session_state:
        st.session_state.wf2_live_polling_active = False
    
    if "wf2_live_last_poll_time" not in st.session_state:
        st.session_state.wf2_live_last_poll_time = None
    
    if "wf2_live_predictions_seen" not in st.session_state:
        st.session_state.wf2_live_predictions_seen = set()
    
    if "wf2_live_warnings_seen" not in st.session_state:
        st.session_state.wf2_live_warnings_seen = set()
    
    if "wf2_live_poll_interval" not in st.session_state:
        st.session_state.wf2_live_poll_interval = 3  # seconds during active run


def get_wf1_status_display(status: str) -> str:
    """Convert workflow 1 status to display string."""
    status_map = {
        "idle": "⏹️ Waiting for input",
        "analyzing": "🔄 Analyzing commit...",
        "completed": "✅ Analysis completed",
        "failed": "❌ Analysis failed"
    }
    return status_map.get(status, status)


def get_wf2_status_display(status: str) -> str:
    """Convert workflow 2 status to display string."""
    status_map = {
        "idle": "⏹️ Ready",
        "discovering": "🔍 Discovering runs...",
        "waiting": "⏳ Waiting for CI run...",
        "running": "🔄 Workflow running...",
        "logs_received": "📋 Logs received, processing...",
        "analyzing": "🔍 Analysis in progress...",
        "completed": "✅ Analysis completed",
        "failed": "❌ Workflow failed",
        "unavailable": "⚠️ Backend unavailable"
    }
    return status_map.get(status, status)


def reset_wf1_state():
    """Reset Workflow 1 state."""
    st.session_state.wf1_status = "idle"
    st.session_state.wf1_results = None
    st.session_state.wf1_error = None
    st.session_state.wf1_last_analyzed = None
    st.session_state.show_graph_viewer = False


def reset_wf2_state():
    """Reset Workflow 2 state."""
    st.session_state.wf2_status = "idle"
    st.session_state.wf2_runs = []
    st.session_state.wf2_results = None
    st.session_state.wf2_error = None
    st.session_state.wf2_last_refresh = None
    st.session_state.wf2_selected_run = None
    st.session_state.wf2_selected_run_id = None
    st.session_state.wf2_polling_active = False
    st.session_state.wf2_last_discovery_repo = None
    st.session_state.wf2_last_discovery_sha = None
    st.session_state.wf2_last_discovery_time = None
