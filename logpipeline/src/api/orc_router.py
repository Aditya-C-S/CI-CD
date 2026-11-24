"""src/api/orc_router.py

FastAPI router for unified ORC (Orchestrator) integration.
Exposes commit analysis endpoint that combines:
  - Failure probability prediction (via Metadata Pipeline)
  - Graph synchronization (via Neo4j)
  - Suspicious file investigation (via graph centrality)
  - SHAP-based explainability
"""

import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

logger = logging.getLogger("orc_router")

router = APIRouter(prefix="/api/orc", tags=["orc"])


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------

class AnalyzeCommitRequest(BaseModel):
    """Request to analyze a commit for CI/CD failure risk."""
    repo_id: str = Field(..., description="Repository identity (owner/repo)")
    target_sha: str = Field(..., description="Target commit SHA to analyze")
    repo_path: str = Field(..., description="Local path to repository")
    base_sha: Optional[str] = Field(
        default=None,
        description="Base commit for comparison (if None, uses target_sha~1)"
    )


class SuspiciousFileResponse(BaseModel):
    """A suspicious file identified in root cause analysis."""
    file_path: str
    centrality_score: float  # [0.0, 1.0]
    reasons: list[str]


class SHAPDriversResponse(BaseModel):
    """SHAP-based feature importance drivers."""
    positive: list[list[Any]]  # [[feature_name, value], ...]
    negative: list[list[Any]]  # [[feature_name, value], ...]


class CommitAnalysisResponse(BaseModel):
    """Unified response from ORC commit analysis."""
    
    # Identity
    repository_identity: str
    target_sha: str
    
    # Prediction results
    failure_probability: float  # [0.0, 1.0]
    verdict: str  # "FAST-TRACK", "STANDARD GATE", "ALERT", "PRE-MERGE BLOCK"
    shap_drivers: SHAPDriversResponse
    
    # Graph synchronization
    graph_status: str  # "SYNCHRONIZED", "SYNC_FAILED", "SKIPPED"
    graph_files_changed: Optional[Dict[str, int]] = None  # {"added": int, "modified": int, "deleted": int}
    
    # Root cause analysis
    suspicious_files: Optional[list[SuspiciousFileResponse]] = None
    
    # Metadata
    timestamp: str
    processing_time_ms: float
    
    # Features (for debugging / model transparency)
    features: Optional[Dict[str, Any]] = None
    
    # Commit provenance
    commit_source: Optional[str] = None
    is_local_commit: Optional[bool] = None


# ---------------------------------------------------------------------------
# Orchestrator Initialization
# ---------------------------------------------------------------------------

_orchestrator = None


def _get_orchestrator():
    """Lazy load ORC Orchestrator with proper path setup."""
    global _orchestrator
    
    if _orchestrator is not None:
        return _orchestrator
    
    try:
        import os
        import types
        from dotenv import load_dotenv

        # Resolve project roots
        base_dir = Path(__file__).resolve().parent.parent.parent.parent
        orc_src = base_dir / "orc" / "src"
        meta_pipeline = base_dir / "Metadata-Pipeline-main"
        graph_gen = base_dir / "graph-doc-gen-main"
        
        # Inject sibling repositories into sys.path
        if str(meta_pipeline) not in sys.path and meta_pipeline.exists():
            sys.path.insert(0, str(meta_pipeline))
        if str(graph_gen) not in sys.path and graph_gen.exists():
            sys.path.insert(0, str(graph_gen))
        
        # Register orc_core as a package in sys.modules so intra-package relative imports resolve
        if "orc_core" not in sys.modules:
            pkg = types.ModuleType("orc_core")
            pkg.__path__ = [str(orc_src)]
            pkg.__file__ = str(orc_src / "__init__.py")
            pkg.__package__ = "orc_core"
            sys.modules["orc_core"] = pkg
        
        from orc_core.orchestrator import Orchestrator
        from orc_core.models import CommitPredictionResult
        
        # Load environment variables from orc/.env if available
        orc_env = base_dir / "orc" / ".env"
        if orc_env.exists():
            load_dotenv(orc_env)
        
        github_token = os.getenv("GITHUB_TOKEN", "")
        if not github_token:
            logger.warning("GITHUB_TOKEN not set; ORC will have limited functionality")
        
        investigation_threshold = float(os.getenv("INVESTIGATION_THRESHOLD", os.getenv("ORC_INVESTIGATION_THRESHOLD", "0.50")))
        
        _orchestrator = Orchestrator(
            github_token=github_token,
            investigation_threshold=investigation_threshold,
            max_retries=3,
            retry_backoff_seconds=2.0,
        )
        
        logger.info("ORC Orchestrator initialized successfully")
        return _orchestrator
    
    except ImportError as e:
        logger.error(f"Failed to import ORC: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"ORC integration not available: {e}"
        )
    except Exception as e:
        logger.error(f"Failed to initialize ORC: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize ORC: {e}"
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/analyze-commit",
    response_model=CommitAnalysisResponse,
    summary="Analyze a commit for CI/CD failure risk",
    description="Unified endpoint combining prediction, graph sync, and RCA",
)
def analyze_commit(req: AnalyzeCommitRequest) -> Dict[str, Any]:
    """
    Analyze a commit for CI/CD failure risk using the ORC orchestrator.
    
    - Predicts failure probability via Metadata Pipeline model
    - Synchronizes and analyzes repository dependency graph
    - Investigates suspicious files based on graph centrality
    - Returns SHAP-based feature importance
    
    Args:
        req: AnalyzeCommitRequest with repo_id, target_sha, repo_path, base_sha
    
    Returns:
        CommitAnalysisResponse with prediction, graph, and RCA results
    
    Raises:
        HTTPException: If processing fails
    """
    try:
        orchestrator = _get_orchestrator()
        
        logger.info(
            f"Analyzing {req.repo_id}@{req.target_sha[:7]} "
            f"(base_sha={req.base_sha[:7] if req.base_sha else 'auto'})"
        )
        
        # Call ORC process_commit
        result = orchestrator.process_commit(
            repo_id=req.repo_id,
            target_sha=req.target_sha,
            repo_path=req.repo_path,
            base_sha=req.base_sha,
        )
        
        # Convert result to dictionary
        result_dict = result.to_dict()
        
        # Convert suspicious_files to response format
        suspicious_files = None
        if result_dict.get("suspicious_files"):
            suspicious_files = [
                {
                    "file_path": sf["file_path"],
                    "centrality_score": sf["centrality_score"],
                    "reasons": sf["reasons"],
                }
                for sf in result_dict["suspicious_files"]
            ]
        
        # Build response
        response = {
            "repository_identity": result_dict["repository_identity"],
            "target_sha": result_dict["target_sha"],
            "failure_probability": result_dict["failure_probability"],
            "verdict": result_dict["verdict"],
            "shap_drivers": result_dict["shap_drivers"],
            "graph_status": result_dict["graph_status"],
            "graph_files_changed": result_dict.get("graph_files_changed"),
            "suspicious_files": suspicious_files,
            "timestamp": result_dict["timestamp"],
            "processing_time_ms": result_dict["processing_time_ms"],
            "features": result_dict.get("features"),
            "commit_source": result_dict.get("commit_source", "Unknown"),
            "is_local_commit": result_dict.get("is_local_commit", False),
        }
        
        logger.info(
            f"Analysis complete: {req.repo_id}@{req.target_sha[:7]} "
            f"→ {result_dict['verdict']} ({result_dict['failure_probability']:.2%} risk)"
        )
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Commit analysis failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Commit analysis failed: {str(e)}"
        )


@router.post(
    "/analyze-commit-async",
    response_model=Dict[str, str],
    summary="Analyze a commit asynchronously",
    description="Queue analysis in background; returns task_id for polling",
)
def analyze_commit_async(
    req: AnalyzeCommitRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, str]:
    """
    Queue a commit analysis to run in the background.
    
    Returns a task_id that can be used to poll for results via GET /api/orc/task/{task_id}
    
    Args:
        req: AnalyzeCommitRequest
        background_tasks: FastAPI background tasks
    
    Returns:
        {"task_id": str, "status": "queued"}
    """
    import uuid
    
    task_id = str(uuid.uuid4())
    
    def run_analysis():
        """Run analysis and store result."""
        try:
            orchestrator = _get_orchestrator()
            result = orchestrator.process_commit(
                repo_id=req.repo_id,
                target_sha=req.target_sha,
                repo_path=req.repo_path,
                base_sha=req.base_sha,
            )
            logger.info(f"Background task {task_id} completed")
            # TODO: Store result in cache/database for retrieval
        except Exception as e:
            logger.error(f"Background task {task_id} failed: {e}")
    
    background_tasks.add_task(run_analysis)
    
    return {
        "task_id": task_id,
        "status": "queued",
    }


@router.get(
    "/health",
    response_model=Dict[str, str],
    summary="Check ORC integration health",
)
def orc_health() -> Dict[str, str]:
    """
    Check if ORC integration is available and healthy.
    
    Returns:
        {"status": "healthy" | "unhealthy", "message": str}
    """
    try:
        orchestrator = _get_orchestrator()
        return {
            "status": "healthy",
            "message": "ORC Orchestrator is available",
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "message": f"ORC unavailable: {str(e)}",
        }
