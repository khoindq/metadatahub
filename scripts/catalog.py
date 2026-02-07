"""catalog.json creation and management.

The catalog is the master registry linking sources to their
converted files, tree indexes, strategies, summaries, and tags.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


CATALOG_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_catalog() -> dict:
    """Create a fresh empty catalog."""
    return {
        "version": CATALOG_VERSION,
        "last_updated": _now_iso(),
        "sources": [],
    }


def load_catalog(path: Path) -> dict:
    """Load catalog from disk, or create a new one if it doesn't exist."""
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return create_catalog()


def save_catalog(catalog: dict, path: Path):
    """Save catalog to disk."""
    catalog["last_updated"] = _now_iso()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, indent=2, default=str) + "\n", encoding="utf-8")


def find_source(catalog: dict, source_id: str) -> Optional[dict]:
    """Find a source entry by ID."""
    for source in catalog["sources"]:
        if source["id"] == source_id:
            return source
    return None


def find_source_by_filename(catalog: dict, filename: str) -> Optional[dict]:
    """Find a source entry by filename."""
    for source in catalog["sources"]:
        if source["filename"] == filename:
            return source
    return None


def add_source(catalog: dict, file_card: dict, converted_path: str = "",
               tree_path: str = "") -> dict:
    """Add or update a source entry in the catalog.

    Args:
        catalog: The catalog dict.
        file_card: File card from detect.py (with strategy from sample.py).
        converted_path: Path to converted files directory.
        tree_path: Path to tree index file.

    Returns:
        The created/updated source entry.
    """
    strategy = file_card.get("strategy") or {}

    entry = {
        "id": file_card["id"],
        "filename": file_card["filename"],
        "original_path": file_card.get("path", ""),
        "type": file_card["type"],
        "category": file_card.get("category", "unknown"),
        "size_kb": file_card["size_kb"],
        "strategy": strategy.get("recommended_approach", "unknown"),
        "tree_path": tree_path,
        "converted_path": converted_path,
        "indexed_at": _now_iso(),
        "summary": strategy.get("summary", ""),
        "tags": strategy.get("tags", []),
        "doc_nature": strategy.get("doc_nature", ""),
        "sampled": file_card.get("sampled", False),
    }

    # Update existing or append new
    existing = find_source(catalog, file_card["id"])
    if existing:
        idx = catalog["sources"].index(existing)
        catalog["sources"][idx] = entry
    else:
        catalog["sources"].append(entry)

    return entry


def remove_source(catalog: dict, source_id: str) -> bool:
    """Remove a source from the catalog. Returns True if found and removed."""
    for i, source in enumerate(catalog["sources"]):
        if source["id"] == source_id:
            catalog["sources"].pop(i)
            return True
    return False


def list_sources(catalog: dict, category: Optional[str] = None,
                 tag: Optional[str] = None) -> list[dict]:
    """List sources, optionally filtered by category or tag."""
    sources = catalog["sources"]
    if category:
        sources = [s for s in sources if s.get("category") == category]
    if tag:
        sources = [s for s in sources if tag in s.get("tags", [])]
    return sources


def catalog_summary(catalog: dict) -> dict:
    """Return a summary of the catalog."""
    sources = catalog["sources"]
    categories = {}
    for s in sources:
        cat = s.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "version": catalog["version"],
        "last_updated": catalog["last_updated"],
        "total_sources": len(sources),
        "by_category": categories,
        "sampled_count": sum(1 for s in sources if s.get("sampled")),
    }
