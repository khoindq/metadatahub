"""MetadataHub configuration management.

Handles loading, validating, and creating config.json which stores:
- Store location (where the index lives)
- OAuth token reference
- Global settings (model, token limits, etc.)
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


DEFAULT_CONFIG_PATH = Path("config.json")

# Default store is the current directory (metadatahub root)
DEFAULT_STORE_PATH = "."

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_MAX_SAMPLE_TOKENS = 2000
DEFAULT_MAX_PAGES_SAMPLE = 2


@dataclass
class OAuthConfig:
    token_file: str = ".oauth_token"
    client_id: Optional[str] = None
    base_url: str = "https://api.anthropic.com"

    def token_path(self, store_root: Path) -> Path:
        return store_root / self.token_file


@dataclass
class IngestSettings:
    max_sample_tokens: int = DEFAULT_MAX_SAMPLE_TOKENS
    max_pages_sample: int = DEFAULT_MAX_PAGES_SAMPLE
    model: str = DEFAULT_MODEL
    inbox_dir: str = "inbox"
    converted_dir: str = "converted"
    tree_index_dir: str = "tree_index"
    vector_store_dir: str = "vector_store"
    catalog_file: str = "catalog.json"


@dataclass
class Config:
    store_path: str = DEFAULT_STORE_PATH
    oauth: OAuthConfig = field(default_factory=OAuthConfig)
    ingest: IngestSettings = field(default_factory=IngestSettings)
    version: str = "1.0"

    @property
    def store_root(self) -> Path:
        return Path(self.store_path).resolve()

    @property
    def inbox_path(self) -> Path:
        return self.store_root / self.ingest.inbox_dir

    @property
    def converted_path(self) -> Path:
        return self.store_root / self.ingest.converted_dir

    @property
    def tree_index_path(self) -> Path:
        return self.store_root / self.ingest.tree_index_dir

    @property
    def vector_store_path(self) -> Path:
        return self.store_root / self.ingest.vector_store_dir

    @property
    def catalog_path(self) -> Path:
        return self.store_root / self.ingest.catalog_file

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: Optional[Path] = None):
        path = path or (self.store_root / DEFAULT_CONFIG_PATH)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        oauth_data = data.get("oauth", {})
        ingest_data = data.get("ingest", {})
        return cls(
            store_path=data.get("store_path", DEFAULT_STORE_PATH),
            oauth=OAuthConfig(**oauth_data),
            ingest=IngestSettings(**ingest_data),
            version=data.get("version", "1.0"),
        )

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        path = path or DEFAULT_CONFIG_PATH
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls.from_dict(data)


def init_config(store_path: str = ".") -> Config:
    """Create a fresh config and ensure all directories exist."""
    config = Config(store_path=store_path)
    for d in [
        config.inbox_path,
        config.converted_path,
        config.tree_index_path,
        config.vector_store_path,
    ]:
        d.mkdir(parents=True, exist_ok=True)
    config.save()
    return config
