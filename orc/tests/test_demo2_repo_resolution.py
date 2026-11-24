"""Tests for Workflow 1 repository cache resolution and GraphAdapter commit validation."""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

ORC_ROOT = Path(__file__).resolve().parents[1]
if str(ORC_ROOT) not in sys.path:
    sys.path.insert(0, str(ORC_ROOT))

from src.orchestrator import Orchestrator
from src.adapters.graph_adapter import GraphAdapter
from src.errors import InvalidCommitException


REPO_CACHE_ROOT = Path(__file__).resolve().parents[2] / "Metadata-Pipeline-main" / ".repo_cache"
FLASK_CACHE_DIR = REPO_CACHE_ROOT / "Aditya-C-S__flask"
CLICK_CACHE_DIR = REPO_CACHE_ROOT / "pallets__click"
DEMO2_COMMIT_SHA = "e5b8365d976867f3433896bdbb068f61696653ae"


def _create_mock_graph_adapter(repo_id: str, repo_path: str):
    """Helper to instantiate GraphAdapter with valid mocked Neo4jClient."""
    with patch("src.adapters.graph_adapter.Neo4jClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.database = "graphdoc"
        MockClient.return_value = mock_instance
        return GraphAdapter(repo_id=repo_id, repo_path=repo_path)


def test_workflow1_resolves_correct_repo_cache_for_flask():
    """Verify that Workflow 1 resolves the correct repository cache for Aditya-C-S/flask."""
    import importlib.util
    orc_handler_path = Path(__file__).resolve().parents[2] / "streamlit-dashboard" / "src" / "backend" / "orc_handler.py"
    spec = importlib.util.spec_from_file_location("orc_handler_module", orc_handler_path)
    orc_handler_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(orc_handler_mod)

    # Initialize handler with click repo path
    handler = orc_handler_mod.ORCHandler(repo_path=str(CLICK_CACHE_DIR))
    
    # Resolving for Aditya-C-S/flask must resolve to Flask cache, not Click
    resolved_flask = handler.resolve_repo_path("Aditya-C-S/flask")
    assert resolved_flask is not None
    assert Path(resolved_flask).resolve() == FLASK_CACHE_DIR.resolve()
    assert Path(resolved_flask).name == "Aditya-C-S__flask"

    # Resolving for pallets/click must resolve to Click cache
    resolved_click = handler.resolve_repo_path("pallets/click")
    assert resolved_click is not None
    assert Path(resolved_click).resolve() == CLICK_CACHE_DIR.resolve()


def test_orchestrator_path_resolution_prioritizes_matching_cache():
    """Verify orchestrator selects the correct repo path where target_sha exists."""
    orch = Orchestrator(github_token="fake_token")
    
    # When passed pallets__click as candidate for Aditya-C-S/flask@e5b8365d...
    # it must reject pallets__click and resolve to Aditya-C-S__flask
    resolved = orch._resolve_repo_path_for_repo(
        repo_id="Aditya-C-S/flask",
        target_sha=DEMO2_COMMIT_SHA,
        candidate_repo_path=str(CLICK_CACHE_DIR),
        prediction_repo_path=str(FLASK_CACHE_DIR),
    )
    assert Path(resolved).resolve() == FLASK_CACHE_DIR.resolve()


def test_graph_adapter_validates_target_commit_in_flask_repo():
    """Verify GraphAdapter validates commit in the correct repository."""
    if not FLASK_CACHE_DIR.exists():
        pytest.skip("Flask cache not available locally")

    adapter = _create_mock_graph_adapter(
        repo_id="Aditya-C-S/flask",
        repo_path=str(FLASK_CACHE_DIR),
    )
    try:
        # Validating the commit must succeed without exception
        adapter._validate_commits(base_sha=DEMO2_COMMIT_SHA, target_sha=DEMO2_COMMIT_SHA)
        assert Path(adapter.repo_path).resolve() == FLASK_CACHE_DIR.resolve()
    finally:
        adapter.close()


def test_graph_adapter_self_corrects_mismatched_repo_path():
    """Verify GraphAdapter detects mismatched candidate path and self-corrects to verified cache."""
    if not FLASK_CACHE_DIR.exists():
        pytest.skip("Flask cache not available locally")

    # Initialize GraphAdapter with pallets__click for Aditya-C-S/flask
    adapter = _create_mock_graph_adapter(
        repo_id="Aditya-C-S/flask",
        repo_path=str(CLICK_CACHE_DIR),
    )
    try:
        # Validation should find commit in Aditya-C-S__flask and update self.repo_path
        adapter._validate_commits(base_sha=DEMO2_COMMIT_SHA, target_sha=DEMO2_COMMIT_SHA)
        assert Path(adapter.repo_path).resolve() == FLASK_CACHE_DIR.resolve()
    finally:
        adapter.close()


def test_missing_or_mismatched_repo_does_not_silently_fallback():
    """Verify that an unknown commit or non-existent repo fails loudly and does not use an unrelated cache."""
    adapter = _create_mock_graph_adapter(
        repo_id="nonexistent-org/nonexistent-repo",
        repo_path=str(CLICK_CACHE_DIR),
    )
    try:
        with pytest.raises(InvalidCommitException) as exc_info:
            adapter._validate_commits(
                base_sha="0000000000000000000000000000000000000000",
                target_sha="1111111111111111111111111111111111111111",
            )
        assert "not found in nonexistent-org/nonexistent-repo" in str(exc_info.value)
        # Ensure it did not silently adopt an unrelated cache
        assert "pallets__click" in adapter.repo_path
    finally:
        adapter.close()
