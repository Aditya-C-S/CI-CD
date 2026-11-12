"""
PHASE 3 Tests: Log Size Estimator

Comprehensive tests for:
1. Historical statistics recording
2. Median calculation
3. Threshold calculation
4. Grouping by repository, workflow, job
5. Fallback estimates
6. Edge cases
7. Database persistence and deduplication
"""

import logging
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from src.ingestion.log_size_estimator import (
    LogSizeEstimate,
    LogSizeEstimator,
    get_log_size_estimator,
    DEFAULT_ESTIMATED_LINES,
    HISTORICAL_RUNS_TO_USE,
    WorkflowRunStat,
)

logger = logging.getLogger(__name__)


class TestLogSizeEstimatorBasics:
    """Test basic estimator functionality."""

    def test_estimator_singleton(self):
        """Verify LogSizeEstimator is a singleton."""
        est1 = get_log_size_estimator()
        est2 = get_log_size_estimator()
        assert est1 is est2, "Should return same singleton instance"
        logger.info("✓ Singleton pattern works")

    def test_database_initialization(self):
        """Verify database initializes correctly."""
        estimator = get_log_size_estimator()
        
        # Check database exists
        assert estimator.db_path.exists(), "Database file should exist"
        
        # Check size
        db_stats = estimator.get_database_size()
        assert "total_records" in db_stats
        logger.info(f"✓ Database initialized: {db_stats['total_records']} records, {db_stats['file_size_mb']} MB")


class TestRecordingCompletedRuns:
    """Test recording workflow run statistics."""

    def test_record_single_run(self):
        """Record a single completed run."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()  # Start fresh
        
        success = estimator.record_completed_run(
            repository_id="test-org/test-repo",
            run_id="run_001",
            actual_line_count=1000,
            workflow_id="ci.yml",
            job_id="test-job",
            commit_sha="abc123",
            workflow_outcome="success",
        )
        
        assert success, "Should successfully record run"
        
        # Verify record exists
        stats = estimator.get_historical_statistics(
            repository_id="test-org/test-repo",
            workflow_id="ci.yml",
            job_id="test-job",
        )
        assert stats["total_runs"] == 1
        assert stats["min_lines"] == 1000
        assert stats["max_lines"] == 1000
        logger.info("✓ Single run recorded")

    def test_record_multiple_runs(self):
        """Record multiple runs for same workflow."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        line_counts = [800, 950, 1100, 1050, 900]
        
        for i, count in enumerate(line_counts):
            estimator.record_completed_run(
                repository_id="test-org/test-repo",
                run_id=f"run_{i:03d}",
                actual_line_count=count,
                workflow_id="ci.yml",
                job_id="test-job",
            )
        
        # Verify all recorded
        stats = estimator.get_historical_statistics(
            repository_id="test-org/test-repo",
            workflow_id="ci.yml",
            job_id="test-job",
        )
        assert stats["total_runs"] == 5
        assert stats["min_lines"] == 800
        assert stats["max_lines"] == 1100
        logger.info(f"✓ Multiple runs recorded: {stats}")

    def test_duplicate_run_handling(self):
        """Verify duplicate run IDs with same context are handled correctly."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        # Record same run_id, workflow, job twice (should create 2 records since workflow_id/job_id are used in unique key)
        estimator.record_completed_run(
            repository_id="test-org/test-repo",
            run_id="run_001",
            actual_line_count=1000,
            workflow_id="ci.yml",
            job_id="test-job",
        )
        
        estimator.record_completed_run(
            repository_id="test-org/test-repo",
            run_id="run_001",
            actual_line_count=2000,
            workflow_id="ci.yml",
            job_id="test-job",
        )
        
        # Should have only 1 record (the second one replaced the first)
        stats = estimator.get_historical_statistics(
            repository_id="test-org/test-repo",
            workflow_id="ci.yml",
            job_id="test-job",
        )
        assert stats["total_runs"] == 1
        # Should use the latest (second) value
        assert stats["max_lines"] == 2000
        logger.info("✓ Duplicate handling works (REPLACE)")

    def test_reject_negative_line_count(self):
        """Reject runs with negative line counts."""
        estimator = get_log_size_estimator()
        
        success = estimator.record_completed_run(
            repository_id="test-org/test-repo",
            run_id="run_bad",
            actual_line_count=-100,
            workflow_id="ci.yml",
        )
        
        assert not success, "Should reject negative line count"
        logger.info("✓ Negative line counts rejected")

    def test_record_zero_line_count(self):
        """Allow zero-line logs (edge case)."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        success = estimator.record_completed_run(
            repository_id="test-org/test-repo",
            run_id="run_empty",
            actual_line_count=0,
            workflow_id="ci.yml",
        )
        
        assert success, "Should accept zero-line logs"
        logger.info("✓ Zero-line logs accepted")


class TestMedianCalculation:
    """Test median calculation logic."""

    def test_median_odd_count(self):
        """Calculate median for odd number of samples."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        samples = [100, 200, 300, 400, 500]
        for i, count in enumerate(samples):
            estimator.record_completed_run(
                repository_id="median-test",
                run_id=f"run_{i}",
                actual_line_count=count,
            )
        
        # Median should be 300 (middle value)
        estimate = estimator.estimate_log_size(repository_id="median-test")
        assert estimate.estimated_lines == 300
        logger.info(f"✓ Median (odd count): {estimate.estimated_lines}")

    def test_median_even_count(self):
        """Calculate median for even number of samples."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        samples = [100, 200, 300, 400]  # Even count
        for i, count in enumerate(samples):
            estimator.record_completed_run(
                repository_id="median-test",
                run_id=f"run_{i}",
                actual_line_count=count,
            )
        
        # Median should be average of 200 and 300 = 250
        estimate = estimator.estimate_log_size(repository_id="median-test")
        assert estimate.estimated_lines == 250
        logger.info(f"✓ Median (even count): {estimate.estimated_lines}")

    def test_median_single_sample(self):
        """Median with single sample."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        estimator.record_completed_run(
            repository_id="median-test",
            run_id="run_1",
            actual_line_count=750,
        )
        
        estimate = estimator.estimate_log_size(repository_id="median-test")
        assert estimate.estimated_lines == 750
        assert estimate.historical_runs_used == 1
        assert estimate.confidence == "LOW"
        logger.info(f"✓ Median (single sample): {estimate.estimated_lines}")

    def test_median_uses_most_recent_five(self):
        """Verify median uses only 5 most recent runs."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        # Record 10 runs with increasing values
        for i in range(10):
            estimator.record_completed_run(
                repository_id="median-test",
                run_id=f"run_{i:02d}",
                actual_line_count=(i + 1) * 100,  # 100, 200, ..., 1000
            )
        
        # Should use only most recent 5: runs 5-9 (600-1000)
        estimate = estimator.estimate_log_size(repository_id="median-test")
        
        # Median of [600, 700, 800, 900, 1000] = 800
        assert estimate.estimated_lines == 800
        assert estimate.historical_runs_used == 5
        logger.info(f"✓ Uses most recent 5 runs: median={estimate.estimated_lines}")


class TestThresholdCalculation:
    """Test 25%, 50%, 75%, 100% threshold calculation."""

    def test_thresholds_from_estimate(self):
        """Calculate thresholds from estimated line count."""
        estimator = get_log_size_estimator()
        
        thresholds = estimator.calculate_thresholds(1000)
        
        assert thresholds[25] == 250
        assert thresholds[50] == 500
        assert thresholds[75] == 750
        assert thresholds[100] == 1000
        logger.info(f"✓ Thresholds calculated: {thresholds}")

    def test_thresholds_maintain_order(self):
        """Verify thresholds maintain increasing order."""
        estimator = get_log_size_estimator()
        
        thresholds = estimator.calculate_thresholds(1234)
        
        assert thresholds[25] < thresholds[50] < thresholds[75] < thresholds[100]
        logger.info("✓ Thresholds maintain order")

    def test_thresholds_minimum_one_line(self):
        """Verify thresholds never go below 1 line."""
        estimator = get_log_size_estimator()
        
        # Even with very small estimate
        thresholds = estimator.calculate_thresholds(3)
        
        assert all(count >= 1 for count in thresholds.values())
        logger.info(f"✓ Minimum line enforcement: {thresholds}")


class TestGroupingByRepository:
    """Test grouping by repository, workflow, and job."""

    def test_different_repos_separate_estimates(self):
        """Different repositories should have separate estimates."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        # Repo A: 1000-line logs
        for i in range(3):
            estimator.record_completed_run(
                repository_id="repo-a",
                run_id=f"run_a_{i}",
                actual_line_count=1000,
                workflow_id="ci.yml",
            )
        
        # Repo B: 500-line logs
        for i in range(3):
            estimator.record_completed_run(
                repository_id="repo-b",
                run_id=f"run_b_{i}",
                actual_line_count=500,
                workflow_id="ci.yml",
            )
        
        # Get estimates
        est_a = estimator.estimate_log_size(repository_id="repo-a", workflow_id="ci.yml")
        est_b = estimator.estimate_log_size(repository_id="repo-b", workflow_id="ci.yml")
        
        assert est_a.estimated_lines == 1000
        assert est_b.estimated_lines == 500
        logger.info("✓ Different repos have separate estimates")

    def test_different_workflows_separate_estimates(self):
        """Different workflows should have separate estimates."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        # Workflow ci.yml: 1000 lines
        for i in range(3):
            estimator.record_completed_run(
                repository_id="repo",
                run_id=f"run_ci_{i}",
                actual_line_count=1000,
                workflow_id="ci.yml",
            )
        
        # Workflow release.yml: 500 lines
        for i in range(3):
            estimator.record_completed_run(
                repository_id="repo",
                run_id=f"run_release_{i}",
                actual_line_count=500,
                workflow_id="release.yml",
            )
        
        est_ci = estimator.estimate_log_size(repository_id="repo", workflow_id="ci.yml")
        est_release = estimator.estimate_log_size(repository_id="repo", workflow_id="release.yml")
        
        assert est_ci.estimated_lines == 1000
        assert est_release.estimated_lines == 500
        logger.info("✓ Different workflows have separate estimates")

    def test_different_jobs_separate_estimates(self):
        """Different jobs should have separate estimates."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        # Job test-ubuntu: 1000 lines
        for i in range(3):
            estimator.record_completed_run(
                repository_id="repo",
                run_id=f"run_ubuntu_{i}",
                actual_line_count=1000,
                workflow_id="ci.yml",
                job_id="test-ubuntu",
            )
        
        # Job test-macos: 800 lines
        for i in range(3):
            estimator.record_completed_run(
                repository_id="repo",
                run_id=f"run_macos_{i}",
                actual_line_count=800,
                workflow_id="ci.yml",
                job_id="test-macos",
            )
        
        est_ubuntu = estimator.estimate_log_size(
            repository_id="repo", workflow_id="ci.yml", job_id="test-ubuntu"
        )
        est_macos = estimator.estimate_log_size(
            repository_id="repo", workflow_id="ci.yml", job_id="test-macos"
        )
        
        assert est_ubuntu.estimated_lines == 1000
        assert est_macos.estimated_lines == 800
        logger.info("✓ Different jobs have separate estimates")


class TestFallbackEstimates:
    """Test fallback estimate when no history exists."""

    def test_fallback_no_history(self):
        """Use fallback when no historical data exists."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        estimate = estimator.estimate_log_size(
            repository_id="new-repo",
            default_estimate=2000,
        )
        
        assert estimate.is_fallback is True
        assert estimate.estimated_lines == 2000
        assert estimate.historical_runs_used == 0
        assert estimate.confidence == "LOW"
        logger.info(f"✓ Fallback estimate used: {estimate.estimated_lines}")

    def test_fallback_default_constant(self):
        """Verify DEFAULT_ESTIMATED_LINES is used when not specified."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        estimate = estimator.estimate_log_size(repository_id="new-repo")
        
        assert estimate.is_fallback is True
        assert estimate.estimated_lines == DEFAULT_ESTIMATED_LINES
        logger.info(f"✓ Default constant used: {DEFAULT_ESTIMATED_LINES}")

    def test_fallback_message_clear(self):
        """Verify fallback status is clearly indicated."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        estimate = estimator.estimate_log_size(repository_id="new-repo")
        
        # Check that confidence is LOW and is_fallback is True
        assert estimate.confidence == "LOW"
        assert estimate.is_fallback is True
        logger.info(f"✓ Fallback clearly indicated: is_fallback={estimate.is_fallback}")


class TestConfidenceLevels:
    """Test confidence classification."""

    def test_confidence_low_no_history(self):
        """Confidence is LOW when no history."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        estimate = estimator.estimate_log_size(repository_id="repo")
        assert estimate.confidence == "LOW"
        logger.info("✓ Confidence LOW with no history")

    def test_confidence_low_one_sample(self):
        """Confidence is LOW with one sample."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        estimator.record_completed_run(
            repository_id="repo",
            run_id="run_1",
            actual_line_count=1000,
        )
        
        estimate = estimator.estimate_log_size(repository_id="repo")
        assert estimate.confidence == "LOW"
        logger.info("✓ Confidence LOW with 1 sample")

    def test_confidence_medium_two_to_four_samples(self):
        """Confidence is MEDIUM with 2-4 samples."""
        estimator = get_log_size_estimator()
        
        for count in [2, 3, 4]:
            estimator.clear_all_data()
            
            for i in range(count):
                estimator.record_completed_run(
                    repository_id="repo",
                    run_id=f"run_{i}",
                    actual_line_count=1000,
                )
            
            estimate = estimator.estimate_log_size(repository_id="repo")
            assert estimate.confidence == "MEDIUM", f"Failed for {count} samples"
        
        logger.info("✓ Confidence MEDIUM with 2-4 samples")

    def test_confidence_high_five_plus_samples(self):
        """Confidence is HIGH with 5+ samples."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        for i in range(5):
            estimator.record_completed_run(
                repository_id="repo",
                run_id=f"run_{i}",
                actual_line_count=1000,
            )
        
        estimate = estimator.estimate_log_size(repository_id="repo")
        assert estimate.confidence == "HIGH"
        logger.info("✓ Confidence HIGH with 5+ samples")


class TestHistoricalStatistics:
    """Test historical statistics retrieval."""

    def test_get_statistics_empty(self):
        """Get statistics when no history exists."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        stats = estimator.get_historical_statistics(repository_id="nonexistent")
        
        assert stats["total_runs"] == 0
        assert stats["samples"] == []
        logger.info("✓ Statistics empty when no history")

    def test_get_statistics_trend_detection(self):
        """Detect trends in log sizes."""
        estimator = get_log_size_estimator()
        estimator.clear_all_data()
        
        # Record runs with increasing trend
        for i in range(10):
            estimator.record_completed_run(
                repository_id="repo",
                run_id=f"run_{i:02d}",
                actual_line_count=500 + (i * 100),  # 500, 600, ..., 1400
            )
        
        stats = estimator.get_historical_statistics(repository_id="repo")
        
        assert stats["total_runs"] == 10
        assert stats["recent_trend"] == "increasing"
        logger.info(f"✓ Trend detected: {stats['recent_trend']}")


class TestLogSizeEstimateDataclass:
    """Test LogSizeEstimate dataclass."""

    def test_estimate_to_dict(self):
        """Verify estimate can be converted to dict."""
        estimate = LogSizeEstimate(
            estimated_lines=1000,
            threshold_25=250,
            threshold_50=500,
            threshold_75=750,
            threshold_100=1000,
            historical_runs_used=5,
            is_fallback=False,
            confidence="HIGH",
        )
        
        d = estimate.to_dict()
        
        assert isinstance(d, dict)
        assert d["estimated_lines"] == 1000
        assert d["confidence"] == "HIGH"
        logger.info("✓ LogSizeEstimate serialization works")


class TestDemonstration:
    """Demonstration test showing complete workflow."""

    def test_phase3_demonstration(self):
        """
        Demonstration: Record 5 historical runs and calculate thresholds for new run.
        """
        logger.info("\n" + "="*80)
        logger.info("PHASE 3 DEMONSTRATION: Historical Log Size Estimator")
        logger.info("="*80)

        estimator = get_log_size_estimator()
        estimator.clear_all_data()

        # Step 1: Record 5 completed runs
        repo_id = "demo-org/demo-repo"
        workflow_id = "ci.yml"
        job_id = "test-ubuntu"

        historical_line_counts = [950, 1050, 1100, 900, 1000]

        logger.info("\n[STEP 1] Recording 5 historical completed runs:")
        for i, count in enumerate(historical_line_counts, 1):
            estimator.record_completed_run(
                repository_id=repo_id,
                run_id=f"workflow_run_{i:03d}",
                actual_line_count=count,
                workflow_id=workflow_id,
                job_id=job_id,
                commit_sha=f"commit_sha_{i:03d}",
                workflow_outcome="success",
            )
            logger.info(f"  Run {i}: {count} lines")

        # Step 2: Get estimate for new run
        logger.info("\n[STEP 2] Estimating size for next run:")
        estimate = estimator.estimate_log_size(
            repository_id=repo_id,
            workflow_id=workflow_id,
            job_id=job_id,
        )

        logger.info(f"  Estimated lines: {estimate.estimated_lines}")
        logger.info(f"  Confidence: {estimate.confidence}")
        logger.info(f"  Historical samples used: {estimate.historical_runs_used}")
        logger.info(f"  Median from history: {estimate.median_from_history}")
        logger.info(f"  Sample distribution: {estimate.historical_samples}")

        # Step 3: Calculate thresholds
        logger.info("\n[STEP 3] Calculating 25%/50%/75%/100% thresholds:")
        logger.info(f"  25%: {estimate.threshold_25} lines")
        logger.info(f"  50%: {estimate.threshold_50} lines")
        logger.info(f"  75%: {estimate.threshold_75} lines")
        logger.info(f"  100%: {estimate.threshold_100} lines")

        # Step 4: Verify statistics
        logger.info("\n[STEP 4] Historical statistics:")
        stats = estimator.get_historical_statistics(
            repository_id=repo_id,
            workflow_id=workflow_id,
            job_id=job_id,
        )
        logger.info(f"  Total runs: {stats['total_runs']}")
        logger.info(f"  Min lines: {stats['min_lines']}")
        logger.info(f"  Max lines: {stats['max_lines']}")
        logger.info(f"  Mean lines: {stats['mean_lines']}")
        logger.info(f"  Median lines: {stats['median_lines']}")
        logger.info(f"  Trend: {stats['recent_trend']}")

        # Assertions
        assert estimate.estimated_lines == 1000  # Median of [900, 950, 1000, 1050, 1100]
        assert estimate.confidence == "HIGH"
        assert estimate.threshold_25 == 250
        assert estimate.threshold_50 == 500
        assert estimate.threshold_75 == 750
        assert estimate.threshold_100 == 1000

        logger.info("\n✅ DEMONSTRATION COMPLETE")
        logger.info("="*80 + "\n")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
