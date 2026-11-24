"""Core orchestration logic: prediction + graph sync + investigation."""

import os
import time
import subprocess
import logging
from pathlib import Path
from typing import Dict, Optional, List, Any

from .adapters import MetadataAdapter, GraphAdapter
from .models import CommitPredictionResult, GraphSyncStatus, SuspiciousFile
from .storage import CheckpointManager, CheckpointState
from .errors import (
    OrchestratorException,
    PredictionException,
    GraphSyncException,
    InvalidCommitException,
)


logger = logging.getLogger(__name__)


class Orchestrator:
    """Main orchestration engine."""
    
    def __init__(
        self,
        github_token: str,
        investigation_threshold: float = 0.50,
        max_retries: int = 3,
        retry_backoff_seconds: float = 2.0,
    ):
        """
        Initialize orchestrator.
        
        Args:
            github_token: GitHub PAT for API access
            investigation_threshold: Risk probability threshold for suspicious-file investigation
            max_retries: Maximum number of retries for transient failures
            retry_backoff_seconds: Initial backoff time for exponential retry
        """
        self.github_token = github_token
        self.investigation_threshold = investigation_threshold
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.checkpoint_manager = CheckpointManager()
    
    def process_commit(
        self,
        repo_id: str,
        target_sha: str,
        repo_path: str,
        base_sha: Optional[str] = None,
    ) -> CommitPredictionResult:
        """
        Process a commit: predict risk, sync graph, investigate if needed, and handle retries.
        
        Args:
            repo_id: Repository identity (owner/repo)
            target_sha: Target commit SHA
            repo_path: Path to local repository
            base_sha: Base commit for graph diff (if None, will compute from target_sha~1)
        
        Returns:
            CommitPredictionResult with all details
        
        Raises:
            OrchestratorException: If processing fails
        """
        start_time = time.perf_counter()
        logger.info(f"Processing {repo_id}@{target_sha[:7]}")
        logger.info(f"DEBUG: process_commit called with repo_path={repo_path}")
        
        # Check if already processed
        cached = self.checkpoint_manager.get(repo_id, target_sha)
        if cached and cached["state"] == CheckpointState.COMPLETE:
            logger.info(f"Cache hit: {repo_id}@{target_sha[:7]} already processed")
            return self._result_from_checkpoint(repo_id, target_sha, cached, repo_path=repo_path, start_time=start_time)
        
        # Initialize graph adapter placeholder (deferred until repo_path is resolved)
        graph_adapter = None
        effective_repo_path = repo_path
        
        try:
            # Step 1: Run prediction (use cached if available)
            if cached and cached["state"] in [
                CheckpointState.PREDICTION_COMPLETE,
                CheckpointState.GRAPH_SYNC_COMPLETE,
                CheckpointState.INVESTIGATION_IN_PROGRESS,
            ]:
                logger.info(f"Reusing cached prediction from checkpoint")
                prediction_result = cached.get("prediction_result", {})
                if not prediction_result:
                    raise PredictionException("Cached checkpoint missing prediction_result")
            else:
                logger.info(f"Running prediction for {repo_id}@{target_sha[:7]}")
                logger.info(f"DEBUG: Creating MetadataAdapter with source_repo_path={repo_path}")
                # Initialize MetadataAdapter with repo_path as source for local commit analysis
                metadata_adapter = MetadataAdapter(self.github_token, source_repo_path=repo_path)
                prediction_result = metadata_adapter.predict(
                    repo_id.split("/")[0],
                    repo_id.split("/")[1],
                    target_sha,
                )
                
                # Save prediction to checkpoint
                self.checkpoint_manager.save(
                    repo_id,
                    target_sha,
                    CheckpointState.PREDICTION_COMPLETE,
                    prediction_result=prediction_result,
                )
                logger.info(f"Prediction complete: {prediction_result['verdict']}")
            
            # Step 1.5: Resolve effective repository path using MetadataAdapter's verified cache
            effective_repo_path = self._resolve_repo_path_for_repo(
                repo_id=repo_id,
                target_sha=target_sha,
                candidate_repo_path=repo_path,
                prediction_repo_path=prediction_result.get("repo_path"),
            )
            logger.info(f"Resolved effective repository path for graph sync: {effective_repo_path}")

            # Initialize graph adapter with verified repository path
            graph_adapter = GraphAdapter(repo_id, effective_repo_path)

            # Step 2: Synchronize graph (always, regardless of risk score)
            if cached and cached["state"] in [
                CheckpointState.GRAPH_SYNC_COMPLETE,
                CheckpointState.INVESTIGATION_IN_PROGRESS,
                CheckpointState.COMPLETE,
            ]:
                graph_sync_result = cached.get("graph_sync_result")
                if graph_sync_result:
                    logger.info(f"Graph already synced, skipping sync")
                else:
                    # Legacy checkpoint without graph_sync_result; re-sync to populate it
                    logger.warning(f"Cached checkpoint missing graph_sync_result; re-syncing to restore data")
                    if base_sha is None:
                        base_sha = self._get_parent_commit(target_sha, effective_repo_path)
                    graph_sync_result = graph_adapter.sync_to_sha(base_sha, target_sha)
                    # Update checkpoint with full result
                    self.checkpoint_manager.save(
                        repo_id,
                        target_sha,
                        CheckpointState.GRAPH_SYNC_COMPLETE,
                        prediction_result=prediction_result,
                        graph_files_changed={
                            "added": graph_sync_result["files_added"],
                            "modified": graph_sync_result["files_modified"],
                            "deleted": graph_sync_result["files_deleted"],
                            "renamed": graph_sync_result["files_renamed"],
                        },
                        graph_sync_result=graph_sync_result,
                    )
            else:
                logger.info(f"Synchronizing graph for {repo_id}@{target_sha[:7]}")
                
                # Determine base SHA if not provided
                # NEW LOGIC: Check if graph has an existing state that's an ancestor of target
                if base_sha is None:
                    # Get the graph's current state
                    graph_current_sync = graph_adapter.client.get_sync_state(repo_id)
                    if graph_current_sync and graph_current_sync.get("commit_verified"):
                        graph_current_sha = graph_current_sync.get("target_sha")
                        # Check if graph SHA is an ancestor of target SHA
                        is_ancestor = self._is_ancestor(graph_current_sha, target_sha, effective_repo_path)
                        if is_ancestor:
                            logger.info(
                                f"Graph is at {graph_current_sha[:7]}, which is an ancestor of target {target_sha[:7]}. "
                                f"Using graph SHA as base for incremental sync."
                            )
                            base_sha = graph_current_sha
                        else:
                            logger.warning(
                                f"Graph is at {graph_current_sha[:7]}, but it's not an ancestor of target {target_sha[:7]}. "
                                f"Histories appear diverged. Falling back to parent-based diff."
                            )
                            base_sha = self._get_parent_commit(target_sha, effective_repo_path)
                    else:
                        # No prior sync or unverified; use parent as base
                        base_sha = self._get_parent_commit(target_sha, effective_repo_path)
                
                graph_sync_result = graph_adapter.sync_to_sha(base_sha, target_sha)
                
                # Save graph sync to checkpoint
                self.checkpoint_manager.save(
                    repo_id,
                    target_sha,
                    CheckpointState.GRAPH_SYNC_COMPLETE,
                    prediction_result=prediction_result,
                    graph_files_changed={
                        "added": graph_sync_result["files_added"],
                        "modified": graph_sync_result["files_modified"],
                        "deleted": graph_sync_result["files_deleted"],
                        "renamed": graph_sync_result["files_renamed"],
                    },
                    graph_sync_result=graph_sync_result,
                )
                logger.info(f"Graph synchronized successfully")
            
            # Ensure base_sha is available for investigation phase
            if base_sha is None:
                base_sha = self._get_parent_commit(target_sha, effective_repo_path)
            
            # Step 3: Investigate if risk meets threshold (skip if already complete)
            if cached and cached["state"] == CheckpointState.COMPLETE:
                logger.info(f"Investigation already complete, using cached result")
                suspicious_files = None  # Would need to re-query or cache
            else:
                suspicious_files = None
                if prediction_result.get("failure_probability", 0.0) >= self.investigation_threshold:
                    logger.info(f"Risk >= threshold ({self.investigation_threshold}), investigating connected files")
                    
                    # Mark investigation as in progress before making expensive query
                    self.checkpoint_manager.save(
                        repo_id,
                        target_sha,
                        CheckpointState.INVESTIGATION_IN_PROGRESS,
                        prediction_result=prediction_result,
                        graph_files_changed={
                            "added": graph_sync_result.get("files_added", 0),
                            "modified": graph_sync_result.get("files_modified", 0),
                            "deleted": graph_sync_result.get("files_deleted", 0),
                            "renamed": graph_sync_result.get("files_renamed", 0),
                        },
                    )
                    
                    # Get changed files for this commit
                    changed_files = graph_sync_result.get("changed_files", [])
                    
                    # Query for connected files with evidence-based ranking
                    suspicious_files = graph_adapter.get_connected_files(changed_files, base_sha=base_sha, target_sha=target_sha)
                    logger.info(f"Found {len(suspicious_files)} suspicious files")
                else:
                    logger.info(f"Risk < threshold, skipping investigation")
            
            # Build result
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            result = CommitPredictionResult(
                repository_identity=repo_id,
                target_sha=target_sha,
                failure_probability=prediction_result.get("failure_probability", 0.0),
                verdict=prediction_result.get("verdict", "UNKNOWN"),
                shap_drivers=prediction_result.get("shap_drivers", {}),
                graph_status=GraphSyncStatus.SYNCHRONIZED,
                graph_files_changed={
                    "added": graph_sync_result.get("files_added", 0),
                    "modified": graph_sync_result.get("files_modified", 0),
                    "deleted": graph_sync_result.get("files_deleted", 0),
                    "renamed": graph_sync_result.get("files_renamed", 0),
                },
                suspicious_files=suspicious_files,
                processing_time_ms=elapsed_ms,
                features=prediction_result.get("features"),
                commit_source=prediction_result.get("commit_source", "Unknown"),
                is_local_commit=prediction_result.get("is_local_commit", False),
            )
            
            # Mark final checkpoint as COMPLETE only after everything succeeds
            self.checkpoint_manager.save(
                repo_id,
                target_sha,
                CheckpointState.COMPLETE,
                prediction_result=prediction_result,
                graph_files_changed={
                    "added": graph_sync_result.get("files_added", 0),
                    "modified": graph_sync_result.get("files_modified", 0),
                    "deleted": graph_sync_result.get("files_deleted", 0),
                    "renamed": graph_sync_result.get("files_renamed", 0),
                },
                graph_sync_result=graph_sync_result,
                suspicious_files=suspicious_files,
                processing_time_ms=elapsed_ms,
            )
            
            logger.info(f"Processing complete in {elapsed_ms:.0f}ms")
            if graph_adapter:
                graph_adapter.close()
            return result
        
        except PredictionException as e:
            logger.error(f"Prediction failed: {e}")
            self.checkpoint_manager.save(
                repo_id,
                target_sha,
                CheckpointState.FAILED,
                error=str(e),
            )
            if graph_adapter:
                graph_adapter.close()
            raise
        
        except InvalidCommitException as e:
            logger.error(f"Invalid commit: {e}")
            self.checkpoint_manager.save(
                repo_id,
                target_sha,
                CheckpointState.FAILED,
                error=str(e),
            )
            if graph_adapter:
                graph_adapter.close()
            raise
        
        except GraphSyncException as e:
            logger.error(f"Graph sync failed: {e}")
            
            # Check if we can retry (reuse prediction, just retry graph sync)
            retry_count = self.checkpoint_manager.get_retry_count(repo_id, target_sha)
            if retry_count < self.max_retries:
                logger.warning(f"Retrying graph sync (attempt {retry_count + 1}/{self.max_retries})")
                self.checkpoint_manager.increment_retry_count(repo_id, target_sha)
                time.sleep(self.retry_backoff_seconds ** retry_count)
                if graph_adapter:
                    graph_adapter.close()
                # Recurse for retry (will reuse cached prediction)
                retry_path = effective_repo_path if 'effective_repo_path' in locals() and effective_repo_path else repo_path
                return self.process_commit(repo_id, target_sha, retry_path, base_sha)
            else:
                logger.error(f"Graph sync failed after {self.max_retries} retries")
                self.checkpoint_manager.save(
                    repo_id,
                    target_sha,
                    CheckpointState.FAILED,
                    error=str(e),
                    retry_count=retry_count,
                )
                if graph_adapter:
                    graph_adapter.close()
                raise
    
    @staticmethod
    def _commit_exists_in_path(commit_sha: str, path: str) -> bool:
        """Check if commit exists in a git repository directory."""
        if not path or not os.path.isdir(path):
            return False
        try:
            res = subprocess.run(
                f'git cat-file -e "{commit_sha}"',
                cwd=path,
                capture_output=True,
                shell=True,
            )
            return res.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _path_matches_repo(repo_id: str, path: str) -> bool:
        """Check if path matches the repo_id (owner/repo)."""
        if not path or not os.path.isdir(path):
            return False
        parts = [p for p in repo_id.strip().split("/") if p]
        if len(parts) == 2:
            safe_id = f"{parts[0]}__{parts[1]}"
            dir_name = Path(path).name
            if dir_name.lower() in [safe_id.lower(), parts[1].lower()]:
                return True
        return False

    def _resolve_repo_path_for_repo(
        self,
        repo_id: str,
        target_sha: str,
        candidate_repo_path: Optional[str] = None,
        prediction_repo_path: Optional[str] = None,
    ) -> str:
        """
        Resolve authoritative repository path matching repo_id and target_sha.
        
        Priority order:
        1. Validated path returned from MetadataAdapter (prediction_repo_path) if it contains target_sha.
        2. candidate_repo_path if it belongs to repo_id AND contains target_sha.
        3. Standard Metadata-Pipeline cache directory (.repo_cache/{owner}__{repo}) if it contains target_sha.
        4. Valid directory from prediction_repo_path.
        5. candidate_repo_path if it matches repo_id.
        6. Default to standard repo_cache directory for repo_id.
        """
        # 1. Validated prediction_repo_path with commit check
        if prediction_repo_path and os.path.isdir(prediction_repo_path):
            if self._commit_exists_in_path(target_sha, prediction_repo_path):
                return prediction_repo_path

        # 2. Check candidate_repo_path if it matches repo_id AND contains target_sha
        if candidate_repo_path and os.path.isdir(candidate_repo_path):
            if self._path_matches_repo(repo_id, candidate_repo_path) and self._commit_exists_in_path(target_sha, candidate_repo_path):
                return candidate_repo_path

        # 3. Check standard Metadata-Pipeline .repo_cache for repo_id
        safe_repo_id = repo_id.strip().replace("/", "__")
        repo_cache_dir = Path(__file__).resolve().parents[2] / "Metadata-Pipeline-main" / ".repo_cache" / safe_repo_id
        if repo_cache_dir.exists() and (repo_cache_dir / ".git").exists():
            if self._commit_exists_in_path(target_sha, str(repo_cache_dir)):
                return str(repo_cache_dir)

        # 4. If prediction_repo_path is a directory, use it
        if prediction_repo_path and os.path.isdir(prediction_repo_path):
            return prediction_repo_path

        # 5. If candidate matches repo_id, use it
        if candidate_repo_path and self._path_matches_repo(repo_id, candidate_repo_path):
            return candidate_repo_path

        # 6. Default to repo_cache directory
        return str(repo_cache_dir)

    def _get_parent_commit(self, target_sha: str, repo_path: str) -> str:
        """Get the parent commit SHA."""
        import subprocess
        try:
            result = subprocess.run(
                f'git rev-parse "{target_sha}~1"',
                cwd=repo_path,
                capture_output=True,
                text=True,
                shell=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                # Root commit, use empty tree
                empty_tree = subprocess.run(
                    'git hash-object -t tree /dev/null',
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    shell=True,
                )
                if empty_tree.returncode == 0:
                    return empty_tree.stdout.strip()
        except Exception as e:
            logger.warning(f"Failed to get parent commit: {e}, using target SHA")
        
        return target_sha
    
    def _is_ancestor(self, potential_ancestor_sha: str, target_sha: str, repo_path: str) -> bool:
        """
        Check if potential_ancestor_sha is an ancestor of target_sha.
        
        Uses `git merge-base --is-ancestor` for reliable ancestry checking.
        
        Args:
            potential_ancestor_sha: SHA to check as potential ancestor
            target_sha: SHA to check against
            repo_path: Path to repository
        
        Returns:
            True if potential_ancestor_sha is an ancestor of target_sha, False otherwise
        """
        import subprocess
        try:
            result = subprocess.run(
                f'git merge-base --is-ancestor "{potential_ancestor_sha}" "{target_sha}"',
                cwd=repo_path,
                capture_output=True,
                shell=True,
            )
            # Exit code 0 means ancestor, 1 means not ancestor, other values are errors
            return result.returncode == 0
        except Exception as e:
            logger.warning(f"Failed to check ancestry for {potential_ancestor_sha[:7]} in {target_sha[:7]}: {e}")
            return False
    
    def _get_changed_files_from_git(self, repo_path: str, base_sha: Optional[str], target_sha: str) -> List[str]:
        """Get list of changed file paths between base_sha and target_sha using git."""
        try:
            cmd = ["git", "diff", "--name-only"]
            if base_sha:
                cmd.extend([base_sha, target_sha])
            else:
                cmd.append(f"{target_sha}~1..{target_sha}")
            res = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
            return [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
        except Exception as e:
            logger.warning(f"Failed to get changed files via git: {e}")
            return []

    def _result_from_checkpoint(
        self,
        repo_id: str,
        target_sha: str,
        checkpoint: Dict,
        repo_path: Optional[str] = None,
        start_time: Optional[float] = None,
    ) -> CommitPredictionResult:
        """Reconstruct result from cached checkpoint, lazily investigating if missing."""
        pred = checkpoint.get("prediction_result", {})
        failure_prob = pred.get("failure_probability", 0.0)
        
        # Check cached suspicious files
        suspicious_files = checkpoint.get("suspicious_files")
        
        # If missing from legacy checkpoint, re-query lazily if risk >= threshold
        if (suspicious_files is None or len(suspicious_files) == 0) and failure_prob >= self.investigation_threshold and repo_path:
            try:
                logger.info(f"Re-querying suspicious files for cached commit {target_sha[:7]}")
                graph_adapter = GraphAdapter(repo_id, repo_path)
                base_sha = self._get_parent_commit(target_sha, repo_path)
                changed_files = []
                if hasattr(graph_adapter, "_diff_agent") and graph_adapter._diff_agent:
                    diff_res = graph_adapter._diff_agent.compute_diff(base_sha, target_sha)
                    changed_files = diff_res.get("changed_files", [])
                if not changed_files:
                    changed_files = self._get_changed_files_from_git(repo_path, base_sha, target_sha)
                
                suspicious_files = graph_adapter.get_connected_files(changed_files, base_sha=base_sha, target_sha=target_sha)
                graph_adapter.close()
                logger.info(f"Lazy re-query found {len(suspicious_files)} suspicious files")
                
                # Persist back to checkpoint so subsequent reads are instant
                self.checkpoint_manager.save(
                    repo_id,
                    target_sha,
                    CheckpointState.COMPLETE,
                    prediction_result=pred,
                    graph_files_changed=checkpoint.get("graph_files_changed"),
                    graph_sync_result=checkpoint.get("graph_sync_result"),
                    suspicious_files=suspicious_files,
                )
            except Exception as e:
                logger.warning(f"Failed to re-query suspicious files for cached commit: {e}")
                suspicious_files = None
        
        # Reconstruct SuspiciousFile dataclass instances if needed
        if suspicious_files:
            reconstructed_susp = []
            for sf in suspicious_files:
                if isinstance(sf, dict):
                    reconstructed_susp.append(SuspiciousFile(
                        file_path=sf.get("file_path", sf.get("path", "")),
                        centrality_score=float(sf.get("centrality_score", sf.get("score", 0.0))),
                        reasons=sf.get("reasons", sf.get("all_reasons", []))
                    ))
                elif isinstance(sf, SuspiciousFile):
                    reconstructed_susp.append(sf)
            suspicious_files = reconstructed_susp

        # Processing time
        proc_time = checkpoint.get("processing_time_ms")
        if proc_time is None or proc_time <= 0:
            if start_time is not None:
                proc_time = (time.perf_counter() - start_time) * 1000
            else:
                proc_time = 0.0
        
        return CommitPredictionResult(
            repository_identity=repo_id,
            target_sha=target_sha,
            failure_probability=failure_prob,
            verdict=pred.get("verdict", "UNKNOWN"),
            shap_drivers=pred.get("shap_drivers", {}),
            graph_status=GraphSyncStatus.SYNCHRONIZED,
            graph_files_changed=checkpoint.get("graph_files_changed"),
            suspicious_files=suspicious_files,
            processing_time_ms=proc_time,
            features=pred.get("features"),
            commit_source=pred.get("commit_source", "Unknown"),
            is_local_commit=pred.get("is_local_commit", False),
        )
