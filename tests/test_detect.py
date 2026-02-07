"""Tests for scripts/detect.py"""

import tempfile
from pathlib import Path

from scripts.detect import (
    detect_file, detect_directory, get_category,
    _detect_by_extension, _detect_by_magic, _detect_by_content,
    _generate_id, _resolve_type,
)


def test_detect_by_extension():
    assert _detect_by_extension(Path("test.pdf")) == "pdf"
    assert _detect_by_extension(Path("test.xlsx")) == "xlsx"
    assert _detect_by_extension(Path("test.py")) == "python"
    assert _detect_by_extension(Path("test.md")) == "markdown"
    assert _detect_by_extension(Path("test.csv")) == "csv"
    assert _detect_by_extension(Path("test.unknown")) is None


def test_detect_by_magic():
    assert _detect_by_magic(b"%PDF-1.4 rest of file") == "pdf"
    assert _detect_by_magic(b"PK\x03\x04") == "zip_based"
    assert _detect_by_magic(b"\x89PNG\r\n") == "image"
    assert _detect_by_magic(b"\xff\xd8\xff\xe0") == "image"
    assert _detect_by_magic(b"Just plain text") is None


def test_detect_by_content():
    assert _detect_by_content(b"# Heading\n\nSome text", None) == "markdown"
    assert _detect_by_content(b"a,b,c\n1,2,3\n4,5,6", None) == "csv"
    assert _detect_by_content(b"a\tb\tc\n1\t2\t3\n4\t5\t6", None) == "tsv"
    assert _detect_by_content(b'{"key": "value"}', None) == "json"
    assert _detect_by_content(b"<?xml version", None) == "xml"
    assert _detect_by_content(b"", None) is None


def test_resolve_type():
    assert _resolve_type("pdf", None, None) == "pdf"
    assert _resolve_type("xlsx", "zip_based", None) == "xlsx"
    assert _resolve_type("docx", "zip_based", None) == "docx"
    assert _resolve_type(None, "pdf", None) == "pdf"
    assert _resolve_type(None, None, "csv") == "csv"
    assert _resolve_type(None, None, None) == "unknown"


def test_get_category():
    assert get_category("pdf") == "document"
    assert get_category("xlsx") == "spreadsheet"
    assert get_category("python") == "code"
    assert get_category("markdown") == "text"
    assert get_category("html") == "web"
    assert get_category("image") == "image"
    assert get_category("nonexistent") == "unknown"


def test_detect_file():
    card = detect_file(Path("PLAN.md"))
    assert card["filename"] == "PLAN.md"
    assert card["type"] == "markdown"
    assert card["category"] == "text"
    assert card["size_kb"] > 0
    assert card["sampled"] is False
    assert card["strategy"] is None
    assert card["id"].startswith("src_")


def test_detect_file_pdf():
    card = detect_file(Path("tests/fixtures/test.pdf"))
    assert card["type"] == "pdf"
    assert card["category"] == "document"
    assert "pages" in card


def test_detect_file_xlsx():
    card = detect_file(Path("tests/fixtures/test.xlsx"))
    assert card["type"] == "xlsx"
    assert card["category"] == "spreadsheet"
    assert "sheets" in card


def test_generate_id_deterministic():
    id1 = _generate_id(Path("PLAN.md"))
    id2 = _generate_id(Path("PLAN.md"))
    assert id1 == id2
    assert id1.startswith("src_")
    assert len(id1) == 14  # src_ + 10 hex chars


def test_detect_directory():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "test.md").write_text("# Hello")
        (Path(tmpdir) / "test.py").write_text("print('hi')")
        (Path(tmpdir) / ".hidden").write_text("skip me")

        cards = detect_directory(Path(tmpdir))
        assert len(cards) == 2  # .hidden should be skipped
        types = {c["type"] for c in cards}
        assert "markdown" in types or "python" in types


def test_detect_file_not_found():
    try:
        detect_file(Path("/nonexistent/file.pdf"))
        assert False, "Should raise FileNotFoundError"
    except FileNotFoundError:
        pass
