"""
User input section for GitHub repository and commit SHA.
SINGLE INPUT SECTION for both workflows.
"""

import streamlit as st
from src.state.session import reset_wf1_state, reset_wf2_state


def render_input_section():
    """Render the single user input section for both workflows."""
    
    # Create two columns for input fields
    col1, col2 = st.columns([2, 1], gap="small")
    
    with col1:
        repo_input = st.text_input(
            label="GitHub Repository",
            value=st.session_state.github_repo,
            placeholder="e.g., owner/repository-name",
            help="Full GitHub repository in format: owner/repo",
            key="repo_input"
        )
        # Update session state
        if repo_input != st.session_state.github_repo:
            st.session_state.github_repo = repo_input
            reset_wf1_state()
            reset_wf2_state()
    
    with col2:
        sha_input = st.text_input(
            label="Commit SHA",
            value=st.session_state.commit_sha,
            placeholder="Full SHA or short hash",
            help="Full commit SHA (40 chars) or short hash (7+ chars)",
            key="sha_input"
        )
        # Update session state
        if sha_input != st.session_state.commit_sha:
            st.session_state.commit_sha = sha_input
            reset_wf1_state()
            reset_wf2_state()
    
    # Input validation indicator
    is_valid = (
        st.session_state.github_repo.strip() != "" and
        "/" in st.session_state.github_repo and
        st.session_state.commit_sha.strip() != "" and
        len(st.session_state.commit_sha.strip()) >= 7
    )
    
    if is_valid:
        st.success(
            f"✅ Ready: {st.session_state.github_repo} @ {st.session_state.commit_sha[:8]}...",
            icon="✅"
        )
    elif st.session_state.github_repo or st.session_state.commit_sha:
        st.warning(
            "⚠️ Please provide valid GitHub repository (owner/repo) and commit SHA (7+ chars)",
            icon="⚠️"
        )
