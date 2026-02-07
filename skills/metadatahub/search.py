#!/usr/bin/env python3
"""MetadataHub Search — Tier 1 vector similarity search.

Usage:
    python search.py "What was Q3 revenue?"
    python search.py "API authentication" --top-k 3
    python search.py "sales data" --store /path/to/store --json

Returns ranked source documents matching the query.
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path for imports
_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root))

from scripts.config import Config
from scripts.build_vectors import search as vector_search


def search(query: str, store_path: str = ".", top_k: int = 5) -> list[dict]:
    """Search the vector index for matching sources.

    Args:
        query: Natural language search query.
        store_path: Path to the MetadataHub store root.
        top_k: Number of results to return.

    Returns:
        List of result dicts with: id, filename, summary, score, rank
    """
    config = Config(store_path=store_path)
    return vector_search(query, config.vector_store_path, top_k=top_k)


def main():
    parser = argparse.ArgumentParser(
        description="Search MetadataHub for relevant documents",
    )
    parser.add_argument("query", type=str, help="Natural language search query")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument("--store", type=str, default=".", help="Store root path")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")

    args = parser.parse_args()
    results = search(args.query, store_path=args.store, top_k=args.top_k)

    if args.json_output:
        print(json.dumps(results, indent=2))
    else:
        if not results:
            print("No results found. Is the index built?")
            sys.exit(1)

        print(f"Search: \"{args.query}\" — {len(results)} results\n")
        for r in results:
            score = r.get("score", 0)
            print(f"  #{r['rank']}  [{score:.3f}]  {r['filename']}")
            print(f"       ID: {r['id']}")
            summary = r.get("summary", "")
            if summary:
                print(f"       {summary[:80]}")
            print()


if __name__ == "__main__":
    main()
