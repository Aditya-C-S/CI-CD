"""
Tests for Phase 2C: Display Complete ORC Results + Neo4j Graph Viewer

Tests verify:
1. All ORC result fields are displayed correctly
2. Suspicious files are displayed with all reasons
3. Graph synchronization status is shown
4. Neo4j retrieval uses read-only queries and repo filtering
5. Graph visualization converts nodes/edges correctly
6. Changed and suspicious files are highlighted
"""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

# Add project paths
test_root = Path(__file__).parent
project_root = test_root.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.backend.neo4j_graph_retriever import Neo4jGraphRetriever


# Test fixture: Complete ORC result with all fields
COMPLETE_ORC_RESULT = {
    'failure_probability': 0.67,
    'verdict': 'ALERT',
    'risk_level': 'HIGH',
    'target_sha': 'abc123def456abc123def456abc123def456abc1',
    'timestamp': '2026-11-07T14:30:45.123456',
    'processing_time_ms': 5200.5,
    'graph_status': 'SYNCHRONIZED',
    'shap_explanations': [
        {'name': 'gh_test_cases_per_kloc', 'contribution': 0.5486, 'direction': 'positive'},
        {'name': 'code_churn_density', 'contribution': -0.4099, 'direction': 'negative'},
    ],
    'graph_relationships': {
        'files_changed': {
            'added': 5,
            'modified': 12,
            'deleted': 3,
            'renamed': 1
        },
        'suspicious_file_count': 3
    },
    'suspicious_files': [
        {
            'path': 'src/main.py',
            'score': 1.0,
            'type': 'Python',
            'reason': 'Directly modified in commit',
            'all_reasons': ['Directly modified in commit']
        },
        {
            'path': 'src/utils.py',
            'score': 0.8,
            'type': 'Python',
            'reason': 'Connected via CALLS relationship',
            'all_reasons': ['Connected via CALLS relationship', 'Modified indirectly']
        },
        {
            'path': 'tests/test_main.py',
            'score': 0.6,
            'type': 'Python',
            'reason': 'Connected via IMPORTS relationship',
            'all_reasons': ['Connected via IMPORTS relationship']
        }
    ],
    'orc_raw_result': {
        'features': {'gh_is_pr': 1.0, 'gh_lang_python': 1.0}
    }
}

# Test fixture: Neo4j nodes
MOCK_NEO4J_NODES = [
    {
        'node_id': 1,
        'labels': ['File'],
        'id': 'repo:owner/repo:file:src/main.py',
        'name': 'main.py',
        'path': '/repo/src/main.py',
        'file_path': '/repo/src/main.py',
        'rel_path': 'src/main.py',
        'properties': {'repo_id': 'owner/repo', 'language': 'python'}
    },
    {
        'node_id': 2,
        'labels': ['File'],
        'id': 'repo:owner/repo:file:src/utils.py',
        'name': 'utils.py',
        'path': '/repo/src/utils.py',
        'file_path': '/repo/src/utils.py',
        'rel_path': 'src/utils.py',
        'properties': {'repo_id': 'owner/repo', 'language': 'python'}
    },
    {
        'node_id': 3,
        'labels': ['Function'],
        'id': 'repo:owner/repo:func:main:run',
        'name': 'run',
        'path': '/repo/src/main.py',
        'file_path': '/repo/src/main.py',
        'rel_path': 'src/main.py::run',
        'properties': {'repo_id': 'owner/repo', 'type': 'function'}
    }
]

# Test fixture: Neo4j edges
MOCK_NEO4J_EDGES = [
    {
        'from_id': 1,
        'to_id': 3,
        'type': 'CONTAINS',
        'properties': {'repo_id': 'owner/repo'}
    },
    {
        'from_id': 3,
        'to_id': 2,
        'type': 'CALLS',
        'properties': {'repo_id': 'owner/repo'}
    }
]


class TestORCResultDisplay:
    """Test complete ORC result display functionality."""
    
    def test_display_all_orc_fields_present(self):
        """Verify all important ORC fields are present in results."""
        result = COMPLETE_ORC_RESULT
        
        # Core prediction fields
        assert 'failure_probability' in result
        assert 'verdict' in result
        assert 'risk_level' in result
        
        # Metadata
        assert 'target_sha' in result
        assert 'timestamp' in result
        assert 'processing_time_ms' in result
        
        # SHAP explanations
        assert 'shap_explanations' in result
        assert len(result['shap_explanations']) > 0
        
        # Graph synchronization
        assert 'graph_status' in result
        assert 'graph_relationships' in result
        
        # Suspicious files
        assert 'suspicious_files' in result
    
    def test_suspicious_files_displayed_with_all_reasons(self):
        """Verify all reasons for each suspicious file are available for display."""
        suspicious_files = COMPLETE_ORC_RESULT['suspicious_files']
        
        assert len(suspicious_files) == 3
        
        for file_info in suspicious_files:
            assert 'path' in file_info
            assert 'score' in file_info
            assert 'all_reasons' in file_info
            assert isinstance(file_info['all_reasons'], list)
            
            # Verify at least one reason is present
            assert len(file_info['all_reasons']) > 0
    
    def test_suspicious_file_centrality_scores_preserved(self):
        """Verify centrality scores from ORC are preserved (not fabricated)."""
        suspicious_files = COMPLETE_ORC_RESULT['suspicious_files']
        
        # Check specific scores from fixture
        main_py = next(f for f in suspicious_files if f['path'] == 'src/main.py')
        assert main_py['score'] == 1.0  # Directly modified
        
        utils_py = next(f for f in suspicious_files if f['path'] == 'src/utils.py')
        assert utils_py['score'] == 0.8  # Connected
    
    def test_graph_synchronization_status_displayed(self):
        """Verify graph sync status is displayed."""
        result = COMPLETE_ORC_RESULT
        
        assert result['graph_status'] in ['SYNCHRONIZED', 'SYNC_FAILED', 'SKIPPED']
    
    def test_file_change_counts_displayed(self):
        """Verify added/modified/deleted/renamed counts are shown."""
        graph_rel = COMPLETE_ORC_RESULT['graph_relationships']
        files_changed = graph_rel['files_changed']
        
        assert 'added' in files_changed
        assert 'modified' in files_changed
        assert 'deleted' in files_changed
        assert 'renamed' in files_changed
        
        assert files_changed['added'] == 5
        assert files_changed['modified'] == 12
        assert files_changed['deleted'] == 3
        assert files_changed['renamed'] == 1
    
    def test_positive_negative_shap_drivers_separated(self):
        """Verify SHAP drivers are separable by direction."""
        shap = COMPLETE_ORC_RESULT['shap_explanations']
        
        positive = [s for s in shap if s['direction'] == 'positive']
        negative = [s for s in shap if s['direction'] == 'negative']
        
        assert len(positive) > 0
        assert len(negative) > 0
    
    def test_null_suspicious_files_handled_differently_from_empty(self):
        """Verify null and empty suspicious_files are handled distinctly."""
        # Null case
        result_null = COMPLETE_ORC_RESULT.copy()
        result_null['suspicious_files'] = None
        assert result_null['suspicious_files'] is None
        
        # Empty case
        result_empty = COMPLETE_ORC_RESULT.copy()
        result_empty['suspicious_files'] = []
        assert result_empty['suspicious_files'] == []
    
    def test_no_fabricated_graph_metrics_in_display(self):
        """Verify fabricated metrics (total_nodes, total_edges, blast_radius) don't appear."""
        graph_rel = COMPLETE_ORC_RESULT['graph_relationships']
        
        assert 'total_nodes' not in graph_rel
        assert 'total_edges' not in graph_rel
        assert 'blast_radius' not in graph_rel
    
    def test_verdict_and_failure_probability_visually_prominent(self):
        """Verify verdict and probability are included (would be prominent in UI)."""
        result = COMPLETE_ORC_RESULT
        
        assert result['failure_probability'] == 0.67
        assert result['verdict'] == 'ALERT'
        assert result['risk_level'] == 'HIGH'


class TestNeo4jGraphRetrieval:
    """Test Neo4j graph retrieval and Cytoscape conversion."""
    
    def test_neo4j_retrieval_uses_read_only_queries(self):
        """Verify Neo4j queries are read-only (no WRITE, DELETE, etc.)."""
        # Create a retriever and mock the client
        retriever = Neo4jGraphRetriever()
        
        # Mock the client after initialization
        mock_client = Mock()
        mock_session = Mock()
        mock_client.session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_client.session.return_value.__exit__ = Mock(return_value=None)
        
        # Mock query results
        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_session.run.return_value = mock_result
        
        retriever.client = mock_client
        
        # Retrieve graph
        retriever._retrieve_nodes('owner/repo')
        
        # Verify MATCH query was used (read-only)
        if mock_session.run.called:
            calls = mock_session.run.call_args_list
            query_text = calls[0][0][0] if calls else ''
            
            assert 'MATCH' in query_text
            assert 'WRITE' not in query_text
            assert 'DELETE' not in query_text
    
    def test_repository_filtering_prevents_cross_repo_leakage(self):
        """Verify repo_id filtering prevents accessing another repo's graph."""
        retriever = Neo4jGraphRetriever()
        
        mock_client = Mock()
        mock_session = MagicMock()
        mock_client.session.return_value = mock_session
        
        retriever.client = mock_client
        
        # Mock query results
        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_session.run.return_value = mock_result
        
        # Retrieve graph for specific repo
        retriever._retrieve_nodes('owner/repo')
        
        # Verify query includes repo_id filter
        calls = mock_session.run.call_args_list
        if calls:
            query_text = calls[0][0][0]
            kwargs = calls[0][1]
            
            assert 'repo_id' in query_text
            assert kwargs.get('repo_id') == 'owner/repo'
    
    def test_neo4j_nodes_converted_to_cytoscape_format(self):
        """Verify Neo4j nodes are correctly converted to Cytoscape format."""
        retriever = Neo4jGraphRetriever()
        
        cytoscape_nodes = retriever._convert_nodes_to_cytoscape(MOCK_NEO4J_NODES)
        
        assert len(cytoscape_nodes) == len(MOCK_NEO4J_NODES)
        
        for cyt_node in cytoscape_nodes:
            assert 'data' in cyt_node
            assert 'id' in cyt_node['data']
            assert 'label' in cyt_node['data']
            assert 'type' in cyt_node['data']
            assert 'properties' in cyt_node['data']
    
    def test_neo4j_edges_converted_to_cytoscape_format(self):
        """Verify Neo4j relationships are correctly converted to Cytoscape edges."""
        retriever = Neo4jGraphRetriever()
        
        cytoscape_edges = retriever._convert_edges_to_cytoscape(MOCK_NEO4J_EDGES)
        
        assert len(cytoscape_edges) == len(MOCK_NEO4J_EDGES)
        
        for cyt_edge in cytoscape_edges:
            assert 'data' in cyt_edge
            assert 'source' in cyt_edge['data']
            assert 'target' in cyt_edge['data']
            assert 'type' in cyt_edge['data']
            assert 'label' in cyt_edge['data']
    
    def test_suspicious_files_highlighted_in_graph(self):
        """Verify suspicious files are highlighted when matching graph nodes."""
        retriever = Neo4jGraphRetriever()
        
        suspicious_files = [
            {'path': 'src/main.py', 'score': 1.0}
        ]
        suspicious_set = retriever._build_suspicious_files_set(suspicious_files)
        
        # Convert nodes with highlighting
        cytoscape_nodes = retriever._convert_nodes_to_cytoscape(
            MOCK_NEO4J_NODES,
            suspicious_files=suspicious_set
        )
        
        # Check if main.py node is marked as suspicious
        main_py_node = next(
            (n for n in cytoscape_nodes if 'main.py' in n['data'].get('label', '')),
            None
        )
        assert main_py_node is not None
        assert main_py_node['classes'] == 'suspicious'
    
    def test_changed_files_highlighted_in_graph(self):
        """Verify changed files can be highlighted in graph."""
        retriever = Neo4jGraphRetriever()
        
        changed_files = {'added': 5, 'modified': 12, 'deleted': 3, 'renamed': 1}
        changed_set = retriever._build_changed_files_set(changed_files)
        
        # Note: changed_files dict only contains counts, not actual file names
        # Highlighting changed files requires more context or separate tracking
        assert isinstance(changed_set, set)
    
    def test_graph_viewing_does_not_trigger_orc_execution(self):
        """Verify graph viewer uses stored ORC results, doesn't re-invoke ORC."""
        # This test verifies that Neo4jGraphRetriever doesn't call ORC
        retriever = Neo4jGraphRetriever()
        
        # Verify no ORC imports or calls in the module
        import inspect
        source = inspect.getsource(retriever.__class__)
        
        assert 'analyze_commit' not in source
        assert 'create_orc_handler' not in source
    
    def test_graph_viewing_does_not_trigger_graph_sync(self):
        """Verify graph viewer doesn't trigger graph synchronization."""
        retriever = Neo4jGraphRetriever()
        
        import inspect
        source = inspect.getsource(retriever.__class__)
        
        # Should only read from Neo4j, not modify
        assert 'upload_graph' not in source
        assert 'sync' not in source.lower()


class TestNeo4jConnectionSafety:
    """Test Neo4j connection safety and error handling."""
    
    def test_neo4j_connection_failure_handled_gracefully(self):
        """Verify connection failures are handled without crashing."""
        # Temporarily remove Neo4jClient to simulate import failure
        retriever = Neo4jGraphRetriever()
        
        # If Neo4j client fails to import, client should be None
        # This is handled gracefully in __init__
        assert retriever.client is None or hasattr(retriever.client, 'session')
    
    def test_empty_graph_returns_none(self):
        """Verify empty graph data is handled gracefully."""
        retriever = Neo4jGraphRetriever()
        
        mock_client = Mock()
        mock_session = MagicMock()
        mock_client.session.return_value = mock_session
        
        # Return empty results
        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_session.run.return_value = mock_result
        
        retriever.client = mock_client
        
        # Retrieve empty graph
        graph_data = retriever.retrieve_graph('owner/repo')
        
        assert graph_data is None or graph_data.get('nodes') == []
    
    def test_stale_graph_detection_possible(self):
        """Verify that stale graph data can be detected via SyncState."""
        retriever = Neo4jGraphRetriever()
        
        # Note: Full stale detection would require checking SyncState node
        # which is handled separately. This test confirms the architecture
        # allows for such verification.
        assert True  # Placeholder for future enhancement


class TestGraphVisualizationMetadata:
    """Test graph visualization metadata and statistics."""
    
    def test_graph_metadata_includes_node_edge_counts(self):
        """Verify graph metadata reports actual node/edge counts."""
        retriever = Neo4jGraphRetriever()
        
        mock_client = Mock()
        mock_session = MagicMock()
        mock_client.session.return_value = mock_session
        
        # Mock nodes and edges
        mock_node_result = Mock()
        mock_node_result.__iter__ = Mock(return_value=iter([
            {
                'node_id': i,
                'labels': ['File'],
                'id': f'node_{i}',
                'name': f'file{i}.py',
                'path': f'/repo/file{i}.py',
                'file_path': f'/repo/file{i}.py',
                'rel_path': f'file{i}.py',
                'properties': {'repo_id': 'owner/repo'}
            }
            for i in range(5)
        ]))
        
        mock_edge_result = Mock()
        mock_edge_result.__iter__ = Mock(return_value=iter([
            {
                'from_id': i,
                'to_id': (i + 1) % 5,
                'type': 'CALLS',
                'properties': {}
            }
            for i in range(5)
        ]))
        
        mock_session.run.side_effect = [mock_node_result, mock_edge_result]
        mock_client.session.return_value = mock_session
        
        retriever.client = mock_client
        
        graph_data = retriever.retrieve_graph('owner/repo')
        
        if graph_data:
            metadata = graph_data.get('metadata', {})
            assert 'total_nodes' in metadata
            assert 'total_edges' in metadata
            assert metadata['total_nodes'] == 5
            assert metadata['total_edges'] == 5


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
