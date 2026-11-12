#!/usr/bin/env python3
"""
CI with Log Forwarding Wrapper

Executes 5 sequential validation commands within a single Log Pipeline run:
1. apt-get update (system package cache refresh)
2. apt-get install (system dependencies: portaudio19-dev, python3-tk)
3. pip install (Python packages: SpeechRecognition, PyAudio)
4. Import validation (validate tkinter, speech_recognition imports)
5. Syntax validation (py_compile on 5 application Python files)

All commands execute in one Log Pipeline run. Individual command exit codes and
overall CI outcome are preserved. Failure of any command stops subsequent execution
but all logs are forwarded and finalization is guaranteed.

Environment Variables (from GitHub Actions):
    LOG_PIPELINE_API_URL: Base URL of Log Pipeline API
    LOG_PIPELINE_API_KEY: API authentication key
    LOG_PIPELINE_REPO_ID: Repository identifier in Log Pipeline
    GITHUB_SHA: Commit SHA (from github.sha)
    GITHUB_RUN_ID: Workflow run ID (from github.run_id)
    GITHUB_RUN_ATTEMPT: Attempt number for retries (from github.run_attempt, default: 1)
    GITHUB_REF_NAME: Branch name (from github.ref_name)
    GITHUB_JOB: Job name (from github.job)
    GITHUB_EVENT_NAME: Trigger type (from github.event_name)
    GITHUB_REPOSITORY: Repository path (from github.repository)
"""

import os
import sys
import logging

# Configure logging before any imports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for CI validation with log forwarding."""
    
    # Parse environment variables
    api_url = os.getenv("LOG_PIPELINE_API_URL")
    api_key = os.getenv("LOG_PIPELINE_API_KEY")
    repo_id = os.getenv("LOG_PIPELINE_REPO_ID")
    commit_sha = os.getenv("GITHUB_SHA", "unknown")
    run_id = os.getenv("GITHUB_RUN_ID", "0")
    run_attempt = os.getenv("GITHUB_RUN_ATTEMPT", "1")
    branch = os.getenv("GITHUB_REF_NAME", "main")
    job_name = os.getenv("GITHUB_JOB", "validate")
    event_name = os.getenv("GITHUB_EVENT_NAME", "unknown")
    repository = os.getenv("GITHUB_REPOSITORY", "unknown/repo")
    
    # Validate required environment variables
    if not api_url:
        logger.error("LOG_PIPELINE_API_URL environment variable is required")
        return 1
    
    if not api_key:
        logger.error("LOG_PIPELINE_API_KEY environment variable is required")
        return 1
    
    if not repo_id:
        logger.error("LOG_PIPELINE_REPO_ID environment variable is required")
        return 1
    
    # Determine if this is a pull request
    is_pr = event_name == "pull_request"
    
    # Construct distinct CI run ID (includes attempt for retry handling)
    ci_run_id = f"gh_{run_id}_attempt_{run_attempt}"
    
    logger.info(f"Starting CI with Log Forwarding")
    logger.info(f"  Repository: {repository}")
    logger.info(f"  Commit SHA: {commit_sha[:8]}...")
    logger.info(f"  Branch: {branch}")
    logger.info(f"  CI Run ID: {ci_run_id}")
    logger.info(f"  Log Pipeline API: {api_url}")
    
    # Import run_with_forwarding from logpipeline
    try:
        from integration.github_actions.log_forwarder import run_with_forwarding
        logger.info("✓ Imported run_with_forwarding from logpipeline")
    except ImportError as e:
        logger.error(f"Failed to import run_with_forwarding: {e}")
        logger.error("Ensure logpipeline/src is in PYTHONPATH")
        return 1
    
    # Define validation commands (5 sequential steps)
    # Each command will be executed in order; failure of any command stops subsequent execution
    commands = [
        {
            "cmd": "apt-get update",
            "step_name": "Update Package Cache",
            "stage": "setup",
        },
        {
            "cmd": "apt-get install -y portaudio19-dev python3-tk",
            "step_name": "Install System Dependencies",
            "stage": "setup",
        },
        {
            "cmd": "pip install --upgrade pip && pip install SpeechRecognition PyAudio",
            "step_name": "Install Python Packages",
            "stage": "setup",
        },
        {
            "cmd": "python -c \"import tkinter; import speech_recognition; print('✓ Imports validated')\"",
            "step_name": "Validate Imports",
            "stage": "validation",
        },
        {
            "cmd": "py_compile Tic-Tac-Toe.py example.py ga.py kas.py check_sound.py",
            "step_name": "Validate Syntax",
            "stage": "validation",
        },
    ]
    
    logger.info(f"Executing {len(commands)} validation commands in single Log Pipeline run...")
    
    # Execute all commands within single Log Pipeline run
    try:
        exit_code = run_with_forwarding(
            api_url=api_url,
            api_key=api_key,
            repo_id=repo_id,
            commit_sha=commit_sha,
            ci_run_id=ci_run_id,
            branch=branch,
            is_pr=is_pr,
            job_name=job_name,
            commands=commands,
            strict_mode=True,  # Fail if Log Pipeline API fails; do not mask command failures
        )
        
        logger.info(f"CI validation completed with exit code: {exit_code}")
        
        if exit_code == 0:
            logger.info("✓ All validation checks passed")
        else:
            logger.warning(f"✗ Validation failed with exit code {exit_code}")
        
        return exit_code
    
    except RuntimeError as e:
        logger.error(f"Log Pipeline error (strict mode): {e}")
        logger.error("CI marked as failed due to log forwarding failure")
        return 1
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.error("CI marked as failed due to unexpected error")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
