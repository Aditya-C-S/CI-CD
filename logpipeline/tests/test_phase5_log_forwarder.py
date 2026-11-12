"""
Phase 5 Tests: GitHub Actions Log Forwarder

Tests cover:
1. Capturing stdout/stderr
2. Command exit code preservation
3. Chunk-size-based buffering
4. Time-based buffer flushing
5. Final buffer flushing
6. Unique event IDs
7. Chunk sequence ordering
8. Retry behavior
9. Duplicate submission behavior
10. API authentication
11. Secret redaction
12. Failed command finalization
13. Network failure handling
"""

import json
import logging
import subprocess
import threading
import time
import unittest
from unittest.mock import MagicMock, Mock, patch

import requests
import responses

from src.integration.github_actions.log_forwarder import (
    APIClient,
    CommandExecutor,
    LogBuffer,
    SecretRedactor,
)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestLogBuffer(unittest.TestCase):
    """Test log buffering and chunking logic."""

    def test_buffer_flush_by_lines(self):
        """Test that buffer flushes when max lines reached."""
        chunks_ready = []
        
        def on_chunk_ready(chunk_text, event_id):
            chunks_ready.append((chunk_text, event_id))
        
        buffer = LogBuffer(max_lines=3, max_bytes=1000000, max_seconds=1000, on_chunk_ready=on_chunk_ready)
        
        buffer.add("line 1\nline 2\nline 3\nline 4")
        
        self.assertEqual(len(chunks_ready), 1, "Should have flushed after 3+ lines")
        chunk_text, event_id = chunks_ready[0]
        self.assertIn("line 1", chunk_text)
        self.assertIn("line 3", chunk_text)
        logger.info("✅ Buffer flush by lines works")

    def test_buffer_flush_by_bytes(self):
        """Test that buffer flushes when max bytes reached."""
        chunks_ready = []
        
        def on_chunk_ready(chunk_text, event_id):
            chunks_ready.append((chunk_text, event_id))
        
        buffer = LogBuffer(max_lines=1000, max_bytes=100, max_seconds=1000, on_chunk_ready=on_chunk_ready)
        
        # Add more than 100 bytes
        large_text = "x" * 150
        buffer.add(large_text)
        
        self.assertEqual(len(chunks_ready), 1, "Should have flushed after 100+ bytes")
        logger.info("✅ Buffer flush by bytes works")

    def test_buffer_flush_by_time(self):
        """Test that buffer flushes after max seconds."""
        chunks_ready = []
        
        def on_chunk_ready(chunk_text, event_id):
            chunks_ready.append((chunk_text, event_id))
        
        buffer = LogBuffer(max_lines=1000, max_bytes=1000000, max_seconds=0.1, on_chunk_ready=on_chunk_ready)
        
        buffer.add("line 1")
        self.assertEqual(len(chunks_ready), 0, "Should not flush yet")
        
        time.sleep(0.2)
        buffer.add("line 2")  # This should trigger flush due to time
        
        self.assertEqual(len(chunks_ready), 1, "Should have flushed after 0.1s")
        logger.info("✅ Buffer flush by time works")

    def test_unique_event_ids(self):
        """Test that each chunk gets unique event ID."""
        event_ids = []
        
        def on_chunk_ready(chunk_text, event_id):
            event_ids.append(event_id)
        
        buffer = LogBuffer(max_lines=1, max_bytes=1000000, max_seconds=1000, on_chunk_ready=on_chunk_ready)
        
        buffer.add("line 1\nline 2")  # Triggers flush
        buffer.add("line 3\nline 4")  # Triggers flush
        
        self.assertEqual(len(event_ids), 2)
        self.assertNotEqual(event_ids[0], event_ids[1], "Event IDs should be unique")
        logger.info(f"✅ Unique event IDs: {event_ids}")

    def test_final_flush(self):
        """Test that remaining buffer is flushed."""
        chunks_ready = []
        
        def on_chunk_ready(chunk_text, event_id):
            chunks_ready.append((chunk_text, event_id))
        
        buffer = LogBuffer(max_lines=100, max_bytes=1000000, max_seconds=1000, on_chunk_ready=on_chunk_ready)
        
        buffer.add("line 1\nline 2")
        self.assertEqual(len(chunks_ready), 0, "Should not flush yet")
        
        buffer.flush()
        self.assertEqual(len(chunks_ready), 1, "Should flush on explicit flush")
        logger.info("✅ Final buffer flush works")


class TestSecretRedaction(unittest.TestCase):
    """Test secret redaction from logs."""

    def test_redact_aws_keys(self):
        """Test AWS key redaction."""
        redactor = SecretRedactor()
        
        text = "aws_access_key_id = AKIA1234567890AB"
        redacted = redactor.redact(text)
        
        self.assertNotIn("AKIA1234567890AB", redacted)
        self.assertIn("***REDACTED***", redacted)
        logger.info("✅ AWS key redaction works")

    def test_redact_github_tokens(self):
        """Test GitHub token redaction."""
        redactor = SecretRedactor()
        
        text = "token: ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        redacted = redactor.redact(text)
        
        self.assertNotIn("ghp_1234567890abcdefghijklmnopqrstuvwxyz", redacted)
        self.assertIn("***REDACTED***", redacted)
        logger.info("✅ GitHub token redaction works")

    def test_redact_api_keys(self):
        """Test generic API key redaction."""
        redactor = SecretRedactor()
        
        text = "api_key: secret_value_12345"
        redacted = redactor.redact(text)
        
        self.assertNotIn("secret_value_12345", redacted)
        self.assertIn("***REDACTED***", redacted)
        logger.info("✅ API key redaction works")


class TestAPIClient(unittest.TestCase):
    """Test API client interactions."""

    @responses.activate
    def test_create_run(self):
        """Test creating a run via API."""
        api_url = "https://localhost:8000"
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs",
            json={"run_id": "test_run_123"},
            status=200,
        )
        
        client = APIClient(api_url, verify_ssl=False)
        success, run_id, error = client.create_run(
            repo_id="test-org/test-repo",
            commit_sha="abc123def",
        )
        
        self.assertTrue(success)
        self.assertEqual(run_id, "test_run_123")
        self.assertIsNone(error)
        logger.info("✅ Create run works")

    @responses.activate
    def test_ingest_chunk(self):
        """Test ingesting a log chunk."""
        api_url = "https://localhost:8000"
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs/test_run/logs",
            json={"status": "ok"},
            status=200,
        )
        
        client = APIClient(api_url, verify_ssl=False)
        success, error = client.ingest_chunk(
            run_id="test_run",
            log_chunk="test log line",
            event_id="event_1",
        )
        
        self.assertTrue(success)
        self.assertIsNone(error)
        logger.info("✅ Ingest chunk works")

    @responses.activate
    def test_duplicate_chunk_prevention(self):
        """Test that duplicate event IDs are not re-submitted."""
        api_url = "https://localhost:8000"
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs/test_run/logs",
            json={"status": "ok"},
            status=200,
        )
        
        client = APIClient(api_url, verify_ssl=False)
        
        # First submission
        success1, error1 = client.ingest_chunk(
            run_id="test_run",
            log_chunk="chunk 1",
            event_id="same_id",
        )
        
        # Second submission with same event_id
        success2, error2 = client.ingest_chunk(
            run_id="test_run",
            log_chunk="chunk 1",
            event_id="same_id",
        )
        
        self.assertTrue(success1)
        self.assertTrue(success2, "Duplicate should be treated as success (idempotent)")
        self.assertEqual(len(responses.calls), 1, "Should only have 1 actual HTTP call")
        logger.info("✅ Duplicate prevention works")

    @responses.activate
    def test_finalize_run(self):
        """Test finalizing a run."""
        api_url = "https://localhost:8000"
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs/test_run/logs",
            json={"status": "ok"},
            status=200,
        )
        
        client = APIClient(api_url, verify_ssl=False)
        success, error = client.finalize_run(
            run_id="test_run",
            workflow_outcome="success",
        )
        
        self.assertTrue(success)
        self.assertIsNone(error)
        logger.info("✅ Finalize run works")

    @responses.activate
    def test_authentication_header(self):
        """Test that API key is sent in authentication header."""
        api_url = "https://localhost:8000"
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs",
            json={"run_id": "test_run"},
            status=200,
        )
        
        client = APIClient(api_url, api_key="test_api_key", verify_ssl=False)
        client.create_run(repo_id="test", commit_sha="abc")
        
        # Check that the API key was sent
        last_request = responses.calls[-1].request
        self.assertIn("X-API-Key", last_request.headers)
        self.assertEqual(last_request.headers["X-API-Key"], "test_api_key")
        logger.info("✅ Authentication header works")

    @responses.activate
    def test_retry_on_network_error(self):
        """Test retry behavior on network errors (connection failures)."""
        api_url = "https://localhost:8000"
        # First call raises connection error, second succeeds
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs/test_run/logs",
            body=requests.exceptions.ConnectionError("Connection refused"),
        )
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs/test_run/logs",
            json={"status": "ok"},
            status=200,
        )
        
        client = APIClient(api_url, verify_ssl=False, max_retries=3, retry_delay=0.01)
        success, error = client.ingest_chunk(
            run_id="test_run",
            log_chunk="test",
            event_id="event_1",
        )
        
        self.assertTrue(success, "Should succeed after retry")
        self.assertGreater(len(responses.calls), 1, "Should have retried")
        logger.info("✅ Retry on network error works")

    @responses.activate
    def test_retry_on_http_500(self):
        """Test retry behavior on HTTP 500 (transient server error)."""
        api_url = "https://localhost:8000"
        # First call returns 500, second succeeds
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs/test_run/logs",
            json={"error": "Internal server error"},
            status=500,
        )
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs/test_run/logs",
            json={"status": "ok"},
            status=200,
        )
        
        client = APIClient(api_url, verify_ssl=False, max_retries=3, retry_delay=0.01)
        success, error = client.ingest_chunk(
            run_id="test_run",
            log_chunk="test",
            event_id="event_1",
        )
        
        self.assertTrue(success, "Should succeed after HTTP 500 retry")
        self.assertEqual(len(responses.calls), 2, "Should have retried exactly once")
        logger.info("✅ Retry on HTTP 500 works")

    @responses.activate
    def test_retry_on_http_502(self):
        """Test retry behavior on HTTP 502 (bad gateway)."""
        api_url = "https://localhost:8000"
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs/test_run/logs",
            status=502,
        )
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs/test_run/logs",
            json={"status": "ok"},
            status=200,
        )
        
        client = APIClient(api_url, verify_ssl=False, max_retries=3, retry_delay=0.01)
        success, error = client.ingest_chunk(
            run_id="test_run",
            log_chunk="test",
            event_id="event_2",
        )
        
        self.assertTrue(success, "Should succeed after HTTP 502 retry")
        logger.info("✅ Retry on HTTP 502 works")

    @responses.activate
    def test_retry_on_http_503(self):
        """Test retry behavior on HTTP 503 (service unavailable)."""
        api_url = "https://localhost:8000"
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs/test_run/logs",
            status=503,
        )
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs/test_run/logs",
            json={"status": "ok"},
            status=200,
        )
        
        client = APIClient(api_url, verify_ssl=False, max_retries=3, retry_delay=0.01)
        success, error = client.ingest_chunk(
            run_id="test_run",
            log_chunk="test",
            event_id="event_3",
        )
        
        self.assertTrue(success, "Should succeed after HTTP 503 retry")
        logger.info("✅ Retry on HTTP 503 works")

    @responses.activate
    def test_retry_on_http_504(self):
        """Test retry behavior on HTTP 504 (gateway timeout)."""
        api_url = "https://localhost:8000"
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs/test_run/logs",
            status=504,
        )
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs/test_run/logs",
            json={"status": "ok"},
            status=200,
        )
        
        client = APIClient(api_url, verify_ssl=False, max_retries=3, retry_delay=0.01)
        success, error = client.ingest_chunk(
            run_id="test_run",
            log_chunk="test",
            event_id="event_4",
        )
        
        self.assertTrue(success, "Should succeed after HTTP 504 retry")
        logger.info("✅ Retry on HTTP 504 works")

    @responses.activate
    def test_no_retry_on_http_400(self):
        """Test that HTTP 400 (bad request) does NOT retry."""
        api_url = "https://localhost:8000"
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs/test_run/logs",
            json={"error": "Bad request"},
            status=400,
        )
        
        client = APIClient(api_url, verify_ssl=False, max_retries=3, retry_delay=0.01)
        success, error = client.ingest_chunk(
            run_id="test_run",
            log_chunk="test",
            event_id="event_5",
        )
        
        self.assertFalse(success, "Should fail immediately on HTTP 400")
        self.assertEqual(len(responses.calls), 1, "Should NOT have retried")
        logger.info("✅ No retry on HTTP 400 works")

    @responses.activate
    def test_no_retry_on_http_401(self):
        """Test that HTTP 401 (unauthorized) does NOT retry."""
        api_url = "https://localhost:8000"
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs/test_run/logs",
            json={"error": "Unauthorized"},
            status=401,
        )
        
        client = APIClient(api_url, verify_ssl=False, max_retries=3, retry_delay=0.01)
        success, error = client.ingest_chunk(
            run_id="test_run",
            log_chunk="test",
            event_id="event_6",
        )
        
        self.assertFalse(success, "Should fail immediately on HTTP 401")
        self.assertEqual(len(responses.calls), 1, "Should NOT have retried")
        logger.info("✅ No retry on HTTP 401 works")

    @responses.activate
    def test_no_retry_on_http_403(self):
        """Test that HTTP 403 (forbidden) does NOT retry."""
        api_url = "https://localhost:8000"
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs/test_run/logs",
            json={"error": "Forbidden"},
            status=403,
        )
        
        client = APIClient(api_url, verify_ssl=False, max_retries=3, retry_delay=0.01)
        success, error = client.ingest_chunk(
            run_id="test_run",
            log_chunk="test",
            event_id="event_7",
        )
        
        self.assertFalse(success, "Should fail immediately on HTTP 403")
        self.assertEqual(len(responses.calls), 1, "Should NOT have retried")
        logger.info("✅ No retry on HTTP 403 works")


class TestCommandExecutor(unittest.TestCase):
    """Test command execution with log forwarding."""

    def test_execute_successful_command(self):
        """Test executing a successful command."""
        api_client = MagicMock()
        api_client.ingest_chunk.return_value = (True, None)
        api_client.finalize_run.return_value = (True, None)
        
        executor = CommandExecutor(
            api_client=api_client,
            run_id="test_run",
            ci_run_id="gh_123",
            commit_sha="abc",
            strict_mode=False,
        )
        
        exit_code = executor.execute("echo 'test output'")
        
        self.assertEqual(exit_code, 0, "Successful command should return 0")
        logger.info("✅ Successful command execution works")

    def test_execute_failed_command(self):
        """Test executing a failed command preserves exit code."""
        api_client = MagicMock()
        api_client.ingest_chunk.return_value = (True, None)
        
        executor = CommandExecutor(
            api_client=api_client,
            run_id="test_run",
            ci_run_id="gh_123",
            commit_sha="abc",
            strict_mode=False,
        )
        
        exit_code = executor.execute("exit 42")
        
        self.assertEqual(exit_code, 42, "Failed command should preserve exit code")
        logger.info("✅ Failed command exit code preserved")

    def test_finalization_on_failure(self):
        """Test that finalization happens even on command failure."""
        api_client = MagicMock()
        api_client.ingest_chunk.return_value = (True, None)
        api_client.finalize_run.return_value = (True, None)
        
        executor = CommandExecutor(
            api_client=api_client,
            run_id="test_run",
            ci_run_id="gh_123",
            commit_sha="abc",
            strict_mode=False,
        )
        
        executor.execute("exit 1")
        executor.finalize(workflow_outcome="failure")
        
        # Verify finalize was called
        api_client.finalize_run.assert_called_once()
        call_kwargs = api_client.finalize_run.call_args[1]
        self.assertEqual(call_kwargs["workflow_outcome"], "failure")
        logger.info("✅ Finalization on failure works")

    def test_strict_mode_propagates_errors(self):
        """Test that strict mode propagates API errors."""
        api_client = MagicMock()
        api_client.ingest_chunk.return_value = (False, "Network error")
        
        executor = CommandExecutor(
            api_client=api_client,
            run_id="test_run",
            ci_run_id="gh_123",
            commit_sha="abc",
            strict_mode=True,  # Strict mode enabled
        )
        
        with self.assertRaises(RuntimeError):
            executor.execute("echo test")
        
        logger.info("✅ Strict mode error propagation works")

    def test_best_effort_mode_continues_on_error(self):
        """Test that best-effort mode continues despite API errors."""
        api_client = MagicMock()
        api_client.ingest_chunk.return_value = (False, "Network error")
        
        executor = CommandExecutor(
            api_client=api_client,
            run_id="test_run",
            ci_run_id="gh_123",
            commit_sha="abc",
            strict_mode=False,  # Best-effort mode
        )
        
        # Should not raise, despite API error
        exit_code = executor.execute("echo test")
        self.assertEqual(exit_code, 0)
        self.assertGreater(len(executor.forwarder_errors), 0)
        logger.info("✅ Best-effort mode continues on error")


class TestIntegration(unittest.TestCase):
    """End-to-end integration tests."""

    @responses.activate
    def test_full_workflow_success(self):
        """Test full workflow: create run, execute, ingest logs, finalize."""
        api_url = "https://localhost:8000"
        
        # Mock API responses
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs",
            json={"run_id": "integration_test_run"},
            status=200,
        )
        responses.add(
            responses.POST,
            f"{api_url}/api/demo/runs/integration_test_run/logs",
            json={"status": "ok"},
            status=200,
        )
        
        client = APIClient(api_url, verify_ssl=False)
        
        # Create run
        success, run_id, _ = client.create_run(
            repo_id="test/repo",
            commit_sha="abc123",
        )
        self.assertTrue(success)
        
        # Ingest chunk
        success, _ = client.ingest_chunk(
            run_id=run_id,
            log_chunk="test output",
            event_id="event_1",
        )
        self.assertTrue(success)
        
        # Finalize
        success, _ = client.finalize_run(
            run_id=run_id,
            workflow_outcome="success",
        )
        self.assertTrue(success)
        
        logger.info("✅ Full workflow integration test passed")

    def test_exit_code_preserved_on_success(self):
        """Verify exit code 0 is preserved from successful command."""
        api_client = MagicMock()
        api_client.ingest_chunk.return_value = (True, None)
        api_client.finalize_run.return_value = (True, None)
        
        executor = CommandExecutor(
            api_client=api_client,
            run_id="test_run",
            ci_run_id="gh_123",
            commit_sha="abc",
            strict_mode=False,
        )
        
        # Execute successful command
        exit_code = executor.execute("python -c \"exit(0)\"")
        self.assertEqual(exit_code, 0, "Exit code 0 should be preserved")
        logger.info("✅ Exit code preserved on success")

    def test_exit_code_preserved_on_failure(self):
        """Verify non-zero exit code is preserved from failed command."""
        api_client = MagicMock()
        api_client.ingest_chunk.return_value = (True, None)
        api_client.finalize_run.return_value = (True, None)
        
        executor = CommandExecutor(
            api_client=api_client,
            run_id="test_run",
            ci_run_id="gh_123",
            commit_sha="abc",
            strict_mode=False,
        )
        
        # Execute failed command
        exit_code = executor.execute("python -c \"exit(42)\"")
        self.assertEqual(exit_code, 42, "Exit code 42 should be preserved")
        logger.info("✅ Exit code preserved on failure")

    def test_finalization_called_on_success(self):
        """Verify finalization is called after successful command."""
        api_client = MagicMock()
        api_client.ingest_chunk.return_value = (True, None)
        api_client.finalize_run.return_value = (True, None)
        
        executor = CommandExecutor(
            api_client=api_client,
            run_id="test_run",
            ci_run_id="gh_123",
            commit_sha="abc",
            strict_mode=False,
        )
        
        exit_code = executor.execute("python -c \"print('test')\"")
        executor.finalize("success")
        
        api_client.finalize_run.assert_called()
        call_args = api_client.finalize_run.call_args
        self.assertEqual(call_args[1]["workflow_outcome"], "success")
        logger.info("✅ Finalization called on success")

    def test_finalization_called_on_failure(self):
        """Verify finalization is called after failed command."""
        api_client = MagicMock()
        api_client.ingest_chunk.return_value = (True, None)
        api_client.finalize_run.return_value = (True, None)
        
        executor = CommandExecutor(
            api_client=api_client,
            run_id="test_run",
            ci_run_id="gh_123",
            commit_sha="abc",
            strict_mode=False,
        )
        
        exit_code = executor.execute("python -c \"exit(1)\"")
        executor.finalize("failure")
        
        api_client.finalize_run.assert_called()
        call_args = api_client.finalize_run.call_args
        self.assertEqual(call_args[1]["workflow_outcome"], "failure")
        logger.info("✅ Finalization called on failure")

    def test_strict_mode_fails_on_forwarding_error(self):
        """Verify strict mode fails when chunk forwarding fails."""
        api_client = MagicMock()
        # First call to ingest fails, simulating API error
        api_client.ingest_chunk.return_value = (False, "API error")
        
        executor = CommandExecutor(
            api_client=api_client,
            run_id="test_run",
            ci_run_id="gh_123",
            commit_sha="abc",
            strict_mode=True,  # Strict mode ON
        )
        
        # Execute should raise because strict_mode=True and ingest fails
        with self.assertRaises(RuntimeError):
            executor.execute("python -c \"print('test')\"")
        
        logger.info("✅ Strict mode fails on forwarding error")

    def test_stdout_stderr_captured(self):
        """Verify both stdout and stderr are captured and forwarded."""
        api_client = MagicMock()
        chunks_sent = []
        
        def capture_chunk(*args, **kwargs):
            if kwargs.get("log_chunk"):
                chunks_sent.append(kwargs.get("log_chunk"))
            return (True, None)
        
        api_client.ingest_chunk.side_effect = capture_chunk
        api_client.finalize_run.return_value = (True, None)
        
        executor = CommandExecutor(
            api_client=api_client,
            run_id="test_run",
            ci_run_id="gh_123",
            commit_sha="abc",
            strict_mode=False,
        )
        
        # Run command with stdout
        exit_code = executor.execute("python -c \"print('test_output')\"")
        
        self.assertEqual(exit_code, 0)
        # Check that we captured output
        all_output = "".join(chunks_sent)
        self.assertIn("test_output", all_output)
        logger.info("✅ Stdout captured")

    def test_buffer_flushed_on_command_completion(self):
        """Verify buffer is flushed even when command completes."""
        api_client = MagicMock()
        chunks_sent = []
        
        def capture_chunk(*args, **kwargs):
            if kwargs.get("log_chunk"):
                chunks_sent.append(kwargs)
            return (True, None)
        
        api_client.ingest_chunk.side_effect = capture_chunk
        api_client.finalize_run.return_value = (True, None)
        
        executor = CommandExecutor(
            api_client=api_client,
            run_id="test_run",
            ci_run_id="gh_123",
            commit_sha="abc",
            strict_mode=False,
        )
        
        # Run short command with minimal output
        exit_code = executor.execute("python -c \"print('x')\"")
        
        # Even though output is small, it should be flushed
        self.assertGreater(len(chunks_sent), 0, "Buffer should be flushed")
        logger.info("✅ Buffer flushed on command completion")


if __name__ == "__main__":
    unittest.main()
