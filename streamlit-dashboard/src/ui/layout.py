"""
Main UI layout for Streamlit dashboard.
Orchestrates user input section and workflow panels.
"""

import streamlit as st
from src.ui.input_section import render_input_section
from src.ui.workflow1 import render_workflow1
from src.ui.workflow2 import render_workflow2
from src.ui.sidebar import render_sidebar


def render_main_layout():
    """Render the complete dashboard layout."""
    
    # Render sidebar (configuration, info)
    render_sidebar()
    
    # Header
    st.title("🚀 CI/CD Failure Predictor & Graph RCA")
    st.markdown(
        "Analyze GitHub commits for build failures using ML predictions, "
        "SHAP explanations, and knowledge graph-based root cause analysis.",
        unsafe_allow_html=False
    )
    
    # User Input Section (SINGLE INPUT SECTION)
    st.divider()
    st.markdown("## 📥 Analysis Input")
    render_input_section()
    
    st.divider()
    
    # Two-column layout for workflows
    col1, col2 = st.columns([1, 1], gap="medium")
    
    # Workflow 1: Metadata Prediction + Graph RCA
    with col1:
        st.markdown("### 🔬 Workflow 1: Metadata Prediction & RCA")
        render_workflow1()
    
    # Workflow 2: CI Log Analysis
    with col2:
        st.markdown("### 📊 Workflow 2: CI Log Analysis")
        render_workflow2()
    
    # Footer
    st.divider()
    st.markdown(
        "<p style='text-align: center; color: #888; font-size: 0.9em;'>"
        "Powered by ORC, Metadata-Pipeline, graph-doc-gen, and Log Pipeline | "
        "v1.0.0"
        "</p>",
        unsafe_allow_html=True
    )
