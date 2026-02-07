"""Claude client using Claude Code CLI (-p mode) as default.

Supports:
- Claude Code CLI (default, uses existing auth)
- Direct API fallback (if CLI not available)
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

import httpx

DEFAULT_BASE_URL = "https://api.anthropic.com"
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
API_VERSION = "2023-06-01"


def check_claude_cli() -> bool:
    """Check if claude CLI is available."""
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


class ClaudeClient:
    """Claude client - prefers CLI, falls back to API."""

    def __init__(
        self,
        use_cli: bool = True,
        token: Optional[str] = None,
        token_file: Optional[Path] = None,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._token = token
        self._token_file = token_file
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client: Optional[httpx.Client] = None
        
        # Prefer CLI if available
        self._use_cli = use_cli and check_claude_cli()

    @property
    def auth_header(self) -> dict:
        """Build the authorization header (for API mode)."""
        if self._use_cli:
            return {"X-Auth-Method": "claude-cli"}
        
        # Try token
        token = self._resolve_token()
        if token:
            return {"Authorization": f"Bearer {token}"}
        # Fallback to API key
        if self._api_key:
            return {"x-api-key": self._api_key}
        raise ValueError(
            "No authentication configured. Install Claude Code CLI, "
            "set ANTHROPIC_API_KEY env var, or provide a token."
        )

    def _resolve_token(self) -> Optional[str]:
        """Resolve OAuth token from various sources."""
        if self._token:
            return self._token
        if self._token_file and self._token_file.exists():
            return self._token_file.read_text().strip()
        return None

    def _call_cli(self, prompt: str, system: Optional[str] = None, max_tokens: int = 1024) -> dict:
        """Call Claude via CLI -p mode."""
        cmd = ["claude", "-p"]
        
        if system:
            full_prompt = f"System: {system}\n\nUser: {prompt}"
        else:
            full_prompt = prompt
        
        try:
            result = subprocess.run(
                cmd,
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Claude CLI error: {result.stderr}")
            
            return {
                "text": result.stdout.strip(),
                "model": "claude-cli",
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "stop_reason": "end_turn"
            }
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude CLI timeout (120s)")
        except FileNotFoundError:
            raise RuntimeError("Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code")

    def _call_api(self, prompt: str, system: Optional[str] = None, max_tokens: int = 1024) -> dict:
        """Call Claude via direct API."""
        if self._client is None:
            self._client = httpx.Client(timeout=60.0)

        messages = [{"role": "user", "content": prompt}]
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            payload["system"] = system

        response = self._client.post(
            f"{self.base_url}/v1/messages",
            json=payload,
            headers={
                **self.auth_header,
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()

        text_parts = [
            block["text"] for block in data.get("content", []) if block.get("type") == "text"
        ]
        return {
            "text": "\n".join(text_parts),
            "model": data.get("model"),
            "usage": data.get("usage", {}),
            "stop_reason": data.get("stop_reason"),
        }

    def send_message(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> dict:
        """Send a message to Claude (CLI or API)."""
        if self._use_cli:
            return self._call_cli(prompt, system, max_tokens)
        return self._call_api(prompt, system, max_tokens)

    def send_json_message(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> dict:
        """Send a message and parse JSON response."""
        result = self.send_message(prompt, system=system, max_tokens=max_tokens)
        text = result["text"].strip()

        # Try to extract JSON from markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```") and not in_block:
                    in_block = True
                    continue
                elif line.startswith("```") and in_block:
                    break
                elif in_block:
                    json_lines.append(line)
            text = "\n".join(json_lines)

        try:
            result["parsed"] = json.loads(text)
        except json.JSONDecodeError:
            result["parsed"] = None
            result["parse_error"] = f"Could not parse JSON from response: {text[:200]}"

        return result

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @classmethod
    def from_config(cls, config, use_cli: bool = True) -> "ClaudeClient":
        """Create a client from a Config object."""
        token_path = config.oauth.token_path(config.store_root)
        return cls(
            use_cli=use_cli,
            token_file=token_path if token_path.exists() else None,
            base_url=config.oauth.base_url,
            model=config.ingest.model,
        )
