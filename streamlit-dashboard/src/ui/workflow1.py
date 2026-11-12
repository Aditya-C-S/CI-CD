"""
Workflow 1: Metadata Prediction + Graph RCA
Displays LightGBM failure probability, SHAP explanations, suspicious files, graph sync status, and optional Neo4j graph visualization.
"""

import streamlit as st
import logging
from datetime import datetime
from src.state.session import get_wf1_status_display, reset_wf1_state
from src.backend.orc_handler import create_orc_handler

logger = logging.getLogger(__name__)


def render_workflow1():
    """Render Workflow 1 UI."""
    
    # Status indicator
    st.markdown(f"**Status:** {get_wf1_status_display(st.session_state.wf1_status)}")
    
    # Check if inputs are valid
    is_valid = (
        st.session_state.github_repo.strip() != "" and
        "/" in st.session_state.github_repo and
        st.session_state.commit_sha.strip() != "" and
        len(st.session_state.commit_sha.strip()) >= 7
    )
    
    # Analyze Commit Button
    col1, col2 = st.columns([3, 1], gap="small")
    
    with col1:
        if st.button(
            "🔍 Analyze Commit",
            disabled=not is_valid or st.session_state.wf1_status == "analyzing",
            use_container_width=True,
            key="btn_analyze_commit"
        ):
            st.session_state.wf1_status = "analyzing"
            st.session_state.wf1_results = None
            st.session_state.wf1_error = None
            st.rerun()
    
    with col2:
        if st.button(
            "🔄 Reset",
            use_container_width=True,
            key="btn_wf1_reset"
        ):
            reset_wf1_state()
            st.rerun()
    
    st.divider()
    
    # Display analysis results based on status
    if st.session_state.wf1_status == "idle" and st.session_state.wf1_results is None:
        st.info("👆 Click 'Analyze Commit' to start the analysis", icon="ℹ️")
    
    elif st.session_state.wf1_status == "analyzing":
        _invoke_orc_analysis()
    
    elif st.session_state.wf1_status == "completed" and st.session_state.wf1_results:
        render_wf1_results(st.session_state.wf1_results)
    
    elif st.session_state.wf1_status == "failed":
        st.error(
            f"Analysis failed: {st.session_state.wf1_error}",
            icon="❌"
        )
        if st.button("🔄 Retry", use_container_width=True, key="btn_wf1_retry"):
            st.session_state.wf1_status = "analyzing"
            st.rerun()


def render_wf1_results(results: dict):
    """Render complete ORC analysis results for Workflow 1."""
    
    # Section A: Commit and Analysis Summary
    st.markdown("### 📋 Commit & Analysis Summary")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        target_sha = results.get('target_sha', 'N/A')
        display_sha = target_sha[:7] if len(target_sha) >= 7 else target_sha
        st.code(display_sha, language=None)
        st.caption("Target Commit SHA")
    with col2:
        timestamp = results.get('timestamp', 'N/A')
        st.text(timestamp)
        st.caption("Analysis Timestamp")
    with col3:
        processing_time = results.get('processing_time_ms', 0)
        st.metric("Processing Time", f"{processing_time:.0f}ms")
    
    st.divider()
    
    # Section B: Failure Probability & Verdict (Prominent)
    st.markdown("### 🎯 Failure Prediction & Verdict")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        failure_prob = results.get('failure_probability', 0)
        # Color-code the metric based on risk level
        risk_level = results.get('risk_level', 'MEDIUM')
        if risk_level == 'HIGH':
            st.error(f"**Failure Probability:** {failure_prob:.1%}", icon="🔴")
        elif risk_level == 'MEDIUM':
            st.warning(f"**Failure Probability:** {failure_prob:.1%}", icon="🟡")
        else:
            st.success(f"**Failure Probability:** {failure_prob:.1%}", icon="🟢")
    
    with col2:
        verdict = results.get('verdict', 'UNKNOWN')
        st.markdown(f"**ORC Verdict:** `{verdict}`")
        st.caption(f"Risk Level: {risk_level}")
    
    st.divider()
    
    # Section C: SHAP Explanations (Positive & Negative)
    st.markdown("### 🔬 Feature Importance (SHAP Drivers)")
    
    shap_explanations = results.get('shap_explanations', [])
    if shap_explanations:
        # Separate positive and negative drivers
        positive_drivers = [s for s in shap_explanations if s['direction'] == 'positive']
        negative_drivers = [s for s in shap_explanations if s['direction'] == 'negative']
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### ↑ Positive Contributors")
            if positive_drivers:
                for i, driver in enumerate(positive_drivers, 1):
                    st.text(f"{i}. {driver['name']}")
                    st.markdown(f"   Contribution: **+{driver['contribution']:.4f}**")
            else:
                st.info("No positive drivers identified")
        
        with col2:
            st.markdown("#### ↓ Negative Contributors")
            if negative_drivers:
                for i, driver in enumerate(negative_drivers, 1):
                    st.text(f"{i}. {driver['name']}")
                    st.markdown(f"   Contribution: **{driver['contribution']:.4f}**")
            else:
                st.info("No negative drivers identified")
    else:
        st.info("No SHAP explanations available")
    
    st.divider()
    
    # Section D: Graph Synchronization Status
    st.markdown("### 📊 Graph Synchronization & File Changes")
    
    graph_status = results.get('graph_status', 'UNKNOWN')
    status_icon = "✅" if graph_status == "SYNCHRONIZED" else "⚠️" if graph_status == "SKIPPED" else "❌"
    st.markdown(f"{status_icon} **Graph Status:** `{graph_status}`")
    
    if results.get('graph_relationships'):
        relationships = results['graph_relationships']
        files_changed = relationships.get('files_changed', {})
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📝 Added", files_changed.get('added', 0))
        with col2:
            st.metric("✏️ Modified", files_changed.get('modified', 0))
        with col3:
            st.metric("🗑️ Deleted", files_changed.get('deleted', 0))
        with col4:
            st.metric("🔄 Renamed", files_changed.get('renamed', 0))
    
    st.divider()
    
    # Section E: Suspicious Files (IMPORTANT)
    st.markdown("### 🚨 Suspicious Files from Graph Analysis")
    
    suspicious_files = results.get('suspicious_files', [])
    
    if suspicious_files is None:
        st.info("ℹ️ Suspicious-file investigation was not available for this analysis")
    elif len(suspicious_files) == 0:
        st.success("✅ No suspicious files identified in this commit")
    else:
        st.markdown(f"**Found {len(suspicious_files)} suspicious file(s)** likely to cause failures:")
        
        for idx, file_info in enumerate(suspicious_files, 1):
            file_path = file_info.get('path', 'Unknown')
            centrality_score = file_info.get('score', 0)
            file_type = file_info.get('type', 'Unknown')
            all_reasons = file_info.get('all_reasons', [])
            
            # Create expander with score indicator
            score_pct = f"{centrality_score:.0%}"
            expander_title = f"{idx}. {file_path} — Centrality: {score_pct}"
            
            with st.expander(expander_title):
                col1, col2 = st.columns([1, 1])
                with col1:
                    st.metric("Centrality Score", f"{centrality_score:.2f}")
                    st.text(f"File Type: {file_type}")
                with col2:
                    st.markdown("**Reasons:**")
                    if all_reasons:
                        for reason in all_reasons:
                            st.markdown(f"- {reason}")
                    else:
                        st.text("No specific reasons recorded")
    
    st.divider()
    
    # Section F+: Optional Neo4j Graph Viewer
    st.markdown("### 🕸️ Code Graph from Neo4j (Optional)")
    
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        if st.button("📈 View in Dashboard", use_container_width=True, key="btn_view_code_graph"):
            st.session_state.show_graph_viewer = not st.session_state.show_graph_viewer
    
    with col2:
        if st.button("🗂️ Open in Graph Explorer", use_container_width=True, key="btn_open_explorer"):
            _open_graph_explorer(results)
            st.success("✅ Opening professional graph explorer...", icon="✅")
    
    with col3:
        if st.button("📋 Show Details", use_container_width=True, key="btn_graph_details"):
            st.session_state.show_graph_details = not st.session_state.get("show_graph_details", False)
    
    st.divider()
    
    if st.session_state.show_graph_viewer:
        with st.spinner("🔄 Loading code graph from Neo4j..."):
            _render_neo4j_graph_viewer(results)
    
    if st.session_state.get("show_graph_details", False):
        _show_graph_details(results)
    
    # Additional Metadata
    st.markdown("### ℹ️ Analysis Metadata")
    
    with st.expander("Show Raw Features & Debug Info", expanded=False):
        orc_raw = results.get('orc_raw_result', {})
        if orc_raw:
            features = orc_raw.get('features', {})
            if features:
                st.markdown("**Model Features (for debugging):**")
                st.json(features)
            else:
                st.info("No features data available")
        else:
            st.info("No raw ORC result available")
    
    # Last Updated
    if st.session_state.wf1_last_analyzed:
        st.caption(f"Last analyzed: {st.session_state.wf1_last_analyzed}")


def _render_neo4j_graph_viewer(results: dict):
    """Render interactive Neo4j graph viewer using Cytoscape.js."""
    st.markdown("#### 📊 Retrieving code graph from Neo4j...")
    
    try:
        from src.backend.neo4j_graph_retriever import Neo4jGraphRetriever
        
        # Get repository and commit info from results
        repo_id = st.session_state.github_repo
        target_sha = results.get('target_sha', '')
        
        # Create retriever
        retriever = Neo4jGraphRetriever()
        
        if retriever.client is None:
            st.warning("⚠️ Neo4j client not available. Check NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD in .env")
            return
        
        logger.info(f"Retrieving graph for {repo_id}...")
        
        # Retrieve graph data
        graph_data = retriever.retrieve_graph(
            repo_id=repo_id,
            target_sha=target_sha,
            changed_files=results.get('graph_relationships', {}).get('files_changed', {}),
            suspicious_files=results.get('suspicious_files', [])
        )
        
        if graph_data:
            logger.info(f"Graph retrieved: {graph_data['metadata']}")
            # Render graph using Cytoscape
            from src.ui.cytoscape_component import render_cytoscape_graph
            render_cytoscape_graph(graph_data)
        else:
            st.warning("⚠️ Could not retrieve graph data from Neo4j. Graph may be empty or out of sync.")
            st.info("Verify that:")
            st.info("- Neo4j database is running and accessible")
            st.info("- Repository has been synchronized to Neo4j")
            st.info("- REPO_PATH points to the correct repository")
    
    except Exception as e:
        logger.error(f"Failed to render Neo4j graph: {e}", exc_info=True)
        st.error(f"❌ Failed to load graph: {str(e)}")
        st.info("Check the logs for more details.")


def _invoke_orc_analysis():
    """
    Invoke ORC analysis and update session state.
    
    This function is called during the "analyzing" state. It:
    1. Invokes ORC CLI via the handler
    2. Transforms the result
    3. Updates session state to either "completed" or "failed"
    4. Triggers a rerun
    """
    with st.spinner("🔄 Invoking ORC and analyzing commit..."):
        try:
            # Create ORC handler
            handler = create_orc_handler()
            
            # Invoke ORC
            st.info("Querying Metadata-Pipeline and graph-doc-gen for results...", icon="ℹ️")
            
            raw_result, error = handler.analyze_commit(
                repo_id=st.session_state.github_repo,
                target_sha=st.session_state.commit_sha.strip()
            )
            
            if error:
                st.session_state.wf1_status = "failed"
                st.session_state.wf1_error = error
                st.rerun()
                return
            
            # Transform result
            transformed_result = handler.transform_result(
                raw_result,
                st.session_state.github_repo
            )
            
            # Update session state
            st.session_state.wf1_status = "completed"
            st.session_state.wf1_results = transformed_result
            st.session_state.wf1_last_analyzed = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            logger.info(f"ORC analysis completed: {st.session_state.github_repo}@{st.session_state.commit_sha[:7]}")
            
        except Exception as e:
            logger.error(f"Unexpected error during ORC analysis: {e}", exc_info=True)
            st.session_state.wf1_status = "failed"
            st.session_state.wf1_error = f"Unexpected error: {str(e)}"
        
        finally:
            st.rerun()


def _open_graph_explorer(results: dict):
    """Open professional graph explorer in a new browser tab."""
    try:
        from src.backend.neo4j_graph_retriever import Neo4jGraphRetriever
        from src.ui.graph_explorer_integration import save_and_open_graph_explorer
        
        repo_id = st.session_state.github_repo
        target_sha = results.get('target_sha', '')
        
        # Create retriever
        retriever = Neo4jGraphRetriever()
        
        if retriever.client is None:
            st.error("⚠️ Neo4j client not available")
            return
        
        logger.info(f"Retrieving graph for explorer: {repo_id}...")
        
        # Retrieve graph data
        graph_data = retriever.retrieve_graph(
            repo_id=repo_id,
            target_sha=target_sha,
            changed_files=results.get('graph_relationships', {}).get('files_changed', {}),
            suspicious_files=results.get('suspicious_files', [])
        )
        
        if graph_data:
            # Open in professional explorer
            success = save_and_open_graph_explorer(
                graph_data,
                repo_id,
                target_sha,
                suspicious_files=results.get('suspicious_files', []),
                changed_files=results.get('graph_relationships', {}).get('files_changed', {})
            )
            if not success:
                st.error("Failed to open graph explorer")
        else:
            st.error("Could not retrieve graph data from Neo4j")
    
    except Exception as e:
        logger.error(f"Failed to open graph explorer: {e}", exc_info=True)
        st.error(f"❌ Error: {str(e)}")


def _show_graph_details(results: dict):
    """Show detailed graph information and statistics."""
    st.markdown("#### 📊 Graph Details & Statistics")
    
    with st.expander("Graph Metadata", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Repository Info:**")
            st.text(f"Repo: {st.session_state.github_repo}")
            target_sha = results.get('target_sha', 'N/A')
            display_sha = target_sha[:7] if len(target_sha) >= 7 else target_sha
            st.text(f"Commit: {display_sha}")
        
        with col2:
            st.markdown("**Graph Status:**")
            graph_status = results.get('graph_status', 'UNKNOWN')
            st.text(f"Status: {graph_status}")
            if results.get('graph_relationships'):
                rel = results['graph_relationships']
                st.text(f"Files Changed: {rel.get('files_changed', {})}")
    
    st.divider()
