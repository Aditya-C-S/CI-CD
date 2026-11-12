"""
Phase 4: Historical Log Size Estimation Integration with Chunk Ingestion

Comprehensive test suite for integrating log_size_estimator with ingest_log_chunk.
Tests cover:
1. Run registration with threshold initialization
2. Threshold detection and prediction triggering
3. Multi-chunk progression with threshold crossing
4. Deduplication and chunk reliability
5. Workflow finalization and stats recording
6. Multi-job isolation
7. Edge cases (empty logs, skipped stages, no history)
"""

import json
import logging
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
from unittest.mock import Mock, patch, MagicMock

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestPhase4ThresholdInitialization(unittest.TestCase):
    """Test Phase 4: Threshold initialization on first chunk"""

    def setUp(self):
        """Set up test fixtures"""
        from src.demo.demo_manager import UnifiedDemoManager
        self.mgr = UnifiedDemoManager.get_instance()
        self.test_run_id = f"test_run_phase4_{datetime.now().timestamp()}"
        self.repo_id = "test-org/test-repo"

    def test_run_registration_with_estimate(self):
        """Test that first chunk triggers threshold initialization"""
        # Create run
        run = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
            branch="main",
            is_pr=True,
        )
        self.assertIsNotNone(run)
        self.assertIsNone(run.estimated_log_size)
        self.assertEqual(len(run.thresholds), 0)
        self.assertEqual(len(run.triggered_thresholds), 0)
        test_run_id = run.run_id

        # Ingest first chunk
        chunk_text = "\n".join([f"log line {i}" for i in range(100)])
        result = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk_text,
            step_name="test_step",
            stage="execution",
            ci_run_id="gh_run_123",
            commit_sha="abc123def",
            timestamp="2024-01-15T10:00:00Z",
            event_id="event_1",
        )

        # Verify estimate was initialized
        self.assertIsNotNone(result["estimated_log_size"])
        self.assertGreater(result["estimated_log_size"], 0)
        self.assertIn(25, result["thresholds"])
        self.assertIn(50, result["thresholds"])
        self.assertIn(75, result["thresholds"])
        self.assertIn(100, result["thresholds"])
        logger.info(f"Thresholds initialized: {result['thresholds']}")

    def test_thresholds_structure(self):
        """Test that thresholds are correctly calculated"""
        run = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
        )
        test_run_id = run.run_id

        chunk_text = "\n".join([f"line {i}" for i in range(100)])
        result = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk_text,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_1",
        )

        thresholds = result["thresholds"]
        # Verify mathematical relationship
        self.assertLess(thresholds[25], thresholds[50])
        self.assertLess(thresholds[50], thresholds[75])
        self.assertLess(thresholds[75], thresholds[100])

        # Verify approximate relationship
        est_total = result["estimated_log_size"]
        self.assertAlmostEqual(thresholds[25], est_total * 0.25, delta=est_total * 0.1)
        self.assertAlmostEqual(thresholds[50], est_total * 0.50, delta=est_total * 0.1)
        self.assertAlmostEqual(thresholds[75], est_total * 0.75, delta=est_total * 0.1)
        self.assertAlmostEqual(thresholds[100], est_total, delta=est_total * 0.1)


class TestPhase4ThresholdDetection(unittest.TestCase):
    """Test Phase 4: Threshold crossing detection and prediction triggering"""

    def setUp(self):
        """Set up test fixtures"""
        from src.demo.demo_manager import UnifiedDemoManager
        self.mgr = UnifiedDemoManager.get_instance()
        self.test_run_id = f"test_run_detect_{datetime.now().timestamp()}"
        self.repo_id = "test-org/test-repo"

    def test_single_threshold_crossing(self):
        """Test that crossing a threshold triggers prediction"""
        run = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
        )
        test_run_id = run.run_id

        # First chunk: small (triggers estimator)
        chunk1 = "\n".join([f"line {i}" for i in range(50)])
        result1 = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk1,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_1",
        )
        
        est_total = result1["estimated_log_size"]
        threshold_25 = result1["thresholds"][25]
        logger.info(f"Est: {est_total}, 25% threshold: {threshold_25}")

        # Second chunk: cross 25% threshold
        chunk2 = "\n".join([f"line {i}" for i in range(50, threshold_25 + 50)])
        result2 = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk2,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_2",
        )

        # Verify threshold was triggered
        self.assertIn(25, result2["triggered_thresholds"])
        logger.info(f"Triggered thresholds: {result2['triggered_thresholds']}")

    def test_multiple_thresholds_in_one_chunk(self):
        """Test that one chunk can cross multiple thresholds"""
        run = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
        )
        test_run_id = run.run_id

        # First chunk to initialize estimate
        chunk1 = "\n".join([f"line {i}" for i in range(50)])
        result1 = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk1,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_1",
        )
        
        threshold_75 = result1["thresholds"][75]
        threshold_100 = result1["thresholds"][100]
        logger.info(f"75% threshold: {threshold_75}, 100% threshold: {threshold_100}")

        # Second chunk: very large, crosses multiple thresholds
        chunk2 = "\n".join([f"line {i}" for i in range(50, threshold_100 + 200)])
        result2 = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk2,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_2",
        )

        # Should have triggered at least 75% and 100%
        triggered = result2["triggered_thresholds"]
        self.assertGreaterEqual(len(triggered), 2)
        logger.info(f"Multiple thresholds triggered: {triggered}")

    def test_threshold_not_retriggered(self):
        """Test that a threshold only triggers once"""
        run = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
        )
        test_run_id = run.run_id

        # Initialize estimate
        chunk1 = "\n".join([f"line {i}" for i in range(50)])
        result1 = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk1,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_1",
        )
        
        threshold_25 = result1["thresholds"][25]

        # Cross 25% threshold
        chunk2 = "\n".join([f"line {i}" for i in range(50, threshold_25 + 100)])
        result2 = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk2,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_2",
        )
        self.assertIn(25, result2["triggered_thresholds"])
        predictions_after_cross = len(result2["runtime_predictions"])

        # Add more content but don't cross any new threshold
        chunk3 = "\n".join([f"line {i}" for i in range(200, 250)])
        result3 = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk3,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_3",
        )

        # 25% threshold should NOT be in triggered again
        self.assertEqual(result3["triggered_thresholds"], result2["triggered_thresholds"])
        logger.info(f"Threshold {25} was not re-triggered (confirmed)")


class TestPhase4Finalization(unittest.TestCase):
    """Test Phase 4: Workflow finalization and stats recording"""

    def setUp(self):
        """Set up test fixtures"""
        from src.demo.demo_manager import UnifiedDemoManager
        self.mgr = UnifiedDemoManager.get_instance()
        self.test_run_id = f"test_run_final_{datetime.now().timestamp()}"
        self.repo_id = "test-org/test-repo"

    def test_final_prediction_recorded(self):
        """Test that final prediction is recorded with FINAL_ACTUAL type"""
        run = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
        )
        test_run_id = run.run_id

        # Ingest chunk with is_final=True
        chunk_text = "\n".join([f"line {i}" for i in range(100)])
        result = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk_text,
            step_name="test_step",
            ci_run_id="gh_run_123",
            is_final=True,
            workflow_outcome="success",
            event_id="event_1",
        )

        # Verify final prediction exists
        predictions = result["runtime_predictions"]
        final_preds = [p for p in predictions if p.get("prediction_type") == "FINAL_ACTUAL"]
        self.assertGreater(len(final_preds), 0)
        
        final_pred = final_preds[0]
        self.assertEqual(final_pred["depth_percentage"], 100)
        self.assertIsNotNone(final_pred.get("estimated_total_lines"))
        logger.info(f"Final prediction recorded: {final_pred['risk_tier']} with prob {final_pred['failure_probability']}")

    def test_workflow_finalization_status(self):
        """Test that is_final marks run as completed"""
        run = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
        )
        test_run_id = run.run_id

        # Ingest with is_final=True
        chunk_text = "\n".join([f"line {i}" for i in range(50)])
        result = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk_text,
            step_name="test_step",
            ci_run_id="gh_run_123",
            is_final=True,
            workflow_outcome="failure",
            exit_code=1,
            event_id="event_1",
        )

        # Verify run status
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["actual_outcome"], "failure")
        self.assertIsNotNone(result["ci_execution"]["completed_at"])
        logger.info(f"Run finalized: status={result['status']}, outcome={result['actual_outcome']}")

    @patch('src.ingestion.log_size_estimator.LogSizeEstimator.record_completed_run')
    def test_record_completed_run_called(self, mock_record):
        """Test that record_completed_run is called on finalization"""
        mock_record.return_value = True

        run = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
        )
        test_run_id = run.run_id

        # Ingest with is_final=True
        chunk_text = "\n".join([f"line {i}" for i in range(100)])
        result = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk_text,
            step_name="test_step",
            ci_run_id="gh_run_123",
            is_final=True,
            workflow_outcome="success",
            event_id="event_1",
        )

        # Verify record_completed_run was called
        mock_record.assert_called_once()
        call_kwargs = mock_record.call_args[1]
        self.assertEqual(call_kwargs["repository_id"], self.repo_id)
        self.assertEqual(call_kwargs["run_id"], test_run_id)
        self.assertEqual(call_kwargs["actual_line_count"], 100)
        logger.info(f"record_completed_run called with: {call_kwargs}")


class TestPhase4ChunkReliability(unittest.TestCase):
    """Test Phase 4: Chunk deduplication and reliability"""

    def setUp(self):
        """Set up test fixtures"""
        from src.demo.demo_manager import UnifiedDemoManager
        self.mgr = UnifiedDemoManager.get_instance()
        self.test_run_id = f"test_run_reliability_{datetime.now().timestamp()}"
        self.repo_id = "test-org/test-repo"

    def test_duplicate_chunk_ignored(self):
        """Test that duplicate event_id chunks are ignored"""
        run = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
        )
        test_run_id = run.run_id

        chunk_text = "\n".join([f"line {i}" for i in range(50)])

        # First ingest
        result1 = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk_text,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_1",
        )
        predictions_1 = len(result1["runtime_predictions"])
        accumulated_1 = result1["accumulated_log"]

        # Re-ingest with same event_id (duplicate)
        result2 = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk_text,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_1",  # Same event_id
        )
        predictions_2 = len(result2["runtime_predictions"])
        accumulated_2 = result2["accumulated_log"]

        # Should be unchanged (duplicate ignored)
        self.assertEqual(predictions_1, predictions_2)
        self.assertEqual(accumulated_1, accumulated_2)
        logger.info("Duplicate chunk correctly ignored")

    def test_sequence_validation(self):
        """Test that out-of-order chunks are handled properly"""
        run = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
        )
        test_run_id = run.run_id

        # Ingest chunks out of order
        chunk1 = "line 1\nline 2\nline 3"
        chunk2 = "line 4\nline 5\nline 6"

        result1 = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk1,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_2",
        )

        result2 = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk2,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_1",  # Earlier event_id but ingested later
        )

        # Should still accumulate properly (dedup by event_id)
        self.assertIn("line 1", result2["accumulated_log"])
        self.assertIn("line 4", result2["accumulated_log"])
        logger.info("Out-of-order chunks handled correctly")

    def test_job_separation(self):
        """Test that separate jobs maintain separate log accumulation"""
        # Create two runs (simulating different jobs)
        run1 = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
        )
        run2 = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
        )
        run_id_1 = run1.run_id
        run_id_2 = run2.run_id

        chunk1 = "job1_line1\njob1_line2"
        chunk2 = "job2_line1\njob2_line2"

        result1 = self.mgr.ingest_log_chunk(
            run_id=run_id_1,
            log_chunk=chunk1,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_1",
        )

        result2 = self.mgr.ingest_log_chunk(
            run_id=run_id_2,
            log_chunk=chunk2,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_1",
        )

        # Verify logs are separate
        self.assertIn("job1_line1", result1["accumulated_log"])
        self.assertNotIn("job2_line1", result1["accumulated_log"])
        
        self.assertIn("job2_line1", result2["accumulated_log"])
        self.assertNotIn("job1_line1", result2["accumulated_log"])
        logger.info("Job logs correctly separated")


class TestPhase4EdgeCases(unittest.TestCase):
    """Test Phase 4: Edge cases and error handling"""

    def setUp(self):
        """Set up test fixtures"""
        from src.demo.demo_manager import UnifiedDemoManager
        self.mgr = UnifiedDemoManager.get_instance()
        self.test_run_id = f"test_run_edge_{datetime.now().timestamp()}"
        self.repo_id = "test-org/test-repo"

    def test_empty_chunk(self):
        """Test handling of empty log chunks"""
        run = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
        )
        test_run_id = run.run_id

        result = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk="",  # Empty
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_1",
        )

        # Should handle gracefully
        self.assertIsNotNone(result)
        logger.info("Empty chunk handled gracefully")

    def test_skipped_stage(self):
        """Test that skipped stages don't generate full predictions"""
        run = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
        )
        test_run_id = run.run_id

        chunk_text = "\n".join([f"line {i}" for i in range(50)])
        result = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk_text,
            step_name="test_step",
            ci_run_id="gh_run_123",
            step_outcome="skipped",
            event_id="event_1",
        )

        # Should still initialize estimate but prediction should be skipped type
        self.assertIsNotNone(result["estimated_log_size"])
        predictions = result["runtime_predictions"]
        # Should have skipped prediction
        skipped = [p for p in predictions if p.get("is_skipped")]
        self.assertGreater(len(skipped), 0)
        logger.info("Skipped stage handled correctly")

    def test_no_historical_data_fallback(self):
        """Test fallback to default estimate when no history exists"""
        # This test verifies graceful degradation
        run = self.mgr.create_run(
            repo_id=f"nonexistent-repo-{datetime.now().timestamp()}",
            commit_sha="abc123def",
        )
        test_run_id = run.run_id

        chunk_text = "\n".join([f"line {i}" for i in range(50)])
        result = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk_text,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_1",
        )

        # Should have some estimate (fallback default)
        self.assertIsNotNone(result["estimated_log_size"])
        self.assertGreater(result["estimated_log_size"], 0)
        self.assertEqual(len(result["thresholds"]), 4)
        logger.info(f"Fallback estimate applied: {result['estimated_log_size']}")

    def test_very_large_log(self):
        """Test handling of very large log chunks"""
        run = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
        )
        test_run_id = run.run_id

        # Very large chunk (10k lines)
        chunk_text = "\n".join([f"line {i}" for i in range(10000)])
        result = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk_text,
            step_name="test_step",
            ci_run_id="gh_run_123",
            is_final=True,
            event_id="event_1",
        )

        # Should handle without error
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["accumulated_log"].splitlines()), 10000)
        # Should have final prediction
        final_preds = [p for p in result["runtime_predictions"] if p.get("prediction_type") == "FINAL_ACTUAL"]
        self.assertGreater(len(final_preds), 0)
        logger.info(f"Large log handled: {len(result['accumulated_log'].splitlines())} lines")


class TestPhase4Metadata(unittest.TestCase):
    """Test Phase 4: Prediction metadata enrichment"""

    def setUp(self):
        """Set up test fixtures"""
        from src.demo.demo_manager import UnifiedDemoManager
        self.mgr = UnifiedDemoManager.get_instance()
        self.test_run_id = f"test_run_metadata_{datetime.now().timestamp()}"
        self.repo_id = "test-org/test-repo"

    def test_prediction_includes_phase4_fields(self):
        """Test that predictions include Phase 4 metadata"""
        run = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
        )
        test_run_id = run.run_id

        chunk_text = "\n".join([f"line {i}" for i in range(100)])
        result = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk_text,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_1",
        )

        # Check predictions have Phase 4 fields
        predictions = result["runtime_predictions"]
        for pred in predictions:
            if pred.get("model_name"):  # Only for actual ML predictions
                self.assertIn("estimated_total_lines", pred)
                self.assertIn("threshold_percentage", pred)
                self.assertIn("prediction_timestamp", pred)
                self.assertIn("low_evidence_warning", pred)
                logger.info(f"Prediction has Phase 4 fields: est={pred['estimated_total_lines']}, threshold={pred['threshold_percentage']}")

    def test_final_prediction_metadata(self):
        """Test that final prediction has correct metadata"""
        run = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
        )
        test_run_id = run.run_id

        chunk_text = "\n".join([f"line {i}" for i in range(100)])
        result = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk_text,
            step_name="test_step",
            ci_run_id="gh_run_123",
            is_final=True,
            event_id="event_1",
        )

        # Find final prediction
        final_preds = [p for p in result["runtime_predictions"] if p.get("prediction_type") == "FINAL_ACTUAL"]
        self.assertGreater(len(final_preds), 0)
        
        final = final_preds[0]
        self.assertEqual(final["threshold_percentage"], 100)
        self.assertEqual(final["depth_percentage"], 100)
        self.assertIsNotNone(final["estimated_total_lines"])
        logger.info(f"Final prediction metadata verified: {final}")


class TestPhase4ModelIntegration(unittest.TestCase):
    """Test Phase 4: Integration with existing ML models"""

    def setUp(self):
        """Set up test fixtures"""
        from src.demo.demo_manager import UnifiedDemoManager
        self.mgr = UnifiedDemoManager.get_instance()
        self.test_run_id = f"test_run_model_{datetime.now().timestamp()}"
        self.repo_id = "test-org/test-repo"

    def test_predictions_use_correct_model(self):
        """Test that predictions use the configured model"""
        run = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
            runtime_model="logistic_regression",
        )
        test_run_id = run.run_id

        chunk_text = "\n".join([f"line {i}" for i in range(100)])
        result = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk_text,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_1",
        )

        predictions = result["runtime_predictions"]
        for pred in predictions:
            if pred.get("model_name"):
                self.assertEqual(pred["model_name"], "logistic_regression")
        logger.info("Predictions use correct model")

    def test_prediction_probability_range(self):
        """Test that predicted probabilities are in valid range [0, 1]"""
        run = self.mgr.create_run(
            repo_id=self.repo_id,
            commit_sha="abc123def",
        )
        test_run_id = run.run_id

        chunk_text = "\n".join([f"line {i}" for i in range(100)])
        result = self.mgr.ingest_log_chunk(
            run_id=test_run_id,
            log_chunk=chunk_text,
            step_name="test_step",
            ci_run_id="gh_run_123",
            event_id="event_1",
        )

        predictions = result["runtime_predictions"]
        for pred in predictions:
            if pred.get("failure_probability") is not None:
                prob = pred["failure_probability"]
                self.assertGreaterEqual(prob, 0.0)
                self.assertLessEqual(prob, 1.0)
        logger.info("All probabilities in valid range")


if __name__ == "__main__":
    unittest.main()
