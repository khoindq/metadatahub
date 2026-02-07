"""Tests for scripts/catalog.py"""

import tempfile
from pathlib import Path

from scripts.catalog import (
    create_catalog, load_catalog, save_catalog,
    add_source, find_source, find_source_by_filename,
    remove_source, list_sources, catalog_summary,
)
from scripts.detect import detect_file
from scripts.sample import sample_file


def _make_card(filename="test.md", file_type="markdown", category="text",
               source_id="src_test123"):
    return {
        "id": source_id,
        "filename": filename,
        "path": f"/path/to/{filename}",
        "type": file_type,
        "category": category,
        "size_kb": 10.0,
        "sampled": True,
        "strategy": {
            "doc_nature": "test_doc",
            "recommended_approach": "tree_index",
            "summary": "A test document",
            "tags": ["test", "markdown"],
        },
    }


def test_create_catalog():
    cat = create_catalog()
    assert cat["version"] == "1.0"
    assert cat["last_updated"]
    assert cat["sources"] == []


def test_add_source():
    cat = create_catalog()
    card = _make_card()
    entry = add_source(cat, card, converted_path="converted/test/")
    assert entry["id"] == "src_test123"
    assert entry["filename"] == "test.md"
    assert entry["strategy"] == "tree_index"
    assert entry["summary"] == "A test document"
    assert len(cat["sources"]) == 1


def test_add_source_update_existing():
    cat = create_catalog()
    card = _make_card()
    add_source(cat, card, converted_path="converted/v1/")
    assert len(cat["sources"]) == 1

    card["strategy"]["summary"] = "Updated summary"
    add_source(cat, card, converted_path="converted/v2/")
    assert len(cat["sources"]) == 1  # Updated, not duplicated
    assert cat["sources"][0]["summary"] == "Updated summary"
    assert cat["sources"][0]["converted_path"] == "converted/v2/"


def test_find_source():
    cat = create_catalog()
    add_source(cat, _make_card())
    found = find_source(cat, "src_test123")
    assert found is not None
    assert found["filename"] == "test.md"
    assert find_source(cat, "nonexistent") is None


def test_find_source_by_filename():
    cat = create_catalog()
    add_source(cat, _make_card())
    found = find_source_by_filename(cat, "test.md")
    assert found is not None
    assert find_source_by_filename(cat, "nope.md") is None


def test_remove_source():
    cat = create_catalog()
    add_source(cat, _make_card())
    assert len(cat["sources"]) == 1
    assert remove_source(cat, "src_test123") is True
    assert len(cat["sources"]) == 0
    assert remove_source(cat, "src_test123") is False


def test_list_sources():
    cat = create_catalog()
    add_source(cat, _make_card("a.md", "markdown", "text", "src_a"))
    add_source(cat, _make_card("b.xlsx", "xlsx", "spreadsheet", "src_b"))
    add_source(cat, _make_card("c.py", "python", "code", "src_c"))

    assert len(list_sources(cat)) == 3
    assert len(list_sources(cat, category="text")) == 1
    assert len(list_sources(cat, category="spreadsheet")) == 1
    assert len(list_sources(cat, tag="test")) == 3
    assert len(list_sources(cat, tag="nonexistent")) == 0


def test_catalog_summary():
    cat = create_catalog()
    add_source(cat, _make_card("a.md", "markdown", "text", "src_a"))
    add_source(cat, _make_card("b.xlsx", "xlsx", "spreadsheet", "src_b"))

    summary = catalog_summary(cat)
    assert summary["total_sources"] == 2
    assert summary["by_category"]["text"] == 1
    assert summary["by_category"]["spreadsheet"] == 1
    assert summary["sampled_count"] == 2


def test_save_load_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "catalog.json"
        cat = create_catalog()
        add_source(cat, _make_card())
        save_catalog(cat, path)

        cat2 = load_catalog(path)
        assert len(cat2["sources"]) == 1
        assert cat2["sources"][0]["filename"] == "test.md"


def test_load_nonexistent():
    cat = load_catalog(Path("/nonexistent/catalog.json"))
    assert cat["version"] == "1.0"
    assert cat["sources"] == []


def test_integration_with_detect_and_sample():
    """End-to-end: detect → sample → catalog."""
    card = detect_file(Path("PLAN.md"))
    card = sample_file(Path("PLAN.md"), card)

    cat = create_catalog()
    entry = add_source(cat, card)
    assert entry["sampled"] is True
    assert entry["strategy"] == "tree_index"
    assert entry["category"] == "text"
