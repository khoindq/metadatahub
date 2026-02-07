"""Cross-source linking - find related documents using embeddings and keywords."""

import json
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np


def extract_keywords(text: str) -> set[str]:
    """Extract keywords from text (simple tokenization)."""
    # Simple keyword extraction - lowercase, split, filter short words
    words = text.lower().split()
    # Filter out common words and short tokens
    stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 
                 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                 'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                 'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through',
                 'and', 'or', 'but', 'if', 'because', 'until', 'while', 'this',
                 'that', 'these', 'those', 'it', 'its'}
    
    keywords = set()
    for word in words:
        # Clean punctuation
        clean = ''.join(c for c in word if c.isalnum())
        if len(clean) > 3 and clean not in stopwords:
            keywords.add(clean)
    
    return keywords


def compute_keyword_similarity(keywords1: set[str], keywords2: set[str]) -> float:
    """Compute Jaccard similarity between keyword sets."""
    if not keywords1 or not keywords2:
        return 0.0
    intersection = len(keywords1 & keywords2)
    union = len(keywords1 | keywords2)
    return intersection / union if union > 0 else 0.0


def find_related_sources(
    store_root: Path,
    min_similarity: float = 0.1,
    max_links: int = 5
) -> Dict[str, List[Dict]]:
    """
    Find related sources based on embedding similarity and keywords.
    
    Returns:
        Dict mapping source_id -> list of related sources with scores
    """
    catalog_file = store_root / "catalog.json"
    if not catalog_file.exists():
        return {}
    
    with open(catalog_file) as f:
        catalog = json.load(f)
    
    sources = catalog.get("sources", [])
    if len(sources) < 2:
        return {}
    
    # Extract keywords for each source
    source_keywords = {}
    for source in sources:
        text = f"{source.get('summary', '')} {' '.join(source.get('tags', []))}"
        source_keywords[source['id']] = extract_keywords(text)
    
    # Try to load vectors for embedding similarity
    vector_store = store_root / "vector_store"
    embeddings = {}
    
    if (vector_store / "id_map.json").exists():
        try:
            import faiss
            
            with open(vector_store / "id_map.json") as f:
                id_map = json.load(f)
            
            index = faiss.read_index(str(vector_store / "index.faiss"))
            
            # Reconstruct vectors
            for i, source_id in enumerate(id_map):
                embeddings[source_id] = index.reconstruct(i)
        except Exception:
            pass  # Fall back to keyword-only similarity
    
    # Compute pairwise similarities
    related = {}
    
    for i, source1 in enumerate(sources):
        id1 = source1['id']
        similarities = []
        
        for j, source2 in enumerate(sources):
            if i == j:
                continue
            
            id2 = source2['id']
            
            # Keyword similarity
            kw_sim = compute_keyword_similarity(
                source_keywords.get(id1, set()),
                source_keywords.get(id2, set())
            )
            
            # Embedding similarity (if available)
            emb_sim = 0.0
            if id1 in embeddings and id2 in embeddings:
                vec1 = embeddings[id1]
                vec2 = embeddings[id2]
                # Cosine similarity
                dot = np.dot(vec1, vec2)
                norm1 = np.linalg.norm(vec1)
                norm2 = np.linalg.norm(vec2)
                if norm1 > 0 and norm2 > 0:
                    emb_sim = dot / (norm1 * norm2)
            
            # Combined score (weighted average)
            combined = 0.4 * kw_sim + 0.6 * emb_sim if emb_sim > 0 else kw_sim
            
            if combined >= min_similarity:
                similarities.append({
                    "id": id2,
                    "filename": source2.get("filename", ""),
                    "score": round(combined, 3),
                    "keyword_sim": round(kw_sim, 3),
                    "embedding_sim": round(emb_sim, 3) if emb_sim > 0 else None
                })
        
        # Sort by score and limit
        similarities.sort(key=lambda x: x["score"], reverse=True)
        related[id1] = similarities[:max_links]
    
    return related


def update_catalog_links(store_root: Path, links: Dict[str, List[Dict]]):
    """Update catalog.json with cross-source links."""
    catalog_file = store_root / "catalog.json"
    if not catalog_file.exists():
        return
    
    with open(catalog_file) as f:
        catalog = json.load(f)
    
    for source in catalog.get("sources", []):
        source_id = source["id"]
        if source_id in links:
            source["related"] = links[source_id]
    
    with open(catalog_file, 'w') as f:
        json.dump(catalog, f, indent=2)


def link_sources(store_root: Path, min_similarity: float = 0.1, max_links: int = 5):
    """Main function to compute and store cross-source links."""
    print("Computing cross-source links...")
    links = find_related_sources(store_root, min_similarity, max_links)
    
    total_links = sum(len(v) for v in links.values())
    print(f"Found {total_links} links across {len(links)} sources")
    
    update_catalog_links(store_root, links)
    print("Updated catalog.json with links")
    
    return links


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Find related documents")
    parser.add_argument("--store", type=Path, default=Path.home() / ".metadatahub" / "store")
    parser.add_argument("--min-similarity", type=float, default=0.1)
    parser.add_argument("--max-links", type=int, default=5)
    
    args = parser.parse_args()
    link_sources(args.store, args.min_similarity, args.max_links)
