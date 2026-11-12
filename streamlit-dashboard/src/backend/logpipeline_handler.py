"""
Log Pipeline API Client Handler

Provides interface to query and retrieve run results from the Log Pipeline backend.
Handles run discovery, filtering, polling, and result transformation for dashboard display.
"""

import logging
import requests
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class LogPipelineHandler:
    """Client for Log Pipeline API endpoints."""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        """
        Initialize Log Pipeline handler.
        
        Args:
            base_url: Base URL of Log Pipeline API (default: localhost:8000)
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        logger.info(f"LogPipelineHandler initialized with base_url={self.base_url}")
    
    def check_api_health(self) -> Tuple[bool, Optional[str]]:
        """
        Check if Log Pipeline API is available.
        
        Returns:
            Tuple of (is_healthy, error_message):
            - (True, None) if API is reachable
            - (False, error_msg) if API is unreachable
        """
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            if response.status_code == 200:
                return True, None
            else:
                return False, f"API returned status {response.status_code}"
        except requests.ConnectionError:
            return False, f"Cannot connect to Log Pipeline API at {self.base_url}"
        except requests.Timeout:
            return False, f"Log Pipeline API timeout at {self.base_url}"
        except Exception as e:
            return False, f"Error checking API health: {str(e)}"
    
    def list_runs(self, limit: int = 50) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        List recent runs from Log Pipeline.
        
        Args:
            limit: Maximum number of runs to retrieve (default: 50)
        
        Returns:
            Tuple of (runs_list, error_message):
            - (runs_list, None) on success
            - (None, error_msg) on failure
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/demo/runs",
                params={"limit": limit},
                timeout=10
            )
            
            if response.status_code == 200:
                runs = response.json()
                logger.info(f"Retrieved {len(runs)} runs from Log Pipeline")
                return runs, None
            else:
                error_msg = f"API returned status {response.status_code}"
                logger.error(f"Error listing runs: {error_msg}")
                return None, error_msg
        
        except requests.Timeout:
            error_msg = "List runs request timed out"
            logger.error(error_msg)
            return None, error_msg
        except Exception as e:
            error_msg = f"Error listing runs: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
    
    def find_runs_by_commit(self, repo_id: str, commit_sha: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        Find all runs matching the repository and commit SHA.
        
        Since the backend doesn't support direct filtering, this fetches all runs
        and filters client-side by repo_id and commit_sha.
        
        Args:
            repo_id: Repository identifier (owner/repo)
            commit_sha: Commit SHA (7+ characters)
        
        Returns:
            Tuple of (matching_runs, error_message):
            - (matching_runs, None) on success (may be empty list if no matches)
            - (None, error_msg) on failure
        """
        runs, error = self.list_runs(limit=100)
        
        if error:
            return None, error
        
        # Filter runs by repo_id and commit_sha
        # Normalize commit_sha for comparison (handle both full and short SHA)
        matching_runs = [
            run for run in (runs or [])
            if (
                run.get("repo_id") == repo_id and
                (
                    run.get("commit_sha") == commit_sha or
                    run.get("commit_sha", "").startswith(commit_sha)
                )
            )
        ]
        
        logger.info(
            f"Found {len(matching_runs)} run(s) for {repo_id} @ {commit_sha}"
        )
        return matching_runs, None
    
    def get_run(self, run_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Retrieve complete run details by run_id.
        
        Args:
            run_id: Run identifier
        
        Returns:
            Tuple of (run_dict, error_message)
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/demo/runs/{run_id}",
                timeout=10
            )
            
            if response.status_code == 200:
                run_data = response.json()
                logger.info(f"Retrieved run {run_id}")
                return run_data, None
            elif response.status_code == 404:
                error_msg = f"Run {run_id} not found"
                logger.warning(error_msg)
                return None, error_msg
            else:
                error_msg = f"API returned status {response.status_code}"
                logger.error(f"Error getting run {run_id}: {error_msg}")
                return None, error_msg
        
        except requests.Timeout:
            error_msg = f"Request timed out retrieving run {run_id}"
            logger.error(error_msg)
            return None, error_msg
        except Exception as e:
            error_msg = f"Error retrieving run {run_id}: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
    
    def get_run_rca(self, run_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Retrieve Root Cause Analysis report for a run.
        
        Args:
            run_id: Run identifier
        
        Returns:
            Tuple of (rca_report, error_message)
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/rca/{run_id}",
                timeout=10
            )
            
            if response.status_code == 200:
                rca_data = response.json()
                logger.info(f"Retrieved RCA for run {run_id}")
                return rca_data, None
            elif response.status_code == 404:
                # RCA may not be available yet
                logger.debug(f"RCA not available for run {run_id}")
                return None, None
            else:
                error_msg = f"API returned status {response.status_code}"
                logger.error(f"Error getting RCA for {run_id}: {error_msg}")
                return None, error_msg
        
        except requests.Timeout:
            error_msg = f"Request timed out retrieving RCA for {run_id}"
            logger.error(error_msg)
            return None, error_msg
        except Exception as e:
            error_msg = f"Error retrieving RCA for {run_id}: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
    
    def get_run_prediction_history(self, run_id: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        Retrieve prediction history (checkpoint predictions) for a run.
        
        Args:
            run_id: Run identifier
        
        Returns:
            Tuple of (prediction_history, error_message)
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/prediction/history/{run_id}",
                timeout=10
            )
            
            if response.status_code == 200:
                history = response.json()
                logger.info(f"Retrieved {len(history)} prediction checkpoints for run {run_id}")
                return history, None
            elif response.status_code == 404:
                logger.debug(f"Prediction history not available for run {run_id}")
                return [], None
            else:
                error_msg = f"API returned status {response.status_code}"
                logger.error(f"Error getting prediction history for {run_id}: {error_msg}")
                return None, error_msg
        
        except requests.Timeout:
            error_msg = f"Request timed out retrieving prediction history for {run_id}"
            logger.error(error_msg)
            return None, error_msg
        except Exception as e:
            error_msg = f"Error retrieving prediction history for {run_id}: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
    
    def get_run_summary(self, run_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Retrieve post-execution summary for a run.
        
        Args:
            run_id: Run identifier
        
        Returns:
            Tuple of (summary, error_message)
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/demo/runs/{run_id}/summary",
                timeout=10
            )
            
            if response.status_code == 200:
                summary = response.json()
                logger.info(f"Retrieved summary for run {run_id}")
                return summary, None
            elif response.status_code == 404:
                logger.debug(f"Summary not available for run {run_id}")
                return None, None
            else:
                error_msg = f"API returned status {response.status_code}"
                logger.error(f"Error getting summary for {run_id}: {error_msg}")
                return None, error_msg
        
        except requests.Timeout:
            error_msg = f"Request timed out retrieving summary for {run_id}"
            logger.error(error_msg)
            return None, error_msg
        except Exception as e:
            error_msg = f"Error retrieving summary for {run_id}: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
    
    def get_run_model_comparison(self, run_id: str, depth: Optional[int] = None) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Retrieve model comparison results for a run.
        
        Compares BiLSTM, TF-IDF + SVM, and TF-IDF + Logistic Regression models
        on the same log evidence.
        
        Args:
            run_id: Run identifier
            depth: Optional pipeline depth percentage (25, 50, 75, 100)
        
        Returns:
            Tuple of (model_comparison, error_message)
        """
        try:
            params = {}
            if depth is not None:
                params["depth"] = depth
            
            response = self.session.get(
                f"{self.base_url}/api/demo/runs/{run_id}/model-comparison",
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                comparison = response.json()
                logger.info(f"Retrieved model comparison for run {run_id}")
                return comparison, None
            elif response.status_code == 404:
                logger.debug(f"Model comparison not available for run {run_id}")
                return None, None
            else:
                error_msg = f"API returned status {response.status_code}"
                logger.error(f"Error getting model comparison for {run_id}: {error_msg}")
                return None, error_msg
        
        except requests.Timeout:
            error_msg = f"Request timed out retrieving model comparison for {run_id}"
            logger.error(error_msg)
            return None, error_msg
        except Exception as e:
            error_msg = f"Error retrieving model comparison for {run_id}: {str(e)}"
            logger.error(error_msg)
            return None, error_msg

    def get_live_run_data(self, run_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Retrieve live run data for progress monitoring.
        
        Returns full run state including:
        - status, current_stage, stages
        - log_lines_count, accumulated_log, log_chunks_count
        - runtime_predictions[], current_runtime_prediction
        - early_warning, warning_history
        - parser_v2_result, rca_result, remediation_result
        - All other run fields
        
        Args:
            run_id: Run identifier
        
        Returns:
            Tuple of (run_data, error_message)
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/demo/runs/{run_id}",
                timeout=10
            )
            
            if response.status_code == 200:
                run_data = response.json()
                logger.debug(f"Retrieved live run data for {run_id}")
                return run_data, None
            elif response.status_code == 404:
                logger.debug(f"Run {run_id} not found")
                return None, "Run not found"
            else:
                error_msg = f"API returned status {response.status_code}"
                logger.error(f"Error getting live run data for {run_id}: {error_msg}")
                return None, error_msg
        
        except requests.Timeout:
            error_msg = f"Request timed out retrieving run {run_id}"
            logger.warning(error_msg)
            return None, error_msg
        except Exception as e:
            error_msg = f"Error retrieving live run data for {run_id}: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
