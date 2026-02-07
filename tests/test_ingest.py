"""Tests for scripts/ingest.py — full pipeline integration."""

import json
import pytest
from pathlib import Path

from scripts.config import init_config
from scripts.ingest import ingest_file, ingest, _count_nodes
from scripts.catalog import load_catalog


@pytest.fixture
def store(tmp_path):
    """Create a fully initialized store."""
    config = init_config(str(tmp_path))
    return config


@pytest.fixture
def sample_pdf(tmp_path):
    """Create a minimal valid PDF for testing."""
    # Minimal PDF that pypdf can parse
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 44>>stream\n"
        b"BT /F1 12 Tf 100 700 Td (Hello World) Tj ET\n"
        b"endstream\nendobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"0000000360 00000 n \n"
        b"trailer<</Size 6/Root 1 0 R>>\n"
        b"startxref\n431\n%%EOF"
    )
    pdf_path = tmp_path / "inbox" / "test.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(pdf_content)
    return pdf_path


@pytest.fixture
def sample_md(tmp_path):
    """Create a sample Markdown file."""
    md_content = """# Test Document

## Introduction
This is a test document for MetadataHub.

## Methods
We use several methods.

### Method A
First approach.

### Method B
Second approach.

## Results
The results are good.
"""
    md_path = tmp_path / "inbox" / "test.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_content)
    return md_path


@pytest.fixture
def sample_xlsx(tmp_path):
    """Create a sample Excel file."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(["date", "product", "amount"])
    ws.append(["2025-01-01", "Widget", 500])
    ws.append(["2025-01-02", "Gadget", 300])

    xlsx_path = tmp_path / "inbox" / "sales.xlsx"
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(xlsx_path)
    return xlsx_path


@pytest.fixture
def sample_txt(tmp_path):
    """Create a plain text file."""
    txt_path = tmp_path / "inbox" / "notes.txt"
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.write_text("These are some plain text notes about the project.\n" * 10)
    return txt_path


class TestCountNodes:
    def test_single_node(self):
        assert _count_nodes({"children": []}) == 1

    def test_nested(self):
        tree = {
            "children": [
                {"children": [{"children": []}]},
                {"children": []},
            ]
        }
        assert _count_nodes(tree) == 4


class TestIngestFile:
    def test_ingest_markdown(self, store, sample_md):
        catalog = load_catalog(store.catalog_path)
        result = ingest_file(sample_md, store, catalog, verbose=False)

        assert result is not None
        assert result["filename"] == "test.md"
        assert result["type"] == "markdown"
        assert result["strategy"] in ("tree_index", "chunk_embed")

        # Check converted files exist
        source_id = result["id"]
        converted_dir = store.converted_path / source_id
        assert converted_dir.exists()

        # Check tree was built
        tree_file = store.tree_index_path / f"{source_id}.tree.json"
        assert tree_file.exists()
        tree = json.loads(tree_file.read_text())
        assert tree["id"] == source_id
        assert len(tree["root"]["children"]) > 0

    def test_ingest_xlsx(self, store, sample_xlsx):
        catalog = load_catalog(store.catalog_path)
        result = ingest_file(sample_xlsx, store, catalog, verbose=False)

        assert result is not None
        assert result["type"] == "xlsx"

        source_id = result["id"]
        tree_file = store.tree_index_path / f"{source_id}.tree.json"
        assert tree_file.exists()
        tree = json.loads(tree_file.read_text())
        assert any("Sheet" in c.get("title", "") for c in tree["root"]["children"])

    def test_ingest_text(self, store, sample_txt):
        catalog = load_catalog(store.catalog_path)
        result = ingest_file(sample_txt, store, catalog, verbose=False)

        assert result is not None
        assert result["type"] == "text"

    def test_ingest_skips_unsupported(self, store, tmp_path):
        """Archive files are skipped."""
        archive = tmp_path / "inbox" / "data.zip"
        archive.write_bytes(b"PK\x03\x04fake zip content")

        catalog = load_catalog(store.catalog_path)
        result = ingest_file(archive, store, catalog, verbose=False)
        assert result is None


class TestIngestPipeline:
    def test_ingest_directory(self, store, sample_md, sample_txt):
        """Ingest a directory with multiple files."""
        result = ingest(
            store.inbox_path, store,
            skip_vectors=True, verbose=False,
        )

        assert result["processed"] >= 2
        assert result["skipped"] == 0

        # Catalog should have entries
        catalog = load_catalog(store.catalog_path)
        assert len(catalog["sources"]) >= 2

    def test_ingest_single_file(self, store, sample_md):
        result = ingest(sample_md, store, skip_vectors=True, verbose=False)
        assert result["processed"] == 1

    def test_ingest_with_vectors(self, store, sample_md, sample_txt):
        """Full pipeline including vector index build."""
        result = ingest(
            store.inbox_path, store,
            skip_vectors=False, verbose=False,
        )

        assert result["processed"] >= 2
        assert result["vector_stats"] is not None
        assert result["vector_stats"]["num_vectors"] >= 2

        # Check FAISS index exists
        assert (store.vector_store_path / "index.faiss").exists()
        assert (store.vector_store_path / "metadata.json").exists()

    def test_ingest_nonexistent_path(self, store, tmp_path):
        with pytest.raises(FileNotFoundError):
            ingest(tmp_path / "nope", store, verbose=False)

    def test_ingest_empty_directory(self, store, tmp_path):
        """Ingest an empty directory."""
        empty = tmp_path / "empty_inbox"
        empty.mkdir()
        result = ingest(empty, store, skip_vectors=True, verbose=False)
        assert result["processed"] == 0


class TestIngestIdempotent:
    def test_reingest_updates(self, store, sample_md):
        """Ingesting the same file twice updates the catalog entry."""
        result1 = ingest(sample_md, store, skip_vectors=True, verbose=False)
        catalog1 = load_catalog(store.catalog_path)
        count1 = len(catalog1["sources"])

        result2 = ingest(sample_md, store, skip_vectors=True, verbose=False)
        catalog2 = load_catalog(store.catalog_path)
        count2 = len(catalog2["sources"])

        # Should update, not duplicate
        assert count2 == count1
