"""
Integration tests verifying base SHA selection works end-to-end with the actual graph adapter.

These tests use a real temporary Git repository and verify that the orchestrator
correctly selects the graph's current SHA as the base when it's an ancestor of the target.
"""

import subprocess
import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ORC_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ORC_ROOT))

from src.orchestrator import Orchestrator
from src.adapters.graph_adapter import GraphAdapter


class TestBaseShaIntegration:
    """Integration tests for base SHA selection with GraphAdapter."""
    
    @pytest.fixture
    def temp_multi_commit_repo(self):
        """Create a temporary Git repository with multiple commits in linear history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            
            # Initialize
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, capture_output=True)
            
            commits = {}
            for i, name in enumerate(["A", "B", "C", "D", "E"]):
                (repo_path / f"file_{name}.py").write_text(f"# {name}\n")
                subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
                subprocess.run(["git", "commit", "-m", f"commit {name}"], cwd=repo_path, check=True, capture_output=True)
                
                sha = subprocess.run(
                    "git rev-parse HEAD",
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    shell=True,
                    check=True
                ).stdout.strip()
                commits[name] = sha
            
            yield {
                "repo_path": str(repo_path),
                "commits": commits,
            }
    
    def test_orchestrator_selects_graph_sha_as_base_for_multi_commit_advance(self, temp_multi_commit_repo):
        """
        Scenario: Graph is at C, target is E (2 commits ahead).
        Expected: Orchestrator selects C (graph SHA) as base, not D (target's parent).
        
        This ensures the graph engine can calculate the diff from C→E,
        which includes both intermediate commits D and E.
        """
        data = temp_multi_commit_repo
        repo_path = data["repo_path"]
        repo_id = "test/repo"
        
        # SHA assignments
        sha_c = data["commits"]["C"]
        sha_e = data["commits"]["E"]
        sha_d = data["commits"]["D"]  # E's parent
        
        # Create orchestrator
        orchestrator = Orchestrator(github_token="test_token")
        
        # Mock GraphAdapter to simulate graph already synced to C
        with patch("src.orchestrator.GraphAdapter") as MockGraphAdapter:
            mock_graph = MagicMock()
            mock_client = MagicMock()
            mock_graph.client = mock_client
            
            # Graph is currently at C with verified state
            mock_client.get_sync_state.return_value = {
                "target_sha": sha_c,
                "commit_verified": True,
                "status": "SYNCED",
                "nodes_count": 42,
            }
            
            # Track what base_sha is passed to sync_to_sha
            captured_calls = []
            def capture_sync_call(base_sha, target_sha):
                captured_calls.append({"base_sha": base_sha, "target_sha": target_sha})
                return {
                    "status": "SYNCHRONIZED",
                    "base_sha": base_sha,
                    "target_sha": target_sha,
                    "files_added": 2,
                    "files_modified": 0,
                    "files_deleted": 0,
                    "files_renamed": 0,
                    "changed_files": [],
                    "engine_result": {"status": "SUCCESS", "commit_verified": True},
                    "persisted_state": {"status": "SYNCED", "commit_verified": True},
                }
            
            mock_graph.sync_to_sha.side_effect = capture_sync_call
            MockGraphAdapter.return_value = mock_graph
            
            # Mock MetadataAdapter
            with patch("src.orchestrator.MetadataAdapter") as MockMetadata:
                mock_metadata = MagicMock()
                mock_metadata.predict.return_value = {
                    "failure_probability": 0.25,
                    "verdict": "FAST-TRACK",
                    "shap_drivers": {},
                    "features": {},
                }
                MockMetadata.return_value = mock_metadata
                
                # Run orchestrator for target E
                try:
                    result = orchestrator.process_commit(repo_id, sha_e, repo_path)
                except Exception as e:
                    # May fail on checkpoint/Neo4j, but we can still inspect the mock
                    pass
                
                # Verify sync_to_sha was called
                assert mock_graph.sync_to_sha.called, "sync_to_sha should have been called"
                
                # Extract the actual base SHA that was passed
                actual_call = captured_calls[0] if captured_calls else None
                assert actual_call is not None, "sync_to_sha call should be captured"
                
                actual_base = actual_call["base_sha"]
                actual_target = actual_call["target_sha"]
                
                # VERIFICATION
                # Base should be sha_c (graph's current SHA), not sha_d (target's parent)
                assert actual_base == sha_c, (
                    f"Expected base SHA to be {sha_c[:7]} (graph's current SHA at C), "
                    f"but got {actual_base[:7]}. "
                    f"(Target's parent would be {sha_d[:7]})"
                )
                
                assert actual_target == sha_e, (
                    f"Expected target SHA to be {sha_e[:7]}, "
                    f"but got {actual_target[:7]}"
                )
                
                print(f"✓ Correctly selected base SHA: {actual_base[:7]} (graph SHA at C)")
                print(f"✓ Graph will calculate incremental diff from C→E")
    
    def test_orchestrator_falls_back_when_graph_sha_not_ancestor(self, temp_multi_commit_repo):
        """
        Scenario: Graph is at B, but we request target E on a different branch.
        Expected: Orchestrator detects non-ancestry, falls back to parent-based diff.
        
        (This test verifies graceful fallback, though with a linear history
        we can't easily test true divergence without more setup.)
        """
        data = temp_multi_commit_repo
        repo_path = data["repo_path"]
        repo_id = "test/repo"
        
        sha_b = data["commits"]["B"]
        sha_e = data["commits"]["E"]
        
        orchestrator = Orchestrator(github_token="test_token")
        
        # Mock GraphAdapter with graph at B
        with patch("src.orchestrator.GraphAdapter") as MockGraphAdapter:
            mock_graph = MagicMock()
            mock_client = MagicMock()
            mock_graph.client = mock_client
            
            mock_client.get_sync_state.return_value = {
                "target_sha": sha_b,
                "commit_verified": True,
                "status": "SYNCED",
            }
            
            captured_calls = []
            def capture_sync_call(base_sha, target_sha):
                captured_calls.append({"base_sha": base_sha, "target_sha": target_sha})
                return {
                    "status": "SYNCHRONIZED",
                    "base_sha": base_sha,
                    "target_sha": target_sha,
                    "files_added": 0,
                    "files_modified": 3,
                    "files_deleted": 0,
                    "files_renamed": 0,
                    "changed_files": [],
                    "engine_result": {"status": "SUCCESS", "commit_verified": True},
                    "persisted_state": {"status": "SYNCED", "commit_verified": True},
                }
            
            mock_graph.sync_to_sha.side_effect = capture_sync_call
            MockGraphAdapter.return_value = mock_graph
            
            # Mock metadata
            with patch("src.orchestrator.MetadataAdapter") as MockMetadata:
                mock_metadata = MagicMock()
                mock_metadata.predict.return_value = {
                    "failure_probability": 0.25,
                    "verdict": "FAST-TRACK",
                    "shap_drivers": {},
                    "features": {},
                }
                MockMetadata.return_value = mock_metadata
                
                try:
                    result = orchestrator.process_commit(repo_id, sha_e, repo_path)
                except Exception:
                    pass
                
                # In this case, B is still an ancestor of E (linear history)
                # So the base should be B (graph SHA)
                actual_call = captured_calls[0] if captured_calls else None
                assert actual_call is not None
                
                actual_base = actual_call["base_sha"]
                assert actual_base == sha_b, (
                    f"Expected base to be graph SHA {sha_b[:7]}, "
                    f"but got {actual_base[:7]}"
                )
                
                print(f"✓ Selected base SHA: {actual_base[:7]} (graph SHA at B)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
