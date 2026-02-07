"""
LangChain + FAISS Runner

Implements the BaseRunner interface for LangChain with FAISS vector store.
"""

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional

from .base_runner import BaseRunner, IndexStats, SearchResult, get_file_size_mb


class LangChainRunner(BaseRunner):
    """
    Runner for LangChain + FAISS RAG system.
    
    LangChain configuration:
    - Embedding: HuggingFace all-MiniLM-L6-v2 (same as others)
    - Vector store: FAISS
    - Chunking: RecursiveCharacterTextSplitter
    """
    
    def __init__(self, persist_dir: Optional[str] = None):
        """
        Initialize LangChain runner.
        
        Args:
            persist_dir: Directory for FAISS index (uses temp if not specified)
        """
        super().__init__("LangChain+FAISS")
        
        if persist_dir:
            self._persist_dir = Path(persist_dir)
        else:
            self._temp_dir = tempfile.mkdtemp(prefix="langchain_bench_")
            self._persist_dir = Path(self._temp_dir)
        
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        
        self._langchain_available = self._check_availability()
        self._vectorstore = None
        self._documents = []
    
    def _check_availability(self) -> bool:
        """Check if LangChain and FAISS are installed."""
        try:
            from langchain_community.vectorstores import FAISS
            from langchain_community.embeddings import HuggingFaceEmbeddings
            from langchain_community.document_loaders import DirectoryLoader
            from langchain.text_splitter import RecursiveCharacterTextSplitter
            return True
        except ImportError as e:
            print(f"LangChain/FAISS not fully installed: {e}")
            print("Install with: pip install langchain langchain-community faiss-cpu sentence-transformers")
            return False
    
    def index(self, corpus_path: str) -> IndexStats:
        """
        Index corpus using LangChain + FAISS.
        
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
        
        if self._langchain_available:
            try:
                from langchain_community.vectorstores import FAISS
                from langchain_community.embeddings import HuggingFaceEmbeddings
                from langchain_community.document_loaders import (
                    DirectoryLoader,
                    TextLoader,
                    UnstructuredMarkdownLoader,
                )
                from langchain.text_splitter import RecursiveCharacterTextSplitter
                from langchain.schema import Document
                
                # Use same embedding model for fair comparison
                embeddings = HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-MiniLM-L6-v2"
                )
                
                # Load documents manually for better control
                documents = []
                for file_path in corpus.rglob("*"):
                    if file_path.is_file() and not file_path.name.startswith("."):
                        if file_path.suffix in [".md", ".py", ".txt", ".json"]:
                            try:
                                content = file_path.read_text(encoding="utf-8")
                                doc = Document(
                                    page_content=content,
                                    metadata={
                                        "source": str(file_path),
                                        "file_name": file_path.name,
                                        "file_type": file_path.suffix
                                    }
                                )
                                documents.append(doc)
                            except Exception as e:
                                print(f"Warning: Could not load {file_path}: {e}")
                
                # Split into chunks
                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=1000,
                    chunk_overlap=200,
                    length_function=len,
                )
                
                split_docs = text_splitter.split_documents(documents)
                chunk_count = len(split_docs)
                
                # Create FAISS index
                if split_docs:
                    self._vectorstore = FAISS.from_documents(
                        split_docs,
                        embeddings
                    )
                    
                    # Save index
                    self._vectorstore.save_local(str(self._persist_dir))
                
                self._documents = documents
                
            except Exception as e:
                print(f"LangChain indexing error: {e}")
                import traceback
                traceback.print_exc()
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
                "indexer": "LangChain+FAISS",
                "chunk_size": 1000,
                "chunk_overlap": 200
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
        Search using LangChain + FAISS.
        
        Args:
            query: Search query
            top_k: Number of results
            
        Returns:
            List of SearchResult
        """
        if not self._is_indexed:
            raise RuntimeError("Must call index() before search()")
        
        results = []
        
        if self._langchain_available and self._vectorstore is not None:
            try:
                # Search with scores
                docs_with_scores = self._vectorstore.similarity_search_with_score(
                    query,
                    k=top_k
                )
                
                for doc, score in docs_with_scores:
                    # FAISS returns L2 distance, convert to similarity
                    # Lower distance = higher similarity
                    similarity = 1 / (1 + score)
                    
                    source = doc.metadata.get("file_name", "unknown")
                    
                    results.append(SearchResult(
                        source=source,
                        content=doc.page_content[:500],
                        score=similarity,
                        metadata=doc.metadata
                    ))
                    
            except Exception as e:
                print(f"LangChain search error: {e}")
        
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
        """Get FAISS index size."""
        return get_file_size_mb(self._persist_dir)
    
    def cleanup(self) -> None:
        """Clean up temporary files."""
        if hasattr(self, "_temp_dir") and os.path.exists(self._temp_dir):
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        self._vectorstore = None
        self._is_indexed = False
