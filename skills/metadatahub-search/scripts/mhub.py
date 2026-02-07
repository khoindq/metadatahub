#!/usr/bin/env python3
"""MetadataHub - Natural language interface for knowledge index."""

import argparse
import re
import subprocess
import sys
from pathlib import Path

METADATAHUB_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(METADATAHUB_ROOT))

DEFAULT_STORE = Path.home() / ".metadatahub" / "store"

# NLP patterns
INGEST_PATTERNS = [
    r"(?:nộp|thêm|add|index|ingest)\s+(?:file|folder|thư mục)?\s*(.+?)(?:\s+vào|\s+into|\s*$)",
    r"(?:nộp|thêm|add)\s+(.+?)\s+(?:vào\s+)?(?:index|knowledge)",
    r"index\s+(?:tất cả\s+)?(?:file\s+)?(?:trong\s+)?(.+)",
]

RETRIEVE_PATTERNS = [
    r"(?:xem|show|view)\s+(?:cấu trúc|structure|tree)\s+(?:của\s+)?(src_\w+)",
    r"(?:retrieve|lấy)\s+(src_\w+)",
]

READ_PATTERNS = [
    r"(?:đọc|read)\s+(?:node\s+)?(\w+)\s+(?:của|of|from)\s+(src_\w+)",
    r"(?:đọc|read)\s+(src_\w+)\s+(\w+)",
]

SEARCH_PATTERNS = [
    r"(?:tìm|search|find)\s+(?:thông tin\s+)?(?:về\s+)?(.+)",
    r"(?:file|tài liệu)\s+(?:nào\s+)?(?:nói\s+)?(?:về\s+)?(.+)",
    r"(?:có\s+)?(?:gì\s+)?(?:về|about)\s+(.+)",
]


def parse_intent(query: str):
    """Parse natural language query to determine intent."""
    query = query.strip().lower()
    
    # Check ingest
    for pattern in INGEST_PATTERNS:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            path = match.group(1).strip().strip('"\'')
            return ("ingest", path)
    
    # Check retrieve
    for pattern in RETRIEVE_PATTERNS:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return ("retrieve", match.group(1))
    
    # Check read
    for pattern in READ_PATTERNS:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            groups = match.groups()
            if groups[0].startswith("src_"):
                return ("read", groups[0], groups[1])
            return ("read", groups[1], groups[0])
    
    # Check search
    for pattern in SEARCH_PATTERNS:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return ("search", match.group(1).strip())
    
    # Default to search
    return ("search", query)


def ingest(input_path: Path, store_path: Path):
    """Ingest files into the index."""
    print(f"📥 Đang nộp: {input_path}")
    cmd = [
        sys.executable, "-m", "scripts.ingest",
        str(input_path), "--store", str(store_path)
    ]
    subprocess.run(cmd, cwd=str(METADATAHUB_ROOT))


def search(query: str, store_path: Path, limit: int = 5):
    """Search for relevant sources."""
    from skills.metadatahub.search import search as mhub_search
    
    print(f"🔍 Tìm kiếm: '{query}'\n")
    results = mhub_search(query, store_path=str(store_path))
    
    if not results:
        print("Không tìm thấy kết quả.")
        return
    
    for i, r in enumerate(results[:limit], 1):
        print(f"{i}. [{r['id']}] {r['filename']} (score: {r['score']:.3f})")
        print(f"   {r['summary']}\n")


def retrieve(source_id: str, store_path: Path):
    """Get tree structure of a source."""
    print(f"🌳 Cấu trúc: {source_id}\n")
    cmd = [
        sys.executable, "-m", "skills.metadatahub.deep_retrieve",
        source_id, "--store", str(store_path)
    ]
    subprocess.run(cmd, cwd=str(METADATAHUB_ROOT))


def read(source_id: str, node_id: str, store_path: Path):
    """Read content from a specific node."""
    print(f"📖 Đọc: {source_id} → {node_id}\n")
    cmd = [
        sys.executable, "-m", "skills.metadatahub.read_source",
        source_id, node_id, "--store", str(store_path)
    ]
    subprocess.run(cmd, cwd=str(METADATAHUB_ROOT))


def main():
    parser = argparse.ArgumentParser(
        description="MetadataHub - Natural language knowledge search"
    )
    parser.add_argument("query", nargs="*", help="Natural language query")
    parser.add_argument("--store", "-s", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--limit", "-n", type=int, default=5)
    
    args = parser.parse_args()
    
    if not args.query:
        parser.print_help()
        print("\nExamples:")
        print('  mhub.py "nộp file report.pdf"')
        print('  mhub.py "tìm thông tin về doanh thu"')
        print('  mhub.py "xem cấu trúc src_abc123"')
        sys.exit(1)
    
    query = " ".join(args.query)
    intent = parse_intent(query)
    
    if intent[0] == "ingest":
        path = Path(intent[1])
        if not path.exists():
            print(f"❌ Không tìm thấy: {path}")
            sys.exit(1)
        args.store.mkdir(parents=True, exist_ok=True)
        ingest(path, args.store)
    
    elif intent[0] == "retrieve":
        if not args.store.exists():
            print(f"❌ Store chưa tồn tại. Hãy nộp file trước.")
            sys.exit(1)
        retrieve(intent[1], args.store)
    
    elif intent[0] == "read":
        if not args.store.exists():
            print(f"❌ Store chưa tồn tại. Hãy nộp file trước.")
            sys.exit(1)
        read(intent[1], intent[2], args.store)
    
    else:  # search
        if not args.store.exists():
            print(f"❌ Store chưa tồn tại. Hãy nộp file trước.")
            sys.exit(1)
        search(intent[1], args.store, args.limit)


if __name__ == "__main__":
    main()
