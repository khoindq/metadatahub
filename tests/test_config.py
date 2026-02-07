"""Tests for scripts/config.py"""

import json
import tempfile
from pathlib import Path

from scripts.config import Config, OAuthConfig, IngestSettings, init_config


def test_default_config():
    c = Config()
    assert c.store_path == "."
    assert c.version == "1.0"
    assert c.oauth.base_url == "https://api.anthropic.com"
    assert c.ingest.model == "claude-sonnet-4-5-20250929"
    assert c.ingest.max_sample_tokens == 2000
    assert c.ingest.max_pages_sample == 2


def test_config_paths():
    c = Config()
    assert c.inbox_path == c.store_root / "inbox"
    assert c.converted_path == c.store_root / "converted"
    assert c.tree_index_path == c.store_root / "tree_index"
    assert c.catalog_path == c.store_root / "catalog.json"


def test_config_roundtrip():
    c = Config(store_path="/tmp/test_store")
    c.oauth.client_id = "test-client"
    d = c.to_dict()
    c2 = Config.from_dict(d)
    assert c2.store_path == "/tmp/test_store"
    assert c2.oauth.client_id == "test-client"
    assert c2.ingest.model == c.ingest.model


def test_config_save_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "config.json"
        c = Config(store_path=tmpdir)
        c.save(path)

        assert path.exists()
        data = json.loads(path.read_text())
        assert data["version"] == "1.0"

        c2 = Config.load(path)
        assert c2.store_path == tmpdir


def test_init_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        c = init_config(store_path=tmpdir)
        assert (Path(tmpdir) / "inbox").is_dir()
        assert (Path(tmpdir) / "converted").is_dir()
        assert (Path(tmpdir) / "tree_index").is_dir()
        assert (Path(tmpdir) / "vector_store").is_dir()
        assert (Path(tmpdir) / "config.json").exists()


def test_oauth_token_path():
    c = Config()
    tp = c.oauth.token_path(c.store_root)
    assert tp.name == ".oauth_token"
