"""Tests for Workflow 2 branch preservation and Git metadata precedence."""

import sys
from pathlib import Path
from unittest.mock import patch
import pytest

# Ensure logpipeline root is in sys.path
LOGPIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(LOGPIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(LOGPIPELINE_ROOT))

from src.demo.demo_manager import UnifiedDemoManager


def test_explicit_branch_preserved_when_git_metadata_fails():
    """Verify explicit branch is preserved even when Git metadata extraction returns fallback main."""
    mgr = UnifiedDemoManager.get_instance()
    
    # Simulate run creation with explicitly supplied branch
    run = mgr.create_run(
        repo_id="Aditya-C-S/flask",
        commit_sha="e5b8365d976867f3433896bdbb068f61696653ae",
        branch="demo/intentional-test-failure",
        auto_advance=False,
    )

    # 1. Authoritative branch in commit_info must be the explicit branch
    assert run.commit_info["branch"] == "demo/intentional-test-failure"
    assert run.commit_info["branch"] != "main"

    # 2. to_dict serialization must reflect the explicit branch
    run_dict = run.to_dict()
    assert run_dict["commit_info"]["branch"] == "demo/intentional-test-failure"
    assert run_dict["branch"] == "demo/intentional-test-failure"


def test_valid_extracted_branch_used_when_no_branch_supplied():
    """Verify that when no branch is supplied, valid Git extracted branch is used."""
    mgr = UnifiedDemoManager.get_instance()

    mock_git_info = {
        "available": True,
        "commit_sha": "test12345678",
        "author": "tester",
        "timestamp": "2026-11-24T12:00:00Z",
        "message": "test commit",
        "branch": "feature/valid-git-branch",
    }

    with patch("src.demo.demo_manager.GitMetadataExtractor.get_commit_info", return_value=mock_git_info):
        run = mgr.create_run(
            repo_id="test-org/sample-service",
            commit_sha="test12345678",
            branch=None,  # No branch supplied
            auto_advance=False,
        )

        assert run.commit_info["branch"] == "feature/valid-git-branch"
        assert run.to_dict()["branch"] == "feature/valid-git-branch"


def test_fallback_main_used_when_no_branch_and_git_unavailable():
    """Verify that when no branch is supplied and Git extraction is unavailable, fallback is main."""
    mgr = UnifiedDemoManager.get_instance()

    mock_fallback_info = {
        "available": False,
        "commit_sha": "test9999",
        "author": "demo-author",
        "timestamp": "2026-11-24T12:00:00Z",
        "message": "Local commit",
        "branch": "main",
    }

    with patch("src.demo.demo_manager.GitMetadataExtractor.get_commit_info", return_value=mock_fallback_info):
        run = mgr.create_run(
            repo_id="test-org/sample-service",
            commit_sha="test9999",
            branch=None,
            auto_advance=False,
        )

        assert run.commit_info["branch"] == "main"
        assert run.to_dict()["branch"] == "main"


def test_explicit_branch_not_overwritten_by_valid_git_branch():
    """Verify that an explicitly supplied branch takes precedence over local Git branch."""
    mgr = UnifiedDemoManager.get_instance()

    mock_git_info = {
        "available": True,
        "commit_sha": "test12345678",
        "author": "tester",
        "timestamp": "2026-11-24T12:00:00Z",
        "message": "test commit",
        "branch": "local-git-branch",
    }

    with patch("src.demo.demo_manager.GitMetadataExtractor.get_commit_info", return_value=mock_git_info):
        run = mgr.create_run(
            repo_id="test-org/sample-service",
            commit_sha="test12345678",
            branch="explicit/requested-branch",
            auto_advance=False,
        )

        # Explicitly supplied branch must be preserved
        assert run.commit_info["branch"] == "explicit/requested-branch"
        assert run.to_dict()["branch"] == "explicit/requested-branch"
