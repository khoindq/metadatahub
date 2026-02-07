"""Batch ingest CLI — the full MetadataHub indexing pipeline.

Usage:
    python -m scripts.ingest ./inbox/
    python -m scripts.ingest ./inbox/ --store ./my_store
    python -m scripts.ingest ./inbox/ --no-vectors  (skip FAISS rebuild)
    python -m scripts.ingest path/to/file.pdf       (single file)

Pipeline per file:
    detect → sample → convert → build_tree → catalog_update

After all files:
    build_vectors (FAISS index from updated catalog)
"""

import argparse
import sys
import time
from pathlib import Path

from scripts.config import Config, init_config
from scripts.detect import detect_file, detect_directory
from scripts.sample import sample_file
from scripts.converters import convert_file
from scripts.build_tree import build_tree_for_source
from scripts.catalog import load_catalog, save_catalog, add_source
from scripts.build_vectors import build_index


def ingest_file(
    filepath: Path,
    config: Config,
    catalog: dict,
    client=None,
    verbose: bool = True,
) -> dict:
    """Ingest a single file through the full pipeline.

    Returns the catalog source entry, or None on failure.
    """
    filepath = Path(filepath).resolve()
    filename = filepath.name

    if verbose:
        print(f"\n  [{filename}]")

    # Step 1: Detect
    if verbose:
        print(f"    Detecting...", end=" ")
    try:
        file_card = detect_file(filepath)
    except Exception as e:
        if verbose:
            print(f"FAILED: {e}")
        return None
    if verbose:
        print(f"{file_card['type']} ({file_card['category']})")

    # Skip unsupported types
    if file_card["type"] in ("archive", "image", "unknown"):
        if verbose:
            print(f"    Skipping unsupported type: {file_card['type']}")
        return None

    # Step 2: Sample (get strategy)
    if verbose:
        print(f"    Sampling...", end=" ")
    file_card = sample_file(filepath, file_card, client=client)
    strategy = file_card.get("strategy", {})
    approach = strategy.get("recommended_approach", "unknown")
    if verbose:
        print(f"{approach}")

    # Step 3: Convert
    if verbose:
        print(f"    Converting...", end=" ")
    source_id = file_card["id"]
    output_dir = config.converted_path / source_id

    try:
        converter_result = convert_file(
            filepath,
            file_card["type"],
            file_card["category"],
            output_dir=output_dir,
        )
    except Exception as e:
        if verbose:
            print(f"FAILED: {e}")
        converter_result = None

    if converter_result:
        num_files = len(converter_result.get("output_files", []))
        if verbose:
            print(f"{num_files} files")
    else:
        # Even if converter fails, continue with what we have
        if verbose:
            print("no converter (raw text fallback)")
        # Write raw text as fallback
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            raw_text = filepath.read_text(encoding="utf-8", errors="ignore")
            (output_dir / "full.txt").write_text(raw_text, encoding="utf-8")
            converter_result = {"text": raw_text, "output_files": [str(output_dir / "full.txt")]}
        except Exception:
            converter_result = None

    # Step 4: Build tree index
    if verbose:
        print(f"    Building tree...", end=" ")

    # Create catalog entry first (build_tree needs it)
    source_entry = add_source(
        catalog,
        file_card,
        converted_path=str(output_dir),
        tree_path=str(config.tree_index_path / f"{source_id}.tree.json"),
    )

    try:
        tree = build_tree_for_source(
            source_entry,
            config.converted_path,
            config.tree_index_path,
            client=client,
            converter_result=converter_result,
        )
        num_nodes = _count_nodes(tree.get("root", {}))
        if verbose:
            print(f"{num_nodes} nodes")
    except Exception as e:
        if verbose:
            print(f"FAILED: {e}")

    if verbose:
        summary = strategy.get("summary", "")[:60]
        if summary:
            print(f"    Summary: {summary}...")

    return source_entry


def _count_nodes(node: dict) -> int:
    """Count total nodes in a tree."""
    count = 1
    for child in node.get("children", []):
        count += _count_nodes(child)
    return count


def ingest(
    input_path: Path,
    config: Config,
    client=None,
    skip_vectors: bool = False,
    verbose: bool = True,
) -> dict:
    """Run the full ingest pipeline on a file or directory.

    Args:
        input_path: Path to a file or directory of files.
        config: MetadataHub Config.
        client: Optional ClaudeClient for AI-powered sampling/tree building.
        skip_vectors: If True, skip FAISS index rebuild.
        verbose: Print progress.

    Returns:
        dict with keys: processed, skipped, failed, catalog_path, vector_stats
    """
    input_path = Path(input_path).resolve()

    # Load or create catalog
    catalog = load_catalog(config.catalog_path)

    # Detect files
    if input_path.is_file():
        files = [input_path]
    elif input_path.is_dir():
        cards = detect_directory(input_path)
        files = [Path(c["path"]) for c in cards]
    else:
        raise FileNotFoundError(f"Input not found: {input_path}")

    if verbose:
        print(f"MetadataHub Ingest")
        print(f"  Store: {config.store_root}")
        print(f"  Files found: {len(files)}")

    start_time = time.time()
    processed = 0
    skipped = 0
    failed = 0

    for filepath in files:
        result = ingest_file(filepath, config, catalog, client=client, verbose=verbose)
        if result is None:
            skipped += 1
        else:
            processed += 1

    # Save catalog
    save_catalog(catalog, config.catalog_path)
    if verbose:
        print(f"\n  Catalog saved: {config.catalog_path} ({len(catalog['sources'])} sources)")

    # Build vector index
    vector_stats = None
    if not skip_vectors and processed > 0:
        if verbose:
            print(f"  Building vector index...", end=" ")
        try:
            vector_stats = build_index(catalog["sources"], config.vector_store_path)
            if verbose:
                print(f"{vector_stats['num_vectors']} vectors")
        except Exception as e:
            if verbose:
                print(f"FAILED: {e}")
            failed += 1

    elapsed = time.time() - start_time
    if verbose:
        print(f"\n  Done in {elapsed:.1f}s — {processed} processed, {skipped} skipped")

    return {
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "catalog_path": str(config.catalog_path),
        "vector_stats": vector_stats,
    }


def main():
    parser = argparse.ArgumentParser(
        description="MetadataHub batch ingest — index files into the knowledge store",
    )
    parser.add_argument(
        "input",
        type=str,
        help="Path to a file or directory to ingest",
    )
    parser.add_argument(
        "--store",
        type=str,
        default=".",
        help="Path to the MetadataHub store (default: current directory)",
    )
    parser.add_argument(
        "--no-vectors",
        action="store_true",
        help="Skip FAISS vector index rebuild",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    args = parser.parse_args()

    # Initialize config and directories
    config = init_config(args.store)

    # Try to create Claude client (optional — falls back to heuristics)
    client = None
    try:
        from scripts.claude_client import ClaudeClient
        client = ClaudeClient.from_config(config)
        # Quick check if auth is available
        _ = client.auth_header
    except Exception:
        if not args.quiet:
            print("  Note: No Claude API access — using heuristic strategies")
        client = None

    result = ingest(
        Path(args.input),
        config,
        client=client,
        skip_vectors=args.no_vectors,
        verbose=not args.quiet,
    )

    sys.exit(0 if result["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
