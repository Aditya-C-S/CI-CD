"""Tests for Demo 2 local unpushed commit analysis support in Workflow 1."""

import os
import sys
import pytest
from pathlib import Path

# Setup paths
ORC_ROOT = Path(__file__).resolve().parents[1]
if str(ORC_ROOT) not in sys.path:
    sys.path.insert(0, str(ORC_ROOT))

FRIEND_VERSION_ROOT = ORC_ROOT.parent
METADATA_PIPELINE_ROOT = FRIEND_VERSION_ROOT / "Metadata-Pipeline-main"
if str(METADATA_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(METADATA_PIPELINE_ROOT))

import importlib.util
orc_handler_path = FRIEND_VERSION_ROOT / "streamlit-dashboard" / "src" / "backend" / "orc_handler.py"
spec = importlib.util.spec_from_file_location("orc_handler_module", orc_handler_path)
orc_handler_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orc_handler_mod)
ORCHandler = orc_handler_mod.ORCHandler

git_engine_path = METADATA_PIPELINE_ROOT / "Metadata_Extractor" / "core" / "git_engine.py"
ge_spec = importlib.util.spec_from_file_location("real_git_engine", git_engine_path)
ge_mod = importlib.util.module_from_spec(ge_spec)
ge_spec.loader.exec_module(ge_mod)
check_commit_provenance = ge_mod.check_commit_provenance

from src.models import CommitPredictionResult, GraphSyncStatus


def test_commit_provenance_detection():
    """Verify check_commit_provenance detects local vs remote commits."""
    cache_dir = FRIEND_VERSION_ROOT / "Metadata-Pipeline-main" / ".repo_cache" / "Aditya-C-S__flask"
    if cache_dir.exists() and (cache_dir / ".git").exists():
        # Target commit was pushed to origin/demo/intentional-test-failure
        target_sha = "e5b8365d976867f3433896bdbb068f61696653ae"
        is_local, src = check_commit_provenance(cache_dir, target_sha)
        assert isinstance(is_local, bool)
        assert isinstance(src, str)

    # Empty SHA returns default remote HEAD
    is_local, src = check_commit_provenance(FRIEND_VERSION_ROOT, "")
    assert is_local is False
    assert "Remote" in src

    # Nonexistent SHA returns local commit fallback
    is_local, src = check_commit_provenance(FRIEND_VERSION_ROOT, "0000000000000000000000000000000000000000")
    assert is_local is True
    assert src == "Local Unpushed Commit"


def test_commit_prediction_result_includes_provenance_fields():
    """Verify CommitPredictionResult models commit_source and is_local_commit."""
    result = CommitPredictionResult(
        repository_identity="Aditya-C-S/flask",
        target_sha="e5b8365d976867f3433896bdbb068f61696653ae",
        failure_probability=0.85,
        verdict="PRE-MERGE BLOCK",
        shap_drivers={"positive": [], "negative": []},
        graph_status=GraphSyncStatus.SYNCHRONIZED,
        commit_source="Local Unpushed Commit",
        is_local_commit=True,
    )
    result_dict = result.to_dict()
    assert result_dict["commit_source"] == "Local Unpushed Commit"
    assert result_dict["is_local_commit"] is True


def test_orc_handler_transform_preserves_provenance():
    """Verify ORCHandler transforms commit provenance into dashboard results."""
    handler = ORCHandler()
    raw_result = {
        "repository_identity": "Aditya-C-S/flask",
        "target_sha": "e5b8365d976867f3433896bdbb068f61696653ae",
        "failure_probability": 0.85,
        "verdict": "PRE-MERGE BLOCK",
        "shap_drivers": {"positive": [], "negative": []},
        "graph_status": "SYNCHRONIZED",
        "graph_files_changed": {"added": 0, "modified": 2, "deleted": 0, "renamed": 0},
        "suspicious_files": [],
        "timestamp": "2026-11-24T22:00:00",
        "processing_time_ms": 450.0,
        "commit_source": "Local Unpushed Commit",
        "is_local_commit": True,
    }
    transformed = handler.transform_result(raw_result, "Aditya-C-S/flask")
    assert transformed["commit_source"] == "Local Unpushed Commit"
    assert transformed["is_local_commit"] is True
    assert transformed["target_sha"] == "e5b8365d976867f3433896bdbb068f61696653ae"
