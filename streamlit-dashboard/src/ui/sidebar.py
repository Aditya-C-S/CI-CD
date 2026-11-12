"""
Sidebar configuration and information.
"""

import streamlit as st


def render_sidebar():
    """Render sidebar with configuration and information."""
    
    with st.sidebar:
        st.markdown("## ⚙️ Configuration")
        
        # Backend endpoints
        st.markdown("### 🔗 Backend Endpoints")
        col1, col2 = st.columns([3, 1])
        with col1:
            orc_url = st.text_input(
                "ORC URL",
                value="http://127.0.0.1:8001",
                help="ORC backend URL for Metadata Pipeline and Graph analysis"
            )
        with col2:
            if st.button("Test", key="btn_test_orc"):
                st.info("ORC connection test (not yet implemented)")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            logpipeline_url = st.text_input(
                "Log Pipeline URL",
                value="http://127.0.0.1:8000",
                help="Log Pipeline backend URL for CI run analysis"
            )
        with col2:
            if st.button("Test", key="btn_test_logpipeline"):
                st.info("Log Pipeline connection test (not yet implemented)")
        
        st.divider()
        
        # Auto-refresh settings
        st.markdown("### 🔄 Auto-Refresh Settings")
        
        refresh_interval = st.slider(
            "Refresh interval (seconds)",
            min_value=5,
            max_value=60,
            value=st.session_state.auto_refresh_interval,
            step=5,
            key="slider_refresh_interval"
        )
        st.session_state.auto_refresh_interval = refresh_interval
        
        st.caption("⏱️ Dashboard will check for new results at this interval when analysis is running.")
        
        st.divider()
        
        # Information
        st.markdown("## 📖 About")
        
        st.markdown("""
**CI/CD Failure Predictor & RCA Dashboard v1.0**

Integrated analysis platform combining:
- **ORC** for commit analysis
- **Metadata-Pipeline** for failure prediction
- **graph-doc-gen** for code relationships
- **Log Pipeline** for CI log analysis

### Workflows:

**Workflow 1** — Metadata Prediction + Graph RCA
- Analyzes commits with LightGBM
- Explains predictions with SHAP
- Provides graph-based root cause analysis

**Workflow 2** — Automatic CI Log Analysis
- Monitors GitHub Actions workflows
- Analyzes logs when available
- Provides remediation suggestions
        """)
        
        st.divider()
        
        # Status
        st.markdown("## 📊 Status")
        
        if st.button("🔄 Check Backend Status", key="btn_check_status", use_container_width=True):
            with st.spinner("Checking backends..."):
                st.info("Backend status check (not yet implemented)")
        
        st.divider()
        
        # Developer info
        st.markdown("""
**Developer Notes:**

- This dashboard does not modify ORC, Metadata-Pipeline, graph-doc-gen, or Log Pipeline
- All implementations are separated and called via their existing APIs
- GitHub Actions workflow forwarding to Log Pipeline is unchanged
- All results are from actual backend analysis, no mock data
        """)
