"""FAISS vector index builder.

Builds a vector index from catalog metadata cards using sentence-transformers.
One embedding per document (from summary + tags + title), stored as:
  vector_store/index.faiss
  vector_store/metadata.json

Small and fast — designed for source-level retrieval (Tier 1).
"""

import json
from pathlib import Path
from typing import Optional

import numpy as np

# Lazy imports to avoid slow load times when not needed
_model = None
_EMBED_DIM = None


def _get_model():
    """Lazy-load the sentence-transformers model."""
    global _model, _EMBED_DIM
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        _EMBED_DIM = _model.get_sentence_embedding_dimension()
    return _model


def get_embedding_dim() -> int:
    """Return the embedding dimension of the model."""
    global _EMBED_DIM
    if _EMBED_DIM is None:
        _get_model()
    return _EMBED_DIM


def _build_embed_text(source: dict) -> str:
    """Build the text to embed for a catalog source entry.

    Combines title/filename, summary, tags, and doc_nature into
    a single string optimized for semantic search.
    """
    parts = []

    # Title / filename
    title = source.get("filename", "")
    if title:
        parts.append(title)

    # Doc nature
    doc_nature = source.get("doc_nature", "")
    if doc_nature:
        parts.append(doc_nature.replace("_", " "))

    # Summary (most important signal)
    summary = source.get("summary", "")
    if summary:
        parts.append(summary)

    # Tags
    tags = source.get("tags", [])
    if tags:
        parts.append("Tags: " + ", ".join(tags))

    # Type + category
    file_type = source.get("type", "")
    category = source.get("category", "")
    if file_type or category:
        parts.append(f"Type: {file_type} ({category})")

    return ". ".join(parts)


def embed_sources(sources: list[dict]) -> tuple[np.ndarray, list[dict]]:
    """Compute embeddings for a list of catalog source entries.

    Args:
        sources: List of source dicts from catalog.json.

    Returns:
        Tuple of (embeddings array [N x dim], metadata list).
        Metadata list preserves order and maps index → source info.
    """
    model = _get_model()

    texts = []
    metadata = []

    for source in sources:
        text = _build_embed_text(source)
        texts.append(text)
        metadata.append({
            "id": source["id"],
            "filename": source.get("filename", ""),
            "summary": source.get("summary", ""),
            "type": source.get("type", ""),
            "category": source.get("category", ""),
            "tags": source.get("tags", []),
        })

    if not texts:
        dim = get_embedding_dim()
        return np.zeros((0, dim), dtype=np.float32), []

    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.array(embeddings, dtype=np.float32), metadata


def build_index(
    sources: list[dict],
    vector_store_dir: Path,
) -> dict:
    """Build a FAISS index from catalog sources and save to disk.

    Args:
        sources: List of source dicts from catalog.json.
        vector_store_dir: Directory to write index.faiss + metadata.json.

    Returns:
        dict with keys: num_vectors, dimension, index_path, metadata_path
    """
    import faiss

    vector_store_dir = Path(vector_store_dir)
    vector_store_dir.mkdir(parents=True, exist_ok=True)

    embeddings, metadata = embed_sources(sources)

    if len(embeddings) == 0:
        dim = get_embedding_dim()
        index = faiss.IndexFlatIP(dim)
    else:
        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)

    # Save FAISS index
    index_path = vector_store_dir / "index.faiss"
    faiss.write_index(index, str(index_path))

    # Save metadata
    metadata_path = vector_store_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    return {
        "num_vectors": index.ntotal,
        "dimension": dim,
        "index_path": str(index_path),
        "metadata_path": str(metadata_path),
    }


def search(
    query: str,
    vector_store_dir: Path,
    top_k: int = 5,
) -> list[dict]:
    """Search the FAISS index for sources matching a query.

    Args:
        query: Natural language search query.
        vector_store_dir: Directory containing index.faiss + metadata.json.
        top_k: Number of results to return.

    Returns:
        List of dicts with keys: id, filename, summary, score, rank
    """
    import faiss

    vector_store_dir = Path(vector_store_dir)
    index_path = vector_store_dir / "index.faiss"
    metadata_path = vector_store_dir / "metadata.json"

    if not index_path.exists() or not metadata_path.exists():
        return []

    index = faiss.read_index(str(index_path))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    if index.ntotal == 0:
        return []

    model = _get_model()
    query_vec = model.encode([query], normalize_embeddings=True)
    query_vec = np.array(query_vec, dtype=np.float32)

    k = min(top_k, index.ntotal)
    scores, indices = index.search(query_vec, k)

    results = []
    for rank, (score, idx) in enumerate(zip(scores[0], indices[0])):
        if idx < 0 or idx >= len(metadata):
            continue
        entry = metadata[idx].copy()
        entry["score"] = float(score)
        entry["rank"] = rank + 1
        results.append(entry)

    return results


def add_to_index(
    sources: list[dict],
    vector_store_dir: Path,
) -> dict:
    """Add new sources to an existing FAISS index.

    If no index exists, creates a new one.

    Args:
        sources: New source dicts to add.
        vector_store_dir: Directory containing the index.

    Returns:
        dict with updated index stats.
    """
    import faiss

    vector_store_dir = Path(vector_store_dir)
    index_path = vector_store_dir / "index.faiss"
    metadata_path = vector_store_dir / "metadata.json"

    # Load existing or create new
    if index_path.exists() and metadata_path.exists():
        index = faiss.read_index(str(index_path))
        existing_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    else:
        dim = get_embedding_dim()
        index = faiss.IndexFlatIP(dim)
        existing_metadata = []

    # Filter out sources already in the index
    existing_ids = {m["id"] for m in existing_metadata}
    new_sources = [s for s in sources if s["id"] not in existing_ids]

    if not new_sources:
        return {
            "num_vectors": index.ntotal,
            "added": 0,
            "index_path": str(index_path),
        }

    embeddings, new_metadata = embed_sources(new_sources)

    if len(embeddings) > 0:
        index.add(embeddings)
        existing_metadata.extend(new_metadata)

    # Save
    vector_store_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_path))
    metadata_path.write_text(
        json.dumps(existing_metadata, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    return {
        "num_vectors": index.ntotal,
        "added": len(new_sources),
        "index_path": str(index_path),
    }
