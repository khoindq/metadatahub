"""Tests for scripts/build_tree.py — tree index generation."""

import json
import pytest
from pathlib import Path

from scripts.build_tree import (
    build_tree_for_source,
    load_tree,
    find_node,
    _build_tree_heuristic,
    _sections_to_tree_nodes,
    _pages_to_tree_nodes,
    _parse_code_symbols,
    _files_to_tree_nodes,
    _build_document_tree,
    _build_schema_tree,
    _build_code_tree,
)


@pytest.fixture
def tmp_store(tmp_path):
    """Create a temporary store structure."""
    (tmp_path / "converted").mkdir()
    (tmp_path / "tree_index").mkdir()
    return tmp_path


@pytest.fixture
def sample_source():
    return {
        "id": "src_abc123",
        "filename": "report.pdf",
        "type": "pdf",
        "category": "document",
        "strategy": "tree_index",
        "summary": "Annual financial report with revenue data",
        "tags": ["finance", "annual"],
    }


@pytest.fixture
def sample_xlsx_source():
    return {
        "id": "src_xlsx01",
        "filename": "sales.xlsx",
        "type": "xlsx",
        "category": "spreadsheet",
        "strategy": "schema_index",
        "summary": "Quarterly sales data",
        "tags": ["sales", "q3"],
    }


@pytest.fixture
def sample_code_source():
    return {
        "id": "src_code01",
        "filename": "app.py",
        "type": "python",
        "category": "code",
        "strategy": "symbol_index",
        "summary": "Main application module",
        "tags": ["python", "app"],
    }


class TestBuildDocumentTree:
    def test_empty_document(self, tmp_store, sample_source):
        """Tree with no converted files produces root-only tree."""
        tree = _build_document_tree(
            "src_abc123", sample_source,
            tmp_store / "converted" / "src_abc123", None,
        )
        assert tree["id"] == "src_abc123"
        assert tree["root"]["node_id"] == "n0"
        assert tree["root"]["title"] == "report.pdf"
        assert isinstance(tree["root"]["children"], list)

    def test_with_sections(self, tmp_store, sample_source):
        """Tree from markdown sections builds hierarchy."""
        sections = [
            {"title": "Introduction", "level": 1, "line_start": 0, "line_end": 10},
            {"title": "Background", "level": 2, "line_start": 10, "line_end": 20},
            {"title": "Methods", "level": 1, "line_start": 20, "line_end": 40},
        ]
        converter_result = {"sections": sections}

        tree = _build_document_tree(
            "src_abc123", sample_source,
            tmp_store / "converted" / "src_abc123", converter_result,
        )
        children = tree["root"]["children"]
        assert len(children) == 2  # Introduction and Methods (top-level)
        assert children[0]["title"] == "Introduction"
        # Background should be nested under Introduction
        assert len(children[0]["children"]) == 1
        assert children[0]["children"][0]["title"] == "Background"

    def test_with_page_texts(self, tmp_store, sample_source):
        """Tree from PDF page texts creates page-range nodes."""
        page_texts = [(i, f"Page {i} content") for i in range(1, 13)]
        converter_result = {"page_texts": page_texts}

        tree = _build_document_tree(
            "src_abc123", sample_source,
            tmp_store / "converted" / "src_abc123", converter_result,
        )
        children = tree["root"]["children"]
        # 12 pages / 5 per chunk = 3 chunks
        assert len(children) == 3
        assert children[0]["title"] == "Pages 1-5"
        assert children[1]["title"] == "Pages 6-10"
        assert children[2]["title"] == "Pages 11-12"

    def test_with_converted_files(self, tmp_store, sample_source):
        """Tree from listing converted files."""
        source_dir = tmp_store / "converted" / "src_abc123"
        source_dir.mkdir(parents=True)
        (source_dir / "section_intro.md").write_text("# Intro\nContent")
        (source_dir / "section_methods.md").write_text("# Methods\nContent")

        tree = _build_document_tree(
            "src_abc123", sample_source, source_dir, None,
        )
        children = tree["root"]["children"]
        assert len(children) == 2


class TestBuildSchemaTree:
    def test_with_sheets(self, tmp_store, sample_xlsx_source):
        """Schema tree from Excel sheets."""
        converter_result = {
            "sheets": [
                {
                    "name": "North America",
                    "headers": ["date", "product", "amount"],
                    "row_count": 100,
                    "column_count": 3,
                    "sample_rows": [{"date": "2025-01-01", "product": "Widget", "amount": 500}],
                },
                {
                    "name": "Europe",
                    "headers": ["date", "product", "amount"],
                    "row_count": 50,
                    "column_count": 3,
                    "sample_rows": [],
                },
            ]
        }

        tree = _build_schema_tree(
            "src_xlsx01", sample_xlsx_source,
            tmp_store / "converted" / "src_xlsx01", converter_result,
        )
        assert tree["id"] == "src_xlsx01"
        children = tree["root"]["children"]
        assert len(children) == 2
        assert children[0]["title"] == "Sheet: North America"
        assert "100 rows" in children[0]["summary"]
        assert "sample_data" in children[0]

    def test_empty_sheets(self, tmp_store, sample_xlsx_source):
        """Schema tree with empty converter result."""
        tree = _build_schema_tree(
            "src_xlsx01", sample_xlsx_source,
            tmp_store / "converted" / "src_xlsx01", None,
        )
        assert tree["root"]["children"] == []


class TestBuildCodeTree:
    def test_with_code_file(self, tmp_store, sample_code_source):
        """Code tree parses functions/classes."""
        source_dir = tmp_store / "converted" / "src_code01"
        source_dir.mkdir(parents=True)
        (source_dir / "full.txt").write_text(
            "class MyApp:\n    pass\n\ndef main():\n    pass\n\nasync def handler():\n    pass\n"
        )

        tree = _build_code_tree(
            "src_code01", sample_code_source, source_dir, None,
        )
        children = tree["root"]["children"]
        assert len(children) == 3
        assert "Class: MyApp" in children[0]["title"]
        assert "Function: main" in children[1]["title"]
        assert "Async Function: handler" in children[2]["title"]

    def test_empty_code(self, tmp_store, sample_code_source):
        """Code tree with no converted files."""
        tree = _build_code_tree(
            "src_code01", sample_code_source,
            tmp_store / "converted" / "src_code01", None,
        )
        assert tree["root"]["children"] == []


class TestSectionsToTreeNodes:
    def test_flat_sections(self):
        """All same level → flat list."""
        sections = [
            {"title": "A", "level": 1, "line_start": 0, "line_end": 10},
            {"title": "B", "level": 1, "line_start": 10, "line_end": 20},
        ]
        nodes = _sections_to_tree_nodes(sections, Path("/fake"))
        assert len(nodes) == 2
        assert nodes[0]["title"] == "A"
        assert nodes[1]["title"] == "B"

    def test_nested_sections(self):
        """Level 2 nests under level 1."""
        sections = [
            {"title": "A", "level": 1, "line_start": 0, "line_end": 30},
            {"title": "A.1", "level": 2, "line_start": 5, "line_end": 15},
            {"title": "A.2", "level": 2, "line_start": 15, "line_end": 30},
            {"title": "B", "level": 1, "line_start": 30, "line_end": 50},
        ]
        nodes = _sections_to_tree_nodes(sections, Path("/fake"))
        assert len(nodes) == 2  # A and B at top level
        assert len(nodes[0]["children"]) == 2  # A.1 and A.2

    def test_empty_sections(self):
        nodes = _sections_to_tree_nodes([], Path("/fake"))
        assert nodes == []


class TestPagesToTreeNodes:
    def test_page_grouping(self):
        page_texts = [(i, f"Content {i}") for i in range(1, 8)]
        nodes = _pages_to_tree_nodes(page_texts, "src_test", Path("/fake"))
        assert len(nodes) == 2  # 5 + 2
        assert nodes[0]["title"] == "Pages 1-5"
        assert nodes[1]["title"] == "Pages 6-7"

    def test_single_page(self):
        page_texts = [(1, "Only page")]
        nodes = _pages_to_tree_nodes(page_texts, "src_test", Path("/fake"))
        assert len(nodes) == 1
        assert nodes[0]["title"] == "Pages 1-1"


class TestParseCodeSymbols:
    def test_python_symbols(self):
        code = "class Foo:\n    pass\n\ndef bar():\n    pass\n"
        nodes = _parse_code_symbols(code)
        assert len(nodes) == 2
        assert "Class: Foo" in nodes[0]["title"]
        assert "Function: bar" in nodes[1]["title"]

    def test_async_functions(self):
        code = "async def handler():\n    pass\n"
        nodes = _parse_code_symbols(code)
        assert len(nodes) == 1
        assert "Async Function: handler" in nodes[0]["title"]

    def test_no_symbols(self):
        code = "x = 1\ny = 2\nprint(x + y)\n"
        nodes = _parse_code_symbols(code)
        assert nodes == []


class TestBuildTreeForSource:
    def test_full_pipeline_pdf(self, tmp_store, sample_source):
        """Full tree build for a PDF source with converter result."""
        converter_result = {
            "pages": 10,
            "page_texts": [(i, f"Page {i}") for i in range(1, 11)],
        }

        tree = build_tree_for_source(
            sample_source,
            tmp_store / "converted",
            tmp_store / "tree_index",
            converter_result=converter_result,
        )

        assert tree["id"] == "src_abc123"
        assert tree["root"]["node_id"] == "n0"
        assert len(tree["root"]["children"]) == 2  # 10 pages / 5 = 2 chunks

        # Check file was written
        tree_file = tmp_store / "tree_index" / "src_abc123.tree.json"
        assert tree_file.exists()
        loaded = json.loads(tree_file.read_text())
        assert loaded["id"] == "src_abc123"

    def test_full_pipeline_xlsx(self, tmp_store, sample_xlsx_source):
        """Full tree build for an Excel source."""
        converter_result = {
            "sheets": [{
                "name": "Sales",
                "headers": ["date", "amount"],
                "row_count": 50,
                "column_count": 2,
                "sample_rows": [{"date": "2025-01-01", "amount": 100}],
            }]
        }

        tree = build_tree_for_source(
            sample_xlsx_source,
            tmp_store / "converted",
            tmp_store / "tree_index",
            converter_result=converter_result,
        )

        assert tree["id"] == "src_xlsx01"
        assert len(tree["root"]["children"]) == 1


class TestLoadAndFindTree:
    def test_load_tree(self, tmp_store):
        tree_data = {
            "id": "src_test",
            "root": {
                "node_id": "n0",
                "title": "Test",
                "summary": "Test doc",
                "children": [
                    {"node_id": "n1", "title": "Section 1", "summary": "S1", "children": []},
                ],
            },
        }
        tree_path = tmp_store / "tree_index" / "src_test.tree.json"
        tree_path.write_text(json.dumps(tree_data))

        loaded = load_tree(tree_path)
        assert loaded["id"] == "src_test"

    def test_load_nonexistent(self, tmp_store):
        assert load_tree(tmp_store / "nope.json") is None

    def test_find_node_root(self):
        tree = {
            "root": {
                "node_id": "n0",
                "title": "Root",
                "children": [
                    {"node_id": "n1", "title": "Child", "children": []},
                ],
            }
        }
        assert find_node(tree, "n0")["title"] == "Root"

    def test_find_node_nested(self):
        tree = {
            "root": {
                "node_id": "n0",
                "title": "Root",
                "children": [
                    {
                        "node_id": "n1",
                        "title": "Parent",
                        "children": [
                            {"node_id": "n1.1", "title": "Nested", "children": []},
                        ],
                    },
                ],
            }
        }
        assert find_node(tree, "n1.1")["title"] == "Nested"

    def test_find_node_missing(self):
        tree = {"root": {"node_id": "n0", "children": []}}
        assert find_node(tree, "n99") is None


class TestHeuristicFallback:
    def test_routes_to_schema(self, tmp_store, sample_xlsx_source):
        tree = _build_tree_heuristic(
            sample_xlsx_source,
            tmp_store / "converted" / "src_xlsx01",
            None,
        )
        assert tree["id"] == "src_xlsx01"

    def test_routes_to_code(self, tmp_store, sample_code_source):
        tree = _build_tree_heuristic(
            sample_code_source,
            tmp_store / "converted" / "src_code01",
            None,
        )
        assert tree["id"] == "src_code01"

    def test_routes_to_document(self, tmp_store, sample_source):
        tree = _build_tree_heuristic(
            sample_source,
            tmp_store / "converted" / "src_abc123",
            None,
        )
        assert tree["id"] == "src_abc123"
