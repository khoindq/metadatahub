"""
LlamaIndex Runner

Implements the BaseRunner interface for LlamaIndex.
Uses LlamaIndex's VectorStoreIndex with default settings.
"""

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional

from .base_runner import BaseRunner, IndexStats, SearchResult, get_file_size_mb


class LlamaIndexRunner(BaseRunner):
    """
    Runner for LlamaIndex RAG system.
    
    LlamaIndex configuration:
    - Embedding: HuggingFace all-MiniLM-L6-v2 (same as MetadataHub)
    - Vector store: Simple in-memory or persistent
    - Chunking: Default sentence splitter
    """
    
    def __init__(self, persist_dir: Optional[str] = None):
        """
        Initialize LlamaIndex runner.
        
        Args:
            persist_dir: Directory for persistent storage (uses temp if not specified)
        """
        super().__init__("LlamaIndex")
        
        if persist_dir:
            self._persist_dir = Path(persist_dir)
        else:
            self._temp_dir = tempfile.mkdtemp(prefix="llamaindex_bench_")
            self._persist_dir = Path(self._temp_dir)
        
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        
        # Lazy import to check availability
        self._llamaindex_available = self._check_availability()
        self._index = None
        self._documents = []
    
    def _check_availability(self) -> bool:
        """Check if LlamaIndex is installed."""
        try:
            from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
            from llama_index.core import Settings
            return True
        except ImportError:
            print("LlamaIndex not installed. Install with: pip install llama-index")
            return False
    
    def index(self, corpus_path: str) -> IndexStats:
        """
        Index corpus using LlamaIndex.
        
        Args:
            corpus_path: Path to corpus directory
            
        Returns:
            IndexStats
        """
        corpus = Path(corpus_path)
        if not corpus.exists():
            raise ValueError(f"Corpus path does not exist: {corpus_path}")
        
        start_time = time.perf_counter()
        
        # Count documents
        doc_files = list(corpus.rglob("*"))
        doc_files = [f for f in doc_files if f.is_file() and not f.name.startswith(".")]
        doc_count = len(doc_files)
        
        chunk_count = 0
        
        if self._llamaindex_available:
            try:
                from llama_index.core import (
                    VectorStoreIndex,
                    SimpleDirectoryReader,
                    Settings,
                    StorageContext,
                )
                from llama_index.embeddings.huggingface import HuggingFaceEmbedding
                
                # Use same embedding model as MetadataHub for fair comparison
                Settings.embed_model = HuggingFaceEmbedding(
                    model_name="sentence-transformers/all-MiniLM-L6-v2"
                )
                
                # Disable LLM (we only need retrieval)
                Settings.llm = None
                
                # Load documents
                reader = SimpleDirectoryReader(
                    input_dir=str(corpus),
                    recursive=True,
                    exclude_hidden=True,
                    required_exts=[".md", ".py", ".txt", ".json"]
                )
                self._documents = reader.load_data()
                
                # Create index
                self._index = VectorStoreIndex.from_documents(
                    self._documents,
                    show_progress=False
                )
                
                # Persist
                self._index.storage_context.persist(persist_dir=str(self._persist_dir))
                
                chunk_count = len(self._documents)
                
            except Exception as e:
                print(f"LlamaIndex indexing error: {e}")
                self._create_simple_index(corpus)
                chunk_count = len(self._simple_docs)
        else:
            self._create_simple_index(corpus)
            chunk_count = len(self._simple_docs)
        
        index_time = time.perf_counter() - start_time
        
        self._index_stats = IndexStats(
            num_documents=doc_count,
            num_chunks=chunk_count,
            index_size_mb=self.get_index_size_mb(),
            index_time_seconds=index_time,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            additional_info={
                "persist_dir": str(self._persist_dir),
                "indexer": "LlamaIndex"
            }
        )
        
        self._is_indexed = True
        return self._index_stats
    
    def _create_simple_index(self, corpus: Path) -> None:
        """Fallback simple index."""
        self._simple_docs = {}
        
        for file_path in corpus.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith("."):
                try:
                    if file_path.suffix in [".md", ".py", ".txt", ".json"]:
                        content = file_path.read_text(encoding="utf-8")
                        self._simple_docs[file_path.name] = content
                except Exception as e:
                    print(f"Warning: Could not read {file_path}: {e}")
    
    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """
        Search using LlamaIndex.
        
        Args:
            query: Search query
            top_k: Number of results
            
        Returns:
            List of SearchResult
        """
        if not self._is_indexed:
            raise RuntimeError("Must call index() before search()")
        
        results = []
        
        if self._llamaindex_available and self._index is not None:
            try:
                # Create retriever
                retriever = self._index.as_retriever(similarity_top_k=top_k)
                
                # Retrieve
                nodes = retriever.retrieve(query)
                
                for node in nodes:
                    # Extract source filename
                    metadata = node.metadata or {}
                    source = metadata.get("file_name", "unknown")
                    if not source or source == "unknown":
                        source = metadata.get("file_path", "unknown")
                        if source != "unknown":
                            source = Path(source).name
                    
                    results.append(SearchResult(
                        source=source,
                        content=node.text[:500] if node.text else "",
                        score=node.score if node.score else 0.0,
                        metadata=metadata
                    ))
                    
            except Exception as e:
                print(f"LlamaIndex search error: {e}")
        
        # Fallback
        if not results and hasattr(self, "_simple_docs"):
            results = self._simple_search(query, top_k)
        
        return results
    
    def _simple_search(self, query: str, top_k: int) -> list[SearchResult]:
        """Simple keyword search fallback."""
        query_terms = set(query.lower().split())
        scored = []
        
        for filename, content in self._simple_docs.items():
            content_lower = content.lower()
            score = sum(
                content_lower.count(term) / len(content_lower) * 100
                for term in query_terms
            )
            if score > 0:
                scored.append((filename, content, score))
        
        scored.sort(key=lambda x: x[2], reverse=True)
        
        return [
            SearchResult(
                source=filename,
                content=content[:500],
                score=min(score / 10, 1.0),
                metadata={"method": "keyword_fallback"}
            )
            for filename, content, score in scored[:top_k]
        ]
    
    def get_index_size_mb(self) -> float:
        """Get LlamaIndex storage size."""
        return get_file_size_mb(self._persist_dir)
    
    def cleanup(self) -> None:
        """Clean up temporary files."""
        if hasattr(self, "_temp_dir") and os.path.exists(self._temp_dir):
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        self._index = None
        self._is_indexed = False
