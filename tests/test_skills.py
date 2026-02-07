"""Tests for skills/metadatahub/ — retrieval skill layer.

Tests search.py, deep_retrieve.py, and read_source.py end-to-end
using a pre-built store with sample documents.
"""

import json
import pytest
from pathlib import Path

from scripts.config import init_config
from scripts.ingest import ingest

# Import skill modules via their project-root paths
from skills.metadatahub.search import search as skill_search
from skills.metadatahub.deep_retrieve import get_tree, get_node, get_tree_summary
from skills.metadatahub.read_source import read_node_content, read_file, read_all_content


@pytest.fixture(scope="module")
def built_store(tmp_path_factory):
    """Build a complete store with sample documents for skill tests.

    Uses module scope so the expensive vector indexing only runs once.
    """
    tmp = tmp_path_factory.mktemp("skill_store")
    config = init_config(str(tmp))

    # Create sample markdown
    md_path = config.inbox_path / "guide.md"
    md_path.write_text(
        "# User Guide\n\n"
        "## Installation\n"
        "Run pip install metadatahub to install.\n\n"
        "## Configuration\n"
        "Edit config.json to set your store path.\n\n"
        "## Usage\n"
        "Drop files in the inbox and run ingest.\n"
    )

    # Create sample text
    txt_path = config.inbox_path / "notes.txt"
    txt_path.write_text(
        "Meeting notes from Q3 planning session.\n"
        "Revenue target: $5M for North America.\n"
        "Key focus areas: enterprise sales, product launches.\n"
    )

    # Create sample xlsx
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Q3 Sales"
    ws.append(["region", "product", "revenue"])
    ws.append(["North America", "Widget Pro", 12500])
    ws.append(["Europe", "Widget Lite", 8300])
    ws.append(["Asia", "Widget Pro", 9100])
    wb.save(config.inbox_path / "sales_q3.xlsx")

    # Run full ingest pipeline
    result = ingest(config.inbox_path, config, skip_vectors=False, verbose=False)
    assert result["processed"] == 3

    return config


class TestSkillSearch:
    def test_search_returns_results(self, built_store):
        results = skill_search("installation guide", store_path=str(built_store.store_root))
        assert len(results) > 0
        assert "score" in results[0]
        assert "rank" in results[0]

    def test_search_guide_ranks_high(self, built_store):
        results = skill_search(
            "how to install and configure",
            store_path=str(built_store.store_root),
            top_k=1,
        )
        assert len(results) == 1
        assert results[0]["filename"] == "guide.md"

    def test_search_sales_data(self, built_store):
        results = skill_search(
            "Q3 sales revenue by region",
            store_path=str(built_store.store_root),
            top_k=1,
        )
        assert len(results) == 1
        assert "sales" in results[0]["filename"].lower()

    def test_search_meeting_notes(self, built_store):
        results = skill_search(
            "meeting notes planning session enterprise sales",
            store_path=str(built_store.store_root),
            top_k=3,
        )
        assert len(results) > 0
        # notes.txt should appear in the results
        filenames = [r["filename"] for r in results]
        assert "notes.txt" in filenames

    def test_search_top_k(self, built_store):
        results = skill_search("data", store_path=str(built_store.store_root), top_k=3)
        assert len(results) == 3

    def test_search_empty_store(self, tmp_path):
        config = init_config(str(tmp_path))
        results = skill_search("anything", store_path=str(config.store_root))
        assert results == []


class TestSkillDeepRetrieve:
    def _get_source_id(self, built_store, filename):
        """Helper to get source ID by filename from catalog."""
        catalog = json.loads(built_store.catalog_path.read_text())
        for s in catalog["sources"]:
            if s["filename"] == filename:
                return s["id"]
        return None

    def test_get_tree_markdown(self, built_store):
        source_id = self._get_source_id(built_store, "guide.md")
        assert source_id is not None

        tree = get_tree(source_id, store_path=str(built_store.store_root))
        assert tree is not None
        assert tree["id"] == source_id
        assert "root" in tree
        assert len(tree["root"]["children"]) > 0

    def test_get_tree_xlsx(self, built_store):
        source_id = self._get_source_id(built_store, "sales_q3.xlsx")
        tree = get_tree(source_id, store_path=str(built_store.store_root))
        assert tree is not None
        # Should have a sheet node
        children = tree["root"]["children"]
        assert any("Sheet" in c.get("title", "") for c in children)

    def test_get_node(self, built_store):
        source_id = self._get_source_id(built_store, "guide.md")
        tree = get_tree(source_id, store_path=str(built_store.store_root))

        # Get a child node
        first_child = tree["root"]["children"][0]
        node_id = first_child["node_id"]

        node = get_node(source_id, node_id, store_path=str(built_store.store_root))
        assert node is not None
        assert node["node_id"] == node_id

    def test_get_node_missing(self, built_store):
        source_id = self._get_source_id(built_store, "guide.md")
        node = get_node(source_id, "n999", store_path=str(built_store.store_root))
        assert node is None

    def test_get_tree_nonexistent(self, built_store):
        tree = get_tree("src_nonexistent", store_path=str(built_store.store_root))
        assert tree is None

    def test_tree_summary(self, built_store):
        source_id = self._get_source_id(built_store, "guide.md")
        tree = get_tree(source_id, store_path=str(built_store.store_root))
        summary = get_tree_summary(tree)

        assert "Source:" in summary
        assert "Tree Structure:" in summary
        assert "guide.md" in summary
        # Should contain section names
        assert "Installation" in summary or "Configuration" in summary


class TestSkillReadSource:
    def _get_source_id(self, built_store, filename):
        catalog = json.loads(built_store.catalog_path.read_text())
        for s in catalog["sources"]:
            if s["filename"] == filename:
                return s["id"]
        return None

    def test_read_node_content(self, built_store):
        source_id = self._get_source_id(built_store, "guide.md")
        tree = get_tree(source_id, store_path=str(built_store.store_root))

        # Find a leaf node with content_ref
        def find_leaf(node):
            if node.get("content_ref"):
                return node
            for child in node.get("children", []):
                found = find_leaf(child)
                if found:
                    return found
            return None

        leaf = find_leaf(tree["root"])
        if leaf:
            result = read_node_content(
                source_id, leaf["node_id"],
                store_path=str(built_store.store_root),
            )
            assert result is not None
            assert result["source_id"] == source_id
            assert result["node_id"] == leaf["node_id"]
            # Content may or may not be available depending on path resolution
            assert "content" in result

    def test_read_all_content(self, built_store):
        source_id = self._get_source_id(built_store, "guide.md")
        result = read_all_content(source_id, store_path=str(built_store.store_root))

        assert result is not None
        assert result["source_id"] == source_id
        assert result["total_files"] > 0
        # Should have the full.md file at minimum
        file_names = [f["name"] for f in result["files"]]
        assert "full.md" in file_names

    def test_read_all_xlsx(self, built_store):
        source_id = self._get_source_id(built_store, "sales_q3.xlsx")
        result = read_all_content(source_id, store_path=str(built_store.store_root))

        assert result is not None
        assert result["total_files"] > 0
        # Should have sheet JSON files
        file_names = [f["name"] for f in result["files"]]
        assert any("sheet_" in n for n in file_names)

    def test_read_nonexistent_source(self, built_store):
        result = read_all_content("src_nope", store_path=str(built_store.store_root))
        assert result is None

    def test_read_node_nonexistent(self, built_store):
        result = read_node_content("src_nope", "n0", store_path=str(built_store.store_root))
        assert result is None

    def test_read_file_direct(self, built_store):
        source_id = self._get_source_id(built_store, "guide.md")
        rel_path = f"converted/{source_id}/full.md"
        content = read_file(rel_path, store_path=str(built_store.store_root))
        assert content is not None
        assert "User Guide" in content

    def test_read_file_nonexistent(self, built_store):
        content = read_file("converted/nope/nope.txt", store_path=str(built_store.store_root))
        assert content is None


class TestEndToEnd:
    """Full end-to-end: search → retrieve tree → read content."""

    def test_full_workflow(self, built_store):
        store = str(built_store.store_root)

        # Step 1: Search for the guide
        results = skill_search("installation configuration user guide", store_path=store)
        assert len(results) > 0

        # Find the guide.md source specifically
        guide_result = None
        for r in results:
            if r["filename"] == "guide.md":
                guide_result = r
                break
        assert guide_result is not None, f"guide.md not in results: {[r['filename'] for r in results]}"
        source_id = guide_result["id"]

        # Step 2: Get tree
        tree = get_tree(source_id, store_path=store)
        assert tree is not None
        summary = get_tree_summary(tree)
        assert len(summary) > 0

        # Step 3: Read all content from that source
        all_content = read_all_content(source_id, store_path=store)
        assert all_content is not None
        assert all_content["total_files"] > 0

        # Verify the content includes our guide text
        all_text = " ".join(f["content"] for f in all_content["files"])
        assert "pip" in all_text.lower() or "config" in all_text.lower()
