"""Tests for scripts/claude_client.py"""

import tempfile
from pathlib import Path

from scripts.claude_client import ClaudeClient
from scripts.config import Config, DEFAULT_BASE_URL, DEFAULT_MODEL


def test_api_key_auth():
    # Explicitly disable CLI to test API auth
    client = ClaudeClient(api_key="test-key-123", use_cli=False)
    assert client.auth_header == {"x-api-key": "test-key-123"}


def test_oauth_token_auth():
    client = ClaudeClient(token="oauth-token-abc", use_cli=False)
    assert client.auth_header == {"Authorization": "Bearer oauth-token-abc"}


def test_token_file_auth():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".token", delete=False) as f:
        f.write("file-token-xyz\n")
        f.flush()
        client = ClaudeClient(token_file=Path(f.name), use_cli=False)
        assert client.auth_header == {"Authorization": "Bearer file-token-xyz"}
        Path(f.name).unlink()


def test_oauth_takes_priority():
    client = ClaudeClient(token="oauth", api_key="api-key", use_cli=False)
    assert client.auth_header == {"Authorization": "Bearer oauth"}


def test_no_auth_raises():
    # Without CLI and without any credentials, should raise
    client = ClaudeClient(use_cli=False)
    try:
        _ = client.auth_header
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "No authentication" in str(e)


def test_from_config():
    config = Config()
    client = ClaudeClient.from_config(config, use_cli=False)
    # Default is now Z.ai
    assert client.base_url == DEFAULT_BASE_URL
    assert client.model == DEFAULT_MODEL


def test_default_model():
    client = ClaudeClient(api_key="test", use_cli=False)
    # ClaudeClient's own default (not config default)
    assert client.model == "claude-sonnet-4-5-20250929"


def test_custom_model():
    client = ClaudeClient(api_key="test", model="claude-haiku-4-5-20251001", use_cli=False)
    assert client.model == "claude-haiku-4-5-20251001"


def test_context_manager():
    with ClaudeClient(api_key="test", use_cli=False) as client:
        assert client.auth_header == {"x-api-key": "test"}
    # After exit, client should be closed (no assertion needed, just no error)


def test_cli_mode_header():
    """When CLI mode is enabled, auth_header returns CLI indicator."""
    client = ClaudeClient(use_cli=True)
    if client._use_cli:  # Only if CLI actually available
        assert client.auth_header == {"X-Auth-Method": "claude-cli"}
