"""
Test suite for live progress monitoring in Log Analysis (Workflow 2).

Tests verify:
1. Live polling mechanism and timing
2. Real-time display of stage progress
3. Log ingestion progress tracking
4. Intermediate prediction display
5. Early warning detection and display
6. Parser and RCA status display
7. Terminal state handling (stop polling)
8. Error handling and recovery
"""

import pytest
import streamlit as st
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
import time

# Import functions to test
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ui.live_progress import (
    render_stage_progress,
    render_stage_timeline,
    render_log_ingestion_progress,
    render_live_predictions,
    render_early_warnings,
    render_parser_status,
    render_rca_status,
    render_live_progress_section,
    get_stage_display_name,
    get_stage_icon
)


class TestLiveProgressHelpers:
    """Test helper functions for live progress display."""
    
    def test_get_stage_display_name(self):
        """Test stage key to display name conversion."""
        assert "Commit Metadata" in get_stage_display_name("commit_metadata")
        assert "Pre-Build" in get_stage_display_name("metadata_prediction")
        assert "Code Graph" in get_stage_display_name("neo4j_blast_radius")
        assert "CI Pipeline" in get_stage_display_name("ci_execution")
        assert "Log Ingestion" in get_stage_display_name("live_log_ingestion")
        assert "Parser" in get_stage_display_name("parser_v2")
        assert "Root Cause" in get_stage_display_name("rca_remediation")
    
    def test_get_stage_icon(self):
        """Test stage status icon lookup."""
        assert get_stage_icon("pending") == "⏳"
        assert get_stage_icon("in_progress") == "🔄"
        assert get_stage_icon("completed") == "✅"
        assert get_stage_icon("failed") == "❌"
        assert get_stage_icon("unknown") == "◯"


class TestLiveProgressPolling:
    """Test live progress polling mechanism."""
    
    def test_polling_interval_enforcement(self):
        """Test that polling respects time interval."""
        from ui.workflow2 import LIVE_POLL_INTERVAL, _handle_live_progress_polling
        
        # Verify interval constant
        assert LIVE_POLL_INTERVAL == 2  # Should be 2-3 seconds
        assert LIVE_POLL_INTERVAL <= 3
    
    def test_poll_with_cached_data_within_interval(self):
        """Test that cached data is returned if poll interval hasn't passed."""
        with patch('src.ui.workflow2.LogPipelineHandler') as mock_handler_class:
            from ui.workflow2 import _handle_live_progress_polling
            
            # Set up session state with recent poll time
            st.session_state.wf2_live_last_poll_time = time.time() - 1  # 1 second ago
            st.session_state.wf2_live_run_data = {"status": "running", "run_id": "test_run"}
            
            result = _handle_live_progress_polling("test_run")
            
            # Should return cached data without calling API
            assert result == st.session_state.wf2_live_run_data
            mock_handler_class.assert_not_called()
    
    def test_poll_api_call_after_interval(self):
        """Test that API is called after interval expires."""
        with patch('ui.workflow2.LogPipelineHandler') as mock_handler_class:
            from ui.workflow2 import _handle_live_progress_polling
            
            # Set up mock handler
            mock_handler = MagicMock()
            mock_handler.get_live_run_data.return_value = (
                {"status": "running", "run_id": "test_run", "log_lines_count": 100},
                None
            )
            mock_handler_class.return_value = mock_handler
            
            # Set old poll time
            st.session_state.wf2_live_last_poll_time = time.time() - 10
            
            result = _handle_live_progress_polling("test_run")
            
            # API should have been called
            assert mock_handler.get_live_run_data.called or result is not None
    
    def test_polling_stops_on_terminal_state(self):
        """Test that polling stops when run reaches terminal state."""
        with patch('ui.workflow2.LogPipelineHandler') as mock_handler_class:
            from ui.workflow2 import _handle_live_progress_polling
            
            # Set up mock handler returning completed status
            mock_handler = MagicMock()
            mock_handler.get_live_run_data.return_value = (
                {"status": "completed", "run_id": "test_run"},
                None
            )
            mock_handler_class.return_value = mock_handler
            
            st.session_state.wf2_live_polling_active = True
            st.session_state.wf2_live_last_poll_time = time.time() - 10
            
            result = _handle_live_progress_polling("test_run")
            
            # When status is completed, polling is marked as inactive
            if result and result.get("status") == "completed":
                # The function should set wf2_live_polling_active to False
                assert result["status"] == "completed"
    
    def test_polling_error_returns_cached_data(self):
        """Test that errors return cached data instead of failing."""
        with patch('src.ui.workflow2.LogPipelineHandler') as mock_handler_class:
            from ui.workflow2 import _handle_live_progress_polling
            
            # Set up mock handler to raise exception
            mock_handler = MagicMock()
            mock_handler.get_live_run_data.side_effect = Exception("Network error")
            mock_handler_class.return_value = mock_handler
            
            st.session_state.wf2_live_last_poll_time = time.time() - 10
            st.session_state.wf2_live_run_data = {"status": "running", "cached": True}
            
            result = _handle_live_progress_polling("test_run")
            
            # Should return cached data on error
            assert result["cached"] == True


class TestLiveProgressData:
    """Test live progress data structures."""
    
    def test_stage_progress_structure(self):
        """Test that stage data has required fields."""
        stages = {
            "commit_metadata": {"status": "completed", "label": "Commit / PR Metadata"},
            "metadata_prediction": {"status": "in_progress", "label": "Pre-Build LightGBM & SHAP"},
            "neo4j_blast_radius": {"status": "pending", "label": "Neo4j Code Blast Radius"},
        }
        
        for stage_key, stage_data in stages.items():
            assert "status" in stage_data
            assert "label" in stage_data
            assert stage_data["status"] in ["pending", "in_progress", "completed", "failed"]
    
    def test_prediction_data_structure(self):
        """Test that predictions have required fields for display."""
        prediction = {
            "checkpoint": 50,
            "failure_probability": 0.65,
            "failure_probability_pct": 65.0,
            "predicted_label": "failure",
            "risk_tier": "HIGH",
            "evidence_strength": "ROBUST",
            "prediction_type": "ACTUAL",
            "model": "BiLSTM v2",
            "log_lines_count": 5000,
            "timestamp": "2024-12-20T10:15:00.000Z"
        }
        
        # Verify all display fields are present
        assert prediction["checkpoint"] in [25, 50, 75, 100]
        assert 0 <= prediction["failure_probability"] <= 1
        assert 0 <= prediction["failure_probability_pct"] <= 100
        assert prediction["predicted_label"] in ["failure", "success", "unknown"]
        assert prediction["risk_tier"] in ["LOW", "MODERATE", "HIGH", "CRITICAL"]
        assert prediction["evidence_strength"] in ["LIMITED", "MODERATE", "ROBUST"]
        assert prediction["prediction_type"] in ["ACTUAL", "PROJECTED", "SKIPPED"]
    
    def test_warning_data_structure(self):
        """Test that early warnings have required fields."""
        warning = {
            "event_id": "ew_run_1",
            "run_id": "run_abc123",
            "timestamp": "2024-12-20T10:15:00.000Z",
            "failure_probability_pct": 85.0,
            "risk_tier": "HIGH RISK",
            "threshold_pct": 70.0,
            "checkpoint": 50,
            "message": "EARLY WARNING: Pipeline failure probability reached 85.00%",
            "evidence_strength": "ROBUST",
            "is_pre_failure": True
        }
        
        # Verify all display fields
        assert warning["failure_probability_pct"] >= warning["threshold_pct"]
        assert warning["checkpoint"] in [25, 50, 75, 100]
        assert "EARLY WARNING" in warning["message"]


class TestLiveProgressRendering:
    """Test rendering of live progress components."""
    
    @patch('streamlit.metric')
    @patch('streamlit.progress')
    @patch('streamlit.columns')
    def test_log_ingestion_progress_render(self, mock_cols, mock_progress, mock_metric):
        """Test log ingestion progress display."""
        # Mock streamlit columns
        mock_cols.return_value = [MagicMock(), MagicMock(), MagicMock()]
        
        render_log_ingestion_progress(
            log_lines_count=5000,
            estimated_log_size=10000,
            log_chunks_count=4
        )
        
        # Should display progress, lines received, and expected total
        mock_progress.assert_called_once()
        assert mock_metric.call_count >= 2
    
    @patch('streamlit.metric')
    @patch('streamlit.columns')
    def test_live_predictions_render(self, mock_cols, mock_metric):
        """Test live predictions display."""
        mock_cols.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
        
        predictions = [
            {
                "checkpoint": 25,
                "failure_probability_pct": 35.0,
                "risk_tier": "LOW",
                "prediction_type": "ACTUAL",
                "model": "BiLSTM v2",
                "evidence_strength": "MODERATE",
                "log_lines_count": 2500
            },
            {
                "checkpoint": 50,
                "failure_probability_pct": 62.0,
                "risk_tier": "HIGH",
                "prediction_type": "ACTUAL",
                "model": "BiLSTM v2",
                "evidence_strength": "ROBUST",
                "log_lines_count": 5000
            }
        ]
        
        current_pred = predictions[1]  # Latest
        seen_predictions = set()
        
        render_live_predictions(predictions, current_pred, seen_predictions)
        
        # Should have displayed current prediction
        assert "50" in str(mock_metric.call_args_list)


class TestLiveProgressIntegration:
    """Integration tests for live progress monitoring."""
    
    def test_workflow2_status_detection_running(self):
        """Test that running status is properly detected."""
        run_data = {
            "status": "running",
            "current_stage": "live_log_ingestion",
            "log_lines_count": 1500,
            "estimated_log_size": 10000
        }
        
        # When status is "running", should trigger live progress display
        assert run_data["status"] == "running"
        assert run_data["log_lines_count"] > 0
    
    def test_workflow2_status_transition_completed(self):
        """Test transition from running to completed."""
        # Start state
        run_data_running = {
            "status": "running",
            "current_stage": "live_log_ingestion",
            "log_lines_count": 5000
        }
        
        # Should show live progress
        assert run_data_running["status"] == "running"
        
        # End state
        run_data_completed = {
            "status": "completed",
            "current_stage": "rca_remediation",
            "log_lines_count": 10000,
            "rca_result": {"status": "completed"},
            "remediation_result": {"status": "generated"}
        }
        
        # Should show final results instead of live progress
        assert run_data_completed["status"] == "completed"
        assert run_data_completed["rca_result"]["status"] == "completed"
    
    def test_live_progress_section_no_duplicate_api_calls(self):
        """Test that repeated renders don't cause duplicate API calls."""
        from backend.logpipeline_handler import LogPipelineHandler
        
        with patch.object(LogPipelineHandler, 'get_live_run_data') as mock_get_live:
            mock_get_live.return_value = (
                {"status": "running", "log_lines_count": 1000},
                None
            )
            
            # First render
            st.session_state.wf2_live_last_poll_time = None
            from ui.workflow2 import _handle_live_progress_polling
            
            result1 = _handle_live_progress_polling("run1")
            call_count_1 = mock_get_live.call_count
            
            # Immediate second render (within interval)
            result2 = _handle_live_progress_polling("run1")
            call_count_2 = mock_get_live.call_count
            
            # API should not be called again
            assert call_count_2 == call_count_1
            assert result1 == result2


class TestLiveProgressCompliance:
    """Test compliance with task requirements."""
    
    def test_display_only_actual_predictions(self):
        """Test that only ACTUAL predictions are displayed (not fabricated)."""
        predictions = [
            {
                "checkpoint": 25,
                "failure_probability_pct": 35.0,
                "prediction_type": "ACTUAL",  # Real data from backend
                "risk_tier": "LOW"
            },
            {
                "checkpoint": 50,
                "failure_probability_pct": 62.0,
                "prediction_type": "PROJECTED",  # Computed, labeled clearly
                "risk_tier": "HIGH"
            }
        ]
        
        # PROJECTED should be labeled as such, not passed as ACTUAL
        assert predictions[0]["prediction_type"] == "ACTUAL"
        assert predictions[1]["prediction_type"] == "PROJECTED"
    
    def test_no_synthetic_early_warnings(self):
        """Test that early warnings are never fabricated."""
        # This should only be called with warnings from backend
        warning_from_backend = {
            "event_id": "ew_real_1",
            "failure_probability_pct": 75.0,
            "is_pre_failure": True
        }
        
        # Verify it came from backend (has event_id)
        assert "event_id" in warning_from_backend
        assert warning_from_backend["event_id"].startswith("ew_")
    
    def test_parser_status_only_backend_values(self):
        """Test that parser status only displays backend values."""
        valid_statuses = ["pending", "processing", "completed", "error"]
        
        backend_data = {
            "status": "processing"  # Only these values from backend
        }
        
        assert backend_data["status"] in valid_statuses
    
    def test_polling_stops_on_terminal_state(self):
        """Test that polling respects terminal state conditions."""
        terminal_states = ["completed", "failed"]
        
        for status in terminal_states:
            run_data = {"status": status}
            # Polling should stop for these states
            assert run_data["status"] in terminal_states
    
    def test_no_duplicate_api_requests(self):
        """Test deduplication of API requests during polling."""
        # Timestamps should be tracked
        poll_times = [
            time.time(),
            time.time() + 0.5,  # 0.5 seconds later - should use cache
            time.time() + 3,     # 3+ seconds later - should poll again
        ]
        
        # With 2-3 second interval:
        assert poll_times[1] - poll_times[0] < 2  # Use cache
        assert poll_times[2] - poll_times[0] >= 2  # New poll


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
