"""
ORC Handler: Subprocess invocation and result transformation for ORC CLI.

This module handles the integration between the Streamlit dashboard and the
ORC (Orchestrator for Risk Control) CLI, which provides:
- LightGBM-based failure probability prediction
- SHAP feature importance explanations
- Neo4j-based code graph synchronization
- Suspicious file identification and ranking
"""

import subprocess
import json
import sys
import os
import logging
from pathlib import Path
from typing import Tuple, Dict, Optional, List

logger = logging.getLogger(__name__)


class ORCHandler:
    """Handler for invoking ORC CLI and transforming results."""
    
    def __init__(self, orc_root: str, repo_path: str):
        """
        Initialize ORC handler.
        
        Args:
            orc_root: Path to ORC project root (where src/main.py is located)
            repo_path: Path to the local repository to analyze
        
        Raises:
            ValueError: If orc_root or repo_path doesn't exist
        """
        self.orc_root = Path(orc_root).resolve()
        self.repo_path = Path(repo_path).resolve()
        
        if not self.orc_root.exists():
            raise ValueError(f"ORC root does not exist: {self.orc_root}")
        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {self.repo_path}")
        
        logger.info(f"ORCHandler initialized with orc_root={self.orc_root}, repo_path={self.repo_path}")
    
    def analyze_commit(
        self,
        repo_id: str,
        target_sha: str,
        base_sha: Optional[str] = None
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Analyze a commit using ORC CLI.
        
        Args:
            repo_id: Repository identity (owner/repo)
            target_sha: Target commit SHA
            base_sha: Optional base commit SHA for graph diff
        
        Returns:
            Tuple of (result_dict, error_message):
            - (result_dict, None) on success - raw ORC JSON output
            - (None, error_message) on failure - user-friendly error string
        
        Note:
            - Exit code 0 indicates success; any other code indicates failure
            - stderr is logged but not directly exposed to user
            - stdout must be valid JSON when exit code is 0
        """
        # Verify repo_path is valid before calling ORC
        if not self.repo_path.exists():
            return None, f"Repository path does not exist: {self.repo_path}"
        
        cmd = [
            sys.executable, '-m', 'src.main',
            repo_id,
            target_sha,
            '--repo-path', str(self.repo_path),
            '--json'
        ]
        
        if base_sha:
            cmd.extend(['--base-sha', base_sha])
        
        logger.info(f"Invoking ORC: {' '.join(cmd)}")
        logger.info(f"DEBUG: Streamlit ORC Handler - repo_path is: {self.repo_path}")
        logger.info(f"DEBUG: Streamlit ORC Handler - repo_path exists: {self.repo_path.exists()}")
        logger.info(f"DEBUG: Streamlit ORC Handler - cmd is: {cmd}")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.orc_root),
                capture_output=True,
                text=True,
                timeout=300,
                env={**os.environ, 'PYTHONUNBUFFERED': '1'}
            )
        except subprocess.TimeoutExpired:
            error_msg = "Analysis timed out after 5 minutes. The commit may be in a large repository."
            logger.error(f"ORC timeout: {error_msg}")
            return None, error_msg
        except Exception as e:
            error_msg = f"Failed to invoke ORC: {str(e)}"
            logger.error(f"ORC invocation error: {error_msg}", exc_info=True)
            return None, error_msg
        
        # Log stderr if present (for debugging)
        if result.stderr:
            logger.debug(f"ORC stderr:\n{result.stderr}")
        
        # Check exit code
        if result.returncode != 0:
            # Extract error message from stderr (first line typically has the key error)
            error_lines = result.stderr.strip().split('\n')
            error_detail = error_lines[-1] if error_lines else "Unknown error"
            
            # Sanitize error message (remove sensitive info)
            error_detail = self._sanitize_error(error_detail)
            
            error_msg = f"ORC analysis failed: {error_detail}"
            logger.error(f"ORC failed with exit code {result.returncode}: {error_msg}")
            return None, error_msg
        
        # Parse JSON output
        # ORC may print log messages to stdout, so we need to find the JSON portion
        # JSON output should be a single object starting with { and ending with }
        stdout = result.stdout.strip()
        
        # Find the first { and last } to extract JSON
        json_start = stdout.find('{')
        json_end = stdout.rfind('}')
        
        if json_start >= 0 and json_end > json_start:
            # Extract just the JSON portion
            stdout = stdout[json_start:json_end + 1]
        
        try:
            result_dict = json.loads(stdout)
        except json.JSONDecodeError as e:
            error_msg = f"ORC returned invalid JSON: {str(e)}"
            logger.error(f"JSON parsing error: {error_msg}\nOutput (first 500 chars): {result.stdout[:500]}")
            return None, error_msg
        
        logger.info(f"ORC analysis succeeded: failure_probability={result_dict.get('failure_probability', 'N/A'):.1%}")
        return result_dict, None
    
    def transform_result(
        self,
        orc_result: Dict,
        repo_id: str
    ) -> Dict:
        """
        Transform raw ORC JSON result into dashboard UI format.
        
        Args:
            orc_result: Raw result from ORC CLI (JSON)
            repo_id: Repository identity for path normalization
        
        Returns:
            Transformed result dict ready for Workflow 1 display
        """
        # Extract core prediction fields
        failure_probability = orc_result.get('failure_probability', 0.0)
        verdict = orc_result.get('verdict', 'UNKNOWN')
        
        # Map verdict to risk level
        risk_level = self._map_verdict_to_risk_level(verdict)
        
        # Transform SHAP drivers
        shap_explanations = self._transform_shap_drivers(orc_result.get('shap_drivers', {}))
        
        # Transform suspicious files
        suspicious_files = self._transform_suspicious_files(
            orc_result.get('suspicious_files', []),
            repo_id
        )
        
        # Build graph relationships summary
        graph_relationships = self._build_graph_relationships(
            orc_result.get('graph_files_changed', {}),
            len(suspicious_files)
        )
        
        return {
            # Prediction results
            'failure_probability': failure_probability,
            'verdict': verdict,
            'risk_level': risk_level,
            
            # SHAP feature importance
            'shap_explanations': shap_explanations,
            
            # Suspicious files from graph RCA
            'suspicious_files': suspicious_files,
            
            # Graph synchronization
            'graph_status': orc_result.get('graph_status', 'UNKNOWN'),
            'graph_relationships': graph_relationships,
            
            # Metadata
            'processing_time_ms': orc_result.get('processing_time_ms', 0),
            'target_sha': orc_result.get('target_sha', ''),
            'timestamp': orc_result.get('timestamp', ''),
            
            # Store original for debugging
            'orc_raw_result': orc_result
        }
    
    def _transform_shap_drivers(self, shap_drivers: Dict) -> List[Dict]:
        """
        Transform SHAP drivers from ORC format to dashboard format.
        
        ORC format:
            {
                'positive': [[feature_name, contribution], ...],
                'negative': [[feature_name, contribution], ...]
            }
        
        Dashboard format:
            [
                {'name': feature_name, 'contribution': value, 'direction': 'positive'},
                ...
            ]
        """
        explanations = []
        
        for direction in ['positive', 'negative']:
            drivers = shap_drivers.get(direction, [])
            
            for item in drivers:
                # Support both array format [name, value] and dict format {feature, contribution}
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    name, contribution = item[0], item[1]
                elif isinstance(item, dict):
                    name = item.get('feature') or item.get('name')
                    contribution = item.get('contribution')
                else:
                    continue
                
                explanations.append({
                    'name': name,
                    'contribution': float(contribution),
                    'direction': direction
                })
        
        # Sort by absolute contribution (most impactful first)
        explanations.sort(key=lambda x: abs(x['contribution']), reverse=True)
        
        return explanations
    
    def _transform_suspicious_files(self, suspicious_files: List[Dict], repo_id: str) -> List[Dict]:
        """
        Transform suspicious files from ORC format to dashboard format.
        
        Handles:
        - Absolute paths from graph cache
        - Relative paths
        - Multiple path formats
        - None values
        """
        if not suspicious_files:
            return []
        
        transformed = []
        
        for sf in suspicious_files:
            file_path = sf.get('file_path', '')
            if not file_path:
                continue
            
            # Normalize path
            normalized_path = self._normalize_file_path(file_path, repo_id)
            
            # Infer file type from extension
            file_type = self._infer_file_type(normalized_path)
            
            # Extract reasons
            reasons = sf.get('reasons', [])
            primary_reason = reasons[0] if reasons else 'Connected to changes'
            
            transformed.append({
                'path': normalized_path,
                'score': float(sf.get('centrality_score', 0.5)),
                'type': file_type,
                'reason': primary_reason,
                'all_reasons': reasons
            })
        
        # Sort by centrality score (descending)
        transformed.sort(key=lambda x: x['score'], reverse=True)
        
        return transformed
    
    def _normalize_file_path(self, file_path: str, repo_id: str) -> str:
        """
        Normalize file path for display.
        
        If path is absolute and points inside .graph_cache, extract the
        relative repository path. Otherwise, use the path as-is or make
        it relative to repo root if possible.
        """
        path_obj = Path(file_path)
        
        # Check if path is in graph cache
        if '.graph_cache' in file_path:
            # Extract path after the repo name in cache
            # Format: .graph_cache/owner__repo/...
            try:
                parts = Path(file_path).parts
                cache_idx = parts.index('.graph_cache')
                # Skip .graph_cache and repo name, keep the rest
                if cache_idx + 2 < len(parts):
                    relative_parts = parts[cache_idx + 2:]
                    return '/'.join(relative_parts)
            except (ValueError, IndexError):
                pass
        
        # Try to make path relative to repo root
        try:
            rel_path = str(path_obj.relative_to(self.repo_path))
            return rel_path
        except ValueError:
            # Not relative to repo root; return as-is or fallback
            return str(path_obj)
    
    def _infer_file_type(self, file_path: str) -> str:
        """Infer file type from extension."""
        ext_map = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.ts': 'TypeScript',
            '.java': 'Java',
            '.cpp': 'C++',
            '.c': 'C',
            '.go': 'Go',
            '.rs': 'Rust',
            '.rb': 'Ruby',
            '.php': 'PHP',
            '.sh': 'Shell',
            '.yaml': 'YAML',
            '.yml': 'YAML',
            '.json': 'JSON',
            '.xml': 'XML',
            '.html': 'HTML',
            '.css': 'CSS',
        }
        
        ext = Path(file_path).suffix.lower()
        return ext_map.get(ext, 'Unknown')
    
    def _build_graph_relationships(self, graph_files_changed: Dict, num_suspicious: int) -> Dict:
        """
        Build graph relationships summary for display.
        
        Only displays genuine ORC data. Does not estimate node or edge counts.
        """
        return {
            'files_changed': {
                'added': graph_files_changed.get('added', 0),
                'modified': graph_files_changed.get('modified', 0),
                'deleted': graph_files_changed.get('deleted', 0),
                'renamed': graph_files_changed.get('renamed', 0)
            },
            'suspicious_file_count': num_suspicious
        }
    
    def _map_verdict_to_risk_level(self, verdict: str) -> str:
        """Map ORC verdict to dashboard risk level."""
        verdict_mapping = {
            'FAST-TRACK': 'LOW',
            'STANDARD GATE': 'MEDIUM',
            'ALERT': 'HIGH',
            'CRITICAL': 'HIGH',
            'PRE-MERGE BLOCK': 'HIGH'
        }
        return verdict_mapping.get(verdict, 'MEDIUM')
    
    def _sanitize_error(self, error_msg: str) -> str:
        """
        Sanitize error message to remove sensitive information.
        
        Never expose:
        - GitHub tokens
        - Neo4j passwords
        - Internal paths
        """
        import re
        
        # Remove token-like patterns
        error_msg = re.sub(r'ghp_[a-zA-Z0-9]+', '[GITHUB_TOKEN]', error_msg)
        error_msg = re.sub(r'password[=:]\s*[^\s]+', 'password=[REDACTED]', error_msg)
        
        # Shorten file paths to just filename (be careful with escaping)
        error_msg = re.sub(r'[A-Z]:\\[^\s]+\\', r'[PATH]\\', error_msg)
        error_msg = re.sub(r'/[^\s/]*/', '/[PATH]/', error_msg)
        
        return error_msg


def create_orc_handler(orc_root: Optional[str] = None, repo_path: Optional[str] = None) -> ORCHandler:
    """
    Factory function to create an ORC handler with configuration.
    
    Configuration priority:
    1. Explicit parameters
    2. Environment variables
    3. Defaults (ORC root only; REPO_PATH is mandatory)
    
    Args:
        orc_root: ORC project root (default: env var ORC_ROOT or ../orc)
        repo_path: Repository path to analyze (REQUIRED: env var REPO_PATH or explicit parameter)
    
    Returns:
        Configured ORCHandler instance
    
    Raises:
        ValueError: If required paths don't exist, REPO_PATH is not configured, or directory is not a Git repository
    """
    # Configure ORC root
    if not orc_root:
        orc_root = os.environ.get('ORC_ROOT')
        if not orc_root:
            # Try relative path from dashboard root
            dashboard_root = Path(__file__).parent.parent.parent
            orc_root = dashboard_root.parent / 'orc'
    
    # Configure repository path - MANDATORY
    if not repo_path:
        repo_path = os.environ.get('REPO_PATH', None)
    
    # REPO_PATH is required - no silent fallback to '.'
    if not repo_path or not repo_path.strip():
        raise ValueError(
            "REPO_PATH not configured. "
            "Set the REPO_PATH environment variable to point to the local Git repository "
            "being analyzed (e.g., export REPO_PATH=/path/to/Voice_based-_Tic-Tac-Toe). "
            "REPO_PATH must be an existing Git repository directory, not the dashboard directory."
        )
    
    # Validate repository path
    repo_path_obj = Path(repo_path).resolve()
    if not repo_path_obj.exists():
        raise ValueError(
            f"REPO_PATH points to non-existent directory: {repo_path_obj}. "
            f"Configure REPO_PATH to an existing local Git repository."
        )
    
    # Validate it's a Git repository
    git_dir = repo_path_obj / '.git'
    if not git_dir.exists():
        raise ValueError(
            f"REPO_PATH does not appear to be a Git repository: {repo_path_obj}. "
            f"The directory must contain a .git folder. "
            f"Configure REPO_PATH to point to the root of a Git repository."
        )
    
    return ORCHandler(str(orc_root), str(repo_path_obj))
