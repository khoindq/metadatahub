"""Incremental re-indexing - only process new/changed files."""

import hashlib
import json
from pathlib import Path
from typing import Dict, Set, Tuple


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of file contents."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def load_hash_index(store_root: Path) -> Dict[str, str]:
    """Load existing file hash index from store."""
    hash_file = store_root / "hash_index.json"
    if hash_file.exists():
        with open(hash_file) as f:
            return json.load(f)
    return {}


def save_hash_index(store_root: Path, hash_index: Dict[str, str]):
    """Save file hash index to store."""
    hash_file = store_root / "hash_index.json"
    with open(hash_file, 'w') as f:
        json.dump(hash_index, f, indent=2)


def get_changed_files(
    input_files: list[Path],
    store_root: Path
) -> Tuple[list[Path], list[Path], list[str]]:
    """
    Compare input files against stored hashes.
    
    Returns:
        - new_files: Files not in index
        - changed_files: Files with different hash
        - unchanged_ids: Source IDs of unchanged files (to skip)
    """
    hash_index = load_hash_index(store_root)
    
    new_files = []
    changed_files = []
    unchanged_ids = []
    
    # Build path -> source_id mapping from catalog
    catalog_file = store_root / "catalog.json"
    path_to_id = {}
    if catalog_file.exists():
        with open(catalog_file) as f:
            catalog = json.load(f)
            for source in catalog.get("sources", []):
                if "original_path" in source:
                    path_to_id[source["original_path"]] = source["id"]
    
    for file_path in input_files:
        current_hash = compute_file_hash(file_path)
        stored_hash = hash_index.get(str(file_path))
        
        if stored_hash is None:
            new_files.append(file_path)
        elif stored_hash != current_hash:
            changed_files.append(file_path)
        else:
            # Unchanged - get source ID to skip
            source_id = path_to_id.get(str(file_path))
            if source_id:
                unchanged_ids.append(source_id)
    
    return new_files, changed_files, unchanged_ids


def update_hash_index(store_root: Path, files: list[Path]):
    """Update hash index with new file hashes."""
    hash_index = load_hash_index(store_root)
    
    for file_path in files:
        hash_index[str(file_path)] = compute_file_hash(file_path)
    
    save_hash_index(store_root, hash_index)


def remove_from_catalog(store_root: Path, source_ids: list[str]):
    """Remove sources from catalog (for re-indexing changed files)."""
    catalog_file = store_root / "catalog.json"
    if not catalog_file.exists():
        return
    
    with open(catalog_file) as f:
        catalog = json.load(f)
    
    catalog["sources"] = [
        s for s in catalog.get("sources", [])
        if s["id"] not in source_ids
    ]
    
    with open(catalog_file, 'w') as f:
        json.dump(catalog, f, indent=2)
