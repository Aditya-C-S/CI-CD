"""
Streamlit Dashboard: CI/CD Failure Prediction & Graph-Based Root Cause Analysis
Integrates ORC and Log Pipeline for comprehensive failure analysis.

Two independent pages:
1. Metadata + Graph RCA
2. Log Analysis (Log Pipeline)
"""

import streamlit as st
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file (must be before any imports that use them)
load_dotenv()

# Add project modules to path
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.state.session import initialize_session_state
from src.ui.input_section import render_input_section
from src.ui.workflow1 import render_workflow1
from src.ui.workflow2 import render_workflow2

# Configure page
st.set_page_config(
    page_title="CI/CD Failure Predictor & RCA",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
initialize_session_state()

# ============================================================================
# HEADER AND SHARED NAVIGATION
# ============================================================================
st.title("🚀 CI/CD Failure Predictor & Graph RCA")
st.markdown(
    "Analyze GitHub commits for build failures using ML predictions, "
    "SHAP explanations, and knowledge graph-based root cause analysis.",
    unsafe_allow_html=False
)

st.divider()

# ============================================================================
# SIDEBAR - SHARED INPUT SECTION + PAGE SELECTOR
# ============================================================================
with st.sidebar:
    st.markdown("## 📥 Analysis Input")
    st.markdown("Enter the GitHub repository and commit SHA to analyze:")
    render_input_section()
    
    st.divider()
    st.markdown("## 📄 Select Analysis Page")
    
    # Page selector radio button
    page = st.radio(
        "Choose workflow:",
        ["Metadata + Graph RCA", "Log Analysis (Log Pipeline)"],
        label_visibility="collapsed",
        horizontal=False
    )

# ============================================================================
# PAGE ROUTING
# ============================================================================

if page == "Metadata + Graph RCA":
    st.markdown("### 🔬 Workflow: Metadata Prediction & Graph-Based RCA")
    st.markdown(
        "Uses metadata analysis and knowledge graph to predict failures and identify root causes."
    )
    st.divider()
    render_workflow1()

elif page == "Log Analysis (Log Pipeline)":
    st.markdown("### 📊 Workflow: Automatic CI Log Analysis")
    st.markdown(
        "Automatically retrieves and analyzes CI logs from the Log Pipeline backend."
    )
    st.divider()
    render_workflow2()

# ============================================================================
# FOOTER
# ============================================================================
st.divider()
st.markdown(
    "<p style='text-align: center; color: #888; font-size: 0.9em;'>"
    "Powered by ORC, Metadata-Pipeline, graph-doc-gen, and Log Pipeline | "
    "v1.0.0"
    "</p>",
    unsafe_allow_html=True
)
