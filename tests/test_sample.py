"""Tests for scripts/sample.py"""

from pathlib import Path

from scripts.detect import detect_file
from scripts.sample import (
    extract_sample, build_sampling_prompt, sample_file,
    _fallback_strategy, SAMPLING_SYSTEM_PROMPT,
)


def test_extract_sample_markdown():
    sample = extract_sample(Path("PLAN.md"), "markdown")
    assert len(sample) > 0
    assert "Table of Contents" in sample


def test_extract_sample_xlsx():
    sample = extract_sample(Path("tests/fixtures/test.xlsx"), "xlsx")
    assert "Sales" in sample
    assert "Headers:" in sample


def test_extract_sample_unknown_type():
    sample = extract_sample(Path("requirements.txt"), "unknown_type")
    assert sample is not None
    assert len(sample) > 0


def test_build_sampling_prompt():
    card = detect_file(Path("PLAN.md"))
    sample = extract_sample(Path("PLAN.md"), "markdown")
    prompt = build_sampling_prompt(card, sample)
    assert "PLAN.md" in prompt
    assert "markdown" in prompt
    assert "text" in prompt
    assert "Document sample:" in prompt


def test_fallback_strategy_document():
    card = {"filename": "test.pdf", "type": "pdf", "category": "document", "size_kb": 100}
    strategy = _fallback_strategy(card)
    assert strategy["recommended_approach"] == "tree_index"
    assert strategy["has_structure"] is True
    assert "Fallback" in strategy["special_handling"]


def test_fallback_strategy_spreadsheet():
    card = {"filename": "test.xlsx", "type": "xlsx", "category": "spreadsheet", "size_kb": 50}
    strategy = _fallback_strategy(card)
    assert strategy["recommended_approach"] == "schema_index"


def test_fallback_strategy_code():
    card = {"filename": "test.py", "type": "python", "category": "code", "size_kb": 10}
    strategy = _fallback_strategy(card)
    assert strategy["recommended_approach"] == "symbol_index"


def test_fallback_strategy_unknown():
    card = {"filename": "test.bin", "type": "unknown", "category": "unknown", "size_kb": 5}
    strategy = _fallback_strategy(card)
    assert strategy["recommended_approach"] == "chunk_embed"


def test_sample_file_no_client():
    card = detect_file(Path("PLAN.md"))
    result = sample_file(Path("PLAN.md"), card, client=None)
    assert result["sampled"] is True
    assert result["strategy"] is not None
    assert result["strategy"]["recommended_approach"] == "tree_index"


def test_sample_file_xlsx_no_client():
    card = detect_file(Path("tests/fixtures/test.xlsx"))
    result = sample_file(Path("tests/fixtures/test.xlsx"), card, client=None)
    assert result["sampled"] is True
    assert result["strategy"]["recommended_approach"] == "schema_index"


def test_system_prompt_valid():
    assert "doc_nature" in SAMPLING_SYSTEM_PROMPT
    assert "recommended_approach" in SAMPLING_SYSTEM_PROMPT
    assert "tree_index" in SAMPLING_SYSTEM_PROMPT
