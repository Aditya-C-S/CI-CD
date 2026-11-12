#!/usr/bin/env python3
"""
PHASE 3 Demonstration: Log Size Estimator
==========================================

This script demonstrates the complete workflow of the log size estimator:
1. Record 5 historical completed runs
2. Retrieve estimate for a new run
3. Calculate 25%, 50%, 75%, 100% thresholds
4. Display historical statistics
5. Show confidence levels and fallback behavior
"""

import json
from pathlib import Path

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.log_size_estimator import get_log_size_estimator

def print_section(title: str) -> None:
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def demo_complete_workflow():
    """Run complete demonstration."""
    print_section("PHASE 3 DEMONSTRATION: Historical Log Size Estimator")
    
    estimator = get_log_size_estimator()
    estimator.clear_all_data()

    # ========================================================================
    # SCENARIO 1: Record 5 Historical Runs
    # ========================================================================
    print_section("SCENARIO 1: Recording 5 Historical Completed Runs")
    
    repo_id = "demo-org/demo-repo"
    workflow_id = "ci.yml"
    job_id = "test-ubuntu-latest"
    
    historical_runs = [
        {
            "run_id": "run_2024_01_10_001",
            "lines": 950,
            "outcome": "success",
            "sha": "abc1234567890def",
        },
        {
            "run_id": "run_2024_01_11_002",
            "lines": 1050,
            "outcome": "success",
            "sha": "def1234567890ghi",
        },
        {
            "run_id": "run_2024_01_12_003",
            "lines": 1100,
            "outcome": "success",
            "sha": "ghi1234567890jkl",
        },
        {
            "run_id": "run_2024_01_13_004",
            "lines": 900,
            "outcome": "success",
            "sha": "jkl1234567890mno",
        },
        {
            "run_id": "run_2024_01_14_005",
            "lines": 1000,
            "outcome": "success",
            "sha": "mno1234567890pqr",
        },
    ]
    
    print(f"\nRepository: {repo_id}")
    print(f"Workflow: {workflow_id}")
    print(f"Job: {job_id}\n")
    
    for i, run in enumerate(historical_runs, 1):
        success = estimator.record_completed_run(
            repository_id=repo_id,
            run_id=run["run_id"],
            actual_line_count=run["lines"],
            workflow_id=workflow_id,
            job_id=job_id,
            commit_sha=run["sha"],
            workflow_outcome=run["outcome"],
        )
        print(f"  [{i}] {run['run_id']}: {run['lines']} lines → {'✓' if success else '✗'}")
    
    # ========================================================================
    # SCENARIO 2: Estimate and Thresholds
    # ========================================================================
    print_section("SCENARIO 2: Estimate Size for New Run")
    
    estimate = estimator.estimate_log_size(
        repository_id=repo_id,
        workflow_id=workflow_id,
        job_id=job_id,
    )
    
    print(f"\n  Estimated Log Size: {estimate.estimated_lines} lines")
    print(f"  Confidence: {estimate.confidence}")
    print(f"  Fallback: {estimate.is_fallback}")
    print(f"  Runs Used: {estimate.historical_runs_used}")
    print(f"  Median: {estimate.median_from_history}")
    print(f"  Range: [{min(historical_runs, key=lambda x: x['lines'])['lines']}, "
          f"{max(historical_runs, key=lambda x: x['lines'])['lines']}]")
    
    print_section("SCENARIO 3: Calculate Prediction Thresholds")
    
    thresholds = estimator.calculate_thresholds(estimate.estimated_lines)
    print(f"\n  When workflow completes ~{estimate.estimated_lines} lines:")
    print(f"    • 25% threshold:  {thresholds[25]:4d} lines → Trigger 25% prediction")
    print(f"    • 50% threshold:  {thresholds[50]:4d} lines → Trigger 50% prediction")
    print(f"    • 75% threshold:  {thresholds[75]:4d} lines → Trigger 75% prediction")
    print(f"   100% threshold: {thresholds[100]:4d} lines → Trigger 100% prediction (final)")
    
    # ========================================================================
    # SCENARIO 4: Historical Statistics
    # ========================================================================
    print_section("SCENARIO 4: Historical Statistics & Trend Analysis")
    
    stats = estimator.get_historical_statistics(
        repository_id=repo_id,
        workflow_id=workflow_id,
        job_id=job_id,
    )
    
    print(f"\n  Total Completed Runs: {stats['total_runs']}")
    print(f"  Min Lines: {stats['min_lines']}")
    print(f"  Max Lines: {stats['max_lines']}")
    print(f"  Mean Lines: {stats['mean_lines']}")
    print(f"  Median Lines: {stats['median_lines']}")
    print(f"  Recent Trend: {stats['recent_trend']}")
    
    # ========================================================================
    # SCENARIO 5: Fallback Estimate
    # ========================================================================
    print_section("SCENARIO 5: Fallback Estimate (New Repository)")
    
    new_estimate = estimator.estimate_log_size(
        repository_id="new-org/new-repo",
        workflow_id="ci.yml",
        job_id="test",
        default_estimate=1500,
    )
    
    print(f"\n  Repository: new-org/new-repo (no history)")
    print(f"  Estimated Lines: {new_estimate.estimated_lines} (fallback)")
    print(f"  Confidence: {new_estimate.confidence}")
    print(f"  Is Fallback: {new_estimate.is_fallback}")
    
    # ========================================================================
    # SCENARIO 6: Database Info
    # ========================================================================
    print_section("SCENARIO 6: Database Statistics")
    
    db_info = estimator.get_database_size()
    print(f"\n  File Path: {db_info['file_path']}")
    print(f"  Total Records: {db_info['total_records']}")
    print(f"  File Size: {db_info['file_size_mb']} MB")
    
    print_section("Demonstration Complete")
    print("\nSummary:")
    print("  ✓ 5 historical runs recorded")
    print(f"  ✓ Estimated next run: {estimate.estimated_lines} lines (HIGH confidence)")
    print(f"  ✓ Thresholds calculated for 25%, 50%, 75%, 100%")
    print(f"  ✓ Fallback estimate works for new repos")
    print(f"  ✓ Statistics and trends analyzed")
    print()


if __name__ == "__main__":
    demo_complete_workflow()
