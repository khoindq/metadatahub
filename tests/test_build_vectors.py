"""Tests for scripts/build_vectors.py — FAISS vector index."""

import json
import pytest
from pathlib import Path

from scripts.build_vectors import (
    _build_embed_text,
    embed_sources,
    build_index,
    search,
    add_to_index,
    get_embedding_dim,
)


@pytest.fixture
def sample_sources():
    return [
        {
            "id": "src_001",
            "filename": "annual_report.pdf",
            "summary": "FY2025 annual report covering revenue, expenses, and guidance",
            "type": "pdf",
            "category": "document",
            "tags": ["finance", "annual", "revenue"],
            "doc_nature": "financial_report",
        },
        {
            "id": "src_002",
            "filename": "sales_q3.xlsx",
            "summary": "Q3 2025 sales data broken down by region and product",
            "type": "xlsx",
            "category": "spreadsheet",
            "tags": ["sales", "q3", "regional"],
            "doc_nature": "sales_data",
        },
        {
            "id": "src_003",
            "filename": "api_docs.md",
            "summary": "REST API documentation for the user management service",
            "type": "markdown",
            "category": "text",
            "tags": ["api", "docs", "users"],
            "doc_nature": "api_documentation",
        },
    ]


@pytest.fixture
def vector_dir(tmp_path):
    d = tmp_path / "vector_store"
    d.mkdir()
    return d


class TestBuildEmbedText:
    def test_all_fields(self):
        source = {
            "filename": "report.pdf",
            "doc_nature": "financial_report",
            "summary": "Annual financial data",
            "tags": ["finance", "annual"],
            "type": "pdf",
            "category": "document",
        }
        text = _build_embed_text(source)
        assert "report.pdf" in text
        assert "financial report" in text  # underscores replaced
        assert "Annual financial data" in text
        assert "finance" in text
        assert "pdf" in text

    def test_minimal_source(self):
        text = _build_embed_text({"id": "src_x"})
        # Should not crash, may be empty or minimal
        assert isinstance(text, str)

    def test_empty_source(self):
        text = _build_embed_text({})
        assert isinstance(text, str)


class TestEmbedSources:
    def test_embed_multiple(self, sample_sources):
        embeddings, metadata = embed_sources(sample_sources)
        assert embeddings.shape[0] == 3
        assert embeddings.shape[1] == get_embedding_dim()
        assert len(metadata) == 3
        assert metadata[0]["id"] == "src_001"

    def test_embed_empty(self):
        embeddings, metadata = embed_sources([])
        assert embeddings.shape[0] == 0
        assert metadata == []

    def test_embed_single(self):
        sources = [{"id": "src_x", "filename": "test.txt", "summary": "A test file"}]
        embeddings, metadata = embed_sources(sources)
        assert embeddings.shape[0] == 1
        assert metadata[0]["id"] == "src_x"


class TestBuildIndex:
    def test_build_and_files(self, sample_sources, vector_dir):
        result = build_index(sample_sources, vector_dir)
        assert result["num_vectors"] == 3
        assert result["dimension"] == get_embedding_dim()
        assert (vector_dir / "index.faiss").exists()
        assert (vector_dir / "metadata.json").exists()

        # Validate metadata file
        meta = json.loads((vector_dir / "metadata.json").read_text())
        assert len(meta) == 3
        assert meta[0]["id"] == "src_001"

    def test_build_empty(self, vector_dir):
        result = build_index([], vector_dir)
        assert result["num_vectors"] == 0
        assert (vector_dir / "index.faiss").exists()


class TestSearch:
    def test_search_returns_results(self, sample_sources, vector_dir):
        build_index(sample_sources, vector_dir)

        results = search("What was the revenue?", vector_dir, top_k=3)
        assert len(results) == 3
        # Financial report should rank high for revenue query
        assert results[0]["rank"] == 1
        assert "score" in results[0]
        assert results[0]["score"] > 0

    def test_search_finance_query(self, sample_sources, vector_dir):
        build_index(sample_sources, vector_dir)

        results = search("annual financial report revenue", vector_dir, top_k=1)
        assert len(results) == 1
        # The annual report should be the top match
        assert results[0]["id"] == "src_001"

    def test_search_api_query(self, sample_sources, vector_dir):
        build_index(sample_sources, vector_dir)

        results = search("REST API user management endpoints", vector_dir, top_k=1)
        assert len(results) == 1
        assert results[0]["id"] == "src_003"

    def test_search_empty_index(self, vector_dir):
        build_index([], vector_dir)
        results = search("anything", vector_dir)
        assert results == []

    def test_search_no_index(self, tmp_path):
        results = search("anything", tmp_path / "nonexistent")
        assert results == []

    def test_search_top_k(self, sample_sources, vector_dir):
        build_index(sample_sources, vector_dir)
        results = search("data", vector_dir, top_k=2)
        assert len(results) == 2


class TestAddToIndex:
    def test_add_new_sources(self, sample_sources, vector_dir):
        # Build initial index with first 2 sources
        build_index(sample_sources[:2], vector_dir)

        # Add the third
        result = add_to_index([sample_sources[2]], vector_dir)
        assert result["num_vectors"] == 3
        assert result["added"] == 1

        # Verify search finds all 3
        results = search("API docs", vector_dir, top_k=5)
        assert len(results) == 3

    def test_add_duplicate_skipped(self, sample_sources, vector_dir):
        build_index(sample_sources, vector_dir)

        # Try to add existing source
        result = add_to_index([sample_sources[0]], vector_dir)
        assert result["num_vectors"] == 3
        assert result["added"] == 0

    def test_add_to_empty(self, sample_sources, vector_dir):
        result = add_to_index(sample_sources[:1], vector_dir)
        assert result["num_vectors"] == 1
        assert result["added"] == 1

    def test_add_mixed_new_and_existing(self, sample_sources, vector_dir):
        build_index(sample_sources[:1], vector_dir)

        result = add_to_index(sample_sources, vector_dir)
        assert result["num_vectors"] == 3
        assert result["added"] == 2  # 2 new, 1 existing


class TestGetEmbeddingDim:
    def test_dimension(self):
        dim = get_embedding_dim()
        assert dim == 384  # all-MiniLM-L6-v2 produces 384-dim vectors
