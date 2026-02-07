"""
MetadataHub Runner

Implements the BaseRunner interface for MetadataHub.
Uses MetadataHub's hybrid vector + tree retrieval.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from .base_runner import BaseRunner, IndexStats, SearchResult, get_file_size_mb


class MetadataHubRunner(BaseRunner):
    """
    Runner for MetadataHub RAG system.
    
    MetadataHub uses:
    - sentence-transformers for embeddings (local)
    - FAISS for vector search
    - Tree index for hierarchical navigation
    """
    
    def __init__(self, store_path: Optional[str] = None):
        """
        Initialize MetadataHub runner.
        
        Args:
            store_path: Path for MetadataHub store (uses temp dir if not specified)
        """
        super().__init__("MetadataHub")
        
        # Determine store path
        if store_path:
            self._store_path = Path(store_path)
        else:
            self._temp_dir = tempfile.mkdtemp(prefix="metadatahub_bench_")
            self._store_path = Path(self._temp_dir) / "store"
        
        self._store_path.mkdir(parents=True, exist_ok=True)
        
        # Get the repo root (parent of benchmark/)
        self._repo_root = Path(__file__).parent.parent.parent
        
        # Try to import MetadataHub modules
        self._mhub_available = self._check_availability()
    
    def _check_availability(self) -> bool:
        """Check if MetadataHub is available."""
        try:
            # Add scripts to path
            scripts_path = self._repo_root / "scripts"
            if str(scripts_path) not in sys.path:
                sys.path.insert(0, str(scripts_path))
            
            # Try importing key modules
            from build_vectors import VectorIndexBuilder
            from catalog import Catalog
            return True
        except ImportError as e:
            print(f"MetadataHub not fully available: {e}")
            return False
    
    def index(self, corpus_path: str) -> IndexStats:
        """
        Index corpus using MetadataHub's ingest pipeline.
        
        Args:
            corpus_path: Path to corpus directory
            
        Returns:
            IndexStats with indexing information
        """
        corpus = Path(corpus_path)
        if not corpus.exists():
            raise ValueError(f"Corpus path does not exist: {corpus_path}")
        
        start_time = time.perf_counter()
        
        # Count documents
        doc_count = sum(1 for _ in corpus.rglob("*") if _.is_file() and not _.name.startswith("."))
        
        if self._mhub_available:
            # Use MetadataHub's ingest script
            ingest_script = self._repo_root / "scripts" / "ingest.py"
            
            if ingest_script.exists():
                result = subprocess.run(
                    [
                        sys.executable, "-m", "scripts.ingest",
                        str(corpus),
                        "--store", str(self._store_path),
                        "--no-ai"  # Use heuristic mode for benchmark consistency
                    ],
                    capture_output=True,
                    text=True,
                    cwd=str(self._repo_root)
                )
                
                if result.returncode != 0:
                    print(f"Ingest warning: {result.stderr}")
        else:
            # Fallback: Create a simple index manually
            self._create_simple_index(corpus)
        
        index_time = time.perf_counter() - start_time
        
        # Get chunk count from catalog if available
        chunk_count = self._get_chunk_count()
        
        self._index_stats = IndexStats(
            num_documents=doc_count,
            num_chunks=chunk_count,
            index_size_mb=self.get_index_size_mb(),
            index_time_seconds=index_time,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            additional_info={
                "store_path": str(self._store_path),
                "indexer": "MetadataHub"
            }
        )
        
        self._is_indexed = True
        return self._index_stats
    
    def _create_simple_index(self, corpus: Path) -> None:
        """Create a simple index when full MetadataHub isn't available."""
        # Store document content for simple search
        self._simple_docs = {}
        
        for file_path in corpus.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith("."):
                try:
                    if file_path.suffix in [".md", ".py", ".txt", ".json"]:
                        content = file_path.read_text(encoding="utf-8")
                        self._simple_docs[file_path.name] = content
                except Exception as e:
                    print(f"Warning: Could not read {file_path}: {e}")
    
    def _get_chunk_count(self) -> int:
        """Get number of chunks in the index."""
        catalog_path = self._store_path / "catalog.json"
        if catalog_path.exists():
            try:
                with open(catalog_path) as f:
                    catalog = json.load(f)
                    return sum(
                        len(entry.get("chunks", []))
                        for entry in catalog.get("sources", {}).values()
                    )
            except Exception:
                pass
        
        # Fallback
        return len(getattr(self, "_simple_docs", {}))
    
    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """
        Search using MetadataHub.
        
        Args:
            query: Search query
            top_k: Number of results
            
        Returns:
            List of SearchResult
        """
        if not self._is_indexed:
            raise RuntimeError("Must call index() before search()")
        
        results = []
        
        if self._mhub_available:
            # Use MetadataHub's search
            try:
                search_script = self._repo_root / "skills" / "metadatahub-search" / "scripts" / "mhub.py"
                
                if search_script.exists():
                    result = subprocess.run(
                        [
                            sys.executable, str(search_script),
                            query,
                            "--store", str(self._store_path),
                            "--top-k", str(top_k),
                            "--format", "json"
                        ],
                        capture_output=True,
                        text=True,
                        cwd=str(self._repo_root)
                    )
                    
                    if result.returncode == 0 and result.stdout.strip():
                        try:
                            search_results = json.loads(result.stdout)
                            for r in search_results.get("results", [])[:top_k]:
                                results.append(SearchResult(
                                    source=r.get("source", "unknown"),
                                    content=r.get("content", "")[:500],
                                    score=r.get("score", 0.0),
                                    metadata=r.get("metadata", {})
                                ))
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                print(f"MetadataHub search error: {e}")
        
        # Fallback to simple search
        if not results and hasattr(self, "_simple_docs"):
            results = self._simple_search(query, top_k)
        
        return results
    
    def _simple_search(self, query: str, top_k: int) -> list[SearchResult]:
        """Simple keyword-based search fallback."""
        query_terms = set(query.lower().split())
        scored = []
        
        for filename, content in self._simple_docs.items():
            content_lower = content.lower()
            # Simple TF scoring
            score = sum(
                content_lower.count(term) / len(content_lower) * 100
                for term in query_terms
            )
            if score > 0:
                scored.append((filename, content, score))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[2], reverse=True)
        
        return [
            SearchResult(
                source=filename,
                content=content[:500],
                score=min(score / 10, 1.0),  # Normalize
                metadata={"method": "keyword_fallback"}
            )
            for filename, content, score in scored[:top_k]
        ]
    
    def get_index_size_mb(self) -> float:
        """Get MetadataHub store size."""
        return get_file_size_mb(self._store_path)
    
    def cleanup(self) -> None:
        """Clean up temporary files."""
        if hasattr(self, "_temp_dir") and os.path.exists(self._temp_dir):
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        self._is_indexed = False
