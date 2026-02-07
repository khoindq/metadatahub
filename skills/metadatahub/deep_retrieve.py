#!/usr/bin/env python3
"""MetadataHub Deep Retrieve — Tier 2 tree-based retrieval.

Usage:
    python deep_retrieve.py src_a1b2c3
    python deep_retrieve.py src_a1b2c3 --node n2.1
    python deep_retrieve.py src_a1b2c3 --query "revenue breakdown"

Loads the tree index for a source and returns the structure
for agent reasoning, or a specific node's details.
"""

import argparse
import json
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root))

from scripts.config import Config
from scripts.build_tree import load_tree, find_node


def get_tree(source_id: str, store_path: str = ".") -> dict | None:
    """Load the full tree index for a source.

    Args:
        source_id: The source ID (e.g., "src_a1b2c3").
        store_path: Path to the MetadataHub store root.

    Returns:
        The tree dict, or None if not found.
    """
    config = Config(store_path=store_path)
    tree_path = config.tree_index_path / f"{source_id}.tree.json"
    return load_tree(tree_path)


def get_node(source_id: str, node_id: str, store_path: str = ".") -> dict | None:
    """Get a specific node from a source's tree.

    Args:
        source_id: The source ID.
        node_id: The node ID (e.g., "n2.1").
        store_path: Store root path.

    Returns:
        The node dict, or None if not found.
    """
    tree = get_tree(source_id, store_path=store_path)
    if tree is None:
        return None
    return find_node(tree, node_id)


def get_tree_summary(tree: dict) -> str:
    """Generate a readable summary of a tree for agent reasoning.

    Returns a formatted text representation the agent can reason over
    to decide which node to visit.
    """
    lines = []
    root = tree.get("root", {})

    lines.append(f"Source: {tree.get('id', '?')}")
    lines.append(f"Title: {root.get('title', '?')}")
    lines.append(f"Summary: {root.get('summary', '')}")
    lines.append("")
    lines.append("Tree Structure:")

    def _walk(node, depth=0):
        indent = "  " * depth
        node_id = node.get("node_id", "?")
        title = node.get("title", "?")
        summary = node.get("summary", "")
        content_ref = node.get("content_ref")

        line = f"{indent}[{node_id}] {title}"
        if content_ref:
            line += f"  → {content_ref}"
        lines.append(line)

        if summary and depth > 0:
            lines.append(f"{indent}     {summary[:100]}")

        for child in node.get("children", []):
            _walk(child, depth + 1)

    _walk(root)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Retrieve tree index for a MetadataHub source",
    )
    parser.add_argument("source_id", type=str, help="Source ID (e.g., src_a1b2c3)")
    parser.add_argument("--node", type=str, help="Get a specific node by ID")
    parser.add_argument("--store", type=str, default=".", help="Store root path")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")
    parser.add_argument("--summary", action="store_true", help="Show readable tree summary")

    args = parser.parse_args()

    if args.node:
        result = get_node(args.source_id, args.node, store_path=args.store)
        if result is None:
            print(f"Node {args.node} not found in source {args.source_id}")
            sys.exit(1)
    else:
        result = get_tree(args.source_id, store_path=args.store)
        if result is None:
            print(f"Tree not found for source {args.source_id}")
            sys.exit(1)

    if args.summary and not args.node:
        print(get_tree_summary(result))
    elif args.json_output:
        print(json.dumps(result, indent=2))
    else:
        if args.node:
            print(json.dumps(result, indent=2))
        else:
            print(get_tree_summary(result))


if __name__ == "__main__":
    main()
