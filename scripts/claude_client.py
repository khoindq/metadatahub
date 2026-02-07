"""Claude API client using httpx with OAuth token support.

Handles:
- Token loading from file
- API key fallback (ANTHROPIC_API_KEY env var)
- Message sending with structured responses
- Token refresh (stub for future OAuth flow)
"""

import json
import os
from pathlib import Path
from typing import Optional

import httpx

DEFAULT_BASE_URL = "https://api.anthropic.com"
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
API_VERSION = "2023-06-01"


class ClaudeClient:
    """Lightweight Claude API client."""

    def __init__(
        self,
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

    @property
    def auth_header(self) -> dict:
        """Build the authorization header."""
        # Prefer OAuth token
        token = self._resolve_token()
        if token:
            return {"Authorization": f"Bearer {token}"}
        # Fallback to API key
        if self._api_key:
            return {"x-api-key": self._api_key}
        raise ValueError(
            "No authentication configured. Set ANTHROPIC_API_KEY env var, "
            "provide a token, or specify a token_file."
        )

    def _resolve_token(self) -> Optional[str]:
        """Resolve OAuth token from direct value or file."""
        if self._token:
            return self._token
        if self._token_file:
            path = Path(self._token_file)
            if path.exists():
                return path.read_text().strip()
        return None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=120.0,
                headers={
                    "anthropic-version": API_VERSION,
                    "content-type": "application/json",
                },
            )
        return self._client

    def send_message(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> dict:
        """Send a message to Claude and return the response.

        Args:
            prompt: The user message content.
            system: Optional system prompt.
            max_tokens: Maximum response tokens.
            temperature: Sampling temperature.

        Returns:
            dict with keys: text (str), usage (dict), stop_reason (str)
        """
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system

        response = self.client.post(
            "/v1/messages",
            json=body,
            headers=self.auth_header,
        )
        response.raise_for_status()
        data = response.json()

        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block["text"]

        return {
            "text": text,
            "usage": data.get("usage", {}),
            "stop_reason": data.get("stop_reason", ""),
            "model": data.get("model", self.model),
        }

    def send_json_message(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> dict:
        """Send a message expecting a JSON response.

        Parses the response text as JSON. Falls back to raw text on parse failure.
        """
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
    def from_config(cls, config) -> "ClaudeClient":
        """Create a client from a Config object."""
        token_path = config.oauth.token_path(config.store_root)
        return cls(
            token_file=token_path if token_path.exists() else None,
            base_url=config.oauth.base_url,
            model=config.ingest.model,
        )
