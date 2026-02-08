"""Tests for scripts/converters/"""

import json
import tempfile
from pathlib import Path

from scripts.converters import get_converter, convert_file, get_sample
from scripts.converters.md_converter import convert as md_convert, get_sample as md_get_sample
from scripts.converters.pdf_converter import convert as pdf_convert, get_sample as pdf_get_sample
from scripts.converters.xlsx_converter import convert as xlsx_convert, get_sample as xlsx_get_sample


# --- Markdown converter ---

def test_md_convert_sections():
    result = md_convert(Path("PLAN.md"))
    assert len(result["sections"]) > 0
    assert result["text"]
    first = result["sections"][0]
    assert "title" in first
    assert "level" in first
    assert "line_start" in first
    assert "line_end" in first


def test_md_convert_output_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = md_convert(Path("PLAN.md"), output_dir=Path(tmpdir))
        assert len(result["output_files"]) > 0
        for f in result["output_files"]:
            assert Path(f).exists()


def test_md_get_sample():
    sample = md_get_sample(Path("PLAN.md"), max_chars=500)
    assert "Table of Contents" in sample
    assert len(sample) <= 2000  # ToC + content preview


# --- PDF converter ---

def test_pdf_convert():
    result = pdf_convert(Path("tests/fixtures/test.pdf"))
    assert result["pages"] == 2
    assert isinstance(result["page_texts"], list)
    assert len(result["page_texts"]) == 2


def test_pdf_convert_output_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = pdf_convert(Path("tests/fixtures/test.pdf"), output_dir=Path(tmpdir))
        assert len(result["output_files"]) > 0
        for f in result["output_files"]:
            assert Path(f).exists()


def test_pdf_get_sample():
    sample = pdf_get_sample(Path("tests/fixtures/test.pdf"))
    assert "[Page 1]" in sample


# --- XLSX converter ---

def test_xlsx_convert():
    result = xlsx_convert(Path("tests/fixtures/test.xlsx"))
    assert result["sheet_count"] == 2
    sheets = result["sheets"]
    sales = sheets[0]
    assert sales["name"] == "Sales"
    assert sales["row_count"] == 6
    assert "Date" in sales["headers"]
    assert len(sales["sample_rows"]) == 5


def test_xlsx_convert_output_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = xlsx_convert(Path("tests/fixtures/test.xlsx"), output_dir=Path(tmpdir))
        assert len(result["output_files"]) == 2
        for f in result["output_files"]:
            assert Path(f).exists()
            data = json.loads(Path(f).read_text())
            assert "name" in data


def test_xlsx_get_sample():
    sample = xlsx_get_sample(Path("tests/fixtures/test.xlsx"))
    assert "[Sheet: Sales]" in sample
    assert "Headers:" in sample


def test_xlsx_column_analysis():
    """Test that column type detection and stats work."""
    result = xlsx_convert(Path("tests/fixtures/test.xlsx"))
    sales = result["sheets"][0]

    # Check columns are analyzed
    assert "columns" in sales
    assert len(sales["columns"]) == 4

    # Find Amount column (numeric)
    amount_col = next(c for c in sales["columns"] if c["name"] == "Amount")
    assert amount_col["type"] == "numeric"
    assert "stats" in amount_col
    assert amount_col["stats"]["sum"] == 83200.0
    assert amount_col["stats"]["min"] == 6300.0
    assert amount_col["stats"]["max"] == 22100.0


def test_xlsx_sheet_stats():
    """Test sheet-level aggregated stats."""
    result = xlsx_convert(Path("tests/fixtures/test.xlsx"))
    sales = result["sheets"][0]

    assert "stats" in sales
    assert sales["stats"]["row_count"] == 6
    assert sales["stats"]["primary_numeric_column"] == "Amount"
    assert sales["stats"]["total_amount"] == 83200.0


def test_xlsx_sample_data_format():
    """Test PageIndex-style sample_data formatting."""
    result = xlsx_convert(Path("tests/fixtures/test.xlsx"))
    sales = result["sheets"][0]

    assert "sample_data" in sales
    assert "Row 1:" in sales["sample_data"]
    assert "Widget Pro" in sales["sample_data"]
    # Should be semicolon-separated rows
    assert ";" in sales["sample_data"]


# --- Registry ---

def test_get_converter_known():
    assert get_converter("pdf") is not None
    assert get_converter("xlsx") is not None
    assert get_converter("markdown") is not None


def test_get_converter_unknown():
    assert get_converter("zip") is None


def test_get_converter_category_fallback():
    assert get_converter("text", "text") is not None


def test_convert_file_dispatch():
    result = convert_file(Path("PLAN.md"), "markdown")
    assert result is not None
    assert "sections" in result


def test_get_sample_dispatch():
    sample = get_sample(Path("tests/fixtures/test.xlsx"), "xlsx")
    assert sample is not None
    assert "Sales" in sample


def test_get_sample_fallback():
    sample = get_sample(Path("requirements.txt"), "unknown_type")
    assert sample is not None
    assert "pypdf" in sample
