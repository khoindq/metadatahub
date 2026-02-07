"""Tree index builder.

Generates hierarchical JSON tree indexes per source document.
Uses Claude for intelligent tree generation when available,
falls back to heuristic tree building from converter output.

Each tree is stored as tree_index/<source_id>.tree.json
"""

import json
from pathlib import Path
from typing import Optional

from scripts.claude_client import ClaudeClient
from scripts.converters import convert_file


TREE_SYSTEM_PROMPT = """You are a document indexing expert. Your job is to produce a hierarchical tree index of a document.

You MUST respond with valid JSON only — no explanations, no markdown, just the JSON object.

The JSON tree follows this schema:
{
  "id": "<source_id>",
  "root": {
    "node_id": "n0",
    "title": "<document title>",
    "summary": "<1-2 sentence summary of the entire document>",
    "children": [
      {
        "node_id": "n1",
        "title": "<section title>",
        "summary": "<1-2 sentence summary of this section>",
        "children": [],
        "content_ref": "<relative path to content file, or null>"
      }
    ]
  }
}

Rules:
- Every node must have: node_id, title, summary, children
- Leaf nodes should have content_ref pointing to the converted file
- Node IDs use dotted notation: n1, n1.1, n1.2, n2, etc.
- Keep summaries concise but informative
- Aim for 2-3 levels of depth for typical documents
- Group related content logically"""

TREE_USER_TEMPLATE = """Build a tree index for this document.

**Source ID:** {source_id}
**Filename:** {filename}
**Type:** {file_type}
**Strategy:** {strategy}

**Available content files:**
{content_files}

**Document sample/structure:**
```
{sample}
```

Respond with the tree JSON only."""


def build_tree_for_source(
    source_entry: dict,
    converted_dir: Path,
    tree_index_dir: Path,
    client: Optional[ClaudeClient] = None,
    converter_result: Optional[dict] = None,
) -> dict:
    """Build a tree index for a single source.

    Args:
        source_entry: Catalog source entry dict.
        converted_dir: Base directory for converted files.
        tree_index_dir: Directory to write tree JSON files.
        client: ClaudeClient for AI tree generation. If None, uses heuristic.
        converter_result: Pre-computed converter result (avoids re-converting).

    Returns:
        The tree dict that was written to disk.
    """
    source_id = source_entry["id"]
    file_type = source_entry["type"]
    category = source_entry.get("category", "unknown")
    strategy = source_entry.get("strategy", "tree_index")

    # Determine output dir for this source's converted files
    source_converted_dir = converted_dir / source_id

    # Get or build converter result for structure info
    if converter_result is None and source_converted_dir.exists():
        # Read existing converted files to understand structure
        converter_result = _read_converted_structure(source_converted_dir)

    # Build the tree
    if client is not None:
        try:
            tree = _build_tree_with_claude(
                source_entry, source_converted_dir, converter_result, client
            )
        except Exception as e:
            print(f"  Warning: Claude tree generation failed for {source_id}: {e}")
            tree = _build_tree_heuristic(
                source_entry, source_converted_dir, converter_result
            )
    else:
        tree = _build_tree_heuristic(
            source_entry, source_converted_dir, converter_result
        )

    # Write tree to disk
    tree_index_dir.mkdir(parents=True, exist_ok=True)
    tree_path = tree_index_dir / f"{source_id}.tree.json"
    tree_path.write_text(json.dumps(tree, indent=2, default=str) + "\n", encoding="utf-8")

    return tree


def _build_tree_with_claude(
    source_entry: dict,
    source_converted_dir: Path,
    converter_result: Optional[dict],
    client: ClaudeClient,
) -> dict:
    """Use Claude to generate an intelligent tree index."""
    source_id = source_entry["id"]

    # List converted content files
    content_files = []
    if source_converted_dir.exists():
        for f in sorted(source_converted_dir.iterdir()):
            if f.is_file():
                content_files.append(str(f.relative_to(source_converted_dir.parent.parent)))

    # Build a sample of the document structure
    sample = _get_structure_sample(source_converted_dir, converter_result)

    prompt = TREE_USER_TEMPLATE.format(
        source_id=source_id,
        filename=source_entry["filename"],
        file_type=source_entry["type"],
        strategy=source_entry.get("strategy", "tree_index"),
        content_files="\n".join(f"- {f}" for f in content_files) or "(none)",
        sample=sample[:3000],
    )

    result = client.send_json_message(
        prompt=prompt,
        system=TREE_SYSTEM_PROMPT,
        max_tokens=4096,
    )

    if result.get("parsed"):
        tree = result["parsed"]
        if "root" in tree:
            tree["id"] = source_id
            return tree

    # Fall back to heuristic if Claude's response is unusable
    return _build_tree_heuristic(source_entry, source_converted_dir, converter_result)


def _build_tree_heuristic(
    source_entry: dict,
    source_converted_dir: Path,
    converter_result: Optional[dict],
) -> dict:
    """Build a tree index from converter output using heuristics."""
    source_id = source_entry["id"]
    file_type = source_entry["type"]
    category = source_entry.get("category", "unknown")
    strategy = source_entry.get("strategy", "tree_index")
    summary = source_entry.get("summary", f"File: {source_entry['filename']}")

    if strategy == "schema_index" or category == "spreadsheet":
        return _build_schema_tree(source_id, source_entry, source_converted_dir, converter_result)
    elif strategy == "symbol_index" or category == "code":
        return _build_code_tree(source_id, source_entry, source_converted_dir, converter_result)
    else:
        return _build_document_tree(source_id, source_entry, source_converted_dir, converter_result)


def _build_document_tree(
    source_id: str,
    source_entry: dict,
    source_converted_dir: Path,
    converter_result: Optional[dict],
) -> dict:
    """Build tree for document-type files (PDF, Markdown, text)."""
    summary = source_entry.get("summary", f"File: {source_entry['filename']}")
    children = []

    # Check for sections (from markdown converter)
    if converter_result and "sections" in converter_result:
        sections = converter_result["sections"]
        # Build tree from heading hierarchy
        children = _sections_to_tree_nodes(sections, source_converted_dir)
    # Check for page_texts (from PDF converter)
    elif converter_result and "page_texts" in converter_result:
        page_texts = converter_result["page_texts"]
        children = _pages_to_tree_nodes(page_texts, source_id, source_converted_dir)
    # Fall back to listing converted files
    elif source_converted_dir.exists():
        children = _files_to_tree_nodes(source_converted_dir)

    return {
        "id": source_id,
        "root": {
            "node_id": "n0",
            "title": source_entry["filename"],
            "summary": summary,
            "children": children,
        },
    }


def _build_schema_tree(
    source_id: str,
    source_entry: dict,
    source_converted_dir: Path,
    converter_result: Optional[dict],
) -> dict:
    """Build schema tree for Excel/CSV/tabular data.
    
    Creates a deeper tree structure with hints for navigation:
    - Root: filename with overall summary
    - Level 1: Sheets with column info hints
    - Each sheet includes row_labels and column info for hint generation
    """
    from scripts.converters.xlsx_converter import get_sheet_hint
    
    summary = source_entry.get("summary", f"Spreadsheet: {source_entry['filename']}")
    children = []

    if converter_result and "sheets" in converter_result:
        for i, sheet in enumerate(converter_result["sheets"]):
            node_id = f"n{i + 1}"
            
            # Generate rich hint for the sheet
            hint = get_sheet_hint(sheet)
            
            sheet_summary = (
                f"{sheet['row_count']} rows, {sheet['column_count']} columns. "
                f"Headers: {', '.join(sheet['headers'][:8])}"
            )
            if len(sheet["headers"]) > 8:
                sheet_summary += f" (+{len(sheet['headers']) - 8} more)"

            # Build content_ref from converted dir - prefer markdown
            safe_name = sheet["name"].replace("/", "_").replace(" ", "_").lower()
            content_ref = None
            md_candidate = source_converted_dir / f"sheet_{safe_name}.md"
            json_candidate = source_converted_dir / f"sheet_{safe_name}.json"
            
            if md_candidate.exists():
                content_ref = str(md_candidate.relative_to(source_converted_dir.parent.parent))
            elif json_candidate.exists():
                content_ref = str(json_candidate.relative_to(source_converted_dir.parent.parent))

            # Build preview from sample data
            preview = ""
            if sheet.get("sample_rows"):
                first_row = sheet["sample_rows"][0]
                preview = ", ".join(f"{k}: {v}" for k, v in list(first_row.items())[:4])

            child = {
                "node_id": node_id,
                "title": f"Sheet: {sheet['name']}",
                "summary": sheet_summary,
                "hint": hint,
                "children": [],
                "content_ref": content_ref,
                # Store metadata for search output
                "headers": sheet.get("headers", []),
                "row_labels": sheet.get("row_labels", [])[:10],
            }
            if preview:
                child["preview"] = preview

            children.append(child)
    elif source_converted_dir.exists():
        children = _files_to_tree_nodes(source_converted_dir)

    total_rows = sum(
        s.get("row_count", 0) for s in (converter_result or {}).get("sheets", [])
    )
    sheet_count = len((converter_result or {}).get("sheets", []))

    return {
        "id": source_id,
        "root": {
            "node_id": "n0",
            "title": source_entry["filename"],
            "summary": f"{summary} ({sheet_count} sheets, {total_rows} total rows)",
            "children": children,
        },
    }


def _build_code_tree(
    source_id: str,
    source_entry: dict,
    source_converted_dir: Path,
    converter_result: Optional[dict],
) -> dict:
    """Build symbol tree for code files."""
    summary = source_entry.get("summary", f"Code: {source_entry['filename']}")

    # For code files, parse basic symbols from converted text
    children = []
    content_ref = None

    if source_converted_dir.exists():
        files = sorted(source_converted_dir.iterdir())
        if files:
            content_ref = str(files[0].relative_to(source_converted_dir.parent.parent))
            # Try to parse symbols from the first file
            try:
                text = files[0].read_text(encoding="utf-8", errors="ignore")
                children = _parse_code_symbols(text)
            except Exception:
                pass

    root_node = {
        "node_id": "n0",
        "title": source_entry["filename"],
        "summary": summary,
        "children": children,
    }
    if content_ref:
        root_node["content_ref"] = content_ref

    return {
        "id": source_id,
        "root": root_node,
    }


def _sections_to_tree_nodes(sections: list[dict], source_converted_dir: Path) -> list[dict]:
    """Convert markdown sections to tree nodes with hierarchy."""
    if not sections:
        return []

    nodes = []
    node_counter = [0]

    def make_node(section: dict) -> dict:
        node_counter[0] += 1
        safe_title = section["title"].lower()
        for ch in " /\\!@#$%^&*()":
            safe_title = safe_title.replace(ch, "_")
        safe_title = safe_title[:50]

        content_ref = None
        candidate = source_converted_dir / f"section_{safe_title}.md"
        if candidate.exists():
            content_ref = str(candidate.relative_to(source_converted_dir.parent.parent))

        return {
            "node_id": f"n{node_counter[0]}",
            "title": section["title"],
            "summary": f"Section: {section['title']} (lines {section['line_start']}-{section['line_end']})",
            "children": [],
            "content_ref": content_ref,
        }

    # Build hierarchy from heading levels
    # Simple approach: level 1/2 headings become top-level, deeper ones nest
    stack = []  # (level, node)
    for section in sections:
        node = make_node(section)
        level = section["level"]

        # Pop stack until we find a parent with lower level
        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            stack[-1][1]["children"].append(node)
        else:
            nodes.append(node)

        stack.append((level, node))

    return nodes


def _pages_to_tree_nodes(
    page_texts: list[tuple], source_id: str, source_converted_dir: Path,
) -> list[dict]:
    """Convert PDF page texts to tree nodes (grouped in chunks of 5)."""
    nodes = []
    chunk_size = 5
    total_pages = len(page_texts)

    for i in range(0, total_pages, chunk_size):
        chunk = page_texts[i:i + chunk_size]
        start_page = chunk[0][0]
        end_page = chunk[-1][0]
        node_num = (i // chunk_size) + 1

        # Build summary from first ~200 chars of each page in chunk
        preview_parts = []
        for page_num, text in chunk:
            snippet = text[:100].replace("\n", " ").strip()
            if snippet:
                preview_parts.append(snippet)
        preview = "; ".join(preview_parts)[:200]

        content_ref = None
        candidate = source_converted_dir / f"pages_{start_page}-{end_page}.txt"
        if candidate.exists():
            content_ref = str(candidate.relative_to(source_converted_dir.parent.parent))

        nodes.append({
            "node_id": f"n{node_num}",
            "title": f"Pages {start_page}-{end_page}",
            "summary": preview or f"Pages {start_page} to {end_page}",
            "children": [],
            "content_ref": content_ref,
        })

    return nodes


def _files_to_tree_nodes(source_converted_dir: Path) -> list[dict]:
    """Create tree nodes from listing converted files."""
    nodes = []
    for i, f in enumerate(sorted(source_converted_dir.iterdir())):
        if f.is_file() and f.name != "full.txt" and f.name != "full.md":
            content_ref = str(f.relative_to(source_converted_dir.parent.parent))
            nodes.append({
                "node_id": f"n{i + 1}",
                "title": f.stem.replace("_", " ").title(),
                "summary": f"Content from {f.name}",
                "children": [],
                "content_ref": content_ref,
            })
    return nodes


def _parse_code_symbols(text: str) -> list[dict]:
    """Parse basic code symbols (functions/classes) from text."""
    import re

    nodes = []
    node_counter = 0

    # Match Python-style definitions
    patterns = [
        (r'^class\s+(\w+)', "Class"),
        (r'^def\s+(\w+)', "Function"),
        (r'^async\s+def\s+(\w+)', "Async Function"),
    ]

    for line_num, line in enumerate(text.split("\n")):
        stripped = line.strip()
        for pattern, kind in patterns:
            m = re.match(pattern, stripped)
            if m:
                node_counter += 1
                name = m.group(1)
                nodes.append({
                    "node_id": f"n{node_counter}",
                    "title": f"{kind}: {name}",
                    "summary": f"{kind} '{name}' at line {line_num + 1}",
                    "children": [],
                })
                break

    return nodes


def _read_converted_structure(source_converted_dir: Path) -> dict:
    """Read converted files and infer structure."""
    result = {"output_files": []}

    for f in sorted(source_converted_dir.iterdir()):
        if f.is_file():
            result["output_files"].append(str(f))

    # Detect type from files present
    files = list(source_converted_dir.iterdir())
    file_names = [f.name for f in files]

    if any(n.startswith("sheet_") and n.endswith(".json") for n in file_names):
        # Excel-like: load sheet info
        result["sheets"] = []
        for f in files:
            if f.name.startswith("sheet_") and f.suffix == ".json":
                try:
                    sheet_data = json.loads(f.read_text(encoding="utf-8"))
                    result["sheets"].append(sheet_data)
                except Exception:
                    pass

    elif any(n.startswith("pages_") and n.endswith(".txt") for n in file_names):
        # PDF-like: infer page_texts
        result["page_texts"] = []
        for f in sorted(files):
            if f.name.startswith("pages_") and f.suffix == ".txt":
                text = f.read_text(encoding="utf-8", errors="ignore")
                # Extract page numbers from filename
                stem = f.stem  # e.g., pages_1-5
                parts = stem.replace("pages_", "").split("-")
                try:
                    start = int(parts[0])
                    end = int(parts[1]) if len(parts) > 1 else start
                    for p in range(start, end + 1):
                        result["page_texts"].append((p, ""))
                except ValueError:
                    pass

    elif any(n.endswith(".md") for n in file_names):
        # Markdown: extract sections from full.md
        for f in files:
            if f.name == "full.md":
                from scripts.converters.md_converter import _extract_sections
                text = f.read_text(encoding="utf-8")
                result["sections"] = _extract_sections(text.split("\n"))
                result["text"] = text
                break

    return result


def _get_structure_sample(source_converted_dir: Path, converter_result: Optional[dict]) -> str:
    """Get a text sample showing document structure for Claude."""
    if not source_converted_dir.exists():
        return "(no converted files available)"

    parts = []

    # Try full.txt or full.md first
    for name in ("full.txt", "full.md"):
        full_path = source_converted_dir / name
        if full_path.exists():
            text = full_path.read_text(encoding="utf-8", errors="ignore")
            parts.append(text[:2000])
            break

    if not parts:
        # Grab first available file
        for f in sorted(source_converted_dir.iterdir()):
            if f.is_file():
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    parts.append(f"[{f.name}]\n{text[:1000]}")
                except Exception:
                    pass
                if len(parts) >= 3:
                    break

    return "\n\n".join(parts) if parts else "(empty)"


def load_tree(tree_path: Path) -> Optional[dict]:
    """Load a tree index from disk."""
    tree_path = Path(tree_path)
    if tree_path.exists():
        return json.loads(tree_path.read_text(encoding="utf-8"))
    return None


def find_node(tree: dict, node_id: str) -> Optional[dict]:
    """Find a node by ID in a tree (depth-first search)."""
    def _search(node: dict) -> Optional[dict]:
        if node.get("node_id") == node_id:
            return node
        for child in node.get("children", []):
            found = _search(child)
            if found:
                return found
        return None

    root = tree.get("root", tree)
    return _search(root)
