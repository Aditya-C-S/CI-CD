"""src/ingestion/log_size_estimator.py

Historical Log Size Estimator for Live CI/CD Log Ingestion

This module maintains historical statistics of completed workflow runs and uses them to estimate
the expected log size for new runs. Estimates are used to calculate progressive prediction thresholds
(25%, 50%, 75%, 100% of estimated final log size).

Key Features:
1. SQLite-based persistent storage of historical run statistics
2. Grouping by repository, workflow, and job
3. Median-based estimation using most recent 5 completed runs
4. Fallback to configurable default when no history exists
5. Clean interface for recording completed runs and retrieving estimates
6. Edge case handling (no history, duplicates, different repos/workflows)

Database Schema:
    workflow_run_stats (
        id: INTEGER PRIMARY KEY,
        repository_id: TEXT NOT NULL,
        workflow_id: TEXT,
        workflow_name: TEXT,
        job_id: TEXT,
        job_name: TEXT,
        run_id: TEXT NOT NULL,
        commit_sha: TEXT,
        actual_line_count: INTEGER NOT NULL,
        workflow_outcome: TEXT,  -- 'success' or 'failure'
        completed_at: TEXT,  -- ISO 8601 timestamp
        created_at: TEXT,
        PRIMARY KEY (repository_id, workflow_id, job_id, run_id)
    )

Usage Examples:
    # Record a completed run
    estimator.record_completed_run(
        repository_id="org/repo",
        workflow_id="ci.yml",
        job_id="test-ubuntu",
        run_id="abc123",
        commit_sha="def456",
        actual_line_count=1250,
        workflow_outcome="success",
        completed_at="2024-01-15T10:30:00Z"
    )

    # Estimate and get thresholds for a new run
    estimate = estimator.estimate_log_size(
        repository_id="org/repo",
        workflow_id="ci.yml",
        job_id="test-ubuntu"
    )
    thresholds = estimator.calculate_thresholds(estimate["estimated_lines"])

    # Get historical statistics
    stats = estimator.get_historical_statistics(
        repository_id="org/repo",
        workflow_id="ci.yml",
        job_id="test-ubuntu"
    )
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_ESTIMATED_LINES = 1000
"""Fallback estimate when no historical data exists."""

HISTORICAL_RUNS_TO_USE = 5
"""Number of most recent completed runs to use for median calculation."""

DATABASE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "log_size_estimates.db"
"""SQLite database location for persistent storage."""


@dataclass
class LogSizeEstimate:
    """Estimated log size for a workflow run."""
    estimated_lines: int
    """Estimated total line count for the completed run."""
    
    threshold_25: int
    """25% of estimated lines."""
    
    threshold_50: int
    """50% of estimated lines."""
    
    threshold_75: int
    """75% of estimated lines."""
    
    threshold_100: int
    """100% (full estimated lines)."""
    
    historical_runs_used: int
    """Number of historical runs used for estimation."""
    
    is_fallback: bool
    """Whether fallback default estimate was used (no history available)."""
    
    median_from_history: Optional[int] = None
    """Median line count from historical runs (if available)."""
    
    historical_samples: Optional[List[int]] = None
    """Actual line counts from historical runs used."""
    
    confidence: str = "MEDIUM"
    """Confidence level: LOW (0-1 runs), MEDIUM (2-4 runs), HIGH (5+ runs)."""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowRunStat:
    """Single workflow run statistics record."""
    repository_id: str
    workflow_id: Optional[str]
    workflow_name: Optional[str]
    job_id: Optional[str]
    job_name: Optional[str]
    run_id: str
    commit_sha: Optional[str]
    actual_line_count: int
    workflow_outcome: Optional[str]
    completed_at: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LogSizeEstimator:
    """
    Manages historical log statistics and estimates for future runs.
    
    Thread-safe singleton providing persistent storage of workflow run statistics
    and median-based estimation for new runs.
    """

    _instance: Optional[LogSizeEstimator] = None
    _lock = threading.Lock()

    def __new__(cls) -> LogSizeEstimator:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.db_path = DATABASE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_lock = threading.Lock()
        self._initialized = True

        # Initialize database
        self._initialize_database()
        logger.info("LogSizeEstimator initialized with database at %s", self.db_path)

    # =========================================================================
    # Database Management
    # =========================================================================

    def _initialize_database(self) -> None:
        """Create database schema if not exists."""
        with self._db_lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS workflow_run_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        repository_id TEXT NOT NULL,
                        workflow_id TEXT,
                        workflow_name TEXT,
                        job_id TEXT,
                        job_name TEXT,
                        run_id TEXT NOT NULL,
                        commit_sha TEXT,
                        actual_line_count INTEGER NOT NULL,
                        workflow_outcome TEXT,
                        completed_at TEXT,
                        created_at TEXT NOT NULL
                    )
                """)
                
                # Create unique index on (repository_id, workflow_id, job_id, run_id)
                # Using NULLS DISTINCT behavior
                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_run_identity
                    ON workflow_run_stats (repository_id, workflow_id, job_id, run_id)
                """)
                
                # Create indexes for common queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_repo_workflow_job
                    ON workflow_run_stats (repository_id, workflow_id, job_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_completed_at
                    ON workflow_run_stats (completed_at DESC)
                """)
                
                conn.commit()
                logger.debug("Database schema initialized")
            finally:
                conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # =========================================================================
    # Core Interface
    # =========================================================================

    def record_completed_run(
        self,
        repository_id: str,
        run_id: str,
        actual_line_count: int,
        workflow_id: Optional[str] = None,
        workflow_name: Optional[str] = None,
        job_id: Optional[str] = None,
        job_name: Optional[str] = None,
        commit_sha: Optional[str] = None,
        workflow_outcome: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> bool:
        """
        Record the statistics of a completed workflow run.

        Parameters
        ----------
        repository_id : str
            Unique identifier for the repository (e.g., "org/repo-name").
        run_id : str
            Unique identifier for the workflow run.
        actual_line_count : int
            Total number of lines in the completed log (>= 0).
        workflow_id : str, optional
            Identifier for the workflow (e.g., "ci.yml").
        workflow_name : str, optional
            Human-readable workflow name (e.g., "CI/CD Pipeline").
        job_id : str, optional
            Identifier for the job within the workflow.
        job_name : str, optional
            Human-readable job name (e.g., "ubuntu-tests").
        commit_sha : str, optional
            Git commit SHA that triggered the run.
        workflow_outcome : str, optional
            Outcome of the workflow: "success" or "failure".
        completed_at : str, optional
            ISO 8601 timestamp of completion. Defaults to now.

        Returns
        -------
        bool
            True if record was successfully inserted or updated, False on error.
        """
        if actual_line_count < 0:
            logger.warning("Rejecting negative line count for run %s", run_id)
            return False

        now_iso = datetime.now(timezone.utc).isoformat()
        completed_at_iso = completed_at or now_iso

        with self._db_lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT OR REPLACE INTO workflow_run_stats
                    (repository_id, workflow_id, workflow_name, job_id, job_name,
                     run_id, commit_sha, actual_line_count, workflow_outcome,
                     completed_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    repository_id, workflow_id, workflow_name, job_id, job_name,
                    run_id, commit_sha, actual_line_count, workflow_outcome,
                    completed_at_iso, now_iso
                ))

                conn.commit()
                logger.info(
                    "Recorded completed run: repo=%s, workflow=%s, job=%s, run=%s, lines=%d",
                    repository_id, workflow_id, job_id, run_id, actual_line_count
                )
                return True
            except sqlite3.IntegrityError as e:
                logger.debug("Duplicate run record (expected behavior): %s", e)
                return True  # Duplicate inserts are acceptable
            except Exception as e:
                logger.error("Failed to record completed run: %s", e)
                return False
            finally:
                conn.close()

    def estimate_log_size(
        self,
        repository_id: str,
        workflow_id: Optional[str] = None,
        job_id: Optional[str] = None,
        default_estimate: int = DEFAULT_ESTIMATED_LINES,
    ) -> LogSizeEstimate:
        """
        Estimate the expected log size for a new workflow run.

        Uses median of the most recent HISTORICAL_RUNS_TO_USE completed runs.
        If fewer runs exist, uses all available. If no history exists, uses fallback.

        Parameters
        ----------
        repository_id : str
            Repository identifier.
        workflow_id : str, optional
            Workflow identifier. If not provided, uses all workflows for this repo.
        job_id : str, optional
            Job identifier. If not provided, uses all jobs for this workflow.
        default_estimate : int, optional
            Fallback estimate when no history available. Defaults to 1000 lines.

        Returns
        -------
        LogSizeEstimate
            Estimate with thresholds (25%, 50%, 75%, 100%).
        """
        with self._db_lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                # Query historical runs (most recent first)
                query = "SELECT actual_line_count FROM workflow_run_stats WHERE repository_id = ?"
                params: List[Any] = [repository_id]

                if workflow_id:
                    query += " AND workflow_id = ?"
                    params.append(workflow_id)

                if job_id:
                    query += " AND job_id = ?"
                    params.append(job_id)

                query += f" ORDER BY completed_at DESC LIMIT {HISTORICAL_RUNS_TO_USE}"

                cursor.execute(query, params)
                rows = cursor.fetchall()

                historical_lines = [row["actual_line_count"] for row in rows]
                
                if not historical_lines:
                    # No history: use fallback
                    logger.info(
                        "No historical data for repo=%s, workflow=%s, job=%s; using fallback estimate=%d",
                        repository_id, workflow_id, job_id, default_estimate
                    )
                    return self._create_estimate(
                        estimated_lines=default_estimate,
                        historical_samples=None,
                        is_fallback=True,
                    )

                # Calculate median
                historical_lines_sorted = sorted(historical_lines)
                median = self._calculate_median(historical_lines_sorted)

                logger.info(
                    "Estimated log size: repo=%s, workflow=%s, job=%s, "
                    "samples=%d, median=%d, range=[%d, %d]",
                    repository_id, workflow_id, job_id,
                    len(historical_lines), median,
                    min(historical_lines), max(historical_lines)
                )

                return self._create_estimate(
                    estimated_lines=median,
                    historical_samples=historical_lines_sorted,
                    is_fallback=False,
                )

            except Exception as e:
                logger.error("Failed to estimate log size: %s", e)
                return self._create_estimate(
                    estimated_lines=default_estimate,
                    historical_samples=None,
                    is_fallback=True,
                )
            finally:
                conn.close()

    def calculate_thresholds(self, estimated_lines: int) -> Dict[int, int]:
        """
        Calculate prediction thresholds based on estimated log size.

        Parameters
        ----------
        estimated_lines : int
            Estimated total line count for the run.

        Returns
        -------
        Dict[int, int]
            Thresholds keyed by percentage: {25: lines_at_25, 50: ..., 75: ..., 100: ...}
        """
        return {
            25: max(1, int(estimated_lines * 0.25)),
            50: max(1, int(estimated_lines * 0.50)),
            75: max(1, int(estimated_lines * 0.75)),
            100: estimated_lines,
        }

    def get_historical_statistics(
        self,
        repository_id: str,
        workflow_id: Optional[str] = None,
        job_id: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Retrieve historical statistics for a workflow/job combination.

        Parameters
        ----------
        repository_id : str
            Repository identifier.
        workflow_id : str, optional
            Workflow identifier.
        job_id : str, optional
            Job identifier.
        limit : int, optional
            Maximum number of records to return. Defaults to 50.

        Returns
        -------
        Dict[str, Any]
            Statistics including:
            - total_runs: Total historical runs
            - samples: List of recent run records
            - min_lines: Minimum observed line count
            - max_lines: Maximum observed line count
            - mean_lines: Mean line count
            - median_lines: Median line count
            - recent_trend: "increasing", "decreasing", or "stable"
        """
        with self._db_lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                # Get all matching records ordered by date
                query = """
                    SELECT * FROM workflow_run_stats
                    WHERE repository_id = ?
                """
                params: List[Any] = [repository_id]

                if workflow_id:
                    query += " AND workflow_id = ?"
                    params.append(workflow_id)

                if job_id:
                    query += " AND job_id = ?"
                    params.append(job_id)

                query += " ORDER BY completed_at DESC LIMIT ?"
                params.append(limit)

                cursor.execute(query, params)
                rows = [dict(row) for row in cursor.fetchall()]

                if not rows:
                    return {
                        "total_runs": 0,
                        "samples": [],
                        "min_lines": None,
                        "max_lines": None,
                        "mean_lines": None,
                        "median_lines": None,
                        "recent_trend": "unknown",
                    }

                line_counts = [r["actual_line_count"] for r in rows]
                sorted_counts = sorted(line_counts)
                median = self._calculate_median(sorted_counts)
                mean = sum(line_counts) / len(line_counts)

                # Determine trend (first 5 vs last 5)
                trend = "stable"
                if len(line_counts) >= 10:
                    recent_mean = sum(line_counts[:5]) / 5
                    older_mean = sum(line_counts[-5:]) / 5
                    if recent_mean > older_mean * 1.1:
                        trend = "increasing"
                    elif recent_mean < older_mean * 0.9:
                        trend = "decreasing"

                return {
                    "total_runs": len(rows),
                    "samples": rows[:10],  # Return most recent 10
                    "min_lines": min(line_counts),
                    "max_lines": max(line_counts),
                    "mean_lines": round(mean, 1),
                    "median_lines": median,
                    "recent_trend": trend,
                }

            except Exception as e:
                logger.error("Failed to retrieve historical statistics: %s", e)
                return {
                    "total_runs": 0,
                    "samples": [],
                    "error": str(e),
                }
            finally:
                conn.close()

    # =========================================================================
    # Helper Methods
    # =========================================================================

    @staticmethod
    def _calculate_median(sorted_values: List[int]) -> int:
        """
        Calculate median of sorted list.

        Parameters
        ----------
        sorted_values : List[int]
            Pre-sorted list of integers.

        Returns
        -------
        int
            Median value (rounded for even-length lists).
        """
        if not sorted_values:
            return DEFAULT_ESTIMATED_LINES

        n = len(sorted_values)
        if n % 2 == 1:
            return sorted_values[n // 2]
        else:
            # Average of two middle values, rounded
            mid1 = sorted_values[n // 2 - 1]
            mid2 = sorted_values[n // 2]
            return round((mid1 + mid2) / 2)

    @staticmethod
    def _create_estimate(
        estimated_lines: int,
        historical_samples: Optional[List[int]] = None,
        is_fallback: bool = False,
    ) -> LogSizeEstimate:
        """Create a LogSizeEstimate from parameters."""
        thresholds = {
            25: max(1, int(estimated_lines * 0.25)),
            50: max(1, int(estimated_lines * 0.50)),
            75: max(1, int(estimated_lines * 0.75)),
            100: estimated_lines,
        }

        historical_runs_used = len(historical_samples) if historical_samples else 0
        median = historical_samples[len(historical_samples) // 2] if historical_samples else None

        if is_fallback:
            confidence = "LOW"
        elif historical_runs_used < 2:
            confidence = "LOW"
        elif historical_runs_used < 5:
            confidence = "MEDIUM"
        else:
            confidence = "HIGH"

        return LogSizeEstimate(
            estimated_lines=estimated_lines,
            threshold_25=thresholds[25],
            threshold_50=thresholds[50],
            threshold_75=thresholds[75],
            threshold_100=thresholds[100],
            historical_runs_used=historical_runs_used,
            is_fallback=is_fallback,
            median_from_history=median,
            historical_samples=historical_samples,
            confidence=confidence,
        )

    # =========================================================================
    # Database Maintenance
    # =========================================================================

    def clear_all_data(self) -> bool:
        """
        Clear all historical data. Use with caution.

        Returns
        -------
        bool
            True if successful, False on error.
        """
        with self._db_lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM workflow_run_stats")
                conn.commit()
                logger.warning("Cleared all historical data from estimator database")
                return True
            except Exception as e:
                logger.error("Failed to clear database: %s", e)
                return False
            finally:
                conn.close()

    def get_database_size(self) -> Dict[str, Any]:
        """
        Get database statistics.

        Returns
        -------
        Dict[str, Any]
            Statistics including record count, file size, etc.
        """
        with self._db_lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) as record_count FROM workflow_run_stats")
                record_count = cursor.fetchone()["record_count"]
                conn.close()

                file_size_mb = 0.0
                if self.db_path.exists():
                    file_size_mb = self.db_path.stat().st_size / (1024 * 1024)

                return {
                    "total_records": record_count,
                    "file_path": str(self.db_path),
                    "file_size_mb": round(file_size_mb, 4),
                }
            except Exception as e:
                logger.error("Failed to get database size: %s", e)
                return {"error": str(e)}


# Singleton getter
def get_log_size_estimator() -> LogSizeEstimator:
    """Get or create the singleton LogSizeEstimator instance."""
    return LogSizeEstimator()
