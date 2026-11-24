"""
ORC Handler: Unified HTTP client and result transformation for ORC Analysis.

This module handles the integration between the Streamlit dashboard and the
unified FastAPI backend (/api/orc/analyze-commit), providing:
- LightGBM-based failure probability prediction
- SHAP feature importance explanations
- Neo4j-based code graph synchronization
- Suspicious file identification and ranking
"""

import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class ORCHandler:
    """Handler for invoking unified FastAPI ORC endpoints and transforming results."""

    def __init__(
        self,
        orc_root: Optional[str] = None,
        repo_path: Optional[str] = None,
        backend_url: Optional[str] = None,
    ):
        """
        Initialize ORC handler.

        Args:
            orc_root: Path to ORC project root (optional / retained for backwards compatibility)
            repo_path: Path to the local repository to analyze
            backend_url: Base URL of the unified FastAPI backend (defaults to BACKEND_API_URL / LOGPIPELINE_URL / http://127.0.0.1:8000)

        Raises:
            ValueError: If repo_path is provided but does not exist
        """
        if orc_root:
            self.orc_root = Path(orc_root).resolve()
        else:
            self.orc_root = None

        if repo_path:
            self.repo_path = Path(repo_path).resolve()
            if not self.repo_path.exists():
                raise ValueError(f"Repository path does not exist: {self.repo_path}")
        else:
            self.repo_path = None

        # Resolve backend URL
        if not backend_url:
            backend_url = (
                os.environ.get("BACKEND_API_URL")
                or os.environ.get("LOGPIPELINE_URL")
                or "http://127.0.0.1:8000"
            )
        self.backend_url = backend_url.rstrip("/")

        # Initialize resilient session
        self.session = requests.Session()
        retries = Retry(
            total=2,
            backoff_factor=0.5,
            status_forcelist=[502, 503, 504],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        logger.info(
            f"ORCHandler initialized with backend_url={self.backend_url}, repo_path={self.repo_path}"
        )

    def resolve_repo_path(self, repo_id: str) -> Optional[Path]:
        """
        Resolve the appropriate repository path for the given repo_id.
        
        Priority:
        1. Check local repositories in Capstone directory (e.g. Capstone/<repo_name> or flask clone).
        2. If self.repo_path directory name matches repo_id, use self.repo_path.
        3. Check if a cache directory exists in Metadata-Pipeline-main/.repo_cache for this repo_id.
        4. Fall back to self.repo_path if it exists.
        """
        if not repo_id:
            return self.repo_path
        
        safe_repo_id = repo_id.strip().replace("/", "__")
        repo_name = repo_id.strip().split("/")[-1]
        dashboard_root = Path(__file__).resolve().parent.parent.parent

        # 1. Check local clones in Capstone root (e.g. Capstone/flask)
        try:
            capstone_root = dashboard_root.parents[2]
            candidate_clone = capstone_root / repo_name
            if candidate_clone.exists() and (candidate_clone / ".git").exists():
                return candidate_clone
        except Exception:
            pass

        # Explicit check for known Capstone flask clone
        flask_local = Path(r"C:\Users\Aditya CS\OneDrive\Documents\Capstone\flask")
        if repo_name.lower() == "flask" and flask_local.exists() and (flask_local / ".git").exists():
            return flask_local

        # 2. Check if configured repo_path matches repo_id
        if self.repo_path and self.repo_path.exists():
            curr_name = self.repo_path.name
            if curr_name.lower() in [safe_repo_id.lower(), repo_name.lower()]:
                return self.repo_path

        # 3. Check Metadata-Pipeline .repo_cache
        repo_cache_dir = dashboard_root.parent / "Metadata-Pipeline-main" / ".repo_cache" / safe_repo_id
        if repo_cache_dir.exists() and (repo_cache_dir / ".git").exists():
            return repo_cache_dir

        return self.repo_path

    def analyze_commit(
        self,
        repo_id: str,
        target_sha: str,
        base_sha: Optional[str] = None,
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Analyze a commit using the unified FastAPI backend (/api/orc/analyze-commit).

        Args:
            repo_id: Repository identity (owner/repo)
            target_sha: Target commit SHA
            base_sha: Optional base commit SHA for graph diff

        Returns:
            Tuple of (result_dict, error_message):
            - (result_dict, None) on success - raw ORC JSON output
            - (None, error_message) on failure - user-friendly error string
        """
        effective_repo_path = self.resolve_repo_path(repo_id)
        if not effective_repo_path or not effective_repo_path.exists():
            return None, f"Repository path does not exist: {effective_repo_path or self.repo_path}"

        endpoint = f"{self.backend_url}/api/orc/analyze-commit"
        payload = {
            "repo_id": repo_id,
            "target_sha": target_sha,
            "repo_path": str(effective_repo_path),
            "base_sha": base_sha,
        }

        logger.info(f"Invoking unified backend at {endpoint} for {repo_id}@{target_sha[:7]}")
        start_mono = time.perf_counter()

        try:
            response = self.session.post(
                endpoint,
                json=payload,
                timeout=120,
            )
            elapsed_ms = (time.perf_counter() - start_mono) * 1000

        except requests.exceptions.ConnectionError:
            error_msg = (
                f"Cannot connect to unified backend API at {self.backend_url}. "
                "Make sure the FastAPI server is running on port 8000."
            )
            logger.error(error_msg)
            return None, error_msg

        except requests.exceptions.Timeout:
            error_msg = (
                f"Analysis request timed out after 120s at {self.backend_url}. "
                "The repository or commit graph may be exceptionally large."
            )
            logger.error(error_msg)
            return None, error_msg

        except Exception as e:
            error_msg = f"Failed to communicate with backend: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return None, error_msg

        # Handle HTTP error status codes
        if response.status_code != 200:
            try:
                err_json = response.json()
                detail = err_json.get("detail", response.text)
            except Exception:
                detail = response.text or f"HTTP {response.status_code}"

            detail = self._sanitize_error(str(detail))
            error_msg = f"Backend analysis failed ({response.status_code}): {detail}"
            logger.error(error_msg)
            return None, error_msg

        # Parse JSON response
        try:
            result_dict = response.json()
        except json.JSONDecodeError as e:
            error_msg = f"Backend returned invalid JSON: {str(e)}"
            logger.error(error_msg)
            return None, error_msg

        # Ensure processing_time_ms is populated
        if result_dict.get("processing_time_ms", 0) <= 0:
            result_dict["processing_time_ms"] = elapsed_ms

        logger.info(
            f"ORC HTTP analysis succeeded in {result_dict.get('processing_time_ms', 0):.1f}ms: "
            f"failure_probability={result_dict.get('failure_probability', 0):.1%}"
        )
        return result_dict, None

    def transform_result(
        self,
        orc_result: Dict,
        repo_id: str,
    ) -> Dict:
        """
        Transform raw ORC JSON result into dashboard UI format.

        Args:
            orc_result: Raw result from ORC API (JSON)
            repo_id: Repository identity for path normalization

        Returns:
            Transformed result dict ready for Workflow 1 display
        """
        failure_probability = orc_result.get("failure_probability", 0.0)
        verdict = orc_result.get("verdict", "UNKNOWN")

        risk_level = self._map_verdict_to_risk_level(verdict)
        shap_explanations = self._transform_shap_drivers(orc_result.get("shap_drivers", {}))
        suspicious_files = self._transform_suspicious_files(
            orc_result.get("suspicious_files", []),
            repo_id,
        )
        graph_relationships = self._build_graph_relationships(
            orc_result.get("graph_files_changed", {}),
            len(suspicious_files),
        )

        return {
            "failure_probability": failure_probability,
            "verdict": verdict,
            "risk_level": risk_level,
            "shap_explanations": shap_explanations,
            "suspicious_files": suspicious_files,
            "graph_status": orc_result.get("graph_status", "UNKNOWN"),
            "graph_relationships": graph_relationships,
            "processing_time_ms": orc_result.get("processing_time_ms", 0),
            "target_sha": orc_result.get("target_sha", ""),
            "timestamp": orc_result.get("timestamp", ""),
            "commit_source": orc_result.get("commit_source", "Unknown"),
            "is_local_commit": orc_result.get("is_local_commit", False),
            "orc_raw_result": orc_result,
        }

    def _transform_shap_drivers(self, shap_drivers: Dict) -> List[Dict]:
        """Transform SHAP drivers from ORC format to dashboard format."""
        explanations = []

        for direction in ["positive", "negative"]:
            drivers = shap_drivers.get(direction, [])

            for item in drivers:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    name, contribution = item[0], item[1]
                elif isinstance(item, dict):
                    name = item.get("feature") or item.get("name")
                    contribution = item.get("contribution")
                else:
                    continue

                explanations.append({
                    "name": name,
                    "contribution": float(contribution),
                    "direction": direction,
                })

        return explanations

    def _transform_suspicious_files(
        self,
        suspicious_files: List[Dict],
        repo_id: str,
    ) -> List[Dict]:
        """Transform suspicious files from ORC format to dashboard format."""
        if not suspicious_files:
            return []

        transformed = []

        for sf in suspicious_files:
            file_path = sf.get("file_path", "")
            if not file_path:
                continue

            normalized_path = self._normalize_file_path(file_path, repo_id)
            file_type = self._infer_file_type(normalized_path)
            reasons = sf.get("reasons", [])
            primary_reason = reasons[0] if reasons else "Connected to changes"

            transformed.append({
                "path": normalized_path,
                "score": float(sf.get("centrality_score", 0.5)),
                "type": file_type,
                "reason": primary_reason,
                "all_reasons": reasons,
            })

        transformed.sort(key=lambda x: x["score"], reverse=True)
        return transformed

    def _normalize_file_path(self, file_path: str, repo_id: str) -> str:
        """Normalize file path for display."""
        path_obj = Path(file_path)

        if ".graph_cache" in file_path:
            try:
                parts = Path(file_path).parts
                cache_idx = parts.index(".graph_cache")
                if cache_idx + 2 < len(parts):
                    relative_parts = parts[cache_idx + 2 :]
                    return "/".join(relative_parts)
            except (ValueError, IndexError):
                pass

        if self.repo_path:
            try:
                rel_path = str(path_obj.relative_to(self.repo_path))
                return rel_path
            except ValueError:
                return str(path_obj)

        return str(path_obj)

    def _infer_file_type(self, file_path: str) -> str:
        """Infer file type from extension."""
        ext_map = {
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".java": "Java",
            ".cpp": "C++",
            ".c": "C",
            ".go": "Go",
            ".rs": "Rust",
            ".rb": "Ruby",
            ".php": "PHP",
            ".sh": "Shell",
            ".yaml": "YAML",
            ".yml": "YAML",
            ".json": "JSON",
            ".xml": "XML",
            ".html": "HTML",
            ".css": "CSS",
        }
        ext = Path(file_path).suffix.lower()
        return ext_map.get(ext, "Unknown")

    def _build_graph_relationships(self, graph_files_changed: Dict, num_suspicious: int) -> Dict:
        """Build graph relationships summary for display."""
        return {
            "files_changed": {
                "added": graph_files_changed.get("added", 0),
                "modified": graph_files_changed.get("modified", 0),
                "deleted": graph_files_changed.get("deleted", 0),
                "renamed": graph_files_changed.get("renamed", 0),
            },
            "suspicious_file_count": num_suspicious,
        }

    def _map_verdict_to_risk_level(self, verdict: str) -> str:
        """Map ORC verdict to dashboard risk level."""
        verdict_mapping = {
            "FAST-TRACK": "LOW",
            "STANDARD GATE": "MEDIUM",
            "ALERT": "HIGH",
            "CRITICAL": "HIGH",
            "PRE-MERGE BLOCK": "HIGH",
        }
        return verdict_mapping.get(verdict, "MEDIUM")

    def _sanitize_error(self, error_msg: str) -> str:
        """Sanitize error message to remove sensitive information."""
        error_msg = re.sub(r"ghp_[a-zA-Z0-9]+", "[GITHUB_TOKEN]", error_msg)
        error_msg = re.sub(r"password[=:]\s*[^\s]+", "password=[REDACTED]", error_msg)
        return error_msg


def create_orc_handler(
    orc_root: Optional[str] = None,
    repo_path: Optional[str] = None,
    backend_url: Optional[str] = None,
) -> ORCHandler:
    """
    Factory function to create a configured ORCHandler.

    Resolves configuration in priority order:
    1. Explicit parameters
    2. Environment variables (REPO_PATH, BACKEND_API_URL, LOGPIPELINE_URL, ORC_ROOT)
    3. Defaults

    Args:
        orc_root: Optional ORC project root (retained for backward compatibility)
        repo_path: Repository path to analyze (REQUIRED: env var REPO_PATH or parameter)
        backend_url: Backend API URL (default: env var BACKEND_API_URL or http://127.0.0.1:8000)

    Returns:
        Configured ORCHandler instance

    Raises:
        ValueError: If required paths don't exist, REPO_PATH is not configured, or directory is not a Git repository
    """
    dashboard_root = Path(__file__).parent.parent.parent

    # Configure backend URL
    if not backend_url:
        backend_url = (
            os.environ.get("BACKEND_API_URL")
            or os.environ.get("LOGPIPELINE_URL")
            or "http://127.0.0.1:8000"
        )

    # Configure repository path - MANDATORY
    if not repo_path:
        repo_path = os.environ.get("REPO_PATH", None)

    if not repo_path or not repo_path.strip():
        raise ValueError(
            "REPO_PATH not configured. "
            "Set the REPO_PATH environment variable to point to the local Git repository "
            "being analyzed (e.g., export REPO_PATH=/path/to/Voice_based-_Tic-Tac-Toe). "
            "REPO_PATH must be an existing Git repository directory, not the dashboard directory."
        )

    # Validate repository path
    repo_path_obj = Path(repo_path)
    if not repo_path_obj.is_absolute() and not repo_path_obj.exists():
        candidate1 = (dashboard_root / repo_path).resolve()
        candidate2 = (dashboard_root.parent / repo_path).resolve()
        if candidate1.exists():
            repo_path_obj = candidate1
        elif candidate2.exists():
            repo_path_obj = candidate2
        else:
            repo_path_obj = repo_path_obj.resolve()
    else:
        repo_path_obj = repo_path_obj.resolve()

    if not repo_path_obj.exists():
        raise ValueError(
            f"REPO_PATH points to non-existent directory: {repo_path_obj}. "
            f"Configure REPO_PATH to an existing local Git repository."
        )

    # Validate it's a Git repository
    git_dir = repo_path_obj / ".git"
    if not git_dir.exists():
        raise ValueError(
            f"REPO_PATH does not appear to be a Git repository: {repo_path_obj}. "
            f"The directory must contain a .git folder. "
            f"Configure REPO_PATH to point to the root of a Git repository."
        )

    # Resolve optional orc_root
    if not orc_root:
        orc_root_env = os.environ.get("ORC_ROOT")
        if orc_root_env:
            candidate = Path(orc_root_env)
            if not candidate.is_absolute() and not candidate.exists():
                if (dashboard_root / orc_root_env).resolve().exists():
                    orc_root = str((dashboard_root / orc_root_env).resolve())
                elif (dashboard_root.parent / orc_root_env).resolve().exists():
                    orc_root = str((dashboard_root.parent / orc_root_env).resolve())
                else:
                    orc_root = str((dashboard_root.parent / "orc").resolve())
            else:
                orc_root = str(candidate.resolve())
        else:
            orc_root = str((dashboard_root.parent / "orc").resolve())

    return ORCHandler(
        orc_root=orc_root,
        repo_path=str(repo_path_obj),
        backend_url=backend_url,
    )
