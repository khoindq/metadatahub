"""Tests for scripts/claude_client.py"""

import tempfile
from pathlib import Path

from scripts.claude_client import ClaudeClient
from scripts.config import Config


def test_api_key_auth():
    client = ClaudeClient(api_key="test-key-123")
    assert client.auth_header == {"x-api-key": "test-key-123"}


def test_oauth_token_auth():
    client = ClaudeClient(token="oauth-token-abc")
    assert client.auth_header == {"Authorization": "Bearer oauth-token-abc"}


def test_token_file_auth():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".token", delete=False) as f:
        f.write("file-token-xyz\n")
        f.flush()
        client = ClaudeClient(token_file=Path(f.name))
        assert client.auth_header == {"Authorization": "Bearer file-token-xyz"}
        Path(f.name).unlink()


def test_oauth_takes_priority():
    client = ClaudeClient(token="oauth", api_key="api-key")
    assert client.auth_header == {"Authorization": "Bearer oauth"}


def test_no_auth_raises():
    client = ClaudeClient()
    try:
        _ = client.auth_header
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "No authentication" in str(e)


def test_from_config():
    config = Config()
    client = ClaudeClient.from_config(config)
    assert client.base_url == "https://api.anthropic.com"
    assert client.model == config.ingest.model


def test_default_model():
    client = ClaudeClient(api_key="test")
    assert client.model == "claude-sonnet-4-5-20250929"


def test_custom_model():
    client = ClaudeClient(api_key="test", model="claude-haiku-4-5-20251001")
    assert client.model == "claude-haiku-4-5-20251001"


def test_context_manager():
    with ClaudeClient(api_key="test") as client:
        assert client.auth_header == {"x-api-key": "test"}
    # After exit, client should be closed (no assertion needed, just no error)
