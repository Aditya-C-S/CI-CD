"""
Test suite for ORC handler: transformation and field mapping.

This test validates the ORC handler against real terminal output structure
without executing ORC or modifying any external systems.
"""

import json
import pytest
from pathlib import Path

# Add project to path
import sys
test_root = Path(__file__).parent
project_root = test_root.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.backend.orc_handler import ORCHandler


# Synthetic test fixture for transformation logic verification
# 
# NOTE: This fixture uses demo values and is NOT captured from real ORC terminal output.
# Used to verify transformation pipeline without executing actual ORC or Neo4j.
# Real end-to-end testing requires actual ORC execution with genuine repository data.
#
# For actual ORC output example, see: data/archive/ or capture with:
#   python -m src.main owner/repo TARGET_SHA --repo-path /path/to/repo --json
#
REAL_ORC_OUTPUT = {
    "repository_identity": "owner/repo",
    "target_sha": "abc123def456abc123def456abc123def456abc1",
    "failure_probability": 0.531719081238633,
    "verdict": "ALERT",
    "shap_drivers": {
        "positive": [
            ["gh_test_cases_per_kloc", 0.5486],
            ["log_built_commits", 0.464],
            ["total_files_changed", 0.4623]
        ],
        "negative": [
            ["code_churn_density", -0.4099],
            ["gh_num_issue_comments", -0.3752],
            ["gh_num_commits_on_files_touched", -0.2357]
        ]
    },
    "graph_status": "SYNCHRONIZED",
    "graph_files_changed": {
        "added": 8,
        "modified": 11,
        "deleted": 5,
        "renamed": 0
    },
    "suspicious_files": [
        {
            "file_path": "/path/to/repo/src/file_b.py",
            "centrality_score": 1.0,
            "reasons": ["Directly modified in commit"]
        },
        {
            "file_path": "/path/to/repo/.graph_cache/owner__repo/src/utils.py",
            "centrality_score": 0.7,
            "reasons": ["Connected via CALLS relationship"]
        }
    ],
    "timestamp": "2026-11-07T12:34:56.789012",
    "processing_time_ms": 4250.5,
    "features": {
        "gh_is_pr": 1.0,
        "gh_lang_python": 1.0,
        "gh_diff_files_modified": 11.0
    }
}


class TestORCHandlerTransformation:
    """Test ORC result transformation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Use temporary paths for testing
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.repo_path = self.temp_dir
        self.orc_root = self.temp_dir
        
        # Create mock directories
        Path(self.repo_path).mkdir(exist_ok=True, parents=True)
        Path(self.orc_root).mkdir(exist_ok=True, parents=True)
    
    def test_transform_result_structure(self):
        """Test that transform_result produces expected output structure."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        
        result = handler.transform_result(REAL_ORC_OUTPUT, "owner/repo")
        
        # Check all required top-level keys exist
        required_keys = [
            'failure_probability',
            'verdict',
            'risk_level',
            'shap_explanations',
            'suspicious_files',
            'graph_status',
            'graph_relationships',
            'processing_time_ms',
            'target_sha',
            'timestamp',
            'orc_raw_result'
        ]
        
        for key in required_keys:
            assert key in result, f"Missing key: {key}"
    
    def test_failure_probability_preserved(self):
        """Test that failure probability is correctly preserved."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        result = handler.transform_result(REAL_ORC_OUTPUT, "owner/repo")
        
        assert result['failure_probability'] == pytest.approx(0.531719081238633, rel=1e-5)
        assert result['target_sha'] == "abc123def456abc123def456abc123def456abc1"
    
    def test_verdict_preserved(self):
        """Test that verdict is preserved as-is."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        result = handler.transform_result(REAL_ORC_OUTPUT, "owner/repo")
        
        assert result['verdict'] == "ALERT"
    
    def test_verdict_to_risk_level_mapping(self):
        """Test verdict to risk level mapping."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        
        test_cases = [
            ("FAST-TRACK", "LOW"),
            ("STANDARD GATE", "MEDIUM"),
            ("ALERT", "HIGH"),
            ("CRITICAL", "HIGH"),
            ("PRE-MERGE BLOCK", "HIGH"),
            ("UNKNOWN", "MEDIUM"),  # Default for unknown
        ]
        
        for verdict, expected_level in test_cases:
            output = REAL_ORC_OUTPUT.copy()
            output['verdict'] = verdict
            result = handler.transform_result(output, "owner/repo")
            assert result['risk_level'] == expected_level, f"Failed for {verdict}"
    
    def test_shap_drivers_transformation_from_array_format(self):
        """Test SHAP drivers transformation from [name, value] format."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        result = handler.transform_result(REAL_ORC_OUTPUT, "owner/repo")
        
        shap = result['shap_explanations']
        
        # Should have 6 total (3 positive + 3 negative)
        assert len(shap) == 6
        
        # Check structure
        for item in shap:
            assert 'name' in item
            assert 'contribution' in item
            assert 'direction' in item
            assert isinstance(item['contribution'], float)
            assert item['direction'] in ['positive', 'negative']
        
        # Check sorting by absolute contribution
        contributions = [abs(item['contribution']) for item in shap]
        assert contributions == sorted(contributions, reverse=True)
    
    def test_shap_drivers_positive_values(self):
        """Test that positive drivers are identified correctly."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        result = handler.transform_result(REAL_ORC_OUTPUT, "owner/repo")
        
        positive_drivers = [s for s in result['shap_explanations'] if s['direction'] == 'positive']
        
        assert len(positive_drivers) == 3
        assert positive_drivers[0]['name'] == 'gh_test_cases_per_kloc'
        assert positive_drivers[0]['contribution'] == pytest.approx(0.5486)
    
    def test_shap_drivers_negative_values(self):
        """Test that negative drivers are identified correctly."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        result = handler.transform_result(REAL_ORC_OUTPUT, "owner/repo")
        
        negative_drivers = [s for s in result['shap_explanations'] if s['direction'] == 'negative']
        
        assert len(negative_drivers) == 3
        assert negative_drivers[0]['name'] == 'code_churn_density'
        assert negative_drivers[0]['contribution'] == pytest.approx(-0.4099)
    
    def test_suspicious_files_transformation(self):
        """Test suspicious files transformation and normalization."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        result = handler.transform_result(REAL_ORC_OUTPUT, "owner/repo")
        
        suspicious = result['suspicious_files']
        
        # Should have 2 suspicious files
        assert len(suspicious) == 2
        
        # Check structure
        for file_info in suspicious:
            assert 'path' in file_info
            assert 'score' in file_info
            assert 'type' in file_info
            assert 'reason' in file_info
            assert isinstance(file_info['score'], float)
            assert 0.0 <= file_info['score'] <= 1.0
    
    def test_suspicious_files_direct_modification_rank(self):
        """Test that directly modified files rank first."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        result = handler.transform_result(REAL_ORC_OUTPUT, "owner/repo")
        
        suspicious = result['suspicious_files']
        
        # First file should be the directly modified one (score 1.0)
        assert suspicious[0]['score'] == 1.0
        # Path should contain the filename
        assert 'file_b.py' in suspicious[0]['path']
        assert 'Directly modified' in suspicious[0]['reason']
    
    def test_suspicious_files_connected_rank(self):
        """Test that connected files rank lower."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        result = handler.transform_result(REAL_ORC_OUTPUT, "owner/repo")
        
        suspicious = result['suspicious_files']
        
        # Second file should be connected (score 0.7)
        assert suspicious[1]['score'] == 0.7
        assert 'Connected' in suspicious[1]['reason']
    
    def test_path_normalization_removes_graph_cache(self):
        """Test that .graph_cache paths are normalized properly."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        
        # Test the normalization function directly
        cache_path = "/path/to/repo/.graph_cache/owner__repo/src/utils.py"
        normalized = handler._normalize_file_path(cache_path, "owner/repo")
        
        # Should extract just the src/utils.py part, not the cache prefix
        assert '.graph_cache' not in normalized
        assert 'owner__repo' not in normalized
    
    def test_file_type_inference(self):
        """Test file type inference from extension."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        
        test_cases = [
            ('file.py', 'Python'),
            ('file.js', 'JavaScript'),
            ('file.java', 'Java'),
            ('file.go', 'Go'),
            ('file.rs', 'Rust'),
            ('file.cpp', 'C++'),
            ('file.yaml', 'YAML'),
            ('file.unknown', 'Unknown'),
        ]
        
        for filename, expected_type in test_cases:
            result_type = handler._infer_file_type(filename)
            assert result_type == expected_type, f"Failed for {filename}"
    
    def test_graph_relationships_structure(self):
        """Test graph relationships contain only genuine ORC data, not estimated metrics."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        result = handler.transform_result(REAL_ORC_OUTPUT, "owner/repo")
        
        graph_rel = result['graph_relationships']
        
        # Should NOT contain fabricated/estimated metrics (removed in Phase 2B.1)
        assert 'total_nodes' not in graph_rel, "total_nodes should not be included (fabricated data)"
        assert 'total_edges' not in graph_rel, "total_edges should not be included (fabricated data)"
        assert 'blast_radius' not in graph_rel, "blast_radius should not be included (fabricated data)"
        
        # Should contain genuine ORC data only
        assert 'files_changed' in graph_rel, "files_changed (genuine ORC metric) should be present"
        assert 'suspicious_file_count' in graph_rel, "suspicious_file_count should be present"
        
        # Verify files_changed has correct structure and values
        files = graph_rel['files_changed']
        assert files['added'] == 8
        assert files['modified'] == 11
        assert files['deleted'] == 5
        assert files['renamed'] == 0
        
        # Verify suspicious_file_count is an integer
        assert isinstance(graph_rel['suspicious_file_count'], int)
        assert graph_rel['suspicious_file_count'] == 2  # From REAL_ORC_OUTPUT fixture
    
    def test_missing_fields_handled_safely(self):
        """Test that missing fields are handled gracefully."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        
        # Create output with missing optional fields
        minimal_output = {
            "repository_identity": "owner/repo",
            "target_sha": "abc123",
            "failure_probability": 0.5,
            "verdict": "ALERT",
            # Missing shap_drivers, suspicious_files, etc.
        }
        
        result = handler.transform_result(minimal_output, "owner/repo")
        
        # Should not crash and should have sensible defaults
        assert result['failure_probability'] == 0.5
        assert result['shap_explanations'] == []
        assert result['suspicious_files'] == []
    
    def test_null_suspicious_files_handled(self):
        """Test that null suspicious_files is handled."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        
        output = REAL_ORC_OUTPUT.copy()
        output['suspicious_files'] = None
        
        result = handler.transform_result(output, "owner/repo")
        
        assert result['suspicious_files'] == []
    
    def test_empty_shap_drivers_handled(self):
        """Test that empty SHAP drivers is handled."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        
        output = REAL_ORC_OUTPUT.copy()
        output['shap_drivers'] = {'positive': [], 'negative': []}
        
        result = handler.transform_result(output, "owner/repo")
        
        assert result['shap_explanations'] == []
    
    def test_raw_result_stored_for_debugging(self):
        """Test that raw ORC result is stored for debugging."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        result = handler.transform_result(REAL_ORC_OUTPUT, "owner/repo")
        
        assert 'orc_raw_result' in result
        assert result['orc_raw_result'] == REAL_ORC_OUTPUT
    
    def test_timestamp_preserved(self):
        """Test that timestamp is preserved."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        result = handler.transform_result(REAL_ORC_OUTPUT, "owner/repo")
        
        assert result['timestamp'] == "2026-11-07T12:34:56.789012"
    
    def test_processing_time_preserved(self):
        """Test that processing time is preserved."""
        handler = ORCHandler(self.orc_root, self.repo_path)
        result = handler.transform_result(REAL_ORC_OUTPUT, "owner/repo")
        
        assert result['processing_time_ms'] == 4250.5


class TestORCHandlerErrorSanitization:
    """Test error message sanitization."""
    
    def setup_method(self):
        """Set up test fixtures."""
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.handler = ORCHandler(self.temp_dir, self.temp_dir)
    
    def test_github_token_sanitized(self):
        """Test that GitHub tokens are redacted."""
        error = "Failed to authenticate: ghp_1234567890abcdefghijklmnopqrstuv"
        sanitized = self.handler._sanitize_error(error)
        
        assert 'ghp_' not in sanitized
        assert '[GITHUB_TOKEN]' in sanitized
    
    def test_password_sanitized(self):
        """Test that passwords are redacted."""
        error = "Neo4j error: password=supersecretpassword123"
        sanitized = self.handler._sanitize_error(error)
        
        assert 'supersecretpassword' not in sanitized
        assert '[REDACTED]' in sanitized


class TestORCHandlerConfiguration:
    """Test ORC handler configuration and validation."""
    
    def test_repo_path_required(self):
        """Test that missing REPO_PATH raises clear error."""
        import os
        
        # Clear REPO_PATH from environment
        old_repo_path = os.environ.pop('REPO_PATH', None)
        
        try:
            with pytest.raises(ValueError) as exc_info:
                from src.backend.orc_handler import create_orc_handler
                create_orc_handler()
            
            error_msg = str(exc_info.value)
            assert 'REPO_PATH not configured' in error_msg
            assert 'environment variable' in error_msg
            assert 'Git repository' in error_msg
        finally:
            # Restore environment
            if old_repo_path:
                os.environ['REPO_PATH'] = old_repo_path
    
    def test_repo_path_empty_string_rejected(self):
        """Test that empty REPO_PATH string is rejected."""
        import os
        import tempfile
        
        old_repo_path = os.environ.get('REPO_PATH')
        
        try:
            os.environ['REPO_PATH'] = ''  # Empty string
            
            with pytest.raises(ValueError) as exc_info:
                from src.backend.orc_handler import create_orc_handler
                create_orc_handler()
            
            error_msg = str(exc_info.value)
            assert 'REPO_PATH not configured' in error_msg or 'non-existent' in error_msg
        finally:
            if old_repo_path:
                os.environ['REPO_PATH'] = old_repo_path
            else:
                os.environ.pop('REPO_PATH', None)
    
    def test_repo_path_nonexistent_rejected(self):
        """Test that non-existent directory is rejected."""
        import os
        
        old_repo_path = os.environ.get('REPO_PATH')
        
        try:
            os.environ['REPO_PATH'] = '/nonexistent/path/to/repo'
            
            with pytest.raises(ValueError) as exc_info:
                from src.backend.orc_handler import create_orc_handler
                create_orc_handler()
            
            error_msg = str(exc_info.value)
            assert 'non-existent' in error_msg
        finally:
            if old_repo_path:
                os.environ['REPO_PATH'] = old_repo_path
            else:
                os.environ.pop('REPO_PATH', None)
    
    def test_repo_path_not_git_repo_rejected(self):
        """Test that directory without .git is rejected."""
        import os
        import tempfile
        
        old_repo_path = os.environ.get('REPO_PATH')
        
        try:
            # Create temp directory (not a git repo)
            with tempfile.TemporaryDirectory() as temp_dir:
                os.environ['REPO_PATH'] = temp_dir
                
                with pytest.raises(ValueError) as exc_info:
                    from src.backend.orc_handler import create_orc_handler
                    create_orc_handler()
                
                error_msg = str(exc_info.value)
                assert 'Git repository' in error_msg or '.git' in error_msg
        finally:
            if old_repo_path:
                os.environ['REPO_PATH'] = old_repo_path
            else:
                os.environ.pop('REPO_PATH', None)
    
    def test_repo_path_absolute_resolution(self):
        """Test that valid repo path is resolved to absolute."""
        import os
        import tempfile
        from pathlib import Path
        
        old_repo_path = os.environ.get('REPO_PATH')
        old_cwd = os.getcwd()
        
        try:
            # Create a temporary git-like directory (with .git folder)
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                (temp_path / '.git').mkdir()  # Fake git repo
                
                os.environ['REPO_PATH'] = temp_dir
                
                from src.backend.orc_handler import create_orc_handler
                handler = create_orc_handler()
                
                # Verify repo_path is absolute
                assert handler.repo_path.is_absolute()
                assert str(handler.repo_path) == str(temp_path.resolve())
        finally:
            if old_repo_path:
                os.environ['REPO_PATH'] = old_repo_path
            else:
                os.environ.pop('REPO_PATH', None)
            os.chdir(old_cwd)
    
    def test_graph_relationships_no_estimated_metrics(self):
        """Test that graph relationships don't contain estimated node/edge counts."""
        import tempfile
        
        temp_dir = tempfile.mkdtemp()
        handler = ORCHandler(temp_dir, temp_dir)
        
        graph_files_changed = {
            'added': 8,
            'modified': 11,
            'deleted': 5,
            'renamed': 0
        }
        
        result = handler._build_graph_relationships(graph_files_changed, num_suspicious=2)
        
        # Should NOT contain estimated metrics
        assert 'total_nodes' not in result
        assert 'total_edges' not in result
        assert 'blast_radius' not in result
        
        # Should contain genuine metrics
        assert 'files_changed' in result
        assert 'suspicious_file_count' in result
        assert result['suspicious_file_count'] == 2
        assert result['files_changed']['added'] == 8
        assert result['files_changed']['modified'] == 11
        assert result['files_changed']['deleted'] == 5
        assert result['files_changed']['renamed'] == 0
    
    def test_shap_and_suspicious_files_continue_working(self):
        """Test that existing SHAP and suspicious-file transformations still work."""
        import tempfile
        
        temp_dir = tempfile.mkdtemp()
        handler = ORCHandler(temp_dir, temp_dir)
        
        # Test SHAP transformation
        shap_result = handler._transform_shap_drivers(REAL_ORC_OUTPUT['shap_drivers'])
        
        assert len(shap_result) == 6  # 3 positive + 3 negative
        assert shap_result[0]['direction'] in ['positive', 'negative']
        assert 'name' in shap_result[0]
        assert 'contribution' in shap_result[0]
        
        # Test suspicious files transformation
        suspicious = handler._transform_suspicious_files(
            REAL_ORC_OUTPUT['suspicious_files'],
            'owner/repo'
        )
        
        assert len(suspicious) == 2
        assert all('path' in f for f in suspicious)
        assert all('score' in f for f in suspicious)
        assert all('reason' in f for f in suspicious)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
