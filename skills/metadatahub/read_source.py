#!/usr/bin/env python3
"""MetadataHub Read Source — fetch content from converted files.

Usage:
    python read_source.py src_a1b2c3 n2.1
    python read_source.py src_a1b2c3 --file converted/src_a1b2c3/pages_15-22.txt
    python read_source.py src_a1b2c3 --all

Reads actual content from the converted files referenced by tree nodes.
"""

import argparse
import json
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root))

from scripts.config import Config
from scripts.build_tree import load_tree, find_node


def read_node_content(
    source_id: str,
    node_id: str,
    store_path: str = ".",
) -> dict | None:
    """Read the content referenced by a tree node.

    Args:
        source_id: The source ID.
        node_id: The tree node ID.
        store_path: Store root path.

    Returns:
        dict with: node_id, title, content_ref, content, or None.
    """
    config = Config(store_path=store_path)

    tree_path = config.tree_index_path / f"{source_id}.tree.json"
    tree = load_tree(tree_path)
    if tree is None:
        return None

    node = find_node(tree, node_id)
    if node is None:
        return None

    content_ref = node.get("content_ref")
    content = ""

    if content_ref:
        content_path = config.store_root / content_ref
        if content_path.exists():
            # Handle JSON and text files differently
            if content_path.suffix == ".json":
                content = content_path.read_text(encoding="utf-8")
                try:
                    content = json.dumps(json.loads(content), indent=2)
                except json.JSONDecodeError:
                    pass
            else:
                content = content_path.read_text(encoding="utf-8", errors="ignore")

    return {
        "source_id": source_id,
        "node_id": node_id,
        "title": node.get("title", ""),
        "summary": node.get("summary", ""),
        "content_ref": content_ref,
        "content": content,
    }


def read_file(filepath: str, store_path: str = ".") -> str | None:
    """Read a specific converted file by relative path.

    Args:
        filepath: Relative path from store root (e.g., converted/src_xxx/pages_1-5.txt).
        store_path: Store root path.

    Returns:
        File contents as string, or None if not found.
    """
    config = Config(store_path=store_path)
    full_path = config.store_root / filepath

    if not full_path.exists():
        return None

    if full_path.suffix == ".json":
        content = full_path.read_text(encoding="utf-8")
        try:
            return json.dumps(json.loads(content), indent=2)
        except json.JSONDecodeError:
            return content

    return full_path.read_text(encoding="utf-8", errors="ignore")


def read_all_content(source_id: str, store_path: str = ".") -> dict | None:
    """Read all converted content for a source.

    Args:
        source_id: The source ID.
        store_path: Store root path.

    Returns:
        dict with: source_id, files (list of {name, content})
    """
    config = Config(store_path=store_path)
    source_dir = config.converted_path / source_id

    if not source_dir.exists():
        return None

    files = []
    for f in sorted(source_dir.iterdir()):
        if f.is_file():
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                files.append({"name": f.name, "content": content})
            except Exception:
                files.append({"name": f.name, "content": "(unreadable)"})

    return {
        "source_id": source_id,
        "files": files,
        "total_files": len(files),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Read content from MetadataHub converted files",
    )
    parser.add_argument("source_id", type=str, help="Source ID")
    parser.add_argument("node_id", nargs="?", type=str, help="Tree node ID to read")
    parser.add_argument("--file", type=str, help="Read a specific file by relative path")
    parser.add_argument("--all", action="store_true", help="Read all content for this source")
    parser.add_argument("--store", type=str, default=".", help="Store root path")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    args = parser.parse_args()

    if args.file:
        content = read_file(args.file, store_path=args.store)
        if content is None:
            print(f"File not found: {args.file}")
            sys.exit(1)
        print(content)

    elif args.all:
        result = read_all_content(args.source_id, store_path=args.store)
        if result is None:
            print(f"No converted files for source {args.source_id}")
            sys.exit(1)
        if args.json_output:
            print(json.dumps(result, indent=2))
        else:
            print(f"Source: {args.source_id} — {result['total_files']} files\n")
            for f in result["files"]:
                print(f"--- {f['name']} ---")
                print(f["content"][:2000])
                if len(f["content"]) > 2000:
                    print(f"[...truncated, {len(f['content'])} chars total]")
                print()

    elif args.node_id:
        result = read_node_content(args.source_id, args.node_id, store_path=args.store)
        if result is None:
            print(f"Node {args.node_id} not found in source {args.source_id}")
            sys.exit(1)
        if args.json_output:
            print(json.dumps(result, indent=2))
        else:
            print(f"[{result['node_id']}] {result['title']}")
            print(f"Summary: {result['summary']}")
            if result["content_ref"]:
                print(f"File: {result['content_ref']}")
            print(f"\n{result['content']}")

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
