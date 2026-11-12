#!/usr/bin/env python3
"""
Strict correctness tests for NO_CHANGES handling in graph synchronization.

These tests verify that:
1. NO_CHANGES genuinely advances SyncState via transactional Neo4j write
2. Mismatched base SHA is rejected
3. Unverified existing state is rejected
4. Missing SyncState is properly initialized with transactional write
5. Failed persistence is caught and never advances checkpoint
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import pytest

ORC_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ORC_ROOT))

from src.adapters.graph_adapter import GraphAdapter
from src.errors import GraphSyncException


class TestNoChangesStrictValidation:
    """Test strict validation and SyncState advancement for NO_CHANGES."""
    
    def _make_adapter(self, repo_id="test/repo"):
        """Create adapter with mocked Neo4jClient."""
        with patch('src.adapters.graph_adapter.Neo4jClient') as MockClient:
            mock_instance = MagicMock()
            mock_instance.database = "graphdoc"
            MockClient.return_value = mock_instance
            return GraphAdapter(repo_id, "/tmp/repo"), mock_instance
    
    def test_no_changes_with_matching_base_sha_advances_syncstate(self):
        """
        Test NO_CHANGES with correct base SHA: SyncState is transactionally advanced.
        
        Scenario:
        - Graph currently at sha_a (verified, SYNCED)
        - Request sync from sha_a to sha_b
        - Engine returns NO_CHANGES (no files changed between a and b)
        - SyncState should be advanced from sha_a to sha_b
        """
        adapter, mock_client = self._make_adapter()
        
        sha_a = "aaaa" * 10
        sha_b = "bbbb" * 10
        
        # Existing SyncState: graph at sha_a, verified, synced
        existing_sync = {
            "repo_id": "test/repo",
            "target_sha": sha_a,
            "commit_verified": True,
            "status": "SYNCED",
            "nodes_count": 50,
        }
        
        # After transactional write, SyncState should show sha_b
        updated_sync = {
            "repo_id": "test/repo",
            "target_sha": sha_b,
            "base_sha": sha_a,
            "commit_verified": True,
            "status": "SYNCED",
            "synced_at": "2026-10-22T12:00:00",
            "updated_at": "2026-10-22T12:00:01",
        }
        
        # Mock session and transaction
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"syncstate": updated_sync}
        mock_session.run.return_value = mock_result
        
        # Mock context manager for session
        mock_client.session.return_value = MagicMock(
            __enter__=MagicMock(return_value=mock_session),
            __exit__=MagicMock(return_value=None)
        )
        
        # Mock get_sync_state: return updated state after write verification
        mock_client.get_sync_state.side_effect = [
            updated_sync,   # Verification after write (only called once)
        ]
        
        # Call the method
        result = adapter._handle_no_changes_syncstate(sha_a, sha_b, existing_sync)
        
        # VERIFY: SyncState was updated
        assert result["target_sha"] == sha_b, "SyncState target_sha should be advanced to sha_b"
        assert result["commit_verified"] is True
        assert result["status"] == "SYNCED"
        
        # VERIFY: Neo4j session.run was called with correct Cypher
        mock_session.run.assert_called_once()
        call_args = mock_session.run.call_args
        cypher_query = call_args[0][0]
        assert "MERGE" in cypher_query, "Should use MERGE for atomic write"
        assert "target_sha" in cypher_query, "Should update target_sha"
        assert "commit_verified = true" in cypher_query
        assert "status = 'SYNCED'" in cypher_query
        
        # VERIFY: get_sync_state called once (verification after write)
        assert mock_client.get_sync_state.call_count == 1
        
        adapter.close()
    
    def test_no_changes_with_mismatched_base_sha_rejected(self):
        """
        Test NO_CHANGES with mismatched base SHA: raises exception.
        
        Scenario:
        - Graph currently at sha_a
        - Request sync from sha_x (different!)
        - This indicates state corruption
        - Should raise GraphSyncException
        """
        adapter, mock_client = self._make_adapter()
        
        sha_a = "aaaa" * 10
        sha_b = "bbbb" * 10
        sha_x = "xxxx" * 10  # Wrong base!
        
        existing_sync = {
            "repo_id": "test/repo",
            "target_sha": sha_a,
            "commit_verified": True,
            "status": "SYNCED",
            "nodes_count": 50,
        }
        
        # Call with mismatched base_sha (sha_x instead of sha_a)
        with pytest.raises(GraphSyncException) as exc_info:
            adapter._handle_no_changes_syncstate(sha_x, sha_b, existing_sync)
        
        # VERIFY: Exception explains the mismatch
        assert "mismatch" in str(exc_info.value).lower()
        assert "state corruption" in str(exc_info.value).lower()
        
        # VERIFY: No Neo4j write was attempted
        mock_client.session.assert_not_called()
        
        adapter.close()
    
    def test_no_changes_with_unverified_existing_state_rejected(self):
        """
        Test NO_CHANGES with unverified existing state: raises exception.
        
        Scenario:
        - Graph SyncState exists but commit_verified=False
        - Cannot make safety guarantees
        - Should raise GraphSyncException
        """
        adapter, mock_client = self._make_adapter()
        
        sha_a = "aaaa" * 10
        sha_b = "bbbb" * 10
        
        # Existing SyncState: UNVERIFIED
        existing_sync = {
            "repo_id": "test/repo",
            "target_sha": sha_a,
            "commit_verified": False,  # Problem!
            "status": "SYNCED",
            "nodes_count": 50,
        }
        
        with pytest.raises(GraphSyncException) as exc_info:
            adapter._handle_no_changes_syncstate(sha_a, sha_b, existing_sync)
        
        assert "commit_verified=false" in str(exc_info.value).lower()
        mock_client.session.assert_not_called()
        
        adapter.close()
    
    def test_no_changes_with_wrong_status_rejected(self):
        """
        Test NO_CHANGES with wrong SyncState status: raises exception.
        """
        adapter, mock_client = self._make_adapter()
        
        sha_a = "aaaa" * 10
        sha_b = "bbbb" * 10
        
        # Existing SyncState: wrong status
        existing_sync = {
            "repo_id": "test/repo",
            "target_sha": sha_a,
            "commit_verified": True,
            "status": "SYNCING",  # Wrong! Expected SYNCED
            "nodes_count": 50,
        }
        
        with pytest.raises(GraphSyncException) as exc_info:
            adapter._handle_no_changes_syncstate(sha_a, sha_b, existing_sync)
        
        assert "status" in str(exc_info.value).lower()
        assert "inconsistent" in str(exc_info.value).lower()
        mock_client.session.assert_not_called()
        
        adapter.close()
    
    def test_no_changes_with_missing_existing_state_creates_new(self):
        """
        Test NO_CHANGES with no existing SyncState: creates new via transactional write.
        
        Scenario:
        - Initial sync with NO_CHANGES
        - No prior SyncState exists
        - Should transactionally create SyncState at target_sha
        """
        adapter, mock_client = self._make_adapter()
        
        sha_a = "aaaa" * 10
        sha_b = "bbbb" * 10
        
        # New SyncState created by transactional write
        new_sync = {
            "repo_id": "test/repo",
            "target_sha": sha_b,
            "base_sha": sha_a,
            "commit_verified": True,
            "status": "SYNCED",
            "synced_at": "2026-10-22T12:00:00",
            "updated_at": "2026-10-22T12:00:01",
        }
        
        # Mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"syncstate": new_sync}
        mock_session.run.return_value = mock_result
        
        # Mock context manager
        mock_client.session.return_value = MagicMock(
            __enter__=MagicMock(return_value=mock_session),
            __exit__=MagicMock(return_value=None)
        )
        
        # Mock get_sync_state: verification read
        mock_client.get_sync_state.return_value = new_sync
        
        # Call with no existing_sync (initial sync)
        result = adapter._handle_no_changes_syncstate(sha_a, sha_b, None)
        
        # VERIFY: SyncState was created
        assert result["target_sha"] == sha_b
        assert result["commit_verified"] is True
        assert result["status"] == "SYNCED"
        
        # VERIFY: Transactional write was called
        mock_session.run.assert_called_once()
        
        # VERIFY: Verification read after write
        mock_client.get_sync_state.assert_called_with("test/repo")
        
        adapter.close()
    
    def test_no_changes_with_failed_neo4j_write_raises(self):
        """
        Test NO_CHANGES with failed Neo4j write: raises exception.
        
        Scenario:
        - Neo4j transaction fails
        - get_sync_state returns None (write didn't persist)
        - Should raise GraphSyncException
        """
        adapter, mock_client = self._make_adapter()
        
        sha_a = "aaaa" * 10
        sha_b = "bbbb" * 10
        
        existing_sync = {
            "repo_id": "test/repo",
            "target_sha": sha_a,
            "commit_verified": True,
            "status": "SYNCED",
            "nodes_count": 50,
        }
        
        # Mock Neo4j write failure
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = None  # Write returned nothing!
        mock_session.run.return_value = mock_result
        mock_client.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_client.session.return_value.__exit__ = MagicMock(return_value=None)
        
        # Call with write failure
        with pytest.raises(GraphSyncException) as exc_info:
            adapter._handle_no_changes_syncstate(sha_a, sha_b, existing_sync)
        
        assert "no result" in str(exc_info.value).lower()
        
        adapter.close()
    
    def test_no_changes_with_verification_mismatch_raises(self):
        """
        Test NO_CHANGES with verification mismatch: raises exception.
        
        Scenario:
        - SyncState was written to Neo4j
        - But verification read returns different target_sha
        - Indicates persistence error or data corruption
        """
        adapter, mock_client = self._make_adapter()
        
        sha_a = "aaaa" * 10
        sha_b = "bbbb" * 10
        sha_wrong = "cccc" * 10
        
        existing_sync = {
            "repo_id": "test/repo",
            "target_sha": sha_a,
            "commit_verified": True,
            "status": "SYNCED",
        }
        
        # Mock transactional write
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"syncstate": {"target_sha": sha_b, "commit_verified": True}}
        mock_session.run.return_value = mock_result
        
        # Mock context manager
        mock_client.session.return_value = MagicMock(
            __enter__=MagicMock(return_value=mock_session),
            __exit__=MagicMock(return_value=None)
        )
        
        # Mock verification read: returns DIFFERENT target_sha (corruption!)
        mock_client.get_sync_state.return_value = {
            "repo_id": "test/repo",
            "target_sha": sha_wrong,  # Wrong!
            "commit_verified": True,
            "status": "SYNCED",
        }
        
        with pytest.raises(GraphSyncException) as exc_info:
            adapter._handle_no_changes_syncstate(sha_a, sha_b, existing_sync)
        
        assert "mismatch" in str(exc_info.value).lower()
        assert "corrupted" in str(exc_info.value).lower() or "failed" in str(exc_info.value).lower()
        
        adapter.close()


class TestNoChangesInFullFlow:
    """Test NO_CHANGES handling in the complete sync_to_sha flow."""
    
    @patch('src.adapters.graph_adapter.GraphAdapter._validate_commits')
    @patch('src.adapters.graph_adapter.get_commit_diff')
    @patch('src.adapters.graph_adapter._ensure_graph_working_copy_at_sha')
    @patch('src.adapters.graph_adapter.update_graph_from_diff')
    @patch('src.adapters.graph_adapter.Neo4jClient')
    def test_full_flow_no_changes_advances_syncstate(
        self, MockClient, mock_engine, mock_working_copy, mock_diff, mock_validate
    ):
        """
        Test full sync_to_sha flow: NO_CHANGES properly advances SyncState.
        """
        # Setup mocks
        mock_client = MagicMock()
        mock_client.database = "graphdoc"
        MockClient.return_value = mock_client
        
        mock_working_copy.return_value = "/tmp/graph_cache"
        mock_diff.return_value = {"added": [], "modified": [], "deleted": [], "renamed": []}
        mock_validate.return_value = None
        
        sha_a = "aaaa" * 10
        sha_b = "bbbb" * 10
        
        # Graph at sha_a (verified, synced)
        existing_sync = {
            "repo_id": "test/repo",
            "target_sha": sha_a,
            "commit_verified": True,
            "status": "SYNCED",
            "nodes_count": 50,
        }
        
        # After NO_CHANGES write, SyncState advanced to sha_b
        updated_sync = {
            "repo_id": "test/repo",
            "target_sha": sha_b,
            "base_sha": sha_a,
            "commit_verified": True,
            "status": "SYNCED",
            "nodes_count": 50,
        }
        
        # Mock Neo4j session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"syncstate": updated_sync}
        mock_session.run.return_value = mock_result
        
        # Mock context manager
        mock_client.session.return_value = MagicMock(
            __enter__=MagicMock(return_value=mock_session),
            __exit__=MagicMock(return_value=None)
        )
        
        # Mock get_sync_state: existing (Step 3), then updated after write (verification)
        mock_client.get_sync_state.side_effect = [
            existing_sync,   # Step 3: Check existing graph state
            updated_sync,    # Verification after write
        ]
        
        # Engine returns NO_CHANGES
        engine_result = {
            "status": "NO_CHANGES",
            "repo_id": "test/repo",
            "target_sha": sha_b,
            "commit_verified": True,
            "files_parsed": 0,
            "nodes_count": 50,
        }
        mock_engine.return_value = engine_result
        
        # Call sync_to_sha
        adapter = GraphAdapter("test/repo", "/tmp/repo")
        result = adapter.sync_to_sha(sha_a, sha_b)
        
        # VERIFY: Result is SYNCHRONIZED
        assert result["status"] == "SYNCHRONIZED"
        assert result["target_sha"] == sha_b
        
        # VERIFY: SyncState was persisted correctly
        assert result["persisted_state"]["target_sha"] == sha_b
        assert result["persisted_state"]["commit_verified"] is True
        
        # VERIFY: Neo4j write was called
        mock_session.run.assert_called_once()
        
        adapter.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
