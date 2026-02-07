"""
Base Runner Interface

Abstract base class that all RAG system runners must implement.
Provides a unified interface for indexing and searching across different systems.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import time


@dataclass
class SearchResult:
    """Standardized search result across all systems."""
    source: str  # Filename or document ID
    content: str  # Retrieved text content
    score: float  # Relevance score (0-1, higher is better)
    metadata: dict = field(default_factory=dict)  # Additional metadata
    
    def __repr__(self) -> str:
        return f"SearchResult(source='{self.source}', score={self.score:.4f})"


@dataclass 
class IndexStats:
    """Statistics about the index."""
    num_documents: int
    num_chunks: int
    index_size_mb: float
    index_time_seconds: float
    embedding_model: str
    additional_info: dict = field(default_factory=dict)


class BaseRunner(ABC):
    """
    Abstract base class for RAG system runners.
    
    Each runner must implement:
    - index(): Build index from corpus
    - search(): Search the index
    - get_index_size_mb(): Report index size
    - cleanup(): Clean up resources
    """
    
    def __init__(self, name: str):
        """
        Initialize the runner.
        
        Args:
            name: Human-readable name of this runner
        """
        self.name = name
        self._index_stats: Optional[IndexStats] = None
        self._is_indexed = False
    
    @abstractmethod
    def index(self, corpus_path: str) -> IndexStats:
        """
        Build an index from the corpus.
        
        Args:
            corpus_path: Path to the corpus directory
            
        Returns:
            IndexStats with information about the created index
        """
        pass
    
    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """
        Search the index for relevant documents.
        
        Args:
            query: Search query string
            top_k: Maximum number of results to return
            
        Returns:
            List of SearchResult objects, sorted by relevance (highest first)
        """
        pass
    
    @abstractmethod
    def get_index_size_mb(self) -> float:
        """
        Get the size of the index in megabytes.
        
        Returns:
            Size in MB
        """
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """Clean up any resources (temporary files, etc.)."""
        pass
    
    def timed_search(self, query: str, top_k: int = 5) -> tuple[list[SearchResult], float]:
        """
        Search with timing.
        
        Args:
            query: Search query
            top_k: Number of results
            
        Returns:
            Tuple of (results, latency_ms)
        """
        start = time.perf_counter()
        results = self.search(query, top_k)
        latency_ms = (time.perf_counter() - start) * 1000
        return results, latency_ms
    
    @property
    def is_indexed(self) -> bool:
        """Check if the corpus has been indexed."""
        return self._is_indexed
    
    @property
    def index_stats(self) -> Optional[IndexStats]:
        """Get index statistics."""
        return self._index_stats
    
    def __repr__(self) -> str:
        status = "indexed" if self._is_indexed else "not indexed"
        return f"{self.__class__.__name__}(name='{self.name}', status={status})"


def normalize_score(score: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """
    Normalize a score to [0, 1] range.
    
    Args:
        score: Raw score
        min_val: Expected minimum value
        max_val: Expected maximum value
        
    Returns:
        Normalized score between 0 and 1
    """
    if max_val == min_val:
        return 0.5
    normalized = (score - min_val) / (max_val - min_val)
    return max(0.0, min(1.0, normalized))


def get_file_size_mb(path: Path) -> float:
    """
    Get total size of a file or directory in MB.
    
    Args:
        path: Path to file or directory
        
    Returns:
        Size in megabytes
    """
    if path.is_file():
        return path.stat().st_size / (1024 * 1024)
    elif path.is_dir():
        total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return total / (1024 * 1024)
    return 0.0
