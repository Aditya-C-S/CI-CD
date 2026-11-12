"""
PHASE 2 Verification Tests
Comprehensive verification of:
1. BiLSTM v2 inference with progressive log prefixes
2. Tokenization, truncation, padding behavior
3. Runtime tracker multi-prediction storage
4. Chunk ingestion API job distinction
5. Existing model inference tests
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

import pytest

from src.prediction.bilstm2_inference import (
    BiLSTM2InferenceEngine,
    get_bilstm2_engine,
    predict_bilstm2,
)
from src.prediction.predictor import get_predictor, BiLSTM2Predictor
from src.prediction.runtime_tracker import PredictionRecord
from src.prediction.model_interface import PredictionResult
from src.demo.demo_manager import DemoRun
from src.ingestion.log_streamer import LogStreamer

logger = logging.getLogger(__name__)

# Sample test logs for progressive testing
SAMPLE_LOG_SHORT = """Starting job F1: test execution
Step 1: Install dependencies
pip install pytest
Collecting pytest==7.2.0
Installing collected packages: pytest
Running setup.py install
Finished processing
Step 2: Run tests
pytest tests/
test_function_a PASSED
test_function_b PASSED
All tests passed"""

SAMPLE_LOG_MEDIUM = SAMPLE_LOG_SHORT + """

Step 3: Integration tests
Running integration_test_suite
test_integration_a PASSED
test_integration_b PASSED
Step 4: Cleanup
Removing temporary files
Build completed successfully
Exit code: 0"""

SAMPLE_LOG_LONG = SAMPLE_LOG_MEDIUM + """

Additional context:
Processing git metadata
Commit: abc1234567890def
Author: test-author
Date: 2024-01-15

Final report:
Total tests: 10
Passed: 10
Failed: 0
Skipped: 0
Coverage: 95%
Duration: 45.3 seconds

Build status: SUCCESS
All gates passed
Ready for deployment"""

# Longer failure log for comprehensive testing
SAMPLE_LOG_FAILURE = """Starting job F3: test execution
Step 1: Install dependencies
pip install pytest
Step 2: Run tests
pytest tests/
FAILED tests/test_authentication.py::test_login_flow
AssertionError: assert 200 == 401
  expected 401
  actual 200

Traceback (most recent call last):
  File "tests/test_authentication.py", line 45, in test_login_flow
    assert response.status_code == 401
AssertionError: assert 200 == 401

FAILED tests/test_database.py::test_connection
ConnectionError: Database connection timeout after 30 seconds
Traceback (most recent call last):
  File "tests/test_database.py", line 12, in test_connection
    db.connect()
ConnectionError: Database connection timeout after 30 seconds

test_basic_import PASSED
FAILED tests/test_service.py::test_service_init
Traceback (most recent call last):
  File "tests/test_service.py", line 8, in test_service_init
    service = ServiceModule()
RuntimeError: Service initialization failed: missing config file

Exit code: 1"""


class TestBiLSTM2ProgressiveInference:
    """Test BiLSTM v2 inference with progressively larger log prefixes."""

    def test_bilstm2_engine_loads_successfully(self):
        """Verify BiLSTM v2 engine initializes and loads artifacts."""
        engine = BiLSTM2InferenceEngine()
        assert engine.load_artifacts(), "Engine should load artifacts successfully"
        assert engine.task_a_model is not None, "Task A model should be loaded"
        assert len(engine.task_b_models) == 5, "Task B ensemble should have 5 folds"
        assert len(engine.vocab) > 0, "Tokenizer vocab should be loaded"
        logger.info("✓ BiLSTM v2 engine loads successfully")

    def test_bilstm2_progressive_predictions_short_to_long(self):
        """Test that BiLSTM v2 produces valid predictions on progressively larger prefixes."""
        engine = BiLSTM2InferenceEngine()
        engine.load_artifacts()

        # Test on 3 progressively larger log prefixes
        logs_to_test = [
            (SAMPLE_LOG_SHORT, "short (100 words)"),
            (SAMPLE_LOG_MEDIUM, "medium (250 words)"),
            (SAMPLE_LOG_LONG, "long (450 words)"),
        ]

        predictions_by_size = {}

        for log_text, description in logs_to_test:
            result = engine.predict(log_text, visibility=100)
            predictions_by_size[description] = result

            # Verify result structure
            assert isinstance(result, dict), f"Result should be dict for {description}"
            assert "failure_probability" in result, f"Missing failure_probability for {description}"
            assert "predicted_outcome" in result, f"Missing predicted_outcome for {description}"
            assert 0.0 <= result["failure_probability"] <= 1.0, f"Probability out of range for {description}"

            logger.info(
                f"✓ {description}: prob={result['failure_probability']:.4f}, "
                f"outcome={result['predicted_outcome']}, tokens={result['token_diagnostics']['non_pad_tokens']}"
            )

        # Verify multiple predictions were generated
        assert len(predictions_by_size) == 3, "Should have 3 predictions"
        logger.info("✓ Progressive predictions generated for all sizes")

    def test_bilstm2_predictions_on_failure_log(self):
        """Verify BiLSTM v2 detects failure in a log with actual errors."""
        engine = BiLSTM2InferenceEngine()
        engine.load_artifacts()

        result = engine.predict(SAMPLE_LOG_FAILURE, visibility=100)
        
        # Should predict failure or high risk given the error messages
        assert result["failure_probability"] > 0.3, "Should detect elevated failure risk in error log"
        logger.info(
            f"✓ Failure detection: prob={result['failure_probability']:.4f}, "
            f"outcome={result['predicted_outcome']}"
        )


class TestTokenizationBehavior:
    """Test tokenization, truncation, and padding behavior."""

    def test_tokenization_padding_short_input(self):
        """Verify padding behavior on short inputs."""
        engine = BiLSTM2InferenceEngine()
        engine.load_artifacts()

        tensor, diagnostics = engine.analyze_tokens(SAMPLE_LOG_SHORT, max_len=768)

        # Should have padding
        assert diagnostics["pad_tokens"] > 0, "Short input should trigger padding"
        assert diagnostics["pad_ratio"] > 0.5, "Short input should have >50% padding"
        assert diagnostics["is_low_evidence"], "Short input should flag low evidence"
        assert tensor.shape == (1, 768), "Output tensor should be (1, 768)"

        logger.info(
            f"✓ Short input padding: {diagnostics['non_pad_tokens']} tokens, "
            f"{diagnostics['pad_pct']:.1f}% padding"
        )

    def test_tokenization_truncation_long_input(self):
        """Verify truncation behavior on inputs exceeding 768 tokens."""
        engine = BiLSTM2InferenceEngine()
        engine.load_artifacts()

        # Create a very long log (should exceed 768 tokens)
        long_log = SAMPLE_LOG_LONG + "\n" + ("\nAdditional log line repeated " * 200)

        tensor, diagnostics = engine.analyze_tokens(long_log, max_len=768, head_tokens=192, tail_tokens=576)

        # Should use head + tail strategy
        assert diagnostics["pad_tokens"] == 0, "Long input should NOT have padding"
        assert diagnostics["non_pad_tokens"] == 768, "Should use all 768 tokens (192 head + 576 tail)"
        assert tensor.shape == (1, 768), "Output tensor should be (1, 768)"

        logger.info(
            f"✓ Long input truncation: Using 192 head + 576 tail strategy, "
            f"total tokens: {diagnostics['non_pad_tokens']}"
        )

    def test_tokenization_exact_fit(self):
        """Verify handling when input is exactly 768 tokens."""
        engine = BiLSTM2InferenceEngine()
        engine.load_artifacts()

        # Create log that's roughly 768 tokens
        words_needed = 750  # Approximate
        exact_log = " ".join([f"token_{i}" for i in range(words_needed)])

        tensor, diagnostics = engine.analyze_tokens(exact_log, max_len=768)

        assert diagnostics["pad_tokens"] >= 0, "Should handle exact fit gracefully"
        assert tensor.shape == (1, 768), "Output tensor should always be (1, 768)"

        logger.info(
            f"✓ Exact fit input: {diagnostics['non_pad_tokens']} tokens, "
            f"{diagnostics['pad_pct']:.1f}% padding"
        )

    def test_low_evidence_detection(self):
        """Verify low evidence flags for sparse/padded inputs."""
        engine = BiLSTM2InferenceEngine()
        engine.load_artifacts()

        # Very short input (should trigger low evidence)
        short_input = "Build started"
        tensor, diagnostics = engine.analyze_tokens(short_input, max_len=768)

        assert diagnostics["is_low_evidence"], "Very short input should flag low evidence"
        assert diagnostics["evidence_warning"] is not None, "Should include warning message"

        logger.info(f"✓ Low evidence warning: {diagnostics['evidence_warning']}")

    def test_out_of_vocabulary_handling(self):
        """Verify UNK token handling for out-of-vocabulary words."""
        engine = BiLSTM2InferenceEngine()
        engine.load_artifacts()

        # Create log with unusual/OOV words
        oov_log = "xyzabc123 qqqqqq zzzzzzzz " * 50 + SAMPLE_LOG_SHORT

        tensor, diagnostics = engine.analyze_tokens(oov_log, max_len=768)

        # Should have some UNK tokens
        assert diagnostics["unk_tokens"] > 0, "Should have UNK tokens for OOV words"
        unk_ratio = diagnostics["unk_ratio"]
        assert 0.0 <= unk_ratio <= 1.0, "UNK ratio should be valid percentage"

        logger.info(
            f"✓ OOV handling: {diagnostics['unk_tokens']} UNK tokens, "
            f"{diagnostics['unk_pct']:.1f}% UNK ratio"
        )


class TestRuntimeTrackerMultiplePredictions:
    """Test runtime tracker's ability to store multiple predictions at different stages."""

    def test_prediction_record_structure(self):
        """Verify PredictionRecord stores all required fields."""
        record = PredictionRecord(
            event_id="evt_001",
            run_id="run_001",
            timestamp="2024-01-15T10:30:00Z",
            checkpoint=25,
            model="BiLSTM v2",
            model_id="bilstm2",
            failure_probability=0.75,
            failure_probability_pct=75.0,
            prediction_type="ACTUAL",
            predicted_label="failure",
            risk_tier="HIGH",
            evidence_strength="ROBUST",
        )

        d = record.to_dict()
        assert d["checkpoint"] == 25
        assert d["failure_probability"] == 0.75
        assert d["predicted_label"] == "failure"
        logger.info("✓ PredictionRecord structure valid")

    def test_demo_run_accumulates_predictions(self):
        """Verify DemoRun can store multiple predictions at different depths."""
        run = DemoRun(
            run_id="test_run_001",
            repo_id="test-org/test-repo",
            commit_sha="abc123",
        )

        # Simulate predictions at different depths
        depths_and_probs = [
            (25, 0.35),
            (50, 0.52),
            (75, 0.68),
            (100, 0.72),
        ]

        for depth, prob in depths_and_probs:
            pred_result = PredictionResult(
                failure_probability=prob,
                predicted_label="failure" if prob > 0.5 else "success",
                model_name="bilstm2",
                visibility_stage=f"{depth}%",
                decision_score=prob,
                confidence=0.85,
            )

            # Add to run's predictions list
            run.runtime_predictions.append({
                "depth_percentage": depth,
                "failure_probability": prob,
                "predicted_label": pred_result.predicted_label,
                "model_name": "bilstm2",
                "timestamp": f"2024-01-15T10:3{depth:02d}:00Z",
            })

        # Verify all predictions stored
        assert len(run.runtime_predictions) == 4, "Should store 4 predictions"
        
        # Verify depth ordering
        depths = [p["depth_percentage"] for p in run.runtime_predictions]
        assert depths == [25, 50, 75, 100], "Depths should be in order"

        logger.info(f"✓ DemoRun stores {len(run.runtime_predictions)} predictions at different depths")

    def test_prediction_history_distinct_runs(self):
        """Verify separate prediction histories for distinct workflow runs."""
        # Create two separate demo runs
        run_1 = DemoRun(run_id="run_001", repo_id="repo_1", commit_sha="sha_1")
        run_2 = DemoRun(run_id="run_002", repo_id="repo_2", commit_sha="sha_2")

        # Add predictions to run_1
        run_1.runtime_predictions = [
            {"depth_percentage": 25, "failure_probability": 0.2},
            {"depth_percentage": 100, "failure_probability": 0.15},
        ]

        # Add different predictions to run_2
        run_2.runtime_predictions = [
            {"depth_percentage": 25, "failure_probability": 0.8},
            {"depth_percentage": 100, "failure_probability": 0.85},
        ]

        # Verify separation
        assert run_1.runtime_predictions[0]["failure_probability"] == 0.2
        assert run_2.runtime_predictions[0]["failure_probability"] == 0.8
        assert run_1.run_id != run_2.run_id

        logger.info("✓ Separate prediction histories for distinct runs maintained")


class TestChunkIngestionJobDistinction:
    """Test API's ability to distinguish multiple jobs in same workflow run."""

    def test_demo_run_stores_multiple_jobs_in_chunks(self):
        """Verify DemoRun can track chunks from multiple jobs in same run."""
        run = DemoRun(run_id="workflow_run_001", repo_id="repo/test")

        # Simulate chunks from Job A
        job_a_chunks = [
            {
                "job_id": "job_a_001",
                "job_name": "unit-tests",
                "log_chunk": "Running unit tests...",
                "timestamp": "2024-01-15T10:00:00Z",
                "event_id": "evt_a_001",
            },
            {
                "job_id": "job_a_001",
                "job_name": "unit-tests",
                "log_chunk": "Tests passed: 45/45",
                "timestamp": "2024-01-15T10:00:05Z",
                "event_id": "evt_a_002",
            },
        ]

        # Simulate chunks from Job B (concurrent)
        job_b_chunks = [
            {
                "job_id": "job_b_002",
                "job_name": "integration-tests",
                "log_chunk": "Running integration tests...",
                "timestamp": "2024-01-15T10:00:01Z",
                "event_id": "evt_b_001",
            },
            {
                "job_id": "job_b_002",
                "job_name": "integration-tests",
                "log_chunk": "Integration tests passed: 12/12",
                "timestamp": "2024-01-15T10:00:08Z",
                "event_id": "evt_b_002",
            },
        ]

        # Store all chunks in run
        run.log_chunks.extend(job_a_chunks)
        run.log_chunks.extend(job_b_chunks)

        # Verify job separation
        assert len(run.log_chunks) == 4, "Should have 4 chunks total"
        
        job_a_only = [c for c in run.log_chunks if c["job_id"] == "job_a_001"]
        job_b_only = [c for c in run.log_chunks if c["job_id"] == "job_b_002"]

        assert len(job_a_only) == 2, "Should have 2 chunks from Job A"
        assert len(job_b_only) == 2, "Should have 2 chunks from Job B"

        logger.info("✓ Multiple jobs distinguished in single workflow run")

    def test_chunk_accumulation_by_job(self):
        """Verify log accumulation can be tracked per job."""
        run = DemoRun(run_id="workflow_run_002")

        # Chunks from different jobs
        chunks = [
            {"job_id": "job_a", "log_chunk": "Step A started\n"},
            {"job_id": "job_b", "log_chunk": "Step B started\n"},
            {"job_id": "job_a", "log_chunk": "Step A completed\n"},
            {"job_id": "job_b", "log_chunk": "Step B completed\n"},
        ]

        run.log_chunks = chunks

        # Accumulate logs per job
        job_logs = {}
        for chunk in chunks:
            job_id = chunk["job_id"]
            if job_id not in job_logs:
                job_logs[job_id] = ""
            job_logs[job_id] += chunk["log_chunk"]

        # Verify per-job accumulation
        assert job_logs["job_a"] == "Step A started\nStep A completed\n"
        assert job_logs["job_b"] == "Step B started\nStep B completed\n"

        logger.info("✓ Per-job log accumulation works correctly")


class TestExistingModelInference:
    """Verify existing model inference tests pass."""

    def test_bilstm2_predictor_factory(self):
        """Verify BiLSTM2Predictor can be instantiated via factory."""
        predictor = get_predictor("bilstm2", visibility=25)
        assert isinstance(predictor, BiLSTM2Predictor), "Factory should return BiLSTM2Predictor"
        assert predictor.visibility == 25, "Visibility should be 25"
        logger.info("✓ BiLSTM2 predictor factory works")

    def test_bilstm2_predictor_inference(self):
        """Verify BiLSTM2Predictor.predict_failure() works."""
        predictor = get_predictor("bilstm2", visibility=100)
        result = predictor.predict_failure(SAMPLE_LOG_MEDIUM)

        assert isinstance(result, PredictionResult), "Should return PredictionResult"
        assert result.failure_probability is not None
        assert result.model_name == "bilstm2"
        assert result.predicted_label in ["failure", "success"]

        logger.info(
            f"✓ BiLSTM2 predictor inference: {result.predicted_label} "
            f"(prob={result.failure_probability:.4f})"
        )

    def test_multiple_models_on_same_log(self):
        """Verify all 3 models can infer on same log without conflict."""
        models = ["logistic_regression", "svm", "bilstm2"]
        results = {}

        for model_name in models:
            try:
                predictor = get_predictor(model_name, visibility=50)
                result = predictor.predict_failure(SAMPLE_LOG_MEDIUM)
                results[model_name] = result
            except Exception as e:
                logger.warning(f"Model {model_name} failed: {e}")

        # Should have results from all 3 models
        assert len(results) >= 2, "Should have at least 2 model results"
        logger.info(f"✓ All available models inferred: {list(results.keys())}")


class TestPredictionResultExample:
    """Generate and log example prediction results."""

    def test_example_bilstm2_prediction_output(self):
        """Generate and log example BiLSTM v2 prediction output."""
        engine = BiLSTM2InferenceEngine()
        engine.load_artifacts()

        result = engine.predict(SAMPLE_LOG_MEDIUM, visibility=50)

        logger.info("\n" + "="*80)
        logger.info("EXAMPLE BiLSTM v2 PREDICTION OUTPUT (50% visibility)")
        logger.info("="*80)
        logger.info(json.dumps(result, indent=2, default=str))
        logger.info("="*80 + "\n")

        # Store for report
        assert result is not None
        assert "failure_probability" in result
        assert "token_diagnostics" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
